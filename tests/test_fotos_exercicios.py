"""As fotos de "Como fazer": o mapa, os arquivos e o nome que o servidor entrega ao celular."""

import json
import re

import pytest

from app import fotos_exercicios
from app.fotos_exercicios import ARQUIVO_DO_MAPA, PASTA_DAS_FOTOS, foto_do_exercicio


def test_exercicio_do_mapa_devolve_o_nome_do_par():
    assert foto_do_exercicio("(15) CADEIRA ABDUTORA") == "Thigh_Abductor"


def test_o_nome_como_o_aluno_ve_sem_o_numero_da_maquina_tambem_acha_a_foto():
    # o treino do aluno traz "CADEIRA ABDUTORA" (sem o "(15)"): é com esse nome que a busca acontece de verdade
    assert foto_do_exercicio("CADEIRA ABDUTORA") == foto_do_exercicio("(15) CADEIRA ABDUTORA") == "Thigh_Abductor"
    assert foto_do_exercicio("VOADOR") == "Butterfly"


def test_dois_nomes_que_viram_o_mesmo_com_fotos_diferentes_nao_sobem(tmp_path, monkeypatch):
    ambiguo = tmp_path / "mapa.json"
    ambiguo.write_text(json.dumps({"(7) VOADOR": "A_1", "VOADOR": "B_1"}), encoding="utf-8")
    monkeypatch.setattr(fotos_exercicios, "ARQUIVO_DO_MAPA", ambiguo)
    fotos_exercicios._mapa.cache_clear()
    try:
        with pytest.raises(ValueError, match="outra foto"):
            foto_do_exercicio("VOADOR")
    finally:
        fotos_exercicios._mapa.cache_clear()


def test_nome_sem_diferenca_de_maiuscula_e_com_espacos_nas_pontas():
    assert foto_do_exercicio("  mesa FLEXORA ") == foto_do_exercicio("Mesa flexora") is not None


@pytest.mark.parametrize("nome", ["EXERCICIO QUE NAO EXISTE", "", None, 42, ["SUPINO RETO"]])
def test_o_que_nao_esta_no_mapa_ou_nao_e_texto_fica_sem_foto(nome):
    assert foto_do_exercicio(nome) is None


def test_todo_par_do_mapa_tem_os_dois_arquivos():
    mapa = json.loads(ARQUIVO_DO_MAPA.read_text(encoding="utf-8"))
    assert mapa, "mapa vazio"
    for nome, foto in mapa.items():
        for k in (0, 1):
            arquivo = PASTA_DAS_FOTOS / f"{foto}_{k}.jpg"
            assert arquivo.is_file() and arquivo.stat().st_size > 5_000, f"{nome}: falta {arquivo.name}"


def test_nomes_do_mapa_so_tem_letras_numeros_sublinhado_e_hifen():
    # o nome vira parte de um endereço no celular: nada de barra, ponto ou aspas
    for foto in json.loads(ARQUIVO_DO_MAPA.read_text(encoding="utf-8")).values():
        assert re.fullmatch(r"[A-Za-z0-9_-]{1,80}", foto), foto


def test_nome_perigoso_no_mapa_nao_sai(tmp_path, monkeypatch):
    perigoso = tmp_path / "mapa.json"
    perigoso.write_text(json.dumps({"A": "../segredo", "B": 'x" onerror="y', "C": "ok_1"}), encoding="utf-8")
    monkeypatch.setattr(fotos_exercicios, "ARQUIVO_DO_MAPA", perigoso)
    fotos_exercicios._mapa.cache_clear()
    try:
        assert foto_do_exercicio("A") is None
        assert foto_do_exercicio("B") is None
        assert foto_do_exercicio("C") == "ok_1"
    finally:
        fotos_exercicios._mapa.cache_clear()


def test_todo_exercicio_do_mapa_existe_na_base_do_app():
    """O nome do mapa é o do quadro de exercícios: se um nome estiver errado, a foto nunca aparece."""
    openpyxl = pytest.importorskip("openpyxl")
    from app.fotos_exercicios import ARQUIVO_DO_MAPA as mapa_arquivo

    quadro = mapa_arquivo.parent.parent / "dados" / "quadro_exercicios_v2.xlsx"
    if not quadro.exists():
        pytest.skip("quadro de exercícios não está aqui")
    linhas = openpyxl.load_workbook(quadro, read_only=True)["Quadro"].iter_rows(values_only=True)
    nomes = {str(r[0]).casefold() for r in linhas if r[0]}
    faltando = [n for n in json.loads(mapa_arquivo.read_text(encoding="utf-8")) if n.casefold() not in nomes]
    assert not faltando, faltando
