"""Tela do professor "Quem sumiu": alunos que têm treino ativo e estão há dias sem treinar (pedido do Thiago, 22/10/2026).

Treinar = uma marcação em `sessao`: o aluno tocou em "Treino concluído" no celular OU a recepção imprimiu a ficha (as duas viram a
mesma linha; ver app/ciclo.py). Quem treina na academia mas nem marca no celular nem imprime a ficha aparece aqui como quem sumiu:
a tela avisa isso, e é só uma lista para o professor olhar, não uma mensagem automática.

Quem entra na lista: aluno Ativo (ou provisório, que o app trata como em uso) com treino ativo. Trancado, pendente, desistente, inativo e
cancelado ficam de fora (não precisam ser chamados de volta).

Duas listas, porque são situações diferentes: (1) quem JÁ registrou treino no app (ou teve a ficha impressa) e parou, e (2) quem
nunca registrou nenhum: conta a partir do início do treino (ou do dia em que o treino foi lançado). Na prática a lista 2 é grande
logo que o app começa a ser usado (quase todo aluno tem treino vindo do Data4U e ainda zero registros), e misturada com a 1 ela
empurraria para fora da tela quem de fato parou de treinar.
"""

import sqlite3
from datetime import datetime

from app.alunos import formatar_whatsapp
from app.datas import dia_local, formatar_dia, hoje, ler_dia

PRAZOS = (7, 14, 30)  # os botões da tela (dias sem treinar)
PRAZO_PADRAO = 7
LIMITE_DA_LISTA = 500


def prazo_pedido(texto: object) -> int:
    """O prazo escolhido na tela (?dias=14). Qualquer coisa fora de PRAZOS volta para o padrão: a tela nunca dá erro por isso."""
    if isinstance(texto, str) and texto.isascii() and texto.isdigit() and int(texto) in PRAZOS:
        return int(texto)
    return PRAZO_PADRAO


def _link_do_whatsapp(digitos: str | None) -> str | None:
    """'27988887766' -> 'https://wa.me/5527988887766' (abre a conversa no WhatsApp do professor; não manda nada sozinho)."""
    if not digitos or not digitos.isascii() or not digitos.isdigit() or len(digitos) not in (10, 11):
        return None
    return f"https://wa.me/55{digitos}"


def listar(conn: sqlite3.Connection, dias: int = PRAZO_PADRAO, agora: datetime | None = None) -> dict:
    """Os que estão há `dias` dias ou mais sem treinar, os mais sumidos primeiro, em duas listas.

    {"dias", "total_com_treino" (alunos com treino ativo: a base da conta),
     "total" e "alunos": quem já registrou treino e parou, "total_sem_registro" e "sem_registro": quem nunca registrou nenhum}.
    Cada aluno: {"id", "nome", "provisorio", "treino", "ultima" ('22/10/2026' ou None), "dias" (inteiro), "nunca" (bool: nenhuma
    marcação ainda; "dias" conta desde "desde"), "desde" (início do treino, só se nunca), "whatsapp", "whatsapp_link"}.
    As duas listas mostram no máximo `LIMITE_DA_LISTA` cada; os totais são os reais.
    """
    dia_de_hoje = ler_dia(hoje(agora))
    linhas = conn.execute(
        """
        SELECT a.id, a.nome, a.provisorio, a.whatsapp, t.nome AS treino, t.inicio, t.criado_em,
               (SELECT MAX(s.feita_em) FROM sessao s JOIN treino x ON x.id = s.treino_id WHERE x.aluno_id = a.id) AS ultima
        FROM aluno a
        JOIN treino t ON t.aluno_id = a.id AND t.ativo = 1
        WHERE a.provisorio = 1 OR a.situacao = 'A'
        """
    ).fetchall()

    com_registro = []
    sem_registro = []
    for linha in linhas:
        ultima = dia_local(linha["ultima"])
        referencia = ler_dia(ultima) if ultima else (ler_dia(linha["inicio"]) or ler_dia(dia_local(linha["criado_em"])))
        if referencia is None:
            continue
        parados = (dia_de_hoje - referencia).days
        if parados < dias:
            continue
        (sem_registro if ultima is None else com_registro).append(
            {
                "id": linha["id"],
                "nome": linha["nome"],
                "provisorio": bool(linha["provisorio"]),
                "treino": linha["treino"],
                "ultima": formatar_dia(ultima),
                "dias": parados,
                "nunca": ultima is None,
                "desde": formatar_dia(referencia.isoformat()) if ultima is None else None,
                "whatsapp": formatar_whatsapp(linha["whatsapp"]),
                "whatsapp_link": _link_do_whatsapp(linha["whatsapp"]),
            }
        )
    for lista in (com_registro, sem_registro):
        lista.sort(key=lambda a: (-a["dias"], a["nome"], a["id"]))
    return {
        "dias": dias,
        "total_com_treino": len(linhas),
        "total": len(com_registro),
        "alunos": com_registro[:LIMITE_DA_LISTA],
        "total_sem_registro": len(sem_registro),
        "sem_registro": sem_registro[:LIMITE_DA_LISTA],
    }
