"""Testes das atualizações do banco: 4 -> 5 (histórico de treinos do Data4U), 5 -> 6 (ciclo do treino) e
6 -> 7 (treinos padrão).

Os bancos antigos são montados a partir de `schema_v4.sql`, `schema_v5.sql` e `schema_v6.sql`: cópias exatas dos
desenhos que estiveram em produção (a versão 4 desde 07/10/2026, a 5 e a 6 desde 08/10/2026). Se alguém
mexer no schema.sql sem escrever a migração, o teste "banco migrado fica igual a um banco novo" falha.
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
SCHEMA_V5 = Path(__file__).with_name("schema_v5.sql")
SCHEMA_V6 = Path(__file__).with_name("schema_v6.sql")


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


def _banco_v5(caminho) -> None:
    """Cria um banco da versão 5 (a de produção até o ciclo do treino), com alunos de vários jeitos:

    - aluno 1: três treinos (o 3 e o 2 com a MESMA data de lançamento: o de maior id é o mais recente);
    - aluno 2: um treino só (lançado às 02:30 UTC de 05/10 = 23:30 de 04/10 em Brasília);
    - aluno 3: nenhum treino.
    """
    conn = sqlite3.connect(caminho)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_V5.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO RETO', 'app')")
    conn.execute("INSERT INTO aluno (id, nome) VALUES (1, 'MARIANA COSTA'), (2, 'JOAO SILVA'), (3, 'ANA LIMA')")
    conn.executemany(
        "INSERT INTO treino (id, aluno_id, nome, montado_por, origem, data4u_id, criado_em) VALUES (?, ?, ?, 'ANA', ?, ?, ?)",
        [
            (1, 1, "TREINO ANTIGO", "data4u", 501, "2026-09-01 12:00:00"),
            (2, 1, "TREINO MEIO", "app", None, "2026-10-05 15:00:00"),
            (3, 1, "TREINO NOVO", "app", None, "2026-10-05 15:00:00"),
            (4, 2, "TREINO UNICO", "app", None, "2026-10-05 02:30:00"),
        ],
    )
    conn.execute("INSERT INTO ficha (id, treino_id, nome, ordem) VALUES (1, 3, 'A', 1)")
    conn.execute(
        "INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, series, repeticoes) VALUES (1, 1, 1, '3', '12')"
    )
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
    assert conn.execute("SELECT COUNT(*) FROM treino WHERE ativo = 1").fetchone()[0] == 4  # em produção todos são ativos
    conn.close()


@pytest.fixture
def caminho_v5(tmp_path):
    caminho = tmp_path / "app.db"
    _banco_v5(caminho)
    return caminho


def _banco_v6(caminho) -> None:
    """Cria um banco da versão 6 (a de produção até os treinos padrão), com um aluno e um treino completo."""
    conn = sqlite3.connect(caminho)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_V6.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO RETO', 'app')")
    conn.execute("INSERT INTO aluno (id, nome) VALUES (1, 'MARIANA COSTA')")
    conn.execute(
        "INSERT INTO treino (id, aluno_id, nome, montado_por, inicio, sessoes_por_ficha)"
        " VALUES (1, 1, 'TREINO ABC', 'ANA', '2026-10-05', 15)"
    )
    conn.execute("INSERT INTO ficha (id, treino_id, nome, ordem) VALUES (1, 1, 'A', 1)")
    conn.execute(
        "INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, series, repeticoes) VALUES (1, 1, 1, '3', '12')"
    )
    conn.execute("INSERT INTO sessao (treino_id, ficha_ordem) VALUES (1, 1)")
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
    conn.close()


@pytest.fixture
def caminho_v6(tmp_path):
    caminho = tmp_path / "app.db"
    _banco_v6(caminho)
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

    assert aplicadas == [4, 5, 6]  # a 4 -> 5 e, na sequência, a 5 -> 6 e a 6 -> 7
    assert conn.execute("PRAGMA user_version").fetchone()[0] == VERSAO_DO_BANCO == 7
    treinos = conn.execute("SELECT id, nome, montado_por, origem, data4u_id FROM treino ORDER BY id").fetchall()
    assert [tuple(t) for t in treinos] == [
        (1, "TREINO ABC", "ANA", "app", None),
        (2, "TREINO D", "ANA", "app", None),
    ]
    assert conn.execute("SELECT COUNT(*) FROM ficha_item").fetchone()[0] == 1
    assert conn.execute("SELECT nome FROM aluno").fetchone()[0] == "MARIANA COSTA"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()


@pytest.mark.parametrize("versao_de_partida", [4, 5, 6])
def test_banco_migrado_fica_igual_a_um_banco_novo(tmp_path, versao_de_partida):
    caminho = tmp_path / "app.db"
    {4: _banco_v4, 5: _banco_v5, 6: _banco_v6}[versao_de_partida](caminho)
    migrado = conectar(caminho)
    migrar(migrado)
    novo = conectar()
    criar_tabelas(novo)

    for tabela in ("treino", "ficha", "ficha_item", "aluno", "exercicio", "sessao", "modelo_treino"):
        assert _colunas(migrado, tabela) == _colunas(novo, tabela), tabela
        assert _indices(migrado, tabela) == _indices(novo, tabela), tabela
    migrado.close()
    novo.close()


def test_rodar_de_novo_nao_faz_nada(caminho_v4):
    conn = conectar(caminho_v4)
    assert migrar(conn) == [4, 5, 6]
    assert migrar(conn) == []
    criar_tabelas(conn)  # também não pode dar erro num banco já atual
    conn.close()


def test_criar_tabelas_atualiza_banco_antigo_e_completa_o_resto(caminho_v4):
    conn = conectar(caminho_v4)

    criar_tabelas(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
    assert "origem" in _colunas(conn, "treino")
    assert "inicio" in _colunas(conn, "treino")
    conn.close()


def test_banco_novo_nao_e_migrado():
    conn = conectar()
    assert migrar(conn) == []  # sem tabelas: nada a migrar
    criar_tabelas(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
    conn.close()


def test_banco_na_memoria_migra_sem_copia():
    conn = conectar()
    conn.executescript(SCHEMA_V4.read_text(encoding="utf-8"))

    assert migrar(conn) == [4, 5, 6]  # não há arquivo para copiar, e não pode dar erro por isso
    conn.close()


# ------------------------------------------------------------------ cópia de segurança antes


def test_tira_copia_de_seguranca_antes_de_migrar(caminho_v4):
    conn = conectar(caminho_v4)

    migrar(conn)  # três passos (4 -> 5 -> 6 -> 7): mesmo assim uma cópia só, do banco como era
    conn.close()

    copias = list((caminho_v4.parent / PASTA_ANTES_DA_MIGRACAO).glob("app-*.db"))
    assert len(copias) == 1
    antiga = sqlite3.connect(copias[0])
    assert antiga.execute("PRAGMA user_version").fetchone()[0] == 4  # a cópia é do banco COMO ERA
    assert antiga.execute("SELECT COUNT(*) FROM treino").fetchone()[0] == 2
    assert "origem" not in {c[1] for c in antiga.execute("PRAGMA table_info(treino)")}
    antiga.close()


def test_copia_de_seguranca_da_versao_5_guarda_o_banco_como_era(caminho_v5):
    conn = conectar(caminho_v5)

    assert migrar(conn) == [5, 6]
    conn.close()

    copias = list((caminho_v5.parent / PASTA_ANTES_DA_MIGRACAO).glob("app-*.db"))
    assert len(copias) == 1
    antiga = sqlite3.connect(copias[0])
    assert antiga.execute("PRAGMA user_version").fetchone()[0] == 5
    assert antiga.execute("SELECT COUNT(*) FROM treino WHERE ativo = 1").fetchone()[0] == 4  # nada mudou na cópia
    assert "inicio" not in {c[1] for c in antiga.execute("PRAGMA table_info(treino)")}
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


def test_migracao_5_para_6_que_quebra_no_meio_nao_deixa_rastro(caminho_v5, monkeypatch):
    def quebra(conn):
        db._de_5_para_6(conn)  # faz tudo...
        raise RuntimeError("falha no fim")  # ...e quebra no último instante

    monkeypatch.setitem(db.MIGRACOES, 5, quebra)
    conn = conectar(caminho_v5)

    with pytest.raises(RuntimeError, match="falha no fim"):
        migrar(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
    assert "inicio" not in _colunas(conn, "treino")
    assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'sessao'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM treino WHERE ativo = 1").fetchone()[0] == 4  # e nenhum treino foi inativado
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
    # cada passo roda uma vez só; quem chega primeiro faz o que dá, o outro faz o resto (ou nada)
    assert sorted(a for r in resultados for a in r) == [4, 5, 6]
    conn = conectar(caminho_v4)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
    conn.close()


# ------------------------------------------------------------------ o app sobe sozinho com banco antigo


def test_app_atualiza_banco_antigo_ao_subir(caminho_v4):
    criar_app(caminho_v4)

    conn = conectar(caminho_v4)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
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


def _treino(conn, aluno=1, nome="TREINO A", origem="app", data4u_id=None, ativo=0, **extras):
    # ativo=0 por padrão: só um treino por aluno pode ser ativo, e estes testes olham outras regras.
    colunas = ["aluno_id", "nome", "montado_por", "origem", "data4u_id", "ativo", *extras]
    valores = [aluno, nome, "ANA", origem, data4u_id, ativo, *extras.values()]
    return conn.execute(
        f"INSERT INTO treino ({', '.join(colunas)}) VALUES ({', '.join('?' * len(colunas))})", valores
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


# ------------------------------------------------------------------ 5 -> 6: o que muda nos dados

DIAS = {1: "2026-09-01", 2: "2026-10-05", 3: "2026-10-05", 4: "2026-10-04"}


def test_5_para_6_so_o_treino_mais_recente_de_cada_aluno_continua_ativo(caminho_v5):
    conn = conectar(caminho_v5)

    migrar(conn)

    ativos = {t["id"]: t["ativo"] for t in conn.execute("SELECT id, ativo FROM treino")}
    # aluno 1: o 3 (mesma data do 2, maior id); aluno 2: o único
    assert ativos == {1: 0, 2: 0, 3: 1, 4: 1}
    conn.close()


def test_5_para_6_inicio_e_o_dia_do_lancamento_em_brasilia(caminho_v5):
    conn = conectar(caminho_v5)

    migrar(conn)

    inicios = {t["id"]: t["inicio"] for t in conn.execute("SELECT id, inicio FROM treino")}
    # o treino 4 foi lançado às 02:30 UTC de 05/10 = 23:30 de 04/10 em Brasília
    assert inicios == DIAS
    conn.close()


def test_5_para_6_inicio_respeita_o_horario_de_verao_de_antes_de_2019(tmp_path):
    caminho = tmp_path / "app.db"
    _banco_v5(caminho)
    antigo = sqlite3.connect(caminho)
    # Em dezembro de 2017 Brasília estava em horário de verão (UTC-2): 02:30 UTC era 00:30 do dia 15.
    # Com um "menos 3 horas" fixo daria 23:30 do dia 14 (errado).
    antigo.execute("UPDATE treino SET criado_em = '2017-12-15 02:30:00' WHERE id = 1")
    antigo.commit()
    antigo.close()
    conn = conectar(caminho)

    migrar(conn)

    assert conn.execute("SELECT inicio FROM treino WHERE id = 1").fetchone()[0] == "2017-12-15"
    conn.close()


def test_5_para_6_fim_concluido_em_e_meta_ficam_vazios(caminho_v5):
    conn = conectar(caminho_v5)

    migrar(conn)

    linhas = conn.execute("SELECT fim, concluido_em, sessoes_por_ficha FROM treino").fetchall()
    assert [tuple(l) for l in linhas] == [(None, None, None)] * 4
    conn.close()


def test_5_para_6_nao_perde_fichas_nem_itens_e_a_tabela_sessao_nasce_vazia(caminho_v5):
    conn = conectar(caminho_v5)

    migrar(conn)

    assert conn.execute("SELECT COUNT(*) FROM ficha").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM ficha_item").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM sessao").fetchone()[0] == 0
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_5_para_6_banco_sem_nenhum_treino(tmp_path):
    caminho = tmp_path / "app.db"
    vazio = sqlite3.connect(caminho)
    vazio.executescript(SCHEMA_V5.read_text(encoding="utf-8"))
    vazio.close()
    conn = conectar(caminho)

    assert migrar(conn) == [5, 6]
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
    conn.close()


# ------------------------------------------------------------------ 6: o que o desenho novo permite e recusa


def test_so_um_treino_ativo_por_aluno(conn_nova):
    _treino(conn_nova, nome="X1", ativo=1)

    with pytest.raises(sqlite3.IntegrityError):
        _treino(conn_nova, nome="X2", ativo=1)

    _treino(conn_nova, nome="X3", ativo=0)  # inativos podem ser muitos
    _treino(conn_nova, nome="X4", ativo=0)
    _treino(conn_nova, aluno=2, nome="X1", ativo=1)  # e cada aluno tem o seu ativo


def test_treino_novo_nasce_ativo_por_padrao(conn_nova):
    conn_nova.execute("INSERT INTO treino (aluno_id, nome, montado_por) VALUES (1, 'X1', 'ANA')")

    assert conn_nova.execute("SELECT ativo FROM treino").fetchone()[0] == 1


@pytest.mark.parametrize("coluna", ["inicio", "fim"])
@pytest.mark.parametrize("valor", ["2026-1-5", "05/10/2026", "2026-10-051", "", "hoje"])
def test_data_do_treino_com_formato_errado_e_recusada(conn_nova, coluna, valor):
    with pytest.raises(sqlite3.IntegrityError):
        _treino(conn_nova, **{coluna: valor})


def test_data_do_treino_certa_e_vazia_sao_aceitas(conn_nova):
    _treino(conn_nova, nome="X1", inicio="2026-10-05", fim="2026-12-31")
    _treino(conn_nova, nome="X2", inicio=None, fim=None)


@pytest.mark.parametrize("valor", [0, -1, 1000])
def test_meta_de_sessoes_fora_de_1_a_999_e_recusada(conn_nova, valor):
    with pytest.raises(sqlite3.IntegrityError):
        _treino(conn_nova, sessoes_por_ficha=valor)


@pytest.mark.parametrize("valor", [1, 15, 999, None])
def test_meta_de_sessoes_valida(conn_nova, valor):
    _treino(conn_nova, sessoes_por_ficha=valor)


def test_sessao_acompanha_o_treino_e_some_junto(conn_nova):
    treino = _treino(conn_nova)
    conn_nova.execute("INSERT INTO sessao (treino_id, ficha_ordem) VALUES (?, 1)", (treino,))
    assert conn_nova.execute("SELECT feita_em FROM sessao").fetchone()[0]  # a hora é preenchida sozinha

    conn_nova.execute("DELETE FROM treino WHERE id = ?", (treino,))

    assert conn_nova.execute("SELECT COUNT(*) FROM sessao").fetchone()[0] == 0


def test_sessao_exige_treino_que_existe_e_ficha_a_partir_de_1(conn_nova):
    treino = _treino(conn_nova)
    with pytest.raises(sqlite3.IntegrityError):
        conn_nova.execute("INSERT INTO sessao (treino_id, ficha_ordem) VALUES (999, 1)")
    with pytest.raises(sqlite3.IntegrityError):
        conn_nova.execute("INSERT INTO sessao (treino_id, ficha_ordem) VALUES (?, 0)", (treino,))


# ------------------------------------------------------------------ 6 -> 7: treinos padrão


def test_6_para_7_nao_perde_nada_e_a_tabela_dos_padroes_nasce_vazia(caminho_v6):
    conn = conectar(caminho_v6)

    assert migrar(conn) == [6]

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
    assert conn.execute("SELECT COUNT(*) FROM modelo_treino").fetchone()[0] == 0
    assert conn.execute("SELECT nome, ativo, inicio, sessoes_por_ficha FROM treino").fetchone()[:] == ("TREINO ABC", 1, "2026-10-05", 15)
    assert conn.execute("SELECT COUNT(*) FROM ficha_item").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM sessao").fetchone()[0] == 1
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_copia_de_seguranca_da_versao_6_guarda_o_banco_como_era(caminho_v6):
    conn = conectar(caminho_v6)

    migrar(conn)
    conn.close()

    copias = list((caminho_v6.parent / PASTA_ANTES_DA_MIGRACAO).glob("app-*.db"))
    assert len(copias) == 1
    antiga = sqlite3.connect(copias[0])
    assert antiga.execute("PRAGMA user_version").fetchone()[0] == 6
    assert antiga.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'modelo_treino'").fetchone()[0] == 0
    antiga.close()


def test_migracao_6_para_7_que_quebra_no_fim_nao_deixa_rastro(caminho_v6, monkeypatch):
    def quebra(conn):
        db._de_6_para_7(conn)
        raise RuntimeError("falha no fim")

    monkeypatch.setitem(db.MIGRACOES, 6, quebra)
    conn = conectar(caminho_v6)

    with pytest.raises(RuntimeError, match="falha no fim"):
        migrar(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
    assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'modelo_treino'").fetchone()[0] == 0
    assert not conn.in_transaction
    conn.close()


def test_banco_com_o_numero_baixado_a_mao_para_6_sobe_de_novo_sem_perder_os_padroes(caminho_v6, monkeypatch):
    # Para abrir o banco com o app antigo (que ignora a tabela nova) alguém pode baixar o número da versão.
    conn = conectar(caminho_v6)
    migrar(conn)
    conn.execute("INSERT INTO modelo_treino (nome, montado_por, conteudo) VALUES ('BÁSICO', 'ANA', '{}')")
    conn.commit()
    conn.execute("PRAGMA user_version = 6")
    monkeypatch.setattr(db, "fazer_backup", lambda *_a, **_k: None)  # o nome da cópia leva só o segundo: aqui não importa

    assert migrar(conn) == [6]  # a tabela já existe: não pode falhar

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
    assert conn.execute("SELECT nome FROM modelo_treino").fetchall()[0][0] == "BÁSICO"
    conn.close()


def test_modelo_treino_aceita_nome_de_1_a_40_e_professor_de_1_a_60(conn_nova):
    def inserir(nome, professor, meta=None):
        conn_nova.execute(
            "INSERT INTO modelo_treino (nome, montado_por, sessoes_por_ficha, conteudo) VALUES (?, ?, ?, '{}')",
            (nome, professor, meta),
        )

    inserir("X" * 40, "Y" * 60, 999)
    inserir("Y", "A", None)
    for nome, professor, meta in [("", "A", None), ("X" * 41, "A", None), ("N", "", None), ("N", "P" * 61, None), ("N", "A", 0), ("N", "A", 1000)]:
        with pytest.raises(sqlite3.IntegrityError):
            inserir(nome, professor, meta)


def test_nome_do_modelo_nao_repete_nem_com_outra_caixa(conn_nova):
    conn_nova.execute("INSERT INTO modelo_treino (nome, montado_por, conteudo) VALUES ('Básico', 'A', '{}')")

    with pytest.raises(sqlite3.IntegrityError):
        conn_nova.execute("INSERT INTO modelo_treino (nome, montado_por, conteudo) VALUES ('básico', 'B', '{}')")
