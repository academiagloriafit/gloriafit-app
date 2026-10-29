"""Nome de pessoa para a tela (visual novo do painel, 28/10/2026)."""

import pytest

from app.nomes import nome_de_pessoa


@pytest.mark.parametrize(
    "entrada, saida",
    [
        ("MARIANA SOUZA", "Mariana Souza"),
        ("MARIANA DE SOUZA", "Mariana de Souza"),
        ("JOÃO PEDRO DOS SANTOS E SILVA", "João Pedro dos Santos e Silva"),
        ("ÂNGELA  D'ÁVILA", "Ângela D'Ávila"),
        ("ANA-MARIA LIMA", "Ana-Maria Lima"),
        ("PEDRO ALVES II", "Pedro Alves II"),
        ("DE LIMA", "De Lima"),  # a primeira palavra sempre com maiúscula
        ("", ""),
        (None, ""),
    ],
)
def test_nome_de_pessoa(entrada, saida):
    assert nome_de_pessoa(entrada) == saida


@pytest.mark.parametrize(
    "entrada, saida",
    [("MARIANA DE SOUZA", "MS"), ("JOÃO PEDRO DOS SANTOS", "JS"), ("ÉRICA", "É"), ("", ""), (None, "")],
)
def test_iniciais(entrada, saida):
    from app.nomes import iniciais

    assert iniciais(entrada) == saida
