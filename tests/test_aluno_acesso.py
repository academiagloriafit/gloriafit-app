"""Testes do login do aluno (app/aluno_acesso.py): código por WhatsApp, senha, sessão e limites de tentativas."""

from datetime import datetime, timedelta, timezone

import pytest

from app import administrador, aluno_acesso, provisorios
from app.aluno_acesso import (
    AlunoLogado,
    CodigoInvalido,
    LimiteDoDia,
    LoginInvalido,
    MuitasTentativas,
    SenhaInvalida,
)
from app.db import conectar, criar_tabelas

AGORA = datetime(2026, 10, 15, 15, 0, 0, tzinfo=timezone.utc)
ENDERECO = "203.0.113.7"
SENHA = "uma senha boa 77"

CPF_ANA = "11144477735"  # ativa, com WhatsApp
CPF_BIA = "52998224725"  # ativa, SEM WhatsApp
CPF_CLO = "39053344705"  # desistente
CPF_REPETIDO = "16899535009"  # dois alunos ativos com o mesmo CPF
CPF_PROVISORIO = "12345678909"  # aluno provisório
CPF_INEXISTENTE = "98765432100"


@pytest.fixture
def conn(tmp_path):
    c = conectar(tmp_path / "aluno.db")
    criar_tabelas(c)
    c.executemany(
        "INSERT INTO aluno (id, nome, cpf, whatsapp, situacao, provisorio) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, "ANA SOUZA", CPF_ANA, "27988887766", "A", 0),
            (2, "BIA LIMA", CPF_BIA, None, "A", 0),
            (3, "CLO DIAS", CPF_CLO, "27977776655", "D", 0),
            (4, "DUDA REIS", CPF_REPETIDO, "27966665544", "A", 0),
            (5, "DUDA REIS (CADASTRO ANTIGO)", CPF_REPETIDO, "27966665544", "A", 0),
            (6, "EVA NOVA", CPF_PROVISORIO, "27955554433", None, 1),
        ],
    )
    c.commit()
    yield c
    c.close()


@pytest.fixture
def sorteios(monkeypatch):
    """Faz o app sortear, nesta ordem, os códigos dados (para testes que dependem de códigos diferentes entre si)."""

    def definir(*codigos):
        fila = iter(codigos)
        monkeypatch.setattr(aluno_acesso.secrets, "randbelow", lambda _limite: next(fila))

    return definir


def _mais(minutes=0, seconds=0, days=0):
    """O instante `AGORA` mais o tempo dado."""
    return AGORA + timedelta(minutes=minutes, seconds=seconds, days=days)


def _pedir(conn, cpf=CPF_ANA, quando=AGORA, endereco=ENDERECO):
    return aluno_acesso.pedir_codigo(conn, cpf, endereco, agora=quando)


def _criar_acesso(conn, cpf=CPF_ANA, senha=SENHA, quando=AGORA, endereco=ENDERECO):
    envio = _pedir(conn, cpf, quando, endereco)
    return aluno_acesso.definir_senha_com_codigo(conn, cpf, envio.codigo, senha, endereco, agora=quando)


def _contar(conn, tabela):
    return conn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]


# ------------------------------------------------------------------ os CPFs de teste são CPFs de verdade


@pytest.mark.parametrize("cpf", [CPF_ANA, CPF_BIA, CPF_CLO, CPF_REPETIDO, CPF_PROVISORIO, CPF_INEXISTENTE])
def test_os_cpfs_usados_nos_testes_passam_na_conferencia_do_app(cpf):
    assert aluno_acesso.validar_cpf(cpf) == cpf


def test_cpf_com_enfeite_e_aceito_e_cpf_errado_levanta_o_erro_do_app():
    assert aluno_acesso.validar_cpf("111.444.777-35") == CPF_ANA
    with pytest.raises(provisorios.CpfInvalido):
        aluno_acesso.validar_cpf("111.444.777-36")


# ------------------------------------------------------------------ pedir o código


def test_pedir_codigo_de_aluno_ativo_cria_um_codigo_de_6_numeros_que_vale_10_minutos(conn):
    envio = _pedir(conn)

    assert envio.aluno_id == 1
    assert envio.whatsapp == "27988887766"
    assert len(envio.codigo) == 6 and envio.codigo.isdigit()
    linha = conn.execute("SELECT * FROM aluno_codigo").fetchone()
    assert linha["id"] == envio.codigo_id
    assert linha["criado_em"] == "2026-10-15 15:00:00"
    assert linha["expira_em"] == "2026-10-15 15:10:00"
    assert (linha["tentativas"], linha["usado_em"], linha["envio"]) == (0, None, "pendente")


def test_o_banco_guarda_so_o_hash_do_codigo(conn):
    envio = _pedir(conn)

    linha = conn.execute("SELECT * FROM aluno_codigo").fetchone()
    assert envio.codigo not in [str(valor) for valor in tuple(linha)]
    assert linha["codigo_hash"] == aluno_acesso._hash_do_codigo(1, envio.codigo)
    assert len(linha["codigo_hash"]) == 64


@pytest.mark.parametrize(
    "cpf",
    [CPF_INEXISTENTE, CPF_BIA, CPF_CLO, CPF_REPETIDO, CPF_PROVISORIO],
    ids=["nao existe", "sem WhatsApp", "desistente", "CPF repetido entre ativos", "provisorio"],
)
def test_quem_nao_pode_receber_codigo_nao_ganha_codigo_mas_o_pedido_e_registrado(conn, cpf):
    assert _pedir(conn, cpf) is None

    assert _contar(conn, "aluno_codigo") == 0
    assert _contar(conn, "aluno_evento") == 2  # um por CPF e um por endereço: o limite vale também para quem não existe


def test_cpf_repetido_com_um_so_ativo_entra_pelo_ativo(conn):
    conn.execute("UPDATE aluno SET situacao = 'D' WHERE id = 5")
    conn.commit()

    assert _pedir(conn, CPF_REPETIDO).aluno_id == 4


def test_novo_pedido_queima_o_codigo_anterior(conn, sorteios):
    sorteios(111111, 222222)
    primeiro = _pedir(conn)
    segundo = _pedir(conn, quando=_mais(minutes=2))
    assert (primeiro.codigo, segundo.codigo) == ("111111", "222222")

    with pytest.raises(CodigoInvalido):
        aluno_acesso.definir_senha_com_codigo(conn, CPF_ANA, primeiro.codigo, SENHA, ENDERECO, agora=_mais(minutes=3))
    entrada = aluno_acesso.definir_senha_com_codigo(conn, CPF_ANA, segundo.codigo, SENHA, ENDERECO, agora=_mais(minutes=3))
    assert entrada.aluno_id == 1


# ------------------------------------------------------------------ limites do pedido de código


def test_so_um_pedido_por_minuto_por_cpf_e_a_espera_sai_na_mensagem(conn):
    _pedir(conn)

    with pytest.raises(MuitasTentativas) as erro:
        _pedir(conn, quando=_mais(seconds=20))

    assert erro.value.segundos == 40
    assert "40 segundos" in erro.value.mensagem
    assert _contar(conn, "aluno_codigo") == 1
    assert _pedir(conn, quando=_mais(seconds=61)) is not None


def test_o_limite_de_um_pedido_por_minuto_vale_tambem_para_cpf_que_nao_existe(conn):
    _pedir(conn, CPF_INEXISTENTE)

    with pytest.raises(MuitasTentativas):
        _pedir(conn, CPF_INEXISTENTE, quando=_mais(seconds=10))


def test_cinco_pedidos_por_dia_por_cpf(conn):
    for i in range(5):
        assert _pedir(conn, quando=_mais(minutes=2 * i)) is not None

    with pytest.raises(MuitasTentativas) as erro:
        _pedir(conn, quando=_mais(minutes=11))
    assert erro.value.segundos > 3600  # só libera quando o primeiro pedido do dia sair da janela de 24 h
    assert _pedir(conn, quando=_mais(days=1, minutes=1)) is not None


def test_limite_por_endereco_pega_quem_testa_muitos_cpfs(conn, monkeypatch):
    monkeypatch.setattr(aluno_acesso, "PEDIDOS_POR_ENDERECO_POR_HORA", 3)
    for i in range(3):
        _pedir(conn, f"0000000000{i}")

    with pytest.raises(MuitasTentativas):
        _pedir(conn, "00000000009")
    assert _pedir(conn, "00000000009", endereco="198.51.100.9") is None  # outro endereço: passa


def test_limite_do_dia_no_app_inteiro_protege_o_gasto_com_mensagens(conn, monkeypatch):
    monkeypatch.setattr(aluno_acesso, "CODIGOS_POR_DIA", 1)
    _pedir(conn)

    with pytest.raises(LimiteDoDia):
        _pedir(conn, "00000000019", quando=_mais(minutes=5))
    assert _contar(conn, "aluno_evento") == 2  # quem foi barrado não alimenta a própria contagem


def test_codigos_e_eventos_antigos_sao_apagados(conn):
    _pedir(conn, CPF_INEXISTENTE)
    _pedir(conn)

    _pedir(conn, quando=_mais(days=8))

    assert _contar(conn, "aluno_codigo") == 1  # o de 8 dias atrás saiu
    assert conn.execute("SELECT COUNT(*) FROM aluno_evento WHERE em < '2026-10-22'").fetchone()[0] == 0


# ------------------------------------------------------------------ primeiro acesso / esqueci a senha


def test_codigo_certo_e_senha_boa_criam_o_acesso_e_ja_deixam_o_aluno_logado(conn):
    envio = _pedir(conn)

    entrada = aluno_acesso.definir_senha_com_codigo(conn, CPF_ANA, envio.codigo, SENHA, ENDERECO, agora=_mais(minutes=1))

    assert (entrada.aluno_id, entrada.nome) == (1, "ANA SOUZA")
    assert aluno_acesso.identificar(conn, entrada.token, agora=_mais(minutes=2)) == AlunoLogado(1, "ANA SOUZA", False)
    assert administrador.hash_confere(SENHA, conn.execute("SELECT senha_hash FROM aluno_senha").fetchone()[0])


def test_o_banco_guarda_so_hash_da_senha_e_do_token(conn):
    entrada = _criar_acesso(conn)

    senha_hash = conn.execute("SELECT senha_hash FROM aluno_senha").fetchone()[0]
    assert senha_hash.startswith("scrypt$") and SENHA not in senha_hash
    sessao = conn.execute("SELECT * FROM aluno_sessao").fetchone()
    assert entrada.token not in [str(valor) for valor in tuple(sessao)]
    assert sessao["token_hash"] == aluno_acesso._hash(entrada.token)


def test_codigo_so_funciona_uma_vez(conn):
    envio = _pedir(conn)
    aluno_acesso.definir_senha_com_codigo(conn, CPF_ANA, envio.codigo, SENHA, ENDERECO, agora=_mais(minutes=1))

    with pytest.raises(CodigoInvalido):
        aluno_acesso.definir_senha_com_codigo(conn, CPF_ANA, envio.codigo, "outra senha 123", ENDERECO, agora=_mais(minutes=2))


def test_codigo_vencido_nao_vale(conn):
    envio = _pedir(conn)

    with pytest.raises(CodigoInvalido):
        aluno_acesso.definir_senha_com_codigo(conn, CPF_ANA, envio.codigo, SENHA, ENDERECO, agora=_mais(minutes=10, seconds=1))
    assert _contar(conn, "aluno_senha") == 0


def test_codigo_de_um_aluno_nao_serve_para_o_cpf_de_outro(conn):
    conn.execute("INSERT INTO aluno (id, nome, cpf, whatsapp, situacao) VALUES (7, 'FABI', '00000000191', '27944443322', 'A')")
    ana = _pedir(conn)

    with pytest.raises(CodigoInvalido):  # a Fabi nunca pediu código
        aluno_acesso.definir_senha_com_codigo(conn, "00000000191", ana.codigo, SENHA, ENDERECO, agora=_mais(minutes=1))
    assert aluno_acesso._hash_do_codigo(1, "123456") != aluno_acesso._hash_do_codigo(7, "123456")  # o id do aluno entra no hash


@pytest.mark.parametrize(
    "formato",
    [lambda c: f"{c[:3]} {c[3:]}", lambda c: f" {c} ", lambda c: f"{c[:3]}-{c[3:]}"],
    ids=["espaco no meio", "espaco nas pontas", "hifen"],
)
def test_o_codigo_digitado_pode_ter_espaco_e_hifen(conn, formato):
    envio = _pedir(conn)

    entrada = aluno_acesso.definir_senha_com_codigo(conn, CPF_ANA, formato(envio.codigo), SENHA, ENDERECO, agora=_mais(minutes=1))

    assert entrada.aluno_id == 1


@pytest.mark.parametrize("digitado", [None, 123456, "", "12345", "1234567", "abcdef", ["123456"], {"a": 1}])
def test_codigo_fora_do_formato_e_recusado(conn, digitado):
    _pedir(conn)

    with pytest.raises(CodigoInvalido):
        aluno_acesso.definir_senha_com_codigo(conn, CPF_ANA, digitado, SENHA, ENDERECO, agora=_mais(minutes=1))


def test_codigo_para_cpf_sem_acesso_da_o_mesmo_erro(conn):
    with pytest.raises(CodigoInvalido):
        aluno_acesso.definir_senha_com_codigo(conn, CPF_INEXISTENTE, "123456", SENHA, ENDERECO, agora=AGORA)


def test_cinco_palpites_errados_matam_o_codigo_mesmo_que_o_limite_do_cpf_fosse_maior(conn, monkeypatch):
    monkeypatch.setattr(aluno_acesso, "FALHAS_POR_CPF", 100)
    monkeypatch.setattr(aluno_acesso, "FALHAS_POR_ENDERECO", 100)
    envio = _pedir(conn)
    errado = "000000" if envio.codigo != "000000" else "111111"

    for i in range(5):
        with pytest.raises(CodigoInvalido):
            aluno_acesso.definir_senha_com_codigo(conn, CPF_ANA, errado, SENHA, ENDERECO, agora=_mais(seconds=i))

    with pytest.raises(CodigoInvalido):  # agora nem o código CERTO funciona
        aluno_acesso.definir_senha_com_codigo(conn, CPF_ANA, envio.codigo, SENHA, ENDERECO, agora=_mais(seconds=10))
    assert conn.execute("SELECT tentativas FROM aluno_codigo").fetchone()[0] == 5


def test_cinco_erros_travam_o_cpf_e_destravam_depois_de_15_minutos(conn):
    envio = _pedir(conn)
    errado = "000000" if envio.codigo != "000000" else "111111"
    for i in range(5):
        with pytest.raises(CodigoInvalido):
            aluno_acesso.definir_senha_com_codigo(conn, CPF_ANA, errado, SENHA, ENDERECO, agora=_mais(seconds=i))

    with pytest.raises(MuitasTentativas) as erro:
        aluno_acesso.definir_senha_com_codigo(conn, CPF_ANA, envio.codigo, SENHA, ENDERECO, agora=_mais(minutes=1))
    assert 13 * 60 < erro.value.segundos <= 15 * 60
    assert "minutos" in erro.value.mensagem

    novo = _pedir(conn, quando=_mais(minutes=16))  # passou a janela: pode pedir outro código e usar
    assert aluno_acesso.definir_senha_com_codigo(conn, CPF_ANA, novo.codigo, SENHA, ENDERECO, agora=_mais(minutes=17)).aluno_id == 1


def test_o_travamento_vale_tambem_para_cpf_que_nao_existe(conn):
    for i in range(5):
        with pytest.raises(CodigoInvalido):
            aluno_acesso.definir_senha_com_codigo(conn, CPF_INEXISTENTE, "123456", SENHA, ENDERECO, agora=_mais(seconds=i))

    with pytest.raises(MuitasTentativas):
        aluno_acesso.definir_senha_com_codigo(conn, CPF_INEXISTENTE, "123456", SENHA, ENDERECO, agora=_mais(seconds=6))


def test_senha_que_nao_serve_nao_gasta_o_codigo_nem_tentativa(conn):
    envio = _pedir(conn)

    with pytest.raises(SenhaInvalida, match="pelo menos 8"):
        aluno_acesso.definir_senha_com_codigo(conn, CPF_ANA, envio.codigo, "curta", ENDERECO, agora=_mais(minutes=1))

    linha = conn.execute("SELECT tentativas, usado_em FROM aluno_codigo").fetchone()
    assert (linha["tentativas"], linha["usado_em"]) == (0, None)
    assert _contar(conn, "aluno_evento") == 2  # só o pedido: nenhum erro registrado
    assert aluno_acesso.definir_senha_com_codigo(conn, CPF_ANA, envio.codigo, SENHA, ENDERECO, agora=_mais(minutes=2)).aluno_id == 1


@pytest.mark.parametrize(
    "senha",
    ["12345678", "ABCD1234", "Academia", "GloriaFit", "senha123", CPF_ANA, "111.444.777-35", "        ", "x" * 129, "com\ttab 12345", None, 12345678],
)
def test_senhas_que_nao_servem(conn, senha):
    envio = _pedir(conn)

    with pytest.raises(SenhaInvalida):
        aluno_acesso.definir_senha_com_codigo(conn, CPF_ANA, envio.codigo, senha, ENDERECO, agora=_mais(minutes=1))


def test_senha_nova_derruba_os_outros_celulares(conn):
    antigo = _criar_acesso(conn)
    assert aluno_acesso.identificar(conn, antigo.token, agora=_mais(minutes=1)) is not None

    novo = _criar_acesso(conn, senha="outra senha 456", quando=_mais(minutes=5))  # "esqueci a senha"

    assert aluno_acesso.identificar(conn, antigo.token, agora=_mais(minutes=6)) is None
    assert aluno_acesso.identificar(conn, novo.token, agora=_mais(minutes=6)) is not None
    assert _contar(conn, "aluno_senha") == 1  # trocou a senha, não criou outra
    with pytest.raises(LoginInvalido):
        aluno_acesso.entrar(conn, CPF_ANA, SENHA, ENDERECO, agora=_mais(minutes=7))
    assert aluno_acesso.entrar(conn, CPF_ANA, "outra senha 456", ENDERECO, agora=_mais(minutes=7)).aluno_id == 1


def test_acertar_o_codigo_zera_os_erros_do_cpf(conn):
    envio = _pedir(conn)
    for _ in range(2):
        with pytest.raises(LoginInvalido):
            aluno_acesso.entrar(conn, CPF_ANA, "errada", ENDERECO, agora=AGORA)
    assert conn.execute("SELECT COUNT(*) FROM aluno_evento WHERE tipo = 'login_errado' AND chave LIKE 'cpf:%'").fetchone()[0] == 2

    aluno_acesso.definir_senha_com_codigo(conn, CPF_ANA, envio.codigo, SENHA, ENDERECO, agora=_mais(minutes=1))

    assert conn.execute("SELECT COUNT(*) FROM aluno_evento WHERE tipo IN ('login_errado', 'codigo_errado') AND chave LIKE 'cpf:%'").fetchone()[0] == 0


# ------------------------------------------------------------------ entrar com CPF e senha


def test_entrar_com_cpf_e_senha_certos(conn):
    _criar_acesso(conn)

    entrada = aluno_acesso.entrar(conn, CPF_ANA, SENHA, ENDERECO, agora=_mais(minutes=30))

    assert (entrada.aluno_id, entrada.nome) == (1, "ANA SOUZA")
    assert aluno_acesso.identificar(conn, entrada.token, agora=_mais(minutes=31)).id == 1
    assert _contar(conn, "aluno_sessao") == 2  # o celular do primeiro acesso e este


@pytest.mark.parametrize("senha", ["senha errada 1", "", None, 12345678, "x" * 5000, SENHA.upper()])
def test_senha_errada_nao_entra(conn, senha):
    _criar_acesso(conn)

    with pytest.raises(LoginInvalido, match="CPF ou senha incorretos"):
        aluno_acesso.entrar(conn, CPF_ANA, senha, ENDERECO, agora=_mais(minutes=30))


def test_a_senha_aceita_acento_digitado_de_dois_jeitos(conn):
    _criar_acesso(conn, senha="coração forte 12")

    assert aluno_acesso.entrar(conn, CPF_ANA, "corac\u0327a\u0303o forte 12", ENDERECO, agora=_mais(minutes=30)).aluno_id == 1


@pytest.mark.parametrize(
    "cpf",
    [CPF_INEXISTENTE, CPF_BIA, CPF_CLO, CPF_REPETIDO],
    ids=["cpf que nao existe", "aluno sem senha", "desistente", "cpf repetido"],
)
def test_quem_nao_pode_entrar_recebe_o_mesmo_erro_e_o_mesmo_trabalho(conn, monkeypatch, cpf):
    _criar_acesso(conn)  # a Ana tem senha; os outros não
    conn.execute("INSERT INTO aluno_senha (aluno_id, senha_hash, definida_em) VALUES (3, ?, '2026-10-01 10:00:00')", (administrador.gerar_hash(SENHA),))
    conn.commit()  # a Clo (desistente) tem senha de quando era ativa: mesmo assim não entra
    chamadas = []
    original = administrador.hash_confere
    monkeypatch.setattr(administrador, "hash_confere", lambda *a: chamadas.append(a) or original(*a))

    with pytest.raises(LoginInvalido, match="CPF ou senha incorretos"):
        aluno_acesso.entrar(conn, cpf, SENHA, ENDERECO, agora=_mais(minutes=30))

    assert len(chamadas) == 1  # o hash lento roda mesmo assim: o tempo de resposta não revela nada


def test_cinco_senhas_erradas_travam_ate_a_senha_certa_e_destravam_em_15_minutos(conn):
    _criar_acesso(conn)
    for i in range(5):
        with pytest.raises(LoginInvalido):
            aluno_acesso.entrar(conn, CPF_ANA, "errada 12345", ENDERECO, agora=_mais(minutes=30, seconds=i))

    with pytest.raises(MuitasTentativas) as erro:
        aluno_acesso.entrar(conn, CPF_ANA, SENHA, ENDERECO, agora=_mais(minutes=31))
    assert 13 * 60 < erro.value.segundos <= 15 * 60

    assert aluno_acesso.entrar(conn, CPF_ANA, SENHA, ENDERECO, agora=_mais(minutes=46)).aluno_id == 1


def test_acertar_a_senha_zera_a_contagem_de_erros(conn):
    _criar_acesso(conn)
    for i in range(4):
        with pytest.raises(LoginInvalido):
            aluno_acesso.entrar(conn, CPF_ANA, "errada 12345", ENDERECO, agora=_mais(minutes=30, seconds=i))
    aluno_acesso.entrar(conn, CPF_ANA, SENHA, ENDERECO, agora=_mais(minutes=31))

    for i in range(4):  # mais 4 erros ainda cabem
        with pytest.raises(LoginInvalido):
            aluno_acesso.entrar(conn, CPF_ANA, "errada 12345", ENDERECO, agora=_mais(minutes=32, seconds=i))


def test_esqueci_a_senha_ignora_o_travamento_de_login(conn):
    _criar_acesso(conn)
    for i in range(5):
        with pytest.raises(LoginInvalido):
            aluno_acesso.entrar(conn, CPF_ANA, "errada 12345", ENDERECO, agora=_mais(minutes=30, seconds=i))
    with pytest.raises(MuitasTentativas):
        aluno_acesso.entrar(conn, CPF_ANA, SENHA, ENDERECO, agora=_mais(minutes=31))

    nova = _criar_acesso(conn, senha="senha nova 7654", quando=_mais(minutes=32))  # prova que tem o WhatsApp: destrava

    assert nova.aluno_id == 1
    assert aluno_acesso.entrar(conn, CPF_ANA, "senha nova 7654", ENDERECO, agora=_mais(minutes=33)).aluno_id == 1


def test_o_limite_por_endereco_trava_quem_testa_varios_cpfs_com_senha_errada(conn, monkeypatch):
    monkeypatch.setattr(aluno_acesso, "FALHAS_POR_ENDERECO", 3)
    for i in range(3):
        with pytest.raises(LoginInvalido):
            aluno_acesso.entrar(conn, f"0000000000{i}", "qualquer coisa 1", ENDERECO, agora=_mais(seconds=i))

    with pytest.raises(MuitasTentativas):
        aluno_acesso.entrar(conn, CPF_ANA, SENHA, ENDERECO, agora=_mais(seconds=10))


# ------------------------------------------------------------------ a sessão (o celular logado)


@pytest.mark.parametrize("token", [None, "", "lixo", "x" * 43, 123, b"bytes", ["a"]])
def test_token_falso_nao_identifica_ninguem(conn, token):
    _criar_acesso(conn)

    assert aluno_acesso.identificar(conn, token, agora=_mais(minutes=1)) is None


@pytest.mark.parametrize("minutos_depois, vale", [(90 * 24 * 60, True), (90 * 24 * 60 + 1, False)], ids=["90 dias exatos", "90 dias e 1 minuto"])
def test_sessao_sem_uso_por_mais_de_90_dias_perde_o_acesso(conn, minutos_depois, vale):
    entrada = _criar_acesso(conn)

    achou = aluno_acesso.identificar(conn, entrada.token, agora=_mais(minutes=minutos_depois))

    assert (achou is not None) is vale


def test_o_ultimo_uso_so_e_regravado_uma_vez_por_hora(conn):
    entrada = _criar_acesso(conn)

    cedo = aluno_acesso.identificar(conn, entrada.token, agora=_mais(minutes=59))
    tarde = aluno_acesso.identificar(conn, entrada.token, agora=_mais(minutes=61))
    logo_depois = aluno_acesso.identificar(conn, entrada.token, agora=_mais(minutes=62))

    assert [a.renovar_cookie for a in (cedo, tarde, logo_depois)] == [False, True, False]
    assert conn.execute("SELECT ultimo_uso_em FROM aluno_sessao").fetchone()[0] == "2026-10-15 16:01:00"


def test_uso_frequente_mantem_a_sessao_viva_alem_de_90_dias(conn):
    entrada = _criar_acesso(conn)
    for semana in range(1, 20):  # 19 semanas = 133 dias, abrindo o app toda semana
        assert aluno_acesso.identificar(conn, entrada.token, agora=_mais(days=7 * semana)) is not None


@pytest.mark.parametrize("situacao", ["D", "I", "C", "T", "P", None])
def test_aluno_que_deixa_de_estar_ativo_perde_o_acesso_na_hora(conn, situacao):
    entrada = _criar_acesso(conn)
    conn.execute("UPDATE aluno SET situacao = ? WHERE id = 1", (situacao,))
    conn.commit()  # a cópia diária do Data4U mudou a situação

    assert aluno_acesso.identificar(conn, entrada.token, agora=_mais(minutes=1)) is None
    with pytest.raises(LoginInvalido):
        aluno_acesso.entrar(conn, CPF_ANA, SENHA, ENDERECO, agora=_mais(minutes=2))


def test_aluno_que_volta_a_ficar_ativo_volta_a_entrar_com_a_mesma_senha(conn):
    _criar_acesso(conn)
    conn.execute("UPDATE aluno SET situacao = 'T' WHERE id = 1")
    conn.commit()
    conn.execute("UPDATE aluno SET situacao = 'A' WHERE id = 1")
    conn.commit()

    assert aluno_acesso.entrar(conn, CPF_ANA, SENHA, ENDERECO, agora=_mais(days=3)).aluno_id == 1


def test_sair_revoga_so_aquele_celular(conn):
    primeiro = _criar_acesso(conn)
    segundo = aluno_acesso.entrar(conn, CPF_ANA, SENHA, ENDERECO, agora=_mais(minutes=5))

    aluno_acesso.sair(conn, primeiro.token, agora=_mais(minutes=6))

    assert aluno_acesso.identificar(conn, primeiro.token, agora=_mais(minutes=7)) is None
    assert aluno_acesso.identificar(conn, segundo.token, agora=_mais(minutes=7)) is not None


@pytest.mark.parametrize("token", [None, "", "nao existe", 5])
def test_sair_com_token_que_nao_existe_nao_faz_nada(conn, token):
    _criar_acesso(conn)

    aluno_acesso.sair(conn, token, agora=_mais(minutes=1))

    assert conn.execute("SELECT COUNT(*) FROM aluno_sessao WHERE revogado_em IS NULL").fetchone()[0] == 1


def test_sessoes_velhas_do_mesmo_aluno_sao_apagadas_ao_entrar(conn):
    _criar_acesso(conn)

    aluno_acesso.entrar(conn, CPF_ANA, SENHA, ENDERECO, agora=_mais(days=100))

    assert _contar(conn, "aluno_sessao") == 1  # a de 100 dias atrás já tinha vencido


def test_cada_sessao_tem_um_token_diferente(conn):
    tokens = {_criar_acesso(conn, quando=_mais(minutes=2 * i)).token for i in range(3)}

    assert len(tokens) == 3 and all(len(t) >= 43 for t in tokens)


# ------------------------------------------------------------------ mandar o código (em segundo plano)


class RemetenteFalso:
    def __init__(self, erro=None):
        self.erro = erro
        self.enviados = []

    def pronto(self):
        return True

    def enviar(self, whatsapp, codigo):
        if self.erro is not None:
            raise self.erro
        self.enviados.append((whatsapp, codigo))
        return "wamid.TESTE"


def _caminho(conn):
    return conn.execute("PRAGMA database_list").fetchone()[2]


def test_envio_que_a_meta_aceita_fica_como_enviado(conn):
    envio = _pedir(conn)
    remetente = RemetenteFalso()

    assert aluno_acesso.executar_envio(_caminho(conn), envio, remetente) is True

    assert remetente.enviados == [("27988887766", envio.codigo)]
    linha = conn.execute("SELECT envio, envio_erro FROM aluno_codigo").fetchone()
    assert (linha["envio"], linha["envio_erro"]) == ("enviado", None)


def test_envio_que_falha_fica_como_falhou_com_o_motivo_sem_o_codigo_nem_o_numero(conn, caplog):
    from app.whatsapp import EnvioFalhou

    envio = _pedir(conn)
    erro = EnvioFalhou("A Meta recusou.", f"HTTP 400 código=131030: número 27988887766 fora da lista; código {envio.codigo}")

    with caplog.at_level("WARNING"):
        assert aluno_acesso.executar_envio(_caminho(conn), envio, RemetenteFalso(erro)) is False

    linha = conn.execute("SELECT envio, envio_erro FROM aluno_codigo").fetchone()
    assert linha["envio"] == "falhou"
    assert "131030" in linha["envio_erro"]
    assert envio.codigo not in linha["envio_erro"] and "27988887766" not in linha["envio_erro"]
    assert envio.codigo not in caplog.text and "27988887766" not in caplog.text
    assert "não foi enviado" in caplog.text


def test_erro_inesperado_no_envio_tambem_so_anota_e_nao_derruba_o_fio(conn):
    envio = _pedir(conn)

    assert aluno_acesso.executar_envio(_caminho(conn), envio, RemetenteFalso(RuntimeError("estourou"))) is False

    linha = conn.execute("SELECT envio, envio_erro FROM aluno_codigo").fetchone()
    assert (linha["envio"], linha["envio_erro"]) == ("falhou", "estourou")


def test_o_motivo_da_falha_cabe_no_limite_do_banco(conn):
    envio = _pedir(conn)

    aluno_acesso.executar_envio(_caminho(conn), envio, RemetenteFalso(RuntimeError("x" * 5000)))

    assert len(conn.execute("SELECT envio_erro FROM aluno_codigo").fetchone()[0]) == 300


# ------------------------------------------------------------------ resumo para o terminal


def test_resumo_conta_os_codigos_e_mostra_as_falhas_sem_nenhum_segredo(conn):
    conn.execute("INSERT INTO aluno (id, nome, cpf, whatsapp, situacao) VALUES (7, 'FABI', '00000000191', '27944443322', 'A')")
    enviado = _pedir(conn)
    aluno_acesso.executar_envio(_caminho(conn), enviado, RemetenteFalso())
    falhou = _pedir(conn, "00000000191", quando=_mais(minutes=1))
    aluno_acesso.executar_envio(_caminho(conn), falhou, RemetenteFalso(RuntimeError("token vencido")))
    _pedir(conn, CPF_ANA, quando=_mais(minutes=2))  # fica pendente
    sessao = _criar_acesso(conn, CPF_ANA, quando=_mais(minutes=4))  # também pendente

    texto = "\n".join(aluno_acesso.resumo_para_o_terminal(conn, agora=_mais(minutes=5)))

    assert "Alunos com senha criada: 1" in texto
    assert "Celulares logados agora: 1" in texto
    assert "enviados 1, falharam 1, ainda mandando 2" in texto
    assert "token vencido" in texto
    for segredo in (enviado.codigo, falhou.codigo, sessao.token, CPF_ANA, "27988887766", "00000000191"):
        assert segredo not in texto
