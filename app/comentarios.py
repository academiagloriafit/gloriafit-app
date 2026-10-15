"""Comentários do aluno sobre o treino (tela /aluno) e a leitura deles pelo professor.

O aluno comenta o treino INTEIRO ou UM exercício (pedido do Thiago, 09/10/2026; entrega 1 de 2: o aluno escreve, o
professor lê e marca como lido; a resposta do professor é a entrega 2). O aluno só comenta: não pede troca de treino por
botão, quem decide trocar é sempre o professor.

Regras de segurança, porque o texto é livre e vem de fora:
- O aluno vem do cookie (nunca do corpo do pedido) e só comenta o PRÓPRIO treino ativo.
- O texto é sempre TEXTO: o celular e a tela do professor desenham com `textContent`, nunca como HTML. Mesmo assim o
  servidor limita o tamanho e recusa caracteres de controle.
- Limite por dia (20 por aluno) e recusa de repetição seguida (o mesmo texto, no mesmo lugar, em 10 minutos): um toque
  duplo ou uma rede ruim que reenvia não enche a lista do professor.
- O comentário guarda uma CÓPIA dos nomes (treino, ficha, exercício): editar o treino apaga e recria as fichas, e o
  comentário precisa continuar legível. Nunca aponta para o id do item da ficha.
- Pode ter dado de saúde ("senti dor no ombro"): só os computadores autorizados da academia leem, e o texto não vai para log.
"""

import sqlite3
import unicodedata
from datetime import datetime, timedelta

from app import aluno_treino
from app.datas import agora_utc, limites_do_dia, momento_local, momento_para_texto

LIMITE_DO_TEXTO = 500
LIMITE_POR_DIA = 20
JANELA_DA_REPETICAO = timedelta(minutes=10)  # cobre o aluno que reenvia depois de a rede cair (o pedido pode ter chegado)
LIMITE_DA_LISTA = 200  # a tela do professor mostra os mais novos primeiro e nunca passa disto
_MAIOR_ID = 2**63 - 1  # o maior número que o SQLite guarda como id

_PERMITIDOS_DE_CONTROLE = ("\n", "\t")
# Controles de direção do texto: um deles faz o que vem depois aparecer invertido e disfarça o que o aluno escreveu.
_DIRECAO_DO_TEXTO = frozenset("\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")


class ComentarioInvalido(Exception):
    """O comentário não pode ser enviado. A mensagem já está pronta para mostrar; `status` é o código da resposta."""

    def __init__(self, mensagem: str, status: int):
        super().__init__(mensagem)
        self.status = status


# ------------------------------------------------------------------ o aluno comenta


def _texto_limpo(texto: object) -> str:
    """O texto sem as bordas em branco e com quebra de linha única, ou ComentarioInvalido."""
    if not isinstance(texto, str):
        raise ComentarioInvalido("Escreva o seu comentário.", 400)
    texto = texto.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not texto:
        raise ComentarioInvalido("Escreva o seu comentário.", 400)
    if len(texto) > LIMITE_DO_TEXTO:
        raise ComentarioInvalido(f"O comentário pode ter até {LIMITE_DO_TEXTO} letras.", 400)
    tem_algo_visivel = False
    for letra in texto:
        categoria = unicodedata.category(letra)
        # "Cs" = metade solta de um par de letras (o SQLite não consegue gravar); "Cc" = controles como o byte nulo.
        if categoria == "Cs" or letra in _DIRECAO_DO_TEXTO or (categoria == "Cc" and letra not in _PERMITIDOS_DE_CONTROLE):
            raise ComentarioInvalido("O comentário tem um caractere que não posso aceitar.", 400)
        # "Cf" (formato) fica permitido: o emoji composto (família, bandeira) usa um. Mas só ele não é um comentário.
        if categoria != "Cf" and not letra.isspace():
            tem_algo_visivel = True
    if not tem_algo_visivel:
        raise ComentarioInvalido("Escreva o seu comentário.", 400)
    return texto


def _inteiro_positivo(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and valor >= 1


def _onde_comentou(treino: dict, nome_do_treino: object, ficha: object, item: object, exercicio: object) -> tuple:
    """(ficha_ordem, ficha_nome, exercicio_nome) do que o aluno estava vendo; (None, None, None) = treino inteiro.

    Confere que o aluno ainda vê o que viu ao escrever: se o professor trocou o treino ou o exercício nesse meio tempo,
    o comentário não pode cair no lugar errado (409 "atualize a página").
    """
    mudou = ComentarioInvalido("O seu treino mudou. Atualize a página e comente de novo.", 409)
    if not isinstance(nome_do_treino, str) or nome_do_treino != treino["nome"]:
        raise mudou
    if ficha is None and item is None and exercicio is None:
        return None, None, None
    if not (_inteiro_positivo(ficha) and _inteiro_positivo(item) and isinstance(exercicio, str) and exercicio):
        raise ComentarioInvalido("Escolha o exercício de novo.", 400)
    for f in treino["fichas"]:
        if f["ordem"] != ficha:
            continue
        for grupo in f["grupos"]:
            for e in grupo["exercicios"]:
                if e["ordem"] == item:
                    if e["exercicio"] != exercicio:
                        raise mudou
                    return f["ordem"], f["nome"], e["exercicio"]
    raise mudou


def enviar_comentario(
    conn: sqlite3.Connection,
    aluno_id: int,
    treino: object,
    texto: object,
    ficha: object = None,
    item: object = None,
    exercicio: object = None,
    agora: datetime | None = None,
) -> dict:
    """O aluno comenta o treino inteiro (sem ficha/item/exercicio) ou um exercício. Devolve {"repetido": bool}.

    `treino` é o nome do treino que o celular mostrava; `ficha` e `item` são os números (1, 2, 3...) da ficha e do exercício
    dentro dela e `exercicio` o nome que o celular mostrava: servem para achar o lugar certo e conferir que nada mudou.
    A conferência e a gravação acontecem na mesma transação (`BEGIN IMMEDIATE`).
    """
    agora = agora or agora_utc()
    texto = _texto_limpo(texto)
    conn.execute("BEGIN IMMEDIATE")
    try:
        ativo = conn.execute("SELECT id FROM treino WHERE aluno_id = ? AND ativo = 1", (aluno_id,)).fetchone()
        visto = aluno_treino.treino_do_aluno(conn, aluno_id, agora) if ativo else None
        if visto is None:
            raise ComentarioInvalido("Você não tem um treino ativo. Atualize a página.", 409)
        ficha_ordem, ficha_nome, exercicio_nome = _onde_comentou(visto, treino, ficha, item, exercicio)

        repetido = conn.execute(
            """
            SELECT 1 FROM comentario
            WHERE aluno_id = ? AND treino_id = ? AND texto = ? AND criado_em >= ?
              AND ficha_ordem IS ? AND exercicio_nome IS ?
            """,
            (aluno_id, ativo["id"], texto, momento_para_texto(agora - JANELA_DA_REPETICAO), ficha_ordem, exercicio_nome),
        ).fetchone()
        if repetido is None:
            comeco, fim = limites_do_dia(agora)
            hoje = conn.execute(
                "SELECT COUNT(*) FROM comentario WHERE aluno_id = ? AND criado_em >= ? AND criado_em < ?",
                (aluno_id, comeco, fim),
            ).fetchone()[0]
            if hoje >= LIMITE_POR_DIA:
                raise ComentarioInvalido(
                    "Você já enviou muitos comentários hoje. Se precisar, fale com o seu professor na academia.", 429
                )
            conn.execute(
                """
                INSERT INTO comentario
                    (aluno_id, treino_id, treino_nome, ficha_ordem, ficha_nome, exercicio_nome, texto, criado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (aluno_id, ativo["id"], visto["nome"], ficha_ordem, ficha_nome, exercicio_nome, texto, momento_para_texto(agora)),
            )
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return {"repetido": repetido is not None}


# ------------------------------------------------------------------ o professor lê


def contar_nao_lidos(conn: sqlite3.Connection) -> int:
    """Quantos comentários nenhum professor marcou como lido (o número do menu "Comentários")."""
    return conn.execute("SELECT COUNT(*) FROM comentario WHERE lido_em IS NULL").fetchone()[0]


def _para_exibir(linha: sqlite3.Row) -> dict:
    return {
        "id": linha["id"],
        "aluno_id": linha["aluno_id"],
        "aluno": linha["aluno_nome"],
        "treino": linha["treino_nome"],
        "ficha": linha["ficha_nome"],  # None = comentário do treino inteiro
        "exercicio": linha["exercicio_nome"],  # None = comentário do treino inteiro
        "texto": linha["texto"],
        "quando": momento_local(linha["criado_em"]).strftime("%d/%m/%Y %H:%M"),
        "lido": linha["lido_em"] is not None,
    }


def listar(
    conn: sqlite3.Connection, so_nao_lidos: bool = True, aluno_id: int | None = None, limite: int = LIMITE_DA_LISTA
) -> dict:
    """Os comentários, do mais novo para o mais antigo: {"nao_lidos": N, "nao_lidos_do_aluno": N, "total": N, "comentarios": [...]}.

    `so_nao_lidos`: só os que ainda não foram marcados como lidos. `aluno_id`: só os de um aluno (a ficha dele).
    Devolve no máximo `limite` (nunca mais que `LIMITE_DA_LISTA`); `total` diz quantos existem com este filtro.
    """
    filtros, valores = [], []
    if so_nao_lidos:
        filtros.append("c.lido_em IS NULL")
    if aluno_id is not None:
        filtros.append("c.aluno_id = ?")
        valores.append(aluno_id)
    onde = ("WHERE " + " AND ".join(filtros)) if filtros else ""
    total = conn.execute(f"SELECT COUNT(*) FROM comentario c {onde}", valores).fetchone()[0]
    linhas = conn.execute(
        f"""
        SELECT c.id, c.aluno_id, a.nome AS aluno_nome, c.treino_nome, c.ficha_nome, c.exercicio_nome,
               c.texto, c.criado_em, c.lido_em
        FROM comentario c JOIN aluno a ON a.id = c.aluno_id
        {onde}
        ORDER BY c.criado_em DESC, c.id DESC
        LIMIT ?
        """,  # o WHERE é montado só com texto fixo do código; os valores vão como parâmetro
        [*valores, min(limite, LIMITE_DA_LISTA)],
    ).fetchall()
    nao_lidos_do_aluno = None
    if aluno_id is not None:
        nao_lidos_do_aluno = conn.execute(
            "SELECT COUNT(*) FROM comentario WHERE aluno_id = ? AND lido_em IS NULL", (aluno_id,)
        ).fetchone()[0]
    return {
        "nao_lidos": contar_nao_lidos(conn),
        "nao_lidos_do_aluno": nao_lidos_do_aluno,  # só quando se pede um aluno
        "total": total,
        "comentarios": [_para_exibir(linha) for linha in linhas],
    }


def marcar_lido(conn: sqlite3.Connection, comentario_id: int, agora: datetime | None = None) -> bool:
    """O professor marcou o comentário como lido. Devolve False se o comentário não existe. Marcar de novo não muda a data."""
    agora = agora or agora_utc()
    with conn:
        existe = conn.execute("SELECT 1 FROM comentario WHERE id = ?", (comentario_id,)).fetchone()
        if existe is None:
            return False
        conn.execute(
            "UPDATE comentario SET lido_em = ? WHERE id = ? AND lido_em IS NULL", (momento_para_texto(agora), comentario_id)
        )
    return True


def marcar_lidos_do_aluno(conn: sqlite3.Connection, aluno_id: int, ids: object, agora: datetime | None = None) -> int:
    """O professor marcou como lidos os comentários `ids` deste aluno (botão da ficha). Devolve quantos mudaram.

    Só marca os que o professor estava vendo na tela (`ids`), e não "tudo o que está sem ler": um comentário que o aluno
    mandou depois de a ficha abrir, ou um antigo que a ficha não mostra (ela mostra só os mais novos), ficaria marcado como
    lido sem ninguém ter lido. Um id de outro aluno ou que não existe é ignorado.
    """
    if (
        not isinstance(ids, list)
        or not 1 <= len(ids) <= LIMITE_DA_LISTA
        or not all(isinstance(i, int) and not isinstance(i, bool) and 1 <= i <= _MAIOR_ID for i in ids)
    ):
        raise ComentarioInvalido("Pedido inválido. Atualize a página.", 400)
    agora = agora or agora_utc()
    marcadores = ",".join("?" * len(ids))  # só "?" separados por vírgula; os números vão como parâmetro
    with conn:
        return conn.execute(
            f"UPDATE comentario SET lido_em = ? WHERE aluno_id = ? AND lido_em IS NULL AND id IN ({marcadores})",
            [momento_para_texto(agora), aluno_id, *ids],
        ).rowcount
