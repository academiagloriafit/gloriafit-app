"""Datas do app: o banco guarda tudo em UTC; a academia vive no horário de Brasília.

Duas formas de data aparecem no banco:
- momento (`criado_em`, `concluido_em`, `feita_em`): 'AAAA-MM-DD HH:MM:SS' em UTC;
- dia (`treino.inicio`, `treino.fim`): 'AAAA-MM-DD', o dia NO CALENDÁRIO DA ACADEMIA (Brasília).
  Um treino que começa "dia 08" começa dia 08 em Brasília, não em Londres.
"""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

# Uma ficha montada às 23h30 de 06/10 não pode aparecer como 07/10.
FUSO_DA_ACADEMIA = ZoneInfo("America/Sao_Paulo")

FORMATO_DO_MOMENTO = "%Y-%m-%d %H:%M:%S"


def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def momento_para_texto(momento: datetime) -> str:
    """datetime (com fuso) -> 'AAAA-MM-DD HH:MM:SS' em UTC, como o banco guarda."""
    return momento.astimezone(timezone.utc).strftime(FORMATO_DO_MOMENTO)


def momento_local(texto_utc: str) -> datetime:
    """'2026-10-07 02:30:00' (UTC) -> o mesmo momento no horário de Brasília."""
    return datetime.strptime(texto_utc, FORMATO_DO_MOMENTO).replace(tzinfo=timezone.utc).astimezone(FUSO_DA_ACADEMIA)


def dia_local(texto_utc: str | None) -> str | None:
    """'2026-10-07 02:30:00' (UTC) -> '2026-10-06' (o dia em Brasília). Vazio -> None."""
    if not texto_utc:
        return None
    return momento_local(texto_utc).date().isoformat()


def hoje(agora: datetime | None = None) -> str:
    """O dia de hoje em Brasília, 'AAAA-MM-DD'."""
    return (agora or agora_utc()).astimezone(FUSO_DA_ACADEMIA).date().isoformat()


def ler_dia(texto) -> date | None:
    """'AAAA-MM-DD' -> date. Devolve None para qualquer outra coisa (inclusive 'AAAA-M-D', '2026-02-30' e não-texto).

    Rigoroso de propósito: só aceita exatamente 10 caracteres com algarismos comuns. O
    `date.fromisoformat` do Python aceita mais formatos conforme a versão.
    """
    if not isinstance(texto, str) or len(texto) != 10 or texto[4] != "-" or texto[7] != "-":
        return None
    partes = texto[:4] + texto[5:7] + texto[8:]
    if not (partes.isascii() and partes.isdigit()):
        return None
    try:
        return date(int(texto[:4]), int(texto[5:7]), int(texto[8:]))
    except ValueError:
        return None


def formatar_dia(texto: str | None) -> str | None:
    """'2026-10-06' -> '06/10/2026'. Vazio -> None."""
    dia = ler_dia(texto)
    return dia.strftime("%d/%m/%Y") if dia else None
