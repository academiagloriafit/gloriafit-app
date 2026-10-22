"""Testes do que o aluno faz DURANTE o treino (app/execucao.py e as partes de app/aluno_treino.py + rotas que usam isso):
marcar exercício como feito, anotar a carga usada ("Última vez") e dar a nota de esforço. Dados inventados."""

from datetime import datetime, timedelta, timezone

import pytest

from app import aluno_acesso, ciclo, execucao, treinos
from app.aluno_treino import (
    MarcacaoInvalida,
    definir_esforco,
    desfazer_marcacao_de_hoje,
    marcar_ficha_feita,
    marcar_exercicio,
    treino_do_aluno,
)
from app.db import conectar, criar_tabelas
from app.web import criar_app

AGORA = datetime(2026, 10, 22, 15, 0, tzinfo=timezone.utc)  # 12h00 em Brasília
ONTEM = AGORA - timedelta(days=1)
AMANHA = AGORA + timedelta(days=1)


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "execucao.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.executemany(
        "INSERT INTO aluno (id, nome, cpf, whatsapp, situacao) VALUES (?, ?, ?, ?, ?)",
        [
            (1, "ANA SOUZA", "11144477735", "27988887766", "A"),
            (2, "BRUNO LIMA", "52998224725", "27977776655", "A"),
        ],
    )
    for nome in ["SUPINO RETO", "CRUCIFIXO", "TRICEPS TESTA", "TRICEPS NA POLIA", "ROSCA DIRETA", "ESTEIRA"]:
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


def _salvar(conn, aluno_id=1, fichas=None, nome="TREINO ABC"):
    fichas = fichas or [("A", [_item(1, pausa=90), _item(2)]), ("B", [_item(3)])]
    return treinos.salvar_treino(
        conn,
        aluno_id,
        {"nome_treino": nome, "montado_por": "PROFESSORA", "fichas": [{"nome": n, "itens": i} for n, i in fichas]},
    )


def _exercicios(conn, aluno_id=1, agora=AGORA, ficha=0):
    treino = treino_do_aluno(conn, aluno_id, agora)
    return [e for grupo in treino["fichas"][ficha]["grupos"] for e in grupo["exercicios"]]


# ------------------------------------------------------------------ a carga digitada


@pytest.mark.parametrize(
    ("digitado", "guardado"),
    [
        ("12,5", "12,5"),
        ("12.5", "12,5"),
        ("30", "30"),
        ("030", "30"),
        ("  7  ", "7"),
        ("12,50", "12,5"),
        ("0,5", "0,5"),
        ("0,01", "0,01"),
        ("100", "100"),
        ("999,99", "999,99"),
        ("2,25", "2,25"),
    ],
)
def test_carga_valida_vira_numero_com_virgula_e_sem_zeros_sobrando(digitado, guardado):
    assert execucao.carga_limpa(digitado) == guardado


@pytest.mark.parametrize("vazio", [None, "", "   ", "\n"])
def test_carga_vazia_significa_apagar(vazio):
    assert execucao.carga_limpa(vazio) is None


@pytest.mark.parametrize(
    "ruim",
    ["abc", "20 kg", "20kg", "-5", "0", "0,00", "1000", "1.000", "1.000,5", "12,555", "1e3", ",5", "5,", "NaN", "Infinity", "١٢", "12;5", 12, 12.5, True, ["12"], {"a": 1}],
)
def test_carga_que_nao_e_um_numero_em_kg_e_recusada(ruim):
    with pytest.raises(execucao.CargaInvalida):
        execucao.carga_limpa(ruim)


# ------------------------------------------------------------------ gravar e ler (o banco)


def _linhas(conn):
    return [tuple(l) for l in conn.execute("SELECT aluno_id, dia, ficha_ordem, exercicio_ordem, exercicio_nome, feito, carga FROM execucao ORDER BY id")]


def test_marcar_feito_cria_a_linha_do_dia_de_brasilia(conn):
    resposta = execucao.gravar(conn, 1, 1, 2, "CRUCIFIXO", feito=True, agora=AGORA)

    assert resposta == {"feito": True, "carga_hoje": ""}
    assert _linhas(conn) == [(1, "2026-10-22", 1, 2, "CRUCIFIXO", 1, None)]


def test_o_dia_e_o_de_brasilia_e_nao_o_do_relogio_de_londres(conn):
    de_madrugada = datetime(2026, 10, 23, 1, 30, tzinfo=timezone.utc)  # 22/10 22h30 em Brasília

    execucao.gravar(conn, 1, 1, 1, "SUPINO RETO", feito=True, agora=de_madrugada)

    assert _linhas(conn)[0][1] == "2026-10-22"


def test_anotar_carga_sem_marcar_feito_guarda_a_carga(conn):
    resposta = execucao.gravar(conn, 1, 1, 1, "SUPINO RETO", carga="30", agora=AGORA)

    assert resposta == {"feito": False, "carga_hoje": "30"}
    assert _linhas(conn) == [(1, "2026-10-22", 1, 1, "SUPINO RETO", 0, "30")]


def test_o_que_nao_veio_no_pedido_nao_muda(conn):
    execucao.gravar(conn, 1, 1, 1, "SUPINO RETO", feito=True, carga="30", agora=AGORA)

    so_a_carga = execucao.gravar(conn, 1, 1, 1, "SUPINO RETO", carga="32,5", agora=AGORA)
    so_o_feito = execucao.gravar(conn, 1, 1, 1, "SUPINO RETO", feito=True, agora=AGORA)

    assert so_a_carga == {"feito": True, "carga_hoje": "32,5"}
    assert so_o_feito == {"feito": True, "carga_hoje": "32,5"}
    assert len(_linhas(conn)) == 1


def test_desmarcar_feito_mantem_a_carga_e_a_linha(conn):
    execucao.gravar(conn, 1, 1, 1, "SUPINO RETO", feito=True, carga="30", agora=AGORA)

    resposta = execucao.gravar(conn, 1, 1, 1, "SUPINO RETO", feito=False, agora=AGORA)

    assert resposta == {"feito": False, "carga_hoje": "30"}
    assert len(_linhas(conn)) == 1


def test_sem_feito_e_sem_carga_a_linha_some(conn):
    execucao.gravar(conn, 1, 1, 1, "SUPINO RETO", feito=True, carga="30", agora=AGORA)
    execucao.gravar(conn, 1, 1, 1, "SUPINO RETO", feito=False, agora=AGORA)

    resposta = execucao.gravar(conn, 1, 1, 1, "SUPINO RETO", carga=None, agora=AGORA)

    assert resposta == {"feito": False, "carga_hoje": ""}
    assert _linhas(conn) == []


def test_apagar_o_que_nunca_foi_anotado_nao_quebra(conn):
    assert execucao.gravar(conn, 1, 1, 1, "SUPINO RETO", feito=False, agora=AGORA) == {"feito": False, "carga_hoje": ""}
    assert _linhas(conn) == []


def test_trocar_o_exercicio_no_meio_do_dia_nao_apaga_o_que_o_aluno_anotou_do_antigo(conn):
    """O professor trocou o exercício no meio do dia: a marca do antigo não passa para o novo, e também não se perde."""
    execucao.gravar(conn, 1, 1, 1, "SUPINO RETO", feito=True, carga="30", agora=AGORA)

    resposta = execucao.gravar(conn, 1, 1, 1, "ESTEIRA", carga="5", agora=AGORA)

    assert resposta == {"feito": False, "carga_hoje": "5"}
    assert _linhas(conn) == [
        (1, "2026-10-22", 1, 1, "SUPINO RETO", 1, "30"),
        (1, "2026-10-22", 1, 1, "ESTEIRA", 0, "5"),
    ]


def test_o_mesmo_nome_em_duas_ocorrencias_na_ficha_tem_duas_linhas(conn):
    execucao.gravar(conn, 1, 1, 1, "AGACHAMENTO", ocorrencia=1, carga="40", agora=AGORA)
    execucao.gravar(conn, 1, 1, 4, "AGACHAMENTO", ocorrencia=2, carga="60", agora=AGORA)

    assert [(l[3], l[6]) for l in _linhas(conn)] == [(1, "40"), (4, "60")]
    marcas = execucao.marcas_do_dia(conn, 1, "2026-10-22")
    assert marcas[(1, "AGACHAMENTO", 1)]["carga"] == "40" and marcas[(1, "AGACHAMENTO", 2)]["carga"] == "60"


def test_cada_dia_tem_a_sua_linha(conn):
    execucao.gravar(conn, 1, 1, 1, "SUPINO RETO", feito=True, carga="30", agora=ONTEM)
    execucao.gravar(conn, 1, 1, 1, "SUPINO RETO", feito=True, carga="35", agora=AGORA)

    assert [(l[1], l[6]) for l in _linhas(conn)] == [("2026-10-21", "30"), ("2026-10-22", "35")]


def test_o_banco_recusa_linha_vazia_ou_carga_enorme(conn):
    with pytest.raises(Exception):
        conn.execute(
            "INSERT INTO execucao (aluno_id, dia, ficha_ordem, exercicio_ordem, exercicio_nome, feito, carga, atualizado_em) "
            "VALUES (1, '2026-10-22', 1, 1, 'X', 0, NULL, '2026-10-22 15:00:00')"
        )
    with pytest.raises(Exception):
        conn.execute(
            "INSERT INTO execucao (aluno_id, dia, ficha_ordem, exercicio_ordem, exercicio_nome, feito, carga, atualizado_em) "
            "VALUES (1, '2026-10-22', 1, 1, 'X', 1, '1234567890', '2026-10-22 15:00:00')"
        )


def test_ultima_carga_e_a_do_dia_mais_recente_antes_de_hoje(conn):
    execucao.gravar(conn, 1, 1, 1, "SUPINO RETO", carga="20", agora=AGORA - timedelta(days=5))
    execucao.gravar(conn, 1, 1, 1, "SUPINO RETO", carga="25", agora=AGORA - timedelta(days=2))
    execucao.gravar(conn, 1, 1, 1, "SUPINO RETO", carga="99", agora=AGORA)  # hoje não conta como "última vez"
    execucao.gravar(conn, 1, 1, 2, "CRUCIFIXO", carga="12", agora=ONTEM)

    ultimas = execucao.ultimas_cargas(conn, 1, {"SUPINO RETO", "CRUCIFIXO", "ESTEIRA"}, "2026-10-22")

    assert ultimas == {"SUPINO RETO": ("25", "2026-10-20"), "CRUCIFIXO": ("12", "2026-10-21")}


def test_ultima_carga_ignora_dia_so_com_feito_e_outro_aluno(conn):
    execucao.gravar(conn, 1, 1, 1, "SUPINO RETO", carga="20", agora=AGORA - timedelta(days=3))
    execucao.gravar(conn, 1, 1, 1, "SUPINO RETO", feito=True, agora=ONTEM)  # fez, mas não anotou: não vira "última carga"
    execucao.gravar(conn, 2, 1, 1, "SUPINO RETO", carga="80", agora=ONTEM)

    assert execucao.ultimas_cargas(conn, 1, {"SUPINO RETO"}, "2026-10-22") == {"SUPINO RETO": ("20", "2026-10-19")}


def test_ultima_carga_com_muitos_nomes_nao_estoura_o_limite_de_parametros(conn):
    nomes = {f"EXERCICIO {i}" for i in range(450)}
    execucao.gravar(conn, 1, 1, 1, "EXERCICIO 449", carga="9", agora=ONTEM)

    assert execucao.ultimas_cargas(conn, 1, nomes, "2026-10-22") == {"EXERCICIO 449": ("9", "2026-10-21")}
    assert execucao.ultimas_cargas(conn, 1, set(), "2026-10-22") == {}


# ------------------------------------------------------------------ o que o aluno vê no treino


def test_treino_sem_nada_marcado_traz_as_chaves_vazias(conn):
    _salvar(conn)

    exercicios = _exercicios(conn)

    assert all(e["feito"] is False and e["carga_hoje"] == "" and e["ultima_carga"] == "" and e["ultima_data"] == "" for e in exercicios)
    assert exercicios[0]["pausa_segundos"] == 90 and exercicios[1]["pausa_segundos"] == 0
    assert treino_do_aluno(conn, 1, AGORA)["fichas"][0]["esforco_hoje"] is None


def test_marcar_exercicio_aparece_no_treino_e_nao_na_ficha_do_lado(conn):
    _salvar(conn)

    resposta = marcar_exercicio(conn, 1, 1, 2, "CRUCIFIXO", feito=True, carga="12,5", agora=AGORA)

    assert resposta == {"feito": True, "carga_hoje": "12,5"}
    primeiro, segundo = _exercicios(conn)
    assert (primeiro["feito"], primeiro["carga_hoje"]) == (False, "")
    assert (segundo["feito"], segundo["carga_hoje"]) == (True, "12,5")
    assert _exercicios(conn, ficha=1)[0]["feito"] is False


def test_no_dia_seguinte_o_treino_volta_limpo_e_mostra_a_ultima_vez(conn):
    _salvar(conn)
    marcar_exercicio(conn, 1, 1, 1, "SUPINO RETO", feito=True, carga="30", agora=AGORA)

    amanha = _exercicios(conn, agora=AMANHA)[0]

    assert amanha["feito"] is False and amanha["carga_hoje"] == ""
    assert amanha["ultima_carga"] == "30" and amanha["ultima_data"] == "22/10/2026"


def test_a_ultima_carga_acompanha_o_exercicio_mesmo_se_o_treino_mudou(conn):
    _salvar(conn, nome="TREINO VELHO")
    marcar_exercicio(conn, 1, 1, 1, "SUPINO RETO", carga="30", agora=AGORA)
    _salvar(conn, nome="TREINO NOVO", fichas=[("A", [_item(2), _item(1)])])  # o supino agora é o 2º exercício

    exercicios = _exercicios(conn, agora=AMANHA)

    assert exercicios[0]["exercicio"] == "CRUCIFIXO" and exercicios[0]["ultima_carga"] == ""
    assert exercicios[1]["exercicio"] == "SUPINO RETO" and exercicios[1]["ultima_carga"] == "30"


def test_exercicio_trocado_no_meio_do_dia_nao_herda_a_marca(conn):
    _salvar(conn, nome="TREINO VELHO")
    marcar_exercicio(conn, 1, 1, 1, "SUPINO RETO", feito=True, carga="30", agora=AGORA)
    _salvar(conn, nome="TREINO NOVO", fichas=[("A", [_item(6), _item(2)])])  # no lugar 1 agora é a esteira

    primeiro = _exercicios(conn)[0]

    assert primeiro["exercicio"] == "ESTEIRA" and primeiro["feito"] is False and primeiro["carga_hoje"] == ""


def test_professor_inclui_exercicio_no_comeco_e_as_marcas_do_aluno_acompanham_os_nomes(conn):
    """O caso do revisor: o aluno anotou SUPINO e CRUCIFIXO; o professor põe ESTEIRA na frente e as posições andam."""
    _salvar(conn, nome="TREINO VELHO")
    marcar_exercicio(conn, 1, 1, 1, "SUPINO RETO", feito=True, carga="30", agora=AGORA)
    marcar_exercicio(conn, 1, 1, 2, "CRUCIFIXO", carga="12", agora=AGORA)
    _salvar(conn, nome="TREINO NOVO", fichas=[("A", [_item(6), _item(1), _item(2)])])  # esteira, supino, crucifixo

    esteira, supino, crucifixo = _exercicios(conn)

    assert (esteira["feito"], esteira["carga_hoje"]) == (False, "")
    assert (supino["feito"], supino["carga_hoje"]) == (True, "30")  # continua valendo, mesmo na posição 2
    assert (crucifixo["feito"], crucifixo["carga_hoje"]) == (False, "12")
    # e o que ele anota agora não apaga o que já estava lá:
    marcar_exercicio(conn, 1, 1, 1, "ESTEIRA", feito=True, agora=AGORA)
    marcar_exercicio(conn, 1, 1, 2, "SUPINO RETO", carga="32", agora=AGORA)
    esteira, supino, crucifixo = _exercicios(conn)
    assert (esteira["feito"], supino["carga_hoje"], crucifixo["carga_hoje"]) == (True, "32", "12")


def test_o_que_o_aluno_anotou_do_exercicio_que_saiu_vira_a_ultima_vez_de_amanha(conn):
    _salvar(conn, nome="TREINO VELHO")
    marcar_exercicio(conn, 1, 1, 2, "CRUCIFIXO", carga="12", agora=AGORA)
    _salvar(conn, nome="TREINO NOVO", fichas=[("A", [_item(6), _item(2)])])
    marcar_exercicio(conn, 1, 1, 2, "CRUCIFIXO", carga="14", agora=AGORA)  # mesmo exercício, outro lugar: atualiza a mesma linha

    amanha = _exercicios(conn, agora=AMANHA)

    assert amanha[1]["exercicio"] == "CRUCIFIXO" and amanha[1]["ultima_carga"] == "14"
    assert conn.execute("SELECT COUNT(*) FROM execucao WHERE exercicio_nome = 'CRUCIFIXO'").fetchone()[0] == 1


def test_exercicio_repetido_na_mesma_ficha_guarda_cada_ocorrencia_separada(conn):
    _salvar(conn, fichas=[("A", [_item(1), _item(2), _item(1)])])  # supino, crucifixo, supino de novo

    marcar_exercicio(conn, 1, 1, 1, "SUPINO RETO", carga="30", agora=AGORA)
    marcar_exercicio(conn, 1, 1, 3, "SUPINO RETO", carga="20", feito=True, agora=AGORA)

    primeiro, meio, terceiro = _exercicios(conn)
    assert (primeiro["carga_hoje"], primeiro["feito"]) == ("30", False)
    assert (meio["carga_hoje"], meio["feito"]) == ("", False)
    assert (terceiro["carga_hoje"], terceiro["feito"]) == ("20", True)


def test_duas_cargas_do_mesmo_exercicio_no_mesmo_dia_valem_a_ultima_anotada(conn):
    _salvar(conn, fichas=[("A", [_item(1)]), ("B", [_item(1)])])
    marcar_exercicio(conn, 1, 1, 1, "SUPINO RETO", carga="40", agora=ONTEM)
    marcar_exercicio(conn, 1, 2, 1, "SUPINO RETO", carga="60", agora=ONTEM + timedelta(minutes=30))
    marcar_exercicio(conn, 1, 1, 1, "SUPINO RETO", carga="45", agora=ONTEM + timedelta(minutes=10))  # corrigiu antes da outra ficha

    assert _exercicios(conn)[0]["ultima_carga"] == "60"
    marcar_exercicio(conn, 1, 1, 1, "SUPINO RETO", carga="42", agora=ONTEM + timedelta(hours=2))  # corrigiu depois

    assert _exercicios(conn)[0]["ultima_carga"] == "42"


@pytest.mark.parametrize("numero", [2**63, 2**70, 10_000])
def test_numero_de_ficha_ou_de_exercicio_enorme_da_400_e_nao_estoura(conn, numero):
    treino_id = _salvar(conn)
    marcar_ficha_feita(conn, 1, 1, AGORA)

    for chamada in (
        lambda: marcar_exercicio(conn, 1, numero, 1, "SUPINO RETO", feito=True, agora=AGORA),
        lambda: marcar_exercicio(conn, 1, 1, numero, "SUPINO RETO", feito=True, agora=AGORA),
        lambda: definir_esforco(conn, 1, numero, 2, AGORA),
        lambda: marcar_ficha_feita(conn, 1, numero, AGORA),
        lambda: desfazer_marcacao_de_hoje(conn, 1, numero, AGORA),
    ):
        with pytest.raises(MarcacaoInvalida) as erro:
            chamada()
        assert erro.value.status == 400
    assert _nada_gravado(conn) and treino_id


def test_cada_aluno_so_ve_as_proprias_marcas(conn):
    _salvar(conn, aluno_id=1)
    _salvar(conn, aluno_id=2, nome="TREINO DO BRUNO")
    marcar_exercicio(conn, 1, 1, 1, "SUPINO RETO", feito=True, carga="30", agora=AGORA)

    bruno = _exercicios(conn, aluno_id=2)[0]

    assert bruno["feito"] is False and bruno["carga_hoje"] == ""
    marcar_exercicio(conn, 2, 1, 1, "SUPINO RETO", carga="80", agora=ONTEM)
    assert _exercicios(conn, aluno_id=1)[0]["ultima_carga"] == ""
    assert _exercicios(conn, aluno_id=2)[0]["ultima_carga"] == "80"


# ------------------------------------------------------------------ marcar_exercicio recusa o que não confere


def _nada_gravado(conn):
    return conn.execute("SELECT COUNT(*) FROM execucao").fetchone()[0] == 0


@pytest.mark.parametrize(
    ("ficha", "item", "exercicio"),
    [(0, 1, "SUPINO RETO"), (True, 1, "SUPINO RETO"), ("1", 1, "SUPINO RETO"), (1, 0, "SUPINO RETO"), (1, True, "SUPINO RETO"), (1, 1.5, "SUPINO RETO"), (1, 1, ""), (1, 1, None), (1, 1, 5), (None, None, None)],
)
def test_lugar_malformado_da_400(conn, ficha, item, exercicio):
    _salvar(conn)

    with pytest.raises(MarcacaoInvalida) as erro:
        marcar_exercicio(conn, 1, ficha, item, exercicio, feito=True, agora=AGORA)

    assert erro.value.status == 400 and _nada_gravado(conn)


def test_pedido_sem_feito_e_sem_carga_da_400(conn):
    _salvar(conn)

    with pytest.raises(MarcacaoInvalida) as erro:
        marcar_exercicio(conn, 1, 1, 1, "SUPINO RETO", agora=AGORA)

    assert erro.value.status == 400


@pytest.mark.parametrize("feito", ["true", 1, 0, None, "sim", [True]])
def test_feito_que_nao_e_verdadeiro_ou_falso_da_400(conn, feito):
    _salvar(conn)

    with pytest.raises(MarcacaoInvalida) as erro:
        marcar_exercicio(conn, 1, 1, 1, "SUPINO RETO", feito=feito, agora=AGORA)

    assert erro.value.status == 400 and _nada_gravado(conn)


@pytest.mark.parametrize("carga", ["muito", "20 kg", "-3", "0", "1000", 20, True])
def test_carga_ruim_da_400_com_a_mensagem_pronta(conn, carga):
    _salvar(conn)

    with pytest.raises(MarcacaoInvalida) as erro:
        marcar_exercicio(conn, 1, 1, 1, "SUPINO RETO", carga=carga, agora=AGORA)

    assert erro.value.status == 400 and str(erro.value) and _nada_gravado(conn)


def test_carga_vazia_e_aceita_e_apaga(conn):
    _salvar(conn)
    marcar_exercicio(conn, 1, 1, 1, "SUPINO RETO", carga="30", agora=AGORA)

    resposta = marcar_exercicio(conn, 1, 1, 1, "SUPINO RETO", carga="", agora=AGORA)

    assert resposta == {"feito": False, "carga_hoje": ""} and _nada_gravado(conn)


@pytest.mark.parametrize(
    ("ficha", "item", "exercicio"),
    [(1, 1, "CRUCIFIXO"), (1, 9, "SUPINO RETO"), (9, 1, "SUPINO RETO"), (2, 1, "SUPINO RETO"), (1, 1, "supino reto")],
)
def test_exercicio_que_o_aluno_nao_esta_vendo_da_409(conn, ficha, item, exercicio):
    _salvar(conn)

    with pytest.raises(MarcacaoInvalida) as erro:
        marcar_exercicio(conn, 1, ficha, item, exercicio, feito=True, agora=AGORA)

    assert erro.value.status == 409 and _nada_gravado(conn)


def test_aluno_sem_treino_ativo_da_409(conn):
    with pytest.raises(MarcacaoInvalida) as erro:
        marcar_exercicio(conn, 1, 1, 1, "SUPINO RETO", feito=True, agora=AGORA)

    assert erro.value.status == 409


def test_treino_concluido_nao_recebe_marcas(conn):
    treino_id = _salvar(conn)
    ciclo.concluir_treino(conn, treino_id)

    with pytest.raises(MarcacaoInvalida) as erro:
        marcar_exercicio(conn, 1, 1, 1, "SUPINO RETO", feito=True, agora=AGORA)

    assert erro.value.status == 409 and _nada_gravado(conn)


def test_marcar_so_mexe_no_proprio_aluno(conn):
    _salvar(conn, aluno_id=1)
    _salvar(conn, aluno_id=2, nome="TREINO DO BRUNO")

    marcar_exercicio(conn, 2, 1, 1, "SUPINO RETO", feito=True, agora=AGORA)

    assert [l[0] for l in _linhas(conn)] == [2]


# ------------------------------------------------------------------ a nota de esforço


def test_esforco_vai_na_conclusao_de_hoje_e_aparece_no_treino(conn):
    _salvar(conn)
    marcar_ficha_feita(conn, 1, 1, AGORA)

    resposta = definir_esforco(conn, 1, 1, 3, AGORA)

    assert resposta == {"ficha": 1, "esforco": 3}
    assert treino_do_aluno(conn, 1, AGORA)["fichas"][0]["esforco_hoje"] == 3
    assert treino_do_aluno(conn, 1, AGORA)["fichas"][1]["esforco_hoje"] is None
    assert conn.execute("SELECT esforco FROM sessao").fetchone()[0] == 3


def test_esforco_pode_ser_trocado_e_apagado(conn):
    _salvar(conn)
    marcar_ficha_feita(conn, 1, 1, AGORA)

    definir_esforco(conn, 1, 1, 1, AGORA)
    definir_esforco(conn, 1, 1, 2, AGORA)
    assert treino_do_aluno(conn, 1, AGORA)["fichas"][0]["esforco_hoje"] == 2
    definir_esforco(conn, 1, 1, None, AGORA)

    assert treino_do_aluno(conn, 1, AGORA)["fichas"][0]["esforco_hoje"] is None


def test_esforco_sem_concluir_a_ficha_da_409(conn):
    _salvar(conn)

    with pytest.raises(MarcacaoInvalida) as erro:
        definir_esforco(conn, 1, 1, 2, AGORA)

    assert erro.value.status == 409


@pytest.mark.parametrize("esforco", [0, 4, -1, "2", "Leve", True, False, 1.5, 2.0, [1], {"a": 1}])
def test_esforco_fora_de_leve_ideal_pesado_da_400(conn, esforco):
    _salvar(conn)
    marcar_ficha_feita(conn, 1, 1, AGORA)

    with pytest.raises(MarcacaoInvalida) as erro:
        definir_esforco(conn, 1, 1, esforco, AGORA)

    assert erro.value.status == 400
    assert conn.execute("SELECT esforco FROM sessao").fetchone()[0] is None


@pytest.mark.parametrize("ficha", [0, True, "1", None])
def test_esforco_com_ficha_malformada_da_400(conn, ficha):
    _salvar(conn)

    with pytest.raises(MarcacaoInvalida) as erro:
        definir_esforco(conn, 1, ficha, 2, AGORA)

    assert erro.value.status == 400


def test_esforco_de_ficha_que_nao_existe_da_404(conn):
    _salvar(conn)

    with pytest.raises(MarcacaoInvalida) as erro:
        definir_esforco(conn, 1, 9, 2, AGORA)

    assert erro.value.status == 404


def test_esforco_so_mexe_na_conclusao_de_hoje_e_na_ficha_pedida(conn):
    _salvar(conn)
    marcar_ficha_feita(conn, 1, 1, ONTEM)
    definir_esforco(conn, 1, 1, 3, ONTEM)
    marcar_ficha_feita(conn, 1, 1, AGORA)
    marcar_ficha_feita(conn, 1, 2, AGORA)

    definir_esforco(conn, 1, 1, 1, AGORA)

    notas = [tuple(l) for l in conn.execute("SELECT ficha_ordem, feita_em, esforco FROM sessao ORDER BY id")]
    assert [n[2] for n in notas] == [3, 1, None]


def test_esforco_so_mexe_no_proprio_aluno(conn):
    _salvar(conn, aluno_id=1)
    _salvar(conn, aluno_id=2, nome="TREINO DO BRUNO")
    marcar_ficha_feita(conn, 2, 1, AGORA)

    with pytest.raises(MarcacaoInvalida) as erro:
        definir_esforco(conn, 1, 1, 2, AGORA)  # a Ana não concluiu nada hoje

    assert erro.value.status == 409
    assert conn.execute("SELECT esforco FROM sessao").fetchone()[0] is None


def test_desfazer_a_conclusao_leva_a_nota_junto(conn):
    _salvar(conn)
    marcar_ficha_feita(conn, 1, 1, AGORA)
    definir_esforco(conn, 1, 1, 3, AGORA)

    desfazer_marcacao_de_hoje(conn, 1, 1, AGORA)
    marcar_ficha_feita(conn, 1, 1, AGORA)

    assert treino_do_aluno(conn, 1, AGORA)["fichas"][0]["esforco_hoje"] is None


def test_concluir_de_novo_no_mesmo_dia_nao_apaga_a_nota(conn):
    _salvar(conn)
    marcar_ficha_feita(conn, 1, 1, AGORA)
    definir_esforco(conn, 1, 1, 2, AGORA)

    marcar_ficha_feita(conn, 1, 1, AGORA)  # toque repetido

    assert treino_do_aluno(conn, 1, AGORA)["fichas"][0]["esforco_hoje"] == 2


# ------------------------------------------------------------------ as rotas


@pytest.fixture
def cliente_da_ana(caminho):
    app = criar_app(caminho)
    conn = conectar(caminho)
    with conn:
        token = aluno_acesso._criar_sessao(conn, 1, datetime.now(timezone.utc))
    conn.close()
    cliente = app.test_client()
    cliente.set_cookie(aluno_acesso.NOME_DO_COOKIE, token)
    return cliente


def _com_treino(caminho):
    conn = conectar(caminho)
    _salvar(conn)
    conn.close()


def _exercicio_pela_rota(cliente, ficha=0, indice=0):
    treino = cliente.get("/api/aluno/treino").get_json()["treino"]
    return [e for g in treino["fichas"][ficha]["grupos"] for e in g["exercicios"]][indice]


def test_rotas_sem_login_respondem_401(caminho):
    cliente = criar_app(caminho).test_client()

    assert cliente.post("/api/aluno/exercicio", json={"ficha": 1, "item": 1, "exercicio": "SUPINO RETO", "feito": True}).status_code == 401
    assert cliente.post("/api/aluno/treino/esforco", json={"ficha": 1, "esforco": 2}).status_code == 401


def test_marcar_e_anotar_pela_rota(caminho, cliente_da_ana):
    _com_treino(caminho)
    corpo = {"ficha": 1, "item": 1, "exercicio": "SUPINO RETO"}

    marcou = cliente_da_ana.post("/api/aluno/exercicio", json={**corpo, "feito": True})
    anotou = cliente_da_ana.post("/api/aluno/exercicio", json={**corpo, "carga": "32,5"})
    depois = _exercicio_pela_rota(cliente_da_ana)
    desmarcou = cliente_da_ana.post("/api/aluno/exercicio", json={**corpo, "feito": False})

    assert marcou.status_code == 200 and marcou.get_json() == {"ok": True, "feito": True, "carga_hoje": ""}
    assert anotou.get_json() == {"ok": True, "feito": True, "carga_hoje": "32,5"}
    assert depois["feito"] is True and depois["carga_hoje"] == "32,5"
    assert desmarcou.get_json() == {"ok": True, "feito": False, "carga_hoje": "32,5"}


def test_esforco_pela_rota(caminho, cliente_da_ana):
    _com_treino(caminho)

    antes = cliente_da_ana.post("/api/aluno/treino/esforco", json={"ficha": 1, "esforco": 2})
    cliente_da_ana.post("/api/aluno/treino/feito", json={"ficha": 1})
    nota = cliente_da_ana.post("/api/aluno/treino/esforco", json={"ficha": 1, "esforco": 3})
    ficha = cliente_da_ana.get("/api/aluno/treino").get_json()["treino"]["fichas"][0]
    apagou = cliente_da_ana.post("/api/aluno/treino/esforco", json={"ficha": 1, "esforco": None})

    assert antes.status_code == 409
    assert nota.status_code == 200 and nota.get_json() == {"ok": True, "ficha": 1, "esforco": 3}
    assert ficha["esforco_hoje"] == 3
    assert apagou.get_json() == {"ok": True, "ficha": 1, "esforco": None}


@pytest.mark.parametrize("corpo", [{}, [], "x", 7, {"ficha": 1, "item": 1, "exercicio": "SUPINO RETO"}, {"ficha": 1, "item": 1, "feito": True}])
def test_corpo_estranho_na_rota_do_exercicio_da_400_e_nao_grava(caminho, cliente_da_ana, corpo):
    _com_treino(caminho)

    resposta = cliente_da_ana.post("/api/aluno/exercicio", json=corpo)

    assert resposta.status_code == 400
    conn = conectar(caminho)
    assert _nada_gravado(conn)
    conn.close()


@pytest.mark.parametrize("rota", ["/api/aluno/treino/esforco", "/api/aluno/treino/feito", "/api/aluno/treino/desfazer"])
def test_numero_de_ficha_enorme_na_rota_da_400_em_json_e_nao_500(caminho, cliente_da_ana, rota):
    _com_treino(caminho)

    resposta = cliente_da_ana.post(rota, json={"ficha": 2**63, "esforco": 2})

    assert resposta.status_code == 400 and resposta.is_json


@pytest.mark.parametrize("corpo", [{}, [], "x", 7, {"ficha": 1}, {"ficha": 1, "esforco": 9}, {"ficha": "1", "esforco": 1}])
def test_corpo_estranho_na_rota_do_esforco_da_400(caminho, cliente_da_ana, corpo):
    _com_treino(caminho)
    cliente_da_ana.post("/api/aluno/treino/feito", json={"ficha": 1})

    resposta = cliente_da_ana.post("/api/aluno/treino/esforco", json=corpo)

    assert resposta.status_code == 400
    assert cliente_da_ana.get("/api/aluno/treino").get_json()["treino"]["fichas"][0]["esforco_hoje"] is None


def test_treino_que_mudou_da_409_na_rota(caminho, cliente_da_ana):
    _com_treino(caminho)

    resposta = cliente_da_ana.post("/api/aluno/exercicio", json={"ficha": 1, "item": 1, "exercicio": "CRUCIFIXO", "feito": True})

    assert resposta.status_code == 409 and "Atualize" in resposta.get_json()["erro"]


def test_carga_ruim_na_rota_da_400_com_mensagem(caminho, cliente_da_ana):
    _com_treino(caminho)

    resposta = cliente_da_ana.post("/api/aluno/exercicio", json={"ficha": 1, "item": 1, "exercicio": "SUPINO RETO", "carga": "pesada"})

    assert resposta.status_code == 400 and "número" in resposta.get_json()["erro"]


def test_rotas_exigem_json_e_origem_do_proprio_site(caminho, cliente_da_ana):
    _com_treino(caminho)
    corpo = {"ficha": 1, "item": 1, "exercicio": "SUPINO RETO", "feito": True}

    assert cliente_da_ana.post("/api/aluno/exercicio", data="ficha=1").status_code == 415
    assert cliente_da_ana.post("/api/aluno/treino/esforco", data="ficha=1").status_code == 415
    de_outro_site = cliente_da_ana.post("/api/aluno/exercicio", json=corpo, headers={"Origin": "https://site-malvado.example"})
    assert de_outro_site.status_code == 403
    conn = conectar(caminho)
    assert _nada_gravado(conn)
    conn.close()


def test_o_aluno_nao_marca_no_treino_de_outro_mandando_ids(caminho, cliente_da_ana):
    conn = conectar(caminho)
    _salvar(conn, aluno_id=1)
    _salvar(conn, aluno_id=2, nome="TREINO DO BRUNO")
    conn.close()

    resposta = cliente_da_ana.post(
        "/api/aluno/exercicio",
        json={"ficha": 1, "item": 1, "exercicio": "SUPINO RETO", "feito": True, "aluno_id": 2, "treino_id": 2},
    )

    assert resposta.status_code == 200
    conn = conectar(caminho)
    assert [l[0] for l in _linhas(conn)] == [1]
    conn.close()


def test_o_computador_do_professor_nao_usa_as_rotas_do_aluno(caminho):
    from app import acesso

    conn = conectar(caminho)
    codigo = acesso.gerar_codigo(conn, "Computador dos professores").codigo
    _salvar(conn)
    conn.close()
    professor = criar_app(caminho).test_client()
    assert professor.post("/api/autorizar", json={"codigo": codigo}).status_code == 200

    assert professor.post("/api/aluno/exercicio", json={"ficha": 1, "item": 1, "exercicio": "SUPINO RETO", "feito": True}).status_code == 401
    assert professor.post("/api/aluno/treino/esforco", json={"ficha": 1, "esforco": 2}).status_code == 401


def test_a_resposta_do_treino_continua_sem_ids_nem_dados_do_professor(caminho, cliente_da_ana):
    _com_treino(caminho)
    cliente_da_ana.post("/api/aluno/exercicio", json={"ficha": 1, "item": 1, "exercicio": "SUPINO RETO", "carga": "30"})

    texto = cliente_da_ana.get("/api/aluno/treino").get_data(as_text=True)

    for proibido in ("aluno_id", "exercicio_id", "montado_por", "PROFESSORA", "atualizado_em", '"id"'):
        assert proibido not in texto, proibido
