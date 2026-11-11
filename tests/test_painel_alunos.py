"""Tela "Alunos" do professor, visual novo (app/painel_alunos.py, 11/11/2026): números do alto, filtros e andamento. Dados inventados."""

from datetime import datetime, timedelta, timezone

import pytest

from app import acesso, painel_alunos
from app.db import conectar, criar_tabelas
from app.web import criar_app

AGORA = datetime(2026, 11, 11, 15, 0, tzinfo=timezone.utc)  # 11/11/2026, meio-dia em Vila Velha


def _texto(momento):
    return momento.strftime("%Y-%m-%d %H:%M:%S")


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "p.db"
    c = conectar(caminho)
    criar_tabelas(c)
    c.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO', 'app')")
    for i, (nome, situacao) in enumerate([("ANA TREINOU HOJE", "A"), ("BIA SUMIDA", "A"), ("CAIO SEM TREINO", "A"), ("DAVI INATIVO", "I")], 1):
        c.execute("INSERT INTO aluno (id, nome, cpf, situacao, data4u_id) VALUES (?, ?, ?, ?, ?)", (i, nome, f"0000000000{i}", situacao, 100 + i))
    for treino_id, aluno, meta in ((1, 1, 10), (2, 2, None)):
        c.execute(
            "INSERT INTO treino (id, aluno_id, nome, montado_por, ativo, inicio, sessoes_por_ficha) VALUES (?, ?, 'TREINO AB', 'P', 1, '2026-10-01', ?)",
            (treino_id, aluno, meta),
        )
        for ordem in (1, 2):
            f = c.execute("INSERT INTO ficha (treino_id, nome, ordem) VALUES (?, ?, ?)", (treino_id, chr(64 + ordem), ordem)).lastrowid
            c.execute("INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, series, repeticoes) VALUES (?, 1, 1, '3', '12')", (f,))
    for dias in (0, 1, 2, 3, 4):  # Ana: 5 sessões, a última hoje
        c.execute("INSERT INTO sessao (treino_id, ficha_ordem, feita_em) VALUES (1, 1, ?)", (_texto(AGORA - timedelta(days=dias)),))
    c.execute("INSERT INTO sessao (treino_id, ficha_ordem, feita_em) VALUES (2, 1, ?)", (_texto(AGORA - timedelta(days=20)),))  # Bia
    c.execute(
        "INSERT INTO comentario (aluno_id, treino_nome, texto, criado_em) VALUES (2, 'TREINO AB', 'Dor no ombro', ?)", (_texto(AGORA),)
    )
    c.commit()
    c.close()
    return caminho


@pytest.fixture
def conn(caminho):
    c = conectar(caminho)
    yield c
    c.close()


def test_numeros_do_alto(conn):
    n = painel_alunos.numeros(conn, AGORA)
    assert n["ativos"] == 3 and n["hoje"] == 1 and n["comentarios"] == 1
    assert n["sem_treino"] == 1  # Caio (ativo sem treino); Davi é inativo
    assert n["sumiram"] == 1 and n["dias_sumido"] == 7  # Bia, 20 dias parada


def test_filtros_devolvem_os_alunos_certos(conn):
    assert painel_alunos.ids_do_filtro(conn, "hoje", AGORA) == {1}
    assert painel_alunos.ids_do_filtro(conn, "sumiram", AGORA) == {2}
    assert painel_alunos.ids_do_filtro(conn, "comentarios", AGORA) == {2}
    assert painel_alunos.ids_do_filtro(conn, "sem_treino", AGORA) == {3}
    assert painel_alunos.ids_do_filtro(conn, "qualquer coisa", AGORA) is None


def test_andamento_com_meta_sem_meta_e_sem_treino(conn):
    a = painel_alunos.andamento(conn, [1, 2, 3], AGORA)
    assert a[1] == {"treino_atual": "TREINO AB", "feitas": 5, "meta_total": 20, "progresso": 25, "ultimo_feito": "2026-11-11", "dias_sem_treinar": 0}
    assert a[2]["meta_total"] is None and a[2]["progresso"] is None and a[2]["dias_sem_treinar"] == 20
    assert a[3]["treino_atual"] is None and a[3]["dias_sem_treinar"] is None
    assert painel_alunos.andamento(conn, [], AGORA) == {}


def _autorizado(app, caminho):
    navegador = app.test_client()
    c = conectar(caminho)
    token = acesso.autorizar(c, acesso.gerar_codigo(c, "Computador de teste").codigo).token
    c.close()
    navegador.set_cookie(acesso.NOME_DO_COOKIE, token)
    return navegador


def test_a_api_filtra_e_traz_o_andamento(caminho):
    navegador = _autorizado(criar_app(caminho), caminho)
    tudo = navegador.get("/api/alunos").get_json()
    assert tudo["total"] == 4 and tudo["filtro"] == ""
    ativos = navegador.get("/api/alunos?filtro=ativos").get_json()
    assert sorted(a["nome"] for a in ativos["alunos"]) == ["ANA TREINOU HOJE", "BIA SUMIDA", "CAIO SEM TREINO"]
    sem = navegador.get("/api/alunos?filtro=sem_treino").get_json()
    assert [a["nome"] for a in sem["alunos"]] == ["CAIO SEM TREINO"]
    ana = navegador.get("/api/alunos?q=ana").get_json()["alunos"][0]
    assert ana["treino_atual"] == "TREINO AB" and ana["sessoes_meta"] == 20 and ana["sessoes_feitas"] == 5
    # filtro desconhecido não quebra nem filtra; texto de ataque vira texto
    assert navegador.get("/api/alunos?filtro=1%27%20OR%201%3D1").get_json()["total"] == 4
    # filtro + busca juntos
    assert navegador.get("/api/alunos?filtro=ativos&q=bia").get_json()["total"] == 1


def test_a_tela_tem_o_logo_oficial_e_os_numeros(caminho):
    html = _autorizado(criar_app(caminho), caminho).get("/alunos").get_data(as_text=True)
    assert "logo-completo-fundo-claro.png" in html and 'alt="Academia Glória Fit"' in html
    for pedaco in ('data-filtro="ativos"', 'data-filtro="hoje"', 'data-filtro="trocar"', 'data-filtro="comentarios"', 'data-filtro="sumiram"', "Alunos ativos"):
        assert pedaco in html, pedaco
