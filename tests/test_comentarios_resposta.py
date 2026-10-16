"""Testes da resposta do professor ao comentário do aluno (entrega 2 de 2): app/comentarios.py e as rotas novas.

Dados inventados. O professor responde (uma vez por comentário, com o nome que digita) e o aluno lê na lista "Seus comentários".
"""

import threading
from datetime import datetime, timedelta, timezone

import pytest

from app import acesso, aluno_acesso, comentarios, treinos
from app.comentarios import (
    LIMITE_DA_LISTA,
    LIMITE_DO_TEXTO,
    ComentarioInvalido,
    contar_nao_lidos,
    enviar_comentario,
    listar,
    listar_do_aluno,
    marcar_respostas_vistas,
    responder,
)
from app.db import conectar, criar_tabelas
from app.web import criar_app

AGORA = datetime(2026, 10, 15, 11, 0, tzinfo=timezone.utc)  # 08h00 em Brasília
RESPOSTA_AS = AGORA + timedelta(hours=2)  # 10h00 em Brasília
SEGREDO_DO_PROFESSOR = "PROFESSORA SEGREDO"  # quem montou o treino: o aluno nunca pode ver


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "respostas.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.executemany(
        "INSERT INTO aluno (id, nome, cpf, whatsapp, situacao) VALUES (?, ?, ?, ?, ?)",
        [
            (1, "ANA SOUZA", "11144477735", "27988887766", "A"),
            (2, "BRUNO LIMA", "52998224725", "27977776655", "A"),
        ],
    )
    for nome in ["SUPINO RETO", "CRUCIFIXO", "(15) CADEIRA ABDUTORA"]:
        conn.execute("INSERT INTO exercicio (nome, origem) VALUES (?, 'app')", (nome,))
    conn.commit()
    conn.close()
    return caminho


@pytest.fixture
def conn(caminho):
    c = conectar(caminho)
    yield c
    c.close()


def _salvar(conn, aluno_id=1, nome="TREINO ABC"):
    item = {"exercicio_id": 1, "series": "4", "repeticoes": "12", "carga": "20 kg"}
    return treinos.salvar_treino(
        conn,
        aluno_id,
        {"nome_treino": nome, "montado_por": SEGREDO_DO_PROFESSOR, "fichas": [{"nome": "A PEITO", "itens": [item]}]},
    )


def _comentar(conn, texto="Não entendi como faz", agora=AGORA, aluno_id=1, treino="TREINO ABC", **onde):
    return enviar_comentario(conn, aluno_id, treino, texto, agora=agora, **onde)


def _linha(conn, comentario_id=1):
    return dict(conn.execute("SELECT * FROM comentario WHERE id = ?", (comentario_id,)).fetchone())


# ------------------------------------------------------------------ o professor responde


def test_responder_grava_a_resposta_o_nome_e_o_momento(conn):
    _salvar(conn)
    _comentar(conn)

    resultado = responder(conn, 1, "  Professor   Carlos ", "  Abra o quadril assim.  ", agora=RESPOSTA_AS)

    assert resultado == {"respondido_por": "Professor Carlos", "respondido_quando": "15/10/2026 10:00"}
    linha = _linha(conn)
    assert linha["resposta"] == "Abra o quadril assim."
    assert linha["respondido_por"] == "Professor Carlos"
    assert linha["respondido_em"] == "2026-10-15 13:00:00"
    assert linha["resposta_vista_em"] is None  # o aluno ainda não viu


def test_responder_tambem_marca_como_lido(conn):
    _salvar(conn)
    _comentar(conn)
    assert contar_nao_lidos(conn) == 1

    responder(conn, 1, "Carlos", "Ok", agora=RESPOSTA_AS)

    assert contar_nao_lidos(conn) == 0
    assert _linha(conn)["lido_em"] == "2026-10-15 13:00:00"


def test_responder_nao_muda_a_data_de_leitura_de_quem_ja_leu(conn):
    _salvar(conn)
    _comentar(conn)
    comentarios.marcar_lido(conn, 1, agora=AGORA + timedelta(minutes=5))

    responder(conn, 1, "Carlos", "Ok", agora=RESPOSTA_AS)

    assert _linha(conn)["lido_em"] == "2026-10-15 11:05:00"


def test_so_uma_resposta_por_comentario(conn):
    _salvar(conn)
    _comentar(conn)
    responder(conn, 1, "Carlos", "Primeira", agora=RESPOSTA_AS)

    with pytest.raises(ComentarioInvalido) as erro:
        responder(conn, 1, "Maria", "Segunda", agora=RESPOSTA_AS + timedelta(minutes=1))

    assert erro.value.status == 409
    assert _linha(conn)["resposta"] == "Primeira" and _linha(conn)["respondido_por"] == "Carlos"


def test_responder_comentario_que_nao_existe_da_404(conn):
    with pytest.raises(ComentarioInvalido) as erro:
        responder(conn, 999, "Carlos", "Ok")

    assert erro.value.status == 404


@pytest.mark.parametrize("professor", [None, "", "   ", 5, ["Carlos"], "A" * 61, "Carlos\x00", "Car\u200blos"])
def test_nome_do_professor_invalido_da_400_e_nao_grava(conn, professor):
    _salvar(conn)
    _comentar(conn)

    with pytest.raises(ComentarioInvalido) as erro:
        responder(conn, 1, professor, "Ok")

    assert erro.value.status == 400
    assert _linha(conn)["resposta"] is None and contar_nao_lidos(conn) == 1


@pytest.mark.parametrize(
    "resposta",
    [None, "", "   ", 5, "x" * (LIMITE_DO_TEXTO + 1), "oi\x00", "oi \ud800", "ok\u202eevil", "\u200b", ["ok"]],
)
def test_resposta_invalida_da_400_e_nao_grava(conn, resposta):
    _salvar(conn)
    _comentar(conn)

    with pytest.raises(ComentarioInvalido) as erro:
        responder(conn, 1, "Carlos", resposta)

    assert erro.value.status == 400
    assert _linha(conn)["resposta"] is None and contar_nao_lidos(conn) == 1


def test_resposta_de_500_letras_e_com_quebra_de_linha_vale(conn):
    _salvar(conn)
    _comentar(conn)

    responder(conn, 1, "Carlos", "a" * (LIMITE_DO_TEXTO - 3) + "\r\nb\n", agora=RESPOSTA_AS)

    assert len(_linha(conn)["resposta"]) == LIMITE_DO_TEXTO - 3 + 2  # "\r\n" virou "\n"; a quebra final foi cortada


def test_duas_respostas_ao_mesmo_tempo_gravam_so_uma(caminho):
    conn = conectar(caminho)
    _salvar(conn)
    _comentar(conn)
    conn.close()
    resultados, barreira = [], threading.Barrier(2)

    def responder_em_paralelo(nome):
        c = conectar(caminho)
        try:
            barreira.wait()
            resultados.append(responder(c, 1, nome, f"Resposta de {nome}", agora=RESPOSTA_AS)["respondido_por"])
        except ComentarioInvalido as erro:
            resultados.append(erro.status)
        finally:
            c.close()

    fios = [threading.Thread(target=responder_em_paralelo, args=(n,)) for n in ("Carlos", "Maria")]
    [f.start() for f in fios]
    [f.join() for f in fios]

    assert sorted(r for r in resultados if isinstance(r, int)) == [409]  # uma recebeu "já respondido"
    assert sum(isinstance(r, str) for r in resultados) == 1  # e a outra gravou
    conn = conectar(caminho)
    assert _linha(conn)["resposta"] in ("Resposta de Carlos", "Resposta de Maria")
    conn.close()


def test_o_professor_ve_a_resposta_na_lista(conn):
    _salvar(conn)
    _comentar(conn)
    _comentar(conn, "Dói", agora=AGORA + timedelta(minutes=11))
    responder(conn, 1, "Carlos", "Faça devagar", agora=RESPOSTA_AS)

    por_id = {c["id"]: c for c in listar(conn, so_nao_lidos=False)["comentarios"]}

    assert por_id[1]["resposta"] == "Faça devagar" and por_id[1]["respondido_por"] == "Carlos"
    assert por_id[1]["respondido_quando"] == "15/10/2026 10:00" and por_id[1]["resposta_vista"] is False
    assert por_id[2]["resposta"] is None and por_id[2]["respondido_quando"] is None


# ------------------------------------------------------------------ o aluno lê as respostas


def test_o_aluno_so_ve_os_proprios_comentarios(conn):
    _salvar(conn, aluno_id=1)
    _salvar(conn, aluno_id=2, nome="TREINO DO BRUNO")
    _comentar(conn, "da Ana")
    _comentar(conn, "do Bruno", aluno_id=2, treino="TREINO DO BRUNO")
    responder(conn, 2, "Carlos", "Resposta para o Bruno", agora=RESPOSTA_AS)

    da_ana = listar_do_aluno(conn, 1)

    assert [c["texto"] for c in da_ana["comentarios"]] == ["da Ana"]
    assert da_ana["total"] == 1 and da_ana["respostas_novas"] == 0
    assert "Resposta para o Bruno" not in str(da_ana)


def test_o_aluno_ve_a_resposta_com_nome_e_hora_e_nada_do_treino_interno(conn):
    _salvar(conn)
    _comentar(conn, "Dói o ombro", ficha=1, item=1, exercicio="SUPINO RETO")
    responder(conn, 1, "Carlos", "Diminua a carga", agora=RESPOSTA_AS)

    visto = listar_do_aluno(conn, 1)

    assert visto["total"] == 1 and visto["respostas_novas"] == 1
    (c,) = visto["comentarios"]
    assert c["texto"] == "Dói o ombro" and c["ficha"] == "A PEITO" and c["exercicio"] == "SUPINO RETO"
    assert c["quando"] == "15/10/2026 08:00"
    assert c["resposta"] == {"por": "Carlos", "quando": "15/10/2026 10:00", "texto": "Diminua a carga", "nova": True}
    assert SEGREDO_DO_PROFESSOR not in str(visto)  # quem montou o treino nunca sai
    assert set(c) == {"id", "treino", "ficha", "exercicio", "texto", "quando", "resposta"}  # sem aluno_id, lido, datas cruas


def test_comentario_do_treino_inteiro_e_sem_resposta(conn):
    _salvar(conn)
    _comentar(conn)

    (c,) = listar_do_aluno(conn, 1)["comentarios"]

    assert c["ficha"] is None and c["exercicio"] is None and c["resposta"] is None


def test_respostas_novas_vem_primeiro_mesmo_as_antigas(conn):
    _salvar(conn)
    for n in range(3):
        _comentar(conn, f"comentário {n}", agora=AGORA + timedelta(minutes=11 * n))
    responder(conn, 1, "Carlos", "Resposta do mais antigo", agora=RESPOSTA_AS)  # o 1 é o mais velho

    textos = [c["texto"] for c in listar_do_aluno(conn, 1)["comentarios"]]

    assert textos == ["comentário 0", "comentário 2", "comentário 1"]


def test_a_lista_do_aluno_tem_limite_mas_conta_todas_as_novas(conn):
    _salvar(conn)
    with conn:
        for n in range(LIMITE_DA_LISTA + 5):
            conn.execute(
                "INSERT INTO comentario (aluno_id, treino_id, treino_nome, texto, criado_em, resposta, respondido_por, respondido_em)"
                " VALUES (1, 1, 'TREINO ABC', ?, '2026-10-15 11:00:00', 'ok', 'Carlos', '2026-10-15 12:00:00')",
                (f"c{n}",),
            )

    visto = listar_do_aluno(conn, 1, limite=10_000)

    assert len(visto["comentarios"]) == LIMITE_DA_LISTA  # nunca passa do teto
    assert visto["total"] == visto["respostas_novas"] == LIMITE_DA_LISTA + 5


def test_marcar_respostas_vistas_so_marca_as_do_aluno_e_so_os_ids_pedidos(conn):
    _salvar(conn, aluno_id=1)
    _salvar(conn, aluno_id=2, nome="TREINO DO BRUNO")
    _comentar(conn, "a1")
    _comentar(conn, "a2", agora=AGORA + timedelta(minutes=11))
    _comentar(conn, "b1", aluno_id=2, treino="TREINO DO BRUNO")
    for n in (1, 2, 3):
        responder(conn, n, "Carlos", f"r{n}", agora=RESPOSTA_AS)

    resultado = marcar_respostas_vistas(conn, 1, [1, 3], agora=RESPOSTA_AS + timedelta(hours=1))  # 3 é do Bruno

    assert resultado == {"marcados": 1, "respostas_novas": 1}  # sobra a r2, que a tela não mostrava
    assert _linha(conn, 1)["resposta_vista_em"] == "2026-10-15 14:00:00"
    assert _linha(conn, 2)["resposta_vista_em"] is None
    assert _linha(conn, 3)["resposta_vista_em"] is None  # o do Bruno ninguém mexe
    assert marcar_respostas_vistas(conn, 1, [1])["marcados"] == 0  # repetir não muda a data
    assert _linha(conn, 1)["resposta_vista_em"] == "2026-10-15 14:00:00"


def test_marcar_vista_comentario_sem_resposta_nao_faz_nada(conn):
    _salvar(conn)
    _comentar(conn)

    assert marcar_respostas_vistas(conn, 1, [1]) == {"marcados": 0, "respostas_novas": 0}
    assert _linha(conn)["resposta_vista_em"] is None


@pytest.mark.parametrize("ids", [None, [], "1", 1, [0], [-1], [True], [1.5], ["1"], [None], [2**63], list(range(1, LIMITE_DA_LISTA + 2))])
def test_marcar_respostas_vistas_com_lista_invalida_da_400(conn, ids):
    with pytest.raises(ComentarioInvalido) as erro:
        marcar_respostas_vistas(conn, 1, ids)

    assert erro.value.status == 400


# ------------------------------------------------------------------ as rotas


@pytest.fixture
def cliente_da_ana(caminho):
    app = criar_app(caminho)
    conn = conectar(caminho)
    with conn:
        token = aluno_acesso._criar_sessao(conn, 1, AGORA)
    conn.close()
    cliente = app.test_client()
    cliente.set_cookie(aluno_acesso.NOME_DO_COOKIE, token)
    return cliente


@pytest.fixture
def professor(caminho):
    conn = conectar(caminho)
    codigo = acesso.gerar_codigo(conn, "Computador dos professores").codigo
    conn.close()
    cliente = criar_app(caminho).test_client()
    assert cliente.post("/api/autorizar", json={"codigo": codigo}).status_code == 200
    return cliente


def _dois_comentarios(caminho):
    conn = conectar(caminho)
    _salvar(conn, aluno_id=1)
    _salvar(conn, aluno_id=2, nome="TREINO DO BRUNO")
    _comentar(conn, "da Ana")
    _comentar(conn, "do Bruno", aluno_id=2, treino="TREINO DO BRUNO")
    conn.close()


def test_professor_responde_pela_rota(caminho, professor):
    _dois_comentarios(caminho)

    r = professor.post("/api/comentarios/1/responder", json={"professor": "Carlos", "resposta": "Faça assim"})

    corpo = r.get_json()
    assert r.status_code == 200 and corpo["ok"] is True and corpo["respondido_por"] == "Carlos"
    assert corpo["nao_lidos"] == 1 and corpo["respondido_quando"]  # o do Bruno continua sem ler


def test_responder_pela_rota_erros(caminho, professor):
    _dois_comentarios(caminho)
    url = "/api/comentarios/1/responder"
    certo = {"professor": "Carlos", "resposta": "Ok"}

    assert professor.post(url, json={**certo, "professor": ""}).status_code == 400
    assert professor.post(url, json={**certo, "resposta": " "}).status_code == 400
    assert professor.post(url, json=["x"]).status_code == 400
    assert professor.post(url, data="professor=Carlos", content_type="application/x-www-form-urlencoded").status_code == 415
    assert professor.post("/api/comentarios/999/responder", json=certo).status_code == 404
    assert professor.post(url, json=certo).status_code == 200
    segunda = professor.post(url, json=certo)
    assert segunda.status_code == 409 and "já foi respondido" in segunda.get_json()["erro"]


@pytest.mark.parametrize("numero", [2**63, 99999999999999999999])
def test_responder_com_id_gigante_da_404(caminho, professor, numero):
    assert professor.post(f"/api/comentarios/{numero}/responder", json={"professor": "C", "resposta": "x"}).status_code == 404


def test_so_computador_autorizado_responde(caminho, cliente_da_ana):
    _dois_comentarios(caminho)
    sem_autorizacao = criar_app(caminho).test_client()
    corpo = {"professor": "Carlos", "resposta": "Ok"}

    assert sem_autorizacao.post("/api/comentarios/1/responder", json=corpo).status_code == 401
    # o aluno logado NÃO é professor: o cookie dele não autoriza a rota do professor
    assert cliente_da_ana.post("/api/comentarios/1/responder", json=corpo).status_code == 401
    conn = conectar(caminho)
    assert _linha(conn)["resposta"] is None
    conn.close()


def test_responder_exige_origem_do_proprio_site(caminho, professor):
    _dois_comentarios(caminho)

    r = professor.post(
        "/api/comentarios/1/responder",
        json={"professor": "Carlos", "resposta": "Ok"},
        headers={"Origin": "https://site-malvado.example"},
    )

    assert r.status_code == 403
    conn = conectar(caminho)
    assert _linha(conn)["resposta"] is None
    conn.close()


def test_aluno_sem_login_nao_le_nem_marca(caminho):
    _dois_comentarios(caminho)
    anonimo = criar_app(caminho).test_client()

    assert anonimo.get("/api/aluno/comentarios").status_code == 401
    assert anonimo.post("/api/aluno/comentarios/vistos", json={"ids": [1]}).status_code == 401


def test_aluno_le_so_os_dele_pela_rota(caminho, cliente_da_ana, professor):
    _dois_comentarios(caminho)
    professor.post("/api/comentarios/1/responder", json={"professor": "Carlos", "resposta": "Para a Ana"})
    professor.post("/api/comentarios/2/responder", json={"professor": "Carlos", "resposta": "Para o Bruno"})

    r = cliente_da_ana.get("/api/aluno/comentarios")

    corpo = r.get_json()
    assert r.status_code == 200 and corpo["total"] == 1 and corpo["respostas_novas"] == 1
    assert corpo["comentarios"][0]["resposta"]["texto"] == "Para a Ana"
    assert "Para o Bruno" not in r.get_data(as_text=True) and SEGREDO_DO_PROFESSOR not in r.get_data(as_text=True)


def test_aluno_marca_como_visto_pela_rota_e_nao_mexe_nos_dos_outros(caminho, cliente_da_ana, professor):
    _dois_comentarios(caminho)
    professor.post("/api/comentarios/1/responder", json={"professor": "Carlos", "resposta": "Para a Ana"})
    professor.post("/api/comentarios/2/responder", json={"professor": "Carlos", "resposta": "Para o Bruno"})

    r = cliente_da_ana.post("/api/aluno/comentarios/vistos", json={"ids": [1, 2]})  # o 2 é do Bruno

    assert r.status_code == 200 and r.get_json() == {"ok": True, "marcados": 1, "respostas_novas": 0}
    conn = conectar(caminho)
    assert _linha(conn, 1)["resposta_vista_em"] is not None and _linha(conn, 2)["resposta_vista_em"] is None
    conn.close()
    assert cliente_da_ana.get("/api/aluno/comentarios").get_json()["comentarios"][0]["resposta"]["nova"] is False


@pytest.mark.parametrize("corpo", [{}, {"ids": []}, {"ids": "1"}, {"ids": [True]}, {"ids": [2**63]}, [1], "x"])
def test_marcar_visto_com_corpo_invalido_da_400(caminho, cliente_da_ana, corpo):
    _dois_comentarios(caminho)

    assert cliente_da_ana.post("/api/aluno/comentarios/vistos", json=corpo).status_code == 400


def test_marcar_visto_exige_json_e_origem(caminho, cliente_da_ana):
    _dois_comentarios(caminho)

    assert cliente_da_ana.post("/api/aluno/comentarios/vistos", data="ids=1", content_type="text/plain").status_code == 415
    de_outro_site = cliente_da_ana.post(
        "/api/aluno/comentarios/vistos", json={"ids": [1]}, headers={"Origin": "https://site-malvado.example"}
    )
    assert de_outro_site.status_code == 403


# ------------------------------------------------------------------ as telas do professor


def test_a_tela_mostra_a_resposta_escapada_e_so_oferece_responder_a_quem_nao_tem(caminho, professor):
    _dois_comentarios(caminho)
    professor.post(
        "/api/comentarios/1/responder", json={"professor": "Carlos <b>", "resposta": '<img src=x onerror="alert(1)"> Faça assim'}
    )

    html = professor.get("/comentarios?todos=1").get_data(as_text=True)

    assert "Respondido por Carlos &lt;b&gt;" in html
    assert "&lt;img src=x onerror=" in html and "<img src=x" not in html
    assert html.count("data-responder=") == 1  # só o comentário do Bruno ainda pode ser respondido
    assert 'data-responder="2"' in html


def test_a_ficha_do_aluno_mostra_a_resposta_e_se_o_aluno_ja_viu(caminho, professor, cliente_da_ana):
    _dois_comentarios(caminho)
    professor.post("/api/comentarios/1/responder", json={"professor": "Carlos", "resposta": "Faça assim"})

    antes = professor.get("/alunos/1").get_data(as_text=True)
    cliente_da_ana.post("/api/aluno/comentarios/vistos", json={"ids": [1]})
    depois = professor.get("/alunos/1").get_data(as_text=True)

    assert "Respondido por Carlos" in antes and "Faça assim" in antes
    assert "o aluno ainda não viu" in antes and "o aluno já viu" not in antes
    assert "o aluno já viu" in depois and "o aluno ainda não viu" not in depois


def test_responder_tira_o_comentario_da_lista_de_novos_e_do_contador(caminho, professor):
    _dois_comentarios(caminho)
    assert 'data-comentarios-novos="2"' in professor.get("/comentarios").get_data(as_text=True)

    professor.post("/api/comentarios/1/responder", json={"professor": "Carlos", "resposta": "Ok"})

    novos = professor.get("/comentarios").get_data(as_text=True)
    assert 'data-comentarios-novos="1"' in novos and "da Ana" not in novos


def test_o_aluno_so_ve_texto_nas_paginas_dele(caminho, cliente_da_ana, professor):
    _dois_comentarios(caminho)
    professor.post("/api/comentarios/1/responder", json={"professor": "Carlos", "resposta": "Faça assim"})

    pagina = cliente_da_ana.get("/aluno").get_data(as_text=True)

    assert "Faça assim" not in pagina  # a resposta só vem pela API (texto), a página não a embute
    assert contar_nao_lidos(conectar(caminho)) == 1


# ------------------------------------------------------------------ casos que a revisão independente pediu


def test_resposta_que_chega_depois_continua_contada_como_nova_para_o_aviso_voltar(conn):
    """O celular mostra a lista de antes; o professor responde outro comentário; o aluno marca só o que viu: sobra 1 nova."""
    _salvar(conn)
    _comentar(conn, "primeiro")
    _comentar(conn, "segundo", agora=AGORA + timedelta(minutes=11))
    responder(conn, 1, "Carlos", "Resposta 1", agora=RESPOSTA_AS)
    vistos_pela_tela = [c["id"] for c in listar_do_aluno(conn, 1)["comentarios"] if c["resposta"] and c["resposta"]["nova"]]
    responder(conn, 2, "Carlos", "Resposta 2", agora=RESPOSTA_AS)  # chegou depois de a tela buscar a lista

    resultado = marcar_respostas_vistas(conn, 1, vistos_pela_tela)

    assert vistos_pela_tela == [1]
    assert resultado == {"marcados": 1, "respostas_novas": 1}
    de_novo = listar_do_aluno(conn, 1)
    assert [c["id"] for c in de_novo["comentarios"] if c["resposta"]["nova"]] == [2]  # a busca seguinte já traz a nova


def test_a_rota_da_lista_do_aluno_mostra_so_os_30_mais_novos_mas_conta_todos(caminho, cliente_da_ana):
    conn = conectar(caminho)
    _salvar(conn)
    for n in range(35):  # direto no banco: o limite de 20 por dia vale para quem comenta pela tela, não para este teste
        conn.execute(
            "INSERT INTO comentario (aluno_id, treino_nome, texto, criado_em) VALUES (1, 'TREINO ABC', ?, ?)",
            (f"comentário {n:02d}", f"2026-10-0{1 + n // 10} 1{n % 10}:00:00"),
        )
    conn.commit()
    responder(conn, 1, "Carlos", "Resposta ao mais antigo", agora=RESPOSTA_AS)
    conn.close()

    corpo = cliente_da_ana.get("/api/aluno/comentarios").get_json()

    assert corpo["total"] == 35 and corpo["respostas_novas"] == 1
    assert len(corpo["comentarios"]) == 30
    assert corpo["comentarios"][0]["resposta"]["nova"] is True  # a resposta nova do mais antigo não fica de fora


def test_sessao_do_aluno_encerrada_perde_o_acesso_as_rotas_novas(caminho, cliente_da_ana):
    _dois_comentarios(caminho)
    assert cliente_da_ana.get("/api/aluno/comentarios").status_code == 200
    conn = conectar(caminho)
    with conn:
        conn.execute("DELETE FROM aluno_sessao")  # como o "Sair" ou a validade vencida
    conn.close()

    assert cliente_da_ana.get("/api/aluno/comentarios").status_code == 401
    assert cliente_da_ana.post("/api/aluno/comentarios/vistos", json={"ids": [1]}).status_code == 401


def test_resposta_dada_de_madrugada_em_utc_mostra_o_dia_certo_em_brasilia(conn):
    _salvar(conn)
    _comentar(conn, agora=datetime(2026, 10, 15, 2, 30, tzinfo=timezone.utc))  # 23h30 do dia 14 em Brasília
    responder(conn, 1, "Carlos", "Boa noite", agora=datetime(2026, 10, 15, 3, 5, tzinfo=timezone.utc))  # 00h05 do dia 15

    (c,) = listar_do_aluno(conn, 1)["comentarios"]

    assert c["quando"] == "14/10/2026 23:30"
    assert c["resposta"]["quando"] == "15/10/2026 00:05"


def test_a_ficha_oferece_responder_so_a_quem_ainda_nao_tem_resposta(caminho, professor):
    _dois_comentarios(caminho)

    antes = professor.get("/alunos/1").get_data(as_text=True)
    professor.post("/api/comentarios/1/responder", json={"professor": "Carlos", "resposta": "Ok"})
    depois = professor.get("/alunos/1").get_data(as_text=True)

    assert 'data-responder="1"' in antes and 'data-responder-area="1"' in antes
    assert 'data-responder="1"' not in depois
