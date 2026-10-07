# Imagem do app Glória Fit para o servidor (um contêiner só, atrás do Traefik).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt "gunicorn==26.2.0"

COPY app ./app
COPY dados ./dados
COPY deploy/entrypoint.sh ./entrypoint.sh

# Roda sem ser administrador: se alguém achar uma falha no app, não chega no sistema inteiro.
# /dados guarda o banco (volume) e /backups as cópias de segurança (volume).
RUN useradd --system --uid 10001 --no-create-home gloriafit \
    && mkdir /dados /backups \
    && chown gloriafit /dados /backups \
    && chmod +x entrypoint.sh
USER gloriafit

ENV GLORIAFIT_DB=/dados/app.db \
    GLORIAFIT_ATRAS_DE_PROXY=1

VOLUME ["/dados", "/backups"]
EXPOSE 8000

# O Docker marca o contêiner como "saudável" quando /saude responde.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/saude', timeout=3).status == 200 else 1)"

CMD ["./entrypoint.sh"]
