"""Foto do aluno (app/fotos.py e as rotas): miniatura, envio do PC da recepção, prazo de 90 dias e quem pode ver. Dados inventados."""

import base64
import hashlib
import io
from datetime import datetime, timedelta, timezone

import pytest
from PIL import Image

from app import acesso, fotos
from app.db import conectar, criar_tabelas
from app.web import criar_app

AGORA = datetime(2026, 10, 29, 8, 15, tzinfo=timezone.utc)


def _jpeg(largura=300, altura=400, cor=(200, 120, 80), formato="JPEG") -> bytes:
    saida = io.BytesIO()
    Image.new("RGB", (largura, altura), cor).save(saida, formato)
    return saida.getvalue()


def _b64(dados: bytes) -> str:
    return base64.b64encode(dados).decode("ascii")


@pytest.fixture
def conn():
    c = conectar()
    criar_tabelas(c)
    c.execute("INSERT INTO aluno (id, nome, situacao, data4u_id) VALUES (1, 'ANA SOUZA', 'A', 501), (2, 'BRUNO LIMA', 'P', 502),"
              " (3, 'CARLA DIAS', 'D', 503), (4, 'DANI PROVISORIA', NULL, NULL)")
    c.execute("UPDATE aluno SET provisorio = 1 WHERE id = 4")
    c.commit()
    yield c
    c.close()


# ------------------------------------------------------------------ miniatura


def test_miniatura_e_um_jpeg_quadrado_pequeno():
    dados = fotos.miniatura(_jpeg(300, 400))
    with Image.open(io.BytesIO(dados)) as imagem:
        assert imagem.format == "JPEG" and imagem.size == (fotos.LADO, fotos.LADO)
    assert len(dados) < 20_000


def test_miniatura_aceita_png():
    with Image.open(io.BytesIO(fotos.miniatura(_jpeg(120, 90, formato="PNG")))) as imagem:
        assert imagem.size == (fotos.LADO, fotos.LADO)


@pytest.mark.parametrize("dados", [b"", b"nao e imagem", b"\xff\xd8\xff" + b"\x00" * 50, _jpeg(formato="GIF")])
def test_miniatura_recusa_o_que_nao_e_foto(dados):
    with pytest.raises(fotos.PacoteInvalido):
        fotos.miniatura(dados)


def test_miniatura_recusa_imagem_com_pixels_demais():
    with pytest.raises(fotos.PacoteInvalido):
        fotos.miniatura(_jpeg(8000, 6000, formato="PNG"))  # 48 milhões de pixels num arquivo pequeno


def test_miniatura_recusa_arquivo_grande_demais():
    with pytest.raises(fotos.PacoteInvalido):
        fotos.miniatura(b"\xff" * (fotos.TAMANHO_MAXIMO_DA_ORIGINAL + 1))


# ------------------------------------------------------------------ estado e importação


def test_estado_lista_so_quem_esta_em_uso_e_vem_do_data4u(conn):
    assert fotos.estado(conn)["alunos"] == [{"id": 501, "sha256": None}, {"id": 502, "sha256": None}]


def test_importar_grava_miniatura_e_o_resumo_da_original(conn):
    original = _jpeg()
    relatorio = fotos.importar(conn, {"fotos": [{"id": 501, "jpg": _b64(original)}], "presentes": [501]}, agora=AGORA)

    assert relatorio == {"gravadas": 1, "recusadas": 0, "sem_aluno": 0, "vistas": 1, "apagadas": 0}
    assert fotos.alunos_com_foto(conn) == {1}
    assert fotos.ler(conn, 1)[:3] == b"\xff\xd8\xff"
    assert fotos.estado(conn)["alunos"][0] == {"id": 501, "sha256": hashlib.sha256(original).hexdigest()}


def test_importar_conta_sem_aluno_e_recusadas_sem_derrubar_o_pacote(conn):
    pacote = {"fotos": [{"id": 999, "jpg": _b64(_jpeg())}, {"id": 502, "jpg": _b64(b"estragada")}, {"id": 501, "jpg": _b64(_jpeg())}]}
    relatorio = fotos.importar(conn, pacote, agora=AGORA)
    assert (relatorio["gravadas"], relatorio["recusadas"], relatorio["sem_aluno"]) == (1, 1, 1)
    assert fotos.alunos_com_foto(conn) == {1}


def test_importar_de_novo_troca_a_foto(conn):
    fotos.importar(conn, {"fotos": [{"id": 501, "jpg": _b64(_jpeg(cor=(10, 10, 10)))}]}, agora=AGORA)
    nova = _jpeg(cor=(250, 250, 250))
    fotos.importar(conn, {"fotos": [{"id": 501, "jpg": _b64(nova)}]}, agora=AGORA)
    assert conn.execute("SELECT COUNT(*), origem_sha256 FROM foto_aluno").fetchone()[:] == (1, hashlib.sha256(nova).hexdigest())


def test_foto_nao_confirmada_por_90_dias_e_apagada(conn):
    fotos.importar(conn, {"fotos": [{"id": 501, "jpg": _b64(_jpeg())}, {"id": 502, "jpg": _b64(_jpeg())}]}, agora=AGORA)

    # 89 dias depois só a Ana continua com foto no cache: a do Bruno ainda fica (não passou do prazo)
    depois = AGORA + timedelta(days=89)
    assert fotos.importar(conn, {"fotos": [], "presentes": [501]}, agora=depois)["apagadas"] == 0
    # 91 dias depois do último "visto" do Bruno: a foto dele some; a da Ana foi vista há 2 dias e fica
    relatorio = fotos.importar(conn, {"fotos": [], "presentes": [501]}, agora=AGORA + timedelta(days=91))
    assert relatorio["apagadas"] == 1
    assert fotos.alunos_com_foto(conn) == {1}


@pytest.mark.parametrize(
    "pacote",
    [
        None,
        [],
        {"fotos": "x"},
        {"fotos": [{"id": 501}]},
        {"fotos": [{"id": "501", "jpg": ""}]},
        {"fotos": [{"id": True, "jpg": ""}]},
        {"fotos": [{"id": 501, "jpg": "não é base64!"}]},
        {"fotos": [{"id": 501, "jpg": "", "rosto": "x"}]},
        {"fotos": [], "presentes": ["501"]},
        {"fotos": [{"id": 501, "jpg": ""}] * (fotos.FOTOS_POR_PACOTE + 1)},
    ],
)
def test_pacote_fora_do_formato_e_recusado_sem_gravar_nada(conn, pacote):
    with pytest.raises(fotos.PacoteInvalido):
        fotos.importar(conn, pacote, agora=AGORA)
    assert fotos.alunos_com_foto(conn) == frozenset()


# ------------------------------------------------------------------ rotas e telas


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "fotos.db"
    c = conectar(caminho)
    criar_tabelas(c)
    c.execute("INSERT INTO aluno (id, nome, situacao, data4u_id) VALUES (1, 'ANA SOUZA', 'A', 501), (2, 'BRUNO LIMA', 'A', 502)")
    c.commit()
    fotos.importar(c, {"fotos": [{"id": 501, "jpg": _b64(_jpeg())}]}, agora=datetime.now(timezone.utc))
    c.close()
    return caminho


def _autorizado(caminho):
    navegador = criar_app(caminho).test_client()
    c = conectar(caminho)
    navegador.set_cookie(acesso.NOME_DO_COOKIE, acesso.autorizar(c, acesso.gerar_codigo(c, "Teste").codigo).token)
    c.close()
    return navegador


def test_foto_so_abre_em_computador_autorizado(caminho):
    sem_cookie = criar_app(caminho).test_client()
    resposta = sem_cookie.get("/alunos/1/foto")
    assert resposta.status_code == 302 and "/autorizar" in resposta.headers["Location"]

    resposta = _autorizado(caminho).get("/alunos/1/foto")
    assert resposta.status_code == 200
    assert resposta.mimetype == "image/jpeg" and resposta.data[:3] == b"\xff\xd8\xff"
    assert resposta.headers["Cache-Control"] == "private, max-age=3600"
    assert resposta.headers["X-Content-Type-Options"] == "nosniff"


def test_aluno_sem_foto_da_404(caminho):
    assert _autorizado(caminho).get("/alunos/2/foto").status_code == 404


def test_api_de_fotos_exige_computador_autorizado(caminho):
    sem_cookie = criar_app(caminho).test_client()
    assert sem_cookie.post("/api/fotos/estado", json={}).status_code == 401
    assert sem_cookie.post("/api/fotos/importar", json={"fotos": []}).status_code == 401


def test_api_de_fotos_estado_e_importar(caminho):
    navegador = _autorizado(caminho)
    estado = navegador.post("/api/fotos/estado", json={}).get_json()
    assert [a["id"] for a in estado["alunos"]] == [501, 502] and estado["fotos_por_pacote"] == fotos.FOTOS_POR_PACOTE

    resposta = navegador.post("/api/fotos/importar", json={"fotos": [{"id": 502, "jpg": _b64(_jpeg())}], "presentes": [501, 502]})
    assert resposta.status_code == 200 and resposta.get_json()["gravadas"] == 1
    assert navegador.post("/api/fotos/importar", json={"fotos": "x"}).status_code == 400


def test_telas_mostram_a_foto_ou_as_iniciais(caminho):
    navegador = _autorizado(caminho)
    ficha_ana = navegador.get("/alunos/1").get_data(as_text=True)
    assert 'src="/alunos/1/foto"' in ficha_ana and "avatar-grande" in ficha_ana
    ficha_bruno = navegador.get("/alunos/2").get_data(as_text=True)
    assert 'src="/alunos/2/foto"' not in ficha_bruno and ">BL</span>" in ficha_bruno

    pendencias = navegador.get("/pendencias").get_data(as_text=True)  # os dois estão sem treino
    assert 'src="/alunos/1/foto"' in pendencias and ">BL</span>" in pendencias

    busca = navegador.get("/api/alunos").get_json()["alunos"]
    assert {a["id"]: a["foto"] for a in busca} == {1: True, 2: False}


# ------------------------------------------------------------------ foto ampliada (versão 20)


def test_foto_grande_mantem_a_proporcao_e_nao_passa_do_limite():
    with Image.open(io.BytesIO(fotos.foto_grande(_jpeg(1200, 1600)))) as imagem:
        assert imagem.format == "JPEG" and imagem.size == (480, fotos.LADO_GRANDE)
    with Image.open(io.BytesIO(fotos.foto_grande(_jpeg(300, 400)))) as imagem:
        assert imagem.size == (300, 400)  # foto pequena não é aumentada


def test_importar_guarda_as_duas_e_foto_sem_a_grande_e_pedida_de_novo(conn):
    original = _jpeg(600, 800)
    fotos.importar(conn, {"fotos": [{"id": 501, "jpg": _b64(original)}]}, agora=AGORA)
    assert len(fotos.ler(conn, 1, grande=True)) > len(fotos.ler(conn, 1))
    assert fotos.estado(conn)["alunos"][0]["sha256"] == hashlib.sha256(original).hexdigest()

    conn.execute("UPDATE foto_aluno SET grande = NULL")  # como ficam as fotos gravadas antes da versão 20
    assert fotos.estado(conn)["alunos"][0]["sha256"] is None  # o PC manda de novo
    assert fotos.ler(conn, 1, grande=True) == fotos.ler(conn, 1)  # enquanto isso, a grande cai na miniatura


def test_rota_da_foto_grande_e_a_tela_tem_o_clique(caminho):
    navegador = _autorizado(caminho)
    pequena = navegador.get("/alunos/1/foto").data
    grande = navegador.get("/alunos/1/foto?tamanho=grande")
    assert grande.status_code == 200 and grande.mimetype == "image/jpeg" and len(grande.data) > len(pequena)

    ficha = navegador.get("/alunos/1").get_data(as_text=True)
    assert 'data-nome="Ana Souza"' in ficha and "foto_grande.js" in ficha
    for tela in ("/alunos", "/pendencias", "/ausentes"):
        assert "foto_grande.js" in navegador.get(tela).get_data(as_text=True), tela
