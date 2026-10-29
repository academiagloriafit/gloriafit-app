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
    assert resposta.headers["Cache-Control"] == "private, no-cache" and resposta.headers["ETag"]
    de_novo = _autorizado(caminho).get("/alunos/1/foto", headers={"If-None-Match": resposta.headers["ETag"]})
    assert de_novo.status_code == 304 and de_novo.data == b""  # a foto não mudou: o navegador usa a cópia dele
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


# ------------------------------------------------------------------ foto escolhida pelo aluno no app (versão 21)


def _aluno_logado(caminho, aluno_id):
    """O celular do aluno, já logado (sem autorização de computador)."""
    from app import aluno_acesso

    celular = criar_app(caminho).test_client()
    c = conectar(caminho)
    with c:
        token = aluno_acesso._criar_sessao(c, aluno_id, datetime.now(timezone.utc))
    c.close()
    celular.set_cookie(aluno_acesso.NOME_DO_COOKIE, token)
    return celular


def test_rotas_da_foto_do_aluno_exigem_o_login_do_aluno(caminho):
    anonimo = criar_app(caminho).test_client()
    assert anonimo.get("/aluno/foto").status_code == 401
    assert anonimo.get("/api/aluno/foto").status_code == 401
    assert anonimo.post("/api/aluno/foto", json={"jpg": _b64(_jpeg())}).status_code == 401
    assert anonimo.post("/api/aluno/foto/apagar", json={}).status_code == 401
    # o aluno logado não abre a foto de outro aluno pela rota do professor
    assert _aluno_logado(caminho, 2).get("/alunos/1/foto").status_code in (302, 401)


def test_aluno_ve_so_a_propria_foto(caminho):
    ana = _aluno_logado(caminho, 1)
    assert ana.get("/api/aluno/foto").get_json() == {"tem_foto": True, "propria": False, "enviada_em": None, "tem_catraca": True}
    assert ana.get("/aluno/foto").data == _autorizado(caminho).get("/alunos/1/foto").data
    bruno = _aluno_logado(caminho, 2)
    assert bruno.get("/aluno/foto").status_code == 404  # Bruno não tem foto; e não há como pedir a de outro
    assert bruno.get("/aluno/foto?id=1").status_code == 404


def test_aluno_troca_a_foto_e_o_professor_ve_na_hora(caminho):
    professor = _autorizado(caminho)
    da_catraca = professor.get("/alunos/1/foto")
    ana = _aluno_logado(caminho, 1)
    resposta = ana.post("/api/aluno/foto", json={"jpg": _b64(_jpeg(900, 1200, cor=(20, 200, 40)))})
    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert corpo["ok"] and corpo["propria"] and corpo["tem_catraca"] and corpo["enviada_em"]

    agora = professor.get("/alunos/1/foto", headers={"If-None-Match": da_catraca.headers["ETag"]})
    assert agora.status_code == 200 and agora.data != da_catraca.data  # a etiqueta mudou: o navegador baixa a nova
    assert ana.get("/aluno/foto").data == agora.data
    ficha = professor.get("/alunos/1").get_data(as_text=True)
    assert "Foto escolhida pelo aluno no app" in ficha and "Voltar para a foto da catraca" in ficha and "ficha_foto.js" in ficha

    # a atualização diária do PC da recepção não passa por cima da foto escolhida
    c = conectar(caminho)
    fotos.importar(c, {"fotos": [{"id": 501, "jpg": _b64(_jpeg(cor=(1, 2, 3)))}]}, agora=datetime.now(timezone.utc))
    c.close()
    assert professor.get("/alunos/1/foto").data == agora.data


def test_aluno_sem_foto_da_catraca_tambem_pode_escolher(caminho):
    bruno = _aluno_logado(caminho, 2)
    assert bruno.post("/api/aluno/foto", json={"jpg": _b64(_jpeg(formato="PNG"))}).status_code == 200
    assert bruno.get("/aluno/foto").mimetype == "image/jpeg"
    busca = _autorizado(caminho).get("/api/alunos").get_json()["alunos"]
    assert {a["id"]: a["foto"] for a in busca} == {1: True, 2: True}
    corpo = bruno.post("/api/aluno/foto/apagar", json={}).get_json()
    assert corpo == {"ok": True, "tem_foto": False, "propria": False, "enviada_em": None, "tem_catraca": False}
    assert bruno.get("/aluno/foto").status_code == 404


@pytest.mark.parametrize("corpo", [{"jpg": "isto não é base64!"}, {"jpg": _b64(b"texto qualquer")}, {"jpg": 5}, {}, []])
def test_foto_que_nao_e_imagem_e_recusada(caminho, corpo):
    resposta = _aluno_logado(caminho, 1).post("/api/aluno/foto", json=corpo)
    assert resposta.status_code == 400
    assert _aluno_logado(caminho, 1).get("/api/aluno/foto").get_json()["propria"] is False


def test_limite_de_trocas_por_dia(caminho):
    ana = _aluno_logado(caminho, 1)
    foto = _b64(_jpeg())
    for _ in range(fotos.TROCAS_POR_DIA):
        assert ana.post("/api/aluno/foto", json={"jpg": foto}).status_code == 200
    resposta = ana.post("/api/aluno/foto", json={"jpg": foto})
    assert resposta.status_code == 429 and "vezes hoje" in resposta.get_json()["erro"]


def test_limite_de_trocas_libera_no_dia_seguinte(conn):
    ontem = AGORA - timedelta(hours=25)
    for _ in range(fotos.TROCAS_POR_DIA):
        fotos.trocar_pela_do_aluno(conn, 1, _jpeg(), agora=ontem)
    with pytest.raises(fotos.MuitasTrocas):
        fotos.trocar_pela_do_aluno(conn, 1, _jpeg(), agora=ontem + timedelta(minutes=5))
    fotos.trocar_pela_do_aluno(conn, 1, _jpeg(), agora=AGORA)  # passou um dia: libera


def test_aluno_volta_para_a_foto_da_recepcao(caminho):
    ana = _aluno_logado(caminho, 1)
    da_catraca = ana.get("/aluno/foto").data
    ana.post("/api/aluno/foto", json={"jpg": _b64(_jpeg(cor=(9, 9, 200)))})
    corpo = ana.post("/api/aluno/foto/apagar", json={}).get_json()
    assert corpo["ok"] and not corpo["propria"] and corpo["tem_foto"]
    assert ana.get("/aluno/foto").data == da_catraca


def test_professor_volta_para_a_foto_da_catraca(caminho):
    ana = _aluno_logado(caminho, 1)
    professor = _autorizado(caminho)
    da_catraca = professor.get("/alunos/1/foto").data
    ana.post("/api/aluno/foto", json={"jpg": _b64(_jpeg(cor=(9, 9, 200)))})

    assert criar_app(caminho).test_client().post("/api/alunos/1/foto/catraca", json={}).status_code == 401
    assert ana.post("/api/alunos/1/foto/catraca", json={}).status_code == 401  # o aluno não usa a rota do professor
    resposta = professor.post("/api/alunos/1/foto/catraca", json={})
    assert resposta.status_code == 200 and resposta.get_json()["havia"] is True
    assert professor.get("/alunos/1/foto").data == da_catraca
    assert "Foto escolhida pelo aluno" not in professor.get("/alunos/1").get_data(as_text=True)
    assert professor.post("/api/alunos/999/foto/catraca", json={}).status_code == 404


def test_foto_escolhida_some_quando_o_aluno_deixa_a_academia(conn):
    fotos.trocar_pela_do_aluno(conn, 1, _jpeg(), agora=AGORA)
    fotos.trocar_pela_do_aluno(conn, 3, _jpeg(), agora=AGORA)  # Carla está desativada (D)
    depois = AGORA + timedelta(days=fotos.DIAS_SEM_CONFIRMACAO + 1)
    fotos.importar(conn, {"fotos": [], "presentes": []}, agora=depois)
    assert fotos.situacao_da_foto(conn, 1)["propria"] is True  # em uso: a foto continua
    assert fotos.situacao_da_foto(conn, 3)["propria"] is False


def test_meu_perfil_tem_a_secao_da_foto(caminho):
    pagina = _aluno_logado(caminho, 1).get("/aluno/perfil").get_data(as_text=True)
    assert 'id="minha-foto"' in pagina and "aluno_foto.js" in pagina and 'accept="image/*"' in pagina
