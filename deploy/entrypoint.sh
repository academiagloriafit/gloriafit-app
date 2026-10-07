#!/bin/sh
# Ponto de partida do contêiner: cria o banco na primeira vez e sobe o servidor (gunicorn).
set -eu

BANCO="${GLORIAFIT_DB:-/dados/app.db}"

if [ ! -f "$BANCO" ]; then
    echo "Banco novo em $BANCO: criando as tabelas e importando os exercícios..."
    python -m app.importar_exercicios dados/quadro_exercicios_v2.xlsx "$BANCO"
fi

# 2 processos: o servidor tem 1 vCPU e metade da memória já em uso por outros serviços.
# O registro de acessos grava só método, caminho (SEM o texto depois do "?", que pode ter
# CPF digitado na busca), código e tempo: nada de dado pessoal nos logs do Docker.
exec gunicorn \
    --bind 0.0.0.0:8000 \
    --workers "${GLORIAFIT_PROCESSOS:-2}" \
    --timeout 30 \
    --no-control-socket \
    --access-logfile - \
    --access-logformat '%(t)s "%(m)s %(U)s" %(s)s %(b)s %(L)ss' \
    "app.web:criar_app()"
