"""Datas do app (app/datas.py): o banco guarda UTC, a academia vive no horário de Brasília."""

from datetime import datetime, timezone

import pytest

from app.datas import dia_local, formatar_dia, hoje, ler_dia, momento_para_texto


def test_dia_local_converte_de_utc_para_brasilia():
    assert dia_local("2026-10-07 02:30:00") == "2026-10-06"  # 23h30 do dia 6 em Brasília
    assert dia_local("2026-10-07 03:00:00") == "2026-10-07"  # meia-noite em Brasília
    assert dia_local("2026-10-07 14:00:00") == "2026-10-07"


def test_dia_local_respeita_o_horario_de_verao_de_antes_de_2019():
    assert dia_local("2017-12-15 02:30:00") == "2017-12-15"  # UTC-2: 00h30 do dia 15
    assert dia_local("2017-12-15 01:30:00") == "2017-12-14"  # UTC-2: 23h30 do dia 14
    assert dia_local("2020-12-15 02:30:00") == "2020-12-14"  # sem horário de verão (UTC-3): 23h30 do dia 14


@pytest.mark.parametrize("vazio", [None, ""])
def test_dia_local_de_vazio_e_vazio(vazio):
    assert dia_local(vazio) is None


def test_hoje_e_o_dia_de_brasilia():
    assert hoje(datetime(2026, 10, 9, 2, 59, 59, tzinfo=timezone.utc)) == "2026-10-08"
    assert hoje(datetime(2026, 10, 9, 3, 0, 0, tzinfo=timezone.utc)) == "2026-10-09"


def test_momento_para_texto_guarda_em_utc_qualquer_que_seja_o_fuso_de_entrada():
    from app.datas import FUSO_DA_ACADEMIA

    local = datetime(2026, 10, 8, 11, 30, 0, tzinfo=FUSO_DA_ACADEMIA)
    assert momento_para_texto(local) == "2026-10-08 14:30:00"


@pytest.mark.parametrize("texto", ["2026-10-08", "2028-02-29", "2020-01-01", "0001-01-01"])
def test_ler_dia_aceita_datas_que_existem(texto):
    assert ler_dia(texto) is not None
    assert ler_dia(texto).isoformat() == texto


@pytest.mark.parametrize(
    "texto",
    ["2027-02-29", "2026-02-30", "2026-13-01", "2026-00-10", "2026-10-00", "2026-1-5", "2026-10-8", "08/10/2026",
     "2026-10-081", "20261008", " 2026-10-08", "2026-10-08 ", "２０２６-10-08", "²⁰²⁶-10-08", "2026/10/08", "", None, 20261008, True],
)
def test_ler_dia_recusa_o_resto(texto):
    assert ler_dia(texto) is None


def test_formatar_dia():
    assert formatar_dia("2026-10-08") == "08/10/2026"
    assert formatar_dia(None) is None
    assert formatar_dia("lixo") is None
