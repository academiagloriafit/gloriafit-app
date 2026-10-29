"""Testes das atualizações do banco: 4 -> 5 (histórico de treinos do Data4U), 5 -> 6 (ciclo do treino),
6 -> 7 (treinos padrão), 7 -> 8 (filas numeradas), 8 -> 9 (senha de administrador), 9 -> 10 (treino sob medida, IA),
10 -> 11 (quando os alunos foram atualizados), 11 -> 12 (login do aluno) e 12 -> 13 (comentários do aluno), 13 -> 14 (esforço ao concluir, exercício feito e carga) 14 -> 15 (o robô aprende com os professores) 15 -> 16 (histórico do treino feito com a IA) 16 -> 17 (fichas diferentes dos dias) e 17 -> 18 (treino agendado).

Os bancos antigos são montados a partir de `schema_v4.sql` ... `schema_v17.sql`: cópias exatas dos desenhos que
estiveram em produção (a versão 4 desde 07/10/2026, a 5 e a 6 desde 08/10/2026, a 7 desde 09/10/2026, a 8 desde 13/10/2026, a 9 desde 13/10/2026, a 10 desde 14/10/2026, a 11 desde 14/10/2026, a 12 desde 15/10/2026, a 13 desde 15/10/2026, a 14 desde 22/10/2026, a 15 desde 23/10/2026). Se alguém
mexer no schema.sql sem escrever a migração, o teste "banco migrado fica igual a um banco novo" falha.
"""

import sqlite3
import threading
from pathlib import Path

import pytest

from app import db
from app.backup import BackupFalhou, BackupJaExiste
from app.db import PASTA_ANTES_DA_MIGRACAO, VERSAO_DO_BANCO, BancoDesatualizado, conectar, criar_tabelas, migrar, verificar_versao
from app.web import criar_app

SCHEMA_V4 = Path(__file__).with_name("schema_v4.sql")
SCHEMA_V5 = Path(__file__).with_name("schema_v5.sql")
SCHEMA_V6 = Path(__file__).with_name("schema_v6.sql")
SCHEMA_V7 = Path(__file__).with_name("schema_v7.sql")
SCHEMA_V8 = Path(__file__).with_name("schema_v8.sql")
SCHEMA_V9 = Path(__file__).with_name("schema_v9.sql")
SCHEMA_V10 = Path(__file__).with_name("schema_v10.sql")
SCHEMA_V11 = Path(__file__).with_name("schema_v11.sql")
SCHEMA_V12 = Path(__file__).with_name("schema_v12.sql")
SCHEMA_V13 = Path(__file__).with_name("schema_v13.sql")
SCHEMA_V14 = Path(__file__).with_name("schema_v14.sql")
SCHEMA_V15 = Path(__file__).with_name("schema_v15.sql")
SCHEMA_V16 = Path(__file__).with_name("schema_v16.sql")
SCHEMA_V17 = Path(__file__).with_name("schema_v17.sql")
SCHEMA_V18 = Path(__file__).with_name("schema_v18.sql")
SCHEMA_V19 = Path(__file__).with_name("schema_v19.sql")
SCHEMA_V20 = Path(__file__).with_name("schema_v20.sql")


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


def _banco_v7(caminho) -> None:
    """Cria um banco da versão 7 (a de produção até as filas numeradas), com um aluno, um treino e um treino padrão."""
    conn = sqlite3.connect(caminho)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_V7.read_text(encoding="utf-8"))
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
    conn.execute("INSERT INTO modelo_treino (id, nome, montado_por, conteudo) VALUES (1, 'BÁSICO', 'ANA', '{}')")
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
    conn.close()


@pytest.fixture
def caminho_v7(tmp_path):
    caminho = tmp_path / "app.db"
    _banco_v7(caminho)
    return caminho


def _banco_v8(caminho) -> None:
    """Cria um banco da versão 8 (a de produção até a senha de administrador), com um aluno, um treino e um padrão numa fila."""
    conn = sqlite3.connect(caminho)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_V8.read_text(encoding="utf-8"))
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
    conn.execute(
        "INSERT INTO modelo_treino (id, nome, montado_por, conteudo, fila_id, numero)"
        " VALUES (1, 'BÁSICO', 'ANA', '{}', 2, 1)"
    )
    conn.execute("INSERT INTO aluno_fila (aluno_id, fila_id, numero_atual, definida_por) VALUES (1, 2, 1, 'ANA')")
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 8
    conn.close()


@pytest.fixture
def caminho_v8(tmp_path):
    caminho = tmp_path / "app.db"
    _banco_v8(caminho)
    return caminho


def _banco_v9(caminho) -> None:
    """Cria um banco da versão 9 (a de produção até o treino sob medida), com um aluno, um treino, um padrão numa fila e a senha de administrador."""
    conn = sqlite3.connect(caminho)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_V9.read_text(encoding="utf-8"))
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
    conn.execute(
        "INSERT INTO modelo_treino (id, nome, montado_por, conteudo, fila_id, numero)"
        " VALUES (1, 'BÁSICO', 'ANA', '{}', 2, 1)"
    )
    conn.execute("INSERT INTO aluno_fila (aluno_id, fila_id, numero_atual, definida_por) VALUES (1, 2, 1, 'ANA')")
    conn.execute("INSERT INTO senha_administrador (id, senha_hash, definida_em) VALUES (1, 'scrypt$x', '2026-10-13 22:00:00')")
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 9
    conn.close()


@pytest.fixture
def caminho_v9(tmp_path):
    caminho = tmp_path / "app.db"
    _banco_v9(caminho)
    return caminho


def _banco_v10(caminho) -> None:
    """Cria um banco da versão 10 (a de produção até a atualização automática dos alunos), com um aluno, um treino, um padrão numa fila, a senha de administrador e um pedido de treino sob medida."""
    conn = sqlite3.connect(caminho)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_V10.read_text(encoding="utf-8"))
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
    conn.execute(
        "INSERT INTO modelo_treino (id, nome, montado_por, conteudo, fila_id, numero)"
        " VALUES (1, 'BÁSICO', 'ANA', '{}', 2, 1)"
    )
    conn.execute("INSERT INTO aluno_fila (aluno_id, fila_id, numero_atual, definida_por) VALUES (1, 2, 1, 'ANA')")
    conn.execute("INSERT INTO senha_administrador (id, senha_hash, definida_em) VALUES (1, 'scrypt$x', '2026-10-13 22:00:00')")
    conn.execute(
        "INSERT INTO ia_pedido (aluno_id, criado_em, dia, situacao, modelo) VALUES (1, '2026-10-14 12:00:00', '2026-10-14', 'pronto', 'm')"
    )
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 10
    conn.close()


@pytest.fixture
def caminho_v10(tmp_path):
    caminho = tmp_path / "app.db"
    _banco_v10(caminho)
    return caminho


def _banco_v11(caminho) -> None:
    """Cria um banco da versão 11 (a de produção até o login do aluno), com um aluno, um treino, a senha de administrador e o registro da última importação."""
    conn = sqlite3.connect(caminho)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_V11.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO RETO', 'app')")
    conn.execute(
        "INSERT INTO aluno (id, nome, cpf, whatsapp, data4u_id, situacao) VALUES (1, 'MARIANA COSTA', '11144477735', '27988887766', 77, 'A')"
    )
    conn.execute(
        "INSERT INTO treino (id, aluno_id, nome, montado_por, inicio, sessoes_por_ficha)"
        " VALUES (1, 1, 'TREINO ABC', 'ANA', '2026-10-05', 15)"
    )
    conn.execute("INSERT INTO senha_administrador (id, senha_hash, definida_em) VALUES (1, 'scrypt$x', '2026-10-13 22:00:00')")
    conn.execute(
        "INSERT INTO importacao (tipo, extraido_em, recebida_em) VALUES ('alunos', '2026-10-14 08:00:17', '2026-10-14 08:15:02')"
    )
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 11
    conn.close()


@pytest.fixture
def caminho_v11(tmp_path):
    caminho = tmp_path / "app.db"
    _banco_v11(caminho)
    return caminho


def _banco_v12(caminho) -> None:
    """Cria um banco da versão 12 (a de produção até os comentários), com um aluno, um treino com um exercício e a senha do aluno."""
    conn = sqlite3.connect(caminho)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_V12.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO RETO', 'app')")
    conn.execute(
        "INSERT INTO aluno (id, nome, cpf, whatsapp, data4u_id, situacao) VALUES (1, 'MARIANA COSTA', '11144477735', '27988887766', 77, 'A')"
    )
    conn.execute(
        "INSERT INTO treino (id, aluno_id, nome, montado_por, inicio, sessoes_por_ficha)"
        " VALUES (1, 1, 'TREINO ABC', 'ANA', '2026-10-05', 15)"
    )
    conn.execute("INSERT INTO ficha (id, treino_id, nome, ordem) VALUES (1, 1, 'A PEITO', 1)")
    conn.execute("INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, series, repeticoes) VALUES (1, 1, 1, '4', '12')")
    conn.execute("INSERT INTO aluno_senha (aluno_id, senha_hash, definida_em) VALUES (1, 'scrypt$x', '2026-10-15 12:00:00')")
    conn.execute("INSERT INTO sessao (treino_id, ficha_ordem, feita_em) VALUES (1, 1, '2026-10-15 20:00:00')")
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 12
    conn.close()


@pytest.fixture
def caminho_v12(tmp_path):
    caminho = tmp_path / "app.db"
    _banco_v12(caminho)
    return caminho


def _banco_v13(caminho) -> None:
    """Cria um banco da versão 13 (a de produção até o esforço e as cargas), com um aluno, um treino, uma sessão e um comentário."""
    conn = sqlite3.connect(caminho)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_V13.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO RETO', 'app')")
    conn.execute(
        "INSERT INTO aluno (id, nome, cpf, whatsapp, data4u_id, situacao) VALUES (1, 'MARIANA COSTA', '11144477735', '27988887766', 77, 'A')"
    )
    conn.execute(
        "INSERT INTO treino (id, aluno_id, nome, montado_por, inicio, sessoes_por_ficha)"
        " VALUES (1, 1, 'TREINO ABC', 'ANA', '2026-10-05', 15)"
    )
    conn.execute("INSERT INTO ficha (id, treino_id, nome, ordem) VALUES (1, 1, 'A PEITO', 1)")
    conn.execute("INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, series, repeticoes) VALUES (1, 1, 1, '4', '12')")
    conn.execute("INSERT INTO sessao (treino_id, ficha_ordem, feita_em) VALUES (1, 1, '2026-10-15 20:00:00')")
    conn.execute(
        "INSERT INTO comentario (aluno_id, treino_id, treino_nome, texto, criado_em)"
        " VALUES (1, 1, 'TREINO ABC', 'Está leve demais', '2026-10-15 21:00:00')"
    )
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 13
    conn.close()


@pytest.fixture
def caminho_v13(tmp_path):
    caminho = tmp_path / "app.db"
    _banco_v13(caminho)
    return caminho


def _banco_v14(caminho) -> None:
    """Cria um banco da versão 14 (a de produção até o robô aprender com os professores), com um aluno, um treino, um pedido de IA e uma carga."""
    conn = sqlite3.connect(caminho)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_V14.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO RETO', 'app')")
    conn.execute(
        "INSERT INTO aluno (id, nome, cpf, whatsapp, data4u_id, situacao) VALUES (1, 'MARIANA COSTA', '11144477735', '27988887766', 77, 'A')"
    )
    conn.execute(
        "INSERT INTO treino (id, aluno_id, nome, montado_por, inicio, sessoes_por_ficha)"
        " VALUES (1, 1, 'TREINO ABC', 'ANA', '2026-10-05', 15)"
    )
    conn.execute("INSERT INTO ficha (id, treino_id, nome, ordem) VALUES (1, 1, 'A PEITO', 1)")
    conn.execute("INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, series, repeticoes) VALUES (1, 1, 1, '4', '12')")
    conn.execute("INSERT INTO sessao (treino_id, ficha_ordem, feita_em, esforco) VALUES (1, 1, '2026-10-20 20:00:00', 2)")
    conn.execute(
        "INSERT INTO execucao (aluno_id, dia, ficha_ordem, exercicio_ordem, exercicio_nome, feito, carga, atualizado_em)"
        " VALUES (1, '2026-10-20', 1, 1, 'SUPINO RETO', 1, '20', '2026-10-20 20:00:00')"
    )
    conn.execute(
        "INSERT INTO ia_pedido (aluno_id, criado_em, dia, situacao, modelo) VALUES (1, '2026-10-21 12:00:00', '2026-10-21', 'pronto', 'm')"
    )
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 14
    conn.close()


@pytest.fixture
def caminho_v14(tmp_path):
    caminho = tmp_path / "app.db"
    _banco_v14(caminho)
    return caminho


def _banco_v15(caminho) -> None:
    """Cria um banco da versão 15 (a de produção até o histórico do treino feito com a IA), com um aluno, um treino e uma linha do retorno."""
    conn = sqlite3.connect(caminho)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_V15.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO RETO', 'app')")
    conn.execute(
        "INSERT INTO aluno (id, nome, cpf, whatsapp, data4u_id, situacao) VALUES (1, 'MARIANA COSTA', '11144477735', '27988887766', 77, 'A')"
    )
    conn.execute(
        "INSERT INTO treino (id, aluno_id, nome, montado_por, inicio, sessoes_por_ficha)"
        " VALUES (1, 1, 'TREINO ABC', 'ANA', '2026-10-05', 15)"
    )
    conn.execute("INSERT INTO ficha (id, treino_id, nome, ordem) VALUES (1, 1, 'A PEITO', 1)")
    conn.execute("INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, series, repeticoes) VALUES (1, 1, 1, '4', '12')")
    conn.execute(
        "INSERT INTO ia_retorno (dia, tipo, objetivo, nivel, dias, minutos, com_observacoes, rodadas, regras, modelo, nota)"
        " VALUES ('2026-10-23', 'avaliacao', 'hipertrofia', 'iniciante', 3, 60, 0, 0, 'abc123', 'claude-sonnet-5-5', 'serviu')"
    )
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 15
    conn.close()


@pytest.fixture
def caminho_v15(tmp_path):
    caminho = tmp_path / "app.db"
    _banco_v15(caminho)
    return caminho


def _banco_v16(caminho) -> None:
    """Cria um banco da versão 16 (a de produção até as fichas diferentes dos dias), com um aluno, um treino e o histórico de um treino feito com a IA."""
    conn = sqlite3.connect(caminho)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_V16.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO RETO', 'app')")
    conn.execute(
        "INSERT INTO aluno (id, nome, cpf, whatsapp, data4u_id, situacao) VALUES (1, 'MARIANA COSTA', '11144477735', '27988887766', 77, 'A')"
    )
    conn.execute(
        "INSERT INTO treino (id, aluno_id, nome, montado_por, inicio, sessoes_por_ficha)"
        " VALUES (1, 1, 'TREINO ABC', 'ANA', '2026-10-05', 15)"
    )
    conn.execute("INSERT INTO ficha (id, treino_id, nome, ordem) VALUES (1, 1, 'A PEITO', 1)")
    conn.execute("INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, series, repeticoes) VALUES (1, 1, 1, '4', '12')")
    conn.execute(
        "INSERT INTO treino_ia (treino_id, objetivo, nivel, dias, minutos, observacoes, justificativa, alertas, ajustes, regras, modelo)"
        " VALUES (1, 'hipertrofia', 'iniciante', 3, 60, 'dor no joelho', '[\"ponto\"]', '[]', '{}', 'abc123', 'claude-sonnet-5-5')"
    )
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 16
    conn.close()


@pytest.fixture
def caminho_v16(tmp_path):
    caminho = tmp_path / "app.db"
    _banco_v16(caminho)
    return caminho


def _banco_v17(caminho) -> None:
    """Cria um banco da versão 17 (a de produção até o treino agendado), com um aluno, um treino ativo e um concluído."""
    conn = sqlite3.connect(caminho)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_V17.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO RETO', 'app')")
    conn.execute("INSERT INTO aluno (id, nome, situacao) VALUES (1, 'MARIANA COSTA', 'A')")
    conn.execute("INSERT INTO treino (id, aluno_id, nome, montado_por, ativo, inicio) VALUES (1, 1, 'TREINO VELHO', 'ANA', 0, '2026-08-01')")
    conn.execute("INSERT INTO treino (id, aluno_id, nome, montado_por, ativo, inicio) VALUES (2, 1, 'TREINO ABC', 'ANA', 1, '2026-10-05')")
    conn.execute("INSERT INTO ficha (id, treino_id, nome, ordem) VALUES (1, 2, 'A PEITO', 1)")
    conn.execute("INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, series, repeticoes) VALUES (1, 1, 1, '4', '12')")
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 17
    conn.close()


@pytest.fixture
def caminho_v17(tmp_path):
    caminho = tmp_path / "app.db"
    _banco_v17(caminho)
    return caminho


def _banco_v18(caminho) -> None:
    """Cria um banco da versão 18 (a de produção até a foto do aluno), com um aluno e um treino ativo."""
    conn = sqlite3.connect(caminho)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_V18.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO RETO', 'app')")
    conn.execute("INSERT INTO aluno (id, nome, situacao, data4u_id) VALUES (1, 'MARIANA COSTA', 'A', 4257)")
    conn.execute("INSERT INTO treino (id, aluno_id, nome, montado_por, ativo, inicio) VALUES (1, 1, 'TREINO ABC', 'ANA', 1, '2026-10-05')")
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 18
    conn.close()


@pytest.fixture
def caminho_v18(tmp_path):
    caminho = tmp_path / "app.db"
    _banco_v18(caminho)
    return caminho


def _banco_v19(caminho) -> None:
    """Cria um banco da versão 19 (a de produção até a foto ampliada), com um aluno e a miniatura da foto dele."""
    conn = sqlite3.connect(caminho)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_V19.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO aluno (id, nome, situacao, data4u_id) VALUES (1, 'MARIANA COSTA', 'A', 4257)")
    conn.execute(
        "INSERT INTO foto_aluno (aluno_id, miniatura, origem_sha256, atualizada_em, vista_em) VALUES (1, ?, ?, '2026-10-29 08:58:20', '2026-10-29 08:58:20')",
        (b"\xff\xd8\xff" + b"x" * 200, "a" * 64),
    )
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 19
    conn.close()


@pytest.fixture
def caminho_v19(tmp_path):
    caminho = tmp_path / "app.db"
    _banco_v19(caminho)
    return caminho


def _banco_v20(caminho) -> None:
    """Cria um banco da versão 20 (a de produção até a foto escolhida pelo aluno), com um aluno e a foto da catraca dele."""
    conn = sqlite3.connect(caminho)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_V20.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO aluno (id, nome, situacao, data4u_id) VALUES (1, 'MARIANA COSTA', 'A', 4257)")
    conn.execute(
        "INSERT INTO foto_aluno (aluno_id, miniatura, grande, origem_sha256, atualizada_em, vista_em) VALUES (1, ?, ?, ?, '2026-10-29 09:16:02', '2026-10-29 09:16:02')",
        (b"\xff\xd8\xff" + b"x" * 200, b"\xff\xd8\xff" + b"y" * 900, "a" * 64),
    )
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 20
    conn.close()


@pytest.fixture
def caminho_v20(tmp_path):
    caminho = tmp_path / "app.db"
    _banco_v20(caminho)
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

    assert aplicadas == [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]  # a 4 -> 5 e, na sequência, 5 -> 6, 6 -> 7, 7 -> 8 e 8 -> 9
    assert conn.execute("PRAGMA user_version").fetchone()[0] == VERSAO_DO_BANCO == 21
    treinos = conn.execute("SELECT id, nome, montado_por, origem, data4u_id FROM treino ORDER BY id").fetchall()
    assert [tuple(t) for t in treinos] == [
        (1, "TREINO ABC", "ANA", "app", None),
        (2, "TREINO D", "ANA", "app", None),
    ]
    assert conn.execute("SELECT COUNT(*) FROM ficha_item").fetchone()[0] == 1
    assert conn.execute("SELECT nome FROM aluno").fetchone()[0] == "MARIANA COSTA"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()


@pytest.mark.parametrize("versao_de_partida", [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20])
def test_banco_migrado_fica_igual_a_um_banco_novo(tmp_path, versao_de_partida):
    caminho = tmp_path / "app.db"
    {4: _banco_v4, 5: _banco_v5, 6: _banco_v6, 7: _banco_v7, 8: _banco_v8, 9: _banco_v9, 10: _banco_v10, 11: _banco_v11, 12: _banco_v12, 13: _banco_v13, 14: _banco_v14, 15: _banco_v15, 16: _banco_v16, 17: _banco_v17, 18: _banco_v18, 19: _banco_v19, 20: _banco_v20}[versao_de_partida](caminho)
    migrado = conectar(caminho)
    migrar(migrado)
    novo = conectar()
    criar_tabelas(novo)

    for tabela in ("treino", "ficha", "ficha_item", "aluno", "exercicio", "sessao", "modelo_treino", "fila", "aluno_fila", "senha_administrador", "senha_administrador_falha", "ia_pedido", "importacao", "aluno_senha", "aluno_codigo", "aluno_sessao", "aluno_evento", "comentario", "execucao", "ia_retorno", "treino_ia", "foto_aluno", "foto_propria", "foto_propria_troca"):
        assert _colunas(migrado, tabela) == _colunas(novo, tabela), tabela
        assert _indices(migrado, tabela) == _indices(novo, tabela), tabela
    migrado.close()
    novo.close()


def test_rodar_de_novo_nao_faz_nada(caminho_v4):
    conn = conectar(caminho_v4)
    assert migrar(conn) == [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
    assert migrar(conn) == []
    criar_tabelas(conn)  # também não pode dar erro num banco já atual
    conn.close()


def test_criar_tabelas_atualiza_banco_antigo_e_completa_o_resto(caminho_v4):
    conn = conectar(caminho_v4)

    criar_tabelas(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    assert "origem" in _colunas(conn, "treino")
    assert "inicio" in _colunas(conn, "treino")
    conn.close()


def test_banco_novo_nao_e_migrado():
    conn = conectar()
    assert migrar(conn) == []  # sem tabelas: nada a migrar
    criar_tabelas(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    conn.close()


def test_banco_na_memoria_migra_sem_copia():
    conn = conectar()
    conn.executescript(SCHEMA_V4.read_text(encoding="utf-8"))

    assert migrar(conn) == [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]  # não há arquivo para copiar, e não pode dar erro por isso
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

    assert migrar(conn) == [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
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


def test_copia_que_outro_processo_acabou_de_tirar_no_mesmo_segundo_nao_impede_a_migracao(caminho_v4, monkeypatch):
    # O nome da cópia só tem segundos: dois processos subindo juntos podem querer o mesmo nome. O segundo não pode falhar por isso
    # (a cópia do primeiro já guarda o banco como era, tirada antes de qualquer passo) e também não pode sobrescrevê-la.
    chamadas = []

    def ja_existe(*_args, **_kwargs):
        chamadas.append(1)
        raise BackupJaExiste("Já existe app-2026-10-23-050000.db: não vou sobrescrever uma cópia.")

    monkeypatch.setattr(db, "fazer_backup", ja_existe)
    conn = conectar(caminho_v4)

    assert migrar(conn) == [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]  # migrou tudo

    assert chamadas == [1]  # tentou a cópia uma vez só (não repete a cada passo)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == VERSAO_DO_BANCO
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
    assert sorted(a for r in resultados for a in r) == [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
    conn = conectar(caminho_v4)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    conn.close()


# ------------------------------------------------------------------ o app sobe sozinho com banco antigo


def test_app_atualiza_banco_antigo_ao_subir(caminho_v4):
    criar_app(caminho_v4)

    conn = conectar(caminho_v4)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
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

    assert migrar(conn) == [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
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

    assert migrar(conn) == [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]  # a 6 -> 7 e, na sequência, 7 -> 8 e 8 -> 9

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
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

    assert migrar(conn) == [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]  # a tabela já existe: não pode falhar

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
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


# ------------------------------------------------------------------ 7 -> 8: filas numeradas


def test_7_para_8_nao_perde_nada_e_nascem_as_cinco_filas(caminho_v7):
    conn = conectar(caminho_v7)

    assert migrar(conn) == [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    filas = [tuple(f) for f in conn.execute("SELECT id, nome, exige_liberacao, ordem FROM fila ORDER BY ordem")]
    assert filas == [
        (1, "Homem", 0, 1),
        (2, "Mulher", 0, 2),
        (3, "Adolescente", 0, 3),
        (4, "Gestante", 1, 4),
        (5, "Grupos de risco", 1, 5),
    ]
    assert conn.execute("SELECT COUNT(*) FROM aluno_fila").fetchone()[0] == 0
    assert conn.execute("SELECT nome, ativo, sessoes_por_ficha FROM treino").fetchone()[:] == ("TREINO ABC", 1, 15)
    assert conn.execute("SELECT COUNT(*) FROM ficha_item").fetchone()[0] == 1
    # o treino padrão que já existia fica solto (sem fila nem número)
    assert conn.execute("SELECT nome, fila_id, numero FROM modelo_treino").fetchone()[:] == ("BÁSICO", None, None)
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_copia_de_seguranca_da_versao_7_guarda_o_banco_como_era(caminho_v7):
    conn = conectar(caminho_v7)

    migrar(conn)
    conn.close()

    copias = list((caminho_v7.parent / PASTA_ANTES_DA_MIGRACAO).glob("app-*.db"))
    assert len(copias) == 1
    antiga = sqlite3.connect(copias[0])
    assert antiga.execute("PRAGMA user_version").fetchone()[0] == 7
    assert antiga.execute("SELECT COUNT(*) FROM sqlite_master WHERE name IN ('fila', 'aluno_fila')").fetchone()[0] == 0
    assert "fila_id" not in {c[1] for c in antiga.execute("PRAGMA table_info(modelo_treino)")}
    antiga.close()


def test_migracao_7_para_8_que_quebra_no_fim_nao_deixa_rastro(caminho_v7, monkeypatch):
    def quebra(conn):
        db._de_7_para_8(conn)
        raise RuntimeError("falha no fim")

    monkeypatch.setitem(db.MIGRACOES, 7, quebra)
    conn = conectar(caminho_v7)

    with pytest.raises(RuntimeError, match="falha no fim"):
        migrar(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
    assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name IN ('fila', 'aluno_fila')").fetchone()[0] == 0
    assert "fila_id" not in {c[1] for c in conn.execute("PRAGMA table_info(modelo_treino)")}
    assert not conn.in_transaction
    conn.close()


def test_banco_com_o_numero_baixado_a_mao_para_7_sobe_de_novo_sem_perder_as_filas(caminho_v7, monkeypatch):
    # Para abrir o banco com o app antigo (que ignora o que é novo) alguém pode baixar o número da versão.
    conn = conectar(caminho_v7)
    migrar(conn)
    conn.execute("UPDATE modelo_treino SET fila_id = 2, numero = 3 WHERE id = 1")
    conn.execute("INSERT INTO aluno_fila (aluno_id, fila_id, numero_atual, definida_por) VALUES (1, 2, 3, 'ANA')")
    conn.commit()
    conn.execute("PRAGMA user_version = 7")
    monkeypatch.setattr(db, "fazer_backup", lambda *_a, **_k: None)  # o nome da cópia leva só o segundo: aqui não importa

    assert migrar(conn) == [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]  # as tabelas e as colunas já existem: não pode falhar

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    assert conn.execute("SELECT fila_id, numero FROM modelo_treino").fetchone()[:] == (2, 3)
    assert conn.execute("SELECT fila_id, numero_atual FROM aluno_fila").fetchone()[:] == (2, 3)
    assert conn.execute("SELECT COUNT(*) FROM fila").fetchone()[0] == 5
    conn.close()


def test_numero_do_treino_so_vale_dentro_de_uma_fila_e_nao_repete(conn_nova):
    def inserir(nome, fila_id, numero):
        conn_nova.execute(
            "INSERT INTO modelo_treino (nome, montado_por, conteudo, fila_id, numero) VALUES (?, 'A', '{}', ?, ?)",
            (nome, fila_id, numero),
        )

    inserir("M1", 2, 1)
    inserir("H1", 1, 1)  # o mesmo número em outra fila vale
    inserir("SOLTO 1", None, None)
    inserir("SOLTO 2", None, None)  # vários sem fila valem
    with pytest.raises(sqlite3.IntegrityError):
        inserir("M1 DE NOVO", 2, 1)  # mesmo número na mesma fila
    for fila_id, numero in [(None, 3), (2, 0), (2, 100), (99, 1)]:  # número sem fila, fora de 1 a 99, fila que não existe
        with pytest.raises(sqlite3.IntegrityError):
            inserir(f"RUIM {fila_id} {numero}", fila_id, numero)


def test_aluno_fila_regras_do_banco(conn_nova):
    # a fixture já criou os alunos 1 e 2
    conn_nova.execute("INSERT INTO aluno_fila (aluno_id, fila_id, definida_por) VALUES (1, 4, 'PROF')")  # sem número: ainda não começou
    conn_nova.execute(
        "INSERT INTO aluno_fila (aluno_id, fila_id, numero_atual, definida_por, liberacao_em, liberacao_por)"
        " VALUES (2, 4, 99, 'PROF', '2026-10-13', 'PROF')"
    )
    with pytest.raises(sqlite3.IntegrityError):  # um aluno, uma fila
        conn_nova.execute("INSERT INTO aluno_fila (aluno_id, fila_id, definida_por) VALUES (1, 2, 'PROF')")
    for coluna, valor in [("numero_atual", 0), ("numero_atual", 100), ("definida_por", ""), ("liberacao_em", "13/10/2026"), ("liberacao_por", "")]:
        conn_nova.execute("DELETE FROM aluno_fila")
        campos = {"aluno_id": 1, "fila_id": 2, "definida_por": "PROF", coluna: valor}
        with pytest.raises(sqlite3.IntegrityError):
            conn_nova.execute(
                f"INSERT INTO aluno_fila ({', '.join(campos)}) VALUES ({', '.join('?' * len(campos))})", list(campos.values())
            )
    with pytest.raises(sqlite3.IntegrityError):  # fila que não existe (as chaves estrangeiras estão ligadas)
        conn_nova.execute("INSERT INTO aluno_fila (aluno_id, fila_id, definida_por) VALUES (1, 99, 'PROF')")


# ------------------------------------------------------------------ 8 -> 9: senha de administrador


def test_8_para_9_nao_perde_nada_e_nascem_as_tabelas_da_senha_vazias(caminho_v8):
    conn = conectar(caminho_v8)

    assert migrar(conn) == [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    assert conn.execute("SELECT COUNT(*) FROM senha_administrador").fetchone()[0] == 0  # sem senha: ações protegidas fechadas
    assert conn.execute("SELECT COUNT(*) FROM senha_administrador_falha").fetchone()[0] == 0
    assert conn.execute("SELECT nome, ativo, sessoes_por_ficha FROM treino").fetchone()[:] == ("TREINO ABC", 1, 15)
    assert conn.execute("SELECT nome, fila_id, numero FROM modelo_treino").fetchone()[:] == ("BÁSICO", 2, 1)
    assert conn.execute("SELECT fila_id, numero_atual FROM aluno_fila").fetchone()[:] == (2, 1)
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_copia_de_seguranca_da_versao_8_guarda_o_banco_como_era(caminho_v8):
    conn = conectar(caminho_v8)
    migrar(conn)
    conn.close()

    copias = sorted((caminho_v8.parent / PASTA_ANTES_DA_MIGRACAO).glob("*.db"))
    assert len(copias) == 1
    copia = sqlite3.connect(copias[0])
    assert copia.execute("PRAGMA user_version").fetchone()[0] == 8
    assert copia.execute("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'senha_administrador%'").fetchone()[0] == 0
    assert copia.execute("SELECT nome FROM modelo_treino").fetchone()[0] == "BÁSICO"
    copia.close()


def test_migracao_8_para_9_que_quebra_no_fim_nao_deixa_rastro(caminho_v8, monkeypatch):
    def quebra(conn):
        db._de_8_para_9(conn)
        raise RuntimeError("falha no fim")

    monkeypatch.setitem(db.MIGRACOES, 8, quebra)
    conn = conectar(caminho_v8)

    with pytest.raises(RuntimeError, match="falha no fim"):
        migrar(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 8
    assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'senha_administrador%'").fetchone()[0] == 0
    assert not conn.in_transaction
    conn.close()


def test_banco_com_o_numero_baixado_a_mao_para_8_sobe_de_novo_e_a_senha_continua_valendo(caminho_v8, monkeypatch):
    # Para abrir o banco com o app antigo (que ignora o que é novo) alguém pode baixar o número da versão.
    from app import administrador

    conn = conectar(caminho_v8)
    migrar(conn)
    administrador.definir_senha(conn, "senha-de-teste-1")
    conn.execute("PRAGMA user_version = 8")
    monkeypatch.setattr(db, "fazer_backup", lambda *_a, **_k: None)

    assert migrar(conn) == [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]  # as tabelas já existem: não pode falhar

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    administrador.conferir_senha(conn, "senha-de-teste-1")  # a senha que já estava lá continua valendo
    conn.close()


def test_9_para_10_nao_perde_nada_e_nasce_a_tabela_dos_pedidos_de_ia_vazia(caminho_v9):
    conn = conectar(caminho_v9)

    assert migrar(conn) == [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    assert conn.execute("SELECT COUNT(*) FROM ia_pedido").fetchone()[0] == 0
    assert conn.execute("SELECT nome, ativo, sessoes_por_ficha FROM treino").fetchone()[:] == ("TREINO ABC", 1, 15)
    assert conn.execute("SELECT nome, fila_id, numero FROM modelo_treino").fetchone()[:] == ("BÁSICO", 2, 1)
    assert conn.execute("SELECT senha_hash FROM senha_administrador").fetchone()[0] == "scrypt$x"  # a senha continua lá
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_copia_de_seguranca_da_versao_9_guarda_o_banco_como_era(caminho_v9):
    conn = conectar(caminho_v9)
    migrar(conn)
    conn.close()

    copias = sorted((caminho_v9.parent / PASTA_ANTES_DA_MIGRACAO).glob("*.db"))
    assert len(copias) == 1
    copia = sqlite3.connect(copias[0])
    assert copia.execute("PRAGMA user_version").fetchone()[0] == 9
    assert copia.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'ia_pedido'").fetchone()[0] == 0
    assert copia.execute("SELECT nome FROM modelo_treino").fetchone()[0] == "BÁSICO"
    copia.close()


def test_migracao_9_para_10_que_quebra_no_fim_nao_deixa_rastro(caminho_v9, monkeypatch):
    def quebra(conn):
        db._de_9_para_10(conn)
        raise RuntimeError("falha no fim")

    monkeypatch.setitem(db.MIGRACOES, 9, quebra)
    conn = conectar(caminho_v9)

    with pytest.raises(RuntimeError, match="falha no fim"):
        migrar(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 9
    assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'ia_pedido'").fetchone()[0] == 0
    assert not conn.in_transaction
    conn.close()


def test_banco_com_o_numero_baixado_a_mao_para_9_sobe_de_novo_e_os_pedidos_continuam_la(caminho_v9, monkeypatch):
    # Para abrir o banco com o app antigo (que ignora o que é novo) alguém pode baixar o número da versão.
    conn = conectar(caminho_v9)
    migrar(conn)
    conn.execute(
        "INSERT INTO ia_pedido (aluno_id, criado_em, dia, situacao, modelo) VALUES (1, '2026-10-13 22:00:00', '2026-10-13', 'pronto', 'm')"
    )
    conn.commit()
    conn.execute("PRAGMA user_version = 9")
    monkeypatch.setattr(db, "fazer_backup", lambda *_a, **_k: None)

    assert migrar(conn) == [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]  # a tabela já existe: não pode falhar

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    assert conn.execute("SELECT COUNT(*) FROM ia_pedido").fetchone()[0] == 1  # o pedido que já estava lá continua
    conn.close()


def test_pedido_de_ia_confere_dia_situacao_e_tokens(conn_nova):
    base = "INSERT INTO ia_pedido (aluno_id, criado_em, dia, situacao, modelo, tokens_entrada) VALUES (1, 'x', ?, ?, 'm', ?)"
    conn_nova.execute(base, ("2026-10-13", "andando", None))
    for dia, situacao, tokens in [("13/10/2026", "andando", None), ("2026-10-13", "cancelado", None), ("2026-10-13", "pronto", -1)]:
        with pytest.raises(sqlite3.IntegrityError):
            conn_nova.execute(base, (dia, situacao, tokens))


def test_10_para_11_nao_perde_nada_e_nasce_a_tabela_do_registro_vazia(caminho_v10):
    conn = conectar(caminho_v10)

    assert migrar(conn) == [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    assert conn.execute("SELECT COUNT(*) FROM importacao").fetchone()[0] == 0
    assert conn.execute("SELECT nome, ativo, sessoes_por_ficha FROM treino").fetchone()[:] == ("TREINO ABC", 1, 15)
    assert conn.execute("SELECT nome, fila_id, numero FROM modelo_treino").fetchone()[:] == ("BÁSICO", 2, 1)
    assert conn.execute("SELECT senha_hash FROM senha_administrador").fetchone()[0] == "scrypt$x"
    assert conn.execute("SELECT situacao FROM ia_pedido").fetchone()[0] == "pronto"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_copia_de_seguranca_da_versao_10_guarda_o_banco_como_era(caminho_v10):
    conn = conectar(caminho_v10)
    migrar(conn)
    conn.close()

    copias = sorted((caminho_v10.parent / PASTA_ANTES_DA_MIGRACAO).glob("*.db"))
    assert len(copias) == 1
    copia = sqlite3.connect(copias[0])
    assert copia.execute("PRAGMA user_version").fetchone()[0] == 10
    assert copia.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'importacao'").fetchone()[0] == 0
    assert copia.execute("SELECT nome FROM modelo_treino").fetchone()[0] == "BÁSICO"
    copia.close()


def test_migracao_10_para_11_que_quebra_no_fim_nao_deixa_rastro(caminho_v10, monkeypatch):
    def quebra(conn):
        db._de_10_para_11(conn)
        raise RuntimeError("falha no fim")

    monkeypatch.setitem(db.MIGRACOES, 10, quebra)
    conn = conectar(caminho_v10)

    with pytest.raises(RuntimeError, match="falha no fim"):
        migrar(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 10
    assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'importacao'").fetchone()[0] == 0
    assert not conn.in_transaction
    conn.close()


def test_banco_com_o_numero_baixado_a_mao_para_10_sobe_de_novo_e_o_registro_continua_la(caminho_v10, monkeypatch):
    # Para abrir o banco com o app antigo (que ignora o que é novo) alguém pode baixar o número da versão.
    conn = conectar(caminho_v10)
    migrar(conn)
    conn.execute(
        "INSERT INTO importacao (tipo, extraido_em, recebida_em) VALUES ('alunos', '2026-10-14 08:00:17', '2026-10-14 08:15:02')"
    )
    conn.commit()
    conn.execute("PRAGMA user_version = 10")
    monkeypatch.setattr(db, "fazer_backup", lambda *_a, **_k: None)

    assert migrar(conn) == [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]  # a tabela já existe: não pode falhar

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    assert conn.execute("SELECT extraido_em FROM importacao WHERE tipo = 'alunos'").fetchone()[0] == "2026-10-14 08:00:17"
    conn.close()


def test_registro_da_importacao_confere_tipo_e_formato_da_data(conn_nova):
    base = "INSERT INTO importacao (tipo, extraido_em, recebida_em) VALUES (?, ?, ?)"
    conn_nova.execute(base, ("alunos", "2026-10-14 08:00:17", "2026-10-14 08:15:02"))
    for tipo, extraido, recebida in [
        ("professores", "2026-10-14 08:00:17", "2026-10-14 08:15:02"),
        ("treinos", "14/10/2026 05:00:17", "2026-10-14 08:15:02"),
        ("treinos", "2026-10-14 08:00:17", "ontem"),
        ("alunos", "2026-10-14 08:00:17", "2026-10-14 08:15:02"),  # um só registro por assunto
    ]:
        with pytest.raises(sqlite3.IntegrityError):
            conn_nova.execute(base, (tipo, extraido, recebida))


def test_11_para_12_nao_perde_nada_e_nascem_as_tabelas_do_login_do_aluno_vazias(caminho_v11):
    conn = conectar(caminho_v11)

    assert migrar(conn) == [11, 12, 13, 14, 15, 16, 17, 18, 19, 20]

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    for tabela in ("aluno_senha", "aluno_codigo", "aluno_sessao", "aluno_evento"):
        assert conn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0] == 0, tabela
    assert conn.execute("SELECT nome, cpf, whatsapp, situacao FROM aluno").fetchone()[:] == (
        "MARIANA COSTA", "11144477735", "27988887766", "A",
    )
    assert conn.execute("SELECT nome FROM treino").fetchone()[0] == "TREINO ABC"
    assert conn.execute("SELECT senha_hash FROM senha_administrador").fetchone()[0] == "scrypt$x"
    assert conn.execute("SELECT extraido_em FROM importacao WHERE tipo = 'alunos'").fetchone()[0] == "2026-10-14 08:00:17"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_copia_de_seguranca_da_versao_11_guarda_o_banco_como_era(caminho_v11):
    conn = conectar(caminho_v11)
    migrar(conn)
    conn.close()

    copias = sorted((caminho_v11.parent / PASTA_ANTES_DA_MIGRACAO).glob("*.db"))
    assert len(copias) == 1
    copia = sqlite3.connect(copias[0])
    assert copia.execute("PRAGMA user_version").fetchone()[0] == 11
    assert copia.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'aluno_senha'").fetchone()[0] == 0
    assert copia.execute("SELECT nome FROM aluno").fetchone()[0] == "MARIANA COSTA"
    copia.close()


def test_migracao_11_para_12_que_quebra_no_fim_nao_deixa_rastro(caminho_v11, monkeypatch):
    def quebra(conn):
        db._de_11_para_12(conn)
        raise RuntimeError("falha no fim")

    monkeypatch.setitem(db.MIGRACOES, 11, quebra)
    conn = conectar(caminho_v11)

    with pytest.raises(RuntimeError, match="falha no fim"):
        migrar(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 11
    for tabela in ("aluno_senha", "aluno_codigo", "aluno_sessao", "aluno_evento"):
        assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = ?", (tabela,)).fetchone()[0] == 0, tabela
    assert not conn.in_transaction
    conn.close()


def test_banco_com_o_numero_baixado_a_mao_para_11_sobe_de_novo_e_a_senha_do_aluno_continua_valendo(caminho_v11, monkeypatch):
    # Para abrir o banco com o app antigo (que ignora o que é novo) alguém pode baixar o número da versão.
    conn = conectar(caminho_v11)
    migrar(conn)
    conn.execute("INSERT INTO aluno_senha (aluno_id, senha_hash, definida_em) VALUES (1, 'scrypt$y', '2026-10-15 12:00:00')")
    conn.commit()
    conn.execute("PRAGMA user_version = 11")
    monkeypatch.setattr(db, "fazer_backup", lambda *_a, **_k: None)

    assert migrar(conn) == [11, 12, 13, 14, 15, 16, 17, 18, 19, 20]  # as tabelas já existem: não pode falhar

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    assert conn.execute("SELECT senha_hash FROM aluno_senha WHERE aluno_id = 1").fetchone()[0] == "scrypt$y"
    conn.close()


def test_login_do_aluno_regras_do_banco(conn_nova):
    conn_nova.execute("INSERT INTO aluno_senha (aluno_id, senha_hash, definida_em) VALUES (1, 'scrypt$x', '2026-10-15 12:00:00')")
    with pytest.raises(sqlite3.IntegrityError):  # uma senha por aluno
        conn_nova.execute("INSERT INTO aluno_senha (aluno_id, senha_hash, definida_em) VALUES (1, 'scrypt$z', '2026-10-15 12:00:00')")
    with pytest.raises(sqlite3.IntegrityError):  # aluno que não existe
        conn_nova.execute("INSERT INTO aluno_senha (aluno_id, senha_hash, definida_em) VALUES (999, 'scrypt$x', '2026-10-15 12:00:00')")

    codigo = "INSERT INTO aluno_codigo (aluno_id, codigo_hash, criado_em, expira_em, {}) VALUES (1, 'h', 'a', 'b', {})"
    conn_nova.execute(codigo.format("envio", "'enviado'"))
    for colunas, valores in [("envio", "'quase'"), ("tentativas", "-1"), ("envio_erro", "'" + "x" * 301 + "'")]:
        with pytest.raises(sqlite3.IntegrityError):
            conn_nova.execute(codigo.format(colunas, valores))

    evento = "INSERT INTO aluno_evento (tipo, chave, em) VALUES (?, 'cpf:x', '2026-10-15 12:00:00')"
    conn_nova.execute(evento, ("login_errado",))
    with pytest.raises(sqlite3.IntegrityError):
        conn_nova.execute(evento, ("outro_tipo",))

    sessao = "INSERT INTO aluno_sessao (aluno_id, token_hash, criado_em, ultimo_uso_em) VALUES (1, ?, 'a', 'a')"
    conn_nova.execute(sessao, ("t1",))
    with pytest.raises(sqlite3.IntegrityError):  # o mesmo cookie não pode valer para duas sessões
        conn_nova.execute(sessao, ("t1",))


def test_12_para_13_nao_perde_nada_e_nasce_a_tabela_dos_comentarios_vazia(caminho_v12):
    conn = conectar(caminho_v12)

    assert migrar(conn) == [12, 13, 14, 15, 16, 17, 18, 19, 20]

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    assert conn.execute("SELECT COUNT(*) FROM comentario").fetchone()[0] == 0
    assert conn.execute("SELECT nome, cpf, whatsapp, situacao FROM aluno").fetchone()[:] == (
        "MARIANA COSTA", "11144477735", "27988887766", "A",
    )
    assert conn.execute("SELECT nome FROM treino").fetchone()[0] == "TREINO ABC"
    assert conn.execute("SELECT nome FROM ficha").fetchone()[0] == "A PEITO"
    assert conn.execute("SELECT senha_hash FROM aluno_senha WHERE aluno_id = 1").fetchone()[0] == "scrypt$x"
    assert conn.execute("SELECT COUNT(*) FROM sessao").fetchone()[0] == 1
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_copia_de_seguranca_da_versao_12_guarda_o_banco_como_era(caminho_v12):
    conn = conectar(caminho_v12)
    migrar(conn)
    conn.close()

    copias = sorted((caminho_v12.parent / PASTA_ANTES_DA_MIGRACAO).glob("*.db"))
    assert len(copias) == 1
    copia = sqlite3.connect(copias[0])
    assert copia.execute("PRAGMA user_version").fetchone()[0] == 12
    assert copia.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'comentario'").fetchone()[0] == 0
    assert copia.execute("SELECT nome FROM aluno").fetchone()[0] == "MARIANA COSTA"
    copia.close()


def test_migracao_12_para_13_que_quebra_no_fim_nao_deixa_rastro(caminho_v12, monkeypatch):
    def quebra(conn):
        db._de_12_para_13(conn)
        raise RuntimeError("falha no fim")

    monkeypatch.setitem(db.MIGRACOES, 12, quebra)
    conn = conectar(caminho_v12)

    with pytest.raises(RuntimeError, match="falha no fim"):
        migrar(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 12
    assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'comentario'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'ix_comentario%'").fetchone()[0] == 0
    assert not conn.in_transaction
    conn.close()


def test_banco_com_o_numero_baixado_a_mao_para_12_sobe_de_novo_e_os_comentarios_continuam_la(caminho_v12, monkeypatch):
    # Para abrir o banco com o app antigo (que ignora o que é novo) alguém pode baixar o número da versão.
    conn = conectar(caminho_v12)
    migrar(conn)
    conn.execute(
        "INSERT INTO comentario (aluno_id, treino_id, treino_nome, texto, criado_em)"
        " VALUES (1, 1, 'TREINO ABC', 'Está leve demais', '2026-10-15 21:00:00')"
    )
    conn.commit()
    conn.execute("PRAGMA user_version = 12")
    monkeypatch.setattr(db, "fazer_backup", lambda *_a, **_k: None)

    assert migrar(conn) == [12, 13, 14, 15, 16, 17, 18, 19, 20]  # a tabela já existe: não pode falhar

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    assert conn.execute("SELECT texto FROM comentario").fetchone()[0] == "Está leve demais"
    conn.close()


def test_comentario_regras_do_banco(conn_nova):
    base = (
        "INSERT INTO comentario (aluno_id, treino_id, treino_nome, ficha_ordem, ficha_nome, exercicio_nome, texto, criado_em)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, '2026-10-15 21:00:00')"
    )
    conn_nova.execute("INSERT INTO treino (id, aluno_id, nome, montado_por) VALUES (1, 1, 'TREINO ABC', 'ANA')")
    conn_nova.execute(base, (1, 1, "TREINO ABC", None, None, None, "Do treino todo"))  # treino inteiro
    conn_nova.execute(base, (1, 1, "TREINO ABC", 1, "A PEITO", "SUPINO RETO", "Do exercício"))  # um exercício
    conn_nova.execute(base, (1, None, "TREINO ABC", None, None, None, "Treino já apagado"))  # treino_id pode ficar vazio

    recusados = [
        (999, 1, "TREINO ABC", None, None, None, "aluno que não existe"),
        (1, 999, "TREINO ABC", None, None, None, "treino que não existe"),
        (1, 1, "", None, None, None, "nome do treino vazio"),
        (1, 1, "T" * 41, None, None, None, "nome do treino comprido demais"),
        (1, 1, "TREINO ABC", None, None, None, ""),  # texto vazio
        (1, 1, "TREINO ABC", None, None, None, "x" * 501),  # texto comprido demais
        (1, 1, "TREINO ABC", 1, "A PEITO", None, "ficha sem exercício"),  # os três vêm juntos ou nenhum
        (1, 1, "TREINO ABC", None, None, "SUPINO RETO", "exercício sem ficha"),
        (1, 1, "TREINO ABC", 0, "A PEITO", "SUPINO RETO", "ficha número 0"),
        (1, 1, "TREINO ABC", 1, "F" * 16, "SUPINO RETO", "nome da ficha comprido demais"),
    ]
    for valores in recusados:
        with pytest.raises(sqlite3.IntegrityError):
            conn_nova.execute(base, valores)

    # 500 letras passam
    conn_nova.execute(base, (1, 1, "TREINO ABC", None, None, None, "x" * 500))

    # resposta: os três campos vêm juntos ou nenhum
    with pytest.raises(sqlite3.IntegrityError):
        conn_nova.execute("UPDATE comentario SET resposta = 'Vamos aumentar a carga' WHERE id = 1")
    conn_nova.execute(
        "UPDATE comentario SET resposta = 'Vamos aumentar a carga', respondido_por = 'ANA', respondido_em = '2026-10-16 10:00:00' WHERE id = 1"
    )

    # apagar o treino NÃO apaga o comentário: ele só perde o vínculo
    conn_nova.execute("DELETE FROM treino WHERE id = 1")
    assert conn_nova.execute("SELECT COUNT(*) FROM comentario").fetchone()[0] == 4
    assert conn_nova.execute("SELECT COUNT(*) FROM comentario WHERE treino_id IS NULL").fetchone()[0] == 4

    # apagar um aluno que tem comentário é recusado (não se perde o histórico sem querer)
    with pytest.raises(sqlite3.IntegrityError):
        conn_nova.execute("DELETE FROM aluno WHERE id = 1")


# ------------------------------------------------------------------ 13 -> 14 (esforço ao concluir, exercício feito e carga)


def test_13_para_14_nao_perde_nada_e_nascem_a_coluna_do_esforco_e_a_tabela_das_cargas_vazias(caminho_v13):
    conn = conectar(caminho_v13)

    assert migrar(conn) == [13, 14, 15, 16, 17, 18, 19, 20]

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    assert conn.execute("SELECT COUNT(*) FROM execucao").fetchone()[0] == 0
    # a sessão que já existia continua, agora com o esforço vazio
    assert conn.execute("SELECT ficha_ordem, feita_em, esforco FROM sessao").fetchone()[:] == (1, "2026-10-15 20:00:00", None)
    assert conn.execute("SELECT texto FROM comentario").fetchone()[0] == "Está leve demais"
    assert conn.execute("SELECT nome FROM treino").fetchone()[0] == "TREINO ABC"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_copia_de_seguranca_da_versao_13_guarda_o_banco_como_era(caminho_v13):
    conn = conectar(caminho_v13)
    migrar(conn)
    conn.close()

    copias = sorted((caminho_v13.parent / PASTA_ANTES_DA_MIGRACAO).glob("*.db"))
    assert len(copias) == 1
    copia = sqlite3.connect(copias[0])
    assert copia.execute("PRAGMA user_version").fetchone()[0] == 13
    assert copia.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'execucao'").fetchone()[0] == 0
    assert "esforco" not in [linha[1] for linha in copia.execute("PRAGMA table_info(sessao)")]
    assert copia.execute("SELECT nome FROM aluno").fetchone()[0] == "MARIANA COSTA"
    copia.close()


def test_migracao_13_para_14_que_quebra_no_fim_nao_deixa_rastro(caminho_v13, monkeypatch):
    def quebra(conn):
        db._de_13_para_14(conn)
        raise RuntimeError("falha no fim")

    monkeypatch.setitem(db.MIGRACOES, 13, quebra)
    conn = conectar(caminho_v13)

    with pytest.raises(RuntimeError, match="falha no fim"):
        migrar(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 13
    assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'execucao'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'ix_execucao%'").fetchone()[0] == 0
    assert "esforco" not in [linha[1] for linha in conn.execute("PRAGMA table_info(sessao)")]
    assert not conn.in_transaction
    conn.close()


def test_banco_com_o_numero_baixado_a_mao_para_13_sobe_de_novo_e_o_que_o_aluno_anotou_continua_la(caminho_v13, monkeypatch):
    # Para abrir o banco com o app antigo (que ignora o que é novo) alguém pode baixar o número da versão.
    conn = conectar(caminho_v13)
    migrar(conn)
    conn.execute("UPDATE sessao SET esforco = 3")
    conn.execute(
        "INSERT INTO execucao (aluno_id, dia, ficha_ordem, exercicio_ordem, exercicio_nome, feito, carga, atualizado_em)"
        " VALUES (1, '2026-10-15', 1, 1, 'SUPINO RETO', 1, '20', '2026-10-15 20:00:00')"
    )
    conn.commit()
    conn.execute("PRAGMA user_version = 13")
    monkeypatch.setattr(db, "fazer_backup", lambda *_a, **_k: None)

    assert migrar(conn) == [13, 14, 15, 16, 17, 18, 19, 20]  # a coluna e a tabela já existem: não pode falhar

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    assert conn.execute("SELECT esforco FROM sessao").fetchone()[0] == 3
    assert conn.execute("SELECT carga FROM execucao").fetchone()[0] == "20"
    conn.close()


def test_esforco_da_sessao_so_aceita_de_1_a_3_ou_vazio(conn_nova):
    conn_nova.execute("INSERT INTO treino (id, aluno_id, nome, montado_por) VALUES (1, 1, 'TREINO ABC', 'ANA')")
    nova = "INSERT INTO sessao (treino_id, ficha_ordem, feita_em, esforco) VALUES (1, 1, '2026-10-15 20:00:00', ?)"
    for valor in (None, 1, 2, 3):
        conn_nova.execute(nova, (valor,))
    for valor in (0, 4, -1):
        with pytest.raises(sqlite3.IntegrityError):
            conn_nova.execute(nova, (valor,))


def test_execucao_regras_do_banco(conn_nova):
    base = (
        "INSERT INTO execucao (aluno_id, dia, ficha_ordem, exercicio_ordem, exercicio_nome, feito, carga, atualizado_em)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, '2026-10-15 20:00:00')"
    )
    conn_nova.execute(base, (1, "2026-10-15", 1, 1, "SUPINO RETO", 1, None))  # só feito
    conn_nova.execute(base, (1, "2026-10-15", 1, 2, "CRUCIFIXO", 0, "12,5"))  # só carga
    conn_nova.execute(base, (1, "2026-10-15", 1, 3, "ROSCA DIRETA", 1, "20"))  # os dois

    recusados = [
        (999, "2026-10-15", 1, 4, "X", 1, None),  # aluno que não existe
        (1, "15/10/2026", 1, 4, "X", 1, None),  # dia fora do formato
        (1, "2026-10-15", 0, 4, "X", 1, None),  # ficha 0
        (1, "2026-10-15", 1, 0, "X", 1, None),  # exercício 0
        (1, "2026-10-15", 1, 4, "", 1, None),  # nome vazio
        (1, "2026-10-15", 1, 4, "X", 2, None),  # feito só vale 0 ou 1
        (1, "2026-10-15", 1, 4, "X", 0, None),  # linha sem nada marcado não existe
        (1, "2026-10-15", 1, 4, "X", 1, ""),  # carga vazia é NULL, não texto vazio
        (1, "2026-10-15", 1, 4, "X", 1, "1234567890"),  # carga comprida demais
        (1, "2026-10-15", 1, 1, "SUPINO RETO", 1, None),  # a mesma linha do dia não se repete
    ]
    for valores in recusados:
        with pytest.raises(sqlite3.IntegrityError):
            conn_nova.execute(base, valores)

    # outro dia, ou outro aluno, pode repetir o mesmo exercício
    conn_nova.execute(base, (1, "2026-10-16", 1, 1, "SUPINO RETO", 1, None))

    # o mesmo nome pode aparecer de novo na mesma ficha (2ª ocorrência), em outra posição; ocorrência 0 não existe
    com_ocorrencia = (
        "INSERT INTO execucao (aluno_id, dia, ficha_ordem, exercicio_ordem, exercicio_nome, ocorrencia, feito, carga, atualizado_em)"
        " VALUES (1, '2026-10-15', 1, ?, 'SUPINO RETO', ?, 1, NULL, '2026-10-15 20:00:00')"
    )
    conn_nova.execute(com_ocorrencia, (5, 2))
    for posicao, ocorrencia in ((6, 2), (6, 0)):
        with pytest.raises(sqlite3.IntegrityError):
            conn_nova.execute(com_ocorrencia, (posicao, ocorrencia))

    # apagar um aluno que tem anotação é recusado (não se perde o que ele registrou sem querer)
    with pytest.raises(sqlite3.IntegrityError):
        conn_nova.execute("DELETE FROM aluno WHERE id = 1")


# ------------------------------------------------------------------ 14 -> 15 (o robô aprende com os professores)


def test_14_para_15_nao_perde_nada_e_nasce_a_tabela_do_retorno_vazia(caminho_v14):
    conn = conectar(caminho_v14)

    assert migrar(conn) == [14, 15, 16, 17, 18, 19, 20]

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    assert conn.execute("SELECT COUNT(*) FROM ia_retorno").fetchone()[0] == 0
    assert conn.execute("SELECT nome FROM treino").fetchone()[0] == "TREINO ABC"
    assert conn.execute("SELECT carga FROM execucao").fetchone()[0] == "20"
    assert conn.execute("SELECT esforco FROM sessao").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM ia_pedido").fetchone()[0] == 1
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_copia_de_seguranca_da_versao_14_guarda_o_banco_como_era(caminho_v14):
    conn = conectar(caminho_v14)
    migrar(conn)
    conn.close()

    copias = sorted((caminho_v14.parent / PASTA_ANTES_DA_MIGRACAO).glob("*.db"))
    assert len(copias) == 1
    copia = sqlite3.connect(copias[0])
    assert copia.execute("PRAGMA user_version").fetchone()[0] == 14
    assert copia.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'ia_retorno'").fetchone()[0] == 0
    assert copia.execute("SELECT nome FROM aluno").fetchone()[0] == "MARIANA COSTA"
    copia.close()


def test_migracao_14_para_15_que_quebra_no_fim_nao_deixa_rastro(caminho_v14, monkeypatch):
    def quebra(conn):
        db._de_14_para_15(conn)
        raise RuntimeError("falha no fim")

    monkeypatch.setitem(db.MIGRACOES, 14, quebra)
    conn = conectar(caminho_v14)

    with pytest.raises(RuntimeError, match="falha no fim"):
        migrar(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 14
    assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'ia_retorno'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'ix_ia_retorno%'").fetchone()[0] == 0
    assert not conn.in_transaction
    conn.close()


def test_banco_com_o_numero_baixado_a_mao_para_14_sobe_de_novo_e_o_retorno_continua_la(caminho_v14, monkeypatch):
    # Para abrir o banco com o app antigo (que ignora o que é novo) alguém pode baixar o número da versão.
    conn = conectar(caminho_v14)
    migrar(conn)
    conn.execute(
        "INSERT INTO ia_retorno (dia, tipo, objetivo, nivel, dias, minutos, com_observacoes, rodadas, regras, modelo, nota)"
        " VALUES ('2026-10-23', 'avaliacao', 'hipertrofia', 'iniciante', 3, 60, 0, 0, 'abc123', 'claude-sonnet-5-5', 'serviu')"
    )
    conn.commit()
    conn.execute("PRAGMA user_version = 14")
    monkeypatch.setattr(db, "fazer_backup", lambda *_a, **_k: None)

    assert migrar(conn) == [14, 15, 16, 17, 18, 19, 20]  # a tabela já existe: não pode falhar

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    assert conn.execute("SELECT nota FROM ia_retorno").fetchone()[0] == "serviu"
    conn.close()


_RETORNO_BASE = {
    "dia": "2026-10-23",
    "tipo": "avaliacao",
    "objetivo": "hipertrofia",
    "nivel": "iniciante",
    "dias": 3,
    "minutos": 60,
    "fila": None,
    "com_observacoes": 0,
    "rodadas": 0,
    "regras": "abc123",
    "modelo": "claude-sonnet-5-5",
    "nota": "serviu",
    "motivo": None,
    "mudancas": None,
}


def _inserir_retorno(conn, **mudar):
    dados = {**_RETORNO_BASE, **mudar}
    colunas = ", ".join(dados)
    conn.execute(f"INSERT INTO ia_retorno ({colunas}) VALUES ({', '.join('?' for _ in dados)})", list(dados.values()))


def test_ia_retorno_regras_do_banco(conn_nova):
    _inserir_retorno(conn_nova)  # avaliação simples
    _inserir_retorno(conn_nova, nota="com_ajustes", motivo="Faltou posterior de coxa", fila="Mulher", com_observacoes=1, rodadas=2)
    _inserir_retorno(conn_nova, tipo="correcao", nota=None, mudancas="{}")  # correção sem nota (o professor não avaliou)
    _inserir_retorno(conn_nova, tipo="correcao", nota="nao_serviu", mudancas="{}")

    recusados = [
        {"dia": "23/10/2026"},  # dia fora do formato
        {"tipo": "outra"},  # tipo que não existe
        {"nota": "otimo"},  # nota que não existe
        {"nota": None},  # avaliação sem nota
        {"tipo": "correcao", "mudancas": None},  # correção sem as mudanças
        {"objetivo": ""},
        {"nivel": ""},
        {"dias": 0},
        {"minutos": 0},
        {"fila": ""},
        {"com_observacoes": 2},
        {"rodadas": 10},
        {"regras": ""},
        {"modelo": ""},
        {"motivo": "x" * 301},
    ]
    for mudar in recusados:
        with pytest.raises(sqlite3.IntegrityError):
            _inserir_retorno(conn_nova, **mudar)

    assert conn_nova.execute("SELECT COUNT(*) FROM ia_retorno").fetchone()[0] == 4


def test_ia_retorno_nao_tem_como_chegar_ao_aluno_nem_ao_professor(conn_nova):
    # A promessa feita ao Thiago: nada nesta tabela diz de quem foi o treino. Se alguém acrescentar uma coluna, este teste chama a atenção.
    colunas = set(_colunas(conn_nova, "ia_retorno"))
    assert colunas == {
        "id", "dia", "tipo", "objetivo", "nivel", "dias", "minutos", "fila", "com_observacoes", "rodadas", "regras", "modelo",
        "nota", "motivo", "mudancas",
    }
    assert conn_nova.execute("SELECT COUNT(*) FROM pragma_foreign_key_list('ia_retorno')").fetchone()[0] == 0


# ------------------------------------------------------------------ 15 -> 16 (histórico do treino feito com a IA)


def test_15_para_16_nao_perde_nada_e_nasce_a_tabela_do_historico_vazia(caminho_v15):
    conn = conectar(caminho_v15)

    assert migrar(conn) == [15, 16, 17, 18, 19, 20]

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    assert conn.execute("SELECT COUNT(*) FROM treino_ia").fetchone()[0] == 0
    assert conn.execute("SELECT nome FROM treino").fetchone()[0] == "TREINO ABC"
    assert conn.execute("SELECT nota FROM ia_retorno").fetchone()[0] == "serviu"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_copia_de_seguranca_da_versao_15_guarda_o_banco_como_era(caminho_v15):
    conn = conectar(caminho_v15)
    migrar(conn)
    conn.close()

    copias = sorted((caminho_v15.parent / PASTA_ANTES_DA_MIGRACAO).glob("*.db"))
    assert len(copias) == 1
    copia = sqlite3.connect(copias[0])
    assert copia.execute("PRAGMA user_version").fetchone()[0] == 15
    assert copia.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'treino_ia'").fetchone()[0] == 0
    assert copia.execute("SELECT nome FROM aluno").fetchone()[0] == "MARIANA COSTA"
    copia.close()


def test_migracao_15_para_16_que_quebra_no_fim_nao_deixa_rastro(caminho_v15, monkeypatch):
    def quebra(conn):
        db._de_15_para_16(conn)
        raise RuntimeError("falha no fim")

    monkeypatch.setitem(db.MIGRACOES, 15, quebra)
    conn = conectar(caminho_v15)

    with pytest.raises(RuntimeError, match="falha no fim"):
        migrar(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 15
    assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'treino_ia'").fetchone()[0] == 0
    assert not conn.in_transaction
    conn.close()


def test_banco_com_o_numero_baixado_a_mao_para_15_sobe_de_novo_e_o_historico_continua_la(caminho_v15, monkeypatch):
    # Para abrir o banco com o app antigo (que ignora o que é novo) alguém pode baixar o número da versão.
    conn = conectar(caminho_v15)
    migrar(conn)
    conn.execute(
        "INSERT INTO treino_ia (treino_id, objetivo, nivel, dias, minutos, observacoes, justificativa, alertas, ajustes, regras, modelo)"
        " VALUES (1, 'hipertrofia', 'iniciante', 3, 60, 'dor no joelho', '[\"ponto\"]', '[]', '{}', 'abc123', 'claude-sonnet-5-5')"
    )
    conn.commit()
    conn.execute("PRAGMA user_version = 15")
    monkeypatch.setattr(db, "fazer_backup", lambda *_a, **_k: None)

    assert migrar(conn) == [15, 16, 17, 18, 19, 20]  # a tabela já existe: não pode falhar

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    assert conn.execute("SELECT observacoes FROM treino_ia").fetchone()[0] == "dor no joelho"
    conn.close()


def test_o_historico_some_junto_com_o_treino(caminho_v15):
    conn = conectar(caminho_v15)
    migrar(conn)
    conn.execute(
        "INSERT INTO treino_ia (treino_id, objetivo, nivel, dias, minutos, justificativa, alertas, ajustes, regras, modelo)"
        " VALUES (1, 'hipertrofia', 'iniciante', 3, 60, '[]', '[]', '{}', 'abc123', 'm')"
    )
    conn.commit()

    conn.execute("DELETE FROM treino WHERE id = 1")
    conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM treino_ia").fetchone()[0] == 0
    conn.close()


# ------------------------------------------------------------------ 16 -> 17 (fichas diferentes dos dias)


def test_16_para_17_nao_perde_nada_e_nasce_a_coluna_vazia(caminho_v16):
    conn = conectar(caminho_v16)

    assert migrar(conn) == [16, 17, 18, 19, 20]

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    linha = conn.execute("SELECT observacoes, justificativa, fichas_pedidas FROM treino_ia").fetchone()
    assert linha["observacoes"] == "dor no joelho" and linha["justificativa"] == '["ponto"]'
    assert linha["fichas_pedidas"] is None  # treino de antes: o número de fichas era sempre igual aos dias
    assert conn.execute("SELECT nome FROM treino").fetchone()[0] == "TREINO ABC"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_copia_de_seguranca_da_versao_16_guarda_o_banco_como_era(caminho_v16):
    conn = conectar(caminho_v16)
    migrar(conn)
    conn.close()

    copias = sorted((caminho_v16.parent / PASTA_ANTES_DA_MIGRACAO).glob("*.db"))
    assert len(copias) == 1
    copia = sqlite3.connect(copias[0])
    assert copia.execute("PRAGMA user_version").fetchone()[0] == 16
    assert "fichas_pedidas" not in {linha[1] for linha in copia.execute("PRAGMA table_info(treino_ia)")}
    assert copia.execute("SELECT observacoes FROM treino_ia").fetchone()[0] == "dor no joelho"
    copia.close()


def test_migracao_16_para_17_que_quebra_no_fim_nao_deixa_rastro(caminho_v16, monkeypatch):
    def quebra(conn):
        db._de_16_para_17(conn)
        raise RuntimeError("falha no fim")

    monkeypatch.setitem(db.MIGRACOES, 16, quebra)
    conn = conectar(caminho_v16)

    with pytest.raises(RuntimeError, match="falha no fim"):
        migrar(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 16
    assert "fichas_pedidas" not in {linha[1] for linha in conn.execute("PRAGMA table_info(treino_ia)")}
    assert not conn.in_transaction
    conn.close()


def test_banco_com_o_numero_baixado_a_mao_para_16_sobe_de_novo_e_as_fichas_pedidas_continuam_la(caminho_v16, monkeypatch):
    # Para abrir o banco com o app antigo (que ignora o que é novo) alguém pode baixar o número da versão.
    conn = conectar(caminho_v16)
    migrar(conn)
    conn.execute("UPDATE treino_ia SET fichas_pedidas = 3")
    conn.commit()
    conn.execute("PRAGMA user_version = 16")
    monkeypatch.setattr(db, "fazer_backup", lambda *_a, **_k: None)

    assert migrar(conn) == [16, 17, 18, 19, 20]  # a coluna já existe: não pode falhar

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    assert conn.execute("SELECT fichas_pedidas FROM treino_ia").fetchone()[0] == 3
    conn.close()


@pytest.mark.parametrize("valor, aceito", [(None, True), (0, True), (2, True), (6, True), (-1, False), (7, False)])
def test_fichas_pedidas_so_aceita_vazio_ou_de_0_a_6(caminho_v16, valor, aceito):
    conn = conectar(caminho_v16)
    migrar(conn)

    if aceito:
        conn.execute("UPDATE treino_ia SET fichas_pedidas = ?", (valor,))
        assert conn.execute("SELECT fichas_pedidas FROM treino_ia").fetchone()[0] == valor
    else:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE treino_ia SET fichas_pedidas = ?", (valor,))
    conn.close()


# ------------------------------------------------------------------ 17 -> 18 (treino agendado)


def test_17_para_18_nao_perde_nada_e_nasce_a_coluna_vazia(caminho_v17):
    conn = conectar(caminho_v17)

    assert migrar(conn) == [17, 18, 19, 20]

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    linhas = [tuple(l) for l in conn.execute("SELECT id, nome, ativo, agendado_para FROM treino ORDER BY id")]
    assert linhas == [(1, "TREINO VELHO", 0, None), (2, "TREINO ABC", 1, None)]
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_copia_de_seguranca_da_versao_17_guarda_o_banco_como_era(caminho_v17):
    conn = conectar(caminho_v17)
    migrar(conn)
    conn.close()

    copias = sorted((caminho_v17.parent / PASTA_ANTES_DA_MIGRACAO).glob("*.db"))
    assert len(copias) == 1
    copia = sqlite3.connect(copias[0])
    assert copia.execute("PRAGMA user_version").fetchone()[0] == 17
    assert "agendado_para" not in {linha[1] for linha in copia.execute("PRAGMA table_info(treino)")}
    copia.close()


def test_migracao_17_para_18_que_quebra_no_fim_nao_deixa_rastro(caminho_v17, monkeypatch):
    def quebra(conn):
        db._de_17_para_18(conn)
        raise RuntimeError("falha no fim")

    monkeypatch.setitem(db.MIGRACOES, 17, quebra)
    conn = conectar(caminho_v17)

    with pytest.raises(RuntimeError, match="falha no fim"):
        migrar(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 17
    assert "agendado_para" not in {linha[1] for linha in conn.execute("PRAGMA table_info(treino)")}
    assert not conn.in_transaction
    conn.close()


def test_banco_com_o_numero_baixado_a_mao_para_17_sobe_de_novo_e_o_agendado_continua_la(caminho_v17, monkeypatch):
    conn = conectar(caminho_v17)
    migrar(conn)
    conn.execute("INSERT INTO treino (aluno_id, nome, montado_por, ativo, inicio, agendado_para) VALUES (1, 'NOVO', 'ANA', 0, '2026-12-01', '2026-12-01')")
    conn.commit()
    conn.execute("PRAGMA user_version = 17")
    monkeypatch.setattr(db, "fazer_backup", lambda *_a, **_k: None)

    assert migrar(conn) == [17, 18, 19, 20]  # a coluna e o índice já existem: não pode falhar

    assert conn.execute("SELECT agendado_para FROM treino WHERE nome = 'NOVO'").fetchone()[0] == "2026-12-01"
    conn.close()


def test_o_banco_so_aceita_agendado_inativo_e_um_por_aluno(caminho_v17):
    conn = conectar(caminho_v17)
    migrar(conn)
    insere = "INSERT INTO treino (aluno_id, nome, montado_por, ativo, inicio, agendado_para) VALUES (1, ?, 'ANA', ?, '2026-12-01', ?)"

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(insere, ("ATIVO E AGENDADO", 1, "2026-12-01"))  # agendado não pode ser o ativo
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(insere, ("DATA ERRADA", 0, "01/12/2026"))
    conn.execute(insere, ("UM", 0, "2026-12-01"))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(insere, ("DOIS", 0, "2026-12-15"))  # um agendado por aluno
    conn.close()


# ------------------------------------------------------------------ 18 -> 19 (foto do aluno)


def test_18_para_19_nao_perde_nada_e_nasce_a_tabela_vazia(caminho_v18):
    conn = conectar(caminho_v18)

    assert migrar(conn) == [18, 19, 20]

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    assert conn.execute("SELECT id, nome, data4u_id FROM aluno").fetchone()[:] == (1, "MARIANA COSTA", 4257)
    assert conn.execute("SELECT COUNT(*) FROM foto_aluno").fetchone()[0] == 0
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_copia_de_seguranca_da_versao_18_guarda_o_banco_como_era(caminho_v18):
    conn = conectar(caminho_v18)
    migrar(conn)
    conn.close()

    copias = sorted((caminho_v18.parent / PASTA_ANTES_DA_MIGRACAO).glob("*.db"))
    assert len(copias) == 1
    copia = sqlite3.connect(copias[0])
    assert copia.execute("PRAGMA user_version").fetchone()[0] == 18
    assert copia.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'foto_aluno'").fetchone()[0] == 0
    copia.close()


# ------------------------------------------------------------------ 19 -> 20 (foto ampliada)


def test_19_para_20_mantem_a_miniatura_e_nasce_a_grande_vazia(caminho_v19):
    conn = conectar(caminho_v19)

    assert migrar(conn) == [19, 20]

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    linha = conn.execute("SELECT aluno_id, length(miniatura), grande, origem_sha256 FROM foto_aluno").fetchone()
    assert tuple(linha) == (1, 203, None, "a" * 64)
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


# ------------------------------------------------------------------ 20 -> 21 (foto escolhida pelo aluno)


def test_20_para_21_mantem_a_foto_da_catraca_e_nascem_as_tabelas_vazias(caminho_v20):
    conn = conectar(caminho_v20)

    assert migrar(conn) == [20]

    assert conn.execute("PRAGMA user_version").fetchone()[0] == 21
    assert conn.execute("SELECT aluno_id, length(grande) FROM foto_aluno").fetchone()[:] == (1, 903)
    assert conn.execute("SELECT COUNT(*) FROM foto_propria").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM foto_propria_troca").fetchone()[0] == 0
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()
