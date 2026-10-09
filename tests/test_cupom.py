"""Conteúdo do cupom do treino (app/cupom.py). Dados inventados."""

import pytest

from app import treinos
from app.cupom import TAMANHO_MAXIMO_DO_ENDERECO, _lista_com_e, montar_cupom
from app.db import conectar, criar_tabelas


@pytest.fixture
def conn():
    c = conectar()
    criar_tabelas(c)
    c.execute("INSERT INTO aluno (nome, cpf) VALUES ('MARIANA COSTA', '52998224725')")
    nomes = ["SUPINO RETO COM BARRA", "CRUCIFIXO COM HALTERES", "SUPINO INCLINADO C/ HALTERES", "TRICEPS NA POLIA", "TRICEPS TESTA"]
    for nome in nomes:
        c.execute("INSERT INTO exercicio (nome, origem) VALUES (?, 'app')", (nome,))
    c.commit()
    yield c
    c.close()


def _item(exercicio_id, series="4", repeticoes="12", carga="30 KG", bloco=None, **extras):
    return {"exercicio_id": exercicio_id, "series": series, "repeticoes": repeticoes, "carga": carga, "bloco": bloco, **extras}


def _salvar(conn, fichas, nome="TREINO ABC", por="Ana Paula", quando="2026-10-07 15:00:00"):
    treino_id = treinos.salvar_treino(
        conn, 1, {"nome_treino": nome, "montado_por": por, "fichas": [{"nome": n, "itens": i} for n, i in fichas]}
    )
    conn.execute("UPDATE treino SET criado_em = ? WHERE id = ?", (quando, treino_id))
    conn.commit()
    return treino_id


def _resumo(cupom, ficha=0):
    return [(l["tipo"], l["etiqueta"], l["esquerda"], l["direita"]) for l in cupom["fichas"][ficha]["linhas"]]


# ------------------------------------------------------------------ cabeçalho


def test_cabecalho_com_aluno_treino_data_e_professor(conn):
    treino = _salvar(conn, [("TREINO A", [_item(1)])], nome="TREINO ABC 07/10/26", por="Ana Paula")

    cupom = montar_cupom(conn, treino)

    assert cupom["academia"] == "Academia Glória Fit"
    assert cupom["cabecalho"] == [
        ("ALUNO", "MARIANA COSTA"),
        ("TREINO", "TREINO ABC 07/10/26"),
        ("DATA", "07/10/2026"),
        ("PROF.", "Ana Paula"),
    ]
    assert cupom["aluno_id"] == 1


def test_a_data_do_cupom_e_a_de_brasilia_e_nao_a_do_banco(conn):
    # 02:30 UTC de 08/10 ainda é noite de 07/10 em Vitória.
    treino = _salvar(conn, [("TREINO A", [_item(1)])], quando="2026-10-08 02:30:00")

    assert ("DATA", "07/10/2026") in montar_cupom(conn, treino)["cabecalho"]


def test_treino_que_nao_existe_devolve_none(conn):
    assert montar_cupom(conn, 999) is None


# ------------------------------------------------------------------ linhas (o desenho)


def test_ficha_do_desenho_com_bi_set_e_exercicios_soltos(conn):
    treino = _salvar(
        conn,
        [
            (
                "TREINO A",
                [
                    _item(1, "4", "12", "30 KG", bloco=1),
                    _item(2, "4", "12", "10 KG", bloco=1),
                    _item(3, "3", "10", "14 KG"),
                    _item(4, "3", "12", "25 KG"),
                    _item(5, "3", "12", "15 KG"),
                ],
            )
        ],
    )

    cupom = montar_cupom(conn, treino)

    assert cupom["fichas"][0]["nome"] == "TREINO A"
    assert _resumo(cupom) == [
        ("exercicio", "A1", "SUPINO RETO COM BARRA", ""),
        ("dose", "", "4 X 12", "30 KG"),
        ("exercicio", "A2", "CRUCIFIXO COM HALTERES", ""),
        ("dose", "", "4 X 12", "10 KG"),
        ("aviso", "", "BI-SET: FAÇA A1 E A2 SEGUIDOS", ""),
        ("exercicio", "3", "SUPINO INCLINADO C/ HALTERES", ""),
        ("dose", "", "3 X 10", "14 KG"),
        ("exercicio", "4", "TRICEPS NA POLIA", ""),
        ("dose", "", "3 X 12", "25 KG"),
        ("exercicio", "5", "TRICEPS TESTA", ""),
        ("dose", "", "3 X 12", "15 KG"),
    ]


def test_tri_set_tem_o_aviso_com_tres_etiquetas(conn):
    treino = _salvar(conn, [("TREINO A", [_item(1, bloco=1), _item(2, bloco=1), _item(3, bloco=1)])])

    avisos = [l for l in _resumo(montar_cupom(conn, treino)) if l[0] == "aviso"]

    assert avisos == [("aviso", "", "TRI-SET: FAÇA A1, A2 E A3 SEGUIDOS", "")]


def test_segundo_bloco_usa_a_letra_b_e_cada_bloco_tem_o_seu_aviso(conn):
    treino = _salvar(
        conn, [("TREINO A", [_item(1, bloco=1), _item(2, bloco=1), _item(3), _item(4, bloco=2), _item(5, bloco=2)])]
    )

    linhas = _resumo(montar_cupom(conn, treino))

    assert [l[1] for l in linhas if l[0] == "exercicio"] == ["A1", "A2", "3", "B1", "B2"]
    assert [l[2] for l in linhas if l[0] == "aviso"] == ["BI-SET: FAÇA A1 E A2 SEGUIDOS", "BI-SET: FAÇA B1 E B2 SEGUIDOS"]


def test_bloco_no_fim_da_ficha_tambem_leva_aviso(conn):
    treino = _salvar(conn, [("TREINO A", [_item(1), _item(2, bloco=1), _item(3, bloco=1)])])

    assert _resumo(montar_cupom(conn, treino))[-1] == ("aviso", "", "BI-SET: FAÇA A1 E A2 SEGUIDOS", "")


def test_o_aviso_vem_depois_do_ultimo_exercicio_do_bloco_e_nao_do_primeiro(conn):
    treino = _salvar(conn, [("TREINO A", [_item(1, bloco=1), _item(2, bloco=1)])])

    tipos = [l[0] for l in _resumo(montar_cupom(conn, treino))]

    assert tipos == ["exercicio", "dose", "exercicio", "dose", "aviso"]


def test_fichas_reiniciam_as_etiquetas_e_mantem_a_ordem(conn):
    treino = _salvar(
        conn,
        [("TREINO A", [_item(1, bloco=1), _item(2, bloco=1)]), ("TREINO B", [_item(3), _item(4)])],
    )

    cupom = montar_cupom(conn, treino)

    assert [f["nome"] for f in cupom["fichas"]] == ["TREINO A", "TREINO B"]
    assert [l[1] for l in _resumo(cupom, 0) if l[0] == "exercicio"] == ["A1", "A2"]
    assert [l[1] for l in _resumo(cupom, 1) if l[0] == "exercicio"] == ["1", "2"]


# ------------------------------------------------------------------ dose e carga


def test_sem_carga_a_linha_da_dose_fica_sem_o_lado_direito(conn):
    treino = _salvar(conn, [("TREINO A", [_item(1, "3", "15", None)])])

    assert _resumo(montar_cupom(conn, treino))[1] == ("dose", "", "3 X 15", "")


def test_carga_e_impressa_como_foi_digitada(conn):
    treino = _salvar(conn, [("TREINO A", [_item(1, "3", "15", "20 kg")])])

    assert _resumo(montar_cupom(conn, treino))[1] == ("dose", "", "3 X 15", "20 kg")


def test_espacos_nas_pontas_da_carga_nao_vao_para_o_papel(conn):
    # O app já apara ao salvar; isto cobre um banco mexido por fora.
    treino = _salvar(conn, [("TREINO A", [_item(1, "3", "15", "20 kg")])])
    conn.execute("UPDATE ficha_item SET carga = '  20 kg  '")
    conn.commit()

    assert _resumo(montar_cupom(conn, treino))[1] == ("dose", "", "3 X 15", "20 kg")


def test_bloco_com_um_exercicio_so_nao_gera_aviso(conn):
    # O app não deixa salvar um bi-set com 1 exercício; cobre um banco mexido por fora.
    treino = _salvar(conn, [("TREINO A", [_item(1), _item(2)])])
    conn.execute("UPDATE ficha_item SET bloco = 7 WHERE exercicio_id = 1")
    conn.commit()

    linhas = _resumo(montar_cupom(conn, treino))

    assert [l[0] for l in linhas if l[0] == "aviso"] == []
    assert [l[1] for l in linhas if l[0] == "exercicio"] == ["A1", "2"]


def test_dose_com_so_um_dos_dois_nao_inventa_o_outro(conn):
    # O app exige séries e repetições, mas o banco aceita vazio: imprime só o que existe.
    treino = _salvar(conn, [("TREINO A", [_item(1), _item(2), _item(3)])])
    conn.execute("UPDATE ficha_item SET repeticoes = NULL, carga = NULL WHERE exercicio_id = 1")
    conn.execute("UPDATE ficha_item SET series = NULL, carga = NULL WHERE exercicio_id = 2")
    conn.execute("UPDATE ficha_item SET series = NULL, repeticoes = NULL, carga = NULL WHERE exercicio_id = 3")
    conn.commit()

    linhas = _resumo(montar_cupom(conn, treino))

    assert linhas == [
        ("exercicio", "1", "SUPINO RETO COM BARRA", ""),
        ("dose", "", "4", ""),
        ("exercicio", "2", "CRUCIFIXO COM HALTERES", ""),
        ("dose", "", "12", ""),
        ("exercicio", "3", "SUPINO INCLINADO C/ HALTERES", ""),  # sem dose e sem carga: sem linha de dose
    ]


# ------------------------------------------------------------------ endereço do app


def test_sem_endereco_o_cupom_nao_fala_do_app(conn):
    treino = _salvar(conn, [("TREINO A", [_item(1)])])

    assert montar_cupom(conn, treino)["endereco_do_app"] is None
    assert montar_cupom(conn, treino, endereco_do_app="")["endereco_do_app"] is None
    assert montar_cupom(conn, treino, endereco_do_app="   ")["endereco_do_app"] is None


def test_endereco_e_limpo_e_cortado_no_tamanho_maximo(conn):
    treino = _salvar(conn, [("TREINO A", [_item(1)])])

    assert montar_cupom(conn, treino, endereco_do_app="  treino.exemplo.com.br  ")["endereco_do_app"] == "treino.exemplo.com.br"
    longo = montar_cupom(conn, treino, endereco_do_app="x" * 500)["endereco_do_app"]
    assert len(longo) == TAMANHO_MAXIMO_DO_ENDERECO


# ------------------------------------------------------------------ texto


@pytest.mark.parametrize(
    "etiquetas, esperado",
    [(["A1"], "A1"), (["A1", "A2"], "A1 E A2"), (["A1", "A2", "A3"], "A1, A2 E A3"), (["B1", "B2", "B3", "B4"], "B1, B2, B3 E B4")],
)
def test_lista_com_e(etiquetas, esperado):
    assert _lista_com_e(etiquetas) == esperado


# ------------------------------------------------------------------ intervalo e observação


def test_intervalo_e_observacao_saem_logo_depois_da_dose(conn):
    treino = _salvar(conn, [("TREINO A", [_item(1, pausa=90, observacao="Descer devagar")])])

    assert _resumo(montar_cupom(conn, treino)) == [
        ("exercicio", "1", "SUPINO RETO COM BARRA", ""),
        ("dose", "", "4 X 12", "30 KG"),
        ("detalhe", "", "INTERVALO: 1 MIN 30 S", ""),
        ("detalhe", "", "OBS: Descer devagar", ""),
    ]


def test_sem_intervalo_e_sem_observacao_nao_ha_linha_de_detalhe(conn):
    treino = _salvar(conn, [("TREINO A", [_item(1), _item(2, pausa=0, observacao="  ")])])

    assert [l[0] for l in _resumo(montar_cupom(conn, treino))] == ["exercicio", "dose", "exercicio", "dose"]


def test_so_o_intervalo_ou_so_a_observacao(conn):
    treino = _salvar(conn, [("TREINO A", [_item(1, pausa=45), _item(2, observacao="Até a falha")])])

    detalhes = [l[2] for l in _resumo(montar_cupom(conn, treino)) if l[0] == "detalhe"]
    assert detalhes == ["INTERVALO: 45 S", "OBS: Até a falha"]


def test_o_aviso_do_bi_set_vem_depois_do_intervalo_e_da_observacao_do_ultimo_exercicio(conn):
    treino = _salvar(
        conn,
        [("TREINO A", [_item(1, bloco=1), _item(2, bloco=1, pausa=60, observacao="Sem pausa entre os dois")])],
    )

    tipos = [l[0] for l in _resumo(montar_cupom(conn, treino))]
    assert tipos == ["exercicio", "dose", "exercicio", "dose", "detalhe", "detalhe", "aviso"]


def test_o_numero_da_maquina_nao_sai_no_papel(conn):
    conn.execute("UPDATE exercicio SET nome = '(15) CADEIRA ABDUTORA' WHERE id = 1")
    conn.commit()
    cupom = montar_cupom(conn, _salvar(conn, [("TREINO A", [_item(1)])]), "")
    assert _resumo(cupom)[0] == ("exercicio", "1", "CADEIRA ABDUTORA", "")


def test_exercicio_de_cardio_sem_dose_sai_so_com_o_nome(conn):
    cupom = montar_cupom(conn, _salvar(conn, [("TREINO A", [_item(1, series="", repeticoes="", carga=""), _item(2)])]), "")
    linhas = _resumo(cupom)
    assert linhas[0] == ("exercicio", "1", "SUPINO RETO COM BARRA", "")
    assert linhas[1][0] == "exercicio"  # sem linha de dose vazia no meio: o próximo exercício vem logo depois
