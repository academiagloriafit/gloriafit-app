"""Ajustes nos treinos padrão: a revisão dos 12 treinos de Homem e Mulher (Thiago, 14/10/2026).

Os padrões são fixos e travados por senha de administrador (app/administrador.py). Trocar um deles pela tela
são DUAS senhas (excluir e guardar de novo); para 11 treinos seriam 22. Este comando troca todos de uma vez,
com UMA senha, digitada pelo Thiago no terminal do servidor (o Claude nunca digita nem lê a senha).

Uso, no terminal do contêiner do app:
    python -m app.ajustar_padroes --simular     # mostra o que mudaria; não pede senha e não grava nada
    python -m app.ajustar_padroes               # confere tudo, pede a senha, faz a cópia de segurança e grava
    python -m app.ajustar_padroes --simular --detalhes    # lista cada mudança, linha por linha

Garantias:
- TUDO OU NADA: se qualquer linha não estiver como a revisão esperava (alguém mexeu no padrão depois), nada é gravado.
- CÓPIA DE SEGURANÇA antes de gravar (a mesma de `python -m app.backup`, em /backups).
- Cada linha trocada é conferida pela posição E pelo nome do exercício, e o valor de antes tem que ser o esperado.
- O treino novo passa pela mesma conferência de um treino de verdade (limites de tamanho, exercício ativo).
- Pode rodar de novo: o que já foi ajustado é reconhecido ("já estava ajustado") e não muda.
- Nome, fila, número, professor e id de cada padrão continuam iguais (só o texto dos treinos muda; dois treinos
  mudam de nome: o 1 de Homem e o 1 de Mulher).

As mudanças (PLANOS) foram decididas uma a uma pelo Thiago; a lista está no doc do projeto.
"""

import argparse
import getpass
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

from app import administrador, db
from app.backup import BackupFalhou, fazer_backup
from app.texto import nome_para_exibir, normalizar
from app.treinos import LIMITE_NOME_TREINO, validar_fichas, validar_texto

CAMPOS = ("series", "repeticoes", "carga", "observacao")
_ROTULO = {"series": "séries", "repeticoes": "repetições", "carga": "carga", "observacao": "observação"}
_CAMPOS_DO_ITEM = ("exercicio_id", "series", "repeticoes", "carga", "pausa", "observacao", "bloco")


class Divergencia(Exception):
    """O padrão não está como a revisão esperava (ou o resultado não passaria na conferência). Nada é gravado."""


# ------------------------------------------------------------------ o plano


@dataclass(frozen=True)
class Linha:
    """Troca o texto de campos de UMA linha (exercício) de uma ficha.

    `posicao` conta de 1, na ordem da ficha. `exercicio` é o nome como aparece na tela (serve só para ter certeza de
    que é a linha certa). `trocas` = ((campo, texto de antes, texto de depois), ...); texto vazio = campo em branco.
    """

    ficha: str
    posicao: int
    exercicio: str
    trocas: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True)
class Limpeza:
    """Apaga o mesmo texto de um campo em TODAS as linhas do treino (ex.: a palavra MODERADO na carga).
    Confere que existem exatamente `quantas` linhas com esse texto."""

    campo: str
    texto: str
    quantas: int


@dataclass(frozen=True)
class Remocao:
    """Tira uma linha repetida de uma ficha. Confere o nome do exercício e quantas linhas a ficha terá depois."""

    ficha: str
    posicao: int
    exercicio: str
    itens_depois: int


@dataclass(frozen=True)
class Plano:
    modelo_id: int
    nome_atual: str | None = None  # só quando o treino muda de nome
    novo_nome: str | None = None
    linhas: tuple[Linha, ...] = ()
    limpezas: tuple[Limpeza, ...] = ()
    remocoes: tuple[Remocao, ...] = ()  # no máximo uma por ficha
    fichas_renomeadas: tuple[tuple[str, str], ...] = ()  # (nome antes, nome depois)


# Os ids são os da produção (conferidos em 14/10/2026): Homem 1 a 6 = 4, 7, 9, 11, 14, 15; Mulher 1 a 6 = 5, 6, 8, 10, 12, 13.
# O Homem 5 (id 14) não muda.
PLANOS: tuple[Plano, ...] = (
    Plano(
        4,
        nome_atual="TREINO ABC HOMEM BÁSICO",
        novo_nome="TREINO HOMEM 1",
        limpezas=(Limpeza("carga", "MODERADO", 27),),
    ),
    Plano(
        5,
        nome_atual="TREINO ABC MULHER BÁSICO",
        novo_nome="TREINO MULHER 1",
        linhas=(Linha("C GLÚTEO", 9, "PANTURRILHA EM PÉ", (("series", "", "3"), ("repeticoes", "", "20"))),),
    ),
    Plano(
        6,
        linhas=(Linha("QUADRÍCEPS", 1, "MOBILIDADE 90/90 + PRANCHA", (("repeticoes", '15/30"!', '15/30"'),)),),
    ),
    Plano(
        7,
        linhas=(Linha("A - INF", 1, "AQUECIMENTO E MOBILIDADE", (("repeticoes", "", "10"),)),),
    ),
    Plano(
        8,
        linhas=(
            Linha("GLUTEOS", 8, "ESTEIRA OU BIKE", (("series", "30", "1"), ("repeticoes", "MINUTOS", "30 MINUTOS"))),
            Linha("QUADRÍCEPS", 8, "ESTEIRA OU BIKE", (("series", "30", "1"), ("repeticoes", "MINUTOS", "30 MINUTOS"))),
        ),
        fichas_renomeadas=(("PEITO", "PEITO/OMB/TRI"), ("DORSAL", "DORSAL/BICEPS")),
    ),
    Plano(
        9,
        linhas=(
            Linha("B-INFERIORES", 3, "CADEIRA EXTENSORA + AGACH. ISO", (("repeticoes", "15/15SEGUND", "15/15 seg"),)),
            Linha("D-ABDOMINAIS", 3, "ABDOMINAL BICICLETA", (("repeticoes", "30alternand", "30 alterna"),)),
        ),
        fichas_renomeadas=(("A-PEITORAL", "A-PEITO/OMB/BIC"), ("C-DORSAL", "C-DORSAL/TRI")),
    ),
    Plano(
        10,
        linhas=(Linha("SUPERIORES 1 B", 9, "CARDIO", (("series", "", "1"), ("observacao", "20-30MIN", ""))),),
    ),
    Plano(
        11,
        linhas=(
            Linha("SEGUNDA", 1, "ALONGAMENTO DE PEITORAL + MANGUITO ABDUZIDO", (("repeticoes", "", "20"),)),
            Linha("QUINTA", 1, "MOBILIDADE", (("repeticoes", "", "20"),)),
        ),
    ),
    Plano(
        12,
        limpezas=(Limpeza("observacao", "MODERADO", 7),),
    ),
    Plano(
        13,
        remocoes=(Remocao("A POST", 7, "Cadeira flexora", 7),),
        fichas_renomeadas=(("A POST", "A PERNAS/POST"),),
    ),
    Plano(
        15,
        linhas=(
            Linha("SEGUNDA - A", 3, "MOBILIDADE", (("series", "", "1-2"), ("repeticoes", "", "10"))),
            Linha("SEGUNDA - A", 10, "ALONGAMENTO", (("series", "", "1-2"), ("repeticoes", "", "20s"))),
            Linha("TERÇA - B", 1, "ABDOMINAIS: BIC.+ REMADOR + BIC.", (("series", "", "3"), ("repeticoes", "", "20"))),
            Linha("QUINTA - C", 8, "ALONGAMENTO", (("series", "", "1-2"), ("repeticoes", "10-15", "20s"))),
            Linha("SEXTA - D", 1, "ABDOMINAL CANIVETE + REMADOR", (("series", "", "3"), ("repeticoes", "", "20"))),
            Linha("SEXTA - D", 2, "ESCALADA", (("series", "", "3"), ("repeticoes", "", "30"))),
        ),
    ),
)


# ------------------------------------------------------------------ calcular o que muda


@dataclass
class Resultado:
    modelo_id: int
    nome: str  # o nome que o padrão tem agora
    novo_nome: str
    conteudo: dict  # o conteúdo novo ({"fichas": [...]}); igual ao de hoje quando não há o que mudar
    mudancas: list[str]  # o que ainda falta fazer, uma frase por mudança (vazio = já estava ajustado)


def _texto(valor) -> str:
    return valor or ""


def _nomes_dos_exercicios(conn: sqlite3.Connection, fichas: list[dict]) -> dict[int, str]:
    ids = sorted({item["exercicio_id"] for ficha in fichas for item in ficha["itens"]})
    if not ids:
        return {}
    marcas = ",".join("?" * len(ids))
    return {
        linha["id"]: nome_para_exibir(linha["nome"])
        for linha in conn.execute(f"SELECT id, nome FROM exercicio WHERE id IN ({marcas})", ids)
    }


def calcular(conn: sqlite3.Connection, plano: Plano) -> Resultado:
    """Aplica o plano numa cópia do padrão (em memória). Levanta Divergencia se algo não bater."""
    linha_do_banco = conn.execute("SELECT nome, conteudo FROM modelo_treino WHERE id = ?", (plano.modelo_id,)).fetchone()
    if linha_do_banco is None:
        raise Divergencia(f"O treino padrão de id {plano.modelo_id} não existe.")
    nome_hoje = linha_do_banco["nome"]
    fichas = json.loads(linha_do_banco["conteudo"])["fichas"]
    exercicios = _nomes_dos_exercicios(conn, fichas)
    onde = f"id {plano.modelo_id} ({nome_hoje})"
    mudancas: list[str] = []

    apelidos = dict(plano.fichas_renomeadas)  # nome antes -> nome depois; a ficha vale por qualquer um dos dois

    def achar_ficha(nome: str) -> dict:
        for ficha in fichas:
            if ficha["nome"] in (nome, apelidos.get(nome)):
                return ficha
        raise Divergencia(f'{onde}: não achei a ficha "{nome}".')

    def conferir_exercicio(item: dict, esperado: str, lugar: str) -> None:
        achado = exercicios.get(item["exercicio_id"], "")
        if normalizar(achado) != normalizar(esperado):
            raise Divergencia(f'{lugar}: esperava o exercício "{esperado}" e achei "{achado}".')

    # 1. o nome do treino
    novo_nome = nome_hoje
    if plano.novo_nome is not None:
        if nome_hoje == plano.nome_atual:
            novo_nome = plano.novo_nome
            mudancas.append(f'nome do treino: "{nome_hoje}" → "{novo_nome}"')
        elif nome_hoje != plano.novo_nome:
            raise Divergencia(f'{onde}: esperava o nome "{plano.nome_atual}".')

    # 2. texto de campos de uma linha
    for linha in plano.linhas:
        ficha = achar_ficha(linha.ficha)
        lugar = f'{onde}, ficha "{linha.ficha}", linha {linha.posicao}'
        if not 1 <= linha.posicao <= len(ficha["itens"]):
            raise Divergencia(f"{lugar}: a ficha não tem essa linha.")
        item = ficha["itens"][linha.posicao - 1]
        conferir_exercicio(item, linha.exercicio, lugar)
        for campo, antes, depois in linha.trocas:
            atual = _texto(item.get(campo))
            if atual == antes:
                item[campo] = depois or None
                mudancas.append(f'{linha.ficha} · linha {linha.posicao} ({linha.exercicio}): {_ROTULO[campo]} "{antes}" → "{depois}"')
            elif atual != depois:
                raise Divergencia(f'{lugar}: {_ROTULO[campo]} era para estar "{antes}" e está "{atual}".')

    # 3. o mesmo texto apagado de todas as linhas
    for limpeza in plano.limpezas:
        donos = [item for ficha in fichas for item in ficha["itens"] if _texto(item.get(limpeza.campo)) == limpeza.texto]
        if len(donos) == limpeza.quantas:
            for item in donos:
                item[limpeza.campo] = None
            mudancas.append(f'{_ROTULO[limpeza.campo]} "{limpeza.texto}" apagada de {limpeza.quantas} linhas')
        elif donos:
            raise Divergencia(
                f'{onde}: esperava {limpeza.quantas} linhas com {_ROTULO[limpeza.campo]} "{limpeza.texto}" e achei {len(donos)}.'
            )

    # 4. linha repetida
    for remocao in plano.remocoes:
        ficha = achar_ficha(remocao.ficha)
        lugar = f'{onde}, ficha "{remocao.ficha}", linha {remocao.posicao}'
        quantos = len(ficha["itens"])
        if quantos == remocao.itens_depois:
            continue  # já foi tirada
        if quantos != remocao.itens_depois + 1 or not 1 <= remocao.posicao <= quantos:
            raise Divergencia(f"{lugar}: a ficha tem {quantos} linhas; esperava {remocao.itens_depois + 1}.")
        conferir_exercicio(ficha["itens"][remocao.posicao - 1], remocao.exercicio, lugar)
        del ficha["itens"][remocao.posicao - 1]
        mudancas.append(f'{remocao.ficha} · linha {remocao.posicao} ({remocao.exercicio}) repetida: tirada')

    # 5. nomes de ficha
    for antes, depois in plano.fichas_renomeadas:
        nomes = [ficha["nome"] for ficha in fichas]
        if antes in nomes:
            fichas[nomes.index(antes)]["nome"] = depois
            mudancas.append(f'nome da ficha: "{antes}" → "{depois}"')
        elif depois not in nomes:
            raise Divergencia(f'{onde}: não achei a ficha "{antes}".')

    conteudo = {"fichas": [{"nome": f["nome"], "itens": [{c: i.get(c) for c in _CAMPOS_DO_ITEM} for i in f["itens"]]} for f in fichas]}
    if mudancas:
        _conferir_resultado(conn, plano.modelo_id, novo_nome, conteudo, onde)
    return Resultado(plano.modelo_id, nome_hoje, novo_nome, conteudo, mudancas)


def _conferir_resultado(conn: sqlite3.Connection, modelo_id: int, nome: str, conteudo: dict, onde: str) -> None:
    """O padrão novo tem que passar na mesma conferência de um treino de verdade."""
    problemas: list[str] = []
    validar_texto(nome, "O nome do treino padrão", LIMITE_NOME_TREINO, True, problemas)
    validar_fichas(conn, conteudo["fichas"], problemas)
    for outro_id, outro_nome in conn.execute("SELECT id, nome FROM modelo_treino"):
        if outro_id != modelo_id and normalizar(outro_nome) == normalizar(nome):
            problemas.append(f'já existe outro treino padrão chamado "{nome}".')
    if problemas:
        raise Divergencia(f"{onde}: o treino ajustado não passa na conferência: " + " ".join(problemas))


def calcular_todos(conn: sqlite3.Connection, planos=PLANOS) -> list[Resultado]:
    """Calcula todos os planos. Se algum não bater, levanta Divergencia com TODAS as divergências."""
    resultados, erros = [], []
    for plano in planos:
        try:
            resultados.append(calcular(conn, plano))
        except Divergencia as erro:
            erros.append(str(erro))
    if erros:
        raise Divergencia("\n".join(erros))
    return resultados


# ------------------------------------------------------------------ gravar


def aplicar(conn: sqlite3.Connection, resultados: list[Resultado], planos=PLANOS) -> int:
    """Grava os padrões que ainda têm o que mudar, TUDO OU NADA. Devolve quantos padrões mudaram."""
    mudar = [r for r in resultados if r.mudancas]
    with conn:  # uma transação só: se algo falhar aqui dentro, volta tudo
        for r in mudar:
            conn.execute(
                "UPDATE modelo_treino SET nome = ?, conteudo = ? WHERE id = ?",
                (r.novo_nome, json.dumps(r.conteudo, ensure_ascii=False), r.modelo_id),
            )
        faltou = [r for r in calcular_todos(conn, planos) if r.mudancas]  # relê o que foi gravado
        if faltou:
            raise Divergencia("Depois de gravar, ainda faltava mudar: " + ", ".join(r.novo_nome for r in faltou) + ". Voltei tudo.")
    return len(mudar)


# ------------------------------------------------------------------ comando de terminal


def _abrir_banco(caminho: Path) -> sqlite3.Connection:
    if not caminho.is_file():
        raise SystemExit(f"Banco de dados não encontrado em '{caminho}'. Use --banco para indicar o arquivo certo.")
    conn = db.conectar(caminho)
    try:
        db.migrar(conn)
        db.verificar_versao(conn)
    except db.BancoDesatualizado as erro:
        conn.close()
        raise SystemExit(str(erro)) from None
    return conn


def _montar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.ajustar_padroes",
        description="Aplica de uma vez os ajustes aprovados nos treinos padrão (pede a senha de administrador, uma vez).",
    )
    parser.add_argument("--banco", default=os.environ.get("GLORIAFIT_DB", "app.db"), help="arquivo do banco (padrão: variável GLORIAFIT_DB ou app.db)")
    parser.add_argument("--copias", default="/backups", help="pasta da cópia de segurança feita antes de gravar (padrão: /backups)")
    parser.add_argument("--simular", action="store_true", help="só mostra o que mudaria: não pede senha e não grava nada")
    parser.add_argument("--detalhes", action="store_true", help="lista cada mudança, linha por linha")
    return parser


def main(argv: list[str] | None = None, pedir_senha=getpass.getpass, planos=PLANOS) -> int:
    args = _montar_parser().parse_args(argv)
    conn = _abrir_banco(Path(args.banco))
    try:
        try:
            resultados = calcular_todos(conn, planos)
        except Divergencia as erro:
            print("NADA foi gravado. Os treinos padrão não estão como a revisão esperava:", file=sys.stderr)
            print(erro, file=sys.stderr)
            return 1

        a_mudar = [r for r in resultados if r.mudancas]
        for r in resultados:
            quantas = len(r.mudancas)
            estado = f"{quantas} mudança{'s' if quantas != 1 else ''}" if quantas else "já estava ajustado"
            print(f"  id {r.modelo_id:>2} · {r.nome}: {estado}")
            if args.detalhes:
                for mudanca in r.mudancas:
                    print(f"        - {mudanca}")
        if not a_mudar:
            print("Nada a fazer: todos os treinos padrão já estão ajustados.")
            return 0
        total = sum(len(r.mudancas) for r in a_mudar)
        print(f"Total: {len(a_mudar)} treinos padrão, {total} mudanças.")
        if args.simular:
            print("Simulação: NADA foi gravado.")
            return 0

        print("Para gravar, digite a senha de administrador (ela não aparece na tela).")
        try:
            administrador.conferir_senha(conn, pedir_senha("Senha de administrador: "))
        except administrador.SenhaNaoDefinida:
            print("A senha de administrador ainda não foi definida. Nada foi alterado.", file=sys.stderr)
            return 2
        except administrador.SenhaIncorreta:
            print("Senha incorreta. Nada foi alterado.", file=sys.stderr)
            return 2
        except administrador.MuitasTentativas as erro:
            print(f"Senhas erradas demais. Tente de novo em {-(-erro.segundos // 60)} min. Nada foi alterado.", file=sys.stderr)
            return 2

        try:
            copia = fazer_backup(args.banco, args.copias)
        except (BackupFalhou, sqlite3.Error, OSError) as erro:
            print(f"Cópia de segurança NÃO feita ({erro}). Nada foi alterado.", file=sys.stderr)
            return 1
        print(f"Cópia de segurança feita: {copia.name}")

        try:
            gravados = aplicar(conn, resultados, planos)
        except (Divergencia, sqlite3.Error) as erro:
            print(f"NÃO gravei nada: {erro}", file=sys.stderr)
            return 1
        print(f"Pronto: {gravados} treinos padrão ajustados.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
