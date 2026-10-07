"""Testes de app/acesso.py: código de uso único, computador autorizado, limite de tentativas."""

import re
from datetime import datetime, timedelta, timezone

import pytest

from app import acesso
from app.db import conectar, criar_tabelas

AGORA = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)
PADRAO_DO_CODIGO = re.compile(r"^[A-HJKMNP-Z2-9]{5}-[A-HJKMNP-Z2-9]{5}$")


@pytest.fixture
def conn():
    conexao = conectar()
    criar_tabelas(conexao)
    yield conexao
    conexao.close()


def _autorizar(conn, nome="Computador dos professores", agora=AGORA):
    codigo = acesso.gerar_codigo(conn, nome, agora=agora)
    return acesso.autorizar(conn, codigo.codigo, agora=agora)


def _falhar(conn, vezes, agora=AGORA):
    for _ in range(vezes):
        with pytest.raises(acesso.CodigoInvalido):
            acesso.autorizar(conn, "AAAAA-AAAAA", agora=agora)


def _contar(conn, tabela):
    return conn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]


# ------------------------------------------------------------------ pequenas ajudas


@pytest.mark.parametrize(
    "digitado, esperado",
    [
        ("ABCDE-23456", "ABCDE23456"),
        ("abcde-23456", "ABCDE23456"),
        ("  abcde 23456 \n", "ABCDE23456"),
        ("a-b-c-d-e-2-3-4-5-6", "ABCDE23456"),
        ("", ""),
        (None, ""),
        (12345, ""),
        (["ABCDE"], ""),
    ],
)
def test_normalizar_codigo(digitado, esperado):
    assert acesso.normalizar_codigo(digitado) == esperado


def test_formatar_codigo_poe_hifen_no_meio():
    assert acesso.formatar_codigo("ABCDE23456") == "ABCDE-23456"


def test_limpar_nome_tira_espacos_das_pontas_e_repetidos():
    assert acesso.limpar_nome("  Computador   da  recepção ") == "Computador da recepção"


@pytest.mark.parametrize("nome", ["", "   ", "\n\t", None, 5, "x" * 41, "Nome\x00ruim", "Nome\x07"])
def test_limpar_nome_recusa_vazio_longo_demais_e_caractere_de_controle(nome):
    with pytest.raises(acesso.NomeInvalido):
        acesso.limpar_nome(nome)


def test_limpar_nome_aceita_exatamente_40_caracteres():
    assert acesso.limpar_nome("x" * 40) == "x" * 40


# ------------------------------------------------------------------ gerar o código


def test_codigo_gerado_tem_o_formato_e_so_letras_faceis_de_ler(conn):
    for _ in range(200):
        codigo = acesso.gerar_codigo(conn, "Teste").codigo
        assert PADRAO_DO_CODIGO.match(codigo)
        assert not set("ILO01") & set(codigo)


def test_codigos_gerados_sao_todos_diferentes(conn):
    codigos = {acesso.gerar_codigo(conn, "Teste").codigo for _ in range(300)}
    assert len(codigos) == 300


def test_codigo_vale_quinze_minutos(conn):
    gerado = acesso.gerar_codigo(conn, "Teste", agora=AGORA)

    assert gerado.expira_em == AGORA + timedelta(minutes=15)


def test_banco_guarda_so_o_hash_do_codigo(conn):
    gerado = acesso.gerar_codigo(conn, "Teste", agora=AGORA)
    puro = gerado.codigo.replace("-", "")

    linha = conn.execute("SELECT * FROM codigo_de_autorizacao").fetchone()

    assert linha["codigo_hash"] != puro
    assert puro not in "".join(str(v) for v in tuple(linha))
    assert re.fullmatch(r"[0-9a-f]{64}", linha["codigo_hash"])
    assert linha["nome_do_dispositivo"] == "Teste"
    assert linha["usado_em"] is None


def test_nome_invalido_nao_grava_codigo(conn):
    with pytest.raises(acesso.NomeInvalido):
        acesso.gerar_codigo(conn, "   ")
    assert _contar(conn, "codigo_de_autorizacao") == 0


def test_gerar_codigo_apaga_codigos_vencidos_ha_mais_de_um_dia(conn):
    antigo = acesso.gerar_codigo(conn, "Antigo", agora=AGORA - timedelta(days=2))
    recente = acesso.gerar_codigo(conn, "Recente", agora=AGORA - timedelta(hours=1))

    acesso.gerar_codigo(conn, "Novo", agora=AGORA)

    nomes = {l[0] for l in conn.execute("SELECT nome_do_dispositivo FROM codigo_de_autorizacao")}
    assert nomes == {"Recente", "Novo"}
    assert antigo and recente


# ------------------------------------------------------------------ autorizar com o código


def test_codigo_certo_cria_o_dispositivo_com_o_nome_do_codigo(conn):
    autorizacao = _autorizar(conn, "Computador da recepção")

    assert autorizacao.nome == "Computador da recepção"
    assert len(autorizacao.token) >= 43
    linha = conn.execute("SELECT * FROM dispositivo").fetchone()
    assert linha["id"] == autorizacao.dispositivo_id
    assert linha["nome"] == "Computador da recepção"
    assert linha["revogado_em"] is None


def test_banco_guarda_so_o_hash_do_token(conn):
    autorizacao = _autorizar(conn)

    linha = conn.execute("SELECT * FROM dispositivo").fetchone()

    assert linha["token_hash"] != autorizacao.token
    assert autorizacao.token not in "".join(str(v) for v in tuple(linha))
    assert re.fullmatch(r"[0-9a-f]{64}", linha["token_hash"])


def test_tokens_de_computadores_diferentes_sao_diferentes(conn):
    a = _autorizar(conn, "Computador dos professores")
    b = _autorizar(conn, "Computador da recepção")

    assert a.token != b.token
    assert a.dispositivo_id != b.dispositivo_id


def test_aceita_o_codigo_em_minusculas_com_espacos_e_sem_hifen(conn):
    gerado = acesso.gerar_codigo(conn, "Teste", agora=AGORA)
    digitado = " " + gerado.codigo.replace("-", " ").lower() + " "

    assert acesso.autorizar(conn, digitado, agora=AGORA).nome == "Teste"


def test_codigo_so_funciona_uma_vez(conn):
    gerado = acesso.gerar_codigo(conn, "Teste", agora=AGORA)
    acesso.autorizar(conn, gerado.codigo, agora=AGORA)

    with pytest.raises(acesso.CodigoInvalido):
        acesso.autorizar(conn, gerado.codigo, agora=AGORA)
    assert _contar(conn, "dispositivo") == 1


def test_codigo_vale_ate_um_instante_antes_dos_quinze_minutos(conn):
    gerado = acesso.gerar_codigo(conn, "Teste", agora=AGORA)

    acesso.autorizar(conn, gerado.codigo, agora=AGORA + timedelta(minutes=14, seconds=59))

    assert _contar(conn, "dispositivo") == 1


@pytest.mark.parametrize("depois", [timedelta(minutes=15), timedelta(minutes=15, seconds=1), timedelta(days=3)])
def test_codigo_vencido_e_recusado(conn, depois):
    gerado = acesso.gerar_codigo(conn, "Teste", agora=AGORA)

    with pytest.raises(acesso.CodigoInvalido):
        acesso.autorizar(conn, gerado.codigo, agora=AGORA + depois)
    assert _contar(conn, "dispositivo") == 0


@pytest.mark.parametrize(
    "digitado", ["AAAAA-AAAAA", "", "   ", None, 123, ["ABCDE23456"], "ABC", "A" * 50, "'; DROP TABLE dispositivo; --", "%", "ABCDE-2345%"]
)
def test_codigo_errado_ou_estranho_e_recusado_e_conta_como_falha(conn, digitado):
    acesso.gerar_codigo(conn, "Teste", agora=AGORA)

    with pytest.raises(acesso.CodigoInvalido):
        acesso.autorizar(conn, digitado, agora=AGORA)

    assert _contar(conn, "dispositivo") == 0
    assert _contar(conn, "autorizacao_falha") == 1
    assert conn.execute("SELECT usado_em FROM codigo_de_autorizacao").fetchone()[0] is None


def test_codigo_errado_nao_queima_o_codigo_certo(conn):
    gerado = acesso.gerar_codigo(conn, "Teste", agora=AGORA)
    _falhar(conn, 2)

    assert acesso.autorizar(conn, gerado.codigo, agora=AGORA).nome == "Teste"


def test_a_mesma_mensagem_vale_para_errado_usado_e_vencido(conn):
    gerado = acesso.gerar_codigo(conn, "Teste", agora=AGORA)
    acesso.autorizar(conn, gerado.codigo, agora=AGORA)
    vencido = acesso.gerar_codigo(conn, "Outro", agora=AGORA - timedelta(hours=1))

    mensagens = set()
    for digitado in ("AAAAA-AAAAA", gerado.codigo, vencido.codigo):
        with pytest.raises(acesso.CodigoInvalido) as erro:
            acesso.autorizar(conn, digitado, agora=AGORA)
        mensagens.add(str(erro.value))
    assert len(mensagens) == 1


# ------------------------------------------------------------------ limite de tentativas


def test_cinco_erros_seguidos_travam_ate_o_codigo_certo(conn):
    gerado = acesso.gerar_codigo(conn, "Teste", agora=AGORA)
    _falhar(conn, acesso.LIMITE_DE_FALHAS)

    with pytest.raises(acesso.MuitasTentativas):
        acesso.autorizar(conn, gerado.codigo, agora=AGORA)
    assert _contar(conn, "dispositivo") == 0
    assert conn.execute("SELECT usado_em FROM codigo_de_autorizacao").fetchone()[0] is None


def test_quatro_erros_ainda_nao_travam(conn):
    gerado = acesso.gerar_codigo(conn, "Teste", agora=AGORA)
    _falhar(conn, acesso.LIMITE_DE_FALHAS - 1)

    assert acesso.autorizar(conn, gerado.codigo, agora=AGORA).nome == "Teste"


def test_travado_nao_registra_mais_falhas_e_diz_quanto_esperar(conn):
    _falhar(conn, acesso.LIMITE_DE_FALHAS)

    for _ in range(3):
        with pytest.raises(acesso.MuitasTentativas) as erro:
            acesso.autorizar(conn, "AAAAA-AAAAA", agora=AGORA + timedelta(minutes=5))

    assert _contar(conn, "autorizacao_falha") == acesso.LIMITE_DE_FALHAS
    assert 10 * 60 <= erro.value.segundos <= 10 * 60 + 1  # 15 min de janela - 5 já passados


def test_o_tempo_de_espera_conta_a_partir_da_falha_mais_antiga(conn):
    _falhar(conn, 3)  # às 12:00
    _falhar_em = AGORA + timedelta(minutes=5)
    for _ in range(2):
        with pytest.raises(acesso.CodigoInvalido):
            acesso.autorizar(conn, "AAAAA-AAAAA", agora=_falhar_em)  # às 12:05

    with pytest.raises(acesso.MuitasTentativas) as erro:
        acesso.autorizar(conn, "AAAAA-AAAAA", agora=AGORA + timedelta(minutes=6))

    # Destrava quando as falhas de 12:00 saem da janela (12:15), não as de 12:05 (12:20).
    assert 9 * 60 <= erro.value.segundos <= 9 * 60 + 1


def test_a_politica_de_seguranca_e_a_combinada():
    """Se alguém mudar um destes números, tem que ser de propósito (e mudar o teste junto)."""
    assert acesso.VALIDADE_DO_CODIGO == timedelta(minutes=15)
    assert acesso.LIMITE_DE_FALHAS == 5
    assert acesso.JANELA_DE_FALHAS == timedelta(minutes=15)
    assert acesso.VALIDADE_SEM_USO == timedelta(days=90)
    assert acesso.INTERVALO_DE_RENOVACAO == timedelta(hours=1)
    assert acesso.TAMANHO_DO_CODIGO == 10
    assert len(acesso.ALFABETO) == 31 and len(set(acesso.ALFABETO)) == 31


def test_destrava_quando_a_janela_passa(conn):
    gerado = acesso.gerar_codigo(conn, "Teste", agora=AGORA + timedelta(minutes=14))
    _falhar(conn, acesso.LIMITE_DE_FALHAS)
    depois = AGORA + timedelta(minutes=15, seconds=1)

    with pytest.raises(acesso.MuitasTentativas):
        acesso.autorizar(conn, gerado.codigo, agora=AGORA + timedelta(minutes=14, seconds=59))
    assert acesso.autorizar(conn, gerado.codigo, agora=depois).nome == "Teste"


def test_falhas_antigas_sao_apagadas(conn):
    _falhar(conn, 3)

    with pytest.raises(acesso.CodigoInvalido):
        acesso.autorizar(conn, "AAAAA-AAAAA", agora=AGORA + timedelta(hours=1))

    assert _contar(conn, "autorizacao_falha") == 1


def test_sucesso_nao_zera_as_falhas(conn):
    gerado = acesso.gerar_codigo(conn, "Teste", agora=AGORA)
    _falhar(conn, 3)

    acesso.autorizar(conn, gerado.codigo, agora=AGORA)

    assert _contar(conn, "autorizacao_falha") == 3


# ------------------------------------------------------------------ reconhecer o computador


def test_identifica_o_computador_pelo_token(conn):
    autorizacao = _autorizar(conn, "Computador da recepção")

    dispositivo = acesso.identificar(conn, autorizacao.token, agora=AGORA)

    assert dispositivo.id == autorizacao.dispositivo_id
    assert dispositivo.nome == "Computador da recepção"
    assert dispositivo.renovar_cookie is False


def test_os_dois_computadores_sao_reconhecidos_cada_um_pelo_seu_token(conn):
    professores = _autorizar(conn, "Computador dos professores")
    recepcao = _autorizar(conn, "Computador da recepção")

    assert acesso.identificar(conn, professores.token, agora=AGORA).nome == "Computador dos professores"
    assert acesso.identificar(conn, recepcao.token, agora=AGORA).nome == "Computador da recepção"


@pytest.mark.parametrize("token", [None, "", "curto", 123, b"x" * 43, "x" * 43, "x" * 500, "' OR 1=1 --" + "x" * 30])
def test_token_invalido_nao_identifica_ninguem(conn, token):
    _autorizar(conn)

    assert acesso.identificar(conn, token, agora=AGORA) is None


def test_token_nao_e_o_hash_nem_o_id(conn):
    _autorizar(conn)
    hash_guardado = conn.execute("SELECT token_hash FROM dispositivo").fetchone()[0]

    assert acesso.identificar(conn, hash_guardado, agora=AGORA) is None
    assert acesso.identificar(conn, "1" * 43, agora=AGORA) is None


def test_computador_revogado_perde_o_acesso(conn):
    autorizacao = _autorizar(conn)

    assert acesso.revogar(conn, autorizacao.dispositivo_id, agora=AGORA) is True

    assert acesso.identificar(conn, autorizacao.token, agora=AGORA) is None


def test_revogar_um_nao_afeta_o_outro(conn):
    professores = _autorizar(conn, "Computador dos professores")
    recepcao = _autorizar(conn, "Computador da recepção")

    acesso.revogar(conn, professores.dispositivo_id, agora=AGORA)

    assert acesso.identificar(conn, professores.token, agora=AGORA) is None
    assert acesso.identificar(conn, recepcao.token, agora=AGORA).nome == "Computador da recepção"


def test_revogar_duas_vezes_ou_id_que_nao_existe_devolve_false(conn):
    autorizacao = _autorizar(conn)

    assert acesso.revogar(conn, autorizacao.dispositivo_id, agora=AGORA) is True
    assert acesso.revogar(conn, autorizacao.dispositivo_id, agora=AGORA) is False
    assert acesso.revogar(conn, 999, agora=AGORA) is False


def test_computador_sem_uso_por_mais_de_90_dias_perde_a_autorizacao(conn):
    # Dois computadores, um para cada instante: usar um deles já renova o prazo dele.
    no_limite = _autorizar(conn, "No limite")
    passou_do_limite = _autorizar(conn, "Passou do limite")

    assert acesso.identificar(conn, no_limite.token, agora=AGORA + timedelta(days=90)) is not None
    assert (
        acesso.identificar(conn, passou_do_limite.token, agora=AGORA + timedelta(days=90, seconds=1))
        is None
    )


def test_uso_renova_o_prazo_de_90_dias(conn):
    autorizacao = _autorizar(conn)

    no_dia_80 = acesso.identificar(conn, autorizacao.token, agora=AGORA + timedelta(days=80))
    assert no_dia_80.renovar_cookie is True

    assert acesso.identificar(conn, autorizacao.token, agora=AGORA + timedelta(days=160)) is not None


def test_ultimo_uso_so_e_regravado_depois_de_uma_hora(conn):
    autorizacao = _autorizar(conn)

    cedo = acesso.identificar(conn, autorizacao.token, agora=AGORA + timedelta(minutes=59, seconds=59))
    assert cedo.renovar_cookie is False
    assert conn.execute("SELECT ultimo_uso_em FROM dispositivo").fetchone()[0] == "2026-10-07 12:00:00"

    na_hora = acesso.identificar(conn, autorizacao.token, agora=AGORA + timedelta(hours=1))
    assert na_hora.renovar_cookie is True
    assert conn.execute("SELECT ultimo_uso_em FROM dispositivo").fetchone()[0] == "2026-10-07 13:00:00"


def test_relogio_atrasado_nao_quebra_nada(conn):
    autorizacao = _autorizar(conn)

    dispositivo = acesso.identificar(conn, autorizacao.token, agora=AGORA - timedelta(hours=2))

    assert dispositivo is not None and dispositivo.renovar_cookie is False


# ------------------------------------------------------------------ listar


def test_listar_mostra_a_situacao_de_cada_computador(conn):
    ativo = _autorizar(conn, "Ativo")
    revogado = _autorizar(conn, "Revogado")
    _autorizar(conn, "Parado", agora=AGORA - timedelta(days=100))
    acesso.revogar(conn, revogado.dispositivo_id, agora=AGORA)

    linhas = acesso.listar(conn, agora=AGORA)

    assert [(l["nome"], l["situacao"]) for l in linhas] == [
        ("Ativo", "ativo"),
        ("Revogado", "revogado"),
        ("Parado", "vencido"),
    ]
    assert linhas[0]["id"] == ativo.dispositivo_id
    assert linhas[0]["criado_em"] == AGORA


def test_listar_sem_computadores_devolve_lista_vazia(conn):
    assert acesso.listar(conn, agora=AGORA) == []
