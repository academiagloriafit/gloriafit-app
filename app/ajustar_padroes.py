"""Ajustes e treinos padrão novos, de vários de uma vez, com UMA senha de administrador (Thiago, 14/10/2026).

Os padrões são fixos e travados por senha de administrador (app/administrador.py). Trocar um deles pela tela
são DUAS senhas (excluir e guardar de novo); para 11 treinos seriam 22. Este comando faz um LOTE inteiro de uma vez,
com UMA senha, digitada pelo Thiago no terminal do servidor (o Claude nunca digita nem lê a senha).

Lotes (cada um foi decidido pelo Thiago, item por item; a lista está no doc do projeto):
- `revisao`: a revisão dos 12 treinos de Homem e Mulher (já aplicada em produção em 14/10/2026).
- `filas`: o Treino 1 das filas Adolescente (o INICIANTE SUP / INF, arrumado e colocado na fila), Gestante e
  Grupos de risco (estes dois são treinos novos, copiados do Data4U).

Uso, no terminal do contêiner do app (sem `--lote`, vale o lote `filas`):
    python -m app.ajustar_padroes --simular     # mostra o que mudaria; não pede senha e não grava nada
    python -m app.ajustar_padroes               # confere tudo, pede a senha, faz a cópia de segurança e grava
    python -m app.ajustar_padroes --simular --detalhes    # lista cada mudança, linha por linha
    python -m app.ajustar_padroes --lote revisao --simular    # o lote antigo (só para conferir; já foi aplicado)

Garantias:
- TUDO OU NADA: se qualquer linha não estiver como o lote esperava (alguém mexeu no padrão depois), nada é gravado.
- CÓPIA DE SEGURANÇA antes de gravar (a mesma de `python -m app.backup`, em /backups).
- Cada linha trocada é conferida pela posição E pelo nome do exercício, e o valor de antes tem que ser o esperado.
- O treino ajustado ou novo passa pela mesma conferência de um treino de verdade (limites de tamanho, exercício ativo,
  fila e número livres).
- Pode rodar de novo: o que já foi feito é reconhecido ("já estava ajustado") e não muda.
- Id, professor e "enchimento" de cada padrão existente continuam iguais. Mudam só o que o lote diz: o texto das linhas,
  o nome do treino e das fichas e, no `filas`, o lugar do INICIANTE (solto → Adolescente · Treino 1).
"""

import argparse
import getpass
import json
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

from app import administrador, db
from app.backup import BackupFalhou, fazer_backup
from app.filas import texto_da_posicao, validar_posicao
from app.texto import nome_para_exibir, normalizar
from app.treinos import (
    LIMITE_NOME_TREINO,
    LIMITE_QUEM_MONTOU,
    validar_fichas,
    validar_texto,
)

PROFESSOR_DOS_PADROES = "Academia Glória Fit"  # o mesmo dos 12 padrões de Homem e Mulher

CAMPOS = ("series", "repeticoes", "carga", "observacao")
_ROTULO = {"series": "séries", "repeticoes": "repetições", "carga": "carga", "observacao": "observação"}
_CAMPOS_DO_ITEM = ("exercicio_id", "series", "repeticoes", "carga", "pausa", "observacao", "bloco")


class Divergencia(Exception):
    """O padrão não está como a revisão esperava (ou o resultado não passaria na conferência). Nada é gravado."""


# ------------------------------------------------------------------ o plano


@dataclass(frozen=True)
class Linha:
    """Troca o texto de campos de UMA linha (exercício) de uma ficha.

    `posicao` conta de 1, na ordem da ficha. `exercicio` é o nome como aparece na tela (serve só para ter certeza de
    que é a linha certa). `trocas` = ((campo, texto de antes, texto de depois), ...); texto vazio = campo em branco.
    """

    ficha: str
    posicao: int
    exercicio: str
    trocas: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True)
class Limpeza:
    """Apaga o mesmo texto de um campo em TODAS as linhas do treino (ex.: a palavra MODERADO na carga).
    Confere que existem exatamente `quantas` linhas com esse texto."""

    campo: str
    texto: str
    quantas: int


@dataclass(frozen=True)
class Remocao:
    """Tira uma linha repetida de uma ficha. Confere o nome do exercício e quantas linhas a ficha terá depois."""

    ficha: str
    posicao: int
    exercicio: str
    itens_depois: int


@dataclass(frozen=True)
class Plano:
    modelo_id: int
    nome_atual: str | None = None  # só quando o treino muda de nome
    novo_nome: str | None = None
    linhas: tuple[Linha, ...] = ()
    limpezas: tuple[Limpeza, ...] = ()
    remocoes: tuple[Remocao, ...] = ()  # no máximo uma por ficha
    fichas_renomeadas: tuple[tuple[str, str], ...] = ()  # (nome antes, nome depois)
    fila: str | None = None  # só quando o treino solto entra numa fila: o nome da fila (ex.: "Adolescente")...
    numero: int | None = None  # ... e o número dele nela


@dataclass(frozen=True)
class Item:
    """Uma linha de um treino NOVO. `exercicio` é o nome como aparece na tela; ele tem que existir UMA vez na lista ativa."""

    exercicio: str
    series: str = ""
    repeticoes: str = ""
    observacao: str = ""


@dataclass(frozen=True)
class FichaNova:
    nome: str
    itens: tuple[Item, ...]


@dataclass(frozen=True)
class Novo:
    """Um treino padrão NOVO, já no lugar dele numa fila (ex.: Gestante · Treino 1). Sem carga e sem intervalo, como os outros."""

    nome: str
    fila: str
    numero: int
    fichas: tuple[FichaNova, ...]
    montado_por: str = PROFESSOR_DOS_PADROES


# Os ids são os da produção (conferidos em 14/10/2026): Homem 1 a 6 = 4, 7, 9, 11, 14, 15; Mulher 1 a 6 = 5, 6, 8, 10, 12, 13.
# O Homem 5 (id 14) não muda.
PLANOS: tuple[Plano, ...] = (
    Plano(
        4,
        nome_atual="TREINO ABC HOMEM BÁSICO",
        novo_nome="TREINO HOMEM 1",
        limpezas=(Limpeza("carga", "MODERADO", 27),),
    ),
    Plano(
        5,
        nome_atual="TREINO ABC MULHER BÁSICO",
        novo_nome="TREINO MULHER 1",
        linhas=(Linha("C GLÚTEO", 9, "PANTURRILHA EM PÉ", (("series", "", "3"), ("repeticoes", "", "20"))),),
    ),
    Plano(
        6,
        linhas=(Linha("QUADRÍCEPS", 1, "MOBILIDADE 90/90 + PRANCHA", (("repeticoes", '15/30"!', '15/30"'),)),),
    ),
    Plano(
        7,
        linhas=(Linha("A - INF", 1, "AQUECIMENTO E MOBILIDADE", (("repeticoes", "", "10"),)),),
    ),
    Plano(
        8,
        linhas=(
            Linha("GLUTEOS", 8, "ESTEIRA OU BIKE", (("series", "30", "1"), ("repeticoes", "MINUTOS", "30 MINUTOS"))),
            Linha("QUADRÍCEPS", 8, "ESTEIRA OU BIKE", (("series", "30", "1"), ("repeticoes", "MINUTOS", "30 MINUTOS"))),
        ),
        fichas_renomeadas=(("PEITO", "PEITO/OMB/TRI"), ("DORSAL", "DORSAL/BICEPS")),
    ),
    Plano(
        9,
        linhas=(
            Linha("B-INFERIORES", 3, "CADEIRA EXTENSORA + AGACH. ISO", (("repeticoes", "15/15SEGUND", "15/15 seg"),)),
            Linha("D-ABDOMINAIS", 3, "ABDOMINAL BICICLETA", (("repeticoes", "30alternand", "30 alterna"),)),
        ),
        fichas_renomeadas=(("A-PEITORAL", "A-PEITO/OMB/BIC"), ("C-DORSAL", "C-DORSAL/TRI")),
    ),
    Plano(
        10,
        linhas=(Linha("SUPERIORES 1 B", 9, "CARDIO", (("series", "", "1"), ("observacao", "20-30MIN", ""))),),
    ),
    Plano(
        11,
        linhas=(
            Linha("SEGUNDA", 1, "ALONGAMENTO DE PEITORAL + MANGUITO ABDUZIDO", (("repeticoes", "", "20"),)),
            Linha("QUINTA", 1, "MOBILIDADE", (("repeticoes", "", "20"),)),
        ),
    ),
    Plano(
        12,
        limpezas=(Limpeza("observacao", "MODERADO", 7),),
    ),
    Plano(
        13,
        remocoes=(Remocao("A POST", 7, "Cadeira flexora", 7),),
        fichas_renomeadas=(("A POST", "A PERNAS/POST"),),
    ),
    Plano(
        15,
        linhas=(
            Linha("SEGUNDA - A", 3, "MOBILIDADE", (("series", "", "1-2"), ("repeticoes", "", "10"))),
            Linha("SEGUNDA - A", 10, "ALONGAMENTO", (("series", "", "1-2"), ("repeticoes", "", "20s"))),
            Linha("TERÇA - B", 1, "ABDOMINAIS: BIC.+ REMADOR + BIC.", (("series", "", "3"), ("repeticoes", "", "20"))),
            Linha("QUINTA - C", 8, "ALONGAMENTO", (("series", "", "1-2"), ("repeticoes", "10-15", "20s"))),
            Linha("SEXTA - D", 1, "ABDOMINAL CANIVETE + REMADOR", (("series", "", "3"), ("repeticoes", "", "20"))),
            Linha("SEXTA - D", 2, "ESCALADA", (("series", "", "3"), ("repeticoes", "", "30"))),
        ),
    ),
)


# Lote `filas` (Thiago, 14/10/2026). O padrão solto id 2 (o "INICIANTE SUP / INF" do Data4U) vira o Adolescente · Treino 1:
# arrumado como nas outras revisões (sem "MODERADO"; as linhas sem séries/repetições ou com "1 x 20 MINUTOS" no tríceps
# ficam 3 x 15; os dois "5' ESTEIRA" ficam em branco, os 5 minutos já estão no nome).
PLANOS_FILAS: tuple[Plano, ...] = (
    Plano(
        2,
        nome_atual="TREINO INICIANTE SUP / INF",
        novo_nome="TREINO ADOLESCENTE 1",
        fila="Adolescente",
        numero=1,
        linhas=(
            Linha("A INFERIOR", 9, "ABDOMINAL RETO", (("series", "", "3"), ("repeticoes", "", "15"))),
            Linha("B SUPERIOR", 1, "MANGUITO EXTERNO", (("series", "", "3"), ("repeticoes", "", "15"))),
            Linha("B SUPERIOR", 8, "TRÍCEPS MÁQUINA", (("series", "1", "3"), ("repeticoes", "20 MINUTOS", "15"))),
            Linha("B SUPERIOR", 9, "BICEPS MAQUINA", (("series", "", "3"), ("repeticoes", "", "15"))),
        ),
        limpezas=(Limpeza("carga", "MODERADO", 15),),
    ),
)

NOVOS: tuple[Novo, ...] = (
    # Gestante · Treino 1: o "TREINO GESTANTE A E B" do Data4U (treino 3081, 13/04/2023). Sem os pesos de aluno; 7 exercícios apagados do Data4U trocados pelos parecidos do app (aprovado pelo Thiago em 14/10/2026).
    Novo(
        "TREINO GESTANTE 1",
        "Gestante",
        1,
        (
            FichaNova(
                "A INFERIOR",
                (
                    Item("MOBILIDADE DE QUADRIL", "3", "20"),
                    Item("LEG HORIZONTAL", "3", "20"),
                    Item("CADEIRA EXTENSORA", "3", "20"),
                    Item("Cadeira flexora", "3", "20"),
                    Item("CADEIRA ABDUTORA", "3", "20"),
                    Item("ELEVAÇÃO PELVICA", "3", "30"),
                    Item("CADEIRA ADUTORA", "3", "20"),
                    Item("PANTURRILHA EM PÉ", "3", "30"),
                    Item("ESTEIRA", "1", "10 A 20 MIN"),
                ),
            ),
            FichaNova(
                "B SUPERIOR",
                (
                    Item("MANGUITO EXTERNO", "2", "20"),
                    Item("VOADOR", "3", "20"),
                    Item("SUPINO MAQUINA", "3", "20"),
                    Item("REMADA MAQ. NEUTRA", "3", "20"),
                    Item("REMADA MAQUINA ABERTA", "3", "20"),
                    Item("PULLEY DE FRENTE", "3", "20"),
                    Item("ELEVAÇÃO CONJUGADA", "3", "20"),
                    Item("ROSCA POLIA", "3", "20"),
                    Item("TRÍCEPS POLIA", "3", "20"),
                    Item("ESTEIRA", "1", "10 A 20 MIN"),
                ),
            ),
        ),
    ),
    # Grupos de risco · Treino 1: o "HIPERTENSÃO CONTROLADA" do Data4U (treino 6477, 03/07/2026), igual ao original (aprovado pelo Thiago em 14/10/2026).
    Novo(
        "TREINO GRUPOS DE RISCO 1",
        "Grupos de risco",
        1,
        (
            FichaNova(
                "FULL BODY A",
                (
                    Item("MOBILIDADE", "1-2", "5-8"),
                    Item("Caminhada na esteira", "2", "", "8-12MIN"),
                    Item("LEG HORIZONTAL", "2", "10-15"),
                    Item("REMADA MÁQUINA", "2", "10-15"),
                    Item("SUPINO MAQUINA", "2", "10-15"),
                    Item("Mesa flexora", "2", "12-15"),
                    Item("Elevação panturrilhas em pé", "2", "12-20"),
                    Item("Abdominal Dead Bug", "2", "6-10"),
                    Item("ALONGAMENTO", "1", "", "15-25S"),
                ),
            ),
            FichaNova(
                "FULL BODY B",
                (
                    Item("MOBILIDADE", "1-2"),
                    Item("BIKE", "", "", "8-12 MIN"),
                    Item("Puxada alta", "2", "10-15"),
                    Item("AGACHAMENTO GOBLET", "2", "10-15"),
                    Item("DESENVOLVIMENTO COM HALTER", "2", "10-15"),
                    Item("CADEIRA ABDUTORA", "2", "12-20"),
                    Item("Caminhada na esteira", "", "", "5MIN"),
                    Item("ALONGAMENTO", "1", "15-20s"),
                ),
            ),
            FichaNova(
                "FULL BODY C",
                (
                    Item("LEG PRESS 45º", "2", "10-15"),
                    Item("REMADA MÁQUINA", "2", "10-15"),
                    Item("Puxada alta", "2", "10-15"),
                    Item("AGACHAMENTO EDUCATIVO", "2", "10-15"),
                    Item("MOBILIDADE", "", "", "5-8 MIN"),
                    Item("Desenvolvimento Pallof Press", "2", "8-12"),
                    Item("ALONGAMENTO", "1", "15-25s"),
                ),
            ),
        ),
    ),
)


@dataclass(frozen=True)
class Lote:
    descricao: str
    planos: tuple[Plano, ...] = ()
    novos: tuple[Novo, ...] = ()


LOTES: dict[str, Lote] = {
    "revisao": Lote("revisão dos 12 treinos de Homem e Mulher (14/10/2026; já aplicada em produção)", planos=PLANOS),
    "filas": Lote("Treino 1 das filas Adolescente, Gestante e Grupos de risco (14/10/2026)", planos=PLANOS_FILAS, novos=NOVOS),
}
LOTE_PADRAO = "filas"


# ------------------------------------------------------------------ calcular o que muda


@dataclass
class Resultado:
    modelo_id: int | None  # None = treino novo, que ainda vai ser criado
    nome: str  # o nome que o padrão tem agora
    novo_nome: str
    conteudo: dict  # o conteúdo novo ({"fichas": [...]}); igual ao de hoje quando não há o que mudar
    mudancas: list[str]  # o que ainda falta fazer, uma frase por mudança (vazio = já estava ajustado)
    fila_id: int | None = None  # o lugar do padrão numa fila (o de hoje, ou o novo)
    numero: int | None = None
    montado_por: str | None = None  # só nos treinos novos
    detalhes: list[str] = field(default_factory=list)  # só nos treinos novos: uma frase por linha (aparece com --detalhes)


def _texto(valor) -> str:
    return valor or ""


def _mesmo_nome(a: str | None, b: str | None) -> bool:
    """Compara nomes de treino sem ligar para maiúsculas, acento ou espaço repetido (o Data4U tem "TREINO  INICIANTE")."""
    return " ".join(normalizar(a).split()) == " ".join(normalizar(b).split())


def _nomes_dos_exercicios(conn: sqlite3.Connection, fichas: list[dict]) -> dict[int, str]:
    ids = sorted({item["exercicio_id"] for ficha in fichas for item in ficha["itens"]})
    if not ids:
        return {}
    marcas = ",".join("?" * len(ids))
    return {
        linha["id"]: nome_para_exibir(linha["nome"])
        for linha in conn.execute(f"SELECT id, nome FROM exercicio WHERE id IN ({marcas})", ids)
    }


def calcular(conn: sqlite3.Connection, plano: Plano) -> Resultado:
    """Aplica o plano numa cópia do padrão (em memória). Levanta Divergencia se algo não bater."""
    linha_do_banco = conn.execute(
        "SELECT nome, conteudo, fila_id, numero FROM modelo_treino WHERE id = ?", (plano.modelo_id,)
    ).fetchone()
    if linha_do_banco is None:
        raise Divergencia(f"O treino padrão de id {plano.modelo_id} não existe.")
    nome_hoje = linha_do_banco["nome"]
    fila_id, numero = linha_do_banco["fila_id"], linha_do_banco["numero"]
    fichas = json.loads(linha_do_banco["conteudo"])["fichas"]
    exercicios = _nomes_dos_exercicios(conn, fichas)
    onde = f"id {plano.modelo_id} ({nome_hoje})"
    mudancas: list[str] = []

    apelidos = dict(plano.fichas_renomeadas)  # nome antes -> nome depois; a ficha vale por qualquer um dos dois

    def achar_ficha(nome: str) -> dict:
        for ficha in fichas:
            if ficha["nome"] in (nome, apelidos.get(nome)):
                return ficha
        raise Divergencia(f'{onde}: não achei a ficha "{nome}".')

    def conferir_exercicio(item: dict, esperado: str, lugar: str) -> None:
        achado = exercicios.get(item["exercicio_id"], "")
        if normalizar(achado) != normalizar(esperado):
            raise Divergencia(f'{lugar}: esperava o exercício "{esperado}" e achei "{achado}".')

    # 1. o nome do treino
    novo_nome = nome_hoje
    if plano.novo_nome is not None:
        if _mesmo_nome(nome_hoje, plano.nome_atual):
            novo_nome = plano.novo_nome
            mudancas.append(f'nome do treino: "{" ".join(nome_hoje.split())}" → "{novo_nome}"')
        elif nome_hoje != plano.novo_nome:
            raise Divergencia(f'{onde}: esperava o nome "{plano.nome_atual}".')

    # 1b. o lugar numa fila (só um treino solto entra; um que já está no lugar certo não muda)
    if plano.fila is not None:
        fila = _achar_fila(conn, plano.fila, onde)
        if (fila_id, numero) == (None, None):
            problemas: list[str] = []
            conflitos: list[str] = []
            validar_posicao(conn, {"fila_id": fila["id"], "numero": plano.numero}, problemas, conflitos)
            if problemas or conflitos:
                raise Divergencia(f"{onde}: não dá para colocar na fila {plano.fila}, Treino {plano.numero}: " + " ".join(problemas + conflitos))
            fila_id, numero = fila["id"], plano.numero
            mudancas.append(f"lugar: solto → {texto_da_posicao(fila['nome'], numero)}")
        elif (fila_id, numero) != (fila["id"], plano.numero):
            raise Divergencia(f"{onde}: esperava o treino solto ou em {texto_da_posicao(fila['nome'], plano.numero)}.")

    # 2. texto de campos de uma linha
    for linha in plano.linhas:
        ficha = achar_ficha(linha.ficha)
        lugar = f'{onde}, ficha "{linha.ficha}", linha {linha.posicao}'
        if not 1 <= linha.posicao <= len(ficha["itens"]):
            raise Divergencia(f"{lugar}: a ficha não tem essa linha.")
        item = ficha["itens"][linha.posicao - 1]
        conferir_exercicio(item, linha.exercicio, lugar)
        for campo, antes, depois in linha.trocas:
            atual = _texto(item.get(campo))
            if atual == antes:
                item[campo] = depois or None
                mudancas.append(f'{linha.ficha} · linha {linha.posicao} ({linha.exercicio}): {_ROTULO[campo]} "{antes}" → "{depois}"')
            elif atual != depois:
                raise Divergencia(f'{lugar}: {_ROTULO[campo]} era para estar "{antes}" e está "{atual}".')

    # 3. o mesmo texto apagado de todas as linhas
    for limpeza in plano.limpezas:
        donos = [item for ficha in fichas for item in ficha["itens"] if _texto(item.get(limpeza.campo)) == limpeza.texto]
        if len(donos) == limpeza.quantas:
            for item in donos:
                item[limpeza.campo] = None
            mudancas.append(f'{_ROTULO[limpeza.campo]} "{limpeza.texto}" apagada de {limpeza.quantas} linhas')
        elif donos:
            raise Divergencia(
                f'{onde}: esperava {limpeza.quantas} linhas com {_ROTULO[limpeza.campo]} "{limpeza.texto}" e achei {len(donos)}.'
            )

    # 4. linha repetida
    for remocao in plano.remocoes:
        ficha = achar_ficha(remocao.ficha)
        lugar = f'{onde}, ficha "{remocao.ficha}", linha {remocao.posicao}'
        quantos = len(ficha["itens"])
        if quantos == remocao.itens_depois:
            continue  # já foi tirada
        if quantos != remocao.itens_depois + 1 or not 1 <= remocao.posicao <= quantos:
            raise Divergencia(f"{lugar}: a ficha tem {quantos} linhas; esperava {remocao.itens_depois + 1}.")
        conferir_exercicio(ficha["itens"][remocao.posicao - 1], remocao.exercicio, lugar)
        del ficha["itens"][remocao.posicao - 1]
        mudancas.append(f'{remocao.ficha} · linha {remocao.posicao} ({remocao.exercicio}) repetida: tirada')

    # 5. nomes de ficha
    for antes, depois in plano.fichas_renomeadas:
        nomes = [ficha["nome"] for ficha in fichas]
        if antes in nomes:
            fichas[nomes.index(antes)]["nome"] = depois
            mudancas.append(f'nome da ficha: "{antes}" → "{depois}"')
        elif depois not in nomes:
            raise Divergencia(f'{onde}: não achei a ficha "{antes}".')

    conteudo = {"fichas": [{"nome": f["nome"], "itens": [{c: i.get(c) for c in _CAMPOS_DO_ITEM} for i in f["itens"]]} for f in fichas]}
    if mudancas:
        _conferir_resultado(conn, plano.modelo_id, novo_nome, conteudo, onde)
    return Resultado(plano.modelo_id, nome_hoje, novo_nome, conteudo, mudancas, fila_id=fila_id, numero=numero)


def _achar_fila(conn: sqlite3.Connection, nome: str, onde: str) -> sqlite3.Row:
    for fila in conn.execute("SELECT id, nome FROM fila"):
        if _mesmo_nome(fila["nome"], nome):
            return fila
    raise Divergencia(f'{onde}: não achei a fila "{nome}".')


def calcular_novo(conn: sqlite3.Connection, novo: Novo) -> Resultado:
    """Prepara um treino padrão NOVO (em memória). Levanta Divergencia se algo não bater.

    Cada exercício é achado pelo nome que aparece na tela e tem que existir exatamente uma vez na lista ativa.
    Se o treino já foi criado antes (mesmo lugar na fila, mesmo nome e mesmo conteúdo), não há o que fazer.
    """
    onde = f'treino novo "{novo.nome}"'
    fila = _achar_fila(conn, novo.fila, onde)
    lugar = texto_da_posicao(fila["nome"], novo.numero)

    ids_por_nome: dict[str, list[int]] = {}
    for linha in conn.execute("SELECT id, nome FROM exercicio WHERE ativo = 1"):
        ids_por_nome.setdefault(normalizar(nome_para_exibir(linha["nome"])), []).append(linha["id"])

    erros: list[str] = []
    fichas_cruas: list[dict] = []
    detalhes: list[str] = []
    for ficha in novo.fichas:
        itens = []
        for posicao, item in enumerate(ficha.itens, start=1):
            ids = ids_por_nome.get(normalizar(item.exercicio), [])
            if len(ids) != 1:
                erros.append(f'{onde}, ficha "{ficha.nome}", linha {posicao}: o exercício "{item.exercicio}" aparece {len(ids)} vezes na lista ativa (esperava 1).')
                continue
            itens.append(
                {
                    "exercicio_id": ids[0],
                    "series": item.series,
                    "repeticoes": item.repeticoes,
                    "carga": "",
                    "pausa": None,
                    "observacao": item.observacao,
                    "bloco": None,
                }
            )
            quanto = " x ".join(t for t in (item.series, item.repeticoes) if t)
            detalhes.append(f'{ficha.nome} · linha {posicao}: {item.exercicio}' + (f" ({quanto})" if quanto else "") + (f" [{item.observacao}]" if item.observacao else ""))
        fichas_cruas.append({"nome": ficha.nome, "itens": itens})
    if erros:
        raise Divergencia("\n".join(erros))

    problemas: list[str] = []
    nome = validar_texto(novo.nome, "O nome do treino padrão", LIMITE_NOME_TREINO, True, problemas)
    professor = validar_texto(novo.montado_por, "O nome de quem montou", LIMITE_QUEM_MONTOU, True, problemas)
    fichas = validar_fichas(conn, fichas_cruas, problemas)
    if problemas or fichas is None:
        raise Divergencia(f"{onde}: não passa na conferência: " + " ".join(problemas))
    conteudo = {
        "fichas": [{"nome": f["nome"], "itens": [{c: i.get(c) for c in _CAMPOS_DO_ITEM} for i in f["itens"]]} for f in fichas]
    }

    do_lugar = conn.execute(
        "SELECT id, nome, conteudo FROM modelo_treino WHERE fila_id = ? AND numero = ?", (fila["id"], novo.numero)
    ).fetchone()
    mesmo_nome = [r for r in conn.execute("SELECT id, nome FROM modelo_treino") if _mesmo_nome(r["nome"], nome)]
    if do_lugar is not None:
        if _mesmo_nome(do_lugar["nome"], nome) and json.loads(do_lugar["conteudo"]) == conteudo:
            return Resultado(do_lugar["id"], nome, nome, conteudo, [], fila_id=fila["id"], numero=novo.numero, montado_por=professor)
        raise Divergencia(f'{onde}: o lugar {lugar} já tem outro treino ("{do_lugar["nome"]}").')
    if mesmo_nome:
        raise Divergencia(f'{onde}: já existe um treino padrão com esse nome (id {mesmo_nome[0]["id"]}), mas não em {lugar}.')

    total = sum(len(f["itens"]) for f in fichas)
    resumo = f'criar "{nome}" em {lugar}: {len(fichas)} fichas, {total} exercícios'
    return Resultado(None, nome, nome, conteudo, [resumo], fila_id=fila["id"], numero=novo.numero, montado_por=professor, detalhes=detalhes)


def _conferir_resultado(conn: sqlite3.Connection, modelo_id: int, nome: str, conteudo: dict, onde: str) -> None:
    """O padrão novo tem que passar na mesma conferência de um treino de verdade."""
    problemas: list[str] = []
    validar_texto(nome, "O nome do treino padrão", LIMITE_NOME_TREINO, True, problemas)
    validar_fichas(conn, conteudo["fichas"], problemas)
    for outro_id, outro_nome in conn.execute("SELECT id, nome FROM modelo_treino"):
        if outro_id != modelo_id and normalizar(outro_nome) == normalizar(nome):
            problemas.append(f'já existe outro treino padrão chamado "{nome}".')
    if problemas:
        raise Divergencia(f"{onde}: o treino ajustado não passa na conferência: " + " ".join(problemas))


def calcular_todos(conn: sqlite3.Connection, planos=PLANOS, novos=()) -> list[Resultado]:
    """Calcula todos os planos e treinos novos. Se algum não bater, levanta Divergencia com TODAS as divergências."""
    resultados, erros = [], []
    for plano in planos:
        try:
            resultados.append(calcular(conn, plano))
        except Divergencia as erro:
            erros.append(str(erro))
    for novo in novos:
        try:
            resultados.append(calcular_novo(conn, novo))
        except Divergencia as erro:
            erros.append(str(erro))
    if erros:
        raise Divergencia("\n".join(erros))
    return resultados


# ------------------------------------------------------------------ gravar


def aplicar(conn: sqlite3.Connection, resultados: list[Resultado], planos=PLANOS, novos=()) -> int:
    """Grava os padrões que ainda têm o que mudar (e cria os novos), TUDO OU NADA. Devolve quantos padrões mudaram."""
    mudar = [r for r in resultados if r.mudancas]
    with conn:  # uma transação só: se algo falhar aqui dentro, volta tudo
        for r in mudar:
            conteudo = json.dumps(r.conteudo, ensure_ascii=False)
            if r.modelo_id is None:
                conn.execute(
                    "INSERT INTO modelo_treino (nome, montado_por, sessoes_por_ficha, conteudo, fila_id, numero)"
                    " VALUES (?, ?, NULL, ?, ?, ?)",
                    (r.novo_nome, r.montado_por, conteudo, r.fila_id, r.numero),
                )
            else:
                conn.execute(
                    "UPDATE modelo_treino SET nome = ?, conteudo = ?, fila_id = ?, numero = ? WHERE id = ?",
                    (r.novo_nome, conteudo, r.fila_id, r.numero, r.modelo_id),
                )
        faltou = [r for r in calcular_todos(conn, planos, novos) if r.mudancas]  # relê o que foi gravado
        if faltou:
            raise Divergencia("Depois de gravar, ainda faltava mudar: " + ", ".join(r.novo_nome for r in faltou) + ". Voltei tudo.")
    return len(mudar)


# ------------------------------------------------------------------ comando de terminal


def _abrir_banco(caminho: Path) -> sqlite3.Connection:
    if not caminho.is_file():
        raise SystemExit(f"Banco de dados não encontrado em '{caminho}'. Use --banco para indicar o arquivo certo.")
    conn = db.conectar(caminho)
    try:
        db.migrar(conn)
        db.verificar_versao(conn)
    except db.BancoDesatualizado as erro:
        conn.close()
        raise SystemExit(str(erro)) from None
    return conn


def _montar_parser(lotes=LOTES) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.ajustar_padroes",
        description="Aplica de uma vez os ajustes e os treinos novos aprovados (pede a senha de administrador, uma vez).",
    )
    parser.add_argument(
        "--lote",
        choices=sorted(lotes),
        default=LOTE_PADRAO,
        help="qual lote aplicar: " + "; ".join(f"{nome} = {lote.descricao}" for nome, lote in lotes.items()) + f" (padrão: {LOTE_PADRAO})",
    )
    parser.add_argument("--banco", default=os.environ.get("GLORIAFIT_DB", "app.db"), help="arquivo do banco (padrão: variável GLORIAFIT_DB ou app.db)")
    parser.add_argument("--copias", default="/backups", help="pasta da cópia de segurança feita antes de gravar (padrão: /backups)")
    parser.add_argument("--simular", action="store_true", help="só mostra o que mudaria: não pede senha e não grava nada")
    parser.add_argument("--detalhes", action="store_true", help="lista cada mudança, linha por linha")
    return parser


def main(argv: list[str] | None = None, pedir_senha=getpass.getpass, lotes=LOTES) -> int:
    args = _montar_parser(lotes).parse_args(argv)
    planos, novos = lotes[args.lote].planos, lotes[args.lote].novos
    conn = _abrir_banco(Path(args.banco))
    try:
        try:
            resultados = calcular_todos(conn, planos, novos)
        except Divergencia as erro:
            print("NADA foi gravado. Os treinos padrão não estão como o lote esperava:", file=sys.stderr)
            print(erro, file=sys.stderr)
            return 1

        print(f"Lote: {args.lote} ({lotes[args.lote].descricao})")
        a_mudar = [r for r in resultados if r.mudancas]
        for r in resultados:
            quantas = len(r.mudancas)
            if r.modelo_id is None:
                estado = "treino novo, ainda não existe"
            else:
                estado = f"{quantas} mudança{'s' if quantas != 1 else ''}" if quantas else "já estava ajustado"
            onde = "novo" if r.modelo_id is None else f"id {r.modelo_id:>2}"
            print(f"  {onde} · {r.nome}: {estado}")
            if args.detalhes:
                for mudanca in r.mudancas:
                    print(f"        - {mudanca}")
                for detalhe in r.detalhes:
                    print(f"        · {detalhe}")
        if not a_mudar:
            print("Nada a fazer: todos os treinos padrão deste lote já estão prontos.")
            return 0
        total = sum(len(r.mudancas) for r in a_mudar)
        criados = sum(1 for r in a_mudar if r.modelo_id is None)
        print(f"Total: {len(a_mudar)} treinos padrão ({criados} novos), {total} mudanças.")
        if args.simular:
            print("Simulação: NADA foi gravado.")
            return 0

        print("Para gravar, digite a senha de administrador (ela não aparece na tela).")
        try:
            administrador.conferir_senha(conn, pedir_senha("Senha de administrador: "))
        except administrador.SenhaNaoDefinida:
            print("A senha de administrador ainda não foi definida. Nada foi alterado.", file=sys.stderr)
            return 2
        except administrador.SenhaIncorreta:
            print("Senha incorreta. Nada foi alterado.", file=sys.stderr)
            return 2
        except administrador.MuitasTentativas as erro:
            print(f"Senhas erradas demais. Tente de novo em {-(-erro.segundos // 60)} min. Nada foi alterado.", file=sys.stderr)
            return 2

        try:
            copia = fazer_backup(args.banco, args.copias)
        except (BackupFalhou, sqlite3.Error, OSError) as erro:
            print(f"Cópia de segurança NÃO feita ({erro}). Nada foi alterado.", file=sys.stderr)
            return 1
        print(f"Cópia de segurança feita: {copia.name}")

        try:
            gravados = aplicar(conn, resultados, planos, novos)
        except (Divergencia, sqlite3.Error) as erro:
            print(f"NÃO gravei nada: {erro}", file=sys.stderr)
            return 1
        novos_criados = sum(1 for r in a_mudar if r.modelo_id is None)
        if novos_criados:
            ajustados = gravados - novos_criados
            ajustados_texto = f"{ajustados} treino padrão ajustado" if ajustados == 1 else f"{ajustados} treinos padrão ajustados"
            criados_texto = "1 criado" if novos_criados == 1 else f"{novos_criados} criados"
            print(f"Pronto: {ajustados_texto} e {criados_texto}.")
        else:
            print(f"Pronto: {gravados} treinos padrão ajustados.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
