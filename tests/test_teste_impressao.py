"""Folha de teste da impressora térmica (/teste-de-impressao). Sem aluno, sem treino, não grava nada."""

import re
import struct
from pathlib import Path

import pytest

from app import acesso
from app.db import conectar, criar_tabelas
from app.web import criar_app

PASTA_ESTATICA = Path(__file__).resolve().parent.parent / "app" / "static"

IMAGENS_DA_FOLHA = (
    "marca/logo-cupom.png",
    "teste_impressao/logo-384.png",
    "teste_impressao/logo-grosso.png",
    "teste_impressao/logo-vetor.svg",
    "teste_impressao/logo-invertido-redondo.png",
    "teste_impressao/logo-invertido-total.png",
    "teste_impressao/pontos-1x1.png",
)


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "teste_impressao.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.close()
    return caminho


@pytest.fixture
def cliente(caminho):
    navegador = criar_app(caminho).test_client()
    conn = conectar(caminho)
    codigo = acesso.gerar_codigo(conn, "Computador de teste").codigo
    token = acesso.autorizar(conn, codigo).token
    conn.close()
    navegador.set_cookie(acesso.NOME_DO_COOKIE, token)
    return navegador


def _pagina(cliente):
    resposta = cliente.get("/teste-de-impressao")
    assert resposta.status_code == 200
    return resposta.get_data(as_text=True)


def test_mostra_as_cinco_partes_do_teste(cliente):
    html = _pagina(cliente)

    for rotulo in (
        "1 REGUA (MM)",
        "2 BARRA PRETA CHEIA",
        "3 PONTOS",
        "4 SIMBOLO: A ANTIGO / B 384 PONTOS",
        "4 SIMBOLO: C GROSSO / D VETOR",
        "4 SIMBOLO INVERTIDO: REDONDO / TOTAL",
        "5 LETRAS",
        "FIM DO TESTE",
    ):
        assert rotulo in html
    assert 'id="botao-imprimir"' in html and "imprimir.js" in html


def test_a_regua_vai_de_0_a_80_mm_com_numero_de_10_em_10(cliente):
    html = _pagina(cliente)

    tracos = re.findall(r'<i class="traco (traco-1|traco-5|traco-10)" style="left: (\d+)mm">', html)
    assert [int(mm) for _, mm in tracos] == list(range(81))
    assert {mm for tipo, mm in tracos if tipo == "traco-10"} == {str(mm) for mm in range(0, 81, 10)}
    numeros = re.findall(r'<b class="numero" style="left: (\d+)mm">(\d+)</b>', html)
    assert numeros == [(str(mm), str(mm)) for mm in range(0, 81, 10)]


def test_as_cinco_amostras_de_letra(cliente):
    html = _pagina(cliente)

    amostras = re.findall(r'<p class="amostra amostra-([a-e])">', html)
    assert amostras == ["a", "b", "c", "d", "e"]


def test_todas_as_imagens_da_folha_existem(cliente):
    html = _pagina(cliente)

    for imagem in IMAGENS_DA_FOLHA:
        assert f"/static/{imagem}" in html
        arquivo = PASTA_ESTATICA / imagem
        assert arquivo.is_file() and arquivo.stat().st_size > 0, imagem
        assert cliente.get(f"/static/{imagem}").status_code == 200


def test_o_simbolo_vetorial_nao_tem_o_quadrado_de_fundo(cliente):
    """Regressão: a primeira vetorização saiu invertida (quadrado preto em volta do símbolo)."""
    svg = (PASTA_ESTATICA / "teste_impressao" / "logo-vetor.svg").read_text()

    primeiro_contorno = re.search(r' d="(M[^M]*)', svg).group(1)
    assert not primeiro_contorno.startswith("M0.0,384.0L0.0,0.0")  # canto do quadrado inteiro
    assert 'viewBox="0 0 768 768"' in svg and "fill-rule=\"evenodd\"" in svg


def _cabecalho_png(arquivo):
    """(largura, altura, bits por ponto) lidos do cabeçalho do PNG. Sem Pillow: a integração contínua não a instala."""
    dados = arquivo.read_bytes()[:33]
    assert dados[:8] == b"\x89PNG\r\n\x1a\n" and dados[12:16] == b"IHDR"
    largura, altura, bits = struct.unpack(">IIB", dados[16:25])
    return largura, altura, bits


@pytest.mark.parametrize("nome", ["logo-invertido-redondo.png", "logo-invertido-total.png"])
def test_os_simbolos_invertidos_tem_o_mesmo_tamanho_e_so_preto_e_branco(nome):
    atual = _cabecalho_png(PASTA_ESTATICA / "marca" / "logo-cupom.png")

    assert _cabecalho_png(PASTA_ESTATICA / "teste_impressao" / nome) == atual == (192, 192, 1)


def test_os_simbolos_invertidos_sao_mesmo_o_contrario_do_atual():
    """Total = o contrário de cada ponto. Redondo = o contrário só dentro do círculo; os cantos ficam papel branco."""
    pil = pytest.importorskip("PIL.Image")  # só local: a integração contínua não tem Pillow
    numpy = pytest.importorskip("numpy")

    def pretos(caminho):
        return numpy.array(pil.open(caminho).convert("L")) < 128

    atual = pretos(PASTA_ESTATICA / "marca" / "logo-cupom.png")
    total = pretos(PASTA_ESTATICA / "teste_impressao" / "logo-invertido-total.png")
    redondo = pretos(PASTA_ESTATICA / "teste_impressao" / "logo-invertido-redondo.png")

    linhas, colunas = numpy.mgrid[0:192, 0:192]
    distancia = numpy.hypot(linhas - 95.5, colunas - 95.5)

    assert (total == ~atual).all()
    assert (redondo[distancia <= 80] == ~atual[distancia <= 80]).all()  # bem dentro do círculo: o contrário do atual
    assert not redondo[distancia >= 96].any()  # cantos (fora do círculo): papel branco
    assert redondo.sum() < total.sum()  # o redondo tem menos preto que o quadrado


def test_a_folha_nao_depende_de_aluno_nem_de_treino(cliente):
    html = _pagina(cliente)

    assert "data-treino" not in html and "data-ficha" not in html  # imprimir.js só grava "treino feito" quando tem data-ficha
    assert "ALUNO:" not in html and "PROF.:" not in html


def test_abrir_a_folha_nao_grava_nada_no_banco(cliente, caminho):
    conn = conectar(caminho)
    tabelas = [linha[0] for linha in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    antes = {tabela: conn.execute(f'SELECT COUNT(*) FROM "{tabela}"').fetchone()[0] for tabela in tabelas}
    conn.close()

    for _ in range(3):
        _pagina(cliente)

    conn = conectar(caminho)
    depois = {tabela: conn.execute(f'SELECT COUNT(*) FROM "{tabela}"').fetchone()[0] for tabela in tabelas}
    conn.close()
    assert depois == antes


def test_sem_autorizacao_manda_para_autorizar(caminho):
    anonimo = criar_app(caminho).test_client()

    resposta = anonimo.get("/teste-de-impressao")

    assert resposta.status_code == 302 and "/autorizar" in resposta.headers["Location"]
    assert b"REGUA" not in resposta.data


def test_a_pagina_nao_fica_em_cache_e_so_aceita_get(cliente):
    assert cliente.get("/teste-de-impressao").headers["Cache-Control"] == "no-store"
    assert cliente.post("/teste-de-impressao", json={}).status_code == 405


def test_o_estilo_da_folha_cabe_no_papel_de_80_mm():
    css = (PASTA_ESTATICA / "teste_impressao.css").read_text()

    assert re.search(r"\.folha-teste\s*\{[^}]*width:\s*80mm", css)
    assert re.search(r"\.bloco-72\s*\{[^}]*72mm", css)
