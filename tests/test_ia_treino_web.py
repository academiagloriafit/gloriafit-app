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

    def __call__(self, chave, corpo, *_a, **_k):
        self.chamadas += 1
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
    [{"objetivo": "x"}, {"nivel": None}, {"dias": 9}, {"minutos": 5}, {"observacoes": "meu cpf 123.456.789-09"}, {"observacoes": "x" * 301}],
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

    assert re.search(r'<textarea[^>]*id="ia-observacoes"[^>]*maxlength="300"', html)
    for chave in ia_treino.OBJETIVOS:
        assert f'<option value="{chave}">' in html
    for chave in ia_treino.NIVEIS:
        assert f'<option value="{chave}">' in html
    for dias in range(2, 7):
        assert f'<option value="{dias}">{dias} dias</option>' in html
    for minutos in ia_treino.EXERCICIOS_POR_FICHA:
        assert f'<option value="{minutos}">{minutos} minutos</option>' in html


def test_cartao_avisa_para_nao_escrever_quem_e_o_aluno(cliente):
    html = _html(cliente)

    assert "Não escreva o nome, CPF nem telefone do aluno" in html
    assert "Quem confere e responde pelo treino é você" in html


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
