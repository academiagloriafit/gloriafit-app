"""Envio do código de acesso do aluno pelo WhatsApp (API oficial da Meta, a "Cloud API").

Como funciona:

1. O aluno pede o código na tela de entrada (ver app/aluno_acesso.py). O app sorteia o código e chama este módulo, que manda
   uma mensagem de MODELO (template) aprovada pela Meta: `codigo_acesso_app`, categoria Autenticação, idioma pt_BR, com o
   botão "Copiar código". O modelo foi criado pelo Thiago no Gerenciador do WhatsApp em 15/10/2026.
2. O envio é uma chamada HTTPS direta à Meta (graph.facebook.com), sem intermediário. A mensagem leva o código duas vezes,
   como a Meta exige: no texto e no botão (https://developers.facebook.com/docs/whatsapp/business-management-api/authentication-templates/copy-code-button-authentication-templates).
3. A "chave" (token) da Meta e o número do remetente ficam num ARQUIVO ao lado do banco (`/dados/whatsapp.json`, permissão
   só do dono), nunca no banco, nunca no código, nunca no log. Quem cuida do servidor grava com:

       python -m app.whatsapp configurar        (o token NÃO aparece na tela enquanto é digitado)

   Outros comandos do terminal do servidor:

       python -m app.whatsapp situacao          (diz se está configurado e como foram os últimos envios; nunca mostra o token)
       python -m app.whatsapp testar 27999998888  (manda um código de teste, "000000", para este WhatsApp; custa uns centavos)

Cuidados de segurança que este arquivo tem:
- O token nunca é escrito em log, em mensagem de erro, na resposta do app nem no banco. Mensagens de erro da Meta passam por
  uma limpeza que tira o token e o número do texto.
- A chamada só vai para https (a Meta), e NÃO segue redirecionamento: sem isso, uma resposta de redirecionamento faria o
  Python reenviar o cabeçalho com o token a outro endereço.
- O arquivo é gravado com permissão 0600 e trocado de uma vez (nunca fica pela metade).
- Mandar o código é demorado e pode falhar: o app faz isso em segundo plano e a resposta ao aluno é a mesma com ou sem sucesso
  (para ninguém descobrir quais CPFs existem). Por isso o resultado de cada envio fica no banco (`aluno_codigo.envio`) e
  aparece em `python -m app.whatsapp situacao`.
- "Enviado" quer dizer que a Meta ACEITOU a mensagem; a entrega no celular só a Meta sabe.
"""

import argparse
import getpass
import http.client
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

NOME_DO_MODELO = "codigo_acesso_app"
IDIOMA_DO_MODELO = "pt_BR"
URL_BASE = "https://graph.facebook.com"
# A versão da API da Meta. Uma versão vale por pelo menos 2 anos desde o lançamento; a v24.0 saiu em 08/10/2025 (página de
# versões da Meta, consultada em 15/10/2026). Fica gravada no arquivo de configuração: dá para trocar sem mexer no código.
VERSAO_PADRAO_DA_API = "v24.0"

NOME_DO_ARQUIVO = "whatsapp.json"
VARIAVEL_DO_ARQUIVO = "GLORIAFIT_ARQUIVO_DO_WHATSAPP"

TEMPO_LIMITE_DA_CHAMADA = 15.0
TENTATIVAS_DA_CHAMADA = 2  # um código vale pouco tempo: não adianta insistir muito

_FORMATO_DO_NUMERO_DO_REMETENTE = re.compile(r"[0-9]{8,25}")
_FORMATO_DO_TOKEN = re.compile(r"[A-Za-z0-9_.\-]{20,1000}")
_FORMATO_DA_VERSAO = re.compile(r"v[0-9]{1,3}\.[0-9]{1,2}")
_FORMATO_DO_TELEFONE = re.compile(r"55[0-9]{10,11}")  # 55 + DDD + número
_FORMATO_DO_CODIGO = re.compile(r"[0-9A-Za-z]{1,15}")  # o limite da Meta é 15 caracteres

_log = logging.getLogger("gloriafit.whatsapp")


class NaoConfigurado(Exception):
    """O servidor ainda não tem o arquivo do WhatsApp (ou ele não serve)."""


class EnvioFalhou(Exception):
    """A Meta não aceitou a mensagem (ou não deu para falar com ela). `detalhe` é para o log: nunca tem token."""

    def __init__(self, mensagem: str, detalhe: str = ""):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.detalhe = detalhe


@dataclass(frozen=True)
class Configuracao:
    numero_do_remetente: str  # o "phone_number_id" da Meta (não é o telefone em si)
    token: str = field(repr=False)  # repr=False: um print por engano não mostra o token
    versao_da_api: str = VERSAO_PADRAO_DA_API


# ------------------------------------------------------------------ o arquivo de configuração


def caminho_da_configuracao(caminho_banco: str | Path) -> Path:
    """Onde fica o arquivo: ao lado do banco (em produção /dados/whatsapp.json), ou onde a variável de ambiente mandar."""
    avulso = os.environ.get(VARIAVEL_DO_ARQUIVO, "").strip()
    return Path(avulso) if avulso else Path(caminho_banco).parent / NOME_DO_ARQUIVO


def validar_configuracao(numero: object, token: object, versao: object = VERSAO_PADRAO_DA_API) -> Configuracao:
    """A configuração limpa, se tiver cara de verdadeira; senão ValueError (sem repetir o que foi digitado)."""
    if not isinstance(numero, str) or not _FORMATO_DO_NUMERO_DO_REMETENTE.fullmatch(numero.strip()):
        raise ValueError("O ID do número de telefone tem que ter só algarismos (de 8 a 25).")
    if not isinstance(token, str) or not _FORMATO_DO_TOKEN.fullmatch(token.strip()):
        raise ValueError(
            "O token tem um formato que não parece de um token da Meta (de 20 a 1000 letras, números, ponto, "
            "hífen ou sublinhado; sem espaço, acento ou quebra de linha)."
        )
    if not isinstance(versao, str) or not _FORMATO_DA_VERSAO.fullmatch(versao.strip()):
        raise ValueError("A versão da API tem que ter o formato v24.0.")
    return Configuracao(numero.strip(), token.strip(), versao.strip())


def ler_configuracao(arquivo: Path) -> Configuracao:
    """A configuração guardada. Levanta NaoConfigurado se não há arquivo ou ele não serve (sem dizer o que tem dentro)."""
    nao_serve = NaoConfigurado("O servidor ainda não tem a configuração do WhatsApp.")
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise nao_serve from None
    if not isinstance(dados, dict):
        raise nao_serve
    try:
        return validar_configuracao(
            dados.get("numero_do_remetente"), dados.get("token"), dados.get("versao_da_api", VERSAO_PADRAO_DA_API)
        )
    except ValueError:
        raise nao_serve from None


def guardar_configuracao(arquivo: Path, configuracao: Configuracao) -> None:
    """Grava (só o dono do arquivo lê). Escreve num arquivo temporário e troca: nunca fica pela metade."""
    validar_configuracao(configuracao.numero_do_remetente, configuracao.token, configuracao.versao_da_api)
    temporario = arquivo.with_name(arquivo.name + ".novo")
    descritor = os.open(temporario, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descritor, "w", encoding="utf-8") as saida:
        json.dump(
            {
                "numero_do_remetente": configuracao.numero_do_remetente,
                "token": configuracao.token,
                "versao_da_api": configuracao.versao_da_api,
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


# ------------------------------------------------------------------ a mensagem


def telefone_para_a_meta(whatsapp: str) -> str:
    """'27988887766' (o que o app guarda: DDD + número) -> '5527988887766' (com o código do Brasil, como a Meta pede)."""
    telefone = "55" + whatsapp
    if not _FORMATO_DO_TELEFONE.fullmatch(telefone):
        raise ValueError("Número de WhatsApp fora do formato (DDD + 8 ou 9 algarismos).")
    return telefone


def corpo_da_mensagem(telefone: str, codigo: str) -> dict:
    """O JSON do modelo `codigo_acesso_app` (com botão "Copiar código"): o código vai no texto e, de novo, no botão."""
    if not _FORMATO_DO_TELEFONE.fullmatch(telefone):
        raise ValueError("Telefone fora do formato 55 + DDD + número.")
    if not _FORMATO_DO_CODIGO.fullmatch(codigo):
        raise ValueError("Código fora do formato (até 15 letras ou números).")
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": telefone,
        "type": "template",
        "template": {
            "name": NOME_DO_MODELO,
            "language": {"code": IDIOMA_DO_MODELO},
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": codigo}]},
                {"type": "button", "sub_type": "url", "index": "0", "parameters": [{"type": "text", "text": codigo}]},
            ],
        },
    }


# ------------------------------------------------------------------ falar com a Meta


class _NaoSeguirRedirecionamento(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None  # sem isto o Python reenviaria o cabeçalho com o token ao endereço novo


_ABRIR = urllib.request.build_opener(_NaoSeguirRedirecionamento)


def _dormir(segundos: float) -> None:
    time.sleep(segundos)  # em função própria para os testes trocarem


def _limpar(texto: str, configuracao: Configuracao, telefone: str, limite: int = 280) -> str:
    """Tira do texto o token e o número, por garantia (a Meta não costuma repeti-los, mas o log não pode arriscar)."""
    for segredo in (configuracao.token, telefone, telefone[2:]):
        if segredo:
            texto = texto.replace(segredo, "***")
    return " ".join(texto.split())[:limite]


def _erro_da_meta(corpo: bytes) -> str:
    """'tipo código=N: mensagem' do JSON de erro da Meta, ou '' se não for o formato esperado."""
    try:
        erro = json.loads(corpo.decode("utf-8", errors="replace")).get("error") or {}
        partes = [str(erro.get("type") or ""), f"código={erro['code']}" if "code" in erro else ""]
        if "error_subcode" in erro:
            partes.append(f"subcódigo={erro['error_subcode']}")
        return " ".join(p for p in partes if p) + f": {erro.get('message') or ''}"
    except (ValueError, AttributeError, TypeError):
        return ""


def enviar_codigo(
    configuracao: Configuracao,
    telefone: str,
    codigo: str,
    tempo_limite: float = TEMPO_LIMITE_DA_CHAMADA,
    url_base: str = URL_BASE,
) -> str:
    """Manda o código ao WhatsApp `telefone` (55 + DDD + número) e devolve o id da mensagem na Meta ('' se ela não informou).

    Levanta EnvioFalhou em qualquer falha. Repete (até TENTATIVAS_DA_CHAMADA no total) só o que costuma passar sozinho: erro
    do lado da Meta (5xx) e falha de rede. Erro de token, de número ou de modelo não se repete. `url_base` só muda nos testes.
    """
    dados = json.dumps(corpo_da_mensagem(telefone, codigo), ensure_ascii=False).encode("utf-8")
    url = f"{url_base}/{configuracao.versao_da_api}/{configuracao.numero_do_remetente}/messages"
    cabecalhos = {"Content-Type": "application/json", "Authorization": f"Bearer {configuracao.token}"}
    ultimo: EnvioFalhou | None = None
    for tentativa in range(1, TENTATIVAS_DA_CHAMADA + 1):
        requisicao = urllib.request.Request(url, data=dados, headers=cabecalhos, method="POST")
        try:
            with _ABRIR.open(requisicao, timeout=tempo_limite) as resposta:
                try:
                    mensagens = json.loads(resposta.read().decode("utf-8")).get("messages") or [{}]
                    return str(mensagens[0].get("id") or "")
                except (ValueError, AttributeError, IndexError, TypeError):
                    return ""  # a Meta respondeu 200: aceitou. Só não deu para ler o id.
        except urllib.error.HTTPError as erro:
            detalhe = _limpar(f"HTTP {erro.code} {_erro_da_meta(erro.read(4000))}", configuracao, telefone)
            if erro.code in (401, 403):
                ultimo = EnvioFalhou("A Meta não aceitou o token do WhatsApp (venceu, foi revogado ou falta permissão).", detalhe)
            elif erro.code in (301, 302, 303, 307, 308):
                ultimo = EnvioFalhou("A Meta respondeu com um redirecionamento, que o app não segue de propósito.", detalhe)
            else:
                ultimo = EnvioFalhou(f"A Meta recusou a mensagem (HTTP {erro.code}).", detalhe)
            if erro.code not in (500, 502, 503, 504):
                raise ultimo from None
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as erro:
            ultimo = EnvioFalhou(
                "Não deu para falar com a Meta (rede ou demora).",
                _limpar(f"rede: {type(erro).__name__}: {erro}", configuracao, telefone),
            )
        if tentativa < TENTATIVAS_DA_CHAMADA:
            _dormir(1.5)
    raise ultimo  # type: ignore[misc]  # o laço roda ao menos uma vez


class Remetente:
    """Quem manda o código de verdade. Os testes trocam por um falso com os mesmos dois métodos (`pronto` e `enviar`)."""

    def __init__(self, arquivo: Path, url_base: str = URL_BASE):
        self.arquivo = arquivo
        self.url_base = url_base

    def pronto(self) -> bool:
        """O arquivo de configuração existe e serve? (Lido a cada vez: dá para configurar sem reiniciar o app.)"""
        return configurado(self.arquivo)

    def enviar(self, whatsapp: str, codigo: str) -> str:
        """`whatsapp`: o número como o app guarda (DDD + número). Levanta NaoConfigurado ou EnvioFalhou."""
        configuracao = ler_configuracao(self.arquivo)
        return enviar_codigo(configuracao, telefone_para_a_meta(whatsapp), codigo, url_base=self.url_base)


# ------------------------------------------------------------------ terminal do servidor


def _caminho_do_banco_do_ambiente() -> Path:
    return Path(os.environ.get("GLORIAFIT_DB", "app.db"))


def _comando_configurar(banco: Path, versao: str | None, pedir_numero=input, pedir_token=getpass.getpass) -> int:
    arquivo = caminho_da_configuracao(banco)
    anterior = None
    try:
        anterior = ler_configuracao(arquivo)
    except NaoConfigurado:
        pass
    print("ID do número de telefone: o número comprido que o Gerenciador do WhatsApp mostra (não é o telefone com DDD).")
    numero = pedir_numero("ID do número de telefone: ")
    print("Cole o token da Meta (ele NÃO aparece na tela) e aperte Enter.")
    token = pedir_token("Token: ")
    try:
        nova = validar_configuracao(numero, token, versao or (anterior.versao_da_api if anterior else VERSAO_PADRAO_DA_API))
    except ValueError as erro:
        print(f"{erro} Nada foi alterado.")
        return 1
    guardar_configuracao(arquivo, nova)
    print(f"Configuração guardada em {arquivo} (só o dono do arquivo lê). Versão da API: {nova.versao_da_api}.")
    print("Para conferir de ponta a ponta: python -m app.whatsapp testar <seu WhatsApp com DDD>")
    return 0


def _comando_situacao(banco: Path) -> int:
    from app import aluno_acesso, db  # aqui dentro: o envio em si não depende do banco

    arquivo = caminho_da_configuracao(banco)
    try:
        configuracao = ler_configuracao(arquivo)
        print(f"WhatsApp: configurado ({arquivo}). Remetente {configuracao.numero_do_remetente}, API {configuracao.versao_da_api}, token guardado.")
    except NaoConfigurado:
        print(f"WhatsApp: NÃO configurado ({arquivo}). Use: python -m app.whatsapp configurar")
    print(f"Modelo: {NOME_DO_MODELO} ({IDIOMA_DO_MODELO})")
    if banco.is_file():
        conn = db.conectar(banco)
        try:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'aluno_codigo'").fetchone():
                for linha in aluno_acesso.resumo_para_o_terminal(conn):
                    print(linha)
        finally:
            conn.close()
    return 0


def _comando_testar(banco: Path, numero: str) -> int:
    """Manda o código de teste 000000 para o WhatsApp dado. Custa o preço de uma mensagem (centavos)."""
    from app.alunos import WhatsappInvalido, validar_whatsapp

    try:
        whatsapp = validar_whatsapp(numero)
    except WhatsappInvalido as erro:
        print(f"{erro}")
        return 2
    remetente = Remetente(caminho_da_configuracao(banco))
    try:
        identificador = remetente.enviar(whatsapp, "000000")
    except NaoConfigurado:
        print("Ainda não há configuração. Use primeiro: python -m app.whatsapp configurar")
        return 1
    except EnvioFalhou as erro:
        print(f"FALHOU: {erro.mensagem}\n(detalhe técnico: {erro.detalhe})")
        return 1
    print(f"A Meta aceitou a mensagem (id {identificador or 'não informado'}). Confira se chegou no WhatsApp {numero}.")
    return 0


def _montar_parser() -> argparse.ArgumentParser:
    comum = argparse.ArgumentParser(add_help=False)
    comum.add_argument("--banco", default=argparse.SUPPRESS, help="arquivo do banco (padrão: variável GLORIAFIT_DB ou app.db)")
    parser = argparse.ArgumentParser(prog="python -m app.whatsapp", description="WhatsApp do app: configurar, ver a situação e testar o envio do código.")
    parser.add_argument("--banco", default=os.environ.get("GLORIAFIT_DB", "app.db"), help="arquivo do banco (padrão: variável GLORIAFIT_DB ou app.db)")
    comandos = parser.add_subparsers(dest="comando", required=True)
    configurar = comandos.add_parser("configurar", parents=[comum], help="guarda o ID do número e o token da Meta (o token não aparece na tela)")
    configurar.add_argument("--versao", default=None, help="versão da API da Meta, por exemplo v24.0 (padrão: a que já estava, ou a do app)")
    comandos.add_parser("situacao", parents=[comum], help="mostra se está configurado e como foram os últimos envios (nunca mostra o token)")
    testar = comandos.add_parser("testar", parents=[comum], help="manda o código de teste 000000 para um WhatsApp (custa uns centavos)")
    testar.add_argument("numero", help="WhatsApp com DDD, por exemplo 27999998888")
    return parser


def main(argv: list[str] | None = None, pedir_numero=input, pedir_token=getpass.getpass) -> int:
    args = _montar_parser().parse_args(argv)
    banco = Path(args.banco)
    if args.comando == "configurar":
        return _comando_configurar(banco, args.versao, pedir_numero, pedir_token)
    if args.comando == "situacao":
        return _comando_situacao(banco)
    return _comando_testar(banco, args.numero)


if __name__ == "__main__":
    sys.exit(main())
