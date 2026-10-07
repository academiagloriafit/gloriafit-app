"""Cópia de segurança diária do banco, sozinha (roda num contêiner à parte, ver deploy/docker-compose.yml).

Uso:
    python -m app.backup_agendado                # fica rodando: uma cópia por dia, às 03:00 de Vila Velha
    python -m app.backup_agendado --verificar    # sai com 0 se a cópia mais nova é recente (usado pelo Docker)

O que faz:
  * Ao ligar, se a cópia mais nova tem mais de 20 horas (ou não há nenhuma), faz uma na hora.
    O limite existe para um contêiner que reinicia em loop não encher a pasta de cópias iguais
    e empurrar para fora as antigas (só as 30 mais novas ficam).
  * Depois, todo dia às 03:00 (horário de Vila Velha: academia fechada, app quase parado).
  * Se uma cópia falhar, avisa no registro do contêiner e tenta de novo em 1 hora, até conseguir.

A cópia em si (consistente, conferida, só o dono lê) é de app/backup.py.

ATENÇÃO: as cópias ficam no MESMO servidor (volume `app-backups`). Isto protege contra erro
(apagar aluno sem querer, banco corrompido), não contra perder o servidor inteiro. Decisão do
Thiago em 07/10/2026: manter só no servidor; o backup semanal do VPS na Hostinger existe à parte.
"""

import argparse
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.alunos import FUSO_DA_ACADEMIA
from app.backup import BackupFalhou, fazer_backup

HORA_DO_BACKUP = 3  # no horário de Vila Velha
COPIAS_GUARDADAS = 30  # um mês de cópias diárias
IDADE_MAXIMA_NA_PARTIDA = timedelta(hours=20)  # mais velha que isto: faz uma ao ligar
IDADE_MAXIMA_NA_VERIFICACAO = timedelta(hours=30)  # 24 h do ciclo + folga para uma nova tentativa
ESPERA_APOS_FALHA = timedelta(hours=1)

_DATA_NO_NOME = re.compile(r"^app-(\d{4}-\d{2}-\d{2}-\d{6})\.db$")


def proximo_horario(agora: datetime) -> datetime:
    """O próximo 03:00 de Vila Velha depois de `agora` (sempre no futuro, nunca igual a `agora`)."""
    local = agora.astimezone(FUSO_DA_ACADEMIA)
    alvo = local.replace(hour=HORA_DO_BACKUP, minute=0, second=0, microsecond=0)
    if alvo <= local:
        alvo = (local + timedelta(days=1)).replace(hour=HORA_DO_BACKUP, minute=0, second=0, microsecond=0)
    return alvo


def copia_mais_nova(pasta: str | Path) -> datetime | None:
    """Quando a cópia mais nova foi feita (lido do nome do arquivo, que é em UTC), ou None."""
    pasta = Path(pasta)
    if not pasta.is_dir():
        return None
    datas = []
    for arquivo in pasta.iterdir():
        achou = _DATA_NO_NOME.match(arquivo.name) if arquivo.is_file() else None
        if achou:
            datas.append(datetime.strptime(achou.group(1), "%Y-%m-%d-%H%M%S").replace(tzinfo=timezone.utc))
    return max(datas) if datas else None


def esta_velha(pasta: str | Path, agora: datetime, idade_maxima: timedelta) -> bool:
    nova = copia_mais_nova(pasta)
    return nova is None or agora - nova > idade_maxima


def verificar(pasta: str | Path, agora: datetime | None = None) -> tuple[bool, str]:
    """Para o Docker: (True, ...) se há cópia recente; (False, motivo) se não."""
    agora = agora or datetime.now(timezone.utc)
    nova = copia_mais_nova(pasta)
    if nova is None:
        return False, "Nenhuma cópia de segurança encontrada."
    if agora - nova > IDADE_MAXIMA_NA_VERIFICACAO:
        horas = int((agora - nova).total_seconds() // 3600)
        return False, f"A cópia mais nova tem {horas} horas (o esperado é uma por dia)."
    return True, f"Cópia mais nova de {nova:%d/%m/%Y %H:%M} UTC."


def _tentar(banco, pasta, guardar, fazer) -> bool:
    try:
        copia = fazer(banco, pasta, guardar)
    except (BackupFalhou, sqlite3.Error, OSError) as erro:
        print(f"BACKUP FALHOU: {erro}", file=sys.stderr, flush=True)
        return False
    print(f"Backup feito: {copia.name} ({copia.stat().st_size} bytes)", flush=True)
    return True


def rodar(
    banco,
    pasta,
    guardar: int = COPIAS_GUARDADAS,
    relogio=lambda: datetime.now(timezone.utc),
    dormir=time.sleep,
    fazer=fazer_backup,
    ciclos: int | None = None,
) -> None:
    """Fica fazendo as cópias. `ciclos` (só para testes) limita quantas esperas diárias rodar."""
    if esta_velha(pasta, relogio(), IDADE_MAXIMA_NA_PARTIDA):
        while not _tentar(banco, pasta, guardar, fazer):
            dormir(ESPERA_APOS_FALHA.total_seconds())
    feitos = 0
    while ciclos is None or feitos < ciclos:
        agora = relogio()
        espera = proximo_horario(agora) - agora
        print(f"Próxima cópia em {int(espera.total_seconds() // 60)} minutos.", flush=True)
        dormir(espera.total_seconds())
        while not _tentar(banco, pasta, guardar, fazer):
            dormir(ESPERA_APOS_FALHA.total_seconds())
        feitos += 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cópia de segurança diária do banco do app.")
    parser.add_argument("--banco", default="/dados/app.db")
    parser.add_argument("--pasta", default="/backups")
    parser.add_argument("--guardar", type=int, default=COPIAS_GUARDADAS)
    parser.add_argument("--verificar", action="store_true", help="só confere se há cópia recente")
    args = parser.parse_args(argv)
    if args.guardar < 1:
        parser.error("--guardar precisa ser pelo menos 1")
    if args.verificar:
        ok, mensagem = verificar(args.pasta)
        print(mensagem)
        return 0 if ok else 1
    rodar(args.banco, args.pasta, args.guardar)
    return 0  # só chega aqui nos testes (o laço de verdade não termina)


if __name__ == "__main__":
    sys.exit(main())
