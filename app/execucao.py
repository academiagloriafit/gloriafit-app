"""O que o aluno faz DURANTE o treino na tela /aluno: marcar cada exercício como feito e anotar a carga que usou.

Pedido do Thiago (22/10/2026):
- "Feito": o aluno marca cada exercício; assim, se parar no meio, ele volta mais tarde e vê onde parou. A marcação vale pelo DIA
  (calendário de Brasília): amanhã o treino volta limpo.
- Carga: o aluno anota quanto usou em cada exercício e, na próxima vez, vê "Última vez: 30 kg". Anotar é opcional ("o treino que ele
  não anotar, ele não anotou"). Um campo por exercício (não por série), só o número, em kg.

Aqui ficam só as contas e a gravação. Quem confere que o exercício é mesmo do treino ativo do aluno é `app.aluno_treino`
(`marcar_exercicio`), porque é lá que se sabe o que o aluno está vendo.

Ligação com o treino: pelo NÚMERO da ficha, o NOME do exercício e a OCORRÊNCIA do nome na ficha (1 = a primeira vez que o nome
aparece nela, 2 = a segunda...), nunca por id (editar um treino apaga e recria fichas e itens) e nunca só pela posição: se o professor
incluir, tirar ou trocar um exercício no meio do dia as posições andam, e o que o aluno já anotou não pode ir parar no exercício
vizinho nem ser apagado. O nome também é a chave da "última vez": a carga que o aluno anotou no mesmo exercício em outro dia vale
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


def marcas_do_dia(conn: sqlite3.Connection, aluno_id: int, dia: str) -> dict[tuple[int, str, int], sqlite3.Row]:
    """{(número da ficha, nome do exercício, ocorrência do nome na ficha): linha} do que o aluno marcou ou anotou NESTE dia."""
    return {
        (linha["ficha_ordem"], linha["exercicio_nome"], linha["ocorrencia"]): linha
        for linha in conn.execute(
            "SELECT ficha_ordem, exercicio_nome, ocorrencia, feito, carga FROM execucao WHERE aluno_id = ? AND dia = ?",
            (aluno_id, dia),
        )
    }


def ultimas_cargas(conn: sqlite3.Connection, aluno_id: int, nomes: set[str], antes_de: str) -> dict[str, tuple[str, str]]:
    """{nome do exercício: (carga, dia)} da carga mais recente anotada em um dia ANTES de `antes_de` ('AAAA-MM-DD').

    Só dos exercícios em `nomes`. Quem não anotou nada ainda não aparece no resultado. Se no mesmo dia o aluno anotou duas cargas
    para o mesmo nome (o exercício aparece em duas fichas, ou duas vezes na mesma), vale a última que ele anotou naquele dia.
    """
    resultado: dict[str, tuple[str, str]] = {}
    # Uma consulta por nome, todas pelo índice (aluno, nome, dia): uma ficha tem dezenas de exercícios, não milhares.
    for nome in sorted(nomes):
        linha = conn.execute(
            """
            SELECT carga, dia FROM execucao
            WHERE aluno_id = ? AND exercicio_nome = ? AND carga IS NOT NULL AND dia < ?
            ORDER BY dia DESC, atualizado_em DESC, id DESC
            LIMIT 1
            """,
            (aluno_id, nome, antes_de),
        ).fetchone()
        if linha is not None:
            resultado[nome] = (linha["carga"], linha["dia"])
    return resultado



def cargas_por_exercicio(conn: sqlite3.Connection, aluno_id: int) -> dict[int, tuple[str, str]]:
    """{id do exercício: (carga, dia 'AAAA-MM-DD')} da carga MAIS RECENTE que o aluno anotou em cada exercício, contando hoje.

    É o que o PROFESSOR vê (ficha do aluno e tela de montar) e o que o robô recebe no treino anterior. A carga é guardada pelo nome do
    exercício (ver o começo deste arquivo); aqui o nome vira o id da lista atual. Exercício renomeado depois perde a ligação (a carga
    antiga continua no banco, só não aparece). Uma consulta só, pelo índice (aluno, nome, dia).
    """
    resultado: dict[int, tuple[str, str]] = {}
    for linha in conn.execute(
        """
        SELECT e.id, x.carga, x.dia FROM execucao x JOIN exercicio e ON e.nome = x.exercicio_nome
        WHERE x.aluno_id = ? AND x.carga IS NOT NULL
        ORDER BY x.dia, x.atualizado_em, x.id
        """,
        (aluno_id,),
    ):
        resultado[linha["id"]] = (linha["carga"], linha["dia"])  # a ordem crescente deixa a mais recente por último
    return resultado


def texto_da_carga(carga: tuple[str, str] | None) -> str:
    """("20", "2026-10-12") -> "20 kg em 12/10"; None -> ""."""
    if not carga:
        return ""
    ano, mes, dia = carga[1].split("-")
    return f"{carga[0]} kg em {dia}/{mes}"

# ------------------------------------------------------------------ gravar


def gravar(
    conn: sqlite3.Connection,
    aluno_id: int,
    ficha: int,
    item: int,
    nome: str,
    *,
    ocorrencia: int = 1,
    feito: object = NADA,
    carga: object = NADA,
    agora: datetime | None = None,
) -> dict:
    """Grava o que o aluno marcou/anotou hoje neste exercício e devolve {"feito": bool, "carga_hoje": str} (carga "" = nenhuma).

    O exercício é achado por ficha + `nome` + `ocorrencia` (a n-ésima vez que o nome aparece na ficha); `item` (a posição dele na
    ficha agora) só fica anotado. `feito` (bool) e `carga` (já limpa por `carga_limpa`; None apaga) só mexem se vierem; o que não veio
    fica como estava. Se não sobrar nada (não está feito e sem carga), a linha é apagada. A transação é de quem chama.
    """
    dia = hoje(agora)
    onde = (aluno_id, dia, ficha, nome, ocorrencia)
    atual = conn.execute(
        "SELECT feito, carga FROM execucao WHERE aluno_id = ? AND dia = ? AND ficha_ordem = ? AND exercicio_nome = ? AND ocorrencia = ?",
        onde,
    ).fetchone()
    novo_feito = (feito if feito is not NADA else bool(atual["feito"]) if atual else False)
    nova_carga = (carga if carga is not NADA else atual["carga"] if atual else None)

    if not novo_feito and nova_carga is None:
        conn.execute(
            "DELETE FROM execucao WHERE aluno_id = ? AND dia = ? AND ficha_ordem = ? AND exercicio_nome = ? AND ocorrencia = ?",
            onde,
        )
    else:
        conn.execute(
            """
            INSERT INTO execucao (aluno_id, dia, ficha_ordem, exercicio_ordem, exercicio_nome, ocorrencia, feito, carga, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (aluno_id, dia, ficha_ordem, exercicio_nome, ocorrencia) DO UPDATE SET
                exercicio_ordem = excluded.exercicio_ordem, feito = excluded.feito, carga = excluded.carga,
                atualizado_em = excluded.atualizado_em
            """,
            (aluno_id, dia, ficha, item, nome, ocorrencia, 1 if novo_feito else 0, nova_carga, momento_para_texto(agora or agora_utc())),
        )
    return {"feito": bool(novo_feito), "carga_hoje": nova_carga or ""}
