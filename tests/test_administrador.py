"""Senha de administrador (app/administrador.py): hash, conferência, trava de tentativas e comando de terminal.

Dados inventados. Nenhuma senha de verdade aparece aqui.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app import administrador
from app.administrador import (
    JANELA_DE_FALHAS,
    LIMITE_DE_FALHAS,
    MAXIMO_DA_SENHA,
    MINIMO_DA_SENHA,
    MuitasTentativas,
    SenhaIncorreta,
    SenhaInvalida,
    SenhaNaoDefinida,
)
from app.db import conectar, criar_tabelas

SENHA = "senha-de-teste-1"
AGORA = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def conn():
    c = conectar()
    criar_tabelas(c)
    yield c
    c.close()


@pytest.fixture
def com_senha(conn):
    administrador.definir_senha(conn, SENHA, agora=AGORA)
    return conn


def _falhas(conn):
    return conn.execute("SELECT COUNT(*) FROM senha_administrador_falha").fetchone()[0]


# ------------------------------------------------------------------ a senha nova


@pytest.mark.parametrize("senha", [None, 123, b"abcdefgh", "", "        ", "\t\n  \t  \n"])
def test_senha_em_branco_ou_que_nao_e_texto_nao_serve(senha):
    with pytest.raises(SenhaInvalida, match="em branco"):
        administrador.validar_senha_nova(senha)


def test_senha_curta_demais_nao_serve():
    with pytest.raises(SenhaInvalida, match=str(MINIMO_DA_SENHA)):
        administrador.validar_senha_nova("a" * (MINIMO_DA_SENHA - 1))
    assert administrador.validar_senha_nova("a" * MINIMO_DA_SENHA) == "a" * MINIMO_DA_SENHA


def test_senha_longa_demais_nao_serve():
    with pytest.raises(SenhaInvalida, match=str(MAXIMO_DA_SENHA)):
        administrador.validar_senha_nova("a" * (MAXIMO_DA_SENHA + 1))
    assert administrador.validar_senha_nova("a" * MAXIMO_DA_SENHA)


def test_senha_com_caractere_de_controle_nao_serve():
    with pytest.raises(SenhaInvalida, match="caracteres"):
        administrador.validar_senha_nova("senha\x00-de-teste")


def test_senha_pode_ter_espacos_acentos_e_simbolos():
    assert administrador.validar_senha_nova("uma frase com acentuação: ção! 123")


# ------------------------------------------------------------------ o hash


def test_o_hash_nao_contem_a_senha_e_tem_sal_diferente_a_cada_vez():
    a = administrador.gerar_hash(SENHA)
    b = administrador.gerar_hash(SENHA)

    assert a != b  # sal sorteado
    assert SENHA not in a and SENHA.encode().hex() not in a
    formato, n, r, p, sal, chave = a.split("$")
    assert (formato, int(n), int(r), int(p)) == ("scrypt", 2**14, 8, 1)
    assert len(bytes.fromhex(sal)) == 16 and len(bytes.fromhex(chave)) == 32


def test_hash_confere_so_com_a_senha_certa():
    guardado = administrador.gerar_hash(SENHA)

    assert administrador.hash_confere(SENHA, guardado)
    assert not administrador.hash_confere(SENHA + "x", guardado)
    assert not administrador.hash_confere(SENHA.upper(), guardado)  # maiúscula e minúscula são diferentes
    assert not administrador.hash_confere("", guardado)


def test_a_mesma_letra_acentuada_digitada_de_dois_jeitos_confere():
    guardado = administrador.gerar_hash("coração-12")  # "ç" e "ã" como uma letra só

    assert administrador.hash_confere("coração-12", guardado)  # "c" + cedilha e "a" + til separados


@pytest.mark.parametrize(
    "guardado",
    ["", "lixo", "scrypt$1$2$3", "md5$16384$8$1$00$00", "scrypt$x$8$1$00$00", "scrypt$16384$8$1$zz$00", "scrypt$16384$8$1$00$zz"],
)
def test_hash_estragado_ou_de_outro_formato_nunca_confere(guardado):
    assert administrador.hash_confere(SENHA, guardado) is False


# ------------------------------------------------------------------ definir a senha


def test_sem_definir_nada_nao_ha_senha(conn):
    assert administrador.tem_senha(conn) is False
    assert administrador.situacao(conn, agora=AGORA) == {"definida": False, "definida_em": None, "travada_por": 0}


def test_definir_guarda_so_o_hash(conn):
    administrador.definir_senha(conn, SENHA, agora=AGORA)

    assert administrador.tem_senha(conn)
    linha = conn.execute("SELECT id, senha_hash, definida_em FROM senha_administrador").fetchone()
    assert linha["id"] == 1 and linha["definida_em"] == "2026-10-13 12:00:00"
    assert linha["senha_hash"].startswith("scrypt$") and SENHA not in linha["senha_hash"]
    # a senha não aparece em lugar nenhum do banco
    despejo = "\n".join(conn.iterdump())
    assert SENHA not in despejo


def test_definir_de_novo_troca_a_senha_e_continua_uma_linha_so(conn):
    administrador.definir_senha(conn, SENHA)
    administrador.definir_senha(conn, "outra-senha-9")

    assert conn.execute("SELECT COUNT(*) FROM senha_administrador").fetchone()[0] == 1
    with pytest.raises(SenhaIncorreta):
        administrador.conferir_senha(conn, SENHA)
    administrador.conferir_senha(conn, "outra-senha-9")


def test_definir_senha_invalida_nao_muda_nada(com_senha):
    antes = com_senha.execute("SELECT senha_hash FROM senha_administrador").fetchone()[0]

    with pytest.raises(SenhaInvalida):
        administrador.definir_senha(com_senha, "curta")

    assert com_senha.execute("SELECT senha_hash FROM senha_administrador").fetchone()[0] == antes


def test_a_tabela_aceita_uma_linha_so(com_senha):
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        com_senha.execute("INSERT INTO senha_administrador (id, senha_hash, definida_em) VALUES (2, 'x', 'y')")


def test_trocar_a_senha_destrava(com_senha):
    for _ in range(LIMITE_DE_FALHAS):
        with pytest.raises(SenhaIncorreta):
            administrador.conferir_senha(com_senha, "errada", agora=AGORA)
    with pytest.raises(MuitasTentativas):
        administrador.conferir_senha(com_senha, SENHA, agora=AGORA)

    administrador.definir_senha(com_senha, "senha-nova-77", agora=AGORA)  # quem tem acesso ao servidor pode trocar

    administrador.conferir_senha(com_senha, "senha-nova-77", agora=AGORA)
    assert _falhas(com_senha) == 0


# ------------------------------------------------------------------ conferir


def test_senha_certa_passa(com_senha):
    assert administrador.conferir_senha(com_senha, SENHA, agora=AGORA) is None


def test_senha_errada_levanta_e_conta_a_falha(com_senha):
    with pytest.raises(SenhaIncorreta):
        administrador.conferir_senha(com_senha, "errada-123", agora=AGORA)

    assert _falhas(com_senha) == 1


@pytest.mark.parametrize("digitada", [None, "", 123, ["a"], {"a": 1}, "x" * (MAXIMO_DA_SENHA + 1)])
def test_senha_que_nao_e_texto_ou_e_vazia_ou_enorme_e_incorreta(com_senha, digitada):
    with pytest.raises(SenhaIncorreta):
        administrador.conferir_senha(com_senha, digitada, agora=AGORA)

    assert _falhas(com_senha) == 1


def test_sem_senha_definida_fica_fechado_e_nao_conta_falha(conn):
    with pytest.raises(SenhaNaoDefinida):
        administrador.conferir_senha(conn, SENHA, agora=AGORA)
    with pytest.raises(SenhaNaoDefinida):
        administrador.conferir_senha(conn, "", agora=AGORA)

    assert _falhas(conn) == 0


def test_cinco_senhas_erradas_travam_ate_a_senha_certa(com_senha):
    for _ in range(LIMITE_DE_FALHAS):
        with pytest.raises(SenhaIncorreta):
            administrador.conferir_senha(com_senha, "errada-123", agora=AGORA)

    with pytest.raises(MuitasTentativas) as erro:
        administrador.conferir_senha(com_senha, SENHA, agora=AGORA)  # nem a senha certa passa enquanto está travado

    assert 1 <= erro.value.segundos <= JANELA_DE_FALHAS.total_seconds() + 1


def test_quatro_erradas_ainda_deixam_a_certa_passar_e_zeram_a_conta(com_senha):
    for _ in range(LIMITE_DE_FALHAS - 1):
        with pytest.raises(SenhaIncorreta):
            administrador.conferir_senha(com_senha, "errada-123", agora=AGORA)

    administrador.conferir_senha(com_senha, SENHA, agora=AGORA)

    assert _falhas(com_senha) == 0  # quem acertou recomeça do zero


def test_travado_nao_registra_mais_falhas(com_senha):
    for _ in range(LIMITE_DE_FALHAS):
        with pytest.raises(SenhaIncorreta):
            administrador.conferir_senha(com_senha, "errada-123", agora=AGORA)

    for _ in range(3):
        with pytest.raises(MuitasTentativas):
            administrador.conferir_senha(com_senha, "errada-123", agora=AGORA + timedelta(minutes=1))

    assert _falhas(com_senha) == LIMITE_DE_FALHAS  # senão o prazo nunca acabaria


def test_a_espera_conta_a_partir_da_falha_mais_antiga(com_senha):
    for minuto in range(LIMITE_DE_FALHAS):
        with pytest.raises(SenhaIncorreta):
            administrador.conferir_senha(com_senha, "errada-123", agora=AGORA + timedelta(minutes=minuto))

    # 4 min depois da primeira falha: faltam ~11 min para ela sair da janela de 15
    with pytest.raises(MuitasTentativas) as erro:
        administrador.conferir_senha(com_senha, SENHA, agora=AGORA + timedelta(minutes=4))

    assert 11 * 60 <= erro.value.segundos <= 11 * 60 + 2


def test_destrava_quando_a_falha_mais_antiga_sai_da_janela(com_senha):
    for _ in range(LIMITE_DE_FALHAS):
        with pytest.raises(SenhaIncorreta):
            administrador.conferir_senha(com_senha, "errada-123", agora=AGORA)

    administrador.conferir_senha(com_senha, SENHA, agora=AGORA + JANELA_DE_FALHAS + timedelta(seconds=1))


def test_falhas_antigas_nao_somam_com_as_novas(com_senha):
    for _ in range(LIMITE_DE_FALHAS - 1):
        with pytest.raises(SenhaIncorreta):
            administrador.conferir_senha(com_senha, "errada-123", agora=AGORA)

    depois = AGORA + JANELA_DE_FALHAS + timedelta(minutes=1)
    with pytest.raises(SenhaIncorreta):  # a quinta, mas as 4 primeiras já venceram: não trava
        administrador.conferir_senha(com_senha, "errada-123", agora=depois)
    administrador.conferir_senha(com_senha, SENHA, agora=depois)


def test_situacao_mostra_a_trava_sem_mostrar_a_senha(com_senha):
    for _ in range(LIMITE_DE_FALHAS):
        with pytest.raises(SenhaIncorreta):
            administrador.conferir_senha(com_senha, "errada-123", agora=AGORA)

    estado = administrador.situacao(com_senha, agora=AGORA)

    assert estado["definida"] is True and estado["definida_em"] == AGORA
    assert estado["travada_por"] > 0
    assert SENHA not in repr(estado)


# ------------------------------------------------------------------ comando de terminal


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "app.db"
    c = conectar(caminho)
    criar_tabelas(c)
    c.close()
    return caminho


def _digitando(*respostas):
    """Um `getpass` de mentira que devolve as respostas em ordem (e guarda as perguntas)."""
    fila = list(respostas)
    perguntas = []

    def pedir(pergunta):
        perguntas.append(pergunta)
        return fila.pop(0)

    pedir.perguntas = perguntas
    return pedir


def _comando(caminho, *args, digitando=None):
    return administrador.main(["--banco", str(caminho), *args], pedir_senha=digitando or _digitando())


def test_comando_define_a_senha_pedindo_duas_vezes(caminho, capsys):
    pedir = _digitando(SENHA, SENHA)

    assert _comando(caminho, "definir-senha", digitando=pedir) == 0

    saida = capsys.readouterr()
    assert "definida" in saida.out and SENHA not in saida.out + saida.err
    assert len(pedir.perguntas) == 2
    c = conectar(caminho)
    administrador.conferir_senha(c, SENHA)
    c.close()


def test_comando_com_senhas_diferentes_nao_muda_nada(caminho, capsys):
    assert _comando(caminho, "definir-senha", digitando=_digitando(SENHA, SENHA + "x")) == 2

    assert "diferentes" in capsys.readouterr().err
    c = conectar(caminho)
    assert administrador.tem_senha(c) is False
    c.close()


def test_comando_com_senha_curta_recusa_antes_de_pedir_de_novo(caminho, capsys):
    pedir = _digitando("curta")

    assert _comando(caminho, "definir-senha", digitando=pedir) == 2

    assert "pelo menos" in capsys.readouterr().err
    assert len(pedir.perguntas) == 1


def test_comando_troca_a_senha_que_ja_existe(caminho):
    _comando(caminho, "definir-senha", digitando=_digitando(SENHA, SENHA))
    _comando(caminho, "definir-senha", digitando=_digitando("senha-nova-77", "senha-nova-77"))

    c = conectar(caminho)
    administrador.conferir_senha(c, "senha-nova-77")
    with pytest.raises(SenhaIncorreta):
        administrador.conferir_senha(c, SENHA)
    c.close()


def test_comando_situacao_diz_se_ja_foi_definida_sem_mostrar_a_senha(caminho, capsys):
    assert _comando(caminho, "situacao") == 0
    assert "AINDA NÃO" in capsys.readouterr().out

    _comando(caminho, "definir-senha", digitando=_digitando(SENHA, SENHA))
    capsys.readouterr()
    assert _comando(caminho, "situacao") == 0

    saida = capsys.readouterr().out
    assert "definida em" in saida and SENHA not in saida and "scrypt" not in saida


def test_comando_com_banco_que_nao_existe_para_com_mensagem(tmp_path):
    with pytest.raises(SystemExit, match="Banco de dados não encontrado"):
        _comando(tmp_path / "nao-existe.db", "situacao")


def test_comando_atualiza_banco_da_versao_8_ao_abrir(tmp_path):
    # O servidor ainda pode estar na versão 8 quando alguém roda o comando com o app novo: o comando migra (com cópia).
    from tests.test_migracao import _banco_v8

    caminho = tmp_path / "app.db"
    _banco_v8(caminho)

    assert _comando(caminho, "definir-senha", digitando=_digitando(SENHA, SENHA)) == 0

    c = conectar(caminho)
    assert c.execute("PRAGMA user_version").fetchone()[0] == 9
    administrador.conferir_senha(c, SENHA)
    c.close()
