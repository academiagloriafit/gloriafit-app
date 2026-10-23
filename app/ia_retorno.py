"""O robô aprende com os professores (pedido do Thiago, 23/10/2026).

O que o robô que monta treino ("Montar rascunho com IA", app/ia_treino.py) sabe vem das regras que escrevemos para ele. Para
melhorar essas regras com base no uso de verdade, duas coisas ficam registradas, SEM ligação nenhuma com o aluno nem com o professor:

1. A AVALIAÇÃO: com o rascunho na tela, o professor toca em "Serviu", "Serviu com ajustes" ou "Não serviu" e, se quiser, escreve o motivo
   (`avaliar`). Vira uma linha 'avaliacao' em `ia_retorno`.
2. A CORREÇÃO: quando o professor salva um treino que veio de um rascunho da IA, o app compara o rascunho com o treino que foi salvo e
   guarda só a DIFERENÇA (`comparar` e `registrar_correcao`): exercícios tirados e incluídos, séries, repetições e pausa que mudaram.
   Vira uma linha 'correcao'. Cargas e o texto das observações dos exercícios NUNCA entram (só se o texto mudou, como contagem).

Uma vez por mês (ou quando o Thiago quiser) o relatório (`python -m app.ia_retorno relatorio`) junta tudo em texto simples: que exercícios
os professores mais tiram e mais põem, que números de séries/repetições mais corrigem, as notas e os motivos escritos. Com ele, o Claude (o do
Thiago, não o do app) propõe regras novas; o app só ganha regra nova depois de o Thiago aprovar e de a mudança ser publicada.

Privacidade (por que é assim):
- `ia_retorno` não tem aluno, professor, número do pedido nem hora: só o DIA e categorias que o professor escolhe na tela (objetivo, nível,
  dias, minutos, nome da fila) e dois dados do rascunho (versão das regras e modelo). Ver o desenho em app/schema.sql.
- Para saber o contexto do rascunho na hora de avaliar/salvar (e não repetir o registro), o app guarda dentro do próprio resultado do
  pedido (`ia_pedido.resultado`, que já é apagado depois de 3 dias) uma área `_retorno`: o contexto e dois sinais ("já avaliado", "já
  registrado"). Essa área não vai para a tela (`ia_treino.consultar_pedido` a tira).
- O motivo é um texto livre: o app recusa o nome do aluno, e-mail e número longo, e a tela avisa para não identificar o aluno. Ainda
  assim ele pode falar de saúde de alguém sem nome ("hérnia de disco"), por isso o texto é curto (300 letras) e só o Thiago lê o relatório.
- Nada aqui vai para a Anthropic nem para a tela do aluno.
"""

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from app import db
from app.datas import hoje
# o mesmo critério de "número longo" das observações:
from app.ia_treino import _PADRAO_DE_NUMERO_LONGO
from app.texto import normalizar
from app.treinos import limpar_espacos, obter_treino, validar_texto

log = logging.getLogger(__name__)

CHAVES_DO_CONTEXTO = ("objetivo", "nivel", "dias", "minutos", "fila", "com_observacoes", "rodadas", "regras", "modelo")  # ver ia_treino.contexto_do_retorno
NOTAS = {"serviu": "Serviu", "com_ajustes": "Serviu com ajustes", "nao_serviu": "Não serviu"}
LIMITE_DO_MOTIVO = 300  # letras (o mesmo CHECK do banco)
MAXIMO_DE_ITENS_POR_LISTA = 60  # exercícios tirados/incluídos/alterados guardados por correção (o resto só é contado)
CAMPOS_COMPARADOS = ("series", "repeticoes", "pausa")  # o que o professor costuma acertar; cargas e observações ficam de fora
ROTULOS_DOS_CAMPOS = {"series": "séries", "repeticoes": "repetições", "pausa": "pausa (segundos)"}


class RetornoInvalido(Exception):
    """A avaliação não pode ser registrada. `problemas` é a lista de motivos, em português."""

    def __init__(self, problemas: list[str]):
        super().__init__("; ".join(problemas))
        self.problemas = problemas


class RascunhoNaoEncontrado(Exception):
    """O pedido não existe, é de outro aluno, não é um rascunho (era só uma pergunta da IA), já foi apagado (3 dias) ou é anterior a esta função."""


class JaAvaliado(Exception):
    """Este rascunho já recebeu uma avaliação (só vale uma por rascunho)."""


# ------------------------------------------------------------------ o contexto do rascunho (guardado no resultado do pedido)


def _carregar(conn: sqlite3.Connection, aluno_id: int, pedido_id: int) -> dict:
    """O resultado guardado do pedido (rascunho + `_retorno`). Levanta RascunhoNaoEncontrado se não há como registrar nada."""
    linha = conn.execute(
        "SELECT resultado FROM ia_pedido WHERE id = ? AND aluno_id = ? AND situacao = 'pronto'", (pedido_id, aluno_id)
    ).fetchone()
    if linha is None or linha["resultado"] is None:
        raise RascunhoNaoEncontrado()
    try:
        resultado = json.loads(linha["resultado"])
    except ValueError:
        raise RascunhoNaoEncontrado() from None
    if not isinstance(resultado, dict) or not isinstance(resultado.get("treino"), dict) or not isinstance(resultado.get("_retorno"), dict):
        raise RascunhoNaoEncontrado()
    if not all(chave in resultado["_retorno"] for chave in CHAVES_DO_CONTEXTO):  # um registro incompleto não vira linha torta no banco
        raise RascunhoNaoEncontrado()
    return resultado


def _guardar(conn: sqlite3.Connection, pedido_id: int, resultado: dict) -> None:
    conn.execute("UPDATE ia_pedido SET resultado = ? WHERE id = ?", (json.dumps(resultado, ensure_ascii=False), pedido_id))


def _inserir(conn: sqlite3.Connection, agora: datetime | None, tipo: str, retorno: dict, nota, motivo, mudancas) -> None:
    conn.execute(
        "INSERT INTO ia_retorno (dia, tipo, objetivo, nivel, dias, minutos, fila, com_observacoes, rodadas, regras, modelo,"
        " nota, motivo, mudancas) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            hoje(agora),
            tipo,
            retorno["objetivo"],
            retorno["nivel"],
            retorno["dias"],
            retorno["minutos"],
            retorno.get("fila"),
            1 if retorno.get("com_observacoes") else 0,
            retorno.get("rodadas", 0),
            retorno["regras"],
            retorno["modelo"],
            nota,
            motivo or None,
            json.dumps(mudancas, ensure_ascii=False) if mudancas is not None else None,
        ),
    )


# ------------------------------------------------------------------ a avaliação do rascunho


def _problemas_do_motivo(texto: str, nome_do_aluno: str | None) -> list[str]:
    """Mesmo cuidado das observações: nada que identifique o aluno (número longo, e-mail, o nome dele)."""
    problemas = []
    if _PADRAO_DE_NUMERO_LONGO.search(texto):
        problemas.append("Tire do motivo números de CPF, telefone ou documento, e datas completas como 15/03/2024: ele não deve identificar o aluno.")
    if "@" in texto:
        problemas.append("Tire do motivo o e-mail: ele não deve identificar o aluno.")
    if nome_do_aluno:
        palavras = set(re.findall(r"[a-z]+", normalizar(texto)))
        partes = {p for p in re.findall(r"[a-z]+", normalizar(nome_do_aluno)) if len(p) >= 4}
        if partes & palavras:
            problemas.append("Tire do motivo o nome do aluno: esta avaliação não guarda quem é o aluno.")
    return problemas


def avaliar(conn: sqlite3.Connection, aluno_id: int, pedido_id: int, nota, motivo=None, agora: datetime | None = None) -> None:
    """Registra a avaliação do professor sobre o rascunho `pedido_id` (do aluno `aluno_id`, que só serve para conferir o pedido).

    Levanta RetornoInvalido (nota fora da lista, motivo comprido ou que identifica o aluno), RascunhoNaoEncontrado e JaAvaliado.
    Tudo ou nada: a linha de `ia_retorno` e o sinal "já avaliado" entram na mesma transação."""
    problemas: list[str] = []
    if nota not in NOTAS:
        problemas.append("Escolha como foi o rascunho: serviu, serviu com ajustes ou não serviu.")
    texto = validar_texto(motivo, "O motivo", LIMITE_DO_MOTIVO, False, problemas)
    if texto:
        nome = conn.execute("SELECT nome FROM aluno WHERE id = ?", (aluno_id,)).fetchone()
        problemas += _problemas_do_motivo(texto, nome["nome"] if nome else None)
    if problemas:
        raise RetornoInvalido(problemas)

    conn.execute("BEGIN IMMEDIATE")  # duas avaliações ao mesmo tempo do mesmo rascunho: só uma entra
    try:
        resultado = _carregar(conn, aluno_id, pedido_id)
        retorno = resultado["_retorno"]
        if retorno.get("avaliado"):
            raise JaAvaliado()
        _inserir(conn, agora, "avaliacao", retorno, nota, texto, None)
        retorno["avaliado"] = True
        retorno["nota"] = nota
        _guardar(conn, pedido_id, resultado)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


# ------------------------------------------------------------------ a correção: o que o professor mudou antes de salvar


def _texto(valor) -> str:
    return limpar_espacos(valor) if isinstance(valor, str) else ""


def _pausa(valor):
    return valor if isinstance(valor, int) and not isinstance(valor, bool) and valor > 0 else None


def _normalizar_item(item: dict) -> dict:
    """Do rascunho (formato de `modelos.para_montar`) ou do treino salvo (`treinos.obter_treino`) para uma forma só."""
    return {
        "id": item.get("exercicio_id"),
        "nome": _texto(item.get("nome") or item.get("exercicio")) or "?",
        "series": _texto(item.get("series")),
        "repeticoes": _texto(item.get("repeticoes")),
        "pausa": _pausa(item.get("pausa")),
        "observacao": _texto(item.get("observacao")),
    }


def _normalizar_fichas(fichas) -> list[dict]:
    resultado = []
    for ficha in fichas if isinstance(fichas, list) else []:
        itens = ficha.get("itens") if isinstance(ficha, dict) else None
        resultado.append(
            {
                "nome": _texto(ficha.get("nome")) if isinstance(ficha, dict) else "",
                "itens": [_normalizar_item(i) for i in itens if isinstance(i, dict)] if isinstance(itens, list) else [],
            }
        )
    return resultado


def _parear(ia: list[dict], final: list[dict]) -> tuple[list[tuple[dict, dict]], list[dict], list[dict]]:
    """Casa os exercícios da mesma ficha pelo id (o mesmo exercício repetido casa na ordem em que aparece).
    Devolve (pares, tirados, incluídos)."""
    candidatos: dict = {}
    for item in final:
        candidatos.setdefault(item["id"], []).append(item)
    pares, tirados = [], []
    for item in ia:
        fila = candidatos.get(item["id"])
        if fila:
            pares.append((item, fila.pop(0)))
        else:
            tirados.append(item)
    incluidos = [item for fila in candidatos.values() for item in fila]
    # `incluidos` na ordem em que o professor os pôs
    ordem = {id(item): n for n, item in enumerate(final)}
    incluidos.sort(key=lambda item: ordem[id(item)])
    return pares, tirados, incluidos


def comparar(rascunho_fichas, salvo_fichas) -> dict:
    """A diferença entre o rascunho da IA e o treino que o professor salvou (as duas listas de fichas, nos formatos de
    `modelos.para_montar` e `treinos.obter_treino`). Só categorias e nomes de exercício da academia: nada do aluno.

    {"fichas": {"ia", "final"}, "exercicios": {"ia", "final"}, "mantidos": n,
     "tirados": [{"ficha", "exercicio"}], "incluidos": [{"ficha", "exercicio"}],
     "alterados": [{"ficha", "exercicio", "campo", "de", "para"}],
     "observacoes_mudadas": n, "fichas_com_ordem_mudada": n, "fichas_renomeadas": n,
     "cortados": n (itens que passaram do máximo e só foram contados)}
    As fichas são casadas pela posição (1 = primeira); o exercício, pelo id dentro da ficha. Passar um exercício de uma ficha para outra
    conta como "tirado" de uma e "incluído" na outra."""
    ia = _normalizar_fichas(rascunho_fichas)
    final = _normalizar_fichas(salvo_fichas)
    tirados, incluidos, alterados = [], [], []
    mantidos = observacoes_mudadas = ordem_mudada = renomeadas = 0
    for posicao in range(max(len(ia), len(final))):
        da_ia = ia[posicao] if posicao < len(ia) else {"nome": "", "itens": []}
        do_final = final[posicao] if posicao < len(final) else {"nome": "", "itens": []}
        numero = posicao + 1
        if posicao < len(ia) and posicao < len(final) and normalizar(da_ia["nome"]) != normalizar(do_final["nome"]):
            renomeadas += 1
        pares, fora, dentro = _parear(da_ia["itens"], do_final["itens"])
        mantidos += len(pares)
        tirados += [{"ficha": numero, "exercicio": i["nome"]} for i in fora]
        incluidos += [{"ficha": numero, "exercicio": i["nome"]} for i in dentro]
        for antes, depois in pares:
            for campo in CAMPOS_COMPARADOS:
                if antes[campo] != depois[campo]:
                    alterados.append(
                        {
                            "ficha": numero,
                            "exercicio": antes["nome"],
                            "campo": campo,
                            "de": "" if antes[campo] is None else str(antes[campo]),
                            "para": "" if depois[campo] is None else str(depois[campo]),
                        }
                    )
            if antes["observacao"] != depois["observacao"]:
                observacoes_mudadas += 1
        # a ordem dos exercícios que ficaram: compara a sequência dos ids dos pares com a ordem em que estavam no rascunho
        lugar_no_final = {id(item): n for n, item in enumerate(do_final["itens"])}
        sequencia_final = [d["id"] for _, d in sorted(pares, key=lambda par: lugar_no_final[id(par[1])])]
        sequencia_ia = [a["id"] for a, _ in pares]
        if sequencia_final != sequencia_ia:
            ordem_mudada += 1
    cortados = 0
    for lista in (tirados, incluidos, alterados):
        if len(lista) > MAXIMO_DE_ITENS_POR_LISTA:
            cortados += len(lista) - MAXIMO_DE_ITENS_POR_LISTA
            del lista[MAXIMO_DE_ITENS_POR_LISTA:]
    return {
        "fichas": {"ia": len(ia), "final": len(final)},
        "exercicios": {"ia": sum(len(f["itens"]) for f in ia), "final": sum(len(f["itens"]) for f in final)},
        "mantidos": mantidos,
        "tirados": tirados,
        "incluidos": incluidos,
        "alterados": alterados,
        "observacoes_mudadas": observacoes_mudadas,
        "fichas_com_ordem_mudada": ordem_mudada,
        "fichas_renomeadas": renomeadas,
        "cortados": cortados,
    }


def registrar_correcao(conn: sqlite3.Connection, aluno_id: int, pedido_id: int, treino_id: int, agora: datetime | None = None) -> bool:
    """O professor acabou de salvar o treino `treino_id` do aluno a partir do rascunho `pedido_id`: guarda o que ele mudou.

    Devolve True se registrou, False se não havia o que registrar (rascunho apagado, de outro aluno, ou já registrado).
    Não confia no navegador: o treino comparado é lido do banco, e precisa ser do mesmo aluno."""
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
        retorno = resultado["_retorno"]
        if retorno.get("corrigido"):
            conn.rollback()
            return False
        mudancas = comparar(resultado["treino"].get("fichas"), treino["fichas"])
        nota = retorno.get("nota") if retorno.get("nota") in NOTAS else None
        _inserir(conn, agora, "correcao", retorno, nota, None, mudancas)
        retorno["corrigido"] = True
        _guardar(conn, pedido_id, resultado)
        conn.commit()
        return True
    except BaseException:
        conn.rollback()
        raise


def registrar_correcao_sem_falhar(conn: sqlite3.Connection, aluno_id: int, pedido_id: int, treino_id: int) -> bool:
    """Como `registrar_correcao`, mas NUNCA levanta erro: o treino já foi salvo e o registro é um extra. Se falhar, só vai para o log."""
    try:
        return registrar_correcao(conn, aluno_id, pedido_id, treino_id)
    except Exception:  # nada aqui pode estragar o "Salvar treino" do professor
        log.exception("Não consegui registrar a correção do rascunho %s", pedido_id)
        return False


# ------------------------------------------------------------------ o relatório (terminal do servidor)


def _linhas(conn: sqlite3.Connection, mes: str | None) -> list[sqlite3.Row]:
    if mes is None:
        return conn.execute("SELECT * FROM ia_retorno ORDER BY id").fetchall()
    return conn.execute("SELECT * FROM ia_retorno WHERE dia LIKE ? ORDER BY id", (mes + "-%",)).fetchall()


def _porcentagem(parte: int, total: int) -> str:
    return f"{round(100 * parte / total)}%" if total else "-"


def _sem_mudancas(m: dict) -> bool:
    """A correção em que o professor salvou exatamente o que a IA fez."""
    return (
        not (m.get("tirados") or m.get("incluidos") or m.get("alterados") or m.get("cortados"))
        and not (m.get("fichas_com_ordem_mudada") or m.get("observacoes_mudadas") or m.get("fichas_renomeadas"))
        and m.get("fichas", {}).get("ia") == m.get("fichas", {}).get("final")
    )


def _mudancas(linha: sqlite3.Row) -> dict:
    try:
        valor = json.loads(linha["mudancas"] or "{}")
    except ValueError:
        return {}
    return valor if isinstance(valor, dict) else {}


def relatorio(conn: sqlite3.Connection, mes: str | None = None) -> str:
    """O relatório em texto simples (para o Thiago ler ou colar no Claude). `mes` = 'AAAA-MM' para um mês só; None = tudo."""
    linhas = _linhas(conn, mes)
    avaliacoes = [l for l in linhas if l["tipo"] == "avaliacao"]
    correcoes = [l for l in linhas if l["tipo"] == "correcao"]
    saida = [f"RETORNO DOS PROFESSORES SOBRE O ROBÔ DE TREINO ({'mês ' + mes if mes else 'tudo o que foi registrado'})", ""]
    if not linhas:
        saida.append("Nada registrado ainda neste período.")
        return "\n".join(saida)
    dias = sorted({l["dia"] for l in linhas})
    saida.append(f"Período com registro: {dias[0]} a {dias[-1]}. Avaliações: {len(avaliacoes)}. Treinos salvos a partir de rascunho: {len(correcoes)}.")
    if len(correcoes) < 10:
        saida.append("ATENÇÃO: menos de 10 treinos salvos neste período. É pouco para concluir qualquer coisa: trate o que segue como pista, não como regra.")

    saida += ["", "== Avaliações dos professores =="]
    contagem = Counter(l["nota"] for l in avaliacoes)
    for nota, rotulo in NOTAS.items():
        saida.append(f"- {rotulo}: {contagem[nota]} ({_porcentagem(contagem[nota], len(avaliacoes))})")
    grupos: dict = {}
    for l in avaliacoes:
        grupos.setdefault((l["objetivo"], l["nivel"]), Counter())[l["nota"]] += 1
    if grupos:
        saida.append("Por objetivo e nível (serviu / com ajustes / não serviu):")
        for (objetivo, nivel), c in sorted(grupos.items()):
            saida.append(f"- {objetivo}, {nivel}: {c['serviu']} / {c['com_ajustes']} / {c['nao_serviu']}")
    por_regra = {}
    for l in avaliacoes:
        por_regra.setdefault(l["regras"], Counter())[l["nota"]] += 1
    if len(por_regra) > 1:
        saida.append("Por versão das regras da IA (serviu / com ajustes / não serviu):")
        for regra, c in sorted(por_regra.items()):
            saida.append(f"- {regra}: {c['serviu']} / {c['com_ajustes']} / {c['nao_serviu']}")

    saida += ["", "== O que os professores mudaram antes de salvar =="]
    if not correcoes:
        saida.append("Nenhum treino salvo a partir de rascunho neste período.")
    else:
        todas = [_mudancas(l) for l in correcoes]
        sem_mudanca = sum(1 for m in todas if _sem_mudancas(m))
        total_ia = sum(m.get("exercicios", {}).get("ia", 0) for m in todas)
        tirados = Counter(i["exercicio"] for m in todas for i in m.get("tirados", []))
        incluidos = Counter(i["exercicio"] for m in todas for i in m.get("incluidos", []))
        saida.append(f"- Salvos exatamente como a IA fez: {sem_mudanca} de {len(correcoes)} ({_porcentagem(sem_mudanca, len(correcoes))})")
        saida.append(
            f"- Exercícios que a IA pôs: {total_ia}; tirados pelos professores: {sum(tirados.values())} ({_porcentagem(sum(tirados.values()), total_ia)}); "
            f"incluídos por eles: {sum(incluidos.values())}"
        )
        saida.append(f"- Treinos em que a ordem dos exercícios mudou: {sum(1 for m in todas if m.get('fichas_com_ordem_mudada'))}")
        saida.append(f"- Treinos com número de fichas diferente do da IA: {sum(1 for m in todas if m.get('fichas', {}).get('ia') != m.get('fichas', {}).get('final'))}")
        if tirados:
            saida.append("Exercícios mais tirados pelos professores (vezes):")
            saida += [f"  - {nome}: {n}" for nome, n in tirados.most_common(10)]
        if incluidos:
            saida.append("Exercícios mais incluídos pelos professores (vezes):")
            saida += [f"  - {nome}: {n}" for nome, n in incluidos.most_common(10)]
        campos = Counter(a["campo"] for m in todas for a in m.get("alterados", []))
        if campos:
            saida.append("Campos corrigidos (vezes): " + ", ".join(f"{ROTULOS_DOS_CAMPOS.get(c, c)} {n}" for c, n in campos.most_common()))
            trocas = Counter((a["campo"], a["de"], a["para"]) for m in todas for a in m.get("alterados", []))
            saida.append("Trocas mais comuns (campo: IA -> professor):")
            saida += [
                f"  - {ROTULOS_DOS_CAMPOS.get(c, c)}: {de or 'vazio'} -> {para or 'vazio'} ({n}x)"
                for (c, de, para), n in trocas.most_common(10)
            ]
        cortes = sum(m.get("cortados", 0) for m in todas)
        if cortes:
            saida.append(f"(Alguns treinos tiveram mudanças demais e só {MAXIMO_DE_ITENS_POR_LISTA} por lista foram guardadas; {cortes} ficaram de fora.)")
        notas_das_correcoes = Counter(l["nota"] for l in correcoes if l["nota"])
        if notas_das_correcoes:
            saida.append("Nota dada pelos professores aos treinos que salvaram: " + ", ".join(f"{NOTAS[n]} {c}" for n, c in notas_das_correcoes.most_common()))

    motivos = [l for l in avaliacoes if l["motivo"]]
    saida += ["", f"== Motivos escritos pelos professores ({len(motivos)}) =="]
    if not motivos:
        saida.append("Nenhum.")
    for l in motivos:
        contexto = f"{l['objetivo']}, {l['nivel']}, {l['dias']} dias, {l['minutos']} min" + (f", fila {l['fila']}" if l["fila"] else "") + (", com observações" if l["com_observacoes"] else "")
        saida.append(f"- [{NOTAS[l['nota']]}; {l['dia']}; {contexto}] {l['motivo']}")

    saida += [
        "",
        "Como usar: leia primeiro as notas e os motivos, depois os exercícios mais tirados. Só vire regra o que se repete em vários treinos e",
        "faz sentido para um professor de musculação; uma ou duas ocorrências soltas são opinião de um dia. Mudar a regra da IA é decisão do Thiago.",
    ]
    return "\n".join(saida)


def _caminho_do_banco_do_ambiente() -> Path:
    return Path(os.environ.get("GLORIAFIT_DB", "app.db"))


def principal(argumentos: list[str] | None = None) -> int:
    analisador = argparse.ArgumentParser(prog="python -m app.ia_retorno", description="Retorno dos professores sobre o robô de treino.")
    analisador.add_argument("comando", choices=["relatorio"])
    analisador.add_argument("--banco", type=Path, default=None, help="arquivo do banco (padrão: GLORIAFIT_DB ou app.db)")
    analisador.add_argument("--mes", default=None, help="só um mês, no formato AAAA-MM (padrão: tudo)")
    ns = analisador.parse_args(argumentos)
    if ns.mes is not None and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", ns.mes):
        print("Use --mes no formato AAAA-MM, por exemplo 2026-11.")
        return 1
    banco = ns.banco or _caminho_do_banco_do_ambiente()
    if not banco.is_file():
        print(f"Não achei o banco em {banco}.")
        return 1
    conn = db.conectar(banco)
    try:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'ia_retorno'").fetchone():
            print("Este banco ainda não tem a tabela do retorno (o app precisa subir uma vez com a versão nova).")
            return 1
        print(relatorio(conn, ns.mes))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(principal())
