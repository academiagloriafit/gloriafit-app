"""Funções de texto usadas na busca."""

import re
import unicodedata

# O Data4U guarda em alguns exercícios o número da máquina no começo do nome: "(15) CADEIRA ABDUTORA".
# Nem toda máquina é numerada, então o número perdeu o sentido (decisão do Thiago, 08/10/2026).
# Só sai o número no INÍCIO, seguido de ")": "(15) ", "( 7 ) " e também "9)" (parêntese de abertura esquecido).
# Parênteses no meio do nome ("BOM DIA ( SQUAT MACHINE )") e números sem ")" ("5' ESTEIRA") ficam como estão.
_NUMERO_DA_MAQUINA = re.compile(r"^\s*\(?\s*[0-9]+\s*\)\s*")


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


def nome_para_exibir(nome: str | None) -> str:
    """O nome do exercício como aparece nas telas e no cupom, sem o número da máquina do começo.

    "(15) CADEIRA ABDUTORA" vira "CADEIRA ABDUTORA". O banco continua guardando o nome original (ele é a
    chave do exercício e vem do Data4U); só a EXIBIÇÃO muda. Se tirar o número deixaria o nome vazio,
    devolve o nome original.
    """
    if not nome:
        return ""
    limpo = _NUMERO_DA_MAQUINA.sub("", nome, count=1).strip()
    return limpo or nome
