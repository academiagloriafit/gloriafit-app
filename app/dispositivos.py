"""Administra os computadores autorizados a abrir a área do professor.

Roda NO SERVIDOR (quem tem acesso ao servidor é quem pode autorizar computadores):

    python -m app.dispositivos codigo --nome "Computador dos professores"
    python -m app.dispositivos codigo --nome "Computador da recepção"
    python -m app.dispositivos listar
    python -m app.dispositivos revogar 2

`codigo` imprime um código de uso único (vale 15 minutos). No computador, abra o
endereço /autorizar do app e digite o código. Cada computador usa o seu próprio código.
`--banco caminho.db` escolhe o arquivo do banco (padrão: variável GLORIAFIT_DB ou app.db).
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from app import acesso, db
from app.alunos import FUSO_DA_ACADEMIA

_SITUACAO = {"ativo": "ativo", "revogado": "REVOGADO", "vencido": "VENCIDO (parado há muito tempo)"}


def _hora_local(momento: datetime) -> str:
    return momento.astimezone(FUSO_DA_ACADEMIA).strftime("%d/%m/%Y %H:%M")


def _abrir_banco(caminho: Path):
    if not caminho.is_file():
        raise SystemExit(
            f"Banco de dados não encontrado em '{caminho}'. Use --banco para indicar o arquivo certo."
        )
    conn = db.conectar(caminho)
    try:
        db.migrar(conn)
        db.verificar_versao(conn)
        tem_tabela = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'dispositivo'"
        ).fetchone()
    except db.BancoDesatualizado as erro:
        conn.close()
        raise SystemExit(str(erro)) from None
    if not tem_tabela:
        conn.close()
        raise SystemExit(
            f"O banco '{caminho}' ainda não tem as tabelas do app. Crie-o antes com: "
            "python -m app.importar_exercicios dados/quadro_exercicios_v2.xlsx app.db"
        )
    return conn


def _montar_parser() -> argparse.ArgumentParser:
    # --banco pode vir antes ou depois do comando. Nos subcomandos o padrão é SUPPRESS:
    # sem isso o padrão deles apagaria o valor dado antes do comando.
    comum = argparse.ArgumentParser(add_help=False)
    comum.add_argument(
        "--banco", default=argparse.SUPPRESS, help="arquivo do banco (padrão: variável GLORIAFIT_DB ou app.db)"
    )

    parser = argparse.ArgumentParser(
        prog="python -m app.dispositivos",
        description="Administra os computadores autorizados a abrir a área do professor.",
    )
    parser.add_argument(
        "--banco",
        default=os.environ.get("GLORIAFIT_DB", "app.db"),
        help="arquivo do banco (padrão: variável GLORIAFIT_DB ou app.db)",
    )
    comandos = parser.add_subparsers(dest="comando", required=True)

    gerar = comandos.add_parser("codigo", parents=[comum], help="gera um código para autorizar um computador")
    gerar.add_argument(
        "--nome", required=True, help='nome do computador, por exemplo "Computador da recepção" (até 40 letras)'
    )
    comandos.add_parser("listar", parents=[comum], help="mostra os computadores já autorizados")
    revogar = comandos.add_parser("revogar", parents=[comum], help="tira a autorização de um computador")
    revogar.add_argument("id", type=int, help="o número que aparece em 'listar'")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _montar_parser().parse_args(argv)
    conn = _abrir_banco(Path(args.banco))
    try:
        if args.comando == "codigo":
            try:
                gerado = acesso.gerar_codigo(conn, args.nome)
            except acesso.NomeInvalido as erro:
                print(f"Erro: {erro}", file=sys.stderr)
                return 2
            print(f'Código para "{gerado.nome}":\n')
            print(f"    {gerado.codigo}\n")
            print(f"Vale até {_hora_local(gerado.expira_em)} (horário de Brasília) e só funciona uma vez.")
            print("No computador, abra o endereço /autorizar do app e digite esse código.")
        elif args.comando == "listar":
            linhas = acesso.listar(conn)
            if not linhas:
                print("Nenhum computador autorizado ainda.")
            for d in linhas:
                print(
                    f"{d['id']:>3}  {d['nome']:<40}  {_SITUACAO[d['situacao']]:<10}  "
                    f"autorizado em {_hora_local(d['criado_em'])}, último uso {_hora_local(d['ultimo_uso_em'])}"
                )
        else:  # revogar
            if acesso.revogar(conn, args.id):
                print(f"Computador {args.id} revogado: ele perde o acesso agora.")
            else:
                print(f"Não há computador ativo com o número {args.id} (veja 'listar').", file=sys.stderr)
                return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
