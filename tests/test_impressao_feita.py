"""Imprimir UMA ficha na recepção conta como "treino feito hoje" (pedido do Thiago em 20/10/2026).

Quem não usa o app pede um papel novo do treino do dia a cada vez que vai treinar. Mesma regra do botão do aluno:
no máximo uma vez por ficha por dia (dia de Brasília), só no treino ativo. Imprimir "todas as fichas" não conta.
Dados inventados.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app import acesso, aluno_treino, ciclo
from app.ciclo import CicloInvalido, TreinoNaoEncontrado
from app.db import conectar, criar_tabelas
from app.treinos import salvar_treino
from app.web import criar_app

# 14h30 UTC = 11h30 em Brasília, 08/10/2026
AGORA = datetime(2026, 10, 8, 14, 30, 0, tzinfo=timezone.utc)


def _preparar(conn):
    conn.execute("INSERT INTO aluno (id, nome) VALUES (1, 'ANA FICTICIA')")
    conn.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO RETO', 'app')")
    conn.commit()
    itens = [{"exercicio_id": 1, "series": "3", "repeticoes": "12"}]
    pedido = {"nome_treino": "TREINO ABC", "montado_por": "Ana", "fichas": [{"nome": n, "itens": itens} for n in ("A", "B")]}
    return salvar_treino(conn, 1, pedido, agora=AGORA)


@pytest.fixture
def conn():
    c = conectar()
    criar_tabelas(c)
    yield c
    c.close()


def _sessoes(conn):
    return [tuple(l) for l in conn.execute("SELECT treino_id, ficha_ordem, feita_em FROM sessao ORDER BY id")]


# ------------------------------------------------------------------ a regra (app/ciclo.py)


def test_imprimir_a_ficha_conta_um_treino_feito(conn):
    treino = _preparar(conn)

    assert ciclo.marcar_impressao(conn, treino, 1, AGORA) == {"ficha": 1, "ja_marcada": False, "feitas": 1}
    assert _sessoes(conn) == [(treino, 1, "2026-10-08 14:30:00")]


def test_imprimir_de_novo_no_mesmo_dia_nao_conta_outra_vez(conn):
    treino = _preparar(conn)
    ciclo.marcar_impressao(conn, treino, 1, AGORA)

    de_novo = ciclo.marcar_impressao(conn, treino, 1, AGORA + timedelta(hours=3))

    assert de_novo == {"ficha": 1, "ja_marcada": True, "feitas": 1}
    assert len(_sessoes(conn)) == 1  # papel perdido, segunda via, clique duplo: continua 1


def test_no_dia_seguinte_conta_de_novo(conn):
    treino = _preparar(conn)
    ciclo.marcar_impressao(conn, treino, 1, AGORA)

    amanha = ciclo.marcar_impressao(conn, treino, 1, AGORA + timedelta(days=1))

    assert amanha == {"ficha": 1, "ja_marcada": False, "feitas": 2}


def test_o_dia_e_o_de_brasilia_e_nao_o_de_londres(conn):
    treino = _preparar(conn)
    # 02h30 UTC de 09/10 = 23h30 de 08/10 em Brasília; 03h30 UTC = 00h30 de 09/10 em Brasília (outro dia da academia)
    ciclo.marcar_impressao(conn, treino, 1, datetime(2026, 10, 9, 2, 30, tzinfo=timezone.utc))
    meia_noite_passou = ciclo.marcar_impressao(conn, treino, 1, datetime(2026, 10, 9, 3, 30, tzinfo=timezone.utc))
    assert meia_noite_passou["ja_marcada"] is False
    # 20h UTC e 14h30 UTC do mesmo dia de Brasília contam uma vez só
    ciclo.marcar_impressao(conn, treino, 2, datetime(2026, 10, 8, 14, 30, tzinfo=timezone.utc))
    assert ciclo.marcar_impressao(conn, treino, 2, datetime(2026, 10, 8, 20, 0, tzinfo=timezone.utc))["ja_marcada"] is True


def test_cada_ficha_conta_separada(conn):
    treino = _preparar(conn)

    ciclo.marcar_impressao(conn, treino, 1, AGORA)
    b = ciclo.marcar_impressao(conn, treino, 2, AGORA)

    assert b == {"ficha": 2, "ja_marcada": False, "feitas": 1}


def test_treino_concluido_nao_conta_e_nada_e_gravado(conn):
    treino = _preparar(conn)
    ciclo.concluir_treino(conn, treino, AGORA)

    with pytest.raises(CicloInvalido, match="concluído"):
        ciclo.marcar_impressao(conn, treino, 1, AGORA)

    assert _sessoes(conn) == []


def test_ficha_que_nao_existe_e_treino_que_nao_existe(conn):
    treino = _preparar(conn)

    with pytest.raises(CicloInvalido, match="não tem essa ficha"):
        ciclo.marcar_impressao(conn, treino, 9, AGORA)
    with pytest.raises(TreinoNaoEncontrado):
        ciclo.marcar_impressao(conn, 999, 1, AGORA)

    assert _sessoes(conn) == []


def test_aluno_que_marcou_no_app_e_depois_imprime_nao_conta_duas_vezes(conn):
    treino = _preparar(conn)
    aluno_treino.marcar_ficha_feita(conn, 1, 1, AGORA)  # marcou no celular

    assert ciclo.marcar_impressao(conn, treino, 1, AGORA + timedelta(hours=1)) == {"ficha": 1, "ja_marcada": True, "feitas": 1}


def test_a_impressao_entra_na_contagem_do_ciclo(conn):
    treino = _preparar(conn)
    ciclo.marcar_impressao(conn, treino, 1, AGORA)
    ciclo.marcar_impressao(conn, treino, 1, AGORA + timedelta(days=1))
    ciclo.marcar_impressao(conn, treino, 2, AGORA)

    assert ciclo.sessoes_feitas_do_aluno(conn, 1) == {treino: {1: 2, 2: 1}}


def test_desfazer_apaga_so_a_de_hoje(conn):
    treino = _preparar(conn)
    ciclo.marcar_impressao(conn, treino, 1, AGORA - timedelta(days=2))  # ontem e antes: fica
    ciclo.marcar_impressao(conn, treino, 1, AGORA)

    assert ciclo.desfazer_impressao(conn, treino, 1, AGORA) == {"ficha": 1, "feitas": 1}
    assert _sessoes(conn) == [(treino, 1, "2026-10-06 14:30:00")]
    # imprimir de novo depois de desfazer volta a contar
    assert ciclo.marcar_impressao(conn, treino, 1, AGORA)["ja_marcada"] is False


def test_desfazer_sem_nada_hoje_nao_muda_nada(conn):
    treino = _preparar(conn)

    assert ciclo.desfazer_impressao(conn, treino, 1, AGORA) == {"ficha": 1, "feitas": 0}


def test_desfazer_em_treino_concluido_e_recusado(conn):
    treino = _preparar(conn)
    ciclo.marcar_impressao(conn, treino, 1, AGORA)
    ciclo.concluir_treino(conn, treino, AGORA)

    with pytest.raises(CicloInvalido):
        ciclo.desfazer_impressao(conn, treino, 1, AGORA)
    assert len(_sessoes(conn)) == 1  # o histórico do treino concluído não é mexido


# ------------------------------------------------------------------ pela web


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "impressao.db"
    c = conectar(caminho)
    criar_tabelas(c)
    _preparar(c)
    c.close()
    return caminho


@pytest.fixture
def cliente(caminho):
    navegador = criar_app(caminho).test_client()
    c = conectar(caminho)
    token = acesso.autorizar(c, acesso.gerar_codigo(c, "Computador de teste").codigo).token
    c.close()
    navegador.set_cookie(acesso.NOME_DO_COOKIE, token)
    return navegador


def _quantas_sessoes(caminho):
    c = conectar(caminho)
    n = c.execute("SELECT COUNT(*) FROM sessao").fetchone()[0]
    c.close()
    return n


URL = "/api/treinos/1/impressao"


def test_registrar_pela_web_e_repetir_no_mesmo_dia(cliente, caminho):
    primeira = cliente.post(URL, json={"ficha": 1})
    segunda = cliente.post(URL, json={"ficha": 1})

    assert primeira.status_code == 200
    assert primeira.get_json() == {"ok": True, "ficha": 1, "ja_marcada": False, "feitas": 1}
    assert segunda.get_json()["ja_marcada"] is True
    assert _quantas_sessoes(caminho) == 1


def test_desfazer_pela_web(cliente, caminho):
    cliente.post(URL, json={"ficha": 2})

    resposta = cliente.post(URL + "/desfazer", json={"ficha": 2})

    assert resposta.status_code == 200 and resposta.get_json() == {"ok": True, "ficha": 2, "feitas": 0}
    assert _quantas_sessoes(caminho) == 0


def test_computador_nao_autorizado_nao_registra(caminho):
    resposta = criar_app(caminho).test_client().post(URL, json={"ficha": 1})

    assert resposta.status_code == 401
    assert _quantas_sessoes(caminho) == 0


def test_pedido_de_outro_site_e_recusado(cliente, caminho):
    resposta = cliente.post(URL, json={"ficha": 1}, headers={"Origin": "https://outro-site.example"})

    assert resposta.status_code == 403
    assert _quantas_sessoes(caminho) == 0


def test_pedido_que_nao_e_json_e_recusado(cliente, caminho):
    assert cliente.post(URL, data="ficha=1").status_code == 415
    assert _quantas_sessoes(caminho) == 0


@pytest.mark.parametrize("ficha", ["1", 0, -1, True, 1.5, None, 10000, "abc", [1], {"a": 1}])
def test_ficha_invalida_e_400_e_nao_grava(cliente, caminho, ficha):
    assert cliente.post(URL, json={"ficha": ficha}).status_code == 400
    assert cliente.post(URL + "/desfazer", json={"ficha": ficha}).status_code == 400
    assert _quantas_sessoes(caminho) == 0


def test_corpo_que_nao_e_objeto_e_400(cliente):
    assert cliente.post(URL, json=[1]).status_code == 400


def test_treino_que_nao_existe_e_404_e_ficha_que_nao_existe_e_409(cliente):
    assert cliente.post("/api/treinos/999/impressao", json={"ficha": 1}).status_code == 404
    assert cliente.post(URL, json={"ficha": 9}).status_code == 409


def test_treino_concluido_e_409_com_mensagem(cliente, caminho):
    c = conectar(caminho)
    ciclo.concluir_treino(c, 1)
    c.close()

    resposta = cliente.post(URL, json={"ficha": 1})

    assert resposta.status_code == 409 and "concluído" in resposta.get_json()["erro"]
    assert _quantas_sessoes(caminho) == 0


def test_so_abrir_a_tela_de_imprimir_nao_registra_nada(cliente, caminho):
    # Abrir (ou trocar de A para B) é só olhar: quem conta é o clique em Imprimir, nunca um GET.
    cliente.get("/treinos/1/imprimir")
    cliente.get("/treinos/1/imprimir?ficha=2")
    cliente.get("/treinos/1/imprimir?ficha=todas")

    assert _quantas_sessoes(caminho) == 0


def test_tela_de_uma_ficha_avisa_o_navegador_e_a_de_todas_nao(cliente):
    uma = cliente.get("/treinos/1/imprimir?ficha=2").get_data(as_text=True)
    todas = cliente.get("/treinos/1/imprimir?ficha=todas").get_data(as_text=True)

    assert 'data-treino="1"' in uma and 'data-ficha="2"' in uma and 'data-nome="B"' in uma
    assert 'id="aviso-registro"' in uma and 'id="botao-desfazer"' in uma
    assert "data-ficha" not in todas and 'id="aviso-registro"' not in todas  # todas as fichas não conta
