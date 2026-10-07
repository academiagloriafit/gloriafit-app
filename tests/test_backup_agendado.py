"""Backup diário sozinho (app/backup_agendado.py). Dados inventados; relógio e espera são trocados nos testes."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app import backup_agendado as ag
from app.backup import BackupFalhou, fazer_backup
from app.db import conectar, criar_tabelas

UTC = timezone.utc
# 07/10/2026 20:15 em Vila Velha (UTC-3) = 23:15 UTC.
AGORA = datetime(2026, 10, 7, 23, 15, tzinfo=UTC)


@pytest.fixture
def banco(tmp_path):
    caminho = tmp_path / "app.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.execute("INSERT INTO aluno (nome, cpf) VALUES ('MARIA TESTE', '11144477735')")
    conn.commit()
    conn.close()
    return caminho


def _copia_de(pasta, quando: datetime):
    pasta.mkdir(exist_ok=True)
    arquivo = pasta / f"app-{quando:%Y-%m-%d-%H%M%S}.db"
    arquivo.write_bytes(b"x")
    return arquivo


# ------------------------------------------------------------------ proximo_horario


def test_o_proximo_horario_depois_das_3_da_manha_e_amanha_as_3():
    alvo = ag.proximo_horario(AGORA)  # 20:15 do dia 07 em Vila Velha

    assert alvo == datetime(2026, 10, 8, 3, 0, tzinfo=ag.FUSO_DA_ACADEMIA)
    assert alvo.astimezone(UTC) == datetime(2026, 10, 8, 6, 0, tzinfo=UTC)


def test_o_proximo_horario_antes_das_3_da_manha_e_hoje_as_3():
    agora = datetime(2026, 10, 7, 4, 0, tzinfo=UTC)  # 01:00 em Vila Velha

    assert ag.proximo_horario(agora).astimezone(UTC) == datetime(2026, 10, 7, 6, 0, tzinfo=UTC)


def test_exatamente_as_3_o_proximo_e_o_de_amanha_e_nao_o_mesmo_instante():
    agora = datetime(2026, 10, 7, 6, 0, tzinfo=UTC)  # 03:00 em Vila Velha

    assert ag.proximo_horario(agora).astimezone(UTC) == datetime(2026, 10, 8, 6, 0, tzinfo=UTC)


def test_o_horario_e_o_de_vila_velha_e_nao_o_do_servidor():
    # 02:59 em Vila Velha ainda é "antes das 3": hoje, não amanhã (em UTC já seria 05:59, "antes das 6").
    agora = datetime(2026, 10, 7, 5, 59, tzinfo=UTC)

    assert ag.proximo_horario(agora).astimezone(UTC) == datetime(2026, 10, 7, 6, 0, tzinfo=UTC)


def test_a_espera_nunca_e_zero_nem_passa_de_um_dia():
    for hora in range(24):
        agora = datetime(2026, 10, 7, hora, 30, tzinfo=UTC)
        espera = ag.proximo_horario(agora) - agora
        assert timedelta(0) < espera <= timedelta(days=1)


# ------------------------------------------------------------------ copia_mais_nova / verificar


def test_sem_pasta_ou_sem_copias_nao_ha_copia_mais_nova(tmp_path):
    assert ag.copia_mais_nova(tmp_path / "nao-existe") is None
    (tmp_path / "vazia").mkdir()
    assert ag.copia_mais_nova(tmp_path / "vazia") is None


def test_a_mais_nova_e_lida_do_nome_do_arquivo(tmp_path):
    pasta = tmp_path / "bk"
    _copia_de(pasta, datetime(2026, 10, 5, 6, 0, 1, tzinfo=UTC))
    _copia_de(pasta, datetime(2026, 10, 7, 6, 0, 2, tzinfo=UTC))
    _copia_de(pasta, datetime(2026, 10, 6, 6, 0, 3, tzinfo=UTC))

    assert ag.copia_mais_nova(pasta) == datetime(2026, 10, 7, 6, 0, 2, tzinfo=UTC)


def test_arquivos_que_nao_sao_copias_sao_ignorados(tmp_path):
    pasta = tmp_path / "bk"
    pasta.mkdir()
    (pasta / "app-2026-10-07-060000.db.parcial").write_bytes(b"x")
    (pasta / "app-2026-10-07.db").write_bytes(b"x")
    (pasta / "anotacao.txt").write_bytes(b"x")
    (pasta / "app-2026-10-07-060000.db.d").mkdir()

    assert ag.copia_mais_nova(pasta) is None


def test_verificar_sem_copia_falha(tmp_path):
    ok, mensagem = ag.verificar(tmp_path, AGORA)

    assert not ok and "Nenhuma cópia" in mensagem


def test_verificar_com_copia_de_ontem_passa(tmp_path):
    _copia_de(tmp_path, AGORA - timedelta(hours=17))

    ok, _ = ag.verificar(tmp_path, AGORA)

    assert ok


def test_verificar_com_copia_de_dois_dias_falha_e_diz_a_idade(tmp_path):
    _copia_de(tmp_path, AGORA - timedelta(hours=49))

    ok, mensagem = ag.verificar(tmp_path, AGORA)

    assert not ok and "49 horas" in mensagem


def test_verificar_aguenta_uma_nova_tentativa_depois_do_horario(tmp_path):
    # Cópia das 03:00 falhou, a de 04:00 deu certo: a anterior tinha 25 h, ainda dentro do limite de 30 h.
    _copia_de(tmp_path, AGORA - timedelta(hours=25))

    assert ag.verificar(tmp_path, AGORA)[0]


# ------------------------------------------------------------------ rodar


class Relogio:
    """Relógio de mentira: `dormir` adianta o tempo em vez de esperar."""

    def __init__(self, inicio):
        self.agora = inicio
        self.dormidas = []

    def __call__(self):
        return self.agora

    def dormir(self, segundos):
        self.dormidas.append(segundos)
        self.agora += timedelta(seconds=segundos)


def _fazer_com_relogio(relogio, chamadas):
    def fazer(banco, pasta, guardar):
        chamadas.append((str(banco), str(pasta), guardar))
        return fazer_backup(banco, pasta, guardar, agora=relogio())

    return fazer


def test_ao_ligar_sem_nenhuma_copia_faz_uma_na_hora_e_depois_uma_por_dia(banco, tmp_path):
    pasta = tmp_path / "bk"
    relogio, chamadas = Relogio(AGORA), []

    ag.rodar(banco, pasta, 30, relogio=relogio, dormir=relogio.dormir, fazer=_fazer_com_relogio(relogio, chamadas), ciclos=2)

    nomes = sorted(p.name for p in pasta.iterdir())
    assert len(nomes) == 3  # na partida + 2 diárias
    assert nomes[0] == "app-2026-10-07-231500.db"
    assert nomes[1] == "app-2026-10-08-060000.db"  # 03:00 de Vila Velha
    assert nomes[2] == "app-2026-10-09-060000.db"
    assert len(chamadas) == 3 and all(c[2] == 30 for c in chamadas)


def test_ao_ligar_com_copia_recente_nao_faz_outra_na_partida(banco, tmp_path):
    pasta = tmp_path / "bk"
    _copia_de(pasta, AGORA - timedelta(hours=2))
    relogio, chamadas = Relogio(AGORA), []

    ag.rodar(banco, pasta, 30, relogio=relogio, dormir=relogio.dormir, fazer=_fazer_com_relogio(relogio, chamadas), ciclos=1)

    assert len(chamadas) == 1  # só a das 03:00
    assert sorted(p.name for p in pasta.iterdir())[-1] == "app-2026-10-08-060000.db"


def test_reinicio_em_loop_nao_enche_a_pasta(banco, tmp_path):
    pasta = tmp_path / "bk"
    relogio = Relogio(AGORA)
    for _ in range(5):  # liga, "reinicia", liga...
        ag.rodar(banco, pasta, 30, relogio=relogio, dormir=relogio.dormir, fazer=_fazer_com_relogio(relogio, []), ciclos=0)
        relogio.agora += timedelta(minutes=1)

    assert len(list(pasta.iterdir())) == 1


def test_ao_ligar_com_copia_velha_faz_uma_na_hora(banco, tmp_path):
    pasta = tmp_path / "bk"
    _copia_de(pasta, AGORA - timedelta(hours=40))
    relogio, chamadas = Relogio(AGORA), []

    ag.rodar(banco, pasta, 30, relogio=relogio, dormir=relogio.dormir, fazer=_fazer_com_relogio(relogio, chamadas), ciclos=0)

    assert len(chamadas) == 1


def test_a_primeira_espera_vai_ate_as_3_da_manha(banco, tmp_path):
    pasta = tmp_path / "bk"
    relogio = Relogio(AGORA)

    ag.rodar(banco, pasta, 30, relogio=relogio, dormir=relogio.dormir, fazer=_fazer_com_relogio(relogio, []), ciclos=1)

    # 23:15 UTC -> 06:00 UTC do dia seguinte = 6 h 45 min
    assert relogio.dormidas == [6 * 3600 + 45 * 60]


def test_falha_avisa_no_registro_e_tenta_de_novo_em_uma_hora(banco, tmp_path, capsys):
    pasta = tmp_path / "bk"
    relogio = Relogio(AGORA)
    tentativas = []

    def fazer(banco_, pasta_, guardar):
        tentativas.append(1)
        if len(tentativas) < 3:
            raise BackupFalhou("disco cheio (teste)")
        return fazer_backup(banco_, pasta_, guardar, agora=relogio())

    ag.rodar(banco, pasta, 30, relogio=relogio, dormir=relogio.dormir, fazer=fazer, ciclos=0)

    erro = capsys.readouterr().err
    assert erro.count("BACKUP FALHOU: disco cheio (teste)") == 2
    assert relogio.dormidas == [3600, 3600]
    assert len(list(pasta.iterdir())) == 1


@pytest.mark.parametrize("erro", [sqlite3.OperationalError("banco travado"), OSError("sem espaço")])
def test_erros_de_banco_e_de_disco_tambem_viram_nova_tentativa(banco, tmp_path, erro):
    pasta = tmp_path / "bk"
    relogio, tentativas = Relogio(AGORA), []

    def fazer(banco_, pasta_, guardar):
        tentativas.append(1)
        if len(tentativas) == 1:
            raise erro
        return fazer_backup(banco_, pasta_, guardar, agora=relogio())

    ag.rodar(banco, pasta, 30, relogio=relogio, dormir=relogio.dormir, fazer=fazer, ciclos=0)

    assert len(tentativas) == 2


def test_so_as_30_copias_mais_novas_ficam(banco, tmp_path):
    pasta = tmp_path / "bk"
    relogio = Relogio(AGORA)

    ag.rodar(banco, pasta, 30, relogio=relogio, dormir=relogio.dormir, fazer=_fazer_com_relogio(relogio, []), ciclos=35)

    nomes = sorted(p.name for p in pasta.iterdir())
    assert len(nomes) == 30
    assert nomes[-1] == "app-2026-11-11-060000.db"  # 35 dias depois de 07/10 (as mais velhas saíram)


def test_a_copia_diaria_tem_os_dados_do_banco(banco, tmp_path):
    pasta = tmp_path / "bk"
    relogio = Relogio(AGORA)

    ag.rodar(banco, pasta, 30, relogio=relogio, dormir=relogio.dormir, fazer=_fazer_com_relogio(relogio, []), ciclos=0)

    copia = next(pasta.iterdir())
    conn = sqlite3.connect(copia)
    assert conn.execute("SELECT nome, cpf FROM aluno").fetchall() == [("MARIA TESTE", "11144477735")]
    conn.close()


# ------------------------------------------------------------------ linha de comando


def test_main_verificar_devolve_0_com_copia_recente_e_1_sem(tmp_path, capsys):
    pasta = tmp_path / "bk"
    assert ag.main(["--verificar", "--pasta", str(pasta)]) == 1
    assert "Nenhuma cópia" in capsys.readouterr().out

    _copia_de(pasta, datetime.now(UTC) - timedelta(hours=1))
    assert ag.main(["--verificar", "--pasta", str(pasta)]) == 0


def test_main_recusa_guardar_zero(tmp_path):
    with pytest.raises(SystemExit):
        ag.main(["--guardar", "0", "--pasta", str(tmp_path)])
