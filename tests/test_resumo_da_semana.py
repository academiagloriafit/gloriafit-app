"""Resumo da semana na tela "Lançar treino" (26/10/2026): o servidor manda os grupos de cada exercício num atributo da página.

A conta em si é do navegador (app/static/resumo_semana.js, testada em tests_js/resumo_semana.test.js). Dados inventados.
"""

import json
import re

import pytest

from app import acesso, exercicios
from app.db import conectar, criar_tabelas
from app.web import criar_app


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "resumo.db"
    c = conectar(caminho)
    criar_tabelas(c)
    c.executemany("INSERT INTO grupo_muscular (id, nome, ordem) VALUES (?, ?, ?)", [(10, "Peito", 1), (20, "Tríceps", 2), (30, "Bíceps", 3)])
    c.execute("INSERT INTO exercicio (id, nome, origem, ativo) VALUES (1, 'SUPINO', 'app', 1), (2, 'ROSCA + TRICEPS', 'app', 1), (3, 'SEM GRUPO', 'app', 1), (4, 'DESATIVADO', 'app', 0)")
    c.executemany("INSERT INTO exercicio_grupo (exercicio_id, grupo_id) VALUES (?, ?)", [(1, 10), (2, 30), (2, 20), (4, 10)])
    c.execute("INSERT INTO aluno (id, nome) VALUES (1, 'ANA FICTICIA')")
    c.commit()
    c.close()
    return caminho


def test_grupos_compactos_usa_indices_na_ordem_do_quadro_e_inclui_desativados(caminho):
    c = conectar(caminho)
    try:
        assert exercicios.grupos_compactos(c) == {"nomes": ["Peito", "Tríceps", "Bíceps"], "ex": {"1": [0], "2": [1, 2], "4": [0]}}
    finally:
        c.close()


def test_banco_sem_grupos_manda_listas_vazias():
    c = conectar()
    criar_tabelas(c)
    c.execute("DELETE FROM grupo_muscular")
    assert exercicios.grupos_compactos(c) == {"nomes": [], "ex": {}}
    c.close()


def test_a_tela_de_montar_tem_o_resumo_fechado_e_os_grupos_no_atributo(caminho):
    app = criar_app(caminho)
    navegador = app.test_client()
    c = conectar(caminho)
    navegador.set_cookie(acesso.NOME_DO_COOKIE, acesso.autorizar(c, acesso.gerar_codigo(c, "Teste").codigo).token)
    c.close()

    html = navegador.get("/alunos/1/montar").get_data(as_text=True)

    bruto = re.search(r"data-grupos='([^']*)'", html).group(1)
    assert json.loads(bruto) == {"nomes": ["Peito", "Tríceps", "Bíceps"], "ex": {"1": [0], "2": [1, 2], "4": [0]}}
    assert '<details class="cartao resumo-semana" id="resumo-semana">' in html  # começa fechado
    assert "Resumo da semana por grupo muscular" in html
    for dias in range(2, 7):
        assert f'<option value="{dias}">{dias} dias</option>' in html
    assert 'id="aviso-rascunho"' in html  # o aviso de rascunho recuperado (escondido até haver um)
