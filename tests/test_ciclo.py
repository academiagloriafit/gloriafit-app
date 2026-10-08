"""O ciclo do treino (app/ciclo.py): Concluído, reativar, sessões feitas e o aviso de trocar o treino."""

import sqlite3
from datetime import datetime, timezone

import pytest

from app import ciclo
from app.alunos import obter_ficha
from app.ciclo import CicloInvalido, TreinoNaoEncontrado, avaliar_ciclo, texto_do_aviso_de_troca
from app.db import conectar, criar_tabelas
from app.treinos import salvar_treino

AGORA = datetime(2026, 10, 8, 14, 30, 0, tzinfo=timezone.utc)


@pytest.fixture
def conn():
    c = conectar()
    criar_tabelas(c)
    c.execute("INSERT INTO aluno (id, nome) VALUES (1, 'ANA FICTICIA'), (2, 'BRUNO FICTICIO')")
    c.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO RETO', 'app')")
    c.commit()
    yield c
    c.close()


def _treino(conn, aluno_id=1, nome="TREINO ABC", fichas=("A", "B", "C"), **extras):
    itens = [{"exercicio_id": 1, "series": "3", "repeticoes": "12"}]
    pedido = {"nome_treino": nome, "montado_por": "Ana", "fichas": [{"nome": f, "itens": itens} for f in fichas], **extras}
    return salvar_treino(conn, aluno_id, pedido, agora=AGORA)


def _estado(conn, treino_id):
    return tuple(conn.execute("SELECT ativo, concluido_em FROM treino WHERE id = ?", (treino_id,)).fetchone())


# ------------------------------------------------------------------ concluir


def test_concluir_deixa_o_treino_inativo_e_guarda_o_momento(conn):
    treino = _treino(conn)

    ciclo.concluir_treino(conn, treino, agora=AGORA)

    assert _estado(conn, treino) == (0, "2026-10-08 14:30:00")


def test_concluir_treino_ja_inativo_e_recusado_e_nao_muda_o_momento(conn):
    treino = _treino(conn)
    ciclo.concluir_treino(conn, treino, agora=AGORA)

    with pytest.raises(CicloInvalido, match="já está concluído"):
        ciclo.concluir_treino(conn, treino, agora=datetime(2026, 11, 1, tzinfo=timezone.utc))

    assert _estado(conn, treino) == (0, "2026-10-08 14:30:00")


def test_concluir_treino_que_nao_existe(conn):
    with pytest.raises(TreinoNaoEncontrado):
        ciclo.concluir_treino(conn, 999)


def test_concluir_nao_apaga_nada_do_treino(conn):
    treino = _treino(conn)

    ciclo.concluir_treino(conn, treino)

    assert conn.execute("SELECT COUNT(*) FROM ficha WHERE treino_id = ?", (treino,)).fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM ficha_item").fetchone()[0] == 3


def test_concluir_o_treino_de_um_aluno_nao_mexe_no_de_outro(conn):
    da_ana = _treino(conn, 1)
    do_bruno = _treino(conn, 2)

    ciclo.concluir_treino(conn, da_ana)

    assert _estado(conn, do_bruno) == (1, None)


# ------------------------------------------------------------------ reativar


def test_reativar_volta_a_ser_o_ativo_e_apaga_o_concluido_em(conn):
    treino = _treino(conn)
    ciclo.concluir_treino(conn, treino, agora=AGORA)

    ciclo.reativar_treino(conn, treino)

    assert _estado(conn, treino) == (1, None)


def test_reativar_treino_ja_ativo_e_recusado(conn):
    treino = _treino(conn)

    with pytest.raises(CicloInvalido, match="já está ativo"):
        ciclo.reativar_treino(conn, treino)


def test_reativar_com_outro_ativo_e_recusado_e_diz_qual(conn):
    antigo = _treino(conn, nome="ANTIGO")
    _treino(conn, nome="ATUAL")  # conclui o ANTIGO e vira o ativo

    with pytest.raises(CicloInvalido) as erro:
        ciclo.reativar_treino(conn, antigo)

    assert '"ATUAL"' in erro.value.mensagem
    assert _estado(conn, antigo)[0] == 0


def test_reativar_depois_de_concluir_o_atual(conn):
    antigo = _treino(conn, nome="ANTIGO")
    atual = _treino(conn, nome="ATUAL")
    ciclo.concluir_treino(conn, atual)

    ciclo.reativar_treino(conn, antigo)

    assert _estado(conn, antigo) == (1, None)
    assert _estado(conn, atual)[0] == 0


def test_reativar_treino_que_nao_existe(conn):
    with pytest.raises(TreinoNaoEncontrado):
        ciclo.reativar_treino(conn, 999)


def test_reativar_corrida_vira_recusa_e_nao_erro_500(conn, monkeypatch):
    antigo = _treino(conn, nome="ANTIGO")
    _treino(conn, nome="ATUAL")
    # a conferência prévia "não vê" o ativo (outro computador acabou de ativar): o índice do banco barra
    monkeypatch.setattr(ciclo, "treino_ativo", lambda *_a, **_k: None)

    with pytest.raises(CicloInvalido, match="Atualize a página"):
        ciclo.reativar_treino(conn, antigo)

    assert _estado(conn, antigo)[0] == 0


# ------------------------------------------------------------------ sessões


def test_registrar_sessao_conta_por_ficha(conn):
    treino = _treino(conn)

    ciclo.registrar_sessao(conn, treino, 1, agora=AGORA)
    ciclo.registrar_sessao(conn, treino, 1, agora=AGORA)
    ciclo.registrar_sessao(conn, treino, 3, agora=AGORA)

    assert ciclo.sessoes_feitas_do_aluno(conn, 1) == {treino: {1: 2, 3: 1}}
    assert conn.execute("SELECT feita_em FROM sessao LIMIT 1").fetchone()[0] == "2026-10-08 14:30:00"


def test_registrar_sessao_em_ficha_que_nao_existe_ou_treino_inativo_e_recusado(conn):
    treino = _treino(conn)  # fichas A, B, C

    with pytest.raises(CicloInvalido, match="não tem essa ficha"):
        ciclo.registrar_sessao(conn, treino, 4)
    with pytest.raises(CicloInvalido, match="não tem essa ficha"):
        ciclo.registrar_sessao(conn, treino, 0)
    ciclo.concluir_treino(conn, treino)
    with pytest.raises(CicloInvalido, match="concluído"):
        ciclo.registrar_sessao(conn, treino, 1)
    with pytest.raises(TreinoNaoEncontrado):
        ciclo.registrar_sessao(conn, 999, 1)

    assert conn.execute("SELECT COUNT(*) FROM sessao").fetchone()[0] == 0


def test_sessoes_feitas_so_do_aluno_pedido(conn):
    da_ana = _treino(conn, 1)
    do_bruno = _treino(conn, 2)
    ciclo.registrar_sessao(conn, da_ana, 1)
    ciclo.registrar_sessao(conn, do_bruno, 2)

    assert ciclo.sessoes_feitas_do_aluno(conn, 1) == {da_ana: {1: 1}}
    assert ciclo.sessoes_feitas_do_aluno(conn, 2) == {do_bruno: {2: 1}}


def test_sessoes_ficam_no_historico_quando_o_treino_e_concluido(conn):
    treino = _treino(conn)
    ciclo.registrar_sessao(conn, treino, 1)
    ciclo.concluir_treino(conn, treino)

    assert ciclo.sessoes_feitas_do_aluno(conn, 1) == {treino: {1: 1}}


# ------------------------------------------------------------------ avaliar o ciclo


def _avaliar(**mudancas):
    base = dict(ativo=True, quantidade_de_fichas=3, sessoes_por_ficha=15, fim=None, feitas_por_ficha={}, hoje_texto="2026-10-08")
    return avaliar_ciclo(**{**base, **mudancas})


def test_sem_meta_e_sem_fim_nunca_manda_trocar():
    avaliacao = _avaliar(sessoes_por_ficha=None, feitas_por_ficha={1: 500, 2: 500, 3: 500})

    assert avaliacao["trocar"] is False
    assert avaliacao["meta_total"] is None
    assert avaliacao["feitas"] == 1500


def test_meta_so_cumprida_quando_TODAS_as_fichas_chegam_la():
    assert _avaliar(feitas_por_ficha={1: 15, 2: 15, 3: 14})["trocar"] is False
    assert _avaliar(feitas_por_ficha={1: 30, 2: 0, 3: 15})["trocar"] is False  # sobra numa ficha não paga a falta de outra
    avaliacao = _avaliar(feitas_por_ficha={1: 15, 2: 15, 3: 15})
    assert avaliacao["trocar"] is True
    assert avaliacao["motivos"] == ["meta"]


def test_passar_da_meta_tambem_conta():
    assert _avaliar(feitas_por_ficha={1: 17, 2: 15, 3: 20})["meta_cumprida"] is True


def test_andamento_por_ficha_e_total():
    avaliacao = _avaliar(feitas_por_ficha={1: 3, 3: 1})

    assert avaliacao["por_ficha"] == [{"ordem": 1, "feitas": 3}, {"ordem": 2, "feitas": 0}, {"ordem": 3, "feitas": 1}]
    assert (avaliacao["feitas"], avaliacao["meta_total"]) == (4, 45)


def test_sessao_de_ficha_que_nao_existe_mais_nao_entra_na_conta():
    # a importação do Data4U pode recriar o treino com menos fichas; a sobra fica de fora
    avaliacao = _avaliar(quantidade_de_fichas=2, feitas_por_ficha={1: 15, 2: 15, 3: 99})

    assert avaliacao["feitas"] == 30
    assert avaliacao["meta_total"] == 30


def test_o_fim_so_vence_no_dia_seguinte():
    assert _avaliar(fim="2026-10-08", hoje_texto="2026-10-08")["trocar"] is False  # no dia do fim ainda vale
    avaliacao = _avaliar(fim="2026-10-08", hoje_texto="2026-10-09")
    assert avaliacao["trocar"] is True
    assert avaliacao["vencido"] is True
    assert avaliacao["motivos"] == ["prazo"]


def test_meta_e_prazo_juntos():
    avaliacao = _avaliar(fim="2026-09-01", feitas_por_ficha={1: 15, 2: 15, 3: 15})

    assert avaliacao["motivos"] == ["meta", "prazo"]


def test_treino_inativo_nunca_manda_trocar():
    avaliacao = _avaliar(ativo=False, fim="2020-01-01", feitas_por_ficha={1: 15, 2: 15, 3: 15})

    assert avaliacao["trocar"] is False
    assert avaliacao["meta_cumprida"] is True  # a informação continua certa; só o aviso some


def test_treino_sem_ficha_com_meta_nao_manda_trocar():
    assert _avaliar(quantidade_de_fichas=0)["trocar"] is False


def test_texto_do_aviso():
    meta = _avaliar(feitas_por_ficha={1: 15, 2: 15, 3: 15})
    prazo = _avaliar(fim="2026-10-01", sessoes_por_ficha=None)
    ambos = _avaliar(fim="2026-10-01", feitas_por_ficha={1: 15, 2: 15, 3: 15})

    assert texto_do_aviso_de_troca("TREINO ABC", meta, 15, None) == (
        'Hora de trocar o treino "TREINO ABC": o aluno fez as 15 sessões de cada ficha.'
    )
    assert texto_do_aviso_de_troca("TREINO ABC", prazo, None, "2026-10-01") == (
        'Hora de trocar o treino "TREINO ABC": a data de fim (01/10/2026) já passou.'
    )
    assert texto_do_aviso_de_troca("X", ambos, 15, "2026-10-01") == (
        'Hora de trocar o treino "X": o aluno fez as 15 sessões de cada ficha e a data de fim (01/10/2026) já passou.'
    )
    assert texto_do_aviso_de_troca("X", _avaliar(), 15, None) == ""


# ------------------------------------------------------------------ na ficha do aluno


def test_ficha_mostra_ativo_inativo_e_andamento(conn):
    antigo = _treino(conn, nome="ANTIGO", inicio="2026-08-01", fim="2026-09-30", sessoes_por_ficha=10)
    atual = _treino(conn, nome="ATUAL", inicio="2026-10-01", sessoes_por_ficha=15)
    ciclo.registrar_sessao(conn, atual, 1)
    ciclo.registrar_sessao(conn, atual, 2)

    ficha = obter_ficha(conn, 1)

    por_nome = {t["nome"]: t for t in ficha["treinos"]}
    assert por_nome["ATUAL"]["ativo"] is True and por_nome["ANTIGO"]["ativo"] is False
    assert (por_nome["ATUAL"]["inicio"], por_nome["ATUAL"]["fim"]) == ("01/10/2026", None)
    assert (por_nome["ANTIGO"]["inicio"], por_nome["ANTIGO"]["fim"]) == ("01/08/2026", "30/09/2026")
    assert por_nome["ATUAL"]["sessoes_texto"] == "2 / 45"
    assert por_nome["ANTIGO"]["sessoes_texto"] == "0 / 30"
    assert [(f["nome"], f["feitas"], f["meta"]) for f in por_nome["ATUAL"]["fichas"]] == [("A", 1, 15), ("B", 1, 15), ("C", 0, 15)]
    assert por_nome["ANTIGO"]["concluido_em"] == "08/10/2026"
    assert ficha["tem_treino_ativo"] is True
    assert ficha["aviso_de_troca"] == ""


def test_ficha_avisa_trocar_quando_a_meta_e_cumprida(conn):
    treino = _treino(conn, fichas=("A", "B"), sessoes_por_ficha=2)
    for ordem in (1, 1, 2, 2):
        ciclo.registrar_sessao(conn, treino, ordem)

    ficha = obter_ficha(conn, 1)

    assert ficha["treinos"][0]["trocar"] is True
    assert ficha["aviso_de_troca"] == 'Hora de trocar o treino "TREINO ABC": o aluno fez as 2 sessões de cada ficha.'


def test_ficha_avisa_trocar_quando_o_fim_passou(conn):
    _treino(conn, inicio="2020-01-01", fim="2020-02-01")

    assert "a data de fim (01/02/2020) já passou" in obter_ficha(conn, 1)["aviso_de_troca"]


def test_ficha_nao_avisa_depois_de_concluir(conn):
    treino = _treino(conn, inicio="2020-01-01", fim="2020-02-01")
    ciclo.concluir_treino(conn, treino)

    ficha = obter_ficha(conn, 1)

    assert ficha["aviso_de_troca"] == ""
    assert ficha["tem_treino_ativo"] is False
    assert ficha["treinos"][0]["trocar"] is False


def test_texto_das_sessoes_sem_meta():
    from app.alunos import texto_das_sessoes

    assert texto_das_sessoes(0, None) == "–"
    assert texto_das_sessoes(7, None) == "7"
    assert texto_das_sessoes(0, 45) == "0 / 45"


def test_treino_ativo_do_aluno(conn):
    assert ciclo.treino_ativo(conn, 1) is None
    treino = _treino(conn, nome="ATUAL")

    assert ciclo.treino_ativo(conn, 1) == {"id": treino, "nome": "ATUAL"}
    assert ciclo.treino_ativo(conn, 2) is None


def test_o_banco_nao_deixa_dois_ativos_nem_por_um_caminho_torto(conn):
    _treino(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO treino (aluno_id, nome, montado_por) VALUES (1, 'OUTRO', 'X')")
