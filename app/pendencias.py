"""Tela "Pendências" (pedido do Thiago, 26/10/2026): o que o professor precisa resolver, num lugar só. Só leitura.

Três listas:
1. HORA DE TROCAR O TREINO: treino ativo que cumpriu a meta de sessões de todas as fichas ou passou da data de fim. É a mesma
   conta do aviso da ficha do aluno (`ciclo.avaliar_ciclo`), feita para todos de uma vez.
2. COMENTÁRIOS SEM LER: os mesmos do número do menu "Comentários" (os mais novos primeiro).
3. ATIVOS SEM TREINO: aluno ativo no Data4U (ou provisório) sem nenhum treino ativo (nem do app, nem copiado do Data4U).

Como em "Quem sumiu", só entram alunos ativos no Data4U (situação 'A') ou provisórios: quem trancou ou saiu não é pendência.
"""

import sqlite3
from datetime import datetime

from app import ciclo, comentarios
from app.datas import formatar_dia, hoje

LIMITE_DA_LISTA = 200  # alunos mostrados em cada lista (os totais são os reais)
COMENTARIOS_NA_TELA = 10

_ALUNO_QUE_CONTA = "(a.provisorio = 1 OR a.situacao = 'A')"


def _hora_de_trocar(conn: sqlite3.Connection, hoje_texto: str) -> list[dict]:
    sessoes: dict[int, dict[int, int]] = {}
    for treino_id, ordem, quantas in conn.execute(
        """
        SELECT s.treino_id, s.ficha_ordem, COUNT(*) FROM sessao s JOIN treino t ON t.id = s.treino_id
        WHERE t.ativo = 1 GROUP BY s.treino_id, s.ficha_ordem
        """
    ):
        sessoes.setdefault(treino_id, {})[ordem] = quantas
    lista = []
    for linha in conn.execute(
        f"""
        SELECT a.id, a.nome, t.id AS treino_id, t.nome AS treino, t.fim, t.sessoes_por_ficha,
               (SELECT COUNT(*) FROM ficha f WHERE f.treino_id = t.id) AS fichas
        FROM treino t JOIN aluno a ON a.id = t.aluno_id
        WHERE t.ativo = 1 AND {_ALUNO_QUE_CONTA} AND (t.fim IS NOT NULL OR t.sessoes_por_ficha IS NOT NULL)
        """
    ):
        avaliacao = ciclo.avaliar_ciclo(
            ativo=True,
            quantidade_de_fichas=linha["fichas"],
            sessoes_por_ficha=linha["sessoes_por_ficha"],
            fim=linha["fim"],
            feitas_por_ficha=sessoes.get(linha["treino_id"], {}),
            hoje_texto=hoje_texto,
        )
        if not avaliacao["trocar"]:
            continue
        motivos = []
        if avaliacao["meta_cumprida"]:
            motivos.append(f"fez as {linha['sessoes_por_ficha']} sessões de cada ficha")
        if avaliacao["vencido"]:
            motivos.append(f"o treino venceu em {formatar_dia(linha['fim'])}")
        lista.append(
            {
                "id": linha["id"],
                "nome": linha["nome"],
                "treino": linha["treino"],
                "motivo": " e ".join(motivos).capitalize(),
                "fim": linha["fim"] or "",  # para ordenar: os vencidos há mais tempo primeiro
            }
        )
    lista.sort(key=lambda a: (a["fim"] == "", a["fim"], a["nome"], a["id"]))
    return lista


def _sem_treino(conn: sqlite3.Connection) -> list[dict]:
    return [
        {"id": linha["id"], "nome": linha["nome"], "provisorio": bool(linha["provisorio"])}
        for linha in conn.execute(
            f"""
            SELECT a.id, a.nome, a.provisorio FROM aluno a
            WHERE {_ALUNO_QUE_CONTA} AND NOT EXISTS (SELECT 1 FROM treino t WHERE t.aluno_id = a.id AND t.ativo = 1)
            ORDER BY a.provisorio DESC, a.nome, a.id
            """
        )
    ]


def listar(conn: sqlite3.Connection, agora: datetime | None = None) -> dict:
    """{"trocar": {"total", "alunos"}, "sem_treino": {"total", "alunos"}, "comentarios": {"total", "comentarios"}, "total"}."""
    trocar = _hora_de_trocar(conn, hoje(agora))
    sem_treino = _sem_treino(conn)
    novos = comentarios.listar(conn, so_nao_lidos=True, limite=COMENTARIOS_NA_TELA)
    return {
        "trocar": {"total": len(trocar), "alunos": trocar[:LIMITE_DA_LISTA]},
        "sem_treino": {"total": len(sem_treino), "alunos": sem_treino[:LIMITE_DA_LISTA]},
        "comentarios": {"total": novos["total"], "comentarios": novos["comentarios"]},
        "total": len(trocar) + len(sem_treino) + novos["total"],
        "limite": LIMITE_DA_LISTA,
    }
