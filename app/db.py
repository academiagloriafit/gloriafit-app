"""Acesso ao banco de dados (SQLite) do app Glória Fit."""

import sqlite3
from pathlib import Path

from app.backup import fazer_backup
from app.datas import dia_local
from app.texto import normalizar

ARQUIVO_SCHEMA = Path(__file__).with_name("schema.sql")

# Número do desenho do banco (o mesmo que está em "PRAGMA user_version" no
# schema.sql). Sobe sempre que o desenho muda de um jeito que arquivos antigos
# não acompanham.
VERSAO_DO_BANCO = 12

# Pasta (ao lado do banco) onde fica a cópia tirada automaticamente antes de uma migração.
PASTA_ANTES_DA_MIGRACAO = "antes-da-migracao"
COPIAS_ANTES_DA_MIGRACAO = 5


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
    """Recusa um banco que já tem tabelas mas não é da versão que o app espera.

    Sem isso, o app subiria e só falharia na hora de salvar, com um erro
    confuso ("no such column"). Um banco novo (sem tabelas) passa. Bancos de uma
    versão que sabemos atualizar (ver `migrar`) devem passar por `migrar` antes.
    """
    tem_tabelas = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'treino'"
    ).fetchone()
    versao = conn.execute("PRAGMA user_version").fetchone()[0]
    if tem_tabelas and versao != VERSAO_DO_BANCO:
        if versao > VERSAO_DO_BANCO:
            raise BancoDesatualizado(
                f"Este banco é da versão {versao} do desenho, mais nova que a {VERSAO_DO_BANCO} que este app "
                "conhece. NÃO apague o arquivo: use a versão mais nova do app, ou restaure uma cópia de segurança."
            )
        raise BancoDesatualizado(
            f"Este banco é da versão {versao} do desenho e o app espera a {VERSAO_DO_BANCO}. "
            f"O app só atualiza sozinho bancos a partir da versão {min(MIGRACOES)}. "
            "As versões anteriores nunca tiveram dados reais: apague o arquivo e crie de novo com "
            "python -m app.importar_exercicios dados/quadro_exercicios_v2.xlsx app.db"
        )


# ------------------------------------------------------------------ migrações


def _de_4_para_5(conn: sqlite3.Connection) -> None:
    """Histórico de treinos do Data4U: o treino ganha `origem` e `data4u_id`.

    O índice de nome repetido passa a valer só para treinos do app (`origem = 'app'`): o
    histórico do Data4U tem nomes repetidos para o mesmo aluno. Treinos que já existem são
    todos do app (ainda não havia importação de treinos): o DEFAULT cuida deles.
    """
    conn.execute(
        "ALTER TABLE treino ADD COLUMN origem TEXT NOT NULL DEFAULT 'app' CHECK (origem IN ('app', 'data4u'))"
    )
    conn.execute("ALTER TABLE treino ADD COLUMN data4u_id INTEGER")
    conn.execute("DROP INDEX IF EXISTS ux_treino_nome_por_aluno")
    conn.execute(
        "CREATE UNIQUE INDEX ux_treino_nome_por_aluno ON treino(aluno_id, nome COLLATE NOCASE) WHERE origem = 'app'"
    )
    conn.execute("CREATE UNIQUE INDEX ux_treino_data4u ON treino(data4u_id)")


_PADRAO_DE_DIA = "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'"
_PADRAO_DE_MOMENTO = "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]'"


def _de_5_para_6(conn: sqlite3.Connection) -> None:
    """Ciclo do treino: início/fim, "Concluído", meta de sessões por ficha e um treino ativo por aluno.

    - `inicio` dos treinos que já existem = o dia (em Brasília) em que foram lançados.
    - Decisão do Thiago (08/10/2026): dos treinos antigos, SÓ O MAIS RECENTE de cada aluno continua
      ativo; os outros viram inativos (histórico). `concluido_em` fica vazio neles: não se sabe quando acabaram.
    - Depois disso é possível criar o índice que garante UM treino ativo por aluno.
    """
    conn.execute(f"ALTER TABLE treino ADD COLUMN inicio TEXT CHECK (inicio IS NULL OR inicio GLOB {_PADRAO_DE_DIA})")
    conn.execute(f"ALTER TABLE treino ADD COLUMN fim TEXT CHECK (fim IS NULL OR fim GLOB {_PADRAO_DE_DIA})")
    conn.execute("ALTER TABLE treino ADD COLUMN concluido_em TEXT")
    conn.execute(
        "ALTER TABLE treino ADD COLUMN sessoes_por_ficha INTEGER "
        "CHECK (sessoes_por_ficha IS NULL OR sessoes_por_ficha BETWEEN 1 AND 999)"
    )
    # Em Python (e não com date(criado_em, '-3 hours')) porque o horário de verão de antes de 2019 muda o dia.
    conn.executemany(
        "UPDATE treino SET inicio = ? WHERE id = ?",
        [(dia_local(criado_em), treino_id) for treino_id, criado_em in conn.execute("SELECT id, criado_em FROM treino")],
    )
    conn.execute(
        """
        UPDATE treino SET ativo = 0
        WHERE id <> (SELECT t2.id FROM treino t2 WHERE t2.aluno_id = treino.aluno_id
                     ORDER BY t2.criado_em DESC, t2.id DESC LIMIT 1)
        """
    )
    conn.execute("CREATE UNIQUE INDEX ux_treino_ativo_por_aluno ON treino(aluno_id) WHERE ativo = 1")
    conn.execute(
        """
        CREATE TABLE sessao (
            id          INTEGER PRIMARY KEY,
            treino_id   INTEGER NOT NULL REFERENCES treino(id) ON DELETE CASCADE,
            ficha_ordem INTEGER NOT NULL CHECK (ficha_ordem >= 1),
            feita_em    TEXT    NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute("CREATE INDEX ix_sessao_treino ON sessao(treino_id)")


def _de_6_para_7(conn: sqlite3.Connection) -> None:
    """Treinos padrão: nasce a tabela `modelo_treino` (treino pronto para copiar para qualquer aluno).

    Só acrescenta uma tabela: nenhum dado que já existe é tocado. Os comandos são "IF NOT EXISTS" de propósito:
    se um dia o número da versão for baixado à mão (para abrir o banco com o app antigo, que ignora a tabela
    nova), subir de novo com este app não falha por a tabela já existir.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS modelo_treino (
            id                INTEGER PRIMARY KEY,
            nome              TEXT    NOT NULL CHECK (length(nome) BETWEEN 1 AND 40),
            montado_por       TEXT    NOT NULL CHECK (length(montado_por) BETWEEN 1 AND 60),
            sessoes_por_ficha INTEGER CHECK (sessoes_por_ficha IS NULL OR sessoes_por_ficha BETWEEN 1 AND 999),
            conteudo          TEXT    NOT NULL,
            criado_em         TEXT    NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_modelo_treino_nome ON modelo_treino(nome COLLATE NOCASE)")


def _de_7_para_8(conn: sqlite3.Connection) -> None:
    """Filas numeradas de treino: nascem `fila` (com as 5 filas do começo) e `aluno_fila`; o treino padrão ganha `fila_id` e `numero`.

    Só acrescenta: nenhum dado que já existe é tocado (os treinos padrão que já existirem ficam sem fila). Os comandos
    são "IF NOT EXISTS" / conferem as colunas de propósito: se um dia o número da versão for baixado à mão (para abrir
    o banco com o app antigo, que ignora o que é novo), subir de novo com este app não falha por já existir.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fila (
            id              INTEGER PRIMARY KEY,
            nome            TEXT    NOT NULL CHECK (length(nome) BETWEEN 1 AND 40),
            exige_liberacao INTEGER NOT NULL DEFAULT 0 CHECK (exige_liberacao IN (0, 1)),
            ordem           INTEGER NOT NULL
        )
        """
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_fila_nome ON fila(nome COLLATE NOCASE)")
    conn.execute(
        "INSERT OR IGNORE INTO fila (id, nome, exige_liberacao, ordem) VALUES "
        "(1, 'Homem', 0, 1), (2, 'Mulher', 0, 2), (3, 'Adolescente', 0, 3), (4, 'Gestante', 1, 4), (5, 'Grupos de risco', 1, 5)"
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS aluno_fila (
            aluno_id      INTEGER PRIMARY KEY REFERENCES aluno(id),
            fila_id       INTEGER NOT NULL REFERENCES fila(id),
            numero_atual  INTEGER CHECK (numero_atual IS NULL OR numero_atual BETWEEN 1 AND 99),
            definida_por  TEXT    NOT NULL CHECK (length(definida_por) BETWEEN 1 AND 60),
            definida_em   TEXT    NOT NULL DEFAULT (datetime('now')),
            liberacao_em  TEXT    CHECK (liberacao_em IS NULL OR liberacao_em GLOB {_PADRAO_DE_DIA}),
            liberacao_por TEXT    CHECK (liberacao_por IS NULL OR length(liberacao_por) BETWEEN 1 AND 60)
        )
        """
    )
    colunas = {linha[1] for linha in conn.execute("PRAGMA table_info(modelo_treino)")}
    if "fila_id" not in colunas:
        conn.execute("ALTER TABLE modelo_treino ADD COLUMN fila_id INTEGER REFERENCES fila(id)")
    if "numero" not in colunas:
        conn.execute(
            "ALTER TABLE modelo_treino ADD COLUMN numero INTEGER "
            "CHECK (numero IS NULL OR (numero BETWEEN 1 AND 99 AND fila_id IS NOT NULL))"
        )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_modelo_fila_numero ON modelo_treino(fila_id, numero) WHERE fila_id IS NOT NULL"
    )


def _de_8_para_9(conn: sqlite3.Connection) -> None:
    """Senha de administrador: nascem `senha_administrador` (uma linha, o hash da senha) e `senha_administrador_falha`.

    Só acrescenta duas tabelas vazias: nenhum dado que já existe é tocado. Os comandos são "IF NOT EXISTS" de propósito:
    se um dia o número da versão for baixado à mão (para abrir o banco com o app antigo, que ignora o que é novo), subir
    de novo com este app não falha por já existir, e a senha já definida continua valendo.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS senha_administrador (
            id          INTEGER PRIMARY KEY CHECK (id = 1),
            senha_hash  TEXT    NOT NULL,
            definida_em TEXT    NOT NULL
        )
        """
    )
    conn.execute("CREATE TABLE IF NOT EXISTS senha_administrador_falha (id INTEGER PRIMARY KEY, em TEXT NOT NULL)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_senha_administrador_falha_em ON senha_administrador_falha(em)")



def _de_9_para_10(conn: sqlite3.Connection) -> None:
    """Treino sob medida (IA): nasce `ia_pedido` (os rascunhos de treino pedidos ao Claude e o contador do limite por dia).

    Só acrescenta uma tabela vazia: nenhum dado que já existe é tocado. Os comandos são "IF NOT EXISTS" de propósito:
    se um dia o número da versão for baixado à mão (para abrir o banco com o app antigo, que ignora o que é novo), subir
    de novo com este app não falha por a tabela já existir, e os pedidos já guardados continuam lá.
    """
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS ia_pedido (
            id             INTEGER PRIMARY KEY,
            aluno_id       INTEGER NOT NULL REFERENCES aluno(id),
            criado_em      TEXT    NOT NULL,
            dia            TEXT    NOT NULL CHECK (dia GLOB {_PADRAO_DE_DIA}),
            situacao       TEXT    NOT NULL CHECK (situacao IN ('andando', 'pronto', 'erro')),
            modelo         TEXT    NOT NULL,
            resultado      TEXT,
            erro           TEXT,
            tokens_entrada INTEGER CHECK (tokens_entrada IS NULL OR tokens_entrada >= 0),
            tokens_saida   INTEGER CHECK (tokens_saida IS NULL OR tokens_saida >= 0),
            terminado_em   TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ix_ia_pedido_dia ON ia_pedido(dia)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_ia_pedido_aluno ON ia_pedido(aluno_id)")


def _de_10_para_11(conn: sqlite3.Connection) -> None:
    """Atualização automática dos alunos: nasce `importacao` (de quando é a última cópia do Data4U aplicada, por assunto).

    Só acrescenta uma tabela vazia: nenhum dado que já existe é tocado. O comando é "IF NOT EXISTS" de propósito:
    se um dia o número da versão for baixado à mão (para abrir o banco com o app antigo, que ignora o que é novo), subir
    de novo com este app não falha por a tabela já existir, e o registro que já estava lá continua.
    """
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS importacao (
            tipo        TEXT PRIMARY KEY CHECK (tipo IN ('alunos', 'treinos')),
            extraido_em TEXT NOT NULL CHECK (extraido_em GLOB {_PADRAO_DE_MOMENTO}),
            recebida_em TEXT NOT NULL CHECK (recebida_em GLOB {_PADRAO_DE_MOMENTO})
        )
        """
    )


def _de_11_para_12(conn: sqlite3.Connection) -> None:
    """Login do aluno: nascem `aluno_senha`, `aluno_codigo`, `aluno_sessao` e `aluno_evento` (senha, códigos por WhatsApp, sessões, limite de tentativas).

    Só acrescenta quatro tabelas vazias: nenhum dado que já existe é tocado. Os comandos são "IF NOT EXISTS" de propósito:
    se um dia o número da versão for baixado à mão (para abrir o banco com o app antigo, que ignora o que é novo), subir
    de novo com este app não falha por as tabelas já existirem, e as senhas já criadas continuam valendo.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS aluno_senha (
            aluno_id    INTEGER PRIMARY KEY REFERENCES aluno(id),
            senha_hash  TEXT    NOT NULL,
            definida_em TEXT    NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS aluno_codigo (
            id          INTEGER PRIMARY KEY,
            aluno_id    INTEGER NOT NULL REFERENCES aluno(id),
            codigo_hash TEXT    NOT NULL,
            criado_em   TEXT    NOT NULL,
            expira_em   TEXT    NOT NULL,
            tentativas  INTEGER NOT NULL DEFAULT 0 CHECK (tentativas >= 0),
            usado_em    TEXT,
            envio       TEXT    NOT NULL DEFAULT 'pendente' CHECK (envio IN ('pendente', 'enviado', 'falhou')),
            envio_erro  TEXT    CHECK (envio_erro IS NULL OR length(envio_erro) <= 300)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ix_aluno_codigo_aluno ON aluno_codigo(aluno_id, criado_em)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_aluno_codigo_criado ON aluno_codigo(criado_em)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS aluno_sessao (
            id            INTEGER PRIMARY KEY,
            aluno_id      INTEGER NOT NULL REFERENCES aluno(id),
            token_hash    TEXT    NOT NULL UNIQUE,
            criado_em     TEXT    NOT NULL,
            ultimo_uso_em TEXT    NOT NULL,
            revogado_em   TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ix_aluno_sessao_aluno ON aluno_sessao(aluno_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS aluno_evento (
            id    INTEGER PRIMARY KEY,
            tipo  TEXT    NOT NULL CHECK (tipo IN ('pedido_codigo', 'codigo_errado', 'login_errado')),
            chave TEXT    NOT NULL,
            em    TEXT    NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ix_aluno_evento ON aluno_evento(tipo, chave, em)")


# versão de partida -> o que leva à versão seguinte. Cada passo muda só o necessário.
MIGRACOES = {
    4: _de_4_para_5, 5: _de_5_para_6, 6: _de_6_para_7, 7: _de_7_para_8, 8: _de_8_para_9, 9: _de_9_para_10,
    10: _de_10_para_11, 11: _de_11_para_12,
}


def _arquivo_do_banco(conn: sqlite3.Connection) -> Path | None:
    """O arquivo da conexão, ou None se o banco está na memória."""
    arquivo = conn.execute("PRAGMA database_list").fetchone()[2]  # colunas: seq, name, file
    return Path(arquivo) if arquivo else None


def migrar(conn: sqlite3.Connection) -> list[int]:
    """Leva um banco antigo até a versão atual. Devolve as versões de partida aplicadas ([] = nada a fazer).

    Segurança, porque aqui já há dados de verdade:
    - Antes de mexer, tira uma cópia consistente em `<pasta do banco>/antes-da-migracao/` (uma só por
      chamada, mesmo que haja vários passos: ela guarda o banco COMO ERA antes de qualquer um).
    - Cada passo roda numa transação: ou muda tudo, ou nada (o DDL do SQLite é transacional).
    - Dois processos subindo juntos (o servidor tem 2): o segundo espera a vez e, ao entrar,
      vê que a versão já subiu e não faz nada (`BEGIN IMMEDIATE` + conferência de novo).
    """
    aplicadas: list[int] = []
    copia_tirada = False
    while True:
        versao = conn.execute("PRAGMA user_version").fetchone()[0]
        tem_tabelas = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'treino'"
        ).fetchone()
        if not tem_tabelas or versao not in MIGRACOES:
            return aplicadas
        conn.execute("BEGIN IMMEDIATE")  # pega a trava de escrita já: ninguém muda o banco daqui até o COMMIT
        try:
            if conn.execute("PRAGMA user_version").fetchone()[0] != versao:
                conn.rollback()  # outro processo migrou enquanto esperávamos a trava
                continue
            arquivo = _arquivo_do_banco(conn)
            if arquivo is not None and not copia_tirada:
                fazer_backup(arquivo, arquivo.parent / PASTA_ANTES_DA_MIGRACAO, COPIAS_ANTES_DA_MIGRACAO)
                copia_tirada = True
            MIGRACOES[versao](conn)
            conn.execute(f"PRAGMA user_version = {versao + 1}")  # número do código, nunca de fora
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        aplicadas.append(versao)


def criar_tabelas(conn: sqlite3.Connection) -> None:
    """Cria as tabelas que ainda não existem (e atualiza um banco antigo). Pode rodar mais de uma vez."""
    migrar(conn)
    verificar_versao(conn)
    conn.executescript(ARQUIVO_SCHEMA.read_text(encoding="utf-8"))
