-- Banco de dados do app Glória Fit (SQLite).
-- Versão 4 (07/10/2026): exercícios, alunos (vindos do Data4U), treinos e computadores autorizados.
-- Mudança da versão 3 para a 4 (proteção da área do professor): entraram as tabelas
-- codigo_de_autorizacao, dispositivo e autorizacao_falha (ver o fim do arquivo).
-- Mudanças da versão 2 para a 3 (importação dos alunos do Data4U): o CPF do aluno
-- pode ficar vazio (361 pessoas do Data4U não têm CPF cadastrado) e o aluno ganhou
-- a coluna `situacao` (a letra da situação no Data4U).
-- Mudança da versão 1 para a 2: saiu a tabela de professores. Os professores da
-- academia mudam muito, então cada treino guarda o NOME de quem montou (digitado
-- na hora de salvar), em treino.montado_por.
-- Fora desta versão, de propósito: login do aluno, pendências da recepção e
-- mensalidade/produtos. Entram em versões seguintes, quando forem desenhados.

PRAGMA user_version = 4;

-- ---------------------------------------------------------------- exercícios

-- Os 15 grupos musculares do quadro de exercícios.
CREATE TABLE IF NOT EXISTS grupo_muscular (
    id    INTEGER PRIMARY KEY,
    nome  TEXT    NOT NULL UNIQUE,
    ordem INTEGER NOT NULL UNIQUE
);

-- Um exercício da biblioteca do app.
-- nome: sem diferença entre maiúsculas e minúsculas (só vale para letras sem acento).
-- combinado: 1 = no Data4U já existe como um exercício só, "A + B".
-- origem: de onde veio. 'app' = criado dentro do app, depois da importação.
CREATE TABLE IF NOT EXISTS exercicio (
    id               INTEGER PRIMARY KEY,
    nome             TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    ativo            INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
    combinado        INTEGER NOT NULL DEFAULT 0 CHECK (combinado IN (0, 1)),
    origem           TEXT    NOT NULL CHECK (origem IN ('data4u_academia', 'data4u_catalogo', 'app')),
    usos_ultimo_ano  INTEGER NOT NULL DEFAULT 0,
    confianca_grupo  TEXT,
    criado_em        TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Um exercício pode ter mais de um grupo (os combinados têm dois ou três).
-- Exercício sem linha aqui = sem grupo ainda.
CREATE TABLE IF NOT EXISTS exercicio_grupo (
    exercicio_id INTEGER NOT NULL REFERENCES exercicio(id) ON DELETE CASCADE,
    grupo_id     INTEGER NOT NULL REFERENCES grupo_muscular(id),
    PRIMARY KEY (exercicio_id, grupo_id)
);

-- Todos os ids que o exercício tem no Data4U (o quadro juntou exercícios
-- repetidos). Serve para devolver o treino ao Data4U. Qual deles usar na hora
-- de gravar ainda não foi decidido.
CREATE TABLE IF NOT EXISTS exercicio_data4u (
    data4u_id    INTEGER PRIMARY KEY,
    exercicio_id INTEGER NOT NULL REFERENCES exercicio(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_exercicio_data4u_exercicio ON exercicio_data4u(exercicio_id);

-- ---------------------------------------------------------------------- alunos

-- cpf: só os 11 dígitos, ou vazio (NULL) quando o Data4U não tem o CPF da pessoa.
-- NÃO é único: na base do Data4U há CPFs em mais de uma pessoa. Como o login por
-- CPF vai tratar isso ainda não foi decidido.
-- whatsapp: só dígitos, com DDD (a base do Data4U tem números fora desse formato;
-- esses ficam vazios).
-- whatsapp_corrigido_no_app: 1 = a recepção corrigiu no app; a cópia diária do
-- Data4U não pode sobrescrever.
-- data4u_id: a MATRÍCULA do aluno (coluna ID da tabela PESSOA do Data4U; conferido
-- pelo Thiago em 07/10/2026 com o cadastro de uma pessoa em que ID e CD_PESSOA diferem).
-- situacao: letra do Data4U na data da cópia (A ativo, T trancado, P pendente,
-- D desistente, I inativo, C cancelado). Vazia no aluno provisório.
-- provisorio: 1 = aluno cadastrado no primeiro dia, ainda sem par no Data4U.
CREATE TABLE IF NOT EXISTS aluno (
    id                         INTEGER PRIMARY KEY,
    nome                       TEXT    NOT NULL,
    cpf                        TEXT
        CHECK (cpf IS NULL OR (length(cpf) = 11 AND cpf NOT GLOB '*[^0-9]*')),
    whatsapp                   TEXT
        CHECK (whatsapp IS NULL OR (length(whatsapp) BETWEEN 10 AND 11 AND whatsapp NOT GLOB '*[^0-9]*')),
    whatsapp_corrigido_no_app  INTEGER NOT NULL DEFAULT 0 CHECK (whatsapp_corrigido_no_app IN (0, 1)),
    data4u_id                  INTEGER UNIQUE,
    situacao                   TEXT
        CHECK (situacao IS NULL OR situacao IN ('A', 'T', 'P', 'D', 'I', 'C')),
    provisorio                 INTEGER NOT NULL DEFAULT 0 CHECK (provisorio IN (0, 1)),
    criado_em                  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_aluno_cpf ON aluno(cpf);

-- --------------------------------------------------------------------- treinos
-- Mesma estrutura do Data4U: treino -> fichas (A, B, C) -> exercícios.

-- nome: até 40 letras (limite de NM_TREINO no Data4U).
-- montado_por: nome de quem montou, digitado na hora de salvar (até 60 letras).
--   Treinos montados automaticamente (robô/Claude, no futuro) usam "Academia Glória Fit".
-- Apagar um aluno que tem treino é recusado (não perde histórico sem querer).
CREATE TABLE IF NOT EXISTS treino (
    id           INTEGER PRIMARY KEY,
    aluno_id     INTEGER NOT NULL REFERENCES aluno(id),
    nome         TEXT    NOT NULL CHECK (length(nome) BETWEEN 1 AND 40),
    montado_por  TEXT    NOT NULL CHECK (length(montado_por) BETWEEN 1 AND 60),
    ativo        INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
    criado_em    TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_treino_aluno ON treino(aluno_id);
-- Um aluno não pode ter dois treinos com o mesmo nome (o Data4U também recusa).
CREATE UNIQUE INDEX IF NOT EXISTS ux_treino_nome_por_aluno ON treino(aluno_id, nome COLLATE NOCASE);

-- nome: até 15 letras (limite de NM_TREINO_FICHA no Data4U; corta sem avisar).
-- ordem: posição da ficha dentro do treino (1 = A, 2 = B...).
CREATE TABLE IF NOT EXISTS ficha (
    id        INTEGER PRIMARY KEY,
    treino_id INTEGER NOT NULL REFERENCES treino(id) ON DELETE CASCADE,
    nome      TEXT    NOT NULL CHECK (length(nome) BETWEEN 1 AND 15),
    ordem     INTEGER NOT NULL CHECK (ordem >= 1),
    UNIQUE (treino_id, ordem)
);

-- Um exercício dentro de uma ficha.
-- bloco: itens da mesma ficha com o mesmo número de bloco formam um bi-set
--        (2 itens) ou tri-set (3 itens). NULL = exercício sozinho.
-- series, repeticoes, carga: texto de até 11 caracteres (limite do Data4U).
-- pausa: número, como no Data4U (a unidade não foi verificada).
-- Exercício já usado numa ficha não pode ser apagado: desative (ativo = 0).
CREATE TABLE IF NOT EXISTS ficha_item (
    id           INTEGER PRIMARY KEY,
    ficha_id     INTEGER NOT NULL REFERENCES ficha(id) ON DELETE CASCADE,
    ordem        INTEGER NOT NULL CHECK (ordem >= 1),
    bloco        INTEGER CHECK (bloco IS NULL OR bloco >= 1),
    exercicio_id INTEGER NOT NULL REFERENCES exercicio(id),
    series       TEXT CHECK (series     IS NULL OR length(series)     <= 11),
    repeticoes   TEXT CHECK (repeticoes IS NULL OR length(repeticoes) <= 11),
    carga        TEXT CHECK (carga      IS NULL OR length(carga)      <= 11),
    pausa        INTEGER CHECK (pausa IS NULL OR pausa >= 0),
    observacao   TEXT,
    UNIQUE (ficha_id, ordem)
);
CREATE INDEX IF NOT EXISTS ix_ficha_item_exercicio ON ficha_item(exercicio_id);

-- ------------------------------------------------------------ acesso do professor
-- A área do professor só abre em computadores AUTORIZADOS (hoje: o dos professores e o
-- da recepção). Quem tem acesso ao servidor gera um código de uso único; digitado na
-- tela /autorizar do computador, ele vira um "dispositivo" reconhecido por um cookie.
-- Nada aqui guarda o código nem o cookie em texto: só o hash SHA-256 de cada um.
-- Datas em UTC, no formato 'AAAA-MM-DD HH:MM:SS' (dá para comparar como texto).

-- Código de uso único, válido por poucos minutos.
-- codigo_hash: SHA-256 do código normalizado (maiúsculas, sem hífen).
-- nome_do_dispositivo: o nome que o computador receberá ao ser autorizado.
-- usado_em: preenchido quando o código é usado (só pode ser usado uma vez).
CREATE TABLE IF NOT EXISTS codigo_de_autorizacao (
    id                  INTEGER PRIMARY KEY,
    codigo_hash         TEXT    NOT NULL UNIQUE,
    nome_do_dispositivo TEXT    NOT NULL CHECK (length(nome_do_dispositivo) BETWEEN 1 AND 40),
    criado_em           TEXT    NOT NULL,
    expira_em           TEXT    NOT NULL,
    usado_em            TEXT
);

-- Um computador autorizado.
-- token_hash: SHA-256 do valor guardado no cookie do navegador.
-- ultimo_uso_em: renovado, no máximo uma vez por hora, enquanto o computador é usado.
--   Computador parado por muito tempo perde a autorização (ver app/acesso.py).
-- revogado_em: preenchido quando alguém revoga o computador (não apagamos a linha).
CREATE TABLE IF NOT EXISTS dispositivo (
    id            INTEGER PRIMARY KEY,
    nome          TEXT    NOT NULL CHECK (length(nome) BETWEEN 1 AND 40),
    token_hash    TEXT    NOT NULL UNIQUE,
    criado_em     TEXT    NOT NULL,
    ultimo_uso_em TEXT    NOT NULL,
    revogado_em   TEXT
);

-- Cada código errado digitado em /autorizar. Serve para limitar tentativas.
CREATE TABLE IF NOT EXISTS autorizacao_falha (
    id INTEGER PRIMARY KEY,
    em TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_autorizacao_falha_em ON autorizacao_falha(em);
