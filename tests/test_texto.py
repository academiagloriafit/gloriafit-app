"""Testes da normalização de texto usada na busca."""

import pytest

from app.texto import normalizar


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("Bíceps", "biceps"),
        ("ABDÔMEN", "abdomen"),
        ("Elevação conjugada", "elevacao conjugada"),
        ("Glúteos", "gluteos"),
        ("Ç ã é ü", "c a e u"),
        ("supino reto", "supino reto"),  # já normalizado: não muda
        ("", ""),
        (None, ""),
    ],
)
def test_normalizar_tira_acento_e_maiuscula(entrada, esperado):
    assert normalizar(entrada) == esperado


def test_normalizar_funciona_com_acento_decomposto():
    # "í" digitado como "i" + acento solto (acontece ao copiar de alguns sistemas)
    assert normalizar("bíceps") == "biceps"
