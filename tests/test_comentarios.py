"""Testes dos comentários do aluno sobre o treino (app/comentarios.py, a rota do celular e as telas do professor).

Dados inventados. Entrega 1 de 2: o aluno escreve; o professor lê e marca como lido (a resposta é a entrega 2, em
tests/test_comentarios_resposta.py).
"""

import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import pytest

from app import acesso, aluno_acesso, comentarios, treinos
from app.comentarios import (
    LIMITE_DA_LISTA,
    LIMITE_DO_TEXTO,
    LIMITE_POR_DIA,
    ComentarioInvalido,
    contar_nao_lidos,
    enviar_comentario,
    listar,
    marcar_lido,
    marcar_lidos_do_aluno,
)
from app.datas import momento_para_texto
from app.db import conectar, criar_tabelas
from app.web import criar_app

AGORA = datetime(2026, 10, 15, 11, 0, tzinfo=timezone.utc)  # 08h00 em Brasília
SEGREDO_DO_PROFESSOR = "PROFESSORA SEGREDO"


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "comentarios.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.executemany(
        "INSERT INTO aluno (id, nome, cpf, whatsapp, situacao) VALUES (?, ?, ?, ?, ?)",
        [
            (1, "ANA SOUZA", "11144477735", "27988887766", "A"),
            (2, "BRUNO LIMA", "52998224725", "27977776655", "A"),
        ],
    )
    for nome in ["SUPINO RETO", "CRUCIFIXO", "(15) CADEIRA ABDUTORA", "TRICEPS TESTA", "ROSCA DIRETA"]:
        conn.execute("INSERT INTO exercicio (nome, origem) VALUES (?, 'app')", (nome,))
    conn.commit()
    conn.close()
    return caminho


@pytest.fixture
def conn(caminho):
    c = conectar(caminho)
    yield c
    c.close()


def _item(exercicio_id, **extras):
    return {"exercicio_id": exercicio_id, "series": "4", "repeticoes": "12", "carga": "20 kg", **extras}


def _salvar(conn, aluno_id=1, nome="TREINO ABC", fichas=None):
    fichas = fichas or [("A PEITO", [_item(1), _item(2)]), ("B PERNA", [_item(3)])]
    return treinos.salvar_treino(
        conn,
        aluno_id,
        {"nome_treino": nome, "montado_por": SEGREDO_DO_PROFESSOR, "fichas": [{"nome": n, "itens": i} for n, i in fichas]},
    )


def _comentar(conn, texto="Está leve demais", treino="TREINO ABC", agora=AGORA, aluno_id=1, **onde):
    return enviar_comentario(conn, aluno_id, treino, texto, agora=agora, **onde)


def _linhas(conn):
    return [dict(linha) for linha in conn.execute("SELECT * FROM comentario ORDER BY id")]


# ------------------------------------------------------------------ o aluno comenta o treino inteiro


def test_comentario_do_treino_inteiro_grava_o_texto_e_a_copia_dos_nomes(conn):
    treino_id = _salvar(conn)

    resposta = _comentar(conn, "  Está leve demais  ")

    assert resposta == {"repetido": False}
    (linha,) = _linhas(conn)
    assert linha["aluno_id"] == 1 and linha["treino_id"] == treino_id and linha["treino_nome"] == "TREINO ABC"
    assert linha["ficha_ordem"] is None and linha["ficha_nome"] is None and linha["exercicio_nome"] is None
    assert linha["texto"] == "Está leve demais"
    assert linha["criado_em"] == "2026-10-15 11:00:00"
    assert linha["lido_em"] is None and linha["resposta"] is None


def test_comentario_de_um_exercicio_guarda_ficha_e_nome_do_que_o_aluno_viu(conn):
    _salvar(conn)

    _comentar(conn, "Dói o ombro", ficha=2, item=1, exercicio="CADEIRA ABDUTORA")  # sem o "(15)" da máquina, como no celular

    (linha,) = _linhas(conn)
    assert (linha["ficha_ordem"], linha["ficha_nome"], linha["exercicio_nome"]) == (2, "B PERNA", "CADEIRA ABDUTORA")
    assert linha["texto"] == "Dói o ombro"


def test_exercicio_dentro_de_bi_set_e_achado_pelo_numero(conn):
    _salvar(conn, fichas=[("A", [_item(1), _item(2, bloco=1), _item(4, bloco=1), _item(5)])])

    _comentar(conn, "Difícil fazer seguido", ficha=1, item=3, exercicio="TRICEPS TESTA")

    assert _linhas(conn)[0]["exercicio_nome"] == "TRICEPS TESTA"


def test_quebra_de_linha_e_tab_passam_e_o_texto_fica_com_quebra_unica(conn):
    _salvar(conn)

    _comentar(conn, "linha 1\r\nlinha 2\tcom tab\rlinha 3")

    assert _linhas(conn)[0]["texto"] == "linha 1\nlinha 2\tcom tab\nlinha 3"


def test_html_no_comentario_e_gravado_como_texto_sem_mexer(conn):
    _salvar(conn)

    _comentar(conn, '<script>alert("oi")</script> & "aspas"')

    assert _linhas(conn)[0]["texto"] == '<script>alert("oi")</script> & "aspas"'


# ------------------------------------------------------------------ texto inválido


@pytest.mark.parametrize("texto", [None, "", "   ", "\n\t ", 7, 1.5, True, [], {}, ["oi"]])
def test_texto_vazio_ou_que_nao_e_texto_da_400_e_nao_grava(conn, texto):
    _salvar(conn)

    with pytest.raises(ComentarioInvalido) as erro:
        _comentar(conn, texto)

    assert erro.value.status == 400
    assert _linhas(conn) == []


def test_limite_de_500_letras(conn):
    _salvar(conn)

    _comentar(conn, "x" * LIMITE_DO_TEXTO)  # 500 passa
    with pytest.raises(ComentarioInvalido) as erro:
        _comentar(conn, "y" * (LIMITE_DO_TEXTO + 1))

    assert erro.value.status == 400 and "500" in str(erro.value)
    assert len(_linhas(conn)) == 1


def test_o_limite_conta_letras_e_nao_bytes(conn):
    _salvar(conn)

    _comentar(conn, "ã" * LIMITE_DO_TEXTO)  # 500 letras com acento (1.000 bytes) passam

    assert len(_linhas(conn)[0]["texto"]) == LIMITE_DO_TEXTO


@pytest.mark.parametrize("letra", ["\x00", "\x07", "\x1b", "\x7f", "\x85"])
def test_caractere_de_controle_e_recusado(conn, letra):
    _salvar(conn)

    with pytest.raises(ComentarioInvalido) as erro:
        _comentar(conn, f"oi{letra}tchau")

    assert erro.value.status == 400
    assert _linhas(conn) == []


@pytest.mark.parametrize("texto", ["oi \ud800 tchau", "metade\udc00", "\ud83d de emoji"])
def test_metade_solta_de_letra_e_recusada_com_400_e_nao_estoura(conn, texto):
    # Um "surrogate" solto não cabe em UTF-8: sem esta conferência o SQLite falhava e a rota respondia 500.
    _salvar(conn)

    with pytest.raises(ComentarioInvalido) as erro:
        _comentar(conn, texto)

    assert erro.value.status == 400 and _linhas(conn) == []


@pytest.mark.parametrize("letra", ["\u202e", "\u202a", "\u2066", "\u2069"])
def test_controle_de_direcao_do_texto_e_recusado(conn, letra):
    # U+202E (e parentes) inverte o que vem depois e disfarça o texto na tela do professor.
    _salvar(conn)

    with pytest.raises(ComentarioInvalido) as erro:
        _comentar(conn, f"ok{letra}evil")

    assert erro.value.status == 400 and _linhas(conn) == []


@pytest.mark.parametrize("texto", ["\u200b", "\u200b\u200d", " \u2060 \n\u200b"])
def test_texto_so_com_caractere_invisivel_nao_e_comentario(conn, texto):
    _salvar(conn)

    with pytest.raises(ComentarioInvalido) as erro:
        _comentar(conn, texto)

    assert erro.value.status == 400 and _linhas(conn) == []


def test_emoji_composto_continua_valendo(conn):
    # A família 👨‍👩‍👧 usa U+200D (categoria "Cf") para juntar os emojis: precisa passar.
    _salvar(conn)

    _comentar(conn, "Gostei \U0001f468\u200d\U0001f469\u200d\U0001f467 \U0001f4aa")

    assert len(_linhas(conn)) == 1


# ------------------------------------------------------------------ o treino tem que existir e ser o que o aluno viu


def test_sem_treino_ativo_da_409(conn):
    with pytest.raises(ComentarioInvalido) as erro:
        _comentar(conn)

    assert erro.value.status == 409
    assert _linhas(conn) == []


def test_treino_concluido_nao_recebe_comentario(conn):
    treino_id = _salvar(conn)
    conn.execute("UPDATE treino SET ativo = 0 WHERE id = ?", (treino_id,))
    conn.commit()

    with pytest.raises(ComentarioInvalido) as erro:
        _comentar(conn)

    assert erro.value.status == 409


def test_aluno_que_nao_existe_da_409_e_nao_grava(conn):
    _salvar(conn)

    with pytest.raises(ComentarioInvalido) as erro:
        _comentar(conn, aluno_id=999)

    assert erro.value.status == 409
    assert _linhas(conn) == []


@pytest.mark.parametrize("nome", ["TREINO NOVO", "treino abc", "", None, 7])
def test_se_o_nome_do_treino_nao_bate_o_celular_estava_velho(conn, nome):
    _salvar(conn)

    with pytest.raises(ComentarioInvalido) as erro:
        _comentar(conn, treino=nome)

    assert erro.value.status == 409
    assert _linhas(conn) == []


def test_professor_troca_o_treino_enquanto_o_aluno_escrevia_nao_cai_no_treino_novo(conn):
    _salvar(conn, nome="TREINO ANTIGO")
    _salvar(conn, nome="TREINO NOVO")  # salvar um novo conclui o antigo

    with pytest.raises(ComentarioInvalido) as erro:
        _comentar(conn, treino="TREINO ANTIGO")

    assert erro.value.status == 409 and "Atualize" in str(erro.value)
    assert _linhas(conn) == []


@pytest.mark.parametrize(
    "onde",
    [
        {"ficha": 1, "item": 1, "exercicio": "CRUCIFIXO"},  # o item 1 da ficha A é outro exercício
        {"ficha": 1, "item": 1, "exercicio": "supino reto"},  # o nome tem que ser igual
        {"ficha": 9, "item": 1, "exercicio": "SUPINO RETO"},  # ficha que não existe
        {"ficha": 1, "item": 9, "exercicio": "SUPINO RETO"},  # item que não existe
    ],
)
def test_exercicio_que_mudou_ou_nao_existe_da_409(conn, onde):
    _salvar(conn)

    with pytest.raises(ComentarioInvalido) as erro:
        _comentar(conn, **onde)

    assert erro.value.status == 409
    assert _linhas(conn) == []


@pytest.mark.parametrize(
    "onde",
    [
        {"ficha": 1},
        {"item": 1},
        {"exercicio": "SUPINO RETO"},
        {"ficha": 1, "item": 1},
        {"ficha": 1, "exercicio": "SUPINO RETO"},
        {"ficha": 0, "item": 1, "exercicio": "SUPINO RETO"},
        {"ficha": 1, "item": 0, "exercicio": "SUPINO RETO"},
        {"ficha": "1", "item": 1, "exercicio": "SUPINO RETO"},
        {"ficha": True, "item": 1, "exercicio": "SUPINO RETO"},
        {"ficha": 1, "item": 1.0, "exercicio": "SUPINO RETO"},
        {"ficha": 1, "item": 1, "exercicio": ""},
        {"ficha": 1, "item": 1, "exercicio": 5},
    ],
)
def test_pedido_de_exercicio_pela_metade_ou_com_tipo_errado_da_400(conn, onde):
    _salvar(conn)

    with pytest.raises(ComentarioInvalido) as erro:
        _comentar(conn, **onde)

    assert erro.value.status == 400
    assert _linhas(conn) == []


def test_o_aluno_so_comenta_o_proprio_treino(conn):
    _salvar(conn, aluno_id=2, nome="TREINO DO BRUNO")  # a Ana não tem treino

    with pytest.raises(ComentarioInvalido) as erro:
        _comentar(conn, treino="TREINO DO BRUNO", aluno_id=1)

    assert erro.value.status == 409
    assert _linhas(conn) == []


# ------------------------------------------------------------------ repetição e limite por dia


def test_o_mesmo_texto_no_mesmo_lugar_em_2_minutos_nao_grava_de_novo(conn):
    _salvar(conn)

    primeiro = _comentar(conn, "Dói o ombro")
    segundo = _comentar(conn, "Dói o ombro", agora=AGORA + timedelta(seconds=30))

    assert primeiro == {"repetido": False} and segundo == {"repetido": True}
    assert len(_linhas(conn)) == 1


def test_ate_9_minutos_depois_o_mesmo_texto_ainda_e_repeticao(conn):
    # O aluno reenvia depois de a rede cair: o primeiro pedido pode ter chegado, então não grava duas vezes.
    _salvar(conn)

    _comentar(conn, "Dói o ombro")
    repetido = _comentar(conn, "Dói o ombro", agora=AGORA + timedelta(minutes=9))

    assert repetido == {"repetido": True} and len(_linhas(conn)) == 1


def test_depois_de_11_minutos_o_mesmo_texto_e_um_comentario_novo(conn):
    _salvar(conn)

    _comentar(conn, "Dói o ombro")
    _comentar(conn, "Dói o ombro", agora=AGORA + timedelta(minutes=11))

    assert len(_linhas(conn)) == 2


def test_o_mesmo_texto_em_outro_lugar_nao_e_repeticao(conn):
    _salvar(conn)

    _comentar(conn, "Dói")
    _comentar(conn, "Dói", ficha=1, item=1, exercicio="SUPINO RETO")
    _comentar(conn, "Dói", ficha=1, item=2, exercicio="CRUCIFIXO")

    assert len(_linhas(conn)) == 3


def test_o_mesmo_texto_de_outro_aluno_nao_e_repeticao(conn):
    _salvar(conn, aluno_id=1)
    _salvar(conn, aluno_id=2)

    _comentar(conn, "Dói")
    _comentar(conn, "Dói", aluno_id=2)

    assert len(_linhas(conn)) == 2


def test_limite_de_comentarios_por_dia(conn):
    _salvar(conn)
    for i in range(LIMITE_POR_DIA):
        _comentar(conn, f"comentário {i}")

    with pytest.raises(ComentarioInvalido) as erro:
        _comentar(conn, "um a mais")

    assert erro.value.status == 429
    assert len(_linhas(conn)) == LIMITE_POR_DIA


def test_o_limite_e_por_aluno_e_o_dia_e_o_de_brasilia(conn):
    _salvar(conn, aluno_id=1)
    _salvar(conn, aluno_id=2)
    antes_da_meia_noite = datetime(2026, 10, 15, 2, 59, tzinfo=timezone.utc)  # 23h59 de 14/10 em Brasília
    depois = antes_da_meia_noite + timedelta(minutes=1)  # 00h00 de 15/10
    for i in range(LIMITE_POR_DIA):
        _comentar(conn, f"comentário {i}", agora=antes_da_meia_noite)

    _comentar(conn, "outro aluno não é afetado", aluno_id=2, agora=antes_da_meia_noite)
    _comentar(conn, "meia-noite virou: dia novo", agora=depois)
    with pytest.raises(ComentarioInvalido):
        _comentar(conn, "ainda é o dia velho", agora=antes_da_meia_noite)

    assert len(_linhas(conn)) == LIMITE_POR_DIA + 2


def test_dois_envios_ao_mesmo_tempo_gravam_uma_vez_so(caminho):
    conn = conectar(caminho)
    _salvar(conn)
    conn.close()
    resultados, erros = [], []
    portao = threading.Barrier(2)

    def enviar():
        c = conectar(caminho)
        try:
            portao.wait()
            resultados.append(_comentar(c, "toque duplo"))
        except BaseException as erro:  # noqa: BLE001  (o teste quer ver qualquer falha)
            erros.append(erro)
        finally:
            c.close()

    fios = [threading.Thread(target=enviar) for _ in range(2)]
    for fio in fios:
        fio.start()
    for fio in fios:
        fio.join()

    assert erros == []
    assert sorted(r["repetido"] for r in resultados) == [False, True]
    conn = conectar(caminho)
    assert len(_linhas(conn)) == 1
    conn.close()


# ------------------------------------------------------------------ o comentário sobrevive às mudanças do treino


def test_trocar_o_treino_mantem_o_comentario_ligado_ao_treino_antigo(conn):
    antigo = _salvar(conn, nome="TREINO ANTIGO")
    _comentar(conn, "Estava pesado", treino="TREINO ANTIGO", ficha=1, item=1, exercicio="SUPINO RETO")
    novo = _salvar(conn, nome="TREINO NOVO")  # conclui o antigo

    _comentar(conn, "Este está bom", treino="TREINO NOVO")

    antigo_c, novo_c = _linhas(conn)
    assert (antigo_c["treino_id"], antigo_c["treino_nome"], antigo_c["exercicio_nome"]) == (antigo, "TREINO ANTIGO", "SUPINO RETO")
    assert (novo_c["treino_id"], novo_c["treino_nome"]) == (novo, "TREINO NOVO")


def test_editar_as_fichas_nao_estraga_o_comentario_de_exercicio(conn):
    treino_id = _salvar(conn)
    _comentar(conn, "Dói o ombro", ficha=1, item=1, exercicio="SUPINO RETO")

    # a edição (e a atualização do Data4U) apaga e recria as fichas e os itens: os ids mudam
    conn.execute("DELETE FROM ficha WHERE treino_id = ?", (treino_id,))
    conn.commit()

    (linha,) = _linhas(conn)
    assert linha["exercicio_nome"] == "SUPINO RETO" and linha["ficha_nome"] == "A PEITO" and linha["treino_id"] == treino_id


def test_treino_apagado_nao_leva_o_comentario_junto(conn):
    treino_id = _salvar(conn)
    _comentar(conn, "Dói o ombro")

    conn.execute("DELETE FROM treino WHERE id = ?", (treino_id,))
    conn.commit()

    (linha,) = _linhas(conn)
    assert linha["treino_id"] is None and linha["treino_nome"] == "TREINO ABC" and linha["texto"] == "Dói o ombro"


# ------------------------------------------------------------------ o professor lê


def test_listar_do_mais_novo_para_o_mais_antigo_com_data_de_brasilia(conn):
    _salvar(conn)
    _comentar(conn, "primeiro", agora=AGORA)
    _comentar(conn, "segundo", ficha=1, item=2, exercicio="CRUCIFIXO", agora=AGORA + timedelta(hours=2))

    resultado = listar(conn)

    assert resultado["total"] == 2 and resultado["nao_lidos"] == 2
    segundo, primeiro = resultado["comentarios"]
    assert segundo == {
        "id": 2,
        "aluno_id": 1,
        "aluno": "ANA SOUZA",
        "treino": "TREINO ABC",
        "ficha": "A PEITO",
        "exercicio": "CRUCIFIXO",
        "texto": "segundo",
        "quando": "15/10/2026 10:00",
        "lido": False,
        "resposta": None,
        "respondido_por": None,
        "respondido_quando": None,
        "resposta_vista": False,
    }
    assert primeiro["texto"] == "primeiro" and primeiro["quando"] == "15/10/2026 08:00"
    assert primeiro["ficha"] is None and primeiro["exercicio"] is None  # do treino inteiro


def test_listar_so_nao_lidos_ou_todos(conn):
    _salvar(conn)
    _comentar(conn, "um", agora=AGORA)
    _comentar(conn, "dois", agora=AGORA + timedelta(minutes=5))
    marcar_lido(conn, 1)

    assert [c["texto"] for c in listar(conn)["comentarios"]] == ["dois"]
    todos = listar(conn, so_nao_lidos=False)
    assert [c["texto"] for c in todos["comentarios"]] == ["dois", "um"]
    assert [c["lido"] for c in todos["comentarios"]] == [False, True]
    assert todos["nao_lidos"] == 1 and todos["total"] == 2


def test_listar_de_um_aluno_so_traz_os_dele(conn):
    _salvar(conn, aluno_id=1)
    _salvar(conn, aluno_id=2)
    _comentar(conn, "da Ana")
    _comentar(conn, "do Bruno", aluno_id=2)

    assert [c["texto"] for c in listar(conn, aluno_id=2)["comentarios"]] == ["do Bruno"]
    assert listar(conn, aluno_id=2)["total"] == 1
    assert listar(conn, aluno_id=2)["nao_lidos"] == 2  # o número do menu é de todos os alunos


def test_listar_respeita_o_limite_mas_o_total_diz_quantos_existem(conn):
    _salvar(conn)
    for i in range(5):
        _comentar(conn, f"comentário {i}", agora=AGORA + timedelta(minutes=i))

    resultado = listar(conn, limite=3)

    assert len(resultado["comentarios"]) == 3 and resultado["total"] == 5
    assert [c["texto"] for c in resultado["comentarios"]] == ["comentário 4", "comentário 3", "comentário 2"]
    assert len(listar(conn, limite=10_000)["comentarios"]) == 5  # e nunca passa do teto da lista


def test_marcar_lido_guarda_o_momento_e_repetir_nao_muda(conn):
    _salvar(conn)
    _comentar(conn)

    assert marcar_lido(conn, 1, agora=AGORA + timedelta(hours=1)) is True
    assert marcar_lido(conn, 1, agora=AGORA + timedelta(hours=5)) is True

    assert _linhas(conn)[0]["lido_em"] == "2026-10-15 12:00:00"
    assert contar_nao_lidos(conn) == 0


def test_marcar_lido_de_comentario_que_nao_existe_devolve_falso(conn):
    assert marcar_lido(conn, 999) is False


def test_marcar_lidos_do_aluno_so_mexe_nos_ids_pedidos_e_nos_dele(conn):
    _salvar(conn, aluno_id=1)
    _salvar(conn, aluno_id=2)
    _comentar(conn, "a1")
    _comentar(conn, "a2", agora=AGORA + timedelta(minutes=11))
    _comentar(conn, "b1", aluno_id=2)
    marcar_lido(conn, 1)

    # 1 já estava lido, 3 é do Bruno (id de outro aluno é ignorado): muda só o 2.
    assert marcar_lidos_do_aluno(conn, 1, [1, 2, 3]) == 1
    assert marcar_lidos_do_aluno(conn, 1, [1, 2, 3]) == 0
    assert contar_nao_lidos(conn) == 1  # o do Bruno continua


def test_marcar_lidos_nao_marca_o_que_chegou_depois_de_a_ficha_abrir(conn):
    # O professor abre a ficha (vê o comentário 1); o aluno manda o 2; o professor clica em "marcar todos".
    _salvar(conn)
    _comentar(conn, "primeiro")
    na_tela = [1]
    _comentar(conn, "chegou depois", agora=AGORA + timedelta(minutes=11))

    assert marcar_lidos_do_aluno(conn, 1, na_tela) == 1

    nao_lidos = [c["texto"] for c in listar(conn, so_nao_lidos=True)["comentarios"]]
    assert nao_lidos == ["chegou depois"]


@pytest.mark.parametrize(
    "ids",
    [None, [], "1", 1, [0], [-1], [True], [1.5], ["1"], [None], [2**63], list(range(1, LIMITE_DA_LISTA + 2)), {"1": 2}],
)
def test_marcar_lidos_com_lista_invalida_da_400(conn, ids):
    _salvar(conn)
    _comentar(conn, "oi")

    with pytest.raises(ComentarioInvalido) as erro:
        marcar_lidos_do_aluno(conn, 1, ids)

    assert erro.value.status == 400 and contar_nao_lidos(conn) == 1


# ------------------------------------------------------------------ a rota do celular do aluno


@pytest.fixture
def cliente_da_ana(caminho):
    """O celular da Ana, já logado (a sessão é criada direto, sem passar pelo código do WhatsApp)."""
    app = criar_app(caminho)
    conn = conectar(caminho)
    with conn:
        token = aluno_acesso._criar_sessao(conn, 1, datetime.now(timezone.utc))
    conn.close()
    cliente = app.test_client()
    cliente.set_cookie(aluno_acesso.NOME_DO_COOKIE, token)
    return cliente


def _enviar(cliente, corpo):
    return cliente.post("/api/aluno/comentario", json=corpo)


def _treino_abc(caminho):
    conn = conectar(caminho)
    _salvar(conn)
    conn.close()


def _comentarios_no_banco(caminho):
    conn = conectar(caminho)
    try:
        return _linhas(conn)
    finally:
        conn.close()


def test_sem_login_a_rota_do_comentario_responde_401(caminho):
    _treino_abc(caminho)
    cliente = criar_app(caminho).test_client()

    resposta = _enviar(cliente, {"treino": "TREINO ABC", "texto": "oi"})

    assert resposta.status_code == 401
    assert _comentarios_no_banco(caminho) == []


def test_com_login_o_comentario_e_gravado_para_a_ana(caminho, cliente_da_ana):
    _treino_abc(caminho)

    resposta = _enviar(cliente_da_ana, {"treino": "TREINO ABC", "texto": "Está leve demais"})

    assert resposta.status_code == 200 and resposta.get_json() == {"ok": True, "repetido": False}
    (linha,) = _comentarios_no_banco(caminho)
    assert linha["aluno_id"] == 1 and linha["texto"] == "Está leve demais"


def test_comentario_de_exercicio_pela_rota(caminho, cliente_da_ana):
    _treino_abc(caminho)

    resposta = _enviar(
        cliente_da_ana,
        {"treino": "TREINO ABC", "texto": "Dói o ombro", "ficha": 1, "item": 2, "exercicio": "CRUCIFIXO"},
    )

    assert resposta.status_code == 200
    (linha,) = _comentarios_no_banco(caminho)
    assert (linha["ficha_nome"], linha["exercicio_nome"]) == ("A PEITO", "CRUCIFIXO")


def test_o_aluno_vem_do_cookie_e_nao_do_corpo(caminho, cliente_da_ana):
    conn = conectar(caminho)
    _salvar(conn, aluno_id=1)
    _salvar(conn, aluno_id=2, nome="TREINO DO BRUNO")
    conn.close()

    _enviar(cliente_da_ana, {"treino": "TREINO ABC", "texto": "oi", "aluno_id": 2, "aluno": 2, "treino_id": 2})
    recusado = _enviar(cliente_da_ana, {"treino": "TREINO DO BRUNO", "texto": "no treino do outro"})

    assert recusado.status_code == 409
    (linha,) = _comentarios_no_banco(caminho)
    assert linha["aluno_id"] == 1 and linha["treino_nome"] == "TREINO ABC"


def test_toque_duplo_pela_rota_responde_repetido(caminho, cliente_da_ana):
    _treino_abc(caminho)
    corpo = {"treino": "TREINO ABC", "texto": "toque duplo"}

    primeiro, segundo = _enviar(cliente_da_ana, corpo), _enviar(cliente_da_ana, corpo)

    assert primeiro.get_json()["repetido"] is False and segundo.get_json()["repetido"] is True
    assert len(_comentarios_no_banco(caminho)) == 1


@pytest.mark.parametrize(
    ("corpo", "status"),
    [
        ({}, 400),  # sem texto
        ({"texto": "oi"}, 409),  # sem o nome do treino: o celular estava velho (ou o pedido não veio do celular)
        ({"treino": "TREINO ABC"}, 400),
        ({"treino": "TREINO ABC", "texto": ""}, 400),
        ({"treino": "TREINO ABC", "texto": "x" * 501}, 400),
        ({"treino": "TREINO ABC", "texto": "oi", "ficha": 1}, 400),
        ({"treino": "OUTRO", "texto": "oi"}, 409),
        ({"treino": "TREINO ABC", "texto": "oi", "ficha": 1, "item": 1, "exercicio": "CRUCIFIXO"}, 409),
    ],
)
def test_pedido_ruim_da_o_codigo_certo_e_nao_grava(caminho, cliente_da_ana, corpo, status):
    _treino_abc(caminho)

    resposta = _enviar(cliente_da_ana, corpo)

    assert resposta.status_code == status and "erro" in resposta.get_json()
    assert _comentarios_no_banco(caminho) == []


@pytest.mark.parametrize("corpo", [[], "texto", 7])
def test_corpo_que_nao_e_um_objeto_da_400(caminho, cliente_da_ana, corpo):
    _treino_abc(caminho)

    assert cliente_da_ana.post("/api/aluno/comentario", json=corpo).status_code == 400
    assert _comentarios_no_banco(caminho) == []


def test_sem_treino_ativo_a_rota_da_409(caminho, cliente_da_ana):
    assert _enviar(cliente_da_ana, {"treino": "TREINO ABC", "texto": "oi"}).status_code == 409


def test_20_por_dia_e_o_21_da_429(caminho, cliente_da_ana):
    _treino_abc(caminho)
    for i in range(LIMITE_POR_DIA):
        assert _enviar(cliente_da_ana, {"treino": "TREINO ABC", "texto": f"comentário {i}"}).status_code == 200

    resposta = _enviar(cliente_da_ana, {"treino": "TREINO ABC", "texto": "um a mais"})

    assert resposta.status_code == 429 and "erro" in resposta.get_json()
    assert len(_comentarios_no_banco(caminho)) == LIMITE_POR_DIA


def test_comentar_exige_json_e_origem_do_proprio_site(caminho, cliente_da_ana):
    _treino_abc(caminho)

    assert cliente_da_ana.post("/api/aluno/comentario", data="texto=oi").status_code == 415
    de_outro_site = cliente_da_ana.post(
        "/api/aluno/comentario",
        json={"treino": "TREINO ABC", "texto": "oi"},
        headers={"Origin": "https://site-malvado.example"},
    )
    assert de_outro_site.status_code == 403
    assert _comentarios_no_banco(caminho) == []


def test_a_resposta_da_rota_nao_devolve_ids_nem_dados_de_outros(caminho, cliente_da_ana):
    _treino_abc(caminho)

    texto = _enviar(cliente_da_ana, {"treino": "TREINO ABC", "texto": "oi"}).get_data(as_text=True)

    assert SEGREDO_DO_PROFESSOR not in texto and "aluno_id" not in texto and "treino_id" not in texto


def test_aluno_que_vira_provisorio_nao_comenta_mais(caminho, cliente_da_ana):
    _treino_abc(caminho)
    conn = conectar(caminho)
    with conn:
        conn.execute("UPDATE aluno SET provisorio = 1 WHERE id = 1")
    conn.close()

    assert _enviar(cliente_da_ana, {"treino": "TREINO ABC", "texto": "oi"}).status_code == 401
    assert _comentarios_no_banco(caminho) == []


def test_o_treino_do_aluno_traz_o_numero_de_cada_exercicio(caminho, cliente_da_ana):
    _treino_abc(caminho)

    treino = cliente_da_ana.get("/api/aluno/treino").get_json()["treino"]

    numeros = [[e["ordem"] for g in f["grupos"] for e in g["exercicios"]] for f in treino["fichas"]]
    assert numeros == [[1, 2], [1]]


# ------------------------------------------------------------------ as telas do professor


@pytest.fixture
def professor(caminho):
    """Um computador autorizado da academia."""
    conn = conectar(caminho)
    codigo = acesso.gerar_codigo(conn, "Computador dos professores").codigo
    conn.close()
    cliente = criar_app(caminho).test_client()
    assert cliente.post("/api/autorizar", json={"codigo": codigo}).status_code == 200
    return cliente


def _tres_comentarios(caminho):
    conn = conectar(caminho)
    _salvar(conn, aluno_id=1)
    _salvar(conn, aluno_id=2, nome="TREINO DO BRUNO")
    _comentar(conn, "Está leve demais", agora=AGORA)
    _comentar(conn, "Dói o ombro", ficha=1, item=1, exercicio="SUPINO RETO", agora=AGORA + timedelta(minutes=5))
    _comentar(conn, "<b>Bruno</b> não gostou", treino="TREINO DO BRUNO", aluno_id=2, agora=AGORA + timedelta(minutes=9))
    conn.close()


def test_so_computador_autorizado_ve_os_comentarios(caminho, cliente_da_ana):
    _tres_comentarios(caminho)
    sem_autorizacao = criar_app(caminho).test_client()

    assert sem_autorizacao.get("/comentarios").status_code == 302
    assert "/autorizar" in sem_autorizacao.get("/comentarios").headers["Location"]
    assert sem_autorizacao.post("/api/comentarios/1/lido").status_code == 401
    assert sem_autorizacao.post("/api/alunos/1/comentarios/lidos").status_code == 401
    # o cookie do ALUNO não abre a área do professor
    assert cliente_da_ana.get("/comentarios").status_code == 302
    assert cliente_da_ana.post("/api/comentarios/1/lido").status_code == 401
    assert contar_nao_lidos(conectar(caminho)) == 3


def test_a_tela_lista_os_comentarios_novos_com_quem_onde_e_quando(caminho, professor):
    _tres_comentarios(caminho)

    html = professor.get("/comentarios").get_data(as_text=True)

    assert "Está leve demais" in html and "Dói o ombro" in html
    assert "ANA SOUZA" in html and "BRUNO LIMA" in html
    assert "SUPINO RETO" in html and "A PEITO" in html and "TREINO ABC" in html
    assert "15/10/2026 08:00" in html
    assert 'href="/alunos/1"' in html and 'href="/alunos/2"' in html
    # o mais novo vem primeiro
    assert html.index("Bruno") < html.index("Dói o ombro") < html.index("Está leve demais")


def test_o_texto_do_aluno_nunca_vira_html_na_tela_do_professor(caminho, professor):
    _tres_comentarios(caminho)

    html = professor.get("/comentarios").get_data(as_text=True)

    assert "<b>Bruno</b>" not in html
    assert "&lt;b&gt;Bruno&lt;/b&gt;" in html


def test_o_menu_mostra_quantos_comentarios_estao_sem_ler(caminho, professor):
    _tres_comentarios(caminho)

    html = professor.get("/alunos").get_data(as_text=True)

    assert 'href="/comentarios"' in html and "Comentários" in html
    assert 'data-comentarios-novos="3"' in html


def test_sem_nenhum_comentario_nao_aparece_contador_e_a_tela_explica(caminho, professor):
    html_menu = professor.get("/alunos").get_data(as_text=True)
    html = professor.get("/comentarios").get_data(as_text=True)

    assert "Comentários" in html_menu and "data-comentarios-novos" not in html_menu
    assert "Nenhum comentário novo" in html


def test_a_tela_so_mostra_os_novos_e_com_todos_mostra_tambem_os_lidos(caminho, professor):
    _tres_comentarios(caminho)
    assert professor.post("/api/comentarios/1/lido").status_code == 200

    novos = professor.get("/comentarios").get_data(as_text=True)
    todos = professor.get("/comentarios?todos=1").get_data(as_text=True)

    assert "Está leve demais" not in novos and "Dói o ombro" in novos
    assert "Está leve demais" in todos and "Dói o ombro" in todos


def test_marcar_como_lido_pela_rota(caminho, professor):
    _tres_comentarios(caminho)

    resposta = professor.post("/api/comentarios/2/lido")

    assert resposta.status_code == 200 and resposta.get_json() == {"ok": True, "nao_lidos": 2}
    assert professor.post("/api/comentarios/2/lido").get_json() == {"ok": True, "nao_lidos": 2}  # repetir não faz mal
    assert professor.post("/api/comentarios/999/lido").status_code == 404


def test_marcar_todos_de_um_aluno_pela_rota(caminho, professor):
    _tres_comentarios(caminho)

    resposta = professor.post("/api/alunos/1/comentarios/lidos", json={"ids": [1, 2]})

    assert resposta.status_code == 200 and resposta.get_json() == {"ok": True, "marcados": 2, "nao_lidos": 1}
    assert professor.post("/api/alunos/999/comentarios/lidos", json={"ids": [1]}).status_code == 404


def test_marcar_todos_pela_rota_so_marca_os_ids_que_o_professor_viu(caminho, professor):
    _tres_comentarios(caminho)

    resposta = professor.post("/api/alunos/1/comentarios/lidos", json={"ids": [1]})

    assert resposta.get_json() == {"ok": True, "marcados": 1, "nao_lidos": 2}
    # o id 3 é do Bruno: pedir pela ficha da Ana não marca nada dele
    assert professor.post("/api/alunos/1/comentarios/lidos", json={"ids": [3]}).get_json()["marcados"] == 0
    assert contar_nao_lidos(conectar(caminho)) == 2


@pytest.mark.parametrize("corpo", [{}, {"ids": []}, {"ids": "1"}, {"ids": [True]}, {"ids": [2**63]}, [1, 2], "x", 5])
def test_marcar_todos_pela_rota_com_corpo_invalido_da_400(caminho, professor, corpo):
    _tres_comentarios(caminho)

    resposta = professor.post("/api/alunos/1/comentarios/lidos", json=corpo)

    assert resposta.status_code == 400 and contar_nao_lidos(conectar(caminho)) == 3


def test_marcar_todos_pela_rota_exige_json(caminho, professor):
    _tres_comentarios(caminho)

    assert professor.post("/api/alunos/1/comentarios/lidos").status_code == 415


@pytest.mark.parametrize("numero", [2**63, 99999999999999999999])
def test_id_gigante_nas_rotas_do_professor_da_404_e_nao_500(caminho, professor, numero):
    _tres_comentarios(caminho)

    assert professor.post(f"/api/comentarios/{numero}/lido").status_code == 404
    assert professor.post(f"/api/alunos/{numero}/comentarios/lidos", json={"ids": [1]}).status_code == 404


def test_marcar_como_lido_exige_origem_do_proprio_site(caminho, professor):
    _tres_comentarios(caminho)

    de_outro_site = professor.post("/api/comentarios/1/lido", headers={"Origin": "https://site-malvado.example"})

    assert de_outro_site.status_code == 403
    assert contar_nao_lidos(conectar(caminho)) == 3


def test_a_ficha_do_aluno_mostra_os_comentarios_dele_e_so_os_dele(caminho, professor):
    _tres_comentarios(caminho)

    html = professor.get("/alunos/1").get_data(as_text=True)

    assert "Comentários do aluno" in html
    assert "Está leve demais" in html and "Dói o ombro" in html
    assert "Bruno" not in html.replace("BRUNO", "")  # o comentário do Bruno não aparece na ficha da Ana
    assert "<b>" not in html.split("Comentários do aluno", 1)[1].split("</section>", 1)[0]


def test_a_ficha_sem_comentarios_nao_tem_a_secao(caminho, professor):
    conn = conectar(caminho)
    _salvar(conn)
    conn.close()

    assert "Comentários do aluno" not in professor.get("/alunos/1").get_data(as_text=True)


def test_a_ficha_destaca_so_os_novos(caminho, professor):
    _tres_comentarios(caminho)
    professor.post("/api/comentarios/1/lido")

    html = professor.get("/alunos/1").get_data(as_text=True)

    assert html.count('data-comentario-novo="1"') == 1
    assert "Marcar todos como lidos" in html


# ------------------------------------------------------------------ o banco segue as mesmas regras de sempre


def test_o_texto_de_501_letras_nem_o_banco_aceita(caminho):
    conn = conectar(caminho)
    _salvar(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO comentario (aluno_id, treino_nome, texto, criado_em) VALUES (1, 'T', ?, '2026-10-15 11:00:00')",
            ("x" * 501,),
        )
    conn.close()


def test_o_modulo_exporta_os_limites_que_o_celular_usa():
    assert comentarios.LIMITE_DO_TEXTO == 500 and comentarios.LIMITE_POR_DIA == 20


# ------------------------------------------------------------------ a ficha com muitos comentários


def _muitos_comentarios(caminho, quantos):
    conn = conectar(caminho)
    _salvar(conn)
    with conn:  # direto no banco: passa do limite de 20 por dia, que só vale para o celular do aluno
        for n in range(quantos):
            conn.execute(
                "INSERT INTO comentario (aluno_id, treino_id, treino_nome, texto, criado_em) VALUES (1, 1, 'TREINO ABC', ?, ?)",
                (f"comentario {n}", momento_para_texto(AGORA + timedelta(minutes=n))),
            )
    conn.close()


def test_a_ficha_com_mais_de_30_comentarios_avisa_que_mostra_so_os_mais_novos(caminho, professor):
    _muitos_comentarios(caminho, 35)

    html = professor.get("/alunos/1").get_data(as_text=True)

    assert "Mostrando só os 30 comentários mais novos" in html
    assert html.count('data-comentario-novo="1"') == 30
    assert "comentario 34" in html and "comentario 4<" not in html  # os 5 mais antigos ficam de fora
    assert "35 sem ler · 35 no total" in html


def test_a_ficha_com_poucos_comentarios_nao_tem_o_aviso(caminho, professor):
    _tres_comentarios(caminho)

    html = professor.get("/alunos/1").get_data(as_text=True)

    assert "Mostrando só os" not in html
    assert "Marcar todos como lidos" in html


def test_o_botao_da_ficha_diz_que_vale_so_para_os_da_tela_quando_ha_mais_sem_ler(caminho, professor):
    _muitos_comentarios(caminho, 35)

    html = professor.get("/alunos/1").get_data(as_text=True)

    assert "Marcar os da tela como lidos" in html and "Marcar todos como lidos" not in html


def test_a_ficha_sem_nenhum_sem_ler_na_tela_nao_tem_o_botao(caminho, professor):
    # 35 comentários, os 30 mais novos já lidos e os 5 antigos sem ler (só aparecem na tela "Comentários").
    _muitos_comentarios(caminho, 35)
    conn = conectar(caminho)
    with conn:
        conn.execute("UPDATE comentario SET lido_em = criado_em WHERE id > 5")
    conn.close()

    html = professor.get("/alunos/1").get_data(as_text=True)

    assert "data-marcar-todos-do-aluno" not in html
    assert "5 sem ler · 35 no total" in html
