"""Testes do quadro "Últimos treinos" na ficha do aluno (ciclo.ultimas_sessoes_do_aluno e GET /alunos/<id>). Dados inventados."""

from datetime import datetime, timedelta, timezone

import pytest

from app import acesso, ciclo, treinos
from app.aluno_treino import definir_esforco, marcar_ficha_feita
from app.db import conectar, criar_tabelas
from app.web import criar_app

AGORA = datetime(2026, 10, 22, 15, 0, tzinfo=timezone.utc)  # 12h00 em Brasília


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "ultimos.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.executemany(
        "INSERT INTO aluno (id, nome, cpf, whatsapp, situacao) VALUES (?, ?, ?, ?, ?)",
        [(1, "ANA SOUZA", "11144477735", "27988887766", "A"), (2, "BRUNO LIMA", "52998224725", "27977776655", "A")],
    )
    conn.execute("INSERT INTO exercicio (nome, origem) VALUES ('SUPINO RETO', 'app')")
    conn.commit()
    conn.close()
    return caminho


@pytest.fixture
def conn(caminho):
    c = conectar(caminho)
    yield c
    c.close()


def _treino(conn, aluno_id=1, nome="TREINO ABC"):
    itens = [{"exercicio_id": 1, "series": "4", "repeticoes": "12"}]
    return treinos.salvar_treino(
        conn,
        aluno_id,
        {"nome_treino": nome, "montado_por": "PROFESSORA", "fichas": [{"nome": "A PEITO", "itens": itens}, {"nome": "B COSTAS", "itens": itens}]},
    )


def test_sem_nenhum_treino_feito_a_lista_vem_vazia(conn):
    _treino(conn)

    assert ciclo.ultimas_sessoes_do_aluno(conn, 1) == []


def test_os_mais_novos_vem_primeiro_com_ficha_treino_data_e_nota(conn):
    _treino(conn)
    marcar_ficha_feita(conn, 1, 1, AGORA - timedelta(days=2))
    definir_esforco(conn, 1, 1, 3, AGORA - timedelta(days=2))
    marcar_ficha_feita(conn, 1, 2, AGORA)

    assert ciclo.ultimas_sessoes_do_aluno(conn, 1) == [
        {"data": "22/10/2026", "treino": "TREINO ABC", "ficha": "B COSTAS", "esforco": None, "esforco_nome": ""},
        {"data": "20/10/2026", "treino": "TREINO ABC", "ficha": "A PEITO", "esforco": 3, "esforco_nome": "Pesado"},
    ]


def test_o_papel_impresso_aparece_sem_nota(conn):
    treino_id = _treino(conn)
    ciclo.marcar_impressao(conn, treino_id, 1, AGORA)

    assert ciclo.ultimas_sessoes_do_aluno(conn, 1)[0]["esforco_nome"] == ""


@pytest.mark.parametrize(("nota", "nome"), [(1, "Leve"), (2, "Ideal"), (3, "Pesado")])
def test_as_tres_notas_tem_nome(conn, nota, nome):
    _treino(conn)
    marcar_ficha_feita(conn, 1, 1, AGORA)
    definir_esforco(conn, 1, 1, nota, AGORA)

    assert ciclo.ultimas_sessoes_do_aluno(conn, 1)[0]["esforco_nome"] == nome


def test_vale_o_dia_de_brasilia(conn):
    _treino(conn)
    marcar_ficha_feita(conn, 1, 1, datetime(2026, 10, 22, 2, 30, tzinfo=timezone.utc))  # 21/10 23h30 em Brasília

    assert ciclo.ultimas_sessoes_do_aluno(conn, 1)[0]["data"] == "21/10/2026"


def test_inclui_treino_antigo_e_so_do_proprio_aluno(conn):
    _treino(conn, 1, nome="TREINO ANTIGO")
    marcar_ficha_feita(conn, 1, 1, AGORA - timedelta(days=30))
    _treino(conn, 1, nome="TREINO NOVO")  # conclui o antigo
    _treino(conn, 2, nome="TREINO DO BRUNO")
    marcar_ficha_feita(conn, 2, 1, AGORA)

    treinos_do_aluno = [u["treino"] for u in ciclo.ultimas_sessoes_do_aluno(conn, 1)]

    assert treinos_do_aluno == ["TREINO ANTIGO"]


def test_respeita_o_limite(conn):
    _treino(conn)
    for dias in range(15):
        marcar_ficha_feita(conn, 1, 1, AGORA - timedelta(days=dias))

    assert len(ciclo.ultimas_sessoes_do_aluno(conn, 1)) == 10
    assert len(ciclo.ultimas_sessoes_do_aluno(conn, 1, limite=3)) == 3


def test_ficha_que_ja_nao_existe_cai_no_numero(conn):
    treino_id = _treino(conn)
    marcar_ficha_feita(conn, 1, 2, AGORA)
    conn.execute("DELETE FROM ficha WHERE treino_id = ? AND ordem = 2", (treino_id,))
    conn.commit()

    assert ciclo.ultimas_sessoes_do_aluno(conn, 1)[0]["ficha"] == "Ficha 2"


# ------------------------------------------------------------------ na ficha do aluno


@pytest.fixture
def professor(caminho):
    conn = conectar(caminho)
    codigo = acesso.gerar_codigo(conn, "Computador dos professores").codigo
    conn.close()
    cliente = criar_app(caminho).test_client()
    assert cliente.post("/api/autorizar", json={"codigo": codigo}).status_code == 200
    return cliente


def test_a_ficha_mostra_os_ultimos_treinos_com_a_nota(caminho, professor):
    conn = conectar(caminho)
    _treino(conn)
    agora = datetime.now(timezone.utc)
    marcar_ficha_feita(conn, 1, 1, agora)
    definir_esforco(conn, 1, 1, 2, agora)
    conn.close()

    html = professor.get("/alunos/1").get_data(as_text=True)

    assert 'id="ultimos-treinos"' in html and "Últimos treinos" in html
    assert "A PEITO" in html and "Ideal" in html


def test_sem_treino_feito_o_quadro_nem_aparece(caminho, professor):
    conn = conectar(caminho)
    _treino(conn)
    conn.close()

    assert 'id="ultimos-treinos"' not in professor.get("/alunos/1").get_data(as_text=True)


def test_nome_do_treino_nunca_vira_html_no_quadro(caminho, professor):
    conn = conectar(caminho)
    _treino(conn, nome="<i>ABC</i>")
    marcar_ficha_feita(conn, 1, 1, datetime.now(timezone.utc))
    conn.close()

    html = professor.get("/alunos/1").get_data(as_text=True)

    assert "<i>ABC</i>" not in html and "&lt;i&gt;ABC&lt;/i&gt;" in html
