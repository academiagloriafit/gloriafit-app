"""Testes da busca de exercícios (banco na memória, com poucos exercícios de teste)."""

import pytest

from app import exercicios
from app.db import conectar, criar_tabelas


@pytest.fixture
def conn():
    c = conectar()
    criar_tabelas(c)
    for ordem, nome in enumerate(["Peito", "Costas", "Bíceps"], start=1):
        c.execute("INSERT INTO grupo_muscular (nome, ordem) VALUES (?, ?)", (nome, ordem))
    yield c
    c.close()


def _grupo(conn, nome):
    return conn.execute("SELECT id FROM grupo_muscular WHERE nome = ?", (nome,)).fetchone()[0]


def _exercicio(conn, nome, grupos=(), usos=0, ativo=1, combinado=0):
    ex_id = conn.execute(
        "INSERT INTO exercicio (nome, origem, usos_ultimo_ano, ativo, combinado)"
        " VALUES (?, 'app', ?, ?, ?)",
        (nome, usos, ativo, combinado),
    ).lastrowid
    for grupo in grupos:
        conn.execute(
            "INSERT INTO exercicio_grupo (exercicio_id, grupo_id) VALUES (?, ?)",
            (ex_id, _grupo(conn, grupo)),
        )
    return ex_id


def _nomes(resultado):
    return [e["nome"] for e in resultado["exercicios"]]


# ------------------------------------------------------------------ busca


def test_sem_filtro_traz_ativos_do_mais_usado_para_o_menos_usado(conn):
    _exercicio(conn, "Rosca direta", ["Bíceps"], usos=80)
    _exercicio(conn, "Supino reto com barra", ["Peito"], usos=100)
    _exercicio(conn, "Crucifixo", ["Peito"], usos=5)

    resultado = exercicios.buscar_exercicios(conn)

    assert _nomes(resultado) == ["Supino reto com barra", "Rosca direta", "Crucifixo"]
    assert resultado["total"] == 3


def test_empate_de_uso_desempata_por_nome_sem_considerar_acento(conn):
    _exercicio(conn, "Bola suíça", usos=1)
    _exercicio(conn, "Árvore", usos=1)  # "Á" tem que ficar antes de "B", não depois do "Z"

    assert _nomes(exercicios.buscar_exercicios(conn)) == ["Árvore", "Bola suíça"]


def test_busca_ignora_acento_e_maiuscula(conn):
    _exercicio(conn, "Flexão de braço", ["Peito"])

    assert _nomes(exercicios.buscar_exercicios(conn, texto="FLEXAO")) == ["Flexão de braço"]
    assert _nomes(exercicios.buscar_exercicios(conn, texto="flexão")) == ["Flexão de braço"]


def test_cada_palavra_digitada_precisa_aparecer_em_qualquer_ordem(conn):
    _exercicio(conn, "Supino reto com barra", ["Peito"])
    _exercicio(conn, "Supino inclinado com halteres", ["Peito"])

    assert _nomes(exercicios.buscar_exercicios(conn, texto="reto supino")) == [
        "Supino reto com barra"
    ]
    assert exercicios.buscar_exercicios(conn, texto="supino")["total"] == 2
    assert exercicios.buscar_exercicios(conn, texto="supino remada")["total"] == 0


def test_texto_so_com_espacos_equivale_a_sem_texto(conn):
    _exercicio(conn, "Rosca direta")

    assert exercicios.buscar_exercicios(conn, texto="   ")["total"] == 1


def test_exercicio_inativo_nunca_aparece(conn):
    _exercicio(conn, "Exercício antigo", ["Peito"], ativo=0)

    assert exercicios.buscar_exercicios(conn)["total"] == 0
    assert exercicios.buscar_exercicios(conn, grupo_id=_grupo(conn, "Peito"))["total"] == 0
    assert exercicios.buscar_exercicios(conn, texto="antigo")["total"] == 0


# ------------------------------------------------------------------ grupo


def test_filtro_por_grupo_traz_so_aquele_grupo(conn):
    _exercicio(conn, "Supino reto", ["Peito"])
    _exercicio(conn, "Rosca direta", ["Bíceps"])

    resultado = exercicios.buscar_exercicios(conn, grupo_id=_grupo(conn, "Peito"))

    assert _nomes(resultado) == ["Supino reto"]


def test_exercicio_combinado_aparece_em_cada_um_dos_seus_grupos(conn):
    _exercicio(conn, "Puxada + Rosca", ["Costas", "Bíceps"], combinado=1)

    for grupo in ("Costas", "Bíceps"):
        resultado = exercicios.buscar_exercicios(conn, grupo_id=_grupo(conn, grupo))
        assert _nomes(resultado) == ["Puxada + Rosca"]
    # e mostra os dois grupos, na ordem do quadro
    assert exercicios.buscar_exercicios(conn)["exercicios"][0]["grupos"] == ["Costas", "Bíceps"]
    assert exercicios.buscar_exercicios(conn)["exercicios"][0]["combinado"] is True


def test_exercicio_sem_grupo_so_aparece_quando_nao_se_filtra_por_grupo(conn):
    _exercicio(conn, "Elevação conjugada")

    todos = exercicios.buscar_exercicios(conn)
    assert _nomes(todos) == ["Elevação conjugada"]
    assert todos["exercicios"][0]["grupos"] == []
    assert exercicios.buscar_exercicios(conn, grupo_id=_grupo(conn, "Peito"))["total"] == 0


def test_filtro_de_grupo_e_texto_juntos(conn):
    _exercicio(conn, "Supino reto", ["Peito"])
    _exercicio(conn, "Remada reta", ["Costas"])

    resultado = exercicios.buscar_exercicios(conn, grupo_id=_grupo(conn, "Peito"), texto="reto")

    assert _nomes(resultado) == ["Supino reto"]


def test_grupo_que_nao_existe_devolve_lista_vazia(conn):
    _exercicio(conn, "Supino reto", ["Peito"])

    assert exercicios.buscar_exercicios(conn, grupo_id=9999)["total"] == 0


# ------------------------------------------------------------------ limite


def test_limite_corta_a_lista_mas_o_total_continua_certo(conn):
    for i in range(5):
        _exercicio(conn, f"Exercício {i}", usos=i)

    resultado = exercicios.buscar_exercicios(conn, limite=2)

    assert len(resultado["exercicios"]) == 2
    assert resultado["total"] == 5


def test_limite_e_mantido_entre_1_e_o_maximo(conn):
    for i in range(3):
        _exercicio(conn, f"Exercício {i}")

    assert len(exercicios.buscar_exercicios(conn, limite=0)["exercicios"]) == 1
    assert len(exercicios.buscar_exercicios(conn, limite=-5)["exercicios"]) == 1
    assert len(exercicios.buscar_exercicios(conn, limite=10**9)["exercicios"]) == 3


# ------------------------------------------------------------------ segurança


@pytest.mark.parametrize("curinga", ["%", "_", "\\", "%%", "a%"])
def test_curingas_do_like_valem_como_caractere_comum(conn, curinga):
    _exercicio(conn, "Supino reto")
    _exercicio(conn, "Rosca direta")

    # Nenhum nome tem esses caracteres: a busca não pode "casar com tudo".
    assert exercicios.buscar_exercicios(conn, texto=curinga)["total"] == 0


def test_busca_acha_nome_que_tem_porcentagem_de_verdade(conn):
    _exercicio(conn, "Corrida 80% do esforço")

    assert exercicios.buscar_exercicios(conn, texto="80%")["total"] == 1


@pytest.mark.parametrize(
    "ataque",
    ["' OR '1'='1", "'; DROP TABLE exercicio; --", '" OR 1=1 --', "x') OR ('a'='a"],
)
def test_texto_de_ataque_nao_vira_sql(conn, ataque):
    _exercicio(conn, "Supino reto")

    resultado = exercicios.buscar_exercicios(conn, texto=ataque)

    assert resultado["total"] == 0
    # a tabela continua lá, intacta
    assert conn.execute("SELECT COUNT(*) FROM exercicio").fetchone()[0] == 1


def test_busca_muito_longa_e_cortada_sem_quebrar(conn):
    _exercicio(conn, "Supino reto")

    assert exercicios.buscar_exercicios(conn, texto="a" * 100_000)["total"] == 0


# ------------------------------------------------------------------ grupos e contagem


def test_listar_grupos_na_ordem_do_quadro_com_a_quantidade_de_ativos(conn):
    _exercicio(conn, "Supino reto", ["Peito"])
    _exercicio(conn, "Crucifixo", ["Peito"])
    _exercicio(conn, "Antigo", ["Peito"], ativo=0)  # inativo não conta
    _exercicio(conn, "Puxada + Rosca", ["Costas", "Bíceps"])

    grupos = exercicios.listar_grupos(conn)

    assert [(g["nome"], g["quantidade"]) for g in grupos] == [
        ("Peito", 2),
        ("Costas", 1),
        ("Bíceps", 1),
    ]
    assert set(grupos[0]) == {"id", "nome", "quantidade"}


def test_contar_exercicios_conta_so_os_ativos(conn):
    _exercicio(conn, "A")
    _exercicio(conn, "B")
    _exercicio(conn, "C", ativo=0)

    assert exercicios.contar_exercicios(conn) == 2
