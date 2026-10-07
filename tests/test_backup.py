"""Cópia de segurança do banco (app/backup.py). Dados inventados."""

import os
import sqlite3
import stat
from datetime import datetime, timedelta, timezone

import pytest

from app.backup import BackupFalhou, fazer_backup, main
from app.db import conectar, criar_tabelas

AGORA = datetime(2026, 10, 7, 20, 30, 15, tzinfo=timezone.utc)


@pytest.fixture
def banco(tmp_path):
    caminho = tmp_path / "app.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.execute("INSERT INTO aluno (nome, cpf) VALUES ('MARIA TESTE', '11144477735')")
    conn.commit()
    conn.close()
    return caminho


def _nomes(pasta):
    return sorted(p.name for p in pasta.iterdir())


def test_a_copia_tem_os_mesmos_dados_e_nome_com_data_e_hora(banco, tmp_path):
    copia = fazer_backup(banco, tmp_path / "bk", agora=AGORA)

    assert copia.name == "app-2026-10-07-203015.db"
    conn = sqlite3.connect(copia)
    assert conn.execute("SELECT nome, cpf FROM aluno").fetchall() == [("MARIA TESTE", "11144477735")]
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_pega_tambem_o_que_ainda_esta_so_no_arquivo_wal(banco, tmp_path):
    # Com o banco aberto por outro processo, parte dos dados mora no "-wal": copiar o arquivo no susto perderia isso.
    aberto = conectar(banco)
    aberto.execute("INSERT INTO aluno (nome) VALUES ('SO NO WAL')")
    aberto.commit()
    assert os.path.exists(str(banco) + "-wal")

    copia = fazer_backup(banco, tmp_path / "bk", agora=AGORA)
    aberto.close()

    conn = sqlite3.connect(copia)
    assert conn.execute("SELECT COUNT(*) FROM aluno").fetchone()[0] == 2
    conn.close()


def test_a_copia_so_pode_ser_lida_pelo_dono(banco, tmp_path):
    copia = fazer_backup(banco, tmp_path / "bk", agora=AGORA)

    assert stat.S_IMODE(copia.stat().st_mode) == 0o600


def test_banco_que_nao_existe_nao_vira_copia_vazia(tmp_path):
    with pytest.raises(BackupFalhou, match="Não achei"):
        fazer_backup(tmp_path / "nao-existe.db", tmp_path / "bk", agora=AGORA)

    assert not (tmp_path / "nao-existe.db").exists()  # nem criou um banco vazio no lugar
    assert not (tmp_path / "bk").exists() or _nomes(tmp_path / "bk") == []


def test_guarda_so_as_mais_novas_e_nao_mexe_em_outros_arquivos(banco, tmp_path):
    pasta = tmp_path / "bk"
    pasta.mkdir()
    (pasta / "anotacao.txt").write_text("não é backup")
    (pasta / "app-velho.db").write_text("nome fora do padrão")
    for dias in range(5):
        fazer_backup(banco, pasta, guardar=3, agora=AGORA + timedelta(days=dias))

    assert _nomes(pasta) == [
        "anotacao.txt",
        "app-2026-10-09-203015.db",
        "app-2026-10-10-203015.db",
        "app-2026-10-11-203015.db",
        "app-velho.db",
    ]


def test_nao_sobrescreve_uma_copia_existente(banco, tmp_path):
    fazer_backup(banco, tmp_path / "bk", agora=AGORA)

    with pytest.raises(BackupFalhou, match="não vou sobrescrever"):
        fazer_backup(banco, tmp_path / "bk", agora=AGORA)


def test_guardar_zero_e_recusado_para_nao_apagar_tudo(banco, tmp_path):
    with pytest.raises(BackupFalhou):
        fazer_backup(banco, tmp_path / "bk", guardar=0, agora=AGORA)


def test_copia_com_defeito_e_descartada_e_nao_leva_o_nome_definitivo(banco, tmp_path, monkeypatch):
    class ConexaoComDefeito(sqlite3.Connection):
        def execute(self, sql, *args):
            if sql == "PRAGMA integrity_check":
                return super().execute("SELECT 'defeito de teste'")
            return super().execute(sql, *args)

    original = sqlite3.connect
    chamadas = []

    def conectar_falso(*args, **kw):
        chamadas.append(1)
        if len(chamadas) == 2:  # a 1ª conexão é a do banco, a 2ª é a da cópia
            kw["factory"] = ConexaoComDefeito
        return original(*args, **kw)

    monkeypatch.setattr("app.backup.sqlite3.connect", conectar_falso)

    with pytest.raises(BackupFalhou, match="defeito de teste"):
        fazer_backup(banco, tmp_path / "bk", agora=AGORA)

    assert _nomes(tmp_path / "bk") == []  # nem a cópia ruim nem o arquivo parcial ficaram


def test_linha_de_comando_faz_a_copia_e_diz_o_nome(banco, tmp_path, capsys):
    codigo = main([str(banco), str(tmp_path / "bk")])

    saida = capsys.readouterr().out
    assert codigo == 0
    assert "Backup feito: app-" in saida
    assert "MARIA" not in saida and "11144477735" not in saida


def test_linha_de_comando_com_banco_ausente_sai_com_erro(tmp_path, capsys):
    codigo = main([str(tmp_path / "nada.db"), str(tmp_path / "bk")])

    assert codigo == 1
    assert "Backup NÃO feito" in capsys.readouterr().err
