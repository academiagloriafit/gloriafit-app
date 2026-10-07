"""Quem pode abrir a área do professor: computadores AUTORIZADOS.

Como funciona, do começo ao fim:

1. Quem tem acesso ao servidor gera um CÓDIGO de uso único para um computador, com o
   nome que ele terá ("Computador dos professores"). Comando: python -m app.dispositivos.
2. No computador, a pessoa abre o endereço /autorizar e digita o código.
3. O servidor confere o código (vale 15 minutos e só funciona uma vez), cria um
   "dispositivo" e entrega ao navegador um TOKEN secreto guardado em um cookie.
4. Dali em diante o navegador manda o cookie em todo pedido e o servidor o reconhece.
   Quem abrir o mesmo endereço em outro aparelho (um celular, por exemplo) não tem o
   cookie e não vê dado nenhum.

Por que assim, e não usuário e senha: o computador da academia fica sempre ligado e
ninguém quer digitar senha toda hora, mas a internet inteira consegue abrir o endereço.
O cookie faz o papel de "chave" gravada no navegador daquele computador.

Cuidados de segurança que este arquivo tem:
- O código e o token são sorteados com `secrets` (feito para segurança; `random` não é).
- O banco guarda só o HASH (SHA-256) de cada um, nunca o valor: quem copiar o banco não
  consegue usar o que viu. SHA-256 simples basta porque os valores são sorteados com
  muita aleatoriedade (senha escolhida por gente é que precisa de hash lento).
- Código errado em excesso trava novas tentativas por um tempo (força bruta).
- Código usado uma vez não serve de novo, mesmo se duas pessoas enviarem ao mesmo tempo.
- Computador parado há muito tempo perde a autorização; qualquer um pode ser revogado.
"""

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

NOME_DO_COOKIE = "gloriafit_dispositivo"

# Letras e números fáceis de ler e de digitar: sem I, L, O, 0 e 1, que se confundem.
# 31 símbolos em 10 posições = cerca de 800 trilhões de códigos possíveis.
ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
TAMANHO_DO_CODIGO = 10

VALIDADE_DO_CODIGO = timedelta(minutes=15)
LIMITE_DE_FALHAS = 5  # códigos errados permitidos...
JANELA_DE_FALHAS = timedelta(minutes=15)  # ...dentro deste tempo
VALIDADE_SEM_USO = timedelta(days=90)  # computador sem uso por tanto tempo perde a autorização
INTERVALO_DE_RENOVACAO = timedelta(hours=1)  # de quanto em quanto tempo o "último uso" é regravado
TAMANHO_MAXIMO_DO_NOME = 40  # o mesmo limite das colunas `nome` do schema

DURACAO_DO_COOKIE = timedelta(days=400)  # o máximo que os navegadores aceitam

_FORMATO_DATA = "%Y-%m-%d %H:%M:%S"  # UTC, como o resto do banco


class NomeInvalido(ValueError):
    """O nome dado ao computador está vazio, longo demais ou tem caracteres estranhos."""


class CodigoInvalido(Exception):
    """Código errado, já usado ou vencido. De propósito, não diz qual dos três."""


class MuitasTentativas(Exception):
    """Muitos códigos errados seguidos: novas tentativas ficam travadas por um tempo."""

    def __init__(self, segundos: int):
        super().__init__(f"Tente de novo em {segundos} segundos.")
        self.segundos = segundos


@dataclass(frozen=True)
class CodigoGerado:
    codigo: str  # já formatado: XXXXX-XXXXX
    nome: str
    expira_em: datetime  # UTC


@dataclass(frozen=True)
class Autorizacao:
    token: str  # o valor que vai para o cookie (só existe aqui; o banco guarda o hash)
    dispositivo_id: int
    nome: str


@dataclass(frozen=True)
class Dispositivo:
    id: int
    nome: str
    renovar_cookie: bool  # True quando o "último uso" acabou de ser regravado


# ------------------------------------------------------------------ pequenas ajudas


def _agora(agora: datetime | None) -> datetime:
    return (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)


def _texto(momento: datetime) -> str:
    return momento.astimezone(timezone.utc).strftime(_FORMATO_DATA)


def _momento(texto: str) -> datetime:
    return datetime.strptime(texto, _FORMATO_DATA).replace(tzinfo=timezone.utc)


def _hash(valor: str) -> str:
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()


def normalizar_codigo(digitado: object) -> str:
    """O que a pessoa digitou -> o código "puro": maiúsculas, sem espaços nem hífens.

    'abcde-23456' e ' ABCDE 23456 ' viram 'ABCDE23456'. Se não for texto, vira ''.
    """
    if not isinstance(digitado, str):
        return ""
    return "".join(c for c in digitado.upper() if not c.isspace() and c != "-")


def formatar_codigo(codigo: str) -> str:
    """'ABCDE23456' -> 'ABCDE-23456' (só para mostrar; o hífen é descartado na conferência)."""
    meio = len(codigo) // 2
    return f"{codigo[:meio]}-{codigo[meio:]}"


def limpar_nome(nome: object) -> str:
    """Nome do computador: sem espaços nas pontas nem repetidos, de 1 a 40 caracteres."""
    if not isinstance(nome, str):
        raise NomeInvalido("O nome do computador precisa ser um texto.")
    limpo = " ".join(nome.split())
    if not limpo:
        raise NomeInvalido("Dê um nome ao computador (por exemplo: Computador da recepção).")
    if len(limpo) > TAMANHO_MAXIMO_DO_NOME:
        raise NomeInvalido(f"O nome pode ter no máximo {TAMANHO_MAXIMO_DO_NOME} caracteres.")
    if not limpo.isprintable():
        raise NomeInvalido("O nome tem caracteres que não podem ser usados.")
    return limpo


# ------------------------------------------------------------------ gerar o código


def gerar_codigo(conn, nome: str, agora: datetime | None = None) -> CodigoGerado:
    """Cria um código de uso único para autorizar UM computador, com o nome dado."""
    nome = limpar_nome(nome)
    agora = _agora(agora)
    expira_em = agora + VALIDADE_DO_CODIGO

    for _ in range(5):  # colisão de código é praticamente impossível; 5 tentativas bastam
        puro = "".join(secrets.choice(ALFABETO) for _ in range(TAMANHO_DO_CODIGO))
        try:
            with conn:
                # Faxina: códigos que venceram há mais de um dia (usados ou não) não servem para nada.
                conn.execute(
                    "DELETE FROM codigo_de_autorizacao WHERE expira_em < ?",
                    (_texto(agora - timedelta(days=1)),),
                )
                conn.execute(
                    "INSERT INTO codigo_de_autorizacao"
                    " (codigo_hash, nome_do_dispositivo, criado_em, expira_em) VALUES (?, ?, ?, ?)",
                    (_hash(puro), nome, _texto(agora), _texto(expira_em)),
                )
        except sqlite3.IntegrityError as erro:
            if "UNIQUE" in str(erro):  # sorteou um código que já existe: sorteia outro
                continue
            raise
        return CodigoGerado(codigo=formatar_codigo(puro), nome=nome, expira_em=expira_em)
    raise RuntimeError("Não consegui sortear um código novo; tente de novo.")  # pragma: no cover


# ------------------------------------------------------------------ usar o código


def autorizar(conn, digitado: object, agora: datetime | None = None) -> Autorizacao:
    """Troca um código válido por um dispositivo autorizado e o token do cookie.

    Levanta MuitasTentativas (travado por excesso de erros) ou CodigoInvalido.
    """
    agora = _agora(agora)

    with conn:
        conn.execute(
            "DELETE FROM autorizacao_falha WHERE em <= ?", (_texto(agora - JANELA_DE_FALHAS),)
        )
    recentes = [
        _momento(linha[0])
        for linha in conn.execute("SELECT em FROM autorizacao_falha ORDER BY em")
    ]
    if len(recentes) >= LIMITE_DE_FALHAS:
        # Travado: nem confere o código (senão o atacante continuaria tentando) e NÃO
        # registra mais falhas (senão ficaria travado para sempre). Destrava quando a
        # falha mais antiga sair da janela.
        espera = (recentes[0] + JANELA_DE_FALHAS) - agora
        raise MuitasTentativas(max(1, int(espera.total_seconds()) + 1))

    puro = normalizar_codigo(digitado)

    with conn:
        # O UPDATE faz duas coisas de uma vez: confere (existe, não foi usado, não venceu)
        # e "queima" o código. Se dois pedidos chegarem juntos com o mesmo código, só um
        # consegue alterar a linha (rowcount == 1); o outro vê 0 e é recusado.
        queimou = False
        if len(puro) == TAMANHO_DO_CODIGO:
            queimou = (
                conn.execute(
                    "UPDATE codigo_de_autorizacao SET usado_em = ?"
                    " WHERE codigo_hash = ? AND usado_em IS NULL AND expira_em > ?",
                    (_texto(agora), _hash(puro), _texto(agora)),
                ).rowcount
                == 1
            )
        if queimou:
            token = secrets.token_urlsafe(32)  # 256 bits sorteados
            nome = conn.execute(
                "SELECT nome_do_dispositivo FROM codigo_de_autorizacao WHERE codigo_hash = ?",
                (_hash(puro),),
            ).fetchone()[0]
            dispositivo_id = conn.execute(
                "INSERT INTO dispositivo (nome, token_hash, criado_em, ultimo_uso_em)"
                " VALUES (?, ?, ?, ?)",
                (nome, _hash(token), _texto(agora), _texto(agora)),
            ).lastrowid
        else:
            conn.execute("INSERT INTO autorizacao_falha (em) VALUES (?)", (_texto(agora),))

    if not queimou:
        raise CodigoInvalido("Código inválido ou vencido.")
    return Autorizacao(token=token, dispositivo_id=dispositivo_id, nome=nome)


# ------------------------------------------------------------------ reconhecer o computador


def identificar(conn, token: object, agora: datetime | None = None) -> Dispositivo | None:
    """O token do cookie -> o dispositivo autorizado, ou None se não vale (não existe,
    foi revogado ou ficou tempo demais sem uso)."""
    if not isinstance(token, str):
        return None
    agora = _agora(agora)

    linha = conn.execute(
        "SELECT id, nome, ultimo_uso_em FROM dispositivo WHERE token_hash = ? AND revogado_em IS NULL",
        (_hash(token),),
    ).fetchone()
    if linha is None:
        return None

    ultimo_uso = _momento(linha["ultimo_uso_em"])
    if agora - ultimo_uso > VALIDADE_SEM_USO:
        return None

    renovar = agora - ultimo_uso >= INTERVALO_DE_RENOVACAO
    if renovar:
        # Regrava no máximo uma vez por hora: gravar a cada clique travaria o banco à toa.
        with conn:
            conn.execute(
                "UPDATE dispositivo SET ultimo_uso_em = ? WHERE id = ?", (_texto(agora), linha["id"])
            )
    return Dispositivo(id=linha["id"], nome=linha["nome"], renovar_cookie=renovar)


# ------------------------------------------------------------------ administrar


def revogar(conn, dispositivo_id: int, agora: datetime | None = None) -> bool:
    """Tira a autorização de um computador. False se ele não existe ou já estava revogado."""
    with conn:
        return (
            conn.execute(
                "UPDATE dispositivo SET revogado_em = ? WHERE id = ? AND revogado_em IS NULL",
                (_texto(_agora(agora)), dispositivo_id),
            ).rowcount
            == 1
        )


def listar(conn, agora: datetime | None = None) -> list[dict]:
    """Todos os computadores já autorizados, com a situação de cada um."""
    agora = _agora(agora)
    resultado = []
    for linha in conn.execute(
        "SELECT id, nome, criado_em, ultimo_uso_em, revogado_em FROM dispositivo ORDER BY id"
    ):
        if linha["revogado_em"]:
            situacao = "revogado"
        elif agora - _momento(linha["ultimo_uso_em"]) > VALIDADE_SEM_USO:
            situacao = "vencido"
        else:
            situacao = "ativo"
        resultado.append(
            {
                "id": linha["id"],
                "nome": linha["nome"],
                "criado_em": _momento(linha["criado_em"]),
                "ultimo_uso_em": _momento(linha["ultimo_uso_em"]),
                "situacao": situacao,
            }
        )
    return resultado
