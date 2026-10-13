"""Editar treino no lugar (app/treinos.py: editar_treino) e as rotas /api/treinos/<id>/editar e /para-editar.

Dados inventados. Regras testadas (combinadas com o Thiago em 13/10/2026): treino criado no app e ATIVO muda no
lugar; treino do Data4U não muda (a tela abre uma cópia, que vira treino novo); treino concluído não muda.
"""

import pytest

from app import acesso, ciclo, modelos
from app.db import conectar, criar_tabelas
from app.treinos import TreinoInvalido, TreinoNaoEncontrado, editar_treino, obter_treino, salvar_treino
from app.web import criar_app

# ------------------------------------------------------------------ preparação


@pytest.fixture
def conn():
    c = conectar()
    criar_tabelas(c)
    c.execute("INSERT INTO aluno (id, nome) VALUES (1, 'ANA FICTICIA'), (2, 'BRUNO FICTICIO')")
    for exercicio_id, nome, ativo in [(1, "SUPINO RETO", 1), (2, "REMADA", 1), (3, "AGACHAMENTO", 1), (4, "DESATIVADO", 0)]:
        c.execute("INSERT INTO exercicio (id, nome, origem, ativo) VALUES (?, ?, 'app', ?)", (exercicio_id, nome, ativo))
    c.commit()
    yield c
    c.close()


def _item(exercicio_id, series="3", repeticoes="12", **extras):
    return {"exercicio_id": exercicio_id, "series": series, "repeticoes": repeticoes, **extras}


def _pedido(nome="TREINO ABC", fichas=None, professor="Bia", **extras):
    fichas = fichas if fichas is not None else [{"nome": "FICHA A", "itens": [_item(1), _item(2)]}]
    return {"nome_treino": nome, "montado_por": professor, "fichas": fichas, **extras}


def _treino_do_data4u(conn, aluno_id=1, nome="TREINO DO DATA4U", ativo=1):
    """Um treino como o importador grava: origem 'data4u'."""
    data4u_id = conn.execute("SELECT COALESCE(MAX(data4u_id), 700) + 1 FROM treino").fetchone()[0]  # único por treino
    treino_id = conn.execute(
        "INSERT INTO treino (aluno_id, nome, montado_por, origem, data4u_id, ativo) VALUES (?, ?, 'PROF DATA4U', 'data4u', ?, ?)",
        (aluno_id, nome, data4u_id, ativo),
    ).lastrowid
    ficha_id = conn.execute("INSERT INTO ficha (treino_id, nome, ordem) VALUES (?, 'FICHA A', 1)", (treino_id,)).lastrowid
    conn.execute("INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, series, repeticoes) VALUES (?, 1, 1, '3', '12')", (ficha_id,))
    conn.commit()
    return treino_id


def _recusado(conn, treino_id, dados, status):
    with pytest.raises(TreinoInvalido) as erro:
        editar_treino(conn, treino_id, dados)
    assert erro.value.status == status
    return erro.value.problemas


def _linhas(conn, sql, *args):
    return [tuple(linha) for linha in conn.execute(sql, args)]


# ------------------------------------------------------------------ editar no lugar


def test_troca_exercicios_nome_professor_e_datas_e_mantem_o_resto(conn):
    treino_id = salvar_treino(conn, 1, _pedido(inicio="2026-10-01"))
    criado_em = conn.execute("SELECT criado_em FROM treino WHERE id = ?", (treino_id,)).fetchone()[0]

    editar_treino(
        conn,
        treino_id,
        _pedido(
            nome="TREINO AB",
            professor="Carlos",
            inicio="2026-10-05",
            fim="2026-11-05",
            sessoes_por_ficha=15,
            fichas=[
                {"nome": "SUPERIOR", "itens": [_item(3, "4", "10", carga="20kg", pausa=90, observacao="devagar")]},
                {"nome": "INFERIOR", "itens": [_item(2), _item(1)]},
            ],
        ),
    )

    treino = obter_treino(conn, treino_id)
    assert (treino["nome"], treino["montado_por"], treino["inicio"], treino["fim"], treino["sessoes_por_ficha"]) == (
        "TREINO AB", "Carlos", "2026-10-05", "2026-11-05", 15,
    )
    assert [f["nome"] for f in treino["fichas"]] == ["SUPERIOR", "INFERIOR"]
    primeiro = treino["fichas"][0]["itens"][0]
    assert (primeiro["exercicio"], primeiro["series"], primeiro["repeticoes"], primeiro["carga"], primeiro["pausa"], primeiro["observacao"]) == (
        "AGACHAMENTO", "4", "10", "20kg", 90, "devagar",
    )
    assert [i["exercicio"] for i in treino["fichas"][1]["itens"]] == ["REMADA", "SUPINO RETO"]
    # continua o mesmo treino: ativo, mesmo dia de criação, mesma origem; só uma linha de treino no aluno
    assert (treino["ativo"], treino["origem"], treino["criado_em"]) == (1, "app", criado_em)
    assert _linhas(conn, "SELECT COUNT(*) FROM treino WHERE aluno_id = 1") == [(1,)]
    # nenhuma ficha ou item sobrou do treino antigo
    assert _linhas(conn, "SELECT COUNT(*) FROM ficha") == [(2,)]
    assert _linhas(conn, "SELECT COUNT(*) FROM ficha_item") == [(3,)]


def test_pode_manter_o_proprio_nome(conn):
    treino_id = salvar_treino(conn, 1, _pedido(nome="MEU TREINO"))

    editar_treino(conn, treino_id, _pedido(nome="meu treino", fichas=[{"nome": "A", "itens": [_item(3)]}]))

    assert obter_treino(conn, treino_id)["nome"] == "meu treino"


def test_as_sessoes_ja_feitas_ficam(conn):
    treino_id = salvar_treino(conn, 1, _pedido(sessoes_por_ficha=10))
    ciclo.registrar_sessao(conn, treino_id, 1)
    ciclo.registrar_sessao(conn, treino_id, 1)

    editar_treino(conn, treino_id, _pedido(sessoes_por_ficha=10, fichas=[{"nome": "NOVA", "itens": [_item(3)]}]))

    assert ciclo.sessoes_feitas_do_aluno(conn, 1) == {treino_id: {1: 2}}


def test_nao_mexe_no_treino_de_outro_aluno_nem_em_outro_treino_do_mesmo(conn):
    meu = salvar_treino(conn, 1, _pedido(nome="MEU"))
    do_outro = salvar_treino(conn, 2, _pedido(nome="DO OUTRO"))

    editar_treino(conn, meu, _pedido(nome="MEU NOVO", fichas=[{"nome": "A", "itens": [_item(3)]}]))

    assert obter_treino(conn, do_outro)["nome"] == "DO OUTRO"
    assert [i["exercicio"] for i in obter_treino(conn, do_outro)["fichas"][0]["itens"]] == ["SUPINO RETO", "REMADA"]


# ------------------------------------------------------------------ o que não se edita no lugar


def test_treino_que_nao_existe(conn):
    with pytest.raises(TreinoNaoEncontrado):
        editar_treino(conn, 999, _pedido())


def test_treino_do_data4u_nao_e_editado_no_lugar(conn):
    treino_id = _treino_do_data4u(conn)

    problemas = _recusado(conn, treino_id, _pedido(nome="OUTRO NOME"), 409)

    assert "Data4U" in problemas[0]
    antes = obter_treino(conn, treino_id)
    assert (antes["nome"], antes["montado_por"]) == ("TREINO DO DATA4U", "PROF DATA4U")
    assert len(antes["fichas"][0]["itens"]) == 1


def test_treino_concluido_nao_e_editado(conn):
    treino_id = salvar_treino(conn, 1, _pedido())
    ciclo.concluir_treino(conn, treino_id)

    problemas = _recusado(conn, treino_id, _pedido(nome="OUTRO"), 409)

    assert "concluído" in problemas[0]
    assert obter_treino(conn, treino_id)["nome"] == "TREINO ABC"


def test_treino_substituido_por_um_novo_deixa_de_ser_editavel(conn):
    antigo = salvar_treino(conn, 1, _pedido(nome="ANTIGO"))
    salvar_treino(conn, 1, _pedido(nome="NOVO", fichas=[{"nome": "A", "itens": [_item(3)]}]))  # conclui o antigo

    _recusado(conn, antigo, _pedido(nome="ANTIGO 2"), 409)


# ------------------------------------------------------------------ a mesma conferência de salvar


def test_nome_de_outro_treino_do_aluno_e_recusado_inclusive_do_historico_do_data4u(conn):
    _treino_do_data4u(conn, nome="TREINO DO DATA4U", ativo=0)
    treino_id = salvar_treino(conn, 1, _pedido(nome="MEU"))

    problemas = _recusado(conn, treino_id, _pedido(nome="treino do data4u"), 409)

    assert "já tem um treino chamado" in problemas[0]
    assert obter_treino(conn, treino_id)["nome"] == "MEU"


def test_o_mesmo_nome_em_outro_aluno_vale(conn):
    salvar_treino(conn, 2, _pedido(nome="IGUAL"))
    treino_id = salvar_treino(conn, 1, _pedido(nome="MEU"))

    editar_treino(conn, treino_id, _pedido(nome="IGUAL"))

    assert obter_treino(conn, treino_id)["nome"] == "IGUAL"


@pytest.mark.parametrize(
    "mudanca, trecho",
    [
        ({"nome_treino": "  "}, "nome do treino"),
        ({"montado_por": ""}, "quem montou"),
        ({"inicio": "2026-10-10", "fim": "2026-10-01"}, "fim não pode"),
        ({"fichas": []}, "fichas"),
        ({"fichas": [{"nome": "A", "itens": [_item(4)]}]}, "exerc"),  # exercício desativado
        ({"fichas": [{"nome": "A", "itens": [_item(999)]}]}, "exerc"),  # não existe
        ({"fichas": [{"nome": "A", "itens": [_item(1, series="x" * 12)]}]}, "11"),
    ],
)
def test_dado_invalido_e_recusado_e_o_treino_fica_como_estava(conn, mudanca, trecho):
    treino_id = salvar_treino(conn, 1, _pedido(nome="MEU"))
    pedido = {**_pedido(nome="MEU"), **mudanca}

    problemas = _recusado(conn, treino_id, pedido, 400)

    assert any(trecho in p for p in problemas)
    treino = obter_treino(conn, treino_id)
    assert treino["montado_por"] == "Bia"
    assert [i["exercicio"] for i in treino["fichas"][0]["itens"]] == ["SUPINO RETO", "REMADA"]


def test_pedido_que_nao_e_um_objeto_e_recusado(conn):
    treino_id = salvar_treino(conn, 1, _pedido())

    problemas = _recusado(conn, treino_id, ["isto não é um treino"], 400)

    assert problemas == ["Formato do pedido inválido."]


def test_bi_set_e_renumerado_como_ao_salvar(conn):
    treino_id = salvar_treino(conn, 1, _pedido())

    editar_treino(
        conn,
        treino_id,
        _pedido(fichas=[{"nome": "A", "itens": [_item(1, bloco=7), _item(2, bloco=7), _item(3)]}]),
    )

    blocos = [i["bloco"] for i in obter_treino(conn, treino_id)["fichas"][0]["itens"]]
    assert blocos == [1, 1, None]


def test_se_a_gravacao_falha_no_meio_nada_muda(conn, monkeypatch):
    from app import treinos

    treino_id = salvar_treino(conn, 1, _pedido(nome="MEU"))

    def quebra(*_args, **_kwargs):
        raise RuntimeError("falha de teste")

    monkeypatch.setattr(treinos, "_gravar_fichas", quebra)
    with pytest.raises(RuntimeError):
        editar_treino(conn, treino_id, _pedido(nome="NOVO NOME", professor="Outro"))

    treino = obter_treino(conn, treino_id)
    assert (treino["nome"], treino["montado_por"]) == ("MEU", "Bia")
    assert [i["exercicio"] for i in treino["fichas"][0]["itens"]] == ["SUPINO RETO", "REMADA"]  # as fichas não sumiram


# ------------------------------------------------------------------ treino_para_editar


def test_para_editar_traz_o_treino_e_os_dados_do_ciclo(conn):
    treino_id = salvar_treino(conn, 1, _pedido(inicio="2026-10-01", fim="2026-12-01", sessoes_por_ficha=12))

    dados = modelos.treino_para_editar(conn, treino_id)

    assert dados["id"] == treino_id and dados["aluno_id"] == 1
    assert (dados["nome"], dados["montado_por"], dados["inicio"], dados["fim"]) == ("TREINO ABC", "Bia", "2026-10-01", "2026-12-01")
    assert (dados["sessoes_por_ficha"], dados["ativo"], dados["origem"]) == (12, True, "app")
    assert [i["nome"] for i in dados["fichas"][0]["itens"]] == ["SUPINO RETO", "REMADA"]
    assert dados["indisponiveis"] == 0


def test_para_editar_de_treino_do_data4u_diz_a_origem(conn):
    treino_id = _treino_do_data4u(conn)

    dados = modelos.treino_para_editar(conn, treino_id)

    assert (dados["origem"], dados["ativo"]) == ("data4u", True)


def test_para_editar_marca_exercicio_que_saiu_da_lista(conn):
    treino_id = salvar_treino(conn, 1, _pedido())
    conn.execute("UPDATE exercicio SET ativo = 0 WHERE id = 2")
    conn.commit()

    dados = modelos.treino_para_editar(conn, treino_id)

    assert dados["indisponiveis"] == 1
    assert [i["indisponivel"] for i in dados["fichas"][0]["itens"]] == [False, True]


def test_para_editar_de_treino_que_nao_existe(conn):
    assert modelos.treino_para_editar(conn, 999) is None


# ------------------------------------------------------------------ pela web


@pytest.fixture
def web(tmp_path):
    caminho = tmp_path / "editar.db"
    c = conectar(caminho)
    criar_tabelas(c)
    c.execute("INSERT INTO aluno (id, nome) VALUES (1, 'ANA FICTICIA')")
    c.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO RETO', 'app'), (2, 'REMADA', 'app')")
    c.commit()
    codigo = acesso.gerar_codigo(c, "Computador de teste").codigo
    token = acesso.autorizar(c, codigo).token
    treino_id = salvar_treino(c, 1, _pedido(nome="MEU"))
    c.close()
    app = criar_app(caminho)
    navegador = app.test_client()
    navegador.set_cookie(acesso.NOME_DO_COOKIE, token)
    return navegador, app.test_client(), caminho, treino_id


def test_web_edita_e_le_de_volta(web):
    cliente, _anonimo, _caminho, treino_id = web

    resposta = cliente.post(f"/api/treinos/{treino_id}/editar", json=_pedido(nome="MEU 2", professor="Carlos"))

    assert resposta.status_code == 200 and resposta.get_json() == {"id": treino_id}
    lido = cliente.get(f"/api/treinos/{treino_id}/para-editar").get_json()
    assert (lido["nome"], lido["montado_por"], lido["origem"], lido["ativo"]) == ("MEU 2", "Carlos", "app", True)


def test_web_erros_viram_os_codigos_certos(web):
    cliente, _anonimo, caminho, treino_id = web
    c = conectar(caminho)
    data4u = _treino_do_data4u(c, ativo=0)  # o aluno já tem o treino ativo MEU; a origem é o que barra
    c.close()

    assert cliente.post("/api/treinos/999/editar", json=_pedido()).status_code == 404
    assert cliente.get("/api/treinos/999/para-editar").status_code == 404
    invalido = cliente.post(f"/api/treinos/{treino_id}/editar", json=_pedido(nome=""))
    assert invalido.status_code == 400 and invalido.get_json()["erros"]
    do_data4u = cliente.post(f"/api/treinos/{data4u}/editar", json=_pedido(nome="X"))
    assert do_data4u.status_code == 409 and "Data4U" in do_data4u.get_json()["erros"][0]


def test_web_so_para_computador_autorizado_e_so_json_do_proprio_site(web):
    cliente, anonimo, _caminho, treino_id = web

    assert anonimo.get(f"/api/treinos/{treino_id}/para-editar").status_code == 401
    assert anonimo.post(f"/api/treinos/{treino_id}/editar", json=_pedido()).status_code == 401
    assert cliente.post(f"/api/treinos/{treino_id}/editar", json=_pedido(), headers={"Origin": "https://outro-site.example"}).status_code == 403
    assert cliente.post(f"/api/treinos/{treino_id}/editar", data="nome=x", content_type="application/x-www-form-urlencoded").status_code == 415
    assert cliente.get(f"/api/treinos/{treino_id}/editar").status_code == 405
    # nada foi mudado por nenhuma dessas tentativas
    assert cliente.get(f"/api/treinos/{treino_id}/para-editar").get_json()["nome"] == "MEU"


def test_a_ficha_mostra_editar_so_no_treino_ativo_e_escolhe_o_caminho_certo(web):
    cliente, _anonimo, caminho, treino_do_app = web
    c = conectar(caminho)
    c.execute("INSERT INTO aluno (id, nome) VALUES (2, 'BRUNO FICTICIO')")
    c.commit()
    ativo_do_data4u = _treino_do_data4u(c, aluno_id=2, nome="ATIVO DO DATA4U", ativo=1)
    inativo_do_data4u = _treino_do_data4u(c, aluno_id=2, nome="ANTIGO DO DATA4U", ativo=0)
    c.close()

    do_app = cliente.get("/alunos/1").get_data(as_text=True)
    do_data4u = cliente.get("/alunos/2").get_data(as_text=True)

    assert f"/alunos/1/montar?editar={treino_do_app}" in do_app  # criado no app: muda no lugar
    assert f"/alunos/2/montar?copiar={ativo_do_data4u}" in do_data4u  # do Data4U: abre uma cópia
    assert f"?copiar={inativo_do_data4u}" not in do_data4u  # concluído: sem botão
    assert do_data4u.count("Editar treino") == 1
