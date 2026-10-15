"""Testes do login do aluno no servidor web (rotas /aluno e /api/aluno/*)."""

import re
from datetime import datetime, timedelta, timezone

import pytest

from app import acesso, aluno_acesso
from app.db import conectar, criar_tabelas
from app.web import ENDPOINTS_PUBLICOS, criar_app

CPF_ANA = "11144477735"
CPF_FORMATADO = "111.444.777-35"
SENHA = "uma senha boa 77"
NOME_SECRETO_DO_PROFESSOR = "ALUNO SIGILOSO DE TESTE"


class RemetenteFalso:
    """No lugar da Meta: guarda o que seria enviado e deixa o teste dizer se está configurado ou se falha."""

    def __init__(self):
        self.configurado = True
        self.erro = None
        self.enviados = []

    def pronto(self):
        return self.configurado

    def enviar(self, whatsapp, codigo):
        if self.erro is not None:
            raise self.erro
        self.enviados.append((whatsapp, codigo))
        return "wamid.TESTE"


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "aluno_web.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.executemany(
        "INSERT INTO aluno (id, nome, cpf, whatsapp, situacao) VALUES (?, ?, ?, ?, ?)",
        [
            (1, "ANA SOUZA", CPF_ANA, "27988887766", "A"),
            (2, NOME_SECRETO_DO_PROFESSOR, "52998224725", "27977776655", "A"),
            (3, "CLO DIAS", "39053344705", "27966665544", "D"),
        ],
    )
    conn.execute(
        "INSERT INTO aluno (id, nome, cpf, whatsapp, situacao, provisorio) VALUES (4, 'EVA NOVA', '12345678909', '27955554433', NULL, 1)"
    )
    conn.commit()
    conn.close()
    return caminho


@pytest.fixture
def remetente():
    return RemetenteFalso()


@pytest.fixture
def app(caminho, remetente):
    app = criar_app(caminho)
    app.config["WHATSAPP"] = remetente
    app.config["WHATSAPP_EM_SEGUNDO_PLANO"] = False  # o envio roda na hora: o teste vê o resultado
    return app


@pytest.fixture
def cliente(app):
    """O celular de um aluno: navegador qualquer, sem nenhuma autorização de computador."""
    return app.test_client()


def _banco(caminho):
    return conectar(caminho)


def _sql(caminho, comando, parametros=()):
    conn = _banco(caminho)
    try:
        with conn:
            return conn.execute(comando, parametros).fetchall()
    finally:
        conn.close()


def _pedir_codigo(cliente, cpf=CPF_FORMATADO):
    return cliente.post("/api/aluno/codigo", json={"cpf": cpf})


def _liberar_novo_pedido(caminho):
    """Faz de conta que passou o minuto de espera entre pedidos do mesmo CPF."""
    _sql(caminho, "UPDATE aluno_evento SET em = datetime(em, '-2 minutes')")


def _criar_acesso(cliente, remetente, caminho, cpf=CPF_FORMATADO, senha=SENHA):
    _liberar_novo_pedido(caminho)
    assert _pedir_codigo(cliente, cpf).status_code == 200
    codigo = remetente.enviados[-1][1]
    return cliente.post("/api/aluno/primeiro-acesso", json={"cpf": cpf, "codigo": codigo, "senha": senha})


def _cookie(cliente, nome=aluno_acesso.NOME_DO_COOKIE):
    cookie = cliente.get_cookie(nome)
    return cookie.value if cookie else None


# ------------------------------------------------------------------ as páginas


def test_a_tela_de_entrar_abre_sem_autorizacao_de_computador(cliente):
    resposta = cliente.get("/aluno/entrar")

    assert resposta.status_code == 200
    html = resposta.get_data(as_text=True)
    for pedaco in ("form-entrar", "form-cpf", "form-codigo", "entrar-cpf", "codigo-codigo", "aluno_entrar.js"):
        assert pedaco in html
    assert "noindex" in html  # a página do aluno não precisa aparecer em buscadores
    assert "Cache-Control" in resposta.headers and "no-store" in resposta.headers["Cache-Control"]


def test_a_tela_do_aluno_nao_mostra_o_menu_do_professor(cliente):
    html = cliente.get("/aluno/entrar").get_data(as_text=True)

    assert "Atualizar alunos" not in html and "/alunos" not in html


def test_aluno_sem_login_que_abre_a_tela_inicial_vai_para_a_de_entrar(cliente):
    resposta = cliente.get("/aluno")

    assert resposta.status_code == 302 and resposta.headers["Location"].endswith("/aluno/entrar")


def test_os_arquivos_das_telas_do_aluno_abrem_sem_autorizacao(cliente):
    for arquivo in ("aluno_entrar.js", "aluno_inicio.js", "aluno_modelo.js", "estilo.css"):
        assert cliente.get(f"/static/{arquivo}").status_code == 200


def test_a_tela_de_autorizar_computador_tem_um_link_para_o_aluno(cliente):
    html = cliente.get("/autorizar").get_data(as_text=True)

    assert 'href="/aluno/entrar"' in html


# ------------------------------------------------------------------ pedir o código


def test_pedir_codigo_manda_o_codigo_ao_whatsapp_do_aluno(cliente, remetente, caminho):
    resposta = _pedir_codigo(cliente)

    assert resposta.status_code == 200
    assert resposta.get_json() == {"ok": True, "espera": 60, "validade_minutos": 10}
    assert len(remetente.enviados) == 1
    whatsapp, codigo = remetente.enviados[0]
    assert whatsapp == "27988887766" and re.fullmatch(r"[0-9]{6}", codigo)
    assert _sql(caminho, "SELECT envio FROM aluno_codigo")[0][0] == "enviado"


def test_a_resposta_nunca_traz_o_codigo_nem_o_numero(cliente):
    corpo = _pedir_codigo(cliente).get_data(as_text=True)

    assert "27988887766" not in corpo and "9888" not in corpo
    assert not re.search(r"[0-9]{6}", corpo)


def test_a_resposta_e_igual_para_cpf_de_aluno_e_cpf_que_nao_existe(app, remetente):
    um = app.test_client()
    outro = app.test_client()

    de_aluno = _pedir_codigo(um, CPF_FORMATADO)
    de_ninguem = _pedir_codigo(outro, "98765432100")
    desistente = _pedir_codigo(app.test_client(), "39053344705")
    provisoria = _pedir_codigo(app.test_client(), "12345678909")

    assert (de_aluno.status_code, de_aluno.get_json()) == (de_ninguem.status_code, de_ninguem.get_json())
    assert (desistente.status_code, desistente.get_json()) == (de_ninguem.status_code, de_ninguem.get_json())
    assert (provisoria.status_code, provisoria.get_json()) == (de_ninguem.status_code, de_ninguem.get_json())
    # A Ana (ativa) e a Clo (desistente) recebem; a Eva (provisória) e o CPF que não existe, não.
    assert sorted(telefone for telefone, _ in remetente.enviados) == ["27966665544", "27988887766"]


def test_envio_que_falha_continua_dando_a_mesma_resposta_e_fica_anotado(cliente, remetente, caminho):
    remetente.erro = RuntimeError("a Meta caiu")

    resposta = _pedir_codigo(cliente)

    assert resposta.status_code == 200 and resposta.get_json()["ok"] is True
    linha = _sql(caminho, "SELECT envio, envio_erro FROM aluno_codigo")[0]
    assert tuple(linha) == ("falhou", "a Meta caiu")


def test_o_envio_roda_em_segundo_plano_quando_nao_e_teste(app, caminho, remetente):
    app.config["WHATSAPP_EM_SEGUNDO_PLANO"] = True
    import threading

    antes = {fio.name for fio in threading.enumerate()}

    resposta = _pedir_codigo(app.test_client())

    assert resposta.status_code == 200
    for fio in threading.enumerate():
        if fio.name.startswith("codigo-") and fio.name not in antes:
            fio.join(timeout=10)
    assert len(remetente.enviados) == 1
    assert _sql(caminho, "SELECT envio FROM aluno_codigo")[0][0] == "enviado"


def test_sem_whatsapp_configurado_o_pedido_e_recusado_sem_criar_codigo(cliente, remetente, caminho):
    remetente.configurado = False

    resposta = _pedir_codigo(cliente)

    assert resposta.status_code == 503
    assert "ainda não está liberado" in resposta.get_json()["erro"]
    assert _sql(caminho, "SELECT COUNT(*) FROM aluno_codigo")[0][0] == 0
    assert _sql(caminho, "SELECT COUNT(*) FROM aluno_evento")[0][0] == 0


@pytest.mark.parametrize("cpf, trecho", [("", "Digite o CPF"), ("123", "11 números"), ("111.444.777-36", "não é válido"), ("abc", "só pode ter")])
def test_cpf_ruim_e_recusado_com_a_explicacao(cliente, remetente, cpf, trecho):
    resposta = _pedir_codigo(cliente, cpf)

    assert resposta.status_code == 400 and trecho in resposta.get_json()["erro"]
    assert remetente.enviados == []


@pytest.mark.parametrize("corpo", [[], "texto", 5, {"cpf": None}, {"cpf": 111}, {"cpf": ["1"]}, {}])
def test_corpo_estranho_e_recusado_sem_erro_do_servidor(cliente, corpo):
    resposta = cliente.post("/api/aluno/codigo", json=corpo)

    assert resposta.status_code == 400


def test_pedido_que_nao_e_json_e_recusado(cliente):
    resposta = cliente.post("/api/aluno/codigo", data=f"cpf={CPF_ANA}", content_type="application/x-www-form-urlencoded")

    assert resposta.status_code == 415


def test_pedido_vindo_de_outro_site_e_recusado(cliente, remetente):
    resposta = cliente.post("/api/aluno/codigo", json={"cpf": CPF_ANA}, headers={"Origin": "https://site-malvado.example"})

    assert resposta.status_code == 403
    assert remetente.enviados == []


def test_segundo_pedido_em_menos_de_um_minuto_recebe_429_com_o_tempo_de_espera(cliente, remetente):
    _pedir_codigo(cliente)

    resposta = _pedir_codigo(cliente)

    assert resposta.status_code == 429
    assert "Espere" in resposta.get_json()["erro"]
    assert 1 <= int(resposta.headers["Retry-After"]) <= 60
    assert len(remetente.enviados) == 1


def test_o_429_do_minuto_tambem_vale_para_cpf_que_nao_existe(cliente):
    _pedir_codigo(cliente, "98765432100")

    assert _pedir_codigo(cliente, "98765432100").status_code == 429


def test_teto_de_codigos_do_dia_responde_503(cliente, monkeypatch):
    monkeypatch.setattr(aluno_acesso, "CODIGOS_POR_DIA", 0)

    resposta = _pedir_codigo(cliente)

    assert resposta.status_code == 503 and "Não estamos conseguindo" in resposta.get_json()["erro"]


# ------------------------------------------------------------------ primeiro acesso


def test_primeiro_acesso_cria_a_senha_deixa_logado_e_manda_o_cookie_certo(cliente, remetente, caminho):
    resposta = _criar_acesso(cliente, remetente, caminho)

    assert resposta.status_code == 200
    assert resposta.get_json() == {"ok": True, "nome": "Ana"}
    cabecalho = next(c for c in resposta.headers.getlist("Set-Cookie") if c.startswith(aluno_acesso.NOME_DO_COOKIE))
    assert "HttpOnly" in cabecalho and "SameSite=Lax" in cabecalho and "Path=/" in cabecalho
    assert f"Max-Age={90 * 24 * 3600}" in cabecalho
    assert "Secure" not in cabecalho  # localhost: o navegador não aceita Secure sem https
    assert _cookie(cliente)


def test_o_cookie_do_aluno_e_secure_fora_do_localhost(app, remetente, caminho):
    cliente = app.test_client()
    base = "https://app.gloriafit.com.br"
    assert cliente.post("/api/aluno/codigo", json={"cpf": CPF_ANA}, base_url=base).status_code == 200

    resposta = cliente.post(
        "/api/aluno/primeiro-acesso", json={"cpf": CPF_ANA, "codigo": remetente.enviados[0][1], "senha": SENHA}, base_url=base
    )

    cabecalho = next(c for c in resposta.headers.getlist("Set-Cookie") if c.startswith(aluno_acesso.NOME_DO_COOKIE))
    assert "Secure" in cabecalho and "HttpOnly" in cabecalho


def test_depois_de_criar_a_senha_a_tela_inicial_cumprimenta_o_aluno(cliente, remetente, caminho):
    _criar_acesso(cliente, remetente, caminho)

    resposta = cliente.get("/aluno")

    assert resposta.status_code == 200
    html = resposta.get_data(as_text=True)
    assert "Olá, Ana!" in html and "aluno_inicio.js" in html
    assert "Cache-Control" in resposta.headers and "no-store" in resposta.headers["Cache-Control"]


def test_aluno_logado_que_abre_a_tela_de_entrar_vai_para_a_inicial(cliente, remetente, caminho):
    _criar_acesso(cliente, remetente, caminho)

    resposta = cliente.get("/aluno/entrar")

    assert resposta.status_code == 302 and resposta.headers["Location"].endswith("/aluno")


def test_o_nome_na_tela_nao_vira_html(cliente, remetente, caminho):
    _sql(caminho, "UPDATE aluno SET nome = ? WHERE id = 1", ("<script>alert(1)</script> SOUZA",))
    _criar_acesso(cliente, remetente, caminho)

    html = cliente.get("/aluno").get_data(as_text=True)

    assert "<script>alert" not in html and "&lt;script&gt;" in html


def test_codigo_errado_e_recusado_com_a_explicacao(cliente, remetente, caminho):
    _pedir_codigo(cliente)
    errado = "000000" if remetente.enviados[0][1] != "000000" else "111111"

    resposta = cliente.post("/api/aluno/primeiro-acesso", json={"cpf": CPF_ANA, "codigo": errado, "senha": SENHA})

    assert resposta.status_code == 400 and "Código inválido ou vencido" in resposta.get_json()["erro"]
    assert _cookie(cliente) is None
    assert _sql(caminho, "SELECT COUNT(*) FROM aluno_senha")[0][0] == 0


def test_senha_fraca_e_recusada_e_o_codigo_continua_valendo(cliente, remetente, caminho):
    _pedir_codigo(cliente)
    codigo = remetente.enviados[0][1]

    fraca = cliente.post("/api/aluno/primeiro-acesso", json={"cpf": CPF_ANA, "codigo": codigo, "senha": "12345678"})
    boa = cliente.post("/api/aluno/primeiro-acesso", json={"cpf": CPF_ANA, "codigo": codigo, "senha": SENHA})

    assert fraca.status_code == 400 and "fácil de adivinhar" in fraca.get_json()["erro"]
    assert boa.status_code == 200


def test_cinco_codigos_errados_seguidos_dao_429_mesmo_com_o_codigo_certo(cliente, remetente):
    _pedir_codigo(cliente)
    codigo = remetente.enviados[0][1]
    errado = "000000" if codigo != "000000" else "111111"
    for _ in range(5):
        assert cliente.post("/api/aluno/primeiro-acesso", json={"cpf": CPF_ANA, "codigo": errado, "senha": SENHA}).status_code == 400

    resposta = cliente.post("/api/aluno/primeiro-acesso", json={"cpf": CPF_ANA, "codigo": codigo, "senha": SENHA})

    assert resposta.status_code == 429 and int(resposta.headers["Retry-After"]) > 0
    assert "Tente de novo em" in resposta.get_json()["erro"]


def test_primeiro_acesso_de_cpf_que_nao_existe_da_o_mesmo_erro_do_codigo_errado(cliente):
    resposta = cliente.post("/api/aluno/primeiro-acesso", json={"cpf": "98765432100", "codigo": "123456", "senha": SENHA})

    assert resposta.status_code == 400 and "Código inválido ou vencido" in resposta.get_json()["erro"]


# ------------------------------------------------------------------ entrar, sair


def test_entrar_com_cpf_e_senha(app, remetente, caminho):
    _criar_acesso(app.test_client(), remetente, caminho)
    outro_celular = app.test_client()

    resposta = outro_celular.post("/api/aluno/entrar", json={"cpf": CPF_FORMATADO, "senha": SENHA})

    assert resposta.status_code == 200 and resposta.get_json() == {"ok": True, "nome": "Ana"}
    assert outro_celular.get("/aluno").status_code == 200


def test_senha_errada_e_cpf_inexistente_dao_exatamente_a_mesma_resposta(app, remetente, caminho):
    _criar_acesso(app.test_client(), remetente, caminho)
    cliente = app.test_client()

    errada = cliente.post("/api/aluno/entrar", json={"cpf": CPF_ANA, "senha": "senha errada 99"})
    inexistente = cliente.post("/api/aluno/entrar", json={"cpf": "98765432100", "senha": "senha errada 99"})
    provisoria = cliente.post("/api/aluno/entrar", json={"cpf": "12345678909", "senha": "senha errada 99"})

    for resposta in (errada, inexistente, provisoria):
        assert resposta.status_code == 401
        assert resposta.get_json() == {"erro": "CPF ou senha incorretos."}
        assert aluno_acesso.NOME_DO_COOKIE not in "".join(resposta.headers.getlist("Set-Cookie"))


def test_cinco_senhas_erradas_dao_429(app, remetente, caminho):
    _criar_acesso(app.test_client(), remetente, caminho)
    cliente = app.test_client()
    for _ in range(5):
        assert cliente.post("/api/aluno/entrar", json={"cpf": CPF_ANA, "senha": "senha errada 99"}).status_code == 401

    resposta = cliente.post("/api/aluno/entrar", json={"cpf": CPF_ANA, "senha": SENHA})

    assert resposta.status_code == 429 and "Retry-After" in resposta.headers


@pytest.mark.parametrize("corpo", [{"cpf": CPF_ANA}, {"cpf": CPF_ANA, "senha": None}, {"cpf": CPF_ANA, "senha": ["a"]}, {"cpf": CPF_ANA, "senha": 12345678}])
def test_entrar_com_senha_ausente_ou_estranha_nao_quebra(cliente, corpo):
    assert cliente.post("/api/aluno/entrar", json=corpo).status_code == 401


def test_sair_encerra_so_aquele_celular_e_apaga_o_cookie(app, remetente, caminho):
    celular_a = app.test_client()
    _criar_acesso(celular_a, remetente, caminho)
    celular_b = app.test_client()
    celular_b.post("/api/aluno/entrar", json={"cpf": CPF_ANA, "senha": SENHA})

    resposta = celular_a.post("/api/aluno/sair", json={})

    assert resposta.status_code == 200
    assert _cookie(celular_a) is None
    assert celular_a.get("/aluno").status_code == 302
    assert celular_b.get("/aluno").status_code == 200


def test_sair_sem_estar_logado_nao_da_erro(cliente):
    assert cliente.post("/api/aluno/sair", json={}).status_code == 200


def test_cookie_falso_nao_loga_ninguem(cliente):
    for valor in ("", "lixo", "x" * 43, "x" * 3000, "' OR 1=1 --", "é" * 43):
        cliente.set_cookie(aluno_acesso.NOME_DO_COOKIE, valor)
        assert cliente.get("/aluno").status_code == 302


def test_aluno_que_vira_desistente_continua_com_a_tela(cliente, remetente, caminho):
    _criar_acesso(cliente, remetente, caminho)
    assert cliente.get("/aluno").status_code == 200

    _sql(caminho, "UPDATE aluno SET situacao = 'D' WHERE id = 1")

    assert cliente.get("/aluno").status_code == 200


def test_cadastro_que_vira_provisorio_perde_a_tela_na_hora(cliente, remetente, caminho):
    _criar_acesso(cliente, remetente, caminho)
    assert cliente.get("/aluno").status_code == 200

    _sql(caminho, "UPDATE aluno SET provisorio = 1 WHERE id = 1")

    assert cliente.get("/aluno").status_code == 302


def test_o_cookie_e_renovado_quando_o_ultimo_uso_e_regravado(cliente, remetente, caminho):
    _criar_acesso(cliente, remetente, caminho)
    antes = datetime.now(timezone.utc) - timedelta(hours=2)
    _sql(caminho, "UPDATE aluno_sessao SET ultimo_uso_em = ?", (antes.strftime("%Y-%m-%d %H:%M:%S"),))

    resposta = cliente.get("/aluno")

    assert resposta.status_code == 200
    assert any(c.startswith(aluno_acesso.NOME_DO_COOKIE) for c in resposta.headers.getlist("Set-Cookie"))


# ------------------------------------------------------------------ o aluno não passa da porta do professor


def test_aluno_logado_nao_abre_nada_da_area_do_professor(cliente, remetente, caminho):
    _criar_acesso(cliente, remetente, caminho)

    for metodo, url in [("get", "/api/alunos"), ("get", "/api/alunos/2/treinos-para-copiar"), ("get", "/api/exercicios"), ("get", "/api/modelos"), ("post", "/api/alunos/1/whatsapp")]:
        resposta = getattr(cliente, metodo)(url, **({"json": {}} if metodo == "post" else {}))
        assert resposta.status_code == 401, url
    for url in ("/alunos", "/alunos/2", "/alunos/atualizar", "/alunos/1/montar", "/exercicios", "/treinos/1/imprimir"):
        resposta = cliente.get(url)
        assert resposta.status_code == 302 and "/autorizar" in resposta.headers["Location"], url
    assert NOME_SECRETO_DO_PROFESSOR not in cliente.get("/aluno").get_data(as_text=True)


def test_computador_autorizado_do_professor_nao_vira_aluno(app, caminho):
    conn = _banco(caminho)
    codigo = acesso.gerar_codigo(conn, "Computador dos professores").codigo
    conn.close()
    professor = app.test_client()
    assert professor.post("/api/autorizar", json={"codigo": codigo}).status_code == 200

    assert professor.get("/aluno").status_code == 302
    assert professor.get("/alunos").status_code == 200


def test_o_cookie_do_computador_nao_serve_de_cookie_de_aluno(app, caminho):
    assert acesso.NOME_DO_COOKIE != aluno_acesso.NOME_DO_COOKIE
    conn = _banco(caminho)
    codigo = acesso.gerar_codigo(conn, "Computador dos professores").codigo
    conn.close()
    professor = app.test_client()
    professor.post("/api/autorizar", json={"codigo": codigo})
    token_do_computador = professor.get_cookie(acesso.NOME_DO_COOKIE).value
    atacante = app.test_client()
    atacante.set_cookie(aluno_acesso.NOME_DO_COOKIE, token_do_computador)

    assert atacante.get("/aluno").status_code == 302


def test_as_rotas_do_aluno_estao_na_lista_de_publicas_e_so_elas(app):
    rotas_do_aluno = {r.endpoint for r in app.url_map.iter_rules() if "aluno" in r.rule.split("/") and r.endpoint != "static"}
    rotas_do_aluno = {e for e in rotas_do_aluno if e.startswith(("pagina_aluno_", "api_aluno_"))}

    assert rotas_do_aluno == {e for e in ENDPOINTS_PUBLICOS if e.startswith(("pagina_aluno_", "api_aluno_"))}
    assert len(rotas_do_aluno) == 9


def test_nenhuma_resposta_do_aluno_mostra_cpf_hash_ou_token(cliente, remetente, caminho):
    respostas = [
        _pedir_codigo(cliente),
        _criar_acesso(cliente, remetente, caminho),
        cliente.get("/aluno"),
        cliente.post("/api/aluno/entrar", json={"cpf": CPF_ANA, "senha": "errada 12345"}),
    ]
    texto = "".join(r.get_data(as_text=True) for r in respostas)

    assert CPF_ANA not in texto and "scrypt" not in texto and _cookie(cliente) not in texto
