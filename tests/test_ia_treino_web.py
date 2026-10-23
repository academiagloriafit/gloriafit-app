"""Treino sob medida pela web: as rotas de app/web.py e o cartão da tela de lançar treino. Dados inventados.

A API da Anthropic é sempre trocada por uma falsa (`app.config["IA_CHAMADA"]`) e o trabalho roda sem fio
(`IA_EM_SEGUNDO_PLANO = False`): nenhum teste fala com a internet nem gasta um centavo.
"""

import html as html_do_python
import json
import re

import pytest

from app import acesso, ia_treino
from app.db import conectar, criar_tabelas
from app.web import criar_app

CHAVE = "sk-ant-chave-de-teste-0123456789abcdef"
PEDIDO = {"objetivo": "hipertrofia", "nivel": "iniciante", "dias": 2, "minutos": 60, "observacoes": "dor no joelho"}


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "ia.db"
    c = conectar(caminho)
    criar_tabelas(c)
    c.execute("INSERT INTO aluno (id, nome, cpf) VALUES (1, 'ANA FICTICIA', '12345678909'), (2, 'BRUNO FICTICIO', NULL)")
    c.execute("INSERT INTO exercicio (id, nome, origem, usos_ultimo_ano) VALUES (1, '(3) SUPINO RETO', 'app', 50), (2, 'REMADA', 'app', 50)")
    c.commit()
    c.close()
    ia_treino.guardar_chave(tmp_path / "ia_chave", CHAVE)
    return caminho


def _rascunho():
    return {
        "stop_reason": "tool_use",
        "content": [
            {
                "type": "tool_use",
                "name": "montar_treino",
                "input": {
                    "fichas": [
                        {"nome": "A - PEITO", "itens": [{"exercicio_id": 1, "series": "3", "repeticoes": "12"}]},
                        {"nome": "B - COSTAS", "itens": [{"exercicio_id": 2, "series": "3", "repeticoes": "10"}]},
                    ],
                    "resumo": "Duas fichas simples.",
                    "alertas": ["Joelho: o professor deve avaliar."],
                },
            }
        ],
        "usage": {"input_tokens": 5000, "output_tokens": 700},
    }


class IAFalsa:
    def __init__(self, devolve=None, levanta=None):
        self.devolve = devolve or _rascunho()
        self.levanta = levanta
        self.chamadas = 0
        self.corpos = []  # o que a IA recebeu em cada chamada

    def __call__(self, chave, corpo, *_a, **_k):
        self.chamadas += 1
        self.corpos.append(corpo)
        if self.levanta:
            raise self.levanta
        return self.devolve


@pytest.fixture
def ia():
    return IAFalsa()


@pytest.fixture
def app(caminho, ia):
    aplicativo = criar_app(caminho)
    aplicativo.config["IA_CHAMADA"] = ia
    aplicativo.config["IA_EM_SEGUNDO_PLANO"] = False
    return aplicativo


@pytest.fixture
def anonimo(app):
    return app.test_client()


@pytest.fixture
def cliente(app, caminho):
    navegador = app.test_client()
    c = conectar(caminho)
    codigo = acesso.gerar_codigo(c, "Computador de teste").codigo
    token = acesso.autorizar(c, codigo).token
    c.close()
    navegador.set_cookie(acesso.NOME_DO_COOKIE, token)
    return navegador


def _pedir(cliente, aluno=1, **extras):
    return cliente.post(f"/api/alunos/{aluno}/treino-ia", json={**PEDIDO, **extras})


# ------------------------------------------------------------------ pedir um rascunho


def test_pedir_devolve_o_numero_do_pedido_e_depois_o_rascunho(cliente, ia):
    resposta = _pedir(cliente)

    assert resposta.status_code == 202
    pedido_id = resposta.get_json()["pedido_id"]
    assert ia.chamadas == 1
    lido = cliente.get(f"/api/alunos/1/treino-ia/{pedido_id}")
    assert lido.status_code == 200
    corpo = lido.get_json()
    assert corpo["situacao"] == "pronto"
    assert [f["nome"] for f in corpo["treino"]["fichas"]] == ["A - PEITO", "B - COSTAS"]
    assert corpo["treino"]["fichas"][0]["itens"][0]["nome"] == "SUPINO RETO"
    assert corpo["resumo"] == "Duas fichas simples." and corpo["alertas"] == ["Joelho: o professor deve avaliar."]


def test_pedir_nao_grava_treino_nenhum_para_o_aluno(cliente, caminho):
    _pedir(cliente)

    c = conectar(caminho)
    try:
        assert c.execute("SELECT COUNT(*) FROM treino").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM ficha_item").fetchone()[0] == 0
    finally:
        c.close()


def test_a_resposta_da_ia_com_erro_chega_como_erro_em_portugues(cliente, app):
    app.config["IA_CHAMADA"] = IAFalsa(levanta=ia_treino.ErroDaIA("A IA está fora do ar ou ocupada agora.", "HTTP 529"))

    pedido_id = _pedir(cliente).get_json()["pedido_id"]

    assert cliente.get(f"/api/alunos/1/treino-ia/{pedido_id}").get_json() == {
        "situacao": "erro",
        "erro": "A IA está fora do ar ou ocupada agora.",
    }


@pytest.mark.parametrize(
    "mudanca",
    [
        {"objetivo": "x"},
        {"nivel": None},
        {"dias": 9},
        {"minutos": 5},
        {"observacoes": "meu cpf 123.456.789-09"},
        {"observacoes": "x" * (ia_treino.LIMITE_DAS_OBSERVACOES + 1)},
        {"fichas_diferentes": 1},
        {"fichas_diferentes": "3"},
        {"dias": 3, "fichas_diferentes": 4},  # mais fichas diferentes do que dias
    ],
)
def test_pedido_invalido_devolve_400_com_os_motivos(cliente, ia, mudanca):
    resposta = _pedir(cliente, **mudanca)

    assert resposta.status_code == 400
    assert resposta.get_json()["erros"] and ia.chamadas == 0


def test_corpo_que_nao_e_json_devolve_415(cliente):
    assert cliente.post("/api/alunos/1/treino-ia", data="objetivo=x").status_code == 415


def test_aluno_que_nao_existe_devolve_404(cliente, ia):
    assert _pedir(cliente, aluno=999).status_code == 404
    assert ia.chamadas == 0


@pytest.mark.parametrize("fila_id", [4, 5])
def test_aluno_de_fila_com_liberacao_devolve_409_sem_gastar(cliente, caminho, ia, fila_id):
    c = conectar(caminho)
    c.execute(
        "INSERT INTO aluno_fila (aluno_id, fila_id, definida_por, liberacao_em, liberacao_por) VALUES (1, ?, 'Ana', '2026-10-01', 'Ana')", (fila_id,)
    )
    c.commit()
    c.close()

    resposta = _pedir(cliente)

    assert resposta.status_code == 409 and resposta.get_json()["bloqueio"] == "fila_com_liberacao"
    assert ia.chamadas == 0


def test_observacao_de_gravidez_devolve_409_sem_gastar(cliente, ia):
    resposta = _pedir(cliente, observacoes="aluna gestante")

    assert resposta.status_code == 409 and resposta.get_json()["bloqueio"] == "gravidez"
    assert ia.chamadas == 0


def test_sem_a_chave_devolve_503_e_a_tela_sabe_que_nao_esta_ligado(cliente, caminho, ia):
    (caminho.parent / "ia_chave").unlink()

    resposta = _pedir(cliente)

    assert resposta.status_code == 503 and resposta.get_json()["configurada"] is False
    assert ia.chamadas == 0


def test_pedidos_demais_no_dia_devolve_429(cliente, caminho):
    for _ in range(ia_treino.LIMITE_DE_PEDIDOS_POR_DIA):
        assert _pedir(cliente).status_code == 202

    resposta = _pedir(cliente)

    assert resposta.status_code == 429 and "limite do dia" in resposta.get_json()["erro"]


# ---- a conversa: a IA pergunta, o professor responde, a IA monta


def _perguntas_da_ia(*perguntas):
    return {
        "stop_reason": "tool_use",
        "content": [{"type": "tool_use", "name": "fazer_perguntas", "input": {"perguntas": list(perguntas)}}],
        "usage": {"input_tokens": 4000, "output_tokens": 200},
    }


def test_a_ia_pergunta_o_professor_responde_e_a_ia_monta(cliente, app):
    ia = IAFalsa(devolve=_perguntas_da_ia("Qual o foco?", "Tem alguma lesão?"))
    app.config["IA_CHAMADA"] = ia

    primeiro = _pedir(cliente, perguntar=True)
    assert primeiro.status_code == 202
    lido = cliente.get(f"/api/alunos/1/treino-ia/{primeiro.get_json()['pedido_id']}").get_json()
    assert lido == {"situacao": "pronto", "perguntas": ["Qual o foco?", "Tem alguma lesão?"], "rodada": 1, "maximo_de_rodadas": 2}
    assert [f["name"] for f in ia.corpos[0]["tools"]] == ["fazer_perguntas", "montar_treino"]

    ia.devolve = _rascunho()
    rodadas = [{"perguntas": ["Qual o foco?", "Tem alguma lesão?"], "respostas": ["Mais peito.", "Condropatia no joelho esquerdo."]}]
    segundo = _pedir(cliente, perguntar=True, rodadas=rodadas)
    assert segundo.status_code == 202
    final = cliente.get(f"/api/alunos/1/treino-ia/{segundo.get_json()['pedido_id']}").get_json()
    assert final["situacao"] == "pronto" and [f["nome"] for f in final["treino"]["fichas"]] == ["A - PEITO", "B - COSTAS"]
    enviado = ia.corpos[1]["messages"][0]["content"]
    assert "Condropatia no joelho esquerdo." in enviado and "Pergunta 1: Qual o foco?" in enviado


def test_fichas_diferentes_escolhidas_chegam_ao_robo_e_sem_escolha_o_robo_decide(cliente, ia):
    assert _pedir(cliente, dias=5, fichas_diferentes=3).status_code == 202
    assert _pedir(cliente, dias=5, fichas_diferentes=None).status_code == 202
    assert _pedir(cliente, dias=5).status_code == 202  # navegador antigo, sem o campo

    escolhido, decide_null, decide_ausente = (c["messages"][0]["content"] for c in ia.corpos)
    assert "Fichas diferentes: 3 (escolha do professor: entregue exatamente 3 fichas; com 5 dias por semana elas se repetem)" in escolhido
    assert "Fichas diferentes: o professor deixou para você decidir" in decide_null
    assert "Fichas diferentes: o professor deixou para você decidir" in decide_ausente


def test_pedido_sem_perguntar_nao_oferece_a_ferramenta_de_perguntas(cliente, ia):
    _pedir(cliente)

    assert [f["name"] for f in ia.corpos[0]["tools"]] == ["montar_treino"]


def test_a_ia_recebe_o_treino_anterior_do_aluno_sem_o_nome_dele(cliente, caminho, ia):
    c = conectar(caminho)
    c.execute("INSERT INTO treino (id, aluno_id, nome, montado_por, ativo, inicio) VALUES (1, 1, 'TREINO DA ANA', 'PROF SECRETO', 1, '2026-09-01')")
    c.execute("INSERT INTO ficha (id, treino_id, nome, ordem) VALUES (1, 1, 'A - PEITO', 1)")
    c.execute("INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, series, repeticoes) VALUES (1, 1, 1, '3', '12')")
    c.commit()
    c.close()

    _pedir(cliente)

    enviado = json.dumps(ia.corpos[0], ensure_ascii=False)
    assert "SUPINO RETO 3x12" in enviado and "Treino anterior do aluno (ativo" in enviado
    for segredo in ("TREINO DA ANA", "FICTICIA", "PROF SECRETO", "12345678909"):
        assert segredo not in enviado


@pytest.mark.parametrize(
    "mudanca",
    [
        {"perguntar": "sim"},
        {"rodadas": "texto"},
        {"rodadas": [{"perguntas": ["a?"], "respostas": []}]},
        {"rodadas": [{"perguntas": ["a?"], "respostas": ["b"]}] * 3},
        {"rodadas": [{"perguntas": ["a?"], "respostas": ["meu cpf 123.456.789-09"]}]},
        {"rodadas": [{"perguntas": ["a?"], "respostas": ["a Ficticia tem dor"]}]},
        {"rodadas": [{"perguntas": ["a?"], "respostas": ["x" * 301]}]},
    ],
)
def test_conversa_invalida_devolve_400_sem_gastar(cliente, ia, mudanca):
    resposta = _pedir(cliente, **mudanca)

    assert resposta.status_code == 400 and resposta.get_json()["erros"] and ia.chamadas == 0


def test_gravidez_numa_resposta_devolve_409_sem_gastar(cliente, ia):
    rodadas = [{"perguntas": ["Alguma condição?"], "respostas": ["Está grávida de 3 meses"]}]

    resposta = _pedir(cliente, perguntar=True, rodadas=rodadas)

    assert resposta.status_code == 409 and resposta.get_json()["bloqueio"] == "gravidez" and "As respostas" in resposta.get_json()["erro"]
    assert ia.chamadas == 0


def test_a_ia_que_pergunta_sem_poder_vira_erro_na_consulta(cliente, app):
    app.config["IA_CHAMADA"] = IAFalsa(devolve=_perguntas_da_ia("Mais uma?"))

    pedido_id = _pedir(cliente).get_json()["pedido_id"]  # perguntar=False: a IA nem recebeu a ferramenta

    assert cliente.get(f"/api/alunos/1/treino-ia/{pedido_id}").get_json()["situacao"] == "erro"


def test_as_respostas_do_professor_nao_ficam_no_banco(cliente, caminho, app):
    app.config["IA_CHAMADA"] = IAFalsa(devolve=_perguntas_da_ia("Prefere halteres?"))
    rodadas = [{"perguntas": ["Alguma lesão?"], "respostas": ["RESPOSTA-SECRETA hérnia de disco"]}]

    _pedir(cliente, perguntar=True, rodadas=rodadas)

    c = conectar(caminho)
    try:
        tudo = "\n".join(c.iterdump())
    finally:
        c.close()
    assert "RESPOSTA-SECRETA" not in tudo and "hérnia" not in tudo


def test_a_chave_nunca_aparece_em_nenhuma_resposta(cliente):
    pedido_id = _pedir(cliente).get_json()["pedido_id"]

    for resposta in (_pedir(cliente), _pedir(cliente, dias=99), cliente.get(f"/api/alunos/1/treino-ia/{pedido_id}")):
        assert CHAVE not in resposta.get_data(as_text=True)


# ------------------------------------------------------------------ ler o pedido


def test_pedido_de_outro_aluno_ou_que_nao_existe_devolve_404(cliente):
    pedido_id = _pedir(cliente, aluno=1).get_json()["pedido_id"]

    assert cliente.get(f"/api/alunos/2/treino-ia/{pedido_id}").status_code == 404
    assert cliente.get("/api/alunos/1/treino-ia/999").status_code == 404


@pytest.mark.parametrize("caminho_da_rota", ["/api/alunos/1/treino-ia/abc", "/api/alunos/1/treino-ia/-1", "/api/alunos/x/treino-ia/1"])
def test_numero_invalido_na_rota_devolve_404(cliente, caminho_da_rota):
    assert cliente.get(caminho_da_rota).status_code == 404


def test_resposta_nunca_fica_guardada_no_navegador(cliente):
    pedido_id = _pedir(cliente).get_json()["pedido_id"]

    assert cliente.get(f"/api/alunos/1/treino-ia/{pedido_id}").headers["Cache-Control"] == "no-store"


# ------------------------------------------------------------------ proteção da área do professor


def test_computador_nao_autorizado_nao_pede_nem_le(anonimo, cliente, ia):
    pedido_id = _pedir(cliente).get_json()["pedido_id"]
    antes = ia.chamadas

    assert anonimo.post("/api/alunos/1/treino-ia", json=PEDIDO).status_code == 401
    assert anonimo.get(f"/api/alunos/1/treino-ia/{pedido_id}").status_code == 401
    assert ia.chamadas == antes


def test_pedido_vindo_de_outro_site_e_recusado(cliente, ia):
    resposta = cliente.post("/api/alunos/1/treino-ia", json=PEDIDO, headers={"Origin": "https://site-malvado.exemplo"})

    assert resposta.status_code == 403 and ia.chamadas == 0


# ------------------------------------------------------------------ a tela de lançar treino


def _html(cliente, aluno=1):
    return cliente.get(f"/alunos/{aluno}/montar").get_data(as_text=True)


def _botao(html, id_):
    return re.search(rf"<button[^>]*id=\"{id_}\"[^>]*>", html).group(0)


def test_cartao_aparece_ligado_quando_ha_chave_e_o_aluno_pode(cliente):
    html = _html(cliente)

    assert 'id="cartao-ia"' in html and "Treino sob medida" in html
    assert " disabled" not in _botao(html, "abrir-ia")
    assert "A IA monta um rascunho só com os exercícios da academia" in html
    # o painel começa fechado e os 4 campos mais as observações existem
    assert re.search(r'<div id="painel-ia"[^>]*\bhidden\b', html)
    for id_ in ("ia-objetivo", "ia-nivel", "ia-dias", "ia-minutos", "ia-observacoes", "gerar-ia", "fechar-ia", "aviso-ia", "confirmar-ia"):
        assert f'id="{id_}"' in html


def test_cartao_tem_as_opcoes_certas_e_o_limite_das_observacoes(cliente):
    html = _html(cliente)

    assert re.search(rf'<textarea[^>]*id="ia-observacoes"[^>]*maxlength="{ia_treino.LIMITE_DAS_OBSERVACOES}"', html)
    assert ia_treino.LIMITE_DAS_OBSERVACOES == 1000
    assert re.search(r'<textarea[^>]*id="ia-observacoes"[^>]*rows="8"', html)  # o campo é alto: cabe a descrição do aluno
    assert "até 1000 letras" in html and "idade, altura, peso" in html
    for chave in ia_treino.OBJETIVOS:
        assert f'<option value="{chave}">' in html
    for chave in ia_treino.NIVEIS:
        assert f'<option value="{chave}">' in html
    for dias in range(2, 7):
        assert f'<option value="{dias}">{dias} dias</option>' in html
    for minutos in ia_treino.EXERCICIOS_POR_FICHA:
        assert f'<option value="{minutos}">{minutos} minutos</option>' in html
    # "Fichas diferentes": opcional, começa em "O robô decide" e vai de 2 até o máximo de dias
    campo = re.search(r'<select id="ia-fichas".*?</select>', html, re.S).group(0)
    assert re.search(r'<option value="">O robô decide</option>', campo) and "aria-required" not in campo
    assert re.findall(r'<option value="(\d+)">', campo) == [str(n) for n in range(ia_treino.MINIMO_DE_FICHAS, ia_treino.MAXIMO_DE_DIAS + 1)]
    assert "A-B-C-A-B" in html  # a dica explica como a semana roda quando há mais dias do que fichas


def test_cartao_avisa_para_nao_escrever_quem_e_o_aluno(cliente):
    html = _html(cliente)

    assert "Não escreva o nome, CPF nem telefone do aluno" in html
    assert "Quem confere e responde pelo treino é você" in html


def test_cartao_explica_o_que_a_ia_le_e_para_onde_vai_o_texto(cliente):
    html = _html(cliente)

    assert "lê o treino anterior do aluno e pode te fazer perguntas" in html
    assert "até 2 rodadas de perguntas" in html and "Montar direto" in html
    assert "Anthropic, nos EUA" in html  # o professor sabe para onde vai o que escreve


def test_cartao_tem_os_dois_botoes_e_a_area_da_conversa_escondida(cliente):
    html = _html(cliente)

    assert "Gerar rascunho" in _botao(html, "gerar-ia") or 'id="gerar-ia"' in html
    for id_ in ("montar-direto-ia", "acoes-ia", "conversa-ia", "historico-ia", "perguntas-ia", "rodada-ia", "enviar-respostas-ia", "montar-agora-ia", "mudar-pedido-ia"):
        assert f'id="{id_}"' in html, id_
    assert re.search(r'<div id="conversa-ia"[^>]*\bhidden\b', html)
    assert re.search(r'<ol id="historico-ia"[^>]*\bhidden\b', html)


def test_todo_id_que_o_script_da_ia_procura_existe_na_tela(cliente):
    """treino_ia.js faz `pegar("id")` sem checar: um id esquecido no HTML quebra o cartão inteiro (e só se vê no navegador)."""
    from pathlib import Path

    script = (Path(__file__).resolve().parent.parent / "app" / "static" / "treino_ia.js").read_text(encoding="utf-8")
    ids = set(re.findall(r'pegar\("([^"]+)"\)', script))
    html = _html(cliente)

    assert len(ids) >= 20  # o script de fato foi lido
    faltam = {i for i in ids if f'id="{i}"' not in html}
    assert not faltam, faltam


def test_cartao_fica_desligado_sem_a_chave_e_diz_o_motivo(cliente, caminho):
    (caminho.parent / "ia_chave").unlink()

    html = _html(cliente)

    assert " disabled" in _botao(html, "abrir-ia")
    assert "falta a chave da IA no servidor" in html


@pytest.mark.parametrize("fila_id, nome", [(4, "Gestante"), (5, "Grupos de risco")])
def test_cartao_fica_desligado_para_aluno_de_fila_com_liberacao(cliente, caminho, fila_id, nome):
    c = conectar(caminho)
    c.execute(
        "INSERT INTO aluno_fila (aluno_id, fila_id, definida_por, liberacao_em, liberacao_por) VALUES (1, ?, 'Ana', '2026-10-01', 'Ana')", (fila_id,)
    )
    c.commit()
    c.close()

    html = _html(cliente)

    assert " disabled" in _botao(html, "abrir-ia")
    assert f'Este aluno está na fila "{nome}"' in html_do_python.unescape(html)  # o Jinja escapa as aspas
    assert " disabled" not in _botao(_html(cliente, aluno=2), "abrir-ia")  # o outro aluno não é afetado


def test_a_tela_nao_leva_a_chave_nem_o_cpf_do_aluno(cliente):
    html = _html(cliente)

    assert CHAVE not in html and "12345678909" not in html


def test_scripts_da_ia_sao_servidos_como_javascript(cliente):
    for arquivo in ("treino_ia.js", "treino_ia_modelo.js"):
        resposta = cliente.get(f"/static/{arquivo}")
        assert resposta.status_code == 200 and "javascript" in resposta.headers["Content-Type"]


def test_cartao_nao_usa_script_nem_estilo_embutido_nem_recurso_externo(cliente):
    html = _html(cliente)

    assert not re.search(r"<script(?![^>]*\bsrc=)", html)
    assert "<style" not in html and "style=" not in html
    assert "http://" not in html and "https://" not in html


def test_os_rotulos_da_tela_combinam_com_os_valores_que_o_servidor_aceita():
    assert set(ia_treino.ROTULOS_DOS_OBJETIVOS) == set(ia_treino.OBJETIVOS)
    assert set(ia_treino.ROTULOS_DOS_NIVEIS) == set(ia_treino.NIVEIS)
    json.dumps(ia_treino.FERRAMENTA)  # a ferramenta enviada à API precisa virar JSON
