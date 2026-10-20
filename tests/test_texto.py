"""Testes da normalização de texto usada na busca."""

import pytest

from app.texto import nome_para_exibir, normalizar, tirar_apagado


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


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("(15) CADEIRA ABDUTORA", "CADEIRA ABDUTORA"),
        ("(2) LEG HORIZONTAL", "LEG HORIZONTAL"),
        ("( 7 ) VOADOR", "VOADOR"),  # espaços dentro do parêntese
        ("  (24) HACK MACHINE", "HACK MACHINE"),  # espaço antes
        ("9)ELEVAÇÃO LATERAL UNIL.", "ELEVAÇÃO LATERAL UNIL."),  # parêntese de abertura esquecido
        ("(15)(2) DOIS NÚMEROS", "(2) DOIS NÚMEROS"),  # tira só o primeiro: não adivinhamos o resto
        # o que NÃO é número de máquina fica como está:
        ("BOM DIA ( SQUAT MACHINE )", "BOM DIA ( SQUAT MACHINE )"),
        ("AGACHAMENTO LIVRE (PIRÂMIDE CRESCENTE)", "AGACHAMENTO LIVRE (PIRÂMIDE CRESCENTE)"),
        ("5' ESTEIRA", "5' ESTEIRA"),
        ("SUPINO MAQUINA (6)", "SUPINO MAQUINA (6)"),  # número no fim não é o da máquina
        ("(A) ALGO", "(A) ALGO"),  # letra, não número
        ("(15)", "(15)"),  # tirar deixaria vazio: devolve o original
        ("", ""),
        (None, ""),
    ],
)
def test_nome_para_exibir_tira_so_o_numero_da_maquina_do_comeco(entrada, esperado):
    assert nome_para_exibir(entrada) == esperado


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("CADEIRA EXTENSORA APAGADO", "CADEIRA EXTENSORA"),
        ("Cadeira extensora Apagado ", "Cadeira extensora"),  # maiúscula e espaço no fim
        ("PULLEY FRENTE  APAGADO", "PULLEY FRENTE"),  # espaço duplo antes
        ("X APAGADO APAGADO", "X"),  # repetido (apagou duas vezes no Data4U)
        ("APAGADO", "APAGADO"),  # só a palavra: tirar deixaria vazio, devolve o original
        ("APAGADOR DE LOUSA", "APAGADOR DE LOUSA"),  # outra palavra
        ("APAGADO CADEIRA", "APAGADO CADEIRA"),  # no começo não sai: só no fim
        ("CADEIRA APAGADO EXTENSORA", "CADEIRA APAGADO EXTENSORA"),  # no meio não sai
        ("(15) CADEIRA ABDUTORA", "(15) CADEIRA ABDUTORA"),  # não mexe no número da máquina (isso é do outro)
        ("", ""),
        (None, ""),
    ],
)
def test_tirar_apagado_tira_so_a_palavra_inteira_do_fim(entrada, esperado):
    assert tirar_apagado(entrada) == esperado


def test_numero_da_maquina_e_apagado_juntos():
    assert tirar_apagado(nome_para_exibir("(15) CADEIRA ABDUTORA APAGADO")) == "CADEIRA ABDUTORA"
