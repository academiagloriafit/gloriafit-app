"""Manda os alunos e o histórico de treinos do Data4U para o app da Glória Fit, sozinho, todo dia.

ONDE RODA: no PC da recepção (Windows, Python 3.12), na mesma pasta do base_total.zip (a pasta NFSE). Só usa a
biblioteca padrão do Python: não precisa instalar nada.

O QUE FAZ, passo a passo (é a mesma coisa que a tela "Atualizar alunos" faz no navegador, sem ninguém clicar):
  1. Espera a extração do Data4U terminar, se ela estiver rodando agora.
  2. Abre o base_total.zip e olha a data da cópia (_manifesto.json). Se essa cópia já foi enviada, não faz nada.
  3. Separa SÓ o que o app usa (LGPD, princípio da necessidade): nome, CPF, situação e celular dos alunos, e os treinos
     com seus exercícios. O zip inteiro (258 tabelas, com RG, nascimento, pagamentos, digitais...) NUNCA sai do PC.
  4. Manda primeiro os alunos e depois o histórico de treinos (a ordem importa: o servidor liga cada treino ao aluno).
  5. Anota o resultado em enviar_alunos_log.txt. Enviar duas vezes a mesma cópia não duplica nada.
  6. Uma vez por dia, as FOTOS dos alunos (29/10/2026): o Data4U guarda as fotos da catraca num banco à parte, o CACHE.D4U. O programa
     copia esse arquivo, pergunta ao servidor quais alunos estão em uso e qual foto ele já tem, e manda só as fotos novas ou trocadas
     desses alunos (nunca o dado de reconhecimento facial). Para ler o CACHE.D4U usa o mesmo leitor do Firebird que a extração diária
     já usa (firebird-driver + o fbclient.dll do Data4U); se ele faltar, as fotos ficam para depois e o resto segue normal.

COMO USAR (no PC, na pasta onde está este arquivo):
  python enviar_alunos.py --autorizar   uma vez só: pede o código de uso único que o Thiago gera no servidor
  python enviar_alunos.py --conferir    monta os pacotes e mostra o resumo (e quantas fotos há), SEM enviar nada (para testar)
  python enviar_alunos.py --instalar    cria a tarefa agendada do Windows (05:15, 08:15 e 12:15, depois das cópias)
  python enviar_alunos.py               o envio de verdade (é o que a tarefa agendada roda)
  python enviar_alunos.py --forcar      envia mesmo que essa cópia já tenha sido enviada

SEGURANÇA: depois de --autorizar o PC guarda uma "chave" (enviar_alunos_dispositivo.txt) que o servidor reconhece,
igual ao navegador autorizado. Quem tiver esse arquivo consegue falar com o app como este PC; para cortar o acesso, o
Thiago revoga o computador no servidor (python -m app.dispositivos revogar N). A chave nunca aparece no log.
O endereço precisa ser https (a chave não viaja aberta pela internet).

O formato dos pacotes é o mesmo de app/static/copia_modelo.js; tests/test_enviar_alunos.py roda os dois lado a lado e
confere que saem iguais.
"""

import argparse
import http.client
import json
import math
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timedelta
from decimal import Decimal
from http.cookies import CookieError, SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

VERSAO = "1.0"
ENDERECO_PADRAO = "https://app.gloriafit.com.br"
NOME_DO_COOKIE = "gloriafit_dispositivo"

NOME_DO_ZIP = "base_total.zip"
NOME_DO_ZIP_EM_CONSTRUCAO = "base_total_nova.zip"  # a extração monta este e só no fim troca pelo base_total.zip
ARQUIVO_DA_CHAVE = "enviar_alunos_dispositivo.txt"
ARQUIVO_DO_ESTADO = "enviar_alunos_estado.json"
ARQUIVO_DO_LOG = "enviar_alunos_log.txt"
NOME_DA_TAREFA = "GloriaFit-EnvioDiario"
HORARIOS_DA_TAREFA = ("05:15", "08:15", "12:15")  # 15 min depois de cada cópia do Data4U (05:00, 08:00 e 12:00)

TAMANHO_MAXIMO_DA_TABELA = 200 * 1024 * 1024  # as maiores tabelas usadas têm poucas dezenas de MB
TAMANHO_MAXIMO_DO_PACOTE = 24 * 1024 * 1024  # o servidor recusa acima de 25 MB nessas rotas
TAMANHO_MAXIMO_DO_LOG = 300 * 1024
MINUTOS_DE_ESPERA_PELA_EXTRACAO = 25
TENTATIVAS_SEM_REDE = 3
SEGUNDOS_ENTRE_TENTATIVAS = 60
SEGUNDOS_ATE_DESISTIR_DO_SERVIDOR = 300  # o servidor grava tudo numa transação; o histórico de treinos leva alguns segundos

# Mesmas listas de app/static/copia_modelo.js (e de app/importar_alunos.py / importar_treinos.py no servidor).
COLUNAS_ENVIADAS = {
    "PESSOA": ["ID", "NM_PESSOA", "TP_PESSOA", "NR_CPF", "ST_DELETED"],
    "PESSOA_STATUS": ["ID_PESSOA", "DT_INI_STATUS", "DT_FIM_STATUS", "CD_STATUS"],
    "CONTATO_PESSOA": ["ID_CONTATO", "ID_PESSOA", "ID_TIPO_CONTATO", "DS_CONTATO"],
}
COLUNAS_DOS_TREINOS = {
    "TREINO": ["ID_TREINO", "ID_LANCAMENTO", "ID_PROFESSOR", "NM_TREINO", "ST_DELETED"],
    "TREINO_FICHA": ["ID_TREINO_FICHA", "ID_TREINO", "NR_FICHA", "NM_TREINO_FICHA"],
    "TREINO_PRESCRICAO": [
        "ID_TREINO_PRESCRICAO", "ID_TREINO_FICHA", "ID_TREINO_EXERCICIO", "NR_ORDEM",
        "NR_SERIE", "DS_REPETICAO", "DS_PESO", "TM_PAUSA", "DS_PRESCRICAO_OBS",
    ],
    "TREINO_EXERCICIO": ["ID_TREINO_EXERCICIO", "NM_EXERCICIO"],
    "LANCAMENTO_OBJ": ["ID_LANCAMENTO", "ID_OBJ", "TP_LANCAMENTO", "DT_LANCAMENTO"],
    "PESSOA": ["ID", "NM_PESSOA"],
}
# O Data4U às vezes guarda número onde o servidor quer texto (CPF, peso...).
COLUNAS_DE_TEXTO = frozenset({
    "NM_PESSOA", "TP_PESSOA", "NR_CPF", "ST_DELETED", "DT_INI_STATUS", "DT_FIM_STATUS", "CD_STATUS", "DS_CONTATO",
    "NM_TREINO", "NM_TREINO_FICHA", "NR_SERIE", "DS_REPETICAO", "DS_PESO", "TM_PAUSA", "DS_PRESCRICAO_OBS", "NM_EXERCICIO",
    "DT_LANCAMENTO",
    "NR_CEP", "CD_UF", "DS_LOCALIDADE", "DS_BAIRRO", "DS_LOGRADOURO", "DS_COMPLEMENTO", "DT_LAST_ACCESS",
})
# Último acesso pela catraca (29/10/2026): decide quem tem foto mesmo inativo. Só vai quem passou nos últimos DIAS_DE_ACESSO dias
# (antes da data da cópia) e só a data; as outras colunas da ACC_PESSOA (contagens, local) ficam no PC.
TABELA_DE_ACESSOS = "ACC_PESSOA"
COLUNAS_DE_ACESSOS = ["ID_PESSOA", "DT_LAST_ACCESS"]
DIAS_DE_ACESSO = 60
TIPO_CONTATO_CELULAR = 30  # tabela TIPO_CONTATO do Data4U: 30 = Celular
TIPO_CONTATO_EMAIL = 100  # 100 = e-mail ("Meu perfil" do aluno, 29/10/2026)
TIPOS_DE_CONTATO_ENVIADOS = (TIPO_CONTATO_CELULAR, TIPO_CONTATO_EMAIL)  # telefone fixo e comercial não saem do PC
# Endereço da pessoa ("Meu perfil"). Vai junto quando a cópia tem as seis colunas; o servidor só guarda o de quem está em uso.
COLUNAS_DO_ENDERECO = ["NR_CEP", "CD_UF", "DS_LOCALIDADE", "DS_BAIRRO", "DS_LOGRADOURO", "DS_COMPLEMENTO"]

# Fotos dos alunos (29/10/2026). O Data4U guarda as fotos da catraca no CACHE.D4U (tabela BLOB_CACHE, chave "foto/<id>_im_foto").
PASTA_DO_DATA4U = Path(r"C:\Users\Public\Documents\Data4U\Fit\Data")
NOME_DO_CACHE = "CACHE.D4U"
COPIA_DO_CACHE = "_cache_fotos_temp.D4U"  # cópia temporária na pasta NFSE; é apagada no fim, dê certo ou não
CLIENTE_DO_FIREBIRD = Path(r"C:\Program Files (x86)\Data4U Fit\FB\fbclient.dll")
ROTA_DO_ESTADO_DAS_FOTOS = "/api/fotos/estado"
ROTA_DAS_FOTOS = "/api/fotos/importar"
BYTES_DE_FOTO_POR_PACOTE = 12 * 1024 * 1024  # antes do base64 (que cresce 1/3): o pacote fica bem abaixo do limite do servidor
TAMANHO_MAXIMO_DA_FOTO = 3 * 1024 * 1024  # o servidor recusa acima disso; as fotos do Data4U têm 30 a 50 KB

ETAPAS = (
    ("alunos", "/api/alunos/importar", "os alunos"),
    ("treinos", "/api/treinos/importar", "o histórico de treinos"),
)


class CopiaInvalida(Exception):
    """O base_total.zip está incompleto, cortado ou fora do formato esperado. Nada é enviado."""


class SemRede(Exception):
    """Não deu para falar com o servidor (internet fora, servidor reiniciando)."""


class NaoAutorizado(Exception):
    """O servidor não reconhece este PC (chave revogada ou vencida). Precisa rodar --autorizar de novo."""


# ------------------------------------------------------------------ ler o base_total.zip


def _recusar_constante(nome):
    raise ValueError(f"constante {nome} não é JSON")  # o JavaScript também recusa NaN e Infinity


def _linhas_json(conteudo: bytes, tabela: str, colunas: list[str] | None = None) -> list[dict]:
    """As linhas do .jsonl como dicionários. Com `colunas`, guarda só elas: as tabelas do Data4U têm dezenas de colunas
    e o app usa poucas, então isso poupa a memória do PC (o resultado é o mesmo, porque só essas colunas são lidas)."""
    try:
        texto = conteudo.decode("utf-8")
    except UnicodeDecodeError:
        raise CopiaInvalida(f"{tabela}.jsonl não está em UTF-8.") from None
    linhas = []
    for numero, bruta in enumerate(texto.split("\n"), start=1):
        if not bruta.strip():
            continue
        try:
            linha = json.loads(bruta, parse_constant=_recusar_constante)
        except ValueError:
            raise CopiaInvalida(f"{tabela}.jsonl, linha {numero}: não é JSON válido.") from None
        if not isinstance(linha, dict):
            raise CopiaInvalida(f"{tabela}.jsonl, linha {numero}: esperava um objeto JSON.")
        linhas.append(linha if colunas is None else {c: linha[c] for c in colunas if c in linha})
    return linhas


def _ler_manifesto(conteudo: bytes) -> dict:
    try:
        manifesto = json.loads(conteudo.decode("utf-8"), parse_constant=_recusar_constante)
    except ValueError:  # (UnicodeDecodeError e JSONDecodeError também são ValueError)
        manifesto = None
    if not isinstance(manifesto, dict) or not isinstance(manifesto.get("extracao"), str) or not isinstance(manifesto.get("tabelas"), dict):
        raise CopiaInvalida("O _manifesto.json não está no formato esperado.")
    return manifesto


def _numero_como_texto(numero: float) -> str:
    """O mesmo texto que o JavaScript faria com String(numero): 20.0 vira "20", 12.5 continua "12.5"."""
    if not math.isfinite(numero):
        raise CopiaInvalida("A cópia tem um número impossível.")
    if numero == 0:
        return "0"
    if not 1e-6 <= abs(numero) < 1e21:
        raise CopiaInvalida("A cópia tem um número fora do esperado.")  # o JavaScript usaria notação científica
    return format(Decimal(repr(numero)).normalize(), "f")


def _para_texto(valor):
    if valor is None or isinstance(valor, str):
        return valor
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, float):
        return _numero_como_texto(valor)
    raise CopiaInvalida("A cópia tem um valor composto onde se esperava texto ou número.")


def _reduzir(colunas: list[str], linhas: list[dict]) -> list[list]:
    return [
        [_para_texto(linha.get(coluna)) if coluna in COLUNAS_DE_TEXTO else linha.get(coluna) for coluna in colunas]
        for linha in linhas
    ]


def _ler_tabela(arquivos: dict[str, bytes], manifesto: dict, tabela: str, colunas: list[str]) -> list[dict]:
    """Lê uma tabela e confere contra o manifesto: ela existe lá, tem as colunas de que o app precisa e o número de
    linhas bate (senão o .zip pode ter sido cortado)."""
    dados = manifesto["tabelas"].get(tabela)
    if not isinstance(dados, dict) or not isinstance(dados.get("colunas"), list) or not isinstance(dados.get("linhas"), int):
        raise CopiaInvalida(f"O manifesto não descreve a tabela {tabela}.")
    faltam = [c for c in colunas if c not in dados["colunas"]]
    if faltam:
        raise CopiaInvalida(f"A tabela {tabela} da cópia não tem a(s) coluna(s) {', '.join(faltam)}.")
    if tabela + ".jsonl" not in arquivos:
        raise CopiaInvalida(f"Não achei {tabela}.jsonl dentro do arquivo.")
    linhas = _linhas_json(arquivos[tabela + ".jsonl"], tabela, colunas)
    if len(linhas) != dados["linhas"]:
        raise CopiaInvalida(
            f"{tabela}: o manifesto diz {dados['linhas']} linhas e o arquivo tem {len(linhas)}. "
            "A cópia pode ter sido cortada: gere de novo."
        )
    return linhas


def colunas_a_enviar(manifesto: dict, tabela: str) -> list[str]:
    """As colunas que vão desta tabela. PESSOA leva também o endereço quando a cópia tem as seis colunas dele."""
    colunas = list(COLUNAS_ENVIADAS[tabela])
    dados = manifesto["tabelas"].get(tabela)
    existentes = dados.get("colunas") if isinstance(dados, dict) else None
    if tabela == "PESSOA" and isinstance(existentes, list) and all(c in existentes for c in COLUNAS_DO_ENDERECO):
        colunas += COLUNAS_DO_ENDERECO
    return colunas


def montar_pacote(arquivos: dict[str, bytes]) -> tuple[dict, dict]:
    """O pacote dos alunos (vai para /api/alunos/importar). `arquivos`: {"_manifesto.json": bytes, "PESSOA.jsonl": bytes, ...}."""
    manifesto = _ler_manifesto(arquivos["_manifesto.json"])
    pacote = {"extracao": manifesto["extracao"], "tabelas": {}}
    resumo = {"extracao": manifesto["extracao"], "linhas": {}}
    for tabela, colunas in COLUNAS_ENVIADAS.items():
        colunas = colunas_a_enviar(manifesto, tabela)
        linhas = _ler_tabela(arquivos, manifesto, tabela, colunas)
        resumo["linhas"][tabela] = len(linhas)
        if tabela == "CONTATO_PESSOA":  # só celular e e-mail; telefone fixo e comercial nem saem do PC
            linhas = [l for l in linhas if l.get("ID_TIPO_CONTATO") in TIPOS_DE_CONTATO_ENVIADOS]
        pacote["tabelas"][tabela] = {"colunas": list(colunas), "linhas": _reduzir(colunas, linhas)}
    dados = manifesto["tabelas"].get(TABELA_DE_ACESSOS)
    if TABELA_DE_ACESSOS + ".jsonl" in arquivos and isinstance(dados, dict) and all(c in (dados.get("colunas") or []) for c in COLUNAS_DE_ACESSOS):
        linhas = _ler_tabela(arquivos, manifesto, TABELA_DE_ACESSOS, COLUNAS_DE_ACESSOS)
        try:
            desde = (datetime.strptime(manifesto["extracao"][:10], "%d/%m/%Y") - timedelta(days=DIAS_DE_ACESSO)).strftime("%Y-%m-%d")
        except ValueError:
            raise CopiaInvalida("O _manifesto.json não informa direito a data da cópia.") from None
        recentes = [l for l in linhas if isinstance(l.get("DT_LAST_ACCESS"), str) and l["DT_LAST_ACCESS"][:10] >= desde]
        resumo["linhas"][TABELA_DE_ACESSOS] = len(recentes)
        pacote["tabelas"][TABELA_DE_ACESSOS] = {"colunas": list(COLUNAS_DE_ACESSOS), "linhas": _reduzir(COLUNAS_DE_ACESSOS, recentes)}
    return pacote, resumo


def _conjunto(linhas: list[dict], coluna: str, ignorar_vazios: bool = False) -> set:
    valores = [l.get(coluna) for l in linhas]
    try:
        return {v for v in valores if not (ignorar_vazios and v is None)}
    except TypeError:
        raise CopiaInvalida(f"A coluna {coluna} da cópia tem um valor composto.") from None


def montar_pacote_de_treinos(arquivos: dict[str, bytes]) -> tuple[dict, dict]:
    """O pacote do histórico de treinos (vai para /api/treinos/importar). Precisa também do PESSOA.jsonl."""
    manifesto = _ler_manifesto(arquivos["_manifesto.json"])
    lidas = {t: _ler_tabela(arquivos, manifesto, t, colunas) for t, colunas in COLUNAS_DOS_TREINOS.items()}

    lancamentos = _conjunto(lidas["TREINO"], "ID_LANCAMENTO", ignorar_vazios=True)
    professores = _conjunto(lidas["TREINO"], "ID_PROFESSOR", ignorar_vazios=True)
    exercicios_usados = _conjunto(lidas["TREINO_PRESCRICAO"], "ID_TREINO_EXERCICIO")
    try:
        aproveitadas = {
            **lidas,
            "LANCAMENTO_OBJ": [l for l in lidas["LANCAMENTO_OBJ"] if l.get("ID_LANCAMENTO") in lancamentos],
            "PESSOA": [p for p in lidas["PESSOA"] if p.get("ID") in professores],
            "TREINO_EXERCICIO": [e for e in lidas["TREINO_EXERCICIO"] if e.get("ID_TREINO_EXERCICIO") in exercicios_usados],
        }
    except TypeError:
        raise CopiaInvalida("A cópia tem um identificador com valor composto.") from None

    pacote = {"extracao": manifesto["extracao"], "tabelas": {}}
    for tabela, colunas in COLUNAS_DOS_TREINOS.items():
        pacote["tabelas"][tabela] = {"colunas": list(colunas), "linhas": _reduzir(colunas, aproveitadas[tabela])}
    resumo = {
        "treinos": len(lidas["TREINO"]),
        "fichas": len(lidas["TREINO_FICHA"]),
        "prescricoes": len(lidas["TREINO_PRESCRICAO"]),
    }
    return pacote, resumo


def ler_arquivos_do_zip(caminho: Path, tabelas: list[str], opcionais: tuple[str, ...] = ()) -> dict[str, bytes]:
    """Abre SÓ as entradas pedidas do .zip (o resto das 258 tabelas nem é lido) e devolve {nome: bytes}. As `opcionais` são lidas
    se existirem (sem elas o pacote vai como antes)."""
    nomes = ["_manifesto.json"] + [t + ".jsonl" for t in tabelas] + [t + ".jsonl" for t in opcionais]
    arquivos = {}
    try:
        with zipfile.ZipFile(caminho) as zip_:
            for nome in nomes:
                try:
                    info = zip_.getinfo(nome)
                except KeyError:
                    if nome in [t + ".jsonl" for t in opcionais]:
                        continue
                    raise CopiaInvalida(f"Não achei {nome} dentro do arquivo.") from None
                if info.flag_bits & 0x1:
                    raise CopiaInvalida(f"{nome} está protegido por senha.")
                if info.file_size > TAMANHO_MAXIMO_DA_TABELA:
                    raise CopiaInvalida(f"{nome} é grande demais para ser a tabela esperada.")
                arquivos[nome] = zip_.read(nome)
    except zipfile.BadZipFile:
        raise CopiaInvalida("O base_total.zip está danificado (ou cortado).") from None
    except (zipfile.LargeZipFile, NotImplementedError, EOFError, RuntimeError):
        raise CopiaInvalida("O base_total.zip usa um formato que este programa não lê.") from None
    return arquivos


TABELAS_DOS_ALUNOS = list(COLUNAS_ENVIADAS)
TABELAS_OPCIONAIS_DOS_ALUNOS = (TABELA_DE_ACESSOS,)
TABELAS_DOS_TREINOS = list(COLUNAS_DOS_TREINOS)  # (PESSOA entra nas duas listas)


def data_da_extracao(texto) -> datetime | None:
    """'07/10/2026 05:00:17' (horário do PC) -> datetime; None se o texto não for isso."""
    try:
        return datetime.strptime(texto, "%d/%m/%Y %H:%M:%S")  # noqa: DTZ007 (horário do relógio do PC, sem fuso, como o Data4U grava)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ o que já foi enviado


def ler_estado(pasta: Path) -> dict:
    """{"alunos": "<data da cópia já enviada>", "treinos": "...", "fotos": "<dia das fotos enviadas>"}. Ausente ou estragado = nada enviado."""
    try:
        estado = json.loads((pasta / ARQUIVO_DO_ESTADO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in estado.items() if k in ("alunos", "treinos", "fotos") and isinstance(v, str)} if isinstance(estado, dict) else {}


def gravar_estado(pasta: Path, estado: dict) -> None:
    temporario = pasta / (ARQUIVO_DO_ESTADO + ".tmp")
    temporario.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporario, pasta / ARQUIVO_DO_ESTADO)  # troca inteira: desligar o PC no meio não deixa arquivo pela metade


def etapas_pendentes(estado: dict, extracao: str, forcar: bool = False) -> list[str]:
    """Quais assuntos ainda não receberam esta cópia. Só envia cópia MAIS NOVA que a última enviada."""
    nova = data_da_extracao(extracao)
    if nova is None:
        raise CopiaInvalida(f"Não entendi a data da cópia ({extracao!r}).")
    pendentes = []
    for chave, _rota, _assunto in ETAPAS:
        enviada = data_da_extracao(estado.get(chave))
        if forcar or enviada is None or nova > enviada:
            pendentes.append(chave)
    return pendentes


# ------------------------------------------------------------------ falar com o servidor


def endereco_valido(endereco: str) -> str:
    partes = urlsplit(endereco)
    local = partes.hostname in ("localhost", "127.0.0.1", "::1")
    if partes.scheme != "https" and not (partes.scheme == "http" and local):
        raise ValueError("O endereço do app precisa começar com https:// (a chave não pode viajar aberta).")
    if not partes.hostname or partes.path not in ("", "/") or partes.query or partes.fragment:
        raise ValueError("Use só o endereço do app, sem caminho (ex.: https://app.gloriafit.com.br).")
    return f"{partes.scheme}://{partes.netloc}"


class _NaoSeguirRedirecionamento(urllib.request.HTTPRedirectHandler):
    """Um POST que o servidor redireciona viraria GET e perderia o corpo em silêncio: melhor tratar como erro."""

    def redirect_request(self, *args, **kwargs):
        return None


def _pedir(url: str, corpo: dict, chave: str | None, segundos: int):
    """POST de JSON. Devolve (status, corpo_json_ou_None, cabecalhos). Levanta SemRede se não houver conversa."""
    dados = json.dumps(corpo, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(dados) > TAMANHO_MAXIMO_DO_PACOTE:
        raise CopiaInvalida(f"O pacote ficou com {len(dados) // (1024 * 1024)} MB, acima do que o servidor aceita.")
    cabecalhos = {"Content-Type": "application/json", "User-Agent": f"GloriaFit-EnvioDiario/{VERSAO}"}
    if chave:
        cabecalhos["Cookie"] = f"{NOME_DO_COOKIE}={chave}"
    pedido = urllib.request.Request(url, data=dados, headers=cabecalhos, method="POST")
    abridor = urllib.request.build_opener(_NaoSeguirRedirecionamento)
    try:
        with abridor.open(pedido, timeout=segundos) as resposta:
            return resposta.status, _json_ou_none(resposta.read()), resposta.headers
    except urllib.error.HTTPError as erro:
        try:
            return erro.code, _json_ou_none(erro.read()), erro.headers
        finally:
            erro.close()
    except (urllib.error.URLError, http.client.HTTPException, OSError) as erro:  # (TimeoutError e ConnectionError são OSError)
        raise SemRede(str(getattr(erro, "reason", erro))) from None


def _json_ou_none(bytes_):
    try:
        corpo = json.loads(bytes_.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return corpo if isinstance(corpo, dict) else None


def enviar_http(endereco: str, rota: str, pacote: dict, chave: str):
    """(status, corpo) de um envio. É a peça que os testes trocam por uma de mentira."""
    status, corpo, _ = _pedir(endereco + rota, pacote, chave, SEGUNDOS_ATE_DESISTIR_DO_SERVIDOR)
    return status, corpo


def interpretar_resposta(status: int, corpo, assunto: str) -> str:
    """Devolve o texto do relatório do servidor (sucesso) ou levanta o erro certo. Só 200 com relatório é sucesso."""
    if status == 200 and isinstance(corpo, dict) and isinstance(corpo.get("texto"), str):
        return corpo["texto"]
    if status == 401:
        raise NaoAutorizado("O servidor não reconhece este PC. Rode: python enviar_alunos.py --autorizar")
    if status == 413:
        raise CopiaInvalida("O arquivo enviado ficou grande demais para o servidor.")
    if status == 400 and isinstance(corpo, dict) and isinstance(corpo.get("erro"), str):
        raise CopiaInvalida(corpo["erro"] + " Nada foi alterado.")
    raise SemRede(f"O servidor não conseguiu atualizar {assunto} (resposta {status}). Nada foi confirmado.")


def autorizar_pc(endereco: str, codigo: str) -> str:
    """Troca o código de uso único pela chave do PC. Devolve a chave (nunca imprima)."""
    status, corpo, cabecalhos = _pedir(endereco + "/api/autorizar", {"codigo": codigo.strip()}, None, 60)
    if status != 200:
        motivo = corpo.get("erro") if isinstance(corpo, dict) else None
        raise NaoAutorizado(motivo or f"O servidor recusou o código (resposta {status}).")
    for texto in cabecalhos.get_all("Set-Cookie") or []:
        cookie = SimpleCookie()
        try:
            cookie.load(texto)
        except CookieError:
            continue
        if NOME_DO_COOKIE in cookie and cookie[NOME_DO_COOKIE].value:
            return cookie[NOME_DO_COOKIE].value
    raise NaoAutorizado("O servidor aceitou o código mas não mandou a chave. Fale com o Thiago.")


def ler_chave(pasta: Path) -> str | None:
    try:
        chave = (pasta / ARQUIVO_DA_CHAVE).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return chave or None


def gravar_chave(pasta: Path, chave: str) -> None:
    arquivo = pasta / ARQUIVO_DA_CHAVE
    arquivo.write_text(chave + "\n", encoding="utf-8")
    try:
        os.chmod(arquivo, 0o600)  # no Windows quase não muda nada; no resto, só o dono lê
    except OSError:
        pass


# ------------------------------------------------------------------ registro do que aconteceu


class Registro:
    """Escreve no enviar_alunos_log.txt (e na tela, quando há tela: a tarefa agendada roda sem janela)."""

    def __init__(self, pasta: Path, agora=None):
        self.arquivo = pasta / ARQUIVO_DO_LOG
        self.agora = agora or datetime.now  # (hora do relógio do PC, só para o log)

    def __call__(self, texto: str) -> None:
        for linha in texto.splitlines() or [""]:
            if sys.stdout is not None:
                try:
                    print(linha)
                except (UnicodeEncodeError, OSError):
                    print(linha.encode("ascii", "replace").decode("ascii"))
        self._girar_se_grande()
        marca = f"{self.agora():%d/%m/%Y %H:%M:%S}"
        try:
            with open(self.arquivo, "a", encoding="utf-8") as saida:
                for linha in texto.splitlines() or [""]:
                    saida.write(f"{marca}  {linha}\n")
        except OSError:
            pass  # não poder escrever o log nunca deve impedir o envio

    def _girar_se_grande(self) -> None:
        try:
            if self.arquivo.stat().st_size > TAMANHO_MAXIMO_DO_LOG:
                os.replace(self.arquivo, self.arquivo.with_suffix(".antigo.txt"))
        except OSError:
            pass


# ------------------------------------------------------------------ o envio de verdade


def extracao_em_andamento(pasta: Path, agora: float | None = None) -> bool:
    """A extração monta o base_total_nova.zip e só no fim troca pelo base_total.zip. Arquivo velho parado não conta."""
    try:
        idade = (agora if agora is not None else time.time()) - (pasta / NOME_DO_ZIP_EM_CONSTRUCAO).stat().st_mtime
    except OSError:
        return False
    return idade < 30 * 60


def esperar_extracao(pasta: Path, registro, dormir=time.sleep, relogio=time.time) -> None:
    """Depois de ligar o PC, a cópia das 05:00 e este envio começam juntos: espera a cópia terminar (até 25 min)."""
    limite = relogio() + MINUTOS_DE_ESPERA_PELA_EXTRACAO * 60
    avisou = False
    while extracao_em_andamento(pasta, relogio()):
        if relogio() >= limite:
            registro("A extração do Data4U ainda não terminou; sigo com a cópia que já existe.")
            return
        if not avisou:
            registro("A extração do Data4U está rodando agora; espero ela terminar.")
            avisou = True
        dormir(20)


def enviar_com_tentativas(enviar, endereco: str, rota: str, pacote: dict, chave: str, registro, dormir=time.sleep):
    """Tenta de novo só quando não houve conversa com o servidor (internet que ainda não subiu depois de ligar o PC).
    Resposta do servidor, boa ou ruim, nunca é repetida aqui: a próxima tentativa é a do próximo horário."""
    for tentativa in range(1, TENTATIVAS_SEM_REDE + 1):
        try:
            return enviar(endereco, rota, pacote, chave)
        except SemRede as erro:
            if tentativa == TENTATIVAS_SEM_REDE:
                raise
            registro(f"Sem conversa com o servidor ({erro}). Tento de novo em {SEGUNDOS_ENTRE_TENTATIVAS} s.")
            dormir(SEGUNDOS_ENTRE_TENTATIVAS)


def executar(
    pasta: Path,
    endereco: str,
    *,
    forcar: bool = False,
    enviar=enviar_http,
    registro=None,
    dormir=time.sleep,
    relogio=time.time,
    ler_fotos=None,
) -> int:
    """O envio do dia. Devolve 0 (enviou, ou não havia nada novo) ou 1 (algo falhou; o motivo está no log)."""
    registro = registro or Registro(pasta)
    chave = ler_chave(pasta)
    if chave is None:
        registro("Este PC ainda não foi autorizado. Rode uma vez: python enviar_alunos.py --autorizar")
        return 1

    esperar_extracao(pasta, registro, dormir, relogio)
    caminho = pasta / NOME_DO_ZIP
    if not caminho.is_file():
        registro(f"Não achei o {NOME_DO_ZIP} em {pasta}. Tento de novo no próximo horário.")
        return 1

    try:
        manifesto = _ler_manifesto(ler_arquivos_do_zip(caminho, [])["_manifesto.json"])
        pendentes = etapas_pendentes(ler_estado(pasta), manifesto["extracao"], forcar)
        if not pendentes:
            registro(f"Nada novo: a cópia de {manifesto['extracao']} já foi enviada.")
        else:
            registro(f"Cópia do Data4U de {manifesto['extracao']}: enviando {' e '.join(pendentes)}.")

        estado = ler_estado(pasta)
        for chave_da_etapa, rota, assunto in ETAPAS:
            if chave_da_etapa not in pendentes:
                continue
            # (monta um pacote por vez: o de treinos ocupa memória e só nasce depois de os alunos terem ido)
            if chave_da_etapa == "alunos":
                pacote, _ = montar_pacote(ler_arquivos_do_zip(caminho, TABELAS_DOS_ALUNOS, TABELAS_OPCIONAIS_DOS_ALUNOS))
            else:
                pacote, _ = montar_pacote_de_treinos(ler_arquivos_do_zip(caminho, TABELAS_DOS_TREINOS))
            status, corpo = enviar_com_tentativas(enviar, endereco, rota, pacote, chave, registro, dormir)
            relatorio = interpretar_resposta(status, corpo, assunto)
            estado[chave_da_etapa] = manifesto["extracao"]
            gravar_estado(pasta, estado)  # grava a cada etapa: se a seguinte falhar, a próxima tentativa só refaz a que falta
            registro(f"Enviado: {assunto}.\n{relatorio}")

        # As fotos (29/10/2026): uma vez por dia, depois dos alunos (o servidor só aceita foto de aluno que ele já conhece).
        hoje = datetime.fromtimestamp(relogio()).strftime("%d/%m/%Y")
        if forcar or estado.get("fotos") != hoje:
            feito = enviar_fotos(pasta, endereco, chave, enviar, registro, dormir, ler_fotos or ler_fotos_do_cache)
            if feito is False:
                return 1
            if feito:
                estado["fotos"] = hoje
                gravar_estado(pasta, estado)
    except CopiaInvalida as erro:
        registro(f"NÃO ENVIADO: {erro}")
        return 1
    except NaoAutorizado as erro:
        registro(f"NÃO ENVIADO: {erro}")
        return 1
    except SemRede as erro:
        registro(f"NÃO ENVIADO: não consegui falar com o servidor ({erro}). Tento de novo no próximo horário.")
        return 1
    return 0


# ------------------------------------------------------------------ fotos dos alunos (29/10/2026)


def id_da_chave_da_foto(chave) -> int | None:
    """'foto/4257_im_foto' -> 4257 (o id da pessoa no Data4U). Qualquer outra coisa -> None."""
    if not isinstance(chave, str) or not chave.startswith("foto/") or not chave.endswith("_im_foto"):
        return None
    numero = chave[len("foto/") : -len("_im_foto")]
    return int(numero) if numero.isdigit() and len(numero) <= 12 else None


def copiar_cache(origem: Path, destino: Path) -> None:
    """Copia o CACHE.D4U com o Data4U aberto (o Data4U não deixa dois programas abrirem o mesmo banco: lê-se a cópia)."""
    with open(origem, "rb") as entrada, open(destino, "wb") as saida:
        while True:
            pedaco = entrada.read(4 * 1024 * 1024)
            if not pedaco:
                break
            saida.write(pedaco)


def ler_fotos_do_cache(pasta: Path, origem: Path | None = None, cliente: Path | None = None) -> dict[int, bytes] | None:
    """{id da pessoa: bytes da foto} lidos de uma cópia do CACHE.D4U. None se não dá para ler aqui (sem cache ou sem o leitor do
    Firebird): as fotos ficam para depois, sem atrapalhar o resto. Só lê as chaves de foto; a cópia é apagada no fim."""
    import importlib  # o leitor do Firebird é carregado só aqui: o resto do programa continua só com a biblioteca padrão

    origem = origem or PASTA_DO_DATA4U / NOME_DO_CACHE
    cliente = cliente or CLIENTE_DO_FIREBIRD
    if not origem.is_file() or not cliente.is_file():
        return None
    try:
        fb = importlib.import_module("firebird.driver")
    except ImportError:
        return None
    copia = pasta / COPIA_DO_CACHE
    try:
        copiar_cache(origem, copia)
        fb.driver_config.fb_client_library.value = str(cliente)
        fotos = {}
        with fb.connect(str(copia), user="SYSDBA", charset="WIN1252") as conexao:
            cursor = conexao.cursor()
            cursor.execute("SELECT ds_key, ds_blob FROM blob_cache WHERE ds_key STARTING WITH 'foto/'")
            for chave, blob in cursor:
                identificador = id_da_chave_da_foto(chave)
                dados = blob.read() if hasattr(blob, "read") else blob
                if identificador is not None and isinstance(dados, bytes) and 0 < len(dados) <= TAMANHO_MAXIMO_DA_FOTO:
                    fotos[identificador] = dados
        return fotos
    finally:
        try:
            copia.unlink()
        except OSError:
            pass


def planejar_fotos(estado_do_servidor, fotos_do_cache: dict[int, bytes]) -> tuple[list[tuple[int, bytes]], list[int]]:
    """(fotos a mandar, ids que têm foto no cache hoje). Só alunos que o servidor listou; só foto nova ou diferente da que ele tem."""
    import hashlib

    alunos = estado_do_servidor.get("alunos") if isinstance(estado_do_servidor, dict) else None
    if not isinstance(alunos, list):
        raise SemRede("O servidor não disse quais alunos estão em uso.")
    resumos = {a["id"]: a.get("sha256") for a in alunos if isinstance(a, dict) and isinstance(a.get("id"), int)}
    presentes = sorted(i for i in fotos_do_cache if i in resumos)
    mandar = [(i, fotos_do_cache[i]) for i in presentes if hashlib.sha256(fotos_do_cache[i]).hexdigest() != resumos[i]]
    return mandar, presentes


def pacotes_de_fotos(mandar: list[tuple[int, bytes]], presentes: list[int], por_pacote: int) -> list[dict]:
    """Divide as fotos em pacotes (até `por_pacote` fotos e BYTES_DE_FOTO_POR_PACOTE). Todo pacote leva a lista de presentes; sem foto
    nova, vai um pacote só com ela (é o que diz ao servidor que essas fotos continuam valendo)."""
    import base64

    pacotes, atual, tamanho = [], [], 0
    for identificador, dados in mandar:
        if atual and (len(atual) >= por_pacote or tamanho + len(dados) > BYTES_DE_FOTO_POR_PACOTE):
            pacotes.append(atual)
            atual, tamanho = [], 0
        atual.append({"id": identificador, "jpg": base64.b64encode(dados).decode("ascii")})
        tamanho += len(dados)
    if atual or not pacotes:
        pacotes.append(atual)
    return [{"fotos": fotos, "presentes": presentes} for fotos in pacotes]


def enviar_fotos(pasta: Path, endereco: str, chave: str, enviar, registro, dormir, ler_fotos=ler_fotos_do_cache) -> bool | None:
    """A etapa das fotos. True = feita; None = não dá para fazer neste PC agora (avisa e tenta no próximo horário, sem contar como
    falha do envio); False = o servidor recusou ou não respondeu (conta como falha; tenta no próximo horário)."""
    fotos_do_cache = ler_fotos(pasta)
    if fotos_do_cache is None:
        registro("Fotos: não deu para ler o CACHE.D4U neste PC (arquivo ou leitor do Firebird não encontrado). Ficam para depois.")
        return None
    status, estado = enviar_com_tentativas(enviar, endereco, ROTA_DO_ESTADO_DAS_FOTOS, {}, chave, registro, dormir)
    if status == 401:
        raise NaoAutorizado("O servidor não reconhece este PC. Rode: python enviar_alunos.py --autorizar")
    if status != 200:
        registro(f"Fotos: o servidor não respondeu como esperado (resposta {status}). Tento de novo no próximo horário.")
        return False
    mandar, presentes = planejar_fotos(estado, fotos_do_cache)
    por_pacote = estado.get("fotos_por_pacote") if isinstance(estado.get("fotos_por_pacote"), int) else 100
    total = {"gravadas": 0, "recusadas": 0, "apagadas": 0}
    for pacote in pacotes_de_fotos(mandar, presentes, max(1, por_pacote)):
        status, corpo = enviar_com_tentativas(enviar, endereco, ROTA_DAS_FOTOS, pacote, chave, registro, dormir)
        if status != 200 or not isinstance(corpo, dict):
            motivo = corpo.get("erro") if isinstance(corpo, dict) else None
            registro(f"Fotos: o servidor recusou um pacote (resposta {status}{': ' + motivo if motivo else ''}). Tento de novo depois.")
            return False
        for campo in total:
            total[campo] += corpo.get(campo, 0) if isinstance(corpo.get(campo), int) else 0
    texto = f"Fotos: {len(presentes)} alunos em uso têm foto no Data4U; {total['gravadas']} novas ou trocadas enviadas"
    if total["recusadas"]:
        texto += f", {total['recusadas']} recusadas pelo servidor"
    if total["apagadas"]:
        texto += f", {total['apagadas']} antigas apagadas"
    registro(texto + ".")
    return True


def conferir(pasta: Path, registro=print, ler_fotos=ler_fotos_do_cache) -> int:
    """Monta os dois pacotes e mostra o resumo (e quantas fotos há no CACHE.D4U), sem enviar nada nem mexer no que já foi enviado."""
    caminho = pasta / NOME_DO_ZIP
    if not caminho.is_file():
        registro(f"Não achei o {NOME_DO_ZIP} em {pasta}.")
        return 1
    try:
        pacote_a, resumo_a = montar_pacote(ler_arquivos_do_zip(caminho, TABELAS_DOS_ALUNOS, TABELAS_OPCIONAIS_DOS_ALUNOS))
        pacote_t, resumo_t = montar_pacote_de_treinos(ler_arquivos_do_zip(caminho, TABELAS_DOS_TREINOS))
    except CopiaInvalida as erro:
        registro(f"A cópia não serve: {erro}")
        return 1

    def tamanho(pacote: dict) -> float:
        return len(json.dumps(pacote, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) / (1024 * 1024)

    tipos = [linha[2] for linha in pacote_a["tabelas"]["CONTATO_PESSOA"]["linhas"]]  # colunas: ID_CONTATO, ID_PESSOA, ID_TIPO_CONTATO, ...
    celulares, emails = tipos.count(TIPO_CONTATO_CELULAR), tipos.count(TIPO_CONTATO_EMAIL)
    registro(f"Cópia do Data4U de {resumo_a['extracao']}.")
    registro(
        f"Alunos: {resumo_a['linhas']['PESSOA']} pessoas, {resumo_a['linhas']['PESSOA_STATUS']} períodos de situação, "
        f"{resumo_a['linhas']['CONTATO_PESSOA']} contatos ({celulares} celulares, {emails} e-mails), "
        f"endereço {'incluído' if 'NR_CEP' in pacote_a['tabelas']['PESSOA']['colunas'] else 'não encontrado na cópia'}, "
        f"{resumo_a['linhas'].get(TABELA_DE_ACESSOS, 'sem')} acessos pela catraca nos últimos {DIAS_DE_ACESSO} dias. "
        f"Pacote: {tamanho(pacote_a):.1f} MB."
    )
    registro(
        f"Treinos: {resumo_t['treinos']} treinos, {resumo_t['fichas']} fichas, {resumo_t['prescricoes']} exercícios prescritos. "
        f"Pacote: {tamanho(pacote_t):.1f} MB."
    )
    fotos_do_cache = ler_fotos(pasta)
    if fotos_do_cache is None:
        registro("Fotos: não deu para ler o CACHE.D4U neste PC (arquivo ou leitor do Firebird não encontrado).")
    else:
        registro(f"Fotos: {len(fotos_do_cache)} pessoas com foto no CACHE.D4U ({sum(map(len, fotos_do_cache.values())) / (1024 * 1024):.1f} MB).")
    registro("Nada foi enviado.")
    return 0


# ------------------------------------------------------------------ a tarefa agendada do Windows


def xml_da_tarefa(comando: str, argumentos: str, pasta: str, usuario: str | None, comeco: datetime) -> str:
    """O XML que o Agendador de Tarefas do Windows lê. Roda só com o usuário logado (como a extração) e, se o PC
    estava desligado na hora, roda assim que der (StartWhenAvailable)."""
    gatilhos = "".join(
        "<CalendarTrigger>"
        f"<StartBoundary>{comeco:%Y-%m-%d}T{horario}:00</StartBoundary>"
        "<Enabled>true</Enabled><ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>"
        "</CalendarTrigger>"
        for horario in HORARIOS_DA_TAREFA
    )
    usuario_xml = f"<UserId>{escape(usuario)}</UserId>" if usuario else ""
    return (
        '<?xml version="1.0" encoding="UTF-16"?>'
        '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">'
        "<RegistrationInfo><Description>Envia os alunos e o historico de treinos do Data4U para o app da Gloria Fit.</Description></RegistrationInfo>"
        f"<Triggers>{gatilhos}</Triggers>"
        f'<Principals><Principal id="Author">{usuario_xml}<LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>'
        "<Settings>"
        "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>"
        "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>"
        "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>"
        "<StartWhenAvailable>true</StartWhenAvailable>"
        "<ExecutionTimeLimit>PT45M</ExecutionTimeLimit>"
        "<Enabled>true</Enabled>"
        "</Settings>"
        f'<Actions Context="Author"><Exec><Command>{escape(comando)}</Command><Arguments>{escape(argumentos)}</Arguments>'
        f"<WorkingDirectory>{escape(pasta)}</WorkingDirectory></Exec></Actions>"
        "</Task>"
    )


def instalar_tarefa(pasta: Path, registro=print) -> int:
    """Cria (ou refaz) a tarefa agendada. Não precisa de administrador. Só no Windows."""
    if os.name != "nt":
        registro("A tarefa agendada só existe no Windows.")
        return 1
    executavel = Path(sys.executable)
    sem_janela = executavel.with_name("pythonw.exe")  # sem janela preta piscando na tela da recepção
    comando = str(sem_janela if sem_janela.is_file() else executavel)
    usuario = f"{os.environ['USERDOMAIN']}\\{os.environ['USERNAME']}" if os.environ.get("USERNAME") and os.environ.get("USERDOMAIN") else None
    xml = xml_da_tarefa(comando, f'"{Path(__file__).resolve()}"', str(pasta), usuario, datetime.now())  # noqa: DTZ005
    with tempfile.NamedTemporaryFile("w", suffix=".xml", encoding="utf-16", delete=False) as temporario:
        temporario.write(xml)
    try:
        resultado = subprocess.run(
            ["schtasks", "/Create", "/TN", NOME_DA_TAREFA, "/XML", temporario.name, "/F"],
            capture_output=True, text=True, check=False,
        )
    finally:
        os.unlink(temporario.name)
    if resultado.returncode != 0:
        registro(f"O Windows recusou criar a tarefa: {(resultado.stdout + resultado.stderr).strip()}")
        return 1
    registro(f"Tarefa {NOME_DA_TAREFA} criada: todo dia às {', '.join(HORARIOS_DA_TAREFA)}.")
    return 0


# ------------------------------------------------------------------ linha de comando


def main(argv: list[str] | None = None) -> int:
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # o console do Windows nem sempre aceita acento
    analisador = argparse.ArgumentParser(description="Envia os alunos e o histórico de treinos do Data4U para o app.")
    grupo = analisador.add_mutually_exclusive_group()
    grupo.add_argument("--autorizar", action="store_true", help="autoriza este PC com um código de uso único")
    grupo.add_argument("--conferir", action="store_true", help="monta os pacotes e mostra o resumo, sem enviar")
    grupo.add_argument("--instalar", action="store_true", help="cria a tarefa agendada do Windows")
    analisador.add_argument("--forcar", action="store_true", help="envia mesmo que a cópia já tenha sido enviada")
    analisador.add_argument("--endereco", default=ENDERECO_PADRAO, help=f"endereço do app (padrão: {ENDERECO_PADRAO})")
    analisador.add_argument("--pasta", default=None, help="pasta do base_total.zip (padrão: a pasta deste programa)")
    argumentos = analisador.parse_args(argv)

    pasta = Path(argumentos.pasta) if argumentos.pasta else Path(__file__).resolve().parent
    try:
        endereco = endereco_valido(argumentos.endereco)
    except ValueError as erro:
        print(erro)
        return 1

    if argumentos.autorizar:
        codigo = input("Código de autorização (o Thiago gera no servidor): ")
        try:
            chave = autorizar_pc(endereco, codigo)
        except (NaoAutorizado, SemRede) as erro:
            print(f"Não autorizou: {erro}")
            return 1
        gravar_chave(pasta, chave)
        Registro(pasta)("Este PC foi autorizado.")
        return 0
    if argumentos.conferir:
        return conferir(pasta)
    if argumentos.instalar:
        return instalar_tarefa(pasta)
    return executar(pasta, endereco, forcar=argumentos.forcar)


if __name__ == "__main__":
    sys.exit(main())
