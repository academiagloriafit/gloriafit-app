"""Servidor web do app Glória Fit (Flask).

Rodar em desenvolvimento (só na sua máquina):
    GLORIAFIT_DB=app.db python -m flask --app "app.web:criar_app" run --debug
NUNCA use --debug num servidor aberto à internet: ele libera um console que
executa código de quem acessar.
"""

import os
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, abort, g, jsonify, redirect, render_template, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from app import acesso, alunos, cupom, db, exercicios, importar_alunos, importar_treinos, provisorios, treinos


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
ENDPOINTS_PUBLICOS = frozenset({"static", "saude", "pagina_autorizar", "api_autorizar"})

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

    @app.errorhandler(ErroDeEntrada)
    def entrada_invalida(erro):
        return jsonify(erro=str(erro)), erro.status

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
            grupos=exercicios.listar_grupos(conn),
            total_exercicios=exercicios.contar_exercicios(conn),
        )

    @app.get("/alunos")
    def pagina_alunos():
        """Tela de buscar aluno."""
        return render_template("alunos.html")

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
        return render_template("atualizar_alunos.html")

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

    @app.get("/alunos/<int:aluno_id>")
    def pagina_ficha(aluno_id: int):
        """Ficha do aluno: treinos salvos, WhatsApp e dados do cadastro."""
        ficha = alunos.obter_ficha(conexao(), aluno_id)
        if ficha is None:
            abort(404)
        return render_template("ficha.html", ficha=ficha)

    @app.get("/treinos/<int:treino_id>/imprimir")
    def pagina_imprimir_treino(treino_id: int):
        """O cupom do treino para a impressora térmica (80 mm), com o botão Imprimir."""
        conteudo = cupom.montar_cupom(conexao(), treino_id, app.config["ENDERECO_DO_APP"])
        if conteudo is None:
            abort(404)
        return render_template("imprimir.html", cupom=conteudo)

    @app.post("/api/alunos/<int:aluno_id>/treinos")
    def api_salvar_treino(aluno_id: int):
        """Grava um treino novo para o aluno. Corpo: JSON (ver treinos.salvar_treino)."""
        dados = corpo_json()
        try:
            treino_id = treinos.salvar_treino(conexao(), aluno_id, dados)
        except treinos.AlunoNaoEncontrado:
            return jsonify(erro="Aluno não encontrado."), 404
        except treinos.TreinoInvalido as erro:
            return jsonify(erros=erro.problemas), erro.status
        return jsonify(id=treino_id), 201

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

    return app
