"""Ícone do app: guardar na tela inicial do celular (manifest) e ícone da aba do navegador."""

import json
import re
import struct
from pathlib import Path

import pytest

from app.db import conectar, criar_tabelas
from app.web import criar_app

PASTA_DO_APP = Path(__file__).resolve().parent.parent / "app"
TELAS_DO_ALUNO = ("aluno_entrar.html", "aluno_inicio.html", "aluno_perfil.html")


@pytest.fixture
def cliente(tmp_path):
    """Qualquer celular: sem login de aluno e sem computador autorizado."""
    caminho = tmp_path / "icone.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.close()
    return criar_app(caminho).test_client()


@pytest.fixture
def manifesto(cliente):
    return json.loads(cliente.get("/static/aluno.webmanifest").get_data(as_text=True))


def _png(corpo):
    """(largura, altura, tem_transparencia) lidos do cabeçalho do PNG, sem biblioteca de imagem."""
    assert corpo[:8] == b"\x89PNG\r\n\x1a\n", "não é um PNG"
    largura, altura = struct.unpack(">II", corpo[16:24])
    tipo_de_cor = corpo[25]  # 2 = RGB (opaco), 6 = RGBA, 3 = paleta
    return largura, altura, tipo_de_cor in (4, 6)


def _lado(tamanho):
    return int(tamanho.split("x")[0])


# ------------------------------------------------------------------ o "cartão de visita" do app


def test_o_manifest_abre_sem_nenhum_login_e_tem_o_tipo_certo(cliente):
    resposta = cliente.get("/static/aluno.webmanifest")

    assert resposta.status_code == 200
    assert resposta.mimetype == "application/manifest+json"


def test_o_manifest_tem_o_que_o_chrome_exige_para_instalar(manifesto):
    assert manifesto["name"] and manifesto["short_name"]
    assert manifesto["start_url"] == "/aluno"
    assert manifesto["display"] in ("standalone", "fullscreen", "minimal-ui")
    icones = {(icone["sizes"], icone["purpose"]) for icone in manifesto["icons"]}
    assert ("192x192", "any") in icones
    assert ("512x512", "any") in icones
    assert ("512x512", "maskable") in icones  # o Android corta este em círculo/gota sem sobrar borda branca


def test_o_endereco_inicial_do_app_esta_dentro_do_escopo_e_existe(cliente, manifesto):
    assert manifesto["start_url"].startswith(manifesto["scope"])

    # Sem login, a página inicial manda para a tela de entrar (não pode dar 404 nem abrir sem senha).
    resposta = cliente.get(manifesto["start_url"])
    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/aluno/entrar")


def test_cada_icone_do_manifest_existe_com_o_tamanho_que_diz_ter(cliente, manifesto):
    for icone in manifesto["icons"]:
        resposta = cliente.get(icone["src"])
        assert resposta.status_code == 200, icone["src"]
        assert resposta.mimetype == icone["type"] == "image/png"
        largura, altura, _ = _png(resposta.get_data())
        assert (largura, altura) == (_lado(icone["sizes"]),) * 2, icone["src"]


def test_o_icone_maskable_nao_tem_transparencia(cliente, manifesto):
    # Transparência vira fundo branco ou preto aleatório quando o Android corta o ícone.
    for icone in manifesto["icons"]:
        if icone["purpose"] == "maskable":
            assert _png(cliente.get(icone["src"]).get_data())[2] is False


def test_o_icone_do_iphone_tem_180_px_e_sem_transparencia(cliente):
    resposta = cliente.get("/static/marca/apple-touch-icon.png")

    assert resposta.status_code == 200
    assert _png(resposta.get_data()) == (180, 180, False)


# ------------------------------------------------------------------ o que cada tela liga no cabeçalho


def _cabecalho(cliente, url):
    resposta = cliente.get(url)
    assert resposta.status_code == 200
    html = resposta.get_data(as_text=True)
    return html[: html.index("</head>")]


def test_as_telas_do_aluno_ligam_manifest_icone_do_iphone_e_cor_da_barra(cliente, manifesto):
    # A tela inicial do aluno (/aluno) exige login; ela usa o mesmo modelo de partes, conferido mais abaixo.
    cabecalho = _cabecalho(cliente, "/aluno/entrar")

    assert '<link rel="manifest" href="/static/aluno.webmanifest">' in cabecalho
    assert 'rel="apple-touch-icon" href="/static/marca/apple-touch-icon.png"' in cabecalho
    assert f'<meta name="theme-color" content="{manifesto["theme_color"]}">' in cabecalho
    assert '<meta name="apple-mobile-web-app-capable" content="yes">' in cabecalho
    assert '<meta name="mobile-web-app-capable" content="yes">' in cabecalho


def test_toda_tela_tem_icone_na_aba_e_todos_os_icones_ligados_existem(cliente):
    # /autorizar é uma tela do professor que abre sem login.
    for url in ("/aluno/entrar", "/autorizar"):
        cabecalho = _cabecalho(cliente, url)
        icones = re.findall(r'<link rel="icon"[^>]*href="([^"]+)"', cabecalho)
        assert icones, f"{url} está sem ícone na aba"
        for href in icones:
            assert cliente.get(href).status_code == 200, href


def test_as_telas_do_professor_nao_oferecem_instalar_o_app(cliente):
    cabecalho = _cabecalho(cliente, "/autorizar")

    assert 'rel="manifest"' not in cabecalho
    assert "apple-touch-icon" not in cabecalho


def test_o_modelo_de_cada_tela_inclui_os_icones_certos():
    """Rede de segurança: tela nova sem os ícones (ou tela do professor com o app do aluno) é pega aqui."""
    telas = [t for t in sorted((PASTA_DO_APP / "templates").glob("*.html")) if not t.name.startswith("_")]
    assert len(telas) >= 11

    for tela in telas:
        texto = tela.read_text(encoding="utf-8")
        assert '{% include "_icones.html" %}' in texto, f"{tela.name} está sem os ícones da aba"
        assert ('{% include "_app_aluno.html" %}' in texto) == (tela.name in TELAS_DO_ALUNO), tela.name


def test_a_cor_da_barra_do_celular_e_a_mesma_do_topo_da_tela_do_aluno(manifesto):
    css = (PASTA_DO_APP / "static" / "estilo.css").read_text(encoding="utf-8")
    bloco_palco = css[css.index(":root.tema-palco {") :]
    topo = re.search(r"--topo-fundo:\s*(#[0-9a-fA-F]{6})", bloco_palco).group(1)

    assert manifesto["theme_color"].lower() == topo.lower()
