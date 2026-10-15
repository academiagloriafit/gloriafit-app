"""Login do aluno: CPF + senha, com o primeiro acesso (e o "esqueci a senha") por um código enviado ao WhatsApp.

Como funciona, do começo ao fim:

1. PRIMEIRO ACESSO (ou esqueci a senha). O aluno digita o CPF e pede o código. Se o CPF é de um aluno que pode entrar e ele tem
   WhatsApp cadastrado, o app sorteia um código de 6 números, guarda só o hash dele (vale 10 minutos, 5 tentativas) e o manda
   para o WhatsApp pelo modelo aprovado da Meta (app/whatsapp.py), em segundo plano. A resposta à tela é SEMPRE a mesma, com
   ou sem aluno, com ou sem WhatsApp: assim ninguém usa a tela para descobrir quais CPFs são de alunos.
2. O aluno digita o código e escolhe uma senha. Se o código confere, a senha é guardada (hash lento, scrypt) e ele já entra.
3. DIA A DIA. CPF + senha. O navegador guarda um cookie (HttpOnly) com um token sorteado; o banco guarda só o hash dele.
4. Senha nova (primeiro acesso ou esqueci) derruba todos os outros celulares em que ele estava logado.

Quem pode entrar (decisão do Thiago em 15/10/2026, em `_quem_pode_entrar`): QUALQUER aluno vindo do Data4U, seja qual for a
situação (Ativo, Trancado, Pendente, Desistente, Inativo ou Cancelado). Motivo: os alunos do Wellhub e do TotalPass aparecem como
Inativo no Data4U, mas a academia monta treino para eles. Ficam de fora só os alunos provisórios (cadastro feito à mão no app,
ainda sem registro no Data4U: o mesmo CPF costuma aparecer de novo quando o Data4U o traz), e quem não é dono SOZINHO do CPF
(o Data4U tem CPFs repetidos; se dois alunos têm o mesmo CPF, ninguém entra por ele até a recepção arrumar). A conferência se
repete a CADA pedido, com o cadastro de hoje.

Cuidados de segurança que este arquivo tem (o endereço é aberto à internet inteira):
- Código e token são sorteados com `secrets`. O banco guarda só hash. O código tem só 1 milhão de possibilidades, então a
  defesa é o LIMITE de tentativas (5 por código, 5 erros por CPF e 50 por endereço a cada 15 min), não o hash. Contas: cada
  CPF pode pedir no máximo 5 códigos por dia, 5 tentativas cada = 25 palpites por dia em 1.000.000.
- Os limites contam também CPF que não existe, com a mesma regra: o bloqueio não revela quem é aluno. CPF e endereço entram
  na tabela como hash (SHA-256), e os registros somem depois de 1 dia.
- Senha errada, CPF que não existe e aluno sem senha dão a MESMA resposta e demoram o mesmo (o hash lento roda nos três casos).
- Teto de códigos por dia no app inteiro (cada um custa uma mensagem paga): `CODIGOS_POR_DIA`.
- Senha escolhida por gente usa hash LENTO (o mesmo da senha de administrador), com recusa das senhas mais óbvias.
- A senha só é conferida depois de o código estar certo, e o código só é gasto depois de a senha nova passar nas regras: erro
  de digitação da senha não faz o aluno perder o código.
- O cookie do aluno NÃO abre a área do professor: é outra tabela, outro cookie, e as rotas do professor continuam exigindo
  computador autorizado.
- Limitação conhecida: quem tem a cópia do banco dentro dos 10 minutos de vida de um código pode achá-lo testando os 1.000.000
  de possibilidades. Quem tem a cópia do banco já tem tudo o que o app guarda, então isso não muda o risco.
"""

import hashlib
import hmac
import logging
import math
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app import administrador, db, provisorios

NOME_DO_COOKIE = "gloriafit_aluno"

def _quem_pode_entrar(tabela: str = "aluno") -> str:
    """O pedaço de SQL que separa quem pode entrar: qualquer situação, menos aluno provisório. Ver a explicação no alto do arquivo."""
    return f"{tabela}.provisorio = 0"


TAMANHO_DO_CODIGO = 6
VALIDADE_DO_CODIGO = timedelta(minutes=10)
TENTATIVAS_POR_CODIGO = 5
INTERVALO_ENTRE_PEDIDOS = timedelta(seconds=60)  # entre dois pedidos de código do mesmo CPF
PEDIDOS_POR_CPF_POR_DIA = 5
PEDIDOS_POR_ENDERECO_POR_HORA = 60  # alto de propósito: a academia inteira usa o mesmo wi-fi
CODIGOS_POR_DIA = 500  # no app todo; cada um é uma mensagem paga (cerca de R$ 0,035)
FALHAS_POR_CPF = 5  # senhas ou códigos errados permitidos por CPF...
FALHAS_POR_ENDERECO = 50  # ...e por endereço (maior pelo mesmo motivo do wi-fi)...
JANELA_DE_FALHAS = timedelta(minutes=15)  # ...dentro deste tempo

VALIDADE_SEM_USO = timedelta(days=90)  # celular sem uso por tanto tempo perde o acesso
INTERVALO_DE_RENOVACAO = timedelta(hours=1)  # de quanto em quanto tempo o "último uso" é regravado
DURACAO_DO_COOKIE = timedelta(days=90)
GUARDAR_CODIGOS_POR = timedelta(days=7)
GUARDAR_EVENTOS_POR = timedelta(days=1)

_FORMATO_DATA = "%Y-%m-%d %H:%M:%S"  # UTC, como o resto do banco

# As senhas mais óbvias (comparadas sem maiúsculas). Não substitui um bom critério; só tira o pior.
_SENHAS_OBVIAS = frozenset(
    {
        "12345678", "123456789", "1234567890", "12341234", "11111111", "00000000", "87654321", "senha123", "senha1234",
        "password", "qwertyui", "abcd1234", "academia", "gloriafit", "glóriafit", "gloria123", "gloriafit123",
    }
)

_log = logging.getLogger("gloriafit.aluno")


# ------------------------------------------------------------------ erros


class CodigoInvalido(Exception):
    """Código errado, já usado, vencido ou de CPF que não existe. De propósito, não diz qual."""


class LoginInvalido(Exception):
    """CPF ou senha errados (ou aluno sem senha, ou sem permissão). De propósito, não diz qual."""


class MuitasTentativas(Exception):
    """Limite estourado (pedidos de código, senhas ou códigos errados). `mensagem` já vem pronta para a tela."""

    def __init__(self, segundos: int):
        super().__init__(f"Tente de novo em {segundos} segundos.")
        self.segundos = segundos
        self.mensagem = _frase_de_espera(segundos)


class LimiteDoDia(Exception):
    """O teto de códigos do dia no app inteiro foi atingido."""


class SenhaInvalida(administrador.SenhaInvalida):
    """A senha nova não serve. A mensagem já está pronta para mostrar na tela."""


@dataclass(frozen=True)
class Envio:
    """O que mandar ao WhatsApp. Só existe na memória (o código em si nunca é gravado)."""

    codigo_id: int
    aluno_id: int
    whatsapp: str  # como o app guarda: DDD + número
    codigo: str


@dataclass(frozen=True)
class Entrada:
    token: str  # o valor que vai para o cookie (só existe aqui; o banco guarda o hash)
    aluno_id: int
    nome: str


@dataclass(frozen=True)
class AlunoLogado:
    id: int
    nome: str
    renovar_cookie: bool  # True quando o "último uso" acabou de ser regravado


# ------------------------------------------------------------------ pequenas ajudas


def _agora(agora: datetime | None) -> datetime:
    return (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)


def _texto(momento: datetime) -> str:
    return momento.astimezone(timezone.utc).strftime(_FORMATO_DATA)


def _momento(texto: str) -> datetime:
    return datetime.strptime(texto, _FORMATO_DATA).replace(tzinfo=timezone.utc)


def _hash(valor: str) -> str:
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()


def _hash_do_codigo(aluno_id: int, codigo: str) -> str:
    return _hash(f"{aluno_id}:{codigo}")


def _frase_de_espera(segundos: int) -> str:
    if segundos < 90:
        return f"Muitas tentativas. Espere {segundos} segundos e tente de novo."
    return f"Muitas tentativas. Tente de novo em {math.ceil(segundos / 60)} minutos."


_hash_de_mentira: str | None = None


def _hash_para_quem_nao_existe() -> str:
    """Um hash de senha que ninguém acerta: serve para o login de CPF inexistente demorar o mesmo que o de CPF real."""
    global _hash_de_mentira
    if _hash_de_mentira is None:
        _hash_de_mentira = administrador.gerar_hash(secrets.token_urlsafe(24))
    return _hash_de_mentira


def validar_cpf(valor: object) -> str:
    """Os 11 números do CPF, ou levanta provisorios.CpfInvalido (a mensagem vai para a tela)."""
    return provisorios.validar_cpf(valor)


def validar_senha_nova(senha: object, cpf: str) -> str:
    """A senha, se servir; senão levanta SenhaInvalida com o motivo em português."""
    try:
        senha = administrador.validar_senha_nova(senha)
    except administrador.SenhaInvalida as erro:
        raise SenhaInvalida(str(erro)) from None
    if senha.strip().lower() in _SENHAS_OBVIAS or re.sub(r"[^0-9]", "", senha) == cpf:
        raise SenhaInvalida("Esta senha é fácil de adivinhar. Escolha outra, que ninguém imagine (não use o CPF nem 12345678).")
    return senha


def _digitos_do_codigo(digitado: object) -> str:
    """O que a pessoa digitou -> só os algarismos comuns ('123 456' vira '123456'). Não sendo texto, vira ''."""
    if not isinstance(digitado, str):
        return ""
    return "".join(c for c in digitado if c in "0123456789")


# ------------------------------------------------------------------ limites de tentativas


def _chave_do_cpf(cpf: str) -> str:
    return "cpf:" + _hash(cpf)


def _chave_do_endereco(endereco: str | None) -> str:
    return "ip:" + _hash(endereco or "?")


def _conferir_limites(
    conn: sqlite3.Connection, tipo: str, regras: list[tuple[str, int, timedelta]], agora: datetime
) -> None:
    """Levanta MuitasTentativas se alguma regra (chave, limite, janela) já estourou. Não registra nada (quem bloqueia
    não alimenta o próprio bloqueio: senão ele nunca terminaria)."""
    espera = 0
    for chave, limite, janela in regras:
        momentos = [
            _momento(linha[0])
            for linha in conn.execute(
                "SELECT em FROM aluno_evento WHERE tipo = ? AND chave = ? AND em > ? ORDER BY em",
                (tipo, chave, _texto(agora - janela)),
            )
        ]
        if len(momentos) >= limite:
            # Libera quando o evento que deixa a conta em "limite - 1" sai da janela.
            libera_em = momentos[len(momentos) - limite] + janela
            espera = max(espera, 1, math.ceil((libera_em - agora).total_seconds()))
    if espera:
        raise MuitasTentativas(espera)


def _registrar(conn: sqlite3.Connection, tipo: str, chaves: list[str], agora: datetime) -> None:
    with conn:
        conn.execute("DELETE FROM aluno_evento WHERE em < ?", (_texto(agora - GUARDAR_EVENTOS_POR),))
        conn.executemany(
            "INSERT INTO aluno_evento (tipo, chave, em) VALUES (?, ?, ?)", [(tipo, chave, _texto(agora)) for chave in chaves]
        )


def _esquecer_erros(conn: sqlite3.Connection, cpf: str) -> None:
    """Quem acertou (a senha ou o código) começa de novo: apaga os erros deste CPF."""
    conn.execute(
        "DELETE FROM aluno_evento WHERE tipo IN ('login_errado', 'codigo_errado') AND chave = ?", (_chave_do_cpf(cpf),)
    )


# ------------------------------------------------------------------ quem é o aluno


def _aluno_do_cpf(conn: sqlite3.Connection, cpf: str) -> sqlite3.Row | None:
    """O aluno dono deste CPF, se há UM só entre os que podem entrar; senão None (não existe, não pode ou é ambíguo)."""
    linhas = conn.execute(
        f"SELECT id, nome, whatsapp FROM aluno WHERE cpf = ? AND {_quem_pode_entrar()}", (cpf,)
    ).fetchall()
    return linhas[0] if len(linhas) == 1 else None


# ------------------------------------------------------------------ pedir o código


def pedir_codigo(
    conn: sqlite3.Connection, cpf: str, endereco: str | None, agora: datetime | None = None
) -> Envio | None:
    """Registra o pedido de código e, se o CPF é de um aluno que pode entrar e tem WhatsApp, cria o código.

    Devolve o `Envio` a fazer (quem chama manda, em segundo plano) ou None quando não há nada a mandar: CPF sem aluno, aluno que
    não pode entrar ou sem WhatsApp. Quem chama responde a MESMA coisa nos dois casos.
    Levanta MuitasTentativas (pediu demais) ou LimiteDoDia. Os limites valem também para CPF que não existe.
    """
    agora = _agora(agora)
    chave_cpf, chave_endereco = _chave_do_cpf(cpf), _chave_do_endereco(endereco)
    _conferir_limites(
        conn,
        "pedido_codigo",
        [
            (chave_cpf, 1, INTERVALO_ENTRE_PEDIDOS),
            (chave_cpf, PEDIDOS_POR_CPF_POR_DIA, timedelta(days=1)),
            (chave_endereco, PEDIDOS_POR_ENDERECO_POR_HORA, timedelta(hours=1)),
        ],
        agora,
    )
    enviados_hoje = conn.execute(
        "SELECT COUNT(*) FROM aluno_codigo WHERE criado_em > ?", (_texto(agora - timedelta(days=1)),)
    ).fetchone()[0]
    if enviados_hoje >= CODIGOS_POR_DIA:
        raise LimiteDoDia()
    _registrar(conn, "pedido_codigo", [chave_cpf, chave_endereco], agora)

    aluno = _aluno_do_cpf(conn, cpf)
    if aluno is None or not aluno["whatsapp"]:
        return None

    codigo = f"{secrets.randbelow(10**TAMANHO_DO_CODIGO):0{TAMANHO_DO_CODIGO}d}"
    with conn:
        conn.execute("DELETE FROM aluno_codigo WHERE criado_em < ?", (_texto(agora - GUARDAR_CODIGOS_POR),))
        # Só o código mais novo vale: o pedido novo queima os anteriores que ainda estavam de pé.
        conn.execute("UPDATE aluno_codigo SET usado_em = ? WHERE aluno_id = ? AND usado_em IS NULL", (_texto(agora), aluno["id"]))
        codigo_id = conn.execute(
            "INSERT INTO aluno_codigo (aluno_id, codigo_hash, criado_em, expira_em) VALUES (?, ?, ?, ?)",
            (aluno["id"], _hash_do_codigo(aluno["id"], codigo), _texto(agora), _texto(agora + VALIDADE_DO_CODIGO)),
        ).lastrowid
    return Envio(codigo_id=codigo_id, aluno_id=aluno["id"], whatsapp=aluno["whatsapp"], codigo=codigo)


def _motivo_da_falha(erro: Exception, envio: Envio) -> str:
    """Texto curto (até 300 letras) para o banco e o log: o que deu errado, sem código nem número."""
    texto = getattr(erro, "detalhe", "") or getattr(erro, "mensagem", "") or str(erro) or type(erro).__name__
    for segredo in (envio.codigo, envio.whatsapp):
        texto = str(texto).replace(segredo, "***")
    return " ".join(str(texto).split())[:300]


def executar_envio(caminho_banco, envio: Envio, remetente) -> bool:
    """Manda o código pelo `remetente` (app/whatsapp.py) e anota no banco se deu certo. Abre a sua própria conexão (roda em
    outro fio). Nunca levanta erro: falha vira `envio = 'falhou'` no banco e uma linha de log. Devolve se foi aceito."""
    conn = db.conectar(caminho_banco)
    try:
        try:
            remetente.enviar(envio.whatsapp, envio.codigo)
            situacao, motivo = "enviado", None
        except Exception as erro:  # noqa: BLE001 - qualquer falha precisa ser anotada, e este fio não tem a quem avisar
            situacao, motivo = "falhou", _motivo_da_falha(erro, envio)
            _log.warning("Código %s (aluno %s) não foi enviado: %s", envio.codigo_id, envio.aluno_id, motivo)
        with conn:
            conn.execute("UPDATE aluno_codigo SET envio = ?, envio_erro = ? WHERE id = ?", (situacao, motivo, envio.codigo_id))
        return situacao == "enviado"
    except Exception:  # noqa: BLE001 - nem anotar deu (banco travado?): só o log, sem o código
        _log.exception("Não consegui anotar o resultado do envio do código %s", envio.codigo_id)
        return False
    finally:
        conn.close()


# ------------------------------------------------------------------ conferir o código


def _confirmar_codigo(
    conn: sqlite3.Connection, cpf: str, digitado: object, endereco: str | None, agora: datetime
) -> sqlite3.Row:
    """Confere o código do CPF e o queima. Devolve o aluno. Levanta MuitasTentativas ou CodigoInvalido."""
    chave_cpf, chave_endereco = _chave_do_cpf(cpf), _chave_do_endereco(endereco)
    _conferir_limites(
        conn,
        "codigo_errado",
        [(chave_cpf, FALHAS_POR_CPF, JANELA_DE_FALHAS), (chave_endereco, FALHAS_POR_ENDERECO, JANELA_DE_FALHAS)],
        agora,
    )
    digitos = _digitos_do_codigo(digitado)
    aluno = _aluno_do_cpf(conn, cpf)
    certo = aluno is not None and len(digitos) == TAMANHO_DO_CODIGO and _gastar_tentativa_e_conferir(conn, aluno["id"], digitos, agora)
    if not certo:
        _registrar(conn, "codigo_errado", [chave_cpf, chave_endereco], agora)
        raise CodigoInvalido("Código inválido ou vencido.")
    return aluno


def _gastar_tentativa_e_conferir(conn: sqlite3.Connection, aluno_id: int, digitos: str, agora: datetime) -> bool:
    """Gasta UMA das tentativas do código mais novo ainda vivo e, se for o certo, queima-o (só um pedido consegue).

    A tentativa é gasta ANTES de comparar e de um jeito atômico (um UPDATE só): palpites feitos ao mesmo tempo não
    ganham tentativas extras.
    """
    with conn:
        vivo = conn.execute(
            "SELECT id, codigo_hash FROM aluno_codigo"
            " WHERE aluno_id = ? AND usado_em IS NULL AND expira_em > ? AND tentativas < ? ORDER BY id DESC LIMIT 1",
            (aluno_id, _texto(agora), TENTATIVAS_POR_CODIGO),
        ).fetchone()
        if vivo is None:
            return False
        gastou = conn.execute(
            "UPDATE aluno_codigo SET tentativas = tentativas + 1 WHERE id = ? AND usado_em IS NULL AND tentativas < ?",
            (vivo["id"], TENTATIVAS_POR_CODIGO),
        ).rowcount
        if gastou != 1 or not hmac.compare_digest(_hash_do_codigo(aluno_id, digitos), vivo["codigo_hash"]):
            return False
        return conn.execute("UPDATE aluno_codigo SET usado_em = ? WHERE id = ? AND usado_em IS NULL", (_texto(agora), vivo["id"])).rowcount == 1


# ------------------------------------------------------------------ sessão (o celular logado)


def _criar_sessao(conn: sqlite3.Connection, aluno_id: int, agora: datetime) -> str:
    """Cria a sessão e devolve o token do cookie. Chamar dentro de `with conn`."""
    token = secrets.token_urlsafe(32)  # 256 bits sorteados
    conn.execute(
        "DELETE FROM aluno_sessao WHERE aluno_id = ? AND (revogado_em IS NOT NULL OR ultimo_uso_em < ?)",
        (aluno_id, _texto(agora - VALIDADE_SEM_USO)),
    )
    conn.execute(
        "INSERT INTO aluno_sessao (aluno_id, token_hash, criado_em, ultimo_uso_em) VALUES (?, ?, ?, ?)",
        (aluno_id, _hash(token), _texto(agora), _texto(agora)),
    )
    return token


def definir_senha_com_codigo(
    conn: sqlite3.Connection, cpf: str, codigo: object, senha: object, endereco: str | None, agora: datetime | None = None
) -> Entrada:
    """Primeiro acesso ou esqueci a senha: troca o código certo pela senha nova e já deixa o aluno logado.

    Levanta SenhaInvalida (senha que não serve: o código NÃO é gasto), MuitasTentativas ou CodigoInvalido.
    Todos os outros celulares em que o aluno estava logado perdem o acesso.
    """
    agora = _agora(agora)
    senha = validar_senha_nova(senha, cpf)
    aluno = _confirmar_codigo(conn, cpf, codigo, endereco, agora)
    guardado = administrador.gerar_hash(senha)
    with conn:
        conn.execute(
            "INSERT INTO aluno_senha (aluno_id, senha_hash, definida_em) VALUES (?, ?, ?)"
            " ON CONFLICT(aluno_id) DO UPDATE SET senha_hash = excluded.senha_hash, definida_em = excluded.definida_em",
            (aluno["id"], guardado, _texto(agora)),
        )
        conn.execute("UPDATE aluno_sessao SET revogado_em = ? WHERE aluno_id = ? AND revogado_em IS NULL", (_texto(agora), aluno["id"]))
        _esquecer_erros(conn, cpf)
        token = _criar_sessao(conn, aluno["id"], agora)
    return Entrada(token=token, aluno_id=aluno["id"], nome=aluno["nome"])


def entrar(conn: sqlite3.Connection, cpf: str, senha: object, endereco: str | None, agora: datetime | None = None) -> Entrada:
    """CPF + senha -> sessão. Levanta MuitasTentativas ou LoginInvalido (a mesma resposta para CPF que não existe, aluno
    sem senha, aluno que não pode entrar e senha errada)."""
    agora = _agora(agora)
    chave_cpf, chave_endereco = _chave_do_cpf(cpf), _chave_do_endereco(endereco)
    _conferir_limites(
        conn,
        "login_errado",
        [(chave_cpf, FALHAS_POR_CPF, JANELA_DE_FALHAS), (chave_endereco, FALHAS_POR_ENDERECO, JANELA_DE_FALHAS)],
        agora,
    )
    aluno = _aluno_do_cpf(conn, cpf)
    linha = conn.execute("SELECT senha_hash FROM aluno_senha WHERE aluno_id = ?", (aluno["id"],)).fetchone() if aluno else None
    # O hash lento roda SEMPRE (num hash de mentira, se não há aluno ou senha): o tempo de resposta não revela nada.
    # Texto de tamanho absurdo nem entra no hash (seria trabalho de graça para quem ataca).
    cabe = isinstance(senha, str) and 0 < len(senha) <= administrador.MAXIMO_DA_SENHA
    confere = administrador.hash_confere(senha if cabe else "", linha["senha_hash"] if linha else _hash_para_quem_nao_existe())
    if not (aluno and linha and cabe and confere):
        _registrar(conn, "login_errado", [chave_cpf, chave_endereco], agora)
        raise LoginInvalido("CPF ou senha incorretos.")
    with conn:
        _esquecer_erros(conn, cpf)
        token = _criar_sessao(conn, aluno["id"], agora)
    return Entrada(token=token, aluno_id=aluno["id"], nome=aluno["nome"])


def identificar(conn: sqlite3.Connection, token: object, agora: datetime | None = None) -> AlunoLogado | None:
    """O token do cookie -> o aluno logado, ou None se não vale (não existe, foi revogado, ficou tempo demais sem uso ou o
    cadastro do aluno deixou de seguir as regras de quem pode entrar, ver o alto do arquivo)."""
    if not isinstance(token, str) or not token:
        return None
    agora = _agora(agora)
    linha = conn.execute(
        "SELECT s.id, s.ultimo_uso_em, a.id AS aluno_id, a.nome"
        " FROM aluno_sessao s JOIN aluno a ON a.id = s.aluno_id"
        f" WHERE s.token_hash = ? AND s.revogado_em IS NULL AND {_quem_pode_entrar('a')}",
        (_hash(token),),
    ).fetchone()
    if linha is None:
        return None
    ultimo_uso = _momento(linha["ultimo_uso_em"])
    if agora - ultimo_uso > VALIDADE_SEM_USO:
        return None
    renovar = agora - ultimo_uso >= INTERVALO_DE_RENOVACAO
    if renovar:
        # Regrava no máximo uma vez por hora: gravar a cada clique travaria o banco à toa.
        with conn:
            conn.execute("UPDATE aluno_sessao SET ultimo_uso_em = ? WHERE id = ?", (_texto(agora), linha["id"]))
    return AlunoLogado(id=linha["aluno_id"], nome=linha["nome"], renovar_cookie=renovar)


def sair(conn: sqlite3.Connection, token: object, agora: datetime | None = None) -> None:
    """Revoga a sessão deste celular. Token que não existe: nada acontece."""
    if not isinstance(token, str) or not token:
        return
    with conn:
        conn.execute(
            "UPDATE aluno_sessao SET revogado_em = ? WHERE token_hash = ? AND revogado_em IS NULL",
            (_texto(_agora(agora)), _hash(token)),
        )


# ------------------------------------------------------------------ para o terminal do servidor


def resumo_para_o_terminal(conn: sqlite3.Connection, agora: datetime | None = None) -> list[str]:
    """Linhas de texto sobre o login do aluno, para `python -m app.whatsapp situacao`. Nunca mostra código, token nem CPF."""
    agora = _agora(agora)
    desde = _texto(agora - timedelta(days=1))
    por_envio = dict(conn.execute("SELECT envio, COUNT(*) FROM aluno_codigo WHERE criado_em > ? GROUP BY envio", (desde,)).fetchall())
    linhas = [
        f"Alunos com senha criada: {conn.execute('SELECT COUNT(*) FROM aluno_senha').fetchone()[0]}",
        f"Celulares logados agora: {conn.execute('SELECT COUNT(*) FROM aluno_sessao WHERE revogado_em IS NULL AND ultimo_uso_em > ?', (_texto(agora - VALIDADE_SEM_USO),)).fetchone()[0]}",
        (
            f"Códigos nas últimas 24 h: {sum(por_envio.values())} de {CODIGOS_POR_DIA} permitidos "
            f"(enviados {por_envio.get('enviado', 0)}, falharam {por_envio.get('falhou', 0)}, ainda mandando {por_envio.get('pendente', 0)})"
        ),
    ]
    falhas = conn.execute(
        "SELECT criado_em, envio_erro FROM aluno_codigo WHERE envio = 'falhou' ORDER BY id DESC LIMIT 5"
    ).fetchall()
    for falha in falhas:
        linhas.append(f"  falhou em {falha['criado_em']} UTC: {falha['envio_erro']}")
    return linhas
