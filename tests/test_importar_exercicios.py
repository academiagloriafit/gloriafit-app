"""Testes do importador do quadro de exercícios."""

from pathlib import Path

import openpyxl
import pytest

from app.db import conectar, criar_tabelas
from app.importar_exercicios import COLUNAS, ErroDeImportacao, importar_quadro

QUADRO_REAL = Path(__file__).resolve().parent.parent / "dados" / "quadro_exercicios_v2.xlsx"
CABECALHO = list(COLUNAS.values())


def _planilha(tmp_path, linhas, cabecalho=None, aba="Quadro"):
    """Cria uma planilha pequena igual à real, só com as colunas que o importador lê."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = aba
    ws.append(cabecalho or CABECALHO)
    for linha in linhas:
        ws.append(linha)
    caminho = tmp_path / "quadro.xlsx"
    wb.save(caminho)
    return caminho


def _linha(nome, grupo, confianca="Alta", usos=10, ids="1", origem="criado na academia", final=None):
    # ordem das colunas = ordem de COLUNAS: nome, sugerido, final, confiança, usos, ids, origem
    return [nome, grupo, final, confianca, usos, ids, origem]


@pytest.fixture
def conn():
    c = conectar()
    criar_tabelas(c)
    yield c
    c.close()


def _grupos_de(conn, nome):
    return [r["nome"] for r in conn.execute(
        "SELECT g.nome FROM exercicio_grupo eg JOIN grupo_muscular g ON g.id = eg.grupo_id "
        "JOIN exercicio e ON e.id = eg.exercicio_id WHERE e.nome = ? ORDER BY g.ordem", (nome,))]


def test_importa_exercicio_simples(conn, tmp_path):
    resumo = importar_quadro(conn, _planilha(tmp_path, [_linha("SUPINO RETO", "Peito", usos=300, ids="42")]))
    ex = conn.execute("SELECT * FROM exercicio WHERE nome = 'SUPINO RETO'").fetchone()
    assert (ex["usos_ultimo_ano"], ex["combinado"], ex["origem"], ex["confianca_grupo"]) == (300, 0, "data4u_academia", "Alta")
    assert _grupos_de(conn, "SUPINO RETO") == ["Peito"]
    assert resumo == {"exercicios": 1, "combinados": 0, "sem_grupo": 0, "ids_data4u": 1}


def test_cria_os_15_grupos_mesmo_sem_uso(conn, tmp_path):
    importar_quadro(conn, _planilha(tmp_path, [_linha("SUPINO RETO", "Peito")]))
    assert conn.execute("SELECT COUNT(*) FROM grupo_muscular").fetchone()[0] == 15


def test_combinado_recebe_os_dois_grupos_e_a_marca(conn, tmp_path):
    linha = _linha("ROSCA POLIA + TRÍCEPS POLIA", "Bíceps + Tríceps", confianca="Revisar (combinado)")
    resumo = importar_quadro(conn, _planilha(tmp_path, [linha]))
    assert _grupos_de(conn, "ROSCA POLIA + TRÍCEPS POLIA") == ["Bíceps", "Tríceps"]
    assert conn.execute("SELECT combinado FROM exercicio").fetchone()[0] == 1
    assert resumo["combinados"] == 1


def test_grupo_com_barra_no_nome_nao_e_separado(conn, tmp_path):
    importar_quadro(conn, _planilha(tmp_path, [_linha("CADEIRA ABDUTORA", "Quadril (adutores/abdutores)")]))
    assert _grupos_de(conn, "CADEIRA ABDUTORA") == ["Quadril (adutores/abdutores)"]


def test_exercicio_sem_grupo_fica_sem_grupo(conn, tmp_path):
    resumo = importar_quadro(conn, _planilha(tmp_path, [_linha("MARCHA NO LUGAR", None, confianca="Sem sugestão")]))
    assert _grupos_de(conn, "MARCHA NO LUGAR") == []
    assert resumo["sem_grupo"] == 1


def test_grupo_final_corrigido_a_mao_vale_mais_que_o_sugerido(conn, tmp_path):
    importar_quadro(conn, _planilha(tmp_path, [_linha("VOADOR", "Peito", final="Ombros")]))
    assert _grupos_de(conn, "VOADOR") == ["Ombros"]


def test_guarda_todos_os_ids_do_data4u(conn, tmp_path):
    importar_quadro(conn, _planilha(tmp_path, [_linha("MOBILIDADE DE QUADRIL", "Mobilidade", ids="128, 660, -122")]))
    ids = [r["data4u_id"] for r in conn.execute("SELECT data4u_id FROM exercicio_data4u ORDER BY data4u_id")]
    assert ids == [-122, 128, 660]  # ids negativos existem no catálogo do Data4U


def test_converte_a_origem(conn, tmp_path):
    linhas = [_linha("A", "Peito", ids="1", origem="criado na academia"),
              _linha("B", "Peito", ids="2", origem="catalogo Data4U (com animacao)")]
    importar_quadro(conn, _planilha(tmp_path, linhas))
    origens = {r["nome"]: r["origem"] for r in conn.execute("SELECT nome, origem FROM exercicio")}
    assert origens == {"A": "data4u_academia", "B": "data4u_catalogo"}


def test_rodar_duas_vezes_nao_duplica_e_atualiza(conn, tmp_path):
    importar_quadro(conn, _planilha(tmp_path, [_linha("SUPINO RETO", "Peito", usos=10, ids="42")]))
    importar_quadro(conn, _planilha(tmp_path, [_linha("SUPINO RETO", "Ombros", usos=99, ids="42, 43")]))
    assert conn.execute("SELECT COUNT(*) FROM exercicio").fetchone()[0] == 1
    assert conn.execute("SELECT usos_ultimo_ano FROM exercicio").fetchone()[0] == 99
    assert _grupos_de(conn, "SUPINO RETO") == ["Ombros"]
    assert conn.execute("SELECT COUNT(*) FROM exercicio_data4u").fetchone()[0] == 2


def test_nao_mexe_em_exercicio_criado_no_app(conn, tmp_path):
    conn.execute("INSERT INTO exercicio (nome, origem) VALUES ('EXERCICIO NOVO DO PROFESSOR', 'app')")
    importar_quadro(conn, _planilha(tmp_path, [_linha("SUPINO RETO", "Peito")]))
    assert conn.execute("SELECT origem FROM exercicio WHERE nome = 'EXERCICIO NOVO DO PROFESSOR'").fetchone()[0] == "app"


@pytest.mark.parametrize("linhas, trecho", [
    ([_linha("A", "Peito", ids="1"), _linha("a", "Peito", ids="2")], "nome repetido"),
    ([_linha("A", "Peito", ids="1"), _linha("B", "Peito", ids="1")], "já está em"),
    ([_linha("A", "Peitoral")], "grupo desconhecido"),
    ([_linha("A", "Peito", ids="abc")], "id do Data4U inválido"),
    ([_linha("A", "Peito", ids=None)], "sem id do Data4U"),
    ([_linha("A", "Peito", origem="internet")], "origem desconhecida"),
    ([_linha(None, "Peito")], "sem nome"),
])
def test_recusa_planilha_com_problema_e_nao_grava_nada(conn, tmp_path, linhas, trecho):
    with pytest.raises(ErroDeImportacao, match=trecho):
        importar_quadro(conn, _planilha(tmp_path, linhas))
    assert conn.execute("SELECT COUNT(*) FROM exercicio").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM exercicio_data4u").fetchone()[0] == 0


def test_recusa_planilha_sem_a_aba_quadro(conn, tmp_path):
    with pytest.raises(ErroDeImportacao, match="aba 'Quadro'"):
        importar_quadro(conn, _planilha(tmp_path, [], aba="Outra"))


def test_recusa_planilha_sem_coluna_obrigatoria(conn, tmp_path):
    cabecalho = [c for c in CABECALHO if c != "IDs Data4U (todos)"]
    with pytest.raises(ErroDeImportacao, match="IDs Data4U"):
        importar_quadro(conn, _planilha(tmp_path, [], cabecalho=cabecalho))


@pytest.mark.skipif(not QUADRO_REAL.exists(), reason="planilha real não está em dados/")
def test_quadro_real_importa_com_as_contagens_conhecidas(conn):
    resumo = importar_quadro(conn, QUADRO_REAL)
    assert resumo == {"exercicios": 1161, "combinados": 107, "sem_grupo": 11, "ids_data4u": 1431}
    assert conn.execute("SELECT COUNT(*) FROM grupo_muscular").fetchone()[0] == 15
    assert conn.execute("SELECT COUNT(*) FROM exercicio WHERE origem = 'data4u_catalogo'").fetchone()[0] == 64
    # Conferência de um caso conhecido: a elevação conjugada foi confirmada como Ombros.
    assert _grupos_de(conn, "ELEVAÇÃO CONJUGADA") == ["Ombros"]
    # Hack Machine e Hack Squat são aparelhos diferentes e nunca podem ser juntados.
    nomes = [r["nome"] for r in conn.execute("SELECT nome FROM exercicio WHERE nome LIKE '%HACK%'")]
    assert any("HACK MACHINE" in n for n in nomes) and any("HACK SQUAT" in n for n in nomes)
