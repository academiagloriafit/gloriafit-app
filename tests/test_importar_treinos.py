"""Testes da importação do histórico de treinos do Data4U (app/importar_treinos.py + a rota).

Todos os dados aqui são inventados: nomes, matrículas, treinos e exercícios.
"""

import copy
from datetime import datetime, timezone

import pytest

from app import acesso, importar_treinos
from app.alunos import data_local
from app.db import conectar, criar_tabelas
from app.importar_treinos import (
    COLUNAS_NECESSARIAS,
    NOME_DO_EXERCICIO_NAO_INFORMADO,
    NOME_DO_EXERCICIO_REMOVIDO,
    NOME_SEM_PROFESSOR,
    NOME_TREINO_SEM_NOME,
    CopiaInvalida,
    copia_de_pacote,
    data_em_utc,
    importar,
    limpar,
    pausa_em_segundos,
    sem_html,
)
from app.web import TAMANHO_MAXIMO_DA_IMPORTACAO, TAMANHO_MAXIMO_DO_PEDIDO, criar_app

AGORA = datetime(2026, 10, 8, 11, 30, 15, tzinfo=timezone.utc)  # 08/10/2026 08:30 em Vila Velha
EXTRACAO = "08/10/2026 05:00:19"


# ------------------------------------------------------------------ montagem do pacote


def mundo_basico():
    """Duas alunas do app (matrículas 101 e 102) e o que o Data4U tem delas.

    treino 1 (aluna 101, "TREINO ABC", prof. 900): fichas A e B; A tem 2 exercícios.
    treino 2 (aluna 102, "TREINO D", prof. 901): uma ficha com 1 exercício.
    """
    return {
        "PESSOA": [[900, "PROF ANA"], [901, "PROF BRUNO"]],
        "LANCAMENTO_OBJ": [
            [5001, 101, -510, "2026-03-02 14:03:24"],
            [5002, 102, -510, "2026-04-10 09:00:00"],
        ],
        "TREINO": [
            [1, 5001, 900, "TREINO ABC", "F"],
            [2, 5002, 901, "TREINO D", "F"],
        ],
        "TREINO_FICHA": [
            [11, 1, 1, "A"],
            [12, 1, 2, "B"],
            [21, 2, 1, "UNICA"],
        ],
        "TREINO_PRESCRICAO": [
            # id, ficha, exercício, ordem, série, repetição, peso, pausa, observação
            [101, 11, -5, 1, "3", "12", "20", "00:01:00", "devagar"],
            [102, 11, 7, 2, "4", "10", None, "00:00:00", None],
            [103, 12, 7, 1, "3", "15", "5", None, None],
            [201, 21, -5, 1, "2", "20", None, "00:00:30", None],
        ],
        "TREINO_EXERCICIO": [
            [-5, "SUPINO RETO"],
            [7, "REMADA BAIXA"],
        ],
    }


def empacotar(mundo, **extras):
    pacote = {
        "extracao": EXTRACAO,
        "tabelas": {
            nome: {"colunas": list(COLUNAS_NECESSARIAS[nome]), "linhas": copy.deepcopy(mundo[nome])}
            for nome in COLUNAS_NECESSARIAS
        },
    }
    pacote.update(extras)
    return pacote


def copia(mundo):
    return copia_de_pacote(empacotar(mundo), agora=AGORA)


@pytest.fixture
def conn():
    c = conectar()
    criar_tabelas(c)
    c.execute("INSERT INTO aluno (id, nome, data4u_id, situacao) VALUES (1, 'ANA FICTICIA', 101, 'A')")
    c.execute("INSERT INTO aluno (id, nome, data4u_id, situacao) VALUES (2, 'BRUNO FICTICIO', 102, 'A')")
    c.commit()  # a importação abre a própria transação: não pode haver uma pendente
    yield c
    c.close()


def _linhas(conn, sql, *args):
    return [tuple(linha) for linha in conn.execute(sql, args)]


def _treinos(conn):
    return _linhas(
        conn, "SELECT id, aluno_id, nome, montado_por, origem, data4u_id, criado_em FROM treino ORDER BY data4u_id, id"
    )


# ------------------------------------------------------------------ funções puras


def test_sem_html_tira_so_as_tags():
    assert limpar(sem_html("<b>(10) CADEIRA EXTENSORA</b> APAGADO")) == "(10) CADEIRA EXTENSORA APAGADO"
    assert limpar(sem_html("<b> ABDUTORA</b> APAGADO")) == "ABDUTORA APAGADO"
    assert limpar(sem_html("SUPINO 3 < 4 RETO")) == "SUPINO 3 < 4 RETO"  # "<" sozinho não é tag


def test_limpar_junta_espacos_e_tira_controles():
    assert limpar("  TREINO \t A\n") == "TREINO A"
    assert limpar("A\x00B\x07C") == "A B C"
    assert limpar(None) == ""


@pytest.mark.parametrize(
    "texto, segundos",
    [("00:00:00", 0), ("00:00:30", 30), ("00:01:00", 60), ("00:02:30", 150), ("01:00:00", 3600), ("1:00:00", 3600)],
)
def test_pausa_em_segundos(texto, segundos):
    assert pausa_em_segundos(texto) == segundos


@pytest.mark.parametrize("texto", [None, "", "60", "1:30", "00:75:00", "00:00:99", "aa:bb:cc", "00:01:00:00", "-1:00:00"])
def test_pausa_ilegivel_vira_vazia(texto):
    assert pausa_em_segundos(texto) is None


def test_data_do_lancamento_vai_de_brasilia_para_utc():
    assert data_em_utc("2026-03-02 14:03:24") == "2026-03-02 17:03:24"  # sem horário de verão: UTC-3
    assert data_em_utc("2018-12-01 10:00:00") == "2018-12-01 12:00:00"  # com horário de verão (até 2019): UTC-2


def test_data_convertida_volta_igual_na_tela():
    # A ficha mostra o dia em Brasília: o dia do Data4U tem que ser o dia da ficha.
    assert data_local(data_em_utc("2026-03-02 23:59:59")) == "02/03/2026"
    assert data_local(data_em_utc("2026-03-02 00:00:01")) == "02/03/2026"


@pytest.mark.parametrize("texto", [None, "", "2026-03-02", "02/03/2026 10:00:00", "2026-13-02 10:00:00", "ontem"])
def test_data_ilegivel(texto):
    assert data_em_utc(texto) is None


# ------------------------------------------------------------------ o pacote


def test_pacote_valido_vira_copia():
    c = copia(mundo_basico())

    assert c.extraido_em == datetime(2026, 10, 8, 5, 0, 19)
    assert len(c.linhas["TREINO"]) == 2
    assert c.posicao["TREINO"]["NM_TREINO"] == 3


def test_a_ordem_das_colunas_no_pacote_nao_importa(conn):
    pacote = empacotar(mundo_basico())
    bloco = pacote["tabelas"]["TREINO_PRESCRICAO"]
    bloco["colunas"] = list(reversed(bloco["colunas"]))
    bloco["linhas"] = [list(reversed(linha)) for linha in bloco["linhas"]]

    importar(conn, copia_de_pacote(pacote, agora=AGORA))

    assert _linhas(conn, "SELECT series, repeticoes FROM ficha_item ORDER BY id")[0] == ("3", "12")


@pytest.mark.parametrize(
    "pacote",
    [None, [], "texto", {}, {"extracao": EXTRACAO}, {"extracao": EXTRACAO, "tabelas": []}],
)
def test_pacote_que_nao_tem_o_formato_esperado(pacote):
    with pytest.raises(CopiaInvalida):
        copia_de_pacote(pacote, agora=AGORA)


def test_copia_velha_demais_e_recusada():
    with pytest.raises(CopiaInvalida, match="velha demais"):
        copia_de_pacote(empacotar(mundo_basico(), extracao="01/10/2026 05:00:00"), agora=AGORA)


def test_tabela_a_menos_ou_a_mais_e_recusada():
    pacote = empacotar(mundo_basico())
    del pacote["tabelas"]["PESSOA"]
    with pytest.raises(CopiaInvalida, match="exatamente as tabelas"):
        copia_de_pacote(pacote, agora=AGORA)

    pacote = empacotar(mundo_basico())
    pacote["tabelas"]["RECEBIMENTO"] = {"colunas": [], "linhas": []}
    with pytest.raises(CopiaInvalida, match="exatamente as tabelas"):
        copia_de_pacote(pacote, agora=AGORA)


def test_coluna_a_mais_ou_a_menos_e_recusada():
    pacote = empacotar(mundo_basico())
    pacote["tabelas"]["PESSOA"]["colunas"].append("NR_CPF")  # dado pessoal que o app não precisa
    for linha in pacote["tabelas"]["PESSOA"]["linhas"]:
        linha.append("12345678909")
    with pytest.raises(CopiaInvalida, match="PESSOA: as colunas enviadas precisam ser exatamente"):
        copia_de_pacote(pacote, agora=AGORA)

    pacote = empacotar(mundo_basico())
    pacote["tabelas"]["TREINO"]["colunas"].pop()
    for linha in pacote["tabelas"]["TREINO"]["linhas"]:
        linha.pop()
    with pytest.raises(CopiaInvalida, match="TREINO: as colunas enviadas"):
        copia_de_pacote(pacote, agora=AGORA)


@pytest.mark.parametrize(
    "tabela, coluna, valor",
    [
        ("TREINO", "ID_TREINO", "1"),  # texto onde devia ser número
        ("TREINO", "ID_TREINO", True),  # bool não vale como número
        ("TREINO", "ID_TREINO", None),
        ("TREINO", "NM_TREINO", 5),
        ("TREINO_FICHA", "NR_FICHA", None),
        ("TREINO_PRESCRICAO", "NR_ORDEM", 1.5),
        ("TREINO_PRESCRICAO", "NR_SERIE", 3),  # o navegador converte para texto antes de enviar
        ("LANCAMENTO_OBJ", "DT_LANCAMENTO", 20260302),
        ("PESSOA", "NM_PESSOA", ["x"]),
    ],
)
def test_valor_no_formato_errado_e_recusado(tabela, coluna, valor):
    pacote = empacotar(mundo_basico())
    posicao = pacote["tabelas"][tabela]["colunas"].index(coluna)
    pacote["tabelas"][tabela]["linhas"][0][posicao] = valor

    with pytest.raises(CopiaInvalida, match=f"{tabela}, linha 1: a coluna {coluna}"):
        copia_de_pacote(pacote, agora=AGORA)


def test_linha_com_tamanho_errado_e_recusada():
    pacote = empacotar(mundo_basico())
    pacote["tabelas"]["TREINO_FICHA"]["linhas"][1].append("sobra")

    with pytest.raises(CopiaInvalida, match="TREINO_FICHA, linha 2: formato inesperado"):
        copia_de_pacote(pacote, agora=AGORA)


@pytest.mark.parametrize(
    "tabela, linha_repetida",
    [
        ("TREINO", [1, 5001, 900, "OUTRO", "F"]),
        ("TREINO_FICHA", [11, 1, 3, "C"]),
        ("TREINO_EXERCICIO", [7, "OUTRO NOME"]),
        ("LANCAMENTO_OBJ", [5001, 101, -510, "2026-03-03 10:00:00"]),
        ("PESSOA", [900, "OUTRA PESSOA"]),
    ],
)
def test_chave_repetida_e_recusada(tabela, linha_repetida):
    mundo = mundo_basico()
    mundo[tabela].append(linha_repetida)

    with pytest.raises(CopiaInvalida, match="valores repetidos"):
        copia(mundo)


def test_pacote_sem_nenhum_treino_e_recusado_para_nao_apagar_o_historico():
    mundo = mundo_basico()
    mundo["TREINO"] = []

    with pytest.raises(CopiaInvalida, match="nenhum treino"):
        copia(mundo)


def test_limite_de_linhas_por_tabela(monkeypatch):
    monkeypatch.setattr("app.importar_treinos.LIMITE_DE_LINHAS_POR_TABELA", 2)

    with pytest.raises(CopiaInvalida, match="TREINO_FICHA: linhas demais"):
        copia(mundo_basico())


# ------------------------------------------------------------------ importação: o caminho feliz


def test_importa_treinos_fichas_e_itens(conn):
    relatorio = importar(conn, copia(mundo_basico()))

    assert (relatorio.treinos_novos, relatorio.treinos_atualizados, relatorio.fichas, relatorio.exercicios_prescritos) == (2, 0, 3, 4)
    assert relatorio.alunos_com_historico == 2
    assert _treinos(conn) == [
        (1, 1, "TREINO ABC", "PROF ANA", "data4u", 1, "2026-03-02 17:03:24"),
        (2, 2, "TREINO D", "PROF BRUNO", "data4u", 2, "2026-04-10 12:00:00"),
    ]
    assert _linhas(conn, "SELECT treino_id, nome, ordem FROM ficha ORDER BY id") == [
        (1, "A", 1), (1, "B", 2), (2, "UNICA", 1),
    ]


def test_item_leva_dose_carga_pausa_em_segundos_e_observacao(conn):
    importar(conn, copia(mundo_basico()))

    itens = _linhas(
        conn,
        "SELECT i.ordem, i.bloco, e.nome, i.series, i.repeticoes, i.carga, i.pausa, i.observacao"
        " FROM ficha_item i JOIN exercicio e ON e.id = i.exercicio_id WHERE i.ficha_id = 1 ORDER BY i.ordem",
    )
    assert itens == [
        (1, None, "SUPINO RETO", "3", "12", "20", 60, "devagar"),
        (2, None, "REMADA BAIXA", "4", "10", None, 0, None),
    ]


def test_fichas_e_itens_seguem_a_ordem_do_data4u_mesmo_com_numeros_repetidos(conn):
    mundo = mundo_basico()
    # No Data4U há treino com NR_FICHA repetido e ficha com NR_ORDEM repetido; o app exige 1, 2, 3...
    mundo["TREINO_FICHA"] = [[12, 1, 2, "TERCEIRA"], [11, 1, 2, "SEGUNDA"], [10, 1, 1, "PRIMEIRA"], [21, 2, 1, "UNICA"]]  # 11 e 12: mesmo NR_FICHA, vale o id
    mundo["TREINO_PRESCRICAO"] = [
        [103, 10, 7, 5, "3", "15", None, None, None],
        [102, 10, -5, 5, "4", "10", None, None, None],  # mesma ordem 5: desempata pelo id da prescrição
        [101, 10, 7, 2, "3", "12", None, None, None],
    ]

    importar(conn, copia(mundo))

    assert _linhas(conn, "SELECT nome, ordem FROM ficha WHERE treino_id = 1 ORDER BY ordem") == [
        ("PRIMEIRA", 1), ("SEGUNDA", 2), ("TERCEIRA", 3),
    ]
    assert _linhas(conn, "SELECT ordem, series, repeticoes FROM ficha_item WHERE ficha_id = 1 ORDER BY ordem") == [
        (1, "3", "12"), (2, "4", "10"), (3, "3", "15"),
    ]


def test_treinos_com_o_mesmo_nome_do_mesmo_aluno_entram_os_dois(conn):
    mundo = mundo_basico()
    mundo["LANCAMENTO_OBJ"].append([5003, 101, -510, "2026-05-01 10:00:00"])
    mundo["TREINO"].append([3, 5003, 900, "treino abc", "F"])  # mesmo nome, outra caixa, mesma aluna

    relatorio = importar(conn, copia(mundo))

    assert relatorio.treinos_novos == 3
    assert _linhas(conn, "SELECT COUNT(*) FROM treino WHERE aluno_id = 1") == [(2,)]


def test_a_data_do_treino_e_a_do_lancamento_nao_a_de_inicio(conn):
    # Só as colunas enviadas existem: DT_INICIO nem chega ao servidor. O horário vem do LANCAMENTO_OBJ.
    importar(conn, copia(mundo_basico()))

    assert _linhas(conn, "SELECT criado_em FROM treino WHERE data4u_id = 1") == [("2026-03-02 17:03:24",)]
    assert "DT_INICIO" not in {c for tabela in COLUNAS_NECESSARIAS.values() for c in tabela}


def test_treino_sem_ficha_entra_e_e_contado(conn):
    mundo = mundo_basico()
    mundo["TREINO_FICHA"] = [f for f in mundo["TREINO_FICHA"] if f[1] != 2]
    mundo["TREINO_PRESCRICAO"] = [p for p in mundo["TREINO_PRESCRICAO"] if p[1] != 21]

    relatorio = importar(conn, copia(mundo))

    assert relatorio.treinos_sem_ficha == 1
    assert _linhas(conn, "SELECT COUNT(*) FROM ficha WHERE treino_id = 2") == [(0,)]
    assert relatorio.treinos_novos == 2


def test_ficha_sem_nenhum_exercicio_entra(conn):
    mundo = mundo_basico()
    mundo["TREINO_PRESCRICAO"] = [p for p in mundo["TREINO_PRESCRICAO"] if p[1] != 12]

    importar(conn, copia(mundo))

    assert _linhas(conn, "SELECT COUNT(*) FROM ficha_item WHERE ficha_id = 2") == [(0,)]
    assert _linhas(conn, "SELECT COUNT(*) FROM ficha WHERE treino_id = 1") == [(2,)]


# ------------------------------------------------------------------ quem fica de fora


def test_treino_apagado_no_data4u_fica_de_fora(conn):
    mundo = mundo_basico()
    mundo["TREINO"][1][4] = "T"

    relatorio = importar(conn, copia(mundo))

    assert relatorio.fora_apagados == 1
    assert [t[5] for t in _treinos(conn)] == [1]


@pytest.mark.parametrize("lancamento", [None, 9999])  # sem lançamento, ou lançamento que não está no pacote
def test_treino_sem_aluno_modelo_fica_de_fora(conn, lancamento):
    mundo = mundo_basico()
    mundo["TREINO"].append([3, lancamento, None, "MODELO INICIANTE", "F"])
    mundo["TREINO_FICHA"].append([31, 3, 1, "A"])
    mundo["TREINO_PRESCRICAO"].append([301, 31, 7, 1, "3", "12", None, None, None])

    relatorio = importar(conn, copia(mundo))

    assert relatorio.fora_sem_aluno == 1
    assert 3 not in [t[5] for t in _treinos(conn)]
    assert _linhas(conn, "SELECT COUNT(*) FROM ficha_item") == [(4,)]  # nada do modelo entrou


def test_lancamento_que_nao_e_de_treino_fica_de_fora(conn):
    mundo = mundo_basico()
    mundo["LANCAMENTO_OBJ"][1][2] = -300

    relatorio = importar(conn, copia(mundo))

    assert relatorio.fora_sem_aluno == 1
    assert [t[5] for t in _treinos(conn)] == [1]


def test_treino_de_pessoa_que_nao_esta_no_app_fica_de_fora_e_conta_as_pessoas(conn):
    mundo = mundo_basico()
    mundo["LANCAMENTO_OBJ"] += [[5003, 777, -510, "2026-05-01 10:00:00"], [5004, 777, -510, "2026-05-02 10:00:00"]]
    mundo["TREINO"] += [[3, 5003, 900, "T1", "F"], [4, 5004, 900, "T2", "F"]]

    relatorio = importar(conn, copia(mundo))

    assert relatorio.fora_aluno_fora_do_app == 2
    assert relatorio.alunos_fora_do_app == 1  # duas vezes a mesma pessoa
    assert relatorio.alunos_com_historico == 2


def test_treino_com_data_ilegivel_fica_de_fora(conn):
    mundo = mundo_basico()
    mundo["LANCAMENTO_OBJ"][1][3] = "10/04/2026"

    relatorio = importar(conn, copia(mundo))

    assert relatorio.fora_sem_data == 1
    assert [t[5] for t in _treinos(conn)] == [1]


def test_treino_cujo_id_ja_e_de_um_treino_do_app_nao_e_duplicado(conn):
    # No futuro o app envia treinos ao Data4U e guarda o ID_TREINO; a cópia seguinte traz esse treino de volta.
    conn.execute(
        "INSERT INTO treino (aluno_id, nome, montado_por, origem, data4u_id) VALUES (1, 'FEITO NO APP', 'ANA', 'app', 1)"
    )
    conn.commit()

    relatorio = importar(conn, copia(mundo_basico()))

    assert relatorio.fora_ja_e_do_app == 1
    assert _linhas(conn, "SELECT nome, origem FROM treino WHERE data4u_id = 1") == [("FEITO NO APP", "app")]


# ------------------------------------------------------------------ nomes e professor


def test_sem_nome_ou_sem_professor_usa_o_rotulo_e_conta(conn):
    mundo = mundo_basico()
    mundo["TREINO"][0][3] = None
    mundo["TREINO"][0][2] = None  # sem professor
    mundo["TREINO"][1][2] = 12345  # professor que não está no pacote

    relatorio = importar(conn, copia(mundo))

    assert relatorio.treinos_sem_nome == 1
    assert relatorio.treinos_sem_professor == 2
    assert [(t[2], t[3]) for t in _treinos(conn)] == [
        (NOME_TREINO_SEM_NOME, NOME_SEM_PROFESSOR),
        ("TREINO D", NOME_SEM_PROFESSOR),
    ]


def test_nomes_longos_sao_cortados_no_limite_e_contados(conn):
    mundo = mundo_basico()
    mundo["TREINO"][0][3] = "T" * 50
    mundo["PESSOA"][0][1] = "P" * 70
    mundo["TREINO_FICHA"][0][3] = "F" * 20

    relatorio = importar(conn, copia(mundo))

    assert relatorio.nomes_cortados == 3
    assert _linhas(conn, "SELECT nome, montado_por FROM treino WHERE data4u_id = 1") == [("T" * 40, "P" * 60)]
    assert _linhas(conn, "SELECT nome FROM ficha WHERE treino_id = 1 AND ordem = 1") == [("F" * 15,)]


def test_ficha_sem_nome_recebe_o_numero(conn):
    mundo = mundo_basico()
    mundo["TREINO_FICHA"][0][3] = None
    mundo["TREINO_FICHA"][1][3] = "  "

    importar(conn, copia(mundo))

    assert _linhas(conn, "SELECT nome FROM ficha WHERE treino_id = 1 ORDER BY ordem") == [("Ficha 1",), ("Ficha 2",)]


def test_nome_do_treino_com_espacos_e_quebras_e_limpo(conn):
    mundo = mundo_basico()
    mundo["TREINO"][0][3] = "  TREINO \n ABC  "

    importar(conn, copia(mundo))

    assert _linhas(conn, "SELECT nome FROM treino WHERE data4u_id = 1") == [("TREINO ABC",)]


# ------------------------------------------------------------------ séries, repetições, carga, pausa, observação


def test_campos_longos_sao_cortados_e_contados(conn):
    mundo = mundo_basico()
    mundo["TREINO_PRESCRICAO"][0][4:9] = ["S" * 15, "R" * 12, "C" * 30, "00:01:00", "O" * 250]

    relatorio = importar(conn, copia(mundo))

    assert relatorio.campos_cortados == 4
    assert _linhas(conn, "SELECT series, repeticoes, carga, length(observacao) FROM ficha_item WHERE ficha_id = 1 AND ordem = 1") == [
        ("S" * 11, "R" * 11, "C" * 11, 200)
    ]


def test_campos_vazios_viram_nulo(conn):
    mundo = mundo_basico()
    mundo["TREINO_PRESCRICAO"][0][4:9] = ["", "  ", "", None, "   "]

    importar(conn, copia(mundo))

    assert _linhas(conn, "SELECT series, repeticoes, carga, pausa, observacao FROM ficha_item WHERE ficha_id = 1 AND ordem = 1") == [
        (None, None, None, None, None)
    ]


def test_pausa_fora_do_formato_fica_vazia_e_e_contada(conn):
    mundo = mundo_basico()
    mundo["TREINO_PRESCRICAO"][0][7] = "um minuto"
    mundo["TREINO_PRESCRICAO"][1][7] = None  # vazia no Data4U: não é "ilegível"

    relatorio = importar(conn, copia(mundo))

    assert relatorio.pausas_ilegiveis == 1
    assert _linhas(conn, "SELECT pausa FROM ficha_item WHERE ficha_id = 1 ORDER BY ordem") == [(None,), (None,)]


# ------------------------------------------------------------------ exercícios


def test_exercicio_que_ja_esta_na_biblioteca_e_reaproveitado(conn):
    biblioteca = conn.execute(
        "INSERT INTO exercicio (nome, origem, ativo) VALUES ('Supino reto com barra', 'data4u_academia', 1)"
    ).lastrowid
    conn.execute("INSERT INTO exercicio_data4u (data4u_id, exercicio_id) VALUES (-5, ?)", (biblioteca,))
    conn.commit()

    relatorio = importar(conn, copia(mundo_basico()))

    assert relatorio.exercicios_ja_na_biblioteca == 1
    assert _linhas(conn, "SELECT DISTINCT exercicio_id FROM ficha_item WHERE ficha_id IN (1, 3) AND ordem = 1") == [(biblioteca,)]
    assert _linhas(conn, "SELECT nome FROM exercicio WHERE nome = 'SUPINO RETO'") == []  # não criou outro com o nome do Data4U


def test_exercicio_que_nao_esta_na_biblioteca_entra_inativo_com_a_origem_certa(conn):
    relatorio = importar(conn, copia(mundo_basico()))

    assert relatorio.exercicios_novos_inativos == 2
    assert _linhas(conn, "SELECT nome, ativo, combinado, origem FROM exercicio ORDER BY nome") == [
        ("REMADA BAIXA", 0, 0, "data4u_academia"),  # id positivo: criado na academia
        ("SUPINO RETO", 0, 0, "data4u_catalogo"),  # id negativo: veio com o Data4U
    ]
    # e o id do Data4U fica registrado (serve para devolver o treino ao Data4U)
    assert _linhas(conn, "SELECT data4u_id FROM exercicio_data4u ORDER BY data4u_id") == [(-5,), (7,)]


def test_exercicio_inativo_nao_aparece_na_biblioteca_nem_pode_ser_usado_em_treino_novo(conn):
    from app import exercicios, treinos

    importar(conn, copia(mundo_basico()))

    assert exercicios.buscar_exercicios(conn)["total"] == 0
    id_inativo = _linhas(conn, "SELECT id FROM exercicio WHERE nome = 'REMADA BAIXA'")[0][0]
    dados = {
        "nome_treino": "NOVO", "montado_por": "ANA",
        "fichas": [{"nome": "A", "itens": [{"exercicio_id": id_inativo, "series": "3", "repeticoes": "10"}]}],
    }
    with pytest.raises(treinos.TreinoInvalido, match="foi desativado"):
        treinos.salvar_treino(conn, 1, dados)


def test_tags_html_saem_do_nome_e_o_apagado_fica(conn):
    mundo = mundo_basico()
    mundo["TREINO_EXERCICIO"][0][1] = "<b>(10) CADEIRA EXTENSORA</b> APAGADO"

    importar(conn, copia(mundo))

    assert _linhas(conn, "SELECT nome FROM exercicio WHERE origem = 'data4u_catalogo'") == [("(10) CADEIRA EXTENSORA APAGADO",)]


def test_exercicio_com_nome_que_ja_existe_no_app_usa_o_existente(conn):
    existente = conn.execute("INSERT INTO exercicio (nome, origem, ativo) VALUES ('supino reto', 'app', 1)").lastrowid
    conn.commit()

    relatorio = importar(conn, copia(mundo_basico()))

    assert relatorio.exercicios_com_nome_ja_existente == 1  # caixa diferente conta como o mesmo nome
    assert relatorio.exercicios_novos_inativos == 1
    assert _linhas(conn, "SELECT exercicio_id FROM exercicio_data4u WHERE data4u_id = -5") == [(existente,)]
    assert _linhas(conn, "SELECT ativo FROM exercicio WHERE id = ?", existente) == [(1,)]  # continua ativo


def test_dois_exercicios_do_data4u_com_o_mesmo_nome_viram_um_so(conn):
    mundo = mundo_basico()
    mundo["TREINO_EXERCICIO"].append([8, "<b>remada baixa</b>"])
    mundo["TREINO_PRESCRICAO"].append([104, 12, 8, 2, "3", "10", None, None, None])

    importar(conn, copia(mundo))

    assert _linhas(conn, "SELECT COUNT(*) FROM exercicio WHERE nome LIKE 'remada baixa'") == [(1,)]
    assert _linhas(conn, "SELECT COUNT(DISTINCT exercicio_id) FROM exercicio_data4u WHERE data4u_id IN (7, 8)") == [(1,)]


def test_exercicio_que_nao_existe_na_tabela_do_data4u_vira_o_rotulo_de_removido(conn):
    mundo = mundo_basico()
    mundo["TREINO_PRESCRICAO"] += [
        [105, 12, 555, 2, "3", "10", None, None, None],
        [106, 12, 556, 3, "3", "10", None, None, None],  # outro id sumido: usa o mesmo rótulo
    ]

    relatorio = importar(conn, copia(mundo))

    assert relatorio.exercicios_sem_cadastro == 2
    assert _linhas(conn, "SELECT nome, ativo FROM exercicio WHERE nome = ?", NOME_DO_EXERCICIO_REMOVIDO) == [
        (NOME_DO_EXERCICIO_REMOVIDO, 0)
    ]
    assert _linhas(conn, "SELECT COUNT(*) FROM ficha_item i JOIN exercicio e ON e.id = i.exercicio_id WHERE e.nome = ?", NOME_DO_EXERCICIO_REMOVIDO) == [(2,)]


def test_nome_de_exercicio_so_com_tags_tambem_vira_o_rotulo(conn):
    mundo = mundo_basico()
    mundo["TREINO_EXERCICIO"][1][1] = "<b></b>"

    relatorio = importar(conn, copia(mundo))

    assert relatorio.exercicios_sem_cadastro == 1


def test_nome_de_exercicio_muito_longo_e_cortado(conn):
    mundo = mundo_basico()
    mundo["TREINO_EXERCICIO"][1][1] = "E" * 130

    relatorio = importar(conn, copia(mundo))

    assert relatorio.nomes_cortados == 1
    assert _linhas(conn, "SELECT length(nome) FROM exercicio WHERE origem = 'data4u_academia'") == [(120,)]


# ------------------------------------------------------------------ prescrição sem exercício escolhido
# Existe no Data4U real (08/10/2026: 236 de 129.471). O primeiro teste com o arquivo de verdade recusou
# o pacote inteiro por causa delas; por isso o servidor as aceita e decide o que fazer com cada uma.


def _mundo_com_itens_sem_exercicio(*itens):
    """O mundo básico, com estes itens (sem exercício) acrescentados na ficha B (id 12), depois do item 103."""
    mundo = mundo_basico()
    mundo["TREINO_PRESCRICAO"] += [list(item) for item in itens]
    return mundo


def test_pacote_com_prescricao_sem_exercicio_e_aceito():
    mundo = _mundo_com_itens_sem_exercicio([104, 12, None, 2, None, None, None, None, None])

    copia_de_pacote(empacotar(mundo), agora=AGORA)  # não levanta


def test_item_sem_exercicio_mas_com_algo_escrito_entra_com_o_rotulo(conn):
    mundo = _mundo_com_itens_sem_exercicio(
        [104, 12, None, 2, "3", "15", "MODERADO", "00:00:00", None],
        [105, 12, None, 3, None, None, None, None, "ABDOMINAL CANOINHA"],
    )

    relatorio = importar(conn, copia(mundo))

    itens = _linhas(
        conn,
        "SELECT i.ordem, e.nome, e.ativo, i.series, i.repeticoes, i.carga, i.observacao"
        " FROM ficha_item i JOIN exercicio e ON e.id = i.exercicio_id WHERE i.ficha_id = 2 ORDER BY i.ordem",
    )
    assert itens == [
        (1, "REMADA BAIXA", 0, "3", "15", "5", None),
        (2, NOME_DO_EXERCICIO_NAO_INFORMADO, 0, "3", "15", "MODERADO", None),
        (3, NOME_DO_EXERCICIO_NAO_INFORMADO, 0, None, None, None, "ABDOMINAL CANOINHA"),
    ]
    assert (relatorio.itens_sem_exercicio, relatorio.itens_vazios_ignorados) == (2, 0)
    assert relatorio.exercicios_prescritos == 6  # os 4 de antes + os 2 novos
    assert _linhas(conn, "SELECT COUNT(*) FROM exercicio WHERE nome = ?", NOME_DO_EXERCICIO_NAO_INFORMADO) == [(1,)]


def test_item_sem_exercicio_e_sem_nada_escrito_fica_de_fora_e_a_ordem_continua_sem_buraco(conn):
    mundo = _mundo_com_itens_sem_exercicio(
        [104, 12, None, 2, None, None, None, None, None],  # em branco
        [105, 12, None, 3, "", "  ", "", "00:00:00", "   "],  # só espaços e pausa zero: também em branco
        [106, 12, 7, 4, "2", "8", None, None, None],  # com exercício: entra, na ordem 2 (não 4)
    )

    relatorio = importar(conn, copia(mundo))

    assert _linhas(
        conn, "SELECT i.ordem, e.nome FROM ficha_item i JOIN exercicio e ON e.id = i.exercicio_id WHERE i.ficha_id = 2 ORDER BY i.ordem"
    ) == [(1, "REMADA BAIXA"), (2, "REMADA BAIXA")]
    assert (relatorio.itens_sem_exercicio, relatorio.itens_vazios_ignorados) == (0, 2)
    assert _linhas(conn, "SELECT COUNT(*) FROM exercicio WHERE nome = ?", NOME_DO_EXERCICIO_NAO_INFORMADO) == [(0,)]


def test_pausa_maior_que_zero_basta_para_o_item_sem_exercicio_entrar(conn):
    mundo = _mundo_com_itens_sem_exercicio(
        [104, 12, None, 2, None, None, None, "00:00:30", None],  # só a pausa: entra
        [105, 12, None, 3, None, None, None, "meio minuto", None],  # pausa ilegível e nada mais: fica de fora
    )

    relatorio = importar(conn, copia(mundo))

    assert (relatorio.itens_sem_exercicio, relatorio.itens_vazios_ignorados) == (1, 1)
    assert _linhas(conn, "SELECT pausa FROM ficha_item WHERE ficha_id = 2 ORDER BY ordem") == [(None,), (30,)]
    assert relatorio.pausas_ilegiveis == 0  # o item ignorado não conta como "pausa ilegível"


def test_item_sem_exercicio_nao_conta_como_exercicio_usado_nem_cria_exercicio_do_data4u(conn):
    mundo = _mundo_com_itens_sem_exercicio([104, 12, None, 2, "3", "15", None, None, None])

    relatorio = importar(conn, copia(mundo))

    assert relatorio.exercicios_usados == 2  # SUPINO RETO e REMADA BAIXA
    assert _linhas(conn, "SELECT COUNT(*) FROM exercicio_data4u WHERE exercicio_id IN (SELECT id FROM exercicio WHERE nome = ?)", NOME_DO_EXERCICIO_NAO_INFORMADO) == [(0,)]


def test_rotulo_de_exercicio_nao_informado_e_um_so_mesmo_rodando_de_novo(conn):
    mundo = _mundo_com_itens_sem_exercicio(
        [104, 12, None, 2, "3", "15", None, None, None],
        [202, 21, None, 2, "3", "15", None, None, None],  # em outro treino
    )

    importar(conn, copia(mundo))
    importar(conn, copia(mundo))

    assert _linhas(conn, "SELECT COUNT(*) FROM exercicio WHERE nome = ?", NOME_DO_EXERCICIO_NAO_INFORMADO) == [(1,)]
    assert _linhas(conn, "SELECT COUNT(*) FROM ficha_item i JOIN exercicio e ON e.id = i.exercicio_id WHERE e.nome = ?", NOME_DO_EXERCICIO_NAO_INFORMADO) == [(2,)]


def test_rotulo_de_exercicio_nao_informado_nao_aparece_na_lista_de_montar_treino(conn):
    mundo = _mundo_com_itens_sem_exercicio([104, 12, None, 2, "3", "15", None, None, None])

    importar(conn, copia(mundo))

    assert _linhas(conn, "SELECT ativo FROM exercicio WHERE nome = ?", NOME_DO_EXERCICIO_NAO_INFORMADO) == [(0,)]


def test_simulacao_com_item_sem_exercicio_nao_deixa_o_rotulo_no_banco(conn):
    mundo = _mundo_com_itens_sem_exercicio([104, 12, None, 2, "3", "15", None, None, None])

    relatorio = importar(conn, copia(mundo), simular=True)

    assert relatorio.itens_sem_exercicio == 1
    assert _linhas(conn, "SELECT COUNT(*) FROM exercicio") == [(0,)]


def test_relatorio_conta_os_itens_sem_exercicio(conn):
    mundo = _mundo_com_itens_sem_exercicio(
        [104, 12, None, 2, "3", "15", None, None, None],
        [105, 12, None, 3, None, None, None, None, None],
    )

    texto = importar(conn, copia(mundo)).texto()

    assert f'(ficaram "{NOME_DO_EXERCICIO_NAO_INFORMADO}"): 1' in texto
    assert "itens sem exercício e sem nada escrito (ficaram de fora): 1" in texto


def test_cupom_de_treino_com_item_sem_exercicio_funciona(conn):
    from app import cupom

    mundo = _mundo_com_itens_sem_exercicio([104, 12, None, 2, None, None, None, None, "ABDOMINAL CANOINHA"])
    importar(conn, copia(mundo))

    conteudo = cupom.montar_cupom(conn, 1)

    exercicios = [linha["esquerda"] for ficha in conteudo["fichas"] for linha in ficha["linhas"] if linha["tipo"] == "exercicio"]
    assert NOME_DO_EXERCICIO_NAO_INFORMADO in exercicios


def test_so_os_exercicios_dos_treinos_importados_entram(conn):
    mundo = mundo_basico()
    mundo["TREINO"][1][4] = "T"  # o treino 2 (único que usa o exercício -5 na ficha 21...) fica de fora
    mundo["TREINO_PRESCRICAO"] = [p for p in mundo["TREINO_PRESCRICAO"] if p[2] != -5 or p[1] == 21]
    mundo["TREINO_EXERCICIO"].append([99, "NUNCA USADO"])

    importar(conn, copia(mundo))

    assert _linhas(conn, "SELECT nome FROM exercicio ORDER BY nome") == [("REMADA BAIXA",)]


# ------------------------------------------------------------------ rodar de novo (espelho)


def test_rodar_de_novo_atualiza_sem_duplicar_e_mantem_os_ids(conn):
    importar(conn, copia(mundo_basico()))
    antes = _treinos(conn)

    relatorio = importar(conn, copia(mundo_basico()))

    assert (relatorio.treinos_novos, relatorio.treinos_atualizados, relatorio.treinos_removidos) == (0, 2, 0)
    assert _treinos(conn) == antes
    assert _linhas(conn, "SELECT COUNT(*) FROM ficha") == [(3,)]
    assert _linhas(conn, "SELECT COUNT(*) FROM ficha_item") == [(4,)]
    assert _linhas(conn, "SELECT COUNT(*) FROM exercicio") == [(2,)]
    assert relatorio.exercicios_novos_inativos == 0  # na segunda vez os exercícios já estão registrados


def test_mudanca_no_data4u_chega_ao_app(conn):
    importar(conn, copia(mundo_basico()))
    mundo = mundo_basico()
    mundo["TREINO"][0][3] = "TREINO ABC NOVO"
    mundo["TREINO_PRESCRICAO"][0][4] = "5"
    mundo["TREINO_PRESCRICAO"].pop()  # sumiu a prescrição da ficha 21

    importar(conn, copia(mundo))

    assert _linhas(conn, "SELECT nome FROM treino WHERE data4u_id = 1") == [("TREINO ABC NOVO",)]
    assert _linhas(conn, "SELECT series FROM ficha_item WHERE ficha_id IN (SELECT id FROM ficha WHERE treino_id = 1) ORDER BY id")[0] == ("5",)
    assert _linhas(conn, "SELECT COUNT(*) FROM ficha_item") == [(3,)]


def test_treino_que_sumiu_do_data4u_sai_do_app_com_fichas_e_itens(conn):
    importar(conn, copia(mundo_basico()))
    mundo = mundo_basico()
    mundo["TREINO"].pop()  # o treino 2 não está mais no Data4U

    relatorio = importar(conn, copia(mundo))

    assert relatorio.treinos_removidos == 1
    assert [t[5] for t in _treinos(conn)] == [1]
    assert _linhas(conn, "SELECT COUNT(*) FROM ficha WHERE treino_id = 2") == [(0,)]
    assert _linhas(conn, "SELECT COUNT(*) FROM ficha_item") == [(3,)]
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_treino_que_deixou_de_valer_sai_do_app(conn):
    importar(conn, copia(mundo_basico()))
    mundo = mundo_basico()
    mundo["TREINO"][1][4] = "T"  # apagado no Data4U depois da primeira cópia

    relatorio = importar(conn, copia(mundo))

    assert relatorio.treinos_removidos == 1
    assert [t[5] for t in _treinos(conn)] == [1]


def test_treino_montado_no_app_nunca_e_tocado(conn):
    conn.execute("INSERT INTO treino (aluno_id, nome, montado_por) VALUES (1, 'MEU TREINO', 'CARLA')")
    conn.execute("INSERT INTO ficha (treino_id, nome, ordem) VALUES (1, 'A', 1)")
    conn.commit()
    importar(conn, copia(mundo_basico()))
    mundo = mundo_basico()
    mundo["TREINO"] = [mundo["TREINO"][1]]  # a aluna 1 perdeu todo o histórico no Data4U

    importar(conn, copia(mundo))

    assert _linhas(conn, "SELECT nome, origem FROM treino WHERE aluno_id = 1") == [("MEU TREINO", "app")]
    assert _linhas(conn, "SELECT COUNT(*) FROM ficha WHERE treino_id = 1") == [(1,)]


def test_treino_move_de_aluno_se_o_data4u_mudar_o_dono(conn):
    importar(conn, copia(mundo_basico()))
    mundo = mundo_basico()
    mundo["LANCAMENTO_OBJ"][0][1] = 102

    importar(conn, copia(mundo))

    assert _linhas(conn, "SELECT aluno_id FROM treino WHERE data4u_id = 1") == [(2,)]


# ------------------------------------------------------------------ tudo ou nada, simulação


def test_erro_no_meio_nao_deixa_nada_gravado(conn, monkeypatch):
    chamadas = []

    def quebra_na_terceira(texto):
        chamadas.append(texto)
        if len(chamadas) == 3:
            raise RuntimeError("falha no meio")
        return None

    monkeypatch.setattr(importar_treinos, "pausa_em_segundos", quebra_na_terceira)

    with pytest.raises(RuntimeError, match="falha no meio"):
        importar(conn, copia(mundo_basico()))

    for tabela in ("treino", "ficha", "ficha_item", "exercicio", "exercicio_data4u"):
        assert _linhas(conn, f"SELECT COUNT(*) FROM {tabela}") == [(0,)], tabela
    assert not conn.in_transaction


def test_erro_no_meio_de_uma_segunda_importacao_mantem_a_primeira(conn, monkeypatch):
    importar(conn, copia(mundo_basico()))
    antes = _linhas(conn, "SELECT id, ficha_id, ordem, series FROM ficha_item ORDER BY id")
    mundo = mundo_basico()
    mundo["TREINO"][0][3] = "MUDOU"

    monkeypatch.setattr(importar_treinos, "pausa_em_segundos", lambda _t: (_ for _ in ()).throw(RuntimeError("x")))
    with pytest.raises(RuntimeError):
        importar(conn, copia(mundo))

    assert _linhas(conn, "SELECT nome FROM treino WHERE data4u_id = 1") == [("TREINO ABC",)]
    assert _linhas(conn, "SELECT id, ficha_id, ordem, series FROM ficha_item ORDER BY id") == antes


def test_simulacao_conta_tudo_mas_nao_grava_nada(conn):
    relatorio = importar(conn, copia(mundo_basico()), simular=True)

    assert relatorio.simulado is True
    assert relatorio.treinos_novos == 2 and relatorio.exercicios_novos_inativos == 2
    assert "SIMULAÇÃO" in relatorio.texto()
    for tabela in ("treino", "ficha", "ficha_item", "exercicio", "exercicio_data4u"):
        assert _linhas(conn, f"SELECT COUNT(*) FROM {tabela}") == [(0,)], tabela
    assert not conn.in_transaction


def test_simulacao_nao_estraga_um_historico_que_ja_existe(conn):
    importar(conn, copia(mundo_basico()))
    antes = _treinos(conn)
    mundo = mundo_basico()
    mundo["TREINO"].pop()

    relatorio = importar(conn, copia(mundo), simular=True)

    assert relatorio.treinos_removidos == 1
    assert _treinos(conn) == antes


# ------------------------------------------------------------------ o relatório


def test_relatorio_so_tem_contagens_sem_nome_de_aluno_ou_professor(conn):
    relatorio = importar(conn, copia(mundo_basico()))

    texto = relatorio.texto()
    dicionario = relatorio.como_dicionario()

    for segredo in ("ANA FICTICIA", "BRUNO FICTICIO", "PROF ANA", "PROF BRUNO", "SUPINO", "REMADA"):
        assert segredo not in texto
        assert segredo not in str(dicionario)
    assert dicionario["treinos"] == 2 and dicionario["novos"] == 2 and dicionario["atualizados"] == 0
    assert dicionario["extraido_em"] == "08/10/2026 05:00"
    assert "Treinos na cópia: 2" in texto


# ------------------------------------------------------------------ o que o resto do app vê


def test_ficha_do_aluno_mostra_o_treino_importado(conn):
    from app import alunos

    importar(conn, copia(mundo_basico()))

    ficha = alunos.obter_ficha(conn, 1)

    assert [t["nome"] for t in ficha["treinos"]] == ["TREINO ABC"]
    treino = ficha["treinos"][0]
    assert treino["montado_por"] == "PROF ANA"
    assert treino["criado_em"] == "02/03/2026"
    assert [f["nome"] for f in treino["fichas"]] == ["A", "B"]
    assert [i["exercicio"] for i in treino["fichas"][0]["itens"]] == ["SUPINO RETO", "REMADA BAIXA"]


def test_cupom_do_treino_importado_funciona(conn):
    from app import cupom

    importar(conn, copia(mundo_basico()))
    treino_id = _linhas(conn, "SELECT id FROM treino WHERE data4u_id = 1")[0][0]

    conteudo = cupom.montar_cupom(conn, treino_id)

    assert ("PROF.", "PROF ANA") in conteudo["cabecalho"]
    assert ("DATA", "02/03/2026") in conteudo["cabecalho"]
    assert conteudo["fichas"][0]["linhas"][0]["esquerda"] == "SUPINO RETO"


def test_professor_nao_pode_repetir_o_nome_de_um_treino_do_historico(conn):
    from app import treinos

    importar(conn, copia(mundo_basico()))
    ativo = conn.execute("INSERT INTO exercicio (nome, origem, ativo) VALUES ('AGACHAMENTO', 'app', 1)").lastrowid
    conn.commit()
    dados = {
        "nome_treino": "treino abc", "montado_por": "CARLA",
        "fichas": [{"nome": "A", "itens": [{"exercicio_id": ativo, "series": "3", "repeticoes": "10"}]}],
    }

    with pytest.raises(treinos.TreinoInvalido, match='já tem um treino chamado "treino abc"') as erro:
        treinos.salvar_treino(conn, 1, dados)

    assert erro.value.status == 409


# ------------------------------------------------------------------ a rota


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "importar_treinos.db"
    c = conectar(caminho)
    criar_tabelas(c)
    c.execute("INSERT INTO aluno (id, nome, data4u_id, situacao) VALUES (1, 'ANA FICTICIA', 101, 'A')")
    c.execute("INSERT INTO aluno (id, nome, data4u_id, situacao) VALUES (2, 'BRUNO FICTICIO', 102, 'A')")
    c.commit()
    c.close()
    return caminho


@pytest.fixture
def app(caminho):
    return criar_app(caminho)


@pytest.fixture
def anonimo(app):
    return app.test_client()


@pytest.fixture
def cliente(app, caminho):
    navegador = app.test_client()
    c = conectar(caminho)
    codigo = acesso.gerar_codigo(c, "Computador de teste").codigo
    token = acesso.autorizar(c, codigo).token
    c.close()
    navegador.set_cookie(acesso.NOME_DO_COOKIE, token)
    return navegador


@pytest.fixture
def pacote_de_hoje():
    """Pacote com a data de "agora" de verdade (a rota usa o relógio real)."""
    from app.alunos import FUSO_DA_ACADEMIA

    agora = datetime.now(timezone.utc).astimezone(FUSO_DA_ACADEMIA)
    return empacotar(mundo_basico(), extracao=f"{agora:%d/%m/%Y %H:%M:%S}")


def _contar(caminho, tabela):
    c = conectar(caminho)
    try:
        return c.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
    finally:
        c.close()


def test_sem_autorizacao_a_rota_devolve_401_e_nao_grava(anonimo, caminho, pacote_de_hoje):
    resposta = anonimo.post("/api/treinos/importar", json=pacote_de_hoje)

    assert resposta.status_code == 401
    assert _contar(caminho, "treino") == 0


def test_rota_importa_e_devolve_o_relatorio(cliente, caminho, pacote_de_hoje):
    resposta = cliente.post("/api/treinos/importar", json=pacote_de_hoje)

    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert corpo["treinos"] == 2 and corpo["novos"] == 2 and corpo["simulado"] is False
    assert "Histórico de treinos do Data4U" in corpo["texto"]
    assert _contar(caminho, "treino") == 2
    assert _contar(caminho, "ficha_item") == 4


def test_rota_enviar_de_novo_nao_duplica(cliente, caminho, pacote_de_hoje):
    cliente.post("/api/treinos/importar", json=pacote_de_hoje)
    segunda = cliente.post("/api/treinos/importar", json=pacote_de_hoje)

    assert segunda.get_json()["atualizados"] == 2
    assert _contar(caminho, "treino") == 2
    assert _contar(caminho, "ficha") == 3


def test_rota_simular_nao_grava(cliente, caminho, pacote_de_hoje):
    pacote_de_hoje["simular"] = True

    resposta = cliente.post("/api/treinos/importar", json=pacote_de_hoje)

    assert resposta.status_code == 200
    assert resposta.get_json()["simulado"] is True
    assert resposta.get_json()["treinos"] == 2
    assert _contar(caminho, "treino") == 0


@pytest.mark.parametrize("valor", ["true", 1, "sim", None])
def test_so_o_booleano_true_liga_a_simulacao(cliente, caminho, pacote_de_hoje, valor):
    pacote_de_hoje["simular"] = valor

    resposta = cliente.post("/api/treinos/importar", json=pacote_de_hoje)

    assert resposta.get_json()["simulado"] is False
    assert _contar(caminho, "treino") == 2


def test_rota_pacote_invalido_devolve_400_e_nao_grava(cliente, caminho, pacote_de_hoje):
    pacote_de_hoje["tabelas"]["TREINO"]["linhas"][0][0] = "um"

    resposta = cliente.post("/api/treinos/importar", json=pacote_de_hoje)

    assert resposta.status_code == 400
    assert "TREINO, linha 1" in resposta.get_json()["erro"]
    assert _contar(caminho, "treino") == 0


def test_rota_pacote_velho_devolve_400(cliente, pacote_de_hoje):
    pacote_de_hoje["extracao"] = "01/01/2020 05:00:00"

    resposta = cliente.post("/api/treinos/importar", json=pacote_de_hoje)

    assert resposta.status_code == 400
    assert "velha demais" in resposta.get_json()["erro"]


def test_rota_exige_json(cliente):
    resposta = cliente.post("/api/treinos/importar", data="x=1", content_type="application/x-www-form-urlencoded")

    assert resposta.status_code == 415


def test_rota_lista_json_nao_vira_erro_500(cliente):
    assert cliente.post("/api/treinos/importar", json=[1, 2, 3]).status_code == 400


def test_rota_aceita_pedido_maior_que_o_limite_comum_mas_nao_maior_que_o_dela(cliente, caminho, pacote_de_hoje):
    # ~150 mil prescrições seriam ~10 MB: bem acima dos 512 KB das outras rotas.
    linhas = [[1000 + n, 11, -5, 3 + n, "3", "12", "20", "00:01:00", "observacao de teste"] for n in range(9000)]
    pacote_de_hoje["tabelas"]["TREINO_PRESCRICAO"]["linhas"] += linhas
    corpo = len(str(pacote_de_hoje))
    assert TAMANHO_MAXIMO_DO_PEDIDO < corpo < TAMANHO_MAXIMO_DA_IMPORTACAO

    resposta = cliente.post("/api/treinos/importar", json=pacote_de_hoje)

    assert resposta.status_code == 200
    assert _contar(caminho, "ficha_item") == 4 + 9000


def test_rota_recusa_pedido_maior_que_o_limite_dela(cliente, pacote_de_hoje):
    pacote_de_hoje["enchimento"] = "x" * (TAMANHO_MAXIMO_DA_IMPORTACAO + 1)

    resposta = cliente.post("/api/treinos/importar", json=pacote_de_hoje)

    assert resposta.status_code == 413


def test_rota_recusa_pedido_vindo_de_outro_site(cliente, caminho, pacote_de_hoje):
    resposta = cliente.post(
        "/api/treinos/importar", json=pacote_de_hoje, headers={"Origin": "https://site-malicioso.example"}
    )

    assert resposta.status_code == 403
    assert _contar(caminho, "treino") == 0


def test_rota_esta_protegida_por_padrao(app):
    from app.web import ENDPOINTS_PUBLICOS

    regras = {regra.rule for regra in app.url_map.iter_rules()}
    assert "/api/treinos/importar" in regras
    assert "api_importar_treinos" not in ENDPOINTS_PUBLICOS


def test_rota_nao_mexe_no_limite_das_outras(cliente, pacote_de_hoje):
    cliente.post("/api/treinos/importar", json=pacote_de_hoje)

    # Um pedido grande para outra rota continua recusado (o limite maior era só da importação).
    grande = cliente.post("/api/alunos/1/whatsapp", json={"whatsapp": "x" * (TAMANHO_MAXIMO_DO_PEDIDO + 10)})
    assert grande.status_code == 413
