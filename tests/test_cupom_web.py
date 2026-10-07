"""Tela de impressão do cupom (app/web.py + templates/imprimir.html). Dados inventados."""

import re
from pathlib import Path

import pytest

from app import acesso, treinos
from app.db import conectar, criar_tabelas
from app.web import criar_app

PASTA_ESTATICA = Path(__file__).resolve().parent.parent / "app" / "static"


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "cupom.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.execute("INSERT INTO aluno (nome, cpf) VALUES ('MARIANA COSTA', '52998224725')")
    conn.execute("INSERT INTO aluno (nome, cpf) VALUES ('<b>ALUNO NEGRITO</b>', '11144477735')")
    for nome in ("SUPINO RETO COM BARRA", "CRUCIFIXO COM HALTERES", "TRICEPS <i>TESTA</i>"):
        conn.execute("INSERT INTO exercicio (nome, origem) VALUES (?, 'app')", (nome,))
    conn.commit()
    itens = [
        {"exercicio_id": 1, "series": "4", "repeticoes": "12", "carga": "30 KG", "bloco": 1},
        {"exercicio_id": 2, "series": "4", "repeticoes": "12", "carga": "10 KG", "bloco": 1},
        {"exercicio_id": 3, "series": "3", "repeticoes": "12", "carga": None, "bloco": None},
    ]
    treinos.salvar_treino(conn, 1, {"nome_treino": "TREINO ABC", "montado_por": "Ana", "fichas": [{"nome": "TREINO A", "itens": itens}]})
    treinos.salvar_treino(conn, 2, {"nome_treino": "<script>x</script>", "montado_por": "Ana", "fichas": [{"nome": "<u>F</u>", "itens": itens}]})
    conn.close()
    return caminho


def _autorizar(navegador, caminho):
    conn = conectar(caminho)
    codigo = acesso.gerar_codigo(conn, "Computador de teste").codigo
    token = acesso.autorizar(conn, codigo).token
    conn.close()
    navegador.set_cookie(acesso.NOME_DO_COOKIE, token)


@pytest.fixture
def cliente(caminho):
    navegador = criar_app(caminho).test_client()
    _autorizar(navegador, caminho)
    return navegador


def _pagina(cliente, treino_id=1):
    resposta = cliente.get(f"/treinos/{treino_id}/imprimir")
    assert resposta.status_code == 200
    return resposta.get_data(as_text=True)


def test_mostra_o_cupom_do_desenho(cliente):
    html = _pagina(cliente)

    # (as letras viram maiúsculas na tela e no papel pelo estilo; no HTML ficam como foram digitadas)
    for texto in ("Academia Glória Fit", "ALUNO: MARIANA COSTA", "TREINO: TREINO ABC", "PROF.: Ana", "TREINO A"):
        assert texto in html
    assert "SUPINO RETO COM BARRA" in html
    assert "BI-SET: FAÇA A1 E A2 SEGUIDOS" in html
    assert "4 X 12" in html and "30 KG" in html
    assert 'id="botao-imprimir"' in html
    assert "imprimir.css" in html and "imprimir.js" in html


def test_tem_o_botao_voltar_para_a_ficha_do_aluno_certo(cliente):
    assert 'class="botao-link botao-link-grande" href="/alunos/1"' in _pagina(cliente, 1)
    assert 'class="botao-link botao-link-grande" href="/alunos/2"' in _pagina(cliente, 2)


def test_nao_fala_do_app_do_aluno_enquanto_nao_houver_endereco(cliente):
    assert "ENTRE NO APP" not in _pagina(cliente)


def test_com_endereco_configurado_o_cupom_termina_com_o_aviso(caminho, monkeypatch):
    monkeypatch.setenv("GLORIAFIT_ENDERECO_DO_APP", "treino.exemplo.com.br")
    navegador = criar_app(caminho).test_client()
    _autorizar(navegador, caminho)

    html = _pagina(navegador)

    assert "ENTRE NO APP COM O SEU CPF:" in html
    assert "treino.exemplo.com.br" in html


def test_texto_com_html_aparece_como_texto(cliente):
    html = _pagina(cliente, 2)

    assert "<b>ALUNO NEGRITO</b>" not in html and "&lt;b&gt;ALUNO NEGRITO&lt;/b&gt;" in html
    assert "<script>x</script>" not in html
    assert "<u>F</u>" not in html and "&lt;u&gt;F&lt;/u&gt;" in html
    assert "<i>TESTA</i>" not in html


def test_treino_que_nao_existe_e_404(cliente):
    assert cliente.get("/treinos/999/imprimir").status_code == 404


def test_numero_que_nao_e_inteiro_e_404(cliente):
    assert cliente.get("/treinos/abc/imprimir").status_code == 404


def test_sem_autorizacao_manda_para_autorizar_e_nao_mostra_nada(caminho):
    anonimo = criar_app(caminho).test_client()

    resposta = anonimo.get("/treinos/1/imprimir")

    assert resposta.status_code == 302 and "/autorizar" in resposta.headers["Location"]
    assert b"MARIANA" not in resposta.data


def test_a_pagina_nao_fica_em_cache(cliente):
    assert cliente.get("/treinos/1/imprimir").headers["Cache-Control"] == "no-store"


def test_so_aceita_get(cliente):
    assert cliente.post("/treinos/1/imprimir", json={}).status_code == 405


def test_a_ficha_do_aluno_tem_o_link_para_imprimir_cada_treino(cliente):
    html = cliente.get("/alunos/1").get_data(as_text=True)

    assert 'href="/treinos/1/imprimir"' in html
    assert 'href="/treinos/2/imprimir"' not in html  # o treino 2 é de outro aluno
    assert 'href="/treinos/2/imprimir"' in cliente.get("/alunos/2").get_data(as_text=True)


def test_a_tela_de_montar_tem_o_link_de_imprimir_escondido_ate_salvar(cliente):
    html = cliente.get("/alunos/1/montar").get_data(as_text=True)

    assert re.search(r'<a id="imprimir-treino"[^>]*\bhidden\b', html)


def test_a_regra_de_pagina_so_vale_para_a_tela_de_impressao():
    # @page (margem zero) afeta TODA impressão da página que carrega o arquivo: não pode vazar para o estilo geral.
    assert "@page" in (PASTA_ESTATICA / "imprimir.css").read_text(encoding="utf-8")
    assert "@page" not in (PASTA_ESTATICA / "estilo.css").read_text(encoding="utf-8")


def test_o_cupom_so_usa_preto_no_papel():
    # Impressora térmica é preta e branca: cinza some ou vira pontilhado ilegível.
    css = (PASTA_ESTATICA / "imprimir.css").read_text(encoding="utf-8")
    cupom = css[css.index("/* ------------------------------------------------------------ o cupom */") :]

    cores = set(re.findall(r"(?<![\w-])color:\s*([^;]+);", cupom))

    assert cores == {"#000"}
