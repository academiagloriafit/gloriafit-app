"""Exercícios que existem só no app (app/exercicios_do_app.py)."""

import pytest

from app import exercicios
from app.db import conectar, criar_tabelas
from app.exercicios_do_app import EXERCICIOS_DO_APP, garantir_exercicios_do_app


@pytest.fixture
def conn():
    c = conectar()
    criar_tabelas(c)
    c.execute("INSERT INTO grupo_muscular (nome, ordem) VALUES ('Cardio', 1)")
    c.commit()
    yield c
    c.close()


def _linhas(conn):
    return conn.execute(
        "SELECT e.nome, e.ativo, e.origem, g.nome AS grupo FROM exercicio e"
        " LEFT JOIN exercicio_grupo eg ON eg.exercicio_id = e.id LEFT JOIN grupo_muscular g ON g.id = eg.grupo_id"
        " ORDER BY e.nome"
    ).fetchall()


def test_cria_o_exercicio_no_grupo_cardio_e_ele_aparece_na_lista(conn):
    resumo = garantir_exercicios_do_app(conn)

    assert resumo == {"criados": ["ELÍPTICO"], "ativados": [], "sem_grupo": []}
    assert [tuple(l) for l in _linhas(conn)] == [("ELÍPTICO", 1, "app", "Cardio")]
    achados = exercicios.buscar_exercicios(conn, texto="eliptico")  # sem acento também acha
    assert [e["nome"] for e in achados["exercicios"]] == ["ELÍPTICO"]
    assert achados["exercicios"][0]["grupos"] == ["Cardio"]


def test_pode_rodar_de_novo_sem_duplicar(conn):
    garantir_exercicios_do_app(conn)
    resumo = garantir_exercicios_do_app(conn)

    assert resumo == {"criados": [], "ativados": [], "sem_grupo": []}
    assert len(_linhas(conn)) == 1


def test_exercicio_inativo_do_historico_com_o_mesmo_nome_e_ativado_sem_trocar_o_id(conn):
    # o histórico do Data4U cria exercícios inativos; as prescrições antigas continuam ligadas a ele
    antigo = conn.execute(
        "INSERT INTO exercicio (nome, ativo, combinado, origem) VALUES ('ELÍPTICO', 0, 0, 'data4u_academia')"
    ).lastrowid
    conn.commit()

    resumo = garantir_exercicios_do_app(conn)

    assert resumo == {"criados": [], "ativados": ["ELÍPTICO"], "sem_grupo": []}
    assert conn.execute("SELECT id, ativo, origem FROM exercicio").fetchone()[:] == (antigo, 1, "data4u_academia")
    assert [e["nome"] for e in exercicios.buscar_exercicios(conn, texto="eliptico")["exercicios"]] == ["ELÍPTICO"]


def test_sem_o_grupo_o_exercicio_fica_sem_grupo_e_avisa(conn):
    conn.execute("DELETE FROM grupo_muscular")
    conn.commit()

    resumo = garantir_exercicios_do_app(conn)

    assert resumo["sem_grupo"] == ["ELÍPTICO"]
    assert conn.execute("SELECT COUNT(*) FROM exercicio_grupo").fetchone()[0] == 0


def test_a_lista_tem_so_exercicios_do_grupo_que_o_quadro_importa():
    from app.importar_exercicios import GRUPOS

    assert {grupo for _, grupo in EXERCICIOS_DO_APP} <= set(GRUPOS)
