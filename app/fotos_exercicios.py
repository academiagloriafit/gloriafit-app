"""Fotos de "Como fazer" dos exercícios.

Cada exercício conferido tem um par de fotos (posição inicial e final) em `app/static/exercicios/<nome>_0.jpg` e
`<nome>_1.jpg`. O mapa "nome do exercício -> nome do par" fica em `fotos_exercicios.json`. Quem muda o mapa é um
commit, não um clique na tela: assim as fotos viajam na imagem do servidor e não precisam de migração do banco.

Fotos: base aberta free-exercise-db (domínio público, licença Unlicense), recortadas e ampliadas.
Exercício que não está no mapa simplesmente não mostra o botão.
"""

import json
import re
import sqlite3
from functools import lru_cache
from pathlib import Path

from app.texto import nome_para_exibir, tirar_apagado

PASTA_DAS_FOTOS = Path(__file__).resolve().parent / "static" / "exercicios"
ARQUIVO_DO_MAPA = Path(__file__).resolve().parent / "fotos_exercicios.json"
_NOME_VALIDO = re.compile(r"[A-Za-z0-9_-]{1,80}")


def _chave(nome: str) -> str:
    """O nome como o aluno o vê (sem o número da máquina do começo, "(15) " e sem o APAGADO do fim), sem diferença de maiúscula."""
    return tirar_apagado(nome_para_exibir(nome.strip())).strip().casefold()


@lru_cache(maxsize=1)
def _mapa() -> dict[str, str]:
    """{nome do exercício como o aluno o vê: nome do par de fotos}. Lido uma vez só.

    O mapa usa os nomes do quadro de exercícios ("(15) CADEIRA ABDUTORA"); a tela e o treino do aluno usam o
    nome sem o número. Dois nomes que viram o mesmo com fotos diferentes seriam ambíguos: o app não sobe.
    """
    mapa: dict[str, str] = {}
    for nome, foto in json.loads(ARQUIVO_DO_MAPA.read_text(encoding="utf-8")).items():
        chave = _chave(nome)
        if mapa.setdefault(chave, foto) != foto:
            raise ValueError(f"fotos_exercicios.json: '{nome}' vira '{chave}' e já tem outra foto")
    return mapa


def foto_do_exercicio(nome: object) -> str | None:
    """O nome do par de fotos do exercício, ou None se ele não tem."""
    if not isinstance(nome, str):
        return None
    foto = _mapa().get(_chave(nome))
    return foto if foto and _NOME_VALIDO.fullmatch(foto) else None


PASTA_DAS_ILUSTRACOES = Path(__file__).resolve().parent / "static" / "ilustracoes"
# Exercícios que não estão no mapa das fotos mas são o MESMO movimento de um desenho que já existe (outro nome, número da
# máquina, isometria, pirâmide, "nova/preta"), ou são combinados ("ROSCA POLIA + TRÍCEPS POLIA": um desenho de cada parte).
# Ligados a partir do quadro de exercícios em 12/11/2026; variação que muda o desenho (unilateral, articulada, pegada...) NÃO entra.
ARQUIVO_DAS_ILUSTRACOES = Path(__file__).resolve().parent / "ilustracoes_exercicios.json"
MAXIMO_DE_IMAGENS = 3  # combinado com muitas partes: só as primeiras


@lru_cache(maxsize=1)
def _mapa_das_ilustracoes() -> dict[str, tuple[str, ...]]:
    """{nome do exercício como o aluno o vê: (desenho, desenho...)}. Dois nomes iguais com desenhos diferentes: o app não sobe."""
    mapa: dict[str, tuple[str, ...]] = {}
    for nome, desenhos in json.loads(ARQUIVO_DAS_ILUSTRACOES.read_text(encoding="utf-8")).items():
        chave = _chave(nome)
        valor = tuple(desenhos)
        if mapa.setdefault(chave, valor) != valor:
            raise ValueError(f"ilustracoes_exercicios.json: '{nome}' vira '{chave}' e já tem outros desenhos")
    return mapa


def _caminho_do_desenho(desenho: str) -> str | None:
    if not _NOME_VALIDO.fullmatch(desenho):
        return None
    if (PASTA_DAS_ILUSTRACOES / f"{desenho}.jpg").is_file():
        return f"ilustracoes/{desenho}.jpg"
    if (PASTA_DAS_FOTOS / f"{desenho}_0.jpg").is_file():
        return f"exercicios/{desenho}_0.jpg"
    return None


def miniaturas_do_exercicio(nome: object) -> list[str]:
    """As imagens do exercício (caminhos dentro de /static), na ordem; lista vazia se não tem nenhuma.

    Primeiro o mapa das fotos (um desenho); senão o mapa das ilustrações (um ou mais desenhos, para os combinados).
    Cada desenho: a ilustração do Canva (static/ilustracoes/<desenho>.jpg); se ainda não existe, a foto de "como fazer".
    """
    if not isinstance(nome, str):
        return []
    foto = foto_do_exercicio(nome)
    desenhos = (foto,) if foto else _mapa_das_ilustracoes().get(_chave(nome), ())
    caminhos = [c for c in (_caminho_do_desenho(d) for d in desenhos) if c]
    return list(dict.fromkeys(caminhos))[:MAXIMO_DE_IMAGENS]


def miniatura_do_exercicio(nome: object) -> str | None:
    """A primeira imagem do exercício, ou None."""
    imagens = miniaturas_do_exercicio(nome)
    return imagens[0] if imagens else None


def fotos_por_id(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """{id do exercício (texto): [caminhos das imagens]} de todos os exercícios que têm imagem.

    A tela de lançar treino põe a imagem pequena ao lado de cada exercício da ficha. Os exercícios chegam lá por vários
    caminhos (lista, importar, IA, fila, editar), mas todos trazem o id: por isso o mapa é por id.
    """
    fotos = {}
    for exercicio_id, nome in conn.execute("SELECT id, nome FROM exercicio"):
        imagens = miniaturas_do_exercicio(nome)
        if imagens:
            fotos[str(exercicio_id)] = imagens
    return fotos
