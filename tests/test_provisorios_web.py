"""Testes da tela e da API de aluno provisório (app/web.py)."""

import re

import pytest

from app import acesso
from app.db import conectar, criar_tabelas
from app.web import criar_app

CPF_A = "11144477735"  # CPFs de exemplo válidos (de documentação)
CPF_B = "52998224725"


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "prov.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.execute("INSERT INTO grupo_muscular (nome, ordem) VALUES ('Peito', 1)")
    conn.execute("INSERT INTO exercicio (nome, origem) VALUES ('Supino', 'app')")
    conn.execute(
        "INSERT INTO aluno (nome, cpf, situacao, data4u_id) VALUES ('MARIA DA SILVA (FICTICIA)', ?, 'D', 4412)", (CPF_B,)
    )
    conn.commit()
    conn.close()
    return caminho


@pytest.fixture
def cliente(caminho):
    app = criar_app(caminho)
    navegador = app.test_client()
    conn = conectar(caminho)
    codigo = acesso.gerar_codigo(conn, "Computador de teste").codigo
    token = acesso.autorizar(conn, codigo).token
    conn.close()
    navegador.set_cookie(acesso.NOME_DO_COOKIE, token)
    return navegador


def _contar(caminho):
    conn = conectar(caminho)
    try:
        return conn.execute("SELECT COUNT(*) FROM aluno").fetchone()[0]
    finally:
        conn.close()


def _linha(caminho, aluno_id):
    conn = conectar(caminho)
    try:
        return conn.execute("SELECT * FROM aluno WHERE id = ?", (aluno_id,)).fetchone()
    finally:
        conn.close()


PEDIDO = {"nome": "Lucas Andrade", "cpf": "111.444.777-35", "whatsapp": "(27) 98888-7766"}


# ------------------------------------------------------------------ a tela


def test_tela_tem_os_tres_campos_o_botao_e_o_script(cliente):
    resposta = cliente.get("/alunos/novo")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    for campo in ('id="nome"', 'id="cpf"', 'id="whatsapp"'):
        assert campo in html
    assert "Salvar e montar treino" in html
    assert "Cancelar" in html
    assert 'src="/static/novo_aluno.js"' in html
    assert 'class="topo-nota">Computador de teste<' in html  # tem o topo com o nome do computador


def test_tela_nao_tem_script_estilo_embutido_nem_recurso_externo(cliente):
    html = cliente.get("/alunos/novo").get_data(as_text=True)

    assert "<script>" not in html and "style=" not in html and "onclick" not in html.lower()
    assert not re.search(r'(src|href)="https?://', html)


def test_tela_explica_que_o_whatsapp_pode_ficar_em_branco_e_o_que_acontece_depois(cliente):
    html = cliente.get("/alunos/novo").get_data(as_text=True)

    assert "pode deixar em branco" in html
    assert "O que acontece depois" in html and "pelo CPF" in html


def test_a_tela_nova_nao_atrapalha_a_ficha_de_aluno(cliente):
    assert cliente.get("/alunos/1").status_code == 200
    assert cliente.get("/alunos/novo").status_code == 200
    assert cliente.get("/alunos/999").status_code == 404


def test_busca_de_alunos_tem_o_cartao_de_aluno_novo(cliente):
    html = cliente.get("/alunos").get_data(as_text=True)

    assert "Aluno novo?" in html
    assert 'href="/alunos/novo"' in html
    assert "Cadastrar aluno provisório" in html


def test_sem_autorizacao_a_tela_e_a_api_ficam_fechadas(caminho):
    anonimo = criar_app(caminho).test_client()

    assert anonimo.get("/alunos/novo").status_code == 302
    resposta = anonimo.post("/api/alunos", json=PEDIDO)
    assert resposta.status_code == 401
    assert _contar(caminho) == 1


# ------------------------------------------------------------------ cadastrar


def test_cadastro_devolve_201_e_o_aluno_abre_na_ficha_e_na_montagem(cliente, caminho):
    resposta = cliente.post("/api/alunos", json=PEDIDO)

    assert resposta.status_code == 201
    aluno_id = resposta.get_json()["id"]
    linha = _linha(caminho, aluno_id)
    assert (linha["nome"], linha["cpf"], linha["whatsapp"], linha["provisorio"]) == (
        "Lucas Andrade",
        CPF_A,
        "27988887766",
        1,
    )
    ficha = cliente.get(f"/alunos/{aluno_id}").get_data(as_text=True)
    assert "Lucas Andrade" in ficha and "Provisório" in ficha and "111.444.777-35" in ficha
    montar = cliente.get(f"/alunos/{aluno_id}/montar")
    assert montar.status_code == 200 and "Lucas Andrade" in montar.get_data(as_text=True)


def test_o_provisorio_aparece_na_busca_por_nome_e_por_cpf_com_a_etiqueta(cliente):
    aluno_id = cliente.post("/api/alunos", json=PEDIDO).get_json()["id"]

    por_nome = cliente.get("/api/alunos?q=lucas").get_json()
    por_cpf = cliente.get("/api/alunos?q=11144477735").get_json()

    for resultado in (por_nome, por_cpf):
        [achado] = resultado["alunos"]
        assert (achado["id"], achado["provisorio"], achado["matricula"]) == (aluno_id, True, None)


def test_cadastro_sem_whatsapp(cliente, caminho):
    aluno_id = cliente.post("/api/alunos", json={"nome": "Lucas", "cpf": CPF_A, "whatsapp": ""}).get_json()["id"]

    assert _linha(caminho, aluno_id)["whatsapp"] is None


def test_campos_invalidos_devolvem_400_com_a_mensagem_de_cada_campo_e_nao_gravam(cliente, caminho):
    resposta = cliente.post("/api/alunos", json={"nome": " ", "cpf": "111.444.777-36", "whatsapp": "123"})

    assert resposta.status_code == 400
    erros = resposta.get_json()["erros"]
    assert set(erros) == {"nome", "cpf", "whatsapp"}
    assert "não é válido" in erros["cpf"]
    assert _contar(caminho) == 1


def test_cpf_que_ja_existe_devolve_409_com_quem_e(cliente, caminho):
    resposta = cliente.post("/api/alunos", json={"nome": "Maria Silva", "cpf": CPF_B})

    assert resposta.status_code == 409
    dados = resposta.get_json()
    assert dados["erro"] == "Já existe um aluno com este CPF."
    assert dados["existentes"] == [
        {"id": 1, "nome": "MARIA DA SILVA (FICTICIA)", "provisorio": False, "situacao_nome": "Desistente"}
    ]
    assert _contar(caminho) == 1


def test_cadastrar_duas_vezes_o_mesmo_aluno_cria_so_um(cliente, caminho):
    primeiro = cliente.post("/api/alunos", json=PEDIDO)
    segundo = cliente.post("/api/alunos", json=PEDIDO)

    assert (primeiro.status_code, segundo.status_code) == (201, 409)
    assert segundo.get_json()["existentes"][0]["id"] == primeiro.get_json()["id"]
    assert segundo.get_json()["existentes"][0]["provisorio"] is True
    assert _contar(caminho) == 2


def test_cadastro_exige_json(cliente, caminho):
    assert cliente.post("/api/alunos", data="nome=Lucas&cpf=" + CPF_A).status_code == 415
    assert _contar(caminho) == 1


@pytest.mark.parametrize("corpo", ["[]", '"texto"', "5", "null"])
def test_corpo_que_nao_e_objeto_devolve_400(cliente, corpo):
    # Texto cru de propósito: json=None não manda corpo nenhum (e aí o erro seria 415).
    resposta = cliente.post("/api/alunos", data=corpo, content_type="application/json")

    assert resposta.status_code == 400


def test_json_quebrado_devolve_400(cliente):
    resposta = cliente.post("/api/alunos", data="{nome:", content_type="application/json")

    assert resposta.status_code == 400


@pytest.mark.parametrize(
    "pedido",
    [
        {"nome": "x" * 5000, "cpf": CPF_A},
        {"nome": "Ana", "cpf": "1" * 5000},
        {"nome": "Ana", "cpf": CPF_A, "whatsapp": "9" * 5000},
        {"nome": ["Ana"], "cpf": {"a": 1}, "whatsapp": [1]},
        {"nome": None, "cpf": None, "whatsapp": None},
        {"nome": "Ana\x00Paula", "cpf": CPF_A},
        {"nome": "Ana", "cpf": "１１１４４４７７７３５"},
    ],
)
def test_pedido_malformado_nunca_vira_erro_500(cliente, caminho, pedido):
    resposta = cliente.post("/api/alunos", json=pedido)

    assert resposta.status_code in (400, 413)
    assert resposta.is_json
    assert _contar(caminho) == 1


def test_resposta_do_cadastro_nao_fica_em_cache(cliente):
    assert cliente.post("/api/alunos", json=PEDIDO).headers["Cache-Control"] == "no-store"


def test_cadastro_com_origem_de_outro_site_e_recusado(cliente, caminho):
    resposta = cliente.post("/api/alunos", json=PEDIDO, headers={"Origin": "https://site-malicioso.example"})

    assert resposta.status_code == 403
    assert _contar(caminho) == 1


def test_nome_com_html_e_guardado_como_texto_e_escapado_na_ficha(cliente):
    nome = "<script>alert(1)</script> & Cia"
    aluno_id = cliente.post("/api/alunos", json={"nome": nome, "cpf": CPF_A}).get_json()["id"]

    html = cliente.get(f"/alunos/{aluno_id}").get_data(as_text=True)

    assert nome not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; Cia" in html


def test_o_script_da_tela_nao_usa_funcoes_que_interpretam_html():
    from pathlib import Path

    pasta = Path(__file__).resolve().parent.parent / "app" / "static"
    for arquivo in ("novo_aluno.js", "novo_aluno_modelo.js"):
        texto = (pasta / arquivo).read_text(encoding="utf-8")
        assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(|new Function", texto)
