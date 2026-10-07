"""Testes do desenho do banco: o que ele aceita e o que ele recusa."""

import sqlite3

import pytest

from app.db import VERSAO_DO_BANCO, BancoDesatualizado, conectar, criar_tabelas


@pytest.fixture
def conn():
    c = conectar()  # banco na memória, novo a cada teste
    criar_tabelas(c)
    yield c
    c.close()


def _exercicio(conn, nome="SUPINO RETO"):
    return conn.execute(
        "INSERT INTO exercicio (nome, origem) VALUES (?, 'app')", (nome,)
    ).lastrowid


def _aluno(conn, cpf="12345678909", **extra):
    return conn.execute(
        "INSERT INTO aluno (nome, cpf, whatsapp) VALUES ('MARIANA COSTA', ?, ?)",
        (cpf, extra.get("whatsapp")),
    ).lastrowid


def _ficha(conn):
    aluno = _aluno(conn)
    treino = conn.execute(
        "INSERT INTO treino (aluno_id, nome, montado_por) VALUES (?, 'TREINO ABC', 'ANA')", (aluno,)
    ).lastrowid
    return conn.execute(
        "INSERT INTO ficha (treino_id, nome, ordem) VALUES (?, 'A PEITO', 1)", (treino,)
    ).lastrowid


def test_cria_todas_as_tabelas(conn):
    tabelas = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {
        "grupo_muscular", "exercicio", "exercicio_grupo", "exercicio_data4u",
        "aluno", "treino", "ficha", "ficha_item",
    } <= tabelas


def test_criar_tabelas_pode_rodar_duas_vezes(conn):
    criar_tabelas(conn)  # não pode dar erro nem apagar nada
    _exercicio(conn)
    criar_tabelas(conn)
    assert conn.execute("SELECT COUNT(*) FROM exercicio").fetchone()[0] == 1


def test_chaves_estrangeiras_estao_ligadas(conn):
    ficha = _ficha(conn)
    with pytest.raises(sqlite3.IntegrityError):  # exercício 999 não existe
        conn.execute("INSERT INTO ficha_item (ficha_id, ordem, exercicio_id) VALUES (?, 1, 999)", (ficha,))


def test_nome_do_exercicio_nao_repete_nem_com_outra_caixa(conn):
    _exercicio(conn, "SUPINO RETO")
    with pytest.raises(sqlite3.IntegrityError):
        _exercicio(conn, "supino reto")


def test_origem_do_exercicio_so_aceita_valores_conhecidos(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO exercicio (nome, origem) VALUES ('X', 'internet')")


@pytest.mark.parametrize("cpf", ["1234567890", "123456789012", "1234567890a", "123.456.789-09", ""])
def test_cpf_so_aceita_11_digitos(conn, cpf):
    with pytest.raises(sqlite3.IntegrityError):
        _aluno(conn, cpf=cpf)


def test_cpf_pode_ficar_vazio(conn):
    # 361 pessoas do Data4U não têm CPF: precisam entrar no app mesmo assim.
    aluno_id = _aluno(conn, cpf=None)
    assert conn.execute("SELECT cpf FROM aluno WHERE id = ?", (aluno_id,)).fetchone()[0] is None


@pytest.mark.parametrize("letra", ["A", "T", "P", "D", "I", "C", None])
def test_situacao_aceita_as_letras_do_data4u_ou_vazio(conn, letra):
    conn.execute("INSERT INTO aluno (nome, situacao) VALUES ('FULANO', ?)", (letra,))
    assert conn.execute("SELECT situacao FROM aluno").fetchone()[0] == letra


@pytest.mark.parametrize("letra", ["a", "F", "X", "", "AT", "Ativo"])
def test_situacao_recusa_qualquer_outra_coisa(conn, letra):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO aluno (nome, situacao) VALUES ('FULANO', ?)", (letra,))


def test_cpf_pode_repetir_entre_alunos(conn):
    # Na base do Data4U há CPFs em mais de uma pessoa; o banco não pode travar a cópia.
    _aluno(conn, cpf="12345678909")
    _aluno(conn, cpf="12345678909")
    assert conn.execute("SELECT COUNT(*) FROM aluno").fetchone()[0] == 2


@pytest.mark.parametrize("numero", ["2799288211", "27992882112"])
def test_whatsapp_aceita_10_ou_11_digitos(conn, numero):
    _aluno(conn, whatsapp=numero)


@pytest.mark.parametrize("numero", ["992882112", "(27) 99288-2112", "5527992882112"])
def test_whatsapp_recusa_formato_fora_do_padrao(conn, numero):
    with pytest.raises(sqlite3.IntegrityError):
        _aluno(conn, whatsapp=numero)


def test_aluno_sem_whatsapp_e_permitido(conn):
    _aluno(conn, whatsapp=None)


def test_nome_da_ficha_tem_no_maximo_15_letras(conn):
    aluno = _aluno(conn)
    treino = conn.execute(
        "INSERT INTO treino (aluno_id, nome, montado_por) VALUES (?, 'T', 'ANA')", (aluno,)
    ).lastrowid
    conn.execute("INSERT INTO ficha (treino_id, nome, ordem) VALUES (?, ?, 1)", (treino, "A" * 15))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO ficha (treino_id, nome, ordem) VALUES (?, ?, 2)", (treino, "A" * 16))


def test_nome_do_treino_tem_no_maximo_40_letras(conn):
    aluno = _aluno(conn)
    sql = "INSERT INTO treino (aluno_id, nome, montado_por) VALUES (?, ?, 'ANA')"
    conn.execute(sql, (aluno, "T" * 40))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql, (aluno, "T" * 41))


@pytest.mark.parametrize("campo", ["series", "repeticoes", "carga"])
def test_campos_do_item_tem_no_maximo_11_caracteres(conn, campo):
    ficha, exercicio = _ficha(conn), _exercicio(conn)
    conn.execute(f"INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, {campo}) VALUES (?, 1, ?, ?)",
                 (ficha, exercicio, "x" * 11))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(f"INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, {campo}) VALUES (?, 2, ?, ?)",
                     (ficha, exercicio, "x" * 12))


def test_ordem_nao_repete_dentro_da_ficha(conn):
    ficha, exercicio = _ficha(conn), _exercicio(conn)
    conn.execute("INSERT INTO ficha_item (ficha_id, ordem, exercicio_id) VALUES (?, 1, ?)", (ficha, exercicio))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO ficha_item (ficha_id, ordem, exercicio_id) VALUES (?, 1, ?)", (ficha, exercicio))


def test_bi_set_e_dois_itens_com_o_mesmo_bloco(conn):
    ficha = _ficha(conn)
    supino, crucifixo = _exercicio(conn, "SUPINO RETO"), _exercicio(conn, "CRUCIFIXO")
    conn.execute("INSERT INTO ficha_item (ficha_id, ordem, bloco, exercicio_id) VALUES (?, 1, 1, ?)", (ficha, supino))
    conn.execute("INSERT INTO ficha_item (ficha_id, ordem, bloco, exercicio_id) VALUES (?, 2, 1, ?)", (ficha, crucifixo))
    bloco = conn.execute("SELECT COUNT(*) FROM ficha_item WHERE ficha_id = ? AND bloco = 1", (ficha,)).fetchone()[0]
    assert bloco == 2


def test_apagar_treino_apaga_fichas_e_itens(conn):
    ficha, exercicio = _ficha(conn), _exercicio(conn)
    conn.execute("INSERT INTO ficha_item (ficha_id, ordem, exercicio_id) VALUES (?, 1, ?)", (ficha, exercicio))
    conn.execute("DELETE FROM treino")
    assert conn.execute("SELECT COUNT(*) FROM ficha").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM ficha_item").fetchone()[0] == 0


def test_nao_deixa_apagar_aluno_que_tem_treino(conn):
    _ficha(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM aluno")


def test_nao_deixa_apagar_exercicio_usado_numa_ficha(conn):
    ficha, exercicio = _ficha(conn), _exercicio(conn)
    conn.execute("INSERT INTO ficha_item (ficha_id, ordem, exercicio_id) VALUES (?, 1, ?)", (ficha, exercicio))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM exercicio WHERE id = ?", (exercicio,))


def test_id_do_data4u_pertence_a_um_exercicio_so(conn):
    a, b = _exercicio(conn, "A"), _exercicio(conn, "B")
    conn.execute("INSERT INTO exercicio_data4u (data4u_id, exercicio_id) VALUES (675, ?)", (a,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO exercicio_data4u (data4u_id, exercicio_id) VALUES (675, ?)", (b,))


# ---------------------------------------------------------------- quem montou o treino


def test_nao_existe_mais_tabela_de_professores(conn):
    tabelas = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "professor" not in tabelas


def test_treino_guarda_o_nome_de_quem_montou(conn):
    aluno = _aluno(conn)
    conn.execute(
        "INSERT INTO treino (aluno_id, nome, montado_por) VALUES (?, 'T', ?)", (aluno, "Maria José")
    )
    assert conn.execute("SELECT montado_por FROM treino").fetchone()[0] == "Maria José"


def test_quem_montou_e_obrigatorio_e_vai_de_1_a_60_letras(conn):
    aluno = _aluno(conn)
    sql = "INSERT INTO treino (aluno_id, nome, montado_por) VALUES (?, 'T', ?)"
    conn.execute(sql, (aluno, "A" * 60))
    for invalido in ["", "A" * 61, None]:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql, (aluno, invalido))
    with pytest.raises(sqlite3.IntegrityError):  # sem informar o campo
        conn.execute("INSERT INTO treino (aluno_id, nome) VALUES (?, 'T')", (aluno,))


# ---------------------------------------------------------------- acesso do professor


def test_banco_tem_as_tabelas_de_acesso(conn):
    tabelas = {l[0] for l in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    assert {"codigo_de_autorizacao", "dispositivo", "autorizacao_falha"} <= tabelas


def _dispositivo(conn, nome="Computador", token_hash="a" * 64):
    conn.execute(
        "INSERT INTO dispositivo (nome, token_hash, criado_em, ultimo_uso_em)"
        " VALUES (?, ?, '2026-10-07 12:00:00', '2026-10-07 12:00:00')",
        (nome, token_hash),
    )


def test_dispositivo_exige_nome_de_1_a_40_caracteres(conn):
    _dispositivo(conn, "x" * 40, "b" * 64)
    for invalido in ["", "x" * 41, None]:
        with pytest.raises(sqlite3.IntegrityError):
            _dispositivo(conn, invalido, "c" * 64)


def test_dois_dispositivos_nao_podem_ter_o_mesmo_token(conn):
    _dispositivo(conn, "Um", "d" * 64)

    with pytest.raises(sqlite3.IntegrityError):
        _dispositivo(conn, "Dois", "d" * 64)


def test_codigo_de_autorizacao_exige_nome_valido_e_hash_unico(conn):
    sql = (
        "INSERT INTO codigo_de_autorizacao (codigo_hash, nome_do_dispositivo, criado_em, expira_em)"
        " VALUES (?, ?, '2026-10-07 12:00:00', '2026-10-07 12:15:00')"
    )
    conn.execute(sql, ("e" * 64, "Computador"))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql, ("e" * 64, "Outro"))  # mesmo hash
    for invalido in ["", "x" * 41, None]:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql, ("f" * 64, invalido))


# ---------------------------------------------------------------- versão do banco


def test_banco_novo_nasce_na_versao_atual(conn):
    assert conn.execute("PRAGMA user_version").fetchone()[0] == VERSAO_DO_BANCO


def test_criar_tabelas_de_novo_num_banco_atual_e_permitido(conn):
    criar_tabelas(conn)  # não pode dar erro


def test_banco_da_versao_antiga_e_recusado_com_instrucao(tmp_path):
    caminho = tmp_path / "antigo.db"
    antigo = sqlite3.connect(caminho)
    antigo.executescript("CREATE TABLE treino (id INTEGER PRIMARY KEY); PRAGMA user_version = 1;")
    antigo.close()

    c = conectar(caminho)
    with pytest.raises(BancoDesatualizado, match="versão 1.*apague o arquivo"):
        criar_tabelas(c)
    c.close()
