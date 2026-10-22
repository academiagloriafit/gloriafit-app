"""Testes da tela "Quem sumiu" (app/ausentes.py e GET /ausentes). Dados inventados."""

from datetime import datetime, timedelta, timezone

import pytest

from app import acesso, aluno_acesso, ausentes, treinos
from app.datas import momento_para_texto
from app.db import conectar, criar_tabelas
from app.web import criar_app

AGORA = datetime(2026, 10, 22, 15, 0, tzinfo=timezone.utc)  # 12h00 de quinta, 22/10/2026, em Brasília


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "ausentes.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.executemany(
        "INSERT INTO aluno (id, nome, cpf, whatsapp, situacao, provisorio) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, "ANA SOUZA", "11144477735", "27988887766", "A", 0),
            (2, "BRUNO LIMA", "52998224725", "27977776655", "A", 0),
            (3, "CARLA DIAS", "39053344705", None, "A", 0),
            (4, "DANILO REIS", "12345678909", "27966665544", "T", 0),  # trancado
            (5, "ELAINE PAES", "98765432100", "27955554433", "D", 0),  # desistente
            (6, "FABIO NEVES", None, "27944443322", None, 1),  # provisório
        ],
    )
    conn.execute("INSERT INTO exercicio (nome, origem) VALUES ('SUPINO RETO', 'app')")
    conn.commit()
    conn.close()
    return caminho


@pytest.fixture
def conn(caminho):
    c = conectar(caminho)
    yield c
    c.close()


def _treino(conn, aluno_id, nome="TREINO ABC", inicio=None):
    extras = {"inicio": inicio} if inicio else {}
    return treinos.salvar_treino(
        conn,
        aluno_id,
        {
            "nome_treino": nome,
            "montado_por": "PROFESSORA",
            "fichas": [{"nome": "A", "itens": [{"exercicio_id": 1, "series": "4", "repeticoes": "12"}]}],
            **extras,
        },
    )


def _sessao(conn, treino_id, quando):
    conn.execute(
        "INSERT INTO sessao (treino_id, ficha_ordem, feita_em) VALUES (?, 1, ?)", (treino_id, momento_para_texto(quando))
    )
    conn.commit()


def _nomes(resultado):
    return [a["nome"] for a in resultado["alunos"]]


# ------------------------------------------------------------------ quem entra na lista


def test_quem_treinou_ha_menos_de_sete_dias_nao_aparece(conn):
    _sessao(conn, _treino(conn, 1), AGORA - timedelta(days=6))

    assert ausentes.listar(conn, 7, AGORA)["alunos"] == []


def test_sete_dias_ja_conta_como_sumido(conn):
    _sessao(conn, _treino(conn, 1), AGORA - timedelta(days=7))

    resultado = ausentes.listar(conn, 7, AGORA)

    assert _nomes(resultado) == ["ANA SOUZA"] and resultado["alunos"][0]["dias"] == 7


def test_o_prazo_escolhido_muda_a_lista(conn):
    _sessao(conn, _treino(conn, 1), AGORA - timedelta(days=9))
    _sessao(conn, _treino(conn, 2), AGORA - timedelta(days=20))

    assert _nomes(ausentes.listar(conn, 7, AGORA)) == ["BRUNO LIMA", "ANA SOUZA"]
    assert _nomes(ausentes.listar(conn, 14, AGORA)) == ["BRUNO LIMA"]
    assert _nomes(ausentes.listar(conn, 30, AGORA)) == []


def test_o_dia_e_o_de_brasilia(conn):
    # 02h30 UTC de 15/10 = 23h30 de 14/10 em Brasília: de 14/10 a 22/10 são 8 dias.
    _sessao(conn, _treino(conn, 1), datetime(2026, 10, 15, 2, 30, tzinfo=timezone.utc))

    assert ausentes.listar(conn, 7, AGORA)["alunos"][0]["dias"] == 8
    assert ausentes.listar(conn, 7, AGORA)["alunos"][0]["ultima"] == "14/10/2026"


def test_conta_a_ultima_marcacao_de_qualquer_treino_do_aluno_e_de_qualquer_ficha(conn):
    antigo = _treino(conn, 1, nome="TREINO ANTIGO")
    _sessao(conn, antigo, AGORA - timedelta(days=30))
    _treino(conn, 1, nome="TREINO NOVO")  # o antigo foi concluído; o novo ainda não tem marcação
    conn.execute("UPDATE treino SET inicio = '2026-10-20' WHERE nome = 'TREINO NOVO'")
    _sessao(conn, antigo, AGORA - timedelta(days=2))
    conn.commit()

    assert ausentes.listar(conn, 7, AGORA)["alunos"] == []


def test_so_alunos_ativos_ou_provisorios_com_treino_ativo_entram(conn):
    for aluno_id in (1, 4, 5, 6):
        treino_id = _treino(conn, aluno_id, inicio="2026-09-01")
        _sessao(conn, treino_id, AGORA - timedelta(days=15))
    _sessao(conn, _treino(conn, 2, nome="CONCLUIDO"), AGORA - timedelta(days=15))
    conn.execute("UPDATE treino SET ativo = 0 WHERE aluno_id = 2")  # Bruno: sem treino ativo
    conn.commit()

    resultado = ausentes.listar(conn, 7, AGORA)

    assert sorted(_nomes(resultado)) == ["ANA SOUZA", "FABIO NEVES"]
    assert resultado["total_com_treino"] == 2
    assert [a["provisorio"] for a in resultado["alunos"] if a["nome"] == "FABIO NEVES"] == [True]


def test_aluno_sem_nenhum_treino_nao_aparece(conn):
    assert ausentes.listar(conn, 7, AGORA) == {
        "dias": 7, "total_com_treino": 0, "total": 0, "alunos": [], "total_sem_registro": 0, "sem_registro": [],
    }


# ------------------------------------------------------------------ quem nunca registrou nada


def test_sem_nenhuma_marcacao_conta_a_partir_do_inicio_do_treino(conn):
    _treino(conn, 1, inicio="2026-10-10")

    resultado = ausentes.listar(conn, 7, AGORA)
    aluno = resultado["sem_registro"][0]

    assert aluno["nunca"] is True and aluno["ultima"] is None
    assert aluno["dias"] == 12 and aluno["desde"] == "10/10/2026"
    assert resultado["alunos"] == [] and resultado["total"] == 0 and resultado["total_sem_registro"] == 1


def test_treino_novo_sem_marcacao_ainda_nao_e_sumico(conn):
    _treino(conn, 1, inicio="2026-10-19")

    resultado = ausentes.listar(conn, 7, AGORA)

    assert resultado["alunos"] == [] and resultado["sem_registro"] == []


def test_treino_que_so_comeca_no_futuro_nao_aparece(conn):
    _treino(conn, 1, inicio="2026-11-15")

    resultado = ausentes.listar(conn, 7, AGORA)

    assert resultado["alunos"] == [] and resultado["sem_registro"] == []


def test_sem_inicio_gravado_vale_o_dia_em_que_o_treino_foi_lancado(conn):
    treino_id = _treino(conn, 1)
    conn.execute("UPDATE treino SET inicio = NULL, criado_em = '2026-10-01 12:00:00' WHERE id = ?", (treino_id,))
    conn.commit()

    aluno = ausentes.listar(conn, 7, AGORA)["sem_registro"][0]

    assert aluno["nunca"] is True and aluno["dias"] == 21 and aluno["desde"] == "01/10/2026"


# ------------------------------------------------------------------ ordem, WhatsApp e limite


def test_os_mais_sumidos_vem_primeiro_e_empate_vai_por_nome(conn):
    _sessao(conn, _treino(conn, 1), AGORA - timedelta(days=10))
    _sessao(conn, _treino(conn, 2), AGORA - timedelta(days=25))
    _sessao(conn, _treino(conn, 3), AGORA - timedelta(days=10))

    assert _nomes(ausentes.listar(conn, 7, AGORA)) == ["BRUNO LIMA", "ANA SOUZA", "CARLA DIAS"]


def test_whatsapp_vem_formatado_e_com_o_link_da_conversa(conn):
    _sessao(conn, _treino(conn, 1), AGORA - timedelta(days=9))

    ana = ausentes.listar(conn, 7, AGORA)["alunos"][0]

    assert ana["whatsapp"] == "(27) 98888-7766" and ana["whatsapp_link"] == "https://wa.me/5527988887766"


@pytest.mark.parametrize("numero", [None, "", "123", "279888877", "279888877660", "27 98888 7766", "2798888776x", "２７９８８８８７７６６"])
def test_link_do_whatsapp_so_sai_para_numero_no_formato_do_app(numero):
    # o banco já recusa número fora do formato; isto é a segunda trava, porque o número vai parar num endereço
    assert ausentes._link_do_whatsapp(numero) is None


@pytest.mark.parametrize(("numero", "link"), [("2738887766", "https://wa.me/552738887766"), ("27988887766", "https://wa.me/5527988887766")])
def test_link_do_whatsapp_aceita_fixo_e_celular(numero, link):
    assert ausentes._link_do_whatsapp(numero) == link


def test_aluno_sem_whatsapp_aparece_sem_link(conn):
    _sessao(conn, _treino(conn, 3), AGORA - timedelta(days=9))

    carla = ausentes.listar(conn, 7, AGORA)["alunos"][0]

    assert carla["whatsapp"] is None and carla["whatsapp_link"] is None


def test_a_lista_tem_limite_mas_o_total_e_real(conn, monkeypatch):
    monkeypatch.setattr(ausentes, "LIMITE_DA_LISTA", 2)
    for aluno_id in (1, 2, 3):
        _sessao(conn, _treino(conn, aluno_id), AGORA - timedelta(days=8 + aluno_id))

    resultado = ausentes.listar(conn, 7, AGORA)

    assert resultado["total"] == 3 and len(resultado["alunos"]) == 2
    assert _nomes(resultado) == ["CARLA DIAS", "BRUNO LIMA"]


def test_quem_nunca_registrou_nao_empurra_para_fora_quem_parou_de_treinar(conn, monkeypatch):
    """Duas listas separadas: com o corte de tamanho, os "nunca registrou" (muitos, e com dias contados desde o início do treino)
    não podem tirar da tela quem treinou pelo app e parou."""
    monkeypatch.setattr(ausentes, "LIMITE_DA_LISTA", 1)
    _treino(conn, 1, inicio="2026-01-05")  # nunca registrou, 290 dias desde o início do treino
    _treino(conn, 2, inicio="2026-01-06")  # idem
    _sessao(conn, _treino(conn, 3), AGORA - timedelta(days=9))  # treinou pelo app e parou há 9 dias

    resultado = ausentes.listar(conn, 7, AGORA)

    assert _nomes(resultado) == ["CARLA DIAS"] and resultado["total"] == 1
    assert [a["nome"] for a in resultado["sem_registro"]] == ["ANA SOUZA"]  # corte por lista (o mais antigo)
    assert resultado["total_sem_registro"] == 2
    assert resultado["total_com_treino"] == 3


@pytest.mark.parametrize(
    ("pedido", "esperado"),
    [("7", 7), ("14", 14), ("30", 30), (None, 7), ("", 7), ("0", 7), ("8", 7), ("-14", 7), ("14.5", 7), ("1e1", 7), ("١٤", 7), ("14 ", 7), (14, 7), (["14"], 7)],
)
def test_prazo_pedido_so_aceita_os_tres_prazos_da_tela(pedido, esperado):
    assert ausentes.prazo_pedido(pedido) == esperado


# ------------------------------------------------------------------ a tela


@pytest.fixture
def professor(caminho):
    conn = conectar(caminho)
    codigo = acesso.gerar_codigo(conn, "Computador dos professores").codigo
    conn.close()
    cliente = criar_app(caminho).test_client()
    assert cliente.post("/api/autorizar", json={"codigo": codigo}).status_code == 200
    return cliente


def _com_sumidos(caminho):
    agora = datetime.now(timezone.utc)
    conn = conectar(caminho)
    _sessao(conn, _treino(conn, 1), agora - timedelta(days=9))
    _sessao(conn, _treino(conn, 2), agora - timedelta(days=20))
    conn.close()


def test_so_computador_autorizado_abre_a_tela(caminho):
    _com_sumidos(caminho)
    sem_autorizacao = criar_app(caminho).test_client()
    conn = conectar(caminho)
    with conn:
        token = aluno_acesso._criar_sessao(conn, 1, datetime.now(timezone.utc))
    conn.close()
    celular = criar_app(caminho).test_client()
    celular.set_cookie(aluno_acesso.NOME_DO_COOKIE, token)

    assert sem_autorizacao.get("/ausentes").status_code == 302
    assert "/autorizar" in sem_autorizacao.get("/ausentes").headers["Location"]
    assert celular.get("/ausentes").status_code == 302  # o cookie do ALUNO não abre a área do professor


def test_a_tela_lista_os_sumidos_com_link_para_a_ficha(caminho, professor):
    _com_sumidos(caminho)

    html = professor.get("/ausentes").get_data(as_text=True)

    assert "Quem sumiu" in html and "ANA SOUZA" in html and "BRUNO LIMA" in html
    assert 'href="/alunos/1"' in html and 'href="/alunos/2"' in html
    assert "9 dias" in html and "20 dias" in html
    assert html.index("BRUNO LIMA") < html.index("ANA SOUZA")  # o mais sumido primeiro
    assert 'href="https://wa.me/5527988887766"' in html and 'rel="noopener noreferrer"' in html


def test_o_prazo_da_tela_vem_da_busca_e_lixo_cai_no_padrao(caminho, professor):
    _com_sumidos(caminho)

    catorze = professor.get("/ausentes?dias=14").get_data(as_text=True)
    lixo = professor.get("/ausentes?dias=abc%27%3E%3Cscript%3E")

    assert "BRUNO LIMA" in catorze and "ANA SOUZA" not in catorze
    assert lixo.status_code == 200 and "<script>" not in lixo.get_data(as_text=True)


def test_nome_do_aluno_nunca_vira_html(caminho, professor):
    _com_sumidos(caminho)
    conn = conectar(caminho)
    conn.execute("UPDATE aluno SET nome = '<b>ANA</b> & CIA' WHERE id = 1")
    conn.commit()
    conn.close()

    html = professor.get("/ausentes").get_data(as_text=True)

    assert "<b>ANA</b>" not in html and "&lt;b&gt;ANA&lt;/b&gt; &amp; CIA" in html


def test_tela_vazia_explica_em_vez_de_mostrar_tabela_sem_linhas(caminho, professor):
    html = professor.get("/ausentes").get_data(as_text=True)

    assert "Nenhum aluno tem treino ativo ainda." in html and 'id="lista-ausentes"' not in html


def test_todos_em_dia_diz_isso(caminho, professor):
    agora = datetime.now(timezone.utc)
    conn = conectar(caminho)
    _sessao(conn, _treino(conn, 1), agora - timedelta(days=1))
    conn.close()

    html = professor.get("/ausentes").get_data(as_text=True)

    assert "Nenhum aluno que já registrou treino está há 7 dias ou mais sem treinar." in html


def test_o_menu_do_professor_tem_quem_sumiu_e_a_tela_nao_aceita_escrita(caminho, professor):
    html = professor.get("/ausentes").get_data(as_text=True)

    assert 'href="/ausentes"' in html and 'aria-current="page">Quem sumiu' in html
    assert professor.post("/ausentes", json={}).status_code == 405


def test_a_tela_separa_quem_nunca_registrou_treino(caminho, professor):
    conn = conectar(caminho)
    _treino(conn, 1, inicio="2026-01-05")  # nunca registrou
    _sessao(conn, _treino(conn, 2), datetime.now(timezone.utc) - timedelta(days=10))
    conn.close()

    html = professor.get("/ausentes").get_data(as_text=True)

    assert 'id="lista-ausentes"' in html and 'id="lista-sem-registro"' in html
    assert "Ainda sem nenhum treino registrado no app" in html
    assert html.index("BRUNO LIMA") < html.index("lista-sem-registro") < html.index("ANA SOUZA")  # cada um na sua seção


def test_sem_ninguem_sem_registro_a_secao_nem_aparece(caminho, professor):
    _com_sumidos(caminho)

    assert "lista-sem-registro" not in professor.get("/ausentes").get_data(as_text=True)
