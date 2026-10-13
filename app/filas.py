"""Filas numeradas de treino (fase 2 do pedido do Thiago de 09/10/2026; decisões de 13/10/2026).

Uma FILA é uma sequência de treinos padrão numerados (Treino 1, 2, 3...) para um tipo de aluno: Homem, Mulher,
Adolescente, Gestante, Grupos de risco. As regras combinadas com o Thiago:

- O app NÃO troca o treino do aluno sozinho. Ele só SUGERE o próximo número da fila, e o professor (ou o Thiago)
  aprova: abrir o treino sugerido na tela de lançar treino, conferir e clicar em "Salvar treino".
- Quem coloca o aluno numa fila é o professor, que digita o próprio nome (o app não tem login de professor).
- Gestante e Grupos de risco só aceitam o aluno depois que o professor registra que conferiu a liberação
  (atestado/triagem): "sim", a data e o nome dele. Só isso é guardado: nem o atestado nem o motivo (dado de saúde).
- A sugestão aparece em dois momentos: quando o aluno não tem treino ativo (por exemplo, o professor clicou em
  "Concluído") e quando o treino ativo chegou na hora de trocar (meta de treinos por ficha cumprida ou data de fim
  vencida: o aviso que já existe em app/ciclo.py).
- Quando o aluno estava no último número da fila, o app avisa "fim da fila": nada recomeça nem se repete sozinho.
- As filas são montadas com o "Salvar como treino padrão" (app/modelos.py), escolhendo a fila e o número.
"""

import sqlite3
from datetime import datetime

from app.datas import agora_utc, dia_local, formatar_dia, hoje, momento_para_texto
from app.treinos import (
    LIMITE_QUEM_MONTOU,
    AlunoNaoEncontrado,
    TreinoInvalido,
    _dia,
    _inteiro,
    validar_texto,
)

# Cada fila tem até 6 treinos padrão ("Treino 1" a "Treino 6"), um evoluindo do outro. O banco ainda aceita até 99
# (CHECK do schema): apertar isso pediria recriar a tabela, e a regra de verdade mora aqui e em treino_modelo.js.
MAXIMO_NUMERO_NA_FILA = 6


class FilaInvalida(TreinoInvalido):
    """O pedido sobre filas não pode ser feito. `problemas` é a lista de motivos, em português."""


# ------------------------------------------------------------------ ler as filas


def _treinos_por_fila(conn: sqlite3.Connection) -> dict[int, list[dict]]:
    """{id da fila: [{"modelo_id", "numero", "nome"}, ...]} com cada fila em ordem de número."""
    resultado: dict[int, list[dict]] = {}
    for linha in conn.execute(
        "SELECT id, fila_id, numero, nome FROM modelo_treino WHERE fila_id IS NOT NULL ORDER BY fila_id, numero"
    ):
        resultado.setdefault(linha["fila_id"], []).append(
            {"modelo_id": linha["id"], "numero": linha["numero"], "nome": linha["nome"]}
        )
    return resultado


def listar_filas(conn: sqlite3.Connection) -> list[dict]:
    """Todas as filas, na ordem das telas, cada uma com os seus treinos (em ordem de número).

    [{"id", "nome", "exige_liberacao" (True/False), "treinos": [{"modelo_id", "numero", "nome"}]}]
    """
    treinos = _treinos_por_fila(conn)
    return [
        {
            "id": f["id"],
            "nome": f["nome"],
            "exige_liberacao": bool(f["exige_liberacao"]),
            "treinos": treinos.get(f["id"], []),
        }
        for f in conn.execute("SELECT id, nome, exige_liberacao FROM fila ORDER BY ordem, id")
    ]


def _fila(conn: sqlite3.Connection, fila_id) -> sqlite3.Row | None:
    if not _inteiro(fila_id):
        return None
    return conn.execute("SELECT id, nome, exige_liberacao FROM fila WHERE id = ?", (fila_id,)).fetchone()


# ------------------------------------------------------------------ o lugar de um treino padrão na fila


def validar_posicao(
    conn: sqlite3.Connection, dados: dict, problemas: list[str], conflitos: list[str]
) -> tuple[int | None, int | None]:
    """Confere a fila e o número que vêm junto com um treino padrão: (fila_id, numero) ou (None, None) se for solto.

    `dados["fila_id"]` e `dados["numero"]`: os dois vazios = treino padrão sem fila; os dois preenchidos = o lugar
    dele na fila. Um sem o outro, fila que não existe ou número fora de 1 a 6 anotam o problema em `problemas`
    (dado inválido, 400); número que já tem treino na fila anota em `conflitos` (409). Nos dois casos devolve (None, None).
    """
    fila_id, numero = dados.get("fila_id"), dados.get("numero")
    fila_id = None if fila_id == "" else fila_id
    numero = None if numero == "" else numero
    if fila_id is None and numero is None:
        return None, None
    if fila_id is None or numero is None:
        problemas.append("Para guardar o treino numa fila, escolha a fila E o número do treino (ou deixe os dois em branco).")
        return None, None
    fila = _fila(conn, fila_id)
    if fila is None:
        problemas.append("A fila escolhida não existe.")
        return None, None
    if not _inteiro(numero) or not 1 <= numero <= MAXIMO_NUMERO_NA_FILA:
        problemas.append(f"O número do treino na fila precisa ser um inteiro de 1 a {MAXIMO_NUMERO_NA_FILA}.")
        return None, None
    ocupado = conn.execute(
        "SELECT nome FROM modelo_treino WHERE fila_id = ? AND numero = ?", (fila["id"], numero)
    ).fetchone()
    if ocupado is not None:
        conflitos.append(f'A fila {fila["nome"]} já tem o Treino {numero} ("{ocupado["nome"]}"). Escolha outro número.')
        return None, None
    return fila["id"], numero


def texto_da_posicao(nome_da_fila: str | None, numero: int | None) -> str:
    """'Mulher · Treino 3' (vazio para treino padrão solto)."""
    return f"{nome_da_fila} · Treino {numero}" if nome_da_fila and numero else ""


# ------------------------------------------------------------------ colocar o aluno numa fila


def definir_fila(conn: sqlite3.Connection, aluno_id: int, dados, agora: datetime | None = None) -> None:
    """O professor coloca o aluno numa fila (ou muda a fila dele).

    `dados` = {"fila_id": int, "professor": str (quem está colocando; até 60 letras),
               "liberacao_conferida": True (obrigatório nas filas que exigem liberação),
               "liberacao_em": "AAAA-MM-DD" (opcional: vazio = hoje; não pode ser no futuro)}.
    Nas filas que exigem liberação (Gestante, Grupos de risco) o professor precisa confirmar que conferiu o
    atestado/triagem; o app guarda só "sim", o dia e o nome dele. Nas outras, esses campos são ignorados.
    Mudar para OUTRA fila zera a posição (o aluno começa no início da nova fila); repetir a mesma fila mantém o número
    em que ele estava. Tudo ou nada.
    """
    if conn.execute("SELECT 1 FROM aluno WHERE id = ?", (aluno_id,)).fetchone() is None:
        raise AlunoNaoEncontrado(aluno_id)
    if not isinstance(dados, dict):
        raise FilaInvalida(["Formato do pedido inválido."])
    agora = agora or agora_utc()
    problemas: list[str] = []
    professor = validar_texto(dados.get("professor"), "O nome do professor", LIMITE_QUEM_MONTOU, True, problemas)
    fila = _fila(conn, dados.get("fila_id"))
    if fila is None:
        problemas.append("Escolha a fila.")

    liberacao_em = liberacao_por = None
    if fila is not None and fila["exige_liberacao"]:
        if dados.get("liberacao_conferida") is not True:
            problemas.append(
                f'A fila {fila["nome"]} só aceita aluno com a liberação conferida: confirme que você viu o atestado/triagem.'
            )
        dia = _dia(dados.get("liberacao_em"), "Data da liberação", problemas)
        if dia is None:
            dia = hoje(agora)
        if dia is not False and dia > hoje(agora):  # 'AAAA-MM-DD' compara como texto
            problemas.append("A data da liberação não pode ser no futuro.")
        liberacao_em, liberacao_por = dia, professor
    if problemas:
        raise FilaInvalida(problemas)

    with conn:
        conn.execute(
            """
            INSERT INTO aluno_fila (aluno_id, fila_id, numero_atual, definida_por, definida_em, liberacao_em, liberacao_por)
            VALUES (?, ?, NULL, ?, ?, ?, ?)
            ON CONFLICT(aluno_id) DO UPDATE SET
                numero_atual  = CASE WHEN aluno_fila.fila_id = excluded.fila_id THEN aluno_fila.numero_atual ELSE NULL END,
                fila_id       = excluded.fila_id,
                definida_por  = excluded.definida_por,
                definida_em   = excluded.definida_em,
                liberacao_em  = excluded.liberacao_em,
                liberacao_por = excluded.liberacao_por
            """,
            (aluno_id, fila["id"], professor, momento_para_texto(agora), liberacao_em, liberacao_por),
        )


def tirar_da_fila(conn: sqlite3.Connection, aluno_id: int) -> None:
    """O aluno deixa de estar numa fila (o treino dele não muda). Sem fila, não faz nada."""
    if conn.execute("SELECT 1 FROM aluno WHERE id = ?", (aluno_id,)).fetchone() is None:
        raise AlunoNaoEncontrado(aluno_id)
    with conn:
        conn.execute("DELETE FROM aluno_fila WHERE aluno_id = ?", (aluno_id,))


# ------------------------------------------------------------------ a fila na ficha do aluno


def proximo_da_fila(treinos: list[dict], numero_atual: int | None) -> dict | None:
    """O primeiro treino da fila com número maior que o atual (ou o primeiro da fila, se o aluno não começou).

    Números podem ter buracos (1, 2, 4): vale o próximo que existe. None = a fila acabou (ou está vazia).
    """
    for treino in treinos:  # já em ordem de número
        if numero_atual is None or treino["numero"] > numero_atual:
            return treino
    return None


def fila_do_aluno(conn: sqlite3.Connection, aluno_id: int, hora_de_trocar: bool) -> dict:
    """O que a ficha do aluno mostra no cartão "Fila de treino".

    `hora_de_trocar` = o aluno não tem treino ativo, ou o treino ativo chegou na hora de trocar (quem calcula é a
    ficha: ver app/alunos.py). Só nesse caso há `sugestao`.

    Devolve {"filas": todas as filas (para escolher), "atual": None (sem fila) ou {
        "fila_id", "nome", "exige_liberacao", "numero_atual" (None = ainda não começou), "definida_por", "definida_em",
        "liberacao_em", "liberacao_por" (vazios nas filas sem liberação),
        "treinos": [{"modelo_id", "numero", "nome", "atual", "sugerido"}], "vazia" (a fila não tem treino padrão ainda),
        "hora_de_trocar", "sugestao": {"modelo_id", "numero", "nome"} ou None, "fim_da_fila" (hora de trocar e o aluno
        já fez o último número)}}.
    """
    filas = listar_filas(conn)
    linha = conn.execute(
        "SELECT fila_id, numero_atual, definida_por, definida_em, liberacao_em, liberacao_por FROM aluno_fila WHERE aluno_id = ?",
        (aluno_id,),
    ).fetchone()
    if linha is None:
        return {"filas": filas, "atual": None}

    fila = next(f for f in filas if f["id"] == linha["fila_id"])
    numero_atual = linha["numero_atual"]
    proximo = proximo_da_fila(fila["treinos"], numero_atual)
    sugestao = proximo if hora_de_trocar else None
    return {
        "filas": filas,
        "atual": {
            "fila_id": fila["id"],
            "nome": fila["nome"],
            "exige_liberacao": fila["exige_liberacao"],
            "numero_atual": numero_atual,
            "definida_por": linha["definida_por"],
            "definida_em": formatar_dia(dia_local(linha["definida_em"])),
            "liberacao_em": formatar_dia(linha["liberacao_em"]),
            "liberacao_por": linha["liberacao_por"],
            "treinos": [
                {
                    **t,
                    "atual": t["numero"] == numero_atual,
                    "sugerido": sugestao is not None and t["modelo_id"] == sugestao["modelo_id"],
                }
                for t in fila["treinos"]
            ],
            "vazia": not fila["treinos"],
            "hora_de_trocar": hora_de_trocar,
            "sugestao": sugestao,
            "fim_da_fila": bool(hora_de_trocar and fila["treinos"] and proximo is None),
        },
    }
