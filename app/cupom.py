"""Cupom do treino para a impressora térmica (papel de 80 mm).

O desenho (tela "Impressão" do canvas) é um cupom em letras de máquina de escrever:

    ACADEMIA GLÓRIA FIT
    ------------------------------
    ALUNO: MARIANA COSTA
    TREINO: TREINO ABC 07/10/26
    DATA: 07/10/2026
    PROF.: ANA PAULA
    ------------------------------
    TREINO A
    A1 SUPINO RETO COM BARRA
       4 X 12                30 KG
    A2 CRUCIFIXO COM HALTERES
       4 X 12                10 KG
       INTERVALO: 1 MIN 30 S
       OBS: DESCER DEVAGAR
       BI-SET: FAÇA A1 E A2 SEGUIDOS
    3  TRICEPS NA POLIA
       3 X 12                25 KG

Aqui só se monta o CONTEÚDO (texto de cada linha). O desenho na tela e no papel fica em
app/templates/imprimir.html e app/static/imprimir.css. A conta das etiquetas (A1, A2, 3...)
é a mesma da ficha do aluno e da tela de montar treino.
"""

import sqlite3

from app import treinos
from app.alunos import data_local, etiquetas_dos_itens, texto_da_pausa

NOME_DA_ACADEMIA = "Academia Glória Fit"
TAMANHO_MAXIMO_DO_ENDERECO = 60  # cabe no cupom sem quebrar o aviso; endereço de app é curto

_NOME_DO_BLOCO = {2: "BI-SET", 3: "TRI-SET"}


def _dose(item: dict) -> str:
    """'4 X 12' (séries X repetições). Se faltar um dos dois, mostra só o que existe."""
    partes = [str(valor).strip() for valor in (item["series"], item["repeticoes"]) if valor and str(valor).strip()]
    return " X ".join(partes)


def _lista_com_e(etiquetas: list[str]) -> str:
    """['A1', 'A2'] -> 'A1 E A2'; ['A1', 'A2', 'A3'] -> 'A1, A2 E A3'."""
    if len(etiquetas) == 1:
        return etiquetas[0]
    return ", ".join(etiquetas[:-1]) + " E " + etiquetas[-1]


def _linhas_da_ficha(itens: list[dict]) -> list[dict]:
    """Cada linha: {"tipo": "exercicio" | "dose" | "detalhe" | "aviso", "etiqueta", "esquerda", "direita"}.

    "exercicio" = etiqueta + nome; "dose" = séries X repetições à esquerda e carga à direita;
    "detalhe" = o intervalo ("INTERVALO: 1 MIN 30 S") e a observação ("OBS: ...") do exercício, quando
    existem (os professores usam os dois, pedido do Thiago em 08/10/2026);
    "aviso" = o lembrete depois do último exercício de um bi-set/tri-set.
    """
    etiquetas = etiquetas_dos_itens(itens)
    linhas: list[dict] = []
    for posicao, item in enumerate(itens):
        linhas.append({"tipo": "exercicio", "etiqueta": etiquetas[posicao], "esquerda": item["exercicio"], "direita": ""})
        dose, carga = _dose(item), (item["carga"] or "").strip()
        if dose or carga:
            linhas.append({"tipo": "dose", "etiqueta": "", "esquerda": dose, "direita": carga})
        pausa = texto_da_pausa(item["pausa"])
        if pausa:
            linhas.append({"tipo": "detalhe", "etiqueta": "", "esquerda": f"INTERVALO: {pausa.upper()}", "direita": ""})
        observacao = (item["observacao"] or "").strip()
        if observacao:
            linhas.append({"tipo": "detalhe", "etiqueta": "", "esquerda": f"OBS: {observacao}", "direita": ""})

        bloco = item["bloco"]
        fim_do_bloco = bloco is not None and (posicao + 1 == len(itens) or itens[posicao + 1]["bloco"] != bloco)
        if fim_do_bloco:
            do_bloco = [etiquetas[i] for i, outro in enumerate(itens) if outro["bloco"] == bloco]
            if len(do_bloco) >= 2:
                nome = _NOME_DO_BLOCO.get(len(do_bloco), "SEQUÊNCIA")
                linhas.append(
                    {"tipo": "aviso", "etiqueta": "", "esquerda": f"{nome}: FAÇA {_lista_com_e(do_bloco)} SEGUIDOS", "direita": ""}
                )
    return linhas


class FichaInexistente(Exception):
    """Pediram para imprimir uma ficha que o treino não tem."""


def montar_cupom(
    conn: sqlite3.Connection, treino_id: int, endereco_do_app: str | None = None, ficha: int | None = None
) -> dict | None:
    """O conteúdo do cupom do treino, ou None se o treino não existe.

    `ficha`: a `ordem` da ficha a imprimir (1 = A, 2 = B...). Sem ela, o cupom leva todas as fichas (pedido do
    Thiago em 20/10/2026: escolher qual ficha imprimir, em vez de imprimir o treino inteiro). Se o treino não tem
    essa ficha, levanta FichaInexistente. "opcoes_de_ficha" lista as fichas com o que há para imprimir, para a tela
    mostrar os botões de escolha.

    `endereco_do_app`: se vier, o cupom termina com "ENTRE NO APP COM O SEU CPF:" e o endereço.
    Só deve ser passado quando o app do aluno já existir (hoje não existe).
    """
    treino = treinos.obter_treino(conn, treino_id)
    if treino is None:
        return None
    aluno = conn.execute("SELECT id, nome FROM aluno WHERE id = ?", (treino["aluno_id"],)).fetchone()
    endereco = (endereco_do_app or "").strip()[:TAMANHO_MAXIMO_DO_ENDERECO] or None
    com_exercicios = [f for f in treino["fichas"] if f["itens"]]
    if ficha is not None and ficha not in {f["ordem"] for f in treino["fichas"]}:
        raise FichaInexistente(ficha)
    a_imprimir = treino["fichas"] if ficha is None else [f for f in treino["fichas"] if f["ordem"] == ficha]
    # Pedido do Thiago em 20/10/2026: com uma ficha só, o cabeçalho leva o nome DELA ("TREINO A"), não o nome do treino
    # inteiro ("TREINO ABC"), e o nome da ficha não se repete embaixo. Com todas as fichas, fica como era.
    uma_ficha_so = ficha is not None
    return {
        "academia": NOME_DA_ACADEMIA,
        "aluno_id": aluno["id"],
        "cabecalho": [
            ("ALUNO", aluno["nome"]),
            ("TREINO", a_imprimir[0]["nome"] if uma_ficha_so else treino["nome"]),
            ("DATA", data_local(treino["criado_em"])),
            ("PROF.", treino["montado_por"]),
        ],
        "fichas": [{"nome": f["nome"], "linhas": _linhas_da_ficha(f["itens"])} for f in a_imprimir],
        "treino_id": treino_id,
        "ficha_escolhida": ficha,  # None = todas
        "mostrar_nome_da_ficha": not uma_ficha_so,  # com uma ficha só, o nome já está no cabeçalho
        "opcoes_de_ficha": [{"ordem": f["ordem"], "nome": f["nome"]} for f in com_exercicios],
        "endereco_do_app": endereco,
    }
