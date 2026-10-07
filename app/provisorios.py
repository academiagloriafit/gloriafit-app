"""Aluno provisório: cadastro feito no primeiro dia, antes de a pessoa chegar pela cópia do Data4U.

Por que existe: o Data4U só chega ao app uma vez por dia (05:00). Quem se matricula hoje
só aparece amanhã. Para o professor não esperar, ele cadastra aqui o nome, o CPF e o
WhatsApp do aluno novo e monta o treino na hora. No dia seguinte, o importador
(app/importar_alunos.py) encontra a pessoa pelo CPF e junta os dois cadastros.

Por isso o CPF é o dado mais importante daqui: ele é a ligação com o Data4U. O app confere
se é um CPF possível (11 números e os dois dígitos verificadores) para pegar erro de
digitação na hora, e recusa um CPF que já esteja no app (nunca cria um segundo cadastro
da mesma pessoa).
"""

import re
import sqlite3
import unicodedata
from dataclasses import dataclass

from app.alunos import SITUACOES, WhatsappInvalido, validar_whatsapp

TAMANHO_MAXIMO_DO_NOME = 100  # limite do app, para não aceitar lixo; um nome de verdade cabe com folga

# [0-9] e não \d: \d também aceita algarismos de outros alfabetos (largura total, árabe...).
_SO_NUMERO_E_ENFEITE = re.compile(r"[0-9\s.\-]+")


class CadastroInvalido(Exception):
    """Algum campo não serve. `erros` é {campo: mensagem pronta para mostrar na tela}."""

    def __init__(self, erros: dict[str, str]):
        super().__init__("; ".join(erros.values()))
        self.erros = erros


@dataclass(frozen=True)
class AlunoExistente:
    id: int
    nome: str
    provisorio: bool
    situacao_nome: str | None


class CpfJaCadastrado(Exception):
    """Já existe aluno (do Data4U ou provisório) com este CPF. Não se cria outro."""

    def __init__(self, existentes: list[AlunoExistente]):
        super().__init__("Já existe aluno com este CPF.")
        self.existentes = existentes


# ------------------------------------------------------------------ validação


class CpfInvalido(ValueError):
    """O CPF digitado não serve. A mensagem já está pronta para mostrar na tela."""


def _digito_verificador(numeros: list[int]) -> int:
    # Regra oficial do CPF: cada número é multiplicado por um peso que desce de
    # (quantidade + 1) até 2; soma-se tudo; o dígito é o que falta para o próximo
    # múltiplo de 11 (10 e 11 viram 0).
    peso = len(numeros) + 1
    soma = sum(n * (peso - i) for i, n in enumerate(numeros))
    resto = (soma * 10) % 11
    return 0 if resto == 10 else resto


def validar_cpf(valor) -> str:
    """Devolve só os 11 números do CPF, ou levanta CpfInvalido.

    Aceita pontos, hífen e espaços ("123.456.789-09"). Recusa CPF com número de dígitos
    errado, com todos os dígitos iguais ("111.111.111-11") ou com dígito verificador errado.
    """
    if not isinstance(valor, str) or not valor.strip():
        raise CpfInvalido("Digite o CPF.")
    if not _SO_NUMERO_E_ENFEITE.fullmatch(valor):
        raise CpfInvalido("O CPF só pode ter números, ponto, hífen e espaço.")
    digitos = re.sub(r"[^0-9]", "", valor)
    if len(digitos) != 11:
        raise CpfInvalido(f"O CPF precisa ter 11 números; este tem {len(digitos)}.")
    numeros = [int(c) for c in digitos]
    if len(set(numeros)) == 1 or numeros[9] != _digito_verificador(numeros[:9]) or numeros[10] != _digito_verificador(numeros[:10]):
        raise CpfInvalido("Este CPF não é válido. Confira os números.")
    return digitos


def validar_nome(valor) -> str:
    """Nome sem espaços nas pontas nem repetidos (de 1 a 100 caracteres, sem caractere de controle)."""
    if not isinstance(valor, str):
        raise ValueError("Digite o nome completo do aluno.")
    limpo = " ".join(valor.split())
    if not limpo:
        raise ValueError("Digite o nome completo do aluno.")
    if len(limpo) > TAMANHO_MAXIMO_DO_NOME:
        raise ValueError(f"O nome pode ter no máximo {TAMANHO_MAXIMO_DO_NOME} caracteres.")
    if any(unicodedata.category(c).startswith("C") for c in limpo):
        raise ValueError("O nome tem caracteres que não podem ser usados.")
    return limpo


# ------------------------------------------------------------------ cadastro


def cadastrar_provisorio(conn: sqlite3.Connection, dados) -> int:
    """Cria o aluno provisório e devolve o id dele.

    `dados`: {"nome", "cpf", "whatsapp"}; o WhatsApp é opcional (em branco = sem número;
    a recepção pode preencher depois na ficha). Levanta CadastroInvalido (campo ruim) ou
    CpfJaCadastrado (a pessoa já está no app).

    O WhatsApp digitado aqui entra como "corrigido no app": a cópia do Data4U não o
    sobrescreve (o número que o professor ouviu do próprio aluno vale mais que o antigo).
    """
    if not isinstance(dados, dict):
        raise CadastroInvalido({"geral": "Formato do pedido inválido."})

    erros: dict[str, str] = {}
    nome = cpf = whatsapp = None
    try:
        nome = validar_nome(dados.get("nome"))
    except ValueError as erro:
        erros["nome"] = str(erro)
    try:
        cpf = validar_cpf(dados.get("cpf"))
    except CpfInvalido as erro:
        erros["cpf"] = str(erro)
    bruto = dados.get("whatsapp")
    if bruto is not None and not (isinstance(bruto, str) and not bruto.strip()):
        try:
            whatsapp = validar_whatsapp(bruto)
        except WhatsappInvalido as erro:
            erros["whatsapp"] = str(erro)
    if erros:
        raise CadastroInvalido(erros)

    with conn:
        # Um comando só confere e grava: o SQLite não deixa dois pedidos simultâneos com o
        # mesmo CPF passarem juntos (o segundo vê o primeiro e não insere).
        criados = conn.execute(
            "INSERT INTO aluno (nome, cpf, whatsapp, whatsapp_corrigido_no_app, provisorio)"
            " SELECT ?, ?, ?, ?, 1 WHERE NOT EXISTS (SELECT 1 FROM aluno WHERE cpf = ?)",
            (nome, cpf, whatsapp, 1 if whatsapp else 0, cpf),
        )
        if criados.rowcount == 1:
            return criados.lastrowid

    raise CpfJaCadastrado(_quem_tem_o_cpf(conn, cpf))


def _quem_tem_o_cpf(conn: sqlite3.Connection, cpf: str) -> list[AlunoExistente]:
    # No Data4U há CPF repetido em mais de uma pessoa, então pode haver mais de um.
    linhas = conn.execute(
        "SELECT id, nome, provisorio, situacao FROM aluno WHERE cpf = ? ORDER BY id LIMIT 5", (cpf,)
    ).fetchall()
    return [
        AlunoExistente(
            id=l["id"],
            nome=l["nome"],
            provisorio=bool(l["provisorio"]),
            situacao_nome=SITUACOES.get(l["situacao"]),
        )
        for l in linhas
    ]
