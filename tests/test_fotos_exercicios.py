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


def test_exercicio_apagado_no_data4u_acha_a_foto_do_exercicio_de_mesmo_nome():
    # o Data4U deixa "CADEIRA EXTENSORA APAGADO" nos treinos antigos; a foto é a da "CADEIRA EXTENSORA"
    assert foto_do_exercicio("CADEIRA EXTENSORA APAGADO") == foto_do_exercicio("CADEIRA EXTENSORA") is not None
    assert foto_do_exercicio("(15) cadeira abdutora Apagado") == "Thigh_Abductor"


def test_apagado_sem_exercicio_de_mesmo_nome_no_mapa_continua_sem_foto():
    assert foto_do_exercicio("EXERCICIO QUE NAO EXISTE APAGADO") is None


def test_fotos_por_id_e_a_api_da_lista_trazem_a_foto(tmp_path):
    """Lançar treino, visual novo (11/11/2026): a foto pequena de cada exercício vem do mapa por id e da /api/exercicios."""
    from app import acesso
    from app.db import conectar, criar_tabelas
    from app.web import criar_app

    caminho = tmp_path / "f.db"
    c = conectar(caminho)
    criar_tabelas(c)
    c.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, '(7) VOADOR', 'app'), (2, 'CORRIDA NA ESTEIRA', 'app')")
    c.execute("INSERT INTO aluno (id, nome, cpf, situacao, data4u_id) VALUES (1, 'ANA', '00000000001', 'A', 1)")
    c.commit()
    assert fotos_exercicios.fotos_por_id(c) == {"1": "ilustracoes/Butterfly.jpg"}  # sem imagem: fica de fora
    token = acesso.autorizar(c, acesso.gerar_codigo(c, "Teste").codigo).token
    c.close()
    navegador = criar_app(caminho).test_client()
    navegador.set_cookie(acesso.NOME_DO_COOKIE, token)
    lista = {e["nome"]: e["miniatura"] for e in navegador.get("/api/exercicios").get_json()["exercicios"]}
    assert lista == {"VOADOR": "ilustracoes/Butterfly.jpg", "CORRIDA NA ESTEIRA": None}
    html = navegador.get("/alunos/1/montar").get_data(as_text=True)
    assert "data-fotos='{\"1\": \"ilustracoes/Butterfly.jpg\"}'" in html and 'data-pasta-fotos="/static/"' in html
    assert "montador-novo" in html


def test_todo_par_de_fotos_tem_ilustracao_e_ela_e_preferida(monkeypatch, tmp_path):
    """As 51 ilustrações do Canva (11/11/2026): uma para cada par do mapa; sem ilustração, volta para a foto."""
    pares = set(json.loads(ARQUIVO_DO_MAPA.read_text(encoding="utf-8")).values())
    for par in pares:
        assert (fotos_exercicios.PASTA_DAS_ILUSTRACOES / f"{par}.jpg").is_file(), par
    assert fotos_exercicios.miniatura_do_exercicio("VOADOR") == "ilustracoes/Butterfly.jpg"
    assert fotos_exercicios.miniatura_do_exercicio("CORRIDA NA ESTEIRA") is None
    monkeypatch.setattr(fotos_exercicios, "PASTA_DAS_ILUSTRACOES", tmp_path)  # pasta vazia: sem ilustração
    assert fotos_exercicios.miniatura_do_exercicio("VOADOR") == "exercicios/Butterfly_0.jpg"


def test_a_tela_de_exercicios_passa_a_pasta_das_ilustracoes(tmp_path):
    """Lista de exercícios (consulta), visual novo (12/11/2026): a página entrega a pasta das imagens para o script."""
    from app import acesso
    from app.db import conectar, criar_tabelas
    from app.web import criar_app

    caminho = tmp_path / "e.db"
    c = conectar(caminho)
    criar_tabelas(c)
    token = acesso.autorizar(c, acesso.gerar_codigo(c, "Teste").codigo).token
    c.close()
    navegador = criar_app(caminho).test_client()
    navegador.set_cookie(acesso.NOME_DO_COOKIE, token)
    html = navegador.get("/exercicios").get_data(as_text=True)
    assert 'class="pagina pagina-larga exercicios-nova" data-pasta-fotos="/static/"' in html and "data-biblioteca" in html
