# App Glória Fit

App de treinos da Academia Glória Fit. Hoje tem estas camadas prontas:

1. **Banco de dados** (SQLite) + importação do quadro de 1.161 exercícios.
2. **Servidor web** (Flask) com a lista de exercícios da tela do professor: busca por nome
   (sem diferenciar acento nem maiúscula) e filtro por grupo muscular.
3. **Tela "Lançar treino"** (`/alunos/<id>/montar`), no jeito do Data4U (palavras e fluxo que os
   professores já conhecem, visual mais atual): o **Treino** tem nome e **Professor** no alto, as
   **fichas** (FICHA A, B, C... ou o nome que o professor der, até 15 letras) são abas, e cada ficha
   é uma tabela de exercícios com séries, repetições, **Peso** (no banco e na API o campo continua
   `carga`), **Intervalo** (minutos : segundos; vai ao servidor em segundos, campo `pausa`) e
   **Observações** (texto, até 200 letras), bi-set e tri-set, conferência dos limites do Data4U. A lista de exercícios fica ao lado
   (busca por nome; "Parte do corpo" recolhido). No alto também ficam **Início** (vem com a data de hoje),
   **Fim** (opcional) e **Treinos por ficha** (opcional: quantas vezes o aluno faz cada ficha no ciclo), e, se o aluno já tem
   um treino ativo, o aviso de que ele será concluído ao salvar. O rascunho (fichas, nome, professor, datas e meta) fica no
   navegador até salvar.
4. **Salvar treino**: um só botão, **Salvar treino**, sempre à vista no rodapé. O nome do treino vem
   sugerido (ex.: "TREINO ABC 07/10/26") e acompanha as fichas até o professor mexer nele; o
   **Professor** é digitado pelo próprio professor (obrigatório, não vem preenchido). Quem tenta
   sair com algo digitado vê **um** aviso ("Descartar este treino sem salvar?"). O treino é gravado
   no banco com esse nome. Treinos montados no futuro por robô/Claude levam `Academia Glória Fit`
   (constante `AUTOR_AUTOMATICO`). (Antes havia uma segunda tela só para salvar; foi retirada em
   08/10/2026 a pedido do Thiago.)
5. **Buscar aluno** (`/alunos`, a página inicial) e **ficha do aluno** (`/alunos/<id>`):
   a busca acha por nome (palavras em qualquer ordem, sem diferenciar acento nem maiúscula),
   por CPF (ou um pedaço dele) ou por matrícula (número igual). A lista mostra matrícula, último
   treino e a **situação** (Ativo, Trancado, Pendente, Desistente, Inativo, Cancelado, ou
   Provisório). A ficha mostra os treinos numa **tabela** (Treino, Data, Fichas, Professor; mais novo primeiro). O
   mais recente vem aberto, com o selo "Mais recente" (é só o mais novo por data, não quer dizer
   "treino ativo"); os antigos abrem com um clique. Botão **Lançar treino**, WhatsApp do aluno
   (editável) e cadastro (CPF, matrícula, situação).
   **Aluno provisório** (`/alunos/novo`): para quem se matriculou hoje e ainda não está na cópia
   do Data4U. O professor digita nome, CPF e WhatsApp (opcional) e já monta o treino. O app
   confere o CPF (11 números e os dois dígitos verificadores) e recusa CPF que já esteja no app.
6. **Importar alunos do Data4U** (`python -m app.importar_alunos`): lê a cópia diária
   (`base_total.zip`) e põe no app toda pessoa física, não apagada, que tenha situação no
   Data4U (hoje 5.496). A **matrícula é o `ID` da pessoa no Data4U** (conferido pelo Thiago em
   07/10/2026). Rodar de novo atualiza quem já existe e acrescenta quem é novo. Quando a pessoa
   aparece pela primeira vez e há um aluno provisório com o **mesmo CPF**, os dois são juntados
   (o treino continua com o aluno).
   **Tela "Atualizar alunos"** (`/alunos/atualizar`, no menu): no PC da recepção, a pessoa escolhe
   o `base_total.zip` (pasta NFSE). **O navegador abre o `.zip` no próprio computador**, confere a
   cópia contra o `_manifesto.json` (data, número de linhas, colunas), mostra de quando ela é e,
   só ao clicar em "Enviar e atualizar alunos", manda ao servidor **apenas 3 tabelas e apenas as
   colunas usadas** (nome, CPF, situação, celular; nada de RG, nascimento, e-mail, pagamentos...).
   O servidor confere o pacote de novo (colunas exatamente iguais às esperadas, tipos dos valores,
   cópia de no máximo 5 dias) e grava tudo ou nada. A resposta traz só contagens, nunca nome ou CPF.
   Enviar de novo não duplica ninguém. O `base_total.zip` inteiro **nunca chega ao servidor**.
7. **Imprimir o treino** (`/treinos/<id>/imprimir`): cupom para a impressora térmica (Bematech
   MP-4200 TH, papel de 80 mm) no formato do desenho: academia, aluno, treino, data, professor e,
   por ficha, os exercícios com etiqueta (A1, A2 de bi-set; 3, 4... dos soltos), séries X
   repetições, carga, "INTERVALO: 1 MIN 30 S", "OBS: ..." (só quando existem) e o aviso
   "BI-SET: FAÇA A1 E A2 SEGUIDOS". O botão **Imprimir na térmica**
   aparece depois de salvar o treino; em cada treino da ficha do aluno o link se chama **Visualizar e imprimir**. **Testado em 07/10/2026
   na impressora do PC dos professores: imprimiu certo** (segundo o Thiago; ver "Ainda em aberto").
8. **Proteção da área do professor**: só **computadores autorizados** abrem as telas e a API
   (hoje serão dois: o dos professores e o da recepção). Cada um é autorizado uma vez, com um
   **código de uso único** gerado no servidor (`python -m app.dispositivos`), e passa a ser
   reconhecido por um cookie. Quem abrir o endereço em outro aparelho cai na tela
   `/autorizar` e não vê dado nenhum.
9. **Histórico de treinos do Data4U** (versão 5 do banco): a mesma tela "Atualizar alunos" também copia
   para o app **todos os treinos antigos de todos os alunos** (hoje cerca de 6.200, com fichas e
   exercícios), para o professor ver na ficha o que o aluno já fez. O navegador manda ao servidor só
   as tabelas do treino (`TREINO`, `TREINO_FICHA`, `TREINO_PRESCRICAO`, `TREINO_EXERCICIO`), os
   lançamentos que ligam treino a aluno e o nome dos professores que montaram treino. O app **espelha**
   o Data4U: cada treino é identificado por `treino.data4u_id`; mandar de novo atualiza o que mudou,
   acrescenta o novo e remove o que sumiu de lá, **sem nunca mexer em treino montado no app**
   (`origem = 'app'`). Na ficha, os treinos antigos levam o selo "Data4U"; dose, carga, pausa e
   observação aparecem. Treino do histórico também pode ser impresso. Detalhes e limites em
   "Histórico de treinos: como funciona" abaixo.

## O que tem

| Arquivo | Para quê |
|---|---|
| `app/schema.sql` | Desenho das tabelas (versão 6): exercícios, grupos musculares, alunos (CPF pode ficar vazio; `situacao`; `data4u_id` = matrícula), treinos (com `montado_por`, `origem` app/data4u, `data4u_id`, `ativo`, `inicio`, `fim`, `concluido_em` e `sessoes_por_ficha`), fichas e itens (com pausa e observação), `sessao` (cada vez que o aluno treinou uma ficha) e os computadores autorizados (`codigo_de_autorizacao`, `dispositivo`, `autorizacao_falha`). Não há tabela de professores: o nome é digitado a cada treino |
| `app/db.py` | Abre o banco (liga as chaves estrangeiras, ensina o SQL a comparar sem acento), cria as tabelas, **atualiza banco da versão 4 ou 5 até a 6 sozinho** (`migrar`, com cópia de segurança antes) e recusa arquivo de versão que não conhece |
| `app/importar_exercicios.py` | Lê a planilha `dados/quadro_exercicios_v2.xlsx` e grava no banco |
| `app/texto.py` | `normalizar`: minúsculas e sem acento ("Bíceps" → "biceps") |
| `app/exercicios.py` | Consultas: grupos e busca de exercícios |
| `app/alunos.py` | Busca de alunos (nome, CPF ou matrícula), ficha com os treinos salvos e o histórico do Data4U, e correção do WhatsApp (valida e grava) |
| `app/importar_alunos.py` | Lê a cópia diária do Data4U (só 3 tabelas: `PESSOA`, `PESSOA_STATUS`, `CONTATO_PESSOA`), confere se está inteira (manifesto) e grava os alunos, tudo ou nada. Imprime um relatório só com contagens |
| `app/importar_treinos.py` | Recebe o pacote do histórico de treinos, confere colunas e tipos, e espelha no banco (acrescenta, atualiza, remove; nunca toca em treino do app). Tudo ou nada; devolve só contagens. Aceita `"simular": true` (faz tudo e desfaz) |
| `app/backup.py`, `app/backup_agendado.py` | Cópia segura do banco (à mão) e o agendador que a faz todo dia às 03:00, guardando 30 cópias |
| `app/provisorios.py` | Aluno provisório: valida nome e CPF (dígitos verificadores) e cadastra, recusando CPF que já exista (a conferência e a gravação são um comando só no SQLite, então dois pedidos juntos não passam os dois) |
| `app/cupom.py` | Monta o conteúdo do cupom do treino (linhas, etiquetas, avisos de bi-set/tri-set); o desenho fica em `templates/imprimir.html` e `static/imprimir.css` |
| `app/treinos.py` | Salvar e ler treinos: confere tudo de novo no servidor e grava tudo-ou-nada (inclui início, fim, meta e a conclusão do treino ativo anterior) |
| `app/ciclo.py` | O ciclo do treino: concluir, reativar, registrar sessão (só testes por enquanto), contar o andamento e decidir o aviso "hora de trocar o treino" |
| `app/datas.py` | Fuso de Brasília: dia local de um momento em UTC, "hoje", leitura rigorosa de `AAAA-MM-DD` |
| `app/acesso.py` | Computadores autorizados: gera o código de uso único, troca o código por um cookie, reconhece o computador, revoga, limita tentativas erradas. O banco guarda só o hash (SHA-256) do código e do cookie |
| `app/dispositivos.py` | Comando do servidor: `codigo --nome "..."` (gera o código), `listar`, `revogar <número>` |
| `app/web.py` | O servidor: páginas e rotas da API (tabela "Rotas" abaixo) e a guarda que barra quem não é computador autorizado |
| `app/templates/`, `app/static/` | Páginas, estilo e JavaScript |
| `app/static/zip_leitor.js` | Lê o `.zip` no navegador sem biblioteca: acha uma entrada pelo índice e descompacta só ela (deflate ou sem compressão); recusa senha, ZIP64, arquivo cortado, tamanho que não bate e "bomba de zip" |
| `app/static/copia_modelo.js` | Prepara o que a tela "Atualizar alunos" envia, em dois pacotes (alunos e treinos): confere o manifesto, reduz às colunas necessárias, só celular (tipo 30), CPF/telefone como texto; envia um depois do outro; textos de aviso e leitura da resposta do servidor |
| `app/static/atualizar_alunos.js` | A tela em si (escolher arquivo, mostrar resumo, enviar os dois pacotes, mostrar o relatório). Usa só `textContent`. Com `?simular_treinos=1` na página, o histórico é só simulado |
| `app/static/treino_modelo.js` | Lógica do treino (fichas, bi-set, validação, rascunho, nome sugerido, pedido de salvar), sem nada de tela |
| `app/static/montar.js`, `salvar.js`, `biblioteca.js` | Desenho da tela Lançar treino (nome, professor, fichas, tabela), envio do treino ao servidor e lista de exercícios |
| `app/static/api.js` | `enviarJson`: envia um POST em JSON com limite de tempo (20 s) e devolve status + corpo; usado por salvar treino e WhatsApp |
| `app/static/autorizar.js`, `autorizar_modelo.js` | Tela `/autorizar`: envia o código e mostra a resposta (o texto de cada resposta fica em `autorizar_modelo.js`, testado à parte) |
| `app/static/novo_aluno.js`, `novo_aluno_modelo.js` | Tela `/alunos/novo`: envia o cadastro e mostra erros por campo ou os links de quem já tem o CPF (o que mostrar para cada resposta fica em `novo_aluno_modelo.js`, testado à parte) |
| `app/static/alunos.js`, `ficha.js` | Busca de alunos (espera 200 ms depois de digitar e cancela a busca anterior) e a edição do WhatsApp na ficha |
| `app/static/ciclo_ficha.js` | Botões **Concluído** (com confirmação) e **Reativar** da ficha do aluno |
| `tests/` | Testes do Python (pytest). `schema_v4.sql` e `schema_v5.sql` são cópias dos desenhos antigos, usadas para provar as migrações; `test_contrato_js_python.py` roda o JavaScript (Node) e entrega o pacote dele ao servidor |
| `tests_js/` | Testes do JavaScript (Vitest) |

## Como rodar

```bash
pip install -r requirements-dev.txt
python -m pytest                                          # testes do Python
npm install && npm test                                   # testes do JavaScript (Vitest)

# 1) cria o banco com os exercícios (pode repetir sem duplicar nada)
python -m app.importar_exercicios dados/quadro_exercicios_v2.xlsx app.db

# 1b) importa os alunos da cópia do Data4U (pode repetir: atualiza e acrescenta, não duplica)
python -m app.importar_alunos /caminho/base_total.zip app.db

# 2) sobe o servidor, SÓ para uso na sua máquina
GLORIAFIT_DB=app.db python -m flask --app "app.web:criar_app" run --debug

# 3) autoriza o computador (uma vez por computador; cada um com o seu código e o seu nome)
python -m app.dispositivos --banco app.db codigo --nome "Computador dos professores"
python -m app.dispositivos --banco app.db codigo --nome "Computador da recepção"
# abra http://127.0.0.1:5000/autorizar no computador e digite o código (vale 15 min, uso único);
# depois disso http://127.0.0.1:5000/ abre a busca de alunos (a lista de exercícios: /exercicios)

python -m app.dispositivos --banco app.db listar         # computadores autorizados e situação
python -m app.dispositivos --banco app.db revogar 2      # tira o acesso do computador número 2
```

`--debug` é só para desenvolvimento: num servidor aberto à internet ele liberaria um
console que executa código de quem acessar. Em produção o servidor é outro: gunicorn, dentro
do Docker (ver "Publicação" abaixo).

## Publicação (servidor)

O app roda num contêiner Docker (`Dockerfile`), atrás do Traefik, que cuida do HTTPS.

| Variável | Para quê |
|---|---|
| `GLORIAFIT_DB` | Onde fica o banco (na imagem: `/dados/app.db`, que deve ser um volume) |
| `GLORIAFIT_ATRAS_DE_PROXY=1` | Confia no Traefik para saber o endereço e o `https` reais. **Só pode ficar ligada se o app não for alcançável sem passar pelo proxy** (senão qualquer um poderia mentir o próprio endereço) |
| `GLORIAFIT_DOMINIO` | Único endereço aceito (ex.: `app.exemplo.com.br`); pedidos para outro nome são recusados |
| `GLORIAFIT_PROCESSOS` | Quantos processos do gunicorn (padrão 2) |

- `deploy/docker-compose.yml` é a receita para colar no Gerenciador Docker da Hostinger (endereço
  `app.gloriafit.com.br`, etiquetas do Traefik copiadas do jeito que o servidor já usa, banco e cópias
  em volumes, **sem abrir porta**). A imagem é construída pelo GitHub (`.github/workflows/imagem.yml`:
  roda os testes, constrói e publica em `ghcr.io/academiagloriafit/gloriafit-app`) e o servidor só a baixa.
  Para atualizar o app: trocar a etiqueta da imagem pelo commit novo e clicar em Implantar.
- O banco novo é criado na primeira subida (tabelas + exercícios). Banco existente nunca é apagado.
- SQLite em modo WAL com espera de 5 s por trava: vários processos podem usar o mesmo arquivo.
- Cabeçalho `Strict-Transport-Security` de 1 semana quando a conexão é HTTPS (subir para 1 ano
  quando estiver tudo funcionando, porque o navegador "lembra" e não deixa mais abrir por HTTP).
- O registro de acessos do gunicorn grava método, caminho, código e tempo, **sem** o que vem depois
  do `?` (a busca de aluno pode levar CPF).
- Cópia de segurança, à mão: `python -m app.backup /dados/app.db /backups` (usa a cópia segura do
  próprio SQLite, confere a integridade e guarda as 14 últimas). Convém fazer uma antes de cada
  atualização do app.
- **Cópia de segurança diária, sozinha** (`app/backup_agendado.py`, serviço `backup` do compose, mesma
  imagem do app): uma por dia às 03:00 de Vila Velha, guarda as **30 mais novas** em `/backups`. Ao
  ligar, se a cópia mais nova tem mais de 20 h, faz uma na hora; se uma falhar, escreve
  `BACKUP FALHOU` no registro do contêiner e tenta de novo em 1 h. Se passar de 30 h sem cópia nova,
  o Docker marca o contêiner `backup` como "unhealthy" no painel. **Decisão do Thiago (07/10/2026):
  as cópias ficam só no servidor.** Isso protege contra erro (apagar aluno sem querer, banco
  quebrado), **não** contra perder o servidor inteiro; para isso existe só o backup semanal do VPS
  na Hostinger. A etiqueta da imagem está nos **dois** serviços do compose: trocar nos dois.
  **Restaurar ainda não foi ensaiado no servidor.** A cópia é um arquivo SQLite comum (testes abrem
  uma cópia e leem os dados); os passos de restauração no servidor ficam para testar com calma.
- Autorizar os computadores no servidor: no painel da Hostinger, Gerenciador Docker, projeto `gloriafit-app`,
  link **Terminal** (abre um shell dentro do contêiner do app), e lá
  `python -m app.dispositivos codigo --nome "..."`. O código vale 15 minutos e só funciona uma vez:
  gere-o com a pessoa já diante do computador, que abre `https://app.gloriafit.com.br/autorizar`.
- **Verificação de saúde** (`deploy/healthcheck.py`): precisa mandar o endereço do app no cabeçalho
  `Host`. Com o Host padrão (`127.0.0.1`) o app a recusava (400), o Docker marcava o contêiner como
  "doente" e o Traefik o ignorava: o site ficava com certificado de erro. Há testes travando isso.
- No ar desde 07/10/2026 em https://app.gloriafit.com.br (conferido: certificado válido, HSTS, CSP,
  API sem autorização responde 401, `/` redireciona para `/autorizar`).

## Rotas

| Rota | O que devolve |
|---|---|
| `GET /autorizar` | Tela onde se digita o código. **Pública.** Quem já está autorizado é levado para `/alunos` |
| `POST /api/autorizar` | **Pública.** Corpo JSON: `{"codigo": "ABCDE-23456"}` (aceita minúsculas, espaço, sem hífen). `200 {"ok": true, "nome": "..."}` e o cookie do computador; `400` código inválido ou vencido (a mensagem é a mesma para errado, já usado e vencido); `429` depois de 5 códigos errados seguidos (trava as tentativas por até 15 min, para qualquer aparelho; computadores já autorizados não são afetados); `415` não é JSON |
| `GET /` | Leva para `/alunos` |
| `GET /alunos` | A página de buscar aluno |
| `GET /treinos/<id>/imprimir` | O cupom do treino para a térmica (404 se não existe), com o botão Imprimir |
| `GET /alunos/novo` | A tela de cadastrar aluno provisório |
| `POST /api/alunos` | Cadastra aluno provisório. Corpo JSON: `nome`, `cpf`, `whatsapp` (opcional). Devolve `201 {"id": N}`; `400 {"erros": {campo: mensagem}}` (nome, cpf ou whatsapp inválido); `409 {"erro", "existentes": [{id, nome, provisorio, situacao_nome}]}` o CPF já está no app; `413`; `415` |
| `GET /api/alunos?q=&limite=` | `{"total": N, "alunos": [{id, nome, provisorio, matricula, situacao, situacao_nome, ultimo_treino, atualizado_em}]}`. `q`: nome (palavras em qualquer ordem) ou só números = pedaço do CPF **ou** matrícula igual (a matrícula vem primeiro); com texto, quem está em uso (ativo, trancado, pendente, provisório) vem antes dos demais; sem `q`, vem primeiro quem tem treino salvo (o mais recente), depois provisórios sem treino, depois o resto. `limite`: 1 a 200 (padrão 50). **Não devolve CPF nem WhatsApp** |
| `GET /alunos/<id>` | A ficha do aluno (404 se não existe) |
| `POST /api/alunos/<id>/whatsapp` | Corrige o WhatsApp. Corpo JSON: `whatsapp` (10 ou 11 algarismos com DDD; aceita espaço, parênteses, ponto e hífen; **sem +55**). Devolve `200 {"whatsapp": "(27) 98888-7766"}`; `400 {"erro"}`; `404`; `415`. Marca o número como corrigido no app (a cópia diária do Data4U não pode mais sobrescrevê-lo) |
| `GET /alunos/atualizar` | A tela "Atualizar alunos" (a recepção escolhe o `base_total.zip`). Com `?simular_treinos=1` mostra "MODO TESTE" e o histórico de treinos não é gravado |
| `POST /api/alunos/importar` | Recebe o pacote de alunos montado pelo navegador (até 25 MB; só esta rota e a de treinos aceitam isso, as demais param em 512 KB). `200` com contagens; `400 {"erro"}` se o pacote não serve (nada é gravado) |
| `POST /api/treinos/importar` | Recebe o pacote do histórico de treinos. `200 {"extraido_em", "simulado", "treinos", "novos", "atualizados", "removidos", "texto"}` (só contagens, nunca nome ou CPF); `400 {"erro"}`. Com `"simular": true` no pacote roda tudo e desfaz |
| `GET /exercicios` | A página da lista de exercícios |
| `GET /api/grupos` | Os 15 grupos, na ordem do quadro, com a quantidade de exercícios de cada |
| `GET /api/exercicios?q=&grupo=&limite=` | `{"total": N, "exercicios": [...]}`. `q`: palavras do nome; `grupo`: id do grupo; `limite`: 1 a 200 (padrão 50) |
| `GET /alunos/<id>/montar` | Tela de montar treino do aluno (404 se o aluno não existe) |
| `POST /api/alunos/<id>/treinos` | Grava um treino. Corpo JSON: `nome_treino`, `montado_por`, `inicio` (`AAAA-MM-DD`, vazio = hoje), `fim` (opcional, não pode ser antes do início), `sessoes_por_ficha` (opcional, 1 a 999), `fichas` (cada uma com `nome` e `itens`: `exercicio_id`, `series`, `repeticoes`, `carga`, `pausa`, `observacao`, `bloco`). Se o aluno já tinha treino ativo, ele é concluído na mesma gravação. Devolve `201 {"id": N, "concluido_anterior": "NOME" ou null}`; `400 {"erros": [...]}` dado inválido; `404` aluno inexistente; `409` o aluno já tem treino com esse nome; `413` pedido grande demais (> 512 KB); `415` não é JSON |
| `POST /api/treinos/<id>/concluir` | Botão "Concluído": o treino vira inativo (guarda `concluido_em`). Corpo JSON `{}`. `200 {"ok": true}`; `404`; `409` já está concluído; `415` |
| `POST /api/treinos/<id>/reativar` | Desfaz o "Concluído". `200 {"ok": true}`; `404`; `409` já está ativo, ou o aluno já tem outro treino ativo (a mensagem diz qual); `415` |
| `GET /saude` | `{"ok": true}` se o app está de pé e enxerga o banco. **Pública** |

**Todas as rotas acima, menos `/autorizar`, `/api/autorizar`, `/saude` e os arquivos de
`/static`, exigem computador autorizado.** Sem a autorização, as páginas respondem `302` para
`/autorizar` e a API responde `401 {"erro": "..."}` (a mesma resposta exista o aluno ou não, para
não dar para descobrir ids). Rota nova nasce protegida: a lista de rotas públicas
(`ENDPOINTS_PUBLICOS` em `app/web.py`) é que precisa ser aumentada de propósito, e um teste
percorre todas as rotas do app para garantir isso. Páginas e API respondem com
`Cache-Control: no-store` (o navegador não guarda cópia de nome e CPF de aluno).

Número inválido em `grupo` ou `limite` devolve erro 400 em JSON.

O servidor **confere tudo de novo** ao salvar (a tela também confere, mas o navegador não é
confiável): limites do Data4U (nome do treino 40, nome da ficha 15, séries/repetições/carga 11),
séries e repetições obrigatórias, intervalo (`pausa`) de 0 a 3.599 s, observação até 200 letras, exercício existente e ativo, bi-set de 2 e tri-set de 3
exercícios juntos, `montado_por` obrigatório (até 60), sem caracteres de controle. O nome do
treino é único por aluno, sem diferenciar maiúscula nem acento (regra do Data4U).

## Ciclo do treino: como funciona

Pedido do Thiago em 08/10/2026 (decisões dele, uma a uma):

- **Um treino ativo por aluno.** O banco garante (índice `ux_treino_ativo_por_aluno`). Os outros ficam **inativos**: são o
  histórico que o professor consulta. **Quando existir o app do aluno, ele só pode mostrar o treino ativo** (`ativo = 1`).
- **Concluído:** o professor clica no botão (com confirmação) e o treino vira inativo; guarda quando (`concluido_em`). **Reativar**
  desfaz, mas só se o aluno não tem outro ativo.
- **Lançar um treino novo conclui o ativo** na mesma gravação (a tela avisa antes, em cima, e depois, na tela "Treino salvo").
- **Início e fim:** `inicio` (padrão: hoje) e `fim` (opcional) são dias do calendário de Brasília. O Data4U guarda "sem fim" como
  07/07/7777; aqui é simplesmente vazio e aparece "–".
- **Treinos por ficha** (`sessoes_por_ficha`, opcional): "15" = o aluno faz a ficha A 15 vezes, a B 15 vezes, a C 15 vezes.
  A coluna **Sessões** mostra feitas / meta de todas as fichas (ex.: `7 / 45`) e cada ficha mostra `x / 15 treinos`.
- **Aviso "hora de trocar o treino"** (só avisa, nunca conclui sozinho): aparece na ficha do aluno quando o treino ativo
  tem **todas** as fichas na meta, ou quando **hoje é depois do fim** (no próprio dia do fim ainda vale). O professor lança o treino
  novo ou clica em Concluído.
- **Quem registra que o aluno treinou:** o próprio aluno, no celular (decisão do Thiago). Esse app ainda não existe: por isso a tabela
  `sessao` existe e `app/ciclo.py:registrar_sessao` está pronta e testada, mas **nada a chama ainda e a contagem fica em zero**.
- **Treinos antigos do Data4U** (migração para a versão 6): de cada aluno, só o treino **mais recente** continua ativo; os outros viram
  inativos. `inicio` do histórico = o dia do lançamento. O importador não mexe em ativo/início/fim/meta/sessões de treino que já veio;
  treino novo do Data4U entra inativo, e só vira o ativo do aluno se for o mais recente dele (o ativo de antes é concluído).
- **Fora desta versão, de propósito:** enviar início/fim/meta de volta ao Data4U (`DT_INICIO`, `DT_FIM`, `NR_SESSOES_PRESCRITAS`);
  registrar *quem* concluiu; aviso de troca na lista de alunos (hoje só na ficha do aluno).

## Histórico de treinos: como funciona

- **Origem dos dados:** as mesmas tabelas do `base_total.zip`. A tela "Atualizar alunos" manda primeiro os
  alunos e depois os treinos (dois envios). Se o segundo falhar, o primeiro já valeu e a tela avisa; basta tentar de novo.
- **Espelho do Data4U:** treino do Data4U é identificado por `data4u_id` (único). Importar de novo atualiza, acrescenta
  e remove o que sumiu de lá. Treino com `origem = 'app'` nunca é alterado nem removido pelo importador.
  Ficam de fora (e entram contados no relatório): treino apagado no Data4U (`ST_DELETED`), os 10 "modelos" sem lançamento (não são de nenhum aluno), treino de pessoa que não está no app, treino com data ilegível e treino cujo id já é de um treino do app.
- **Data do treino:** vem do lançamento (`DT_LANCAMENTO`, tipo -510), em horário de Brasília convertido para UTC.
- **Exercício que sumiu do Data4U:** o item fica com o exercício "Exercício removido do Data4U". Exercícios do histórico
  que não estão na biblioteca do app são criados **inativos** (aparecem no histórico, não aparecem na busca de montar treino).
- **Item sem exercício escolhido:** na cópia real de 08/10/2026, 236 dos 129.471 itens não tinham exercício (campo vazio no Data4U; o
  primeiro teste com o arquivo de verdade parou por causa deles, sem gravar nada). Os 168 totalmente em branco ficam de fora; os 68 com
  alguma coisa escrita (séries, repetições, carga, pausa maior que zero ou observação) entram como "Exercício não informado no Data4U"
  (exercício inativo). As duas contagens saem no relatório.
- **Pausa** vem como hora (`00:01:30`) e vira segundos; **observação** do exercício vem sem tags HTML.
- **Nome repetido:** treino do histórico conta na regra "nome único por aluno" (sem diferenciar maiúscula/acento): se o aluno
  tem um treino antigo "TREINO ABC", o professor não consegue salvar outro novo com o mesmo nome (recebe o aviso 409 e escolhe outro).
- **Impressão:** o cupom da térmica mostra séries × repetições, carga, intervalo e observação do exercício (desde 08/10/2026, a pedido do Thiago: os professores usam os dois).
- **Tamanho e tempo:** pacote de ~8,7 MB; o servidor leva 2 a 2,5 s e fica com o banco travado para gravar nesse tempo
  (quem salva treino exatamente nesse momento espera um pouco; o tempo de espera é 5 s).
- **Modo teste:** abrir `/alunos/atualizar?simular_treinos=1`: o servidor faz toda a importação e **desfaz**, devolvendo as contagens
  ("SIMULAÇÃO: nada foi gravado"). Os alunos continuam sendo gravados normalmente nesse envio; só o histórico é simulado.

## Cuidados

- `app.db` vai ter CPF e WhatsApp de alunos (dado pessoal, LGPD). Não vai para o Git
  (`.gitignore`), a pasta do servidor onde ele fica não pode ser pública e a cópia de
  segurança precisa sair do servidor com acesso restrito.
- **Área do professor protegida por computador autorizado** (veja a camada 7). O código de
  autorização só é gerado por quem tem acesso ao servidor; vale 15 minutos e uma vez só; o
  banco guarda apenas o hash. O cookie do computador é `HttpOnly` (o JavaScript da página não
  lê), `SameSite=Lax`, `Secure` fora de localhost, dura até 400 dias e é renovado a cada hora
  de uso; um computador **sem uso por 90 dias** perde a autorização. Pedido que muda dado (POST)
  vindo de outro site é recusado (conferência do cabeçalho `Origin`).
  **Antes de colocar dado real no servidor publicado, ainda falta a parte da implantação:**
  HTTPS (sem ele o cookie `Secure` não funciona), HSTS e `ProxyFix` (para o app enxergar o
  endereço certo atrás do proxy).
- **Quem usa o computador autorizado tem acesso ao app**, sem senha (decisão do projeto: o
  computador da academia fica sempre autorizado). Quem tiver acesso físico a ele, ou copiar o
  cookie do navegador dele, entra. Se um computador for perdido, trocado ou suspeito: `revogar`.
- Para autorizar um computador novo é preciso acesso ao servidor (o código sai de lá). Uma tela
  de "aparelhos autorizados" dentro do app, aberta a um computador já autorizado, não existe
  ainda.
- A trava de tentativas é **global** (5 códigos errados seguidos, de qualquer aparelho, travam
  a tela `/autorizar` por até 15 minutos): quem estiver na internet consegue atrapalhar uma
  autorização nova, mas não consegue entrar; computadores já autorizados continuam funcionando.
- **As revogações ficam no banco.** Restaurar uma cópia de segurança antiga restaura também os
  computadores como estavam naquele dia (um computador revogado depois pode voltar a valer):
  depois de restaurar, rode `listar` e revogue de novo o que for preciso.
- A página só carrega arquivos do próprio servidor (sem fontes nem scripts de terceiros) e
  tem política de segurança (CSP) que proíbe script e estilo embutidos na página.
- Os testes usam banco temporário; nenhum teste toca em dado real de aluno.
- A ficha mostra o **CPF inteiro** a quem abrir a página (como no desenho). É dado pessoal
  (LGPD): mais um motivo para a área do professor ter proteção antes de existir aluno real.
  Os ids de aluno são sequenciais (1, 2, 3...); hoje só computador autorizado chega até eles.
- O WhatsApp corrigido na ficha vale só no app (`whatsapp_corrigido_no_app`); o Data4U não
  é alterado.
- "Professor" (campo `montado_por`) é texto livre e **não prova quem fez**: qualquer pessoa na tela de um computador
  autorizado digita qualquer nome. Serve de registro, não de controle de acesso.
- O servidor só aceita `POST` com `Content-Type: application/json` (um formulário de outro
  site não consegue mandar esse tipo), com cookie `SameSite=Lax` e com conferência de origem:
  três camadas contra pedidos forjados por outro site.
- **Atualização do banco (migração).** Os bancos das versões 4 e 5 sobem sozinhos até a 6 (a 4 -> 5 é a de
  07/10/2026; a 5 -> 6 é o ciclo do treino, de 08/10/2026) quando o app novo liga: antes de mexer, o app tira uma cópia
  consistente em `<pasta do banco>/antes-da-migracao/` (uma por subida, guarda as 5 últimas); cada passo roda numa
  transação (ou muda tudo, ou nada); os 2 processos do gunicorn subindo juntos não migram duas vezes. Banco mais antigo
  que a versão 4 ainda é recusado (`BancoDesatualizado`).
  **Voltar atrás:** depois que o banco virou versão 6, a imagem ANTIGA do app se recusa a abrir (ela só
  conhece a 5). Para voltar à imagem antiga é preciso também voltar o arquivo: copiar a cópia de
  `/dados/antes-da-migracao/` (ou uma de `/backups`) por cima de `/dados/app.db` com o app parado. Nunca apagar
  o banco para "resolver": o erro de versão **mais nova** diz isso na mensagem.
- O importador **não copia** senha, RG, nascimento, salário nem observações do Data4U: lê só
  nome, CPF, situação e celular. Mas o `.zip` que ele lê tem o banco inteiro: tratar o arquivo
  como dado sensível (não vai para o Git, não fica em pasta pública, apagar do servidor depois de importar).

## Ainda em aberto (de propósito, não decidido)

- Qual dos ids do Data4U usar ao gravar um exercício que tem mais de um.
- Como o login por CPF trata os 4 CPFs que aparecem em mais de uma pessoa no Data4U.
- Como o app do aluno vai registrar "treino feito" (a tabela `sessao` e `registrar_sessao` esperam por ele) e como início/fim/meta voltam ao Data4U.
- Tela de "aparelhos autorizados" dentro do app (hoje só pelo comando no servidor).
- Aviso de "combinação nova no Data4U" (o desenho mostra na montagem e no salvar): precisa
  saber quais combinações já existem como um exercício só; entra no passo de salvar.
- Qual `professor_id` do Data4U usar ao enviar o treino para lá (o app guarda só o nome digitado;
  a fila do Data4U exige um id de pessoa).
- Se o Data4U aceita séries/repetições vazias (o app exige as duas).
- A busca de alunos mostra o **último treino** (o mais novo, do app ou do histórico), que normalmente é o ativo; ainda falta o app do aluno.
- A **situação** mostrada é a letra do Data4U (Ativo, Pendente...), no lugar do "Em dia" do
  desenho. "Em dia" não foi verificado (o desenho dizia "pagou nos últimos 30 dias").
- Importar todo dia, **sozinho**: hoje é manual, pela tela "Atualizar alunos" (alguém da recepção
  escolhe o `base_total.zip` depois das 05:00). Automatizar exigiria mandar os dados do PC da
  recepção ao servidor sem ninguém na tela: ainda não decidido. A cópia tem as 258 tabelas do Data4U
  (digitais, anamnese, pagamentos...) e o app só usa 3; a tela já envia só elas e só as colunas usadas.
- A tela "Atualizar alunos" lê o `.zip` com o `DecompressionStream` do navegador (Chrome e Edge
  atuais) e **não lê ZIP64** (só usado acima de 4 GB). Foi testada com `.zip` gerado pelo Python
  (deflate) num Chromium de verdade; **falta testar com o `base_total.zip` real** no PC da recepção.
- Dos 369 alunos ativos, trancados ou pendentes: 19 não têm CPF no Data4U (não conseguirão entrar
  no app do aluno) e 136 estão sem WhatsApp usável (12 sem celular; 112 com celular de 9 números, sem DDD,
  que o app não completa; 12 com número fora do formato). A recepção corrige na ficha (WhatsApp) ou no Data4U (CPF).
- **Impressão (testada em 07/10/2026 no PC dos professores: imprimiu certo):** não sei qual bobina está instalada (80 mm ou 57 mm), nem a
  largura útil real (o cupom usa 72 mm, `--largura-util` em `imprimir.css`). O tamanho do papel **não** é
  pedido pela página (o Chrome não aceita altura automática no `@page` e uma altura fixa gastaria
  bobina): é preciso escolher o papel de 80 mm da Bematech na janela de impressão ou, melhor, nas
  preferências da impressora no Windows. Conferido só no Chromium, com o cupom em PDF de 80 mm. Os
  nomes dos exercícios saem como estão na base do Data4U (alguns começam com número entre parênteses,
  ex.: "(16) CADEIRA ADUTORA"). O cupom imprime **todas as fichas** do treino, uma depois da outra. O
  endereço do app do aluno **não** é impresso enquanto não existir app do aluno: quando existir, defina
  `GLORIAFIT_ENDERECO_DO_APP` e o cupom passa a terminar com "ENTRE NO APP COM O SEU CPF:" e o endereço.
  As caixas "Mostrar no app do aluno / Imprimir / Enviar ao Data4U" do desenho de Salvar não foram
  feitas: hoje são só os botões "Imprimir na térmica".
- **Aluno provisório:** o WhatsApp digitado no cadastro vale mais que o do Data4U (fica marcado como
  corrigido no app); na junção, nome e situação vêm do Data4U. Se o CPF estiver em mais de uma
  pessoa do Data4U (acontece: 4 casos na base), o app **não junta** e o provisório continua provisório
  (o relatório da importação conta quantos ficaram assim). Provisório sem par continua na lista até
  alguém conferir o CPF: ainda não existe a tela de pendências. O CPF repetido é recusado sem
  distinguir "mesma pessoa" de "CPF digitado errado": a tela mostra a ficha de quem já tem o CPF.
- Login do aluno (código por WhatsApp), pendências da recepção, mensalidade e produtos: entram em versões seguintes.
