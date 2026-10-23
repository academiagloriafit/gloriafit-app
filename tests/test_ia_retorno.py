"""O robô aprende com os professores (app/ia_retorno.py): a avaliação do rascunho, a diferença entre o rascunho e o treino salvo, e o
relatório. A API da Anthropic é sempre uma falsa; dados inventados. A promessa que estes testes protegem: o registro NÃO identifica o
aluno nem o professor, e nunca estraga o "Salvar treino"."""

import json

import pytest

from app import acesso, ia_retorno, ia_treino
from app.datas import hoje
from app.db import conectar, criar_tabelas
from app.web import criar_app

CHAVE = "sk-ant-chave-de-teste-0123456789abcdef"
OBSERVACOES = "dor no joelho direito ao agachar, 35 anos"
PEDIDO = {"objetivo": "hipertrofia", "nivel": "iniciante", "dias": 2, "minutos": 60, "observacoes": OBSERVACOES}


def _item(exercicio_id, nome, series="3", repeticoes="12", pausa=None, observacao="", carga="", bloco=None):
    return {"exercicio_id": exercicio_id, "nome": nome, "series": series, "repeticoes": repeticoes, "pausa": pausa, "observacao": observacao, "carga": carga, "bloco": bloco}


def _salvo(exercicio_id, nome, **extras):
    """Um item no formato de `treinos.obter_treino` (o nome do exercício vem em `exercicio`)."""
    item = _item(exercicio_id, nome, **extras)
    item["exercicio"] = item.pop("nome")
    return item


# ------------------------------------------------------------------ comparar: a diferença entre o rascunho e o treino salvo


def test_treino_salvo_igual_ao_rascunho_nao_tem_diferenca():
    ia = [{"nome": "A", "itens": [_item(1, "SUPINO RETO"), _item(2, "REMADA", series="4", repeticoes="8", pausa=60)]}]
    salvo = [{"nome": "A", "ordem": 1, "itens": [_salvo(1, "SUPINO RETO"), _salvo(2, "REMADA", series="4", repeticoes="8", pausa=60)]}]

    resultado = ia_retorno.comparar(ia, salvo)

    assert resultado["mantidos"] == 2
    assert resultado["tirados"] == resultado["incluidos"] == resultado["alterados"] == []
    assert resultado["fichas"] == {"ia": 1, "final": 1}
    assert resultado["exercicios"] == {"ia": 2, "final": 2}
    assert resultado["fichas_com_ordem_mudada"] == resultado["observacoes_mudadas"] == resultado["fichas_renomeadas"] == 0


def test_exercicio_tirado_e_exercicio_incluido():
    ia = [{"nome": "A", "itens": [_item(1, "SUPINO RETO"), _item(2, "REMADA")]}]
    salvo = [{"nome": "A", "itens": [_salvo(1, "SUPINO RETO"), _salvo(3, "LEG PRESS")]}]

    resultado = ia_retorno.comparar(ia, salvo)

    assert resultado["mantidos"] == 1
    assert resultado["tirados"] == [{"ficha": 1, "exercicio": "REMADA"}]
    assert resultado["incluidos"] == [{"ficha": 1, "exercicio": "LEG PRESS"}]


def test_series_repeticoes_e_pausa_mudadas_vao_com_de_e_para():
    ia = [{"nome": "A", "itens": [_item(1, "SUPINO RETO", series="3", repeticoes="12", pausa=60)]}]
    salvo = [{"nome": "A", "itens": [_salvo(1, "SUPINO RETO", series="4", repeticoes="8-10", pausa=None)]}]

    alterados = ia_retorno.comparar(ia, salvo)["alterados"]

    assert {(a["campo"], a["de"], a["para"]) for a in alterados} == {
        ("series", "3", "4"),
        ("repeticoes", "12", "8-10"),
        ("pausa", "60", ""),
    }
    assert all(a["ficha"] == 1 and a["exercicio"] == "SUPINO RETO" for a in alterados)


def test_carga_e_texto_da_observacao_nunca_entram_so_a_contagem():
    ia = [{"nome": "A", "itens": [_item(1, "SUPINO RETO", observacao="Cuidado com o ombro", carga="")]}]
    salvo = [{"nome": "A", "itens": [_salvo(1, "SUPINO RETO", observacao="Maria tem lesão no ombro direito", carga="40")]}]

    resultado = ia_retorno.comparar(ia, salvo)

    texto = json.dumps(resultado, ensure_ascii=False)
    assert "Maria" not in texto and "ombro" not in texto and "40" not in texto
    assert resultado["observacoes_mudadas"] == 1
    assert resultado["alterados"] == []  # carga não é comparada


def test_ordem_mudada_dos_exercicios_que_ficaram():
    ia = [{"nome": "A", "itens": [_item(1, "SUPINO RETO"), _item(2, "REMADA"), _item(3, "LEG PRESS")]}]
    salvo = [{"nome": "A", "itens": [_salvo(3, "LEG PRESS"), _salvo(1, "SUPINO RETO"), _salvo(2, "REMADA")]}]

    resultado = ia_retorno.comparar(ia, salvo)

    assert resultado["fichas_com_ordem_mudada"] == 1
    assert resultado["mantidos"] == 3 and resultado["tirados"] == [] and resultado["incluidos"] == []


def test_ficha_inteira_tirada_e_ficha_renomeada():
    ia = [
        {"nome": "A - PEITO", "itens": [_item(1, "SUPINO RETO")]},
        {"nome": "B - COSTAS", "itens": [_item(2, "REMADA"), _item(3, "LEG PRESS")]},
    ]
    salvo = [{"nome": "A", "itens": [_salvo(1, "SUPINO RETO")]}]

    resultado = ia_retorno.comparar(ia, salvo)

    assert resultado["fichas"] == {"ia": 2, "final": 1}
    assert resultado["tirados"] == [{"ficha": 2, "exercicio": "REMADA"}, {"ficha": 2, "exercicio": "LEG PRESS"}]
    assert resultado["fichas_renomeadas"] == 1


def test_exercicio_passado_de_uma_ficha_para_outra_conta_como_tirado_e_incluido():
    ia = [{"nome": "A", "itens": [_item(1, "SUPINO RETO"), _item(2, "REMADA")]}, {"nome": "B", "itens": [_item(3, "LEG PRESS")]}]
    salvo = [{"nome": "A", "itens": [_salvo(1, "SUPINO RETO")]}, {"nome": "B", "itens": [_salvo(3, "LEG PRESS"), _salvo(2, "REMADA")]}]

    resultado = ia_retorno.comparar(ia, salvo)

    assert resultado["tirados"] == [{"ficha": 1, "exercicio": "REMADA"}]
    assert resultado["incluidos"] == [{"ficha": 2, "exercicio": "REMADA"}]


def test_mesmo_exercicio_posto_duas_vezes_conta_a_segunda_como_incluida():
    ia = [{"nome": "A", "itens": [_item(1, "SUPINO RETO")]}]
    salvo = [{"nome": "A", "itens": [_salvo(1, "SUPINO RETO"), _salvo(1, "SUPINO RETO")]}]

    resultado = ia_retorno.comparar(ia, salvo)

    assert resultado["mantidos"] == 1
    assert resultado["incluidos"] == [{"ficha": 1, "exercicio": "SUPINO RETO"}]


def test_listas_muito_grandes_sao_cortadas_e_o_resto_so_contado():
    ia = [{"nome": "A", "itens": [_item(n, f"EX {n}") for n in range(1, 91)]}]
    salvo = [{"nome": "A", "itens": [_salvo(1000 + n, f"NOVO {n}") for n in range(1, 91)]}]

    resultado = ia_retorno.comparar(ia, salvo)

    assert len(resultado["tirados"]) == len(resultado["incluidos"]) == ia_retorno.MAXIMO_DE_ITENS_POR_LISTA
    assert resultado["cortados"] == 2 * (90 - ia_retorno.MAXIMO_DE_ITENS_POR_LISTA)
    assert resultado["exercicios"] == {"ia": 90, "final": 90}  # os totais continuam certos


def test_comparar_aguenta_lixo_sem_levantar_erro():
    assert ia_retorno.comparar(None, None)["fichas"] == {"ia": 0, "final": 0}
    assert ia_retorno.comparar([{"itens": None}, "x", {"nome": 3, "itens": [{"exercicio_id": 1}, 7]}], [])["exercicios"]["ia"] == 1


# ------------------------------------------------------------------ pelo app: fixtures


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
                    "alertas": [],
                },
            }
        ],
        "usage": {"input_tokens": 5000, "output_tokens": 700},
    }


def _perguntas():
    return {
        "stop_reason": "tool_use",
        "content": [{"type": "tool_use", "name": "fazer_perguntas", "input": {"perguntas": ["Treina há quanto tempo?"]}}],
        "usage": {"input_tokens": 3000, "output_tokens": 100},
    }


class IAFalsa:
    def __init__(self, devolve=None):
        self.devolve = devolve or _rascunho()

    def __call__(self, chave, corpo, *_a, **_k):
        return self.devolve


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "ia.db"
    c = conectar(caminho)
    criar_tabelas(c)
    c.execute("INSERT INTO aluno (id, nome, cpf) VALUES (1, 'ANA FICTICIA', '12345678909'), (2, 'BRUNO FICTICIO', NULL)")
    c.execute(
        "INSERT INTO exercicio (id, nome, origem, usos_ultimo_ano) VALUES"
        " (1, '(3) SUPINO RETO', 'app', 50), (2, 'REMADA', 'app', 50), (3, 'LEG PRESS', 'app', 50)"
    )
    c.commit()
    c.close()
    ia_treino.guardar_chave(tmp_path / "ia_chave", CHAVE)
    return caminho


@pytest.fixture
def app(caminho):
    aplicativo = criar_app(caminho)
    aplicativo.config["IA_CHAMADA"] = IAFalsa()
    aplicativo.config["IA_EM_SEGUNDO_PLANO"] = False
    return aplicativo


@pytest.fixture
def cliente(app, caminho):
    navegador = app.test_client()
    c = conectar(caminho)
    codigo = acesso.gerar_codigo(c, "Computador de teste").codigo
    token = acesso.autorizar(c, codigo).token
    c.close()
    navegador.set_cookie(acesso.NOME_DO_COOKIE, token)
    return navegador


def _pedir(cliente, aluno=1, **extras) -> int:
    resposta = cliente.post(f"/api/alunos/{aluno}/treino-ia", json={**PEDIDO, **extras})
    assert resposta.status_code == 202
    return resposta.get_json()["pedido_id"]


def _avaliar(cliente, pedido_id, aluno=1, **corpo):
    return cliente.post(f"/api/alunos/{aluno}/treino-ia/{pedido_id}/avaliacao", json=corpo)


def _treino_final(exercicio_a=1, exercicio_b=3, series_a="3"):
    """O que o professor salva: o rascunho com o exercício 2 da ficha B trocado pelo 3 (e, se pedir, as séries da ficha A mudadas)."""
    return {
        "nome_treino": "TREINO DA ANA",
        "montado_por": "PROFESSOR TESTE",
        "fichas": [
            {"nome": "A - PEITO", "itens": [{"exercicio_id": exercicio_a, "series": series_a, "repeticoes": "12", "carga": "40"}]},
            {"nome": "B - COSTAS", "itens": [{"exercicio_id": exercicio_b, "series": "3", "repeticoes": "10"}]},
        ],
    }


def _linhas(caminho, sql="SELECT * FROM ia_retorno ORDER BY id"):
    c = conectar(caminho)
    try:
        return [dict(l) for l in c.execute(sql)]
    finally:
        c.close()


# ------------------------------------------------------------------ avaliar o rascunho


def test_avaliar_serviu_grava_so_o_contexto_e_a_nota(cliente, caminho):
    pedido_id = _pedir(cliente)

    resposta = _avaliar(cliente, pedido_id, nota="serviu")

    assert resposta.status_code == 201 and resposta.get_json() == {"ok": True}
    [linha] = _linhas(caminho)
    assert linha == {
        "id": linha["id"],
        "dia": hoje(),
        "tipo": "avaliacao",
        "objetivo": "hipertrofia",
        "nivel": "iniciante",
        "dias": 2,
        "minutos": 60,
        "fila": None,
        "com_observacoes": 1,
        "rodadas": 0,
        "regras": ia_treino.VERSAO_DAS_REGRAS,
        "modelo": ia_treino.modelo_em_uso(),
        "nota": "serviu",
        "motivo": None,
        "mudancas": None,
    }


def test_o_registro_nao_guarda_aluno_professor_nem_o_que_foi_escrito_nas_observacoes(cliente, caminho):
    pedido_id = _pedir(cliente)
    _avaliar(cliente, pedido_id, nota="com_ajustes", motivo="Faltou posterior de coxa")
    cliente.post("/api/alunos/1/treinos", json={**_treino_final(), "ia": {"pedido_id": pedido_id}})

    tudo = json.dumps(_linhas(caminho), ensure_ascii=False)

    for proibido in ("ANA", "FICTICIA", "PROFESSOR TESTE", "TREINO DA ANA", "12345678909", "joelho", "35 anos", OBSERVACOES):
        assert proibido not in tudo
    assert len(_linhas(caminho)) == 2


def test_avaliar_com_motivo_grava_o_motivo_limpo(cliente, caminho):
    pedido_id = _pedir(cliente)

    assert _avaliar(cliente, pedido_id, nota="nao_serviu", motivo="  Faltou   exercício de\nposterior de coxa ").status_code == 201

    assert _linhas(caminho)[0]["motivo"] == "Faltou exercício de posterior de coxa"


def test_so_vale_uma_avaliacao_por_rascunho(cliente, caminho):
    pedido_id = _pedir(cliente)
    assert _avaliar(cliente, pedido_id, nota="serviu").status_code == 201

    segunda = _avaliar(cliente, pedido_id, nota="nao_serviu", motivo="mudei de ideia")

    assert segunda.status_code == 409
    assert [l["nota"] for l in _linhas(caminho)] == ["serviu"]


@pytest.mark.parametrize(
    "corpo",
    [
        {"nota": "otimo"},
        {"nota": None},
        {},
        {"nota": "serviu", "motivo": 12},
        {"nota": "serviu", "motivo": "x" * 301},
        {"nota": "serviu", "motivo": "A Ficticia reclamou do treino"},  # o nome (sobrenome) do aluno
        {"nota": "serviu", "motivo": "Ela mora na rua tal, tel 27 99999 8888"},  # número longo
        {"nota": "serviu", "motivo": "falar com ana@exemplo.com"},  # e-mail
        {"nota": "serviu", "motivo": "tem 15/03/2024 de data"},  # data completa
        {"nota": "serviu", "motivo": "bom\u0000ruim"},  # caractere de controle
    ],
)
def test_avaliacao_invalida_e_recusada_e_nada_e_gravado(cliente, caminho, corpo):
    pedido_id = _pedir(cliente)

    resposta = _avaliar(cliente, pedido_id, **corpo)

    assert resposta.status_code == 400 and resposta.get_json()["erros"]
    assert _linhas(caminho) == []
    # e o rascunho continua podendo ser avaliado direito depois
    assert _avaliar(cliente, pedido_id, nota="serviu").status_code == 201


def test_corpo_que_nao_e_um_objeto_e_recusado(cliente):
    pedido_id = _pedir(cliente)

    assert cliente.post(f"/api/alunos/1/treino-ia/{pedido_id}/avaliacao", json=["serviu"]).status_code == 400


def test_nao_avalia_pedido_de_outro_aluno_nem_inexistente_nem_so_pergunta(cliente, app, caminho):
    pedido_id = _pedir(cliente)

    assert _avaliar(cliente, pedido_id, aluno=2, nota="serviu").status_code == 404
    assert _avaliar(cliente, 9999, nota="serviu").status_code == 404
    app.config["IA_CHAMADA"] = IAFalsa(_perguntas())
    pedido_de_perguntas = _pedir(cliente, perguntar=True)
    assert _avaliar(cliente, pedido_de_perguntas, nota="serviu").status_code == 404
    assert _linhas(caminho) == []


def test_rascunho_apagado_depois_de_3_dias_nao_pode_mais_ser_avaliado(cliente, caminho):
    pedido_id = _pedir(cliente)
    c = conectar(caminho)
    c.execute("UPDATE ia_pedido SET resultado = NULL")
    c.commit()
    c.close()

    assert _avaliar(cliente, pedido_id, nota="serviu").status_code == 404


def test_a_tela_nao_recebe_a_area_interna_do_retorno(cliente, caminho):
    pedido_id = _pedir(cliente)

    corpo = cliente.get(f"/api/alunos/1/treino-ia/{pedido_id}").get_json()

    assert "_retorno" not in corpo and corpo["situacao"] == "pronto"
    # mas ela está guardada no pedido, sem o texto das observações (o texto fica só na área `_historico`)
    [linha] = _linhas(caminho, "SELECT resultado FROM ia_pedido")
    guardado = json.loads(linha["resultado"])
    assert guardado["_retorno"]["objetivo"] == "hipertrofia" and guardado["_retorno"]["com_observacoes"] is True
    assert "joelho" not in json.dumps(guardado["_retorno"])  # o texto das observações NUNCA entra na área do retorno
    assert "_historico" not in corpo  # (o texto fica na área do histórico do treino, que também não vai para a tela)


def test_avaliar_exige_computador_autorizado(app, cliente):
    pedido_id = _pedir(cliente)

    resposta = app.test_client().post(f"/api/alunos/1/treino-ia/{pedido_id}/avaliacao", json={"nota": "serviu"})

    assert resposta.status_code == 401


# ------------------------------------------------------------------ salvar o treino: a correção


def test_salvar_a_partir_do_rascunho_registra_so_o_que_o_professor_mudou(cliente, caminho):
    pedido_id = _pedir(cliente)

    resposta = cliente.post("/api/alunos/1/treinos", json={**_treino_final(series_a="4"), "ia": {"pedido_id": pedido_id}})

    assert resposta.status_code == 201
    [linha] = _linhas(caminho)
    assert linha["tipo"] == "correcao" and linha["nota"] is None and linha["motivo"] is None
    assert (linha["objetivo"], linha["nivel"], linha["dias"], linha["minutos"]) == ("hipertrofia", "iniciante", 2, 60)
    mudancas = json.loads(linha["mudancas"])
    assert mudancas["fichas"] == {"ia": 2, "final": 2} and mudancas["mantidos"] == 1
    assert mudancas["tirados"] == [{"ficha": 2, "exercicio": "REMADA"}]
    assert mudancas["incluidos"] == [{"ficha": 2, "exercicio": "LEG PRESS"}]
    assert mudancas["alterados"] == [{"ficha": 1, "exercicio": "SUPINO RETO", "campo": "series", "de": "3", "para": "4"}]
    assert "40" not in linha["mudancas"]  # a carga que o professor digitou não vai


def test_salvar_exatamente_o_rascunho_tambem_e_registrado_como_sem_diferenca(cliente, caminho):
    pedido_id = _pedir(cliente)
    final = _treino_final(exercicio_b=2)

    assert cliente.post("/api/alunos/1/treinos", json={**final, "ia": {"pedido_id": pedido_id}}).status_code == 201

    mudancas = json.loads(_linhas(caminho)[0]["mudancas"])
    assert mudancas["tirados"] == mudancas["incluidos"] == mudancas["alterados"] == [] and mudancas["mantidos"] == 2


def test_a_correcao_leva_a_nota_dada_antes(cliente, caminho):
    pedido_id = _pedir(cliente)
    _avaliar(cliente, pedido_id, nota="com_ajustes")

    cliente.post("/api/alunos/1/treinos", json={**_treino_final(), "ia": {"pedido_id": pedido_id}})

    assert [(l["tipo"], l["nota"]) for l in _linhas(caminho)] == [("avaliacao", "com_ajustes"), ("correcao", "com_ajustes")]


def test_o_mesmo_rascunho_so_gera_uma_correcao(cliente, caminho):
    pedido_id = _pedir(cliente)
    cliente.post("/api/alunos/1/treinos", json={**_treino_final(), "ia": {"pedido_id": pedido_id}})

    segunda = cliente.post("/api/alunos/1/treinos", json={**_treino_final(), "nome_treino": "OUTRO NOME", "ia": {"pedido_id": pedido_id}})

    assert segunda.status_code == 201
    assert len(_linhas(caminho)) == 1


def test_avaliar_depois_de_salvar_continua_valendo(cliente, caminho):
    pedido_id = _pedir(cliente)
    cliente.post("/api/alunos/1/treinos", json={**_treino_final(), "ia": {"pedido_id": pedido_id}})

    assert _avaliar(cliente, pedido_id, nota="serviu").status_code == 201

    assert [l["tipo"] for l in _linhas(caminho)] == ["correcao", "avaliacao"]


@pytest.mark.parametrize("ia", [None, "x", [], {}, {"pedido_id": "1"}, {"pedido_id": True}, {"pedido_id": 0}, {"pedido_id": -3}, {"pedido_id": 9999}])
def test_salvar_com_ia_que_nao_vale_salva_o_treino_e_nao_registra_nada(cliente, caminho, ia):
    _pedir(cliente)
    corpo = _treino_final()
    if ia is not None:
        corpo["ia"] = ia

    resposta = cliente.post("/api/alunos/1/treinos", json=corpo)

    assert resposta.status_code == 201
    assert _linhas(caminho) == []
    assert _linhas(caminho, "SELECT COUNT(*) AS n FROM treino")[0]["n"] == 1


def test_rascunho_de_outro_aluno_nao_registra_nada_mas_o_treino_e_salvo(cliente, caminho):
    pedido_id = _pedir(cliente, aluno=1)

    resposta = cliente.post("/api/alunos/2/treinos", json={**_treino_final(), "ia": {"pedido_id": pedido_id}})

    assert resposta.status_code == 201
    assert _linhas(caminho) == []


def test_treino_recusado_nao_gasta_o_rascunho(cliente, caminho):
    pedido_id = _pedir(cliente)
    invalido = {**_treino_final(), "montado_por": "", "ia": {"pedido_id": pedido_id}}

    assert cliente.post("/api/alunos/1/treinos", json=invalido).status_code == 400
    assert _linhas(caminho) == []

    assert cliente.post("/api/alunos/1/treinos", json={**_treino_final(), "ia": {"pedido_id": pedido_id}}).status_code == 201
    assert len(_linhas(caminho)) == 1  # o mesmo rascunho ainda valia


def test_defeito_no_registro_nunca_atrapalha_o_salvar(cliente, caminho, monkeypatch):
    pedido_id = _pedir(cliente)

    def quebra(*_a, **_k):
        raise RuntimeError("defeito de teste")

    monkeypatch.setattr(ia_retorno, "registrar_correcao", quebra)

    resposta = cliente.post("/api/alunos/1/treinos", json={**_treino_final(), "ia": {"pedido_id": pedido_id}})

    assert resposta.status_code == 201 and resposta.get_json()["id"] > 0
    assert _linhas(caminho, "SELECT COUNT(*) AS n FROM treino")[0]["n"] == 1
    assert _linhas(caminho) == []


# ------------------------------------------------------------------ o contexto do rascunho


def test_contexto_nao_guarda_o_texto_das_observacoes_so_se_havia(cliente, caminho):
    com = _pedir(cliente)
    sem = _pedir(cliente, observacoes="")
    _avaliar(cliente, com, nota="serviu")
    _avaliar(cliente, sem, nota="serviu")

    assert [l["com_observacoes"] for l in _linhas(caminho)] == [1, 0]


def test_contexto_leva_o_nome_da_fila_do_aluno(cliente, caminho):
    c = conectar(caminho)
    c.execute("INSERT INTO aluno_fila (aluno_id, fila_id, numero_atual, definida_por) VALUES (1, 2, 1, 'Ana')")  # a fila "Mulher" já vem pronta
    c.commit()
    c.close()
    pedido_id = _pedir(cliente)

    _avaliar(cliente, pedido_id, nota="serviu")

    assert _linhas(caminho)[0]["fila"] == "Mulher"


def test_a_versao_das_regras_muda_quando_o_texto_das_regras_muda(monkeypatch):
    import hashlib

    atual = ia_treino.VERSAO_DAS_REGRAS
    outra = hashlib.sha256((ia_treino.REGRAS_DA_CASA + " regra nova").encode("utf-8")).hexdigest()[:8]

    assert len(atual) == 8 and atual != outra
    assert atual == hashlib.sha256(ia_treino.REGRAS_DA_CASA.encode("utf-8")).hexdigest()[:8]


# ------------------------------------------------------------------ o relatório


def test_relatorio_sem_nada_registrado(caminho):
    c = conectar(caminho)
    try:
        assert "Nada registrado" in ia_retorno.relatorio(c)
    finally:
        c.close()


def _popular(cliente, caminho):
    """Três rascunhos: um que serviu e foi salvo igual, um com ajustes (REMADA trocada por LEG PRESS e séries mudadas), um que não serviu."""
    primeiro = _pedir(cliente)
    _avaliar(cliente, primeiro, nota="serviu")
    cliente.post("/api/alunos/1/treinos", json={**_treino_final(exercicio_b=2), "nome_treino": "T1", "ia": {"pedido_id": primeiro}})
    segundo = _pedir(cliente, aluno=2, nivel="intermediario")
    _avaliar(cliente, segundo, aluno=2, nota="com_ajustes", motivo="Faltou posterior de coxa")
    cliente.post("/api/alunos/2/treinos", json={**_treino_final(series_a="4"), "nome_treino": "T2", "ia": {"pedido_id": segundo}})
    terceiro = _pedir(cliente, objetivo="emagrecimento")
    _avaliar(cliente, terceiro, nota="nao_serviu", motivo="Muito volume para iniciante")


def test_relatorio_junta_notas_trocas_e_motivos(cliente, caminho):
    _popular(cliente, caminho)
    c = conectar(caminho)
    try:
        texto = ia_retorno.relatorio(c)
    finally:
        c.close()

    assert "Avaliações: 3" in texto and "Treinos salvos a partir de rascunho: 2" in texto
    assert "Serviu: 1 (33%)" in texto and "Serviu com ajustes: 1" in texto and "Não serviu: 1" in texto
    assert "hipertrofia, iniciante: 1 / 0 / 0" in texto and "emagrecimento, iniciante: 0 / 0 / 1" in texto
    assert "Salvos exatamente como a IA fez: 1 de 2 (50%)" in texto
    assert "REMADA: 1" in texto and "LEG PRESS: 1" in texto  # mais tirado / mais incluído
    assert "séries: 3 -> 4 (1x)" in texto
    assert "Faltou posterior de coxa" in texto and "Muito volume para iniciante" in texto
    assert "menos de 10 treinos" in texto  # pouco dado: o relatório avisa para não tirar conclusão
    for proibido in ("ANA", "BRUNO", "FICTICI", "PROFESSOR TESTE", "joelho"):
        assert proibido not in texto


def test_relatorio_do_mes_so_conta_aquele_mes(cliente, caminho):
    _popular(cliente, caminho)
    c = conectar(caminho)
    try:
        c.execute("UPDATE ia_retorno SET dia = '2026-09-15' WHERE id = 1")
        c.commit()
        todo = ia_retorno.relatorio(c)
        setembro = ia_retorno.relatorio(c, "2026-09")
        outubro_ou_depois = ia_retorno.relatorio(c, hoje()[:7])
    finally:
        c.close()

    assert "mês 2026-09" in setembro and "Avaliações: 1" in setembro
    assert "Avaliações: 3" in todo
    assert "Avaliações: 2" in outubro_ou_depois


def test_comando_do_terminal_mostra_o_relatorio(cliente, caminho, capsys):
    _popular(cliente, caminho)

    assert ia_retorno.principal(["relatorio", "--banco", str(caminho)]) == 0
    assert "RETORNO DOS PROFESSORES" in capsys.readouterr().out


def test_comando_do_terminal_recusa_mes_mal_escrito_e_banco_que_nao_existe(tmp_path, caminho, capsys):
    assert ia_retorno.principal(["relatorio", "--banco", str(caminho), "--mes", "outubro"]) == 1
    assert ia_retorno.principal(["relatorio", "--banco", str(caminho), "--mes", "2026-13"]) == 1
    assert ia_retorno.principal(["relatorio", "--banco", str(tmp_path / "nao-existe.db")]) == 1
    assert capsys.readouterr().out.count("\n") >= 3


def test_rascunho_guardado_sem_o_contexto_completo_nao_vira_registro_torto(cliente, caminho):
    pedido_id = _pedir(cliente)
    c = conectar(caminho)
    guardado = json.loads(c.execute("SELECT resultado FROM ia_pedido").fetchone()[0])
    del guardado["_retorno"]["objetivo"]
    c.execute("UPDATE ia_pedido SET resultado = ?", (json.dumps(guardado),))
    c.commit()
    c.close()

    assert _avaliar(cliente, pedido_id, nota="serviu").status_code == 404
    assert cliente.post("/api/alunos/1/treinos", json={**_treino_final(), "ia": {"pedido_id": pedido_id}}).status_code == 201
    assert _linhas(caminho) == []


def test_a_tela_de_montar_traz_a_pergunta_do_rascunho_escondida_com_o_limite_do_motivo(cliente):
    pagina = cliente.get("/alunos/1/montar").get_data(as_text=True)

    assert 'id="avaliacao-ia"' in pagina and 'id="motivo-ia-texto"' in pagina
    assert f"Até {ia_retorno.LIMITE_DO_MOTIVO} letras" in pagina
    assert 'class="avaliacao-ia" id="avaliacao-ia" aria-labelledby="titulo-avaliacao-ia" hidden' in pagina  # só abre depois de salvar um treino da IA
