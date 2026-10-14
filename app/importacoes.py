"""De quando é a última atualização dos alunos e do histórico de treinos — e o aviso quando ela para.

A atualização é automática: o PC da recepção manda uma cópia do Data4U todo dia (app/static/recepcao/enviar_alunos.py).
Se esse envio parar (PC desligado, internet fora, autorização revogada), ninguém percebe por si só: o app continua
funcionando, só com os alunos de ontem, de anteontem... Aqui fica o registro de quando foi a última cópia aplicada,
para a tela avisar.

O que se guarda é a hora em que o PC TIROU a cópia (`extraido_em`), não a hora em que ela chegou: reenviar uma cópia
velha não deixa os alunos mais novos, e é a idade dos dados que importa para quem olha a tela. Uma linha por assunto,
sempre a última cópia aplicada (a mais nova que chegou ao app).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.datas import FUSO_DA_ACADEMIA, agora_utc, momento_local, momento_para_texto

TIPOS = ("alunos", "treinos")
NOMES = {"alunos": "Os alunos", "treinos": "O histórico de treinos"}

# Depois de quanto tempo o app avisa. Um fim de semana com o PC desligado dá uns dois dias sem cópia nova;
# o aviso é para quando passa disso. (A tela manual dizia 36 h; o automático roda todo dia, então 48 h = faltou um dia inteiro.)
HORAS_ATE_AVISAR = 48


@dataclass(frozen=True)
class Atualizacao:
    tipo: str
    extraido_em: datetime  # horário de Brasília
    recebida_em: datetime  # horário de Brasília


def registrar(conn, tipo: str, extraido_em: datetime, agora: datetime | None = None) -> None:
    """Anota que a cópia tirada em `extraido_em` (horário de Brasília, sem fuso, como vem do Data4U) foi aplicada.

    Não confirma nada por conta própria: quem chama já gravou os alunos/treinos. Um erro aqui não desfaz a importação
    (por isso roda depois dela, em separado) — só deixaria o aviso de atraso desatualizado.
    """
    if tipo not in TIPOS:
        raise ValueError(f"Assunto desconhecido: {tipo!r}.")
    if extraido_em.tzinfo is None:
        extraido_em = extraido_em.replace(tzinfo=FUSO_DA_ACADEMIA)
    extraido = momento_para_texto(extraido_em)
    recebida = momento_para_texto(agora or agora_utc())
    with conn:
        conn.execute(
            "INSERT INTO importacao (tipo, extraido_em, recebida_em) VALUES (?, ?, ?)"
            " ON CONFLICT(tipo) DO UPDATE SET extraido_em = excluded.extraido_em, recebida_em = excluded.recebida_em",
            (tipo, extraido, recebida),
        )


def ultimas(conn) -> dict[str, Atualizacao]:
    """{assunto: última atualização}. Assunto que nunca foi registrado não aparece."""
    return {
        linha["tipo"]: Atualizacao(
            tipo=linha["tipo"],
            extraido_em=momento_local(linha["extraido_em"]),
            recebida_em=momento_local(linha["recebida_em"]),
        )
        for linha in conn.execute("SELECT tipo, extraido_em, recebida_em FROM importacao")
    }


def quando(momento: datetime) -> str:
    """'14/10/2026 às 05:00' (horário de Brasília)."""
    return f"{momento:%d/%m/%Y} às {momento:%H:%M}"


def idade_em_horas(atualizacao: Atualizacao, agora: datetime | None = None) -> float:
    return ((agora or agora_utc()).astimezone(timezone.utc) - atualizacao.extraido_em.astimezone(timezone.utc)) / timedelta(hours=1)


def avisos_de_atraso(conn, agora: datetime | None = None) -> list[str]:
    """Frases para a tela, uma por assunto que está velho demais. Lista vazia = tudo em dia.

    Assunto que nunca foi registrado não gera aviso: banco recém-criado (ou recém-atualizado para a versão que tem
    este registro) ainda não tem de onde saber. O aviso passa a valer a partir da primeira cópia aplicada.
    """
    avisos = []
    for tipo, atualizacao in ultimas(conn).items():
        horas = idade_em_horas(atualizacao, agora)
        if horas > HORAS_ATE_AVISAR:
            avisos.append(
                f"{NOMES[tipo]} não são atualizados desde {quando(atualizacao.extraido_em)} (cópia do Data4U). "
                "Avise o Thiago: o envio automático do PC da recepção pode ter parado."
            )
    return avisos


def resumo_para_a_tela(conn, agora: datetime | None = None) -> list[dict]:
    """Uma linha por assunto para a tela de atualizar: {"nome", "extraido", "recebida", "atrasado"}."""
    registradas = ultimas(conn)
    linhas = []
    for tipo in TIPOS:
        atualizacao = registradas.get(tipo)
        if atualizacao is None:
            linhas.append({"nome": NOMES[tipo], "extraido": None, "recebida": None, "atrasado": False})
            continue
        linhas.append(
            {
                "nome": NOMES[tipo],
                "extraido": quando(atualizacao.extraido_em),
                "recebida": quando(atualizacao.recebida_em),
                "atrasado": idade_em_horas(atualizacao, agora) > HORAS_ATE_AVISAR,
            }
        )
    return linhas
