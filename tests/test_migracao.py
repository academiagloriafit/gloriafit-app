"""Testes da atualização do banco da versão 4 para a 5 (histórico de treinos do Data4U).

O banco da versão 4 é montado a partir de `schema_v4.sql`: a cópia exata do desenho que está
em produção desde 07/10/2026. Se alguém mexer no schema.sql sem escrever a migração, o teste
"banco migrado fica igual a um banco novo" falha.
"""

import sqlite3
import threading
from pathlib import Path

import pytest

from app import db
from app.backup import BackupFalhou
from app.db import PASTA_ANTES_DA_MIGRACAO, VERSAO_DO_BANCO, BancoDesatualizado, conectar, criar_tabelas, migrar, verificar_versao
from app.web import criar_app

SCHEMA_V4 = Path(__file__).with_name("schema_v4.sql")


def _banco_v4(caminho) -> None:
    """Cria um banco da versão 4, com um aluno, dois treinos (um completo) e um exercício."""
    conn = sqlite3.connect(caminho)
    # Em produção o arquivo já está em modo WAL (o `conectar` grava isso no próprio arquivo na primeira vez).
    # Sem esta linha, duas conexões abrindo juntas tentariam trocar o modo ao mesmo tempo e uma falharia com
    # "database is locked" ANTES de chegar à migração, o que não acontece de verdade.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_V4.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO RETO', 'app')")
    conn.execute("INSERT INTO aluno (id, nome, cpf, data4u_id) VALUES (1, 'MARIANA COSTA', '12345678909', 77)")
    conn.execute("INSERT INTO treino (id, aluno_id, nome, montado_por) VALUES (1, 1, 'TREINO ABC', 'ANA')")
    conn.execute("INSERT INTO treino (id, aluno_id, nome, montado_por) VALUES (2, 1, 'TREINO D', 'ANA')")
    conn.execute("INSERT INTO ficha (id, treino_id, nome, ordem) VALUES (1, 1, 'A', 1)")
    conn.execute(
        "INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, series, repeticoes) VALUES (1, 1, 1, '3', '12')"
    )
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
    conn.close()


@pytest.fixture
def caminho_v4(tmp_path):
    caminho = tmp_path / "app.db"
    _banco_v4(caminho)
    return caminho


def _colunas(conn, tabela):
    return {
        linha["name"]: (linha["type"], linha["notnull"], linha["dflt_value"], linha["pk"])
        for linha in conn.execute(f"PRAGMA table_info({tabela})")
    }


def _indices(conn, tabela):
    """{nome do índice: (único?, parcial?, colunas)}."""
    resultado = {}
    for indice in conn.execute(f"PRAGMA index_list({tabela})"):
        if indice["origin"] != "c":  # só os criados com CREATE INDEX (os automáticos de UNIQUE não interessam)
            continue
        colunas = tuple(c["name"] for c in conn.execute(f"PRAGMA index_info({indice['name']})"))
        resultado[indice["name"]] = (bool(indice["unique"]), bool(indice["partial"]), colunas)
    return resultado


# ------------------------------------------------------------------ a migração em si


def test_migra_da_4_para_a_5_sem_perder_nada(caminho_v4):
    conn = conectar(caminho_v4)

    aplicadas = migrar(conn)

    assert aplicadas == [4]
    assert conn.execute("PRAGMA user_version").fetchone()[0] == VERSAO_DO_BANCO == 5
    treinos = conn.execute("SELECT id, nome, montado_por, origem, data4u_id FROM treino ORDER BY id").fetchall()
    assert [tuple(t) for t in treinos] == [
        (1, "TREINO ABC", "ANA", "app", None),
        (2, "TREINO D", "ANA", "app", None),
    ]
    assert conn.execute("SELECT COUNT(*) FROM ficha_item").fetchone()[0] == 1
    assert conn.execute("SELECT nome FROM aluno").fetchone()[0] == "MARIANA COSTA"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()


def test_banco_migrado_fica_igual_a_um_banco_novo(caminho_v4):
    migrado = conectar(caminho_v4)
    migrar(migrado)
    novo = conectar()
    criar_tabelas(novo)

    for tabela in ("treino", "ficha", "ficha_item", "aluno", "exercicio"):
        assert _colunas(migrado, tabela) == _colunas(novo, tabela), tabela
        assert _indices(migrado, tabela) == _indices(novo, tabela), tabela
    migrado.close()
    novo.close()


def test_rodar_de_novo_nao_faz_nada(caminho_v4):
    conn = conectar(caminho_v4)
    assert migrar(conn) == [4]
    assert migrar(conn) == []
    criar_tabelas(conn)  # também não pode dar erro num banco já atual
    conn.close()


def test_criar_tabelas_atualiza_banco_antigo_e_completa_o_resto(caminho_v4):
    conn = conectar(caminho_v4)

    criar_tabelas(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
    assert "origem" in _colunas(conn, "treino")
    conn.close()


def test_banco_novo_nao_e_migrado():
    conn = conectar()
    assert migrar(conn) == []  # sem tabelas: nada a migrar
    criar_tabelas(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
    conn.close()


def test_banco_na_memoria_migra_sem_copia():
    conn = conectar()
    conn.executescript(SCHEMA_V4.read_text(encoding="utf-8"))

    assert migrar(conn) == [4]  # não há arquivo para copiar, e não pode dar erro por isso
    conn.close()


# ------------------------------------------------------------------ cópia de segurança antes


def test_tira_copia_de_seguranca_antes_de_migrar(caminho_v4):
    conn = conectar(caminho_v4)

    migrar(conn)
    conn.close()

    copias = list((caminho_v4.parent / PASTA_ANTES_DA_MIGRACAO).glob("app-*.db"))
    assert len(copias) == 1
    antiga = sqlite3.connect(copias[0])
    assert antiga.execute("PRAGMA user_version").fetchone()[0] == 4  # a cópia é do banco COMO ERA
    assert antiga.execute("SELECT COUNT(*) FROM treino").fetchone()[0] == 2
    assert "origem" not in {c[1] for c in antiga.execute("PRAGMA table_info(treino)")}
    antiga.close()


def test_sem_copia_de_seguranca_nao_migra(caminho_v4, monkeypatch):
    def falha(*_args, **_kwargs):
        raise BackupFalhou("disco cheio")

    monkeypatch.setattr(db, "fazer_backup", falha)
    conn = conectar(caminho_v4)

    with pytest.raises(BackupFalhou):
        migrar(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
    assert "origem" not in _colunas(conn, "treino")
    conn.close()


def test_migracao_que_quebra_no_meio_nao_deixa_rastro(caminho_v4, monkeypatch):
    def quebra(conn):
        conn.execute("ALTER TABLE treino ADD COLUMN origem TEXT NOT NULL DEFAULT 'app'")
        raise RuntimeError("falha no meio")

    monkeypatch.setitem(db.MIGRACOES, 4, quebra)
    conn = conectar(caminho_v4)

    with pytest.raises(RuntimeError, match="falha no meio"):
        migrar(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 4  # a versão também volta
    assert "origem" not in _colunas(conn, "treino")  # e a coluna acrescentada some
    assert not conn.in_transaction
    conn.close()


def test_dois_processos_subindo_juntos_migram_uma_vez_so(caminho_v4):
    resultados = []
    erros = []
    barreira = threading.Barrier(2)

    def subir():
        try:
            conn = conectar(caminho_v4)  # cada processo tem a sua conexão
            barreira.wait(timeout=10)
            resultados.append(migrar(conn))
            conn.close()
        except BaseException as erro:  # noqa: BLE001 - o teste quer ver qualquer falha
            erros.append(erro)

    threads = [threading.Thread(target=subir) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert erros == []
    assert sorted(resultados) == [[], [4]]
    conn = conectar(caminho_v4)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
    conn.close()


# ------------------------------------------------------------------ o app sobe sozinho com banco antigo


def test_app_atualiza_banco_antigo_ao_subir(caminho_v4):
    criar_app(caminho_v4)

    conn = conectar(caminho_v4)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
    conn.close()


# ------------------------------------------------------------------ versões que não sabemos atualizar


def test_versao_antes_da_4_continua_recusada(tmp_path):
    caminho = tmp_path / "v3.db"
    antigo = sqlite3.connect(caminho)
    antigo.executescript("CREATE TABLE treino (id INTEGER PRIMARY KEY); PRAGMA user_version = 3;")
    antigo.close()
    conn = conectar(caminho)

    assert migrar(conn) == []
    with pytest.raises(BancoDesatualizado, match="versão 3.*a partir da versão 4"):
        verificar_versao(conn)
    conn.close()


def test_banco_mais_novo_que_o_app_e_recusado_sem_mandar_apagar(tmp_path):
    caminho = tmp_path / "futuro.db"
    futuro = sqlite3.connect(caminho)
    futuro.executescript("CREATE TABLE treino (id INTEGER PRIMARY KEY); PRAGMA user_version = 99;")
    futuro.close()
    conn = conectar(caminho)

    with pytest.raises(BancoDesatualizado) as erro:
        verificar_versao(conn)

    assert "NÃO apague" in str(erro.value)
    assert "apague o arquivo e crie" not in str(erro.value)
    conn.close()


# ------------------------------------------------------------------ o que o desenho novo permite e recusa


@pytest.fixture
def conn_nova():
    c = conectar()
    criar_tabelas(c)
    c.execute("INSERT INTO aluno (id, nome) VALUES (1, 'MARIANA COSTA'), (2, 'JOAO SILVA')")
    yield c
    c.close()


def _treino(conn, aluno=1, nome="TREINO A", origem="app", data4u_id=None):
    return conn.execute(
        "INSERT INTO treino (aluno_id, nome, montado_por, origem, data4u_id) VALUES (?, ?, 'ANA', ?, ?)",
        (aluno, nome, origem, data4u_id),
    ).lastrowid


def test_nome_repetido_continua_barrado_entre_treinos_do_app(conn_nova):
    _treino(conn_nova, nome="Treino A")

    with pytest.raises(sqlite3.IntegrityError):
        _treino(conn_nova, nome="TREINO A")  # maiúscula/minúscula não diferencia


def test_historico_do_data4u_pode_repetir_nome(conn_nova):
    _treino(conn_nova, nome="TREINO A", origem="data4u", data4u_id=10)
    _treino(conn_nova, nome="TREINO A", origem="data4u", data4u_id=11)

    assert conn_nova.execute("SELECT COUNT(*) FROM treino").fetchone()[0] == 2


def test_treino_do_app_pode_ter_o_nome_de_um_do_historico_no_banco(conn_nova):
    # O banco deixa; quem barra isso para o professor é app/treinos.py (testado em test_treinos.py).
    _treino(conn_nova, nome="TREINO A", origem="data4u", data4u_id=10)
    _treino(conn_nova, nome="TREINO A", origem="app")


def test_data4u_id_nao_repete_mas_vazio_pode_repetir(conn_nova):
    _treino(conn_nova, nome="X1", origem="data4u", data4u_id=10)
    _treino(conn_nova, aluno=2, nome="X2")
    _treino(conn_nova, aluno=2, nome="X3")  # vários sem data4u_id: normal

    with pytest.raises(sqlite3.IntegrityError):
        _treino(conn_nova, aluno=2, nome="X4", origem="data4u", data4u_id=10)


def test_origem_so_aceita_app_ou_data4u(conn_nova):
    with pytest.raises(sqlite3.IntegrityError):
        _treino(conn_nova, origem="outra")


def test_sqlite_desfaz_o_numero_da_versao_junto_com_a_transacao(tmp_path):
    # A migração depende disto: se a mudança do número da versão não voltasse junto com o
    # resto, uma migração cortada ao meio deixaria o banco marcado como atualizado sem estar.
    conn = conectar(tmp_path / "t.db")
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("PRAGMA user_version = 9")
    conn.rollback()

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    conn.close()
