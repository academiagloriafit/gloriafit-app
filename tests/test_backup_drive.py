"""Cópia diária para o Google Drive (app/backup_drive.py): criptografia, arquivo de credenciais, conversa com o Google
(contra um servidor de mentira na própria máquina), integração com o agendador e comandos do terminal do servidor.
Dados e segredos inventados."""

import json
import os
import re
import stat
import threading
import urllib.parse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app import backup_agendado as ag
from app import backup_drive as bd
from app.backup import fazer_backup
from app.db import conectar, criar_tabelas

UTC = timezone.utc
# Terça-feira, 20/10/2026, 03:00 em Vila Velha (06:00 UTC): a cópia diária.
TERCA_3H = datetime(2026, 10, 20, 6, 0, 0, tzinfo=UTC)

CLIENT_ID = "123456789012-abcdefghijklmnopqrstuvwxyz012345.apps.googleusercontent.com"
CLIENT_SECRET = "GOCSPX-" + "a1B2c3D4" * 4
REFRESH_TOKEN = "1//0g" + "RefreshTokenDeMentira" * 3
TOKEN_DE_ACESSO = "ya29.token-de-acesso-de-mentira-123456"
DEVICE_CODE = "device-code-de-mentira-0123456789"
SENHA = "uma frase longa e boa para a copia 2026"
PASTA_ID = "PASTAFAKE0001"


# ------------------------------------------------------------------ servidor de mentira (Google)


class _Google(BaseHTTPRequestHandler):
    """Faz de conta de oauth2.googleapis.com e www.googleapis.com/drive. Guarda cada pedido e os arquivos "enviados".
    `servidor.forcadas` = [(método, começo do caminho, status, corpo dict|bytes, cabeçalhos)]: a primeira que casar vale uma vez."""

    protocol_version = "HTTP/1.1"

    def _responder(self, status, corpo, cabecalhos=None):
        dados = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        for nome, valor in (cabecalhos or {}).items():
            self.send_header(nome, valor)
        self.end_headers()
        self.wfile.write(dados)

    def _tratar(self, metodo):
        tamanho = int(self.headers.get("Content-Length", 0))
        corpo = self.rfile.read(tamanho) if tamanho else b""
        url = urllib.parse.urlparse(self.path)
        consulta = urllib.parse.parse_qs(url.query)
        srv = self.server
        srv.pedidos.append({"metodo": metodo, "caminho": url.path, "consulta": consulta, "cabecalhos": dict(self.headers), "corpo": corpo})

        for forcada in srv.forcadas:
            if forcada[0] == metodo and url.path.startswith(forcada[1]):
                srv.forcadas.remove(forcada)
                return self._responder(forcada[2], forcada[3], forcada[4] if len(forcada) > 4 else None)

        if metodo == "POST" and url.path == "/device/code":
            return self._responder(200, {"device_code": DEVICE_CODE, "user_code": "ABCD-EFGH", "verification_url": "https://www.google.com/device", "expires_in": 1800, "interval": 5})
        if metodo == "POST" and url.path == "/token":
            campos = urllib.parse.parse_qs(corpo.decode("utf-8"))
            if campos.get("grant_type") == ["refresh_token"]:
                return self._responder(200, {"access_token": TOKEN_DE_ACESSO, "expires_in": 3599, "token_type": "Bearer"})
            return self._responder(200, {"access_token": TOKEN_DE_ACESSO, "refresh_token": REFRESH_TOKEN, "expires_in": 3599})
        if metodo == "POST" and url.path == "/drive/v3/files":
            identificador = f"PASTAFAKE{len(srv.pastas) + 1:04d}"
            srv.pastas[identificador] = {"trashed": False}
            return self._responder(200, {"id": identificador})
        if metodo == "GET" and url.path.startswith("/drive/v3/files/"):
            identificador = url.path.rsplit("/", 1)[1]
            if identificador not in srv.pastas:
                return self._responder(404, {"error": {"code": 404, "message": "File not found", "status": "NOT_FOUND"}})
            return self._responder(200, {"id": identificador, "trashed": srv.pastas[identificador]["trashed"]})
        if metodo == "GET" and url.path == "/drive/v3/files":
            achou = re.search(r"name = '([^']+)' and '([^']+)' in parents", consulta["q"][0])
            achados = [{"id": i} for i, a in srv.arquivos.items() if achou and a["nome"] == achou.group(1) and a["pai"] == achou.group(2)]
            return self._responder(200, {"files": achados[:1]})
        if metodo in ("POST", "PATCH") and url.path.startswith("/upload/drive/v3/files"):
            numero = len(srv.sessoes) + 1
            alvo = url.path.rsplit("/", 1)[1] if metodo == "PATCH" else None
            srv.sessoes[numero] = {"metadados": json.loads(corpo), "arquivo_id": alvo}
            return self._responder(200, b"", {"Location": f"{srv.url}/sessao/{numero}"})
        if metodo == "PUT" and url.path.startswith("/sessao/"):
            sessao = srv.sessoes[int(url.path.rsplit("/", 1)[1])]
            metadados = sessao["metadados"]
            identificador = sessao["arquivo_id"] or f"ARQUIVO{len(srv.arquivos) + 1:05d}"
            atual = srv.arquivos.get(identificador, {})
            srv.arquivos[identificador] = {
                "nome": metadados.get("name", atual.get("nome")),
                "pai": (metadados.get("parents") or [atual.get("pai")])[0],
                "descricao": metadados.get("description"),
                "conteudo": corpo,
            }
            return self._responder(200 if sessao["arquivo_id"] else 201, {"id": identificador})
        return self._responder(404, {"error": "caminho desconhecido"})

    def do_GET(self):
        self._tratar("GET")

    def do_POST(self):
        self._tratar("POST")

    def do_PATCH(self):
        self._tratar("PATCH")

    def do_PUT(self):
        self._tratar("PUT")

    def log_message(self, *_args):
        pass


@pytest.fixture
def google():
    servidor = HTTPServer(("127.0.0.1", 0), _Google)
    servidor.pedidos, servidor.forcadas, servidor.pastas, servidor.arquivos, servidor.sessoes = [], [], {PASTA_ID: {"trashed": False}}, {}, {}
    servidor.url = f"http://127.0.0.1:{servidor.server_port}"
    servidor.enderecos = bd.Enderecos(oauth=servidor.url, drive=servidor.url)
    fio = threading.Thread(target=lambda: servidor.serve_forever(poll_interval=0.01), daemon=True)
    fio.start()
    yield servidor
    servidor.shutdown()
    servidor.server_close()


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    esperas = []
    monkeypatch.setattr(bd, "_dormir", esperas.append)
    return esperas


@pytest.fixture
def pastas(tmp_path):
    for nome in ("dados", "backups"):
        (tmp_path / nome).mkdir()
    return tmp_path / "dados", tmp_path / "backups"


@pytest.fixture
def banco(pastas):
    caminho = pastas[0] / "app.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.execute("INSERT INTO aluno (nome, cpf) VALUES ('MARIA TESTE', '11144477735')")
    conn.commit()
    conn.close()
    return caminho


@pytest.fixture
def copia(banco, pastas):
    return fazer_backup(banco, pastas[1], 30, agora=TERCA_3H)


@pytest.fixture
def arquivo_de_credenciais(pastas):
    arquivo = pastas[0] / bd.NOME_DO_ARQUIVO
    bd.guardar_configuracao(arquivo, bd.Configuracao(CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN, SENHA, PASTA_ID))
    return arquivo


def _corpo_form(pedido):
    return {k: v[0] for k, v in urllib.parse.parse_qs(pedido["corpo"].decode("utf-8")).items()}


# ------------------------------------------------------------------ criptografia


def test_criptografar_e_descriptografar_devolvem_o_mesmo_conteudo():
    original = b"SQLite format 3\x00" + os.urandom(5000)

    assert bd.descriptografar(bd.criptografar(original, SENHA), SENHA) == original


def test_o_arquivo_criptografado_nao_deixa_ver_o_conteudo_e_muda_a_cada_vez():
    original = b"SQLite format 3\x00 CPF 11144477735 MARIA TESTE"

    primeiro, segundo = bd.criptografar(original, SENHA), bd.criptografar(original, SENHA)

    assert primeiro.startswith(bd.CABECALHO_DO_ARQUIVO)
    assert b"11144477735" not in primeiro and b"MARIA" not in primeiro
    assert primeiro != segundo  # sal novo a cada arquivo
    assert bd.descriptografar(segundo, SENHA) == original


def test_senha_errada_nao_abre():
    pacote = bd.criptografar(b"conteudo", SENHA)

    with pytest.raises(bd.ArquivoOuSenhaInvalidos):
        bd.descriptografar(pacote, SENHA + "x")


def test_arquivo_alterado_nao_abre():
    pacote = bytearray(bd.criptografar(b"conteudo importante", SENHA))
    pacote[-5] ^= 0x01

    with pytest.raises(bd.ArquivoOuSenhaInvalidos):
        bd.descriptografar(bytes(pacote), SENHA)


@pytest.mark.parametrize("lixo", [b"", b"GFBK1\n", b"GFBK1\n" + b"s" * 16, b"outra coisa qualquer", b"SQLite format 3\x00" + b"x" * 100])
def test_o_que_nao_e_uma_copia_do_app_e_recusado(lixo):
    with pytest.raises(bd.ArquivoOuSenhaInvalidos):
        bd.descriptografar(lixo, SENHA)


def test_senha_curta_nao_serve_para_criptografar():
    with pytest.raises(ValueError):
        bd.criptografar(b"x", "curta")


# ------------------------------------------------------------------ o arquivo de credenciais


def test_credenciais_sao_guardadas_so_para_o_dono_e_lidas_de_volta(pastas, arquivo_de_credenciais):
    assert stat.S_IMODE(arquivo_de_credenciais.stat().st_mode) == 0o600
    assert not list(pastas[0].glob("*.novo"))

    lida = bd.ler_configuracao(arquivo_de_credenciais)

    assert (lida.client_id, lida.client_secret, lida.refresh_token, lida.senha, lida.pasta_id) == (CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN, SENHA, PASTA_ID)
    assert bd.configurado(arquivo_de_credenciais)


def test_o_repr_da_configuracao_nao_mostra_segredo():
    texto = repr(bd.Configuracao(CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN, SENHA, PASTA_ID))

    for segredo in (CLIENT_SECRET, REFRESH_TOKEN, SENHA):
        assert segredo not in texto


@pytest.mark.parametrize("conteudo", [None, "", "isto nao e json", "[]", '{"client_id": 1}', json.dumps({"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "refresh_token": REFRESH_TOKEN, "senha": SENHA})])
def test_arquivo_ausente_estragado_ou_sem_pasta_conta_como_nao_configurado(pastas, conteudo):
    arquivo = pastas[0] / bd.NOME_DO_ARQUIVO
    if conteudo is not None:
        arquivo.write_text(conteudo, encoding="utf-8")

    assert not bd.configurado(arquivo)
    with pytest.raises(bd.NaoConfigurado):
        bd.ler_configuracao(arquivo)


@pytest.mark.parametrize(
    "campo, valor",
    [("client_id", "curto"), ("client_id", "tem espaco no meio.apps.googleusercontent.com"), ("client_secret", "x"), ("refresh_token", "curto"), ("senha", "curta"), ("pasta_id", "../fora")],
)
def test_credenciais_fora_do_formato_nao_sao_guardadas(pastas, campo, valor):
    campos = {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "refresh_token": REFRESH_TOKEN, "senha": SENHA, "pasta_id": PASTA_ID, campo: valor}

    with pytest.raises(ValueError):
        bd.guardar_configuracao(pastas[0] / bd.NOME_DO_ARQUIVO, bd.Configuracao(**campos))

    assert not (pastas[0] / bd.NOME_DO_ARQUIVO).exists()


def test_o_arquivo_fica_ao_lado_do_banco_ou_onde_a_variavel_mandar(tmp_path, monkeypatch):
    monkeypatch.delenv(bd.VARIAVEL_DO_ARQUIVO, raising=False)
    assert bd.caminho_da_configuracao(tmp_path / "dados" / "app.db") == tmp_path / "dados" / "drive_backup.json"

    monkeypatch.setenv(bd.VARIAVEL_DO_ARQUIVO, str(tmp_path / "outro.json"))
    assert bd.caminho_da_configuracao(tmp_path / "dados" / "app.db") == tmp_path / "outro.json"


# ------------------------------------------------------------------ nomes e datas


def test_o_nome_no_drive_e_o_dia_da_semana_em_vila_velha():
    assert bd.nome_no_drive(TERCA_3H) == "app-terca.gfbk"  # 03:00 de terça
    # 02:30 UTC de terça = 23:30 de SEGUNDA em Vila Velha
    assert bd.nome_no_drive(datetime(2026, 10, 20, 2, 30, tzinfo=UTC)) == "app-segunda.gfbk"
    dias = {bd.nome_no_drive(TERCA_3H + timedelta(days=n)) for n in range(7)}
    assert dias == {f"app-{d}.gfbk" for d in ("segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo")}


def test_a_data_da_copia_vem_do_nome_do_arquivo(tmp_path):
    assert bd.quando_da_copia(tmp_path / "app-2026-10-20-060000.db") == TERCA_3H
    agora = datetime(2026, 1, 2, 3, 4, tzinfo=UTC)
    assert bd.quando_da_copia(tmp_path / "qualquer.db", agora) == agora


def test_a_copia_local_mais_nova_ignora_o_que_nao_e_copia(tmp_path):
    assert bd.copia_local_mais_nova(tmp_path / "nao-existe") is None
    for nome in ("app-2026-10-18-060000.db", "app-2026-10-19-060000.db", "app-2026-10-20-060000.db.parcial", "drive-ultimo-envio.json"):
        (tmp_path / nome).write_bytes(b"x")

    assert bd.copia_local_mais_nova(tmp_path).name == "app-2026-10-19-060000.db"


# ------------------------------------------------------------------ enviar uma cópia (servidor de mentira)


def _enviar(copia, arquivo, pastas, google, agora=TERCA_3H + timedelta(seconds=20)):
    return bd.enviar_copia(copia, arquivo, pastas[1], agora=agora, enderecos=google.enderecos)


def test_a_primeira_vez_cria_o_arquivo_do_dia_na_pasta_com_o_conteudo_criptografado(copia, arquivo_de_credenciais, pastas, google):
    nome = _enviar(copia, arquivo_de_credenciais, pastas, google)

    assert nome == "app-terca.gfbk"
    assert len(google.arquivos) == 1
    enviado = next(iter(google.arquivos.values()))
    assert (enviado["nome"], enviado["pai"]) == ("app-terca.gfbk", PASTA_ID)
    assert "20/10/2026 03:00" in enviado["descricao"] and "Vila Velha" in enviado["descricao"]
    assert b"11144477735" not in enviado["conteudo"]  # saiu criptografado
    assert bd.descriptografar(enviado["conteudo"], SENHA) == copia.read_bytes()  # e abre com a senha, igualzinho


def test_o_envio_fica_registrado_so_depois_de_dar_certo(copia, arquivo_de_credenciais, pastas, google):
    assert bd.ler_ultimo_envio(pastas[1]) is None

    _enviar(copia, arquivo_de_credenciais, pastas, google)

    quando, nome = bd.ler_ultimo_envio(pastas[1])
    assert quando == TERCA_3H + timedelta(seconds=20) and nome == "app-terca.gfbk"


def test_no_mesmo_dia_da_semana_troca_o_conteudo_do_mesmo_arquivo_sem_duplicar(copia, banco, arquivo_de_credenciais, pastas, google):
    _enviar(copia, arquivo_de_credenciais, pastas, google)
    id_do_arquivo = next(iter(google.arquivos))
    semana_seguinte = fazer_backup(banco, pastas[1], 30, agora=TERCA_3H + timedelta(days=7))

    _enviar(semana_seguinte, arquivo_de_credenciais, pastas, google, TERCA_3H + timedelta(days=7, seconds=20))

    assert list(google.arquivos) == [id_do_arquivo]  # o mesmo arquivo, não um segundo
    assert google.arquivos[id_do_arquivo]["nome"] == "app-terca.gfbk"  # a troca não apaga o nome
    assert "27/10/2026" in google.arquivos[id_do_arquivo]["descricao"]
    assert [p["metodo"] for p in google.pedidos if p["caminho"].startswith("/upload")] == ["POST", "PATCH"]


def test_outro_dia_da_semana_vai_para_outro_arquivo(copia, banco, arquivo_de_credenciais, pastas, google):
    quarta = fazer_backup(banco, pastas[1], 30, agora=TERCA_3H + timedelta(days=1))

    _enviar(copia, arquivo_de_credenciais, pastas, google)
    _enviar(quarta, arquivo_de_credenciais, pastas, google)

    assert sorted(a["nome"] for a in google.arquivos.values()) == ["app-quarta.gfbk", "app-terca.gfbk"]


def test_o_token_vai_nas_chamadas_da_api_mas_nao_no_envio_do_arquivo(copia, arquivo_de_credenciais, pastas, google):
    _enviar(copia, arquivo_de_credenciais, pastas, google)

    for pedido in google.pedidos:
        if pedido["caminho"].startswith(("/drive/", "/upload/")):
            assert pedido["cabecalhos"]["Authorization"] == f"Bearer {TOKEN_DE_ACESSO}"
    envio = next(p for p in google.pedidos if p["metodo"] == "PUT")
    assert "Authorization" not in envio["cabecalhos"]  # o endereço da sessão já carrega a permissão


def test_o_refresh_token_e_o_segredo_vao_so_ao_servidor_de_autorizacao(copia, arquivo_de_credenciais, pastas, google):
    _enviar(copia, arquivo_de_credenciais, pastas, google)

    troca = next(p for p in google.pedidos if p["caminho"] == "/token")
    assert _corpo_form(troca) == {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "refresh_token": REFRESH_TOKEN, "grant_type": "refresh_token"}
    for pedido in google.pedidos:
        if pedido["caminho"] != "/token":
            assert REFRESH_TOKEN not in pedido["corpo"].decode("utf-8", "replace") and CLIENT_SECRET not in str(pedido["cabecalhos"])


def test_sem_configuracao_nao_envia_nada(copia, pastas, google):
    with pytest.raises(bd.NaoConfigurado):
        _enviar(copia, pastas[0] / bd.NOME_DO_ARQUIVO, pastas, google)

    assert google.pedidos == []


def test_autorizacao_retirada_pede_para_configurar_de_novo(copia, arquivo_de_credenciais, pastas, google):
    google.forcadas.append(("POST", "/token", 400, {"error": "invalid_grant", "error_description": "Token has been expired or revoked."}))

    with pytest.raises(bd.DriveFalhou) as falha:
        _enviar(copia, arquivo_de_credenciais, pastas, google)

    assert "configurar" in falha.value.mensagem
    assert bd.ler_ultimo_envio(pastas[1]) is None  # falhou: não conta como enviado


def test_pasta_apagada_ou_na_lixeira_e_avisada(copia, arquivo_de_credenciais, pastas, google):
    google.pastas.clear()
    with pytest.raises(bd.DriveFalhou, match="sumiu"):
        _enviar(copia, arquivo_de_credenciais, pastas, google)

    google.pastas[PASTA_ID] = {"trashed": True}
    with pytest.raises(bd.DriveFalhou, match="lixeira"):
        _enviar(copia, arquivo_de_credenciais, pastas, google)

    assert google.arquivos == {}


def test_erro_de_permissao_nao_se_repete(copia, arquivo_de_credenciais, pastas, google, sem_espera):
    google.forcadas.append(("POST", "/upload", 403, {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": "sem permissao"}}))

    with pytest.raises(bd.DriveFalhou) as falha:
        _enviar(copia, arquivo_de_credenciais, pastas, google)

    assert "PERMISSION_DENIED" in falha.value.detalhe
    assert len([p for p in google.pedidos if p["caminho"].startswith("/upload")]) == 1
    assert sem_espera == []


def test_erro_5xx_do_google_e_tentado_de_novo_e_passa(copia, arquivo_de_credenciais, pastas, google, sem_espera):
    google.forcadas.append(("PUT", "/sessao", 503, {"error": {"message": "Backend Error"}}))

    nome = _enviar(copia, arquivo_de_credenciais, pastas, google)

    assert nome == "app-terca.gfbk" and len(google.arquivos) == 1
    assert sem_espera == [3.0]


def test_erro_5xx_sempre_desiste_depois_de_3_tentativas(copia, arquivo_de_credenciais, pastas, google, sem_espera):
    for _ in range(3):
        google.forcadas.append(("POST", "/upload", 500, {"error": {"message": "Internal Error"}}))

    with pytest.raises(bd.DriveFalhou, match="problema do lado dele"):
        _enviar(copia, arquivo_de_credenciais, pastas, google)

    assert sem_espera == [3.0, 10.0]
    assert google.arquivos == {}


def test_sem_internet_vira_erro_claro_e_nao_trava(copia, arquivo_de_credenciais, pastas, sem_espera):
    sem_servidor = bd.Enderecos(oauth="http://127.0.0.1:1", drive="http://127.0.0.1:1")

    with pytest.raises(bd.DriveFalhou, match="rede ou demora"):
        bd.enviar_copia(copia, arquivo_de_credenciais, pastas[1], enderecos=sem_servidor)

    assert len(sem_espera) == 2  # 3 tentativas, 2 esperas


def test_redirecionamento_nao_e_seguido(copia, arquivo_de_credenciais, pastas, google):
    google.forcadas.append(("POST", "/token", 302, b"", {"Location": f"{google.url}/outro-lugar"}))

    with pytest.raises(bd.DriveFalhou, match="redirecionamento"):
        _enviar(copia, arquivo_de_credenciais, pastas, google)

    assert not any(p["caminho"] == "/outro-lugar" for p in google.pedidos)


def test_cabecalho_de_envio_sem_endereco_da_sessao_falha_sem_mandar_o_arquivo(copia, arquivo_de_credenciais, pastas, google):
    google.forcadas.append(("POST", "/upload", 200, b"", {}))

    with pytest.raises(bd.DriveFalhou, match="endereço de envio"):
        _enviar(copia, arquivo_de_credenciais, pastas, google)

    assert not any(p["metodo"] == "PUT" for p in google.pedidos)


def test_cabecalho_de_envio_com_endereco_de_esquema_diferente_falha_sem_mandar_o_arquivo(copia, arquivo_de_credenciais, pastas, google):
    google.forcadas.append(("POST", "/upload", 200, b"", {"Location": "https://outro.exemplo/sessao/1"}))

    with pytest.raises(bd.DriveFalhou, match="endereço de envio"):
        _enviar(copia, arquivo_de_credenciais, pastas, google)

    assert not any(p["metodo"] == "PUT" for p in google.pedidos)


def test_erro_do_google_que_repete_segredos_nao_vaza_para_a_mensagem(copia, arquivo_de_credenciais, pastas, google):
    eco = f"token {TOKEN_DE_ACESSO} senha {SENHA} segredo {CLIENT_SECRET} refresh {REFRESH_TOKEN}"
    google.forcadas.append(("POST", "/upload", 400, {"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": eco}}))

    with pytest.raises(bd.DriveFalhou) as falha:
        _enviar(copia, arquivo_de_credenciais, pastas, google)

    texto = f"{falha.value.mensagem} | {falha.value.detalhe} | {falha.value!r}"
    for segredo in (TOKEN_DE_ACESSO, SENHA, CLIENT_SECRET, REFRESH_TOKEN):
        assert segredo not in texto
    assert "***" in falha.value.detalhe


def test_copia_local_que_sumiu_vira_erro_claro(arquivo_de_credenciais, pastas, google, tmp_path):
    with pytest.raises(bd.DriveFalhou, match="ler a cópia local"):
        _enviar(tmp_path / "app-2026-10-20-060000.db", arquivo_de_credenciais, pastas, google)


# ------------------------------------------------------------------ autorização pelo celular (fluxo de dispositivo)


def test_pedir_o_codigo_manda_o_id_do_cliente_e_o_escopo_so_do_drive_file(google):
    pedido = bd.iniciar_autorizacao(bd._Google(google.enderecos), CLIENT_ID)

    assert pedido["user_code"] == "ABCD-EFGH" and pedido["endereco"] == "https://www.google.com/device"
    assert pedido["intervalo"] == 5 and pedido["expira_em"] == 1800
    enviado = _corpo_form(google.pedidos[0])
    assert enviado == {"client_id": CLIENT_ID, "scope": "https://www.googleapis.com/auth/drive.file"}


def test_id_de_cliente_do_tipo_errado_explica_o_que_fazer(google):
    google.forcadas.append(("POST", "/device/code", 401, {"error": "invalid_client", "error_description": "Invalid client type."}))

    with pytest.raises(bd.DriveFalhou, match="TVs e dispositivos"):
        bd.iniciar_autorizacao(bd._Google(google.enderecos), CLIENT_ID)


def _pedido():
    return {"device_code": DEVICE_CODE, "user_code": "ABCD-EFGH", "endereco": "https://www.google.com/device", "expira_em": 1800, "intervalo": 5}


class _RelogioDeMentira:
    def __init__(self):
        self.agora = 0.0
        self.dormidas = []

    def __call__(self):
        return self.agora

    def dormir(self, segundos):
        self.dormidas.append(segundos)
        self.agora += segundos


def test_espera_ate_o_thiago_digitar_o_codigo_e_devolve_o_refresh_token(google):
    relogio = _RelogioDeMentira()
    google.forcadas += [("POST", "/token", 428, {"error": "authorization_pending"}), ("POST", "/token", 428, {"error": "authorization_pending"})]

    refresh = bd.esperar_autorizacao(bd._Google(google.enderecos), CLIENT_ID, CLIENT_SECRET, _pedido(), relogio.dormir, relogio)

    assert refresh == REFRESH_TOKEN
    assert relogio.dormidas == [5, 5, 5]
    ultimo = _corpo_form(google.pedidos[-1])
    assert ultimo["device_code"] == DEVICE_CODE and ultimo["grant_type"] == "urn:ietf:params:oauth:grant-type:device_code"
    assert ultimo["client_secret"] == CLIENT_SECRET


def test_slow_down_aumenta_o_intervalo(google):
    relogio = _RelogioDeMentira()
    google.forcadas.append(("POST", "/token", 403, {"error": "slow_down"}))

    bd.esperar_autorizacao(bd._Google(google.enderecos), CLIENT_ID, CLIENT_SECRET, _pedido(), relogio.dormir, relogio)

    assert relogio.dormidas == [5, 10]


@pytest.mark.parametrize(
    "erro, trecho", [("access_denied", "recusada"), ("expired_token", "expirou"), ("invalid_grant", "expirou"), ("invalid_client", "ID/segredo")]
)
def test_recusa_ou_codigo_vencido_param_a_espera(google, erro, trecho):
    relogio = _RelogioDeMentira()
    google.forcadas.append(("POST", "/token", 403, {"error": erro}))

    with pytest.raises(bd.DriveFalhou, match=trecho):
        bd.esperar_autorizacao(bd._Google(google.enderecos), CLIENT_ID, CLIENT_SECRET, _pedido(), relogio.dormir, relogio)


def test_passou_do_prazo_sem_digitar_o_codigo(google):
    relogio = _RelogioDeMentira()
    for _ in range(400):
        google.forcadas.append(("POST", "/token", 428, {"error": "authorization_pending"}))

    with pytest.raises(bd.DriveFalhou, match="tempo"):
        bd.esperar_autorizacao(bd._Google(google.enderecos), CLIENT_ID, CLIENT_SECRET, _pedido(), relogio.dormir, relogio)

    assert sum(relogio.dormidas) >= 1800


def test_autorizado_mas_sem_refresh_token_e_recusado(google):
    relogio = _RelogioDeMentira()
    google.forcadas.append(("POST", "/token", 200, {"access_token": TOKEN_DE_ACESSO}))

    with pytest.raises(bd.DriveFalhou, match="refresh token"):
        bd.esperar_autorizacao(bd._Google(google.enderecos), CLIENT_ID, CLIENT_SECRET, _pedido(), relogio.dormir, relogio)


# ------------------------------------------------------------------ EnvioAoDrive (o que o agendador usa)


def test_envio_atrasado_e_verificacao(pastas, arquivo_de_credenciais):
    envio = bd.EnvioAoDrive(arquivo_de_credenciais, pastas[1])
    agora = TERCA_3H + timedelta(hours=1)

    assert envio.configurado()
    assert envio.atrasado(agora, timedelta(hours=20))  # nunca enviou
    assert envio.verificar(agora, timedelta(hours=30)) == (False, "Nenhum envio ao Drive registrado.")

    bd.registrar_envio(pastas[1], TERCA_3H, "app-2026-10-20-060000.db", "app-terca.gfbk")
    assert not envio.atrasado(agora, timedelta(hours=20))
    assert envio.verificar(agora, timedelta(hours=30))[0]

    muito_depois = TERCA_3H + timedelta(hours=49)
    assert envio.atrasado(muito_depois, timedelta(hours=20))
    ok, mensagem = envio.verificar(muito_depois, timedelta(hours=30))
    assert not ok and "49 horas" in mensagem


def test_estado_estragado_conta_como_sem_envio(pastas):
    (pastas[1] / bd.NOME_DO_ESTADO).write_text("{ nao e json", encoding="utf-8")

    assert bd.ler_ultimo_envio(pastas[1]) is None


# ------------------------------------------------------------------ dentro do agendador (app/backup_agendado.py)


class _Relogio:
    def __init__(self, inicio):
        self.agora = inicio
        self.dormidas = []

    def __call__(self):
        return self.agora

    def dormir(self, segundos):
        self.dormidas.append(segundos)
        self.agora += timedelta(seconds=segundos)


class _DriveDeMentira:
    """Tem os mesmos métodos de bd.EnvioAoDrive. `erros` = o que levantar em cada chamada (None = dá certo)."""

    def __init__(self, configurado=True, atrasado=True, erros=()):
        self._configurado, self._atrasado, self.erros = configurado, atrasado, list(erros)
        self.enviadas = []

    def configurado(self):
        return self._configurado

    def atrasado(self, agora, idade_maxima):
        return self._atrasado

    def verificar(self, agora, idade_maxima):
        return False, "Nenhum envio ao Drive registrado."

    def enviar(self, copia):
        self.enviadas.append(copia.name)
        erro = self.erros.pop(0) if self.erros else None
        if erro is not None:
            raise erro
        return "app-teste.gfbk"


AGORA = datetime(2026, 10, 19, 23, 15, tzinfo=UTC)  # segunda 20:15 em Vila Velha


def _rodar(banco, pastas, drive, ciclos, relogio=None):
    relogio = relogio or _Relogio(AGORA)
    ag.rodar(
        banco, pastas[1], 30, relogio=relogio, dormir=relogio.dormir, ciclos=ciclos, drive=drive,
        fazer=lambda b, p, g: fazer_backup(b, p, g, agora=relogio()),
    )
    return relogio


def test_depois_de_cada_copia_das_3h_a_copia_nova_vai_ao_drive(banco, pastas):
    drive = _DriveDeMentira(atrasado=False)

    _rodar(banco, pastas, drive, ciclos=2)

    assert drive.enviadas == ["app-2026-10-20-060000.db", "app-2026-10-21-060000.db"]  # na partida não: não estava atrasado


def test_ao_ligar_com_envio_atrasado_manda_a_copia_local_mais_nova(banco, pastas):
    drive = _DriveDeMentira(atrasado=True)

    _rodar(banco, pastas, drive, ciclos=0)

    assert drive.enviadas == ["app-2026-10-19-231500.db"]  # a copia feita agora, na partida


def test_ao_ligar_sem_copia_nenhuma_e_com_envio_em_dia_nao_manda_nada(banco, pastas):
    drive = _DriveDeMentira(atrasado=False)

    _rodar(banco, pastas, drive, ciclos=0)

    assert drive.enviadas == []


def test_sem_configuracao_nao_chama_o_drive(banco, pastas):
    drive = _DriveDeMentira(configurado=False)

    _rodar(banco, pastas, drive, ciclos=2)

    assert drive.enviadas == []


def test_sem_drive_nenhum_tudo_funciona_como_antes(banco, pastas):
    _rodar(banco, pastas, None, ciclos=2)

    assert len(list(pastas[1].glob("app-*.db"))) == 3


def test_envio_que_falha_tenta_4_vezes_de_hora_em_hora_e_nao_atrapalha_as_copias(banco, pastas, capsys):
    erro = bd.DriveFalhou("O Google recusou: teste.", "HTTP 500 detalhe")
    drive = _DriveDeMentira(atrasado=False, erros=[erro] * 4)

    relogio = _rodar(banco, pastas, drive, ciclos=2)

    assert len(drive.enviadas) == 4 + 1  # 4 tentativas na copia de terca + 1 (deu certo) na de quarta
    saida = capsys.readouterr().err
    assert saida.count("ENVIO AO DRIVE FALHOU") == 4
    assert "tentativa 1 de 4" in saida and "tentativa 4 de 4" in saida and "HTTP 500 detalhe" in saida
    assert relogio.dormidas.count(3600) == 3  # uma hora entre as 4 tentativas (e nao depois da ultima)
    assert len(list(pastas[1].glob("app-*.db"))) == 3  # as cópias locais seguiram: a da partida e as duas diárias


def test_defeito_inesperado_no_envio_nao_derruba_o_laco_e_nao_vaza_a_mensagem(banco, pastas, capsys):
    drive = _DriveDeMentira(atrasado=False, erros=[RuntimeError(f"segredo {SENHA}")] * 4)

    _rodar(banco, pastas, drive, ciclos=1)

    saida = capsys.readouterr().err
    assert "erro inesperado: RuntimeError" in saida and SENHA not in saida
    assert len(list(pastas[1].glob("app-2026-10-20-060000.db"))) == 1  # a copia local foi feita


def test_configuracao_que_some_no_meio_do_envio_e_silenciosa(banco, pastas, capsys):
    drive = _DriveDeMentira(atrasado=False, erros=[bd.NaoConfigurado("x")])

    _rodar(banco, pastas, drive, ciclos=1)

    assert "FALHOU" not in capsys.readouterr().err and len(drive.enviadas) == 1


def test_verificar_sem_drive_configurado_olha_so_a_copia_local(pastas):
    (pastas[1] / "app-2026-10-20-060000.db").write_bytes(b"x")
    agora = TERCA_3H + timedelta(hours=2)

    assert ag.verificar(pastas[1], agora, drive=_DriveDeMentira(configurado=False))[0]
    assert ag.verificar(pastas[1], agora)[0]


def test_verificar_com_drive_configurado_exige_envio_recente(pastas, arquivo_de_credenciais):
    (pastas[1] / "app-2026-10-20-060000.db").write_bytes(b"x")
    agora = TERCA_3H + timedelta(hours=2)
    envio = bd.EnvioAoDrive(arquivo_de_credenciais, pastas[1])

    ok, mensagem = ag.verificar(pastas[1], agora, drive=envio)
    assert not ok and "Nenhum envio ao Drive" in mensagem

    bd.registrar_envio(pastas[1], TERCA_3H, "app-2026-10-20-060000.db", "app-terca.gfbk")
    ok, mensagem = ag.verificar(pastas[1], agora, drive=envio)
    assert ok and "Cópia mais nova" in mensagem and "Último envio ao Drive" in mensagem


def test_verificar_enxerga_o_drive_pelo_caminho_do_banco(pastas, arquivo_de_credenciais, banco):
    (pastas[1] / "app-2026-10-20-060000.db").write_bytes(b"x")
    ok, mensagem = ag.verificar(pastas[1], TERCA_3H + timedelta(hours=1), drive=bd.EnvioAoDrive(bd.caminho_da_configuracao(banco), pastas[1]))

    assert not ok and "Nenhum envio ao Drive" in mensagem


# ------------------------------------------------------------------ comandos do terminal


class _Digitacao:
    """Responde aos pedidos de texto e de segredo na ordem em que vierem. Guarda o que foi perguntado."""

    def __init__(self, textos=(), segredos=()):
        self.textos, self.segredos, self.perguntas = list(textos), list(segredos), []

    def texto(self, pergunta):
        self.perguntas.append(pergunta)
        return self.textos.pop(0)

    def segredo(self, pergunta):
        self.perguntas.append(pergunta)
        return self.segredos.pop(0)


def _configurar(banco, pastas, google, digitacao):
    relogio = _RelogioDeMentira()
    return bd.main(
        ["--banco", str(banco), "--pasta", str(pastas[1]), "configurar"],
        enderecos=google.enderecos, pedir_texto=digitacao.texto, pedir_segredo=digitacao.segredo, dormir=relogio.dormir, relogio=relogio,
    )


def _nenhum_segredo(texto):
    for segredo in (CLIENT_SECRET, SENHA, REFRESH_TOKEN, TOKEN_DE_ACESSO, DEVICE_CODE):
        assert segredo not in texto


def test_configurar_de_ponta_a_ponta_autoriza_cria_a_pasta_guarda_e_faz_o_primeiro_envio(banco, copia, pastas, google, capsys):
    digitacao = _Digitacao(textos=[CLIENT_ID], segredos=[CLIENT_SECRET, SENHA, SENHA])

    codigo = _configurar(banco, pastas, google, digitacao)

    saida = capsys.readouterr()
    assert codigo == 0
    assert "https://www.google.com/device" in saida.out and "ABCD-EFGH" in saida.out  # o que o Thiago digita no celular
    _nenhum_segredo(saida.out + saida.err)
    guardada = bd.ler_configuracao(pastas[0] / bd.NOME_DO_ARQUIVO)
    assert (guardada.client_id, guardada.refresh_token, guardada.senha) == (CLIENT_ID, REFRESH_TOKEN, SENHA)
    assert guardada.pasta_id in google.pastas and guardada.pasta_id != PASTA_ID  # a pasta foi criada agora
    assert stat.S_IMODE((pastas[0] / bd.NOME_DO_ARQUIVO).stat().st_mode) == 0o600
    assert "Enviado: app-terca.gfbk" in saida.out
    assert [a["nome"] for a in google.arquivos.values()] == ["app-terca.gfbk"]
    assert bd.ler_ultimo_envio(pastas[1]) is not None


def test_configurar_sem_copia_local_avisa_que_o_primeiro_envio_sera_depois_das_3h(banco, pastas, google, capsys):
    codigo = _configurar(banco, pastas, google, _Digitacao(textos=[CLIENT_ID], segredos=[CLIENT_SECRET, SENHA, SENHA]))

    assert codigo == 0
    assert "próxima cópia" in capsys.readouterr().out
    assert google.arquivos == {} and bd.configurado(pastas[0] / bd.NOME_DO_ARQUIVO)


@pytest.mark.parametrize("senhas", [["curta", "curta"], [SENHA, SENHA + "!"]])
def test_configurar_recusa_senha_curta_ou_diferente_sem_falar_com_o_google(banco, pastas, google, capsys, senhas):
    codigo = _configurar(banco, pastas, google, _Digitacao(textos=[CLIENT_ID], segredos=[CLIENT_SECRET, *senhas]))

    assert codigo == 1
    assert "Nada foi alterado" in capsys.readouterr().out
    assert google.pedidos == [] and not (pastas[0] / bd.NOME_DO_ARQUIVO).exists()


def test_configurar_recusa_id_do_cliente_com_cara_errada(banco, pastas, google, capsys):
    codigo = _configurar(banco, pastas, google, _Digitacao(textos=["isto nao e um id"], segredos=[CLIENT_SECRET, SENHA, SENHA]))

    assert codigo == 1 and google.pedidos == []
    _nenhum_segredo(capsys.readouterr().out)


def test_configurar_com_autorizacao_recusada_nao_grava_nada(banco, pastas, google, capsys):
    google.forcadas.append(("POST", "/token", 403, {"error": "access_denied"}))

    codigo = _configurar(banco, pastas, google, _Digitacao(textos=[CLIENT_ID], segredos=[CLIENT_SECRET, SENHA, SENHA]))

    saida = capsys.readouterr().out
    assert codigo == 1 and "recusada" in saida and "Nada foi alterado" in saida
    assert not (pastas[0] / bd.NOME_DO_ARQUIVO).exists()
    _nenhum_segredo(saida)


def test_configurar_de_novo_lembra_de_usar_a_mesma_senha(banco, arquivo_de_credenciais, pastas, google, capsys):
    _configurar(banco, pastas, google, _Digitacao(textos=[CLIENT_ID], segredos=[CLIENT_SECRET, SENHA, SENHA]))

    assert "MESMA senha" in capsys.readouterr().out


def test_situacao_nunca_mostra_segredo(banco, arquivo_de_credenciais, pastas, capsys):
    bd.registrar_envio(pastas[1], TERCA_3H, "app-2026-10-20-060000.db", "app-terca.gfbk")

    codigo = bd.main(["--banco", str(banco), "--pasta", str(pastas[1]), "situacao"])

    saida = capsys.readouterr().out
    assert codigo == 0 and "configurado" in saida and "NÃO" not in saida
    assert "20/10/2026 03:00" in saida and "app-terca.gfbk" in saida
    _nenhum_segredo(saida)


def test_situacao_sem_configuracao_diz_o_que_fazer(banco, pastas, capsys):
    bd.main(["--banco", str(banco), "--pasta", str(pastas[1]), "situacao"])

    saida = capsys.readouterr().out
    assert "NÃO configurado" in saida and "configurar" in saida and "nenhum registrado" in saida


def test_enviar_agora_manda_a_copia_local_mais_nova(banco, copia, arquivo_de_credenciais, pastas, google, capsys):
    codigo = bd.main(["--banco", str(banco), "--pasta", str(pastas[1]), "enviar-agora"], enderecos=google.enderecos)

    assert codigo == 0 and "Enviado: app-terca.gfbk" in capsys.readouterr().out
    assert len(google.arquivos) == 1


def test_enviar_agora_sem_copia_ou_sem_configuracao_diz_o_que_falta(banco, copia, pastas, google, capsys):
    assert bd.main(["--banco", str(banco), "--pasta", str(pastas[1]), "enviar-agora"], enderecos=google.enderecos) == 1
    assert "configurar" in capsys.readouterr().out

    assert bd.main(["--banco", str(banco), "--pasta", str(pastas[1] / "vazia"), "enviar-agora"], enderecos=google.enderecos) == 1
    assert "nenhuma cópia" in capsys.readouterr().out
    assert google.pedidos == []


def test_descriptografar_devolve_o_banco_original_so_para_o_dono(copia, tmp_path, capsys):
    baixado = tmp_path / "app-terca.gfbk"
    baixado.write_bytes(bd.criptografar(copia.read_bytes(), SENHA))
    saida_db = tmp_path / "restaurado.db"

    codigo = bd.main(["descriptografar", str(baixado), str(saida_db)], pedir_segredo=lambda _pergunta: SENHA)

    assert codigo == 0 and saida_db.read_bytes() == copia.read_bytes()
    assert stat.S_IMODE(saida_db.stat().st_mode) == 0o600
    _nenhum_segredo(capsys.readouterr().out)


def test_descriptografar_com_senha_errada_nao_grava_nada(copia, tmp_path, capsys):
    baixado = tmp_path / "app-terca.gfbk"
    baixado.write_bytes(bd.criptografar(copia.read_bytes(), SENHA))

    codigo = bd.main(["descriptografar", str(baixado), str(tmp_path / "restaurado.db")], pedir_segredo=lambda _pergunta: SENHA + "x")

    assert codigo == 1 and "Senha errada" in capsys.readouterr().out
    assert not (tmp_path / "restaurado.db").exists()


def test_descriptografar_nao_sobrescreve_arquivo_que_ja_existe(copia, tmp_path, capsys):
    baixado = tmp_path / "app-terca.gfbk"
    baixado.write_bytes(bd.criptografar(copia.read_bytes(), SENHA))
    existente = tmp_path / "restaurado.db"
    existente.write_bytes(b"importante")

    codigo = bd.main(["descriptografar", str(baixado), str(existente)], pedir_segredo=lambda _pergunta: SENHA)

    assert codigo == 1 and existente.read_bytes() == b"importante"


def test_descriptografar_recusa_conteudo_que_nao_e_banco(tmp_path, capsys):
    baixado = tmp_path / "lixo.gfbk"
    baixado.write_bytes(bd.criptografar(b"isto nao e um banco", SENHA))

    codigo = bd.main(["descriptografar", str(baixado), str(tmp_path / "saida.db")], pedir_segredo=lambda _pergunta: SENHA)

    assert codigo == 1 and not (tmp_path / "saida.db").exists()
    assert "não é um banco" in capsys.readouterr().out
