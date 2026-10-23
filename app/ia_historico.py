"""Histórico do treino feito com a IA: "Por que este treino foi montado assim" (pedido do Thiago, 23/10/2026).

Um professor deu a ideia: quando outro professor abre o treino de um aluno na ficha, ele precisa entender por que o treino está dividido
daquele jeito e por que tem aquela quantidade de exercícios. Hoje o que o professor escreve para o robô (idade, lesões, comorbidades, o que o
aluno quer) some depois de montar o rascunho. Este módulo guarda, LIGADO AO TREINO:

1. o pedido do professor (objetivo, nível, dias, minutos, fila) e o texto que ele escreveu para o robô (as observações; "nenhuma" se não
   escreveu nada) e a conversa de perguntas e respostas, se o robô perguntou algo;
2. a justificativa que o próprio robô escreveu junto com o rascunho (campo `justificativa` da ferramenta, ver app/ia_treino.py) e os alertas;
3. o que o professor mudou entre o rascunho e o treino que salvou (`ia_retorno.comparar`), porque a justificativa descreve o RASCUNHO.

Como funciona: ao criar o rascunho, o servidor guarda o que o robô recebeu na área `_historico` do `ia_pedido.resultado` (que já é apagado
depois de 3 dias: rascunho que ninguém salvou some). Ao salvar o treino com `ia: {pedido_id}`, `registrar` copia isso para `treino_ia`
(permanente, uma linha por treino). A ficha do aluno lê `do_aluno`. Nada daqui vai para a tela do aluno nem para a impressão.

DIFERENTE de app/ia_retorno.py (o relatório do que o robô aprende), que de propósito não liga nada ao aluno. Aqui a ligação é o objetivo:
o texto é do aluno, inclusive saúde (comorbidade, lesão), e fica enquanto o treino existir. Quem tem acesso à ficha do aluno vê (os computadores
autorizados da academia, como já ocorre com o CPF e o WhatsApp), e o texto entra nas cópias de segurança. O texto que o professor escreve já
passa pela conferência de privacidade (sem nome do aluno, CPF, telefone, e-mail) antes de ir ao robô; este módulo só copia o que o robô recebeu.

Limites honestos: (a) a justificativa é a explicação que o robô escreveu junto com o treino, não uma prova do que "pesou" nele; (b) treinos
feitos antes desta função, à mão ou copiados do Data4U não têm histórico; (c) mudanças feitas depois, em "Editar treino", não entram.
"""

import json
import logging
import sqlite3

from app.ia_retorno import ROTULOS_DOS_CAMPOS, RascunhoNaoEncontrado, _carregar, _guardar, comparar
from app.ia_treino import ROTULOS_DOS_NIVEIS, ROTULOS_DOS_OBJETIVOS
from app.treinos import obter_treino

log = logging.getLogger(__name__)

MAXIMO_DE_MUDANCAS_NA_TELA = 10  # linhas de "série/repetição/pausa mudou"; o resto aparece só como "e mais N"


def _lista_de_textos(valor) -> list[str]:
    """Lista de textos não vazios (o que vier torto vira lista vazia)."""
    return [texto for texto in valor if isinstance(texto, str) and texto.strip()] if isinstance(valor, list) else []


def _conversa_limpa(valor) -> list[list[dict]]:
    """As rodadas de perguntas e respostas, só com texto: [[{"pergunta", "resposta"}, ...], ...]. Torto vira vazio."""
    rodadas = []
    for rodada in valor if isinstance(valor, list) else []:
        pares = [
            {"pergunta": par["pergunta"], "resposta": par.get("resposta") if isinstance(par.get("resposta"), str) else ""}
            for par in (rodada if isinstance(rodada, list) else [])
            if isinstance(par, dict) and isinstance(par.get("pergunta"), str) and par["pergunta"].strip()
        ]
        if pares:
            rodadas.append(pares)
    return rodadas


# ------------------------------------------------------------------ guardar (ao salvar o treino)


def registrar(conn: sqlite3.Connection, aluno_id: int, pedido_id: int, treino_id: int) -> bool:
    """O professor acabou de salvar o treino `treino_id` do aluno a partir do rascunho `pedido_id`: guarda o histórico dele.

    Devolve True se registrou, False se não havia o que registrar (rascunho apagado depois de 3 dias, de outro aluno, de antes desta
    função, ou já registrado). Não confia no navegador: o treino comparado é lido do banco e precisa ser do mesmo aluno."""
    treino = obter_treino(conn, treino_id)
    if treino is None or treino["aluno_id"] != aluno_id:
        return False
    conn.execute("BEGIN IMMEDIATE")
    try:
        try:
            resultado = _carregar(conn, aluno_id, pedido_id)
        except RascunhoNaoEncontrado:
            conn.rollback()
            return False
        historico = resultado.get("_historico")
        if not isinstance(historico, dict) or historico.get("gravado"):
            conn.rollback()
            return False
        if conn.execute("SELECT 1 FROM treino_ia WHERE treino_id = ?", (treino_id,)).fetchone():
            conn.rollback()
            return False
        retorno = resultado["_retorno"]
        resumo = resultado.get("resumo")
        justificativa = _lista_de_textos(resultado.get("justificativa")) or ([resumo] if isinstance(resumo, str) and resumo.strip() else [])
        conversa = _conversa_limpa(historico.get("conversa"))
        fichas_pedidas = historico.get("fichas_pedidas")
        fichas_pedidas = fichas_pedidas if isinstance(fichas_pedidas, int) and not isinstance(fichas_pedidas, bool) and 0 <= fichas_pedidas <= 6 else None
        observacoes = historico.get("observacoes") if isinstance(historico.get("observacoes"), str) else ""
        conn.execute(
            "INSERT INTO treino_ia (treino_id, objetivo, nivel, dias, minutos, fila, observacoes, conversa, justificativa, alertas, ajustes,"
            " regras, modelo, fichas_pedidas) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                treino_id,
                retorno["objetivo"],
                retorno["nivel"],
                retorno["dias"],
                retorno["minutos"],
                retorno.get("fila"),
                observacoes,
                json.dumps(conversa, ensure_ascii=False) if conversa else None,
                json.dumps(justificativa, ensure_ascii=False),
                json.dumps(_lista_de_textos(resultado.get("alertas")), ensure_ascii=False),
                json.dumps(comparar(resultado["treino"].get("fichas"), treino["fichas"]), ensure_ascii=False),
                retorno["regras"],
                retorno["modelo"],
                fichas_pedidas,
            ),
        )
        historico["gravado"] = True
        _guardar(conn, pedido_id, resultado)
        conn.commit()
        return True
    except BaseException:
        conn.rollback()
        raise


def registrar_sem_falhar(conn: sqlite3.Connection, aluno_id: int, pedido_id: int, treino_id: int) -> bool:
    """Como `registrar`, mas NUNCA levanta erro: o treino já foi salvo e o histórico é um extra. Se falhar, só vai para o log."""
    try:
        return registrar(conn, aluno_id, pedido_id, treino_id)
    except Exception:  # nada aqui pode estragar o "Salvar treino" do professor
        log.exception("Não consegui guardar o histórico do treino %s (rascunho %s)", treino_id, pedido_id)
        return False


# ------------------------------------------------------------------ mostrar (ficha do aluno)


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _lista_de_exercicios(itens: list[dict]) -> str:
    return "; ".join(f"{item['exercicio']} (ficha {item['ficha']})" for item in itens)


def texto_dos_ajustes(mudancas) -> dict:
    """O que o professor mudou entre o rascunho e o treino salvo, em frases para a tela: {"igual": bool, "linhas": [str]}.

    `mudancas` é o que `ia_retorno.comparar` devolveu (guardado em `treino_ia.ajustes`). "igual": o treino saiu exatamente como o robô fez."""
    if not isinstance(mudancas, dict):
        return {"igual": False, "linhas": []}
    fichas = mudancas.get("fichas") if isinstance(mudancas.get("fichas"), dict) else {}
    tirados = [i for i in mudancas.get("tirados") or [] if isinstance(i, dict)]
    incluidos = [i for i in mudancas.get("incluidos") or [] if isinstance(i, dict)]
    alterados = [i for i in mudancas.get("alterados") or [] if isinstance(i, dict)]
    observacoes = mudancas.get("observacoes_mudadas") or 0
    ordem = mudancas.get("fichas_com_ordem_mudada") or 0
    renomeadas = mudancas.get("fichas_renomeadas") or 0
    cortados = mudancas.get("cortados") or 0
    numero_diferente = fichas.get("ia") != fichas.get("final")
    igual = not (tirados or incluidos or alterados or observacoes or ordem or renomeadas or cortados or numero_diferente)
    linhas: list[str] = []
    if numero_diferente:
        linhas.append(f"Número de fichas: o robô fez {fichas.get('ia')} e o treino ficou com {fichas.get('final')}.")
    if tirados:
        linhas.append(f"Tirou: {_lista_de_exercicios(tirados)}.")
    if incluidos:
        linhas.append(f"Incluiu: {_lista_de_exercicios(incluidos)}.")
    for mudanca in alterados[:MAXIMO_DE_MUDANCAS_NA_TELA]:
        campo = ROTULOS_DOS_CAMPOS.get(mudanca.get("campo"), str(mudanca.get("campo")))
        antes = mudanca.get("de") or "em branco"
        depois = mudanca.get("para") or "em branco"
        linhas.append(f"{mudanca.get('exercicio')} (ficha {mudanca.get('ficha')}): {campo} de {antes} para {depois}.")
    if len(alterados) > MAXIMO_DE_MUDANCAS_NA_TELA:
        linhas.append(f"E mais {len(alterados) - MAXIMO_DE_MUDANCAS_NA_TELA} mudanças de séries, repetições ou pausa.")
    if observacoes:
        linhas.append(f"Mudou o texto de observação de {_plural(observacoes, 'exercício', 'exercícios')}.")
    if ordem:
        linhas.append(f"Mudou a ordem dos exercícios em {_plural(ordem, 'ficha', 'fichas')}.")
    if renomeadas:
        linhas.append(f"Mudou o nome de {_plural(renomeadas, 'ficha', 'fichas')}.")
    if cortados:
        linhas.append(f"Houve mais {cortados} mudanças do que cabe aqui.")
    return {"igual": igual, "linhas": linhas}


def _json(texto, padrao):
    try:
        return json.loads(texto) if texto else padrao
    except ValueError:
        return padrao


def _para_a_tela(linha: sqlite3.Row) -> dict:
    pedido = [
        ("Objetivo", ROTULOS_DOS_OBJETIVOS.get(linha["objetivo"], linha["objetivo"])),
        ("Nível", ROTULOS_DOS_NIVEIS.get(linha["nivel"], linha["nivel"])),
        ("Dias de treino por semana", str(linha["dias"])),
        ("Tempo de cada treino", f"{linha['minutos']} minutos"),
    ]
    if linha["fichas_pedidas"] is not None:  # NULL = treino de antes da versão 17 (o número de fichas era sempre igual aos dias): sem linha
        pedido.append(("Fichas diferentes", f"{linha['fichas_pedidas']} (escolha do professor)" if linha["fichas_pedidas"] else "O robô decidiu"))
    if linha["fila"]:
        pedido.append(("Fila do aluno", linha["fila"]))
    return {
        "pedido": pedido,
        "observacoes": linha["observacoes"],
        "conversa": _conversa_limpa(_json(linha["conversa"], [])),
        "justificativa": _lista_de_textos(_json(linha["justificativa"], [])),
        "alertas": _lista_de_textos(_json(linha["alertas"], [])),
        "ajustes": texto_dos_ajustes(_json(linha["ajustes"], None)),
    }


def do_aluno(conn: sqlite3.Connection, aluno_id: int) -> dict[int, dict]:
    """O histórico dos treinos do aluno que saíram de um rascunho da IA, pronto para a ficha: {treino_id: {...}}.

    Treino sem linha aqui (feito à mão, copiado do Data4U ou de antes desta função) não aparece no resultado."""
    linhas = conn.execute(
        "SELECT h.* FROM treino_ia h JOIN treino t ON t.id = h.treino_id WHERE t.aluno_id = ?", (aluno_id,)
    ).fetchall()
    return {linha["treino_id"]: _para_a_tela(linha) for linha in linhas}
