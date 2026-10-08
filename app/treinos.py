"""Salvar e ler treinos (treino -> fichas -> exercícios).

A validação aqui é a que vale: a tela também confere, mas o navegador não é
confiável (qualquer um pode mandar um pedido direto ao servidor), então tudo
é conferido de novo antes de gravar.
"""

import sqlite3
import unicodedata

from app.texto import normalizar

# Quando o Claude ou um robô montar treinos sozinhos (no futuro), este é o autor.
AUTOR_AUTOMATICO = "Academia Glória Fit"

# Limites do Data4U (colunas NM_TREINO, NM_TREINO_FICHA, NR_SERIE, DS_REPETICAO, DS_PESO)
LIMITE_NOME_TREINO = 40
LIMITE_NOME_FICHA = 15
LIMITE_CAMPO = 11
# Limites nossos
LIMITE_QUEM_MONTOU = 60
LIMITE_OBSERVACAO = 200  # a maior observação real do Data4U tem 131 letras (conferido em 08/10/2026)
MAXIMO_PAUSA = 3599  # segundos: 59 min 59 s (o Data4U guarda "hh:mm:ss"; nenhuma pausa real passa de 1 hora)
MAXIMO_FICHAS = 26
MAXIMO_ITENS_POR_FICHA = 100
MINIMO_NO_BLOCO = 2
MAXIMO_NO_BLOCO = 3


class AlunoNaoEncontrado(Exception):
    pass


class TreinoInvalido(Exception):
    """O treino não pode ser salvo. `problemas` é a lista de motivos, em português."""

    def __init__(self, problemas: list[str], status: int = 400):
        super().__init__("; ".join(problemas))
        self.problemas = problemas
        self.status = status  # 400 = dado inválido, 409 = conflito (nome já usado)


# ------------------------------------------------------------------ texto


def limpar_espacos(texto: str) -> str:
    """Tira espaços das pontas e troca qualquer sequência de espaços/quebras de linha por um espaço."""
    return " ".join(texto.split())


def _tem_caractere_de_controle(texto: str) -> bool:
    # Categorias "C...": controle (ex.: caractere nulo, bip), formato invisível etc.
    return any(unicodedata.category(c).startswith("C") for c in texto)


def _texto(valor, rotulo: str, maximo: int, obrigatorio: bool, problemas: list[str]) -> str | None:
    """Confere um campo de texto. Devolve o texto limpo, ou None (e anota o problema)."""
    if valor is None and not obrigatorio:
        return ""
    if not isinstance(valor, str):
        problemas.append(f"{rotulo} precisa ser um texto.")
        return None
    limpo = limpar_espacos(valor)
    if _tem_caractere_de_controle(limpo):
        problemas.append(f"{rotulo} tem caracteres inválidos.")
        return None
    if obrigatorio and not limpo:
        problemas.append(f"{rotulo} é obrigatório.")
        return None
    if len(limpo) > maximo:
        problemas.append(f"{rotulo} tem {len(limpo)} caracteres; o máximo é {maximo}.")
        return None
    return limpo


def _inteiro(valor) -> bool:
    # bool é um tipo de int em Python (True == 1): não pode valer como número aqui.
    return isinstance(valor, int) and not isinstance(valor, bool)


# ------------------------------------------------------------------ validação


def _pausa(valor, rotulo: str, problemas: list[str]):
    """Intervalo em segundos. Aceita vazio (None) e 0 (= sem intervalo, guardado como vazio).
    Devolve o número (ou None quando não há intervalo); se o valor é inválido, anota o problema e devolve False."""
    if valor is None:
        return None
    if not _inteiro(valor) or not 0 <= valor <= MAXIMO_PAUSA:
        problemas.append(f"{rotulo}: intervalo inválido (de 0 a 59 min e 59 s).")
        return False
    return valor or None


def _validar_itens(conn, itens, rotulo: str, problemas: list[str]) -> list[dict] | None:
    if not isinstance(itens, list) or not itens:
        problemas.append(f"{rotulo}: adicione pelo menos um exercício.")
        return None
    if len(itens) > MAXIMO_ITENS_POR_FICHA:
        problemas.append(f"{rotulo}: no máximo {MAXIMO_ITENS_POR_FICHA} exercícios.")
        return None

    limpos = []
    for posicao, item in enumerate(itens, start=1):
        onde = f"{rotulo}, exercício {posicao}"
        if not isinstance(item, dict):
            problemas.append(f"{onde}: formato inválido.")
            continue
        exercicio_id = item.get("exercicio_id")
        if not _inteiro(exercicio_id):
            problemas.append(f"{onde}: exercício inválido.")
            continue
        series = _texto(item.get("series"), f"{onde}: séries", LIMITE_CAMPO, True, problemas)
        repeticoes = _texto(item.get("repeticoes"), f"{onde}: repetições", LIMITE_CAMPO, True, problemas)
        carga = _texto(item.get("carga"), f"{onde}: peso", LIMITE_CAMPO, False, problemas)
        observacao = _texto(item.get("observacao"), f"{onde}: observação", LIMITE_OBSERVACAO, False, problemas)
        pausa = _pausa(item.get("pausa"), onde, problemas)
        bloco = item.get("bloco")
        if bloco is not None and (not _inteiro(bloco) or bloco < 1):
            problemas.append(f"{onde}: bloco inválido.")
            continue
        if None in (series, repeticoes, carga, observacao) or pausa is False:
            continue
        limpos.append(
            {"exercicio_id": exercicio_id, "series": series, "repeticoes": repeticoes,
             "carga": carga or None, "pausa": pausa, "observacao": observacao or None,
             "bloco": bloco, "posicao": posicao}
        )
    if len(limpos) != len(itens):
        return None  # já anotamos os problemas; não vale conferir o resto

    # todos os exercícios existem e estão ativos?
    ids = sorted({i["exercicio_id"] for i in limpos})
    marcas = ",".join("?" * len(ids))
    achados = {
        linha[0]
        for linha in conn.execute(f"SELECT id FROM exercicio WHERE ativo = 1 AND id IN ({marcas})", ids)
    }
    faltando = [i for i in ids if i not in achados]
    if faltando:
        problemas.append(f"{rotulo}: exercício que não existe ou foi desativado (id {faltando[0]}).")
        return None

    return _renumerar_blocos(limpos, rotulo, problemas)


def _renumerar_blocos(itens: list[dict], rotulo: str, problemas: list[str]) -> list[dict] | None:
    """Confere os bi-sets/tri-sets e renumera os blocos 1, 2, 3... na ordem em que aparecem."""
    novo_numero: dict[int, int] = {}
    fechados: set[int] = set()  # blocos que já terminaram (não podem reaparecer mais abaixo)
    i = 0
    ok = True
    while i < len(itens):
        bloco = itens[i]["bloco"]
        if bloco is None:
            i += 1
            continue
        j = i
        while j < len(itens) and itens[j]["bloco"] == bloco:
            j += 1
        tamanho = j - i
        if bloco in fechados:
            problemas.append(f"{rotulo}: os exercícios do mesmo bi-set/tri-set precisam estar juntos.")
            ok = False
        elif not MINIMO_NO_BLOCO <= tamanho <= MAXIMO_NO_BLOCO:
            problemas.append(f"{rotulo}: um bi-set tem 2 exercícios e um tri-set tem 3.")
            ok = False
        fechados.add(bloco)
        novo_numero.setdefault(bloco, len(novo_numero) + 1)
        i = j
    if not ok:
        return None
    for item in itens:
        if item["bloco"] is not None:
            item["bloco"] = novo_numero[item["bloco"]]
    return itens


def _validar_fichas(conn, fichas, problemas: list[str]) -> list[dict] | None:
    if not isinstance(fichas, list) or not 1 <= len(fichas) <= MAXIMO_FICHAS:
        problemas.append(f"O treino precisa ter de 1 a {MAXIMO_FICHAS} fichas (A, B, C...).")
        return None
    validas = []
    for numero, ficha in enumerate(fichas, start=1):
        if not isinstance(ficha, dict):
            problemas.append(f"Ficha {numero}: formato inválido.")
            continue
        nome = _texto(ficha.get("nome"), f"O nome da ficha {numero}", LIMITE_NOME_FICHA, True, problemas)
        itens = _validar_itens(conn, ficha.get("itens"), nome or f"Ficha {numero}", problemas)
        if nome is not None and itens is not None:
            validas.append({"nome": nome, "itens": itens})
    return validas if len(validas) == len(fichas) else None


# ------------------------------------------------------------------ salvar e ler


def salvar_treino(conn: sqlite3.Connection, aluno_id: int, dados) -> int:
    """Grava um treino novo para o aluno. Devolve o id do treino.

    `dados` = {"nome_treino": str, "montado_por": str,
               "fichas": [{"nome": str, "itens": [{"exercicio_id", "series",
                           "repeticoes", "carga" (o "Peso" da tela), "pausa" (intervalo, em
                           segundos, opcional), "observacao" (opcional), "bloco"}]}]}
    A ordem das fichas e dos exercícios é a ordem das listas. Tudo ou nada: se
    qualquer coisa estiver errada, nada é gravado.
    """
    if conn.execute("SELECT 1 FROM aluno WHERE id = ?", (aluno_id,)).fetchone() is None:
        raise AlunoNaoEncontrado(aluno_id)
    if not isinstance(dados, dict):
        raise TreinoInvalido(["Formato do pedido inválido."])

    problemas: list[str] = []
    nome_treino = _texto(dados.get("nome_treino"), "O nome do treino", LIMITE_NOME_TREINO, True, problemas)
    montado_por = _texto(dados.get("montado_por"), "O nome de quem montou", LIMITE_QUEM_MONTOU, True, problemas)
    fichas = _validar_fichas(conn, dados.get("fichas"), problemas)
    if problemas:
        raise TreinoInvalido(problemas)

    # O Data4U recusa dois treinos com o mesmo nome para o mesmo aluno; o app segue a mesma regra.
    # Vale contra TODOS os treinos do aluno, inclusive o histórico copiado do Data4U.
    usados = {normalizar(r[0]) for r in conn.execute("SELECT nome FROM treino WHERE aluno_id = ?", (aluno_id,))}
    if normalizar(nome_treino) in usados:
        raise TreinoInvalido(
            [f'Este aluno já tem um treino chamado "{nome_treino}". Escolha outro nome.'], status=409
        )

    try:
        with conn:  # uma transação: ou grava tudo, ou nada
            treino_id = conn.execute(
                "INSERT INTO treino (aluno_id, nome, montado_por) VALUES (?, ?, ?)",
                (aluno_id, nome_treino, montado_por),
            ).lastrowid
            for ordem_ficha, ficha in enumerate(fichas, start=1):
                ficha_id = conn.execute(
                    "INSERT INTO ficha (treino_id, nome, ordem) VALUES (?, ?, ?)",
                    (treino_id, ficha["nome"], ordem_ficha),
                ).lastrowid
                for ordem_item, item in enumerate(ficha["itens"], start=1):
                    conn.execute(
                        "INSERT INTO ficha_item (ficha_id, ordem, bloco, exercicio_id, series, repeticoes, carga,"
                        " pausa, observacao) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (ficha_id, ordem_item, item["bloco"], item["exercicio_id"],
                         item["series"], item["repeticoes"], item["carga"], item["pausa"], item["observacao"]),
                    )
    except sqlite3.IntegrityError as erro:
        # Dois "salvar" ao mesmo tempo com o mesmo nome: o índice único do banco barra o segundo.
        # Só ESTE erro (violação de "único") vira 409. Qualquer outra violação (regra CHECK,
        # chave estrangeira...) é defeito nosso e precisa aparecer como erro, não ser
        # mascarada como "nome repetido".
        if erro.sqlite_errorcode != sqlite3.SQLITE_CONSTRAINT_UNIQUE:
            raise
        raise TreinoInvalido(
            [f'Este aluno já tem um treino chamado "{nome_treino}". Escolha outro nome.'], status=409
        ) from None
    return treino_id


def obter_treino(conn: sqlite3.Connection, treino_id: int) -> dict | None:
    """O treino completo (com nomes dos exercícios), ou None se não existir.

    `origem` é 'app' (montado aqui) ou 'data4u' (histórico copiado do Data4U). Nos itens, `series`,
    `repeticoes`, `carga`, `pausa` (segundos) e `observacao` podem ser None: o histórico do Data4U
    tem prescrições sem esses campos.
    """
    treino = conn.execute(
        "SELECT id, aluno_id, nome, montado_por, ativo, origem, criado_em FROM treino WHERE id = ?", (treino_id,)
    ).fetchone()
    if treino is None:
        return None
    resultado = dict(treino)
    resultado["fichas"] = []
    for ficha in conn.execute("SELECT id, nome, ordem FROM ficha WHERE treino_id = ? ORDER BY ordem", (treino_id,)):
        itens = conn.execute(
            """
            SELECT i.ordem, i.bloco, i.exercicio_id, e.nome AS exercicio,
                   i.series, i.repeticoes, i.carga, i.pausa, i.observacao
            FROM ficha_item i JOIN exercicio e ON e.id = i.exercicio_id
            WHERE i.ficha_id = ? ORDER BY i.ordem
            """,
            (ficha["id"],),
        ).fetchall()
        resultado["fichas"].append(
            {"nome": ficha["nome"], "ordem": ficha["ordem"], "itens": [dict(i) for i in itens]}
        )
    return resultado
