"""Cópia diária do banco para o Google Drive da academia (FORA do servidor), sempre criptografada.

Por que existe: as cópias de `/backups` ficam no mesmo servidor (ver app/backup_agendado.py). Se o servidor for perdido,
só sobra o backup semanal da Hostinger (até 7 dias de trabalho perdidos). Aqui, depois de cada cópia das 03:00, o mesmo
contêiner `backup` manda uma versão CRIPTOGRAFADA para uma pasta do Drive: no máximo 1 dia perdido.

Como funciona:

1. A cópia é criptografada ANTES de sair do servidor (Fernet: AES + assinatura, da biblioteca `cryptography`), com uma chave
   derivada de uma senha que só o Thiago sabe (scrypt, com sal sorteado por arquivo). Quem entrar na conta Google vê só lixo:
   a cópia tem nome e CPF de alunos. SEM A SENHA A CÓPIA DO DRIVE NÃO ABRE; guarde-a fora do servidor.
2. São 7 arquivos, um por dia da semana (`app-segunda.gfbk` ... `app-domingo.gfbk`): cada um é substituído uma vez por
   semana. Não há nada para apagar (e o Drive guarda versões antigas de um arquivo substituído por cerca de 30 dias).
3. O servidor fala com o Google por HTTPS direto (sem intermediário), com o escopo `drive.file`: ele só enxerga os arquivos que
   ELE criou (a pasta e os 7 arquivos), nunca o resto do Drive. A autorização é feita uma vez pelo "fluxo de dispositivo": o
   terminal mostra um código curto e o Thiago o digita no celular, na conta Google da academia (nenhuma senha do Google passa
   por aqui). O app guarda só o "refresh token" que o Google devolve.
4. As credenciais (ID e segredo do cliente, refresh token, senha da criptografia, id da pasta) ficam num ARQUIVO ao lado do
   banco (`/dados/drive_backup.json`, permissão 0600), nunca no banco, no código, no log ou em mensagem de erro.

Comandos (no terminal do contêiner `backup` ou `app`; quem digita é quem cuida do servidor, e os segredos não aparecem na tela):

    python -m app.backup_drive configurar        (autoriza o Google, cria a pasta, guarda tudo e faz o primeiro envio)
    python -m app.backup_drive situacao          (diz se está configurado e quando foi o último envio; nunca mostra segredo)
    python -m app.backup_drive enviar-agora      (manda a cópia local mais nova já, sem esperar as 03:00)
    python -m app.backup_drive descriptografar app-terca.gfbk restaurado.db     (abre uma cópia baixada do Drive)

Cuidados de segurança que este arquivo tem:
- Nenhum segredo vai para log, mensagem de erro ou tela; textos de erro do Google passam por uma limpeza.
- Só HTTPS para o Google e SEM seguir redirecionamento (senão o Python reenviaria o cabeçalho com o token a outro endereço).
- O arquivo de credenciais é gravado com 0600 e trocado de uma vez (nunca fica pela metade).
- Se o envio falhar, a cópia local das 03:00 continua sendo feita; o erro aparece no registro do contêiner (`ENVIO AO DRIVE
  FALHOU`) e, se passar de 30 h sem envio, o Docker marca o contêiner `backup` como "unhealthy" no painel.
"""

import argparse
import base64
import getpass
import hashlib
import http.client
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.alunos import FUSO_DA_ACADEMIA
from app.backup import PADRAO_DO_NOME

ESCOPO = "https://www.googleapis.com/auth/drive.file"
URL_DO_OAUTH = "https://oauth2.googleapis.com"
URL_DO_DRIVE = "https://www.googleapis.com"
NOME_DA_PASTA = "Backup do app Glória Fit"
DIAS_DA_SEMANA = ("segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo")  # 0 = segunda, como datetime.weekday()

NOME_DO_ARQUIVO = "drive_backup.json"
VARIAVEL_DO_ARQUIVO = "GLORIAFIT_ARQUIVO_DO_DRIVE"
NOME_DO_ESTADO = "drive-ultimo-envio.json"  # fica em /backups, ao lado das cópias; só diz quando foi o último envio

TEMPO_LIMITE_DAS_CHAMADAS = 30.0
TEMPO_LIMITE_DO_ENVIO = 300.0  # a cópia criptografada tem uns 13 MB
ESPERAS_ENTRE_TENTATIVAS = (3.0, 10.0)  # 3 tentativas no total, só para falha de rede e erro 5xx do Google
TAMANHO_MINIMO_DA_SENHA = 16

_FORMATO_DO_ID_DO_CLIENTE = re.compile(r"[A-Za-z0-9._\-]{10,200}")
_FORMATO_DO_SEGREDO_DO_CLIENTE = re.compile(r"[A-Za-z0-9_\-]{10,200}")
_FORMATO_DO_REFRESH_TOKEN = re.compile(r"[A-Za-z0-9_.\-/+]{20,2000}")
_FORMATO_DO_ID_DA_PASTA = re.compile(r"[A-Za-z0-9_\-]{10,200}")

CABECALHO_DO_ARQUIVO = b"GFBK1\n"  # identifica o formato: "Glória Fit BacKup, versão 1"
_TAMANHO_DO_SAL = 16
_PARAMETROS_DO_SCRYPT = {"n": 2**15, "r": 8, "p": 1, "maxmem": 64 * 1024 * 1024, "dklen": 32}
_CABECALHO_DO_SQLITE = b"SQLite format 3\x00"


class NaoConfigurado(Exception):
    """O servidor ainda não tem o arquivo de credenciais do Drive (ou ele não serve)."""


class DriveFalhou(Exception):
    """Não deu para guardar a cópia no Drive. `detalhe` é para o log e nunca tem segredo."""

    def __init__(self, mensagem: str, detalhe: str = ""):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.detalhe = detalhe


class ArquivoOuSenhaInvalidos(Exception):
    """O arquivo não é uma cópia do app, está danificado, ou a senha está errada (não dá para distinguir)."""


@dataclass(frozen=True)
class Enderecos:
    """Onde ficam o OAuth e o Drive do Google. Só os testes trocam (por um servidor de mentira na própria máquina)."""

    oauth: str = URL_DO_OAUTH
    drive: str = URL_DO_DRIVE


ENDERECOS_REAIS = Enderecos()


@dataclass(frozen=True)
class Configuracao:
    client_id: str
    client_secret: str = field(repr=False)  # repr=False: um print por engano não mostra segredo
    refresh_token: str = field(repr=False)
    senha: str = field(repr=False)
    pasta_id: str = ""


# ------------------------------------------------------------------ o arquivo de credenciais


def caminho_da_configuracao(caminho_banco: str | Path) -> Path:
    """Ao lado do banco (em produção /dados/drive_backup.json), ou onde a variável de ambiente mandar."""
    avulso = os.environ.get(VARIAVEL_DO_ARQUIVO, "").strip()
    return Path(avulso) if avulso else Path(caminho_banco).parent / NOME_DO_ARQUIVO


def validar_senha(senha: object) -> str:
    if not isinstance(senha, str) or len(senha) < TAMANHO_MINIMO_DA_SENHA or len(senha) > 200 or not senha.isprintable():
        raise ValueError(f"A senha precisa ter de {TAMANHO_MINIMO_DA_SENHA} a 200 caracteres, sem quebra de linha.")
    return senha


def validar_configuracao(client_id: object, client_secret: object, refresh_token: object, senha: object, pasta_id: object = "") -> Configuracao:
    """A configuração limpa, se tiver cara de verdadeira; senão ValueError (sem repetir o que foi digitado)."""
    if not isinstance(client_id, str) or not _FORMATO_DO_ID_DO_CLIENTE.fullmatch(client_id.strip()):
        raise ValueError("O ID do cliente não tem cara de um ID do Google (letras, números, ponto e hífen; sem espaço).")
    if not isinstance(client_secret, str) or not _FORMATO_DO_SEGREDO_DO_CLIENTE.fullmatch(client_secret.strip()):
        raise ValueError("O segredo do cliente não tem cara de um segredo do Google (letras, números, hífen ou sublinhado).")
    if not isinstance(refresh_token, str) or not _FORMATO_DO_REFRESH_TOKEN.fullmatch(refresh_token.strip()):
        raise ValueError("O refresh token do Google está num formato inesperado.")
    validar_senha(senha)
    if not isinstance(pasta_id, str) or (pasta_id and not _FORMATO_DO_ID_DA_PASTA.fullmatch(pasta_id.strip())):
        raise ValueError("O id da pasta do Drive está num formato inesperado.")
    return Configuracao(client_id.strip(), client_secret.strip(), refresh_token.strip(), senha, pasta_id.strip())  # type: ignore[arg-type]


def ler_configuracao(arquivo: Path) -> Configuracao:
    """As credenciais guardadas. Levanta NaoConfigurado se não há arquivo ou ele não serve (sem dizer o que tem dentro)."""
    nao_serve = NaoConfigurado("O servidor ainda não tem a configuração do Drive.")
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise nao_serve from None
    if not isinstance(dados, dict):
        raise nao_serve
    try:
        configuracao = validar_configuracao(
            dados.get("client_id"), dados.get("client_secret"), dados.get("refresh_token"), dados.get("senha"), dados.get("pasta_id", "")
        )
    except ValueError:
        raise nao_serve from None
    if not configuracao.pasta_id:
        raise nao_serve  # sem pasta ainda não dá para enviar: configurar foi interrompido
    return configuracao


def guardar_configuracao(arquivo: Path, configuracao: Configuracao) -> None:
    """Grava (só o dono do arquivo lê). Escreve num arquivo temporário e troca: nunca fica pela metade."""
    validar_configuracao(
        configuracao.client_id, configuracao.client_secret, configuracao.refresh_token, configuracao.senha, configuracao.pasta_id
    )
    temporario = arquivo.with_name(arquivo.name + ".novo")
    descritor = os.open(temporario, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descritor, "w", encoding="utf-8") as saida:
        json.dump(
            {
                "client_id": configuracao.client_id,
                "client_secret": configuracao.client_secret,
                "refresh_token": configuracao.refresh_token,
                "senha": configuracao.senha,
                "pasta_id": configuracao.pasta_id,
            },
            saida,
        )
        saida.write("\n")
    os.chmod(temporario, 0o600)
    os.replace(temporario, arquivo)


def configurado(arquivo: Path) -> bool:
    try:
        ler_configuracao(arquivo)
    except NaoConfigurado:
        return False
    return True


# ------------------------------------------------------------------ criptografia


def _chave_da_senha(senha: str, sal: bytes) -> bytes:
    return base64.urlsafe_b64encode(hashlib.scrypt(senha.encode("utf-8"), salt=sal, **_PARAMETROS_DO_SCRYPT))


def criptografar(dados: bytes, senha: str) -> bytes:
    """`GFBK1\\n` + sal (16 bytes) + o "token" Fernet. Cada arquivo tem um sal novo: o mesmo banco nunca sai igual duas vezes."""
    sal = secrets.token_bytes(_TAMANHO_DO_SAL)
    return CABECALHO_DO_ARQUIVO + sal + Fernet(_chave_da_senha(validar_senha(senha), sal)).encrypt(dados)


def descriptografar(pacote: bytes, senha: str) -> bytes:
    """O contrário de `criptografar`. Levanta ArquivoOuSenhaInvalidos se o arquivo não é daqui, foi alterado ou a senha não é a certa."""
    inicio_do_token = len(CABECALHO_DO_ARQUIVO) + _TAMANHO_DO_SAL
    if not pacote.startswith(CABECALHO_DO_ARQUIVO) or len(pacote) <= inicio_do_token:
        raise ArquivoOuSenhaInvalidos("Este arquivo não é uma cópia criptografada do app.")
    sal = pacote[len(CABECALHO_DO_ARQUIVO) : inicio_do_token]
    try:
        return Fernet(_chave_da_senha(senha, sal)).decrypt(pacote[inicio_do_token:])
    except InvalidToken:
        raise ArquivoOuSenhaInvalidos("Senha errada, ou o arquivo foi alterado ou está danificado.") from None


# ------------------------------------------------------------------ falar com o Google


class _NaoSeguirRedirecionamento(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None  # sem isto o Python reenviaria o cabeçalho com o token ao endereço novo


_ABRIR = urllib.request.build_opener(_NaoSeguirRedirecionamento)


def _dormir(segundos: float) -> None:
    time.sleep(segundos)  # em função própria para os testes trocarem


class _SemResposta(Exception):
    """A chamada nem chegou a ter resposta (rede, demora)."""


class _Google:
    """Uma conversa com o Google. Guarda os segredos só para tirá-los de qualquer texto que vá para o log."""

    def __init__(self, enderecos: Enderecos, segredos=()):
        self.enderecos = enderecos
        self.segredos = [s for s in segredos if s]

    def esconder(self, segredo: str) -> None:
        if segredo and segredo not in self.segredos:
            self.segredos.append(segredo)

    def limpar(self, texto: str, limite: int = 300) -> str:
        for segredo in self.segredos:
            texto = texto.replace(segredo, "***")
        return " ".join(texto.split())[:limite]

    def uma_chamada(self, metodo: str, url: str, dados: bytes | None, cabecalhos: dict, tempo_limite: float):
        """(status, cabeçalhos da resposta, corpo). HTTP 4xx/5xx NÃO levanta: quem chamou decide. Levanta _SemResposta."""
        requisicao = urllib.request.Request(url, data=dados, headers=cabecalhos, method=metodo)
        try:
            with _ABRIR.open(requisicao, timeout=tempo_limite) as resposta:
                return resposta.status, resposta.headers, resposta.read()
        except urllib.error.HTTPError as erro:
            return erro.code, erro.headers, erro.read(8000)
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as erro:
            raise _SemResposta(self.limpar(f"rede: {type(erro).__name__}: {erro}")) from None

    def com_repeticao(self, fazer):
        """Roda `fazer()` (que devolve (status, cabeçalhos, corpo)) até 3 vezes se faltou resposta ou o Google deu erro 5xx."""
        ultimo: DriveFalhou | None = None
        tentativas = len(ESPERAS_ENTRE_TENTATIVAS) + 1
        for numero in range(1, tentativas + 1):
            try:
                resposta = fazer()
            except _SemResposta as erro:
                ultimo = DriveFalhou("Não deu para falar com o Google (rede ou demora).", str(erro))
            else:
                if resposta[0] not in (500, 502, 503, 504):
                    return resposta
                ultimo = DriveFalhou(f"O Google teve um problema do lado dele (HTTP {resposta[0]}).", self.erro_do_google(resposta[2]))
            if numero < tentativas:
                _dormir(ESPERAS_ENTRE_TENTATIVAS[numero - 1])
        raise ultimo  # type: ignore[misc]  # o laço roda ao menos uma vez

    def pedir(self, metodo: str, url: str, dados: bytes | None = None, cabecalhos: dict | None = None, tempo_limite: float = TEMPO_LIMITE_DAS_CHAMADAS):
        cabecalhos = cabecalhos or {}
        return self.com_repeticao(lambda: self.uma_chamada(metodo, url, dados, cabecalhos, tempo_limite))

    def erro_do_google(self, corpo: bytes) -> str:
        """Resumo do JSON de erro do Google ('' se não for o formato esperado), já sem segredos."""
        try:
            erro = json.loads(corpo.decode("utf-8", errors="replace"))
            bruto = erro.get("error")
            if isinstance(bruto, dict):
                partes = [str(bruto.get("status") or ""), str(bruto.get("message") or "")]
                motivos = [str(e.get("reason") or "") for e in (bruto.get("errors") or []) if isinstance(e, dict)]
                texto = " ".join(p for p in partes + motivos if p)
            else:
                texto = " ".join(str(p) for p in (bruto, erro.get("error_description")) if p)
        except (ValueError, AttributeError, TypeError):
            return ""
        return self.limpar(texto)

    def json_de(self, resposta, o_que: str, ok=(200,)) -> dict:
        status, _cabecalhos, corpo = resposta
        if status in (301, 302, 303, 307, 308):
            raise DriveFalhou(f"O Google respondeu com um redirecionamento ({o_que}), que o app não segue de propósito.", f"HTTP {status}")
        if status not in ok:
            raise DriveFalhou(f"O Google recusou: {o_que}.", self.limpar(f"HTTP {status} {self.erro_do_google(corpo)}"))
        try:
            dados = json.loads(corpo.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise DriveFalhou(f"O Google respondeu algo que não deu para ler ({o_que}).", f"HTTP {status}") from None
        if not isinstance(dados, dict):
            raise DriveFalhou(f"O Google respondeu algo inesperado ({o_que}).", f"HTTP {status}")
        return dados


def _formulario(**campos: str) -> tuple[bytes, dict]:
    return urllib.parse.urlencode(campos).encode("utf-8"), {"Content-Type": "application/x-www-form-urlencoded"}


# ------------------------------------------------------------------ autorização (fluxo de dispositivo)


def iniciar_autorizacao(google: _Google, client_id: str) -> dict:
    """Pede ao Google um código curto para o Thiago digitar no celular. Devolve o pedido (url, código, prazo)."""
    dados, cabecalhos = _formulario(client_id=client_id, scope=ESCOPO)
    resposta = google.pedir("POST", f"{google.enderecos.oauth}/device/code", dados, cabecalhos)
    if resposta[0] == 400 or resposta[0] == 401:
        raise DriveFalhou(
            "O Google não aceitou o ID do cliente. Confira se ele foi criado como 'TVs e dispositivos de entrada limitada'.",
            google.limpar(f"HTTP {resposta[0]} {google.erro_do_google(resposta[2])}"),
        )
    pedido = google.json_de(resposta, "pedido do código de autorização")
    endereco = pedido.get("verification_url") or pedido.get("verification_uri")
    if not (isinstance(endereco, str) and isinstance(pedido.get("user_code"), str) and isinstance(pedido.get("device_code"), str)):
        raise DriveFalhou("O Google respondeu ao pedido de autorização num formato inesperado.")
    google.esconder(pedido["device_code"])
    return {
        "device_code": pedido["device_code"],
        "user_code": pedido["user_code"],
        "endereco": endereco,
        "expira_em": int(pedido.get("expires_in") or 1800),
        "intervalo": max(int(pedido.get("interval") or 5), 1),
    }


def esperar_autorizacao(google: _Google, client_id: str, client_secret: str, pedido: dict, dormir=_dormir, relogio=time.monotonic) -> str:
    """Espera o Thiago digitar o código no celular e devolve o refresh token. Levanta DriveFalhou se recusou ou o prazo acabou."""
    intervalo = pedido["intervalo"]
    limite = relogio() + pedido["expira_em"]
    while relogio() < limite:
        dormir(intervalo)
        dados, cabecalhos = _formulario(
            client_id=client_id,
            client_secret=client_secret,
            device_code=pedido["device_code"],
            grant_type="urn:ietf:params:oauth:grant-type:device_code",
        )
        status, _, corpo = google.pedir("POST", f"{google.enderecos.oauth}/token", dados, cabecalhos)
        try:
            resposta = json.loads(corpo.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            resposta = {}
        if not isinstance(resposta, dict):
            resposta = {}
        if status == 200:
            refresh = resposta.get("refresh_token")
            if not isinstance(refresh, str) or not _FORMATO_DO_REFRESH_TOKEN.fullmatch(refresh):
                raise DriveFalhou("O Google autorizou mas não entregou o refresh token (rode configurar de novo).")
            google.esconder(refresh)
            return refresh
        erro = resposta.get("error")
        if erro == "authorization_pending":
            continue
        if erro == "slow_down":
            intervalo += 5
            continue
        if erro == "access_denied":
            raise DriveFalhou("A autorização foi recusada na tela do Google.")
        if erro in ("expired_token", "invalid_grant"):
            raise DriveFalhou("O código expirou (ou já foi usado) antes de ser aprovado. Rode configurar de novo.")
        raise DriveFalhou("O Google não aceitou o ID/segredo do cliente ou o pedido.", google.limpar(f"HTTP {status} {google.erro_do_google(corpo)}"))
    raise DriveFalhou("O tempo para digitar o código acabou. Rode configurar de novo.")


def token_de_acesso(google: _Google, client_id: str, client_secret: str, refresh_token: str) -> str:
    """Troca o refresh token por um token de acesso (vale cerca de 1 hora; é pedido de novo a cada envio)."""
    dados, cabecalhos = _formulario(client_id=client_id, client_secret=client_secret, refresh_token=refresh_token, grant_type="refresh_token")
    status, _, corpo = google.pedir("POST", f"{google.enderecos.oauth}/token", dados, cabecalhos)
    if status == 400 and '"invalid_grant"' in corpo.decode("utf-8", errors="replace"):
        raise DriveFalhou(
            "O Google não aceita mais a autorização do servidor (foi retirada ou venceu). Rode: python -m app.backup_drive configurar",
            "invalid_grant",
        )
    resposta = google.json_de((status, None, corpo), "troca do refresh token pelo token de acesso")
    token = resposta.get("access_token")
    if not isinstance(token, str) or not token:
        raise DriveFalhou("O Google não entregou o token de acesso.")
    google.esconder(token)
    return token


# ------------------------------------------------------------------ o Drive


def _cabecalho_de_acesso(token: str, **extras: str) -> dict:
    return {"Authorization": f"Bearer {token}", **extras}


def criar_pasta(google: _Google, token: str) -> str:
    corpo = json.dumps({"name": NOME_DA_PASTA, "mimeType": "application/vnd.google-apps.folder"}).encode("utf-8")
    resposta = google.pedir(
        "POST",
        f"{google.enderecos.drive}/drive/v3/files?fields=id",
        corpo,
        _cabecalho_de_acesso(token, **{"Content-Type": "application/json; charset=UTF-8"}),
    )
    identificador = google.json_de(resposta, "criação da pasta no Drive").get("id")
    if not isinstance(identificador, str) or not _FORMATO_DO_ID_DA_PASTA.fullmatch(identificador):
        raise DriveFalhou("O Drive não devolveu o id da pasta.")
    return identificador


def conferir_pasta(google: _Google, token: str, pasta_id: str) -> None:
    """A pasta ainda existe e não está na lixeira? Senão, DriveFalhou (o Thiago roda `configurar` de novo)."""
    resposta = google.pedir("GET", f"{google.enderecos.drive}/drive/v3/files/{pasta_id}?fields=id,trashed", None, _cabecalho_de_acesso(token))
    if resposta[0] == 404:
        raise DriveFalhou("A pasta de backup sumiu do Drive. Rode: python -m app.backup_drive configurar", "HTTP 404")
    if google.json_de(resposta, "conferência da pasta no Drive").get("trashed"):
        raise DriveFalhou("A pasta de backup está na lixeira do Drive. Tire de lá ou rode: python -m app.backup_drive configurar")


def procurar_arquivo(google: _Google, token: str, pasta_id: str, nome: str) -> str | None:
    consulta = f"name = '{nome}' and '{pasta_id}' in parents and trashed = false"
    parametros = urllib.parse.urlencode({"q": consulta, "fields": "files(id)", "pageSize": "1", "spaces": "drive"})
    resposta = google.pedir("GET", f"{google.enderecos.drive}/drive/v3/files?{parametros}", None, _cabecalho_de_acesso(token))
    achados = google.json_de(resposta, "busca do arquivo no Drive").get("files") or []
    return achados[0].get("id") if achados and isinstance(achados[0], dict) else None


def subir_arquivo(google: _Google, token: str, pasta_id: str, nome: str, descricao: str, conteudo: bytes, arquivo_id: str | None) -> None:
    """Cria o arquivo (ou troca o conteúdo do que já existe) pelo envio "resumível" do Drive, numa única remessa."""
    if arquivo_id:
        metodo, caminho = "PATCH", f"/upload/drive/v3/files/{arquivo_id}"
        metadados = {"description": descricao}
    else:
        metodo, caminho = "POST", "/upload/drive/v3/files"
        metadados = {"name": nome, "parents": [pasta_id], "description": descricao, "mimeType": "application/octet-stream"}
    abertura = _cabecalho_de_acesso(
        token, **{"Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Type": "application/octet-stream", "X-Upload-Content-Length": str(len(conteudo))}
    )
    corpo_da_abertura = json.dumps(metadados).encode("utf-8")
    base = google.enderecos.drive

    def uma_vez():
        # 1) abre a sessão de envio; o Google devolve o endereço dela no cabeçalho Location
        resposta = google.uma_chamada(metodo, f"{base}{caminho}?uploadType=resumable&fields=id", corpo_da_abertura, abertura, TEMPO_LIMITE_DAS_CHAMADAS)
        if resposta[0] != 200:
            return resposta
        endereco = resposta[1].get("Location") if resposta[1] is not None else None
        if not endereco or urllib.parse.urlparse(endereco).scheme != urllib.parse.urlparse(base).scheme:
            raise DriveFalhou("O Drive não devolveu o endereço de envio esperado.")
        # 2) manda o arquivo. O endereço da sessão já carrega a permissão: não se manda o token junto.
        return google.uma_chamada("PUT", endereco, conteudo, {"Content-Type": "application/octet-stream"}, TEMPO_LIMITE_DO_ENVIO)

    resposta = google.com_repeticao(uma_vez)
    google.json_de(resposta, "envio do arquivo ao Drive", ok=(200, 201))


# ------------------------------------------------------------------ a cópia do dia


def quando_da_copia(copia: Path, agora: datetime | None = None) -> datetime:
    """Quando a cópia foi feita (do nome `app-AAAA-MM-DD-HHMMSS.db`, que é em UTC); sem esse nome, `agora`."""
    achou = re.fullmatch(r"app-(\d{4}-\d{2}-\d{2}-\d{6})\.db", copia.name)
    if achou:
        return datetime.strptime(achou.group(1), "%Y-%m-%d-%H%M%S").replace(tzinfo=timezone.utc)
    return agora or datetime.now(timezone.utc)


def nome_no_drive(quando: datetime) -> str:
    """`app-terca.gfbk`: o dia da semana (em Vila Velha) em que a cópia foi feita. A cópia das 03:00 de terça vai para terça."""
    return f"app-{DIAS_DA_SEMANA[quando.astimezone(FUSO_DA_ACADEMIA).weekday()]}.gfbk"


def copia_local_mais_nova(pasta: str | Path) -> Path | None:
    pasta = Path(pasta)
    if not pasta.is_dir():
        return None
    copias = sorted(p for p in pasta.iterdir() if p.is_file() and PADRAO_DO_NOME.match(p.name))
    return copias[-1] if copias else None


def registrar_envio(pasta_do_estado: Path, quando: datetime, copia: str, nome: str) -> None:
    pasta_do_estado.mkdir(parents=True, exist_ok=True)
    arquivo = pasta_do_estado / NOME_DO_ESTADO
    temporario = arquivo.with_name(arquivo.name + ".novo")
    temporario.write_text(json.dumps({"enviado_em": quando.astimezone(timezone.utc).isoformat(), "copia": copia, "arquivo_no_drive": nome}), encoding="utf-8")
    os.replace(temporario, arquivo)


def ler_ultimo_envio(pasta_do_estado: Path) -> tuple[datetime, str] | None:
    """(quando, nome do arquivo no Drive) do último envio que deu certo, ou None."""
    try:
        dados = json.loads((Path(pasta_do_estado) / NOME_DO_ESTADO).read_text(encoding="utf-8"))
        quando = datetime.fromisoformat(dados["enviado_em"])
        return (quando if quando.tzinfo else quando.replace(tzinfo=timezone.utc)), str(dados.get("arquivo_no_drive") or "")
    except (OSError, ValueError, KeyError, TypeError):
        return None


def enviar_copia(
    copia: Path,
    arquivo_da_configuracao: Path,
    pasta_do_estado: Path,
    agora: datetime | None = None,
    enderecos: Enderecos = ENDERECOS_REAIS,
) -> str:
    """Criptografa `copia` e a coloca na pasta do Drive (no arquivo do dia da semana). Devolve o nome no Drive.

    Levanta NaoConfigurado ou DriveFalhou. Só registra o envio como feito se o Drive aceitou o arquivo inteiro.
    """
    configuracao = ler_configuracao(arquivo_da_configuracao)
    agora = agora or datetime.now(timezone.utc)
    google = _Google(enderecos, [configuracao.client_secret, configuracao.refresh_token, configuracao.senha])
    try:
        conteudo = copia.read_bytes()
    except OSError as erro:
        raise DriveFalhou("Não deu para ler a cópia local.", type(erro).__name__) from None
    pacote = criptografar(conteudo, configuracao.senha)
    token = token_de_acesso(google, configuracao.client_id, configuracao.client_secret, configuracao.refresh_token)
    conferir_pasta(google, token, configuracao.pasta_id)
    quando = quando_da_copia(copia, agora)
    nome = nome_no_drive(quando)
    descricao = (
        f"Cópia do banco de {quando.astimezone(FUSO_DA_ACADEMIA):%d/%m/%Y %H:%M} (Vila Velha), criptografada. "
        "Para abrir: python -m app.backup_drive descriptografar"
    )
    subir_arquivo(google, token, configuracao.pasta_id, nome, descricao, pacote, procurar_arquivo(google, token, configuracao.pasta_id, nome))
    registrar_envio(pasta_do_estado, agora, copia.name, nome)
    return nome


class EnvioAoDrive:
    """O que o agendador usa (app/backup_agendado.py). Os testes dele trocam por um falso com os mesmos métodos."""

    def __init__(self, arquivo_da_configuracao: Path, pasta_do_estado: Path, enderecos: Enderecos = ENDERECOS_REAIS):
        self.arquivo = Path(arquivo_da_configuracao)
        self.pasta_do_estado = Path(pasta_do_estado)
        self.enderecos = enderecos

    def configurado(self) -> bool:
        """Lido a cada vez: dá para configurar sem reiniciar o contêiner."""
        return configurado(self.arquivo)

    def atrasado(self, agora: datetime, idade_maxima: timedelta) -> bool:
        ultimo = ler_ultimo_envio(self.pasta_do_estado)
        return ultimo is None or agora - ultimo[0] > idade_maxima

    def verificar(self, agora: datetime, idade_maxima: timedelta) -> tuple[bool, str]:
        ultimo = ler_ultimo_envio(self.pasta_do_estado)
        if ultimo is None:
            return False, "Nenhum envio ao Drive registrado."
        if agora - ultimo[0] > idade_maxima:
            return False, f"O último envio ao Drive tem {int((agora - ultimo[0]).total_seconds() // 3600)} horas (o esperado é um por dia)."
        return True, f"Último envio ao Drive em {ultimo[0]:%d/%m/%Y %H:%M} UTC."

    def enviar(self, copia: Path) -> str:
        return enviar_copia(copia, self.arquivo, self.pasta_do_estado, enderecos=self.enderecos)


# ------------------------------------------------------------------ terminal do servidor


def _comando_configurar(
    banco: Path,
    pasta_das_copias: Path,
    enderecos: Enderecos,
    pedir_texto=input,
    pedir_segredo=getpass.getpass,
    dormir=_dormir,
    relogio=time.monotonic,
) -> int:
    arquivo = caminho_da_configuracao(banco)
    print("Vamos ligar o servidor ao Google Drive da academia. Nada é gravado até o fim da autorização.")
    client_id = pedir_texto("ID do cliente (termina em .apps.googleusercontent.com): ").strip()
    client_secret = pedir_segredo("Segredo do cliente (NÃO aparece na tela): ").strip()
    if configurado(arquivo):
        print("ATENÇÃO: já existe uma configuração. Digite a MESMA senha de antes, senão as cópias antigas do Drive não abrem mais.")
    print(f"Senha da criptografia: mínimo {TAMANHO_MINIMO_DA_SENHA} caracteres. Guarde-a FORA do servidor; sem ela a cópia do Drive não abre.")
    senha = pedir_segredo("Senha da criptografia (NÃO aparece na tela): ")
    repetida = pedir_segredo("Repita a senha: ")
    try:
        if senha != repetida:
            raise ValueError("As duas senhas não são iguais.")
        validar_configuracao(client_id, client_secret, "x" * 30, senha)
    except ValueError as erro:
        print(f"{erro} Nada foi alterado.")
        return 1

    google = _Google(enderecos, [client_secret, senha])
    try:
        pedido = iniciar_autorizacao(google, client_id)
        print()
        print(f"Agora, no celular (ou no computador), abra: {pedido['endereco']}")
        print(f"Entre com a conta Google da academia e digite o código: {pedido['user_code']}")
        print(f"Estou esperando (o código vale uns {pedido['expira_em'] // 60} minutos)...")
        refresh = esperar_autorizacao(google, client_id, client_secret, pedido, dormir, relogio)
        token = token_de_acesso(google, client_id, client_secret, refresh)
        pasta_id = criar_pasta(google, token)
    except DriveFalhou as erro:
        print(f"FALHOU: {erro.mensagem}" + (f"\n(detalhe técnico: {erro.detalhe})" if erro.detalhe else "") + "\nNada foi alterado.")
        return 1

    guardar_configuracao(arquivo, validar_configuracao(client_id, client_secret, refresh, senha, pasta_id))
    print(f"Autorizado. Criei a pasta '{NOME_DA_PASTA}' no Drive. Credenciais guardadas em {arquivo} (só o dono do arquivo lê).")

    copia = copia_local_mais_nova(pasta_das_copias)
    if copia is None:
        print("Ainda não há cópia local; o primeiro envio será logo depois da próxima cópia das 03:00.")
        return 0
    return _enviar_e_contar(banco, pasta_das_copias, copia, enderecos)


def _enviar_e_contar(banco: Path, pasta_das_copias: Path, copia: Path, enderecos: Enderecos) -> int:
    try:
        nome = EnvioAoDrive(caminho_da_configuracao(banco), pasta_das_copias, enderecos).enviar(copia)
    except NaoConfigurado:
        print("Ainda não há configuração. Use primeiro: python -m app.backup_drive configurar")
        return 1
    except DriveFalhou as erro:
        print(f"FALHOU: {erro.mensagem}" + (f"\n(detalhe técnico: {erro.detalhe})" if erro.detalhe else ""))
        return 1
    print(f"Enviado: {nome} (a partir de {copia.name}). Confira a pasta '{NOME_DA_PASTA}' no Drive.")
    return 0


def _comando_situacao(banco: Path, pasta_das_copias: Path) -> int:
    arquivo = caminho_da_configuracao(banco)
    if configurado(arquivo):
        print(f"Drive: configurado ({arquivo}). Pasta '{NOME_DA_PASTA}'. Segredos guardados.")
    else:
        print(f"Drive: NÃO configurado ({arquivo}). Use: python -m app.backup_drive configurar")
    ultimo = ler_ultimo_envio(pasta_das_copias)
    if ultimo is None:
        print("Último envio: nenhum registrado.")
    else:
        print(f"Último envio: {ultimo[0].astimezone(FUSO_DA_ACADEMIA):%d/%m/%Y %H:%M} (Vila Velha), arquivo {ultimo[1]}.")
    return 0


def _comando_enviar_agora(banco: Path, pasta_das_copias: Path, enderecos: Enderecos) -> int:
    copia = copia_local_mais_nova(pasta_das_copias)
    if copia is None:
        print(f"Não achei nenhuma cópia em {pasta_das_copias}.")
        return 1
    return _enviar_e_contar(banco, pasta_das_copias, copia, enderecos)


def _comando_descriptografar(entrada: Path, saida: Path, pedir_segredo=getpass.getpass) -> int:
    """Abre uma cópia baixada do Drive. Não precisa de configuração: só do arquivo e da senha (serve num computador qualquer)."""
    if saida.exists():
        print(f"{saida} já existe: não vou sobrescrever. Escolha outro nome.")
        return 1
    try:
        pacote = entrada.read_bytes()
    except OSError as erro:
        print(f"Não deu para ler {entrada}: {type(erro).__name__}.")
        return 1
    senha = pedir_segredo("Senha da criptografia (NÃO aparece na tela): ")
    try:
        dados = descriptografar(pacote, senha)
    except ArquivoOuSenhaInvalidos as erro:
        print(f"{erro} Nada foi gravado.")
        return 1
    if not dados.startswith(_CABECALHO_DO_SQLITE):
        print("A senha abriu o arquivo, mas o conteúdo não é um banco SQLite. Nada foi gravado.")
        return 1
    descritor = os.open(saida, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descritor, "wb") as destino:
        destino.write(dados)
    print(f"Pronto: {saida} é o banco aberto (só o dono do arquivo lê). Confira antes de usar: python -m app.backup {saida} <pasta>")
    return 0


def _montar_parser() -> argparse.ArgumentParser:
    comum = argparse.ArgumentParser(add_help=False)
    comum.add_argument("--banco", default=argparse.SUPPRESS, help="arquivo do banco (padrão: variável GLORIAFIT_DB ou app.db)")
    comum.add_argument("--pasta", default=argparse.SUPPRESS, help="pasta das cópias locais (padrão: /backups)")
    parser = argparse.ArgumentParser(prog="python -m app.backup_drive", description="Cópia diária do banco, criptografada, para o Google Drive da academia.")
    parser.add_argument("--banco", default=os.environ.get("GLORIAFIT_DB", "app.db"), help="arquivo do banco (padrão: variável GLORIAFIT_DB ou app.db)")
    parser.add_argument("--pasta", default="/backups", help="pasta das cópias locais (padrão: /backups)")
    comandos = parser.add_subparsers(dest="comando", required=True)
    comandos.add_parser("configurar", parents=[comum], help="autoriza o Google, cria a pasta, guarda as credenciais e faz o primeiro envio")
    comandos.add_parser("situacao", parents=[comum], help="mostra se está configurado e quando foi o último envio (nunca mostra segredo)")
    comandos.add_parser("enviar-agora", parents=[comum], help="manda a cópia local mais nova já, sem esperar as 03:00")
    abrir = comandos.add_parser("descriptografar", help="abre uma cópia baixada do Drive (pede a senha)")
    abrir.add_argument("entrada", help="arquivo baixado do Drive, por exemplo app-terca.gfbk")
    abrir.add_argument("saida", help="nome do banco a criar, por exemplo restaurado.db (não pode já existir)")
    return parser


def main(argv: list[str] | None = None, enderecos: Enderecos = ENDERECOS_REAIS, pedir_texto=input, pedir_segredo=getpass.getpass, dormir=_dormir, relogio=time.monotonic) -> int:
    args = _montar_parser().parse_args(argv)
    if args.comando == "descriptografar":
        return _comando_descriptografar(Path(args.entrada), Path(args.saida), pedir_segredo)
    banco, pasta = Path(args.banco), Path(args.pasta)
    if args.comando == "configurar":
        return _comando_configurar(banco, pasta, enderecos, pedir_texto, pedir_segredo, dormir, relogio)
    if args.comando == "situacao":
        return _comando_situacao(banco, pasta)
    return _comando_enviar_agora(banco, pasta, enderecos)


if __name__ == "__main__":
    sys.exit(main())
