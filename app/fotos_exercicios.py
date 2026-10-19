"""Fotos de "Como fazer" dos exercícios.

Cada exercício conferido tem um par de fotos (posição inicial e final) em `app/static/exercicios/<nome>_0.jpg` e
`<nome>_1.jpg`. O mapa "nome do exercício -> nome do par" fica em `fotos_exercicios.json`. Quem muda o mapa é um
commit, não um clique na tela: assim as fotos viajam na imagem do servidor e não precisam de migração do banco.

Fotos: base aberta free-exercise-db (domínio público, licença Unlicense), recortadas e ampliadas.
Exercício que não está no mapa simplesmente não mostra o botão.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

from app.texto import nome_para_exibir

PASTA_DAS_FOTOS = Path(__file__).resolve().parent / "static" / "exercicios"
ARQUIVO_DO_MAPA = Path(__file__).resolve().parent / "fotos_exercicios.json"
_NOME_VALIDO = re.compile(r"[A-Za-z0-9_-]{1,80}")


def _chave(nome: str) -> str:
    """O nome como o aluno o vê (sem o número da máquina do começo, "(15) "), sem diferença de maiúscula."""
    return nome_para_exibir(nome.strip()).strip().casefold()


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
