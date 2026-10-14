# ruff: noqa: DTZ001 (as horas da cópia do Data4U são horário de Brasília, sem fuso, de propósito)
"""Testes do registro de "de quando são os alunos" (app/importacoes.py) e dos avisos na tela.

Todos os dados são inventados. "Agora" é fixo: quarta-feira, 14/10/2026, 12:00 em Vila Velha (15:00 UTC).
"""

from datetime import datetime, timezone

import pytest

from app import acesso, importacoes
from app.db import conectar, criar_tabelas
from app.web import criar_app

AGORA = datetime(2026, 10, 14, 15, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def conn():
    conexao = conectar()
    criar_tabelas(conexao)
    yield conexao
    conexao.close()


# ------------------------------------------------------------------ registrar / ultimas


def test_registrar_guarda_em_utc_a_hora_de_brasilia_da_copia(conn):
    importacoes.registrar(conn, "alunos", datetime(2026, 10, 14, 5, 0, 17), agora=AGORA)

    linha = conn.execute("SELECT tipo, extraido_em, recebida_em FROM importacao").fetchone()
    assert tuple(linha) == ("alunos", "2026-10-14 08:00:17", "2026-10-14 15:00:00")


def test_ultimas_devolve_no_horario_de_brasilia(conn):
    importacoes.registrar(conn, "alunos", datetime(2026, 10, 14, 5, 0, 17), agora=AGORA)

    alunos = importacoes.ultimas(conn)["alunos"]

    assert (alunos.extraido_em.hour, alunos.extraido_em.minute) == (5, 0)
    assert (alunos.recebida_em.hour, alunos.recebida_em.minute) == (12, 0)
    assert "treinos" not in importacoes.ultimas(conn)  # nunca registrado: não aparece


def test_registrar_de_novo_troca_o_registro_em_vez_de_acrescentar(conn):
    importacoes.registrar(conn, "alunos", datetime(2026, 10, 13, 5, 0, 0), agora=AGORA)
    importacoes.registrar(conn, "alunos", datetime(2026, 10, 14, 5, 0, 0), agora=AGORA)

    assert conn.execute("SELECT COUNT(*) FROM importacao").fetchone()[0] == 1
    assert conn.execute("SELECT extraido_em FROM importacao").fetchone()[0] == "2026-10-14 08:00:00"


def test_alunos_e_treinos_tem_registros_separados(conn):
    importacoes.registrar(conn, "alunos", datetime(2026, 10, 14, 5, 0, 0), agora=AGORA)
    importacoes.registrar(conn, "treinos", datetime(2026, 10, 13, 5, 0, 0), agora=AGORA)

    ultimas = importacoes.ultimas(conn)

    assert ultimas["alunos"].extraido_em.day == 14 and ultimas["treinos"].extraido_em.day == 13


def test_assunto_desconhecido_e_recusado(conn):
    with pytest.raises(ValueError, match="desconhecido"):
        importacoes.registrar(conn, "professores", datetime(2026, 10, 14, 5, 0, 0), agora=AGORA)


# ------------------------------------------------------------------ avisos de atraso


def test_sem_nenhum_registro_nao_avisa(conn):
    assert importacoes.avisos_de_atraso(conn, AGORA) == []


def test_copia_de_hoje_nao_avisa(conn):
    importacoes.registrar(conn, "alunos", datetime(2026, 10, 14, 5, 0, 17), agora=AGORA)
    importacoes.registrar(conn, "treinos", datetime(2026, 10, 14, 5, 0, 17), agora=AGORA)

    assert importacoes.avisos_de_atraso(conn, AGORA) == []


def test_fim_de_semana_com_o_pc_desligado_nao_avisa(conn):
    # Última cópia: sexta 12:00 em Brasília. Domingo 11:00 são 47 h depois: ainda dentro do limite de 48 h.
    importacoes.registrar(conn, "alunos", datetime(2026, 10, 9, 12, 0, 0), agora=AGORA)
    domingo = datetime(2026, 10, 11, 14, 0, 0, tzinfo=timezone.utc)  # 11:00 em Brasília

    assert importacoes.avisos_de_atraso(conn, domingo) == []


def test_passou_de_48_horas_avisa_com_a_data_da_copia(conn):
    importacoes.registrar(conn, "alunos", datetime(2026, 10, 9, 12, 0, 0), agora=AGORA)
    domingo = datetime(2026, 10, 11, 16, 0, 0, tzinfo=timezone.utc)  # 13:00 em Brasília: 49 h depois

    avisos = importacoes.avisos_de_atraso(conn, domingo)

    assert len(avisos) == 1
    assert "09/10/2026 às 12:00" in avisos[0] and avisos[0].startswith("Os alunos")
    assert "Thiago" in avisos[0]


def test_so_o_assunto_atrasado_entra_no_aviso(conn):
    importacoes.registrar(conn, "alunos", datetime(2026, 10, 14, 5, 0, 0), agora=AGORA)
    importacoes.registrar(conn, "treinos", datetime(2026, 10, 8, 5, 0, 0), agora=AGORA)

    avisos = importacoes.avisos_de_atraso(conn, AGORA)

    assert len(avisos) == 1 and avisos[0].startswith("O histórico de treinos")


def test_resumo_da_tela_tem_uma_linha_por_assunto(conn):
    importacoes.registrar(conn, "alunos", datetime(2026, 10, 14, 5, 0, 17), agora=AGORA)

    resumo = importacoes.resumo_para_a_tela(conn, AGORA)

    assert resumo == [
        {"nome": "Os alunos", "extraido": "14/10/2026 às 05:00", "recebida": "14/10/2026 às 12:00", "atrasado": False},
        {"nome": "O histórico de treinos", "extraido": None, "recebida": None, "atrasado": False},
    ]


# ------------------------------------------------------------------ as telas


@pytest.fixture
def navegador(tmp_path):
    caminho = tmp_path / "app.db"
    ligacao = conectar(caminho)
    criar_tabelas(ligacao)
    ligacao.commit()
    codigo = acesso.gerar_codigo(ligacao, "Computador de teste").codigo
    token = acesso.autorizar(ligacao, codigo).token
    ligacao.close()
    cliente = criar_app(caminho).test_client()
    cliente.set_cookie(acesso.NOME_DO_COOKIE, token)
    return cliente, caminho


def _registrar_no_banco(caminho, tipo, extraido_em):
    ligacao = conectar(caminho)
    importacoes.registrar(ligacao, tipo, extraido_em)
    ligacao.close()


def test_tela_de_buscar_aluno_nao_mostra_aviso_quando_esta_em_dia(navegador):
    cliente, caminho = navegador
    agora_br = datetime.now(timezone.utc).astimezone(importacoes.FUSO_DA_ACADEMIA).replace(tzinfo=None)
    _registrar_no_banco(caminho, "alunos", agora_br)

    pagina = cliente.get("/alunos").get_data(as_text=True)

    assert "aviso-importado" not in pagina


def test_tela_de_buscar_aluno_avisa_quando_a_copia_esta_velha(navegador):
    cliente, caminho = navegador
    _registrar_no_banco(caminho, "alunos", datetime(2026, 1, 5, 5, 0, 0))

    pagina = cliente.get("/alunos").get_data(as_text=True)

    assert "aviso-importado-atencao" in pagina
    assert "05/01/2026 às 05:00" in pagina


def test_tela_de_atualizar_mostra_de_quando_e_cada_assunto(navegador):
    cliente, caminho = navegador
    _registrar_no_banco(caminho, "alunos", datetime(2026, 1, 5, 5, 0, 0))

    pagina = cliente.get("/alunos/atualizar").get_data(as_text=True)

    assert "Os alunos: cópia do Data4U de 05/01/2026 às 05:00" in pagina
    assert "Está atrasado" in pagina
    assert "O histórico de treinos: ainda não há registro" in pagina
