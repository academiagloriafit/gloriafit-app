"""Ajustes para rodar no servidor: atrás do proxy (HTTPS), HSTS, domínio fixo e banco em WAL.

O servidor de verdade (Traefik na frente, gunicorn atrás) só existe depois da publicação;
aqui os cabeçalhos que o Traefik manda são simulados.
"""

import sqlite3

import pytest

from app import acesso
from app.db import conectar, criar_tabelas
from app.web import HSTS_SEGUNDOS, criar_app

DOMINIO = "app.exemplo.com.br"
DO_PROXY = {"X-Forwarded-Proto": "https", "X-Forwarded-Host": DOMINIO, "X-Forwarded-For": "203.0.113.9"}


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "prod.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.execute("INSERT INTO aluno (nome, cpf) VALUES ('MARIA TESTE', '11144477735')")
    conn.commit()
    conn.close()
    return caminho


def _codigo(caminho):
    conn = conectar(caminho)
    try:
        return acesso.gerar_codigo(conn, "Computador de teste").codigo
    finally:
        conn.close()


def _autorizado_atras_do_proxy(caminho, monkeypatch, dominio=DOMINIO):
    monkeypatch.setenv("GLORIAFIT_ATRAS_DE_PROXY", "1")
    if dominio:
        monkeypatch.setenv("GLORIAFIT_DOMINIO", dominio)
    navegador = criar_app(caminho).test_client()
    resposta = navegador.post("/api/autorizar", json={"codigo": _codigo(caminho)}, headers={**DO_PROXY, "Origin": f"https://{DOMINIO}"})
    assert resposta.status_code == 200, resposta.get_data(as_text=True)
    return navegador, resposta


# ------------------------------------------------------------------ atrás do proxy


def test_atras_do_proxy_o_app_enxerga_https_e_o_endereco_publico(caminho, monkeypatch):
    navegador, _ = _autorizado_atras_do_proxy(caminho, monkeypatch)

    resposta = navegador.get("/api/alunos", headers=DO_PROXY)

    assert resposta.status_code == 200
    assert resposta.headers["Strict-Transport-Security"] == f"max-age={HSTS_SEGUNDOS}"


def test_cookie_do_computador_sai_com_secure_httponly_e_samesite_no_servidor(caminho, monkeypatch):
    _, resposta = _autorizado_atras_do_proxy(caminho, monkeypatch)

    cookie = resposta.headers["Set-Cookie"]

    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_atras_do_proxy_pedido_de_escrita_so_passa_com_origem_https_do_proprio_site(caminho, monkeypatch):
    navegador, _ = _autorizado_atras_do_proxy(caminho, monkeypatch)
    pedido = {"whatsapp": "(27) 98888-7766"}

    mesma = navegador.post("/api/alunos/1/whatsapp", json=pedido, headers={**DO_PROXY, "Origin": f"https://{DOMINIO}"})
    so_http = navegador.post("/api/alunos/1/whatsapp", json=pedido, headers={**DO_PROXY, "Origin": f"http://{DOMINIO}"})
    outro_site = navegador.post("/api/alunos/1/whatsapp", json=pedido, headers={**DO_PROXY, "Origin": "https://site-malicioso.example"})

    assert (mesma.status_code, so_http.status_code, outro_site.status_code) == (200, 403, 403)


def test_sem_a_chave_do_proxy_os_cabecalhos_forjados_sao_ignorados(caminho, monkeypatch):
    # Se o app for acessível direto (sem proxy), ninguém pode se passar por "https" ou por outro endereço.
    monkeypatch.delenv("GLORIAFIT_ATRAS_DE_PROXY", raising=False)
    monkeypatch.delenv("GLORIAFIT_DOMINIO", raising=False)
    navegador = criar_app(caminho).test_client()

    resposta = navegador.get("/saude", headers=DO_PROXY)

    assert resposta.status_code == 200
    assert "Strict-Transport-Security" not in resposta.headers
    forjado = navegador.post("/api/autorizar", json={"codigo": "X"}, headers={**DO_PROXY, "Origin": f"https://{DOMINIO}"})
    assert forjado.status_code == 403  # a origem https do endereço forjado não vale


def test_http_puro_nao_recebe_hsts(caminho, monkeypatch):
    monkeypatch.delenv("GLORIAFIT_ATRAS_DE_PROXY", raising=False)
    navegador = criar_app(caminho).test_client()

    assert "Strict-Transport-Security" not in navegador.get("/saude").headers


def test_o_prazo_do_hsts_comeca_curto(caminho):
    # 1 semana: se o HTTPS der problema, o estrago dura pouco. Subir para 1 ano só com tudo estável.
    assert HSTS_SEGUNDOS == 7 * 24 * 3600


# ------------------------------------------------------------------ domínio fixo


def test_com_dominio_definido_outro_host_e_recusado(caminho, monkeypatch):
    monkeypatch.setenv("GLORIAFIT_DOMINIO", DOMINIO)
    navegador = criar_app(caminho).test_client()

    certo = navegador.get("/saude", headers={"Host": DOMINIO})
    errado = navegador.get("/saude", headers={"Host": "outro.exemplo.com"})

    assert certo.status_code == 200
    assert errado.status_code == 400


def test_sem_dominio_definido_qualquer_host_funciona(caminho, monkeypatch):
    monkeypatch.delenv("GLORIAFIT_DOMINIO", raising=False)
    navegador = criar_app(caminho).test_client()

    assert navegador.get("/saude", headers={"Host": "qualquer.exemplo.com"}).status_code == 200


# ------------------------------------------------------------------ banco com vários processos


def test_banco_em_arquivo_usa_wal_e_espera_a_vez(caminho):
    conn = conectar(caminho)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    finally:
        conn.close()


def test_banco_na_memoria_continua_funcionando():
    conn = conectar()
    try:
        criar_tabelas(conn)
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "memory"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    finally:
        conn.close()


def test_quem_le_nao_trava_quem_grava_e_quem_grava_nao_trava_quem_le(caminho):
    leitor, escritor = conectar(caminho), conectar(caminho)
    try:
        leitor.execute("BEGIN")
        leitor.execute("SELECT COUNT(*) FROM aluno").fetchone()  # leitura aberta
        escritor.execute("INSERT INTO aluno (nome) VALUES ('NOVO')")  # em WAL isto não espera pelo leitor
        escritor.commit()
        assert leitor.execute("SELECT COUNT(*) FROM aluno").fetchone()[0] == 1  # o leitor ainda vê o estado dele
        leitor.rollback()
        assert leitor.execute("SELECT COUNT(*) FROM aluno").fetchone()[0] == 2
    finally:
        leitor.close()
        escritor.close()


def test_dois_escritores_ao_mesmo_tempo_um_espera_o_outro_em_vez_de_falhar(caminho):
    primeiro, segundo = conectar(caminho), conectar(caminho)
    try:
        primeiro.execute("PRAGMA busy_timeout = 100")
        segundo.execute("PRAGMA busy_timeout = 100")
        primeiro.execute("BEGIN IMMEDIATE")
        # Com a espera curta do teste o segundo desiste, mas com a mensagem de "ocupado" (e não corrompe nada).
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            segundo.execute("BEGIN IMMEDIATE")
        primeiro.rollback()
        segundo.execute("BEGIN IMMEDIATE")  # liberado, passa
        segundo.rollback()
    finally:
        primeiro.close()
        segundo.close()
