-- Banco de dados do app Glória Fit (SQLite).
-- Versão 19 (29/10/2026): exercícios, alunos (vindos do Data4U), treinos, treinos padrão, filas numeradas, computadores autorizados, senha de administrador, pedidos de treino sob medida (IA), o registro de quando os alunos e o histórico de treinos foram atualizados, o login do aluno (senha, códigos por WhatsApp, sessões), os comentários do aluno sobre o treino e o que o aluno faz durante o treino (esforço ao concluir, exercício feito, carga usada) e o que o robô aprende com os professores (avaliação do rascunho da IA e o que o professor mudou antes de salvar) e o histórico de por que um treino feito com a IA foi montado daquele jeito (o que o professor escreveu para o robô, quantas fichas diferentes ele pediu e a justificativa do robô) e o treino agendado (montado hoje para entrar numa data futura) e a foto do aluno (a da catraca, em miniatura).
-- Mudança da versão 18 para a 19 (foto do aluno): nasceu a tabela `foto_aluno` (a miniatura da foto que a recepção tirou no Data4U, só para
-- o professor reconhecer o aluno nas telas). Bancos da versão 18 são atualizados sozinhos na subida.
-- Mudança da versão 17 para a 18 (treino agendado): `treino` ganhou `agendado_para` (o dia em que um treino montado antes da hora vira o ativo
-- do aluno; o atual é concluído nesse dia). Vazio = treino comum. Bancos da versão 17 são atualizados sozinhos na subida.
-- Mudança da versão 16 para a 17 (fichas diferentes dos dias): `treino_ia` ganhou `fichas_pedidas` (quantas fichas DIFERENTES o professor pediu ao
-- robô: 0 = deixou o robô decidir; 2 a 6 = escolheu; vazio = treino de antes desta função, quando o número de fichas era sempre igual aos dias).
-- Bancos da versão 16 são atualizados sozinhos na subida.
-- Mudança da versão 15 para a 16 (histórico do treino feito com a IA): nasceu a tabela `treino_ia` (uma linha por treino salvo a partir de um
-- rascunho da IA: o pedido do professor, as observações e a conversa com o robô, a justificativa do robô e o que o professor mudou antes de
-- salvar). Ao contrário de `ia_retorno`, ESTA tabela é ligada ao treino (e portanto ao aluno) de propósito. Bancos da versão 15 são
-- atualizados sozinhos na subida.
-- Mudança da versão 14 para a 15 (o robô aprende com os professores): nasceu a tabela `ia_retorno` (uma linha por avaliação do rascunho da IA e uma
-- por treino salvo a partir de um rascunho, com o que o professor mudou; NÃO tem aluno, professor nem hora, só o dia). Bancos da versão 14 são
-- atualizados sozinhos na subida.
-- Mudança da versão 13 para a 14 (treino com mais detalhe): a `sessao` ganhou `esforco` (1 leve, 2 ideal, 3 pesado: como o aluno achou o treino
-- ao concluí-lo) e nasceu a tabela `execucao` (por dia, o exercício que o aluno marcou como feito e a carga que usou). Bancos da versão 13 são
-- atualizados sozinhos na subida.
-- Mudança da versão 12 para a 13 (comentários do aluno): nasceu a tabela `comentario` (o que o aluno escreve sobre o treino inteiro ou
-- sobre um exercício; o professor lê, marca como lido e, na segunda entrega, responde). Bancos da versão 12 são atualizados sozinhos na subida.
-- Mudança da versão 11 para a 12 (login do aluno): nasceram as tabelas `aluno_senha` (o hash da senha de cada aluno), `aluno_codigo`
-- (os códigos de 6 números enviados por WhatsApp, só o hash), `aluno_sessao` (os celulares em que o aluno está logado, só o hash do
-- cookie) e `aluno_evento` (pedidos de código e erros, para limitar tentativas). Bancos da versão 11 são atualizados sozinhos na subida.
-- Mudança da versão 10 para a 11 (atualização automática dos alunos): nasceu a tabela `importacao` (de quando é a última cópia do
-- Data4U aplicada, para os alunos e para o histórico de treinos; serve para avisar na tela quando a atualização parar).
-- Bancos da versão 10 são atualizados sozinhos na subida.
-- Mudança da versão 9 para a 10 (treino sob medida): nasceu a tabela `ia_pedido` (cada rascunho de treino que o Claude
-- foi chamado para montar: andando, pronto ou com erro; serve de fila de espera da tela e de contador do limite por dia).
-- Bancos da versão 9 são atualizados sozinhos na subida.
-- Mudança da versão 8 para a 9 (senha de administrador): nasceram as tabelas `senha_administrador` (o hash da senha
-- que protege adicionar e excluir treino padrão) e `senha_administrador_falha` (senhas erradas, para limitar tentativas).
-- Bancos da versão 8 são atualizados sozinhos na subida.
-- Mudança da versão 7 para a 8 (filas numeradas de treino): nasceram as tabelas `fila` (Homem, Mulher, Adolescente,
-- Gestante, Grupos de risco) e `aluno_fila` (em que fila cada aluno está, em que número, e a liberação de quem precisa);
-- o treino padrão (`modelo_treino`) ganhou `fila_id` e `numero`. Bancos da versão 7 são atualizados sozinhos na subida.
-- Mudança da versão 6 para a 7 (treinos padrão): nasceu a tabela `modelo_treino` (treino pronto para copiar para
-- qualquer aluno, pelo botão "Importar treino"). Bancos da versão 6 são atualizados sozinhos na subida do app.
-- Mudança da versão 5 para a 6 (ciclo do treino): o treino ganhou `inicio`, `fim`,
-- `concluido_em` e `sessoes_por_ficha`; só UM treino por aluno pode ficar ativo (índice
-- `ux_treino_ativo_por_aluno`); nasceu a tabela `sessao` (cada vez que o aluno treinou uma ficha).
-- Bancos da versão 5 são atualizados sozinhos na subida do app (ver app/db.py, função `migrar`).
-- Mudança da versão 4 para a 5 (histórico de treinos do Data4U): o treino ganhou `origem`
-- ('app' ou 'data4u') e `data4u_id`, e o índice de nome repetido passou a valer só para os
-- treinos feitos no app (o histórico do Data4U tem nomes repetidos). Bancos da versão 4 são
-- atualizados sozinhos na subida do app (ver app/db.py, função `migrar`).
-- Mudança da versão 3 para a 4 (proteção da área do professor): entraram as tabelas
-- codigo_de_autorizacao, dispositivo e autorizacao_falha (ver o fim do arquivo).
-- Mudanças da versão 2 para a 3 (importação dos alunos do Data4U): o CPF do aluno
-- pode ficar vazio (361 pessoas do Data4U não têm CPF cadastrado) e o aluno ganhou
-- a coluna `situacao` (a letra da situação no Data4U).
-- Mudança da versão 1 para a 2: saiu a tabela de professores. Os professores da
-- academia mudam muito, então cada treino guarda o NOME de quem montou (digitado
-- na hora de salvar), em treino.montado_por.
-- Fora desta versão, de propósito: pendências da recepção e mensalidade/produtos.
-- Entram em versões seguintes, quando forem desenhados.

PRAGMA user_version = 19;

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
--   Nos treinos do Data4U é o nome do professor registrado lá.
-- origem: 'app' = montado aqui; 'data4u' = histórico copiado do Data4U (app/importar_treinos.py).
--   Os 'data4u' são um espelho: cada importação apaga todos e grava de novo.
-- data4u_id: ID_TREINO no Data4U (histórico importado; no futuro, também o treino do app
--   depois de enviado ao Data4U). Único; vazio nos treinos que ainda não existem lá.
-- criado_em: UTC. No histórico é o DT_LANCAMENTO do Data4U (horário de Brasília) convertido.
-- ativo: 1 = o treino que o aluno está fazendo; 0 = inativo (concluído ou substituído), fica no
--   histórico e o aluno não vê. Só um por aluno pode ser ativo (índice ux_treino_ativo_por_aluno).
-- inicio, fim: dias 'AAAA-MM-DD' do calendário de Brasília. `fim` é opcional (sem fim = vazio) e,
--   passando dele, o app avisa que está na hora de trocar o treino.
-- concluido_em: UTC; quando o professor clicou em "Concluído" (ou o treino foi substituído por um novo).
--   Vazio nos treinos inativados pela migração (não se sabe quando acabaram).
-- sessoes_por_ficha: quantas vezes o aluno deve treinar CADA ficha neste ciclo (ex.: 15). Vazio = sem meta.
-- Apagar um aluno que tem treino é recusado (não perde histórico sem querer).
CREATE TABLE IF NOT EXISTS treino (
    id           INTEGER PRIMARY KEY,
    aluno_id     INTEGER NOT NULL REFERENCES aluno(id),
    nome         TEXT    NOT NULL CHECK (length(nome) BETWEEN 1 AND 40),
    montado_por  TEXT    NOT NULL CHECK (length(montado_por) BETWEEN 1 AND 60),
    ativo        INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
    origem       TEXT    NOT NULL DEFAULT 'app' CHECK (origem IN ('app', 'data4u')),
    data4u_id    INTEGER,
    criado_em    TEXT    NOT NULL DEFAULT (datetime('now')),
    inicio       TEXT    CHECK (inicio IS NULL OR inicio GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    fim          TEXT    CHECK (fim IS NULL OR fim GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    concluido_em TEXT,
    sessoes_por_ficha INTEGER CHECK (sessoes_por_ficha IS NULL OR sessoes_por_ficha BETWEEN 1 AND 999),
    agendado_para TEXT CHECK (agendado_para IS NULL OR (agendado_para GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' AND ativo = 0))
);
CREATE INDEX IF NOT EXISTS ix_treino_aluno ON treino(aluno_id);
-- Só um treino ativo por aluno: é a trava final da regra "um ativo por vez" (quem ativa um treino
-- precisa inativar o outro ANTES; ver app/treinos.py e app/ciclo.py).
CREATE UNIQUE INDEX IF NOT EXISTS ux_treino_ativo_por_aluno ON treino(aluno_id) WHERE ativo = 1;
-- Treino agendado (versão 18): no máximo UM por aluno. É também o índice que a troca automática usa para achar os que chegaram no dia.
CREATE UNIQUE INDEX IF NOT EXISTS ux_treino_agendado_por_aluno ON treino(aluno_id) WHERE agendado_para IS NOT NULL;
-- Um aluno não pode ter dois treinos do app com o mesmo nome (o Data4U também recusa). O índice
-- só vale para os treinos do app: no histórico do Data4U há nomes repetidos, e o app precisa
-- guardá-los como estão. A conferência contra TODOS os treinos do aluno (inclusive os do
-- Data4U) está em app/treinos.py; este índice é a trava final contra dois "salvar" ao mesmo tempo.
CREATE UNIQUE INDEX IF NOT EXISTS ux_treino_nome_por_aluno
    ON treino(aluno_id, nome COLLATE NOCASE) WHERE origem = 'app';
CREATE UNIQUE INDEX IF NOT EXISTS ux_treino_data4u ON treino(data4u_id);

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
-- pausa: o "Intervalo", em segundos. No Data4U é um horário "hh:mm:ss" (o histórico importado é
--        convertido). Na tela de montar o professor digita minutos e segundos (desde 08/10/2026).
-- observacao: texto livre do Data4U (DS_PRESCRICAO_OBS); a tela de montar pede e grava (até 200 letras).
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

-- Cada vez que o aluno treinou uma ficha do treino (quando o app do aluno existir, é ele quem
-- registra). `ficha_ordem` (1 = A, 2 = B...) e não o id da ficha: a importação do Data4U
-- apaga e recria as fichas dos treinos copiados, e a contagem não pode se perder.
CREATE TABLE IF NOT EXISTS sessao (
    id          INTEGER PRIMARY KEY,
    treino_id   INTEGER NOT NULL REFERENCES treino(id) ON DELETE CASCADE,
    ficha_ordem INTEGER NOT NULL CHECK (ficha_ordem >= 1),
    feita_em    TEXT    NOT NULL DEFAULT (datetime('now')),
    -- Como o aluno achou o treino, escolhido por ele depois de "Treino concluído" (opcional): 1 leve, 2 ideal, 3 pesado.
    -- Vazio nas sessões de antes e nas que vieram do papel impresso na recepção.
    esforco     INTEGER CHECK (esforco IS NULL OR esforco BETWEEN 1 AND 3)
);
CREATE INDEX IF NOT EXISTS ix_sessao_treino ON sessao(treino_id);

-- ------------------------------------------------------------ filas numeradas
-- Uma fila é uma sequência de treinos padrão numerados (Treino 1, 2, 3...) para um tipo de aluno. O app NÃO troca o
-- treino do aluno sozinho: ele só SUGERE o próximo número da fila e o professor aprova (ver app/filas.py).
-- exige_liberacao: 1 = o aluno só entra na fila depois que o professor registra que conferiu a liberação
--   (atestado/triagem). Hoje: Gestante e Grupos de risco.
-- ordem: a posição da fila nas telas.
CREATE TABLE IF NOT EXISTS fila (
    id              INTEGER PRIMARY KEY,
    nome            TEXT    NOT NULL CHECK (length(nome) BETWEEN 1 AND 40),
    exige_liberacao INTEGER NOT NULL DEFAULT 0 CHECK (exige_liberacao IN (0, 1)),
    ordem           INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_fila_nome ON fila(nome COLLATE NOCASE);
INSERT OR IGNORE INTO fila (id, nome, exige_liberacao, ordem) VALUES
    (1, 'Homem', 0, 1),
    (2, 'Mulher', 0, 2),
    (3, 'Adolescente', 0, 3),
    (4, 'Gestante', 1, 4),
    (5, 'Grupos de risco', 1, 5);

-- A fila de cada aluno (no máximo uma). Quem coloca o aluno na fila é o professor (digita o próprio nome).
-- numero_atual: o número do treino da fila em que o aluno está (vazio = ainda não começou a fila).
-- definida_por, definida_em: o professor e o momento (UTC) em que o aluno foi colocado na fila.
-- liberacao_em, liberacao_por: só nas filas que exigem liberação: o dia ('AAAA-MM-DD') em que o professor conferiu
--   o atestado/triagem e o nome dele. É TUDO o que o app guarda: nem o atestado nem o motivo (dado de saúde).
CREATE TABLE IF NOT EXISTS aluno_fila (
    aluno_id      INTEGER PRIMARY KEY REFERENCES aluno(id),
    fila_id       INTEGER NOT NULL REFERENCES fila(id),
    numero_atual  INTEGER CHECK (numero_atual IS NULL OR numero_atual BETWEEN 1 AND 99),
    definida_por  TEXT    NOT NULL CHECK (length(definida_por) BETWEEN 1 AND 60),
    definida_em   TEXT    NOT NULL DEFAULT (datetime('now')),
    liberacao_em  TEXT    CHECK (liberacao_em IS NULL OR liberacao_em GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    liberacao_por TEXT    CHECK (liberacao_por IS NULL OR length(liberacao_por) BETWEEN 1 AND 60)
);

-- ------------------------------------------------------------ treinos padrão
-- Um treino pronto (fichas e exercícios) que o professor copia para um aluno pelo botão "Importar
-- treino" da tela de lançar treino. Copiar NÃO liga o aluno ao padrão: depois de copiado, o treino do
-- aluno é só dele (mexer ou apagar o padrão não muda os treinos que já foram copiados).
-- nome: até 40 letras, como o do treino; não repete (sem diferença de maiúscula/minúscula).
-- montado_por: o professor que montou (até 60 letras).
-- sessoes_por_ficha: a meta "treinos por ficha" que vem junto na cópia (vazio = sem meta).
-- conteudo: JSON {"fichas": [{"nome", "itens": [{"exercicio_id", "series", "repeticoes", "carga",
--   "pausa" (segundos), "observacao", "bloco"}]}]}: o mesmo desenho do pedido de salvar treino, já conferido
--   (app/modelos.py). Guarda só o id do exercício; na hora de copiar, o app confere se ele ainda está ativo.
-- criado_em: UTC.
-- fila_id, numero: o lugar do treino padrão numa fila numerada ("Mulher, Treino 3"); os dois vazios = treino padrão
-- solto, sem fila. Cada número aparece uma vez por fila (índice ux_modelo_fila_numero). Não mudam depois de guardados.
CREATE TABLE IF NOT EXISTS modelo_treino (
    id                INTEGER PRIMARY KEY,
    nome              TEXT    NOT NULL CHECK (length(nome) BETWEEN 1 AND 40),
    montado_por       TEXT    NOT NULL CHECK (length(montado_por) BETWEEN 1 AND 60),
    sessoes_por_ficha INTEGER CHECK (sessoes_por_ficha IS NULL OR sessoes_por_ficha BETWEEN 1 AND 999),
    conteudo          TEXT    NOT NULL,
    criado_em         TEXT    NOT NULL DEFAULT (datetime('now')),
    fila_id           INTEGER REFERENCES fila(id),
    numero            INTEGER CHECK (numero IS NULL OR (numero BETWEEN 1 AND 99 AND fila_id IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_modelo_treino_nome ON modelo_treino(nome COLLATE NOCASE);
CREATE UNIQUE INDEX IF NOT EXISTS ux_modelo_fila_numero ON modelo_treino(fila_id, numero) WHERE fila_id IS NOT NULL;

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

-- ------------------------------------------------------------ senha de administrador
-- Adicionar ou excluir um treino padrão só vale com a senha de administrador (ver app/administrador.py). A senha é
-- definida no terminal do servidor: python -m app.administrador definir-senha.
-- Uma linha só (id = 1). senha_hash: 'scrypt$N$r$p$sal$chave' (nunca a senha). definida_em: UTC.
CREATE TABLE IF NOT EXISTS senha_administrador (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    senha_hash  TEXT    NOT NULL,
    definida_em TEXT    NOT NULL
);

-- Cada senha de administrador errada. Serve para limitar tentativas (5 em 15 minutos).
CREATE TABLE IF NOT EXISTS senha_administrador_falha (
    id INTEGER PRIMARY KEY,
    em TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_senha_administrador_falha_em ON senha_administrador_falha(em);

-- ------------------------------------------------------------ treino sob medida (IA)
-- Cada vez que o professor pede um RASCUNHO de treino ao Claude (app/ia_treino.py). O rascunho nunca vira treino do aluno
-- sozinho: o professor confere na tela e salva como qualquer outro treino.
-- aluno_id: para quem foi pedido (um pedido só pode ser lido pelo mesmo aluno da tela).
-- dia: o dia de Brasília 'AAAA-MM-DD' do pedido (limite de pedidos por dia).
-- situacao: 'andando' (esperando a resposta), 'pronto' (resultado guardado) ou 'erro' (erro guarda o motivo em português).
-- resultado: o rascunho em JSON (formato da tela de montar) e, só nos rascunhos, a área `_retorno` (o contexto escolhido na tela e os sinais "já
-- avaliado" e "já registrado", ver `ia_retorno` abaixo). Nunca guarda o que o professor escreveu em "observações".
-- tokens_entrada / tokens_saida: o que a Anthropic informou ter usado (para acompanhar o gasto). Vazios se deu erro antes.
-- Os resultados são apagados depois de alguns dias (ia_treino.limpar_pedidos_antigos); a contagem do dia fica.
CREATE TABLE IF NOT EXISTS ia_pedido (
    id             INTEGER PRIMARY KEY,
    aluno_id       INTEGER NOT NULL REFERENCES aluno(id),
    criado_em      TEXT    NOT NULL,
    dia            TEXT    NOT NULL CHECK (dia GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    situacao       TEXT    NOT NULL CHECK (situacao IN ('andando', 'pronto', 'erro')),
    modelo         TEXT    NOT NULL,
    resultado      TEXT,
    erro           TEXT,
    tokens_entrada INTEGER CHECK (tokens_entrada IS NULL OR tokens_entrada >= 0),
    tokens_saida   INTEGER CHECK (tokens_saida IS NULL OR tokens_saida >= 0),
    terminado_em   TEXT
);
CREATE INDEX IF NOT EXISTS ix_ia_pedido_dia ON ia_pedido(dia);
CREATE INDEX IF NOT EXISTS ix_ia_pedido_aluno ON ia_pedido(aluno_id);

-- --------------------------------------------- o que o robô aprende com os professores (versão 15)
-- Duas coisas ficam registradas (app/ia_retorno.py), para o Thiago rever de tempos em tempos e propor regras novas à IA:
--   'avaliacao': o professor avaliou o rascunho da IA (serviu / serviu com ajustes / não serviu) e, se quis, escreveu o motivo.
--   'correcao':  o professor salvou um treino que veio de um rascunho da IA; `mudancas` guarda só a DIFERENÇA entre o rascunho e o treino
--                salvo (exercícios tirados e incluídos, séries/repetições/pausa mudadas), em JSON. Cargas e textos de observação NÃO entram.
-- De propósito NÃO há aluno, professor, número do pedido nem hora aqui, só o DIA: ninguém consegue saber de quem foi o treino.
-- Os campos de contexto são só categorias que o professor escolhe na tela (objetivo, nível, dias, minutos, nome da fila do aluno, ex.: "Mulher").
--   com_observacoes: 1 se o professor escreveu observações (o texto delas nunca é guardado). rodadas: quantas rodadas de perguntas a IA fez.
--   regras: identificador curto da versão das regras da IA (app/ia_treino.py) com que o rascunho foi feito; modelo: o modelo da IA.
--   motivo: texto livre do professor (até 300 letras; o app recusa nome do aluno, e-mail e números longos).
CREATE TABLE IF NOT EXISTS ia_retorno (
    id              INTEGER PRIMARY KEY,
    dia             TEXT    NOT NULL CHECK (dia GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    tipo            TEXT    NOT NULL CHECK (tipo IN ('avaliacao', 'correcao')),
    objetivo        TEXT    NOT NULL CHECK (length(objetivo) BETWEEN 1 AND 40),
    nivel           TEXT    NOT NULL CHECK (length(nivel) BETWEEN 1 AND 40),
    dias            INTEGER NOT NULL CHECK (dias >= 1),
    minutos         INTEGER NOT NULL CHECK (minutos >= 1),
    fila            TEXT    CHECK (fila IS NULL OR length(fila) BETWEEN 1 AND 60),
    com_observacoes INTEGER NOT NULL CHECK (com_observacoes IN (0, 1)),
    rodadas         INTEGER NOT NULL CHECK (rodadas BETWEEN 0 AND 9),
    regras          TEXT    NOT NULL CHECK (length(regras) BETWEEN 1 AND 40),
    modelo          TEXT    NOT NULL CHECK (length(modelo) BETWEEN 1 AND 80),
    nota            TEXT    CHECK (nota IS NULL OR nota IN ('serviu', 'com_ajustes', 'nao_serviu')),
    motivo          TEXT    CHECK (motivo IS NULL OR length(motivo) <= 300),
    mudancas        TEXT,
    CHECK (tipo <> 'avaliacao' OR nota IS NOT NULL),
    CHECK (tipo <> 'correcao' OR mudancas IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS ix_ia_retorno_dia ON ia_retorno(dia, tipo);

-- ------------------------------------------------- por que este treino foi montado assim (versão 16)
-- Quando o professor salva um treino que saiu de um rascunho da IA, o app guarda aqui, ligado ao treino, o que o robô recebeu e o que ele
-- respondeu (app/ia_historico.py), para qualquer professor consultar depois na ficha do aluno ("Por que este treino foi montado assim").
-- DIFERENTE de `ia_retorno` (que não liga nada ao aluno): aqui o texto é do aluno, inclusive saúde, e fica enquanto o treino existir.
--   objetivo, nivel, dias, minutos, fila: o que o professor escolheu na tela (fila = nome da fila do aluno, ex.: "Mulher", ou NULL).
--   observacoes: o texto que o professor escreveu para o robô ('' = nenhuma observação); conversa: JSON com as rodadas de perguntas do
--     robô e as respostas do professor (NULL = o robô não perguntou nada).
--   justificativa: JSON, lista de pontos que o próprio robô escreveu (divisão das fichas, quantidade de exercícios, séries, o que pesou).
--   alertas: JSON, lista dos avisos do robô ao professor (pode ser []).
--   ajustes: JSON com o que o professor mudou entre o rascunho e o treino salvo (app/ia_retorno.comparar). Mudanças feitas DEPOIS, em
--     "Editar treino", não entram aqui.
--   regras: versão das regras da IA (hash curto); modelo: o modelo da IA.
--   fichas_pedidas: quantas fichas DIFERENTES o professor pediu (0 = deixou o robô decidir; NULL = treino de antes da versão 17).
CREATE TABLE IF NOT EXISTS treino_ia (
    treino_id     INTEGER PRIMARY KEY REFERENCES treino(id) ON DELETE CASCADE,
    objetivo      TEXT    NOT NULL CHECK (length(objetivo) BETWEEN 1 AND 40),
    nivel         TEXT    NOT NULL CHECK (length(nivel) BETWEEN 1 AND 40),
    dias          INTEGER NOT NULL CHECK (dias >= 1),
    minutos       INTEGER NOT NULL CHECK (minutos >= 1),
    fila          TEXT    CHECK (fila IS NULL OR length(fila) BETWEEN 1 AND 60),
    observacoes   TEXT    NOT NULL DEFAULT '' CHECK (length(observacoes) <= 1000),
    conversa      TEXT,
    justificativa TEXT    NOT NULL,
    alertas       TEXT    NOT NULL,
    ajustes       TEXT    NOT NULL,
    regras        TEXT    NOT NULL CHECK (length(regras) BETWEEN 1 AND 40),
    modelo        TEXT    NOT NULL CHECK (length(modelo) BETWEEN 1 AND 80),
    fichas_pedidas INTEGER CHECK (fichas_pedidas IS NULL OR fichas_pedidas BETWEEN 0 AND 6)
);

-- ------------------------------------------------------- quando os alunos foram atualizados
-- Uma linha por assunto ('alunos' = a tela/robô que traz os alunos; 'treinos' = o histórico de treinos do Data4U),
-- sempre a ÚLTIMA cópia aplicada (app/importacoes.py). Serve só para avisar na tela quando a atualização parar.
-- extraido_em: quando o PC da recepção tirou a cópia do Data4U (UTC, como o resto do banco).
-- recebida_em: quando o app terminou de aplicá-la (UTC).
CREATE TABLE IF NOT EXISTS importacao (
    tipo        TEXT PRIMARY KEY CHECK (tipo IN ('alunos', 'treinos')),
    extraido_em TEXT NOT NULL CHECK (extraido_em GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]'),
    recebida_em TEXT NOT NULL CHECK (recebida_em GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]')
);

-- ------------------------------------------------------------------ login do aluno
-- O aluno entra pelo celular com CPF + senha (app/aluno_acesso.py). Na primeira vez, e quando esquece a senha, ele
-- pede um CÓDIGO de 6 números, que o app manda para o WhatsApp cadastrado (app/whatsapp.py), e cria a senha.
-- Nada aqui guarda senha, código ou cookie em texto: só hash. Datas em UTC, 'AAAA-MM-DD HH:MM:SS'.

-- A senha do aluno (uma por aluno). senha_hash: 'scrypt$N$r$p$sal$chave', o mesmo formato da senha de administrador.
CREATE TABLE IF NOT EXISTS aluno_senha (
    aluno_id    INTEGER PRIMARY KEY REFERENCES aluno(id),
    senha_hash  TEXT    NOT NULL,
    definida_em TEXT    NOT NULL
);

-- Cada código enviado. codigo_hash: SHA-256 de 'id do aluno:código'. Vale poucos minutos e só funciona uma vez.
-- tentativas: quantas vezes alguém tentou este código (passando de 5, ele morre). usado_em: preenchido quando o código é
-- usado ou trocado por um mais novo. envio: 'pendente' (ainda mandando), 'enviado' (a Meta aceitou) ou 'falhou' (envio_erro
-- diz o motivo, sem nenhum dado secreto). Os antigos são apagados depois de alguns dias.
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
);
CREATE INDEX IF NOT EXISTS ix_aluno_codigo_aluno ON aluno_codigo(aluno_id, criado_em);
CREATE INDEX IF NOT EXISTS ix_aluno_codigo_criado ON aluno_codigo(criado_em);

-- Um celular em que o aluno está logado. token_hash: SHA-256 do valor guardado no cookie. Como o computador autorizado
-- (`dispositivo`), mas é outra tabela de propósito: o cookie do aluno nunca abre a área do professor.
-- Fica sem uso por muito tempo = perde o acesso. Quando o aluno cria uma senha nova, todas as sessões antigas são revogadas.
CREATE TABLE IF NOT EXISTS aluno_sessao (
    id            INTEGER PRIMARY KEY,
    aluno_id      INTEGER NOT NULL REFERENCES aluno(id),
    token_hash    TEXT    NOT NULL UNIQUE,
    criado_em     TEXT    NOT NULL,
    ultimo_uso_em TEXT    NOT NULL,
    revogado_em   TEXT
);
CREATE INDEX IF NOT EXISTS ix_aluno_sessao_aluno ON aluno_sessao(aluno_id);

-- Pedidos de código e erros (senha errada, código errado), para limitar tentativas. chave: 'cpf:' ou 'ip:' + SHA-256 do
-- CPF ou do endereço (nunca o valor puro); vale também para CPF que não existe, para o limite não revelar quem é aluno.
-- Os eventos com mais de um dia são apagados.
CREATE TABLE IF NOT EXISTS aluno_evento (
    id    INTEGER PRIMARY KEY,
    tipo  TEXT    NOT NULL CHECK (tipo IN ('pedido_codigo', 'codigo_errado', 'login_errado')),
    chave TEXT    NOT NULL,
    em    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_aluno_evento ON aluno_evento(tipo, chave, em);

-- ------------------------------------------------------------------ comentários do aluno
-- O aluno comenta (tela /aluno) o treino INTEIRO ou UM exercício; o professor lê em "Comentários" e na ficha do aluno.
-- Âncora: o treino, o número da ficha (1 = A, 2 = B...) e o NOME do exercício, nunca o id do item da ficha: editar um treino
-- apaga e recria as fichas e os itens, e a atualização de alunos recopia os treinos do Data4U. Por isso o comentário guarda
-- também uma cópia dos nomes (treino_nome, ficha_nome, exercicio_nome): ele continua legível mesmo que o treino mude.
--   treino_id: some (vira NULL) se o treino for apagado (treino do Data4U que saiu de lá); o comentário NÃO se perde.
--   ficha_ordem, ficha_nome, exercicio_nome: os três vazios = comentário do treino inteiro; os três preenchidos = de um exercício.
--   texto: o que o aluno escreveu (1 a 500 letras). Sempre tratado como TEXTO, nunca como HTML.
--   criado_em, lido_em: UTC. lido_em vazio = ainda não lido por nenhum professor (o app não tem login por professor).
--   resposta, respondido_por, respondido_em, resposta_vista_em: a resposta do professor (segunda entrega) e quando o aluno a viu.
-- Só se cria e se marca como lido; apagar não existe (o histórico do que o aluno disse fica). Apagar o aluno é recusado.
CREATE TABLE IF NOT EXISTS comentario (
    id                 INTEGER PRIMARY KEY,
    aluno_id           INTEGER NOT NULL REFERENCES aluno(id),
    treino_id          INTEGER REFERENCES treino(id) ON DELETE SET NULL,
    treino_nome        TEXT    NOT NULL CHECK (length(treino_nome) BETWEEN 1 AND 40),
    ficha_ordem        INTEGER CHECK (ficha_ordem IS NULL OR ficha_ordem >= 1),
    ficha_nome         TEXT    CHECK (ficha_nome IS NULL OR length(ficha_nome) BETWEEN 1 AND 15),
    exercicio_nome     TEXT    CHECK (exercicio_nome IS NULL OR length(exercicio_nome) >= 1),
    texto              TEXT    NOT NULL CHECK (length(texto) BETWEEN 1 AND 500),
    criado_em          TEXT    NOT NULL,
    lido_em            TEXT,
    resposta           TEXT    CHECK (resposta IS NULL OR length(resposta) BETWEEN 1 AND 500),
    respondido_por     TEXT    CHECK (respondido_por IS NULL OR length(respondido_por) BETWEEN 1 AND 60),
    respondido_em      TEXT,
    resposta_vista_em  TEXT,
    CHECK ((ficha_ordem IS NULL) = (ficha_nome IS NULL) AND (ficha_ordem IS NULL) = (exercicio_nome IS NULL)),
    CHECK ((resposta IS NULL) = (respondido_por IS NULL) AND (resposta IS NULL) = (respondido_em IS NULL))
);
CREATE INDEX IF NOT EXISTS ix_comentario_aluno ON comentario(aluno_id, criado_em);
-- Apagar um treino (o importador do Data4U faz isso) solta o vínculo dos comentários dele (ON DELETE SET NULL): sem
-- este índice o SQLite varreria a tabela inteira a cada treino apagado.
CREATE INDEX IF NOT EXISTS ix_comentario_treino ON comentario(treino_id);
-- Os não lidos são poucos: a lista e o contador do menu leem só este índice.
CREATE INDEX IF NOT EXISTS ix_comentario_nao_lidos ON comentario(criado_em) WHERE lido_em IS NULL;

-- ------------------------------------------------------------------ o que o aluno faz durante o treino (versão 14)
-- Na tela /aluno o aluno marca cada exercício como feito e anota a carga que usou. Uma linha por aluno, por DIA (calendário
-- de Brasília), por exercício. A linha só existe se algo foi marcado: desmarcar o "feito" e apagar a carga apaga a linha.
-- Âncora: o número da ficha (1 = A, 2 = B...), o NOME do exercício e a ocorrência do nome na ficha (1 = a primeira vez que esse nome
-- aparece nela, 2 = a segunda...), nunca o id do item: editar um treino apaga e recria fichas e itens. Por NOME e não por posição
-- porque o professor pode incluir, tirar ou trocar um exercício no meio do dia e as posições andam: o que o aluno já anotou do
-- exercício que ficou continua valendo e o que ele anotou do exercício que saiu não se perde. O nome também serve de chave para a
-- "última vez" (a carga que o aluno anotou no MESMO exercício em outro dia, mesmo que o treino tenha mudado). Por isso não há ligação
-- com `treino`.
--   exercicio_ordem: a posição do exercício na ficha no momento da última gravação (só informativa, não é chave).
--   dia: 'AAAA-MM-DD' em Brasília. Passou o dia, o "feito" deixa de valer (a carga vira a "última vez").
--   carga: o que o aluno digitou, em kg (ex.: '12,5'); vazio = não anotou. Só números, vírgula e no máximo 2 casas (o app confere).
--   atualizado_em: UTC.
-- Apagar o aluno é recusado (não se perde o que ele anotou sem querer).
CREATE TABLE IF NOT EXISTS execucao (
    id              INTEGER PRIMARY KEY,
    aluno_id        INTEGER NOT NULL REFERENCES aluno(id),
    dia             TEXT    NOT NULL CHECK (dia GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    ficha_ordem     INTEGER NOT NULL CHECK (ficha_ordem >= 1),
    exercicio_ordem INTEGER NOT NULL CHECK (exercicio_ordem >= 1),
    exercicio_nome  TEXT    NOT NULL CHECK (length(exercicio_nome) >= 1),
    ocorrencia      INTEGER NOT NULL DEFAULT 1 CHECK (ocorrencia >= 1),
    feito           INTEGER NOT NULL DEFAULT 0 CHECK (feito IN (0, 1)),
    carga           TEXT    CHECK (carga IS NULL OR length(carga) BETWEEN 1 AND 9),
    atualizado_em   TEXT    NOT NULL,
    CHECK (feito = 1 OR carga IS NOT NULL),
    UNIQUE (aluno_id, dia, ficha_ordem, exercicio_nome, ocorrencia)
);
-- A pergunta mais frequente: "qual foi a última carga deste aluno neste exercício?" (cada ficha aberta faz uma por exercício).
CREATE INDEX IF NOT EXISTS ix_execucao_exercicio ON execucao(aluno_id, exercicio_nome, dia);

-- ------------------------------------------------------------------ foto do aluno (versão 19)
-- A foto que a recepção tirou no Data4U (cadastro da catraca), reduzida a uma miniatura, só para o professor reconhecer o aluno nas
-- telas do computador autorizado. Vem do PC da recepção no envio diário (app/fotos.py). Nunca aparece no app do aluno nem em página aberta.
--   miniatura: JPEG quadrado pequeno, refeito no servidor a partir da foto original (a original não é guardada).
--   origem_sha256: o "resumo" da foto original; o PC da recepção compara e só manda de novo a foto que mudou.
--   atualizada_em: quando a miniatura foi gravada (UTC). vista_em: a última vez que o envio diário confirmou que o aluno continua ativo
--   e com foto (UTC). Passados 90 dias sem confirmação (o aluno saiu), a foto é apagada.
-- Nada além da imagem: o dado de reconhecimento facial do Data4U (biometria) NUNCA vem para cá.
CREATE TABLE IF NOT EXISTS foto_aluno (
    aluno_id       INTEGER PRIMARY KEY REFERENCES aluno(id) ON DELETE CASCADE,
    miniatura      BLOB    NOT NULL CHECK (length(miniatura) BETWEEN 100 AND 60000),
    origem_sha256  TEXT    NOT NULL CHECK (length(origem_sha256) = 64 AND origem_sha256 NOT GLOB '*[^0-9a-f]*'),
    atualizada_em  TEXT    NOT NULL,
    vista_em       TEXT    NOT NULL
);
