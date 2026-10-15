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
   navegador até salvar. O botão **Importar treino** (no alto) começa de um treino pronto: um **treino padrão** ou o treino de
   **outro aluno** (ver "Treinos padrão e Importar treino" abaixo); **Salvar como treino padrão** (no rodapé) guarda o que está na tela.
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
   **Envio automático (desde 14/10/2026):** o PC da recepção roda sozinho, todo dia, o programa
   `app/static/recepcao/enviar_alunos.py`, que faz o mesmo que a tela sem ninguém clicar, e o app avisa se a
   atualização parar (ver "Atualização automática dos alunos" abaixo). A tela continua valendo para atualizar na hora.
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
10. **Filas numeradas de treino** (versão 8 do banco): o professor coloca o aluno numa fila (Homem, Mulher, Adolescente, Gestante,
   Grupos de risco) e o app **sugere** o próximo treino da fila quando chega a hora de trocar. Nada é trocado sozinho. Ver "Filas
   numeradas: como funciona" abaixo.

## O que tem

| Arquivo | Para quê |
|---|---|
| `app/schema.sql` | Desenho das tabelas (versão 12): exercícios, grupos musculares, alunos (CPF pode ficar vazio; `situacao`; `data4u_id` = matrícula), treinos (com `montado_por`, `origem` app/data4u, `data4u_id`, `ativo`, `inicio`, `fim`, `concluido_em` e `sessoes_por_ficha`), fichas e itens (com pausa e observação), `sessao` (cada vez que o aluno treinou uma ficha), `modelo_treino` (treinos padrão, com `fila_id` e `numero` quando fazem parte de uma fila), `fila` (as 5 filas) e `aluno_fila` (em que fila cada aluno está, em que número, quem o colocou e a liberação) os computadores autorizados (`codigo_de_autorizacao`, `dispositivo`, `autorizacao_falha`), a senha de administrador, os pedidos de treino sob medida (`ia_pedido`) `importacao` (de quando é a última cópia do Data4U aplicada) e o login do aluno (`aluno_senha`, `aluno_codigo`, `aluno_sessao`, `aluno_evento`). Não há tabela de professores: o nome é digitado a cada treino |
| `app/db.py` | Abre o banco (liga as chaves estrangeiras, ensina o SQL a comparar sem acento), cria as tabelas, **atualiza banco da versão 4 a 11 até a 12 sozinho** (`migrar`, com cópia de segurança antes) e recusa arquivo de versão que não conhece |
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
| `app/modelos.py` | Treinos padrão (`modelo_treino`: criar, listar, excluir) e a cópia de treinos para a tela de lançar treino: devolve um treino padrão ou o treino de um aluno no formato da tela (`para_montar`), marcando exercício que saiu da lista e arrumando bi-sets fora do molde. **Não grava nada para o aluno** |
| `app/filas.py` | Filas numeradas: listar as filas, conferir a fila e o número de um treino padrão, colocar o aluno numa fila (com a liberação de Gestante e Grupos de risco), tirar da fila e montar o que a ficha mostra (treinos da fila, o atual, o sugerido, "fim da fila"). Quem **aprova** é `salvar_treino` (`fila_modelo_id`) |
| `app/ciclo.py` | O ciclo do treino: concluir, reativar, registrar sessão (só testes por enquanto), contar o andamento e decidir o aviso "hora de trocar o treino" |
| `app/datas.py` | Fuso de Brasília: dia local de um momento em UTC, "hoje", leitura rigorosa de `AAAA-MM-DD` |
| `app/acesso.py` | Computadores autorizados: gera o código de uso único, troca o código por um cookie, reconhece o computador, revoga, limita tentativas erradas. O banco guarda só o hash (SHA-256) do código e do cookie |
| `app/dispositivos.py` | Comando do servidor: `codigo --nome "..."` (gera o código), `listar`, `revogar <número>` |
| `app/aluno_acesso.py` | **Login do aluno** (CPF + senha; primeiro acesso e "esqueci a senha" por código no WhatsApp): sorteia o código, guarda só o hash, confere, cria a senha (scrypt), as sessões do celular e **todos os limites de tentativa** (ver "Login do aluno: como funciona") |
| `app/whatsapp.py` | Manda o código pela API da Meta (modelo `codigo_acesso_app`), em https e sem seguir redirecionamento. A chave da Meta fica em `/dados/whatsapp.json` (só o dono lê), nunca no banco nem no log. Comando do servidor: `python -m app.whatsapp configurar`, `situacao`, `testar <WhatsApp>` |
| `app/web.py` | O servidor: páginas e rotas da API (tabela "Rotas" abaixo) e a guarda que barra quem não é computador autorizado |
| `app/templates/`, `app/static/` | Páginas, estilo e JavaScript |
| `app/static/zip_leitor.js` | Lê o `.zip` no navegador sem biblioteca: acha uma entrada pelo índice e descompacta só ela (deflate ou sem compressão); recusa senha, ZIP64, arquivo cortado, tamanho que não bate e "bomba de zip" |
| `app/static/copia_modelo.js` | Prepara o que a tela "Atualizar alunos" envia, em dois pacotes (alunos e treinos): confere o manifesto, reduz às colunas necessárias, só celular (tipo 30), CPF/telefone como texto; envia um depois do outro; textos de aviso e leitura da resposta do servidor |
| `app/importacoes.py` | De quando é a última atualização dos alunos e do histórico de treinos (tabela `importacao`) e o aviso de atraso (mais de 48 h) que aparece na busca de alunos e na tela "Atualizar alunos" |
| `app/static/recepcao/enviar_alunos.py` | O programa do **PC da recepção** (Windows, Python 3.12, só biblioteca padrão): lê o `base_total.zip`, monta os mesmos dois pacotes do navegador e os envia sozinho; `--autorizar`, `--conferir`, `--instalar`. Fica em `/static/` só para o PC poder baixá-lo (não tem segredo) |
| `app/static/atualizar_alunos.js` | A tela em si (escolher arquivo, mostrar resumo, enviar os dois pacotes, mostrar o relatório). Usa só `textContent`. Com `?simular_treinos=1` na página, o histórico é só simulado |
| `app/static/treino_modelo.js` | Lógica do treino (fichas, bi-set, validação, rascunho, nome sugerido, pedido de salvar), sem nada de tela |
| `app/static/montar.js`, `salvar.js`, `biblioteca.js` | Desenho da tela Lançar treino (nome, professor, fichas, tabela), envio do treino ao servidor e lista de exercícios |
| `app/static/importar_treino.js` | O painel **Importar treino** (abas "Treino padrão" e "Treino de outro aluno"): só lê do servidor e entrega o treino escolhido a `montar.js`; pede confirmação antes de substituir o que já está na tela |
| `app/static/padrao_ficha.js` | Botão **Salvar como treino padrão** de cada treino na ficha do aluno |
| `app/static/dom.js` | `el()`: cria elementos de tela só com `textContent` (nada vindo do banco vira HTML) |
| `app/static/api.js` | `enviarJson` (POST em JSON) e `buscarJson` (GET) com limite de tempo (20 s) devolvendo status + corpo; `textoDoErro` escolhe a mensagem para mostrar; usado por salvar treino, WhatsApp e importar treino |
| `app/static/aluno_entrar.js`, `aluno_modelo.js`, `aluno_inicio.js` | Telas do celular do aluno (`/aluno/entrar` e `/aluno`): entrar, pedir o código e criar a senha, sair. O que mostrar para cada resposta e as conferências rápidas ficam em `aluno_modelo.js` (testado à parte) |
| `app/static/autorizar.js`, `autorizar_modelo.js` | Tela `/autorizar`: envia o código e mostra a resposta (o texto de cada resposta fica em `autorizar_modelo.js`, testado à parte) |
| `app/static/novo_aluno.js`, `novo_aluno_modelo.js` | Tela `/alunos/novo`: envia o cadastro e mostra erros por campo ou os links de quem já tem o CPF (o que mostrar para cada resposta fica em `novo_aluno_modelo.js`, testado à parte) |
| `app/static/alunos.js`, `ficha.js` | Busca de alunos (espera 200 ms depois de digitar e cancela a busca anterior) e a edição do WhatsApp na ficha |
| `app/static/fila_ficha.js`, `filas_modelo.js`, `fila_padrao.js` | Cartão **Fila de treino** da ficha (escolher a fila, liberação, tirar da fila), a lógica pura de conferir o que o professor digitou (`filas_modelo.js`, testada à parte) e os campos **Fila** e **Número** do "Salvar como treino padrão" (sugere o próximo número livre) |
| `app/static/ciclo_ficha.js` | Botões **Concluído** (com confirmação) e **Reativar** da ficha do aluno |
| `tests/` | Testes do Python (pytest). `schema_v4.sql` a `schema_v11.sql` são cópias dos desenhos antigos, usadas para provar as migrações; `test_contrato_js_python.py` roda o JavaScript (Node) e entrega o pacote dele ao servidor; `test_enviar_alunos.py` confere que o programa do PC monta pacotes **iguais** aos do navegador e roda o envio contra um servidor de verdade |
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
| `GET /aluno/entrar` | **Pública.** A tela do celular do aluno: entrar (CPF + senha), primeiro acesso / esqueci a senha, digitar o código. Aluno já logado vai para `/aluno` |
| `GET /aluno` | **Pública** (confere o cookie do aluno). A primeira tela do aluno logado; sem login, `302` para `/aluno/entrar` |
| `POST /api/aluno/codigo` | **Pública.** Corpo `{"cpf": "..."}`. Manda o código de 6 números ao WhatsApp do aluno, em segundo plano. `200 {"ok": true, "espera": 60, "validade_minutos": 10}` **igual** para CPF de aluno e CPF que não existe; `400` CPF mal digitado; `429` (espera, com `Retry-After`) pediu demais; `503` WhatsApp ainda não configurado ou teto de códigos do dia atingido; `415` |
| `POST /api/aluno/primeiro-acesso` | **Pública.** Corpo `{"cpf", "codigo", "senha"}`. Troca o código certo pela senha nova e já entra (cookie `gloriafit_aluno`). `200 {"ok": true, "nome": "Ana"}`; `400` senha que não serve (o código **não** é gasto) ou código inválido/vencido (mesma mensagem para todos os motivos); `429`; `415` |
| `POST /api/aluno/entrar` | **Pública.** Corpo `{"cpf", "senha"}`. `200 {"ok": true, "nome"}` e o cookie; `401 {"erro": "CPF ou senha incorretos."}` (igual para CPF que não existe, aluno sem senha, aluno que não pode entrar e senha errada); `429`; `415` |
| `POST /api/aluno/sair` | **Pública.** Encerra este celular e apaga o cookie |
| `GET /api/aluno/treino` | **Pública** (confere o cookie do aluno; sem login, `401`). O treino **ativo** do aluno logado, em texto pronto: `{"treino": null}` (sem treino ativo) ou `{"treino": {nome, inicio, fim, meta_por_ficha, fichas: [{nome, ordem, feitas, feita_hoje, grupos: [{nome, instrucao, exercicios: [{etiqueta, exercicio, dose, carga, intervalo, observacao}]}]}]}}`. O aluno vem do cookie, nunca da URL. **Não devolve** ids, quem montou, origem nem o aviso de "hora de trocar" (`feitas` e `meta_por_ficha` são o andamento do próprio aluno) |
| `POST /api/aluno/treino/feito` | **Pública** (cookie do aluno). "Fiz esta ficha hoje". Corpo `{"ficha": 1}` (1 = A, 2 = B...; o aluno vem do cookie, ids no corpo são ignorados). Conta **no máximo uma vez por ficha por dia** (dia de Brasília); marcar de novo no mesmo dia não grava e responde `ja_marcada: true`. `200 {"ok", "ficha", "ja_marcada", "feitas"}`; `400` ficha inválida; `401`; `404` a ficha não existe; `409` sem treino ativo; `415` |
| `POST /api/aluno/treino/desfazer` | **Pública** (cookie do aluno). Desfaz a marcação **de hoje** da ficha (toque errado); nunca apaga as de outros dias. Corpo `{"ficha": 1}`. `200 {"ok", "ficha", "feitas"}`; mesmos erros do `/feito` |
| `GET /alunos` | A página de buscar aluno |
| `GET /treinos/<id>/imprimir` | O cupom do treino para a térmica (404 se não existe), com o botão Imprimir |
| `GET /alunos/novo` | A tela de cadastrar aluno provisório |
| `POST /api/alunos` | Cadastra aluno provisório. Corpo JSON: `nome`, `cpf`, `whatsapp` (opcional). Devolve `201 {"id": N}`; `400 {"erros": {campo: mensagem}}` (nome, cpf ou whatsapp inválido); `409 {"erro", "existentes": [{id, nome, provisorio, situacao_nome}]}` o CPF já está no app; `413`; `415` |
| `GET /api/alunos?q=&limite=` | `{"total": N, "alunos": [{id, nome, provisorio, matricula, situacao, situacao_nome, ultimo_treino, atualizado_em}]}`. `q`: nome (palavras em qualquer ordem) ou só números = pedaço do CPF **ou** matrícula igual (a matrícula vem primeiro); com texto, quem está em uso (ativo, trancado, pendente, provisório) vem antes dos demais; sem `q`, vem primeiro quem tem treino salvo (o mais recente), depois provisórios sem treino, depois o resto. `limite`: 1 a 200 (padrão 50). **Não devolve CPF nem WhatsApp** |
| `GET /alunos/<id>` | A ficha do aluno (404 se não existe) |
| `POST /api/alunos/<id>/whatsapp` | Corrige o WhatsApp. Corpo JSON: `whatsapp` (10 ou 11 algarismos com DDD; aceita espaço, parênteses, ponto e hífen; **sem +55**). Devolve `200 {"whatsapp": "(27) 98888-7766"}`; `400 {"erro"}`; `404`; `415`. Marca o número como corrigido no app (a cópia diária do Data4U não pode mais sobrescrevê-lo) |
| `GET /static/recepcao/enviar_alunos.py` | O programa do PC da recepção (público, como o resto de `/static/`; não tem segredo) |
| `GET /alunos/atualizar` | A tela "Atualizar alunos" (a recepção escolhe o `base_total.zip`). Com `?simular_treinos=1` mostra "MODO TESTE" e o histórico de treinos não é gravado |
| `POST /api/alunos/importar` | Recebe o pacote de alunos montado pelo navegador (até 25 MB; só esta rota e a de treinos aceitam isso, as demais param em 512 KB). `200` com contagens; `400 {"erro"}` se o pacote não serve (nada é gravado) |
| `POST /api/treinos/importar` | Recebe o pacote do histórico de treinos. `200 {"extraido_em", "simulado", "treinos", "novos", "atualizados", "removidos", "texto"}` (só contagens, nunca nome ou CPF); `400 {"erro"}`. Com `"simular": true` no pacote roda tudo e desfaz |
| `GET /exercicios` | A página da lista de exercícios |
| `GET /api/grupos` | Os 15 grupos, na ordem do quadro, com a quantidade de exercícios de cada |
| `GET /api/exercicios?q=&grupo=&limite=` | `{"total": N, "exercicios": [...]}`. `q`: palavras do nome; `grupo`: id do grupo; `limite`: 1 a 200 (padrão 50) |
| `GET /alunos/<id>/montar` | Tela de montar treino do aluno (404 se o aluno não existe) |
| `POST /api/alunos/<id>/treinos` | Grava um treino. Corpo JSON: `nome_treino`, `montado_por`, `inicio` (`AAAA-MM-DD`, vazio = hoje), `fim` (opcional, não pode ser antes do início), `sessoes_por_ficha` (opcional, 1 a 999), `fichas` (cada uma com `nome` e `itens`: `exercicio_id`, `series`, `repeticoes`, `carga`, `pausa`, `observacao`, `bloco`). Se o aluno já tinha treino ativo, ele é concluído na mesma gravação. Opcional: `fila_modelo_id` (o treino padrão da fila que o professor abriu e aprovou): na mesma gravação o aluno passa para esse número da fila; `409` se o padrão não está numa fila ou o aluno não está nessa fila. Devolve `201 {"id": N, "concluido_anterior": "NOME" ou null}`; `400 {"erros": [...]}` dado inválido; `404` aluno inexistente; `409` o aluno já tem treino com esse nome; `413` pedido grande demais (> 512 KB); `415` não é JSON |
| `POST /api/treinos/<id>/concluir` | Botão "Concluído": o treino vira inativo (guarda `concluido_em`). Corpo JSON `{}`. `200 {"ok": true}`; `404`; `409` já está concluído; `415` |
| `POST /api/treinos/<id>/reativar` | Desfaz o "Concluído". `200 {"ok": true}`; `404`; `409` já está ativo, ou o aluno já tem outro treino ativo (a mensagem diz qual); `415` |
| `GET /api/modelos` | `{"modelos": [{id, nome, montado_por, sessoes_por_ficha, criado_em, fichas, exercicios, resumo, fila_id, fila, numero, posicao}]}`: os treinos padrão, em ordem alfabética (`posicao` = "Mulher · Treino 3", vazio se não está em fila) |
| `GET /api/modelos/<id>` | Um treino padrão no formato da tela de montar: `{nome, sessoes_por_ficha, indisponiveis, fila_id, fila, numero, fichas: [{nome, itens: [{exercicio_id, nome, series, repeticoes, carga, pausa, observacao, bloco, indisponivel}]}]}` (`fila_id`, `fila` e `numero` vêm vazios num padrão sem fila). **Não grava nada.** `404` |
| `POST /api/modelos` | Guarda o treino da tela como treino padrão. **Exige `senha_admin` no corpo** (ver "Senha de administrador"). Corpo JSON: `senha_admin`, `nome` (até 40), `montado_por`, `sessoes_por_ficha` (opcional), `fila_id` e `numero` (opcionais, **os dois juntos**: o lugar do treino numa fila, número de 1 a 6), `fichas` (mesmo formato de salvar treino; mesma conferência). `201 {"id"}`; `403`/`429` (senha, ver abaixo); `400 {"erros"}` (inclui fila que não existe ou só um dos dois); `409` já existe padrão com esse nome (sem diferenciar maiúscula nem acento) **ou** a fila já tem um treino com esse número; `415` |
| `POST /api/modelos/<id>/excluir` | Apaga um treino padrão (os treinos já copiados para alunos não mudam). **Exige `senha_admin`.** Corpo `{"senha_admin": "..."}`. `200 {"ok": true}`; `403`/`429` (senha); `404`; `415` |
| `POST /api/treinos/<id>/modelo` | "Salvar como treino padrão" de um treino que já existe. **Exige `senha_admin`.** Corpo JSON: `{"senha_admin": "...", "nome": "...", "fila_id": N, "numero": N}` (os dois últimos opcionais, como em `POST /api/modelos`). Fica com o professor e a meta do treino original. `201 {"id"}`; `403`/`429` (senha); `400 {"erros"}` (inclui treino com exercício que saiu da lista); `404`; `409` nome repetido ou número já usado na fila; `415` |
| `POST /api/alunos/<id>/fila` | O professor coloca o aluno numa fila (ou muda a fila dele). Corpo JSON: `fila_id`, `professor` (até 60 letras, obrigatório) e, nas filas que exigem liberação (Gestante e Grupos de risco), `liberacao_conferida: true` e `liberacao_em` (`AAAA-MM-DD`, não pode ser no futuro). Mudar para OUTRA fila zera a posição; repetir a mesma fila mantém o número. `200 {"ok": true}`; `400 {"erros": [...]}`; `404`; `415` |
| `POST /api/alunos/<id>/fila/tirar` | Tira o aluno da fila (o treino dele não muda). Corpo `{}`. `200 {"ok": true}`; `404`; `415` |
| `GET /api/alunos/<id>/treinos-para-copiar` | `{"treinos": [{id, nome, ativo, do_data4u, inicio, montado_por, fichas, exercicios, resumo}]}`: os treinos do aluno que têm exercício (o ativo primeiro). `404` aluno inexistente |
| `GET /api/treinos/<id>/para-montar` | Um treino de aluno no formato da tela de montar (igual ao de `/api/modelos/<id>`). **Não grava nada.** `404` |
| `GET /api/treinos/<id>/para-editar` | Igual a `/api/treinos/<id>/para-montar`, mais `{id, aluno_id, montado_por, inicio, fim, ativo, origem}` (a tela de editar precisa dos dados do treino). **Não grava nada.** `404` |
| `POST /api/treinos/<id>/editar` | Edita **no lugar** o treino ATIVO criado no app. Corpo JSON igual ao de salvar treino (`nome_treino`, `montado_por`, `inicio`, `fim`, `sessoes_por_ficha`, `fichas`), com a mesma conferência. Troca os dados e **recria as fichas e os exercícios** na mesma gravação (tudo ou nada); o id, o `ativo` e o `criado_em` do treino não mudam. `200 {"id": N}`; `400 {"erros"}`; `404` treino inexistente; `409` treino do Data4U, treino já concluído, ou nome já usado em outro treino do aluno; `413`; `415` |
| `GET /saude` | `{"ok": true}` se o app está de pé e enxerga o banco. **Pública** |

**Todas as rotas acima, menos `/autorizar`, `/api/autorizar`, `/saude`, os arquivos de
`/static` e as do aluno (`/aluno...` e `/api/aluno/...`, que usam o cookie do aluno e só mostram dados do próprio aluno), exigem computador autorizado.** Sem a autorização, as páginas respondem `302` para
`/autorizar` e a API responde `401 {"erro": "..."}` (a mesma resposta exista o aluno ou não, para
não dar para descobrir ids). Rota nova nasce protegida: a lista de rotas públicas
(`ENDPOINTS_PUBLICOS` em `app/web.py`) é que precisa ser aumentada de propósito, e um teste
percorre todas as rotas do app para garantir isso. Páginas e API respondem com
`Cache-Control: no-store` (o navegador não guarda cópia de nome e CPF de aluno).

Número inválido em `grupo` ou `limite` devolve erro 400 em JSON.

O servidor **confere tudo de novo** ao salvar (a tela também confere, mas o navegador não é
confiável): limites do Data4U (nome do treino 40, nome da ficha 15, séries/repetições/carga 11),
séries e repetições opcionais (em branco vale: cardio), intervalo (`pausa`) de 0 a 3.599 s, observação até 200 letras, exercício existente e ativo, bi-set de 2 e tri-set de 3
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
- **Quem registra que o aluno treinou:** o próprio aluno, no celular (decisão do Thiago), pelo botão **"Fiz esta ficha hoje"** da tela `/aluno` (desde 15/10/2026; ver "Meu treino" em "Login do aluno"). **Conta no máximo uma vez por ficha por dia** (decisão do Thiago em 15/10: se o aluno tocar de novo no mesmo dia, o app não conta outra vez). A conta e o aviso "hora de trocar" do professor usam essa contagem. `app/ciclo.py:registrar_sessao` continua sendo o registro de baixo nível (sem a regra do dia); o botão do aluno usa `app/aluno_treino.py:marcar_ficha_feita`.
- **Treinos antigos do Data4U** (migração para a versão 6): de cada aluno, só o treino **mais recente** continua ativo; os outros viram
  inativos. `inicio` do histórico = o dia do lançamento. O importador não mexe em ativo/início/fim/meta/sessões de treino que já veio;
  treino novo do Data4U entra inativo, e só vira o ativo do aluno se for o mais recente dele (o ativo de antes é concluído).
- **Fora desta versão, de propósito:** enviar início/fim/meta de volta ao Data4U (`DT_INICIO`, `DT_FIM`, `NR_SESSOES_PRESCRITAS`);
  registrar *quem* concluiu; aviso de troca na lista de alunos (hoje só na ficha do aluno).

## Treinos padrão e "Importar treino": como funciona

Pedido do Thiago em 09/10/2026: começar um treino sem partir do zero, copiando um treino padrão da academia ou o treino de outro
aluno de perfil parecido.

- **Botão "Importar treino"** (tela Lançar treino, no alto), duas abas: **Treino padrão** (os guardados) e **Treino de outro aluno**
  (busca o aluno e mostra os treinos dele, o ativo primeiro; vale também para repetir um treino antigo do próprio aluno).
- **Importar não grava nada para o aluno.** O treino escolhido entra na tela (fichas, exercícios, séries, repetições, peso, intervalo,
  observação, bi-sets e a meta "treinos por ficha"); o professor confere, ajusta e clica em **Salvar treino**, que passa pela
  conferência de sempre. Se já há exercícios na tela, o painel pergunta antes de substituir. Nome do treino, professor, início e fim
  não vêm junto (são de cada aluno e de cada ciclo).
- **Copiar não liga ao original.** Depois de salvo, o treino é só do aluno; mexer ou apagar o padrão não muda treinos já copiados.
- **Treino padrão** = linha da tabela `modelo_treino` (nome único, professor, meta e o conteúdo em JSON, no mesmo desenho do pedido de
  salvar treino, já conferido). **A tabela começa vazia.** Para criar um: botão **Salvar como treino padrão** dentro de cada treino
  na ficha do aluno, ou no rodapé da tela Lançar treino (guarda o que está na tela, sem salvar nada para o aluno; precisa do campo
  Professor preenchido). Treino com exercício que saiu da lista de exercícios não vira padrão (a mensagem diz quais).
- **Exercício que saiu da lista** (acontece nos treinos antigos do Data4U e, no futuro, se um exercício for desativado): vem marcado
  **"Fora da lista"**, em vermelho, e a tela não deixa salvar enquanto ele estiver lá: o professor remove e escolhe outro. O servidor
  também recusaria.
- **Bi-sets/tri-sets do Data4U fora do molde** (bloco com 1 exercício ou com 4 ou mais) viram exercícios sozinhos ao copiar; blocos
  bons são renumerados.
- **Filas numeradas** (sequência básico, intermediário...): já existem; ver "Filas numeradas: como funciona". **Treino sob medida pelo Claude** (rascunho que o professor confere): já existe; ver "Treino sob medida pelo Claude: como funciona".

## Senha de administrador: como funciona

Pedido do Thiago (13/10/2026): **os treinos padrão ficam fixos.** Eles são montados pela academia (Treino 1 a 6 de cada fila) e o professor
não acrescenta nem exclui padrão por acidente. Quem quiser um treino diferente abre "Importar treino", pega o padrão (ou o treino de outro
aluno) e ajusta **só para aquele aluno**: o padrão nunca muda.

- **Só três ações pedem a senha:** *Salvar como treino padrão* (na tela Lançar treino e na ficha do aluno) e *Excluir* um padrão
  (`POST /api/modelos`, `POST /api/modelos/<id>/excluir`, `POST /api/treinos/<id>/modelo`). Usar, copiar e editar para um aluno continuam livres.
- **Uma senha só**, pedida **toda vez** (não fica lembrada). Só o Thiago a sabe. Ela vai no corpo JSON (`senha_admin`), **nunca na URL**, e a tela
  apaga o campo assim que envia. Não vai para o `sessionStorage`, nem para o console.
- **No servidor:** guardada só como *hash* `scrypt` com sal (tabela `senha_administrador`, uma linha); comparada em tempo constante.
  Mínimo 8 e máximo 128 caracteres. **Sem senha definida, as três ações ficam fechadas** (`403`, `senha: "nao_definida"`). Senha errada: `403`,
  `senha: "incorreta"`. **5 erros em 15 minutos travam** (`429` + `Retry-After`, `senha: "travada"`) até passar o prazo, mesmo com a senha certa.
  A senha é conferida **antes** de achar o padrão (`404`) ou validar o resto.
- **Definir ou trocar a senha** (no terminal do servidor, quem digita é o Thiago; a senha não aparece na tela nem vai para arquivo):
  `python -m app.administrador definir-senha`. `python -m app.administrador situacao` diz só se há senha, quando foi definida e se está travada (nunca a senha).
- **Ajustar vários padrões de uma vez, ou criar padrões novos** (14/10/2026): `python -m app.ajustar_padroes [--lote revisao|filas]` (no terminal do
  servidor; quem digita a senha é o Thiago). Aplica um **lote** decidido item por item: troca textos dentro de padrões já guardados, renomeia
  treino e fichas, coloca um padrão solto numa fila e **cria padrões novos** já no lugar da fila, com **uma senha só**, **cópia de segurança antes**
  e **tudo ou nada**. `--simular` mostra o que mudaria sem pedir senha nem gravar (`--detalhes` lista linha por linha). Os lotes ficam em
  `app/ajustar_padroes.py`: `revisao` (os 12 treinos de Homem e Mulher; já aplicada) e `filas` (Treino 1 de Adolescente, Gestante e Grupos de
  risco; sem `--lote` vale este). Cada linha é conferida por posição, nome do exercício e valor de antes; cada exercício de treino novo é achado
  pelo nome que aparece na tela e tem que existir **uma vez só** na lista ativa; rodar de novo reconhece o que já foi feito. Para um lote novo:
  escrever os `Plano`/`Novo`, registrar em `LOTES`, testar, publicar e rodar `--simular` em produção antes. É uma ferramenta de manutenção, não
  uma tela do app.
- **Limite honesto:** o computador autorizado + a senha protegem de acidente e de curioso. Quem tem acesso ao servidor ou ao banco de dados
  pode contornar (é a regra de qualquer sistema sem conta de usuário).

## Filas numeradas: como funciona

Pedido do Thiago (09/10/2026), decisões de 13/10/2026 (fase 2 da "troca automática"). A fase 3 (treino sob medida montado pelo Claude e
conferido pelo professor) está na seção "Treino sob medida pelo Claude: como funciona".

- **Fila** = sequência de treinos padrão numerados, **do Treino 1 ao Treino 6** (um evolui do outro), para um tipo de aluno. Começam **cinco**, todas **vazias**: Homem,
  Mulher, Adolescente, Gestante e Grupos de risco (tabela `fila`; Gestante e Grupos de risco têm `exige_liberacao`).
- **Montar uma fila:** em **Salvar como treino padrão** (ficha do aluno ou rodapé da tela Lançar treino) escolher a **Fila** e o **Número**.
  O app sugere o próximo número livre e mostra os que já existem. Número repetido na mesma fila é recusado (índice único no banco).
  Depois de guardado, a fila e o número do padrão não mudam (para mudar: excluir e guardar de novo).
- **Colocar o aluno na fila:** cartão **Fila de treino** na ficha do aluno. **Quem escolhe é o professor**, digitando o próprio nome.
  Gestante e Grupos de risco só aceitam depois que o professor marca "conferi a liberação" e informa a data: o app guarda **só "sim",
  a data e o nome do professor** (nunca o atestado nem o motivo, que seriam dado de saúde).
- **O app NÃO troca o treino sozinho.** Ele só **sugere** o próximo número da fila, em dois momentos: o aluno **sem treino ativo** (por
  exemplo, depois de "Concluído") e o treino ativo **na hora de trocar** (meta de treinos por ficha cumprida ou data de fim vencida, o
  aviso de `app/ciclo.py`). A sugestão aparece no alto da tabela de treinos, com o botão **Abrir o Treino N**.
- **Aprovar = salvar.** O botão abre `/alunos/<id>/montar?fila=<treino padrão>`: o treino padrão entra na tela como treino novo (nome
  sugerido "MULHER TREINO 3 13/10/26"; "Importar treino" fica escondido), o professor confere, ajusta e clica em **Salvar treino**. Na
  mesma gravação o treino ativo é concluído (regra de sempre) e o aluno passa para esse número (`aluno_fila.numero_atual`). O professor
  também pode abrir qualquer outro treino da fila pela lista do cartão (**Abrir**).
- **Fim da fila:** quando o aluno já fez o último número, o app avisa "Fim da fila" e **não repete nem recomeça nada**; o professor decide
  (lançar outro treino ou mudar o aluno de fila). Fila sem nenhum treino padrão também avisa.
- **Mudar de fila** zera a posição (começa no início da nova fila); repetir a mesma fila mantém o número. **Tirar da fila** não mexe no
  treino do aluno. Números com buraco (1, 2, 4) funcionam: vale o próximo que existe.
- **Segurança e erros:** tudo é conferido de novo no servidor (fila existente, número de 1 a 6, liberação `true` literal, data não futura,
  aluno realmente na fila do treino). Se a fila do aluno mudar entre abrir e salvar, nada é gravado (tudo ou nada) e a tela mostra o motivo.
  Textos vindos do banco (nome do padrão, professor) entram na página sempre escapados.

## Treino sob medida pelo Claude: como funciona

Fase 3 do "Importar treino" (pedido do Thiago de 09/10/2026; no ar desde 14/10/2026, banco versão 10). Na tela **Lançar treino** há o cartão
**"Treino sob medida"**: o professor responde objetivo, nível, dias por semana e tempo por treino, pode escrever observações (lesão,
preferência) e clica em **Gerar rascunho**. O app pede ao Claude (API da Anthropic) um **rascunho** feito só com exercícios da academia e o
coloca na tela de montar, como um treino importado. **Nada é salvo para o aluno:** o professor confere, ajusta e clica em **Salvar treino**,
como sempre.

**A conversa (14/10/2026, "opção A" do Thiago):** o Claude lê o **treino anterior** do aluno e, antes de montar, pode fazer **até 2 rodadas de
perguntas** ao professor (o que mudar ou evoluir, objetivo, comorbidades, condropatia, lesões, preferências; até 5 perguntas por rodada). O
professor responde na própria tela e a IA monta (ou pergunta mais uma vez). O botão **Montar direto, sem perguntas** pula tudo isso, e
**Montar agora, sem mais perguntas** encerra a conversa no meio. Na última rodada a IA não recebe mais a ferramenta de perguntas: ela é
obrigada a entregar o treino.

- **Como a conversa funciona por dentro (servidor SEM memória):** o servidor não guarda a conversa; quem guarda é a tela
  (`treino_ia.js`), que manda tudo de novo a cada chamada: `POST .../treino-ia` com `perguntar` (true = a IA pode perguntar) e `rodadas`
  (`[{"perguntas": [...], "respostas": [...]}]`, no máximo 2). Cada chamada à IA é independente (uma mensagem só) e é um `ia_pedido` próprio.
  A IA tem **duas ferramentas**: `fazer_perguntas` (só oferecida enquanto `perguntar` e sobrar rodada) e `montar_treino`. Com `tool_choice`
  `auto` quem decide é o texto do pedido ("se ainda faltar informação, chame fazer_perguntas; se basta, chame montar_treino"). O resultado de
  `GET .../treino-ia/<pedido>` é o rascunho (`treino`, `resumo`, `alertas`, `removidos`) **ou** `{"perguntas", "rodada", "maximo_de_rodadas"}`; a
  tela distingue pela presença de `perguntas`. Recarregar a página apaga a conversa (de propósito: resposta sobre saúde não fica em lugar nenhum).
- **Treino anterior** (`treino_anterior`, em `app/ia_treino.py`): o treino **ativo** do aluno; sem ativo, o mais recente que tenha exercício.
  Vai só: ativo ou concluído, há quantos dias começou, nome das fichas e, por exercício, o número na lista da academia (ou "fora da lista"),
  o nome, séries e repetições. **Não vão:** nome do treino, professor, observações, cargas, datas exatas. Nome de ficha que traga parte do
  nome do aluno vira "ficha N". Texto do treino anterior é informação, não ordem.

- **Como o pedido anda:** `POST /api/alunos/<id>/treino-ia` grava uma linha em `ia_pedido` (situação `andando`) e responde `202` na hora; um
  fio de segundo plano chama a API; a tela pergunta a cada 2 s em `GET /api/alunos/<id>/treino-ia/<pedido>` (a resposta leva dezenas de
  segundos e o gunicorn derruba pedido acima de 30 s). Erros do `POST`: `400` (campo inválido), `404`, `409` (aluno em fila que exige
  liberação, ou gravidez nas observações/respostas), `429` (limite), `503` (IA sem chave). Pedido `andando` há mais de 4 min vira `erro`; resultado fica guardado por 3 dias.
- **O que vai para a Anthropic:** objetivo, nível, dias, tempo, o nome da fila do aluno (ex.: "Mulher"), as observações do professor, o
  **treino anterior** (só exercícios, séries e repetições), as **perguntas da IA e as respostas do professor** e as listas de exercícios e
  treinos padrão da academia. **Não vão:** nome, CPF, WhatsApp, e-mail, matrícula, nome do treino, professor nem cargas. O app **recusa**
  observação ou resposta com sequência de 8 ou mais algarismos, com e-mail ou com o nome do aluno (e a tela avisa o mesmo no navegador).
  **Observações e respostas não são guardadas no banco** (só o resultado: as perguntas novas da IA ou o rascunho, por 3 dias).
  **Atenção, dado de saúde:** as respostas costumam falar de comorbidade, condropatia, lesão: é dado pessoal **sensível** (LGPD). Os
  servidores da Anthropic ficam fora do Brasil (espaço "App Academia", geografia Estados Unidos): é transferência internacional de dado.
  O cartão avisa o professor de que o que ele escreve vai para o serviço da IA. A academia deve confirmar com quem cuida da LGPD se isso
  precisa de consentimento do aluno (isto não é parecer jurídico).
- **Quem não usa:** aluno em fila que exige liberação (Gestante, Grupos de risco) e observação **ou resposta** que fala de gravidez: o
  treino é do professor.
- **Limites:** 40 pedidos por dia (dia de Brasília; **cada rodada de perguntas é uma chamada paga e conta**; só contam os que andaram/
  prontos ou com erro depois de gastar token) e 2 ao mesmo tempo. O teto de verdade é o **gasto mensal do espaço "App Academia" na
  Anthropic (US$ 10)**. Medido em 14/10/2026, sem treino anterior nem conversa: 1 rascunho = 17.245 tokens de entrada + 1.531 de saída,
  cerca de **US$ 0,05**. Uma conversa completa (2 rodadas + montagem) são até 3 chamadas, na ordem de US$ 0,15.
- **Catálogo enviado:** só exercícios que a academia usou ao menos 5 vezes no último ano (ou que estão num treino padrão) e até 16 padrões
  como exemplo do jeito da casa. O servidor **desconfia da resposta**: id fora da lista é descartado, textos são cortados nos limites do
  Data4U e o treino passa pela mesma conferência de um treino de verdade (`treinos.validar_fichas`). Texto de observação é dado, não ordem.
- **Chave da API:** num arquivo ao lado do banco (`/dados/ia_chave`, permissão `0600`); nunca no banco, no código, no navegador nem em
  backup. No terminal do contêiner (quem digita é quem cuida do servidor; a chave não aparece na tela): `python -m app.ia_treino
  definir-chave`; `situacao` (chave guardada?, modelo, pedidos de hoje, tokens do mês); `testar` (chamada mínima); `diagnosticar [--esforco
  low|medium|high] [--sem-pensar] [--dias N] [--minutos N] [--observacoes "..."] [--perguntar] [--aluno N]` (pedido real **sem salvar
  nada**: mostra tempo, tokens, custo estimado e o rascunho; `--perguntar` deixa a IA perguntar e mostra as perguntas; `--aluno N` manda
  também o treino anterior desse aluno).
- **Regras do modelo (Claude Sonnet 5.5; conferidas na documentação da Anthropic):** `tool_choice` "tool"/"any" dá erro 400, então usamos
  `auto` + ferramenta `strict` + ordem escrita no pedido; `thinking` ligado por padrão (adaptativo) e `{"type":"disabled"}` dá 400 (o
  jeito de desligar é `between_tools`); `temperature`/`top_p`/`top_k` fora do padrão e *prefill* dão 400; o esforço vai em
  `output_config.effort` (padrão do app: `medium`). O esquema `strict` não aceita `minimum`/`maximum`/`minLength`/`maxLength`/`maxItems`
  (limites ficam nas descrições e na conferência do servidor). Testes travam tudo isso (`tests/test_ia_treino.py`).
- **Voltar atrás:** banco versão 10 só acrescenta a tabela `ia_pedido`. Para a imagem anterior (`b4860bf`, que conhece até a versão 9):
  app parado, `PRAGMA user_version = 9`, ou restaurar a cópia feita antes da migração. Sem a chave, o botão responde `503` e o resto do app não muda. A conversa com perguntas **não muda o banco** (continua versão 10).

## Editar treino: como funciona

Pedido do Thiago (09/10/2026): o professor precisa poder abrir o treino do aluno e corrigi-lo (e, no futuro, agir sobre os comentários
que o aluno fizer no app dele).

- **Onde fica:** botão **Editar treino** dentro do treino **ativo** na ficha do aluno (treino concluído não tem o botão; para usar um
  treino antigo, "Importar treino").
- **Treino criado no app** (`origem` = app): a tela de montar abre com tudo preenchido (`/alunos/<id>/montar?editar=<treino>`) e
  **Salvar alterações** muda o MESMO treino (mesmo id, continua ativo, mantém a data em que foi montado). As mudanças valem na hora
  para o aluno.
- **Treino vindo do Data4U** (`origem` = data4u): a atualização de alunos recopia esses treinos do Data4U e desfaria a edição. Por
  isso o botão abre uma **cópia** (`?copiar=<treino>`); ao salvar, ela vira um treino **novo** do app e o antigo é **concluído**
  (decisão do Thiago: "Criar treino novo").
- **Professor:** o campo começa vazio; quem está editando digita o próprio nome e ele **substitui** o professor do treino (a dica
  mostra quem era o anterior).
- **Sem rascunho:** na edição o rascunho do navegador fica desligado (não mistura com um treino novo do mesmo aluno). Se a página for
  recarregada, volta ao que está salvo; sair com alteração pergunta antes de descartar.
- **Endereço ruim** (`?editar=abc`, treino de outro aluno, treino concluído ou do Data4U, treino inexistente): `?editar=abc` cai na
  tela normal de lançar treino; os outros mostram uma faixa vermelha explicando e **não** mostram a área de montagem (nada é alterado).
- **Cuidado para o futuro:** editar no lugar apaga e recria as fichas e os exercícios, então os **ids de ficha e de exercício do
  treino mudam**. As sessões já feitas (`sessao`) ficam ligadas pelo número da ficha, e continuam valendo. Os comentários do aluno
  (ainda não existem) devem apontar para o treino, o número da ficha e o exercício, nunca para o id do item da ficha.

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

## Atualização automática dos alunos: como funciona

Pedido do Thiago de 14/10/2026 ("atualizar os alunos todo dia sem ninguém clicar"). Antes, alguém da recepção escolhia o
`base_total.zip` na tela todo dia; agora o PC da recepção manda sozinho.

- **Quem faz o quê:** a extração do Data4U (tarefa `GloriaFit-ExtracaoDiaria`, 05:00, 08:00 e 12:00) continua igual. Uma
  segunda tarefa, `GloriaFit-EnvioDiario`, roda `enviar_alunos.py` **15 minutos depois** de cada uma (05:15, 08:15 e 12:15), sem
  janela (`pythonw`), só com o usuário logado e, se o PC estava desligado na hora, assim que ligar (`StartWhenAvailable`).
- **O que o programa faz:** espera a extração terminar, se ela estiver rodando (arquivo `base_total_nova.zip` recente, até 25 min);
  abre só 4 a 9 entradas do `.zip` (as outras 250 tabelas nem são lidas); confere contra o `_manifesto.json`; monta os **mesmos
  dois pacotes** da tela (`copia_modelo.js` é a referência; `tests/test_enviar_alunos.py` roda os dois sobre o mesmo `.zip` e exige
  resultado igual); manda primeiro os alunos e depois o histórico de treinos para as mesmas rotas da tela.
  **Só envia cópia mais nova que a última enviada** (por isso o das 08:15 e o das 12:15 quase sempre são "nada novo"); cada
  assunto tem o seu registro (`enviar_alunos_estado.json`), então se o histórico falhar os alunos não vão de novo.
  Sem internet, tenta 3 vezes (1 min entre elas); resposta do servidor nunca é repetida na hora (a próxima chance é o próximo horário).
- **Onde ficam os arquivos (na pasta NFSE do PC):** `enviar_alunos.py`, `enviar_alunos_dispositivo.txt` (a chave do PC),
  `enviar_alunos_estado.json` e `enviar_alunos_log.txt` (o que aconteceu em cada rodada; vira `.antigo.txt` aos 300 KB).
- **Autorização:** o PC é um "dispositivo" como o navegador: uma vez, `python enviar_alunos.py --autorizar` troca um código de
  uso único (`python -m app.dispositivos codigo --nome "PC da recepção (envio automático)"`) pela chave, que o servidor guarda só
  como hash. Dá para ver e cortar: `python -m app.dispositivos listar` / `revogar N`. **Risco aceito:** a chave abre a área do
  professor inteira, não só a importação, e fica num arquivo da pasta NFSE; mas ali já está o `base_total.zip` com o banco inteiro do
  Data4U, e o Chrome da recepção já tem o cookie de acesso. Se um dia isso incomodar, o caminho é uma chave que só vale para as
  duas rotas de importação (exige mudança no servidor e nos testes).
- **Segurança:** só `https://` (a chave não viaja aberta; `http://localhost` só para teste); redirecionamento do servidor é erro,
  não é seguido (um POST redirecionado perderia o corpo em silêncio); a chave nunca vai para o log nem para a tela; o programa
  **não se atualiza sozinho** (instalar uma versão nova é baixar de novo à mão), para que um servidor comprometido não mande código
  para o PC.
- **Se parar, o app avisa:** cada importação bem-sucedida grava em `importacao` a hora da cópia (tabela nova, banco versão 11). Passando
  de 48 horas, a busca de alunos mostra uma faixa laranja e a tela "Atualizar alunos" marca "atrasado". 48 h cobre um fim de semana
  de PC desligado; um dia inteiro sem cópia nova já aparece. Assunto nunca registrado não avisa (o aviso vale a partir da primeira cópia).
- **Instalar no PC** (uma vez; o programa vem do próprio app): na pasta NFSE, baixar
  `https://app.gloriafit.com.br/static/recepcao/enviar_alunos.py`; `python enviar_alunos.py --conferir` (monta os pacotes e mostra o
  resumo, sem enviar nada); `python enviar_alunos.py --autorizar` (o Thiago digita o código); `python enviar_alunos.py` (primeiro envio, à mão);
  `python enviar_alunos.py --instalar` (cria a tarefa agendada). Para desfazer: `schtasks /Delete /TN GloriaFit-EnvioDiario /F`.
- **Medido com tabelas do tamanho real (sintéticas, 176 mil lançamentos e 129 mil exercícios prescritos):** ~2,6 s e até ~0,5 GB de memória para montar
  os dois pacotes (2 + 7 MB); o programa guarda só as colunas usadas, então na prática gasta menos. O servidor leva 2 a 2,5 s para gravar o
  histórico. Em Python de 32 bits o limite é de 2 a 4 GB: folgado.
- **Voltar atrás:** o banco versão 11 só acrescenta a tabela `importacao`. Para a imagem anterior (`e9c6961`, que conhece até a versão 10): app parado,
  `PRAGMA user_version = 10` (a tabela fica lá, sem atrapalhar), ou restaurar a cópia feita antes da migração. O PC continua tentando enviar e
  acusando erro no log; nada se perde (enviar de novo não duplica).
- **Não testado ainda no PC de verdade:** `--instalar` (criar a tarefa com `schtasks`) e a execução com `pythonw` só podem ser provados no
  Windows; o XML da tarefa tem teste de formato, mas não de execução.

## Login do aluno: como funciona

*Feito em 15/10/2026 (banco versão 12). O aluno entra pelo celular, em `/aluno/entrar`. Testado de ponta a ponta em produção no celular do Thiago em 15/10 (código no WhatsApp, senha, sair e entrar de novo). A tela do aluno logado mostra o treino ativo (seção "Meu treino", logo abaixo).*

**Primeiro acesso e "esqueci a senha" (o mesmo caminho):**
1. O aluno digita o CPF e toca em "Enviar o código". O app sorteia um código de **6 números** (`secrets`), guarda **só o hash** (vale **10 minutos**, **5 tentativas**) e o manda ao WhatsApp cadastrado pelo modelo `codigo_acesso_app` da Meta (`app/whatsapp.py`), em segundo plano.
2. A resposta da tela é **sempre a mesma**, com ou sem aluno, com ou sem WhatsApp ("se o CPF estiver liberado, o código chega..."): assim a tela não serve para descobrir quem é aluno. Por isso a tela **não mostra** o número com algumas casas escondidas (como o doc 24 sugeria): mostrar revelaria que o CPF existe.
3. O aluno digita o código e escolhe a senha (8 a 128 caracteres; recusa as óbvias, como o CPF e `12345678`). Se o código confere, a senha é guardada com **scrypt** (o mesmo hash lento da senha de administrador) e ele já entra. Senha que não serve **não gasta** o código.
4. Senha nova **derruba todos os outros celulares** em que ele estava logado (se o celular foi perdido, "esqueci a senha" resolve).

**No dia a dia:** CPF + senha. O celular guarda o cookie `gloriafit_aluno` (HttpOnly, SameSite=Lax, Secure fora do localhost, 90 dias, renovado a cada hora de uso); o banco guarda só o hash. Sessão sem uso por 90 dias perde o acesso.

**Quem pode entrar (decisão do Thiago em 15/10/2026):** **qualquer aluno do Data4U, seja qual for a situação** (Ativo, Trancado, Pendente, Desistente, Inativo, Cancelado). Motivo: quem vem pelo Wellhub ou pelo TotalPass aparece como Inativo no Data4U, mas a academia monta treino para essas pessoas. Fica de fora só o aluno **provisório** (cadastro feito à mão no app; o mesmo CPF costuma voltar quando o Data4U o traz e os dois são juntados). **CPF em mais de um cadastro** (3 casos em 15/10; o do próprio Thiago é um deles: um Inativo e um Desistente): o app escolhe sozinho o melhor cadastro, nesta ordem de situação: Ativo, Trancado, Pendente, Inativo, Desistente, Cancelado; empate, o mais novo (maior `data4u_id`, depois maior `id`). O código vai para o WhatsApp do escolhido e a sessão fica presa a ele. Se os cadastros forem de pessoas diferentes (CPF digitado errado), a outra pessoa não consegue entrar até a recepção arrumar (ninguém vê dado de outra pessoa). Limitação: se a escolha mudar de um cadastro para o outro (por exemplo, o aluno comprou plano no cadastro que era o pior), a senha criada no primeiro não vale no segundo e ele refaz o "primeiro acesso". A conferência vale **a cada pedido**, com o cadastro de hoje. A regra está em `_quem_pode_entrar` e `_escolher_o_cadastro` em `app/aluno_acesso.py` (antes de 15/10 só entrava situação Ativo). Como todo o cadastro (cerca de 5.500 pessoas, perto de 3.500 com WhatsApp) pode pedir código, o teto de 500 códigos por dia e os limites por CPF e por endereço são a proteção contra gasto e abuso. Quem não tem WhatsApp no app (ou o tem errado) não recebe o código: a recepção corrige na ficha do aluno (o número do app vale mais que o do Data4U).

**Limites de tentativa (todos contam também CPF que não existe, com a mesma regra, para o bloqueio não revelar quem é aluno; CPF e endereço entram na tabela `aluno_evento` como hash e somem em 1 dia):**

| O quê | Limite |
|---|---|
| Pedidos de código por CPF | 1 por minuto e 5 por dia |
| Pedidos de código por endereço (IP) | 60 por hora (alto de propósito: a academia inteira usa o mesmo wi-fi) |
| Códigos no app inteiro | 500 por dia (`CODIGOS_POR_DIA`; cada um é uma mensagem paga, cerca de R$ 0,035) |
| Tentativas por código | 5 (depois ele morre) |
| Códigos errados ou senhas erradas | 5 por CPF e 50 por endereço a cada 15 min (travado, nem confere o que vier; destrava sozinho) |

Contas do pior caso: um CPF tem no máximo 25 palpites por dia contra 1.000.000 de códigos possíveis. "Esqueci a senha" ignora o travamento de login (quem prova que tem o WhatsApp destrava) e acertar zera os erros. Senha errada, CPF que não existe, aluno sem senha e aluno que não pode entrar dão **a mesma resposta e o mesmo trabalho** (o hash lento roda nos quatro casos).

**Configurar a Meta (uma vez, no terminal do servidor; o Claude nunca vê o token):**
```
python -m app.whatsapp configurar     # pergunta o ID do número de telefone e o token (o token não aparece na tela)
python -m app.whatsapp testar 27999998888   # manda o código de teste 000000 a esse WhatsApp
python -m app.whatsapp situacao       # configurado? códigos das últimas 24 h (enviados, falharam, e os motivos)
```
Sem a configuração o pedido de código responde `503` ("o envio ainda não está liberado") e nada é criado. O arquivo `/dados/whatsapp.json` vale na hora, sem reiniciar o app. A versão da API da Meta (`v24.0`, a mais nova na página de versões da Meta em 15/10/2026) fica no arquivo e pode ser trocada com `configurar --versao`. "Enviado" no banco quer dizer que a **Meta aceitou** a mensagem; se chegou no celular só a Meta sabe.

**Meu treino (tela `/aluno`, 15/10/2026):** depois de entrar, o aluno vê o **treino ativo** dele (a regra de 08/10: só um ativo por aluno; treino concluído ou trocado fica só no histórico do professor). Botões com as fichas (A, B, C; só aparecem se houver mais de uma), e cada ficha lista os exercícios na ordem, com `séries × repetições · carga`, "Intervalo" e "Obs." quando existem; bi-set e tri-set aparecem num quadro com "Faça A1 e A2 seguidos" (mesmas etiquetas e frases do cupom impresso). A conta toda é feita no servidor (`app/aluno_treino.py`, com as mesmas funções do cupom); o navegador (`aluno_inicio.js`) só desenha, sempre com `textContent` (um nome de exercício com HTML aparece como texto). Sem treino ativo: "Você ainda não tem um treino ativo. Fale com o seu professor na academia." O treino do Data4U (espelho) também aparece. **O que o aluno não vê:** ids, quem montou, de onde veio, "hora de trocar" e treinos antigos. **"Fiz esta ficha hoje" (15/10/2026):** embaixo de cada ficha há o andamento ("Você fez esta ficha 3 de 15 vezes", ou só "3 vezes" se o treino não tem meta) e o botão. **No máximo uma vez por ficha por dia** (decisão do Thiago), com "hoje" no calendário de Brasília (a ficha marcada às 23h55 e às 00h05 conta em dias diferentes; testado com a virada do dia em UTC). Depois de marcar aparece "Marcada como feita hoje" e o botão **"Desfazer (marquei sem querer)"**, que só apaga a marcação de hoje daquela ficha (suposição minha, declarada). A conferência e a gravação ficam na mesma transação (`BEGIN IMMEDIATE`): dois toques ao mesmo tempo, ou dois celulares, gravam uma vez só (testado com duas conexões em paralelo). O aluno só marca no **próprio treino ativo**; o número da ficha vem no corpo, o aluno e o treino vêm do cookie. O aluno **não vê** o aviso "hora de trocar": só o professor. Limite conhecido: a marcação é a palavra do aluno (ninguém confere se ele treinou); quem marca e desfaz sem parar só gera gravações, nunca mais de uma marcação por ficha por dia. **Ainda não existe:** vídeo do exercício (o banco não tem) e comentários. Limitação: com CPF repetido a sessão fica presa ao melhor cadastro, e se o treino foi montado no outro cadastro o aluno vê "sem treino ativo" (a recepção junta os cadastros no Data4U).

**Voltar atrás:** o banco versão 12 só acrescenta quatro tabelas. Para a imagem anterior (`842ef45`, que conhece até a versão 11): app parado, `PRAGMA user_version = 11` (as tabelas ficam lá, sem atrapalhar; as senhas criadas continuam valendo quando se sobe de novo), ou restaurar a cópia feita antes da migração (`/dados/antes-da-migracao`).

**Limitações conhecidas:**
- O envio pela Meta foi **provado em produção em 15/10/2026** (o código de teste e o de login chegaram no WhatsApp do Thiago). O token foi gerado com validade "Nunca" (pedido; a tela não foi conferida): se os códigos pararem de chegar por volta de 60 dias, gerar um token novo.
- Número de WhatsApp de 10 dígitos (DDD + 8) é enviado como está, com o `55` na frente; se a Meta o aceita ou não só o teste real mostra.
- Quem tem a cópia do banco dentro dos 10 minutos de vida de um código pode achá-lo testando os 1.000.000 de possibilidades; mas quem tem a cópia do banco já tem tudo o que o app guarda.
- Quem quiser atrapalhar o "esqueci a senha" de um aluno consegue travá-lo por 15 minutos (5 códigos errados no CPF dele); não consegue entrar.
- O endereço do app ainda não é divulgado: só aparece o link "É aluno da academia?" na tela de autorizar; o endereço do app no cupom (`GLORIAFIT_ENDERECO_DO_APP`) continua em aberto.

## Cuidados

- **Cardio e exercícios sem dose:** séries e repetições podem ficar em branco (pedido do Thiago,
  08/10/2026): o professor escreve o tempo ("15 MIN") em Repetições ou em Observações, ou deixa em branco.
  No banco, em branco vira NULL (como no histórico do Data4U). CARDIO, ESTEIRA, BIKE e ESCADA já existem
  no quadro; **ELÍPTICO** é um exercício só do app (`app/exercicios_do_app.py`; rodar uma vez em cada
  banco: `python -m app.exercicios_do_app /dados/app.db`). Ele não existe no Data4U: antes de devolver
  treinos ao Data4U, precisa ser criado lá ou ligado a um exercício de lá.
- **Nome do exercício sem o número da máquina:** o Data4U guarda em alguns exercícios o número da
  máquina no começo do nome ("(15) CADEIRA ABDUTORA"). Nem toda máquina é numerada, então o número
  perdeu o sentido (decisão do Thiago, 08/10/2026). `app/texto.py: nome_para_exibir` tira só o
  número do INÍCIO ("(15) ", "( 7 ) " e "9)") na lista de exercícios, na ficha do aluno e no cupom.
  O banco guarda o nome original (é a chave do exercício e a ligação com o Data4U); só a exibição muda.
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
- **Atualização do banco (migração).** Os bancos das versões 4, 5, 6 e 7 sobem sozinhos até a 8 (a 4 -> 5 é a de
  07/10/2026; a 5 -> 6 é o ciclo do treino, de 08/10/2026; a 6 -> 7 acrescenta a tabela dos treinos padrão, de 09/10/2026; a 7 -> 8 acrescenta as filas numeradas, de 13/10/2026) quando o app novo liga: antes de mexer, o app tira uma cópia
  consistente em `<pasta do banco>/antes-da-migracao/` (uma por subida, guarda as 5 últimas); cada passo roda numa
  transação (ou muda tudo, ou nada); os 2 processos do gunicorn subindo juntos não migram duas vezes. Banco mais antigo
  que a versão 4 ainda é recusado (`BancoDesatualizado`).
  **Voltar atrás:** depois que o banco virou versão 8, a imagem ANTIGA do app se recusa a abrir (ela só
  conhece a 7; a 6, a 5 e a 4 idem). **Só da 8 para a imagem da versão 7** (`3629c30` ou `e5b09fc`) há um atalho testado numa cópia:
  baixar o número de versão do banco (`PRAGMA user_version = 7`, com o app parado), porque o código antigo ignora as tabelas e colunas
  novas das filas; ao subir a 8 de novo, a migração 7 -> 8 repete sem perder nada (há teste). Para voltar à imagem antiga é preciso também voltar o arquivo: copiar a cópia de
  `/dados/antes-da-migracao/` (ou uma de `/backups`) por cima de `/dados/app.db` com o app parado. Nunca apagar
  o banco para "resolver": o erro de versão **mais nova** diz isso na mensagem.
- O importador **não copia** senha, RG, nascimento, salário nem observações do Data4U: lê só
  nome, CPF, situação e celular. Mas o `.zip` que ele lê tem o banco inteiro: tratar o arquivo
  como dado sensível (não vai para o Git, não fica em pasta pública, apagar do servidor depois de importar).

## Ainda em aberto (de propósito, não decidido)

- Qual dos ids do Data4U usar ao gravar um exercício que tem mais de um.
- Login do aluno: aluno provisório não entra (decidir se deve, quando o Thiago pedir); CPF repetido no Data4U fica com o melhor cadastro (ver "Login do aluno").
- Como início/fim/meta e as sessões feitas voltam ao Data4U (o botão "Fiz esta ficha hoje" já grava na tabela `sessao` do app).
- Tela de "aparelhos autorizados" dentro do app (hoje só pelo comando no servidor).
- Aviso de "combinação nova no Data4U" (o desenho mostra na montagem e no salvar): precisa
  saber quais combinações já existem como um exercício só; entra no passo de salvar.
- Qual `professor_id` do Data4U usar ao enviar o treino para lá (o app guarda só o nome digitado;
  a fila do Data4U exige um id de pessoa).
- Se o Data4U aceita séries/repetições vazias (o app aceita em branco, para o cardio).
- A busca de alunos mostra o **último treino** (o mais novo, do app ou do histórico), que normalmente é o ativo; o aluno vê o treino ativo no celular (`/aluno`).
- A **situação** mostrada é a letra do Data4U (Ativo, Pendente...), no lugar do "Em dia" do
  desenho. "Em dia" não foi verificado (o desenho dizia "pagou nos últimos 30 dias").
- Importar todo dia, **sozinho**: feito em 14/10/2026 (ver "Atualização automática dos alunos"). Em aberto: provar `--instalar` e a
  tarefa agendada no PC da recepção, e uma chave que só valha para as rotas de importação (hoje a chave do PC vale para a área toda).
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
