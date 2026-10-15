"""O treino que o aluno vê no celular (tela /aluno, rota GET /api/aluno/treino).

Regra (decidida pelo Thiago em 08/10/2026, ver README "Ciclo do treino"): o aluno vê só o treino ATIVO, e cada
aluno tem no máximo um. Treino inativo (concluído ou trocado por outro) fica no histórico do professor e o aluno
não vê.

Tudo sai daqui em texto pronto (dose "4 × 12", intervalo "1 min 30 s", etiquetas "A1"/"A2" do bi-set), com as mesmas
funções que a impressão do cupom usa, para o celular e o papel nunca discordarem. O navegador só desenha.

Também é daqui que o aluno marca "fiz esta ficha hoje" (e desfaz): no máximo UMA vez por ficha por dia, dia de
Brasília (decisão do Thiago, 15/10/2026). A contagem alimenta a meta "treinos por ficha" do professor (app/ciclo.py).

O que NÃO sai daqui, de propósito: ids (do treino, da ficha, do exercício), quem montou, a origem (app ou Data4U),
o aviso de "hora de trocar" (só o professor vê) e dados de outros treinos. O aluno recebe só o que precisa para treinar,
mais o próprio andamento (quantas vezes fez cada ficha e a meta).
"""

import sqlite3
from datetime import datetime, time, timedelta

from app import ciclo, treinos
from app.alunos import dose_do_item, etiquetas_dos_itens, texto_da_pausa
from app.datas import FUSO_DA_ACADEMIA, agora_utc, formatar_dia, momento_para_texto

_NOME_DO_BLOCO = {2: "Bi-set", 3: "Tri-set"}


def _lista_com_e(etiquetas: list[str]) -> str:
    """['A1', 'A2'] -> 'A1 e A2'; ['A1', 'A2', 'A3'] -> 'A1, A2 e A3'."""
    if len(etiquetas) == 1:
        return etiquetas[0]
    return ", ".join(etiquetas[:-1]) + " e " + etiquetas[-1]


def _exercicio(item: dict, etiqueta: str) -> dict:
    return {
        "etiqueta": etiqueta,
        "exercicio": item["exercicio"],
        "dose": dose_do_item(item),
        "carga": (item["carga"] or "").strip(),
        "intervalo": texto_da_pausa(item["pausa"]),
        "observacao": (item["observacao"] or "").strip(),
    }


def _grupos_da_ficha(itens: list[dict]) -> list[dict]:
    """Os exercícios da ficha na ordem, juntando os do mesmo bi-set/tri-set.

    Cada grupo: {"nome": None | "Bi-set" | "Tri-set" | "Sequência", "instrucao": "" | "Faça A1 e A2 seguidos",
    "exercicios": [...]}. Exercício sozinho = grupo sem nome com um exercício.
    """
    etiquetas = etiquetas_dos_itens(itens)
    grupos: list[dict] = []
    ultimo_bloco = None
    for item, etiqueta in zip(itens, etiquetas, strict=True):
        bloco = item["bloco"]
        if bloco is not None and grupos and bloco == ultimo_bloco:
            grupos[-1]["exercicios"].append(_exercicio(item, etiqueta))
        else:
            grupos.append({"nome": None, "instrucao": "", "exercicios": [_exercicio(item, etiqueta)]})
        ultimo_bloco = bloco
    for grupo in grupos:
        quantos = len(grupo["exercicios"])
        if quantos >= 2:
            grupo["nome"] = _NOME_DO_BLOCO.get(quantos, "Sequência")
            grupo["instrucao"] = f"Faça {_lista_com_e([e['etiqueta'] for e in grupo['exercicios']])} seguidos"
    return grupos


def _limites_do_dia(agora: datetime) -> tuple[str, str]:
    """O dia de hoje em Brasília, como o par [começo, fim) em UTC no formato do banco (`sessao.feita_em`).

    "Hoje" é o dia do calendário da academia: uma ficha marcada às 23h30 e outra às 00h10 são de dias diferentes,
    mesmo que o relógio de Londres ainda esteja no mesmo dia.
    """
    hoje_local = agora.astimezone(FUSO_DA_ACADEMIA).date()
    comeco = datetime.combine(hoje_local, time.min, tzinfo=FUSO_DA_ACADEMIA)
    fim = datetime.combine(hoje_local + timedelta(days=1), time.min, tzinfo=FUSO_DA_ACADEMIA)
    return momento_para_texto(comeco), momento_para_texto(fim)


def _andamento_das_fichas(conn: sqlite3.Connection, treino_id: int, agora: datetime) -> dict[int, dict]:
    """{ordem da ficha: {"feitas": quantas vezes (neste treino), "feita_hoje": bool}}."""
    comeco, fim = _limites_do_dia(agora)
    linhas = conn.execute(
        """
        SELECT ficha_ordem, COUNT(*), MAX(feita_em >= ? AND feita_em < ?)
        FROM sessao WHERE treino_id = ? GROUP BY ficha_ordem
        """,
        (comeco, fim, treino_id),
    )
    return {ordem: {"feitas": feitas, "feita_hoje": bool(hoje)} for ordem, feitas, hoje in linhas}


def treino_do_aluno(conn: sqlite3.Connection, aluno_id: int, agora: datetime | None = None) -> dict | None:
    """O treino ativo do aluno pronto para mostrar, ou None se ele não tem treino ativo.

    {"nome", "inicio" ("06/10/2026" ou None), "fim" (idem), "meta_por_ficha" (quantas vezes cada ficha, ou None),
    "fichas": [{"nome", "ordem", "feitas", "feita_hoje", "grupos": [...]}]}.
    `ordem` (1 = A, 2 = B...) é o que o celular manda de volta ao marcar a ficha como feita.
    Ficha sem nenhum exercício não aparece (não há o que mostrar).
    """
    agora = agora or agora_utc()
    linha = conn.execute("SELECT id FROM treino WHERE aluno_id = ? AND ativo = 1", (aluno_id,)).fetchone()
    if linha is None:
        return None
    treino = treinos.obter_treino(conn, linha["id"])
    if treino is None:  # apagado entre as duas consultas (a importação do Data4U apaga e recria)
        return None
    andamento = _andamento_das_fichas(conn, linha["id"], agora)
    return {
        "nome": treino["nome"],
        "inicio": formatar_dia(treino["inicio"]),
        "fim": formatar_dia(treino["fim"]),
        "meta_por_ficha": treino["sessoes_por_ficha"],
        "fichas": [
            {
                "nome": ficha["nome"],
                "ordem": ficha["ordem"],
                "feitas": andamento.get(ficha["ordem"], {}).get("feitas", 0),
                "feita_hoje": andamento.get(ficha["ordem"], {}).get("feita_hoje", False),
                "grupos": _grupos_da_ficha(ficha["itens"]),
            }
            for ficha in treino["fichas"]
            if ficha["itens"]
        ],
    }


# ------------------------------------------------------------------ "Treino concluído"


class MarcacaoInvalida(Exception):
    """O aluno não pode marcar isto. A mensagem já está pronta para mostrar; `status` é o código da resposta."""

    def __init__(self, mensagem: str, status: int):
        super().__init__(mensagem)
        self.status = status


def _ficha_do_treino_ativo(conn: sqlite3.Connection, aluno_id: int, ficha_ordem: object) -> int:
    """O id do treino ativo do aluno, se ele tem esse treino e essa ficha; senão MarcacaoInvalida."""
    if isinstance(ficha_ordem, bool) or not isinstance(ficha_ordem, int) or ficha_ordem < 1:
        raise MarcacaoInvalida("Escolha a ficha de novo.", 400)
    ativo = ciclo.treino_ativo(conn, aluno_id)
    if ativo is None:
        raise MarcacaoInvalida("Você não tem um treino ativo. Atualize a página.", 409)
    existe = conn.execute(
        "SELECT 1 FROM ficha WHERE treino_id = ? AND ordem = ?", (ativo["id"], ficha_ordem)
    ).fetchone()
    if existe is None:
        raise MarcacaoInvalida("Esta ficha não existe no seu treino. Atualize a página.", 404)
    return ativo["id"]


def _quantas_vezes(conn: sqlite3.Connection, treino_id: int, ficha_ordem: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM sessao WHERE treino_id = ? AND ficha_ordem = ?", (treino_id, ficha_ordem)
    ).fetchone()[0]


def marcar_ficha_feita(
    conn: sqlite3.Connection, aluno_id: int, ficha_ordem: object, agora: datetime | None = None
) -> dict:
    """O aluno marca "fiz esta ficha hoje". No máximo UMA vez por ficha por dia (decisão do Thiago, 15/10/2026).

    Marcar de novo no mesmo dia não faz nada (`ja_marcada: True`). Devolve {"ficha", "ja_marcada", "feitas"}.
    A conferência e a gravação acontecem na mesma transação (`BEGIN IMMEDIATE`): dois toques ao mesmo tempo,
    ou o mesmo aluno em dois celulares, nunca gravam duas vezes.
    """
    agora = agora or agora_utc()
    comeco, fim = _limites_do_dia(agora)
    conn.execute("BEGIN IMMEDIATE")
    try:
        treino_id = _ficha_do_treino_ativo(conn, aluno_id, ficha_ordem)
        ja_marcada = conn.execute(
            "SELECT 1 FROM sessao WHERE treino_id = ? AND ficha_ordem = ? AND feita_em >= ? AND feita_em < ?",
            (treino_id, ficha_ordem, comeco, fim),
        ).fetchone() is not None
        if not ja_marcada:
            conn.execute(
                "INSERT INTO sessao (treino_id, ficha_ordem, feita_em) VALUES (?, ?, ?)",
                (treino_id, ficha_ordem, momento_para_texto(agora)),
            )
        feitas = _quantas_vezes(conn, treino_id, ficha_ordem)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return {"ficha": ficha_ordem, "ja_marcada": ja_marcada, "feitas": feitas}


def desfazer_marcacao_de_hoje(
    conn: sqlite3.Connection, aluno_id: int, ficha_ordem: object, agora: datetime | None = None
) -> dict:
    """O aluno desfaz a marcação de HOJE de uma ficha (toque errado). Só apaga as de hoje, nunca as de outros dias.

    Devolve {"ficha", "feitas"} (quantas ficaram). Se não havia marcação hoje, não muda nada.
    """
    agora = agora or agora_utc()
    comeco, fim = _limites_do_dia(agora)
    conn.execute("BEGIN IMMEDIATE")
    try:
        treino_id = _ficha_do_treino_ativo(conn, aluno_id, ficha_ordem)
        conn.execute(
            "DELETE FROM sessao WHERE treino_id = ? AND ficha_ordem = ? AND feita_em >= ? AND feita_em < ?",
            (treino_id, ficha_ordem, comeco, fim),
        )
        feitas = _quantas_vezes(conn, treino_id, ficha_ordem)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return {"ficha": ficha_ordem, "feitas": feitas}
