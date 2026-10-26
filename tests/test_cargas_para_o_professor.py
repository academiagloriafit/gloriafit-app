"""O professor vê a carga que o aluno anotou no celular (pedido do Thiago, 26/10/2026).

Onde aparece: na ficha do aluno (só no treino ATIVO), embaixo de cada exercício na tela de montar e no treino anterior que vai para o
robô (só o número, para ele ver quem progrediu). Dados inventados.
"""

import json
import re

import pytest

from app import acesso, execucao, ia_treino
from app.alunos import obter_ficha
from app.db import conectar, criar_tabelas
from app.web import criar_app


def _anotar(conn, aluno, dia, nome, carga, ficha=1, item=1, hora="12:00:00"):
    conn.execute(
        "INSERT INTO execucao (aluno_id, dia, ficha_ordem, exercicio_ordem, exercicio_nome, feito, carga, atualizado_em)"
        " VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
        (aluno, dia, ficha, item, nome, carga, f"{dia} {hora}"),
    )


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "cargas.db"
    c = conectar(caminho)
    criar_tabelas(c)
    c.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO RETO', 'app'), (2, 'REMADA', 'app'), (3, 'LEG PRESS', 'app')")
    c.execute("INSERT INTO aluno (id, nome) VALUES (1, 'ANA FICTICIA'), (2, 'BRUNO FICTICIO')")
    # treino antigo (concluído) e treino ativo da Ana
    c.execute("INSERT INTO treino (id, aluno_id, nome, montado_por, ativo, inicio) VALUES (1, 1, 'ANTIGO', 'PROF', 0, '2026-08-01')")
    c.execute("INSERT INTO treino (id, aluno_id, nome, montado_por, ativo, inicio) VALUES (2, 1, 'ATUAL', 'PROF', 1, '2026-10-01')")
    for treino in (1, 2):
        ficha = c.execute("INSERT INTO ficha (treino_id, nome, ordem) VALUES (?, 'A', 1)", (treino,)).lastrowid
        c.execute("INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, series, repeticoes) VALUES (?, 1, 1, '3', '12')", (ficha,))
        c.execute("INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, series, repeticoes) VALUES (?, 2, 2, '3', '12')", (ficha,))
    _anotar(c, 1, "2026-10-05", "SUPINO RETO", "18")
    _anotar(c, 1, "2026-10-12", "SUPINO RETO", "20")  # a mais recente
    _anotar(c, 1, "2026-10-12", "SUPINO RETO", "22,5", ficha=2, hora="12:30:00")  # mesmo dia, anotada depois: vale esta
    _anotar(c, 1, "2026-10-14", "EXERCICIO QUE FOI RENOMEADO", "50")
    _anotar(c, 2, "2026-10-20", "REMADA", "40")  # outro aluno
    c.execute(
        "INSERT INTO execucao (aluno_id, dia, ficha_ordem, exercicio_ordem, exercicio_nome, feito, carga, atualizado_em)"
        " VALUES (1, '2026-10-20', 1, 2, 'REMADA', 1, NULL, '2026-10-20 12:00:00')"  # feito sem carga: não conta
    )
    c.commit()
    c.close()
    return caminho


@pytest.fixture
def conn(caminho):
    c = conectar(caminho)
    yield c
    c.close()


@pytest.fixture
def cliente(caminho):
    app = criar_app(caminho)
    navegador = app.test_client()
    c = conectar(caminho)
    token = acesso.autorizar(c, acesso.gerar_codigo(c, "Computador de teste").codigo).token
    c.close()
    navegador.set_cookie(acesso.NOME_DO_COOKIE, token)
    return navegador


# ------------------------------------------------------------------ a consulta


def test_cargas_por_exercicio_traz_a_mais_recente_de_cada_exercicio_do_aluno(conn):
    assert execucao.cargas_por_exercicio(conn, 1) == {1: ("22,5", "2026-10-12")}  # remada sem carga e nome antigo ficam de fora
    assert execucao.cargas_por_exercicio(conn, 2) == {2: ("40", "2026-10-20")}
    assert execucao.cargas_por_exercicio(conn, 99) == {}


@pytest.mark.parametrize("carga, esperado", [(("20", "2026-10-12"), "20 kg em 12/10"), (("12,5", "2026-01-03"), "12,5 kg em 03/01"), (None, "")])
def test_texto_da_carga(carga, esperado):
    assert execucao.texto_da_carga(carga) == esperado


# ------------------------------------------------------------------ ficha do aluno


def test_a_ficha_mostra_a_carga_so_no_treino_ativo(conn):
    treinos = {t["nome"]: t for t in obter_ficha(conn, 1)["treinos"]}

    atual = treinos["ATUAL"]["fichas"][0]["itens"]
    assert [i["carga_do_aluno"] for i in atual] == ["22,5 kg em 12/10", ""]
    assert all(i["carga_do_aluno"] == "" for i in treinos["ANTIGO"]["fichas"][0]["itens"])


def test_a_pagina_da_ficha_escreve_o_que_o_aluno_anotou(cliente):
    html = cliente.get("/alunos/1").get_data(as_text=True)

    assert "Aluno anotou: 22,5 kg em 12/10" in html
    assert html.count("Aluno anotou:") == 1


# ------------------------------------------------------------------ tela de montar


def test_a_tela_de_montar_leva_as_cargas_num_atributo_que_o_navegador_le(cliente):
    html = cliente.get("/alunos/1/montar").get_data(as_text=True)

    bruto = re.search(r"data-cargas='([^']*)'", html).group(1)
    assert json.loads(bruto.replace("&#34;", '"')) == {"1": {"carga": "22,5", "dia": "22,5 kg em 12/10"}}
    assert not re.search(r"<script(?![^>]*\bsrc=)", html)  # nada de script embutido


def test_cada_aluno_leva_so_as_proprias_cargas(cliente):
    c = cliente.get("/alunos/2/montar").get_data(as_text=True)

    assert "data-cargas='{\"2\"" in c or "data-cargas='{&#34;2&#34;" in c  # o Bruno anotou só a remada


# ------------------------------------------------------------------ o robô


def test_o_robo_recebe_a_carga_anotada_no_treino_anterior_so_o_numero(conn):
    texto = ia_treino.treino_anterior(conn, 1, {1, 2, 3})

    assert "1 SUPINO RETO 3x12 (anotou 22,5 kg)" in texto
    assert "2 REMADA 3x12 |" not in texto and texto.rstrip().endswith("2 REMADA 3x12")  # sem carga anotada, sem o "(anotou...)"
    assert "12/10" not in texto and "2026-10-12" not in texto  # a data não vai


def test_regra_12_diz_para_usar_a_carga_so_para_ver_o_progresso():
    assert '"anotou X kg"' in ia_treino.REGRAS_DA_CASA and "não escreva carga no treino" in ia_treino.REGRAS_DA_CASA
