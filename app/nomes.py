"""Nome de pessoa para a tela (28/10/2026, visual novo do painel).

O Data4U guarda os nomes em MAIÚSCULAS ("MARIANA DE SOUZA"). No topo da ficha do aluno o nome aparece como se escreve
("Mariana de Souza"). Só muda o jeito de mostrar: o nome gravado no banco continua igual.
"""

import re

# Palavras que ficam minúsculas no meio do nome
_LIGACOES = {"da", "das", "de", "do", "dos", "e", "di", "du", "del", "la", "le", "van", "von"}
# Sufixos que ficam como siglas
_SIGLAS = {"ii", "iii", "iv"}


def _palavra(palavra: str, primeira: bool) -> str:
    minuscula = palavra.lower()
    if not primeira and minuscula in _LIGACOES:
        return minuscula
    if minuscula in _SIGLAS:
        return minuscula.upper()
    # hífen e apóstrofo: cada pedaço com maiúscula ("Ana-Maria", "D'Ávila")
    return re.sub(r"[^\W\d_]+", lambda m: m.group(0)[:1].upper() + m.group(0)[1:], minuscula)


def nome_de_pessoa(texto: str | None) -> str:
    """'MARIANA DE SOUZA' -> 'Mariana de Souza'. Vazio fica vazio; espaços repetidos viram um só."""
    palavras = (texto or "").split()
    return " ".join(_palavra(p, i == 0) for i, p in enumerate(palavras))
