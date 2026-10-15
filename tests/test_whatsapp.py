"""Testes do envio do código pelo WhatsApp (app/whatsapp.py): a mensagem, o arquivo de configuração, a conversa com a Meta
(contra um servidor de mentira na própria máquina) e os comandos do terminal do servidor."""

import json
import os
import stat
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app import aluno_acesso, whatsapp
from app.db import conectar, criar_tabelas

TOKEN = "EAAGm0PX4ZCpsBO" + "x" * 60  # parece um token da Meta; não é de verdade
NUMERO_DO_REMETENTE = "109876543210987"
TELEFONE = "5527988887766"


def _configuracao(**extras):
    return whatsapp.Configuracao(NUMERO_DO_REMETENTE, TOKEN, **extras)


# ------------------------------------------------------------------ a mensagem


def test_corpo_da_mensagem_e_o_do_modelo_de_autenticacao_com_o_codigo_no_texto_e_no_botao():
    assert whatsapp.corpo_da_mensagem(TELEFONE, "123456") == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "5527988887766",
        "type": "template",
        "template": {
            "name": "codigo_acesso_app",
            "language": {"code": "pt_BR"},
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": "123456"}]},
                {"type": "button", "sub_type": "url", "index": "0", "parameters": [{"type": "text", "text": "123456"}]},
            ],
        },
    }


@pytest.mark.parametrize("telefone", ["", "27988887766", "5527", "55279888877661234", "55abc88887766", "+5527988887766", "5527988887766 "])
def test_telefone_fora_do_formato_nao_e_enviado(telefone):
    with pytest.raises(ValueError):
        whatsapp.corpo_da_mensagem(telefone, "123456")


@pytest.mark.parametrize("codigo", ["", "1234567890123456", "12 34", "12-34", "é12345"])
def test_codigo_fora_do_formato_nao_e_enviado(codigo):
    with pytest.raises(ValueError):
        whatsapp.corpo_da_mensagem(TELEFONE, codigo)


@pytest.mark.parametrize("whatsapp_do_app, esperado", [("27988887766", "5527988887766"), ("2733334444", "552733334444")])
def test_telefone_para_a_meta_poe_o_55_na_frente(whatsapp_do_app, esperado):
    assert whatsapp.telefone_para_a_meta(whatsapp_do_app) == esperado


@pytest.mark.parametrize("numero", ["", "988887766", "279888877661", "27 98888 7766", "2798888776a"])
def test_numero_do_app_fora_do_formato_levanta_erro(numero):
    with pytest.raises(ValueError):
        whatsapp.telefone_para_a_meta(numero)


# ------------------------------------------------------------------ o arquivo de configuração


def test_configuracao_aceita_o_que_tem_cara_de_verdadeiro():
    configuracao = whatsapp.validar_configuracao(f" {NUMERO_DO_REMETENTE} ", f" {TOKEN} ", "v24.0")

    assert configuracao == _configuracao(versao_da_api="v24.0")


@pytest.mark.parametrize(
    "numero, token, versao",
    [
        ("", TOKEN, "v24.0"),
        ("12ab", TOKEN, "v24.0"),
        ("1234567", TOKEN, "v24.0"),  # curto demais
        (None, TOKEN, "v24.0"),
        (NUMERO_DO_REMETENTE, "curto", "v24.0"),
        (NUMERO_DO_REMETENTE, TOKEN + " com espaço", "v24.0"),
        (NUMERO_DO_REMETENTE, TOKEN + "\n" + TOKEN, "v24.0"),
        (NUMERO_DO_REMETENTE, "açúcar" * 10, "v24.0"),
        (NUMERO_DO_REMETENTE, None, "v24.0"),
        (NUMERO_DO_REMETENTE, TOKEN, "24"),
        (NUMERO_DO_REMETENTE, TOKEN, "v24"),
        (NUMERO_DO_REMETENTE, TOKEN, "../v24.0"),
        (NUMERO_DO_REMETENTE, TOKEN, None),
    ],
)
def test_configuracao_que_nao_serve_e_recusada_sem_repetir_o_que_foi_digitado(numero, token, versao):
    with pytest.raises(ValueError) as erro:
        whatsapp.validar_configuracao(numero, token, versao)

    assert TOKEN not in str(erro.value)


def test_o_token_nao_aparece_quando_o_objeto_e_impresso():
    assert TOKEN not in repr(_configuracao()) and TOKEN not in str(_configuracao())


def test_guardar_e_ler_a_configuracao_com_permissao_so_do_dono(tmp_path):
    arquivo = tmp_path / "whatsapp.json"

    whatsapp.guardar_configuracao(arquivo, _configuracao(versao_da_api="v24.0"))

    assert stat.S_IMODE(os.stat(arquivo).st_mode) == 0o600
    assert whatsapp.ler_configuracao(arquivo) == _configuracao(versao_da_api="v24.0")
    assert whatsapp.configurado(arquivo) is True
    assert list(tmp_path.iterdir()) == [arquivo]  # o arquivo temporário não ficou para trás


def test_guardar_de_novo_troca_o_arquivo_inteiro(tmp_path):
    arquivo = tmp_path / "whatsapp.json"
    whatsapp.guardar_configuracao(arquivo, _configuracao())

    whatsapp.guardar_configuracao(arquivo, whatsapp.Configuracao("11111111111", "t" * 30, "v25.0"))

    assert whatsapp.ler_configuracao(arquivo).numero_do_remetente == "11111111111"
    assert stat.S_IMODE(os.stat(arquivo).st_mode) == 0o600


def test_nao_grava_configuracao_que_nao_serve(tmp_path):
    arquivo = tmp_path / "whatsapp.json"

    with pytest.raises(ValueError):
        whatsapp.guardar_configuracao(arquivo, whatsapp.Configuracao("abc", TOKEN))

    assert not arquivo.exists() and list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("conteudo", [None, "", "isto não é json", "[]", "null", '{"numero_do_remetente": "1"}', '{"token": "x"}', b"\xff\xfe\x00"])
def test_arquivo_ausente_ou_estragado_conta_como_nao_configurado(tmp_path, conteudo):
    arquivo = tmp_path / "whatsapp.json"
    if isinstance(conteudo, bytes):
        arquivo.write_bytes(conteudo)
    elif conteudo is not None:
        arquivo.write_text(conteudo, encoding="utf-8")

    with pytest.raises(whatsapp.NaoConfigurado) as erro:
        whatsapp.ler_configuracao(arquivo)

    assert whatsapp.configurado(arquivo) is False
    assert (str(conteudo) not in str(erro.value)) or not conteudo


def test_versao_padrao_quando_o_arquivo_nao_diz(tmp_path):
    arquivo = tmp_path / "whatsapp.json"
    arquivo.write_text(json.dumps({"numero_do_remetente": NUMERO_DO_REMETENTE, "token": TOKEN}), encoding="utf-8")

    assert whatsapp.ler_configuracao(arquivo).versao_da_api == whatsapp.VERSAO_PADRAO_DA_API


def test_o_arquivo_fica_ao_lado_do_banco_ou_onde_a_variavel_mandar(tmp_path, monkeypatch):
    monkeypatch.delenv(whatsapp.VARIAVEL_DO_ARQUIVO, raising=False)
    assert whatsapp.caminho_da_configuracao(tmp_path / "dados" / "app.db") == tmp_path / "dados" / "whatsapp.json"

    monkeypatch.setenv(whatsapp.VARIAVEL_DO_ARQUIVO, str(tmp_path / "outro.json"))
    assert whatsapp.caminho_da_configuracao(tmp_path / "dados" / "app.db") == tmp_path / "outro.json"


# ------------------------------------------------------------------ falar com a Meta (servidor de mentira)


class _Meta(BaseHTTPRequestHandler):
    """Servidor de mentira: guarda cada pedido recebido e responde o que o teste combinou (`respostas`, uma por pedido)."""

    def do_POST(self):
        tamanho = int(self.headers.get("Content-Length", 0))
        self.server.pedidos.append(
            {"caminho": self.path, "cabecalhos": dict(self.headers), "corpo": json.loads(self.rfile.read(tamanho) or b"null")}
        )
        status, corpo, cabecalhos = self.server.respostas.pop(0) if self.server.respostas else (200, {"messages": [{"id": "wamid.PADRAO"}]}, {})
        dados = json.dumps(corpo).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        for nome, valor in cabecalhos.items():
            self.send_header(nome, valor)
        self.end_headers()
        self.wfile.write(dados)

    def log_message(self, *_args):  # sem barulho no terminal dos testes
        pass


@pytest.fixture
def meta():
    servidor = HTTPServer(("127.0.0.1", 0), _Meta)
    servidor.pedidos = []
    servidor.respostas = []
    servidor.url = f"http://127.0.0.1:{servidor.server_port}"
    fio = threading.Thread(target=servidor.serve_forever, daemon=True)
    fio.start()
    yield servidor
    servidor.shutdown()
    servidor.server_close()


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(whatsapp, "_dormir", lambda _segundos: None)


def test_envio_vai_para_o_endereco_certo_com_o_token_e_devolve_o_id_da_mensagem(meta):
    meta.respostas.append((200, {"messaging_product": "whatsapp", "messages": [{"id": "wamid.ABC123"}]}, {}))

    identificador = whatsapp.enviar_codigo(_configuracao(), TELEFONE, "654321", url_base=meta.url)

    assert identificador == "wamid.ABC123"
    assert len(meta.pedidos) == 1
    pedido = meta.pedidos[0]
    assert pedido["caminho"] == f"/v24.0/{NUMERO_DO_REMETENTE}/messages"
    assert pedido["cabecalhos"]["Authorization"] == f"Bearer {TOKEN}"
    assert pedido["cabecalhos"]["Content-Type"] == "application/json"
    assert pedido["corpo"] == whatsapp.corpo_da_mensagem(TELEFONE, "654321")


def test_a_versao_da_api_vem_da_configuracao(meta):
    whatsapp.enviar_codigo(_configuracao(versao_da_api="v99.1"), TELEFONE, "654321", url_base=meta.url)

    assert meta.pedidos[0]["caminho"].startswith("/v99.1/")


def test_resposta_200_sem_id_ainda_conta_como_aceita(meta):
    meta.respostas.append((200, {"ok": True}, {}))
    meta.respostas.append((200, {"messages": []}, {}))

    assert whatsapp.enviar_codigo(_configuracao(), TELEFONE, "654321", url_base=meta.url) == ""
    assert whatsapp.enviar_codigo(_configuracao(), TELEFONE, "654321", url_base=meta.url) == ""


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429])
def test_erro_do_nosso_lado_nao_se_repete(meta, status):
    meta.respostas.append((status, {"error": {"message": "Recusado", "type": "OAuthException", "code": 190, "error_subcode": 463}}, {}))

    with pytest.raises(whatsapp.EnvioFalhou) as erro:
        whatsapp.enviar_codigo(_configuracao(), TELEFONE, "654321", url_base=meta.url)

    assert len(meta.pedidos) == 1
    assert f"HTTP {status}" in erro.value.detalhe
    assert "OAuthException código=190 subcódigo=463: Recusado" in erro.value.detalhe


def test_erro_de_token_tem_uma_mensagem_clara(meta):
    meta.respostas.append((401, {"error": {"message": "Error validating access token", "code": 190}}, {}))

    with pytest.raises(whatsapp.EnvioFalhou) as erro:
        whatsapp.enviar_codigo(_configuracao(), TELEFONE, "654321", url_base=meta.url)

    assert "token" in erro.value.mensagem.lower()


def test_erro_do_lado_da_meta_tenta_mais_uma_vez(meta):
    meta.respostas.append((503, {"error": {"message": "Indisponível"}}, {}))
    meta.respostas.append((200, {"messages": [{"id": "wamid.SEGUNDA"}]}, {}))

    assert whatsapp.enviar_codigo(_configuracao(), TELEFONE, "654321", url_base=meta.url) == "wamid.SEGUNDA"
    assert len(meta.pedidos) == 2


def test_erro_do_lado_da_meta_que_persiste_desiste_depois_de_duas_tentativas(meta):
    meta.respostas.extend([(500, {"error": {"message": "Falhou 1"}}, {}), (500, {"error": {"message": "Falhou 2"}}, {})])

    with pytest.raises(whatsapp.EnvioFalhou) as erro:
        whatsapp.enviar_codigo(_configuracao(), TELEFONE, "654321", url_base=meta.url)

    assert len(meta.pedidos) == whatsapp.TENTATIVAS_DA_CHAMADA == 2
    assert "Falhou 2" in erro.value.detalhe


def test_a_mensagem_de_erro_da_meta_nao_vaza_o_token_nem_o_numero(meta):
    meta.respostas.append((400, {"error": {"message": f"Token {TOKEN} inválido para {TELEFONE} e 27988887766", "code": 1}}, {}))

    with pytest.raises(whatsapp.EnvioFalhou) as erro:
        whatsapp.enviar_codigo(_configuracao(), TELEFONE, "654321", url_base=meta.url)

    for segredo in (TOKEN, TELEFONE, "27988887766"):
        assert segredo not in erro.value.detalhe and segredo not in erro.value.mensagem
    assert "***" in erro.value.detalhe


def test_resposta_de_erro_que_nao_e_json_nao_derruba(meta):
    class Quebrado(_Meta):
        def do_POST(self):
            self.send_response(400)
            self.send_header("Content-Length", "9")
            self.end_headers()
            self.wfile.write(b"<html>!!!")

    meta.RequestHandlerClass = Quebrado

    with pytest.raises(whatsapp.EnvioFalhou) as erro:
        whatsapp.enviar_codigo(_configuracao(), TELEFONE, "654321", url_base=meta.url)

    assert "HTTP 400" in erro.value.detalhe


def test_redirecionamento_nao_e_seguido_e_o_token_nao_vai_para_outro_endereco(meta):
    outro = HTTPServer(("127.0.0.1", 0), _Meta)
    outro.pedidos, outro.respostas = [], []
    fio = threading.Thread(target=outro.serve_forever, daemon=True)
    fio.start()
    try:
        meta.respostas.append((302, {}, {"Location": f"http://127.0.0.1:{outro.server_port}/roubo"}))

        with pytest.raises(whatsapp.EnvioFalhou) as erro:
            whatsapp.enviar_codigo(_configuracao(), TELEFONE, "654321", url_base=meta.url)

        assert "redirecionamento" in erro.value.mensagem
        assert outro.pedidos == []  # o segundo servidor nunca recebeu nada, muito menos o token
        assert len(meta.pedidos) == 1
    finally:
        outro.shutdown()
        outro.server_close()


def test_sem_rede_vira_envio_falhou_sem_o_token(meta):
    endereco_morto = meta.url
    meta.shutdown()
    meta.server_close()

    with pytest.raises(whatsapp.EnvioFalhou) as erro:
        whatsapp.enviar_codigo(_configuracao(), TELEFONE, "654321", tempo_limite=2, url_base=endereco_morto)

    assert "rede" in erro.value.detalhe
    assert TOKEN not in erro.value.detalhe and TELEFONE not in erro.value.detalhe


def test_o_endereco_padrao_da_meta_e_https():
    assert whatsapp.URL_BASE == "https://graph.facebook.com"


# ------------------------------------------------------------------ o Remetente (o que o app usa)


def test_remetente_so_esta_pronto_com_a_configuracao_no_lugar(tmp_path):
    arquivo = tmp_path / "whatsapp.json"
    remetente = whatsapp.Remetente(arquivo)
    assert remetente.pronto() is False

    whatsapp.guardar_configuracao(arquivo, _configuracao())  # configurar com o app já no ar: vale na hora, sem reiniciar

    assert remetente.pronto() is True


def test_remetente_sem_configuracao_levanta_nao_configurado(tmp_path):
    with pytest.raises(whatsapp.NaoConfigurado):
        whatsapp.Remetente(tmp_path / "whatsapp.json").enviar("27988887766", "123456")


def test_remetente_manda_o_numero_do_app_com_o_55(tmp_path, meta):
    arquivo = tmp_path / "whatsapp.json"
    whatsapp.guardar_configuracao(arquivo, _configuracao())

    identificador = whatsapp.Remetente(arquivo, url_base=meta.url).enviar("27988887766", "123456")

    assert identificador == "wamid.PADRAO"
    assert meta.pedidos[0]["corpo"]["to"] == "5527988887766"


# ------------------------------------------------------------------ terminal do servidor


def _banco(tmp_path):
    caminho = tmp_path / "app.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.close()
    return caminho


def test_configurar_guarda_o_arquivo_e_nunca_mostra_o_token(tmp_path, capsys):
    banco = _banco(tmp_path)

    resultado = whatsapp.main(["configurar", "--banco", str(banco)], pedir_numero=lambda _p: NUMERO_DO_REMETENTE, pedir_token=lambda _p: TOKEN)

    saida = capsys.readouterr()
    assert resultado == 0
    assert TOKEN not in saida.out + saida.err
    configuracao = whatsapp.ler_configuracao(tmp_path / "whatsapp.json")
    assert (configuracao.numero_do_remetente, configuracao.token, configuracao.versao_da_api) == (NUMERO_DO_REMETENTE, TOKEN, "v24.0")


def test_configurar_com_dado_ruim_nao_mexe_em_nada(tmp_path, capsys):
    banco = _banco(tmp_path)
    whatsapp.guardar_configuracao(tmp_path / "whatsapp.json", _configuracao())
    antes = (tmp_path / "whatsapp.json").read_text(encoding="utf-8")

    resultado = whatsapp.main(["configurar", "--banco", str(banco)], pedir_numero=lambda _p: "abc", pedir_token=lambda _p: "token ruim")

    assert resultado == 1
    assert "Nada foi alterado" in capsys.readouterr().out
    assert (tmp_path / "whatsapp.json").read_text(encoding="utf-8") == antes


def test_configurar_de_novo_mantem_a_versao_que_ja_estava(tmp_path):
    banco = _banco(tmp_path)
    whatsapp.guardar_configuracao(tmp_path / "whatsapp.json", _configuracao(versao_da_api="v25.0"))

    whatsapp.main(["configurar", "--banco", str(banco)], pedir_numero=lambda _p: NUMERO_DO_REMETENTE, pedir_token=lambda _p: TOKEN)
    assert whatsapp.ler_configuracao(tmp_path / "whatsapp.json").versao_da_api == "v25.0"

    whatsapp.main(["configurar", "--versao", "v26.0", "--banco", str(banco)], pedir_numero=lambda _p: NUMERO_DO_REMETENTE, pedir_token=lambda _p: TOKEN)
    assert whatsapp.ler_configuracao(tmp_path / "whatsapp.json").versao_da_api == "v26.0"


def test_situacao_sem_configuracao(tmp_path, capsys):
    banco = _banco(tmp_path)

    assert whatsapp.main(["situacao", "--banco", str(banco)]) == 0

    saida = capsys.readouterr().out
    assert "NÃO configurado" in saida and "python -m app.whatsapp configurar" in saida
    assert "Códigos nas últimas 24 h: 0" in saida


def test_situacao_configurada_mostra_o_remetente_mas_nunca_o_token(tmp_path, capsys):
    banco = _banco(tmp_path)
    whatsapp.guardar_configuracao(tmp_path / "whatsapp.json", _configuracao())

    whatsapp.main(["situacao", "--banco", str(banco)])

    saida = capsys.readouterr().out
    assert "configurado" in saida and "NÃO" not in saida
    assert NUMERO_DO_REMETENTE in saida and "token guardado" in saida
    assert TOKEN not in saida


def test_situacao_mostra_as_falhas_de_envio_do_banco(tmp_path, capsys):
    banco = _banco(tmp_path)
    conn = conectar(banco)
    conn.execute("INSERT INTO aluno (id, nome, cpf, whatsapp, situacao) VALUES (1, 'ANA', '11144477735', '27988887766', 'A')")
    agora = aluno_acesso._texto(aluno_acesso._agora(None))
    conn.execute(
        "INSERT INTO aluno_codigo (aluno_id, codigo_hash, criado_em, expira_em, envio, envio_erro) VALUES (1, 'h', ?, ?, 'falhou', 'HTTP 401 token vencido')",
        (agora, agora),
    )
    conn.commit()
    conn.close()

    whatsapp.main(["situacao", "--banco", str(banco)])

    saida = capsys.readouterr().out
    assert "falharam 1" in saida and "HTTP 401 token vencido" in saida


def test_testar_manda_o_codigo_000000_para_o_numero_dado(tmp_path, capsys, monkeypatch, meta):
    banco = _banco(tmp_path)
    whatsapp.guardar_configuracao(tmp_path / "whatsapp.json", _configuracao())
    monkeypatch.setattr(whatsapp, "URL_BASE", meta.url)
    monkeypatch.setattr(whatsapp.Remetente.__init__, "__defaults__", (meta.url,))  # url_base padrão do Remetente

    resultado = whatsapp.main(["testar", "(27) 98888-7766", "--banco", str(banco)])

    assert resultado == 0
    assert meta.pedidos[0]["corpo"]["to"] == "5527988887766"
    assert meta.pedidos[0]["corpo"]["template"]["components"][0]["parameters"][0]["text"] == "000000"
    assert "A Meta aceitou" in capsys.readouterr().out


def test_testar_sem_configuracao_orienta(tmp_path, capsys):
    banco = _banco(tmp_path)

    assert whatsapp.main(["testar", "27988887766", "--banco", str(banco)]) == 1

    assert "configurar" in capsys.readouterr().out


def test_testar_com_numero_ruim_nao_envia_nada(tmp_path, capsys):
    banco = _banco(tmp_path)

    assert whatsapp.main(["testar", "123", "--banco", str(banco)]) == 2


def test_testar_mostra_o_motivo_quando_a_meta_recusa(tmp_path, capsys, monkeypatch, meta):
    banco = _banco(tmp_path)
    whatsapp.guardar_configuracao(tmp_path / "whatsapp.json", _configuracao())
    monkeypatch.setattr(whatsapp.Remetente.__init__, "__defaults__", (meta.url,))
    meta.respostas.append((401, {"error": {"message": "Error validating access token", "code": 190}}, {}))

    resultado = whatsapp.main(["testar", "27988887766", "--banco", str(banco)])

    saida = capsys.readouterr().out
    assert resultado == 1 and "FALHOU" in saida and "código=190" in saida
    assert TOKEN not in saida
