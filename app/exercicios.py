"""Consultas da biblioteca de exercícios (a lista da tela do professor)."""

import sqlite3

from app.texto import nome_para_exibir, normalizar

LIMITE_PADRAO = 50
LIMITE_MAXIMO = 200
TAMANHO_MAXIMO_BUSCA = 100


def contar_exercicios(conn: sqlite3.Connection) -> int:
    """Quantos exercícios ativos existem (o "1.161" da tela)."""
    return conn.execute("SELECT COUNT(*) FROM exercicio WHERE ativo = 1").fetchone()[0]


def listar_grupos(conn: sqlite3.Connection) -> list[dict]:
    """Os grupos musculares na ordem do quadro, cada um com quantos exercícios ativos tem.

    Um exercício combinado (ex.: Peito + Tríceps) conta em cada um dos seus grupos.
    """
    linhas = conn.execute(
        """
        SELECT g.id, g.nome, COUNT(e.id) AS quantidade
        FROM grupo_muscular g
        LEFT JOIN exercicio_grupo eg ON eg.grupo_id = g.id
        LEFT JOIN exercicio e ON e.id = eg.exercicio_id AND e.ativo = 1
        GROUP BY g.id
        ORDER BY g.ordem
        """
    ).fetchall()
    return [dict(linha) for linha in linhas]


def _escapar_like(termo: str) -> str:
    # No LIKE, % e _ são curingas. Se o aluno ou professor digitar "%", não
    # pode significar "qualquer coisa": escapamos para valer como o caractere.
    return termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def buscar_exercicios(
    conn: sqlite3.Connection,
    grupo_id: int | None = None,
    texto: str = "",
    limite: int = LIMITE_PADRAO,
) -> dict:
    """Busca exercícios ativos por grupo muscular e/ou por pedaço do nome.

    - `texto` não diferencia maiúscula nem acento, e cada palavra digitada precisa
      aparecer no nome, em qualquer ordem: "supino reto" acha "Supino reto com barra".
    - `grupo_id`: só exercícios desse grupo. Exercícios sem grupo (ainda sem
      classificação) só aparecem quando NÃO se filtra por grupo.
    - Ordem: os mais usados no último ano primeiro, depois alfabética.

    Devolve {"total": quantos existem com esse filtro, "exercicios": até `limite` deles}.
    """
    limite = max(1, min(int(limite), LIMITE_MAXIMO))

    # SEGURANÇA: o que o usuário digitou NUNCA entra no texto do SQL (isso abriria
    # a porta para "SQL injection"). Só entram os trechos fixos abaixo; os valores
    # vão separados, nos "?", e o SQLite os trata sempre como dado.
    condicoes = ["e.ativo = 1"]
    parametros: list = []
    if grupo_id is not None:
        condicoes.append(
            "EXISTS (SELECT 1 FROM exercicio_grupo eg"
            " WHERE eg.exercicio_id = e.id AND eg.grupo_id = ?)"
        )
        parametros.append(grupo_id)
    for termo in normalizar(texto[:TAMANHO_MAXIMO_BUSCA]).split():
        condicoes.append("sem_acento(e.nome) LIKE ? ESCAPE '\\'")
        parametros.append(f"%{_escapar_like(termo)}%")
    onde = " AND ".join(condicoes)

    total = conn.execute(
        f"SELECT COUNT(*) FROM exercicio e WHERE {onde}", parametros
    ).fetchone()[0]
    linhas = conn.execute(
        f"""
        SELECT e.id, e.nome, e.combinado
        FROM exercicio e
        WHERE {onde}
        ORDER BY e.usos_ultimo_ano DESC, sem_acento(e.nome), e.id
        LIMIT ?
        """,
        [*parametros, limite],
    ).fetchall()

    grupos_por_exercicio = _grupos_dos_exercicios(conn, [linha["id"] for linha in linhas])
    exercicios = [
        {
            "id": linha["id"],
            "nome": nome_para_exibir(linha["nome"]),
            "combinado": bool(linha["combinado"]),
            "grupos": grupos_por_exercicio.get(linha["id"], []),
        }
        for linha in linhas
    ]
    return {"total": total, "exercicios": exercicios}


def _grupos_dos_exercicios(conn: sqlite3.Connection, ids: list[int]) -> dict[int, list[str]]:
    """Nomes dos grupos de cada exercício, na ordem do quadro."""
    if not ids:
        return {}
    marcas = ",".join("?" * len(ids))  # "?,?,?": só marcadores, nunca valores
    linhas = conn.execute(
        f"""
        SELECT eg.exercicio_id, g.nome
        FROM exercicio_grupo eg
        JOIN grupo_muscular g ON g.id = eg.grupo_id
        WHERE eg.exercicio_id IN ({marcas})
        ORDER BY g.ordem
        """,
        ids,
    ).fetchall()
    resultado: dict[int, list[str]] = {}
    for linha in linhas:
        resultado.setdefault(linha["exercicio_id"], []).append(linha["nome"])
    return resultado
