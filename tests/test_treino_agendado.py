"""Treino agendado (pedido do Thiago, 28/10/2026): o professor monta hoje um treino que entra sozinho numa data futura.

O que estes testes protegem:
- início depois de hoje = treino AGENDADO: o ativo continua até o dia; no dia, o novo entra e o atual é concluído;
- a troca acontece no primeiro pedido do dia (aluno, recepção ou professor), uma vez só;
- um agendado por aluno: com um marcado, nada mais se salva até editar ou cancelar;
- editar o agendado (continua agendado; com início hoje, entra na hora) e cancelar (apaga; o ativo não muda);
- o agendado não aparece para o aluno, não é "treino anterior" para o robô e não pode ser "reativado";
- a ficha, a tela de montar, a tela "Pendências" e o celular mostram o que precisam. Dados inventados.
"""

from datetime import datetime, timezone

import pytest

from app import acesso, aluno_acesso, ciclo, ia_treino, pendencias, treinos
from app.aluno_treino import treino_do_aluno
from app.db import conectar, criar_tabelas
from app.web import criar_app

HOJE = datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc)  # 28/10/2026, meio-dia em Brasília
DIA_DA_TROCA = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)  # 12/11/2026, 7h em Brasília
VESPERA = datetime(2026, 11, 12, 2, 0, tzinfo=timezone.utc)  # 11/11/2026, 23h em Brasília: ainda não é o dia


def _dados(nome="TREINO NOVO", inicio="2026-11-12", **extras):
    return {
        "nome_treino": nome,
        "montado_por": "PROF ANA",
        "inicio": inicio,
        "fichas": [{"nome": "A", "itens": [{"exercicio_id": 1, "series": "3", "repeticoes": "12"}]}],
        **extras,
    }


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "agenda.db"
    c = conectar(caminho)
    criar_tabelas(c)
    c.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO RETO', 'app')")
    c.execute("INSERT INTO aluno (id, nome, situacao) VALUES (1, 'ANA FICTICIA', 'A'), (2, 'BIA FICTICIA', 'A')")
    c.commit()
    treinos.salvar_treino(c, 1, _dados("TREINO ATUAL", inicio="2026-10-01", fim="2026-11-11"), agora=HOJE)
    c.close()
    return caminho


@pytest.fixture
def conn(caminho):
    c = conectar(caminho)
    yield c
    c.close()


def _situacao(conn, aluno=1):
    return [tuple(l) for l in conn.execute("SELECT nome, ativo, agendado_para FROM treino WHERE aluno_id = ? ORDER BY id", (aluno,))]


# ------------------------------------------------------------------ salvar


def test_inicio_depois_de_hoje_fica_agendado_e_o_atual_continua(conn):
    treinos.salvar_treino(conn, 1, _dados(), agora=HOJE)

    assert _situacao(conn) == [("TREINO ATUAL", 1, None), ("TREINO NOVO", 0, "2026-11-12")]
    assert treino_do_aluno(conn, 1, HOJE)["nome"] == "TREINO ATUAL"  # o aluno não vê o agendado


def test_inicio_hoje_ou_antes_entra_na_hora_como_sempre(conn):
    treinos.salvar_treino(conn, 1, _dados(inicio="2026-10-28"), agora=HOJE)

    assert _situacao(conn) == [("TREINO ATUAL", 0, None), ("TREINO NOVO", 1, None)]


def test_um_agendado_por_aluno_e_nada_mais_se_salva_ate_editar_ou_cancelar(conn):
    treinos.salvar_treino(conn, 1, _dados(), agora=HOJE)

    for inicio in ("2026-12-01", "2026-10-28"):  # outro agendado, ou um treino para hoje (o agendado o trocaria no dia)
        with pytest.raises(treinos.TreinoInvalido) as erro:
            treinos.salvar_treino(conn, 1, _dados("OUTRO", inicio=inicio), agora=HOJE)
        assert 'já tem um treino agendado: "TREINO NOVO", para começar em 12/11/2026' in erro.value.problemas[0]
    assert len(_situacao(conn)) == 2
    treinos.salvar_treino(conn, 2, _dados("DA BIA"), agora=HOJE)  # outro aluno pode


# ------------------------------------------------------------------ a troca automática


def test_na_vespera_nada_muda_e_no_dia_o_novo_entra_e_o_atual_e_concluido(conn):
    treinos.salvar_treino(conn, 1, _dados(), agora=HOJE)

    assert treinos.ativar_agendados(conn, VESPERA) == 0
    assert _situacao(conn)[1] == ("TREINO NOVO", 0, "2026-11-12")

    assert treinos.ativar_agendados(conn, DIA_DA_TROCA) == 1
    assert _situacao(conn) == [("TREINO ATUAL", 0, None), ("TREINO NOVO", 1, None)]
    assert conn.execute("SELECT concluido_em FROM treino WHERE nome = 'TREINO ATUAL'").fetchone()[0] == "2026-11-12 10:00:00"
    assert treinos.ativar_agendados(conn, DIA_DA_TROCA) == 0  # de novo: nada (já trocou)


def test_quem_ficou_sem_abrir_o_app_por_dias_troca_no_primeiro_acesso_depois(conn):
    treinos.salvar_treino(conn, 1, _dados(), agora=HOJE)

    assert treinos.ativar_agendados(conn, datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc)) == 1
    assert _situacao(conn)[1] == ("TREINO NOVO", 1, None)


def test_aluno_sem_treino_ativo_tambem_recebe_o_agendado(conn):
    treinos.salvar_treino(conn, 2, _dados("DA BIA"), agora=HOJE)

    treinos.ativar_agendados(conn, DIA_DA_TROCA)

    assert _situacao(conn, 2) == [("DA BIA", 1, None)]


def test_a_troca_nao_roda_no_meio_da_transacao_de_quem_chamou(conn):
    treinos.salvar_treino(conn, 1, _dados(), agora=HOJE)
    conn.execute("BEGIN")
    try:
        assert treinos.ativar_agendados(conn, DIA_DA_TROCA) == 0
    finally:
        conn.rollback()


# ------------------------------------------------------------------ editar, cancelar, reativar


def test_editar_o_agendado_mantem_agendado_com_a_data_nova(conn):
    treino_id = treinos.salvar_treino(conn, 1, _dados(), agora=HOJE)

    treinos.editar_treino(conn, treino_id, _dados("NOVO EDITADO", inicio="2026-11-20"), agora=HOJE)

    assert _situacao(conn) == [("TREINO ATUAL", 1, None), ("NOVO EDITADO", 0, "2026-11-20")]


def test_editar_o_agendado_com_inicio_hoje_faz_ele_entrar_na_hora(conn):
    treino_id = treinos.salvar_treino(conn, 1, _dados(), agora=HOJE)

    treinos.editar_treino(conn, treino_id, _dados(inicio="2026-10-28"), agora=HOJE)

    assert _situacao(conn) == [("TREINO ATUAL", 0, None), ("TREINO NOVO", 1, None)]


def test_cancelar_apaga_o_agendado_e_o_atual_continua(conn):
    treino_id = treinos.salvar_treino(conn, 1, _dados(), agora=HOJE)

    treinos.cancelar_agendamento(conn, treino_id)

    assert _situacao(conn) == [("TREINO ATUAL", 1, None)]
    with pytest.raises(treinos.TreinoNaoEncontrado):
        treinos.cancelar_agendamento(conn, treino_id)
    atual = conn.execute("SELECT id FROM treino WHERE nome = 'TREINO ATUAL'").fetchone()[0]
    with pytest.raises(treinos.TreinoInvalido):
        treinos.cancelar_agendamento(conn, atual)  # o ativo não se cancela


def test_agendado_nao_pode_ser_reativado(conn):
    treino_id = treinos.salvar_treino(conn, 2, _dados("DA BIA"), agora=HOJE)

    with pytest.raises(ciclo.CicloInvalido, match="agendado"):
        ciclo.reativar_treino(conn, treino_id)


def test_o_robo_nao_ve_o_agendado_como_treino_anterior(conn):
    treinos.salvar_treino(conn, 2, _dados("DA BIA"), agora=HOJE)

    assert ia_treino.treino_anterior(conn, 2, {1}) == ""


def test_inicio_sugerido_e_o_dia_seguinte_ao_fim_do_atual(conn):
    assert ciclo.inicio_sugerido(conn, 1, HOJE) == "2026-11-12"
    assert ciclo.inicio_sugerido(conn, 1, datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc)) is None  # já passou
    assert ciclo.inicio_sugerido(conn, 2, HOJE) is None  # sem treino ativo


def test_aviso_de_treino_novo_so_no_dia_em_que_ele_comecou(conn):
    treinos.salvar_treino(conn, 1, _dados(), agora=HOJE)
    treinos.ativar_agendados(conn, DIA_DA_TROCA)

    assert treino_do_aluno(conn, 1, DIA_DA_TROCA)["novo_hoje"] is True
    assert treino_do_aluno(conn, 1, datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc))["novo_hoje"] is False


def test_pendencias_listam_as_trocas_agendadas_e_marcam_quem_ja_tem(conn):
    treinos.salvar_treino(conn, 1, _dados(), agora=HOJE)
    treinos.salvar_treino(conn, 2, _dados("DA BIA", inicio="2026-11-05"), agora=HOJE)

    p = pendencias.listar(conn, datetime(2026, 11, 13, 1, 0, tzinfo=timezone.utc))  # 12/11 22h: o atual da Ana venceu em 11/11

    assert [(a["nome"], a["dia"]) for a in p["agendados"]["alunos"]] == [("BIA FICTICIA", "05/11/2026"), ("ANA FICTICIA", "12/11/2026")]
    assert {a["nome"]: a["agendado"] for a in p["trocar"]["alunos"]} == {"ANA FICTICIA": "12/11/2026"}
    assert {a["nome"]: a["agendado"] for a in p["sem_treino"]["alunos"]} == {"BIA FICTICIA": "05/11/2026"}


# ------------------------------------------------------------------ pelas telas


def _professor(caminho):
    app = criar_app(caminho)
    navegador = app.test_client()
    c = conectar(caminho)
    navegador.set_cookie(acesso.NOME_DO_COOKIE, acesso.autorizar(c, acesso.gerar_codigo(c, "Teste").codigo).token)
    c.close()
    return navegador


def test_salvar_pela_api_responde_agendado_e_a_ficha_mostra_e_deixa_cancelar(caminho):
    navegador = _professor(caminho)

    resposta = navegador.post("/api/alunos/1/treinos", json=_dados(inicio="2099-01-15"))

    assert resposta.status_code == 201
    corpo = resposta.get_json()
    assert corpo["agendado_para"] == "15/01/2099" and corpo["continua"] == "TREINO ATUAL" and corpo["concluido_anterior"] is None
    html = navegador.get("/alunos/1").get_data(as_text=True)
    assert "Agendado 15/01<" in html and "Entra sozinho em 15/01/2099" in html
    assert "Cancelar agendamento" in html and "Troca agendada: 15/01/2099" in html
    # o aviso antes de cancelar deixa claro que o treino montado se perde
    assert "o treino que você montou será APAGADO e não dá para recuperar" in html and "Sim, apagar o treino agendado" in html
    assert navegador.post(f"/api/treinos/{corpo['id']}/cancelar-agendamento", json={}).status_code == 200
    assert "Agendado 15/01<" not in navegador.get("/alunos/1").get_data(as_text=True)
    assert navegador.post(f"/api/treinos/{corpo['id']}/cancelar-agendamento", json={}).status_code == 404


def test_a_tela_de_montar_avisa_do_agendado_e_sugere_o_inicio(caminho):
    navegador = _professor(caminho)

    html = navegador.get("/alunos/1/montar").get_data(as_text=True)
    assert 'id="aviso-agendar"' in html and "Data depois de hoje: o treino fica agendado" in html
    assert 'id="aviso-ja-agendado"' not in html

    navegador.post("/api/alunos/1/treinos", json=_dados(inicio="2099-01-15"))
    html = navegador.get("/alunos/1/montar").get_data(as_text=True)
    assert 'id="aviso-ja-agendado"' in html and "15/01/2099" in html


def test_a_troca_acontece_no_primeiro_pedido_do_dia_ate_o_do_aluno(caminho, monkeypatch):
    c = conectar(caminho)
    treinos.salvar_treino(c, 1, _dados(), agora=HOJE)
    token = aluno_acesso._criar_sessao(c, 1, datetime.now(timezone.utc))
    c.commit()
    c.close()
    app = criar_app(caminho)
    monkeypatch.setattr(treinos, "agora_utc", lambda: DIA_DA_TROCA)  # o servidor "acorda" no dia da troca
    aluno = app.test_client()
    aluno.set_cookie(aluno_acesso.NOME_DO_COOKIE, token)

    resposta = aluno.get("/api/aluno/treino")

    assert resposta.status_code == 200
    c = conectar(caminho)
    assert _situacao(c) == [("TREINO ATUAL", 0, None), ("TREINO NOVO", 1, None)]
    c.close()
