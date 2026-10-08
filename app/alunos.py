"""Alunos: busca, ficha (com os treinos salvos) e correção do WhatsApp.

Os alunos chegam da cópia diária do Data4U (app/importar_alunos.py) ou serão
cadastrados como provisórios (app/provisorios.py). Aqui só lemos e, no caso do
WhatsApp, corrigimos o número.
"""

import re
import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app import treinos
from app.exercicios import _escapar_like
from app.texto import normalizar
from app.treinos import AlunoNaoEncontrado

LIMITE_PADRAO = 50
LIMITE_MAXIMO = 200
TAMANHO_MAXIMO_BUSCA = 100

# Letra da situação do aluno no Data4U (tabela PESSOA_STATUS) -> nome mostrado na
# tela. Os significados foram conferidos em 21/09/2026 cruzando os dados (doc 15
# do projeto): A ativo; T trancado; P plano vencido, na carência; D desistente;
# I cadastro que nunca virou aluno; C cancelado.
SITUACOES = {
    "A": "Ativo",
    "T": "Trancado",
    "P": "Pendente",
    "D": "Desistente",
    "I": "Inativo",
    "C": "Cancelado",
}

# O banco guarda as datas em UTC (datetime('now')). Na tela, hora de Brasília:
# uma ficha montada às 23h30 de 06/10 não pode aparecer como 07/10.
FUSO_DA_ACADEMIA = ZoneInfo("America/Sao_Paulo")

# Só estes caracteres são aceitos ao digitar um WhatsApp: números e os enfeites comuns.
# [0-9] e não \d: \d também aceita algarismos de outros alfabetos (como "２７" em largura
# total), que o banco recusaria depois com erro 500.
_SO_NUMERO_E_ENFEITE = re.compile(r"[0-9\s().\-]+")


class WhatsappInvalido(Exception):
    """O número digitado não serve. A mensagem já está pronta para mostrar na tela."""


# ------------------------------------------------------------------ formatação


def formatar_cpf(cpf: str | None) -> str | None:
    """'12345678909' -> '123.456.789-09'. Sem CPF cadastrado, devolve None."""
    if not cpf:
        return None
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def formatar_whatsapp(digitos: str | None) -> str | None:
    """'27988887766' -> '(27) 98888-7766'; com 10 dígitos: '(27) 3888-7766'."""
    if not digitos:
        return None
    return f"({digitos[:2]}) {digitos[2:-4]}-{digitos[-4:]}"


def data_local(texto_utc: str | None) -> str | None:
    """'2026-10-07 02:30:00' (UTC, como o banco guarda) -> '06/10/2026' (Brasília)."""
    if not texto_utc:
        return None
    momento = datetime.strptime(texto_utc, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return momento.astimezone(FUSO_DA_ACADEMIA).strftime("%d/%m/%Y")


# ------------------------------------------------------------------ busca


def buscar_alunos(conn: sqlite3.Connection, texto: str = "", limite: int = LIMITE_PADRAO) -> dict:
    """Busca alunos por nome, CPF ou matrícula.

    - Só números (com ou sem pontos e traço): procura esses números no CPF e também
      uma matrícula (número do Data4U) igual a eles.
    - Senão: cada palavra precisa aparecer no nome, em qualquer ordem, sem
      diferenciar maiúscula nem acento ("joao silva" acha "SILVA, João").
    - Com texto: matrícula igual ao número digitado primeiro; depois quem está
      em uso (ativo, trancado, pendente ou provisório), depois os demais; dentro de
      cada grupo, ordem alfabética.
    - Sem texto: quem tem treino montado no app (o mais recente primeiro), depois os
      provisórios sem treino (o mais recente primeiro), depois os demais (em uso
      antes), em ordem alfabética. O histórico copiado do Data4U NÃO entra nessa
      conta (senão os 3 mil alunos com treinos antigos empurrariam para o fim o aluno
      que acabou de se matricular), mas aparece na coluna "Último treino".

    Devolve {"total": quantos existem, "alunos": até `limite` deles}. Não devolve
    o CPF (a lista não precisa dele; ele aparece só na ficha).
    """
    limite = max(1, min(int(limite), LIMITE_MAXIMO))
    texto = texto[:TAMANHO_MAXIMO_BUSCA]

    # SEGURANÇA: o que foi digitado vai sempre nos "?" (nunca dentro do SQL).
    condicoes: list[str] = []
    parametros_onde: list = []
    parametros_ordem: list = []
    so_numero = re.fullmatch(r"[0-9\s.\-]+", texto.strip()) is not None
    matricula_digitada = None
    if so_numero:
        digitos = re.sub(r"[^0-9]", "", texto)
        if digitos:
            alternativas = ["a.cpf LIKE ?"]
            parametros_onde.append(f"%{digitos}%")  # só dígitos: não há curinga a escapar
            # Matrícula é um número pequeno. O limite de 9 dígitos evita passar ao SQLite
            # um inteiro grande demais (o SQLite só guarda até 64 bits).
            if len(digitos) <= 9:
                matricula_digitada = int(digitos)
                alternativas.append("a.data4u_id = ?")
                parametros_onde.append(matricula_digitada)
            condicoes.append("(" + " OR ".join(alternativas) + ")")
    else:
        for termo in normalizar(texto).split():
            condicoes.append("sem_acento(a.nome) LIKE ? ESCAPE '\\'")
            parametros_onde.append(f"%{_escapar_like(termo)}%")
    onde = " AND ".join(condicoes) if condicoes else "1 = 1"

    em_uso = "CASE WHEN a.provisorio = 1 OR a.situacao IN ('A', 'T', 'P') THEN 0 ELSE 1 END"
    if condicoes:
        partes_da_ordem = []
        if matricula_digitada is not None:
            partes_da_ordem.append("CASE WHEN a.data4u_id = ? THEN 0 ELSE 1 END")
            parametros_ordem.append(matricula_digitada)
        partes_da_ordem += [em_uso, "sem_acento(a.nome)", "a.id"]
    else:
        partes_da_ordem = [
            "CASE WHEN ta.id IS NOT NULL THEN 0 WHEN a.provisorio = 1 THEN 1 ELSE 2 END",
            "CASE WHEN ta.id IS NOT NULL THEN ta.criado_em WHEN a.provisorio = 1 THEN a.criado_em END DESC",
            em_uso,
            "sem_acento(a.nome)",
            "a.id",
        ]
    ordem = ", ".join(partes_da_ordem)

    total = conn.execute(f"SELECT COUNT(*) FROM aluno a WHERE {onde}", parametros_onde).fetchone()[0]
    linhas = conn.execute(
        f"""
        SELECT a.id, a.nome, a.provisorio, a.data4u_id, a.situacao,
               t.nome AS ultimo_treino, t.criado_em AS treino_em
        FROM aluno a
        LEFT JOIN treino t ON t.id = (
            SELECT id FROM treino WHERE aluno_id = a.id ORDER BY criado_em DESC, id DESC LIMIT 1
        )
        LEFT JOIN treino ta ON ta.id = (
            SELECT id FROM treino WHERE aluno_id = a.id AND origem = 'app' ORDER BY criado_em DESC, id DESC LIMIT 1
        )
        WHERE {onde}
        ORDER BY {ordem}
        LIMIT ?
        """,
        [*parametros_onde, *parametros_ordem, limite],
    ).fetchall()
    alunos = [
        {
            "id": linha["id"],
            "nome": linha["nome"],
            "provisorio": bool(linha["provisorio"]),
            "matricula": linha["data4u_id"],
            "situacao": linha["situacao"],
            "situacao_nome": SITUACOES.get(linha["situacao"]),
            "ultimo_treino": linha["ultimo_treino"],
            "atualizado_em": data_local(linha["treino_em"]),
        }
        for linha in linhas
    ]
    return {"total": total, "alunos": alunos}


# ------------------------------------------------------------------ ficha


def etiquetas_dos_itens(itens: list[dict]) -> list[str]:
    """A1, A2 para exercícios de bi-set/tri-set; 3, 4, 5... (posição) para os sozinhos.

    Mesma regra da tela de montar (treino_modelo.js, função `etiquetas`).
    """
    etiquetas = []
    letras_por_bloco: dict[int, str] = {}
    posicao_no_bloco: dict[int, int] = {}
    for posicao, item in enumerate(itens, start=1):
        bloco = item["bloco"]
        if bloco is None:
            etiquetas.append(str(posicao))
            continue
        if bloco not in letras_por_bloco:
            letras_por_bloco[bloco] = chr(ord("A") + len(letras_por_bloco) % 26)
        posicao_no_bloco[bloco] = posicao_no_bloco.get(bloco, 0) + 1
        etiquetas.append(f"{letras_por_bloco[bloco]}{posicao_no_bloco[bloco]}")
    return etiquetas


def dose_do_item(item: dict) -> str:
    """'4 × 12' (séries × repetições). Se faltar um dos dois, mostra só o que existe; se faltar tudo, ''."""
    partes = [str(valor).strip() for valor in (item["series"], item["repeticoes"]) if valor and str(valor).strip()]
    return " × ".join(partes)


def texto_da_pausa(segundos: int | None) -> str:
    """90 -> '1 min 30 s'; 60 -> '1 min'; 30 -> '30 s'; 0 ou vazio -> '' (sem pausa informada)."""
    if not segundos:
        return ""
    horas, resto = divmod(segundos, 3600)
    minutos, segs = divmod(resto, 60)
    partes = [f"{horas} h" if horas else "", f"{minutos} min" if minutos else "", f"{segs} s" if segs else ""]
    return " ".join(p for p in partes if p)


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _resumo_da_ficha(itens: list[dict]) -> str:
    """'5 exercícios, 1 bi-set' (mesmo texto da tela de montar)."""
    partes = [_plural(len(itens), "exercício", "exercícios")]
    tamanhos: dict[int, int] = {}
    for item in itens:
        if item["bloco"] is not None:
            tamanhos[item["bloco"]] = tamanhos.get(item["bloco"], 0) + 1
    bis = sum(1 for t in tamanhos.values() if t == 2)
    tris = sum(1 for t in tamanhos.values() if t == 3)
    if bis:
        partes.append(_plural(bis, "bi-set", "bi-sets"))
    if tris:
        partes.append(_plural(tris, "tri-set", "tri-sets"))
    return ", ".join(partes)


def obter_ficha(conn: sqlite3.Connection, aluno_id: int) -> dict | None:
    """O aluno com seus treinos salvos (mais novo primeiro), ou None se não existe."""
    aluno = conn.execute(
        "SELECT id, nome, cpf, whatsapp, whatsapp_corrigido_no_app, data4u_id, situacao, provisorio"
        " FROM aluno WHERE id = ?",
        (aluno_id,),
    ).fetchone()
    if aluno is None:
        return None

    ids = [
        linha[0]
        for linha in conn.execute(
            "SELECT id FROM treino WHERE aluno_id = ? ORDER BY criado_em DESC, id DESC", (aluno_id,)
        )
    ]
    lista_de_treinos = []
    for treino_id in ids:
        treino = treinos.obter_treino(conn, treino_id)
        fichas = []
        for ficha in treino["fichas"]:
            itens = ficha["itens"]
            etiquetas = etiquetas_dos_itens(itens)
            fichas.append(
                {
                    "nome": ficha["nome"],
                    "resumo": _resumo_da_ficha(itens),
                    "itens": [
                        {
                            **item,
                            "etiqueta": etiquetas[i],
                            "dose": dose_do_item(item),
                            "pausa_texto": texto_da_pausa(item["pausa"]),
                        }
                        for i, item in enumerate(itens)
                    ],
                }
            )
        lista_de_treinos.append(
            {
                "id": treino["id"],
                "nome": treino["nome"],
                "montado_por": treino["montado_por"],
                "do_data4u": treino["origem"] == "data4u",
                "criado_em": data_local(treino["criado_em"]),
                "fichas": fichas,
            }
        )

    return {
        "id": aluno["id"],
        "nome": aluno["nome"],
        "cpf": formatar_cpf(aluno["cpf"]),
        "whatsapp": formatar_whatsapp(aluno["whatsapp"]),
        "whatsapp_corrigido_no_app": bool(aluno["whatsapp_corrigido_no_app"]),
        "matricula": aluno["data4u_id"],
        "situacao": aluno["situacao"],
        "situacao_nome": SITUACOES.get(aluno["situacao"]),
        "provisorio": bool(aluno["provisorio"]),
        "treinos": lista_de_treinos,
    }


# ------------------------------------------------------------------ WhatsApp


def validar_whatsapp(valor) -> str:
    """Devolve só os dígitos do número (10 ou 11, com DDD) ou levanta WhatsappInvalido."""
    exemplo = "Digite com DDD, por exemplo (27) 98888-7766."
    if not isinstance(valor, str) or not valor.strip():
        raise WhatsappInvalido("Digite o número do WhatsApp. " + exemplo)
    if not _SO_NUMERO_E_ENFEITE.fullmatch(valor):
        raise WhatsappInvalido("O número só pode ter algarismos, espaço, parênteses, ponto e hífen (sem +55). " + exemplo)
    digitos = re.sub(r"[^0-9]", "", valor)
    if len(digitos) in (8, 9):
        raise WhatsappInvalido("Parece faltar o DDD. " + exemplo)
    if len(digitos) not in (10, 11):
        raise WhatsappInvalido(
            f"O número precisa ter 10 ou 11 algarismos com o DDD; este tem {len(digitos)}. " + exemplo
        )
    if int(digitos[:2]) < 11:
        raise WhatsappInvalido("O DDD é inválido (vai de 11 a 99). " + exemplo)
    return digitos


def salvar_whatsapp(conn: sqlite3.Connection, aluno_id: int, valor) -> str:
    """Corrige o WhatsApp do aluno no app. Devolve o número formatado.

    Marca `whatsapp_corrigido_no_app`: a cópia diária do Data4U não pode mais
    sobrescrever este número (decisão do Thiago em 07/10/2026).
    """
    digitos = validar_whatsapp(valor)
    with conn:
        alterados = conn.execute(
            "UPDATE aluno SET whatsapp = ?, whatsapp_corrigido_no_app = 1 WHERE id = ?",
            (digitos, aluno_id),
        ).rowcount
    if alterados == 0:
        raise AlunoNaoEncontrado(aluno_id)
    return formatar_whatsapp(digitos)
