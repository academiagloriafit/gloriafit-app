"""Funções de texto usadas na busca."""

import unicodedata


def normalizar(texto: str | None) -> str:
    """Deixa o texto em minúsculas e sem acento: "Bíceps" vira "biceps".

    É assim que a busca compara: quem digita "biceps" encontra "Bíceps", e
    "SUPINO" encontra "supino". Texto vazio ou None vira "".
    """
    if texto is None:
        return ""
    # NFKD separa a letra do acento ("í" vira "i" + acento solto);
    # depois jogamos fora os acentos soltos.
    decomposto = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return sem_acento.casefold()
