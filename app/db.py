"""Acesso ao banco de dados (SQLite) do app Glória Fit."""

import sqlite3
from pathlib import Path

from app.texto import normalizar

ARQUIVO_SCHEMA = Path(__file__).with_name("schema.sql")

# Número do desenho do banco (o mesmo que está em "PRAGMA user_version" no
# schema.sql). Sobe sempre que o desenho muda de um jeito que arquivos antigos
# não acompanham.
VERSAO_DO_BANCO = 4


class BancoDesatualizado(Exception):
    """O arquivo do banco foi criado por uma versão antiga do app."""


def conectar(caminho: str | Path = ":memory:") -> sqlite3.Connection:
    """Abre o banco. Sem argumento, usa um banco temporário na memória (testes)."""
    conn = sqlite3.connect(caminho)
    conn.row_factory = sqlite3.Row  # permite ler colunas pelo nome: linha["nome"]
    # O SQLite NÃO confere chaves estrangeiras por padrão. Sem esta linha ele
    # aceitaria, por exemplo, um item de ficha apontando para um exercício que
    # não existe. Precisa ser ligada em toda conexão.
    conn.execute("PRAGMA foreign_keys = ON")
    # O SQLite só ignora maiúsculas/minúsculas em letras SEM acento. Esta função
    # deixa o SQL comparar sem acento também: sem_acento(nome) LIKE '%biceps%'.
    conn.create_function("sem_acento", 1, normalizar, deterministic=True)
    # No servidor há mais de um processo (gunicorn) usando o mesmo arquivo. Por padrão o
    # SQLite trava a leitura enquanto alguém grava e devolve "database is locked" na hora.
    # busy_timeout: espera até 5 s pela vez em vez de falhar. WAL: quem lê não trava quem
    # grava (e vice-versa); fica gravado no próprio arquivo do banco. Não vale para a memória.
    conn.execute("PRAGMA busy_timeout = 5000")
    if str(caminho) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


def verificar_versao(conn: sqlite3.Connection) -> None:
    """Recusa um banco que já tem tabelas mas é de uma versão antiga do desenho.

    Sem isso, o app subiria e só falharia na hora de salvar, com um erro
    confuso ("no such column"). Um banco novo (sem tabelas) passa.
    """
    tem_tabelas = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'treino'"
    ).fetchone()
    versao = conn.execute("PRAGMA user_version").fetchone()[0]
    if tem_tabelas and versao != VERSAO_DO_BANCO:
        raise BancoDesatualizado(
            f"Este banco é da versão {versao} do desenho e o app espera a {VERSAO_DO_BANCO}. "
            "Ainda não há dados de alunos para migrar: apague o arquivo e crie de novo com "
            "python -m app.importar_exercicios dados/quadro_exercicios_v2.xlsx app.db"
        )


def criar_tabelas(conn: sqlite3.Connection) -> None:
    """Cria as tabelas que ainda não existem. Pode rodar mais de uma vez."""
    verificar_versao(conn)
    conn.executescript(ARQUIVO_SCHEMA.read_text(encoding="utf-8"))
