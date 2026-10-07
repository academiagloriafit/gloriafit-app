"""Testes do cadastro de aluno provisório (app/provisorios.py)."""

import random

import pytest

from app.db import conectar, criar_tabelas
from app.provisorios import (
    CadastroInvalido,
    CpfInvalido,
    CpfJaCadastrado,
    cadastrar_provisorio,
    validar_cpf,
    validar_nome,
)


@pytest.fixture
def conn():
    c = conectar()
    criar_tabelas(c)
    yield c
    c.close()


def _digito(numeros):
    """Dígito verificador do CPF pela forma clássica (soma ponderada, resto de 11).
    De propósito escrita diferente da do app, para um conferir o outro."""
    soma = sum(n * p for n, p in zip(numeros, range(len(numeros) + 1, 1, -1)))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def cpf_valido(base9):
    """Monta um CPF válido a partir de 9 números (lista)."""
    numeros = list(base9)
    numeros.append(_digito(numeros))
    numeros.append(_digito(numeros))
    return "".join(str(n) for n in numeros)


CPF_A = "11144477735"  # CPFs de exemplo conhecidos por serem válidos (usados em documentação)
CPF_B = "52998224725"


def _aluno(conn, nome, cpf, provisorio=0, situacao=None, data4u_id=None):
    return conn.execute(
        "INSERT INTO aluno (nome, cpf, provisorio, situacao, data4u_id) VALUES (?, ?, ?, ?, ?)",
        (nome, cpf, provisorio, situacao, data4u_id),
    ).lastrowid


def _linha(conn, aluno_id):
    return conn.execute("SELECT * FROM aluno WHERE id = ?", (aluno_id,)).fetchone()


def _total(conn):
    return conn.execute("SELECT COUNT(*) FROM aluno").fetchone()[0]


# ------------------------------------------------------------------ CPF


def test_os_cpfs_de_exemplo_sao_validos():
    assert validar_cpf(CPF_A) == CPF_A
    assert validar_cpf(CPF_B) == CPF_B


@pytest.mark.parametrize("digitado", ["111.444.777-35", " 111.444.777-35 ", "111 444 777 35", "111-444-777.35", "11144477735"])
def test_cpf_aceita_pontos_hifen_e_espacos_e_devolve_so_os_numeros(digitado):
    assert validar_cpf(digitado) == "11144477735"


def _valido_pela_segunda_implementacao(texto):
    if len(texto) != 11 or len(set(texto)) == 1:
        return False
    numeros = [int(c) for c in texto]
    return numeros[9] == _digito(numeros[:9]) and numeros[10] == _digito(numeros[:10])


def test_cpf_concorda_com_uma_segunda_implementacao_em_3000_casos():
    sorteio = random.Random(2026)
    aceitos = recusados = 0
    for i in range(3000):
        if i % 3 == 0:  # um terço: CPF válido montado de propósito
            texto = cpf_valido([sorteio.randrange(10) for _ in range(9)])
        elif i % 3 == 1:  # um terço: um CPF válido com um número trocado
            texto = cpf_valido([sorteio.randrange(10) for _ in range(9)])
            posicao = sorteio.randrange(11)
            texto = texto[:posicao] + str((int(texto[posicao]) + sorteio.randrange(1, 10)) % 10) + texto[posicao + 1 :]
        else:  # um terço: 11 números quaisquer
            texto = "".join(str(sorteio.randrange(10)) for _ in range(11))
        esperado = _valido_pela_segunda_implementacao(texto)
        if esperado:
            assert validar_cpf(texto) == texto, texto
            aceitos += 1
        else:
            with pytest.raises(CpfInvalido):
                validar_cpf(texto)
            recusados += 1
    assert aceitos > 1000 and recusados > 1000  # o sorteio exercitou os dois lados


@pytest.mark.parametrize("digito", "0123456789")
def test_cpf_com_todos_os_digitos_iguais_e_recusado(digito):
    # 000.000.000-00 passaria na conta dos dígitos verificadores, mas não existe.
    with pytest.raises(CpfInvalido, match="não é válido"):
        validar_cpf(digito * 11)


def test_cpf_com_digito_verificador_errado_e_recusado():
    with pytest.raises(CpfInvalido, match="não é válido"):
        validar_cpf("11144477736")
    with pytest.raises(CpfInvalido, match="não é válido"):
        validar_cpf("11144477745")  # erra o 10º número


@pytest.mark.parametrize("digitado, trecho", [("", "Digite"), ("   ", "Digite"), (None, "Digite"), (12345678909, "Digite"), (["1"], "Digite")])
def test_cpf_vazio_ou_que_nao_e_texto(digitado, trecho):
    with pytest.raises(CpfInvalido, match=trecho):
        validar_cpf(digitado)


@pytest.mark.parametrize("digitado", ["111.444.777-3a", "abc", "111,444,777-35", "+5511144477735", "111/444/777-35", "１１１４４４７７７３５"])
def test_cpf_com_caractere_estranho_e_recusado(digitado):
    with pytest.raises(CpfInvalido, match="só pode ter números"):
        validar_cpf(digitado)


@pytest.mark.parametrize("digitado, quantos", [("1114447773", 10), ("111444777355", 12), ("1", 1)])
def test_cpf_com_quantidade_errada_de_numeros_diz_quantos_tem(digitado, quantos):
    with pytest.raises(CpfInvalido, match=f"11 números; este tem {quantos}"):
        validar_cpf(digitado)


# ------------------------------------------------------------------ nome


def test_nome_arruma_espacos():
    assert validar_nome("  Ana   Paula  Souza ") == "Ana Paula Souza"


def test_nome_aceita_acento_e_apostrofo_e_100_caracteres():
    assert validar_nome("João D'Ávila Çelso") == "João D'Ávila Çelso"
    assert validar_nome("a" * 100) == "a" * 100


@pytest.mark.parametrize("nome", ["", "   ", "\n\t", None, 5, ["Ana"], "a" * 101, "Ana\x00", "Ana\x07Paula", "Ana​Paula"])
def test_nome_recusa_vazio_longo_demais_e_caractere_invisivel(nome):
    with pytest.raises(ValueError):
        validar_nome(nome)


# ------------------------------------------------------------------ cadastrar


def test_cadastra_com_todos_os_dados(conn):
    aluno_id = cadastrar_provisorio(
        conn, {"nome": "  Lucas   Andrade ", "cpf": "111.444.777-35", "whatsapp": "(27) 98888-7766"}
    )

    linha = _linha(conn, aluno_id)
    assert linha["nome"] == "Lucas Andrade"
    assert linha["cpf"] == CPF_A
    assert linha["whatsapp"] == "27988887766"
    assert linha["whatsapp_corrigido_no_app"] == 1  # a cópia do Data4U não sobrescreve
    assert linha["provisorio"] == 1
    assert linha["data4u_id"] is None
    assert linha["situacao"] is None
    assert linha["criado_em"]


@pytest.mark.parametrize("branco", [None, "", "   ", "\n"])
def test_whatsapp_pode_ficar_em_branco(conn, branco):
    dados = {"nome": "Lucas", "cpf": CPF_A}
    if branco is not None:
        dados["whatsapp"] = branco

    linha = _linha(conn, cadastrar_provisorio(conn, dados))

    assert linha["whatsapp"] is None
    assert linha["whatsapp_corrigido_no_app"] == 0  # sem número digitado, o do Data4U pode entrar amanhã


@pytest.mark.parametrize("whatsapp", ["988887766", "(27) 988", "abc", "(00) 98888-7766", 27988887766, ["27"]])
def test_whatsapp_digitado_mas_invalido_e_recusado(conn, whatsapp):
    with pytest.raises(CadastroInvalido) as erro:
        cadastrar_provisorio(conn, {"nome": "Lucas", "cpf": CPF_A, "whatsapp": whatsapp})

    assert set(erro.value.erros) == {"whatsapp"}
    assert _total(conn) == 0


def test_todos_os_campos_ruins_sao_apontados_de_uma_vez(conn):
    with pytest.raises(CadastroInvalido) as erro:
        cadastrar_provisorio(conn, {"nome": "", "cpf": "123", "whatsapp": "1"})

    assert set(erro.value.erros) == {"nome", "cpf", "whatsapp"}
    assert "11 números" in erro.value.erros["cpf"]
    assert _total(conn) == 0


@pytest.mark.parametrize("dados", [None, [], "texto", 5, [{"nome": "x"}]])
def test_pedido_que_nao_e_objeto_e_recusado(conn, dados):
    with pytest.raises(CadastroInvalido) as erro:
        cadastrar_provisorio(conn, dados)

    assert set(erro.value.erros) == {"geral"}


def test_campos_que_faltam_viram_erro_de_campo(conn):
    with pytest.raises(CadastroInvalido) as erro:
        cadastrar_provisorio(conn, {})

    assert set(erro.value.erros) == {"nome", "cpf"}  # WhatsApp é opcional


def test_campos_extras_sao_ignorados_e_nao_viram_dado(conn):
    aluno_id = cadastrar_provisorio(
        conn, {"nome": "Lucas", "cpf": CPF_A, "situacao": "A", "data4u_id": 5, "provisorio": 0, "id": 99}
    )

    linha = _linha(conn, aluno_id)
    assert (linha["situacao"], linha["data4u_id"], linha["provisorio"]) == (None, None, 1)
    assert linha["id"] == aluno_id != 99


def test_texto_de_ataque_vira_so_texto(conn):
    nome = "Robert'); DROP TABLE aluno;-- <script>alert(1)</script>"

    aluno_id = cadastrar_provisorio(conn, {"nome": nome, "cpf": CPF_A})

    assert _linha(conn, aluno_id)["nome"] == nome
    assert _total(conn) == 1


def test_cpf_de_aluno_do_data4u_nao_pode_ser_cadastrado_de_novo(conn):
    existente = _aluno(conn, "MARIA DA SILVA", CPF_A, situacao="D", data4u_id=4412)

    with pytest.raises(CpfJaCadastrado) as erro:
        cadastrar_provisorio(conn, {"nome": "Maria Silva", "cpf": "111.444.777-35"})

    [achado] = erro.value.existentes
    assert (achado.id, achado.nome, achado.provisorio, achado.situacao_nome) == (existente, "MARIA DA SILVA", False, "Desistente")
    assert _total(conn) == 1


def test_cpf_de_outro_provisorio_tambem_e_recusado(conn):
    primeiro = cadastrar_provisorio(conn, {"nome": "Lucas", "cpf": CPF_A})

    with pytest.raises(CpfJaCadastrado) as erro:
        cadastrar_provisorio(conn, {"nome": "Lucas de novo", "cpf": CPF_A})

    [achado] = erro.value.existentes
    assert (achado.id, achado.provisorio, achado.situacao_nome) == (primeiro, True, None)
    assert _total(conn) == 1


def test_cpf_que_aparece_em_mais_de_uma_pessoa_lista_todas(conn):
    # No Data4U há CPF repetido em pessoas diferentes: o professor vê todas e escolhe.
    a = _aluno(conn, "PESSOA UM", CPF_A, situacao="A", data4u_id=1)
    b = _aluno(conn, "PESSOA DOIS", CPF_A, situacao="C", data4u_id=2)

    with pytest.raises(CpfJaCadastrado) as erro:
        cadastrar_provisorio(conn, {"nome": "Outra", "cpf": CPF_A})

    assert [e.id for e in erro.value.existentes] == [a, b]
    assert [e.situacao_nome for e in erro.value.existentes] == ["Ativo", "Cancelado"]


def test_lista_de_quem_ja_tem_o_cpf_para_em_5(conn):
    for i in range(7):
        _aluno(conn, f"PESSOA {i}", CPF_A, situacao="A", data4u_id=i + 1)

    with pytest.raises(CpfJaCadastrado) as erro:
        cadastrar_provisorio(conn, {"nome": "Outra", "cpf": CPF_A})

    assert len(erro.value.existentes) == 5


def test_aluno_sem_cpf_no_app_nao_bloqueia_ninguem(conn):
    _aluno(conn, "SEM CPF", None, situacao="A", data4u_id=1)

    aluno_id = cadastrar_provisorio(conn, {"nome": "Lucas", "cpf": CPF_A})

    assert _linha(conn, aluno_id)["cpf"] == CPF_A
    assert _total(conn) == 2


def test_cpf_diferente_cadastra_normalmente(conn):
    _aluno(conn, "MARIA", CPF_A, situacao="A", data4u_id=1)

    cadastrar_provisorio(conn, {"nome": "Lucas", "cpf": CPF_B})

    assert _total(conn) == 2


def test_dois_provisorios_seguidos_de_cpfs_diferentes_ficam_com_ids_diferentes(conn):
    a = cadastrar_provisorio(conn, {"nome": "Um", "cpf": CPF_A})
    b = cadastrar_provisorio(conn, {"nome": "Dois", "cpf": CPF_B})

    assert a != b


def test_cpf_recusado_nao_deixa_transacao_aberta(conn):
    _aluno(conn, "MARIA", CPF_A, situacao="A", data4u_id=1)
    conn.commit()

    with pytest.raises(CpfJaCadastrado):
        cadastrar_provisorio(conn, {"nome": "Lucas", "cpf": CPF_A})

    assert conn.in_transaction is False


def test_cadastro_dois_pedidos_ao_mesmo_tempo_com_o_mesmo_cpf_cria_so_um(tmp_path):
    caminho = tmp_path / "corrida.db"
    inicial = conectar(caminho)
    criar_tabelas(inicial)
    inicial.close()
    a, b = conectar(caminho), conectar(caminho)
    try:
        cadastrar_provisorio(a, {"nome": "Primeiro", "cpf": CPF_A})
        with pytest.raises(CpfJaCadastrado):
            cadastrar_provisorio(b, {"nome": "Segundo", "cpf": CPF_A})
        assert b.execute("SELECT COUNT(*) FROM aluno").fetchone()[0] == 1
    finally:
        a.close()
        b.close()
