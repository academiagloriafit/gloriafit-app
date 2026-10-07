"""Junção do aluno provisório com a pessoa do Data4U, pelo CPF (app/importar_alunos.py).

Todos os dados aqui são inventados. O CPF 12345678909 é válido pelos dígitos verificadores
e não pertence a ninguém conhecido; o 98765432100 também.
"""

import sqlite3

import pytest

from app.importar_alunos import importar
from app.provisorios import cadastrar_provisorio
from tests.test_importar_alunos import AGORA, conn, contato, importar_de, pessoa, periodo  # noqa: F401  (conn é fixture)

CPF = "12345678909"
OUTRO_CPF = "98765432100"


def _provisorio(conn, nome="CARLA NOVA", cpf=CPF, whatsapp=None):
    return cadastrar_provisorio(conn, {"nome": nome, "cpf": cpf, "whatsapp": whatsapp})


def _linha(conn, aluno_id):
    return dict(conn.execute("SELECT * FROM aluno WHERE id = ?", (aluno_id,)).fetchone())


def _total(conn):
    return conn.execute("SELECT COUNT(*) FROM aluno").fetchone()[0]


# ------------------------------------------------------------------ o caso normal


def test_junta_o_provisorio_com_a_pessoa_do_data4u_pelo_cpf(conn, tmp_path):
    aluno_id = _provisorio(conn, "CARLA", whatsapp="27977776666")
    conn.execute("INSERT INTO exercicio (nome, origem) VALUES ('SUPINO', 'app')")
    conn.execute("INSERT INTO treino (aluno_id, nome, montado_por) VALUES (?, 'TREINO A', 'Prof')", (aluno_id,))
    conn.commit()
    criado_em = _linha(conn, aluno_id)["criado_em"]

    relatorio = importar_de(
        conn, tmp_path, [pessoa(500, "  CARLA  MARIA  SOUZA ", "123.456.789-09")], [periodo(500, "A")]
    )

    assert _total(conn) == 1  # não nasceu um segundo cadastro
    aluno = _linha(conn, aluno_id)  # a linha do provisório é a que ficou
    assert aluno["provisorio"] == 0
    assert aluno["data4u_id"] == 500
    assert aluno["nome"] == "CARLA MARIA SOUZA"  # o nome do Data4U prevalece
    assert aluno["situacao"] == "A"
    assert aluno["cpf"] == CPF
    assert aluno["criado_em"] == criado_em
    assert conn.execute("SELECT COUNT(*) FROM treino WHERE aluno_id = ?", (aluno_id,)).fetchone()[0] == 1
    assert (relatorio.novos, relatorio.provisorios_juntados) == (0, 1)
    assert relatorio.importadas == 1
    assert (relatorio.provisorios_sem_par, relatorio.provisorios_com_cpf_duvidoso) == (0, 0)


def test_whatsapp_digitado_no_app_vale_mais_que_o_do_data4u(conn, tmp_path):
    aluno_id = _provisorio(conn, whatsapp="27977776666")

    relatorio = importar_de(
        conn, tmp_path, [pessoa(500, "CARLA", CPF)], [periodo(500, "A")], [contato(1, 500, "27911112222")]
    )

    aluno = _linha(conn, aluno_id)
    assert aluno["whatsapp"] == "27977776666"
    assert aluno["whatsapp_corrigido_no_app"] == 1
    assert relatorio.whatsapp_mantido_do_app == 1


def test_provisorio_sem_whatsapp_recebe_o_do_data4u(conn, tmp_path):
    aluno_id = _provisorio(conn, whatsapp=None)

    importar_de(conn, tmp_path, [pessoa(500, "CARLA", CPF)], [periodo(500, "A")], [contato(1, 500, "(27) 91111-2222")])

    aluno = _linha(conn, aluno_id)
    assert aluno["whatsapp"] == "27911112222"
    assert aluno["whatsapp_corrigido_no_app"] == 0  # esse número veio do Data4U: pode ser atualizado depois


def test_provisorio_sem_whatsapp_e_data4u_sem_celular_continua_sem_whatsapp(conn, tmp_path):
    aluno_id = _provisorio(conn)

    importar_de(conn, tmp_path, [pessoa(500, "CARLA", CPF)], [periodo(500, "A")])

    assert _linha(conn, aluno_id)["whatsapp"] is None


def test_depois_de_juntado_vira_aluno_comum_e_a_segunda_importacao_nao_muda_nada(conn, tmp_path):
    aluno_id = _provisorio(conn)
    args = ([pessoa(500, "CARLA", CPF)], [periodo(500, "A")])
    importar_de(conn, tmp_path, *args)
    antes = _linha(conn, aluno_id)

    segunda = importar_de(conn, tmp_path, *args)

    assert _linha(conn, aluno_id) == antes
    assert _total(conn) == 1
    assert (segunda.novos, segunda.atualizados, segunda.iguais, segunda.provisorios_juntados) == (0, 0, 1, 0)


def test_junta_so_o_provisorio_certo_e_deixa_os_outros(conn, tmp_path):
    carla = _provisorio(conn, "CARLA", CPF)
    davi = _provisorio(conn, "DAVI", OUTRO_CPF)

    relatorio = importar_de(conn, tmp_path, [pessoa(500, "CARLA", CPF)], [periodo(500, "A")])

    assert _linha(conn, carla)["provisorio"] == 0
    assert _linha(conn, davi)["provisorio"] == 1
    assert _linha(conn, davi)["data4u_id"] is None
    assert (relatorio.provisorios_juntados, relatorio.provisorios_sem_par, relatorio.provisorios_com_cpf_duvidoso) == (1, 1, 0)


def test_junta_varios_de_uma_vez(conn, tmp_path):
    carla = _provisorio(conn, "CARLA", CPF)
    davi = _provisorio(conn, "DAVI", OUTRO_CPF)

    relatorio = importar_de(
        conn,
        tmp_path,
        [pessoa(500, "CARLA", CPF), pessoa(501, "DAVI", OUTRO_CPF), pessoa(502, "ELISA", "11111111111")],
        [periodo(500, "A"), periodo(501, "P"), periodo(502, "A")],
    )

    assert _linha(conn, carla)["data4u_id"] == 500
    assert _linha(conn, davi)["data4u_id"] == 501
    assert _total(conn) == 3
    assert (relatorio.novos, relatorio.provisorios_juntados, relatorio.provisorios_sem_par) == (1, 2, 0)


# ------------------------------------------------------------------ quando NÃO junta


def test_cpf_diferente_nao_junta(conn, tmp_path):
    aluno_id = _provisorio(conn)

    relatorio = importar_de(conn, tmp_path, [pessoa(500, "CARLA", OUTRO_CPF)], [periodo(500, "A")])

    assert _linha(conn, aluno_id)["provisorio"] == 1
    assert _total(conn) == 2
    assert (relatorio.novos, relatorio.provisorios_juntados) == (1, 0)
    assert (relatorio.provisorios_sem_par, relatorio.provisorios_com_cpf_duvidoso) == (1, 0)


def test_mesmo_nome_mas_cpf_diferente_nao_junta(conn, tmp_path):
    # Nome igual não prova que é a mesma pessoa: só o CPF liga.
    aluno_id = _provisorio(conn, "CARLA MARIA SOUZA", CPF)

    importar_de(conn, tmp_path, [pessoa(500, "CARLA MARIA SOUZA", "11111111111")], [periodo(500, "A")])

    assert _linha(conn, aluno_id)["provisorio"] == 1


def test_pessoa_do_data4u_sem_cpf_nao_junta(conn, tmp_path):
    aluno_id = _provisorio(conn)

    importar_de(conn, tmp_path, [pessoa(500, "CARLA", None)], [periodo(500, "A")])

    assert _linha(conn, aluno_id)["provisorio"] == 1
    assert _total(conn) == 2


def test_provisorio_sem_cpf_nunca_e_juntado_com_pessoa_sem_cpf(conn, tmp_path):
    # O app exige CPF no provisório, mas se um dia existir um sem CPF, "sem CPF" não liga com "sem CPF".
    aluno_id = conn.execute("INSERT INTO aluno (nome, provisorio) VALUES ('SEM CPF', 1)").lastrowid
    conn.commit()

    relatorio = importar_de(conn, tmp_path, [pessoa(500, "OUTRA SEM CPF", None)], [periodo(500, "A")])

    assert _linha(conn, aluno_id)["provisorio"] == 1
    assert _total(conn) == 2
    assert relatorio.provisorios_juntados == 0


def test_pessoa_com_cpf_invalido_no_data4u_nao_junta(conn, tmp_path):
    aluno_id = _provisorio(conn)

    importar_de(conn, tmp_path, [pessoa(500, "CARLA", "123456789")], [periodo(500, "A")])  # 9 números

    assert _linha(conn, aluno_id)["provisorio"] == 1


@pytest.mark.parametrize(
    "extra, periodos",
    [
        ({"tipo": "J"}, [periodo(500, "A")]),  # pessoa jurídica
        ({"apagada": "T"}, [periodo(500, "A")]),  # cadastro apagado no Data4U
        ({}, []),  # sem situação nenhuma
    ],
    ids=["pessoa_juridica", "apagada", "sem_situacao"],
)
def test_pessoa_que_nao_entra_no_app_nao_junta(conn, tmp_path, extra, periodos):
    aluno_id = _provisorio(conn)

    relatorio = importar_de(conn, tmp_path, [pessoa(500, "CARLA", CPF, **extra)], periodos)

    assert _linha(conn, aluno_id)["provisorio"] == 1
    assert _total(conn) == 1
    assert relatorio.provisorios_juntados == 0


def test_duas_pessoas_do_data4u_com_o_mesmo_cpf_nao_junta_com_nenhuma(conn, tmp_path):
    # No Data4U há CPF repetido em mais de uma pessoa (4 casos conferidos). Sem certeza, não junta.
    aluno_id = _provisorio(conn)

    relatorio = importar_de(
        conn,
        tmp_path,
        [pessoa(500, "CARLA UM", CPF), pessoa(501, "CARLA DOIS", CPF)],
        [periodo(500, "A"), periodo(501, "A")],
    )

    assert _linha(conn, aluno_id)["provisorio"] == 1
    assert _linha(conn, aluno_id)["data4u_id"] is None
    assert _total(conn) == 3  # as duas pessoas entraram como alunos novos, o provisório ficou
    assert (relatorio.novos, relatorio.provisorios_juntados) == (2, 0)
    assert (relatorio.provisorios_sem_par, relatorio.provisorios_com_cpf_duvidoso) == (1, 1)


def test_cpf_repetido_entre_pessoa_da_copia_e_pessoa_ja_importada_antes_nao_junta(conn, tmp_path):
    # A pessoa 400 entrou em outro dia e não vem nesta cópia; a 500 tem o mesmo CPF.
    # (O app não deixa cadastrar o provisório com um CPF que já está nele; montamos o estado à força.)
    conn.execute("INSERT INTO aluno (nome, cpf, data4u_id, situacao) VALUES ('ANTIGA', ?, 400, 'D')", (CPF,))
    aluno_id = conn.execute("INSERT INTO aluno (nome, cpf, provisorio) VALUES ('CARLA', ?, 1)", (CPF,)).lastrowid
    conn.commit()

    relatorio = importar_de(conn, tmp_path, [pessoa(500, "CARLA", CPF)], [periodo(500, "A")])

    assert _linha(conn, aluno_id)["provisorio"] == 1
    assert relatorio.provisorios_juntados == 0
    assert relatorio.provisorios_com_cpf_duvidoso == 1


def test_dois_provisorios_com_o_mesmo_cpf_nao_junta_com_nenhum(conn, tmp_path):
    # O app não deixa cadastrar dois (CPF repetido é recusado), mas se acontecer por outro caminho
    # o importador não escolhe no palpite.
    a = conn.execute("INSERT INTO aluno (nome, cpf, provisorio) VALUES ('A', ?, 1)", (CPF,)).lastrowid
    b = conn.execute("INSERT INTO aluno (nome, cpf, provisorio) VALUES ('B', ?, 1)", (CPF,)).lastrowid
    conn.commit()

    relatorio = importar_de(conn, tmp_path, [pessoa(500, "CARLA", CPF)], [periodo(500, "A")])

    assert _linha(conn, a)["provisorio"] == 1 and _linha(conn, b)["provisorio"] == 1
    assert (relatorio.novos, relatorio.provisorios_juntados) == (1, 0)
    assert (relatorio.provisorios_sem_par, relatorio.provisorios_com_cpf_duvidoso) == (2, 2)


def test_provisorio_cujo_cpf_ja_e_de_aluno_ligado_ao_data4u_nao_e_juntado(conn, tmp_path):
    # A pessoa 500 já estava no app; agora o Data4U passou a trazer o CPF dela igual ao do provisório.
    importar_de(conn, tmp_path, [pessoa(500, "CARLA", None)], [periodo(500, "A")])
    aluno_id = conn.execute("INSERT INTO aluno (nome, cpf, provisorio) VALUES ('CARLA N', ?, 1)", (CPF,)).lastrowid
    conn.commit()

    relatorio = importar_de(conn, tmp_path, [pessoa(500, "CARLA", CPF)], [periodo(500, "A")])

    assert _linha(conn, aluno_id)["provisorio"] == 1  # só junta quando a pessoa aparece pela primeira vez
    assert relatorio.provisorios_juntados == 0
    assert relatorio.provisorios_com_cpf_duvidoso == 1


def test_aluno_comum_sem_matricula_nao_e_confundido_com_provisorio(conn, tmp_path):
    comum = conn.execute("INSERT INTO aluno (nome, cpf, provisorio) VALUES ('COMUM', ?, 0)", (CPF,)).lastrowid
    conn.commit()

    relatorio = importar_de(conn, tmp_path, [pessoa(500, "CARLA", CPF)], [periodo(500, "A")])

    assert _linha(conn, comum)["data4u_id"] is None
    assert relatorio.provisorios_juntados == 0
    assert _total(conn) == 2


# ------------------------------------------------------------------ segurança dos dados


def test_se_der_erro_depois_da_juncao_o_provisorio_volta_ao_que_era(conn, tmp_path):
    aluno_id = _provisorio(conn, "CARLA", whatsapp="27977776666")
    antes = _linha(conn, aluno_id)
    conn.execute(
        "CREATE TRIGGER explode BEFORE INSERT ON aluno WHEN NEW.nome = 'EXPLODE' "
        "BEGIN SELECT RAISE(ABORT, 'erro de teste'); END"
    )

    with pytest.raises(sqlite3.IntegrityError, match="erro de teste"):
        importar_de(
            conn,
            tmp_path,
            [pessoa(500, "CARLA", CPF), pessoa(501, "EXPLODE", "11111111111")],
            [periodo(500, "A"), periodo(501, "A")],
        )

    assert _linha(conn, aluno_id) == antes
    assert _total(conn) == 1


def test_juntar_nao_apaga_nem_duplica_treinos_fichas_e_itens(conn, tmp_path):
    aluno_id = _provisorio(conn)
    conn.execute("INSERT INTO exercicio (nome, origem) VALUES ('SUPINO', 'app')")
    treino = conn.execute(
        "INSERT INTO treino (aluno_id, nome, montado_por) VALUES (?, 'TREINO A', 'Prof')", (aluno_id,)
    ).lastrowid
    ficha = conn.execute("INSERT INTO ficha (treino_id, nome, ordem) VALUES (?, 'A', 1)", (treino,)).lastrowid
    conn.execute("INSERT INTO ficha_item (ficha_id, ordem, exercicio_id) VALUES (?, 1, 1)", (ficha,))
    conn.commit()

    importar_de(conn, tmp_path, [pessoa(500, "CARLA", CPF)], [periodo(500, "A")])

    assert conn.execute("SELECT COUNT(*) FROM treino WHERE aluno_id = ?", (aluno_id,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM ficha_item").fetchone()[0] == 1


# ------------------------------------------------------------------ relatório


def test_relatorio_conta_os_provisorios_e_nao_traz_dado_pessoal(conn, tmp_path):
    _provisorio(conn, "NOME SECRETO", CPF)
    _provisorio(conn, "OUTRO SECRETO", OUTRO_CPF)

    relatorio = importar_de(conn, tmp_path, [pessoa(500, "NOME SECRETO", CPF)], [periodo(500, "A")])
    texto = relatorio.texto()

    assert "1 provisórios do app juntados pelo CPF" in texto
    assert "continuam sem par no Data4U: 1" in texto
    assert "SECRETO" not in texto and CPF not in texto and OUTRO_CPF not in texto


def test_relatorio_sem_provisorios_diz_zero(conn, tmp_path):
    texto = importar_de(conn, tmp_path, [pessoa(1)], [periodo(1, "A")]).texto()

    assert "0 provisórios do app juntados pelo CPF" in texto
    assert "continuam sem par no Data4U: 0" in texto
