"""Treinos padrão e cópia de treinos: o botão "Importar treino" da tela de lançar treino.

Dois jeitos de começar um treino sem partir do zero (pedido do Thiago, 09/10/2026):
- um TREINO PADRÃO: treino pronto guardado na tabela `modelo_treino`, que serve para qualquer aluno;
- o treino de OUTRO ALUNO (ou um treino antigo do mesmo aluno): útil quando o perfil é parecido.

Nos dois casos o servidor NÃO grava treino nenhum para o aluno: ele devolve o treino no formato que a
tela de montar entende (`para_montar`). O professor confere, ajusta e só então clica em "Salvar treino",
que passa pela validação de sempre (app/treinos.py). Copiar não liga o aluno ao original: depois de salvo,
o treino é só dele.

Exercício que não está mais ativo na lista (acontece nos treinos antigos do Data4U) vem marcado com
`indisponivel`: a tela pede para o professor trocá-lo, e o servidor recusaria o treino se ele ficasse.
"""

import json
import sqlite3

from app.alunos import data_local
from app.datas import formatar_dia
from app.texto import nome_para_exibir, normalizar
from app.treinos import (
    LIMITE_NOME_TREINO,
    LIMITE_QUEM_MONTOU,
    MAXIMO_NO_BLOCO,
    MINIMO_NO_BLOCO,
    AlunoNaoEncontrado,
    TreinoInvalido,
    validar_fichas,
    validar_sessoes_por_ficha,
    validar_texto,
)

# Nome mostrado quando o exercício de um padrão não existe mais no banco. Nunca acontece hoje (exercício
# nunca é apagado, só desativado), mas o padrão guarda só o id e a tela não pode quebrar por isso.
NOME_DO_EXERCICIO_SUMIDO = "Exercício que não existe mais"

# Pedaços de consulta: o SQLite limita quantos "?" cabem numa consulta só.
_PEDACO_DE_IDS = 500


class ModeloNaoEncontrado(Exception):
    pass


class TreinoNaoEncontrado(Exception):
    pass


# ------------------------------------------------------------------ ajudantes


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _resumo(fichas: list[dict]) -> tuple[int, int, str]:
    """(quantidade de fichas, quantidade de exercícios, texto '3 fichas · 24 exercícios')."""
    exercicios = sum(len(f["itens"]) for f in fichas)
    return len(fichas), exercicios, f"{_plural(len(fichas), 'ficha', 'fichas')} · {_plural(exercicios, 'exercício', 'exercícios')}"


def normalizar_blocos(itens: list[dict]) -> None:
    """Deixa os bi-sets/tri-sets de uma ficha no formato que a tela e o servidor aceitam. Altera `itens`.

    Cada sequência de itens vizinhos com o mesmo `bloco` é um bloco; ele só vale com 2 ou 3 itens (senão
    os itens viram exercícios sozinhos) e ganha um número novo (1, 2, 3...), mesmo que o número antigo
    apareça de novo mais abaixo. Treinos do Data4U podem trazer blocos fora desse molde.
    """
    proximo = 1
    i = 0
    while i < len(itens):
        bloco = itens[i]["bloco"]
        j = i + 1
        if bloco is not None:
            while j < len(itens) and itens[j]["bloco"] == bloco:
                j += 1
            if MINIMO_NO_BLOCO <= j - i <= MAXIMO_NO_BLOCO:
                for item in itens[i:j]:
                    item["bloco"] = proximo
                proximo += 1
            else:
                for item in itens[i:j]:
                    item["bloco"] = None
        i = j


def _exercicios_por_id(conn: sqlite3.Connection, ids: set[int]) -> dict[int, sqlite3.Row]:
    achados: dict[int, sqlite3.Row] = {}
    lista = sorted(ids)
    for inicio in range(0, len(lista), _PEDACO_DE_IDS):
        pedaco = lista[inicio : inicio + _PEDACO_DE_IDS]
        marcas = ",".join("?" * len(pedaco))
        for linha in conn.execute(f"SELECT id, nome, ativo FROM exercicio WHERE id IN ({marcas})", pedaco):
            achados[linha["id"]] = linha
    return achados


def _fichas_cruas_do_treino(conn: sqlite3.Connection, treino_id: int) -> list[dict]:
    """As fichas do treino no formato do pedido de salvar (exercicio_id, series, ...), com blocos arrumados."""
    fichas = []
    for ficha in conn.execute("SELECT id, nome FROM ficha WHERE treino_id = ? ORDER BY ordem", (treino_id,)):
        itens = [
            {
                "exercicio_id": i["exercicio_id"],
                "series": i["series"],
                "repeticoes": i["repeticoes"],
                "carga": i["carga"],
                "pausa": i["pausa"],
                "observacao": i["observacao"],
                "bloco": i["bloco"],
            }
            for i in conn.execute(
                "SELECT exercicio_id, series, repeticoes, carga, pausa, observacao, bloco"
                " FROM ficha_item WHERE ficha_id = ? ORDER BY ordem",
                (ficha["id"],),
            )
        ]
        normalizar_blocos(itens)
        fichas.append({"nome": ficha["nome"], "itens": itens})
    return fichas


def _ids_dos_exercicios(fichas: list[dict]) -> set[int]:
    return {item["exercicio_id"] for ficha in fichas for item in ficha["itens"]}


def para_montar(conn: sqlite3.Connection, nome: str, sessoes_por_ficha: int | None, fichas: list[dict]) -> dict:
    """O treino no formato da tela de montar.

    {"nome", "sessoes_por_ficha", "indisponiveis" (quantos exercícios precisam ser trocados),
     "fichas": [{"nome", "itens": [{"exercicio_id", "nome" (sem o número da máquina), "series", "repeticoes",
                "carga", "observacao" (textos, vazios em vez de None), "pausa" (segundos ou None),
                "bloco", "indisponivel"}]}]}
    """
    exercicios = _exercicios_por_id(conn, _ids_dos_exercicios(fichas))
    indisponiveis = 0
    saida = []
    for ficha in fichas:
        itens = []
        for item in ficha["itens"]:
            exercicio = exercicios.get(item["exercicio_id"])
            fora = exercicio is None or not exercicio["ativo"]
            indisponiveis += fora
            itens.append(
                {
                    "exercicio_id": item["exercicio_id"],
                    "nome": nome_para_exibir(exercicio["nome"]) if exercicio else NOME_DO_EXERCICIO_SUMIDO,
                    "series": item["series"] or "",
                    "repeticoes": item["repeticoes"] or "",
                    "carga": item["carga"] or "",
                    "pausa": item["pausa"] or None,
                    "observacao": item["observacao"] or "",
                    "bloco": item["bloco"],
                    "indisponivel": fora,
                }
            )
        saida.append({"nome": ficha["nome"], "itens": itens})
    return {"nome": nome, "sessoes_por_ficha": sessoes_por_ficha, "indisponiveis": indisponiveis, "fichas": saida}


# ------------------------------------------------------------------ treinos padrão


def criar_modelo(conn: sqlite3.Connection, dados) -> int:
    """Guarda um treino padrão. Devolve o id.

    `dados` = {"nome": str (até 40 letras), "montado_por": str (até 60), "sessoes_por_ficha": int ou None,
               "fichas": [{"nome", "itens": [...]}]} (o mesmo formato do pedido de salvar treino).
    Vale a mesma conferência de um treino de verdade: todos os exercícios existem e estão ativos, limites
    de tamanho, bi-sets certos. Dois padrões não têm o mesmo nome. Tudo ou nada.
    """
    if not isinstance(dados, dict):
        raise TreinoInvalido(["Formato do pedido inválido."])
    problemas: list[str] = []
    nome = validar_texto(dados.get("nome"), "O nome do treino padrão", LIMITE_NOME_TREINO, True, problemas)
    montado_por = validar_texto(dados.get("montado_por"), "O nome de quem montou", LIMITE_QUEM_MONTOU, True, problemas)
    sessoes = validar_sessoes_por_ficha(dados.get("sessoes_por_ficha"), problemas)
    fichas = validar_fichas(conn, dados.get("fichas"), problemas)
    if problemas:
        raise TreinoInvalido(problemas)

    mensagem_de_nome_repetido = f'Já existe um treino padrão chamado "{nome}". Escolha outro nome.'
    if normalizar(nome) in {normalizar(r[0]) for r in conn.execute("SELECT nome FROM modelo_treino")}:
        raise TreinoInvalido([mensagem_de_nome_repetido], status=409)

    conteudo = {
        "fichas": [
            {
                "nome": ficha["nome"],
                "itens": [
                    {campo: item[campo] for campo in ("exercicio_id", "series", "repeticoes", "carga", "pausa", "observacao", "bloco")}
                    for item in ficha["itens"]
                ],
            }
            for ficha in fichas
        ]
    }
    try:
        with conn:
            return conn.execute(
                "INSERT INTO modelo_treino (nome, montado_por, sessoes_por_ficha, conteudo) VALUES (?, ?, ?, ?)",
                (nome, montado_por, sessoes, json.dumps(conteudo, ensure_ascii=False)),
            ).lastrowid
    except sqlite3.IntegrityError as erro:
        # Dois "salvar" ao mesmo tempo com o mesmo nome: o índice do banco barra o segundo.
        if erro.sqlite_errorcode != sqlite3.SQLITE_CONSTRAINT_UNIQUE:
            raise
        raise TreinoInvalido([mensagem_de_nome_repetido], status=409) from None


def criar_modelo_do_treino(conn: sqlite3.Connection, treino_id: int, nome) -> int:
    """Botão "Salvar como treino padrão" da ficha do aluno: transforma um treino que já existe em padrão.

    Fica com o professor e a meta ("treinos por ficha") do treino original. Treino com exercício que saiu da
    lista (comum nos antigos do Data4U) não vira padrão: o aviso diz quais são.
    """
    treino = conn.execute(
        "SELECT id, montado_por, sessoes_por_ficha FROM treino WHERE id = ?", (treino_id,)
    ).fetchone()
    if treino is None:
        raise TreinoNaoEncontrado(treino_id)
    fichas = _fichas_cruas_do_treino(conn, treino_id)
    exercicios = _exercicios_por_id(conn, _ids_dos_exercicios(fichas))
    fora = sorted(
        {nome_para_exibir(e["nome"]) for e in exercicios.values() if not e["ativo"]}
    )
    if fora:
        mostrados = ", ".join(fora[:3]) + (f" e mais {len(fora) - 3}" if len(fora) > 3 else "")
        raise TreinoInvalido(
            [
                "Este treino usa exercícios que não estão mais na lista (" + mostrados + "), "
                "então não pode virar treino padrão. Monte-o de novo com exercícios da lista."
            ]
        )
    return criar_modelo(
        conn,
        {
            "nome": nome,
            "montado_por": treino["montado_por"],
            "sessoes_por_ficha": treino["sessoes_por_ficha"],
            "fichas": fichas,
        },
    )


def listar_modelos(conn: sqlite3.Connection) -> list[dict]:
    """Os treinos padrão, em ordem alfabética, com um resumo ('3 fichas · 24 exercícios')."""
    modelos = []
    for linha in conn.execute(
        "SELECT id, nome, montado_por, sessoes_por_ficha, conteudo, criado_em FROM modelo_treino"
        " ORDER BY nome COLLATE NOCASE, id"
    ):
        fichas = json.loads(linha["conteudo"])["fichas"]
        quantas_fichas, quantos_exercicios, resumo = _resumo(fichas)
        modelos.append(
            {
                "id": linha["id"],
                "nome": linha["nome"],
                "montado_por": linha["montado_por"],
                "sessoes_por_ficha": linha["sessoes_por_ficha"],
                "criado_em": data_local(linha["criado_em"]),
                "fichas": quantas_fichas,
                "exercicios": quantos_exercicios,
                "resumo": resumo,
            }
        )
    return modelos


def modelo_para_montar(conn: sqlite3.Connection, modelo_id: int) -> dict | None:
    """O treino padrão no formato da tela de montar, ou None se não existe."""
    linha = conn.execute(
        "SELECT nome, sessoes_por_ficha, conteudo FROM modelo_treino WHERE id = ?", (modelo_id,)
    ).fetchone()
    if linha is None:
        return None
    return para_montar(conn, linha["nome"], linha["sessoes_por_ficha"], json.loads(linha["conteudo"])["fichas"])


def excluir_modelo(conn: sqlite3.Connection, modelo_id: int) -> None:
    """Apaga um treino padrão. Os treinos que já foram copiados para alunos não mudam."""
    with conn:
        apagados = conn.execute("DELETE FROM modelo_treino WHERE id = ?", (modelo_id,)).rowcount
    if apagados == 0:
        raise ModeloNaoEncontrado(modelo_id)


# ------------------------------------------------------------------ treino de outro aluno


def listar_treinos_do_aluno(conn: sqlite3.Connection, aluno_id: int) -> list[dict]:
    """Os treinos do aluno que podem ser copiados (o ativo primeiro, depois do mais novo para o mais antigo).

    Treino sem nenhum exercício (existe no histórico do Data4U) não aparece: não há o que copiar.
    """
    if conn.execute("SELECT 1 FROM aluno WHERE id = ?", (aluno_id,)).fetchone() is None:
        raise AlunoNaoEncontrado(aluno_id)
    resultado = []
    for t in conn.execute(
        """
        SELECT t.id, t.nome, t.ativo, t.origem, t.inicio, t.criado_em, t.montado_por,
               (SELECT COUNT(*) FROM ficha f WHERE f.treino_id = t.id) AS fichas,
               (SELECT COUNT(*) FROM ficha_item i JOIN ficha f ON f.id = i.ficha_id WHERE f.treino_id = t.id) AS exercicios
        FROM treino t WHERE t.aluno_id = ?
        ORDER BY t.ativo DESC, t.criado_em DESC, t.id DESC
        """,
        (aluno_id,),
    ):
        if t["exercicios"] == 0:
            continue
        resultado.append(
            {
                "id": t["id"],
                "nome": t["nome"],
                "ativo": bool(t["ativo"]),
                "do_data4u": t["origem"] == "data4u",
                "inicio": formatar_dia(t["inicio"]) or data_local(t["criado_em"]),
                "montado_por": t["montado_por"],
                "fichas": t["fichas"],
                "exercicios": t["exercicios"],
                "resumo": f"{_plural(t['fichas'], 'ficha', 'fichas')} · {_plural(t['exercicios'], 'exercício', 'exercícios')}",
            }
        )
    return resultado


def treino_para_montar(conn: sqlite3.Connection, treino_id: int) -> dict | None:
    """O treino de um aluno no formato da tela de montar, ou None se não existe."""
    treino = conn.execute("SELECT nome, sessoes_por_ficha FROM treino WHERE id = ?", (treino_id,)).fetchone()
    if treino is None:
        return None
    return para_montar(conn, treino["nome"], treino["sessoes_por_ficha"], _fichas_cruas_do_treino(conn, treino_id))
