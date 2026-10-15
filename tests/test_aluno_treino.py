"""Testes do treino que o aluno vê no celular (app/aluno_treino.py e GET /api/aluno/treino). Dados inventados."""

from datetime import datetime, timezone

import pytest

from app import aluno_acesso, treinos
from app.aluno_treino import treino_do_aluno
from app.db import conectar, criar_tabelas
from app.web import criar_app

AGORA = datetime(2026, 10, 15, 11, 0, tzinfo=timezone.utc)
SEGREDO_DO_PROFESSOR = "PROFESSORA SEGREDO"


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "aluno_treino.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.executemany(
        "INSERT INTO aluno (id, nome, cpf, whatsapp, situacao) VALUES (?, ?, ?, ?, ?)",
        [
            (1, "ANA SOUZA", "11144477735", "27988887766", "A"),
            (2, "BRUNO LIMA", "52998224725", "27977776655", "A"),
        ],
    )
    for nome in ["SUPINO RETO", "CRUCIFIXO", "TRICEPS TESTA", "TRICEPS NA POLIA", "ROSCA DIRETA", "ESTEIRA"]:
        conn.execute("INSERT INTO exercicio (nome, origem) VALUES (?, 'app')", (nome,))
    conn.commit()
    conn.close()
    return caminho


@pytest.fixture
def conn(caminho):
    c = conectar(caminho)
    yield c
    c.close()


def _item(exercicio_id, **extras):
    return {"exercicio_id": exercicio_id, "series": "4", "repeticoes": "12", "carga": "20 kg", **extras}


def _salvar(conn, aluno_id=1, fichas=None, nome="TREINO ABC", **extras):
    fichas = fichas or [("A PEITO", [_item(1), _item(2)])]
    return treinos.salvar_treino(
        conn,
        aluno_id,
        {
            "nome_treino": nome,
            "montado_por": SEGREDO_DO_PROFESSOR,
            "fichas": [{"nome": n, "itens": i} for n, i in fichas],
            **extras,
        },
    )


# ------------------------------------------------------------------ quem tem e quem não tem treino


def test_aluno_sem_nenhum_treino_recebe_none(conn):
    assert treino_do_aluno(conn, 1) is None


def test_aluno_que_nao_existe_recebe_none(conn):
    assert treino_do_aluno(conn, 999) is None


def test_o_aluno_so_ve_o_treino_ativo(conn):
    antigo = _salvar(conn, nome="TREINO ANTIGO")
    _salvar(conn, nome="TREINO NOVO")  # salvar um novo conclui o antigo

    treino = treino_do_aluno(conn, 1)

    assert treino["nome"] == "TREINO NOVO"
    assert conn.execute("SELECT ativo FROM treino WHERE id = ?", (antigo,)).fetchone()[0] == 0


def test_treino_concluido_nao_aparece(conn):
    treino_id = _salvar(conn)
    conn.execute("UPDATE treino SET ativo = 0 WHERE id = ?", (treino_id,))
    conn.commit()

    assert treino_do_aluno(conn, 1) is None


def test_cada_aluno_ve_so_o_seu(conn):
    _salvar(conn, aluno_id=1, nome="TREINO DA ANA")
    _salvar(conn, aluno_id=2, nome="TREINO DO BRUNO")

    assert treino_do_aluno(conn, 1)["nome"] == "TREINO DA ANA"
    assert treino_do_aluno(conn, 2)["nome"] == "TREINO DO BRUNO"


# ------------------------------------------------------------------ o que sai de cada exercício


def test_o_exercicio_sai_em_texto_pronto(conn):
    _salvar(
        conn,
        fichas=[("A PEITO", [_item(1, pausa=90, observacao="  Descer devagar  "), _item(2, carga=None)])],
        inicio="2026-10-06",
        fim="2026-11-06",
    )

    treino = treino_do_aluno(conn, 1)

    assert treino["inicio"] == "06/10/2026" and treino["fim"] == "06/11/2026"
    ficha = treino["fichas"][0]
    assert ficha["nome"] == "A PEITO"
    primeiro, segundo = (grupo["exercicios"][0] for grupo in ficha["grupos"])
    assert primeiro == {
        "etiqueta": "1",
        "exercicio": "SUPINO RETO",
        "dose": "4 × 12",
        "carga": "20 kg",
        "intervalo": "1 min 30 s",
        "observacao": "Descer devagar",
    }
    assert segundo["etiqueta"] == "2" and segundo["carga"] == "" and segundo["intervalo"] == "" and segundo["observacao"] == ""


def test_cardio_sem_series_nem_repeticoes_nao_quebra(conn):
    _salvar(conn, fichas=[("CARDIO", [{"exercicio_id": 6, "observacao": "20 minutos"}])])

    exercicio = treino_do_aluno(conn, 1)["fichas"][0]["grupos"][0]["exercicios"][0]

    assert exercicio["dose"] == "" and exercicio["carga"] == "" and exercicio["observacao"] == "20 minutos"


def test_sem_datas_a_data_de_inicio_e_a_de_hoje_e_o_fim_fica_vazio(conn):
    _salvar(conn)

    treino = treino_do_aluno(conn, 1)

    assert treino["fim"] is None
    assert len(treino["inicio"]) == 10 and treino["inicio"][2] == "/"


# ------------------------------------------------------------------ bi-set e tri-set


def test_bi_set_vira_um_grupo_com_o_aviso_de_fazer_seguidos(conn):
    _salvar(conn, fichas=[("B", [_item(1), _item(3, bloco=1), _item(4, bloco=1), _item(5)])])

    grupos = treino_do_aluno(conn, 1)["fichas"][0]["grupos"]

    assert [g["nome"] for g in grupos] == [None, "Bi-set", None]
    assert grupos[1]["instrucao"] == "Faça A1 e A2 seguidos"
    assert [e["etiqueta"] for e in grupos[1]["exercicios"]] == ["A1", "A2"]
    assert [e["etiqueta"] for g in grupos for e in g["exercicios"]] == ["1", "A1", "A2", "4"]
    assert grupos[0]["instrucao"] == ""


def test_tri_set_e_dois_blocos_seguidos_nao_se_misturam(conn):
    _salvar(
        conn,
        fichas=[("C", [_item(1, bloco=1), _item(2, bloco=1), _item(3, bloco=1), _item(4, bloco=2), _item(5, bloco=2)])],
    )

    grupos = treino_do_aluno(conn, 1)["fichas"][0]["grupos"]

    assert [g["nome"] for g in grupos] == ["Tri-set", "Bi-set"]
    assert grupos[0]["instrucao"] == "Faça A1, A2 e A3 seguidos"
    assert [e["etiqueta"] for e in grupos[1]["exercicios"]] == ["B1", "B2"]


# ------------------------------------------------------------------ fichas


def test_as_fichas_vem_na_ordem(conn):
    _salvar(conn, fichas=[("A PEITO", [_item(1)]), ("B COSTAS", [_item(2)]), ("C PERNA", [_item(3)])])

    assert [f["nome"] for f in treino_do_aluno(conn, 1)["fichas"]] == ["A PEITO", "B COSTAS", "C PERNA"]


def test_ficha_sem_exercicio_nao_aparece(conn):
    treino_id = _salvar(conn, fichas=[("A", [_item(1)]), ("B", [_item(2)])])
    conn.execute("DELETE FROM ficha_item WHERE ficha_id = (SELECT id FROM ficha WHERE treino_id = ? AND ordem = 2)", (treino_id,))
    conn.commit()

    assert [f["nome"] for f in treino_do_aluno(conn, 1)["fichas"]] == ["A"]


def test_treino_ativo_sem_nenhuma_ficha_com_exercicio_volta_com_lista_vazia(conn):
    treino_id = _salvar(conn)
    conn.execute("DELETE FROM ficha_item")
    conn.commit()

    treino = treino_do_aluno(conn, 1)

    assert treino["nome"] == "TREINO ABC" and treino["fichas"] == []
    assert treino_id  # o treino continua existindo


def test_treino_do_data4u_tambem_aparece(conn):
    conn.execute(
        "INSERT INTO treino (id, aluno_id, nome, montado_por, ativo, origem, data4u_id, inicio) "
        "VALUES (50, 1, 'TREINO DO DATA4U', 'PROF ANTIGO', 1, 'data4u', 777, '2026-09-01')"
    )
    conn.execute("INSERT INTO ficha (id, treino_id, nome, ordem) VALUES (60, 50, 'A', 1)")
    conn.execute("INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, series, repeticoes) VALUES (60, 1, 1, '3', '10')")
    conn.commit()

    treino = treino_do_aluno(conn, 1)

    assert treino["nome"] == "TREINO DO DATA4U" and treino["inicio"] == "01/09/2026"
    assert treino["fichas"][0]["grupos"][0]["exercicios"][0]["dose"] == "3 × 10"


def test_o_numero_da_maquina_nao_aparece_no_nome_do_exercicio(conn):
    conn.execute("UPDATE exercicio SET nome = '(15) CADEIRA ABDUTORA' WHERE id = 1")
    conn.commit()
    _salvar(conn)

    # Mesma regra da tela do professor e do cupom (app/texto.py): o número entre parênteses no começo é o da máquina.
    assert treino_do_aluno(conn, 1)["fichas"][0]["grupos"][0]["exercicios"][0]["exercicio"] == "CADEIRA ABDUTORA"


# ------------------------------------------------------------------ o que NÃO sai


def test_nada_de_ids_professor_origem_ou_ciclo_na_resposta(conn):
    _salvar(conn, sessoes_por_ficha=15, fim="2026-11-06")

    texto = repr(treino_do_aluno(conn, 1))

    assert SEGREDO_DO_PROFESSOR not in texto
    for proibido in ("aluno_id", "exercicio_id", "montado_por", "origem", "data4u", "sessoes_por_ficha", "ativo", "'id'"):
        assert proibido not in texto, proibido


# ------------------------------------------------------------------ a rota


@pytest.fixture
def cliente_da_ana(caminho):
    """O celular da Ana, já logado (a sessão é criada direto, sem passar pelo código do WhatsApp)."""
    app = criar_app(caminho)
    conn = conectar(caminho)
    with conn:
        token = aluno_acesso._criar_sessao(conn, 1, AGORA)
    conn.close()
    cliente = app.test_client()
    cliente.set_cookie(aluno_acesso.NOME_DO_COOKIE, token)
    return cliente


def test_sem_login_a_rota_responde_401(caminho):
    cliente = criar_app(caminho).test_client()

    resposta = cliente.get("/api/aluno/treino")

    assert resposta.status_code == 401
    assert "treino" not in resposta.get_json()


def test_com_login_e_sem_treino_a_rota_devolve_treino_nulo(cliente_da_ana):
    resposta = cliente_da_ana.get("/api/aluno/treino")

    assert resposta.status_code == 200 and resposta.get_json() == {"treino": None}


def test_com_login_a_rota_devolve_o_treino_da_ana_e_nao_o_do_bruno(caminho, cliente_da_ana):
    conn = conectar(caminho)
    _salvar(conn, aluno_id=1, nome="TREINO DA ANA")
    _salvar(conn, aluno_id=2, nome="TREINO DO BRUNO")
    conn.close()

    resposta = cliente_da_ana.get("/api/aluno/treino")

    assert resposta.status_code == 200
    assert resposta.get_json()["treino"]["nome"] == "TREINO DA ANA"
    assert "BRUNO" not in resposta.get_data(as_text=True) and SEGREDO_DO_PROFESSOR not in resposta.get_data(as_text=True)


def test_a_rota_nao_aceita_numero_de_aluno_na_url_nem_na_busca(caminho, cliente_da_ana):
    conn = conectar(caminho)
    _salvar(conn, aluno_id=2, nome="TREINO DO BRUNO")
    conn.close()

    assert cliente_da_ana.get("/api/aluno/2/treino").status_code == 404
    resposta = cliente_da_ana.get("/api/aluno/treino?aluno_id=2&id=2")
    assert resposta.get_json() == {"treino": None}  # a Ana não tem treino; o do Bruno não vaza


def test_a_resposta_nao_fica_guardada_no_navegador(caminho, cliente_da_ana):
    resposta = cliente_da_ana.get("/api/aluno/treino")

    assert "no-store" in resposta.headers["Cache-Control"]


def test_cookie_falso_nao_ve_treino(caminho):
    conn = conectar(caminho)
    _salvar(conn, aluno_id=1)
    conn.close()
    cliente = criar_app(caminho).test_client()
    cliente.set_cookie(aluno_acesso.NOME_DO_COOKIE, "um-token-que-eu-inventei")

    assert cliente.get("/api/aluno/treino").status_code == 401


def test_aluno_que_vira_provisorio_perde_o_treino_na_hora(caminho, cliente_da_ana):
    conn = conectar(caminho)
    _salvar(conn, aluno_id=1)
    with conn:
        conn.execute("UPDATE aluno SET provisorio = 1 WHERE id = 1")
    conn.close()

    assert cliente_da_ana.get("/api/aluno/treino").status_code == 401


def test_o_computador_do_professor_sem_login_de_aluno_nao_ve_treino_de_aluno(caminho):
    from app import acesso

    conn = conectar(caminho)
    codigo = acesso.gerar_codigo(conn, "Computador dos professores").codigo
    _salvar(conn, aluno_id=1)
    conn.close()
    professor = criar_app(caminho).test_client()
    assert professor.post("/api/autorizar", json={"codigo": codigo}).status_code == 200

    assert professor.get("/api/aluno/treino").status_code == 401


def test_a_pagina_do_aluno_tem_os_pontos_que_o_javascript_usa(caminho, cliente_da_ana):
    html = cliente_da_ana.get("/aluno").get_data(as_text=True)

    for id_ in ("aviso-treino", "botao-de-novo", "treino", "titulo-treino", "treino-datas", "fichas-botoes", "ficha-atual", "botao-sair"):
        assert f'id="{id_}"' in html, id_
