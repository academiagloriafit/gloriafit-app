"""Testes de buscar alunos, ficha do aluno e correção do WhatsApp (app/alunos.py)."""

import pytest

from app.alunos import (
    SITUACOES,
    AlunoNaoEncontrado,
    WhatsappInvalido,
    buscar_alunos,
    data_local,
    formatar_cpf,
    formatar_whatsapp,
    obter_ficha,
    salvar_whatsapp,
    validar_whatsapp,
)
from app.db import conectar, criar_tabelas


@pytest.fixture
def conn():
    c = conectar()  # banco na memória, novo a cada teste
    criar_tabelas(c)
    yield c
    c.close()


def _aluno(
    conn, nome, cpf, whatsapp=None, provisorio=0, criado_em="2026-01-01 12:00:00", situacao=None, data4u_id=None
):
    # CPFs de teste, inventados
    return conn.execute(
        "INSERT INTO aluno (nome, cpf, whatsapp, provisorio, criado_em, situacao, data4u_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (nome, cpf, whatsapp, provisorio, criado_em, situacao, data4u_id),
    ).lastrowid


@pytest.fixture
def exercicios(conn):
    return [
        conn.execute("INSERT INTO exercicio (nome, origem) VALUES (?, 'app')", (nome,)).lastrowid
        for nome in ("SUPINO RETO", "CRUCIFIXO", "REMADA", "AGACHAMENTO", "ROSCA DIRETA", "TRICEPS CORDA")
    ]


def _treino(conn, aluno_id, nome, criado_em, montado_por="Ana", fichas=()):
    """fichas: [(nome_da_ficha, [(exercicio_id, bloco, series, reps, carga)])]"""
    treino_id = conn.execute(
        "INSERT INTO treino (aluno_id, nome, montado_por, criado_em) VALUES (?, ?, ?, ?)",
        (aluno_id, nome, montado_por, criado_em),
    ).lastrowid
    for ordem, (nome_ficha, itens) in enumerate(fichas, start=1):
        ficha_id = conn.execute(
            "INSERT INTO ficha (treino_id, nome, ordem) VALUES (?, ?, ?)", (treino_id, nome_ficha, ordem)
        ).lastrowid
        for ordem_item, (ex, bloco, series, reps, carga) in enumerate(itens, start=1):
            conn.execute(
                "INSERT INTO ficha_item (ficha_id, ordem, bloco, exercicio_id, series, repeticoes, carga)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ficha_id, ordem_item, bloco, ex, series, reps, carga),
            )
    return treino_id


def _nomes(resultado):
    return [a["nome"] for a in resultado["alunos"]]


# ------------------------------------------------------------------ formatação


def test_formatar_cpf():
    assert formatar_cpf("12345678909") == "123.456.789-09"


def test_formatar_whatsapp_com_11_e_com_10_digitos():
    assert formatar_whatsapp("27988887766") == "(27) 98888-7766"
    assert formatar_whatsapp("2738887766") == "(27) 3888-7766"
    assert formatar_whatsapp(None) is None
    assert formatar_whatsapp("") is None


def test_data_local_converte_de_utc_para_brasilia():
    assert data_local("2026-10-07 15:00:00") == "07/10/2026"
    # 02:30 UTC de 07/10 ainda é 23:30 de 06/10 em Brasília (UTC-3): o dia muda!
    assert data_local("2026-10-07 02:30:00") == "06/10/2026"
    # 03:00 UTC = meia-noite em Brasília: já é o dia seguinte
    assert data_local("2026-10-07 03:00:00") == "07/10/2026"
    assert data_local(None) is None
    assert data_local("") is None


# ------------------------------------------------------------------ busca por nome


@pytest.fixture
def turma(conn):
    _aluno(conn, "MARIA DA SILVA", "11111111111")
    _aluno(conn, "JOÃO PEDRO LIMA", "22222222222")
    _aluno(conn, "Joana Silva Souza", "33333333333")
    _aluno(conn, "CÉLIA ANDRADE", "44444444444", provisorio=1)
    return conn


def test_busca_nao_diferencia_maiuscula_nem_acento(turma):
    assert _nomes(buscar_alunos(turma, "joao")) == ["JOÃO PEDRO LIMA"]
    assert _nomes(buscar_alunos(turma, "CELIA")) == ["CÉLIA ANDRADE"]
    assert _nomes(buscar_alunos(turma, "João")) == ["JOÃO PEDRO LIMA"]


def test_busca_exige_todas_as_palavras_em_qualquer_ordem(turma):
    assert _nomes(buscar_alunos(turma, "silva maria")) == ["MARIA DA SILVA"]
    assert _nomes(buscar_alunos(turma, "silva")) == ["Joana Silva Souza", "MARIA DA SILVA"]
    assert _nomes(buscar_alunos(turma, "silva pedro")) == []


def test_busca_com_texto_vem_em_ordem_alfabetica_sem_acento(turma):
    assert _nomes(buscar_alunos(turma, "a")) == [
        "CÉLIA ANDRADE", "Joana Silva Souza", "JOÃO PEDRO LIMA", "MARIA DA SILVA",
    ]


def test_busca_sem_resultado(turma):
    resultado = buscar_alunos(turma, "zzz")
    assert resultado == {"total": 0, "alunos": []}


def test_curingas_do_like_valem_como_caractere(turma):
    # "%" e "_" no LIKE significam "qualquer coisa"; digitados, precisam valer só como eles mesmos.
    assert buscar_alunos(turma, "%")["total"] == 0
    assert buscar_alunos(turma, "_")["total"] == 0
    assert buscar_alunos(turma, "m_ria")["total"] == 0


def test_texto_de_ataque_vira_so_texto(turma):
    resultado = buscar_alunos(turma, "x' OR '1'='1'; DROP TABLE aluno;--")
    assert resultado["total"] == 0
    assert turma.execute("SELECT COUNT(*) FROM aluno").fetchone()[0] == 4


def test_texto_muito_comprido_e_cortado(turma):
    assert buscar_alunos(turma, "maria " + "x" * 5000)["total"] == 0  # não quebra


def test_resultado_nao_traz_cpf_nem_whatsapp(turma):
    aluno = buscar_alunos(turma, "maria")["alunos"][0]
    assert set(aluno) == {
        "id", "nome", "provisorio", "matricula", "situacao", "situacao_nome", "ultimo_treino", "atualizado_em",
    }


def test_provisorio_aparece_marcado(turma):
    celia = buscar_alunos(turma, "celia")["alunos"][0]
    assert celia["provisorio"] is True
    assert buscar_alunos(turma, "maria")["alunos"][0]["provisorio"] is False


# ------------------------------------------------------------------ busca por CPF


def test_busca_por_cpf_completo_com_ou_sem_pontuacao(turma):
    assert _nomes(buscar_alunos(turma, "22222222222")) == ["JOÃO PEDRO LIMA"]
    assert _nomes(buscar_alunos(turma, "222.222.222-22")) == ["JOÃO PEDRO LIMA"]


def test_busca_por_pedaco_do_cpf(turma):
    assert _nomes(buscar_alunos(turma, "3333")) == ["Joana Silva Souza"]
    assert _nomes(buscar_alunos(turma, "444.444")) == ["CÉLIA ANDRADE"]


def test_busca_por_cpf_inexistente(turma):
    assert buscar_alunos(turma, "99999999999")["total"] == 0


def test_numero_misturado_com_nome_busca_no_nome_e_nao_acha(turma):
    assert buscar_alunos(turma, "maria 111")["total"] == 0


# ------------------------------------------------------------------ busca por matrícula e situação


def test_busca_por_matricula_acha_o_aluno_e_ela_vem_antes_de_quem_so_tem_o_numero_no_cpf(conn):
    com_cpf_parecido = _aluno(conn, "AAA CPF PARECIDO", "00044120000", situacao="A")
    matriculado = _aluno(conn, "ZZZ MATRICULADO", "55555555555", situacao="A", data4u_id=4412)

    resultado = buscar_alunos(conn, "4412")

    assert _nomes(resultado) == ["ZZZ MATRICULADO", "AAA CPF PARECIDO"]  # matrícula igual primeiro
    assert resultado["alunos"][0]["matricula"] == 4412
    assert com_cpf_parecido and matriculado


def test_matricula_so_vale_igual_nao_como_pedaco(conn):
    _aluno(conn, "FULANO", "55555555555", data4u_id=44120)

    assert buscar_alunos(conn, "4412")["total"] == 0
    assert _nomes(buscar_alunos(conn, "44120")) == ["FULANO"]


def test_numero_sem_correspondencia_nao_acha_nada(conn):
    _aluno(conn, "FULANO", "55555555555", data4u_id=10)

    assert buscar_alunos(conn, "999")["total"] == 0


def test_matricula_aceita_ate_9_digitos_e_numero_gigante_nao_estoura(conn):
    _aluno(conn, "NOVE", "55555555555", data4u_id=123456789)
    _aluno(conn, "CPF LONGO", "12345678909")

    assert _nomes(buscar_alunos(conn, "123456789")) == ["NOVE", "CPF LONGO"]
    assert _nomes(buscar_alunos(conn, "1234567890")) == ["CPF LONGO"]  # 10 dígitos: só CPF
    assert buscar_alunos(conn, "9" * 100)["total"] == 0  # 100 dígitos: sem erro de inteiro grande


def test_aluno_sem_cpf_nao_aparece_na_busca_por_cpf_mas_aparece_pelo_nome(conn):
    _aluno(conn, "SEM CPF", None, data4u_id=7, situacao="A")
    _aluno(conn, "COM CPF", "12345678909")

    assert _nomes(buscar_alunos(conn, "123")) == ["COM CPF"]
    assert _nomes(buscar_alunos(conn, "sem cpf")) == ["SEM CPF"]
    # "7": a matrícula 7 vem primeiro; "COM CPF" entra por ter 7 no meio do CPF
    assert _nomes(buscar_alunos(conn, "7")) == ["SEM CPF", "COM CPF"]


def test_com_texto_quem_esta_em_uso_vem_antes_dos_outros(conn):
    _aluno(conn, "ANA 1 DESISTENTE", "10000000001", situacao="D")
    _aluno(conn, "ANA 2 ATIVA", "10000000002", situacao="A")
    _aluno(conn, "ANA 3 PENDENTE", "10000000003", situacao="P")
    _aluno(conn, "ANA 4 PROVISORIA", "10000000004", provisorio=1)
    _aluno(conn, "ANA 5 INATIVA", "10000000005", situacao="I")
    _aluno(conn, "ANA 6 TRANCADA", "10000000006", situacao="T")
    _aluno(conn, "ANA 7 CANCELADA", "10000000007", situacao="C")

    assert _nomes(buscar_alunos(conn, "ana")) == [
        "ANA 2 ATIVA", "ANA 3 PENDENTE", "ANA 4 PROVISORIA", "ANA 6 TRANCADA",
        "ANA 1 DESISTENTE", "ANA 5 INATIVA", "ANA 7 CANCELADA",
    ]


def test_cada_letra_de_situacao_tem_o_seu_nome(conn):
    assert SITUACOES == {
        "A": "Ativo", "T": "Trancado", "P": "Pendente", "D": "Desistente", "I": "Inativo", "C": "Cancelado",
    }
    for letra, nome in SITUACOES.items():
        _aluno(conn, f"ALUNO {letra}", f"1000000000{len(letra)}", situacao=letra)
        achado = buscar_alunos(conn, f"aluno {letra}")["alunos"][0]
        assert (achado["situacao"], achado["situacao_nome"]) == (letra, nome)


def test_aluno_provisorio_ou_sem_situacao_nao_tem_nome_de_situacao(turma):
    celia = buscar_alunos(turma, "celia")["alunos"][0]

    assert celia["situacao"] is None
    assert celia["situacao_nome"] is None
    assert celia["matricula"] is None


# ------------------------------------------------------------------ busca vazia, limite, último treino


def test_sem_texto_a_ordem_e_treino_recente_depois_provisorio_depois_o_resto(conn, exercicios):
    a_ficha = [("TREINO A", [(exercicios[0], None, "3", "10", None)])]
    # criados "ao contrário" de propósito: a ordem não pode vir do id
    desistente = _aluno(conn, "ANA DESISTENTE", "10000000001", situacao="D")
    ativo_b = _aluno(conn, "BRUNO ATIVO", "10000000002", situacao="A")
    ativo_a = _aluno(conn, "ARTUR ATIVO", "10000000003", situacao="A")
    prov_velho = _aluno(conn, "PROV VELHO", "10000000004", provisorio=1, criado_em="2026-09-01 10:00:00")
    prov_novo = _aluno(conn, "PROV NOVO", "10000000005", provisorio=1, criado_em="2026-10-01 10:00:00")
    treino_velho = _aluno(conn, "TREINO VELHO", "10000000006", situacao="D")
    treino_novo = _aluno(conn, "TREINO NOVO", "10000000007", situacao="A")
    _treino(conn, treino_velho, "TREINO A", "2026-09-10 10:00:00", fichas=a_ficha)
    _treino(conn, treino_novo, "TREINO A", "2026-10-05 10:00:00", fichas=a_ficha)

    assert _nomes(buscar_alunos(conn, "")) == [
        "TREINO NOVO",     # quem tem treino: o mais recente primeiro
        "TREINO VELHO",
        "PROV NOVO",       # provisório sem treino: o cadastro mais recente primeiro
        "PROV VELHO",
        "ARTUR ATIVO",     # o resto: em uso antes, em ordem alfabética
        "BRUNO ATIVO",
        "ANA DESISTENTE",
    ]
    assert desistente and ativo_b and ativo_a and prov_velho and prov_novo


def test_sem_texto_com_muitos_alunos_sem_treino_a_ordem_e_estavel(conn):
    # Importação de uma vez só: todos com o mesmo instante de cadastro.
    for i in (3, 1, 2):
        _aluno(conn, f"ALUNO {i}", f"1000000000{i}", situacao="D", criado_em="2026-10-07 05:00:00")

    assert _nomes(buscar_alunos(conn, "")) == ["ALUNO 1", "ALUNO 2", "ALUNO 3"]


def test_limite_e_total(conn):
    for i in range(5):
        _aluno(conn, f"ALUNO {i}", f"2000000000{i}")

    resultado = buscar_alunos(conn, "aluno", limite=2)

    assert resultado["total"] == 5
    assert len(resultado["alunos"]) == 2


@pytest.mark.parametrize("limite, esperado", [(0, 1), (-5, 1), (10_000, 200)])
def test_limite_fora_da_faixa_e_ajustado(conn, limite, esperado):
    for i in range(205):  # mais que o máximo, para o teto de 200 aparecer
        _aluno(conn, f"ALUNO {i}", f"{i:011d}")

    resultado = buscar_alunos(conn, "", limite=limite)

    assert len(resultado["alunos"]) == esperado
    assert resultado["total"] == 205


def test_mostra_o_ultimo_treino_e_a_data_em_horario_de_brasilia(conn, exercicios):
    aluno = _aluno(conn, "MARIANA COSTA", "12345678909")
    fichas = [("TREINO A", [(exercicios[0], None, "3", "10", None)])]
    _treino(conn, aluno, "TREINO A 01/09/26", "2026-09-01 12:00:00", fichas=fichas)
    _treino(conn, aluno, "TREINO AB 07/10/26", "2026-10-07 02:30:00", fichas=fichas)

    mariana = buscar_alunos(conn, "mariana")["alunos"][0]

    assert mariana["ultimo_treino"] == "TREINO AB 07/10/26"
    assert mariana["atualizado_em"] == "06/10/2026"  # 02:30 UTC = 23:30 do dia 06 em Brasília


def test_aluno_sem_treino_tem_campos_vazios(turma):
    maria = buscar_alunos(turma, "maria")["alunos"][0]

    assert maria["ultimo_treino"] is None
    assert maria["atualizado_em"] is None


def test_treinos_no_mesmo_instante_desempatam_pelo_id(conn, exercicios):
    aluno = _aluno(conn, "EMPATE", "40000000001")
    fichas = [("TREINO A", [(exercicios[0], None, "3", "10", None)])]
    _treino(conn, aluno, "PRIMEIRO", "2026-10-07 12:00:00", fichas=fichas)
    _treino(conn, aluno, "SEGUNDO", "2026-10-07 12:00:00", fichas=fichas)

    assert buscar_alunos(conn, "empate")["alunos"][0]["ultimo_treino"] == "SEGUNDO"


def test_aluno_com_varios_treinos_aparece_uma_vez_so(conn, exercicios):
    aluno = _aluno(conn, "VARIOS TREINOS", "50000000001")
    fichas = [("TREINO A", [(exercicios[0], None, "3", "10", None)])]
    for i in range(3):
        _treino(conn, aluno, f"TREINO {i}", f"2026-10-0{i + 1} 12:00:00", fichas=fichas)

    resultado = buscar_alunos(conn, "")

    assert resultado["total"] == 1 and len(resultado["alunos"]) == 1


# ------------------------------------------------------------------ ficha


def test_ficha_de_aluno_que_nao_existe(conn):
    assert obter_ficha(conn, 999) is None


def test_ficha_sem_treino_e_sem_whatsapp(conn):
    aluno = _aluno(conn, "SEM NADA", "12345678909")

    ficha = obter_ficha(conn, aluno)

    assert ficha["nome"] == "SEM NADA"
    assert ficha["cpf"] == "123.456.789-09"
    assert ficha["whatsapp"] is None
    assert ficha["whatsapp_corrigido_no_app"] is False
    assert ficha["provisorio"] is False
    assert ficha["treinos"] == []


def test_ficha_mostra_whatsapp_formatado_e_ids(conn):
    aluno = _aluno(conn, "COM ZAP", "12345678909", whatsapp="27988887766")
    conn.execute("UPDATE aluno SET data4u_id = 4412 WHERE id = ?", (aluno,))

    ficha = obter_ficha(conn, aluno)

    assert ficha["whatsapp"] == "(27) 98888-7766"
    assert ficha["matricula"] == 4412


def test_ficha_traz_situacao_e_matricula(conn):
    aluno = _aluno(conn, "FULANA", "12345678909", situacao="P", data4u_id=5022)

    ficha = obter_ficha(conn, aluno)

    assert (ficha["matricula"], ficha["situacao"], ficha["situacao_nome"]) == (5022, "P", "Pendente")


def test_ficha_de_pessoa_sem_cpf(conn):
    aluno = _aluno(conn, "SEM CPF", None, data4u_id=9)

    assert obter_ficha(conn, aluno)["cpf"] is None


def test_formatar_cpf_vazio_devolve_none():
    assert formatar_cpf(None) is None
    assert formatar_cpf("") is None


def test_ficha_lista_treinos_do_mais_novo_para_o_mais_antigo(conn, exercicios):
    aluno = _aluno(conn, "MARIANA", "12345678909")
    fichas = [("TREINO A", [(exercicios[0], None, "3", "10", None)])]
    _treino(conn, aluno, "VELHO", "2026-08-01 12:00:00", montado_por="Bia", fichas=fichas)
    _treino(conn, aluno, "NOVO", "2026-10-05 12:00:00", montado_por="Ana Paula", fichas=fichas)

    treinos = obter_ficha(conn, aluno)["treinos"]

    assert [t["nome"] for t in treinos] == ["NOVO", "VELHO"]
    assert treinos[0]["montado_por"] == "Ana Paula"
    assert treinos[0]["criado_em"] == "05/10/2026"


def test_ficha_nao_mistura_treinos_de_outro_aluno(conn, exercicios):
    a = _aluno(conn, "ALUNA A", "60000000001")
    b = _aluno(conn, "ALUNO B", "60000000002")
    fichas = [("TREINO A", [(exercicios[0], None, "3", "10", None)])]
    _treino(conn, a, "DA A", "2026-10-01 12:00:00", fichas=fichas)
    _treino(conn, b, "DO B", "2026-10-02 12:00:00", fichas=fichas)

    assert [t["nome"] for t in obter_ficha(conn, a)["treinos"]] == ["DA A"]


def test_ficha_traz_fichas_itens_resumo_e_etiquetas(conn, exercicios):
    s, c, r, ag, ro, tr = exercicios
    aluno = _aluno(conn, "MARIANA", "12345678909")
    _treino(
        conn, aluno, "TREINO AB", "2026-10-05 12:00:00",
        fichas=[
            # 1 solto, um bi-set (c, r), 1 solto, um tri-set (ag, ro, tr)
            ("TREINO A", [
                (s, None, "4", "10", "30"),
                (c, 1, "3", "12", None),
                (r, 1, "3", "12", None),
                (ag, None, "5", "8", "60"),
                (ro, 2, "3", "10", "10"),
                (tr, 2, "3", "10", "15"),
                (s, 2, "3", "10", None),
            ]),
            ("TREINO B", [(s, None, "3", "15", None)]),
        ],
    )

    treino = obter_ficha(conn, aluno)["treinos"][0]
    a, b = treino["fichas"]

    assert [f["nome"] for f in treino["fichas"]] == ["TREINO A", "TREINO B"]
    assert a["resumo"] == "7 exercícios, 1 bi-set, 1 tri-set"
    assert b["resumo"] == "1 exercício"
    assert [i["etiqueta"] for i in a["itens"]] == ["1", "A1", "A2", "4", "B1", "B2", "B3"]
    assert [i["etiqueta"] for i in b["itens"]] == ["1"]
    primeiro = a["itens"][0]
    assert (primeiro["exercicio"], primeiro["series"], primeiro["repeticoes"], primeiro["carga"]) == ("SUPINO RETO", "4", "10", "30")
    assert a["itens"][1]["carga"] is None


def test_resumo_no_plural_e_no_singular_dos_blocos(conn, exercicios):
    s, c, r, *_ = exercicios
    aluno = _aluno(conn, "DOIS BISETS", "70000000001")
    _treino(
        conn, aluno, "T", "2026-10-05 12:00:00",
        fichas=[("TREINO A", [(s, 1, "3", "10", None), (c, 1, "3", "10", None), (r, 2, "3", "10", None), (s, 2, "3", "10", None)])],
    )

    ficha = obter_ficha(conn, aluno)["treinos"][0]["fichas"][0]

    assert ficha["resumo"] == "4 exercícios, 2 bi-sets"


# ------------------------------------------------------------------ WhatsApp


@pytest.mark.parametrize(
    "digitado, esperado",
    [
        ("(27) 98888-7766", "27988887766"),
        ("27988887766", "27988887766"),
        ("27 9 8888 7766", "27988887766"),
        ("27.98888.7766", "27988887766"),
        ("  (27) 3888-7766  ", "2738887766"),
        ("11 98888-7766", "11988887766"),
        ("99 98888-7766", "99988887766"),
    ],
)
def test_validar_whatsapp_aceita_formatos_comuns(digitado, esperado):
    assert validar_whatsapp(digitado) == esperado


@pytest.mark.parametrize(
    "digitado, trecho",
    [
        ("", "Digite o número"),
        ("   ", "Digite o número"),
        (None, "Digite o número"),
        (27988887766, "Digite o número"),
        (["27988887766"], "Digite o número"),
        ("98888-7766", "faltar o DDD"),
        ("8888-7766", "faltar o DDD"),
        ("2798888", "10 ou 11"),
        ("2798888776655", "10 ou 11"),
        ("(10) 98888-7766", "DDD é inválido"),
        ("(01) 3888-7766", "DDD é inválido"),
        ("+55 27 98888-7766", "sem +55"),
        ("27 98888-7766 ramal 2", "sem +55"),
        ("abc", "sem +55"),
        ("27988887766; DROP TABLE aluno", "sem +55"),
    ],
)
def test_validar_whatsapp_recusa_com_mensagem_clara(digitado, trecho):
    with pytest.raises(WhatsappInvalido) as erro:
        validar_whatsapp(digitado)
    assert trecho in str(erro.value)


def test_salvar_whatsapp_grava_so_digitos_e_marca_como_corrigido(conn):
    aluno = _aluno(conn, "MARIANA", "12345678909", whatsapp="27999990000")

    formatado = salvar_whatsapp(conn, aluno, "(27) 98888-7766")

    assert formatado == "(27) 98888-7766"
    linha = conn.execute("SELECT whatsapp, whatsapp_corrigido_no_app FROM aluno WHERE id = ?", (aluno,)).fetchone()
    assert tuple(linha) == ("27988887766", 1)


def test_salvar_whatsapp_em_aluno_sem_numero(conn):
    aluno = _aluno(conn, "SEM NUMERO", "12345678909")

    salvar_whatsapp(conn, aluno, "27988887766")

    assert obter_ficha(conn, aluno)["whatsapp"] == "(27) 98888-7766"


def test_numero_invalido_nao_altera_nada(conn):
    aluno = _aluno(conn, "MARIANA", "12345678909", whatsapp="27999990000")

    with pytest.raises(WhatsappInvalido):
        salvar_whatsapp(conn, aluno, "123")

    linha = conn.execute("SELECT whatsapp, whatsapp_corrigido_no_app FROM aluno WHERE id = ?", (aluno,)).fetchone()
    assert tuple(linha) == ("27999990000", 0)


def test_salvar_whatsapp_so_mexe_no_aluno_certo(conn):
    a = _aluno(conn, "ALUNA A", "80000000001", whatsapp="27911110000")
    b = _aluno(conn, "ALUNO B", "80000000002", whatsapp="27922220000")

    salvar_whatsapp(conn, a, "27988887766")

    assert conn.execute("SELECT whatsapp FROM aluno WHERE id = ?", (b,)).fetchone()[0] == "27922220000"


def test_salvar_whatsapp_de_aluno_que_nao_existe(conn):
    with pytest.raises(AlunoNaoEncontrado):
        salvar_whatsapp(conn, 999, "27988887766")


@pytest.mark.parametrize("numero", ["２７９８８８８７７６６", "٢٧٩٨٨٨٨٧٧٦٦", "(２７) ９８８８８-７７６６"])
def test_whatsapp_com_algarismos_de_outros_alfabetos_e_recusado_e_nao_estoura(conn, numero):
    # \d do Python aceitava esses algarismos e o banco os recusava depois (erro 500).
    aluno = _aluno(conn, "Maria", "11144477735")

    with pytest.raises(WhatsappInvalido):
        salvar_whatsapp(conn, aluno, numero)
    with pytest.raises(WhatsappInvalido):
        validar_whatsapp(numero)


def test_busca_com_algarismos_de_largura_total_nao_quebra(conn):
    _aluno(conn, "Maria", "11144477735")

    assert buscar_alunos(conn, "１１１４４４")["total"] == 0
