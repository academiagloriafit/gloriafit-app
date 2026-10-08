"""O ciclo do treino: ativo/inativo, "Concluído", sessões feitas e o aviso de trocar o treino.

Regras (decisões do Thiago, 08/10/2026):

- Cada aluno tem NO MÁXIMO UM treino ativo (o banco garante). Os outros ficam inativos, no histórico;
  o aluno só vê o ativo.
- O professor clica em "Concluído" quando o treino acaba: o treino vira inativo e vai para o histórico.
- O professor pode dar ao treino uma data de fim e uma meta: "treinos por ficha" (ex.: 15 = o aluno faz
  a ficha A 15 vezes, a B 15 vezes, a C 15 vezes). Quando TODAS as fichas chegam à meta, ou quando
  passa a data de fim, o app só AVISA que está na hora de trocar o treino (não conclui sozinho).
- Quem registra que o aluno treinou é o próprio aluno, no celular. Esse app ainda não existe: por isso
  `registrar_sessao` só é usada pelos testes por enquanto, e a contagem fica em zero.
"""

import sqlite3
from datetime import datetime

from app.datas import agora_utc, formatar_dia, momento_para_texto


class TreinoNaoEncontrado(Exception):
    pass


class CicloInvalido(Exception):
    """A ação não vale para o estado atual do treino (ex.: concluir um treino que já está inativo)."""

    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem


def _treino(conn: sqlite3.Connection, treino_id: int) -> sqlite3.Row:
    treino = conn.execute("SELECT id, aluno_id, nome, ativo FROM treino WHERE id = ?", (treino_id,)).fetchone()
    if treino is None:
        raise TreinoNaoEncontrado(treino_id)
    return treino


def treino_ativo(conn: sqlite3.Connection, aluno_id: int) -> dict | None:
    """O treino ativo do aluno (id e nome), ou None se ele não tem nenhum."""
    linha = conn.execute("SELECT id, nome FROM treino WHERE aluno_id = ? AND ativo = 1", (aluno_id,)).fetchone()
    return dict(linha) if linha else None


# ------------------------------------------------------------------ concluir e reativar


def concluir_treino(conn: sqlite3.Connection, treino_id: int, agora: datetime | None = None) -> None:
    """Botão "Concluído": o treino vira inativo e entra no histórico. Guarda o momento."""
    with conn:
        _treino(conn, treino_id)  # 404 se não existe
        # "AND ativo = 1": dois cliques ao mesmo tempo não concluem duas vezes (o segundo não muda nada).
        alterados = conn.execute(
            "UPDATE treino SET ativo = 0, concluido_em = ? WHERE id = ? AND ativo = 1",
            (momento_para_texto(agora or agora_utc()), treino_id),
        ).rowcount
        if alterados == 0:
            raise CicloInvalido("Este treino já está concluído (inativo).")


def reativar_treino(conn: sqlite3.Connection, treino_id: int) -> None:
    """Desfaz um "Concluído" (clique errado, ou o aluno voltou a usar o treino).

    Só vale se o aluno não tem outro treino ativo: o app nunca troca um treino por outro sem avisar.
    """
    try:
        with conn:
            treino = _treino(conn, treino_id)
            if treino["ativo"]:
                raise CicloInvalido("Este treino já está ativo.")
            outro = treino_ativo(conn, treino["aluno_id"])
            if outro is not None:
                raise CicloInvalido(
                    f'Este aluno já tem um treino ativo ("{outro["nome"]}"). Conclua esse antes de reativar outro.'
                )
            conn.execute("UPDATE treino SET ativo = 1, concluido_em = NULL WHERE id = ?", (treino_id,))
    except sqlite3.IntegrityError as erro:
        # Dois cliques ao mesmo tempo (ou dois computadores): o índice do banco barra o segundo.
        if erro.sqlite_errorcode != sqlite3.SQLITE_CONSTRAINT_UNIQUE:
            raise
        raise CicloInvalido("Este aluno já tem um treino ativo. Atualize a página.") from None


# ------------------------------------------------------------------ sessões


def registrar_sessao(
    conn: sqlite3.Connection, treino_id: int, ficha_ordem: int, agora: datetime | None = None
) -> int:
    """Anota que o aluno treinou uma ficha (1 = A, 2 = B...). Só em treino ativo e em ficha que existe.

    Hoje nada chama isto fora dos testes: quem vai chamar é o app do aluno (ainda não existe).
    """
    with conn:
        treino = _treino(conn, treino_id)
        if not treino["ativo"]:
            raise CicloInvalido("Este treino está concluído: não dá para registrar treino nele.")
        existe = conn.execute(
            "SELECT 1 FROM ficha WHERE treino_id = ? AND ordem = ?", (treino_id, ficha_ordem)
        ).fetchone()
        if existe is None:
            raise CicloInvalido("Este treino não tem essa ficha.")
        return conn.execute(
            "INSERT INTO sessao (treino_id, ficha_ordem, feita_em) VALUES (?, ?, ?)",
            (treino_id, ficha_ordem, momento_para_texto(agora or agora_utc())),
        ).lastrowid


def sessoes_feitas_do_aluno(conn: sqlite3.Connection, aluno_id: int) -> dict[int, dict[int, int]]:
    """{id do treino: {ordem da ficha: quantas vezes foi feita}} para todos os treinos do aluno."""
    resultado: dict[int, dict[int, int]] = {}
    for treino_id, ordem, quantas in conn.execute(
        """
        SELECT s.treino_id, s.ficha_ordem, COUNT(*)
        FROM sessao s JOIN treino t ON t.id = s.treino_id
        WHERE t.aluno_id = ? GROUP BY s.treino_id, s.ficha_ordem
        """,
        (aluno_id,),
    ):
        resultado.setdefault(treino_id, {})[ordem] = quantas
    return resultado


# ------------------------------------------------------------------ avaliação do ciclo


def avaliar_ciclo(
    *,
    ativo: bool,
    quantidade_de_fichas: int,
    sessoes_por_ficha: int | None,
    fim: str | None,
    feitas_por_ficha: dict[int, int],
    hoje_texto: str,
) -> dict:
    """Quanto do ciclo já foi feito e se está na hora de trocar o treino.

    Devolve: `por_ficha` (lista de {ordem, feitas}), `feitas` (soma), `meta_total` (meta x fichas, ou None),
    `meta_cumprida` (TODAS as fichas chegaram à meta), `vencido` (hoje é depois do fim; no dia do fim o
    treino ainda vale), `trocar` (treino ativo e meta cumprida ou vencido) e `motivos` (lista com "meta"/"prazo").
    """
    por_ficha = [
        {"ordem": ordem, "feitas": feitas_por_ficha.get(ordem, 0)} for ordem in range(1, quantidade_de_fichas + 1)
    ]
    meta_cumprida = bool(
        sessoes_por_ficha and por_ficha and all(ficha["feitas"] >= sessoes_por_ficha for ficha in por_ficha)
    )
    vencido = bool(fim and hoje_texto > fim)  # 'AAAA-MM-DD' compara como texto
    motivos = [nome for nome, vale in (("meta", meta_cumprida), ("prazo", vencido)) if vale]
    return {
        "por_ficha": por_ficha,
        "feitas": sum(ficha["feitas"] for ficha in por_ficha),
        "meta_total": sessoes_por_ficha * quantidade_de_fichas if sessoes_por_ficha else None,
        "meta_cumprida": meta_cumprida,
        "vencido": vencido,
        "trocar": bool(ativo and motivos),
        "motivos": motivos,
    }


def texto_do_aviso_de_troca(nome_do_treino: str, avaliacao: dict, sessoes_por_ficha: int | None, fim: str | None) -> str:
    """A frase do aviso "hora de trocar o treino" (vazia se não for hora)."""
    if not avaliacao["trocar"]:
        return ""
    partes = []
    if avaliacao["meta_cumprida"]:
        partes.append(f"o aluno fez as {sessoes_por_ficha} sessões de cada ficha")
    if avaliacao["vencido"]:
        partes.append(f"a data de fim ({formatar_dia(fim)}) já passou")
    return f'Hora de trocar o treino "{nome_do_treino}": ' + " e ".join(partes) + "."
