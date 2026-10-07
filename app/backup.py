"""Cópia de segurança do banco de dados (SQLite).

Uso:
    python -m app.backup /dados/app.db /backups            # guarda as 14 cópias mais novas
    python -m app.backup /dados/app.db /backups --guardar 30

Por que não simplesmente copiar o arquivo: com o app rodando, o banco pode estar no meio de
uma gravação (e parte dos dados está no arquivo "-wal", ao lado). Copiar o arquivo "no
susto" pode dar uma cópia quebrada. Aqui se usa o recurso de cópia do próprio SQLite, que
entrega uma foto consistente, mesmo com o app em uso.

A cópia tem nome e CPF de alunos: o arquivo é criado só com permissão do dono (0600).

ATENÇÃO: uma cópia guardada no MESMO servidor não protege contra perder o servidor. Esta
etapa só produz a cópia; levá-la para FORA do servidor ainda depende de decidir o destino.
"""

import argparse
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

PADRAO_DO_NOME = re.compile(r"^app-\d{4}-\d{2}-\d{2}-\d{6}\.db$")
COPIAS_GUARDADAS_PADRAO = 14


class BackupFalhou(Exception):
    """Não deu para fazer uma cópia confiável. Nada de errado fica guardado no lugar dela."""


def fazer_backup(
    banco: str | Path,
    pasta: str | Path,
    guardar: int = COPIAS_GUARDADAS_PADRAO,
    agora: datetime | None = None,
) -> Path:
    """Copia o banco para `pasta`, confere a cópia e apaga as mais antigas. Devolve a cópia."""
    banco, pasta = Path(banco), Path(pasta)
    if guardar < 1:
        raise BackupFalhou("É preciso guardar pelo menos 1 cópia.")
    if not banco.is_file():
        # sqlite3.connect criaria um banco vazio em silêncio: a "cópia" seria um arquivo vazio.
        raise BackupFalhou(f"Não achei o banco em {banco}.")
    pasta.mkdir(parents=True, exist_ok=True)

    agora = agora or datetime.now(timezone.utc)
    destino = pasta / f"app-{agora:%Y-%m-%d-%H%M%S}.db"
    if destino.exists():
        raise BackupFalhou(f"Já existe {destino.name}: não vou sobrescrever uma cópia.")
    provisorio = destino.with_name(destino.name + ".parcial")
    provisorio.unlink(missing_ok=True)

    try:
        # Cria o arquivo já fechado para os outros usuários, antes de entrar qualquer dado.
        os.close(os.open(provisorio, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        origem = sqlite3.connect(banco)
        copia = sqlite3.connect(provisorio)
        try:
            origem.backup(copia)
            resultado = copia.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            copia.close()
            origem.close()
        if resultado != "ok":
            raise BackupFalhou(f"A cópia ficou com defeito ({resultado}); descartada.")
        provisorio.rename(destino)  # só ganha o nome definitivo depois de conferida
    except BaseException:
        provisorio.unlink(missing_ok=True)
        raise

    _apagar_as_mais_antigas(pasta, guardar)
    return destino


def _apagar_as_mais_antigas(pasta: Path, guardar: int) -> None:
    copias = sorted(p for p in pasta.iterdir() if p.is_file() and PADRAO_DO_NOME.match(p.name))
    for antiga in copias[:-guardar]:  # o nome tem a data: ordem alfabética = ordem de tempo
        antiga.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cópia de segurança do banco do app.")
    parser.add_argument("banco", help="o arquivo do banco (ex.: /dados/app.db)")
    parser.add_argument("pasta", help="a pasta onde as cópias ficam (ex.: /backups)")
    parser.add_argument("--guardar", type=int, default=COPIAS_GUARDADAS_PADRAO, help="quantas cópias manter")
    args = parser.parse_args(argv)
    try:
        copia = fazer_backup(args.banco, args.pasta, args.guardar)
    except (BackupFalhou, sqlite3.Error, OSError) as erro:
        print(f"Backup NÃO feito: {erro}", file=sys.stderr)
        return 1
    print(f"Backup feito: {copia.name} ({copia.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
