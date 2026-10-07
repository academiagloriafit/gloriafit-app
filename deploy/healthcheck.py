"""Verificação de saúde do contêiner (o Docker roda isto a cada 30 s).

Pergunta ao próprio app, por dentro do contêiner, se ele está de pé e enxerga o banco.
Importante: o app só aceita pedidos para o endereço dele (GLORIAFIT_DOMINIO), então a
pergunta precisa levar esse endereço no cabeçalho Host. Sem isso o app recusa a própria
verificação (erro 400), o Docker marca o contêiner como "doente" e o Traefik passa a
ignorá-lo: o site fica fora do ar com certificado de erro, sem nenhum aviso claro.
"""

import os
import sys
import urllib.request

PORTA = 8000


def montar_pedido(ambiente) -> urllib.request.Request:
    host = ambiente.get("GLORIAFIT_DOMINIO") or f"127.0.0.1:{PORTA}"
    return urllib.request.Request(f"http://127.0.0.1:{PORTA}/saude", headers={"Host": host})


def main() -> int:
    try:
        with urllib.request.urlopen(montar_pedido(os.environ), timeout=3) as resposta:
            return 0 if resposta.status == 200 else 1
    except Exception:  # qualquer falha (recusou, demorou, erro) = não está saudável
        return 1


if __name__ == "__main__":
    sys.exit(main())
