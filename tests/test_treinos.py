"""Testes de salvar e ler treinos (app/treinos.py)."""

import pytest

from app.db import conectar, criar_tabelas
from app.treinos import (
    AUTOR_AUTOMATICO,
    AlunoNaoEncontrado,
    TreinoInvalido,
    obter_treino,
    salvar_treino,
)


@pytest.fixture
def conn():
    c = conectar()  # banco na memória, novo a cada teste
    criar_tabelas(c)
    yield c
    c.close()


@pytest.fixture
def aluno_id(conn):
    # CPF inventado, só para teste
    return conn.execute("INSERT INTO aluno (nome, cpf) VALUES ('ALUNO DE TESTE', '00000000000')").lastrowid


@pytest.fixture
def exercicios(conn):
    """Três exercícios ativos e um desativado. Devolve {'a': id, 'b': id, 'c': id, 'off': id}."""
    ids = {}
    for chave, nome, ativo in [("a", "SUPINO RETO", 1), ("b", "REMADA CURVADA", 1),
                               ("c", "AGACHAMENTO", 1), ("off", "EXERCICIO DESATIVADO", 0)]:
        ids[chave] = conn.execute(
            "INSERT INTO exercicio (nome, origem, ativo) VALUES (?, 'app', ?)", (nome, ativo)
        ).lastrowid
    return ids


def _item(exercicio_id, series="3", repeticoes="12", carga="20", bloco=None, **extras):
    """`extras`: campos opcionais do exercício (`pausa` em segundos, `observacao`)."""
    return {"exercicio_id": exercicio_id, "series": series, "repeticoes": repeticoes,
            "carga": carga, "bloco": bloco, **extras}


def _pedido(fichas, nome_treino="TREINO AB", montado_por="Ana Paula"):
    return {"nome_treino": nome_treino, "montado_por": montado_por, "fichas": fichas}


def _ficha(itens, nome="TREINO A"):
    return {"nome": nome, "itens": itens}


def _contagens(conn):
    return tuple(
        conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("treino", "ficha", "ficha_item")
    )


def _problemas(conn, aluno_id, pedido, status=400):
    with pytest.raises(TreinoInvalido) as erro:
        salvar_treino(conn, aluno_id, pedido)
    assert erro.value.status == status
    return erro.value.problemas


# ------------------------------------------------------------------ caminho feliz


def test_salva_treino_com_duas_fichas_e_le_de_volta(conn, aluno_id, exercicios):
    pedido = _pedido(
        [
            _ficha([_item(exercicios["a"], "4", "10", "30"), _item(exercicios["b"], "3", "12", "")], "TREINO A"),
            _ficha([_item(exercicios["c"], "5", "8", "60")], "TREINO B"),
        ]
    )

    treino_id = salvar_treino(conn, aluno_id, pedido)
    treino = obter_treino(conn, treino_id)

    assert treino["aluno_id"] == aluno_id
    assert treino["nome"] == "TREINO AB"
    assert treino["montado_por"] == "Ana Paula"
    assert treino["ativo"] == 1
    assert [f["nome"] for f in treino["fichas"]] == ["TREINO A", "TREINO B"]
    assert [f["ordem"] for f in treino["fichas"]] == [1, 2]
    primeira = treino["fichas"][0]["itens"]
    assert [(i["ordem"], i["exercicio"], i["series"], i["repeticoes"], i["carga"]) for i in primeira] == [
        (1, "SUPINO RETO", "4", "10", "30"),
        (2, "REMADA CURVADA", "3", "12", None),  # carga vazia vira "sem valor", não texto vazio
    ]


def test_guarda_a_ordem_da_lista_mesmo_com_ids_fora_de_ordem(conn, aluno_id, exercicios):
    pedido = _pedido([_ficha([_item(exercicios["c"]), _item(exercicios["a"]), _item(exercicios["b"])])])

    itens = obter_treino(conn, salvar_treino(conn, aluno_id, pedido))["fichas"][0]["itens"]

    assert [i["exercicio"] for i in itens] == ["AGACHAMENTO", "SUPINO RETO", "REMADA CURVADA"]


def test_mesmo_exercicio_pode_aparecer_duas_vezes_na_ficha(conn, aluno_id, exercicios):
    pedido = _pedido([_ficha([_item(exercicios["a"]), _item(exercicios["a"])])])

    itens = obter_treino(conn, salvar_treino(conn, aluno_id, pedido))["fichas"][0]["itens"]

    assert len(itens) == 2


def test_carga_ausente_ou_nula_tambem_fica_sem_valor(conn, aluno_id, exercicios):
    sem_chave = {"exercicio_id": exercicios["a"], "series": "3", "repeticoes": "10"}
    nula = _item(exercicios["b"], carga=None)

    itens = obter_treino(conn, salvar_treino(conn, aluno_id, _pedido([_ficha([sem_chave, nula])])))["fichas"][0]["itens"]

    assert [i["carga"] for i in itens] == [None, None]


def test_limpa_espacos_dos_textos(conn, aluno_id, exercicios):
    pedido = _pedido(
        [_ficha([_item(exercicios["a"], "  3 ", " 10\n", "  20  kg ")], "  TREINO   A ")],
        nome_treino="  Treino   do   Joao ",
        montado_por="  Ana \n  Paula  ",
    )

    treino = obter_treino(conn, salvar_treino(conn, aluno_id, pedido))

    assert treino["nome"] == "Treino do Joao"
    assert treino["montado_por"] == "Ana Paula"
    assert treino["fichas"][0]["nome"] == "TREINO A"
    item = treino["fichas"][0]["itens"][0]
    assert (item["series"], item["repeticoes"], item["carga"]) == ("3", "10", "20 kg")


def test_aceita_o_autor_automatico_e_acentos(conn, aluno_id, exercicios):
    pedido = _pedido([_ficha([_item(exercicios["a"])])], montado_por=AUTOR_AUTOMATICO)

    treino = obter_treino(conn, salvar_treino(conn, aluno_id, pedido))

    assert treino["montado_por"] == "Academia Glória Fit"


def test_texto_perigoso_e_guardado_como_texto_e_nao_executado(conn, aluno_id, exercicios):
    # SQL injection: o texto entra como parâmetro, nunca dentro do comando.
    estranho = "x'); DROP TABLE treino;--"
    pedido = _pedido([_ficha([_item(exercicios["a"])])], montado_por=estranho)

    treino = obter_treino(conn, salvar_treino(conn, aluno_id, pedido))

    assert treino["montado_por"] == estranho
    assert conn.execute("SELECT COUNT(*) FROM treino").fetchone()[0] == 1


def test_dois_alunos_podem_ter_treinos_com_o_mesmo_nome(conn, aluno_id, exercicios):
    outro = conn.execute("INSERT INTO aluno (nome, cpf) VALUES ('OUTRO ALUNO', '00000000001')").lastrowid
    pedido = _pedido([_ficha([_item(exercicios["a"])])])

    salvar_treino(conn, aluno_id, pedido)
    salvar_treino(conn, outro, pedido)

    assert _contagens(conn)[0] == 2


# ------------------------------------------------------------------ limites exatos


def test_aceita_exatamente_os_limites(conn, aluno_id, exercicios):
    pedido = _pedido(
        [_ficha([_item(exercicios["a"], "1" * 11, "2" * 11, "3" * 11)], "N" * 15)],
        nome_treino="T" * 40,
        montado_por="P" * 60,
    )

    treino = obter_treino(conn, salvar_treino(conn, aluno_id, pedido))

    assert len(treino["nome"]) == 40
    assert len(treino["montado_por"]) == 60
    assert len(treino["fichas"][0]["nome"]) == 15


@pytest.mark.parametrize(
    "campo, valor",
    [("nome_treino", "T" * 41), ("montado_por", "P" * 61)],
)
def test_recusa_um_caractere_alem_do_limite_do_treino(conn, aluno_id, exercicios, campo, valor):
    pedido = _pedido([_ficha([_item(exercicios["a"])])])
    pedido[campo] = valor

    assert _problemas(conn, aluno_id, pedido)
    assert _contagens(conn) == (0, 0, 0)


def test_recusa_nome_de_ficha_com_16_caracteres(conn, aluno_id, exercicios):
    problemas = _problemas(conn, aluno_id, _pedido([_ficha([_item(exercicios["a"])], "N" * 16)]))

    assert any("15" in p for p in problemas)


@pytest.mark.parametrize("campo", ["series", "repeticoes", "carga"])
def test_recusa_campo_do_exercicio_com_12_caracteres(conn, aluno_id, exercicios, campo):
    item = _item(exercicios["a"])
    item[campo] = "9" * 12

    problemas = _problemas(conn, aluno_id, _pedido([_ficha([item])]))

    assert any("11" in p for p in problemas)


# ------------------------------------------------------------------ campos obrigatórios


@pytest.mark.parametrize("valor", [None, "", "   ", "\n\t "])
def test_quem_montou_e_obrigatorio(conn, aluno_id, exercicios, valor):
    pedido = _pedido([_ficha([_item(exercicios["a"])])], montado_por=valor)

    problemas = _problemas(conn, aluno_id, pedido)

    assert any("quem montou" in p for p in problemas)
    assert _contagens(conn) == (0, 0, 0)


def test_quem_montou_ausente_do_pedido_tambem_e_recusado(conn, aluno_id, exercicios):
    pedido = _pedido([_ficha([_item(exercicios["a"])])])
    del pedido["montado_por"]

    assert _problemas(conn, aluno_id, pedido)


@pytest.mark.parametrize("valor", [None, "", "  "])
def test_nome_do_treino_e_obrigatorio(conn, aluno_id, exercicios, valor):
    pedido = _pedido([_ficha([_item(exercicios["a"])])], nome_treino=valor)

    assert any("nome do treino" in p for p in _problemas(conn, aluno_id, pedido))


@pytest.mark.parametrize("campo", ["series", "repeticoes"])
@pytest.mark.parametrize("valor", [None, "", "  "])
def test_series_e_repeticoes_sao_obrigatorias(conn, aluno_id, exercicios, campo, valor):
    item = _item(exercicios["a"])
    item[campo] = valor

    assert _problemas(conn, aluno_id, _pedido([_ficha([item])]))


def test_ficha_sem_nome_e_recusada(conn, aluno_id, exercicios):
    assert _problemas(conn, aluno_id, _pedido([_ficha([_item(exercicios["a"])], nome=" ")]))


@pytest.mark.parametrize("fichas", [[], None, "x", {}])
def test_treino_sem_fichas_e_recusado(conn, aluno_id, fichas):
    assert _problemas(conn, aluno_id, _pedido(fichas))


@pytest.mark.parametrize("itens", [[], None, "x", {}])
def test_ficha_sem_exercicios_e_recusada(conn, aluno_id, itens):
    assert _problemas(conn, aluno_id, _pedido([_ficha(itens)]))


def test_recusa_mais_de_26_fichas(conn, aluno_id, exercicios):
    fichas = [_ficha([_item(exercicios["a"])], f"F{n}") for n in range(27)]

    assert _problemas(conn, aluno_id, _pedido(fichas))


def test_recusa_mais_de_100_exercicios_na_ficha(conn, aluno_id, exercicios):
    itens = [_item(exercicios["a"]) for _ in range(101)]

    assert _problemas(conn, aluno_id, _pedido([_ficha(itens)]))


# ------------------------------------------------------------------ tipos errados e caracteres estranhos


@pytest.mark.parametrize("pedido", [None, [], "texto", 5])
def test_pedido_que_nao_e_objeto_e_recusado(conn, aluno_id, pedido):
    assert _problemas(conn, aluno_id, pedido) == ["Formato do pedido inválido."]


@pytest.mark.parametrize("valor", [123, ["Ana"], {"nome": "Ana"}, True])
def test_quem_montou_que_nao_e_texto_e_recusado(conn, aluno_id, exercicios, valor):
    pedido = _pedido([_ficha([_item(exercicios["a"])])], montado_por=valor)

    assert any("texto" in p for p in _problemas(conn, aluno_id, pedido))


@pytest.mark.parametrize("sujeira", ["Ana\x00Paula", "Ana\x07", "Ana​Paula", "Ana\x1b[31m"])
def test_recusa_caracteres_de_controle_e_invisiveis(conn, aluno_id, exercicios, sujeira):
    pedido = _pedido([_ficha([_item(exercicios["a"])])], montado_por=sujeira)

    assert any("inválidos" in p for p in _problemas(conn, aluno_id, pedido))


@pytest.mark.parametrize("campo", ["series", "repeticoes", "carga"])
def test_recusa_numero_no_lugar_de_texto_nos_campos_do_exercicio(conn, aluno_id, exercicios, campo):
    item = _item(exercicios["a"])
    item[campo] = 3  # o app manda texto; número solto é pedido fora do padrão

    assert _problemas(conn, aluno_id, _pedido([_ficha([item])]))


@pytest.mark.parametrize("valor", [None, "1", 1.5, True, [1], "abc"])
def test_exercicio_id_precisa_ser_inteiro(conn, aluno_id, exercicios, valor):
    item = _item(exercicios["a"])
    item["exercicio_id"] = valor

    assert any("exercício inválido" in p for p in _problemas(conn, aluno_id, _pedido([_ficha([item])])))


def test_true_nao_vale_como_exercicio_numero_1(conn, aluno_id):
    # Em Python True == 1; sem o cuidado, o pedido gravaria o exercício de id 1.
    conn.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'EXERCICIO UM', 'app')")
    item = _item(True)

    assert _problemas(conn, aluno_id, _pedido([_ficha([item])]))
    assert _contagens(conn) == (0, 0, 0)


def test_item_que_nao_e_objeto_e_recusado(conn, aluno_id):
    assert _problemas(conn, aluno_id, _pedido([_ficha(["supino"])]))


def test_ficha_que_nao_e_objeto_e_recusada(conn, aluno_id):
    assert _problemas(conn, aluno_id, _pedido(["TREINO A"]))


# ------------------------------------------------------------------ exercícios


def test_exercicio_que_nao_existe_e_recusado_e_nada_e_gravado(conn, aluno_id, exercicios):
    pedido = _pedido([_ficha([_item(exercicios["a"]), _item(99999)])])

    problemas = _problemas(conn, aluno_id, pedido)

    assert any("99999" in p for p in problemas)
    assert _contagens(conn) == (0, 0, 0)


def test_exercicio_desativado_e_recusado(conn, aluno_id, exercicios):
    assert _problemas(conn, aluno_id, _pedido([_ficha([_item(exercicios["off"])])]))


# ------------------------------------------------------------------ bi-set e tri-set


def _blocos(conn, treino_id):
    return [i["bloco"] for f in obter_treino(conn, treino_id)["fichas"] for i in f["itens"]]


def test_bi_set_e_tri_set_sao_gravados_e_renumerados_na_ordem(conn, aluno_id, exercicios):
    a, b, c = exercicios["a"], exercicios["b"], exercicios["c"]
    # a tela pode mandar números "soltos" (7 e 3); o banco guarda 1, 2, 3...
    itens = [_item(a), _item(a, bloco=7), _item(b, bloco=7), _item(c), _item(a, bloco=3), _item(b, bloco=3), _item(c, bloco=3)]

    treino_id = salvar_treino(conn, aluno_id, _pedido([_ficha(itens)]))

    assert _blocos(conn, treino_id) == [None, 1, 1, None, 2, 2, 2]


def test_blocos_em_fichas_diferentes_comecam_do_1_em_cada_ficha(conn, aluno_id, exercicios):
    a, b = exercicios["a"], exercicios["b"]
    fichas = [
        _ficha([_item(a, bloco=5), _item(b, bloco=5)], "TREINO A"),
        _ficha([_item(a, bloco=9), _item(b, bloco=9)], "TREINO B"),
    ]

    assert _blocos(conn, salvar_treino(conn, aluno_id, _pedido(fichas))) == [1, 1, 1, 1]


def test_dois_bi_sets_seguidos_com_numeros_diferentes_ficam_separados(conn, aluno_id, exercicios):
    a, b = exercicios["a"], exercicios["b"]
    itens = [_item(a, bloco=1), _item(b, bloco=1), _item(a, bloco=2), _item(b, bloco=2)]

    assert _blocos(conn, salvar_treino(conn, aluno_id, _pedido([_ficha(itens)]))) == [1, 1, 2, 2]


def test_recusa_bloco_com_um_exercicio_so(conn, aluno_id, exercicios):
    itens = [_item(exercicios["a"], bloco=1), _item(exercicios["b"])]

    assert any("bi-set" in p for p in _problemas(conn, aluno_id, _pedido([_ficha(itens)])))


def test_recusa_bloco_com_quatro_exercicios(conn, aluno_id, exercicios):
    a = exercicios["a"]
    itens = [_item(a, bloco=1) for _ in range(4)]

    assert any("bi-set" in p for p in _problemas(conn, aluno_id, _pedido([_ficha(itens)])))


def test_recusa_bloco_separado_por_outro_exercicio(conn, aluno_id, exercicios):
    a, b = exercicios["a"], exercicios["b"]
    itens = [_item(a, bloco=1), _item(b), _item(a, bloco=1)]

    assert any("juntos" in p for p in _problemas(conn, aluno_id, _pedido([_ficha(itens)])))


@pytest.mark.parametrize("bloco", [0, -1, "1", 1.5, True])
def test_recusa_numero_de_bloco_invalido(conn, aluno_id, exercicios, bloco):
    itens = [_item(exercicios["a"], bloco=bloco), _item(exercicios["b"], bloco=bloco)]

    assert any("bloco inválido" in p for p in _problemas(conn, aluno_id, _pedido([_ficha(itens)])))


# ------------------------------------------------------------------ vários erros de uma vez


def test_junta_todos_os_problemas_numa_resposta_so(conn, aluno_id, exercicios):
    pedido = _pedido(
        [_ficha([_item(exercicios["a"], series="")], "N" * 16)],
        nome_treino="",
        montado_por="",
    )

    problemas = _problemas(conn, aluno_id, pedido)

    assert len(problemas) >= 4  # nome do treino, quem montou, nome da ficha, séries


def test_mensagem_de_erro_diz_em_qual_ficha_e_exercicio(conn, aluno_id, exercicios):
    pedido = _pedido(
        [_ficha([_item(exercicios["a"])], "TREINO A"), _ficha([_item(exercicios["a"]), _item(exercicios["b"], repeticoes="")], "TREINO B")]
    )

    problemas = _problemas(conn, aluno_id, pedido)

    assert len(problemas) == 1
    assert "TREINO B" in problemas[0] and "exercício 2" in problemas[0]


# ------------------------------------------------------------------ intervalo e observação

# Pedido do Thiago (08/10/2026): os professores usam Intervalo e Observações em cada exercício.


def _item_gravado(conn, treino_id, posicao=0):
    return obter_treino(conn, treino_id)["fichas"][0]["itens"][posicao]


def test_grava_o_intervalo_em_segundos_e_a_observacao(conn, aluno_id, exercicios):
    pedido = _pedido([_ficha([_item(exercicios["a"], pausa=90, observacao="Descer devagar")])])

    treino_id = salvar_treino(conn, aluno_id, pedido)

    item = _item_gravado(conn, treino_id)
    assert item["pausa"] == 90
    assert item["observacao"] == "Descer devagar"


def test_sem_intervalo_e_sem_observacao_ficam_vazios(conn, aluno_id, exercicios):
    # pedido antigo (sem os dois campos), vazio, nulo e zero: tudo vira "sem valor"
    itens = [
        _item(exercicios["a"]),
        _item(exercicios["b"], pausa=None, observacao=None),
        _item(exercicios["c"], pausa=0, observacao=""),
        _item(exercicios["a"], observacao="   "),
    ]

    treino_id = salvar_treino(conn, aluno_id, _pedido([_ficha(itens)]))

    for posicao in range(4):
        item = _item_gravado(conn, treino_id, posicao)
        assert item["pausa"] is None and item["observacao"] is None


def test_observacao_tem_os_espacos_limpos(conn, aluno_id, exercicios):
    pedido = _pedido([_ficha([_item(exercicios["a"], observacao="  até   a\nfalha  ")])])

    treino_id = salvar_treino(conn, aluno_id, pedido)

    assert _item_gravado(conn, treino_id)["observacao"] == "até a falha"


def test_aceita_os_limites_do_intervalo_e_da_observacao(conn, aluno_id, exercicios):
    pedido = _pedido(
        [_ficha([_item(exercicios["a"], pausa=1, observacao="x" * 200), _item(exercicios["b"], pausa=3599)])]
    )

    treino_id = salvar_treino(conn, aluno_id, pedido)

    assert _item_gravado(conn, treino_id, 0)["pausa"] == 1
    assert len(_item_gravado(conn, treino_id, 0)["observacao"]) == 200
    assert _item_gravado(conn, treino_id, 1)["pausa"] == 3599


@pytest.mark.parametrize("pausa", [-1, 3600, 90.5, "90", True, [], {}])
def test_recusa_intervalo_invalido(conn, aluno_id, exercicios, pausa):
    pedido = _pedido([_ficha([_item(exercicios["a"], pausa=pausa)])])

    problemas = _problemas(conn, aluno_id, pedido)

    assert len(problemas) == 1 and "intervalo" in problemas[0]
    assert _contagens(conn) == (0, 0, 0)


def test_recusa_observacao_com_201_caracteres(conn, aluno_id, exercicios):
    pedido = _pedido([_ficha([_item(exercicios["a"], observacao="x" * 201)])])

    problemas = _problemas(conn, aluno_id, pedido)

    assert len(problemas) == 1 and "observação" in problemas[0] and "200" in problemas[0]


@pytest.mark.parametrize("valor", [123, ["a"], {"a": 1}, True])
def test_recusa_observacao_que_nao_e_texto(conn, aluno_id, exercicios, valor):
    problemas = _problemas(conn, aluno_id, _pedido([_ficha([_item(exercicios["a"], observacao=valor)])]))

    assert len(problemas) == 1 and "observação" in problemas[0]


@pytest.mark.parametrize("sujeira", ["a\x00b", "a\u202eb", "a\x07b"])
def test_recusa_caracteres_de_controle_na_observacao(conn, aluno_id, exercicios, sujeira):
    problemas = _problemas(conn, aluno_id, _pedido([_ficha([_item(exercicios["a"], observacao=sujeira)])]))

    assert len(problemas) == 1 and "caracteres inválidos" in problemas[0]


def test_observacao_perigosa_e_guardada_como_texto(conn, aluno_id, exercicios):
    texto = "<script>alert(1)</script> ' OR 1=1 --"
    treino_id = salvar_treino(conn, aluno_id, _pedido([_ficha([_item(exercicios["a"], observacao=texto)])]))

    assert _item_gravado(conn, treino_id)["observacao"] == texto


def test_mensagens_do_servidor_falam_ficha_e_peso(conn, aluno_id, exercicios):
    # as mesmas palavras da tela (e do Data4U): "ficha" e "peso", não "treino 1" nem "carga"
    problemas = _problemas(conn, aluno_id, _pedido([_ficha([_item(exercicios["a"], carga="c" * 12)], "")]))
    assert any("nome da ficha 1" in p for p in problemas)

    problemas = _problemas(conn, aluno_id, _pedido([_ficha([_item(exercicios["a"], carga="c" * 12)], "FICHA A")]))
    assert len(problemas) == 1 and "peso" in problemas[0] and "carga" not in problemas[0]

    problemas = _problemas(conn, aluno_id, _pedido([]))
    assert "Treino A" not in problemas[0]


# ------------------------------------------------------------------ aluno


def test_aluno_que_nao_existe(conn, exercicios):
    with pytest.raises(AlunoNaoEncontrado):
        salvar_treino(conn, 999, _pedido([_ficha([_item(exercicios["a"])])]))
    assert _contagens(conn) == (0, 0, 0)


# ------------------------------------------------------------------ nome repetido


def test_mesmo_nome_para_o_mesmo_aluno_da_409_sem_diferenciar_maiuscula_nem_acento(conn, aluno_id, exercicios):
    fichas = [_ficha([_item(exercicios["a"])])]
    salvar_treino(conn, aluno_id, _pedido(fichas, nome_treino="Treino Hipertrofia"))

    problemas = _problemas(conn, aluno_id, _pedido(fichas, nome_treino="TREINO HIPERTROFIA"), status=409)
    assert "já tem um treino" in problemas[0]

    salvar_treino(conn, aluno_id, _pedido(fichas, nome_treino="Treino Força"))
    _problemas(conn, aluno_id, _pedido(fichas, nome_treino="treino forca"), status=409)

    assert _contagens(conn) == (2, 2, 2)


def test_nome_repetido_com_espacos_a_mais_tambem_e_barrado(conn, aluno_id, exercicios):
    fichas = [_ficha([_item(exercicios["a"])])]
    salvar_treino(conn, aluno_id, _pedido(fichas, nome_treino="Treino A"))

    _problemas(conn, aluno_id, _pedido(fichas, nome_treino="  Treino   A "), status=409)


def test_indice_unico_do_banco_barra_nome_repetido_mesmo_sem_a_conferencia_previa(conn, aluno_id, exercicios):
    # Dois "salvar" ao mesmo tempo passariam pela conferência prévia; o índice único é a última barreira.
    import sqlite3

    # ativo = 0 nos dois: o que está em teste é o índice do NOME, não o do "um ativo por aluno"
    conn.execute("INSERT INTO treino (aluno_id, nome, montado_por, ativo) VALUES (?, 'Treino X', 'Ana', 0)", (aluno_id,))

    with pytest.raises(sqlite3.IntegrityError, match="treino"):
        conn.execute("INSERT INTO treino (aluno_id, nome, montado_por, ativo) VALUES (?, 'TREINO x', 'Bia', 0)", (aluno_id,))


def test_corrida_entre_dois_salvar_vira_409_e_nao_erro_500(conn, aluno_id, exercicios, monkeypatch):
    # Simula a corrida: a conferência prévia "não vê" o treino que outro pedido acabou de gravar.
    import app.treinos as modulo

    fichas = [_ficha([_item(exercicios["a"])])]
    salvar_treino(conn, aluno_id, _pedido(fichas, nome_treino="Treino Y"))
    monkeypatch.setattr(modulo, "normalizar", lambda texto: texto)  # conferência prévia deixa de achar

    problemas = _problemas(conn, aluno_id, _pedido(fichas, nome_treino="TREINO y"), status=409)

    assert "já tem um treino" in problemas[0]
    assert _contagens(conn) == (1, 1, 1)  # nada pela metade


# ------------------------------------------------------------------ tudo ou nada


def test_falha_no_meio_da_gravacao_desfaz_tudo(conn, aluno_id, exercicios):
    # Um gatilho faz o 2º item falhar: o treino e a ficha já gravados precisam sumir.
    conn.execute(
        """
        CREATE TRIGGER falha_no_segundo_item BEFORE INSERT ON ficha_item
        WHEN NEW.ordem = 2
        BEGIN SELECT RAISE(ABORT, 'falha de teste'); END
        """
    )
    import sqlite3

    pedido = _pedido([_ficha([_item(exercicios["a"]), _item(exercicios["b"])])])

    with pytest.raises(sqlite3.DatabaseError):
        salvar_treino(conn, aluno_id, pedido)

    assert _contagens(conn) == (0, 0, 0)


def test_pedido_invalido_nao_deixa_nada_para_tras(conn, aluno_id, exercicios):
    pedido = _pedido([_ficha([_item(exercicios["a"])], "TREINO A"), _ficha([], "TREINO B")])

    _problemas(conn, aluno_id, pedido)

    assert _contagens(conn) == (0, 0, 0)


# ------------------------------------------------------------------ ler


def test_obter_treino_que_nao_existe_devolve_none(conn):
    assert obter_treino(conn, 123) is None


def test_autor_automatico_tem_o_nome_combinado():
    assert AUTOR_AUTOMATICO == "Academia Glória Fit"


# ------------------------------------------------------------------ ciclo: início, fim, meta e "um ativo por aluno"

from datetime import datetime, timezone  # noqa: E402

AGORA = datetime(2026, 10, 8, 14, 30, 0, tzinfo=timezone.utc)  # 08/10/2026 11:30 em Brasília


def _com(fichas_exercicio, **extras):
    return {**_pedido([_ficha([_item(fichas_exercicio)])]), **extras}


def _ciclo(conn, treino_id):
    return tuple(
        conn.execute(
            "SELECT inicio, fim, sessoes_por_ficha, ativo, concluido_em FROM treino WHERE id = ?", (treino_id,)
        ).fetchone()
    )


def test_treino_novo_sem_datas_comeca_hoje_ativo_e_sem_meta(conn, aluno_id, exercicios):
    treino_id = salvar_treino(conn, aluno_id, _com(exercicios["a"]), agora=AGORA)

    assert _ciclo(conn, treino_id) == ("2026-10-08", None, None, 1, None)


def test_inicio_de_hoje_usa_o_dia_de_brasilia_e_nao_o_de_utc(conn, aluno_id, exercicios):
    de_madrugada = datetime(2026, 10, 9, 1, 30, 0, tzinfo=timezone.utc)  # ainda é 08/10, 22h30, em Brasília

    treino_id = salvar_treino(conn, aluno_id, _com(exercicios["a"]), agora=de_madrugada)

    assert _ciclo(conn, treino_id)[0] == "2026-10-08"


def test_grava_inicio_fim_e_treinos_por_ficha(conn, aluno_id, exercicios):
    dados = _com(exercicios["a"], inicio="2026-10-10", fim="2026-12-31", sessoes_por_ficha=15)

    treino_id = salvar_treino(conn, aluno_id, dados, agora=AGORA)

    assert _ciclo(conn, treino_id) == ("2026-10-10", "2026-12-31", 15, 1, None)
    treino = obter_treino(conn, treino_id)
    assert (treino["inicio"], treino["fim"], treino["sessoes_por_ficha"], treino["ativo"]) == ("2026-10-10", "2026-12-31", 15, 1)


@pytest.mark.parametrize("vazio", [None, ""])
def test_inicio_fim_e_meta_vazios_valem_como_nao_informados(conn, aluno_id, exercicios, vazio):
    dados = _com(exercicios["a"], inicio=vazio, fim=vazio, sessoes_por_ficha=vazio)

    treino_id = salvar_treino(conn, aluno_id, dados, agora=AGORA)

    assert _ciclo(conn, treino_id) == ("2026-10-08", None, None, 1, None)


def test_fim_no_mesmo_dia_do_inicio_vale(conn, aluno_id, exercicios):
    treino_id = salvar_treino(conn, aluno_id, _com(exercicios["a"], inicio="2026-10-08", fim="2026-10-08"))

    assert _ciclo(conn, treino_id)[:2] == ("2026-10-08", "2026-10-08")


def test_fim_antes_do_inicio_e_recusado(conn, aluno_id, exercicios):
    problemas = _problemas(conn, aluno_id, _com(exercicios["a"], inicio="2026-10-10", fim="2026-10-09"))

    assert problemas == ["A data do fim não pode ser antes da data do início."]
    assert _contagens(conn) == (0, 0, 0)


def test_fim_antes_de_hoje_sem_inicio_informado_tambem_e_recusado(conn, aluno_id, exercicios):
    # sem início, vale hoje: um fim ontem não faz sentido
    problemas = _problemas(conn, aluno_id, _com(exercicios["a"], fim="2020-01-01"))

    assert "A data do fim não pode ser antes da data do início." in problemas


@pytest.mark.parametrize(
    "valor",
    ["2026-02-30", "2026-13-01", "2026-1-5", "08/10/2026", "2026-10-081", "ontem", " 2026-10-08", "２０２６-10-08",
     "0202-10-08", "2206-10-08", "2019-12-31", 20261008, True, ["2026-10-08"]],
)
def test_data_invalida_e_recusada_no_inicio_e_no_fim(conn, aluno_id, exercicios, valor):
    assert "Início: data inválida" in _problemas(conn, aluno_id, _com(exercicios["a"], inicio=valor))[0]
    assert "Fim: data inválida" in _problemas(conn, aluno_id, _com(exercicios["a"], fim=valor))[0]
    assert _contagens(conn) == (0, 0, 0)


@pytest.mark.parametrize("valor", [1, 15, 999])
def test_meta_valida(conn, aluno_id, exercicios, valor):
    treino_id = salvar_treino(conn, aluno_id, _com(exercicios["a"], sessoes_por_ficha=valor))

    assert _ciclo(conn, treino_id)[2] == valor


@pytest.mark.parametrize("valor", [0, -1, 1000, 1.5, "15", "abc", True, [15]])
def test_meta_invalida_e_recusada(conn, aluno_id, exercicios, valor):
    problemas = _problemas(conn, aluno_id, _com(exercicios["a"], sessoes_por_ficha=valor))

    assert problemas == ["Treinos por ficha: use um número inteiro de 1 a 999."]
    assert _contagens(conn) == (0, 0, 0)


def test_varios_problemas_de_ciclo_aparecem_juntos_com_os_do_resto(conn, aluno_id, exercicios):
    pedido = _com(exercicios["a"], inicio="ontem", sessoes_por_ficha=0, nome_treino="")

    problemas = _problemas(conn, aluno_id, pedido)

    assert len(problemas) == 3


def test_treino_novo_conclui_o_ativo_anterior_na_mesma_gravacao(conn, aluno_id, exercicios):
    primeiro = salvar_treino(conn, aluno_id, _com(exercicios["a"], nome_treino="PRIMEIRO"), agora=AGORA)

    segundo = salvar_treino(conn, aluno_id, _com(exercicios["b"], nome_treino="SEGUNDO"), agora=AGORA)

    assert _ciclo(conn, primeiro)[3:] == (0, "2026-10-08 14:30:00")  # inativo, com o momento (UTC) em que acabou
    assert _ciclo(conn, segundo)[3:] == (1, None)
    assert conn.execute("SELECT COUNT(*) FROM treino WHERE aluno_id = ? AND ativo = 1", (aluno_id,)).fetchone()[0] == 1


def test_treino_recusado_nao_conclui_o_ativo(conn, aluno_id, exercicios):
    primeiro = salvar_treino(conn, aluno_id, _com(exercicios["a"], nome_treino="PRIMEIRO"))

    _problemas(conn, aluno_id, _com(exercicios["a"], nome_treino="primeiro"), status=409)  # nome repetido
    _problemas(conn, aluno_id, _com(exercicios["a"], nome_treino="OUTRO", sessoes_por_ficha=0))

    assert _ciclo(conn, primeiro)[3:] == (1, None)


def test_falha_na_gravacao_nao_conclui_o_ativo(conn, aluno_id, exercicios):
    primeiro = salvar_treino(conn, aluno_id, _com(exercicios["a"], nome_treino="PRIMEIRO"))
    conn.execute(
        "CREATE TRIGGER falha_no_item BEFORE INSERT ON ficha_item BEGIN SELECT RAISE(ABORT, 'falha de teste'); END"
    )
    import sqlite3

    with pytest.raises(sqlite3.DatabaseError):
        salvar_treino(conn, aluno_id, _com(exercicios["b"], nome_treino="SEGUNDO"))

    assert _ciclo(conn, primeiro)[3:] == (1, None)  # a conclusão volta junto com o resto


def test_concluir_o_ativo_de_um_aluno_nao_mexe_nos_outros(conn, aluno_id, exercicios):
    outro = conn.execute("INSERT INTO aluno (nome) VALUES ('OUTRA ALUNA')").lastrowid
    do_outro = salvar_treino(conn, outro, _com(exercicios["a"], nome_treino="DA OUTRA"))

    salvar_treino(conn, aluno_id, _com(exercicios["a"], nome_treino="X1"))
    salvar_treino(conn, aluno_id, _com(exercicios["a"], nome_treino="X2"))

    assert _ciclo(conn, do_outro)[3:] == (1, None)


def test_treino_do_historico_inativo_continua_inativo_ao_salvar_novo(conn, aluno_id, exercicios):
    antigo = conn.execute(
        "INSERT INTO treino (aluno_id, nome, montado_por, origem, data4u_id, ativo) VALUES (?, 'ANTIGO', 'X', 'data4u', 9, 0)",
        (aluno_id,),
    ).lastrowid

    novo = salvar_treino(conn, aluno_id, _com(exercicios["a"]), agora=AGORA)

    assert _ciclo(conn, antigo)[3:] == (0, None)  # não ganha "concluído em" que não aconteceu agora
    assert _ciclo(conn, novo)[3] == 1


def test_o_treino_lido_mostra_o_exercicio_sem_o_numero_da_maquina(conn, aluno_id):
    ex = conn.execute("INSERT INTO exercicio (nome, origem) VALUES ('(6) SUPINO MAQUINA', 'app')").lastrowid
    treino_id = salvar_treino(conn, aluno_id, _pedido([_ficha([_item(ex)])]))
    item = obter_treino(conn, treino_id)["fichas"][0]["itens"][0]
    assert item["exercicio"] == "SUPINO MAQUINA"
    assert item["exercicio_id"] == ex  # a ligação com o exercício não muda
