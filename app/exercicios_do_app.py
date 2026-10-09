"""Exercícios que existem só no app (origem 'app'), fora do quadro do Data4U.

Hoje: "ELÍPTICO", o cardio genérico. A academia usa CARDIO, ESTEIRA, BIKE e ESCADA (já estão no quadro) e
ELÍPTICO, sem tempo no nome: o professor escreve o tempo ao lado, ou deixa em branco (pedido do Thiago,
08/10/2026; séries e repetições podem ficar em branco).

Uso (uma vez, no terminal do contêiner; pode repetir sem problema):
    python -m app.exercicios_do_app /dados/app.db

Atenção: este exercício NÃO existe no Data4U. Antes de mandar treinos de volta ao Data4U, ele precisa ser
criado lá (ou ligado a um exercício de lá) em `exercicio_data4u`.
"""

import sqlite3
import sys

from app.db import conectar, criar_tabelas

# (nome, grupo muscular). O grupo precisa existir (vem da importação do quadro).
EXERCICIOS_DO_APP = [
    ("ELÍPTICO", "Cardio"),
]


def garantir_exercicios_do_app(conn: sqlite3.Connection) -> dict:
    """Cria o que falta e deixa ativo e no grupo certo. Devolve {"criados": [...], "ativados": [...], "sem_grupo": [...]}.

    - Já existe ativo: só confere o grupo.
    - Já existe mas inativo (o histórico do Data4U cria exercícios inativos): ativa, para aparecer na lista.
    - O que já tem prescrições antigas continua ligado a elas (o id não muda).
    """
    resumo: dict[str, list[str]] = {"criados": [], "ativados": [], "sem_grupo": []}
    with conn:
        for nome, grupo in EXERCICIOS_DO_APP:
            linha = conn.execute("SELECT id, ativo FROM exercicio WHERE nome = ?", (nome,)).fetchone()
            if linha is None:
                exercicio_id = conn.execute(
                    "INSERT INTO exercicio (nome, ativo, combinado, origem) VALUES (?, 1, 0, 'app')", (nome,)
                ).lastrowid
                resumo["criados"].append(nome)
            else:
                exercicio_id = linha["id"]
                if not linha["ativo"]:
                    conn.execute("UPDATE exercicio SET ativo = 1 WHERE id = ?", (exercicio_id,))
                    resumo["ativados"].append(nome)
            grupo_id = conn.execute("SELECT id FROM grupo_muscular WHERE nome = ?", (grupo,)).fetchone()
            if grupo_id is None:
                resumo["sem_grupo"].append(nome)  # o grupo ainda não foi importado: o exercício fica sem grupo
                continue
            conn.execute(
                "INSERT OR IGNORE INTO exercicio_grupo (exercicio_id, grupo_id) VALUES (?, ?)",
                (exercicio_id, grupo_id["id"]),
            )
    return resumo


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Uso: python -m app.exercicios_do_app <banco.db>")
        return 2
    conn = conectar(argv[1])
    criar_tabelas(conn)
    print("Exercícios do app:", garantir_exercicios_do_app(conn))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
