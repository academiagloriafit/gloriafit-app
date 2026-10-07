# App Glória Fit

App de treinos da Academia Glória Fit. Hoje tem estas camadas prontas:

1. **Banco de dados** (SQLite) + importação do quadro de 1.161 exercícios.
2. **Servidor web** (Flask) com a lista de exercícios da tela do professor: busca por nome
   (sem diferenciar acento nem maiúscula) e filtro por grupo muscular.
3. **Tela de montar treino** (`/alunos/<id>/montar`): fichas (Treino A, B, C...), exercícios
   com séries/repetições/carga, bi-set e tri-set, conferência dos limites do Data4U.
   O rascunho fica no navegador até salvar.
4. **Salvar treino**: o professor confere o nome do treino (o app sugere um, ex.:
   "TREINO ABC 07/10/26") e **digita o próprio nome em "Quem montou este treino?"
   (obrigatório)**. O treino é gravado no banco com esse nome. Treinos montados no futuro
   por robô/Claude levam `Academia Glória Fit` (constante `AUTOR_AUTOMATICO`).
5. **Buscar aluno** (`/alunos`, a página inicial) e **ficha do aluno** (`/alunos/<id>`):
   a busca acha por nome (palavras em qualquer ordem, sem diferenciar acento nem maiúscula),
   por CPF (ou um pedaço dele) ou por matrícula (número igual). A lista mostra matrícula, último
   treino e a **situação** (Ativo, Trancado, Pendente, Desistente, Inativo, Cancelado, ou
   Provisório). A ficha mostra os treinos salvos (mais novo primeiro, com quem montou e a data),
   o botão **Montar novo treino**, o WhatsApp do aluno (editável) e o cadastro (CPF, matrícula,
   situação).
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
   repetições, carga e o aviso "BI-SET: FAÇA A1 E A2 SEGUIDOS". O botão **Imprimir na térmica**
   aparece depois de salvar o treino e em cada treino da ficha do aluno. **Testado em 07/10/2026
   na impressora do PC dos professores: imprimiu certo** (segundo o Thiago; ver "Ainda em aberto").
8. **Proteção da área do professor**: só **computadores autorizados** abrem as telas e a API
   (hoje serão dois: o dos professores e o da recepção). Cada um é autorizado uma vez, com um
   **código de uso único** gerado no servidor (`python -m app.dispositivos`), e passa a ser
   reconhecido por um cookie. Quem abrir o endereço em outro aparelho cai na tela
   `/autorizar` e não vê dado nenhum.

## O que tem

| Arquivo | Para quê |
|---|---|
| `app/schema.sql` | Desenho das tabelas (versão 4): exercícios, grupos musculares, alunos (CPF pode ficar vazio; `situacao`; `data4u_id` = matrícula), treinos (com `montado_por`), fichas e itens, e os computadores autorizados (`codigo_de_autorizacao`, `dispositivo`, `autorizacao_falha`). Não há tabela de professores: o nome é digitado a cada treino |
| `app/db.py` | Abre o banco (liga as chaves estrangeiras, ensina o SQL a comparar sem acento), cria as tabelas e recusa arquivo de banco de versão antiga |
| `app/importar_exercicios.py` | Lê a planilha `dados/quadro_exercicios_v2.xlsx` e grava no banco |
| `app/texto.py` | `normalizar`: minúsculas e sem acento ("Bíceps" → "biceps") |
| `app/exercicios.py` | Consultas: grupos e busca de exercícios |
| `app/alunos.py` | Busca de alunos (nome, CPF ou matrícula), ficha com os treinos salvos e correção do WhatsApp (valida e grava) |
| `app/importar_alunos.py` | Lê a cópia diária do Data4U (só 3 tabelas: `PESSOA`, `PESSOA_STATUS`, `CONTATO_PESSOA`), confere se está inteira (manifesto) e grava os alunos, tudo ou nada. Imprime um relatório só com contagens |
| `app/provisorios.py` | Aluno provisório: valida nome e CPF (dígitos verificadores) e cadastra, recusando CPF que já exista (a conferência e a gravação são um comando só no SQLite, então dois pedidos juntos não passam os dois) |
| `app/cupom.py` | Monta o conteúdo do cupom do treino (linhas, etiquetas, avisos de bi-set/tri-set); o desenho fica em `templates/imprimir.html` e `static/imprimir.css` |
| `app/treinos.py` | Salvar e ler treinos: confere tudo de novo no servidor e grava tudo-ou-nada |
| `app/acesso.py` | Computadores autorizados: gera o código de uso único, troca o código por um cookie, reconhece o computador, revoga, limita tentativas erradas. O banco guarda só o hash (SHA-256) do código e do cookie |
| `app/dispositivos.py` | Comando do servidor: `codigo --nome "..."` (gera o código), `listar`, `revogar <número>` |
| `app/web.py` | O servidor: páginas e rotas da API (tabela "Rotas" abaixo) e a guarda que barra quem não é computador autorizado |
| `app/templates/`, `app/static/` | Páginas, estilo e JavaScript |
| `app/static/zip_leitor.js` | Lê o `.zip` no navegador sem biblioteca: acha uma entrada pelo índice e descompacta só ela (deflate ou sem compressão); recusa senha, ZIP64, arquivo cortado, tamanho que não bate e "bomba de zip" |
| `app/static/copia_modelo.js` | Prepara o que a tela "Atualizar alunos" envia: confere o manifesto, reduz às colunas necessárias, só celular (tipo 30), CPF/telefone como texto; textos de aviso e leitura da resposta do servidor |
| `app/static/atualizar_alunos.js` | A tela em si (escolher arquivo, mostrar resumo, enviar). Usa só `textContent` |
| `app/static/treino_modelo.js` | Lógica do treino (fichas, bi-set, validação, rascunho, nome sugerido, pedido de salvar), sem nada de tela |
| `app/static/montar.js`, `salvar.js`, `biblioteca.js` | Desenho da tela de montar treino, da tela de salvar e da lista de exercícios |
| `app/static/api.js` | `enviarJson`: envia um POST em JSON com limite de tempo (20 s) e devolve status + corpo; usado por salvar treino e WhatsApp |
| `app/static/autorizar.js`, `autorizar_modelo.js` | Tela `/autorizar`: envia o código e mostra a resposta (o texto de cada resposta fica em `autorizar_modelo.js`, testado à parte) |
| `app/static/novo_aluno.js`, `novo_aluno_modelo.js` | Tela `/alunos/novo`: envia o cadastro e mostra erros por campo ou os links de quem já tem o CPF (o que mostrar para cada resposta fica em `novo_aluno_modelo.js`, testado à parte) |
| `app/static/alunos.js`, `ficha.js` | Busca de alunos (espera 200 ms depois de digitar e cancela a busca anterior) e a edição do WhatsApp na ficha |
| `tests/` | Testes do Python (pytest) |
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
- Cópia de segurança: `python -m app.backup /dados/app.db /backups` (usa a
  cópia segura do próprio SQLite, confere a integridade e guarda as 14 últimas). Isso fica no
  mesmo servidor; **falta** mandar uma cópia diária para fora dele.
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
| `GET /exercicios` | A página da lista de exercícios |
| `GET /api/grupos` | Os 15 grupos, na ordem do quadro, com a quantidade de exercícios de cada |
| `GET /api/exercicios?q=&grupo=&limite=` | `{"total": N, "exercicios": [...]}`. `q`: palavras do nome; `grupo`: id do grupo; `limite`: 1 a 200 (padrão 50) |
| `GET /alunos/<id>/montar` | Tela de montar treino do aluno (404 se o aluno não existe) |
| `POST /api/alunos/<id>/treinos` | Grava um treino. Corpo JSON: `nome_treino`, `montado_por`, `fichas` (cada uma com `nome` e `itens`: `exercicio_id`, `series`, `repeticoes`, `carga`, `bloco`). Devolve `201 {"id": N}`; `400 {"erros": [...]}` dado inválido; `404` aluno inexistente; `409` o aluno já tem treino com esse nome; `413` pedido grande demais (> 512 KB); `415` não é JSON |
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
séries e repetições obrigatórias, exercício existente e ativo, bi-set de 2 e tri-set de 3
exercícios juntos, `montado_por` obrigatório (até 60), sem caracteres de controle. O nome do
treino é único por aluno, sem diferenciar maiúscula nem acento (regra do Data4U).

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
- "Quem montou" é texto livre e **não prova quem fez**: qualquer pessoa na tela de um computador
  autorizado digita qualquer nome. Serve de registro, não de controle de acesso.
- O servidor só aceita `POST` com `Content-Type: application/json` (um formulário de outro
  site não consegue mandar esse tipo), com cookie `SameSite=Lax` e com conferência de origem:
  três camadas contra pedidos forjados por outro site.
- O app **não sobe** com banco de versão antiga (`BancoDesatualizado`): enquanto não há dado
  de aluno real no servidor, basta apagar o arquivo, importar os exercícios e os alunos de novo.
- O importador **não copia** senha, RG, nascimento, salário nem observações do Data4U: lê só
  nome, CPF, situação e celular. Mas o `.zip` que ele lê tem o banco inteiro: tratar o arquivo
  como dado sensível (não vai para o Git, não fica em pasta pública, apagar do servidor depois de importar).

## Ainda em aberto (de propósito, não decidido)

- Qual dos ids do Data4U usar ao gravar um exercício que tem mais de um.
- Como o login por CPF trata os 4 CPFs que aparecem em mais de uma pessoa no Data4U.
- Regra de qual é o "treino atual" do aluno e como treinos antigos aparecem.
- Tela de "aparelhos autorizados" dentro do app (hoje só pelo comando no servidor).
- Aviso de "combinação nova no Data4U" (o desenho mostra na montagem e no salvar): precisa
  saber quais combinações já existem como um exercício só; entra no passo de salvar.
- Qual `professor_id` do Data4U usar ao enviar o treino para lá (o app guarda só o nome digitado;
  a fila do Data4U exige um id de pessoa).
- Se o Data4U aceita séries/repetições vazias (o app exige as duas).
- Treinos salvos aparecem na ficha do aluno, mas não há regra de qual é o "treino atual"
  (a busca mostra o **último treino salvo**) e ainda falta o app do aluno.
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
