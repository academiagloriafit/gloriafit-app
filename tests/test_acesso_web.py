"""Testes da proteção da área do professor no servidor web (app/web.py)."""

import re
from datetime import datetime, timedelta, timezone

import pytest

from app import acesso
from app.db import conectar, criar_tabelas
from app.web import ENDPOINTS_PUBLICOS, criar_app

NOME_SECRETO = "ALUNO SIGILOSO DE TESTE"


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "acesso.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.execute("INSERT INTO grupo_muscular (nome, ordem) VALUES ('Peito', 1)")
    conn.execute("INSERT INTO exercicio (nome, origem) VALUES ('Supino', 'app')")
    conn.execute("INSERT INTO aluno (nome, cpf) VALUES (?, '11144477735')", (NOME_SECRETO,))
    conn.commit()
    conn.close()
    return caminho


@pytest.fixture
def app(caminho):
    return criar_app(caminho)


@pytest.fixture
def anonimo(app):
    """Um navegador qualquer, sem cookie nenhum (o celular de alguém, por exemplo)."""
    return app.test_client()


def _banco(caminho):
    return conectar(caminho)


def _gerar_codigo(caminho, nome="Computador dos professores", agora=None):
    conn = _banco(caminho)
    try:
        return acesso.gerar_codigo(conn, nome, agora=agora).codigo
    finally:
        conn.close()


def _autorizado(app, caminho, nome="Computador dos professores"):
    """Navegador que passou pelo /autorizar de verdade."""
    cliente = app.test_client()
    resposta = cliente.post("/api/autorizar", json={"codigo": _gerar_codigo(caminho, nome)})
    assert resposta.status_code == 200
    return cliente


def _linha_do_dispositivo(caminho):
    conn = _banco(caminho)
    try:
        return conn.execute("SELECT * FROM dispositivo ORDER BY id DESC").fetchone()
    finally:
        conn.close()


def _sql(caminho, comando, parametros=()):
    conn = _banco(caminho)
    try:
        with conn:
            conn.execute(comando, parametros)
    finally:
        conn.close()


def _contar(caminho, tabela):
    conn = _banco(caminho)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
    finally:
        conn.close()


# ------------------------------------------------------------------ sem autorização


PAGINAS = ["/", "/alunos", "/alunos/1", "/alunos/1/montar", "/exercicios"]
APIS_GET = ["/api/alunos", "/api/alunos?q=sigiloso", "/api/exercicios", "/api/grupos"]


@pytest.mark.parametrize("caminho_da_pagina", PAGINAS)
def test_pagina_sem_autorizacao_leva_para_autorizar_e_nao_mostra_nada(anonimo, caminho_da_pagina):
    resposta = anonimo.get(caminho_da_pagina)

    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/autorizar")
    corpo = resposta.get_data(as_text=True)
    assert NOME_SECRETO not in corpo
    assert "11144477735" not in corpo


@pytest.mark.parametrize("url", APIS_GET)
def test_api_sem_autorizacao_devolve_401_em_json_sem_dados(anonimo, url):
    resposta = anonimo.get(url)

    assert resposta.status_code == 401
    assert resposta.is_json
    assert "autorizado" in resposta.get_json()["erro"]
    assert "/autorizar" in resposta.get_json()["erro"]
    assert resposta.headers["Cache-Control"] == "no-store"
    texto = resposta.get_data(as_text=True)
    assert NOME_SECRETO not in texto and "Supino" not in texto


def test_aluno_que_existe_e_aluno_que_nao_existe_parecem_iguais_sem_autorizacao(anonimo):
    # Sem esta igualdade, dava para descobrir quais ids existem testando um por um.
    existe = anonimo.get("/alunos/1")
    nao_existe = anonimo.get("/alunos/987654")

    assert (existe.status_code, existe.headers["Location"]) == (
        nao_existe.status_code,
        nao_existe.headers["Location"],
    )


def test_rotas_de_escrita_sem_autorizacao_devolvem_401_e_nao_gravam(anonimo, caminho):
    treino = anonimo.post("/api/alunos/1/treinos", json={"nome": "X"})
    whatsapp = anonimo.post("/api/alunos/1/whatsapp", json={"whatsapp": "(27) 98888-7766"})

    assert treino.status_code == 401
    assert whatsapp.status_code == 401
    assert _contar(caminho, "treino") == 0
    conn = _banco(caminho)
    assert conn.execute("SELECT whatsapp FROM aluno").fetchone()[0] is None
    conn.close()


@pytest.mark.parametrize("cookie", ["", "lixo", "x" * 43, "x" * 3000, "' OR 1=1 --", "é" * 43])
def test_cookie_falso_nao_vale(anonimo, cookie):
    anonimo.set_cookie(acesso.NOME_DO_COOKIE, cookie)

    assert anonimo.get("/api/alunos").status_code == 401
    assert anonimo.get("/alunos").status_code == 302


def test_toda_rota_do_app_exige_autorizacao_exceto_as_publicas(app, anonimo):
    """Rede de segurança: rota nova esquecida da lista de públicas tem que ficar protegida."""
    adaptador = app.url_map.bind("localhost")
    testadas = 0
    for regra in app.url_map.iter_rules():
        if regra.endpoint in ENDPOINTS_PUBLICOS:
            continue
        url = adaptador.build(regra.endpoint, {argumento: 1 for argumento in regra.arguments})
        for metodo in sorted(regra.methods - {"HEAD", "OPTIONS"}):
            resposta = anonimo.open(url, method=metodo, json={} if metodo != "GET" else None)
            assert resposta.status_code in (302, 401), f"{metodo} {url} está aberto sem autorização"
            testadas += 1
    assert testadas >= 10  # garante que o laço realmente testou as rotas


def test_a_lista_de_rotas_publicas_so_tem_rotas_que_existem(app):
    existentes = {regra.endpoint for regra in app.url_map.iter_rules()}

    assert ENDPOINTS_PUBLICOS <= existentes


def test_rotas_publicas_abrem_sem_autorizacao(anonimo):
    assert anonimo.get("/saude").status_code == 200
    assert anonimo.get("/static/estilo.css").status_code == 200
    assert anonimo.get("/static/autorizar.js").status_code == 200
    assert anonimo.get("/autorizar").status_code == 200


def test_rota_que_nao_existe_continua_404_sem_autorizacao(anonimo):
    assert anonimo.get("/nao-existe").status_code == 404


# ------------------------------------------------------------------ a tela /autorizar


def test_tela_de_autorizar_tem_campo_botao_e_script_externo(anonimo):
    html = anonimo.get("/autorizar").get_data(as_text=True)

    assert 'id="codigo"' in html
    assert "Autorizar este computador" in html
    assert 'src="/static/autorizar.js"' in html
    assert NOME_SECRETO not in html
    assert "<script>" not in html and "style=" not in html
    assert not re.search(r'(src|href)="https?://', html)


def test_tela_de_autorizar_nao_mostra_o_menu_do_app(anonimo):
    assert 'href="/alunos"' not in anonimo.get("/autorizar").get_data(as_text=True)


def test_tela_de_autorizar_leva_para_os_alunos_se_o_computador_ja_esta_autorizado(app, caminho):
    cliente = _autorizado(app, caminho)

    resposta = cliente.get("/autorizar")

    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/alunos")


# ------------------------------------------------------------------ autorizar de verdade


def test_codigo_certo_autoriza_e_o_cookie_abre_a_area(app, caminho):
    cliente = app.test_client()
    codigo = _gerar_codigo(caminho)

    resposta = cliente.post("/api/autorizar", json={"codigo": codigo})

    assert resposta.status_code == 200
    assert resposta.get_json() == {"ok": True, "nome": "Computador dos professores"}
    ficha = cliente.get("/alunos/1")
    assert ficha.status_code == 200
    assert NOME_SECRETO in ficha.get_data(as_text=True)
    assert cliente.get("/api/alunos").status_code == 200


def test_cookie_de_autorizacao_tem_as_protecoes_certas(app, caminho):
    resposta = app.test_client().post("/api/autorizar", json={"codigo": _gerar_codigo(caminho)})

    cookie = resposta.headers["Set-Cookie"]
    assert cookie.startswith(acesso.NOME_DO_COOKIE + "=")
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    assert "Path=/" in cookie
    assert "Max-Age=34560000" in cookie  # 400 dias
    assert "Domain" not in cookie  # só vale para este endereço, nunca para subdomínios
    assert "Secure" not in cookie  # em localhost (desenvolvimento) o navegador não aceita Secure sem HTTPS


def test_cookie_em_endereco_de_verdade_e_marcado_secure(app, caminho):
    resposta = app.test_client().post(
        "/api/autorizar",
        json={"codigo": _gerar_codigo(caminho)},
        base_url="https://app.exemplo.com.br",
    )

    assert resposta.status_code == 200
    assert "Secure" in resposta.headers["Set-Cookie"]


def test_cookie_nao_vai_na_resposta_quando_o_codigo_esta_errado(anonimo):
    resposta = anonimo.post("/api/autorizar", json={"codigo": "AAAAA-AAAAA"})

    assert resposta.status_code == 400
    assert "Set-Cookie" not in resposta.headers


def test_o_valor_do_cookie_nao_aparece_no_corpo_nem_no_banco(app, caminho):
    resposta = app.test_client().post("/api/autorizar", json={"codigo": _gerar_codigo(caminho)})
    token = re.match(rf"{acesso.NOME_DO_COOKIE}=([^;]+);", resposta.headers["Set-Cookie"]).group(1)

    assert token not in resposta.get_data(as_text=True)
    linha = _linha_do_dispositivo(caminho)
    assert token not in "".join(str(v) for v in tuple(linha))


def test_dois_computadores_cada_um_com_seu_codigo_e_seu_nome(app, caminho):
    professores = _autorizado(app, caminho, "Computador dos professores")
    recepcao = _autorizado(app, caminho, "Computador da recepção")

    html_professores = professores.get("/alunos").get_data(as_text=True)
    html_recepcao = recepcao.get("/alunos").get_data(as_text=True)

    assert '<div class="topo-nota">Computador dos professores</div>' in html_professores
    assert '<div class="topo-nota">Computador da recepção</div>' in html_recepcao


def test_codigo_ja_usado_nao_autoriza_outro_aparelho(app, caminho):
    codigo = _gerar_codigo(caminho)
    app.test_client().post("/api/autorizar", json={"codigo": codigo})

    celular = app.test_client()
    resposta = celular.post("/api/autorizar", json={"codigo": codigo})

    assert resposta.status_code == 400
    assert celular.get("/api/alunos").status_code == 401


def test_codigo_vencido_e_recusado(app, caminho, anonimo):
    codigo = _gerar_codigo(caminho, agora=datetime.now(timezone.utc) - timedelta(minutes=16))

    resposta = anonimo.post("/api/autorizar", json={"codigo": codigo})

    assert resposta.status_code == 400
    assert resposta.get_json()["erro"] == "Código inválido ou vencido."


def test_codigo_digitado_com_minusculas_e_espacos_funciona(app, caminho):
    codigo = _gerar_codigo(caminho).lower().replace("-", " ")

    resposta = app.test_client().post("/api/autorizar", json={"codigo": f"  {codigo}  "})

    assert resposta.status_code == 200


@pytest.mark.parametrize("corpo", [{}, {"codigo": ""}, {"codigo": "   "}, {"codigo": None}, {"codigo": 123}, {"codigo": ["A"]}])
def test_codigo_vazio_ou_de_tipo_errado_devolve_400_e_nao_conta_como_tentativa(anonimo, caminho, corpo):
    resposta = anonimo.post("/api/autorizar", json=corpo)

    assert resposta.status_code == 400
    assert _contar(caminho, "autorizacao_falha") == 0


@pytest.mark.parametrize("corpo", [[], "texto", 5, ["ABCDE-23456"]])
def test_corpo_que_nao_e_objeto_devolve_400(anonimo, corpo):
    assert anonimo.post("/api/autorizar", json=corpo).status_code == 400


def test_autorizar_exige_json(anonimo):
    resposta = anonimo.post("/api/autorizar", data="codigo=AAAAA-AAAAA")

    assert resposta.status_code == 415


def test_autorizar_so_aceita_post(anonimo):
    assert anonimo.get("/api/autorizar").status_code == 405
    assert anonimo.put("/api/autorizar", json={}).status_code == 405


def test_cinco_codigos_errados_travam_ate_o_codigo_certo(app, caminho, anonimo):
    codigo = _gerar_codigo(caminho)
    for _ in range(acesso.LIMITE_DE_FALHAS):
        assert anonimo.post("/api/autorizar", json={"codigo": "AAAAA-AAAAA"}).status_code == 400

    travado = anonimo.post("/api/autorizar", json={"codigo": codigo})

    assert travado.status_code == 429
    assert "Muitos códigos errados" in travado.get_json()["erro"]
    assert int(travado.headers["Retry-After"]) > 0
    assert "Set-Cookie" not in travado.headers
    assert _contar(caminho, "dispositivo") == 0


def test_o_travamento_vale_para_qualquer_navegador(app, caminho):
    codigo = _gerar_codigo(caminho)
    atacante = app.test_client()
    for _ in range(acesso.LIMITE_DE_FALHAS):
        atacante.post("/api/autorizar", json={"codigo": "AAAAA-AAAAA"})

    outro_navegador = app.test_client()

    assert outro_navegador.post("/api/autorizar", json={"codigo": codigo}).status_code == 429


def test_travamento_nao_atrapalha_quem_ja_esta_autorizado(app, caminho):
    cliente = _autorizado(app, caminho)
    for _ in range(acesso.LIMITE_DE_FALHAS):
        app.test_client().post("/api/autorizar", json={"codigo": "AAAAA-AAAAA"})

    assert cliente.get("/api/alunos").status_code == 200


# ------------------------------------------------------------------ pedidos vindos de outro site


def _treino_minimo():
    return {"nome": "TREINO", "montado_por": "Ana", "fichas": []}


def test_pedido_de_escrita_com_origem_de_outro_site_e_recusado(app, caminho):
    cliente = _autorizado(app, caminho)

    resposta = cliente.post(
        "/api/alunos/1/whatsapp",
        json={"whatsapp": "(27) 98888-7766"},
        headers={"Origin": "https://site-malicioso.example"},
    )

    assert resposta.status_code == 403
    conn = _banco(caminho)
    assert conn.execute("SELECT whatsapp FROM aluno").fetchone()[0] is None
    conn.close()


@pytest.mark.parametrize(
    "origem",
    [
        "null",
        "",
        "http://localhost.evil.example",
        "http://evil.example/localhost",
        "http://localhost:9999",
        "https://localhost",  # mesmo endereço, mas https: o esquema também é conferido
    ],
)
def test_origens_parecidas_mas_diferentes_tambem_sao_recusadas(app, caminho, origem):
    cliente = _autorizado(app, caminho)

    resposta = cliente.post("/api/alunos/1/whatsapp", json={"whatsapp": "(27) 98888-7766"}, headers={"Origin": origem})

    assert resposta.status_code == 403


def test_origem_do_proprio_site_ou_sem_origem_passa(app, caminho):
    cliente = _autorizado(app, caminho)

    mesma = cliente.post(
        "/api/alunos/1/whatsapp", json={"whatsapp": "(27) 98888-7766"}, headers={"Origin": "http://localhost"}
    )
    sem_origem = cliente.post("/api/alunos/1/whatsapp", json={"whatsapp": "(27) 97777-6655"})

    assert mesma.status_code == 200
    assert sem_origem.status_code == 200


def test_origem_de_outro_site_nao_gasta_o_codigo_de_autorizacao(app, caminho, anonimo):
    codigo = _gerar_codigo(caminho)

    recusado = anonimo.post(
        "/api/autorizar", json={"codigo": codigo}, headers={"Origin": "https://site-malicioso.example"}
    )

    assert recusado.status_code == 403
    assert _contar(caminho, "autorizacao_falha") == 0
    assert anonimo.post("/api/autorizar", json={"codigo": codigo}).status_code == 200


def test_leitura_com_origem_de_outro_site_nao_e_barrada_pela_checagem_de_origem(app, caminho):
    # GET não muda nada; quem protege os dados dele é o cookie (SameSite) e a autorização.
    cliente = _autorizado(app, caminho)

    resposta = cliente.get("/api/alunos", headers={"Origin": "https://outro.example"})

    assert resposta.status_code == 200


# ------------------------------------------------------------------ computador revogado ou parado


def test_computador_revogado_perde_o_acesso_na_hora(app, caminho):
    cliente = _autorizado(app, caminho)
    assert cliente.get("/api/alunos").status_code == 200

    conn = _banco(caminho)
    acesso.revogar(conn, _linha_do_dispositivo(caminho)["id"])
    conn.close()

    assert cliente.get("/api/alunos").status_code == 401
    assert cliente.get("/alunos").status_code == 302
    assert cliente.post("/api/alunos/1/whatsapp", json={"whatsapp": "(27) 98888-7766"}).status_code == 401


def test_revogar_um_computador_nao_derruba_o_outro(app, caminho):
    professores = _autorizado(app, caminho, "Computador dos professores")
    recepcao = _autorizado(app, caminho, "Computador da recepção")

    conn = _banco(caminho)
    acesso.revogar(conn, 1)
    conn.close()

    assert professores.get("/api/alunos").status_code == 401
    assert recepcao.get("/api/alunos").status_code == 200


def test_computador_parado_por_mais_de_90_dias_perde_o_acesso(app, caminho):
    cliente = _autorizado(app, caminho)
    antigo = (datetime.now(timezone.utc) - timedelta(days=91)).strftime("%Y-%m-%d %H:%M:%S")
    _sql(caminho, "UPDATE dispositivo SET ultimo_uso_em = ?", (antigo,))

    assert cliente.get("/api/alunos").status_code == 401


def test_computador_revogado_pode_ser_autorizado_de_novo_com_codigo_novo(app, caminho):
    cliente = _autorizado(app, caminho)
    conn = _banco(caminho)
    acesso.revogar(conn, 1)
    conn.close()
    assert cliente.get("/api/alunos").status_code == 401

    assert cliente.post("/api/autorizar", json={"codigo": _gerar_codigo(caminho)}).status_code == 200

    assert cliente.get("/api/alunos").status_code == 200


def test_uso_depois_de_uma_hora_renova_o_cookie_e_o_ultimo_uso(app, caminho):
    cliente = _autorizado(app, caminho)
    antigo = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    _sql(caminho, "UPDATE dispositivo SET ultimo_uso_em = ?", (antigo,))

    resposta = cliente.get("/api/alunos")

    assert resposta.status_code == 200
    assert acesso.NOME_DO_COOKIE + "=" in resposta.headers["Set-Cookie"]
    assert "Max-Age=34560000" in resposta.headers["Set-Cookie"]
    assert _linha_do_dispositivo(caminho)["ultimo_uso_em"] > antigo


def test_uso_dentro_da_hora_nao_regrava_nada_nem_reenvia_o_cookie(app, caminho):
    cliente = _autorizado(app, caminho)
    antes = _linha_do_dispositivo(caminho)["ultimo_uso_em"]

    resposta = cliente.get("/api/alunos")

    assert resposta.status_code == 200
    assert "Set-Cookie" not in resposta.headers
    assert _linha_do_dispositivo(caminho)["ultimo_uso_em"] == antes


# ------------------------------------------------------------------ cabeçalhos


@pytest.mark.parametrize("url", ["/alunos", "/alunos/1", "/alunos/1/montar", "/exercicios", "/api/alunos"])
def test_paginas_e_api_autorizadas_nao_ficam_em_cache(app, caminho, url):
    cliente = _autorizado(app, caminho)

    assert cliente.get(url).headers["Cache-Control"] == "no-store"


def test_redirecionamento_para_autorizar_tambem_nao_fica_em_cache(anonimo):
    assert anonimo.get("/alunos").headers["Cache-Control"] == "no-store"


def test_arquivos_estaticos_continuam_podendo_ficar_em_cache(anonimo):
    assert anonimo.get("/static/estilo.css").headers.get("Cache-Control") != "no-store"
