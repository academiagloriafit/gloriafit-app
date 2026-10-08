"""Concluído / Reativar / início, fim e meta, pela web (app/web.py + telas). Dados inventados."""

import re
from pathlib import Path

import pytest

from app import acesso, ciclo
from app.datas import hoje
from app.db import conectar, criar_tabelas
from app.treinos import salvar_treino
from app.web import criar_app

PASTA_ESTATICA = Path(__file__).resolve().parent.parent / "app" / "static"


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "ciclo.db"
    c = conectar(caminho)
    criar_tabelas(c)
    c.execute("INSERT INTO aluno (id, nome) VALUES (1, 'ANA FICTICIA'), (2, 'BRUNO FICTICIO')")
    c.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO RETO', 'app')")
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


def _pedido(nome="TREINO ABC", **extras):
    itens = [{"exercicio_id": 1, "series": "3", "repeticoes": "12"}]
    return {"nome_treino": nome, "montado_por": "Ana", "fichas": [{"nome": "A", "itens": itens}], **extras}


def _salvar(caminho, aluno=1, **pedido):
    c = conectar(caminho)
    treino = salvar_treino(c, aluno, _pedido(**pedido))
    c.close()
    return treino


def _banco(caminho, sql, *args):
    c = conectar(caminho)
    try:
        return [tuple(linha) for linha in c.execute(sql, args)]
    finally:
        c.close()


# ------------------------------------------------------------------ salvar pela API


def test_salvar_com_ciclo_pela_api(cliente, caminho):
    resposta = cliente.post("/api/alunos/1/treinos", json=_pedido(inicio="2026-10-10", fim="2026-12-31", sessoes_por_ficha=15))

    assert resposta.status_code == 201
    assert resposta.get_json() == {"id": 1, "concluido_anterior": None}
    assert _banco(caminho, "SELECT inicio, fim, sessoes_por_ficha, ativo FROM treino") == [("2026-10-10", "2026-12-31", 15, 1)]


def test_salvar_outro_treino_avisa_qual_foi_concluido(cliente, caminho):
    cliente.post("/api/alunos/1/treinos", json=_pedido("PRIMEIRO"))

    resposta = cliente.post("/api/alunos/1/treinos", json=_pedido("SEGUNDO"))

    assert resposta.get_json() == {"id": 2, "concluido_anterior": "PRIMEIRO"}
    assert _banco(caminho, "SELECT nome, ativo FROM treino ORDER BY id") == [("PRIMEIRO", 0), ("SEGUNDO", 1)]


def test_salvar_com_data_ruim_devolve_400_e_nao_conclui_o_ativo(cliente, caminho):
    cliente.post("/api/alunos/1/treinos", json=_pedido("PRIMEIRO"))

    resposta = cliente.post("/api/alunos/1/treinos", json=_pedido("SEGUNDO", fim="2020-01-01", inicio="2026-10-10"))

    assert resposta.status_code == 400
    assert any("antes da data do início" in e for e in resposta.get_json()["erros"])
    assert _banco(caminho, "SELECT nome, ativo FROM treino") == [("PRIMEIRO", 1)]


# ------------------------------------------------------------------ concluir e reativar


def test_concluir_pela_api(cliente, caminho):
    treino = _salvar(caminho)

    resposta = cliente.post(f"/api/treinos/{treino}/concluir", json={})

    assert resposta.status_code == 200 and resposta.get_json() == {"ok": True}
    assert _banco(caminho, "SELECT ativo, concluido_em IS NOT NULL FROM treino") == [(0, 1)]


def test_concluir_de_novo_devolve_409(cliente, caminho):
    treino = _salvar(caminho)
    cliente.post(f"/api/treinos/{treino}/concluir", json={})

    resposta = cliente.post(f"/api/treinos/{treino}/concluir", json={})

    assert resposta.status_code == 409
    assert "já está concluído" in resposta.get_json()["erro"]


def test_concluir_treino_que_nao_existe_devolve_404(cliente):
    assert cliente.post("/api/treinos/999/concluir", json={}).status_code == 404
    assert cliente.post("/api/treinos/999/reativar", json={}).status_code == 404


def test_reativar_pela_api(cliente, caminho):
    treino = _salvar(caminho)
    cliente.post(f"/api/treinos/{treino}/concluir", json={})

    resposta = cliente.post(f"/api/treinos/{treino}/reativar", json={})

    assert resposta.status_code == 200
    assert _banco(caminho, "SELECT ativo, concluido_em FROM treino") == [(1, None)]


def test_reativar_com_outro_ativo_devolve_409_com_o_nome(cliente, caminho):
    antigo = _salvar(caminho, nome="ANTIGO")
    _salvar(caminho, nome="ATUAL")

    resposta = cliente.post(f"/api/treinos/{antigo}/reativar", json={})

    assert resposta.status_code == 409
    assert '"ATUAL"' in resposta.get_json()["erro"]


@pytest.mark.parametrize("acao", ["concluir", "reativar"])
def test_as_rotas_exigem_json_e_computador_autorizado_e_origem_certa(cliente, anonimo, caminho, acao):
    treino = _salvar(caminho)
    url = f"/api/treinos/{treino}/{acao}"

    assert anonimo.post(url, json={}).status_code == 401
    assert cliente.post(url, data="x=1", content_type="application/x-www-form-urlencoded").status_code == 415
    assert cliente.post(url, json={}, headers={"Origin": "https://outro-site.example"}).status_code == 403
    assert cliente.get(url).status_code == 405
    assert _banco(caminho, "SELECT ativo FROM treino") == [(1,)]  # nenhuma das tentativas mexeu no treino


def test_as_rotas_estao_protegidas_por_padrao(app):
    from app.web import ENDPOINTS_PUBLICOS

    assert "api_concluir_treino" not in ENDPOINTS_PUBLICOS
    assert "api_reativar_treino" not in ENDPOINTS_PUBLICOS


# ------------------------------------------------------------------ telas


def test_tela_de_montar_tem_os_campos_do_ciclo_e_o_inicio_vem_de_hoje(cliente):
    html = cliente.get("/alunos/1/montar").get_data(as_text=True)

    assert re.search(rf'<input id="data-inicio" type="date" value="{hoje()}"', html)
    assert 'id="data-fim"' in html and 'id="sessoes-por-ficha"' in html
    assert "Treinos por ficha" in html
    assert 'id="aviso-treino-ativo"' not in html  # aluno sem treino ativo: sem aviso


def test_tela_de_montar_avisa_que_o_ativo_sera_concluido(cliente, caminho):
    _salvar(caminho, nome="TREINO <b>ATUAL</b>")

    html = cliente.get("/alunos/1/montar").get_data(as_text=True)

    assert 'id="aviso-treino-ativo"' in html
    assert "&lt;b&gt;ATUAL&lt;/b&gt;" in html and "<b>ATUAL</b>" not in html  # nome escapado
    assert "será <strong>concluído</strong>" in html
    # outro aluno não vê o aviso do treino alheio
    assert 'id="aviso-treino-ativo"' not in cliente.get("/alunos/2/montar").get_data(as_text=True)


def test_ficha_mostra_botao_concluido_so_no_treino_ativo(cliente, caminho):
    _salvar(caminho, nome="ANTIGO")
    _salvar(caminho, nome="ATUAL")

    html = cliente.get("/alunos/1").get_data(as_text=True)

    assert html.count('class="botao-link botao-concluir"') == 1
    assert 'class="botao-link botao-reativar"' not in html  # há um ativo: ninguém pode ser reativado
    ativo = html[html.index("linha-treino treino-ativo") :]
    assert ativo.index("ATUAL") < ativo.index("botao-concluir")


def test_ficha_oferece_reativar_quando_nao_ha_ativo(cliente, caminho):
    treino = _salvar(caminho)
    cliente.post(f"/api/treinos/{treino}/concluir", json={})

    html = cliente.get("/alunos/1").get_data(as_text=True)

    assert html.count('class="botao-link botao-reativar"') == 1
    assert "botao-concluir" not in html
    assert "selo-treino-inativo" in html and "Concluído em" in html


def test_ficha_mostra_inicio_fim_e_sessoes(cliente, caminho):
    _salvar(caminho, inicio="2026-10-01", fim="2026-12-31", sessoes_por_ficha=15)

    html = cliente.get("/alunos/1").get_data(as_text=True)

    assert 'class="treino-inicio">01/10/2026<' in html
    assert 'class="treino-fim">31/12/2026<' in html
    assert 'class="treino-sessoes">0 / 15<' in html
    assert "Meta: 15 treinos por ficha" in html
    assert "0 / 15 treinos" in html  # dentro de cada ficha
    assert "Hora de trocar" not in html


def test_ficha_sem_fim_mostra_traco_e_nunca_a_data_7777(cliente, caminho):
    _salvar(caminho)

    html = cliente.get("/alunos/1").get_data(as_text=True)

    assert 'class="treino-fim">–<' in html
    assert "7777" not in html


def test_ficha_mostra_o_aviso_de_trocar_o_treino(cliente, caminho):
    treino = _salvar(caminho, inicio="2026-01-01", sessoes_por_ficha=1)
    c = conectar(caminho)
    ciclo.registrar_sessao(c, treino, 1)
    c.close()

    html = cliente.get("/alunos/1").get_data(as_text=True)

    assert 'role="alert"' in html and "Hora de trocar o treino" in html
    assert "selo-treino-trocar" in html


def test_ficha_do_outro_aluno_nao_herda_o_aviso(cliente, caminho):
    _salvar(caminho, aluno=1, inicio="2020-01-01", fim="2020-02-01")
    _salvar(caminho, aluno=2, nome="TREINO NOVO")

    assert "Hora de trocar" in cliente.get("/alunos/1").get_data(as_text=True)
    assert "Hora de trocar" not in cliente.get("/alunos/2").get_data(as_text=True)


def test_nome_do_treino_com_html_continua_escapado_na_tabela_nova(cliente, caminho):
    _salvar(caminho, nome="<img src=x onerror=alert(1)>")

    html = cliente.get("/alunos/1").get_data(as_text=True)

    assert "<img src=x" not in html and "&lt;img src=x" in html


def test_a_ficha_carrega_o_javascript_do_concluido_e_o_montar_nao_tem_script_embutido(cliente):
    ficha = cliente.get("/alunos/1").get_data(as_text=True)
    montar = cliente.get("/alunos/1/montar").get_data(as_text=True)

    assert 'src="/static/ciclo_ficha.js"' in ficha
    for html in (ficha, montar):
        assert not re.search(r"<script(?![^>]*\bsrc=)", html)  # CSP: nada de script embutido
        assert " style=" not in html and "onclick=" not in html
    assert (PASTA_ESTATICA / "ciclo_ficha.js").is_file()
