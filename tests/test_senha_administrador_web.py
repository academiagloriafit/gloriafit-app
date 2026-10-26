"""A senha de administrador nas rotas de treino padrão (adicionar e excluir). Dados inventados.

Regra do Thiago (13/10/2026): os treinos padrão ficam fixos. Salvar como padrão e excluir um padrão só valem com a
senha de administrador; abrir um padrão e ajustá-lo para UM aluno continua livre e nunca muda o padrão.
"""

import json
import re
from pathlib import Path

import pytest

from app import acesso, administrador
from app.db import conectar, criar_tabelas
from app.treinos import salvar_treino
from app.web import criar_app

SENHA = "senha-de-teste-1"

ROTAS_PROTEGIDAS = ["/api/modelos", "/api/modelos/1/excluir", "/api/treinos/1/modelo"]


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "senha.db"
    c = conectar(caminho)
    criar_tabelas(c)
    c.execute("INSERT INTO aluno (id, nome) VALUES (1, 'ANA FICTICIA')")
    c.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO RETO', 'app'), (2, 'REMADA', 'app')")
    c.commit()
    administrador.definir_senha(c, SENHA)
    c.close()
    return caminho


@pytest.fixture
def cliente(caminho):
    navegador = criar_app(caminho).test_client()
    c = conectar(caminho)
    codigo = acesso.gerar_codigo(c, "Computador de teste").codigo
    token = acesso.autorizar(c, codigo).token
    c.close()
    navegador.set_cookie(acesso.NOME_DO_COOKIE, token)
    return navegador


def _fichas():
    return [{"nome": "A", "itens": [{"exercicio_id": 1, "series": "3", "repeticoes": "12"}]}]


def _corpo(**extras):
    return {"nome": "MULHER 1", "montado_por": "Ana", "fichas": _fichas(), **extras}


def _banco(caminho, sql, *args):
    c = conectar(caminho)
    try:
        return [tuple(linha) for linha in c.execute(sql, args)]
    finally:
        c.close()


def _guardar_padrao(cliente, nome="MULHER 1", **extras):
    resposta = cliente.post("/api/modelos", json=_corpo(nome=nome, senha_admin=SENHA, **extras))
    assert resposta.status_code == 201
    return resposta.get_json()["id"]


def _treino_do_aluno(caminho, nome="TREINO ABC"):
    c = conectar(caminho)
    try:
        return salvar_treino(c, 1, {"nome_treino": nome, "montado_por": "Bia", "fichas": _fichas()})
    finally:
        c.close()


def _pedido_de(url, senha=None, **extras):
    corpo = {} if url.endswith("/excluir") else ({"nome": "NOVO PADRÃO"} if url.endswith("/modelo") else _corpo())
    if senha is not None:
        corpo["senha_admin"] = senha
    return {"json": {**corpo, **extras}}


def _quantos_padroes(caminho):
    return _banco(caminho, "SELECT COUNT(*) FROM modelo_treino")[0][0]


# ------------------------------------------------------------------ sem a senha, nada muda


@pytest.mark.parametrize("url", ROTAS_PROTEGIDAS)
def test_sem_a_senha_a_acao_e_recusada_e_nada_e_gravado(cliente, caminho, url):
    _guardar_padrao(cliente, "EXISTENTE")
    treino_id = _treino_do_aluno(caminho)
    url = url.replace("/treinos/1/", f"/treinos/{treino_id}/").replace("/modelos/1/", "/modelos/1/")

    resposta = cliente.post(url, **_pedido_de(url))

    assert resposta.status_code == 403
    assert resposta.get_json() == {"erro": "Senha de administrador incorreta.", "senha": "incorreta"}
    assert _banco(caminho, "SELECT nome FROM modelo_treino") == [("EXISTENTE",)]  # nem criou, nem excluiu


@pytest.mark.parametrize("url", ROTAS_PROTEGIDAS)
@pytest.mark.parametrize("senha", ["errada-123", SENHA.upper(), SENHA + " ", "", None, 12345, ["a"], {"a": 1}, True])
def test_senha_errada_ou_de_tipo_estranho_e_recusada(cliente, caminho, url, senha):
    _guardar_padrao(cliente, "EXISTENTE")
    treino_id = _treino_do_aluno(caminho)
    url = url.replace("/treinos/1/", f"/treinos/{treino_id}/")
    pedido = _pedido_de(url)
    pedido["json"]["senha_admin"] = senha

    resposta = cliente.post(url, **pedido)

    assert resposta.status_code == 403 and resposta.get_json()["senha"] == "incorreta"
    assert _banco(caminho, "SELECT nome FROM modelo_treino") == [("EXISTENTE",)]


@pytest.mark.parametrize("url", ROTAS_PROTEGIDAS)
def test_a_senha_na_url_nao_vale(cliente, caminho, url):
    treino_id = _treino_do_aluno(caminho)
    url = url.replace("/treinos/1/", f"/treinos/{treino_id}/")

    resposta = cliente.post(f"{url}?senha_admin={SENHA}", **_pedido_de(url))

    assert resposta.status_code == 403
    assert _quantos_padroes(caminho) == 0


def test_a_senha_nao_e_repetida_na_resposta(cliente):
    resposta = cliente.post("/api/modelos", json=_corpo(senha_admin="tentativa-secreta-77"))

    assert "tentativa-secreta-77" not in resposta.get_data(as_text=True)


# ------------------------------------------------------------------ com a senha, funciona como antes


def test_com_a_senha_certa_cria_e_exclui_o_padrao(cliente, caminho):
    modelo_id = _guardar_padrao(cliente)

    excluido = cliente.post(f"/api/modelos/{modelo_id}/excluir", json={"senha_admin": SENHA})

    assert excluido.status_code == 200 and excluido.get_json() == {"ok": True}
    assert _quantos_padroes(caminho) == 0


def test_com_a_senha_certa_o_treino_do_aluno_vira_padrao(cliente, caminho):
    treino_id = _treino_do_aluno(caminho)

    resposta = cliente.post(f"/api/treinos/{treino_id}/modelo", json={"senha_admin": SENHA, "nome": "Padrão da Ana"})

    assert resposta.status_code == 201
    assert _banco(caminho, "SELECT nome FROM modelo_treino") == [("Padrão da Ana",)]


def test_com_a_senha_certa_os_erros_de_conteudo_continuam_os_mesmos(cliente):
    cliente.post("/api/modelos", json=_corpo(senha_admin=SENHA))

    repetido = cliente.post("/api/modelos", json=_corpo(senha_admin=SENHA))
    vazio = cliente.post("/api/modelos", json={"senha_admin": SENHA, "nome": "", "fichas": []})
    inexistente = cliente.post("/api/modelos/99/excluir", json={"senha_admin": SENHA})

    assert (repetido.status_code, vazio.status_code, inexistente.status_code) == (409, 400, 404)


def test_a_senha_e_conferida_antes_de_dizer_se_o_padrao_existe(cliente):
    # Quem não tem a senha não descobre, pela diferença entre 403 e 404, quais padrões existem.
    _guardar_padrao(cliente)

    existe = cliente.post("/api/modelos/1/excluir", json={"senha_admin": "errada-123"})
    nao_existe = cliente.post("/api/modelos/99/excluir", json={"senha_admin": "errada-123"})

    assert existe.status_code == nao_existe.status_code == 403
    assert existe.get_json() == nao_existe.get_json()


@pytest.mark.parametrize("corpo", [[], "texto", 5, [{"senha_admin": SENHA}]])
@pytest.mark.parametrize("url", ROTAS_PROTEGIDAS)
def test_corpo_que_nao_e_objeto_volta_400(cliente, url, corpo):
    assert cliente.post(url, json=corpo).status_code == 400


# ------------------------------------------------------------------ servidor sem senha definida: fechado


@pytest.mark.parametrize("url", ROTAS_PROTEGIDAS)
def test_sem_senha_definida_no_servidor_a_acao_fica_fechada(tmp_path, url):
    caminho = tmp_path / "sem-senha.db"
    c = conectar(caminho)
    criar_tabelas(c)
    c.execute("INSERT INTO aluno (id, nome) VALUES (1, 'ANA')")
    c.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO RETO', 'app')")
    c.commit()
    codigo = acesso.gerar_codigo(c, "Computador de teste").codigo
    token = acesso.autorizar(c, codigo).token
    c.close()
    navegador = criar_app(caminho).test_client()
    navegador.set_cookie(acesso.NOME_DO_COOKIE, token)
    treino_id = _treino_do_aluno(caminho)
    url = url.replace("/treinos/1/", f"/treinos/{treino_id}/")

    resposta = navegador.post(url, **_pedido_de(url, senha=SENHA))

    assert resposta.status_code == 403
    assert resposta.get_json()["senha"] == "nao_definida"
    assert "definir a senha" in resposta.get_json()["erro"]
    assert _quantos_padroes(caminho) == 0
    assert _banco(caminho, "SELECT COUNT(*) FROM senha_administrador_falha") == [(0,)]  # não é erro de digitação


# ------------------------------------------------------------------ trava por excesso de erros


def test_cinco_senhas_erradas_travam_ate_a_senha_certa_e_a_resposta_diz_quanto_esperar(cliente, caminho):
    for _ in range(administrador.LIMITE_DE_FALHAS):
        assert cliente.post("/api/modelos", json=_corpo(senha_admin="errada-123")).status_code == 403

    travado = cliente.post("/api/modelos", json=_corpo(senha_admin=SENHA))

    assert travado.status_code == 429
    assert travado.get_json()["senha"] == "travada"
    assert "Tente de novo em" in travado.get_json()["erro"] and "min" in travado.get_json()["erro"]
    assert 1 <= int(travado.headers["Retry-After"]) <= 15 * 60 + 1
    assert _quantos_padroes(caminho) == 0


def test_a_trava_vale_para_as_tres_rotas(cliente, caminho):
    for _ in range(administrador.LIMITE_DE_FALHAS):
        cliente.post("/api/modelos", json=_corpo(senha_admin="errada-123"))
    treino_id = _treino_do_aluno(caminho)

    excluir = cliente.post("/api/modelos/1/excluir", json={"senha_admin": SENHA})
    como_padrao = cliente.post(f"/api/treinos/{treino_id}/modelo", json={"senha_admin": SENHA, "nome": "X"})

    assert excluir.status_code == como_padrao.status_code == 429


def test_acertar_zera_a_conta_de_erros(cliente, caminho):
    for _ in range(administrador.LIMITE_DE_FALHAS - 1):
        cliente.post("/api/modelos", json=_corpo(senha_admin="errada-123"))
    assert cliente.post("/api/modelos", json=_corpo(senha_admin=SENHA)).status_code == 201

    assert _banco(caminho, "SELECT COUNT(*) FROM senha_administrador_falha") == [(0,)]


# ------------------------------------------------------------------ o que continua livre (sem senha)


def test_ler_padroes_e_abrir_um_para_o_aluno_continua_livre(cliente):
    modelo_id = _guardar_padrao(cliente)

    assert cliente.get("/api/modelos").status_code == 200
    assert cliente.get(f"/api/modelos/{modelo_id}").status_code == 200


def test_lancar_treino_para_o_aluno_com_o_padrao_aberto_nao_pede_senha_e_nao_muda_o_padrao(cliente, caminho):
    modelo_id = _guardar_padrao(cliente)
    padrao_antes = _banco(caminho, "SELECT nome, conteudo FROM modelo_treino WHERE id = ?", modelo_id)

    # o professor abre o padrão, muda o número de séries e salva SÓ para o aluno (sem senha)
    aberto = cliente.get(f"/api/modelos/{modelo_id}").get_json()
    fichas = [
        {"nome": f["nome"], "itens": [{**i, "series": "5", "repeticoes": "8", "carga": i["carga"] or ""} for i in f["itens"]]}
        for f in aberto["fichas"]
    ]
    pedido = {"nome_treino": "TREINO DA ANA", "montado_por": "Bia", "fichas": fichas}
    resposta = cliente.post("/api/alunos/1/treinos", json=pedido)

    assert resposta.status_code == 201, resposta.get_data(as_text=True)
    assert _banco(caminho, "SELECT nome, conteudo FROM modelo_treino WHERE id = ?", modelo_id) == padrao_antes  # padrão intacto
    assert _banco(caminho, "SELECT series FROM ficha_item") == [("5",)]


def test_editar_o_treino_do_aluno_nao_pede_senha(cliente, caminho):
    treino_id = _treino_do_aluno(caminho)
    pedido = {"nome_treino": "TREINO ABC", "montado_por": "Bia", "fichas": _fichas()}

    resposta = cliente.post(f"/api/treinos/{treino_id}/editar", json=pedido)

    assert resposta.status_code == 200


def test_so_as_tres_rotas_de_padrao_exigem_a_senha(cliente):
    # Toda rota que muda dados e NÃO está na lista de protegidas não pode pedir senha: ela nunca devolve o "senha".
    app = cliente.application
    protegidas = {"api_criar_modelo", "api_excluir_modelo", "api_treino_como_modelo"}
    for regra in app.url_map.iter_rules():
        if regra.endpoint in protegidas or "POST" not in regra.methods:
            continue
        if regra.endpoint in {"api_autorizar"}:
            continue
        url = regra.rule
        for argumento in regra.arguments:
            url = url.replace(f"<int:{argumento}>", "99999")
        resposta = cliente.post(url, json={})
        corpo = resposta.get_json(silent=True) or {}
        assert "senha" not in corpo, f"{regra.endpoint} pede a senha de administrador"
    assert protegidas <= {r.endpoint for r in app.url_map.iter_rules()}, "o nome de uma rota protegida mudou: atualize este teste"


def test_nao_ha_rota_para_ler_a_senha_nem_o_hash(cliente):
    for rota in cliente.application.url_map.iter_rules():
        assert "senha" not in rota.rule.lower(), rota.rule
    assert "senha_administrador" not in json.dumps(cliente.get("/api/modelos").get_json())


# ------------------------------------------------------------------ as telas pedem a senha (sem guardá-la em lugar nenhum)

PASTA_ESTATICA = Path(__file__).resolve().parent.parent / "app" / "static"


def _campos_de_senha(html):
    return re.findall(r"<input\b[^>]*\btype=\"password\"[^>]*>", html)


def test_a_tela_de_montar_pede_a_senha_ao_salvar_como_padrao(cliente):
    html = cliente.get("/alunos/1/montar").get_data(as_text=True)

    campos = _campos_de_senha(html)
    assert len(campos) == 1
    assert 'id="senha-admin-padrao"' in campos[0]
    assert 'autocomplete="off"' in campos[0]
    assert "value=" not in campos[0]  # a senha nunca vem escrita na página
    assert 'for="senha-admin-padrao"' in html  # com rótulo, para leitor de tela


def test_a_ficha_pede_a_senha_em_cada_treino_ao_salvar_como_padrao(cliente, caminho):
    _treino_do_aluno(caminho, "TREINO ANTIGO")
    _treino_do_aluno(caminho, "TREINO NOVO")
    html = cliente.get("/alunos/1").get_data(as_text=True)

    campos = _campos_de_senha(html)
    assert len(campos) == 2
    ids = [re.search(r'id="([^"]+)"', c).group(1) for c in campos]
    assert len(set(ids)) == 2  # um id para cada treino
    for campo, id_ in zip(campos, ids):
        assert 'class="campo-senha-admin"' in campo and 'autocomplete="off"' in campo and "value=" not in campo
        assert f'for="{id_}"' in html


def test_as_telas_sem_formulario_de_padrao_nao_pedem_senha(cliente):
    # a lista de alunos e a busca não têm nada a ver com treino padrão
    assert _campos_de_senha(cliente.get("/alunos").get_data(as_text=True)) == []


def test_o_rascunho_do_navegador_nunca_leva_a_senha():
    codigo = (PASTA_ESTATICA / "montar.js").read_text(encoding="utf-8")
    trecho = codigo[codigo.index("function guardarRascunho") : codigo.index("function lerDadosGuardados")]

    assert "Local.gravar" in trecho  # (o trecho certo foi encontrado: desde 26/10/2026 o rascunho vai para o localStorage)
    assert "enha" not in trecho


@pytest.mark.parametrize("arquivo", sorted(p.name for p in PASTA_ESTATICA.glob("*.js")))
def test_nenhum_javascript_poe_a_senha_na_url_nem_no_armazenamento(arquivo):
    codigo = (PASTA_ESTATICA / arquivo).read_text(encoding="utf-8")
    linhas_com_senha = [l for l in codigo.splitlines() if re.search(r"senha_admin|senhaAdmin|\bsenha\b|Senha", l) and not l.lstrip().startswith("//")]

    for linha in linhas_com_senha:
        assert not re.search(r"localStorage|sessionStorage|document\.cookie|location\.|URLSearchParams|history\.", linha), linha
        assert not re.search(r"console\.", linha), linha  # nem no console
