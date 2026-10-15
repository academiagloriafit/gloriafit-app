"""O treino que o aluno vê no celular (tela /aluno, rota GET /api/aluno/treino).

Regra (decidida pelo Thiago em 08/10/2026, ver README "Ciclo do treino"): o aluno vê só o treino ATIVO, e cada
aluno tem no máximo um. Treino inativo (concluído ou trocado por outro) fica no histórico do professor e o aluno
não vê.

Tudo sai daqui em texto pronto (dose "4 × 12", intervalo "1 min 30 s", etiquetas "A1"/"A2" do bi-set), com as mesmas
funções que a impressão do cupom usa, para o celular e o papel nunca discordarem. O navegador só desenha.

O que NÃO sai daqui, de propósito: ids (do treino, da ficha, do exercício), quem montou, a origem (app ou Data4U),
o andamento do ciclo ("hora de trocar") e dados de outros treinos. O aluno recebe só o que precisa para treinar.
"""

import sqlite3

from app import treinos
from app.alunos import dose_do_item, etiquetas_dos_itens, texto_da_pausa
from app.datas import formatar_dia

_NOME_DO_BLOCO = {2: "Bi-set", 3: "Tri-set"}


def _lista_com_e(etiquetas: list[str]) -> str:
    """['A1', 'A2'] -> 'A1 e A2'; ['A1', 'A2', 'A3'] -> 'A1, A2 e A3'."""
    if len(etiquetas) == 1:
        return etiquetas[0]
    return ", ".join(etiquetas[:-1]) + " e " + etiquetas[-1]


def _exercicio(item: dict, etiqueta: str) -> dict:
    return {
        "etiqueta": etiqueta,
        "exercicio": item["exercicio"],
        "dose": dose_do_item(item),
        "carga": (item["carga"] or "").strip(),
        "intervalo": texto_da_pausa(item["pausa"]),
        "observacao": (item["observacao"] or "").strip(),
    }


def _grupos_da_ficha(itens: list[dict]) -> list[dict]:
    """Os exercícios da ficha na ordem, juntando os do mesmo bi-set/tri-set.

    Cada grupo: {"nome": None | "Bi-set" | "Tri-set" | "Sequência", "instrucao": "" | "Faça A1 e A2 seguidos",
    "exercicios": [...]}. Exercício sozinho = grupo sem nome com um exercício.
    """
    etiquetas = etiquetas_dos_itens(itens)
    grupos: list[dict] = []
    ultimo_bloco = None
    for item, etiqueta in zip(itens, etiquetas, strict=True):
        bloco = item["bloco"]
        if bloco is not None and grupos and bloco == ultimo_bloco:
            grupos[-1]["exercicios"].append(_exercicio(item, etiqueta))
        else:
            grupos.append({"nome": None, "instrucao": "", "exercicios": [_exercicio(item, etiqueta)]})
        ultimo_bloco = bloco
    for grupo in grupos:
        quantos = len(grupo["exercicios"])
        if quantos >= 2:
            grupo["nome"] = _NOME_DO_BLOCO.get(quantos, "Sequência")
            grupo["instrucao"] = f"Faça {_lista_com_e([e['etiqueta'] for e in grupo['exercicios']])} seguidos"
    return grupos


def treino_do_aluno(conn: sqlite3.Connection, aluno_id: int) -> dict | None:
    """O treino ativo do aluno pronto para mostrar, ou None se ele não tem treino ativo.

    {"nome", "inicio" ("06/10/2026" ou None), "fim" (idem), "fichas": [{"nome", "grupos": [...]}]}.
    Ficha sem nenhum exercício não aparece (não há o que mostrar).
    """
    linha = conn.execute("SELECT id FROM treino WHERE aluno_id = ? AND ativo = 1", (aluno_id,)).fetchone()
    if linha is None:
        return None
    treino = treinos.obter_treino(conn, linha["id"])
    if treino is None:  # apagado entre as duas consultas (a importação do Data4U apaga e recria)
        return None
    return {
        "nome": treino["nome"],
        "inicio": formatar_dia(treino["inicio"]),
        "fim": formatar_dia(treino["fim"]),
        "fichas": [
            {"nome": ficha["nome"], "grupos": _grupos_da_ficha(ficha["itens"])}
            for ficha in treino["fichas"]
            if ficha["itens"]
        ],
    }
