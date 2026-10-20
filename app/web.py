"""Servidor web do app Glória Fit (Flask).

Rodar em desenvolvimento (só na sua máquina):
    GLORIAFIT_DB=app.db python -m flask --app "app.web:criar_app" run --debug
NUNCA use --debug num servidor aberto à internet: ele libera um console que
executa código de quem acessar.
"""

import os
import threading
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, abort, g, jsonify, redirect, render_template, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from app import (
    acesso,
    administrador,
    aluno_acesso,
    aluno_treino,
    alunos,
    ciclo,
    comentarios,
    cupom,
    datas,
    db,
    exercicios,
    filas,
    ia_treino,
    importacoes,
    importar_alunos,
    importar_treinos,
    modelos,
    provisorios,
    treinos,
    whatsapp,
)

# Um treino enorme (26 fichas x 100 exercícios) tem poucas dezenas de KB. Acima disto o
# pedido é recusado antes de ser lido inteiro: ninguém precisa mandar megabytes para salvar.
TAMANHO_MAXIMO_DO_PEDIDO = 512 * 1024

# Só as rotas de "Atualizar alunos" recebem um pedido grande: as 3 tabelas dos alunos, com só as
# colunas usadas, dão alguns MB (51 mil linhas de situação), e o histórico de treinos uns 8 MB
# (129 mil exercícios prescritos). O teto vale só para elas.
TAMANHO_MAXIMO_DA_IMPORTACAO = 25 * 1024 * 1024


# Páginas e rotas que NÃO exigem computador autorizado (o resto exige). Quem cria uma
# rota nova e esquece de pensar nisso fica protegido por padrão, não exposto.
#   static: CSS e JavaScript, que não têm dado nenhum.
#   saude: só diz "ok" (o servidor usa para saber se o app está de pé).
#   pagina_autorizar / api_autorizar: a tela e a rota onde o código é digitado.
#   pagina_aluno_* / api_aluno_*: o login do aluno, pelo celular dele (app/aluno_acesso.py). Não usam computador
#     autorizado: cada uma confere o cookie do aluno (outro cookie, outra tabela) e só mostra dados do próprio aluno.
ENDPOINTS_PUBLICOS = frozenset(
    {
        "static",
        "saude",
        "pagina_autorizar",
        "api_autorizar",
        "pagina_aluno_entrar",
        "pagina_aluno_inicio",
        "api_aluno_pedir_codigo",
        "api_aluno_definir_senha",
        "api_aluno_entrar",
        "api_aluno_sair",
        "api_aluno_treino",
        "api_aluno_treino_feito",
        "api_aluno_treino_desfazer",
        "api_aluno_comentario",
        "api_aluno_comentarios",
        "api_aluno_comentarios_vistos",
    }
)

# Métodos que só leem. Os outros (POST etc.) mudam dados e passam pela checagem de origem.
METODOS_QUE_SO_LEEM = frozenset({"GET", "HEAD", "OPTIONS"})

# HSTS: depois de ver o site em HTTPS, o navegador se recusa a abri-lo em http pelo prazo
# abaixo. Começa em 1 semana de propósito: se algo der errado com o HTTPS, o estrago dura
# pouco. Quando tudo estiver estável, dá para subir para 1 ano (31536000).
HSTS_SEGUNDOS = 7 * 24 * 3600

# Nesses endereços (desenvolvimento) o navegador aceita cookie sem HTTPS; em qualquer
# outro o cookie é marcado "Secure" e só trafega por HTTPS.
NOMES_LOCAIS = frozenset({"localhost", "127.0.0.1", "::1"})


class ErroDeEntrada(Exception):
    """Pedido com dado inválido (vira resposta 400 em JSON)."""

    status = 400


class TipoNaoSuportado(ErroDeEntrada):
    """O pedido não veio como JSON (vira resposta 415 em JSON)."""

    status = 415


class SenhaDeAdministradorRecusada(Exception):
    """A ação exige a senha de administrador e ela não passou (vira resposta 403 ou 429 em JSON).

    `motivo` ("incorreta", "nao_definida" ou "travada") deixa a tela saber o que aconteceu sem ler a frase.
    """

    def __init__(self, mensagem: str, motivo: str, status: int = 403, espera: int | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.motivo = motivo
        self.status = status
        self.espera = espera


def criar_app(caminho_banco: str | Path | None = None) -> Flask:
    """Monta o aplicativo. Sem argumento, usa o arquivo de GLORIAFIT_DB (ou app.db)."""
    caminho = Path(caminho_banco or os.environ.get("GLORIAFIT_DB", "app.db"))
    if not caminho.is_file():
        # Sem esta checagem o SQLite criaria um banco vazio em silêncio, e o erro
        # só apareceria depois como "no such table". Melhor falhar já, com clareza.
        raise FileNotFoundError(
            f"Banco de dados não encontrado em '{caminho}'. Crie-o antes com: "
            "python -m app.importar_exercicios dados/quadro_exercicios_v2.xlsx app.db"
        )

    # Banco de versão antiga que sabemos atualizar: é atualizado agora, na subida, com uma cópia
    # de segurança antes (ver db.migrar). Banco que não sabemos atualizar: falha já aqui (com a
    # explicação), não na hora de salvar.
    conn_inicial = db.conectar(caminho)
    try:
        db.migrar(conn_inicial)
        db.verificar_versao(conn_inicial)
    finally:
        conn_inicial.close()

    app = Flask(__name__)
    app.config["CAMINHO_BANCO"] = str(caminho)
    app.config["MAX_CONTENT_LENGTH"] = TAMANHO_MAXIMO_DO_PEDIDO
    # No servidor o app fica ATRÁS de um proxy (Traefik), que cuida do HTTPS e repassa o
    # pedido por http. GLORIAFIT_ATRAS_DE_PROXY=1 faz o app acreditar nos cabeçalhos
    # X-Forwarded-* (endereço e https de verdade). SÓ ligue se o app NÃO for acessível sem
    # passar pelo proxy: senão qualquer um poderia forjar esses cabeçalhos.
    if os.environ.get("GLORIAFIT_ATRAS_DE_PROXY") == "1":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    # Endereço público do app (ex.: app.gloriafit.com.br). Se definido, pedido com outro
    # endereço no cabeçalho Host é recusado (400).
    dominio = os.environ.get("GLORIAFIT_DOMINIO", "").strip()
    if dominio:
        app.config["TRUSTED_HOSTS"] = [dominio]
    # Endereço do app do aluno, impresso no fim do cupom. Vazio (o normal hoje, o app do aluno
    # ainda não existe) = o cupom não fala do app. Defina GLORIAFIT_ENDERECO_DO_APP quando existir.
    app.config["ENDERECO_DO_APP"] = os.environ.get("GLORIAFIT_ENDERECO_DO_APP", "").strip() or None
    app.json.ensure_ascii = False  # acentos legíveis no JSON
    # Treino sob medida (IA): quem fala com a API da Anthropic e se o trabalho roda em segundo plano. Os testes trocam os dois
    # (API falsa, sem fio) para nunca chamar a API de verdade.
    app.config["IA_CHAMADA"] = ia_treino.chamar_claude
    app.config["IA_EM_SEGUNDO_PLANO"] = True
    # Código de acesso do aluno por WhatsApp: quem manda (a Meta; a configuração fica em /dados/whatsapp.json) e se o envio roda
    # em segundo plano. Os testes trocam os dois (remetente falso, sem fio) para nunca falar com a Meta de verdade.
    app.config["WHATSAPP"] = whatsapp.Remetente(whatsapp.caminho_da_configuracao(caminho))
    app.config["WHATSAPP_EM_SEGUNDO_PLANO"] = True

    def conexao():
        # Uma conexão por pedido: o SQLite não deve ser compartilhado entre
        # threads, e o servidor atende vários pedidos ao mesmo tempo.
        if "conn" not in g:
            g.conn = db.conectar(app.config["CAMINHO_BANCO"])
        return g.conn

    @app.teardown_appcontext
    def fechar_conexao(_erro):
        conn = g.pop("conn", None)
        if conn is not None:
            conn.close()

    @app.after_request
    def cabecalhos_de_seguranca(resposta):
        # Cabeçalhos que pedem ao navegador para ser mais rígido.
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        resposta.headers["X-Frame-Options"] = "DENY"
        resposta.headers["Referrer-Policy"] = "same-origin"
        # Só aceita script/estilo/imagem do próprio site: se alguém conseguir
        # injetar um <script> numa página, o navegador se recusa a executá-lo.
        resposta.headers["Content-Security-Policy"] = (
            "default-src 'self'; frame-ancestors 'none'"
        )
        if request.is_secure:
            resposta.headers["Strict-Transport-Security"] = f"max-age={HSTS_SEGUNDOS}"
        if request.endpoint != "static":
            # Páginas e respostas da API têm nome e CPF de aluno: o navegador não guarda cópia.
            resposta.headers["Cache-Control"] = "no-store"
        if g.get("renovar_cookie"):
            definir_cookie_do_dispositivo(resposta, g.renovar_cookie)
        if g.get("renovar_cookie_aluno"):
            definir_cookie_do_aluno(resposta, g.renovar_cookie_aluno)
        return resposta

    # ------------------------------------------------------------ computador autorizado

    def definir_cookie_do_dispositivo(resposta, token: str) -> None:
        resposta.set_cookie(
            acesso.NOME_DO_COOKIE,
            token,
            max_age=int(acesso.DURACAO_DO_COOKIE.total_seconds()),
            httponly=True,  # JavaScript da página não consegue ler o cookie
            secure=urlsplit("//" + request.host).hostname not in NOMES_LOCAIS,
            samesite="Lax",  # outro site não consegue mandar este cookie junto de um POST
            path="/",
        )

    def dispositivo_atual():
        """O computador autorizado deste pedido, ou None. Confere uma vez por pedido."""
        if "dispositivo" not in g:
            token = request.cookies.get(acesso.NOME_DO_COOKIE)
            g.dispositivo = acesso.identificar(conexao(), token) if token else None
            if g.dispositivo is not None and g.dispositivo.renovar_cookie:
                g.renovar_cookie = token  # o after_request renova o cookie (mais 400 dias)
        return g.dispositivo

    # ------------------------------------------------------------ aluno logado (celular do aluno)

    def definir_cookie_do_aluno(resposta, token: str) -> None:
        resposta.set_cookie(
            aluno_acesso.NOME_DO_COOKIE,
            token,
            max_age=int(aluno_acesso.DURACAO_DO_COOKIE.total_seconds()),
            httponly=True,  # JavaScript da página não consegue ler o cookie
            secure=urlsplit("//" + request.host).hostname not in NOMES_LOCAIS,
            samesite="Lax",
            path="/",
        )

    def aluno_atual():
        """O aluno logado neste pedido, ou None. Confere uma vez por pedido. Nada a ver com o computador autorizado."""
        if "aluno" not in g:
            token = request.cookies.get(aluno_acesso.NOME_DO_COOKIE)
            g.aluno = aluno_acesso.identificar(conexao(), token) if token else None
            if g.aluno is not None and g.aluno.renovar_cookie:
                g.renovar_cookie_aluno = token  # o after_request renova o cookie
        return g.aluno

    @app.before_request
    def guarda_da_area_do_professor():
        # 1) Pedido que muda dados e veio de outro site: recusado. O navegador sempre
        #    informa de onde o pedido saiu (cabeçalho Origin); se não for este mesmo
        #    endereço, é outro site tentando agir em nome de quem está logado aqui.
        #    Compara esquema (http/https) e endereço (host:porta). Atrás do proxy, o esquema
        #    certo só chega com GLORIAFIT_ATRAS_DE_PROXY=1; sem isso, no servidor, todo POST
        #    seria recusado (falha para o lado seguro, e visível).
        if request.method not in METODOS_QUE_SO_LEEM:
            origem = request.headers.get("Origin")
            if origem is not None:
                partes = urlsplit(origem)
                if (partes.scheme, partes.netloc) != (request.scheme, request.host):
                    return jsonify(erro="Pedido recusado: ele não saiu deste site."), 403

        # 2) Rota que não existe (404) ou pública: segue.
        if request.endpoint is None or request.endpoint in ENDPOINTS_PUBLICOS:
            return None

        # 3) Todo o resto exige computador autorizado.
        if dispositivo_atual() is not None:
            return None
        if request.path.startswith("/api/"):
            return (
                jsonify(
                    erro="Este computador não está autorizado. "
                    "Abra o endereço /autorizar e digite um código novo."
                ),
                401,
            )
        return redirect(url_for("pagina_autorizar"))

    @app.context_processor
    def nome_do_computador():
        # Aparece no topo das telas ("Computador dos professores").
        dispositivo = g.get("dispositivo")
        return {"dispositivo_nome": dispositivo.nome if dispositivo else None}

    @app.context_processor
    def contador_de_comentarios():
        # O número do menu "Comentários". É uma função (e não um número) para a conta só rodar nas telas que a usam (o topo do professor).
        return {"comentarios_novos": lambda: comentarios.contar_nao_lidos(conexao())}

    @app.errorhandler(ErroDeEntrada)
    def entrada_invalida(erro):
        return jsonify(erro=str(erro)), erro.status

    @app.errorhandler(SenhaDeAdministradorRecusada)
    def senha_de_administrador_recusada(erro):
        resposta = jsonify(erro=erro.mensagem, senha=erro.motivo)
        resposta.status_code = erro.status
        if erro.espera is not None:
            resposta.headers["Retry-After"] = str(erro.espera)
        return resposta

    @app.errorhandler(413)
    def pedido_grande_demais(_erro):
        return jsonify(erro="O pedido é grande demais."), 413

    def inteiro_opcional(nome: str) -> int | None:
        bruto = request.args.get(nome, "").strip()
        if not bruto:
            return None
        try:
            return int(bruto)
        except ValueError:
            raise ErroDeEntrada(f"'{nome}' precisa ser um número inteiro.") from None

    def corpo_json():
        """O JSON do pedido. Exigir "application/json" também protege contra pedidos
        forjados por outros sites: um formulário de outro site não consegue enviar
        esse tipo sem permissão do navegador (e este servidor não dá essa permissão)."""
        if not request.is_json:
            raise TipoNaoSuportado("Envie o pedido como JSON (Content-Type: application/json).")
        dados = request.get_json(silent=True)
        if dados is None:
            raise ErroDeEntrada("O JSON enviado é inválido.")
        return dados

    def exigir_senha_de_administrador(dados) -> None:
        """Confere a senha de administrador que veio no pedido (campo `senha_admin` do JSON) ANTES de qualquer coisa.

        Só passa quem acerta. Sem senha definida no servidor a ação fica fechada (403), nunca aberta. O corpo do pedido
        com a senha não vai para log nenhum e a senha nunca é repetida na resposta.
        """
        if not isinstance(dados, dict):
            raise ErroDeEntrada("Formato do pedido inválido.")
        try:
            administrador.conferir_senha(conexao(), dados.get("senha_admin"))
        except administrador.MuitasTentativas as erro:
            minutos = -(-erro.segundos // 60)  # arredonda para cima
            raise SenhaDeAdministradorRecusada(
                f"Muitas senhas erradas seguidas. Tente de novo em {minutos} min.", "travada", 429, erro.segundos
            ) from None
        except administrador.SenhaNaoDefinida:
            raise SenhaDeAdministradorRecusada(
                "A senha de administrador ainda não foi definida no servidor, então esta ação está fechada. "
                "Peça a quem cuida do servidor para definir a senha.",
                "nao_definida",
            ) from None
        except administrador.SenhaIncorreta:
            raise SenhaDeAdministradorRecusada("Senha de administrador incorreta.", "incorreta") from None

    # ------------------------------------------------------------------ rotas

    @app.get("/")
    def raiz():
        return redirect(url_for("pagina_alunos"))

    @app.get("/saude")
    def saude():
        """Para o servidor/proxy conferir se o app está de pé e enxerga o banco."""
        conexao().execute("SELECT 1").fetchone()
        return jsonify(ok=True)

    @app.get("/autorizar")
    def pagina_autorizar():
        """Tela onde se digita o código de uso único para autorizar este computador."""
        if dispositivo_atual() is not None:
            return redirect(url_for("pagina_alunos"))
        return render_template("autorizar.html")

    @app.post("/api/autorizar")
    def api_autorizar():
        """Troca o código por um cookie de computador autorizado. Corpo: {"codigo": "ABCDE-23456"}."""
        dados = corpo_json()
        if not isinstance(dados, dict):
            raise ErroDeEntrada("Formato do pedido inválido.")
        if not acesso.normalizar_codigo(dados.get("codigo")):
            raise ErroDeEntrada("Digite o código de autorização.")
        try:
            autorizacao = acesso.autorizar(conexao(), dados.get("codigo"))
        except acesso.MuitasTentativas as erro:
            minutos = -(-erro.segundos // 60)  # arredonda para cima
            resposta = jsonify(
                erro=f"Muitos códigos errados seguidos. Tente de novo em {minutos} min."
            )
            resposta.status_code = 429
            resposta.headers["Retry-After"] = str(erro.segundos)
            return resposta
        except acesso.CodigoInvalido:
            return jsonify(erro="Código inválido ou vencido."), 400
        resposta = jsonify(ok=True, nome=autorizacao.nome)
        definir_cookie_do_dispositivo(resposta, autorizacao.token)
        return resposta

    # ------------------------------------------------------------------ login do aluno

    def primeiro_nome(nome: str) -> str:
        return (nome.split() or [""])[0].capitalize()

    def espera_recusada(erro: aluno_acesso.MuitasTentativas):
        resposta = jsonify(erro=erro.mensagem)
        resposta.status_code = 429
        resposta.headers["Retry-After"] = str(erro.segundos)
        return resposta

    def cpf_do_pedido(dados) -> str:
        if not isinstance(dados, dict):
            raise ErroDeEntrada("Formato do pedido inválido.")
        try:
            return aluno_acesso.validar_cpf(dados.get("cpf"))
        except provisorios.CpfInvalido as erro:
            raise ErroDeEntrada(str(erro)) from None

    @app.get("/aluno/entrar")
    def pagina_aluno_entrar():
        """Entrar (CPF + senha), primeiro acesso e esqueci a senha. Tela do celular do aluno."""
        if aluno_atual() is not None:
            return redirect(url_for("pagina_aluno_inicio"))
        return render_template("aluno_entrar.html")

    @app.get("/aluno")
    def pagina_aluno_inicio():
        """Primeira tela do aluno logado."""
        aluno = aluno_atual()
        if aluno is None:
            return redirect(url_for("pagina_aluno_entrar"))
        return render_template("aluno_inicio.html", primeiro_nome=primeiro_nome(aluno.nome))

    @app.post("/api/aluno/codigo")
    def api_aluno_pedir_codigo():
        """Manda um código de 6 números ao WhatsApp do aluno. Corpo: {"cpf": "..."}.

        A resposta é a mesma para CPF que é de aluno e CPF que não é: ninguém descobre quem é aluno por aqui.
        """
        cpf = cpf_do_pedido(corpo_json())
        remetente = app.config["WHATSAPP"]
        if not remetente.pronto():
            return jsonify(erro="O envio do código ainda não está liberado. Fale com a recepção da academia."), 503
        try:
            envio = aluno_acesso.pedir_codigo(conexao(), cpf, request.remote_addr)
        except aluno_acesso.MuitasTentativas as erro:
            return espera_recusada(erro)
        except aluno_acesso.LimiteDoDia:
            return jsonify(erro="Não estamos conseguindo enviar códigos agora. Tente mais tarde ou fale com a recepção."), 503
        if envio is not None:
            trabalho = (app.config["CAMINHO_BANCO"], envio, remetente)
            if app.config["WHATSAPP_EM_SEGUNDO_PLANO"]:
                threading.Thread(target=aluno_acesso.executar_envio, args=trabalho, name=f"codigo-{envio.codigo_id}", daemon=True).start()
            else:
                aluno_acesso.executar_envio(*trabalho)
        return jsonify(
            ok=True,
            espera=int(aluno_acesso.INTERVALO_ENTRE_PEDIDOS.total_seconds()),
            validade_minutos=int(aluno_acesso.VALIDADE_DO_CODIGO.total_seconds() // 60),
        )

    @app.post("/api/aluno/primeiro-acesso")
    def api_aluno_definir_senha():
        """Troca o código pela senha nova e já entra. Corpo: {"cpf", "codigo", "senha"}."""
        dados = corpo_json()
        cpf = cpf_do_pedido(dados)
        try:
            entrada = aluno_acesso.definir_senha_com_codigo(
                conexao(), cpf, dados.get("codigo"), dados.get("senha"), request.remote_addr
            )
        except aluno_acesso.SenhaInvalida as erro:
            raise ErroDeEntrada(str(erro)) from None
        except aluno_acesso.MuitasTentativas as erro:
            return espera_recusada(erro)
        except aluno_acesso.CodigoInvalido:
            return jsonify(erro="Código inválido ou vencido. Confira os 6 números ou peça um código novo."), 400
        resposta = jsonify(ok=True, nome=primeiro_nome(entrada.nome))
        definir_cookie_do_aluno(resposta, entrada.token)
        return resposta

    @app.post("/api/aluno/entrar")
    def api_aluno_entrar():
        """Entra com CPF e senha. Corpo: {"cpf", "senha"}."""
        dados = corpo_json()
        cpf = cpf_do_pedido(dados)
        try:
            entrada = aluno_acesso.entrar(conexao(), cpf, dados.get("senha"), request.remote_addr)
        except aluno_acesso.MuitasTentativas as erro:
            return espera_recusada(erro)
        except aluno_acesso.LoginInvalido:
            return jsonify(erro="CPF ou senha incorretos."), 401
        resposta = jsonify(ok=True, nome=primeiro_nome(entrada.nome))
        definir_cookie_do_aluno(resposta, entrada.token)
        return resposta

    @app.post("/api/aluno/sair")
    def api_aluno_sair():
        """Sai deste celular (a sessão deixa de valer)."""
        aluno_acesso.sair(conexao(), request.cookies.get(aluno_acesso.NOME_DO_COOKIE))
        resposta = jsonify(ok=True)
        resposta.delete_cookie(aluno_acesso.NOME_DO_COOKIE, path="/")
        return resposta

    @app.get("/api/aluno/treino")
    def api_aluno_treino():
        """O treino ativo do aluno logado: 200 {"treino": {...}} ou {"treino": null} (sem treino ativo); 401 sem login.

        O aluno vem do cookie, nunca de um número na URL: não há como pedir o treino de outra pessoa.
        """
        aluno = aluno_atual()
        if aluno is None:
            return jsonify(erro="Você precisa entrar de novo."), 401
        return jsonify(treino=aluno_treino.treino_do_aluno(conexao(), aluno.id))

    def ficha_do_pedido_do_aluno() -> tuple:
        """(aluno, número da ficha) do pedido de marcar/desfazer, ou a resposta 401. O número vem no corpo: {"ficha": 1}."""
        aluno = aluno_atual()
        if aluno is None:
            return None, None
        dados = corpo_json()
        return aluno, dados.get("ficha") if isinstance(dados, dict) else None

    @app.post("/api/aluno/treino/feito")
    def api_aluno_treino_feito():
        """"Treino concluído". Corpo {"ficha": 1} (1 = A, 2 = B...). Conta no máximo uma vez por ficha por dia.

        200 {"ok", "ficha", "ja_marcada", "feitas"}; 400 ficha inválida; 401 sem login; 404 a ficha não existe;
        409 sem treino ativo; 415 não é JSON.
        """
        aluno, ficha = ficha_do_pedido_do_aluno()
        if aluno is None:
            return jsonify(erro="Você precisa entrar de novo."), 401
        try:
            resultado = aluno_treino.marcar_ficha_feita(conexao(), aluno.id, ficha)
        except aluno_treino.MarcacaoInvalida as erro:
            return jsonify(erro=str(erro)), erro.status
        return jsonify(ok=True, **resultado)

    @app.post("/api/aluno/treino/desfazer")
    def api_aluno_treino_desfazer():
        """Desfaz a marcação de HOJE de uma ficha. Corpo {"ficha": 1}. 200 {"ok", "ficha", "feitas"}; mesmos erros do /feito."""
        aluno, ficha = ficha_do_pedido_do_aluno()
        if aluno is None:
            return jsonify(erro="Você precisa entrar de novo."), 401
        try:
            resultado = aluno_treino.desfazer_marcacao_de_hoje(conexao(), aluno.id, ficha)
        except aluno_treino.MarcacaoInvalida as erro:
            return jsonify(erro=str(erro)), erro.status
        return jsonify(ok=True, **resultado)

    @app.post("/api/aluno/comentario")
    def api_aluno_comentario():
        """O aluno comenta o treino inteiro ou um exercício. Corpo: {"treino": "nome que o celular mostra", "texto": "...",
        e, se for de um exercício, "ficha": 1, "item": 2, "exercicio": "nome que o celular mostra"}.

        200 {"ok", "repetido"}; 400 texto ou exercício inválido; 401 sem login; 409 sem treino ativo ou o treino mudou
        (atualizar a página); 415 não é JSON; 429 muitos comentários hoje. O aluno vem do cookie, nunca do corpo.
        """
        aluno = aluno_atual()
        if aluno is None:
            return jsonify(erro="Você precisa entrar de novo."), 401
        dados = corpo_json()
        if not isinstance(dados, dict):
            raise ErroDeEntrada("Formato do pedido inválido.")
        try:
            resultado = comentarios.enviar_comentario(
                conexao(),
                aluno.id,
                dados.get("treino"),
                dados.get("texto"),
                ficha=dados.get("ficha"),
                item=dados.get("item"),
                exercicio=dados.get("exercicio"),
            )
        except comentarios.ComentarioInvalido as erro:
            return jsonify(erro=str(erro)), erro.status
        return jsonify(ok=True, **resultado)

    @app.get("/api/aluno/comentarios")
    def api_aluno_comentarios():
        """Os comentários do PRÓPRIO aluno com as respostas do professor (as não vistas primeiro).

        200 {"total", "respostas_novas", "comentarios": [...]}; 401 sem login. O aluno vem do cookie, nunca da URL.
        """
        aluno = aluno_atual()
        if aluno is None:
            return jsonify(erro="Você precisa entrar de novo."), 401
        return jsonify(comentarios.listar_do_aluno(conexao(), aluno.id))

    @app.post("/api/aluno/comentarios/vistos")
    def api_aluno_comentarios_vistos():
        """O aluno abriu as respostas. Corpo: {"ids": [3, 5]} (as que a tela mostrava; só valem as dele).

        200 {"ok", "marcados", "respostas_novas"}; 400 lista inválida; 401; 415.
        """
        aluno = aluno_atual()
        if aluno is None:
            return jsonify(erro="Você precisa entrar de novo."), 401
        dados = corpo_json()
        try:
            resultado = comentarios.marcar_respostas_vistas(
                conexao(), aluno.id, dados.get("ids") if isinstance(dados, dict) else None
            )
        except comentarios.ComentarioInvalido as erro:
            return jsonify(erro=str(erro)), erro.status
        return jsonify(ok=True, **resultado)

    @app.get("/api/grupos")
    def api_grupos():
        return jsonify(exercicios.listar_grupos(conexao()))

    @app.get("/api/exercicios")
    def api_exercicios():
        resultado = exercicios.buscar_exercicios(
            conexao(),
            grupo_id=inteiro_opcional("grupo"),
            texto=request.args.get("q", ""),
            limite=inteiro_opcional("limite") or exercicios.LIMITE_PADRAO,
        )
        return jsonify(resultado)

    @app.get("/exercicios")
    def pagina_exercicios():
        conn = conexao()
        return render_template(
            "exercicios.html",
            grupos=exercicios.listar_grupos(conn),
            total_exercicios=exercicios.contar_exercicios(conn),
        )

    @app.get("/alunos/<int:aluno_id>/montar")
    def pagina_montar(aluno_id: int):
        """Tela do professor para montar o treino de um aluno."""
        conn = conexao()
        aluno = conn.execute("SELECT id, nome FROM aluno WHERE id = ?", (aluno_id,)).fetchone()
        if aluno is None:
            abort(404)
        return render_template(
            "montar.html",
            aluno=aluno,
            treino_ativo=ciclo.treino_ativo(conn, aluno_id),  # o aviso "será concluído ao salvar"
            hoje=datas.hoje(),
            grupos=exercicios.listar_grupos(conn),
            total_exercicios=exercicios.contar_exercicios(conn),
            filas=filas.listar_filas(conn),  # o seletor "Fila" do "Salvar como treino padrão"
            ia=ia_treino.situacao_para_tela(conn, aluno_id, app.config["CAMINHO_BANCO"]),  # o cartão "Treino sob medida"
            ia_objetivos=ia_treino.ROTULOS_DOS_OBJETIVOS,
            ia_niveis=ia_treino.ROTULOS_DOS_NIVEIS,
            ia_dias=range(ia_treino.MINIMO_DE_DIAS, ia_treino.MAXIMO_DE_DIAS + 1),
            ia_minutos=list(ia_treino.EXERCICIOS_POR_FICHA),
            ia_limite_das_observacoes=ia_treino.LIMITE_DAS_OBSERVACOES,
        )

    @app.get("/alunos")
    def pagina_alunos():
        """Tela de buscar aluno."""
        return render_template("alunos.html", avisos_de_atraso=importacoes.avisos_de_atraso(conexao()))

    @app.get("/api/alunos")
    def api_alunos():
        resultado = alunos.buscar_alunos(
            conexao(),
            texto=request.args.get("q", ""),
            limite=inteiro_opcional("limite") or alunos.LIMITE_PADRAO,
        )
        return jsonify(resultado)

    @app.get("/alunos/atualizar")
    def pagina_atualizar_alunos():
        """Tela onde a recepção escolhe o base_total.zip e atualiza os alunos do app."""
        return render_template("atualizar_alunos.html", atualizacoes=importacoes.resumo_para_a_tela(conexao()))

    @app.post("/api/alunos/importar")
    def api_importar_alunos():
        """Importa os alunos a partir do pacote que o navegador montou (ver importar_alunos.copia_de_pacote).

        200 com o relatório (só contagens); 400 {"erro"} se o pacote não serve (nada é gravado).
        """
        request.max_content_length = TAMANHO_MAXIMO_DA_IMPORTACAO  # só nesta rota, antes de ler o corpo
        pacote = corpo_json()
        try:
            copia = importar_alunos.copia_de_pacote(pacote)
        except importar_alunos.CopiaInvalida as erro:
            return jsonify(erro=str(erro)), 400
        relatorio = importar_alunos.importar(conexao(), copia)
        importacoes.registrar(conexao(), "alunos", relatorio.extraido_em)
        return jsonify(relatorio.como_dicionario())

    @app.post("/api/treinos/importar")
    def api_importar_treinos():
        """Importa o histórico de treinos do Data4U a partir do pacote que o navegador montou
        (ver importar_treinos.copia_de_pacote). Com `"simular": true` no pacote, roda tudo e desfaz.

        200 com o relatório (só contagens); 400 {"erro"} se o pacote não serve (nada é gravado).
        """
        request.max_content_length = TAMANHO_MAXIMO_DA_IMPORTACAO  # só nesta rota, antes de ler o corpo
        pacote = corpo_json()
        try:
            copia = importar_treinos.copia_de_pacote(pacote)
        except importar_alunos.CopiaInvalida as erro:
            return jsonify(erro=str(erro)), 400
        relatorio = importar_treinos.importar(conexao(), copia, simular=pacote.get("simular") is True)
        if not relatorio.simulado:
            importacoes.registrar(conexao(), "treinos", relatorio.extraido_em)
        return jsonify(relatorio.como_dicionario())

    @app.get("/alunos/novo")
    def pagina_novo_aluno():
        """Tela de cadastrar aluno provisório (quem se matriculou hoje e ainda não está no Data4U)."""
        return render_template("novo_aluno.html")

    @app.post("/api/alunos")
    def api_cadastrar_aluno():
        """Cadastra um aluno provisório. Corpo JSON: {"nome", "cpf", "whatsapp" (opcional)}.

        201 {"id"}; 400 {"erros": {campo: mensagem}}; 409 {"erro", "existentes": [...]} se o CPF
        já está no app.
        """
        dados = corpo_json()
        try:
            aluno_id = provisorios.cadastrar_provisorio(conexao(), dados)
        except provisorios.CadastroInvalido as erro:
            return jsonify(erros=erro.erros), 400
        except provisorios.CpfJaCadastrado as erro:
            return (
                jsonify(
                    erro="Já existe um aluno com este CPF.",
                    existentes=[
                        {
                            "id": e.id,
                            "nome": e.nome,
                            "provisorio": e.provisorio,
                            "situacao_nome": e.situacao_nome,
                        }
                        for e in erro.existentes
                    ],
                ),
                409,
            )
        return jsonify(id=aluno_id), 201

    @app.get("/comentarios")
    def pagina_comentarios():
        """O que os alunos escreveram sobre o treino: os novos primeiro; com ?todos=1 também os já lidos."""
        todos = request.args.get("todos") == "1"
        return render_template("comentarios.html", lista=comentarios.listar(conexao(), so_nao_lidos=not todos), todos=todos)

    @app.post("/api/comentarios/<int(max=9223372036854775807):comentario_id>/lido")
    def api_comentario_lido(comentario_id: int):
        """O professor leu o comentário. 200 {"ok", "nao_lidos"}; 404 se não existe. Repetir não faz mal."""
        conn = conexao()
        if not comentarios.marcar_lido(conn, comentario_id):
            return jsonify(erro="Comentário não encontrado."), 404
        return jsonify(ok=True, nao_lidos=comentarios.contar_nao_lidos(conn))

    @app.post("/api/comentarios/<int(max=9223372036854775807):comentario_id>/responder")
    def api_comentario_responder(comentario_id: int):
        """O professor responde o comentário. Corpo: {"professor": "nome digitado", "resposta": "texto"}.

        200 {"ok", "respondido_por", "respondido_quando", "nao_lidos"} (responder também marca como lido); 400 nome ou texto
        inválido; 404 não existe; 409 já foi respondido (uma resposta por comentário); 415.
        """
        dados = corpo_json()
        if not isinstance(dados, dict):
            raise ErroDeEntrada("Formato do pedido inválido.")
        conn = conexao()
        try:
            resultado = comentarios.responder(conn, comentario_id, dados.get("professor"), dados.get("resposta"))
        except comentarios.ComentarioInvalido as erro:
            return jsonify(erro=str(erro)), erro.status
        return jsonify(ok=True, nao_lidos=comentarios.contar_nao_lidos(conn), **resultado)

    @app.post("/api/alunos/<int(max=9223372036854775807):aluno_id>/comentarios/lidos")
    def api_comentarios_do_aluno_lidos(aluno_id: int):
        """O professor leu os comentários deste aluno que estavam na tela. Corpo: {"ids": [3, 5]} (os que ele viu).

        200 {"ok", "marcados", "nao_lidos"}; 400 lista inválida; 404 se o aluno não existe. Só marca esses ids, nunca "tudo
        o que está sem ler": o que chegou depois de a ficha abrir não pode ser dado como lido sem ninguém ter lido.
        """
        conn = conexao()
        dados = corpo_json()
        if conn.execute("SELECT 1 FROM aluno WHERE id = ?", (aluno_id,)).fetchone() is None:
            return jsonify(erro="Aluno não encontrado."), 404
        try:
            marcados = comentarios.marcar_lidos_do_aluno(conn, aluno_id, dados.get("ids") if isinstance(dados, dict) else None)
        except comentarios.ComentarioInvalido as erro:
            return jsonify(erro=str(erro)), erro.status
        return jsonify(ok=True, marcados=marcados, nao_lidos=comentarios.contar_nao_lidos(conn))

    @app.get("/alunos/<int:aluno_id>")
    def pagina_ficha(aluno_id: int):
        """Ficha do aluno: treinos salvos, WhatsApp e dados do cadastro."""
        ficha = alunos.obter_ficha(conexao(), aluno_id)
        if ficha is None:
            abort(404)
        return render_template(
            "ficha.html",
            ficha=ficha,
            hoje=datas.hoje(),
            comentarios_do_aluno=comentarios.listar(conexao(), so_nao_lidos=False, aluno_id=aluno_id, limite=30),
        )

    @app.get("/treinos/<int:treino_id>/imprimir")
    def pagina_imprimir_treino(treino_id: int):
        """O cupom do treino para a impressora térmica (80 mm), com o botão Imprimir."""
        # ?ficha=2 imprime só a ficha de ordem 2 (B); ?ficha=todas imprime o treino inteiro; sem nada, a primeira.
        pedida = request.args.get("ficha", "")
        if pedida == "todas":
            ficha = None
        elif pedida == "":
            primeira = conexao().execute(
                "SELECT MIN(ordem) FROM ficha WHERE treino_id = ?", (treino_id,)
            ).fetchone()[0]
            ficha = primeira  # treino sem ficha: None, e a tela mostra um cupom só com o cabeçalho
        elif pedida.isascii() and pedida.isdigit() and len(pedida) <= 4:
            ficha = int(pedida)
        else:
            abort(404)
        try:
            conteudo = cupom.montar_cupom(conexao(), treino_id, app.config["ENDERECO_DO_APP"], ficha)
        except cupom.FichaInexistente:
            abort(404)
        if conteudo is None:
            abort(404)
        return render_template("imprimir.html", cupom=conteudo)

    @app.get("/teste-de-impressao")
    def pagina_teste_de_impressao():
        """Folha de teste da impressora térmica: régua em milímetros, barra preta, pontos, o símbolo em 4 versões e as letras
        em 5 estilos. Sem aluno, sem treino, não grava nada. Serve para separar "a impressora falha" de "o desenho
        chega mal na impressora" (pedido do Thiago em 20/10/2026, cupom saindo com riscos brancos e a letra da esquerda cortada)."""
        return render_template("teste_impressao.html")

    @app.post("/api/alunos/<int:aluno_id>/treinos")
    def api_salvar_treino(aluno_id: int):
        """Grava um treino novo para o aluno. Corpo: JSON (ver treinos.salvar_treino).

        Se o aluno já tinha um treino ativo, ele é concluído na mesma gravação; a resposta traz o nome
        dele em `concluido_anterior` (ou null) para a tela avisar o professor."""
        dados = corpo_json()
        conn = conexao()
        anterior = ciclo.treino_ativo(conn, aluno_id)  # só para o aviso: quem decide é o salvar_treino
        try:
            treino_id = treinos.salvar_treino(conn, aluno_id, dados)
        except treinos.AlunoNaoEncontrado:
            return jsonify(erro="Aluno não encontrado."), 404
        except treinos.TreinoInvalido as erro:
            return jsonify(erros=erro.problemas), erro.status
        return jsonify(id=treino_id, concluido_anterior=anterior["nome"] if anterior else None), 201

    @app.post("/api/treinos/<int:treino_id>/concluir")
    def api_concluir_treino(treino_id: int):
        """Botão "Concluído": o treino vira inativo e entra no histórico do aluno."""
        corpo_json()  # o corpo é vazio ({}), mas o pedido precisa ser JSON como os outros
        try:
            ciclo.concluir_treino(conexao(), treino_id)
        except ciclo.TreinoNaoEncontrado:
            return jsonify(erro="Treino não encontrado."), 404
        except ciclo.CicloInvalido as erro:
            return jsonify(erro=erro.mensagem), 409
        return jsonify(ok=True)

    @app.post("/api/treinos/<int:treino_id>/reativar")
    def api_reativar_treino(treino_id: int):
        """Desfaz o "Concluído": o treino volta a ser o ativo (só se o aluno não tem outro ativo)."""
        corpo_json()
        try:
            ciclo.reativar_treino(conexao(), treino_id)
        except ciclo.TreinoNaoEncontrado:
            return jsonify(erro="Treino não encontrado."), 404
        except ciclo.CicloInvalido as erro:
            return jsonify(erro=erro.mensagem), 409
        return jsonify(ok=True)

    # ------------------------------------------------- impressão na recepção conta como "treino feito"

    def ficha_do_pedido_de_impressao() -> int:
        """O número da ficha ({"ficha": 2}) do pedido de marcar/desfazer a impressão. Só inteiro de 1 a 9999."""
        dados = corpo_json()
        ficha = dados.get("ficha") if isinstance(dados, dict) else None
        if isinstance(ficha, bool) or not isinstance(ficha, int) or not 1 <= ficha <= 9999:
            raise ErroDeEntrada("Escolha a ficha de novo.")
        return ficha

    @app.post("/api/treinos/<int:treino_id>/impressao")
    def api_marcar_impressao(treino_id: int):
        """A recepção imprimiu UMA ficha: conta como treino feito hoje daquela ficha (uma vez por ficha por dia).

        Corpo {"ficha": 2}. 200 {"ok", "ficha", "ja_marcada", "feitas"}; 404 treino não existe; 409 treino concluído ou
        sem essa ficha. Quem não usa o app pede um papel novo a cada treino (Thiago, 20/10/2026).
        """
        ficha = ficha_do_pedido_de_impressao()
        try:
            resultado = ciclo.marcar_impressao(conexao(), treino_id, ficha)
        except ciclo.TreinoNaoEncontrado:
            return jsonify(erro="Treino não encontrado."), 404
        except ciclo.CicloInvalido as erro:
            return jsonify(erro=erro.mensagem), 409
        return jsonify(ok=True, **resultado)

    @app.post("/api/treinos/<int:treino_id>/impressao/desfazer")
    def api_desfazer_impressao(treino_id: int):
        """Desfaz a marcação de HOJE da impressão (a recepção imprimiu a ficha errada). Corpo {"ficha": 2}."""
        ficha = ficha_do_pedido_de_impressao()
        try:
            resultado = ciclo.desfazer_impressao(conexao(), treino_id, ficha)
        except ciclo.TreinoNaoEncontrado:
            return jsonify(erro="Treino não encontrado."), 404
        except ciclo.CicloInvalido as erro:
            return jsonify(erro=erro.mensagem), 409
        return jsonify(ok=True, **resultado)

    # ------------------------------------------------- treinos padrão e cópia de treinos ("Importar treino")

    @app.get("/api/modelos")
    def api_listar_modelos():
        """Os treinos padrão, em ordem alfabética, com resumo."""
        return jsonify(modelos=modelos.listar_modelos(conexao()))

    @app.get("/api/modelos/<int:modelo_id>")
    def api_obter_modelo(modelo_id: int):
        """Um treino padrão no formato da tela de montar (ver modelos.para_montar). Não grava nada."""
        treino = modelos.modelo_para_montar(conexao(), modelo_id)
        if treino is None:
            return jsonify(erro="Treino padrão não encontrado."), 404
        return jsonify(treino)

    @app.post("/api/modelos")
    def api_criar_modelo():
        """Guarda o treino que está na tela de montar como treino padrão (não grava nada para o aluno).

        Corpo: {"senha_admin", "nome", "montado_por", "sessoes_por_ficha", "fichas", "fila_id" e "numero" (opcionais, juntos)}.
        Exige a senha de administrador (403 se errada ou ainda não definida, 429 se travada).
        201 {"id"}; 400 {"erros"}; 409 {"erros"} se já existe um padrão com esse nome ou esse número na fila.
        """
        dados = corpo_json()
        exigir_senha_de_administrador(dados)
        try:
            modelo_id = modelos.criar_modelo(conexao(), dados)
        except treinos.TreinoInvalido as erro:
            return jsonify(erros=erro.problemas), erro.status
        return jsonify(id=modelo_id), 201

    @app.post("/api/modelos/<int:modelo_id>/excluir")
    def api_excluir_modelo(modelo_id: int):
        """Apaga um treino padrão. Os treinos já copiados para alunos não mudam.

        Corpo: {"senha_admin"}. Exige a senha de administrador (403 se errada ou ainda não definida, 429 se travada).
        """
        exigir_senha_de_administrador(corpo_json())
        try:
            modelos.excluir_modelo(conexao(), modelo_id)
        except modelos.ModeloNaoEncontrado:
            return jsonify(erro="Treino padrão não encontrado."), 404
        return jsonify(ok=True)

    @app.post("/api/treinos/<int:treino_id>/modelo")
    def api_treino_como_modelo(treino_id: int):
        """Botão "Salvar como treino padrão" da ficha do aluno. Corpo: {"senha_admin", "nome": "nome do treino padrão",
        "fila_id" e "numero" (opcionais, os dois juntos: o lugar do treino numa fila numerada)}.
        Exige a senha de administrador (403 se errada ou ainda não definida, 429 se travada)."""
        dados = corpo_json()
        exigir_senha_de_administrador(dados)
        try:
            modelo_id = modelos.criar_modelo_do_treino(
                conexao(), treino_id, dados.get("nome"), fila_id=dados.get("fila_id"), numero=dados.get("numero")
            )
        except modelos.TreinoNaoEncontrado:
            return jsonify(erro="Treino não encontrado."), 404
        except treinos.TreinoInvalido as erro:
            return jsonify(erros=erro.problemas), erro.status
        return jsonify(id=modelo_id), 201

    @app.get("/api/alunos/<int:aluno_id>/treinos-para-copiar")
    def api_treinos_do_aluno(aluno_id: int):
        """Os treinos do aluno que dá para copiar (o ativo primeiro). Para a aba "Treino de outro aluno"."""
        try:
            return jsonify(treinos=modelos.listar_treinos_do_aluno(conexao(), aluno_id))
        except treinos.AlunoNaoEncontrado:
            return jsonify(erro="Aluno não encontrado."), 404

    @app.get("/api/treinos/<int:treino_id>/para-montar")
    def api_treino_para_montar(treino_id: int):
        """Um treino de aluno no formato da tela de montar (ver modelos.para_montar). Não grava nada."""
        treino = modelos.treino_para_montar(conexao(), treino_id)
        if treino is None:
            return jsonify(erro="Treino não encontrado."), 404
        return jsonify(treino)

    @app.get("/api/treinos/<int:treino_id>/para-editar")
    def api_treino_para_editar(treino_id: int):
        """O treino no formato da tela de montar, com professor, datas, ativo e origem (botão "Editar treino")."""
        treino = modelos.treino_para_editar(conexao(), treino_id)
        if treino is None:
            return jsonify(erro="Treino não encontrado."), 404
        return jsonify(treino)

    @app.post("/api/treinos/<int:treino_id>/editar")
    def api_editar_treino(treino_id: int):
        """Muda no lugar o treino ativo criado no app. Corpo: o mesmo JSON de salvar treino (ver treinos.editar_treino).

        200 {"id"}; 400 {"erros"} (dado inválido); 404; 409 {"erros"} (treino do Data4U, concluído ou nome repetido).
        """
        dados = corpo_json()
        try:
            treinos.editar_treino(conexao(), treino_id, dados)
        except treinos.TreinoNaoEncontrado:
            return jsonify(erro="Treino não encontrado."), 404
        except treinos.TreinoInvalido as erro:
            return jsonify(erros=erro.problemas), erro.status
        return jsonify(id=treino_id)

    # ------------------------------------------------- filas numeradas de treino (ver app/filas.py)

    @app.post("/api/alunos/<int:aluno_id>/fila")
    def api_definir_fila(aluno_id: int):
        """O professor coloca o aluno numa fila (ou muda a fila dele).

        Corpo: {"fila_id", "professor", "liberacao_conferida" (obrigatório nas filas que exigem), "liberacao_em"}.
        200 {"ok": true}; 400 {"erros"}; 404 aluno inexistente.
        """
        dados = corpo_json()
        try:
            filas.definir_fila(conexao(), aluno_id, dados)
        except filas.AlunoNaoEncontrado:
            return jsonify(erro="Aluno não encontrado."), 404
        except filas.FilaInvalida as erro:
            return jsonify(erros=erro.problemas), erro.status
        return jsonify(ok=True)

    @app.post("/api/alunos/<int:aluno_id>/fila/tirar")
    def api_tirar_da_fila(aluno_id: int):
        """O aluno deixa de estar numa fila (o treino dele não muda). Corpo: {}. 200; 404 aluno inexistente."""
        corpo_json()
        try:
            filas.tirar_da_fila(conexao(), aluno_id)
        except filas.AlunoNaoEncontrado:
            return jsonify(erro="Aluno não encontrado."), 404
        return jsonify(ok=True)

    @app.post("/api/alunos/<int:aluno_id>/whatsapp")
    def api_corrigir_whatsapp(aluno_id: int):
        """Corrige o WhatsApp do aluno. Corpo: {"whatsapp": "(27) 98888-7766"}."""
        dados = corpo_json()
        if not isinstance(dados, dict):
            raise ErroDeEntrada("Formato do pedido inválido.")
        try:
            formatado = alunos.salvar_whatsapp(conexao(), aluno_id, dados.get("whatsapp"))
        except alunos.AlunoNaoEncontrado:
            return jsonify(erro="Aluno não encontrado."), 404
        except alunos.WhatsappInvalido as erro:
            return jsonify(erro=str(erro)), 400
        return jsonify(whatsapp=formatado)

    # ------------------------------------------------- treino sob medida (IA) (ver app/ia_treino.py)

    @app.post("/api/alunos/<int:aluno_id>/treino-ia")
    def api_pedir_treino_ia(aluno_id: int):
        """O professor pede um RASCUNHO de treino ao Claude (ou a vez de a IA perguntar). Nada é salvo para o aluno.

        Corpo: {"objetivo", "nivel", "dias", "minutos", "observacoes" (opcional), "perguntar" (opcional, true = a IA pode fazer
        perguntas antes de montar), "rodadas" (opcional: as rodadas de perguntas já respondidas, [{"perguntas": [...],
        "respostas": [...]}], no máximo 2; o servidor não guarda a conversa, o navegador manda tudo de novo a cada chamada)}.
        202 {"pedido_id"} (a resposta demora: a tela pergunta de tempos em tempos em GET .../treino-ia/<pedido_id>);
        400 {"erros"}; 404 aluno inexistente; 409 {"erro", "bloqueio"} (aluno de fila com liberação, ou gravidez nas
        observações ou nas respostas); 429 {"erro"} (pedidos demais; cada chamada à IA conta); 503 {"erro", "configurada": false}
        (o servidor ainda não tem a chave).
        """
        dados = corpo_json()
        conn = conexao()
        try:
            pedido = ia_treino.conferir_pedido(conn, aluno_id, dados)
            pedido_id = ia_treino.criar_pedido(
                app.config["CAMINHO_BANCO"],
                aluno_id,
                pedido,
                chamar=app.config["IA_CHAMADA"],
                em_segundo_plano=app.config["IA_EM_SEGUNDO_PLANO"],
            )
        except ia_treino.AlunoNaoEncontrado:
            return jsonify(erro="Aluno não encontrado."), 404
        except ia_treino.PedidoInvalido as erro:
            return jsonify(erros=erro.problemas), 400
        except ia_treino.PedidoBloqueado as erro:
            return jsonify(erro=erro.mensagem, bloqueio=erro.motivo), 409
        except ia_treino.ChaveNaoConfigurada:
            return jsonify(erro="O treino sob medida ainda não está ligado neste servidor (falta a chave da IA). Avise o Thiago.", configurada=False), 503
        except ia_treino.LimiteDaIA as erro:
            return jsonify(erro=erro.mensagem), 429
        return jsonify(pedido_id=pedido_id), 202

    @app.get("/api/alunos/<int:aluno_id>/treino-ia/<int:pedido_id>")
    def api_ver_treino_ia(aluno_id: int, pedido_id: int):
        """Como está o pedido. {"situacao": "andando"} | {"situacao": "pronto", "treino", "resumo", "alertas", "removidos"}
        (o rascunho) | {"situacao": "pronto", "perguntas", "rodada", "maximo_de_rodadas"} (a IA quer saber mais antes de
        montar) | {"situacao": "erro", "erro"}. 404 se o pedido não existe ou é de outro aluno."""
        try:
            return jsonify(ia_treino.consultar_pedido(conexao(), aluno_id, pedido_id))
        except ia_treino.PedidoNaoEncontrado:
            return jsonify(erro="Pedido não encontrado."), 404

    return app
