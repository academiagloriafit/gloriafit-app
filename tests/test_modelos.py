"""Treinos padrão e cópia de treinos (app/modelos.py). Dados inventados."""

import json
import sqlite3

import pytest

from app import modelos
from app.db import conectar, criar_tabelas
from app.treinos import AlunoNaoEncontrado, TreinoInvalido, obter_treino, salvar_treino


@pytest.fixture
def conn():
    c = conectar()
    criar_tabelas(c)
    yield c
    c.close()


@pytest.fixture
def exercicios(conn):
    """Quatro ativos e um desativado. Devolve {'a','b','c','d','off'} -> id."""
    ids = {}
    for chave, nome, ativo in [
        ("a", "(15) CADEIRA ABDUTORA", 1),
        ("b", "REMADA CURVADA", 1),
        ("c", "AGACHAMENTO", 1),
        ("d", "ELÍPTICO", 1),
        ("off", "EXERCICIO DESATIVADO", 0),
    ]:
        ids[chave] = conn.execute("INSERT INTO exercicio (nome, origem, ativo) VALUES (?, 'app', ?)", (nome, ativo)).lastrowid
    return ids


@pytest.fixture
def alunos(conn):
    conn.execute("INSERT INTO aluno (id, nome) VALUES (1, 'ANA FICTICIA'), (2, 'BRUNO FICTICIO')")


def _item(exercicio_id, series="3", repeticoes="12", carga="", bloco=None, **extras):
    return {"exercicio_id": exercicio_id, "series": series, "repeticoes": repeticoes, "carga": carga, "bloco": bloco, **extras}


def _ficha(itens, nome="FICHA A"):
    return {"nome": nome, "itens": itens}


def _pedido_de_modelo(fichas, nome="BÁSICO 1", montado_por="Ana Paula", **extras):
    return {"nome": nome, "montado_por": montado_por, "fichas": fichas, **extras}


def _problemas(conn, dados, status=400):
    with pytest.raises(TreinoInvalido) as erro:
        modelos.criar_modelo(conn, dados)
    assert erro.value.status == status
    return erro.value.problemas


def _treino_do_aluno(conn, aluno_id, fichas, nome="TREINO ABC", **extras):
    return salvar_treino(conn, aluno_id, {"nome_treino": nome, "montado_por": "Bia", "fichas": fichas, **extras})


# ------------------------------------------------------------------ criar_modelo


def test_cria_modelo_e_guarda_o_conteudo_conferido(conn, exercicios):
    pedido = _pedido_de_modelo(
        [
            _ficha([_item(exercicios["a"], "4", "10", "30", pausa=90, observacao="  devagar   no fim "), _item(exercicios["b"])]),
            _ficha([_item(exercicios["c"])], "FICHA B"),
        ],
        sessoes_por_ficha=15,
    )

    modelo_id = modelos.criar_modelo(conn, pedido)

    linha = conn.execute("SELECT nome, montado_por, sessoes_por_ficha, conteudo FROM modelo_treino WHERE id = ?", (modelo_id,)).fetchone()
    assert (linha["nome"], linha["montado_por"], linha["sessoes_por_ficha"]) == ("BÁSICO 1", "Ana Paula", 15)
    fichas = json.loads(linha["conteudo"])["fichas"]
    assert [f["nome"] for f in fichas] == ["FICHA A", "FICHA B"]
    assert fichas[0]["itens"][0] == {
        "exercicio_id": exercicios["a"], "series": "4", "repeticoes": "10", "carga": "30",
        "pausa": 90, "observacao": "devagar no fim", "bloco": None,
    }
    assert fichas[0]["itens"][1]["carga"] is None  # em branco vira vazio, como nos treinos
    assert "posicao" not in fichas[0]["itens"][0]  # nada de campo interno do validador


def test_modelo_sem_meta_guarda_vazio(conn, exercicios):
    modelo_id = modelos.criar_modelo(conn, _pedido_de_modelo([_ficha([_item(exercicios["a"])])]))

    assert conn.execute("SELECT sessoes_por_ficha FROM modelo_treino WHERE id = ?", (modelo_id,)).fetchone()[0] is None


def test_series_e_repeticoes_podem_ficar_em_branco_no_modelo(conn, exercicios):
    # cardio: o professor escreve o tempo depois (mesma regra do treino de verdade)
    modelo_id = modelos.criar_modelo(conn, _pedido_de_modelo([_ficha([_item(exercicios["d"], "", "")])]))

    assert modelos.modelo_para_montar(conn, modelo_id)["fichas"][0]["itens"][0]["series"] == ""


def test_bi_set_e_renumerado_no_modelo(conn, exercicios):
    itens = [_item(exercicios["a"], bloco=7), _item(exercicios["b"], bloco=7), _item(exercicios["c"])]

    modelo_id = modelos.criar_modelo(conn, _pedido_de_modelo([_ficha(itens)]))

    guardado = json.loads(conn.execute("SELECT conteudo FROM modelo_treino WHERE id = ?", (modelo_id,)).fetchone()[0])
    assert [i["bloco"] for i in guardado["fichas"][0]["itens"]] == [1, 1, None]


@pytest.mark.parametrize(
    "mudanca, trecho",
    [
        ({"nome": ""}, "nome do treino padrão é obrigatório"),
        ({"nome": "X" * 41}, "máximo é 40"),
        ({"nome": None}, "precisa ser um texto"),
        ({"montado_por": ""}, "quem montou é obrigatório"),
        ({"montado_por": "Y" * 61}, "máximo é 60"),
        ({"sessoes_por_ficha": 0}, "Treinos por ficha"),
        ({"sessoes_por_ficha": 1000}, "Treinos por ficha"),
        ({"sessoes_por_ficha": "15"}, "Treinos por ficha"),
        ({"sessoes_por_ficha": True}, "Treinos por ficha"),
        ({"fichas": []}, "de 1 a 26 fichas"),
        ({"fichas": "A"}, "de 1 a 26 fichas"),
        ({"fichas": [_ficha([])]}, "adicione pelo menos um exercício"),
    ],
)
def test_modelo_invalido_e_recusado_e_nada_e_gravado(conn, exercicios, mudanca, trecho):
    base = _pedido_de_modelo([_ficha([_item(exercicios["a"])])])

    problemas = _problemas(conn, {**base, **mudanca})

    assert any(trecho in p for p in problemas), problemas
    assert conn.execute("SELECT COUNT(*) FROM modelo_treino").fetchone()[0] == 0


@pytest.mark.parametrize("dados", [None, [], "texto", 7])
def test_modelo_que_nao_e_um_objeto_e_recusado(conn, dados):
    assert _problemas(conn, dados) == ["Formato do pedido inválido."]


def test_modelo_com_exercicio_desativado_ou_que_nao_existe_e_recusado(conn, exercicios):
    for exercicio_id in (exercicios["off"], 99999):
        problemas = _problemas(conn, _pedido_de_modelo([_ficha([_item(exercicio_id)])]))
        assert "não existe ou foi desativado" in problemas[0]


def test_modelo_com_campo_acima_do_limite_e_recusado(conn, exercicios):
    problemas = _problemas(conn, _pedido_de_modelo([_ficha([_item(exercicios["a"], series="1" * 12)])]))

    assert "séries" in problemas[0]


def test_modelo_com_bi_set_de_um_exercicio_e_recusado(conn, exercicios):
    problemas = _problemas(conn, _pedido_de_modelo([_ficha([_item(exercicios["a"], bloco=1), _item(exercicios["b"])])]))

    assert "bi-set tem 2" in problemas[0]


def test_nome_repetido_e_recusado_sem_diferenciar_maiuscula_nem_acento(conn, exercicios):
    modelos.criar_modelo(conn, _pedido_de_modelo([_ficha([_item(exercicios["a"])])], nome="Básico Iniciante"))

    problemas = _problemas(
        conn, _pedido_de_modelo([_ficha([_item(exercicios["b"])])], nome="BASICO INICIANTE"), status=409
    )

    assert "Já existe um treino padrão" in problemas[0]
    assert conn.execute("SELECT COUNT(*) FROM modelo_treino").fetchone()[0] == 1


def test_o_banco_tambem_barra_nome_repetido(conn):
    conn.execute("INSERT INTO modelo_treino (nome, montado_por, conteudo) VALUES ('X', 'A', '{}')")

    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        conn.execute("INSERT INTO modelo_treino (nome, montado_por, conteudo) VALUES ('x', 'A', '{}')")


def test_dois_salvar_ao_mesmo_tempo_com_o_mesmo_nome_viram_409(conn, exercicios, monkeypatch):
    # Simula a corrida: a conferência não vê o nome (outro processo ainda não gravou), mas o índice do banco barra.
    pedido = _pedido_de_modelo([_ficha([_item(exercicios["a"])])])
    modelos.criar_modelo(conn, pedido)
    monkeypatch.setattr(modelos, "normalizar", lambda texto: object())  # a conferência em Python "não acha" nada

    with pytest.raises(TreinoInvalido) as erro:
        modelos.criar_modelo(conn, pedido)

    assert erro.value.status == 409
    assert conn.execute("SELECT COUNT(*) FROM modelo_treino").fetchone()[0] == 1


# ------------------------------------------------------------------ listar, ler e excluir


def test_lista_em_ordem_alfabetica_com_resumo(conn, exercicios):
    um = [_ficha([_item(exercicios["a"]), _item(exercicios["b"])]), _ficha([_item(exercicios["c"])], "FICHA B")]
    modelos.criar_modelo(conn, _pedido_de_modelo(um, nome="intermediário", sessoes_por_ficha=12))
    modelos.criar_modelo(conn, _pedido_de_modelo([_ficha([_item(exercicios["a"])])], nome="Básico"))

    lista = modelos.listar_modelos(conn)

    assert [m["nome"] for m in lista] == ["Básico", "intermediário"]
    assert lista[1]["resumo"] == "2 fichas · 3 exercícios"
    assert lista[0]["resumo"] == "1 ficha · 1 exercício"
    assert (lista[1]["fichas"], lista[1]["exercicios"], lista[1]["sessoes_por_ficha"]) == (2, 3, 12)
    assert lista[1]["montado_por"] == "Ana Paula"
    assert lista[1]["criado_em"]  # data de hoje, em dia/mês/ano


def test_lista_vazia(conn):
    assert modelos.listar_modelos(conn) == []


def test_modelo_para_montar_traz_nomes_sem_numero_da_maquina_e_textos_vazios(conn, exercicios):
    itens = [_item(exercicios["a"], "3", "12", "20", pausa=90, observacao="devagar"), _item(exercicios["d"], "", "")]
    modelo_id = modelos.criar_modelo(conn, _pedido_de_modelo([_ficha(itens)], sessoes_por_ficha=15))

    montar = modelos.modelo_para_montar(conn, modelo_id)

    assert montar["nome"] == "BÁSICO 1"
    assert montar["sessoes_por_ficha"] == 15
    assert montar["indisponiveis"] == 0
    primeiro, segundo = montar["fichas"][0]["itens"]
    assert primeiro == {
        "exercicio_id": exercicios["a"], "nome": "CADEIRA ABDUTORA", "series": "3", "repeticoes": "12", "carga": "20",
        "pausa": 90, "observacao": "devagar", "bloco": None, "indisponivel": False,
    }
    assert (segundo["nome"], segundo["series"], segundo["pausa"], segundo["observacao"]) == ("ELÍPTICO", "", None, "")


def test_exercicio_desativado_depois_vem_marcado_como_indisponivel(conn, exercicios):
    itens = [_item(exercicios["a"]), _item(exercicios["b"])]
    modelo_id = modelos.criar_modelo(conn, _pedido_de_modelo([_ficha(itens)]))
    conn.execute("UPDATE exercicio SET ativo = 0 WHERE id = ?", (exercicios["b"],))

    montar = modelos.modelo_para_montar(conn, modelo_id)

    assert [i["indisponivel"] for i in montar["fichas"][0]["itens"]] == [False, True]
    assert montar["indisponiveis"] == 1


def test_exercicio_que_sumiu_do_banco_nao_quebra_a_leitura(conn, exercicios):
    modelo_id = modelos.criar_modelo(conn, _pedido_de_modelo([_ficha([_item(exercicios["a"])])]))
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DELETE FROM exercicio WHERE id = ?", (exercicios["a"],))

    item = modelos.modelo_para_montar(conn, modelo_id)["fichas"][0]["itens"][0]

    assert (item["nome"], item["indisponivel"]) == (modelos.NOME_DO_EXERCICIO_SUMIDO, True)


def test_modelo_que_nao_existe(conn):
    assert modelos.modelo_para_montar(conn, 99) is None


def test_exclui_modelo_e_nao_mexe_nos_treinos_ja_copiados(conn, exercicios, alunos):
    fichas = [_ficha([_item(exercicios["a"])])]
    modelo_id = modelos.criar_modelo(conn, _pedido_de_modelo(fichas))
    treino_id = _treino_do_aluno(conn, 1, fichas)

    modelos.excluir_modelo(conn, modelo_id)

    assert modelos.listar_modelos(conn) == []
    assert obter_treino(conn, treino_id)["fichas"][0]["itens"][0]["exercicio"] == "CADEIRA ABDUTORA"
    with pytest.raises(modelos.ModeloNaoEncontrado):
        modelos.excluir_modelo(conn, modelo_id)


# ------------------------------------------------------------------ treino de outro aluno


def test_lista_os_treinos_do_aluno_o_ativo_primeiro(conn, exercicios, alunos):
    fichas = [_ficha([_item(exercicios["a"]), _item(exercicios["b"])]), _ficha([_item(exercicios["c"])], "FICHA B")]
    antigo = _treino_do_aluno(conn, 1, fichas, "TREINO ANTIGO")
    novo = _treino_do_aluno(conn, 1, fichas[:1], "TREINO NOVO")  # o antigo vira inativo

    lista = modelos.listar_treinos_do_aluno(conn, 1)

    assert [t["id"] for t in lista] == [novo, antigo]
    assert [t["ativo"] for t in lista] == [True, False]
    assert lista[0]["resumo"] == "1 ficha · 2 exercícios"
    assert lista[1]["resumo"] == "2 fichas · 3 exercícios"
    assert lista[0]["inicio"]  # dia/mês/ano
    assert lista[0]["do_data4u"] is False


def test_treino_sem_exercicio_nao_aparece_para_copiar(conn, exercicios, alunos):
    conn.execute("INSERT INTO treino (id, aluno_id, nome, montado_por, ativo) VALUES (50, 1, 'VAZIO', 'X', 0)")
    conn.execute("INSERT INTO ficha (treino_id, nome, ordem) VALUES (50, 'A', 1)")

    assert modelos.listar_treinos_do_aluno(conn, 1) == []


def test_aluno_sem_treino_e_aluno_que_nao_existe(conn, alunos):
    assert modelos.listar_treinos_do_aluno(conn, 2) == []
    with pytest.raises(AlunoNaoEncontrado):
        modelos.listar_treinos_do_aluno(conn, 99)


def test_treino_para_montar_copia_dose_pausa_observacao_meta_e_bi_set(conn, exercicios, alunos):
    itens = [
        _item(exercicios["a"], "4", "10", "30", bloco=1, pausa=60, observacao="obs"),
        _item(exercicios["b"], "4", "10", bloco=1),
        _item(exercicios["c"], "", ""),
    ]
    treino_id = _treino_do_aluno(conn, 1, [_ficha(itens)], sessoes_por_ficha=15)

    montar = modelos.treino_para_montar(conn, treino_id)

    assert (montar["nome"], montar["sessoes_por_ficha"], montar["indisponiveis"]) == ("TREINO ABC", 15, 0)
    linhas = montar["fichas"][0]["itens"]
    assert [(i["nome"], i["bloco"]) for i in linhas] == [("CADEIRA ABDUTORA", 1), ("REMADA CURVADA", 1), ("AGACHAMENTO", None)]
    assert (linhas[0]["series"], linhas[0]["carga"], linhas[0]["pausa"], linhas[0]["observacao"]) == ("4", "30", 60, "obs")
    assert (linhas[2]["series"], linhas[2]["repeticoes"], linhas[2]["pausa"]) == ("", "", None)


def test_treino_antigo_com_exercicio_fora_da_lista_vem_marcado(conn, exercicios, alunos):
    conn.execute("INSERT INTO treino (id, aluno_id, nome, montado_por, ativo, origem, data4u_id) VALUES (7, 1, 'DO DATA4U', 'X', 0, 'data4u', 70)")
    conn.execute("INSERT INTO ficha (id, treino_id, nome, ordem) VALUES (7, 7, 'A', 1)")
    for ordem, chave in enumerate(("a", "off"), start=1):
        conn.execute("INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, series) VALUES (7, ?, ?, '3')", (ordem, exercicios[chave]))

    montar = modelos.treino_para_montar(conn, 7)

    assert montar["indisponiveis"] == 1
    assert [i["indisponivel"] for i in montar["fichas"][0]["itens"]] == [False, True]
    assert modelos.listar_treinos_do_aluno(conn, 1)[0]["do_data4u"] is True


def test_treino_que_nao_existe_para_montar(conn):
    assert modelos.treino_para_montar(conn, 99) is None


@pytest.mark.parametrize(
    "blocos, esperado",
    [
        ([1, 1, None], [1, 1, None]),
        ([5, 5, 9, 9, 9], [1, 1, 2, 2, 2]),  # renumera na ordem
        ([1, None, None], [None, None, None]),  # bi-set de um só: vira sozinho
        ([1, 1, 1, 1], [None, None, None, None]),  # bloco de 4: não existe
        ([1, 1, None, 1, 1], [1, 1, None, 2, 2]),  # o mesmo número em dois lugares: dois blocos
        ([None, None], [None, None]),
        ([], []),
    ],
)
def test_normalizar_blocos_do_historico(blocos, esperado):
    itens = [{"bloco": b} for b in blocos]

    modelos.normalizar_blocos(itens)

    assert [i["bloco"] for i in itens] == esperado


def test_treino_do_historico_com_blocos_fora_do_molde_chega_arrumado(conn, exercicios, alunos):
    conn.execute("INSERT INTO treino (id, aluno_id, nome, montado_por, ativo, origem, data4u_id) VALUES (7, 1, 'DO DATA4U', 'X', 0, 'data4u', 70)")
    conn.execute("INSERT INTO ficha (id, treino_id, nome, ordem) VALUES (7, 7, 'A', 1)")
    for ordem, (chave, bloco) in enumerate((("a", 3), ("b", None), ("c", 4)), start=1):
        conn.execute(
            "INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, bloco) VALUES (7, ?, ?, ?)", (ordem, exercicios[chave], bloco)
        )

    montar = modelos.treino_para_montar(conn, 7)

    assert [i["bloco"] for i in montar["fichas"][0]["itens"]] == [None, None, None]  # blocos de 1 só não valem


# ------------------------------------------------------------------ salvar como treino padrão (a partir de um treino)


def test_treino_vira_padrao_com_professor_e_meta_do_original(conn, exercicios, alunos):
    itens = [_item(exercicios["a"], "4", "10", "30", bloco=1, pausa=60), _item(exercicios["b"], bloco=1), _item(exercicios["c"])]
    treino_id = _treino_do_aluno(conn, 1, [_ficha(itens)], sessoes_por_ficha=15)

    modelo_id = modelos.criar_modelo_do_treino(conn, treino_id, "  Básico   do João ")

    linha = conn.execute("SELECT nome, montado_por, sessoes_por_ficha FROM modelo_treino WHERE id = ?", (modelo_id,)).fetchone()
    assert tuple(linha) == ("Básico do João", "Bia", 15)
    copiado = modelos.modelo_para_montar(conn, modelo_id)["fichas"][0]["itens"]
    assert [(i["nome"], i["series"], i["bloco"]) for i in copiado] == [
        ("CADEIRA ABDUTORA", "4", 1), ("REMADA CURVADA", "3", 1), ("AGACHAMENTO", "3", None),
    ]
    assert copiado[0]["pausa"] == 60


def test_treino_com_exercicio_fora_da_lista_nao_vira_padrao_e_o_aviso_diz_quais(conn, exercicios, alunos):
    conn.execute("INSERT INTO treino (id, aluno_id, nome, montado_por, ativo, origem, data4u_id) VALUES (7, 1, 'DO DATA4U', 'X', 0, 'data4u', 70)")
    conn.execute("INSERT INTO ficha (id, treino_id, nome, ordem) VALUES (7, 7, 'A', 1)")
    for ordem, chave in enumerate(("a", "off"), start=1):
        conn.execute("INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, series) VALUES (7, ?, ?, '3')", (ordem, exercicios[chave]))

    with pytest.raises(TreinoInvalido) as erro:
        modelos.criar_modelo_do_treino(conn, 7, "TESTE")

    assert "EXERCICIO DESATIVADO" in erro.value.problemas[0]
    assert conn.execute("SELECT COUNT(*) FROM modelo_treino").fetchone()[0] == 0


def test_treino_do_historico_com_bloco_de_um_so_exercicio_vira_padrao_assim_mesmo(conn, exercicios, alunos):
    conn.execute("INSERT INTO treino (id, aluno_id, nome, montado_por, ativo, origem, data4u_id) VALUES (7, 1, 'DO DATA4U', 'X', 0, 'data4u', 70)")
    conn.execute("INSERT INTO ficha (id, treino_id, nome, ordem) VALUES (7, 7, 'A', 1)")
    for ordem, (chave, bloco) in enumerate((("a", 1), ("b", None)), start=1):
        conn.execute(
            "INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, series, bloco) VALUES (7, ?, ?, '3', ?)",
            (ordem, exercicios[chave], bloco),
        )

    modelo_id = modelos.criar_modelo_do_treino(conn, 7, "TESTE")  # sem a arrumação, o servidor recusaria o "bi-set" de 1

    assert [i["bloco"] for i in modelos.modelo_para_montar(conn, modelo_id)["fichas"][0]["itens"]] == [None, None]


def test_nome_vazio_ou_repetido_ao_salvar_treino_como_padrao(conn, exercicios, alunos):
    treino_id = _treino_do_aluno(conn, 1, [_ficha([_item(exercicios["a"])])])
    modelos.criar_modelo_do_treino(conn, treino_id, "BÁSICO")

    for nome, status in (("", 400), (None, 400), ("básico", 409)):
        with pytest.raises(TreinoInvalido) as erro:
            modelos.criar_modelo_do_treino(conn, treino_id, nome)
        assert erro.value.status == status


def test_treino_que_nao_existe_nao_vira_padrao(conn):
    with pytest.raises(modelos.TreinoNaoEncontrado):
        modelos.criar_modelo_do_treino(conn, 99, "X")


# ------------------------------------------------------------------ o que sai daqui volta a ser um treino aceito


def test_treino_copiado_de_um_padrao_e_aceito_pelo_servidor_ao_salvar(conn, exercicios, alunos):
    """O formato de `para_montar` tem tudo que o salvar precisa: o que a tela devolver sem mexer é aceito."""
    itens = [
        _item(exercicios["a"], "4", "10", "30", bloco=1, pausa=90, observacao="obs"),
        _item(exercicios["b"], bloco=1),
        _item(exercicios["d"], "", ""),
    ]
    modelo_id = modelos.criar_modelo(conn, _pedido_de_modelo([_ficha(itens)], sessoes_por_ficha=15))
    montar = modelos.modelo_para_montar(conn, modelo_id)

    pedido = {
        "nome_treino": "TREINO COPIADO",
        "montado_por": "Bia",
        "sessoes_por_ficha": montar["sessoes_por_ficha"],
        "fichas": [
            {"nome": f["nome"], "itens": [{k: i[k] for k in ("exercicio_id", "series", "repeticoes", "carga", "pausa", "observacao", "bloco")} for i in f["itens"]]}
            for f in montar["fichas"]
        ],
    }
    treino_id = salvar_treino(conn, 2, pedido)

    copiado = obter_treino(conn, treino_id)
    assert [(i["exercicio"], i["series"], i["bloco"], i["pausa"]) for i in copiado["fichas"][0]["itens"]] == [
        ("CADEIRA ABDUTORA", "4", 1, 90), ("REMADA CURVADA", "3", 1, None), ("ELÍPTICO", None, None, None),
    ]
    assert copiado["sessoes_por_ficha"] == 15
