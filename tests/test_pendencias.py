"""Tela "Pendências" (app/pendencias.py): treino na hora de trocar, comentários sem ler e ativos sem treino. Dados inventados."""

from datetime import datetime, timezone

import pytest

from app import acesso, pendencias
from app.db import conectar, criar_tabelas
from app.web import criar_app

AGORA = datetime(2026, 10, 26, 15, 0, tzinfo=timezone.utc)  # 26/10/2026 em Brasília


def _treino(c, treino_id, aluno, fichas=2, meta=None, fim=None, ativo=1):
    c.execute(
        "INSERT INTO treino (id, aluno_id, nome, montado_por, ativo, inicio, fim, sessoes_por_ficha) VALUES (?, ?, ?, 'PROF', ?, '2026-09-01', ?, ?)",
        (treino_id, aluno, f"TREINO {treino_id}", ativo, fim, meta),
    )
    for ordem in range(1, fichas + 1):
        f = c.execute("INSERT INTO ficha (treino_id, nome, ordem) VALUES (?, ?, ?)", (treino_id, chr(64 + ordem), ordem)).lastrowid
        c.execute("INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, series, repeticoes) VALUES (?, 1, 1, '3', '12')", (f,))


def _sessoes(c, treino_id, ficha, quantas):
    for n in range(quantas):
        c.execute("INSERT INTO sessao (treino_id, ficha_ordem, feita_em) VALUES (?, ?, ?)", (treino_id, ficha, f"2026-10-{n + 1:02d} 20:00:00"))


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "pend.db"
    c = conectar(caminho)
    criar_tabelas(c)
    c.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO RETO', 'app')")
    alunos = [
        (1, "ANA META CUMPRIDA", "A", 0),
        (2, "BRUNO VENCIDO", "A", 0),
        (3, "CARLA NO MEIO", "A", 0),
        (4, "DANI SEM TREINO", "A", 0),
        (5, "EDU TRANCADO", "T", 0),
        (6, "FABI PROVISORIA", None, 1),
        (7, "GUI SO TREINO VELHO", "A", 0),
        (8, "HELO META E VENCIDO", "A", 0),
    ]
    c.executemany("INSERT INTO aluno (id, nome, situacao, provisorio) VALUES (?, ?, ?, ?)", alunos)
    _treino(c, 1, 1, fichas=2, meta=3)
    _sessoes(c, 1, 1, 3), _sessoes(c, 1, 2, 3)  # as duas fichas chegaram a 3
    _treino(c, 2, 2, fim="2026-10-20")  # venceu
    _treino(c, 3, 3, fichas=2, meta=3, fim="2026-12-01")
    _sessoes(c, 3, 1, 3), _sessoes(c, 3, 2, 1)  # uma ficha ainda não chegou
    _treino(c, 5, 5, fim="2026-01-01")  # trancado: não é pendência
    _treino(c, 7, 7, ativo=0)  # só um treino concluído: conta como sem treino
    _treino(c, 8, 8, fichas=1, meta=2, fim="2026-10-25")
    _sessoes(c, 8, 1, 2)
    _treino(c, 9, 4, fim="2026-10-26")  # Dani tem treino ativo? não: este é dela mas está concluído abaixo
    c.execute("UPDATE treino SET ativo = 0 WHERE id = 9")
    c.execute(
        "INSERT INTO comentario (aluno_id, treino_id, treino_nome, texto, criado_em) VALUES (3, 3, 'TREINO 3', 'Dor no ombro no supino', '2026-10-25 12:00:00')"
    )
    c.execute(
        "INSERT INTO comentario (aluno_id, treino_id, treino_nome, texto, criado_em, lido_em) VALUES (3, 3, 'TREINO 3', 'Já lido', '2026-10-20 12:00:00', '2026-10-21 12:00:00')"
    )
    c.commit()
    c.close()
    return caminho


@pytest.fixture
def conn(caminho):
    c = conectar(caminho)
    yield c
    c.close()


def test_hora_de_trocar_pega_meta_cumprida_e_vencido_so_de_quem_esta_ativo(conn):
    p = pendencias.listar(conn, AGORA)

    nomes = [a["nome"] for a in p["trocar"]["alunos"]]
    assert nomes == ["BRUNO VENCIDO", "HELO META E VENCIDO", "ANA META CUMPRIDA"]  # o vencido há mais tempo primeiro; sem fim por último
    motivos = {a["nome"]: a["motivo"] for a in p["trocar"]["alunos"]}
    assert motivos["ANA META CUMPRIDA"] == "Fez as 3 sessões de cada ficha"
    assert motivos["BRUNO VENCIDO"] == "O treino venceu em 20/10/2026"
    assert motivos["HELO META E VENCIDO"] == "Fez as 2 sessões de cada ficha e o treino venceu em 25/10/2026"


def test_no_dia_do_fim_o_treino_ainda_vale(conn):
    conn.execute("UPDATE treino SET fim = '2026-10-26' WHERE id = 2")

    assert "BRUNO VENCIDO" not in [a["nome"] for a in pendencias.listar(conn, AGORA)["trocar"]["alunos"]]


def test_ativos_sem_treino_inclui_provisorio_e_quem_so_tem_treino_concluido(conn):
    p = pendencias.listar(conn, AGORA)

    assert [a["nome"] for a in p["sem_treino"]["alunos"]] == ["FABI PROVISORIA", "DANI SEM TREINO", "GUI SO TREINO VELHO"]
    assert p["sem_treino"]["alunos"][0]["provisorio"] is True


def test_comentarios_sem_ler_e_o_total(conn):
    p = pendencias.listar(conn, AGORA)

    assert p["comentarios"]["total"] == 1 and p["comentarios"]["comentarios"][0]["texto"] == "Dor no ombro no supino"
    assert p["total"] == 3 + 3 + 1


def test_lista_grande_corta_no_limite_mas_o_total_e_o_real(conn, monkeypatch):
    monkeypatch.setattr(pendencias, "LIMITE_DA_LISTA", 1)

    p = pendencias.listar(conn, AGORA)

    assert p["sem_treino"]["total"] == 3 and len(p["sem_treino"]["alunos"]) == 1


# ------------------------------------------------------------------ a tela


@pytest.fixture
def app(caminho):
    return criar_app(caminho)


def _autorizado(app, caminho):
    navegador = app.test_client()
    c = conectar(caminho)
    token = acesso.autorizar(c, acesso.gerar_codigo(c, "Computador de teste").codigo).token
    c.close()
    navegador.set_cookie(acesso.NOME_DO_COOKIE, token)
    return navegador


def test_a_tela_mostra_as_tres_listas_com_links(app, caminho):
    html = _autorizado(app, caminho).get("/pendencias").get_data(as_text=True)

    assert "Hora de trocar o treino" in html and "Comentários sem ler" in html and "Ativos sem treino" in html
    assert "ANA META CUMPRIDA" in html and "DANI SEM TREINO" in html and "Dor no ombro no supino" in html
    assert 'href="/alunos/4/montar"' in html and 'href="/alunos/1"' in html
    assert "EDU TRANCADO" not in html and "Já lido" not in html
    assert 'aria-current="page">Pendências</a>' in html  # o menu marca a tela


def test_comentario_com_html_sai_escapado(app, caminho):
    c = conectar(caminho)
    c.execute("INSERT INTO comentario (aluno_id, treino_nome, texto, criado_em) VALUES (3, 'TREINO 3', '<script>alert(1)</script>', '2026-10-26 12:00:00')")
    c.commit()
    c.close()

    html = _autorizado(app, caminho).get("/pendencias").get_data(as_text=True)

    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


def test_computador_nao_autorizado_nao_ve_as_pendencias(app):
    resposta = app.test_client().get("/pendencias")

    assert resposta.status_code in (302, 401, 403)
    assert "ANA META CUMPRIDA" not in resposta.get_data(as_text=True)


def test_o_menu_de_todas_as_telas_do_professor_tem_pendencias(app, caminho):
    navegador = _autorizado(app, caminho)
    for url in ("/alunos", "/ausentes", "/comentarios", "/alunos/1"):
        assert "Pendências</a>" in navegador.get(url).get_data(as_text=True), url
