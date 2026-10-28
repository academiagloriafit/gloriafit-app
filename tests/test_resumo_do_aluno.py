"""Resumo no topo da ficha do aluno (28/10/2026): treino atual, último treino, último esforço e comentários. Dados inventados."""

import re
from datetime import datetime, timezone

import pytest

from app import acesso, ciclo
from app.db import conectar, criar_tabelas
from app.web import criar_app


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "resumo.db"
    c = conectar(caminho)
    criar_tabelas(c)
    c.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO RETO', 'app')")
    c.execute("INSERT INTO aluno (id, nome, situacao) VALUES (1, 'ANA COMPLETA', 'A'), (2, 'BIA NOVATA', 'A')")
    c.execute(
        "INSERT INTO treino (id, aluno_id, nome, montado_por, ativo, inicio, fim, sessoes_por_ficha)"
        " VALUES (1, 1, 'TREINO <ABC>', 'PROF', 1, '2026-10-01', '2026-10-20', 10)"  # venceu: hora de trocar
    )
    f = c.execute("INSERT INTO ficha (treino_id, nome, ordem) VALUES (1, 'A - PEITO', 1)").lastrowid
    c.execute("INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, series, repeticoes) VALUES (?, 1, 1, '3', '12')", (f,))
    c.execute("INSERT INTO sessao (treino_id, ficha_ordem, feita_em, esforco) VALUES (1, 1, '2026-10-20 12:00:00', 2)")
    c.execute("INSERT INTO sessao (treino_id, ficha_ordem, feita_em, esforco) VALUES (1, 1, '2026-10-25 12:00:00', 3)")
    c.execute("INSERT INTO comentario (aluno_id, treino_id, treino_nome, texto, criado_em) VALUES (1, 1, 'TREINO', 'Doeu o ombro', '2026-10-25 13:00:00')")
    c.commit()
    c.close()
    return caminho


def test_dias_desde_o_ultimo_treino_conta_em_brasilia(caminho):
    c = conectar(caminho)
    try:
        assert ciclo.dias_desde_o_ultimo_treino(c, 1, datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc)) == 3
        assert ciclo.dias_desde_o_ultimo_treino(c, 1, datetime(2026, 10, 25, 20, 0, tzinfo=timezone.utc)) == 0
        # 26/10 às 01h em UTC ainda é 25/10 em Brasília: "ontem" não, "hoje"
        assert ciclo.dias_desde_o_ultimo_treino(c, 1, datetime(2026, 10, 26, 1, 0, tzinfo=timezone.utc)) == 0
        assert ciclo.dias_desde_o_ultimo_treino(c, 2) is None
    finally:
        c.close()


def _pagina(caminho, aluno):
    app = criar_app(caminho)
    navegador = app.test_client()
    c = conectar(caminho)
    navegador.set_cookie(acesso.NOME_DO_COOKIE, acesso.autorizar(c, acesso.gerar_codigo(c, "Teste").codigo).token)
    c.close()
    html = navegador.get(f"/alunos/{aluno}").get_data(as_text=True)
    return re.search(r'<section class="resumo-aluno".*?</section>', html, re.S).group(0)


def test_resumo_do_aluno_com_tudo(caminho):
    resumo = _pagina(caminho, 1)

    assert "TREINO &lt;ABC&gt;" in resumo and "<ABC>" not in resumo  # nome escapado
    assert "Hora de trocar" in resumo
    assert "Há " in resumo and "A - PEITO · 25/10/2026" in resumo
    assert "Pesado" in resumo
    assert "1 sem ler" in resumo and 'href="#comentarios-do-aluno"' in resumo
    # trocar, esforço pesado e comentário; o "último treino" só fica laranja com 7 dias ou mais (depende do dia em que o teste roda)
    assert resumo.count("resumo-alerta") in (3, 4)


def test_resumo_do_aluno_sem_nada(caminho):
    resumo = _pagina(caminho, 2)

    assert "Nenhum ativo" in resumo and 'href="/alunos/2/montar"' in resumo
    assert "Nenhum registrado" in resumo and "Sem nota" in resumo
    assert "Nenhum sem ler" in resumo and "O aluno ainda não comentou" in resumo
    assert "resumo-alerta" not in resumo
