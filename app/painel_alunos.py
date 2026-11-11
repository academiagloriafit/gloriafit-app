"""Tela "Alunos" do professor, visual novo (mescla das opções C e E do Canva, escolhida pelo Thiago em 11/11/2026).

Dá à tela:
- os NÚMEROS do alto (alunos ativos, treinaram hoje, hora de trocar o treino, comentários novos, quem sumiu e sem treino);
- os FILTROS (cada número é um botão que deixa na lista só aqueles alunos): `ids_do_filtro` devolve quem entra;
- o ANDAMENTO de cada aluno da lista (sessões feitas / meta do treino ativo e o dia do último treino feito).

Tudo sai das mesmas contas das telas que já existem (Pendências, Quem sumiu, Comentários), para os números baterem entre elas.
Nada aqui grava no banco.
"""

import sqlite3
from datetime import datetime

from app import ausentes, comentarios, pendencias
from app.datas import dia_local, hoje, ler_dia, limites_do_dia

# Os filtros que a tela conhece. Qualquer outro texto vindo do navegador é ignorado (vira "todos").
FILTROS = ("ativos", "hoje", "trocar", "comentarios", "sumiram", "sem_treino")


def _ids_que_treinaram_hoje(conn: sqlite3.Connection, agora: datetime | None) -> set[int]:
    comeco, fim = limites_do_dia(agora)
    return {
        linha[0]
        for linha in conn.execute(
            "SELECT DISTINCT t.aluno_id FROM sessao s JOIN treino t ON t.id = s.treino_id WHERE s.feita_em >= ? AND s.feita_em < ?",
            (comeco, fim),
        )
    }


def _ids_com_comentario_novo(conn: sqlite3.Connection) -> set[int]:
    return {linha[0] for linha in conn.execute("SELECT DISTINCT aluno_id FROM comentario WHERE lido_em IS NULL")}


def ids_do_filtro(conn: sqlite3.Connection, filtro: str, agora: datetime | None = None) -> set[int] | None:
    """Os ids dos alunos que o filtro deixa na lista; None = sem filtro (todos). "ativos" é tratado na própria busca."""
    if filtro == "hoje":
        return _ids_que_treinaram_hoje(conn, agora)
    if filtro == "trocar":
        return {aluno["id"] for aluno in pendencias._hora_de_trocar(conn, hoje(agora))}
    if filtro == "sem_treino":
        return {aluno["id"] for aluno in pendencias._sem_treino(conn)}
    if filtro == "comentarios":
        return _ids_com_comentario_novo(conn)
    if filtro == "sumiram":
        # os mesmos alunos da tela "Quem sumiu" (as duas listas juntas), sem o corte de tamanho daquela tela
        lista = ausentes.listar(conn, agora=agora, limite=10**9)
        return {aluno["id"] for aluno in lista["alunos"] + lista["sem_registro"]}
    return None


def numeros(conn: sqlite3.Connection, agora: datetime | None = None) -> dict:
    """Os números do alto da tela. Os mesmos totais de Pendências, Quem sumiu e Comentários."""
    pend = pendencias.listar(conn, agora)
    sumidos = ausentes.listar(conn, agora=agora)
    return {
        "ativos": conn.execute("SELECT COUNT(*) FROM aluno WHERE situacao = 'A'").fetchone()[0],
        "hoje": len(_ids_que_treinaram_hoje(conn, agora)),
        "trocar": pend["trocar"]["total"],
        "comentarios": comentarios.listar(conn, so_nao_lidos=True, limite=1)["total"],
        "sumiram": sumidos["total"] + sumidos["total_sem_registro"],
        "dias_sumido": sumidos["dias"],
        "sem_treino": pend["sem_treino"]["total"],
    }


def andamento(conn: sqlite3.Connection, aluno_ids: list[int], agora: datetime | None = None) -> dict[int, dict]:
    """{id do aluno: {"treino_atual", "feitas", "meta_total", "progresso" (0-100 ou None), "ultimo_feito" ('AAAA-MM-DD' ou None),
    "dias_sem_treinar" (inteiro ou None)}} para os alunos pedidos (a lista da tela tem no máximo 50)."""
    if not aluno_ids:
        return {}
    marcas = ",".join("?" * len(aluno_ids))
    resultado: dict[int, dict] = {
        aluno_id: {"treino_atual": None, "feitas": 0, "meta_total": None, "progresso": None, "ultimo_feito": None, "dias_sem_treinar": None}
        for aluno_id in aluno_ids
    }
    for linha in conn.execute(
        f"""
        SELECT t.aluno_id, t.nome, t.sessoes_por_ficha,
               (SELECT COUNT(*) FROM ficha f WHERE f.treino_id = t.id) AS fichas,
               (SELECT COUNT(*) FROM sessao s WHERE s.treino_id = t.id) AS feitas
        FROM treino t WHERE t.ativo = 1 AND t.aluno_id IN ({marcas})
        """,
        aluno_ids,
    ):
        meta = linha["sessoes_por_ficha"] * linha["fichas"] if linha["sessoes_por_ficha"] and linha["fichas"] else None
        feitas = linha["feitas"]
        resultado[linha["aluno_id"]].update(
            treino_atual=linha["nome"],
            feitas=feitas,
            meta_total=meta,
            progresso=max(0, min(100, round(feitas * 100 / meta))) if meta else None,
        )
    dia_de_hoje = ler_dia(hoje(agora))
    for aluno_id, ultima in conn.execute(
        f"SELECT t.aluno_id, MAX(s.feita_em) FROM sessao s JOIN treino t ON t.id = s.treino_id WHERE t.aluno_id IN ({marcas}) GROUP BY t.aluno_id",
        aluno_ids,
    ):
        dia = dia_local(ultima)
        if dia:
            resultado[aluno_id]["ultimo_feito"] = dia
            resultado[aluno_id]["dias_sem_treinar"] = (dia_de_hoje - ler_dia(dia)).days
    return resultado
