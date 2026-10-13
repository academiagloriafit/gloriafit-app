"""Filas numeradas de treino (app/filas.py) e o que elas mudam em treinos, modelos, ficha e rotas.

Dados inventados. Regras combinadas com o Thiago em 13/10/2026:
- o app só SUGERE o próximo treino da fila; quem aprova é o professor (salvando o treino aberto pela fila);
- o professor coloca o aluno na fila; Gestante e Grupos de risco exigem a liberação registrada (sim + data + nome);
- a sugestão aparece quando o aluno não tem treino ativo ou quando é hora de trocar o ativo;
- no último número da fila o app avisa "fim da fila" e não repete nada sozinho.
"""

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app import acesso, ciclo, filas, modelos
from app.alunos import obter_ficha
from app.db import conectar, criar_tabelas
from app.treinos import AlunoNaoEncontrado, TreinoInvalido, obter_treino, salvar_treino
from app.web import criar_app

HOMEM, MULHER, ADOLESCENTE, GESTANTE, RISCO = 1, 2, 3, 4, 5
AGORA = datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc)  # 12h em Brasília, dia 13/10/2026


# ------------------------------------------------------------------ preparação


@pytest.fixture
def conn():
    c = conectar()
    criar_tabelas(c)
    c.execute("INSERT INTO aluno (id, nome) VALUES (1, 'ANA FICTICIA'), (2, 'BRUNO FICTICIO')")
    c.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO RETO', 'app'), (2, 'REMADA', 'app')")
    c.commit()
    yield c
    c.close()


def _fichas():
    return [{"nome": "FICHA A", "itens": [{"exercicio_id": 1, "series": "3", "repeticoes": "12"}, {"exercicio_id": 2, "series": "3", "repeticoes": "10"}]}]


def _padrao(conn, nome, fila_id=None, numero=None):
    return modelos.criar_modelo(
        conn, {"nome": nome, "montado_por": "Ana", "fichas": _fichas(), "fila_id": fila_id, "numero": numero}
    )


def _fila_com_treinos(conn, fila_id=MULHER, numeros=(1, 2, 3)):
    """Cria os treinos padrão da fila; devolve {numero: id do padrão}."""
    return {n: _padrao(conn, f"F{fila_id} TREINO {n}", fila_id, n) for n in numeros}


def _pedido(nome="TREINO ABC", **extras):
    return {"nome_treino": nome, "montado_por": "Bia", "fichas": _fichas(), **extras}


def _entrar(conn, aluno_id=1, fila_id=MULHER, **extras):
    filas.definir_fila(conn, aluno_id, {"fila_id": fila_id, "professor": "Bia", **extras}, agora=AGORA)


def _situacao(conn, aluno_id=1, hora=True):
    return filas.fila_do_aluno(conn, aluno_id, hora_de_trocar=hora)


# ------------------------------------------------------------------ as filas do começo


def test_as_cinco_filas_do_comeco_e_quais_exigem_liberacao(conn):
    lista = filas.listar_filas(conn)

    assert [(f["nome"], f["exige_liberacao"]) for f in lista] == [
        ("Homem", False),
        ("Mulher", False),
        ("Adolescente", False),
        ("Gestante", True),
        ("Grupos de risco", True),
    ]
    assert all(f["treinos"] == [] for f in lista)  # no começo todas as filas estão vazias


def test_listar_filas_traz_os_treinos_em_ordem_de_numero(conn):
    ids = {n: _padrao(conn, f"M{n}", MULHER, n) for n in (3, 1, 2)}
    _padrao(conn, "H1", HOMEM, 1)
    _padrao(conn, "SOLTO")

    mulher = next(f for f in filas.listar_filas(conn) if f["id"] == MULHER)
    homem = next(f for f in filas.listar_filas(conn) if f["id"] == HOMEM)

    assert [(t["numero"], t["modelo_id"], t["nome"]) for t in mulher["treinos"]] == [(1, ids[1], "M1"), (2, ids[2], "M2"), (3, ids[3], "M3")]
    assert [t["nome"] for t in homem["treinos"]] == ["H1"]  # o padrão solto não está em fila nenhuma


# ------------------------------------------------------------------ guardar o treino padrão numa fila


def test_treino_padrao_fica_na_fila_com_numero(conn):
    modelo_id = _padrao(conn, "MULHER 3", MULHER, 3)

    assert tuple(conn.execute("SELECT fila_id, numero FROM modelo_treino WHERE id = ?", (modelo_id,)).fetchone()) == (MULHER, 3)
    dado = next(m for m in modelos.listar_modelos(conn) if m["id"] == modelo_id)
    assert (dado["fila_id"], dado["fila"], dado["numero"], dado["posicao"]) == (MULHER, "Mulher", 3, "Mulher · Treino 3")


def test_treino_padrao_solto_continua_valendo(conn):
    modelo_id = _padrao(conn, "SOLTO")

    dado = next(m for m in modelos.listar_modelos(conn) if m["id"] == modelo_id)
    assert (dado["fila_id"], dado["fila"], dado["numero"], dado["posicao"]) == (None, None, None, "")


def test_fila_e_numero_vazios_valem_como_solto(conn):
    # a tela manda "" ou null quando o professor não escolhe fila
    for i, (fila_id, numero) in enumerate([("", ""), (None, ""), ("", None)]):
        modelos.criar_modelo(conn, {"nome": f"SOLTO {i}", "montado_por": "A", "fichas": _fichas(), "fila_id": fila_id, "numero": numero})
    assert conn.execute("SELECT COUNT(*) FROM modelo_treino WHERE fila_id IS NULL").fetchone()[0] == 3


@pytest.mark.parametrize(
    "extras, trecho",
    [
        ({"fila_id": MULHER}, "a fila E o número"),
        ({"numero": 2}, "a fila E o número"),
        ({"fila_id": 99, "numero": 1}, "A fila escolhida não existe"),
        ({"fila_id": "2", "numero": 1}, "A fila escolhida não existe"),
        ({"fila_id": True, "numero": 1}, "A fila escolhida não existe"),
        ({"fila_id": MULHER, "numero": 0}, "de 1 a 99"),
        ({"fila_id": MULHER, "numero": 100}, "de 1 a 99"),
        ({"fila_id": MULHER, "numero": "3"}, "de 1 a 99"),
        ({"fila_id": MULHER, "numero": 1.5}, "de 1 a 99"),
        ({"fila_id": MULHER, "numero": True}, "de 1 a 99"),
    ],
)
def test_posicao_invalida_e_recusada_com_400_e_nada_e_gravado(conn, extras, trecho):
    with pytest.raises(TreinoInvalido) as erro:
        modelos.criar_modelo(conn, {"nome": "X", "montado_por": "A", "fichas": _fichas(), **extras})

    assert erro.value.status == 400
    assert trecho in " ".join(erro.value.problemas)
    assert conn.execute("SELECT COUNT(*) FROM modelo_treino").fetchone()[0] == 0


def test_numero_ja_ocupado_na_fila_e_conflito_409(conn):
    _padrao(conn, "MULHER 1", MULHER, 1)

    with pytest.raises(TreinoInvalido) as erro:
        _padrao(conn, "OUTRO", MULHER, 1)

    assert erro.value.status == 409
    assert 'A fila Mulher já tem o Treino 1 ("MULHER 1")' in erro.value.problemas[0]
    assert conn.execute("SELECT COUNT(*) FROM modelo_treino").fetchone()[0] == 1


def test_o_mesmo_numero_em_outra_fila_vale(conn):
    _padrao(conn, "MULHER 1", MULHER, 1)

    _padrao(conn, "HOMEM 1", HOMEM, 1)

    assert conn.execute("SELECT COUNT(*) FROM modelo_treino WHERE numero = 1").fetchone()[0] == 2


def test_dados_ruins_vencem_o_conflito_de_numero(conn):
    _padrao(conn, "MULHER 1", MULHER, 1)

    with pytest.raises(TreinoInvalido) as erro:
        modelos.criar_modelo(conn, {"nome": "", "montado_por": "A", "fichas": _fichas(), "fila_id": MULHER, "numero": 1})

    assert erro.value.status == 400


def test_guardar_um_treino_do_aluno_como_padrao_numa_fila(conn):
    treino_id = salvar_treino(conn, 1, _pedido(), agora=AGORA)

    modelo_id = modelos.criar_modelo_do_treino(conn, treino_id, "MULHER 2", fila_id=MULHER, numero=2)

    assert tuple(conn.execute("SELECT fila_id, numero FROM modelo_treino WHERE id = ?", (modelo_id,)).fetchone()) == (MULHER, 2)


def test_guardar_um_treino_do_aluno_como_padrao_numa_fila_ocupada_e_409(conn):
    treino_id = salvar_treino(conn, 1, _pedido(), agora=AGORA)
    _padrao(conn, "MULHER 2", MULHER, 2)

    with pytest.raises(TreinoInvalido) as erro:
        modelos.criar_modelo_do_treino(conn, treino_id, "OUTRO NOME", fila_id=MULHER, numero=2)

    assert erro.value.status == 409


def test_modelo_para_montar_traz_a_fila_e_o_numero(conn):
    com_fila = _padrao(conn, "MULHER 2", MULHER, 2)
    solto = _padrao(conn, "SOLTO")

    a = modelos.modelo_para_montar(conn, com_fila)
    b = modelos.modelo_para_montar(conn, solto)

    assert (a["fila_id"], a["fila"], a["numero"]) == (MULHER, "Mulher", 2)
    assert (b["fila_id"], b["fila"], b["numero"]) == (None, None, None)
    assert a["fichas"][0]["itens"][0]["exercicio_id"] == 1  # o resto do formato continua igual


def test_excluir_o_treino_da_fila_deixa_o_buraco_e_libera_o_numero(conn):
    ids = _fila_com_treinos(conn, MULHER, (1, 2, 3))

    modelos.excluir_modelo(conn, ids[2])

    assert [t["numero"] for t in next(f for f in filas.listar_filas(conn) if f["id"] == MULHER)["treinos"]] == [1, 3]
    _padrao(conn, "NOVO 2", MULHER, 2)  # o número voltou a ficar livre


# ------------------------------------------------------------------ colocar o aluno na fila


def test_professor_coloca_o_aluno_numa_fila_sem_liberacao(conn):
    _entrar(conn, 1, MULHER)

    linha = conn.execute("SELECT * FROM aluno_fila WHERE aluno_id = 1").fetchone()
    assert (linha["fila_id"], linha["numero_atual"], linha["definida_por"]) == (MULHER, None, "Bia")
    assert linha["definida_em"] == "2026-10-13 15:00:00"
    assert (linha["liberacao_em"], linha["liberacao_por"]) == (None, None)


def test_nas_filas_sem_liberacao_os_campos_de_liberacao_sao_ignorados(conn):
    _entrar(conn, 1, HOMEM, liberacao_conferida=True, liberacao_em="2026-10-01")

    linha = conn.execute("SELECT liberacao_em, liberacao_por FROM aluno_fila WHERE aluno_id = 1").fetchone()
    assert (linha["liberacao_em"], linha["liberacao_por"]) == (None, None)


@pytest.mark.parametrize("fila", [GESTANTE, RISCO])
def test_filas_com_liberacao_exigem_a_confirmacao(conn, fila):
    for extras in [{}, {"liberacao_conferida": False}, {"liberacao_conferida": "sim"}, {"liberacao_conferida": 1}]:
        with pytest.raises(TreinoInvalido) as erro:
            _entrar(conn, 1, fila, **extras)
        assert erro.value.status == 400
        assert "liberação conferida" in erro.value.problemas[0]
    assert conn.execute("SELECT COUNT(*) FROM aluno_fila").fetchone()[0] == 0


def test_liberacao_guarda_sim_data_e_nome_do_professor(conn):
    _entrar(conn, 1, GESTANTE, professor="  Carla   Souza ", liberacao_conferida=True, liberacao_em="2026-10-10")

    linha = conn.execute("SELECT definida_por, liberacao_em, liberacao_por FROM aluno_fila").fetchone()
    assert tuple(linha) == ("Carla Souza", "2026-10-10", "Carla Souza")


def test_liberacao_sem_data_vale_hoje_em_brasilia(conn):
    # 01h de 14/10 em UTC ainda é 22h de 13/10 em Brasília
    agora = datetime(2026, 10, 14, 1, 0, tzinfo=timezone.utc)

    filas.definir_fila(conn, 1, {"fila_id": RISCO, "professor": "Bia", "liberacao_conferida": True}, agora=agora)

    assert conn.execute("SELECT liberacao_em FROM aluno_fila").fetchone()[0] == "2026-10-13"


@pytest.mark.parametrize("data", ["2026-10-14", "2027-01-01"])
def test_liberacao_no_futuro_e_recusada(conn, data):
    with pytest.raises(TreinoInvalido) as erro:
        _entrar(conn, 1, GESTANTE, liberacao_conferida=True, liberacao_em=data)

    assert "no futuro" in erro.value.problemas[0]


@pytest.mark.parametrize("data", ["13/10/2026", "2026-02-30", "2019-12-31", 20261010, "hoje"])
def test_liberacao_com_data_invalida_e_recusada(conn, data):
    with pytest.raises(TreinoInvalido) as erro:
        _entrar(conn, 1, GESTANTE, liberacao_conferida=True, liberacao_em=data)

    assert "Data da liberação" in erro.value.problemas[0]


def test_liberacao_de_hoje_e_aceita(conn):
    _entrar(conn, 1, GESTANTE, liberacao_conferida=True, liberacao_em="2026-10-13")

    assert conn.execute("SELECT liberacao_em FROM aluno_fila").fetchone()[0] == "2026-10-13"


@pytest.mark.parametrize("professor", [None, "", "   ", 5, "x" * 61, "Bia\x00"])
def test_o_professor_e_obrigatorio_e_conferido(conn, professor):
    with pytest.raises(TreinoInvalido) as erro:
        filas.definir_fila(conn, 1, {"fila_id": MULHER, "professor": professor}, agora=AGORA)

    assert "professor" in erro.value.problemas[0]


@pytest.mark.parametrize("fila_id", [None, "", 0, 99, "2", True, 2.0])
def test_fila_que_nao_existe_e_recusada(conn, fila_id):
    with pytest.raises(TreinoInvalido) as erro:
        filas.definir_fila(conn, 1, {"fila_id": fila_id, "professor": "Bia"}, agora=AGORA)

    assert "Escolha a fila" in erro.value.problemas[0]


@pytest.mark.parametrize("dados", [None, [], "texto", 5])
def test_pedido_fora_do_formato_e_recusado(conn, dados):
    with pytest.raises(TreinoInvalido):
        filas.definir_fila(conn, 1, dados, agora=AGORA)


def test_aluno_que_nao_existe(conn):
    with pytest.raises(AlunoNaoEncontrado):
        _entrar(conn, 99)
    with pytest.raises(AlunoNaoEncontrado):
        filas.tirar_da_fila(conn, 99)


def test_problemas_vem_todos_juntos(conn):
    with pytest.raises(TreinoInvalido) as erro:
        filas.definir_fila(conn, 1, {"fila_id": GESTANTE, "professor": ""}, agora=AGORA)

    assert len(erro.value.problemas) == 2  # falta o professor e falta a confirmação


def test_mudar_de_fila_zera_a_posicao_e_repetir_a_mesma_mantem(conn):
    _fila_com_treinos(conn, MULHER, (1, 2, 3))
    _entrar(conn, 1, MULHER)
    conn.execute("UPDATE aluno_fila SET numero_atual = 2")

    _entrar(conn, 1, MULHER)  # a mesma fila (ex.: o professor só confirmou de novo)
    assert conn.execute("SELECT numero_atual FROM aluno_fila").fetchone()[0] == 2

    _entrar(conn, 1, HOMEM)  # outra fila
    linha = conn.execute("SELECT fila_id, numero_atual FROM aluno_fila").fetchone()
    assert (linha["fila_id"], linha["numero_atual"]) == (HOMEM, None)
    assert conn.execute("SELECT COUNT(*) FROM aluno_fila").fetchone()[0] == 1  # um aluno, uma fila


def test_ir_de_uma_fila_com_liberacao_para_outra_sem_apaga_a_liberacao(conn):
    _entrar(conn, 1, GESTANTE, liberacao_conferida=True, liberacao_em="2026-10-10")

    _entrar(conn, 1, MULHER)

    linha = conn.execute("SELECT liberacao_em, liberacao_por FROM aluno_fila").fetchone()
    assert (linha["liberacao_em"], linha["liberacao_por"]) == (None, None)


def test_tirar_da_fila_nao_mexe_no_treino(conn):
    treino_id = salvar_treino(conn, 1, _pedido(), agora=AGORA)
    _entrar(conn, 1, MULHER)

    filas.tirar_da_fila(conn, 1)
    filas.tirar_da_fila(conn, 1)  # sem fila: não faz nada nem dá erro

    assert conn.execute("SELECT COUNT(*) FROM aluno_fila").fetchone()[0] == 0
    assert obter_treino(conn, treino_id)["ativo"] == 1


# ------------------------------------------------------------------ a sugestão do próximo treino


def test_aluno_sem_fila(conn):
    resposta = _situacao(conn)

    assert resposta["atual"] is None
    assert [f["nome"] for f in resposta["filas"]][:2] == ["Homem", "Mulher"]


def test_quem_ainda_nao_comecou_a_fila_recebe_o_primeiro_na_hora_de_trocar(conn):
    ids = _fila_com_treinos(conn, MULHER, (1, 2, 3))
    _entrar(conn, 1, MULHER)

    atual = _situacao(conn, hora=True)["atual"]

    assert atual["numero_atual"] is None
    assert atual["sugestao"] == {"modelo_id": ids[1], "numero": 1, "nome": "F2 TREINO 1"}
    assert [(t["numero"], t["atual"], t["sugerido"]) for t in atual["treinos"]] == [(1, False, True), (2, False, False), (3, False, False)]
    assert (atual["fim_da_fila"], atual["vazia"], atual["hora_de_trocar"]) == (False, False, True)


def test_sem_hora_de_trocar_nao_ha_sugestao(conn):
    _fila_com_treinos(conn, MULHER, (1, 2, 3))
    _entrar(conn, 1, MULHER)
    conn.execute("UPDATE aluno_fila SET numero_atual = 1")

    atual = _situacao(conn, hora=False)["atual"]

    assert atual["sugestao"] is None
    assert atual["fim_da_fila"] is False
    assert [(t["numero"], t["atual"], t["sugerido"]) for t in atual["treinos"]] == [(1, True, False), (2, False, False), (3, False, False)]


def test_na_hora_de_trocar_sugere_o_numero_seguinte(conn):
    ids = _fila_com_treinos(conn, MULHER, (1, 2, 3))
    _entrar(conn, 1, MULHER)
    conn.execute("UPDATE aluno_fila SET numero_atual = 2")

    atual = _situacao(conn, hora=True)["atual"]

    assert atual["sugestao"]["modelo_id"] == ids[3]
    assert [(t["numero"], t["atual"], t["sugerido"]) for t in atual["treinos"]] == [(1, False, False), (2, True, False), (3, False, True)]


def test_numeros_com_buraco_pulam_para_o_proximo_que_existe(conn):
    ids = _fila_com_treinos(conn, MULHER, (1, 2, 4))
    _entrar(conn, 1, MULHER)
    conn.execute("UPDATE aluno_fila SET numero_atual = 2")

    assert _situacao(conn)["atual"]["sugestao"]["modelo_id"] == ids[4]


def test_numero_atual_sem_treino_correspondente_ainda_sugere_o_proximo(conn):
    ids = _fila_com_treinos(conn, MULHER, (1, 4))
    _entrar(conn, 1, MULHER)
    conn.execute("UPDATE aluno_fila SET numero_atual = 3")  # o Treino 3 foi excluído depois

    atual = _situacao(conn)["atual"]

    assert atual["sugestao"]["modelo_id"] == ids[4]
    assert not any(t["atual"] for t in atual["treinos"])


def test_no_ultimo_numero_o_app_avisa_fim_da_fila_e_nao_sugere(conn):
    _fila_com_treinos(conn, MULHER, (1, 2, 3))
    _entrar(conn, 1, MULHER)
    conn.execute("UPDATE aluno_fila SET numero_atual = 3")

    atual = _situacao(conn, hora=True)["atual"]

    assert atual["sugestao"] is None
    assert atual["fim_da_fila"] is True
    assert not any(t["sugerido"] for t in atual["treinos"])


def test_no_ultimo_numero_sem_hora_de_trocar_nao_avisa_fim(conn):
    _fila_com_treinos(conn, MULHER, (1, 2, 3))
    _entrar(conn, 1, MULHER)
    conn.execute("UPDATE aluno_fila SET numero_atual = 3")

    assert _situacao(conn, hora=False)["atual"]["fim_da_fila"] is False


def test_fila_vazia_avisa_que_nao_tem_treino_e_nao_e_fim_da_fila(conn):
    _entrar(conn, 1, MULHER)

    atual = _situacao(conn, hora=True)["atual"]

    assert atual["vazia"] is True
    assert atual["sugestao"] is None
    assert atual["fim_da_fila"] is False
    assert atual["treinos"] == []


def test_a_situacao_traz_quem_colocou_quando_e_a_liberacao(conn):
    _entrar(conn, 1, GESTANTE, professor="Carla", liberacao_conferida=True, liberacao_em="2026-10-10")

    atual = _situacao(conn)["atual"]

    assert (atual["nome"], atual["exige_liberacao"]) == ("Gestante", True)
    assert (atual["definida_por"], atual["definida_em"]) == ("Carla", "13/10/2026")
    assert (atual["liberacao_em"], atual["liberacao_por"]) == ("10/10/2026", "Carla")


def test_a_fila_de_um_aluno_nao_aparece_para_outro(conn):
    _entrar(conn, 1, MULHER)

    assert _situacao(conn, aluno_id=2)["atual"] is None


# ------------------------------------------------------------------ na ficha do aluno


def test_ficha_sem_treino_ativo_e_hora_de_sugerir(conn):
    ids = _fila_com_treinos(conn, MULHER, (1, 2))
    _entrar(conn, 1, MULHER)

    ficha = obter_ficha(conn, 1)

    assert ficha["tem_treino_ativo"] is False
    assert ficha["fila"]["atual"]["sugestao"]["modelo_id"] == ids[1]


def test_ficha_com_treino_ativo_em_dia_nao_sugere(conn):
    _fila_com_treinos(conn, MULHER, (1, 2))
    _entrar(conn, 1, MULHER)
    salvar_treino(conn, 1, _pedido(fim="2026-12-31"), agora=AGORA)

    atual = obter_ficha(conn, 1)["fila"]["atual"]

    assert atual["hora_de_trocar"] is False
    assert atual["sugestao"] is None


def test_ficha_com_treino_vencido_sugere(conn):
    ids = _fila_com_treinos(conn, MULHER, (1, 2))
    _entrar(conn, 1, MULHER)
    salvar_treino(conn, 1, _pedido(inicio="2020-01-01", fim="2020-02-01"), agora=AGORA)  # o fim já passou

    ficha = obter_ficha(conn, 1)

    assert ficha["aviso_de_troca"] != ""
    assert ficha["fila"]["atual"]["sugestao"]["modelo_id"] == ids[1]


def test_depois_de_concluir_o_treino_a_sugestao_aparece(conn):
    ids = _fila_com_treinos(conn, MULHER, (1, 2))
    _entrar(conn, 1, MULHER)
    treino_id = salvar_treino(conn, 1, _pedido(fim="2026-12-31"), agora=AGORA)
    assert obter_ficha(conn, 1)["fila"]["atual"]["sugestao"] is None

    ciclo.concluir_treino(conn, treino_id)

    assert obter_ficha(conn, 1)["fila"]["atual"]["sugestao"]["modelo_id"] == ids[1]


def test_ficha_de_quem_nao_tem_fila(conn):
    ficha = obter_ficha(conn, 1)

    assert ficha["fila"]["atual"] is None
    assert len(ficha["fila"]["filas"]) == 5


# ------------------------------------------------------------------ aprovar: salvar o treino aberto pela fila


def test_salvar_o_treino_da_fila_marca_o_numero_do_aluno(conn):
    ids = _fila_com_treinos(conn, MULHER, (1, 2, 3))
    _entrar(conn, 1, MULHER)

    salvar_treino(conn, 1, _pedido(fila_modelo_id=ids[1]), agora=AGORA)
    assert conn.execute("SELECT numero_atual FROM aluno_fila").fetchone()[0] == 1

    salvar_treino(conn, 1, _pedido(nome="TREINO 2", fila_modelo_id=ids[2]), agora=AGORA)
    assert conn.execute("SELECT numero_atual FROM aluno_fila").fetchone()[0] == 2


def test_depois_de_aprovar_o_proximo_da_fila_e_o_seguinte(conn):
    ids = _fila_com_treinos(conn, MULHER, (1, 2, 3))
    _entrar(conn, 1, MULHER)
    treino_id = salvar_treino(conn, 1, _pedido(fila_modelo_id=ids[1]), agora=AGORA)
    ciclo.concluir_treino(conn, treino_id)

    atual = obter_ficha(conn, 1)["fila"]["atual"]

    assert atual["numero_atual"] == 1
    assert atual["sugestao"]["modelo_id"] == ids[2]


def test_o_professor_pode_pular_para_qualquer_treino_da_fila(conn):
    ids = _fila_com_treinos(conn, MULHER, (1, 2, 3))
    _entrar(conn, 1, MULHER)

    salvar_treino(conn, 1, _pedido(fila_modelo_id=ids[3]), agora=AGORA)

    assert conn.execute("SELECT numero_atual FROM aluno_fila").fetchone()[0] == 3


def test_salvar_sem_fila_modelo_id_nao_mexe_na_fila(conn):
    _fila_com_treinos(conn, MULHER, (1, 2))
    _entrar(conn, 1, MULHER)
    conn.execute("UPDATE aluno_fila SET numero_atual = 1")

    salvar_treino(conn, 1, _pedido(), agora=AGORA)
    salvar_treino(conn, 1, _pedido(nome="OUTRO", fila_modelo_id=None), agora=AGORA)

    assert conn.execute("SELECT numero_atual FROM aluno_fila").fetchone()[0] == 1


def test_salvar_sem_estar_em_fila_nenhuma_com_treino_da_fila_e_recusado(conn):
    ids = _fila_com_treinos(conn, MULHER, (1,))  # o aluno NÃO está na fila

    with pytest.raises(TreinoInvalido) as erro:
        salvar_treino(conn, 1, _pedido(fila_modelo_id=ids[1]), agora=AGORA)

    assert erro.value.status == 409
    assert conn.execute("SELECT COUNT(*) FROM treino").fetchone()[0] == 0  # nada foi gravado


def test_treino_de_outra_fila_e_recusado_e_nada_muda(conn):
    ids = _fila_com_treinos(conn, HOMEM, (1,))
    _entrar(conn, 1, MULHER)
    anterior = salvar_treino(conn, 1, _pedido("ANTERIOR"), agora=AGORA)

    with pytest.raises(TreinoInvalido) as erro:
        salvar_treino(conn, 1, _pedido(fila_modelo_id=ids[1]), agora=AGORA)

    assert erro.value.status == 409
    assert conn.execute("SELECT COUNT(*) FROM treino").fetchone()[0] == 1
    assert obter_treino(conn, anterior)["ativo"] == 1  # o treino anterior não foi concluído à toa
    assert conn.execute("SELECT numero_atual FROM aluno_fila").fetchone()[0] is None


def test_padrao_sem_fila_ou_que_nao_existe_e_recusado(conn):
    solto = _padrao(conn, "SOLTO")
    _entrar(conn, 1, MULHER)

    for modelo_id in (solto, 9999):
        with pytest.raises(TreinoInvalido) as erro:
            salvar_treino(conn, 1, _pedido(fila_modelo_id=modelo_id), agora=AGORA)
        assert erro.value.status == 409


@pytest.mark.parametrize("valor", ["1", 0, -1, 1.5, True, [], {}])
def test_fila_modelo_id_fora_do_formato_e_recusado(conn, valor):
    _fila_com_treinos(conn, MULHER, (1,))
    _entrar(conn, 1, MULHER)

    with pytest.raises(TreinoInvalido) as erro:
        salvar_treino(conn, 1, _pedido(fila_modelo_id=valor), agora=AGORA)

    assert erro.value.status == 400
    assert conn.execute("SELECT COUNT(*) FROM treino").fetchone()[0] == 0


def test_se_a_fila_do_aluno_mudar_no_meio_do_salvar_nada_e_gravado(conn, monkeypatch):
    # dois computadores: enquanto um salva, o outro troca a fila do aluno
    ids = _fila_com_treinos(conn, MULHER, (1,))
    _entrar(conn, 1, MULHER)
    from app import treinos

    original = treinos._conferir_treino_da_fila

    def conferir_e_trocar_a_fila(conn_, aluno_id, dados):
        numero = original(conn_, aluno_id, dados)
        conn_.execute("UPDATE aluno_fila SET fila_id = ? WHERE aluno_id = ?", (HOMEM, aluno_id))  # a fila mudou
        conn_.commit()
        return numero

    monkeypatch.setattr(treinos, "_conferir_treino_da_fila", conferir_e_trocar_a_fila)

    with pytest.raises(TreinoInvalido) as erro:
        salvar_treino(conn, 1, _pedido(fila_modelo_id=ids[1]), agora=AGORA)

    assert erro.value.status == 409
    assert conn.execute("SELECT COUNT(*) FROM treino").fetchone()[0] == 0
    assert conn.execute("SELECT numero_atual FROM aluno_fila").fetchone()[0] is None


def test_editar_treino_nao_mexe_na_fila(conn):
    ids = _fila_com_treinos(conn, MULHER, (1, 2))
    _entrar(conn, 1, MULHER)
    treino_id = salvar_treino(conn, 1, _pedido(fila_modelo_id=ids[1]), agora=AGORA)
    from app.treinos import editar_treino

    editar_treino(conn, treino_id, _pedido("NOME NOVO", fila_modelo_id=ids[2]), agora=AGORA)

    assert conn.execute("SELECT numero_atual FROM aluno_fila").fetchone()[0] == 1


# ------------------------------------------------------------------ rotas


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "filas.db"
    c = conectar(caminho)
    criar_tabelas(c)
    c.execute("INSERT INTO aluno (id, nome) VALUES (1, 'ANA FICTICIA'), (2, 'BRUNO FICTICIO')")
    c.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO RETO', 'app'), (2, 'REMADA', 'app')")
    c.commit()
    c.close()
    return caminho


@pytest.fixture
def anonimo(caminho):
    return criar_app(caminho).test_client()


@pytest.fixture
def cliente(caminho):
    navegador = criar_app(caminho).test_client()
    c = conectar(caminho)
    codigo = acesso.gerar_codigo(c, "Computador de teste").codigo
    token = acesso.autorizar(c, codigo).token
    c.close()
    navegador.set_cookie(acesso.NOME_DO_COOKIE, token)
    return navegador


def _banco(caminho, sql, *args):
    c = conectar(caminho)
    try:
        return [tuple(linha) for linha in c.execute(sql, args)]
    finally:
        c.close()


def _corpo_de_modelo(nome="MULHER 1", **extras):
    return {"nome": nome, "montado_por": "Ana", "fichas": _fichas(), **extras}


@pytest.mark.parametrize("url", ["/api/alunos/1/fila", "/api/alunos/1/fila/tirar"])
def test_rotas_das_filas_exigem_computador_autorizado(anonimo, url):
    assert anonimo.post(url, json={}).status_code == 401


@pytest.mark.parametrize("url", ["/api/alunos/1/fila", "/api/alunos/1/fila/tirar"])
def test_rotas_das_filas_exigem_json(cliente, url):
    assert cliente.post(url, data="fila_id=2").status_code == 415


def test_rota_coloca_o_aluno_na_fila(cliente, caminho):
    resposta = cliente.post("/api/alunos/1/fila", json={"fila_id": MULHER, "professor": "Bia"})

    assert resposta.status_code == 200 and resposta.get_json() == {"ok": True}
    assert _banco(caminho, "SELECT aluno_id, fila_id, definida_por FROM aluno_fila") == [(1, MULHER, "Bia")]


def test_rota_da_fila_com_liberacao(cliente, caminho):
    sem = cliente.post("/api/alunos/1/fila", json={"fila_id": GESTANTE, "professor": "Bia"})
    com = cliente.post(
        "/api/alunos/1/fila",
        json={"fila_id": GESTANTE, "professor": "Bia", "liberacao_conferida": True, "liberacao_em": "2026-10-10"},
    )

    assert sem.status_code == 400 and "liberação" in sem.get_json()["erros"][0]
    assert com.status_code == 200
    assert _banco(caminho, "SELECT liberacao_em, liberacao_por FROM aluno_fila") == [("2026-10-10", "Bia")]


def test_rota_da_fila_aluno_inexistente_e_404(cliente):
    assert cliente.post("/api/alunos/99/fila", json={"fila_id": MULHER, "professor": "Bia"}).status_code == 404
    assert cliente.post("/api/alunos/99/fila/tirar", json={}).status_code == 404


def test_rota_da_fila_com_pedido_ruim_e_400(cliente, caminho):
    assert cliente.post("/api/alunos/1/fila", json=[1, 2]).status_code == 400
    assert cliente.post("/api/alunos/1/fila", json={"fila_id": 99, "professor": "Bia"}).status_code == 400
    assert _banco(caminho, "SELECT COUNT(*) FROM aluno_fila") == [(0,)]


def test_rota_tira_o_aluno_da_fila(cliente, caminho):
    cliente.post("/api/alunos/1/fila", json={"fila_id": MULHER, "professor": "Bia"})

    resposta = cliente.post("/api/alunos/1/fila/tirar", json={})

    assert resposta.status_code == 200
    assert _banco(caminho, "SELECT COUNT(*) FROM aluno_fila") == [(0,)]


def test_rota_de_treino_padrao_aceita_fila_e_numero(cliente, caminho):
    ok = cliente.post("/api/modelos", json=_corpo_de_modelo(fila_id=MULHER, numero=1))
    repetido = cliente.post("/api/modelos", json=_corpo_de_modelo("OUTRO", fila_id=MULHER, numero=1))
    faltando = cliente.post("/api/modelos", json=_corpo_de_modelo("TERCEIRO", fila_id=MULHER))

    assert ok.status_code == 201
    assert repetido.status_code == 409 and "já tem o Treino 1" in repetido.get_json()["erros"][0]
    assert faltando.status_code == 400
    assert _banco(caminho, "SELECT nome, fila_id, numero FROM modelo_treino") == [("MULHER 1", MULHER, 1)]


def test_rota_lista_e_le_o_treino_padrao_com_a_fila(cliente):
    modelo_id = cliente.post("/api/modelos", json=_corpo_de_modelo(fila_id=ADOLESCENTE, numero=4)).get_json()["id"]

    listado = cliente.get("/api/modelos").get_json()["modelos"][0]
    lido = cliente.get(f"/api/modelos/{modelo_id}").get_json()

    assert (listado["fila"], listado["numero"], listado["posicao"]) == ("Adolescente", 4, "Adolescente · Treino 4")
    assert (lido["fila_id"], lido["fila"], lido["numero"]) == (ADOLESCENTE, "Adolescente", 4)


def test_rota_do_treino_do_aluno_como_padrao_aceita_fila(cliente, caminho):
    treino_id = cliente.post("/api/alunos/1/treinos", json=_pedido()).get_json()["id"]

    resposta = cliente.post(f"/api/treinos/{treino_id}/modelo", json={"nome": "HOMEM 1", "fila_id": HOMEM, "numero": 1})

    assert resposta.status_code == 201
    assert _banco(caminho, "SELECT nome, fila_id, numero FROM modelo_treino") == [("HOMEM 1", HOMEM, 1)]


def test_rota_de_salvar_treino_pela_fila_marca_a_posicao(cliente, caminho):
    modelo_id = cliente.post("/api/modelos", json=_corpo_de_modelo(fila_id=MULHER, numero=2)).get_json()["id"]
    cliente.post("/api/alunos/1/fila", json={"fila_id": MULHER, "professor": "Bia"})

    resposta = cliente.post("/api/alunos/1/treinos", json=_pedido(fila_modelo_id=modelo_id))

    assert resposta.status_code == 201
    assert _banco(caminho, "SELECT numero_atual FROM aluno_fila") == [(2,)]


def test_rota_de_salvar_treino_de_outra_fila_e_409(cliente, caminho):
    modelo_id = cliente.post("/api/modelos", json=_corpo_de_modelo(fila_id=HOMEM, numero=1)).get_json()["id"]
    cliente.post("/api/alunos/1/fila", json={"fila_id": MULHER, "professor": "Bia"})

    resposta = cliente.post("/api/alunos/1/treinos", json=_pedido(fila_modelo_id=modelo_id))

    assert resposta.status_code == 409
    assert _banco(caminho, "SELECT COUNT(*) FROM treino") == [(0,)]


# ------------------------------------------------------------------ as telas (o HTML tem o que o JavaScript procura)

PASTA_ESTATICA = Path(__file__).resolve().parent.parent / "app" / "static"
# ids que a ficha só traz quando o aluno JÁ está numa fila (o JavaScript os procura com cuidado)
IDS_SO_COM_FILA = {"abrir-form-fila", "fila-tirar", "confirmar-tirar-fila", "fila-tirar-sim", "fila-tirar-nao", "fila-cancelar"}


def _ids_que_o_js_procura(arquivo):
    codigo = (PASTA_ESTATICA / arquivo).read_text(encoding="utf-8")
    return set(re.findall(r'(?:pegar|getElementById)\("([^"]+)"\)', codigo))


def _ficha_html(cliente, aluno=1):
    resposta = cliente.get(f"/alunos/{aluno}")
    assert resposta.status_code == 200
    return resposta.get_data(as_text=True)


def _na_fila(caminho, aluno=1, fila_id=MULHER, numero_atual=None, **extras):
    c = conectar(caminho)
    try:
        filas.definir_fila(c, aluno, {"fila_id": fila_id, "professor": "Bia", **extras})
        if numero_atual is not None:
            c.execute("UPDATE aluno_fila SET numero_atual = ? WHERE aluno_id = ?", (numero_atual, aluno))
            c.commit()
    finally:
        c.close()


def _padroes_da_fila(caminho, fila_id=MULHER, numeros=(1, 2, 3)):
    c = conectar(caminho)
    try:
        return _fila_com_treinos(c, fila_id, numeros)
    finally:
        c.close()


def test_a_ficha_sem_fila_mostra_o_formulario_aberto_com_as_cinco_filas(cliente):
    html = _ficha_html(cliente)

    assert 'id="painel-fila"' in html
    assert "Este aluno não está em nenhuma fila" in html
    assert re.search(r'<div id="form-fila" class="form-fila" >', html)  # sem "hidden": já vem aberto
    for nome in ("Homem", "Mulher", "Adolescente", "Gestante", "Grupos de risco"):
        assert f"{nome}" in html
    # Gestante e Grupos de risco pedem a liberação; as outras não
    assert re.findall(r'data-exige="(\d)"[^>]*>(Gestante|Grupos de risco)', html) == [("1", "Gestante"), ("1", "Grupos de risco")]
    assert len(re.findall(r'data-exige="1"', html)) == 2
    assert 'src="/static/fila_ficha.js"' in html
    assert "style=" not in html  # a política de segurança não aceita estilo dentro da página


def test_a_ficha_sem_fila_tem_os_ids_obrigatorios_do_javascript(cliente):
    html = _ficha_html(cliente)

    ids = _ids_que_o_js_procura("fila_ficha.js") - IDS_SO_COM_FILA
    assert {"painel-fila", "form-fila", "fila-escolhida", "fila-professor", "bloco-liberacao", "fila-colocar"} <= ids
    faltando = {i for i in ids if f'id="{i}"' not in html}
    assert faltando == set(), f"fila_ficha.js procura ids que a ficha não tem: {sorted(faltando)}"
    for opcional in IDS_SO_COM_FILA:
        assert f'id="{opcional}"' not in html, opcional


def test_a_ficha_de_quem_esta_na_fila_tem_todos_os_ids_e_o_formulario_fechado(cliente, caminho):
    _na_fila(caminho)
    html = _ficha_html(cliente)

    assert "Ainda não começou a fila" in html
    assert re.search(r'<div id="form-fila" class="form-fila" hidden>', html)
    faltando = {i for i in _ids_que_o_js_procura("fila_ficha.js") if f'id="{i}"' not in html}
    assert faltando == set(), sorted(faltando)
    assert 'value="2" data-exige="0" selected' in html  # a fila atual já vem escolhida


def test_a_ficha_mostra_quem_colocou_e_a_liberacao(cliente, caminho):
    _na_fila(caminho, fila_id=GESTANTE, liberacao_conferida=True, liberacao_em="2026-10-01")
    html = _ficha_html(cliente)

    assert "por Bia" in html
    assert "Liberação conferida em 01/10/2026 por Bia" in html


def test_a_ficha_lista_os_treinos_da_fila_com_atual_e_sugerido_e_o_link_para_abrir(cliente, caminho):
    padroes = _padroes_da_fila(caminho)
    _na_fila(caminho, numero_atual=1)  # sem treino ativo: é hora de trocar -> o Treino 2 é o sugerido
    html = _ficha_html(cliente)

    assert re.search(r"Treino 1</span>.*?>Atual<", html, re.S)
    assert re.search(r"Treino 2</span>.*?>Sugerido<", html, re.S)
    assert html.count(">Sugerido<") == 1
    for numero, modelo_id in padroes.items():
        assert f'href="/alunos/1/montar?fila={modelo_id}"' in html


def test_a_sugestao_aparece_no_alto_dos_treinos_com_o_botao_de_abrir(cliente, caminho):
    padroes = _padroes_da_fila(caminho)
    _na_fila(caminho, numero_atual=1)
    html = _ficha_html(cliente)

    sugestao = re.search(r'<p class="aviso-troca[^>]*id="sugestao-fila">(.*?)</p>', html, re.S).group(1)
    assert "Sugestão da fila Mulher: Treino 2" in sugestao
    assert f'href="/alunos/1/montar?fila={padroes[2]}"' in sugestao
    assert "Abrir o Treino 2" in sugestao


def test_sem_hora_de_trocar_nao_ha_sugestao_na_ficha(cliente, caminho):
    _padroes_da_fila(caminho)
    c = conectar(caminho)
    salvar_treino(c, 1, _pedido(sessoes_por_ficha=None))  # treino ativo, sem meta nem fim: não é hora de trocar
    c.close()
    _na_fila(caminho, numero_atual=1)
    html = _ficha_html(cliente)

    assert 'id="sugestao-fila"' not in html
    assert ">Sugerido<" not in html


def test_no_fim_da_fila_a_ficha_avisa_e_nao_oferece_botao(cliente, caminho):
    _padroes_da_fila(caminho)
    _na_fila(caminho, numero_atual=3)
    html = _ficha_html(cliente)

    sugestao = re.search(r'<p class="aviso-troca[^>]*id="sugestao-fila">(.*?)</p>', html, re.S).group(1)
    assert "Fim da fila Mulher" in sugestao
    assert "Nada recomeça sozinho" in sugestao
    assert "Abrir o Treino" not in sugestao


def test_fila_sem_treinos_a_ficha_avisa_como_montar(cliente, caminho):
    _na_fila(caminho)
    html = _ficha_html(cliente)

    assert "A fila Mulher ainda não tem treinos" in html
    assert 'class="fila-treinos"' not in html


def test_o_nome_do_treino_da_fila_e_escapado_na_ficha(cliente, caminho):
    c = conectar(caminho)
    _padrao(c, 'MULHER <b>1</b> "X"', MULHER, 1)
    c.close()
    _na_fila(caminho)
    html = _ficha_html(cliente)

    assert "<b>1</b>" not in html
    assert "&lt;b&gt;1&lt;/b&gt;" in html


def test_o_salvar_como_padrao_da_ficha_tem_fila_e_numero_com_os_numeros_ja_usados(cliente, caminho):
    c = conectar(caminho)
    salvar_treino(c, 1, _pedido())
    _fila_com_treinos(c, MULHER, (1, 2, 4))
    c.close()
    html = _ficha_html(cliente)

    assert html.count('class="campo-fila-padrao"') == 1
    assert html.count('class="campo-numero-padrao"') == 1
    assert 'value="2" data-usados="1,2,4">Mulher<' in html
    assert 'value="1" data-usados="">Homem<' in html
    assert 'class="dica dica-fila-padrao"' in html


def test_a_tela_de_montar_tem_fila_e_numero_e_o_texto_do_treino_da_fila(cliente, caminho):
    c = conectar(caminho)
    _fila_com_treinos(c, MULHER, (1, 3))
    c.close()
    html = cliente.get("/alunos/1/montar").get_data(as_text=True)

    for id_ in ("fila-padrao", "numero-padrao", "dica-fila-padrao", "texto-fila"):
        assert f'id="{id_}"' in html, id_
    assert 'value="2" data-usados="1,3">Mulher<' in html
    assert re.search(r'id="numero-padrao"[^>]*disabled', html)  # sem fila escolhida, sem número
    assert "style=" not in html


@pytest.mark.parametrize("arquivo", ["montar.js", "importar_treino.js", "salvar.js"])
def test_a_tela_de_montar_tem_todos_os_ids_que_o_javascript_procura_com_as_filas(cliente, arquivo):
    html = cliente.get("/alunos/1/montar").get_data(as_text=True)

    ids = _ids_que_o_js_procura(arquivo) - {"titulo-exercicios", "aviso-treino-ativo"}
    assert ids
    faltando = {i for i in ids if f'id="{i}"' not in html}
    assert faltando == set(), f"{arquivo} procura ids que a tela não tem: {sorted(faltando)}"


def test_os_arquivos_novos_das_filas_sao_servidos(cliente):
    for arquivo in ("fila_ficha.js", "fila_padrao.js", "filas_modelo.js"):
        resposta = cliente.get(f"/static/{arquivo}")
        assert resposta.status_code == 200, arquivo
        assert "javascript" in resposta.content_type
