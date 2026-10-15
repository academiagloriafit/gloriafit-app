"""Testes do treino que o aluno vê no celular (app/aluno_treino.py e GET /api/aluno/treino). Dados inventados."""

import threading
from datetime import datetime, timedelta, timezone

import pytest

from app import aluno_acesso, ciclo, treinos
from app.aluno_treino import (
    MarcacaoInvalida,
    desfazer_marcacao_de_hoje,
    marcar_ficha_feita,
    treino_do_aluno,
)
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


# ------------------------------------------------------------------ "Fiz esta ficha hoje"

MEIO_DIA = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)  # 12h00 em Brasília


def _sessoes(conn, aluno_id=1):
    return [
        tuple(linha)
        for linha in conn.execute(
            "SELECT s.ficha_ordem, s.feita_em FROM sessao s JOIN treino t ON t.id = s.treino_id "
            "WHERE t.aluno_id = ? ORDER BY s.id",
            (aluno_id,),
        )
    ]


def _treino_abc(conn, aluno_id=1, nome="TREINO ABC", **extras):
    return _salvar(conn, aluno_id=aluno_id, nome=nome, fichas=[("A", [_item(1)]), ("B", [_item(2)]), ("C", [_item(3)])], **extras)


def test_marcar_grava_uma_sessao_com_o_momento_certo(conn):
    _treino_abc(conn)

    resposta = marcar_ficha_feita(conn, 1, 1, MEIO_DIA)

    assert resposta == {"ficha": 1, "ja_marcada": False, "feitas": 1}
    assert _sessoes(conn) == [(1, "2026-10-15 15:00:00")]


def test_marcar_de_novo_no_mesmo_dia_nao_conta_duas_vezes(conn):
    _treino_abc(conn)
    marcar_ficha_feita(conn, 1, 1, MEIO_DIA)

    resposta = marcar_ficha_feita(conn, 1, 1, MEIO_DIA + timedelta(hours=3))

    assert resposta == {"ficha": 1, "ja_marcada": True, "feitas": 1}
    assert len(_sessoes(conn)) == 1


def test_no_dia_seguinte_conta_de_novo(conn):
    _treino_abc(conn)
    marcar_ficha_feita(conn, 1, 1, MEIO_DIA)

    resposta = marcar_ficha_feita(conn, 1, 1, MEIO_DIA + timedelta(days=1))

    assert resposta == {"ficha": 1, "ja_marcada": False, "feitas": 2}


def test_o_dia_e_o_de_brasilia_e_nao_o_do_relogio_de_londres(conn):
    _treino_abc(conn)
    cinco_depois_da_meia_noite = datetime(2026, 10, 15, 3, 5, tzinfo=timezone.utc)  # 00h05 de 15/10 em Brasília
    cinco_antes_da_meia_noite = datetime(2026, 10, 16, 2, 55, tzinfo=timezone.utc)  # 23h55 de 15/10 em Brasília (16/10 em UTC)
    cinco_depois_da_virada = datetime(2026, 10, 16, 3, 5, tzinfo=timezone.utc)  # 00h05 de 16/10 em Brasília

    assert marcar_ficha_feita(conn, 1, 1, cinco_depois_da_meia_noite)["ja_marcada"] is False
    assert marcar_ficha_feita(conn, 1, 1, cinco_antes_da_meia_noite)["ja_marcada"] is True  # mesmo dia em Brasília
    assert marcar_ficha_feita(conn, 1, 1, cinco_depois_da_virada)["ja_marcada"] is False  # já é outro dia


def test_fichas_diferentes_no_mesmo_dia_contam_cada_uma(conn):
    _treino_abc(conn)

    marcar_ficha_feita(conn, 1, 1, MEIO_DIA)
    marcar_ficha_feita(conn, 1, 2, MEIO_DIA)

    assert [ordem for ordem, _ in _sessoes(conn)] == [1, 2]


def test_a_contagem_alimenta_o_ciclo_do_professor(conn):
    treino_id = _treino_abc(conn, sessoes_por_ficha=2)
    marcar_ficha_feita(conn, 1, 1, MEIO_DIA)
    marcar_ficha_feita(conn, 1, 1, MEIO_DIA + timedelta(days=1))

    assert ciclo.sessoes_feitas_do_aluno(conn, 1) == {treino_id: {1: 2}}


@pytest.mark.parametrize("ficha", [0, -1, True, False, "1", None, 1.5, [1], {"a": 1}])
def test_ficha_que_nao_e_um_numero_valido_e_recusada(conn, ficha):
    _treino_abc(conn)

    with pytest.raises(MarcacaoInvalida) as erro:
        marcar_ficha_feita(conn, 1, ficha, MEIO_DIA)

    assert erro.value.status == 400
    assert _sessoes(conn) == [] and not conn.in_transaction


def test_ficha_que_o_treino_nao_tem_e_recusada(conn):
    _treino_abc(conn)

    with pytest.raises(MarcacaoInvalida) as erro:
        marcar_ficha_feita(conn, 1, 4, MEIO_DIA)

    assert erro.value.status == 404 and _sessoes(conn) == [] and not conn.in_transaction


def test_aluno_sem_treino_ativo_nao_marca_nada(conn):
    with pytest.raises(MarcacaoInvalida) as erro:
        marcar_ficha_feita(conn, 1, 1, MEIO_DIA)

    assert erro.value.status == 409 and not conn.in_transaction


def test_treino_concluido_nao_recebe_marcacao(conn):
    treino_id = _treino_abc(conn)
    ciclo.concluir_treino(conn, treino_id)

    with pytest.raises(MarcacaoInvalida) as erro:
        marcar_ficha_feita(conn, 1, 1, MEIO_DIA)

    assert erro.value.status == 409 and _sessoes(conn) == []


def test_marcar_so_mexe_no_treino_do_proprio_aluno(conn):
    _treino_abc(conn, aluno_id=1)
    _treino_abc(conn, aluno_id=2, nome="TREINO DO BRUNO")

    marcar_ficha_feita(conn, 1, 1, MEIO_DIA)

    assert len(_sessoes(conn, 1)) == 1 and _sessoes(conn, 2) == []


def test_dois_toques_ao_mesmo_tempo_gravam_uma_vez_so(caminho):
    conn = conectar(caminho)
    _treino_abc(conn)
    conn.close()
    resultados, erros = [], []
    largada = threading.Barrier(2)

    def tocar():
        c = conectar(caminho)
        try:
            largada.wait()
            resultados.append(marcar_ficha_feita(c, 1, 1, MEIO_DIA)["ja_marcada"])
        except Exception as erro:  # noqa: BLE001 - o teste quer ver qualquer falha
            erros.append(erro)
        finally:
            c.close()

    fios = [threading.Thread(target=tocar) for _ in range(2)]
    for fio in fios:
        fio.start()
    for fio in fios:
        fio.join()

    assert erros == []
    assert sorted(resultados) == [False, True]  # um gravou, o outro viu que já estava marcada
    c = conectar(caminho)
    assert len(_sessoes(c)) == 1
    c.close()


# ------------------------------------------------------------------ desfazer


def test_desfazer_apaga_a_marcacao_de_hoje_e_deixa_marcar_de_novo(conn):
    _treino_abc(conn)
    marcar_ficha_feita(conn, 1, 1, MEIO_DIA)

    assert desfazer_marcacao_de_hoje(conn, 1, 1, MEIO_DIA) == {"ficha": 1, "feitas": 0}
    assert marcar_ficha_feita(conn, 1, 1, MEIO_DIA)["ja_marcada"] is False


def test_desfazer_nunca_apaga_marcacao_de_outro_dia(conn):
    _treino_abc(conn)
    marcar_ficha_feita(conn, 1, 1, MEIO_DIA - timedelta(days=1))
    marcar_ficha_feita(conn, 1, 1, MEIO_DIA)

    assert desfazer_marcacao_de_hoje(conn, 1, 1, MEIO_DIA) == {"ficha": 1, "feitas": 1}
    assert _sessoes(conn) == [(1, "2026-10-14 15:00:00")]


def test_desfazer_sem_marcacao_hoje_nao_muda_nada(conn):
    _treino_abc(conn)
    marcar_ficha_feita(conn, 1, 1, MEIO_DIA - timedelta(days=1))

    assert desfazer_marcacao_de_hoje(conn, 1, 1, MEIO_DIA) == {"ficha": 1, "feitas": 1}


def test_desfazer_so_mexe_na_ficha_pedida_e_no_proprio_aluno(conn):
    _treino_abc(conn, aluno_id=1)
    _treino_abc(conn, aluno_id=2, nome="TREINO DO BRUNO")
    for aluno in (1, 2):
        marcar_ficha_feita(conn, aluno, 1, MEIO_DIA)
        marcar_ficha_feita(conn, aluno, 2, MEIO_DIA)

    desfazer_marcacao_de_hoje(conn, 1, 1, MEIO_DIA)

    assert [o for o, _ in _sessoes(conn, 1)] == [2]
    assert [o for o, _ in _sessoes(conn, 2)] == [1, 2]


@pytest.mark.parametrize("ficha", [0, True, "1", None])
def test_desfazer_ficha_invalida_e_recusado(conn, ficha):
    _treino_abc(conn)

    with pytest.raises(MarcacaoInvalida) as erro:
        desfazer_marcacao_de_hoje(conn, 1, ficha, MEIO_DIA)

    assert erro.value.status == 400 and not conn.in_transaction


# ------------------------------------------------------------------ o que a tela recebe


def test_o_treino_traz_ordem_feitas_feita_hoje_e_a_meta(conn):
    _treino_abc(conn, sessoes_por_ficha=15)
    marcar_ficha_feita(conn, 1, 1, MEIO_DIA - timedelta(days=2))
    marcar_ficha_feita(conn, 1, 1, MEIO_DIA)
    marcar_ficha_feita(conn, 1, 2, MEIO_DIA - timedelta(days=1))

    treino = treino_do_aluno(conn, 1, MEIO_DIA)

    assert treino["meta_por_ficha"] == 15
    assert [(f["ordem"], f["feitas"], f["feita_hoje"]) for f in treino["fichas"]] == [(1, 2, True), (2, 1, False), (3, 0, False)]


def test_sem_meta_o_treino_traz_meta_nula(conn):
    _treino_abc(conn)

    assert treino_do_aluno(conn, 1, MEIO_DIA)["meta_por_ficha"] is None


def test_treino_novo_comeca_a_contar_do_zero(conn):
    _treino_abc(conn, nome="TREINO ANTIGO")
    marcar_ficha_feita(conn, 1, 1, MEIO_DIA - timedelta(days=3))
    _treino_abc(conn, nome="TREINO NOVO")  # conclui o antigo

    treino = treino_do_aluno(conn, 1, MEIO_DIA)

    assert treino["nome"] == "TREINO NOVO" and [f["feitas"] for f in treino["fichas"]] == [0, 0, 0]


# ------------------------------------------------------------------ as rotas de marcar e desfazer


def _post(cliente, rota, corpo):
    return cliente.post(f"/api/aluno/treino/{rota}", json=corpo)


def test_rotas_de_marcar_sem_login_respondem_401(caminho):
    cliente = criar_app(caminho).test_client()

    assert _post(cliente, "feito", {"ficha": 1}).status_code == 401
    assert _post(cliente, "desfazer", {"ficha": 1}).status_code == 401


def test_marcar_e_desfazer_pela_rota(caminho, cliente_da_ana):
    conn = conectar(caminho)
    _treino_abc(conn)
    conn.close()

    primeira = _post(cliente_da_ana, "feito", {"ficha": 1})
    segunda = _post(cliente_da_ana, "feito", {"ficha": 1})
    depois = cliente_da_ana.get("/api/aluno/treino").get_json()["treino"]["fichas"][0]
    desfeita = _post(cliente_da_ana, "desfazer", {"ficha": 1})
    final = cliente_da_ana.get("/api/aluno/treino").get_json()["treino"]["fichas"][0]

    assert primeira.status_code == 200 and primeira.get_json() == {"ok": True, "ficha": 1, "ja_marcada": False, "feitas": 1}
    assert segunda.get_json()["ja_marcada"] is True and segunda.get_json()["feitas"] == 1
    assert depois["feita_hoje"] is True and depois["feitas"] == 1
    assert desfeita.get_json() == {"ok": True, "ficha": 1, "feitas": 0}
    assert final["feita_hoje"] is False and final["feitas"] == 0


@pytest.mark.parametrize("corpo", [{}, {"ficha": "1"}, {"ficha": 0}, {"ficha": True}, {"ficha": None}, [], "ficha", 7])
def test_corpo_estranho_da_400_e_nao_grava(caminho, cliente_da_ana, corpo):
    conn = conectar(caminho)
    _treino_abc(conn)
    conn.close()

    resposta = _post(cliente_da_ana, "feito", corpo)

    assert resposta.status_code == 400 and "erro" in resposta.get_json()
    conn = conectar(caminho)
    assert _sessoes(conn) == []
    conn.close()


def test_ficha_que_nao_existe_da_404_e_sem_treino_da_409(caminho, cliente_da_ana):
    assert _post(cliente_da_ana, "feito", {"ficha": 1}).status_code == 409
    conn = conectar(caminho)
    _treino_abc(conn)
    conn.close()

    assert _post(cliente_da_ana, "feito", {"ficha": 9}).status_code == 404


def test_marcar_exige_json_e_origem_do_proprio_site(caminho, cliente_da_ana):
    conn = conectar(caminho)
    _treino_abc(conn)
    conn.close()

    assert cliente_da_ana.post("/api/aluno/treino/feito", data="ficha=1").status_code == 415
    de_outro_site = cliente_da_ana.post("/api/aluno/treino/feito", json={"ficha": 1}, headers={"Origin": "https://site-malvado.example"})
    assert de_outro_site.status_code == 403
    conn = conectar(caminho)
    assert _sessoes(conn) == []
    conn.close()


def test_o_aluno_nao_consegue_marcar_no_treino_de_outro_mandando_ids(caminho, cliente_da_ana):
    conn = conectar(caminho)
    _treino_abc(conn, aluno_id=1)
    _treino_abc(conn, aluno_id=2, nome="TREINO DO BRUNO")
    conn.close()

    resposta = _post(cliente_da_ana, "feito", {"ficha": 1, "aluno_id": 2, "treino_id": 2})

    assert resposta.status_code == 200
    conn = conectar(caminho)
    assert len(_sessoes(conn, 1)) == 1 and _sessoes(conn, 2) == []
    conn.close()


def test_o_computador_do_professor_nao_marca_ficha_de_aluno(caminho):
    from app import acesso

    conn = conectar(caminho)
    codigo = acesso.gerar_codigo(conn, "Computador dos professores").codigo
    _treino_abc(conn)
    conn.close()
    professor = criar_app(caminho).test_client()
    assert professor.post("/api/autorizar", json={"codigo": codigo}).status_code == 200

    assert _post(professor, "feito", {"ficha": 1}).status_code == 401
