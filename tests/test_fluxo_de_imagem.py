"""Guardas do fluxo que constrói e publica a imagem Docker (.github/workflows/imagem.yml).

O fluxo roda sozinho no GitHub a cada envio para a "main". Estes testes travam o que seria
grave perder numa edição: permissões além do mínimo, ações de terceiros (que poderiam levar
o token embora) e a imagem sair sem passar pelos testes.
"""

from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
FLUXO = yaml.safe_load((RAIZ / ".github" / "workflows" / "imagem.yml").read_text(encoding="utf-8"))
TEXTO = (RAIZ / ".github" / "workflows" / "imagem.yml").read_text(encoding="utf-8")
PASSOS = FLUXO["jobs"]["imagem"]["steps"]
# No YAML 1.1 a palavra "on" vira True; aceita as duas formas.
GATILHOS = FLUXO.get("on", FLUXO.get(True))


def test_permissoes_sao_so_ler_codigo_e_escrever_o_pacote():
    assert FLUXO["permissions"] == {"contents": "read", "packages": "write"}


def test_so_usa_acoes_do_proprio_github():
    usadas = [p["uses"] for p in PASSOS if "uses" in p]

    assert usadas  # tem pelo menos o checkout
    assert all(u.startswith("actions/") for u in usadas), usadas


def test_dispara_so_em_envio_para_main_ou_a_mao_nunca_em_pedido_de_outra_pessoa():
    assert set(GATILHOS) == {"push", "workflow_dispatch"}
    assert GATILHOS["push"]["branches"] == ["main"]
    assert "pull_request_target" not in TEXTO and "pull_request" not in TEXTO


def test_so_o_token_automatico_e_usado_como_segredo():
    import re

    segredos = set(re.findall(r"secrets\.([A-Z_]+)", TEXTO))

    assert segredos == {"GITHUB_TOKEN"}


def test_testes_rodam_antes_de_construir_e_publicar():
    comandos = [p.get("run", "") for p in PASSOS]
    ordem = {nome: i for i, nome in enumerate(p.get("name", "") for p in PASSOS)}

    assert ordem["Testes"] < ordem["Construir a imagem"] < ordem["Publicar a imagem"]
    assert any("pytest" in c for c in comandos)


def test_imagem_leva_o_commit_como_etiqueta_e_aponta_para_o_repositorio():
    assert "github.sha" in TEXTO
    assert "org.opencontainers.image.source=https://github.com/${{ github.repository }}" in TEXTO
    assert FLUXO["jobs"]["imagem"]["env"]["IMAGEM"] == "ghcr.io/${{ github.repository_owner }}/gloriafit-app"


def test_token_nao_e_escrito_direto_no_comando():
    # Segredo passa por variável de ambiente, nunca colado na linha de comando (apareceria no registro).
    for passo in PASSOS:
        assert "secrets." not in passo.get("run", ""), passo.get("name")
