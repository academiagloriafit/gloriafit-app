"""Testes do comando python -m app.dispositivos (gerar código, listar, revogar)."""

import re
import sqlite3

import pytest

from app import acesso, dispositivos
from app.db import conectar, criar_tabelas


@pytest.fixture
def banco(tmp_path):
    caminho = tmp_path / "cli.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.close()
    return caminho


def _comando(comando, banco, *resto):
    # --banco depois do subcomando, como a pessoa digitaria
    return dispositivos.main([comando, "--banco", str(banco), *resto])


def test_codigo_mostra_o_codigo_o_nome_e_a_validade_em_horario_de_brasilia(banco, capsys):
    resultado = _comando("codigo", banco, "--nome", "Computador da recepção")

    saida = capsys.readouterr().out
    assert resultado == 0
    assert 'Código para "Computador da recepção"' in saida
    assert re.search(r"^    [A-HJKMNP-Z2-9]{5}-[A-HJKMNP-Z2-9]{5}$", saida, re.MULTILINE)
    assert re.search(r"Vale até \d\d/\d\d/\d{4} \d\d:\d\d \(horário de Brasília\)", saida)
    assert "/autorizar" in saida


def test_o_codigo_impresso_autoriza_um_computador_com_aquele_nome(banco, capsys):
    _comando("codigo", banco, "--nome", "Computador dos professores")
    codigo = re.search(r"^    (\S+)$", capsys.readouterr().out, re.MULTILINE).group(1)

    conn = conectar(banco)
    autorizacao = acesso.autorizar(conn, codigo)
    conn.close()

    assert autorizacao.nome == "Computador dos professores"


def test_nome_e_obrigatorio(banco, capsys):
    with pytest.raises(SystemExit) as erro:
        _comando("codigo", banco)

    assert erro.value.code == 2
    assert "--nome" in capsys.readouterr().err


@pytest.mark.parametrize("nome", ["", "   ", "x" * 41])
def test_nome_invalido_devolve_erro_e_nao_gera_codigo(banco, capsys, nome):
    resultado = _comando("codigo", banco, "--nome", nome)

    assert resultado == 2
    assert capsys.readouterr().err.startswith("Erro:")
    conn = conectar(banco)
    assert conn.execute("SELECT COUNT(*) FROM codigo_de_autorizacao").fetchone()[0] == 0
    conn.close()


def test_listar_sem_computadores(banco, capsys):
    assert _comando("listar", banco) == 0

    assert "Nenhum computador autorizado ainda." in capsys.readouterr().out


def test_listar_mostra_numero_nome_e_situacao_dos_dois_computadores(banco, capsys):
    conn = conectar(banco)
    for nome in ("Computador dos professores", "Computador da recepção"):
        acesso.autorizar(conn, acesso.gerar_codigo(conn, nome).codigo)
    acesso.revogar(conn, 2)
    conn.close()

    assert _comando("listar", banco) == 0

    linhas = capsys.readouterr().out.strip().splitlines()
    assert len(linhas) == 2
    assert re.match(r"\s*1\s+Computador dos professores\s+ativo\s+autorizado em ", linhas[0])
    assert re.match(r"\s*2\s+Computador da recepção\s+REVOGADO\s+autorizado em ", linhas[1])


def test_listar_nunca_mostra_token_nem_hash(banco, capsys):
    conn = conectar(banco)
    autorizacao = acesso.autorizar(conn, acesso.gerar_codigo(conn, "Teste").codigo)
    hash_guardado = conn.execute("SELECT token_hash FROM dispositivo").fetchone()[0]
    conn.close()

    _comando("listar", banco)

    saida = capsys.readouterr().out
    assert autorizacao.token not in saida and hash_guardado not in saida


def test_revogar_tira_o_acesso(banco, capsys):
    conn = conectar(banco)
    autorizacao = acesso.autorizar(conn, acesso.gerar_codigo(conn, "Teste").codigo)

    assert _comando("revogar", banco, "1") == 0

    assert "revogado" in capsys.readouterr().out
    assert acesso.identificar(conn, autorizacao.token) is None
    conn.close()


def test_revogar_numero_que_nao_existe_ou_ja_revogado_devolve_1(banco, capsys):
    assert _comando("revogar", banco, "7") == 1
    assert "Não há computador ativo" in capsys.readouterr().err


def test_revogar_exige_numero(banco, capsys):
    with pytest.raises(SystemExit) as erro:
        _comando("revogar", banco, "abc")

    assert erro.value.code == 2


def test_banco_inexistente_explica_e_nao_cria_arquivo(tmp_path):
    caminho = tmp_path / "nao_existe.db"

    with pytest.raises(SystemExit) as erro:
        _comando("listar", caminho)

    assert "não encontrado" in str(erro.value)
    assert not caminho.exists()


def test_banco_de_versao_antiga_explica(tmp_path):
    antigo = tmp_path / "antigo.db"
    conexao = sqlite3.connect(antigo)
    conexao.executescript("CREATE TABLE treino (id INTEGER PRIMARY KEY); PRAGMA user_version = 3;")
    conexao.close()

    with pytest.raises(SystemExit) as erro:
        _comando("listar", antigo)

    assert "versão 3" in str(erro.value)


def test_banco_vazio_sem_tabelas_explica(tmp_path):
    vazio = tmp_path / "vazio.db"
    sqlite3.connect(vazio).close()

    with pytest.raises(SystemExit) as erro:
        _comando("listar", vazio)

    assert "ainda não tem as tabelas" in str(erro.value)


def test_banco_pode_vir_antes_do_comando(banco, capsys):
    assert dispositivos.main(["--banco", str(banco), "codigo", "--nome", "Teste"]) == 0

    conn = conectar(banco)
    assert conn.execute("SELECT COUNT(*) FROM codigo_de_autorizacao").fetchone()[0] == 1
    conn.close()


def test_banco_depois_do_comando_vale_mesmo_com_a_variavel_de_ambiente_diferente(banco, monkeypatch, tmp_path):
    monkeypatch.setenv("GLORIAFIT_DB", str(tmp_path / "outro.db"))

    assert _comando("codigo", banco, "--nome", "Teste") == 0


def test_usa_a_variavel_de_ambiente_quando_nao_recebe_o_banco(banco, monkeypatch, capsys):
    monkeypatch.setenv("GLORIAFIT_DB", str(banco))

    assert dispositivos.main(["listar"]) == 0

    assert "Nenhum computador" in capsys.readouterr().out
