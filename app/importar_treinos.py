"""Importa o histórico de treinos do Data4U para o banco do app.

Como os alunos (app/importar_alunos.py), o histórico chega num pacote que o NAVEGADOR monta a
partir do base_total.zip, na tela "Atualizar alunos": só as tabelas e colunas de que o app
precisa. Formato (cada linha é uma lista, na ordem das colunas):

    {"extracao": "08/10/2026 05:00:19",
     "tabelas": {"TREINO": {"colunas": ["ID_TREINO", ...], "linhas": [[1, ...], ...]}, ...}}

As tabelas: TREINO, TREINO_FICHA, TREINO_PRESCRICAO, TREINO_EXERCICIO (só os exercícios que
alguma prescrição usa), LANCAMENTO_OBJ (só os lançamentos dos treinos; é ela que diz de QUEM é
cada treino) e PESSOA (só os professores que montaram treinos: id e nome).

Regras (as decisões são do Thiago, de 08/10/2026, salvo onde dito o contrário):

- Entram TODOS os treinos antigos de TODOS os alunos que estão no app. A ligação é
  TREINO.ID_LANCAMENTO -> LANCAMENTO_OBJ.ID_OBJ (= aluno.data4u_id), só lançamentos do tipo
  -510 (conferido em 08/10/2026: todos os lançamentos de treino têm esse tipo).
- Ficam de fora (e são contados no relatório): treino apagado no Data4U (ST_DELETED = 'T');
  treino sem lançamento (são 10 "modelos", que não pertencem a nenhum aluno); treino de pessoa
  que não está no app; treino com data de lançamento ilegível; treino cujo ID já pertence a um
  treino montado no app (quando o app passar a enviar treinos ao Data4U).
- A data do treino (`criado_em`, a "Montado em" da ficha) é a do LANÇAMENTO (DT_LANCAMENTO, com
  a hora, horário de Brasília) e não a de início (DT_INICIO): em 89% dos treinos o dia é o mesmo,
  mas o início pode vir até 1.586 dias depois (conferido em 08/10/2026), e é a data do
  lançamento que diz quando o professor registrou o treino.
- É um ESPELHO do Data4U: rodar de novo atualiza os treinos que já vieram (mesmo `data4u_id`,
  mesmo id no app), acrescenta os novos e remove os que sumiram do Data4U. Os treinos montados
  no app (`origem = 'app'`) nunca são tocados.
- Exercícios: o que já está na biblioteca (pela tabela `exercicio_data4u`) é reaproveitado.
  O que não está (o quadro do app só tem os usados no último ano) entra como exercício
  INATIVO: aparece no histórico, mas não na lista da tela de montar. Tags HTML do nome
  (`<b>X</b> APAGADO`, como o Data4U marca o que o usuário apagou) são tiradas; o "APAGADO"
  fica. Se o nome já existe no app (sem diferenciar maiúsculas), o exercício existente é usado.
  Exercício que uma prescrição usa mas não existe na tabela do Data4U vira "Exercício removido do Data4U".
- Nada é adivinhado nem cortado em silêncio: valor longo demais é cortado no limite do
  banco e CONTADO no relatório; pausa que não é "hh:mm:ss" fica vazia e é contada.
- Tudo ou nada: se algo der errado no meio, o banco fica como estava. `simular=True` roda tudo
  e desfaz no fim (devolve o relatório do que ACONTECERIA).
"""

import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from app.alunos import FUSO_DA_ACADEMIA
from app.importar_alunos import (
    LIMITE_DE_LINHAS_POR_TABELA,
    CopiaInvalida,
    conferir_data_do_pacote,
    valor_serve,
)
from app.treinos import (
    LIMITE_CAMPO,
    LIMITE_NOME_FICHA,
    LIMITE_NOME_TREINO,
    LIMITE_QUEM_MONTOU,
    limpar_espacos,
)

TIPO_LANCAMENTO_DE_TREINO = -510
LIMITE_NOME_EXERCICIO = 120  # o maior nome real tem 74 letras
LIMITE_OBSERVACAO = 200  # a maior observação real tem 131 letras

NOME_DO_EXERCICIO_REMOVIDO = "Exercício removido do Data4U"
NOME_SEM_PROFESSOR = "Professor não informado"
NOME_TREINO_SEM_NOME = "(sem nome)"

COLUNAS_NECESSARIAS = {
    "TREINO": ("ID_TREINO", "ID_LANCAMENTO", "ID_PROFESSOR", "NM_TREINO", "ST_DELETED"),
    "TREINO_FICHA": ("ID_TREINO_FICHA", "ID_TREINO", "NR_FICHA", "NM_TREINO_FICHA"),
    "TREINO_PRESCRICAO": (
        "ID_TREINO_PRESCRICAO", "ID_TREINO_FICHA", "ID_TREINO_EXERCICIO", "NR_ORDEM",
        "NR_SERIE", "DS_REPETICAO", "DS_PESO", "TM_PAUSA", "DS_PRESCRICAO_OBS",
    ),
    "TREINO_EXERCICIO": ("ID_TREINO_EXERCICIO", "NM_EXERCICIO"),
    "LANCAMENTO_OBJ": ("ID_LANCAMENTO", "ID_OBJ", "TP_LANCAMENTO", "DT_LANCAMENTO"),
    "PESSOA": ("ID", "NM_PESSOA"),
}
TABELAS_USADAS = tuple(COLUNAS_NECESSARIAS)

# (tipo obrigatório, aceita vazio?). int não aceita bool (True seria 1).
_TIPOS_DAS_COLUNAS = {
    "TREINO": {"ID_TREINO": (int, False), "ID_LANCAMENTO": (int, True), "ID_PROFESSOR": (int, True),
               "NM_TREINO": (str, True), "ST_DELETED": (str, True)},
    "TREINO_FICHA": {"ID_TREINO_FICHA": (int, False), "ID_TREINO": (int, False), "NR_FICHA": (int, False),
                     "NM_TREINO_FICHA": (str, True)},
    "TREINO_PRESCRICAO": {"ID_TREINO_PRESCRICAO": (int, False), "ID_TREINO_FICHA": (int, False),
                          "ID_TREINO_EXERCICIO": (int, False), "NR_ORDEM": (int, False),
                          "NR_SERIE": (str, True), "DS_REPETICAO": (str, True), "DS_PESO": (str, True),
                          "TM_PAUSA": (str, True), "DS_PRESCRICAO_OBS": (str, True)},
    "TREINO_EXERCICIO": {"ID_TREINO_EXERCICIO": (int, False), "NM_EXERCICIO": (str, True)},
    "LANCAMENTO_OBJ": {"ID_LANCAMENTO": (int, False), "ID_OBJ": (int, True), "TP_LANCAMENTO": (int, True),
                       "DT_LANCAMENTO": (str, True)},
    "PESSOA": {"ID": (int, False), "NM_PESSOA": (str, True)},
}
# Colunas cujo valor não pode se repetir na tabela (se repetisse, ligar uma tabela à outra seria um palpite).
_CHAVES_UNICAS = {
    "TREINO": "ID_TREINO",
    "TREINO_FICHA": "ID_TREINO_FICHA",
    "TREINO_EXERCICIO": "ID_TREINO_EXERCICIO",
    "LANCAMENTO_OBJ": "ID_LANCAMENTO",
    "PESSOA": "ID",
}


# ------------------------------------------------------------------ pacote enviado pelo navegador


@dataclass
class CopiaDeTreinos:
    extraido_em: datetime
    linhas: dict[str, list[list]]  # tabela -> linhas (listas, na ordem de `posicao`)
    posicao: dict[str, dict[str, int]]  # tabela -> coluna -> posição na linha


def copia_de_pacote(pacote, agora: datetime | None = None) -> CopiaDeTreinos:
    """Valida o pacote enviado pelo navegador. Nada é gravado aqui."""
    extraido_em = conferir_data_do_pacote(pacote, agora)
    if set(pacote["tabelas"]) != set(TABELAS_USADAS):
        raise CopiaInvalida("O pacote de treinos precisa ter exatamente as tabelas " + ", ".join(TABELAS_USADAS) + ".")

    todas: dict[str, list[list]] = {}
    posicoes: dict[str, dict[str, int]] = {}
    for nome in TABELAS_USADAS:
        bloco = pacote["tabelas"][nome]
        colunas = bloco.get("colunas") if isinstance(bloco, dict) else None
        linhas = bloco.get("linhas") if isinstance(bloco, dict) else None
        if not isinstance(colunas, list) or not isinstance(linhas, list):
            raise CopiaInvalida(f"{nome}: formato inesperado.")
        # Exatamente as colunas usadas: coluna a mais seria dado que o app não precisa.
        if len(colunas) != len(set(colunas)) or set(colunas) != set(COLUNAS_NECESSARIAS[nome]):
            raise CopiaInvalida(f"{nome}: as colunas enviadas precisam ser exatamente {', '.join(COLUNAS_NECESSARIAS[nome])}.")
        if len(linhas) > LIMITE_DE_LINHAS_POR_TABELA:
            raise CopiaInvalida(f"{nome}: linhas demais.")
        posicao = {coluna: i for i, coluna in enumerate(colunas)}
        checagens = [(posicao[c], tipo, vazio, c) for c, (tipo, vazio) in _TIPOS_DAS_COLUNAS[nome].items()]
        for numero, linha in enumerate(linhas, start=1):
            if not isinstance(linha, list) or len(linha) != len(colunas):
                raise CopiaInvalida(f"{nome}, linha {numero}: formato inesperado.")
            for i, tipo, aceita_vazio, coluna in checagens:
                if not valor_serve(linha[i], tipo, aceita_vazio):
                    raise CopiaInvalida(f"{nome}, linha {numero}: a coluna {coluna} está num formato inesperado.")
        chave = _CHAVES_UNICAS.get(nome)
        if chave is not None:
            i = posicao[chave]
            if len({linha[i] for linha in linhas}) != len(linhas):
                raise CopiaInvalida(f"{nome}: a coluna {chave} tem valores repetidos.")
        todas[nome] = linhas
        posicoes[nome] = posicao

    if not todas["TREINO"]:
        # Pacote sem treino nenhum não é "nenhum treino": apagaria o histórico inteiro do app.
        raise CopiaInvalida("O pacote não tem nenhum treino. Gere a cópia de novo no PC da recepção.")
    return CopiaDeTreinos(extraido_em, todas, posicoes)


# ------------------------------------------------------------------ regras (funções puras)


def sem_html(texto: str) -> str:
    """Tira as tags HTML: '<b>(10) CADEIRA</b> APAGADO' -> '(10) CADEIRA APAGADO'."""
    return re.sub(r"<[^>]*>", " ", texto)


def limpar(texto: str | None) -> str:
    """Troca caracteres de controle por espaço e junta espaços repetidos."""
    if texto is None:
        return ""
    sem_controle = "".join(" " if (ord(c) < 32 or 127 <= ord(c) < 160) else c for c in texto)
    return limpar_espacos(sem_controle)


_PAUSA = re.compile(r"([0-9]{1,2}):([0-9]{2}):([0-9]{2})")


def pausa_em_segundos(texto: str | None) -> int | None:
    """'00:01:30' -> 90. Vazio ou fora do formato -> None."""
    if texto is None:
        return None
    achou = _PAUSA.fullmatch(texto.strip())
    if not achou:
        return None
    horas, minutos, segundos = (int(g) for g in achou.groups())
    if minutos > 59 or segundos > 59:
        return None
    return horas * 3600 + minutos * 60 + segundos


def data_em_utc(texto: str | None) -> str | None:
    """'2021-02-26 14:03:24' (horário de Brasília, como o Data4U guarda) -> '2021-02-26 17:03:24' (UTC)."""
    try:
        local = datetime.strptime(texto or "", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return local.replace(tzinfo=FUSO_DA_ACADEMIA).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------ relatório


@dataclass
class Relatorio:
    extraido_em: datetime
    simulado: bool = False
    # o que havia na cópia
    treinos_na_copia: int = 0
    # o que entrou
    treinos_novos: int = 0
    treinos_atualizados: int = 0
    treinos_removidos: int = 0  # estavam no app, não estão mais no Data4U
    fichas: int = 0
    exercicios_prescritos: int = 0
    alunos_com_historico: int = 0
    # o que ficou de fora
    fora_apagados: int = 0
    fora_sem_aluno: int = 0  # sem lançamento de treino (modelos)
    fora_aluno_fora_do_app: int = 0
    alunos_fora_do_app: int = 0
    fora_sem_data: int = 0
    fora_ja_e_do_app: int = 0
    # exercícios
    exercicios_usados: int = 0
    exercicios_ja_na_biblioteca: int = 0
    exercicios_novos_inativos: int = 0
    exercicios_com_nome_ja_existente: int = 0
    exercicios_sem_cadastro: int = 0
    # ajustes feitos para caber no banco
    treinos_sem_nome: int = 0
    treinos_sem_professor: int = 0
    treinos_sem_ficha: int = 0
    nomes_cortados: int = 0
    campos_cortados: int = 0
    pausas_ilegiveis: int = 0

    @property
    def treinos_no_app(self) -> int:
        return self.treinos_novos + self.treinos_atualizados

    def como_dicionario(self) -> dict:
        """Para a tela "Atualizar alunos": só contagens e o texto do relatório (sem nome de aluno)."""
        return {
            "extraido_em": f"{self.extraido_em:%d/%m/%Y %H:%M}",
            "simulado": self.simulado,
            "treinos": self.treinos_no_app,
            "novos": self.treinos_novos,
            "atualizados": self.treinos_atualizados,
            "removidos": self.treinos_removidos,
            "texto": self.texto(),
        }

    def texto(self) -> str:
        linhas = []
        if self.simulado:
            linhas.append("SIMULAÇÃO: nada foi gravado. O que aconteceria:")
        linhas += [
            f"Histórico de treinos do Data4U (cópia de {self.extraido_em:%d/%m/%Y %H:%M})",
            f"  Treinos na cópia: {self.treinos_na_copia}",
            f"  Treinos no app a partir da cópia: {self.treinos_no_app} "
            f"({self.treinos_novos} novos, {self.treinos_atualizados} atualizados), de {self.alunos_com_historico} alunos",
            f"  Fichas: {self.fichas}; exercícios prescritos: {self.exercicios_prescritos}",
            f"  Treinos que sumiram do Data4U e saíram do app: {self.treinos_removidos}",
            "  Ficaram de fora:",
            f"    treino apagado no Data4U: {self.fora_apagados}",
            f"    treino sem aluno (modelo, ou sem lançamento de treino): {self.fora_sem_aluno}",
            f"    treino de aluno que não está no app: {self.fora_aluno_fora_do_app} ({self.alunos_fora_do_app} pessoas)",
            f"    treino sem data de lançamento legível: {self.fora_sem_data}",
            f"    treino que já pertence a um treino montado no app: {self.fora_ja_e_do_app}",
            f"  Exercícios usados nos treinos: {self.exercicios_usados}",
            f"    já estavam na biblioteca do app: {self.exercicios_ja_na_biblioteca}",
            f"    entraram só para o histórico (inativos): {self.exercicios_novos_inativos}",
            f"    já existiam no app com o mesmo nome (reaproveitados): {self.exercicios_com_nome_ja_existente}",
            f"    sem cadastro no Data4U (viraram \"{NOME_DO_EXERCICIO_REMOVIDO}\"): {self.exercicios_sem_cadastro}",
            "  Ajustes para caber no banco:",
            f"    treinos sem nome (ficaram \"{NOME_TREINO_SEM_NOME}\"): {self.treinos_sem_nome}",
            f"    treinos sem professor (ficaram \"{NOME_SEM_PROFESSOR}\"): {self.treinos_sem_professor}",
            f"    treinos sem nenhuma ficha: {self.treinos_sem_ficha}",
            f"    nomes cortados no limite do banco: {self.nomes_cortados}",
            f"    séries, repetições, cargas ou observações cortadas: {self.campos_cortados}",
            f"    pausas fora do formato hh:mm:ss (ficaram vazias): {self.pausas_ilegiveis}",
        ]
        return "\n".join(linhas)


# ------------------------------------------------------------------ importação


class _Desfazer(Exception):
    """Só para a simulação: sai do bloco da transação para o banco voltar ao que era."""


def _cortar(texto: str, limite: int) -> tuple[str, bool]:
    return (texto[:limite].rstrip(), True) if len(texto) > limite else (texto, False)


def _resolver_exercicios(conn, nomes_do_data4u: dict[int, str | None], necessarios: set[int], relatorio: Relatorio) -> dict[int, int]:
    """data4u_id do exercício -> id do exercício no app, criando (inativo) o que faltar."""
    conhecidos = {linha[0]: linha[1] for linha in conn.execute("SELECT data4u_id, exercicio_id FROM exercicio_data4u")}
    por_nome = {linha[1].lower(): linha[0] for linha in conn.execute("SELECT id, nome FROM exercicio")}
    mapa: dict[int, int] = {}
    relatorio.exercicios_usados = len(necessarios)
    for data4u_id in sorted(necessarios):
        if data4u_id in conhecidos:
            mapa[data4u_id] = conhecidos[data4u_id]
            relatorio.exercicios_ja_na_biblioteca += 1
            continue
        nome = limpar(sem_html(nomes_do_data4u.get(data4u_id) or ""))
        sem_cadastro = not nome
        if sem_cadastro:
            nome = NOME_DO_EXERCICIO_REMOVIDO
            relatorio.exercicios_sem_cadastro += 1
        else:
            nome, cortado = _cortar(nome, LIMITE_NOME_EXERCICIO)
            relatorio.nomes_cortados += cortado
        exercicio_id = por_nome.get(nome.lower())
        if exercicio_id is None:
            exercicio_id = conn.execute(
                "INSERT INTO exercicio (nome, ativo, combinado, origem) VALUES (?, 0, 0, ?)",
                (nome, "data4u_catalogo" if data4u_id < 0 else "data4u_academia"),
            ).lastrowid
            por_nome[nome.lower()] = exercicio_id
            if not sem_cadastro:
                relatorio.exercicios_novos_inativos += 1
        elif not sem_cadastro:
            relatorio.exercicios_com_nome_ja_existente += 1
        conn.execute(
            "INSERT OR IGNORE INTO exercicio_data4u (data4u_id, exercicio_id) VALUES (?, ?)", (data4u_id, exercicio_id)
        )
        mapa[data4u_id] = exercicio_id
    return mapa


def importar(conn: sqlite3.Connection, copia: CopiaDeTreinos, simular: bool = False) -> Relatorio:
    """Grava o histórico de treinos da cópia no banco, tudo ou nada. Devolve o relatório."""
    relatorio = Relatorio(extraido_em=copia.extraido_em, simulado=simular)
    pos = copia.posicao
    relatorio.treinos_na_copia = len(copia.linhas["TREINO"])

    # ---- índices da cópia (posições das colunas, para não criar um dicionário por linha: são 129 mil)
    t, f, p = pos["TREINO"], pos["TREINO_FICHA"], pos["TREINO_PRESCRICAO"]
    col = pos["PESSOA"]
    professores = {
        linha[col["ID"]]: limpar(linha[col["NM_PESSOA"]]) for linha in copia.linhas["PESSOA"]
    }
    col = pos["LANCAMENTO_OBJ"]
    lancamentos = {
        linha[col["ID_LANCAMENTO"]]: (linha[col["ID_OBJ"]], linha[col["TP_LANCAMENTO"]], linha[col["DT_LANCAMENTO"]])
        for linha in copia.linhas["LANCAMENTO_OBJ"]
    }
    col = pos["TREINO_EXERCICIO"]
    nomes_dos_exercicios = {
        linha[col["ID_TREINO_EXERCICIO"]]: linha[col["NM_EXERCICIO"]] for linha in copia.linhas["TREINO_EXERCICIO"]
    }
    fichas_por_treino: dict[int, list[list]] = defaultdict(list)
    for linha in copia.linhas["TREINO_FICHA"]:
        fichas_por_treino[linha[f["ID_TREINO"]]].append(linha)
    itens_por_ficha: dict[int, list[list]] = defaultdict(list)
    for linha in copia.linhas["TREINO_PRESCRICAO"]:
        itens_por_ficha[linha[p["ID_TREINO_FICHA"]]].append(linha)

    conn.execute("BEGIN IMMEDIATE")  # ninguém muda o banco entre as leituras e as gravações abaixo
    try:
        alunos_do_app = {
            linha[0]: linha[1] for linha in conn.execute("SELECT data4u_id, id FROM aluno WHERE data4u_id IS NOT NULL")
        }
        do_app = {
            linha[0] for linha in conn.execute("SELECT data4u_id FROM treino WHERE origem = 'app' AND data4u_id IS NOT NULL")
        }
        do_data4u = {
            linha[0]: linha[1] for linha in conn.execute("SELECT data4u_id, id FROM treino WHERE origem = 'data4u'")
        }

        # ---- quais treinos entram
        escolhidos = []  # (linha do treino, id do aluno no app, criado_em em UTC)
        pessoas_fora = set()
        for linha in sorted(copia.linhas["TREINO"], key=lambda linha: linha[t["ID_TREINO"]]):
            if linha[t["ST_DELETED"]] == "T":
                relatorio.fora_apagados += 1
                continue
            lancamento = lancamentos.get(linha[t["ID_LANCAMENTO"]])  # None se o treino não tem lançamento
            if lancamento is None or lancamento[1] != TIPO_LANCAMENTO_DE_TREINO or lancamento[0] is None:
                relatorio.fora_sem_aluno += 1
                continue
            aluno_id = alunos_do_app.get(lancamento[0])
            if aluno_id is None:
                relatorio.fora_aluno_fora_do_app += 1
                pessoas_fora.add(lancamento[0])
                continue
            criado_em = data_em_utc(lancamento[2])
            if criado_em is None:
                relatorio.fora_sem_data += 1
                continue
            if linha[t["ID_TREINO"]] in do_app:
                relatorio.fora_ja_e_do_app += 1
                continue
            escolhidos.append((linha, aluno_id, criado_em))
        relatorio.alunos_fora_do_app = len(pessoas_fora)
        relatorio.alunos_com_historico = len({aluno_id for _, aluno_id, _ in escolhidos})

        # ---- exercícios que esses treinos usam
        necessarios = {
            item[p["ID_TREINO_EXERCICIO"]]
            for linha, _, _ in escolhidos
            for ficha in fichas_por_treino.get(linha[t["ID_TREINO"]], [])
            for item in itens_por_ficha.get(ficha[f["ID_TREINO_FICHA"]], [])
        }
        mapa_de_exercicios = _resolver_exercicios(conn, nomes_dos_exercicios, necessarios, relatorio)

        # ---- gravar
        for linha, aluno_id, criado_em in escolhidos:
            data4u_id = linha[t["ID_TREINO"]]

            nome = limpar(linha[t["NM_TREINO"]])
            if not nome:
                nome = NOME_TREINO_SEM_NOME
                relatorio.treinos_sem_nome += 1
            nome, cortado = _cortar(nome, LIMITE_NOME_TREINO)
            relatorio.nomes_cortados += cortado

            professor = professores.get(linha[t["ID_PROFESSOR"]]) if linha[t["ID_PROFESSOR"]] is not None else None
            if not professor:
                professor = NOME_SEM_PROFESSOR
                relatorio.treinos_sem_professor += 1
            professor, cortado = _cortar(professor, LIMITE_QUEM_MONTOU)
            relatorio.nomes_cortados += cortado

            treino_id = do_data4u.get(data4u_id)
            if treino_id is None:
                treino_id = conn.execute(
                    "INSERT INTO treino (aluno_id, nome, montado_por, origem, data4u_id, criado_em)"
                    " VALUES (?, ?, ?, 'data4u', ?, ?)",
                    (aluno_id, nome, professor, data4u_id, criado_em),
                ).lastrowid
                relatorio.treinos_novos += 1
            else:
                conn.execute(
                    "UPDATE treino SET aluno_id = ?, nome = ?, montado_por = ?, criado_em = ? WHERE id = ?",
                    (aluno_id, nome, professor, criado_em, treino_id),
                )
                conn.execute("DELETE FROM ficha WHERE treino_id = ?", (treino_id,))  # apaga os itens junto
                relatorio.treinos_atualizados += 1
            do_data4u.pop(data4u_id, None)  # o que sobrar em `do_data4u` sumiu do Data4U

            fichas = sorted(fichas_por_treino.get(data4u_id, []), key=lambda linha: (linha[f["NR_FICHA"]], linha[f["ID_TREINO_FICHA"]]))
            if not fichas:
                relatorio.treinos_sem_ficha += 1
            for ordem_da_ficha, ficha in enumerate(fichas, start=1):
                nome_da_ficha = limpar(ficha[f["NM_TREINO_FICHA"]]) or f"Ficha {ordem_da_ficha}"
                nome_da_ficha, cortado = _cortar(nome_da_ficha, LIMITE_NOME_FICHA)
                relatorio.nomes_cortados += cortado
                ficha_id = conn.execute(
                    "INSERT INTO ficha (treino_id, nome, ordem) VALUES (?, ?, ?)", (treino_id, nome_da_ficha, ordem_da_ficha)
                ).lastrowid
                relatorio.fichas += 1

                itens = sorted(
                    itens_por_ficha.get(ficha[f["ID_TREINO_FICHA"]], []),
                    key=lambda linha: (linha[p["NR_ORDEM"]], linha[p["ID_TREINO_PRESCRICAO"]]),
                )
                linhas_dos_itens = []
                for ordem, item in enumerate(itens, start=1):
                    campos = []
                    for coluna, limite in (("NR_SERIE", LIMITE_CAMPO), ("DS_REPETICAO", LIMITE_CAMPO),
                                           ("DS_PESO", LIMITE_CAMPO), ("DS_PRESCRICAO_OBS", LIMITE_OBSERVACAO)):
                        texto, cortado = _cortar(limpar(item[p[coluna]]), limite)
                        relatorio.campos_cortados += cortado
                        campos.append(texto or None)
                    pausa = pausa_em_segundos(item[p["TM_PAUSA"]])
                    relatorio.pausas_ilegiveis += pausa is None and item[p["TM_PAUSA"]] is not None
                    series, repeticoes, carga, observacao = campos
                    linhas_dos_itens.append(
                        (ficha_id, ordem, mapa_de_exercicios[item[p["ID_TREINO_EXERCICIO"]]],
                         series, repeticoes, carga, pausa, observacao)
                    )
                conn.executemany(
                    "INSERT INTO ficha_item (ficha_id, ordem, exercicio_id, series, repeticoes, carga, pausa, observacao)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    linhas_dos_itens,
                )
                relatorio.exercicios_prescritos += len(linhas_dos_itens)

        # ---- o que sumiu do Data4U sai do app (o histórico é um espelho)
        conn.executemany("DELETE FROM treino WHERE id = ?", [(treino_id,) for treino_id in do_data4u.values()])
        relatorio.treinos_removidos = len(do_data4u)

        if simular:
            raise _Desfazer
        conn.commit()
    except _Desfazer:
        conn.rollback()
    except BaseException:
        conn.rollback()
        raise
    return relatorio
