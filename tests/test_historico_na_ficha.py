"""Testes de como o histórico do Data4U aparece: ficha do aluno, busca, impressão.

Os treinos do histórico são gravados direto no banco (sem passar pelo importador, que tem os
seus próprios testes em test_importar_treinos.py). Todos os dados são inventados.
"""

import re

import pytest

from app import acesso
from app.alunos import buscar_alunos, dose_do_item, obter_ficha, texto_da_pausa
from app.db import conectar, criar_tabelas
from app.web import criar_app

# ------------------------------------------------------------------ funções puras


@pytest.mark.parametrize(
    "series, repeticoes, esperado",
    [("4", "12", "4 × 12"), ("4", None, "4"), (None, "12", "12"), (None, None, ""), ("", "  ", ""), (" 3 ", "10", "3 × 10")],
)
def test_dose_do_item(series, repeticoes, esperado):
    assert dose_do_item({"series": series, "repeticoes": repeticoes}) == esperado


@pytest.mark.parametrize(
    "segundos, esperado",
    [(None, ""), (0, ""), (30, "30 s"), (60, "1 min"), (90, "1 min 30 s"), (150, "2 min 30 s"), (3600, "1 h"), (3690, "1 h 1 min 30 s")],
)
def test_texto_da_pausa(segundos, esperado):
    assert texto_da_pausa(segundos) == esperado


# ------------------------------------------------------------------ banco com histórico


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "historico.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    exercicio = conn.execute("INSERT INTO exercicio (nome, origem, ativo) VALUES ('SUPINO RETO', 'data4u_academia', 0)").lastrowid
    conn.execute("INSERT INTO aluno (id, nome, data4u_id, situacao) VALUES (1, 'ANA FICTICIA', 101, 'A')")  # só histórico
    conn.execute("INSERT INTO aluno (id, nome, data4u_id, situacao) VALUES (2, 'BRUNO FICTICIO', 102, 'A')")  # histórico + app
    conn.execute("INSERT INTO aluno (id, nome, data4u_id, situacao) VALUES (3, 'CARLA FICTICIA', 103, 'A')")  # sem treino
    conn.execute("INSERT INTO aluno (id, nome, provisorio) VALUES (4, 'DANI PROVISORIA', 1)")  # provisório, sem treino
    # histórico antigo da Ana (2 treinos) e do Bruno (1)
    for treino_id, aluno, nome, data, data4u in [(1, 1, "TREINO 2021", "2021-03-02 17:00:00", 11), (2, 1, "TREINO 2022", "2022-05-10 12:00:00", 12), (3, 2, "TREINO ANTIGO", "2020-01-01 12:00:00", 13)]:
        conn.execute(
            "INSERT INTO treino (id, aluno_id, nome, montado_por, origem, data4u_id, criado_em) VALUES (?, ?, ?, 'PROF ANA', 'data4u', ?, ?)",
            (treino_id, aluno, nome, data4u, data),
        )
    # treino do Bruno montado no app, mais recente que o histórico
    conn.execute(
        "INSERT INTO treino (id, aluno_id, nome, montado_por, origem, criado_em) VALUES (4, 2, 'TREINO NOVO', 'CARLOS', 'app', '2026-10-01 12:00:00')"
    )
    # uma ficha com itens do histórico: um completo e um sem série nem repetição, com observação
    conn.execute("INSERT INTO ficha (id, treino_id, nome, ordem) VALUES (1, 2, 'A', 1)")
    conn.execute(
        "INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, series, repeticoes, carga, pausa, observacao)"
        " VALUES (1, 1, ?, '4', '12', '30', 90, 'devagar na descida')",
        (exercicio,),
    )
    conn.execute(
        "INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, series, repeticoes, carga, pausa, observacao)"
        " VALUES (1, 2, ?, NULL, NULL, NULL, 0, '<script>alert(1)</script>')",
        (exercicio,),
    )
    conn.commit()
    conn.close()
    return caminho


@pytest.fixture
def conn(caminho):
    c = conectar(caminho)
    yield c
    c.close()


@pytest.fixture
def cliente(caminho):
    navegador = criar_app(caminho).test_client()
    c = conectar(caminho)
    codigo = acesso.gerar_codigo(c, "Computador de teste").codigo
    token = acesso.autorizar(c, codigo).token
    c.close()
    navegador.set_cookie(acesso.NOME_DO_COOKIE, token)
    return navegador


# ------------------------------------------------------------------ busca


def test_lista_sem_texto_nao_deixa_o_historico_empurrar_provisorio_e_treino_novo(conn):
    nomes = [a["nome"] for a in buscar_alunos(conn)["alunos"]]

    # 1º quem tem treino montado no app; 2º provisório; depois os demais (Ana, com histórico, vem em ordem alfabética)
    assert nomes == ["BRUNO FICTICIO", "DANI PROVISORIA", "ANA FICTICIA", "CARLA FICTICIA"]


def test_coluna_ultimo_treino_mostra_o_historico_quando_nao_ha_treino_do_app(conn):
    por_nome = {a["nome"]: a for a in buscar_alunos(conn)["alunos"]}

    assert por_nome["ANA FICTICIA"]["ultimo_treino"] == "TREINO 2022"  # o mais novo dos dois
    assert por_nome["ANA FICTICIA"]["atualizado_em"] == "10/05/2022"
    assert por_nome["BRUNO FICTICIO"]["ultimo_treino"] == "TREINO NOVO"  # o do app é mais recente que o antigo
    assert por_nome["CARLA FICTICIA"]["ultimo_treino"] is None


def test_busca_com_texto_acha_aluno_so_com_historico(conn):
    resultado = buscar_alunos(conn, "ana fict")

    assert [a["nome"] for a in resultado["alunos"]] == ["ANA FICTICIA"]
    assert resultado["alunos"][0]["ultimo_treino"] == "TREINO 2022"


def test_treino_do_historico_mais_novo_que_o_do_app_aparece_na_coluna_mas_nao_na_ordem(conn):
    conn.execute(
        "INSERT INTO treino (aluno_id, nome, montado_por, origem, data4u_id, criado_em)"
        " VALUES (3, 'RECENTE DO DATA4U', 'PROF', 'data4u', 99, '2026-10-07 12:00:00')"
    )
    conn.commit()

    resultado = buscar_alunos(conn)["alunos"]

    assert [a["nome"] for a in resultado][:2] == ["BRUNO FICTICIO", "DANI PROVISORIA"]
    assert {a["nome"]: a["ultimo_treino"] for a in resultado}["CARLA FICTICIA"] == "RECENTE DO DATA4U"


# ------------------------------------------------------------------ ficha


def test_ficha_junta_app_e_historico_do_mais_novo_para_o_mais_antigo(conn):
    ficha = obter_ficha(conn, 2)

    assert [(t["nome"], t["do_data4u"]) for t in ficha["treinos"]] == [("TREINO NOVO", False), ("TREINO ANTIGO", True)]


def test_ficha_com_dois_treinos_do_historico_vem_em_ordem_de_data(conn):
    ficha = obter_ficha(conn, 1)

    assert [t["nome"] for t in ficha["treinos"]] == ["TREINO 2022", "TREINO 2021"]
    assert [t["criado_em"] for t in ficha["treinos"]] == ["10/05/2022", "02/03/2021"]


def test_itens_levam_dose_e_pausa_em_texto(conn):
    itens = obter_ficha(conn, 1)["treinos"][0]["fichas"][0]["itens"]

    assert (itens[0]["dose"], itens[0]["carga"], itens[0]["pausa_texto"], itens[0]["observacao"]) == ("4 × 12", "30", "1 min 30 s", "devagar na descida")
    assert (itens[1]["dose"], itens[1]["carga"], itens[1]["pausa_texto"]) == ("", None, "")


def test_pagina_da_ficha_marca_o_que_veio_do_data4u(cliente):
    html = cliente.get("/alunos/2").get_data(as_text=True)

    assert html.count("selo-origem") == 1  # só o TREINO ANTIGO, não o TREINO NOVO
    assert html.index("TREINO NOVO") < html.index("TREINO ANTIGO")  # e o do app vem primeiro
    assert 'class="selo-origem" title="Treino antigo, copiado do Data4U">Data4U</span>' in html


def test_pagina_da_ficha_e_uma_tabela_de_treinos_com_o_mais_recente_aberto_e_destacado(cliente):
    html = cliente.get("/alunos/2").get_data(as_text=True)

    # colunas como a aba Treinos do Data4U
    for coluna in ("Treino", "Data", "Fichas", "Professor"):
        assert f"<span>{coluna}</span>" in html
    assert html.count('class="linha-treino') == 2
    assert html.count("Mais recente") == 1  # só o primeiro (o mais novo), nunca o histórico
    assert re.search(r'<details class="linha-treino treino-recente" open>', html)
    antigo = html[html.index("TREINO ANTIGO") - 400 : html.index("TREINO ANTIGO")]
    assert "treino-recente" not in antigo and " open" not in antigo.split("<details")[-1]
    # o professor e a data do treino aparecem na linha, sem a palavra "Montado por"
    assert 'class="treino-professor">PROF ANA<' in html
    assert 'class="treino-data">01/10/2026<' in html
    assert "Montado por" not in html


def test_pagina_da_ficha_so_com_historico_tambem_destaca_o_mais_recente(cliente):
    html = cliente.get("/alunos/1").get_data(as_text=True)

    assert html.count("Mais recente") == 1
    assert html.index("TREINO 2022") < html.index("Mais recente") < html.index("TREINO 2021")


def test_pagina_da_ficha_mostra_dose_carga_pausa_e_observacao(cliente):
    html = cliente.get("/alunos/1").get_data(as_text=True)

    assert "4 × 12 · 30 · pausa 1 min 30 s" in html
    assert "devagar na descida" in html


def test_pagina_da_ficha_nunca_escreve_none_nem_dose_vazia_estranha(cliente):
    html = cliente.get("/alunos/1").get_data(as_text=True)

    assert "None" not in html
    assert " × </span>" not in html and "× None" not in html


def test_observacao_do_data4u_e_escapada_na_pagina(cliente):
    html = cliente.get("/alunos/1").get_data(as_text=True)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_ficha_so_com_historico_nao_mostra_aviso_de_sem_treino(cliente):
    html = cliente.get("/alunos/1").get_data(as_text=True)

    assert "ainda não tem treino" not in html


def test_aluno_sem_nada_continua_com_o_aviso(cliente):
    assert "ainda não tem treino" in cliente.get("/alunos/3").get_data(as_text=True)


# ------------------------------------------------------------------ impressão


def test_treino_do_historico_pode_ser_impresso(cliente):
    resposta = cliente.get("/treinos/2/imprimir")

    assert resposta.status_code == 200
    html = resposta.get_data(as_text=True)
    assert "PROF ANA" in html and "SUPINO RETO" in html
    assert "None" not in html


def test_cupom_de_item_sem_dose_nao_quebra(conn):
    from app import cupom

    conteudo = cupom.montar_cupom(conn, 2)

    linhas = conteudo["fichas"][0]["linhas"]
    assert [linha["tipo"] for linha in linhas] == ["exercicio", "dose", "exercicio"]  # o item sem dose nem carga não ganha linha de dose
