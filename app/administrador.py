"""Senha de administrador: protege o que não pode mudar por acidente.

Pedido do Thiago (13/10/2026): os treinos padrão (Treino 1 a 6 de cada fila) ficam FIXOS. O professor continua
podendo abrir um padrão e ajustar o treino só para o aluno (isso não mexe no padrão), mas ADICIONAR um treino padrão
("Salvar como treino padrão") ou EXCLUIR um que já existe só vale com a senha de administrador.

Como funciona:

1. Quem cuida do servidor define a senha, uma vez, no terminal do servidor (a senha não aparece na tela):
       python -m app.administrador definir-senha
   O comando pergunta duas vezes. Para trocar a senha, é só rodar de novo.
2. As telas de "Salvar como treino padrão" e de "Excluir" do padrão pedem a senha a cada vez (nada fica guardado no
   navegador) e mandam junto do pedido, no campo `senha_admin` do JSON (nunca na URL).
3. O servidor confere de novo, antes de qualquer outra coisa. Sem senha definida, essas ações ficam FECHADAS
   (falha para o lado seguro), nunca abertas.

Cuidados de segurança que este arquivo tem:
- O banco guarda só o HASH da senha (scrypt, com sal sorteado), nunca a senha. Quem copiar o banco não a lê.
  Aqui, ao contrário do código de autorização (app/acesso.py, sorteado com muita aleatoriedade), a senha é escolhida
  por gente: por isso usa um hash LENTO, que encarece cada palpite.
- Senha errada em excesso trava novas tentativas por um tempo (força bruta). A trava vale para o app inteiro, como a
  da tela /autorizar: alguém num computador autorizado pode atrapalhar uma ação de administrador por alguns minutos,
  mas não consegue passar por ela.
- A conferência usa comparação de tempo constante (`hmac.compare_digest`).
- Isto protege contra ACIDENTE e contra quem usa o computador autorizado sem ser o administrador. Não protege contra
  quem sabe a senha, nem contra quem tem acesso ao servidor ou ao banco (esses já podem tudo).
"""

import argparse
import getpass
import hashlib
import hmac
import os
import secrets
import sqlite3
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import db

MINIMO_DA_SENHA = 8
MAXIMO_DA_SENHA = 128

LIMITE_DE_FALHAS = 5  # senhas erradas permitidas...
JANELA_DE_FALHAS = timedelta(minutes=15)  # ...dentro deste tempo

# scrypt: custo de CPU/memória por palpite (16 MiB e dezenas de milissegundos). Os valores ficam gravados junto do
# hash, então dá para aumentar aqui no futuro sem invalidar a senha que já existe.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_TAMANHO_DO_SAL = 16
_TAMANHO_DA_CHAVE = 32

_FORMATO_DATA = "%Y-%m-%d %H:%M:%S"  # UTC, como o resto do banco


class SenhaInvalida(ValueError):
    """A senha nova que se quer definir não serve (curta ou longa demais, em branco)."""


class SenhaNaoDefinida(Exception):
    """Ainda não existe senha de administrador no servidor: as ações protegidas ficam fechadas."""


class SenhaIncorreta(Exception):
    """A senha digitada não confere. De propósito, sem dizer mais nada."""


class MuitasTentativas(Exception):
    """Muitas senhas erradas seguidas: novas tentativas ficam travadas por um tempo."""

    def __init__(self, segundos: int):
        super().__init__(f"Tente de novo em {segundos} segundos.")
        self.segundos = segundos


# ------------------------------------------------------------------ pequenas ajudas


def _agora(agora: datetime | None) -> datetime:
    return (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)


def _texto(momento: datetime) -> str:
    return momento.astimezone(timezone.utc).strftime(_FORMATO_DATA)


def _momento(texto: str) -> datetime:
    return datetime.strptime(texto, _FORMATO_DATA).replace(tzinfo=timezone.utc)


def _bytes_da_senha(senha: str) -> bytes:
    # NFKC: o mesmo "ã" digitado como uma letra só ou como "a" + til vira o mesmo texto.
    return unicodedata.normalize("NFKC", senha).encode("utf-8")


def _hash_da_senha(senha: str, sal: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(_bytes_da_senha(senha), salt=sal, n=n, r=r, p=p, dklen=_TAMANHO_DA_CHAVE, maxmem=128 * 1024 * 1024)


def gerar_hash(senha: str) -> str:
    """'scrypt$N$r$p$sal$chave' (sal e chave em hexadecimal). Cada chamada sorteia um sal novo."""
    sal = secrets.token_bytes(_TAMANHO_DO_SAL)
    chave = _hash_da_senha(senha, sal, _SCRYPT_N, _SCRYPT_R, _SCRYPT_P)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${sal.hex()}${chave.hex()}"


def hash_confere(senha: str, guardado: str) -> bool:
    """A senha digitada bate com o hash guardado? Hash estragado ou de outro formato nunca confere."""
    try:
        formato, n, r, p, sal, chave = guardado.split("$")
        if formato != "scrypt":
            return False
        esperado = bytes.fromhex(chave)
        calculado = _hash_da_senha(senha, bytes.fromhex(sal), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calculado, esperado)


def validar_senha_nova(senha: object) -> str:
    """A senha que se quer definir, se servir; senão levanta SenhaInvalida com o motivo em português."""
    if not isinstance(senha, str) or not senha.strip():
        raise SenhaInvalida("A senha não pode ficar em branco.")
    if len(senha) < MINIMO_DA_SENHA:
        raise SenhaInvalida(f"A senha precisa ter pelo menos {MINIMO_DA_SENHA} caracteres.")
    if len(senha) > MAXIMO_DA_SENHA:
        raise SenhaInvalida(f"A senha pode ter no máximo {MAXIMO_DA_SENHA} caracteres.")
    if not senha.isprintable():
        raise SenhaInvalida("A senha tem caracteres que não podem ser usados.")
    return senha


# ------------------------------------------------------------------ definir e conferir


def tem_senha(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM senha_administrador WHERE id = 1").fetchone() is not None


def definir_senha(conn: sqlite3.Connection, senha: object, agora: datetime | None = None) -> None:
    """Define (ou troca) a senha de administrador. Zera as tentativas erradas."""
    senha = validar_senha_nova(senha)
    guardado = gerar_hash(senha)
    with conn:
        conn.execute(
            "INSERT INTO senha_administrador (id, senha_hash, definida_em) VALUES (1, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET senha_hash = excluded.senha_hash, definida_em = excluded.definida_em",
            (guardado, _texto(_agora(agora))),
        )
        conn.execute("DELETE FROM senha_administrador_falha")


def conferir_senha(conn: sqlite3.Connection, digitada: object, agora: datetime | None = None) -> None:
    """Confere a senha de administrador digitada. Não devolve nada: se passar, segue; senão levanta uma destas:

    MuitasTentativas (travado por excesso de erros: nem confere a senha), SenhaNaoDefinida (o servidor ainda não tem
    senha) ou SenhaIncorreta. Acertar zera as tentativas erradas.
    """
    agora = _agora(agora)
    with conn:
        conn.execute("DELETE FROM senha_administrador_falha WHERE em <= ?", (_texto(agora - JANELA_DE_FALHAS),))
    recentes = [_momento(linha[0]) for linha in conn.execute("SELECT em FROM senha_administrador_falha ORDER BY em")]
    if len(recentes) >= LIMITE_DE_FALHAS:
        # Travado: nem confere (senão o atacante continuaria tentando) e NÃO registra mais falhas (senão ficaria
        # travado para sempre). Destrava quando a falha mais antiga sair da janela.
        espera = (recentes[0] + JANELA_DE_FALHAS) - agora
        raise MuitasTentativas(max(1, int(espera.total_seconds()) + 1))

    linha = conn.execute("SELECT senha_hash FROM senha_administrador WHERE id = 1").fetchone()
    if linha is None:
        raise SenhaNaoDefinida("O servidor ainda não tem senha de administrador.")

    # Texto de tamanho absurdo nem entra no hash (seria trabalho de graça para quem ataca).
    certa = isinstance(digitada, str) and 0 < len(digitada) <= MAXIMO_DA_SENHA and hash_confere(digitada, linha["senha_hash"])
    with conn:
        if certa:
            conn.execute("DELETE FROM senha_administrador_falha")
        else:
            conn.execute("INSERT INTO senha_administrador_falha (em) VALUES (?)", (_texto(agora),))
    if not certa:
        raise SenhaIncorreta("Senha incorreta.")


def situacao(conn: sqlite3.Connection, agora: datetime | None = None) -> dict:
    """{"definida": bool, "definida_em": datetime ou None, "travada_por": segundos (0 = não travada)}."""
    agora = _agora(agora)
    linha = conn.execute("SELECT definida_em FROM senha_administrador WHERE id = 1").fetchone()
    recentes = sorted(
        _momento(r[0])
        for r in conn.execute("SELECT em FROM senha_administrador_falha")
        if agora - _momento(r[0]) < JANELA_DE_FALHAS
    )
    travada = 0
    if len(recentes) >= LIMITE_DE_FALHAS:
        travada = max(1, int(((recentes[0] + JANELA_DE_FALHAS) - agora).total_seconds()) + 1)
    return {"definida": linha is not None, "definida_em": _momento(linha[0]) if linha else None, "travada_por": travada}


# ------------------------------------------------------------------ comando de terminal


def _abrir_banco(caminho: Path) -> sqlite3.Connection:
    if not caminho.is_file():
        raise SystemExit(f"Banco de dados não encontrado em '{caminho}'. Use --banco para indicar o arquivo certo.")
    conn = db.conectar(caminho)
    try:
        db.migrar(conn)
        db.verificar_versao(conn)
        tem_tabela = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'senha_administrador'").fetchone()
    except db.BancoDesatualizado as erro:
        conn.close()
        raise SystemExit(str(erro)) from None
    if not tem_tabela:
        conn.close()
        raise SystemExit(f"O banco '{caminho}' ainda não tem as tabelas do app. Crie-o antes com: python -m app.importar_exercicios dados/quadro_exercicios_v2.xlsx app.db")
    return conn


def _montar_parser() -> argparse.ArgumentParser:
    comum = argparse.ArgumentParser(add_help=False)
    comum.add_argument("--banco", default=argparse.SUPPRESS, help="arquivo do banco (padrão: variável GLORIAFIT_DB ou app.db)")
    parser = argparse.ArgumentParser(
        prog="python -m app.administrador",
        description="Senha de administrador (adicionar ou excluir treino padrão).",
    )
    parser.add_argument("--banco", default=os.environ.get("GLORIAFIT_DB", "app.db"), help="arquivo do banco (padrão: variável GLORIAFIT_DB ou app.db)")
    comandos = parser.add_subparsers(dest="comando", required=True)
    comandos.add_parser("definir-senha", parents=[comum], help="define (ou troca) a senha; ela é pedida duas vezes e não aparece na tela")
    comandos.add_parser("situacao", parents=[comum], help="diz se a senha já foi definida (nunca mostra a senha)")
    return parser


def main(argv: list[str] | None = None, pedir_senha=getpass.getpass) -> int:
    args = _montar_parser().parse_args(argv)
    conn = _abrir_banco(Path(args.banco))
    try:
        if args.comando == "situacao":
            estado = situacao(conn)
            if not estado["definida"]:
                print("A senha de administrador AINDA NÃO foi definida: adicionar e excluir treino padrão estão fechados.")
            else:
                print(f"Senha de administrador definida em {estado['definida_em'].strftime('%d/%m/%Y %H:%M')} (UTC).")
                if estado["travada_por"]:
                    print(f"Travada por excesso de senhas erradas: libera em {-(-estado['travada_por'] // 60)} min.")
            return 0
        # definir-senha
        try:
            primeira = pedir_senha("Nova senha de administrador (não aparece na tela): ")
            validar_senha_nova(primeira)
            segunda = pedir_senha("Repita a senha: ")
            if primeira != segunda:
                raise SenhaInvalida("As duas senhas são diferentes. Nada foi alterado.")
            definir_senha(conn, primeira)
        except SenhaInvalida as erro:
            print(f"Erro: {erro}", file=sys.stderr)
            return 2
        print("Senha de administrador definida. Guarde-a em lugar seguro: ela não pode ser lida de volta, só trocada.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
