"""Treinos padrão e cópia de treinos, pela web (rotas de app/web.py). Dados inventados."""

import re
from pathlib import Path

import pytest

from app import acesso
from app.db import conectar, criar_tabelas
from app.treinos import salvar_treino
from app.web import criar_app


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "modelos.db"
    c = conectar(caminho)
    criar_tabelas(c)
    c.execute("INSERT INTO aluno (id, nome) VALUES (1, 'ANA FICTICIA'), (2, 'BRUNO FICTICIO')")
    c.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, '(3) SUPINO RETO', 'app'), (2, 'REMADA', 'app')")
    c.execute("INSERT INTO exercicio (id, nome, origem, ativo) VALUES (3, 'DESATIVADO', 'app', 0)")
    c.commit()
    c.close()
    return caminho


@pytest.fixture
def app(caminho):
    return criar_app(caminho)


@pytest.fixture
def anonimo(app):
    return app.test_client()


@pytest.fixture
def cliente(app, caminho):
    navegador = app.test_client()
    c = conectar(caminho)
    codigo = acesso.gerar_codigo(c, "Computador de teste").codigo
    token = acesso.autorizar(c, codigo).token
    c.close()
    navegador.set_cookie(acesso.NOME_DO_COOKIE, token)
    return navegador


def _fichas():
    return [{"nome": "FICHA A", "itens": [{"exercicio_id": 1, "series": "3", "repeticoes": "12"}, {"exercicio_id": 2, "series": "3", "repeticoes": "10"}]}]


def _corpo_do_modelo(nome="BÁSICO 1", **extras):
    return {"nome": nome, "montado_por": "Ana", "sessoes_por_ficha": 15, "fichas": _fichas(), **extras}


def _treino_do_aluno(caminho, aluno=1, nome="TREINO ABC"):
    c = conectar(caminho)
    try:
        return salvar_treino(c, aluno, {"nome_treino": nome, "montado_por": "Bia", "fichas": _fichas()})
    finally:
        c.close()


def _banco(caminho, sql, *args):
    c = conectar(caminho)
    try:
        return [tuple(linha) for linha in c.execute(sql, args)]
    finally:
        c.close()


# ------------------------------------------------------------------ proteção


@pytest.mark.parametrize(
    "metodo, url",
    [
        ("get", "/api/modelos"),
        ("get", "/api/modelos/1"),
        ("post", "/api/modelos"),
        ("post", "/api/modelos/1/excluir"),
        ("post", "/api/treinos/1/modelo"),
        ("get", "/api/alunos/1/treinos-para-copiar"),
        ("get", "/api/treinos/1/para-montar"),
    ],
)
def test_sem_computador_autorizado_tudo_e_recusado(anonimo, metodo, url):
    resposta = getattr(anonimo, metodo)(url, **({"json": {}} if metodo == "post" else {}))

    assert resposta.status_code == 401


@pytest.mark.parametrize("url", ["/api/modelos", "/api/modelos/1/excluir", "/api/treinos/1/modelo"])
def test_pedido_que_muda_dados_vindo_de_outro_site_e_recusado(cliente, url):
    resposta = cliente.post(url, json=_corpo_do_modelo(), headers={"Origin": "https://outro-site.example"})

    assert resposta.status_code == 403
    assert _banco(cliente.application.config["CAMINHO_BANCO"], "SELECT COUNT(*) FROM modelo_treino") == [(0,)]


@pytest.mark.parametrize("url", ["/api/modelos", "/api/modelos/1/excluir", "/api/treinos/1/modelo"])
def test_pedido_que_nao_e_json_e_recusado(cliente, url):
    resposta = cliente.post(url, data="nome=x", content_type="application/x-www-form-urlencoded")

    assert resposta.status_code == 415


@pytest.mark.parametrize("url", ["/api/modelos/1/excluir", "/api/treinos/1/modelo"])
def test_rotas_que_mudam_dados_nao_aceitam_get(cliente, url):
    assert cliente.get(url).status_code == 405


def test_respostas_nao_ficam_guardadas_no_navegador(cliente):
    assert cliente.get("/api/modelos").headers["Cache-Control"] == "no-store"


# ------------------------------------------------------------------ criar, listar, ler, excluir


def test_cria_lista_le_e_exclui_um_treino_padrao(cliente, caminho):
    criado = cliente.post("/api/modelos", json=_corpo_do_modelo())
    assert criado.status_code == 201
    modelo_id = criado.get_json()["id"]

    lista = cliente.get("/api/modelos").get_json()["modelos"]
    assert [(m["nome"], m["resumo"], m["sessoes_por_ficha"]) for m in lista] == [("BÁSICO 1", "1 ficha · 2 exercícios", 15)]

    montar = cliente.get(f"/api/modelos/{modelo_id}").get_json()
    assert montar["nome"] == "BÁSICO 1"
    assert [i["nome"] for i in montar["fichas"][0]["itens"]] == ["SUPINO RETO", "REMADA"]  # sem o número da máquina
    assert montar["indisponiveis"] == 0

    assert cliente.post(f"/api/modelos/{modelo_id}/excluir", json={}).get_json() == {"ok": True}
    assert cliente.get("/api/modelos").get_json() == {"modelos": []}


def test_modelo_invalido_volta_400_com_os_motivos(cliente, caminho):
    resposta = cliente.post("/api/modelos", json=_corpo_do_modelo(nome="", fichas=[]))

    assert resposta.status_code == 400
    assert len(resposta.get_json()["erros"]) == 2
    assert _banco(caminho, "SELECT COUNT(*) FROM modelo_treino") == [(0,)]


def test_modelo_com_exercicio_desativado_volta_400(cliente):
    fichas = [{"nome": "A", "itens": [{"exercicio_id": 3, "series": "3", "repeticoes": "12"}]}]

    resposta = cliente.post("/api/modelos", json=_corpo_do_modelo(fichas=fichas))

    assert resposta.status_code == 400
    assert "desativado" in resposta.get_json()["erros"][0]


def test_nome_repetido_volta_409(cliente):
    cliente.post("/api/modelos", json=_corpo_do_modelo())

    resposta = cliente.post("/api/modelos", json=_corpo_do_modelo(nome="básico 1"))

    assert resposta.status_code == 409
    assert "Já existe" in resposta.get_json()["erros"][0]


@pytest.mark.parametrize("corpo", [[], "texto", 5])
def test_corpo_que_nao_e_objeto_volta_400(cliente, corpo):
    assert cliente.post("/api/modelos", json=corpo).status_code == 400


def test_modelo_que_nao_existe_volta_404(cliente):
    assert cliente.get("/api/modelos/99").status_code == 404
    assert cliente.post("/api/modelos/99/excluir", json={}).status_code == 404


# ------------------------------------------------------------------ salvar como padrão a partir de um treino


def test_treino_vira_padrao_pela_ficha_do_aluno(cliente, caminho):
    treino_id = _treino_do_aluno(caminho)

    resposta = cliente.post(f"/api/treinos/{treino_id}/modelo", json={"nome": "Padrão da Ana"})

    assert resposta.status_code == 201
    assert _banco(caminho, "SELECT nome, montado_por FROM modelo_treino") == [("Padrão da Ana", "Bia")]


def test_treino_como_padrao_erros(cliente, caminho):
    treino_id = _treino_do_aluno(caminho)
    cliente.post(f"/api/treinos/{treino_id}/modelo", json={"nome": "X"})

    assert cliente.post(f"/api/treinos/{treino_id}/modelo", json={"nome": "x"}).status_code == 409
    assert cliente.post(f"/api/treinos/{treino_id}/modelo", json={"nome": ""}).status_code == 400
    assert cliente.post(f"/api/treinos/{treino_id}/modelo", json={}).status_code == 400
    assert cliente.post(f"/api/treinos/{treino_id}/modelo", json=[]).status_code == 400
    assert cliente.post("/api/treinos/99/modelo", json={"nome": "Y"}).status_code == 404


# ------------------------------------------------------------------ treino de outro aluno


def test_lista_treinos_do_aluno_e_devolve_um_para_montar(cliente, caminho):
    treino_id = _treino_do_aluno(caminho, aluno=1)

    lista = cliente.get("/api/alunos/1/treinos-para-copiar").get_json()["treinos"]
    assert [(t["id"], t["nome"], t["ativo"], t["resumo"]) for t in lista] == [(treino_id, "TREINO ABC", True, "1 ficha · 2 exercícios")]

    montar = cliente.get(f"/api/treinos/{treino_id}/para-montar").get_json()
    assert montar["nome"] == "TREINO ABC"
    assert montar["fichas"][0]["itens"][0]["exercicio_id"] == 1
    assert montar["fichas"][0]["itens"][0]["nome"] == "SUPINO RETO"


def test_ler_um_treino_para_copiar_nao_grava_nada(cliente, caminho):
    treino_id = _treino_do_aluno(caminho, aluno=1)
    antes = _banco(caminho, "SELECT (SELECT COUNT(*) FROM treino), (SELECT COUNT(*) FROM ficha_item), (SELECT COUNT(*) FROM modelo_treino)")

    cliente.get(f"/api/treinos/{treino_id}/para-montar")
    cliente.get("/api/alunos/1/treinos-para-copiar")

    assert _banco(caminho, "SELECT (SELECT COUNT(*) FROM treino), (SELECT COUNT(*) FROM ficha_item), (SELECT COUNT(*) FROM modelo_treino)") == antes


def test_aluno_ou_treino_que_nao_existe(cliente):
    assert cliente.get("/api/alunos/99/treinos-para-copiar").status_code == 404
    assert cliente.get("/api/treinos/99/para-montar").status_code == 404


def test_aluno_sem_treino_tem_lista_vazia(cliente):
    assert cliente.get("/api/alunos/2/treinos-para-copiar").get_json() == {"treinos": []}


# ------------------------------------------------------------------ as telas (o HTML tem tudo que o JavaScript procura)
PASTA_ESTATICA = Path(__file__).resolve().parent.parent / "app" / "static"
# ids que o próprio JavaScript cria na hora (não estão na página recém-aberta)
IDS_CRIADOS_PELO_JS = {"titulo-exercicios"}


def _ids_que_o_js_procura(arquivo: str) -> set[str]:
    codigo = (PASTA_ESTATICA / arquivo).read_text(encoding="utf-8")
    return set(re.findall(r'(?:pegar|getElementById)\("([^"]+)"\)', codigo)) - IDS_CRIADOS_PELO_JS


@pytest.mark.parametrize("arquivo", ["montar.js", "importar_treino.js"])
def test_a_tela_de_montar_tem_todos_os_ids_que_o_javascript_procura(cliente, arquivo):
    html = cliente.get("/alunos/1/montar").get_data(as_text=True)

    ids = _ids_que_o_js_procura(arquivo)
    assert ids, "o teste não achou nenhum id: o jeito de procurar mudou?"
    faltando = {i for i in ids if f'id="{i}"' not in html}
    assert faltando == set(), f"{arquivo} procura ids que a tela não tem: {sorted(faltando)}"


def test_a_tela_de_montar_tem_os_botoes_novos_e_carrega_o_javascript(cliente):
    html = cliente.get("/alunos/1/montar").get_data(as_text=True)

    assert "Importar treino" in html
    assert "Salvar como treino padrão" in html
    assert 'src="/static/montar.js"' in html
    assert "style=" not in html  # a política de segurança não aceita estilo dentro da página


def test_a_ficha_do_aluno_tem_o_botao_de_treino_padrao_em_cada_treino(cliente, caminho):
    _treino_do_aluno(caminho, nome='TREINO "ESPECIAL" <b>')
    _treino_do_aluno(caminho, nome="OUTRO TREINO")

    html = cliente.get("/alunos/1").get_data(as_text=True)

    assert html.count('class="botao-link botao-padrao"') == 2
    assert html.count('class="campo-padrao"') == 2
    assert 'src="/static/padrao_ficha.js"' in html
    assert "<b>" not in html  # o nome do treino é escapado
    assert "style=" not in html


def test_os_arquivos_novos_do_navegador_sao_servidos(cliente):
    for arquivo in ("importar_treino.js", "padrao_ficha.js", "dom.js", "api.js", "treino_modelo.js"):
        resposta = cliente.get(f"/static/{arquivo}")
        assert resposta.status_code == 200, arquivo
