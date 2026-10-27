"""O treino que o aluno vê no celular (tela /aluno, rota GET /api/aluno/treino).

Regra (decidida pelo Thiago em 08/10/2026, ver README "Ciclo do treino"): o aluno vê só o treino ATIVO, e cada
aluno tem no máximo um. Treino inativo (concluído ou trocado por outro) fica no histórico do professor e o aluno
não vê.

Tudo sai daqui em texto pronto (dose "4 × 12", intervalo "1 min 30 s", etiquetas "A1"/"A2" do bi-set), com as mesmas
funções que a impressão do cupom usa, para o celular e o papel nunca discordarem. O navegador só desenha.

Também é daqui que o aluno marca "fiz esta ficha hoje" (e desfaz): no máximo UMA vez por ficha por dia, dia de
Brasília (decisão do Thiago, 15/10/2026). A contagem alimenta a meta "treinos por ficha" do professor (app/ciclo.py).

E, desde 22/10/2026, o que o aluno faz DURANTE o treino (pedido do Thiago): marcar cada exercício como feito, anotar a carga
usada (e ver "Última vez") e dar a nota de esforço ao concluir (Leve / Ideal / Pesado). As contas de feito e carga estão em
app/execucao.py; aqui só se confere que o exercício é mesmo do treino que o aluno está vendo.

O que NÃO sai daqui, de propósito: ids (do treino, da ficha, do exercício), quem montou, a origem (app ou Data4U),
o aviso de "hora de trocar" (só o professor vê) e dados de outros treinos. O aluno recebe só o que precisa para treinar,
mais o próprio andamento (quantas vezes fez cada ficha e a meta).
"""

import sqlite3
from datetime import datetime, time, timedelta

from app import ciclo, execucao, treinos
from app.alunos import dose_do_item, etiquetas_dos_itens, texto_da_pausa
from app.datas import FUSO_DA_ACADEMIA, agora_utc, dia_local, formatar_dia, hoje, ler_dia, limites_do_dia, momento_para_texto

_NOME_DO_BLOCO = {2: "Bi-set", 3: "Tri-set"}

# A nota que o aluno dá ao concluir a ficha (decisão do Thiago, 22/10/2026): opcional, três opções, sem número na tela.
ESFORCOS = ciclo.ESFORCOS
MAIOR_NUMERO = 9999  # maior número de ficha ou de exercício aceito do celular (um inteiro enorme faria o SQLite dar erro 500)


def _lista_com_e(etiquetas: list[str]) -> str:
    """['A1', 'A2'] -> 'A1 e A2'; ['A1', 'A2', 'A3'] -> 'A1, A2 e A3'."""
    if len(etiquetas) == 1:
        return etiquetas[0]
    return ", ".join(etiquetas[:-1]) + " e " + etiquetas[-1]


def _exercicio(item: dict, etiqueta: str) -> dict:
    return {
        "ordem": item["ordem"],  # a posição na ficha (1, 2, 3...): é como o celular diz sobre qual exercício o aluno comentou
        "etiqueta": etiqueta,
        "exercicio": item["exercicio"],
        "dose": dose_do_item(item),
        "carga": (item["carga"] or "").strip(),
        "intervalo": texto_da_pausa(item["pausa"]),
        "pausa_segundos": item["pausa"] or 0,  # preenche o campo do tempo de descanso no celular (0 = o professor não informou: o campo fica em branco)
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


def _andamento_das_fichas(conn: sqlite3.Connection, treino_id: int, agora: datetime) -> dict[int, dict]:
    """{ordem da ficha: {"feitas": quantas vezes (neste treino), "feita_hoje": bool}}."""
    comeco, fim = limites_do_dia(agora)
    linhas = conn.execute(
        """
        SELECT ficha_ordem, COUNT(*), MAX(feita_em >= ? AND feita_em < ?)
        FROM sessao WHERE treino_id = ? GROUP BY ficha_ordem
        """,
        (comeco, fim, treino_id),
    )
    return {ordem: {"feitas": feitas, "feita_hoje": bool(hoje)} for ordem, feitas, hoje in linhas}


def _proxima_ficha(ordens: list[int], depois_de: int) -> int:
    """A ficha que vem depois de `depois_de` na sequência (A, B, C, A, B...). `ordens` é não vazia e está em ordem."""
    for ordem in ordens:
        if ordem > depois_de:
            return ordem
    return ordens[0]  # passou da última: volta para a primeira


def ficha_do_dia(conn: sqlite3.Connection, treino_id: int, ordens: list[int], agora: datetime) -> int | None:
    """A `ordem` da ficha que o aluno circula como "Treino de hoje" (regra decidida pelo Thiago em 22/10/2026).

    O cadastro não diz qual ficha é de qual dia; quem diz é o que o aluno já fez neste treino:
      - nunca concluiu nenhuma ficha deste treino: a primeira;
      - a última ficha concluída foi HOJE (dia de Brasília): continua sendo ela, com "feito hoje", até amanhã;
      - a última foi em outro dia: a próxima na sequência (A, B, A, B...).
    `ordens` são só as fichas que têm exercício (as que o aluno vê). None se não há nenhuma.
    """
    if not ordens:
        return None
    ultima = conn.execute(
        "SELECT ficha_ordem, feita_em FROM sessao WHERE treino_id = ? ORDER BY feita_em DESC, id DESC LIMIT 1",
        (treino_id,),
    ).fetchone()
    if ultima is None:
        return ordens[0]
    comeco, fim = limites_do_dia(agora)
    if comeco <= ultima["feita_em"] < fim and ultima["ficha_ordem"] in ordens:
        return ultima["ficha_ordem"]
    return _proxima_ficha(ordens, ultima["ficha_ordem"])


def _ordens_com_exercicio(conn: sqlite3.Connection, treino_id: int) -> list[int]:
    """As fichas do treino que têm ao menos um exercício, em ordem (as mesmas que `treino_do_aluno` mostra)."""
    return [
        linha["ordem"]
        for linha in conn.execute(
            "SELECT f.ordem FROM ficha f WHERE f.treino_id = ? "
            "AND EXISTS (SELECT 1 FROM ficha_item i WHERE i.ficha_id = f.id) ORDER BY f.ordem",
            (treino_id,),
        )
    ]


def _treino_sem_execucao(conn: sqlite3.Connection, aluno_id: int, agora: datetime) -> dict | None:
    """O treino ativo do aluno pronto para mostrar, sem o que ele marcou/anotou hoje (isso é `treino_do_aluno` que junta)."""
    linha = conn.execute("SELECT id FROM treino WHERE aluno_id = ? AND ativo = 1", (aluno_id,)).fetchone()
    if linha is None:
        return None
    treino = treinos.obter_treino(conn, linha["id"])
    if treino is None:  # apagado entre as duas consultas (a importação do Data4U apaga e recria)
        return None
    andamento = _andamento_das_fichas(conn, linha["id"], agora)
    fichas = [ficha for ficha in treino["fichas"] if ficha["itens"]]
    return {
        "nome": treino["nome"],
        "inicio": formatar_dia(treino["inicio"]),
        "fim": formatar_dia(treino["fim"]),
        "meta_por_ficha": treino["sessoes_por_ficha"],
        "ficha_do_dia": ficha_do_dia(conn, linha["id"], [ficha["ordem"] for ficha in fichas], agora),
        "fichas": [
            {
                "nome": ficha["nome"],
                "ordem": ficha["ordem"],
                "feitas": andamento.get(ficha["ordem"], {}).get("feitas", 0),
                "feita_hoje": andamento.get(ficha["ordem"], {}).get("feita_hoje", False),
                "esforco_hoje": None,
                "grupos": _grupos_da_ficha(ficha["itens"]),
            }
            for ficha in fichas
        ],
        "_treino_id": linha["id"],
    }


def _esforcos_de_hoje(conn: sqlite3.Connection, treino_id: int, agora: datetime) -> dict[int, int]:
    """{ordem da ficha: nota de esforço (1, 2 ou 3)} das fichas concluídas HOJE em que o aluno deu nota."""
    comeco, fim = limites_do_dia(agora)
    return {
        ordem: esforco
        for ordem, esforco in conn.execute(
            "SELECT ficha_ordem, esforco FROM sessao WHERE treino_id = ? AND esforco IS NOT NULL AND feita_em >= ? AND feita_em < ?",
            (treino_id, comeco, fim),
        )
    }


def _exercicios_com_ocorrencia(ficha: dict):
    """Cada exercício da ficha, na ordem, com a OCORRÊNCIA do nome dele na ficha: (exercício, 1) na primeira vez que o nome aparece,
    (exercício, 2) na segunda... É com o nome + essa ocorrência que se acha o que o aluno marcou (ver app/execucao.py)."""
    vistos: dict[str, int] = {}
    for grupo in ficha["grupos"]:
        for e in grupo["exercicios"]:
            vistos[e["exercicio"]] = vistos.get(e["exercicio"], 0) + 1
            yield e, vistos[e["exercicio"]]


def _juntar_execucao(conn: sqlite3.Connection, aluno_id: int, treino: dict, agora: datetime) -> None:
    """Põe em cada exercício o que o aluno marcou/anotou HOJE e a "última vez" (carga de um dia anterior); e a nota de cada ficha.

    A marca é achada pelo NOME do exercício (e a ocorrência do nome na ficha), não pela posição: se o professor incluir, tirar ou
    trocar um exercício no meio do dia, o que o aluno marcou nos outros continua valendo, e a marca de um exercício que saiu não
    passa para outro. Todas as chaves saem SEMPRE (o celular compara o treino inteiro para saber se mudou).
    """
    dia = hoje(agora)
    marcas = execucao.marcas_do_dia(conn, aluno_id, dia)
    nomes = {e["exercicio"] for ficha in treino["fichas"] for grupo in ficha["grupos"] for e in grupo["exercicios"]}
    ultimas = execucao.ultimas_cargas(conn, aluno_id, nomes, dia)
    recentes = execucao.cargas_recentes(conn, aluno_id, nomes, dia)
    esforcos = _esforcos_de_hoje(conn, treino["_treino_id"], agora)
    for ficha in treino["fichas"]:
        ficha["esforco_hoje"] = esforcos.get(ficha["ordem"])
        for e, ocorrencia in _exercicios_com_ocorrencia(ficha):
            marca = marcas.get((ficha["ordem"], e["exercicio"], ocorrencia))
            ultima = ultimas.get(e["exercicio"])
            e["feito"] = bool(marca["feito"]) if marca else False
            e["carga_hoje"] = (marca["carga"] or "") if marca else ""
            e["ultima_carga"] = ultima[0] if ultima else ""
            e["ultima_data"] = (formatar_dia(ultima[1]) or "") if ultima else ""
            e["cargas_recentes"] = recentes.get(e["exercicio"], [])  # "Últimas: 20 → 22,5 → 25 kg" (da mais antiga para a mais nova)


def treinos_na_semana(conn: sqlite3.Connection, aluno_id: int, agora: datetime | None = None) -> int:
    """Em quantos DIAS desta semana (segunda a domingo, em Brasília) o aluno treinou: dias com alguma sessão registrada ("Treino
    concluído" no celular ou ficha impressa na recepção), de qualquer treino dele. Duas fichas no mesmo dia contam como um treino.
    É a linha "Esta semana: N treinos" da tela inicial (pedido do Thiago, 26/10/2026)."""
    agora = agora or agora_utc()
    dia = ler_dia(hoje(agora))
    segunda = datetime.combine(dia - timedelta(days=dia.weekday()), time(0, 0), tzinfo=FUSO_DA_ACADEMIA)
    linhas = conn.execute(
        "SELECT s.feita_em FROM sessao s JOIN treino t ON t.id = s.treino_id WHERE t.aluno_id = ? AND s.feita_em >= ?",
        (aluno_id, momento_para_texto(segunda)),
    )
    return len({dia_local(linha["feita_em"]) for linha in linhas if dia_local(linha["feita_em"]) <= dia.isoformat()})


def treino_do_aluno(conn: sqlite3.Connection, aluno_id: int, agora: datetime | None = None) -> dict | None:
    """O treino ativo do aluno pronto para mostrar, ou None se ele não tem treino ativo.

    {"nome", "inicio" ("06/10/2026" ou None), "fim" (idem), "meta_por_ficha" (quantas vezes cada ficha, ou None),
    "ficha_do_dia" (a `ordem` da ficha circulada como "Treino de hoje"; ver `ficha_do_dia`),
    "fichas": [{"nome", "ordem", "feitas", "feita_hoje", "esforco_hoje" (1 Leve, 2 Ideal, 3 Pesado ou None), "grupos": [...]}]}.
    Cada exercício leva também o que o aluno fez HOJE e a última vez: "feito" (marcou como feito), "carga_hoje" ("" = nada
    anotado), "ultima_carga" e "ultima_data" ("" = nunca anotou antes) e "pausa_segundos" (preenche o campo do tempo de descanso).
    `ordem` (1 = A, 2 = B...) é o que o celular manda de volta ao marcar a ficha como feita.
    Ficha sem nenhum exercício não aparece (não há o que mostrar).
    """
    agora = agora or agora_utc()
    treino = _treino_sem_execucao(conn, aluno_id, agora)
    if treino is None:
        return None
    _juntar_execucao(conn, aluno_id, treino, agora)
    treino["treinos_na_semana"] = treinos_na_semana(conn, aluno_id, agora)
    del treino["_treino_id"]  # interno: o aluno não recebe ids
    return treino


# ------------------------------------------------------------------ "Treino concluído"


class MarcacaoInvalida(Exception):
    """O aluno não pode marcar isto. A mensagem já está pronta para mostrar; `status` é o código da resposta."""

    def __init__(self, mensagem: str, status: int):
        super().__init__(mensagem)
        self.status = status


def _ficha_do_treino_ativo(conn: sqlite3.Connection, aluno_id: int, ficha_ordem: object) -> int:
    """O id do treino ativo do aluno, se ele tem esse treino e essa ficha; senão MarcacaoInvalida."""
    if isinstance(ficha_ordem, bool) or not isinstance(ficha_ordem, int) or not 1 <= ficha_ordem <= MAIOR_NUMERO:
        raise MarcacaoInvalida("Escolha a ficha de novo.", 400)  # o teto evita um inteiro grande demais para o SQLite (erro 500)
    ativo = ciclo.treino_ativo(conn, aluno_id)
    if ativo is None:
        raise MarcacaoInvalida("Você não tem um treino ativo. Atualize a página.", 409)
    existe = conn.execute(
        "SELECT 1 FROM ficha WHERE treino_id = ? AND ordem = ?", (ativo["id"], ficha_ordem)
    ).fetchone()
    if existe is None:
        raise MarcacaoInvalida("Esta ficha não existe no seu treino. Atualize a página.", 404)
    return ativo["id"]


def marcar_ficha_feita(
    conn: sqlite3.Connection, aluno_id: int, ficha_ordem: object, agora: datetime | None = None
) -> dict:
    """O aluno marca "fiz esta ficha hoje". No máximo UMA vez por ficha por dia (decisão do Thiago, 15/10/2026).

    Marcar de novo no mesmo dia não faz nada (`ja_marcada: True`). Devolve {"ficha", "ja_marcada", "feitas", "ficha_do_dia"}
    (`ficha_do_dia`: qual ficha fica circulada agora; quem decide é só o servidor, o celular não refaz a conta).
    A conferência e a gravação acontecem na mesma transação (`BEGIN IMMEDIATE`): dois toques ao mesmo tempo,
    ou o mesmo aluno em dois celulares, nunca gravam duas vezes.
    """
    agora = agora or agora_utc()
    conn.execute("BEGIN IMMEDIATE")
    try:
        treino_id = _ficha_do_treino_ativo(conn, aluno_id, ficha_ordem)
        ja_marcada, feitas = ciclo.gravar_sessao_do_dia(conn, treino_id, ficha_ordem, agora)
        do_dia = ficha_do_dia(conn, treino_id, _ordens_com_exercicio(conn, treino_id), agora)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return {"ficha": ficha_ordem, "ja_marcada": ja_marcada, "feitas": feitas, "ficha_do_dia": do_dia}


def desfazer_marcacao_de_hoje(
    conn: sqlite3.Connection, aluno_id: int, ficha_ordem: object, agora: datetime | None = None
) -> dict:
    """O aluno desfaz a marcação de HOJE de uma ficha (toque errado). Só apaga as de hoje, nunca as de outros dias.

    Devolve {"ficha", "feitas", "ficha_do_dia"} (quantas ficaram e qual ficha fica circulada agora). Se não havia
    marcação hoje, não muda nada.
    """
    agora = agora or agora_utc()
    conn.execute("BEGIN IMMEDIATE")
    try:
        treino_id = _ficha_do_treino_ativo(conn, aluno_id, ficha_ordem)
        feitas = ciclo.apagar_sessoes_do_dia(conn, treino_id, ficha_ordem, agora)
        do_dia = ficha_do_dia(conn, treino_id, _ordens_com_exercicio(conn, treino_id), agora)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return {"ficha": ficha_ordem, "feitas": feitas, "ficha_do_dia": do_dia}


# ------------------------------------------------------------------ durante o treino: exercício feito, carga e nota


def _inteiro_positivo(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and 1 <= valor <= MAIOR_NUMERO


def marcar_exercicio(
    conn: sqlite3.Connection,
    aluno_id: int,
    ficha: object,
    item: object,
    exercicio: object,
    *,
    feito: object = execucao.NADA,
    carga: object = execucao.NADA,
    agora: datetime | None = None,
) -> dict:
    """O aluno marca um exercício como feito e/ou anota a carga que usou HOJE. Devolve {"feito", "carga_hoje"} (carga "" = nenhuma).

    `ficha` e `item` são os números (1, 2, 3...) da ficha e do exercício dentro dela e `exercicio` o nome que o celular
    mostrava: servem para achar o lugar certo e conferir que nada mudou (se o professor trocou o treino nesse meio tempo, 409
    "atualize a página"; nada é gravado no exercício errado). Só o que veio é mudado: `feito` (true/false) e/ou `carga`
    ("12,5"; "" ou null apaga). A conferência e a gravação ficam na mesma transação (`BEGIN IMMEDIATE`).
    """
    if not (_inteiro_positivo(ficha) and _inteiro_positivo(item) and isinstance(exercicio, str) and exercicio):
        raise MarcacaoInvalida("Escolha o exercício de novo.", 400)
    if feito is execucao.NADA and carga is execucao.NADA:
        raise MarcacaoInvalida("Diga se fez o exercício ou qual carga usou.", 400)
    if feito is not execucao.NADA and not isinstance(feito, bool):
        raise MarcacaoInvalida("Marque o exercício de novo.", 400)
    if carga is not execucao.NADA:
        try:
            carga = execucao.carga_limpa(carga)
        except execucao.CargaInvalida as erro:
            raise MarcacaoInvalida(str(erro), 400) from None
    agora = agora or agora_utc()
    conn.execute("BEGIN IMMEDIATE")
    try:
        treino = _treino_sem_execucao(conn, aluno_id, agora)
        if treino is None:
            raise MarcacaoInvalida("Você não tem um treino ativo. Atualize a página.", 409)
        ocorrencia = None
        for f in treino["fichas"]:
            if f["ordem"] == ficha:
                for e, n_esima in _exercicios_com_ocorrencia(f):
                    if e["ordem"] == item and e["exercicio"] == exercicio:
                        ocorrencia = n_esima
        if ocorrencia is None:
            raise MarcacaoInvalida("O seu treino mudou. Atualize a página.", 409)
        resultado = execucao.gravar(conn, aluno_id, ficha, item, exercicio, ocorrencia=ocorrencia, feito=feito, carga=carga, agora=agora)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return resultado


def definir_esforco(
    conn: sqlite3.Connection, aluno_id: int, ficha_ordem: object, esforco: object, agora: datetime | None = None
) -> dict:
    """O aluno dá a nota de esforço (1 Leve, 2 Ideal, 3 Pesado; null apaga) à ficha que concluiu HOJE. Devolve {"ficha", "esforco"}.

    A nota fica na marcação "treino concluído" de hoje (a mesma que conta na meta do professor): sem ela (o aluno ainda não
    concluiu a ficha, ou desfez) não há onde guardar e a resposta é 409. Pedido do Thiago, 22/10/2026: a nota é opcional.
    """
    if esforco is not None and not (isinstance(esforco, int) and not isinstance(esforco, bool) and esforco in ESFORCOS):
        raise MarcacaoInvalida("Escolha Leve, Ideal ou Pesado.", 400)
    agora = agora or agora_utc()
    conn.execute("BEGIN IMMEDIATE")
    try:
        treino_id = _ficha_do_treino_ativo(conn, aluno_id, ficha_ordem)
        comeco, fim = limites_do_dia(agora)
        alteradas = conn.execute(
            "UPDATE sessao SET esforco = ? WHERE treino_id = ? AND ficha_ordem = ? AND feita_em >= ? AND feita_em < ?",
            (esforco, treino_id, ficha_ordem, comeco, fim),
        ).rowcount
        if alteradas == 0:
            raise MarcacaoInvalida("Conclua o treino primeiro, depois escolha como foi.", 409)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return {"ficha": ficha_ordem, "esforco": esforco}
