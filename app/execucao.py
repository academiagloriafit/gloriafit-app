"""O que o aluno faz DURANTE o treino na tela /aluno: marcar cada exercício como feito e anotar a carga que usou.

Pedido do Thiago (22/10/2026):
- "Feito": o aluno marca cada exercício; assim, se parar no meio, ele volta mais tarde e vê onde parou. A marcação vale pelo DIA
  (calendário de Brasília): amanhã o treino volta limpo.
- Carga: o aluno anota quanto usou em cada exercício e, na próxima vez, vê "Última vez: 30 kg". Anotar é opcional ("o treino que ele
  não anotar, ele não anotou"). Um campo por exercício (não por série), só o número, em kg.

Aqui ficam só as contas e a gravação. Quem confere que o exercício é mesmo do treino ativo do aluno é `app.aluno_treino`
(`marcar_exercicio`), porque é lá que se sabe o que o aluno está vendo.

Ligação com o treino: pelo NÚMERO da ficha, o NÚMERO do exercício e o NOME do exercício, nunca por id (editar um treino apaga e
recria fichas e itens). O nome também é a chave da "última vez": a carga que o aluno anotou no mesmo exercício em outro dia vale
mesmo que o treino tenha mudado.
"""

import re
import sqlite3
from datetime import datetime
from decimal import Decimal

from app.datas import agora_utc, hoje, momento_para_texto

MAIOR_CARGA = Decimal("999.99")
_NUMERO_DA_CARGA = re.compile(r"[0-9]{1,3}(?:[.,][0-9]{1,2})?")

NADA = object()  # "o pedido não falou deste campo": não mexe nele (diferente de None, que apaga)


class CargaInvalida(ValueError):
    """A carga digitada não serve. A mensagem já está pronta para mostrar ao aluno."""


def carga_limpa(valor: object) -> str | None:
    """A carga como o app guarda: '12,5' (vírgula, sem zeros sobrando); None = o aluno apagou (campo vazio).

    Aceita ponto ou vírgula, até 2 casas, de 0,01 a 999,99 (kg). Qualquer outra coisa levanta CargaInvalida: o campo existe para
    comparar uma vez com a outra, e texto solto ("20 kg cada", "leve") não compara.
    """
    if valor is None:
        return None
    if not isinstance(valor, str):
        raise CargaInvalida("Digite só o número, em kg. Exemplo: 12,5")
    texto = valor.strip()
    if not texto:
        return None
    if not _NUMERO_DA_CARGA.fullmatch(texto):
        raise CargaInvalida("Digite só o número, em kg. Exemplo: 12,5")
    numero = Decimal(texto.replace(",", "."))
    if numero <= 0:
        raise CargaInvalida("A carga precisa ser maior que zero. Se não usou peso, deixe em branco.")
    if numero > MAIOR_CARGA:
        raise CargaInvalida("A carga pode ter até 999,99 kg.")
    return format(numero.normalize(), "f").replace(".", ",")


# ------------------------------------------------------------------ ler


def marcas_do_dia(conn: sqlite3.Connection, aluno_id: int, dia: str) -> dict[tuple[int, int], sqlite3.Row]:
    """{(número da ficha, número do exercício): linha} do que o aluno marcou ou anotou NESTE dia."""
    return {
        (linha["ficha_ordem"], linha["exercicio_ordem"]): linha
        for linha in conn.execute(
            "SELECT ficha_ordem, exercicio_ordem, exercicio_nome, feito, carga FROM execucao WHERE aluno_id = ? AND dia = ?",
            (aluno_id, dia),
        )
    }


def ultimas_cargas(conn: sqlite3.Connection, aluno_id: int, nomes: set[str], antes_de: str) -> dict[str, tuple[str, str]]:
    """{nome do exercício: (carga, dia)} da carga mais recente anotada em um dia ANTES de `antes_de` ('AAAA-MM-DD').

    Só dos exercícios em `nomes`. Quem não anotou nada ainda não aparece no resultado.
    """
    if not nomes:
        return {}
    ordenados = sorted(nomes)
    resultado: dict[str, tuple[str, str]] = {}
    # Em lotes: o SQLite aceita poucas "?" por consulta em versões antigas, e uma ficha grande tem dezenas de exercícios.
    for comeco in range(0, len(ordenados), 200):
        lote = ordenados[comeco : comeco + 200]
        marcadores = ", ".join("?" * len(lote))
        # No SQLite, a coluna "solta" ao lado de MAX() vem da mesma linha do máximo: aqui, a carga do dia mais recente.
        for nome, carga, dia in conn.execute(
            f"""
            SELECT exercicio_nome, carga, MAX(dia) FROM execucao
            WHERE aluno_id = ? AND carga IS NOT NULL AND dia < ? AND exercicio_nome IN ({marcadores})
            GROUP BY exercicio_nome
            """,
            (aluno_id, antes_de, *lote),
        ):
            resultado[nome] = (carga, dia)
    return resultado


# ------------------------------------------------------------------ gravar


def gravar(
    conn: sqlite3.Connection,
    aluno_id: int,
    ficha: int,
    item: int,
    nome: str,
    *,
    feito: object = NADA,
    carga: object = NADA,
    agora: datetime | None = None,
) -> dict:
    """Grava o que o aluno marcou/anotou hoje neste exercício e devolve {"feito": bool, "carga_hoje": str} (carga "" = nenhuma).

    `feito` (bool) e `carga` (já limpa por `carga_limpa`; None apaga) só mexem se vierem; o que não veio fica como estava.
    Se não sobrar nada (não está feito e sem carga), a linha é apagada. A transação é de quem chama.
    Uma linha antiga do mesmo lugar com OUTRO nome de exercício (o professor trocou o treino no meio do dia) não vale: é refeita.
    """
    dia = hoje(agora)
    atual = conn.execute(
        "SELECT exercicio_nome, feito, carga FROM execucao WHERE aluno_id = ? AND dia = ? AND ficha_ordem = ? AND exercicio_ordem = ?",
        (aluno_id, dia, ficha, item),
    ).fetchone()
    if atual is not None and atual["exercicio_nome"] != nome:
        atual = None
    novo_feito = (feito if feito is not NADA else bool(atual["feito"]) if atual else False)
    nova_carga = (carga if carga is not NADA else atual["carga"] if atual else None)

    if not novo_feito and nova_carga is None:
        conn.execute(
            "DELETE FROM execucao WHERE aluno_id = ? AND dia = ? AND ficha_ordem = ? AND exercicio_ordem = ?",
            (aluno_id, dia, ficha, item),
        )
    else:
        conn.execute(
            """
            INSERT INTO execucao (aluno_id, dia, ficha_ordem, exercicio_ordem, exercicio_nome, feito, carga, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (aluno_id, dia, ficha_ordem, exercicio_ordem) DO UPDATE SET
                exercicio_nome = excluded.exercicio_nome, feito = excluded.feito, carga = excluded.carga,
                atualizado_em = excluded.atualizado_em
            """,
            (aluno_id, dia, ficha, item, nome, 1 if novo_feito else 0, nova_carga, momento_para_texto(agora or agora_utc())),
        )
    return {"feito": bool(novo_feito), "carga_hoje": nova_carga or ""}
