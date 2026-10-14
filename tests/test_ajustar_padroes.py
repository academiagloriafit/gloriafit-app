"""Ajustes nos treinos padrão (app/ajustar_padroes.py): o motor, o plano da revisão de 14/10/2026 e o comando de terminal.

Dados inventados. Nenhuma senha de verdade aparece aqui.
"""

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from app import administrador, ajustar_padroes
from app.ajustar_padroes import (
    CAMPOS,
    PLANOS,
    Divergencia,
    Limpeza,
    Linha,
    Plano,
    Remocao,
)
from app.db import conectar, criar_tabelas
from app.treinos import (
    LIMITE_CAMPO,
    LIMITE_NOME_FICHA,
    LIMITE_NOME_TREINO,
    LIMITE_OBSERVACAO,
)

SENHA = "senha-de-teste-1"
AGORA = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)


# ------------------------------------------------------------------ ajudantes


class Montador:
    """Cria treinos padrão de mentira no banco. Exercícios são criados pelo nome, na primeira vez que aparecem."""

    def __init__(self, conn):
        self.conn = conn
        self.ids = {}

    def exercicio(self, nome):
        if nome not in self.ids:
            self.ids[nome] = self.conn.execute("INSERT INTO exercicio (nome, origem, ativo) VALUES (?, 'app', 1)", (nome,)).lastrowid
        return self.ids[nome]

    def padrao(self, modelo_id, nome, fichas):
        """`fichas` = {nome da ficha: [(exercício, séries, repetições, carga, observação), ...]}."""
        conteudo = {
            "fichas": [
                {
                    "nome": nome_da_ficha,
                    "itens": [
                        {
                            "exercicio_id": self.exercicio(exercicio),
                            "series": series or None,
                            "repeticoes": repeticoes or None,
                            "carga": carga or None,
                            "pausa": None,
                            "observacao": observacao or None,
                            "bloco": None,
                        }
                        for exercicio, series, repeticoes, carga, observacao in linhas
                    ],
                }
                for nome_da_ficha, linhas in fichas.items()
            ]
        }
        self.conn.execute(
            "INSERT INTO modelo_treino (id, nome, montado_por, conteudo) VALUES (?, ?, 'Academia Glória Fit', ?)",
            (modelo_id, nome, json.dumps(conteudo, ensure_ascii=False)),
        )
        self.conn.commit()


@pytest.fixture
def conn():
    c = conectar()
    criar_tabelas(c)
    yield c
    c.close()


@pytest.fixture
def montador(conn):
    return Montador(conn)


def _linhas_do_padrao(conn, modelo_id):
    """{nome da ficha: [(exercício, séries, repetições, carga, observação)]} como está no banco agora."""
    nomes = {r["id"]: r["nome"] for r in conn.execute("SELECT id, nome FROM exercicio")}
    conteudo = json.loads(conn.execute("SELECT conteudo FROM modelo_treino WHERE id = ?", (modelo_id,)).fetchone()[0])
    return {
        f["nome"]: [(nomes[i["exercicio_id"]], i["series"] or "", i["repeticoes"] or "", i["carga"] or "", i["observacao"] or "") for i in f["itens"]]
        for f in conteudo["fichas"]
    }


def _nome_do_padrao(conn, modelo_id):
    return conn.execute("SELECT nome FROM modelo_treino WHERE id = ?", (modelo_id,)).fetchone()[0]


# ------------------------------------------------------------------ o plano da revisão: forma e limites


def test_o_plano_cobre_11_treinos_sem_repetir_id_e_deixa_o_homem_5_de_fora():
    ids = [p.modelo_id for p in PLANOS]
    assert len(ids) == len(set(ids)) == 11
    assert 14 not in ids  # Homem 5: sem ajustes
    assert set(ids) == {4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 15}


@pytest.mark.parametrize("plano", PLANOS, ids=lambda p: f"id{p.modelo_id}")
def test_cada_plano_respeita_os_limites_do_app(plano):
    assert (plano.nome_atual is None) == (plano.novo_nome is None)
    if plano.novo_nome:
        assert plano.novo_nome != plano.nome_atual
        assert 1 <= len(plano.novo_nome) <= LIMITE_NOME_TREINO
    for linha in plano.linhas:
        assert linha.posicao >= 1
        assert linha.trocas
        for campo, antes, depois in linha.trocas:
            assert campo in CAMPOS
            assert antes != depois
            assert len(depois) <= (LIMITE_OBSERVACAO if campo == "observacao" else LIMITE_CAMPO)
    for antes, depois in plano.fichas_renomeadas:
        assert antes != depois
        assert 1 <= len(depois) <= LIMITE_NOME_FICHA
    for limpeza in plano.limpezas:
        assert limpeza.campo in CAMPOS and limpeza.texto and limpeza.quantas >= 1
    fichas_com_remocao = [r.ficha for r in plano.remocoes]
    assert len(fichas_com_remocao) == len(set(fichas_com_remocao))  # no máximo uma remoção por ficha


def test_os_nomes_novos_dos_treinos_nao_se_repetem_nem_batem_com_os_de_hoje():
    novos = [p.novo_nome for p in PLANOS if p.novo_nome]
    assert novos == ["TREINO HOMEM 1", "TREINO MULHER 1"]
    atuais = {p.nome_atual for p in PLANOS if p.nome_atual}
    assert not set(novos) & atuais


# ------------------------------------------------------------------ o plano inteiro, num banco de mentira


def _estado_de_antes(montador, plano):
    """Monta um padrão que está exatamente como a revisão esperava ANTES (só o que o plano pede; o resto é enchimento)."""
    tamanhos: dict[str, int] = {}
    for linha in plano.linhas:
        tamanhos[linha.ficha] = max(tamanhos.get(linha.ficha, 1), linha.posicao)
    for remocao in plano.remocoes:
        tamanhos[remocao.ficha] = max(tamanhos.get(remocao.ficha, 1), remocao.itens_depois + 1)
    for antes, _depois in plano.fichas_renomeadas:
        tamanhos.setdefault(antes, 1)
    fichas = {nome: [(f"ENCHIMENTO {nome} {k}", "3", "12", "", "") for k in range(tamanho)] for nome, tamanho in tamanhos.items()}
    for remocao in plano.remocoes:
        fichas[remocao.ficha][remocao.posicao - 1] = (remocao.exercicio, "2-3", "8-12", "", "")
    for linha in plano.linhas:
        valores = {"series": "3", "repeticoes": "12", "carga": "", "observacao": ""}
        for campo, antes, _depois in linha.trocas:
            valores[campo] = antes
        fichas[linha.ficha][linha.posicao - 1] = (linha.exercicio, valores["series"], valores["repeticoes"], valores["carga"], valores["observacao"])
    for limpeza in plano.limpezas:
        extra = []
        for k in range(limpeza.quantas):
            valores = {"series": "3", "repeticoes": "12", "carga": "", "observacao": ""}
            valores[limpeza.campo] = limpeza.texto
            extra.append((f"LIMPAR {k}", valores["series"], valores["repeticoes"], valores["carga"], valores["observacao"]))
        fichas.setdefault("LIMPEZA", []).extend(extra)
    if not fichas:
        fichas = {"A": [("ENCHIMENTO", "3", "12", "", "")]}
    montador.padrao(plano.modelo_id, plano.nome_atual or f"TREINO DE TESTE {plano.modelo_id}", fichas)


@pytest.fixture
def banco_da_revisao(conn, montador):
    for plano in PLANOS:
        _estado_de_antes(montador, plano)
    return conn


def test_o_plano_inteiro_aplica_e_cada_mudanca_aparece_no_banco(banco_da_revisao):
    conn = banco_da_revisao
    resultados = ajustar_padroes.calcular_todos(conn)
    assert all(r.mudancas for r in resultados)
    assert ajustar_padroes.aplicar(conn, resultados) == 11

    for plano in PLANOS:
        linhas = _linhas_do_padrao(conn, plano.modelo_id)
        renomeadas = dict(plano.fichas_renomeadas)
        if plano.novo_nome:
            assert _nome_do_padrao(conn, plano.modelo_id) == plano.novo_nome
        for linha in plano.linhas:
            ficha = linhas[renomeadas.get(linha.ficha, linha.ficha)]
            exercicio, series, repeticoes, carga, observacao = ficha[linha.posicao - 1]
            assert exercicio == linha.exercicio
            atual = {"series": series, "repeticoes": repeticoes, "carga": carga, "observacao": observacao}
            for campo, _antes, depois in linha.trocas:
                assert atual[campo] == depois
        for limpeza in plano.limpezas:
            indice = CAMPOS.index(limpeza.campo)
            assert not [x for f in linhas.values() for x in f if x[1 + indice] == limpeza.texto]
        for remocao in plano.remocoes:
            assert len(linhas[renomeadas.get(remocao.ficha, remocao.ficha)]) == remocao.itens_depois
        for antes, depois in plano.fichas_renomeadas:
            assert depois in linhas and antes not in linhas


def test_rodar_de_novo_nao_muda_nada_e_diz_que_ja_estava_ajustado(banco_da_revisao):
    conn = banco_da_revisao
    ajustar_padroes.aplicar(conn, ajustar_padroes.calcular_todos(conn))
    antes = conn.execute("SELECT id, nome, conteudo FROM modelo_treino ORDER BY id").fetchall()
    segunda = ajustar_padroes.calcular_todos(conn)
    assert [r.mudancas for r in segunda] == [[]] * 11
    assert ajustar_padroes.aplicar(conn, segunda) == 0
    assert conn.execute("SELECT id, nome, conteudo FROM modelo_treino ORDER BY id").fetchall() == antes


def test_o_que_nao_esta_no_plano_fica_igual_nome_fila_professor_e_enchimento(banco_da_revisao):
    conn = banco_da_revisao
    conn.execute("UPDATE modelo_treino SET sessoes_por_ficha = 4 WHERE id = 7")
    antes_h2 = _linhas_do_padrao(conn, 7)
    ajustar_padroes.aplicar(conn, ajustar_padroes.calcular_todos(conn))
    depois_h2 = _linhas_do_padrao(conn, 7)
    assert depois_h2["A - INF"][0][2] == "10"
    assert depois_h2["A - INF"][1:] == antes_h2["A - INF"][1:]
    assert conn.execute("SELECT sessoes_por_ficha, montado_por FROM modelo_treino WHERE id = 7").fetchone()[:] == (4, "Academia Glória Fit")


# ------------------------------------------------------------------ o motor: o que dá errado


def _plano_pequeno(**extras):
    return Plano(1, **extras)


@pytest.fixture
def um_padrao(conn, montador):
    montador.padrao(
        1,
        "TREINO UM",
        {
            "A": [("SUPINO", "3", "12", "MODERADO", ""), ("REMADA", "", "", "", ""), ("ROSCA", "3", "12", "", "")],
            "B": [("AGACHAMENTO", "4", "10", "", "ir devagar")],
        },
    )
    return conn


def test_troca_de_campo_em_branco_e_com_texto(um_padrao):
    plano = _plano_pequeno(linhas=(Linha("A", 2, "REMADA", (("series", "", "3"), ("repeticoes", "", "15"))), Linha("B", 1, "AGACHAMENTO", (("observacao", "ir devagar", ""),))))
    ajustar_padroes.aplicar(um_padrao, ajustar_padroes.calcular_todos(um_padrao, (plano,)), (plano,))
    linhas = _linhas_do_padrao(um_padrao, 1)
    assert linhas["A"][1] == ("REMADA", "3", "15", "", "")
    assert linhas["B"][0][4] == ""


def test_exercicio_errado_na_posicao_para_tudo(um_padrao):
    plano = _plano_pequeno(linhas=(Linha("A", 2, "ROSCA", (("series", "", "3"),)),))
    with pytest.raises(Divergencia, match='esperava o exercício "ROSCA" e achei "REMADA"'):
        ajustar_padroes.calcular(um_padrao, plano)


def test_valor_de_antes_diferente_do_esperado_para_tudo(um_padrao):
    plano = _plano_pequeno(linhas=(Linha("A", 3, "ROSCA", (("series", "5", "6"),)),))
    with pytest.raises(Divergencia, match='séries era para estar "5" e está "3"'):
        ajustar_padroes.calcular(um_padrao, plano)


def test_ficha_ou_linha_que_nao_existe_para_tudo(um_padrao):
    with pytest.raises(Divergencia, match='não achei a ficha "Z"'):
        ajustar_padroes.calcular(um_padrao, _plano_pequeno(linhas=(Linha("Z", 1, "SUPINO", (("series", "3", "4"),)),)))
    with pytest.raises(Divergencia, match="não tem essa linha"):
        ajustar_padroes.calcular(um_padrao, _plano_pequeno(linhas=(Linha("A", 9, "SUPINO", (("series", "3", "4"),)),)))


def test_padrao_que_nao_existe_para_tudo(um_padrao):
    with pytest.raises(Divergencia, match="não existe"):
        ajustar_padroes.calcular(um_padrao, Plano(99))


def test_limpeza_exige_a_quantidade_exata(um_padrao):
    certo = _plano_pequeno(limpezas=(Limpeza("carga", "MODERADO", 1),))
    ajustar_padroes.aplicar(um_padrao, ajustar_padroes.calcular_todos(um_padrao, (certo,)), (certo,))
    assert _linhas_do_padrao(um_padrao, 1)["A"][0][3] == ""
    errado = _plano_pequeno(limpezas=(Limpeza("observacao", "ir devagar", 2),))
    with pytest.raises(Divergencia, match="esperava 2 linhas"):
        ajustar_padroes.calcular(um_padrao, errado)


def test_remocao_confere_o_nome_e_o_tamanho_da_ficha(um_padrao):
    with pytest.raises(Divergencia, match="esperava o exercício"):
        ajustar_padroes.calcular(um_padrao, _plano_pequeno(remocoes=(Remocao("A", 1, "ROSCA", 2),)))
    with pytest.raises(Divergencia, match="a ficha tem 3 linhas; esperava 6"):
        ajustar_padroes.calcular(um_padrao, _plano_pequeno(remocoes=(Remocao("A", 1, "SUPINO", 5),)))
    certo = _plano_pequeno(remocoes=(Remocao("A", 2, "REMADA", 2),))
    ajustar_padroes.aplicar(um_padrao, ajustar_padroes.calcular_todos(um_padrao, (certo,)), (certo,))
    assert [x[0] for x in _linhas_do_padrao(um_padrao, 1)["A"]] == ["SUPINO", "ROSCA"]
    assert ajustar_padroes.calcular(um_padrao, certo).mudancas == []  # já tirada


def test_renomear_ficha_e_aceitar_o_nome_novo_na_segunda_vez(um_padrao):
    plano = _plano_pequeno(fichas_renomeadas=(("A", "A/NOVA"),))
    ajustar_padroes.aplicar(um_padrao, ajustar_padroes.calcular_todos(um_padrao, (plano,)), (plano,))
    assert list(_linhas_do_padrao(um_padrao, 1)) == ["A/NOVA", "B"]
    assert ajustar_padroes.calcular(um_padrao, plano).mudancas == []
    sem_a = _plano_pequeno(fichas_renomeadas=(("X", "Y"),))
    with pytest.raises(Divergencia, match='não achei a ficha "X"'):
        ajustar_padroes.calcular(um_padrao, sem_a)


def test_renomear_o_treino_confere_o_nome_de_hoje(um_padrao):
    plano = _plano_pequeno(nome_atual="OUTRO NOME", novo_nome="TREINO NOVO")
    with pytest.raises(Divergencia, match='esperava o nome "OUTRO NOME"'):
        ajustar_padroes.calcular(um_padrao, plano)
    certo = _plano_pequeno(nome_atual="TREINO UM", novo_nome="TREINO NOVO")
    ajustar_padroes.aplicar(um_padrao, ajustar_padroes.calcular_todos(um_padrao, (certo,)), (certo,))
    assert _nome_do_padrao(um_padrao, 1) == "TREINO NOVO"


def test_nome_novo_que_ja_e_de_outro_padrao_para_tudo(um_padrao, montador):
    montador.padrao(2, "treino novo", {"A": [("SUPINO", "3", "12", "", "")]})  # outra caixa e o mesmo nome: o banco tampouco deixaria
    with pytest.raises(Divergencia, match='já existe outro treino padrão chamado "TREINO NOVO"'):
        ajustar_padroes.calcular(um_padrao, _plano_pequeno(nome_atual="TREINO UM", novo_nome="TREINO NOVO"))


def test_resultado_que_nao_passa_na_conferencia_de_treino_para_tudo(um_padrao):
    longo = _plano_pequeno(linhas=(Linha("A", 3, "ROSCA", (("repeticoes", "12", "texto grande demais"),)),))
    with pytest.raises(Divergencia, match="não passa na conferência"):
        ajustar_padroes.calcular(um_padrao, longo)
    ficha_grande = _plano_pequeno(fichas_renomeadas=(("A", "UM NOME DE FICHA GRANDE DEMAIS"),))
    with pytest.raises(Divergencia, match="não passa na conferência"):
        ajustar_padroes.calcular(um_padrao, ficha_grande)


def test_todas_as_divergencias_aparecem_juntas_e_nada_e_gravado(um_padrao):
    ruim1 = _plano_pequeno(linhas=(Linha("A", 3, "ROSCA", (("series", "5", "6"),)),))
    ruim2 = Plano(99)
    boa = _plano_pequeno(linhas=(Linha("A", 2, "REMADA", (("series", "", "3"),)),))
    with pytest.raises(Divergencia) as erro:
        ajustar_padroes.calcular_todos(um_padrao, (boa, ruim1, ruim2))
    assert "séries era para estar" in str(erro.value) and "id 99 não existe" in str(erro.value)
    assert _linhas_do_padrao(um_padrao, 1)["A"][1] == ("REMADA", "", "", "", "")


def test_se_a_conferencia_de_depois_de_gravar_falhar_volta_tudo(um_padrao, monkeypatch):
    plano = _plano_pequeno(linhas=(Linha("A", 2, "REMADA", (("series", "", "3"),)),))
    resultados = ajustar_padroes.calcular_todos(um_padrao, (plano,))
    chamadas = []

    def sempre_falta(conn, planos=None):
        chamadas.append(1)
        return [ajustar_padroes.Resultado(1, "TREINO UM", "TREINO UM", {"fichas": []}, ["ainda falta"])]

    monkeypatch.setattr(ajustar_padroes, "calcular_todos", sempre_falta)
    with pytest.raises(Divergencia, match="Voltei tudo"):
        ajustar_padroes.aplicar(um_padrao, resultados, (plano,))
    assert chamadas
    assert _linhas_do_padrao(um_padrao, 1)["A"][1] == ("REMADA", "", "", "", "")


# ------------------------------------------------------------------ o comando de terminal


@pytest.fixture
def banco_em_arquivo(tmp_path):
    caminho = tmp_path / "app.db"
    c = conectar(caminho)
    criar_tabelas(c)
    m = Montador(c)
    for plano in PLANOS:
        _estado_de_antes(m, plano)
    administrador.definir_senha(c, SENHA, agora=AGORA)
    c.close()
    return caminho


def _digitando(*respostas):
    fila = list(respostas)
    perguntas = []

    def pedir(pergunta):
        perguntas.append(pergunta)
        return fila.pop(0)

    pedir.perguntas = perguntas
    return pedir


def _comando(caminho, tmp_path, *args, digitando=None):
    copias = tmp_path / "copias"
    return ajustar_padroes.main(["--banco", str(caminho), "--copias", str(copias), *args], pedir_senha=digitando or _digitando())


def _conteudos(caminho):
    c = sqlite3.connect(caminho)
    try:
        return c.execute("SELECT id, nome, conteudo FROM modelo_treino ORDER BY id").fetchall()
    finally:
        c.close()


def test_simular_mostra_o_que_mudaria_sem_pedir_senha_e_sem_gravar(banco_em_arquivo, tmp_path, capsys):
    antes = _conteudos(banco_em_arquivo)
    digitando = _digitando()
    assert _comando(banco_em_arquivo, tmp_path, "--simular", digitando=digitando) == 0
    saida = capsys.readouterr().out
    assert "Total: 11 treinos padrão" in saida and "Simulação: NADA foi gravado." in saida
    assert digitando.perguntas == []
    assert _conteudos(banco_em_arquivo) == antes
    assert not (tmp_path / "copias").exists()


def test_detalhes_lista_cada_mudanca(banco_em_arquivo, tmp_path, capsys):
    _comando(banco_em_arquivo, tmp_path, "--simular", "--detalhes")
    saida = capsys.readouterr().out
    assert 'nome do treino: "TREINO ABC HOMEM BÁSICO" → "TREINO HOMEM 1"' in saida
    assert 'carga "MODERADO" apagada de 27 linhas' in saida
    assert 'repetições "30alternand" → "30 alterna"' in saida
    assert 'nome da ficha: "A POST" → "A PERNAS/POST"' in saida


def test_com_a_senha_certa_faz_a_copia_e_grava_tudo(banco_em_arquivo, tmp_path, capsys):
    digitando = _digitando(SENHA)
    assert _comando(banco_em_arquivo, tmp_path, digitando=digitando) == 0
    saida = capsys.readouterr().out
    assert "Cópia de segurança feita: app-" in saida and "Pronto: 11 treinos padrão ajustados." in saida
    assert len(digitando.perguntas) == 1  # uma senha só, para os 11 treinos
    copias = list((tmp_path / "copias").glob("app-*.db"))
    assert len(copias) == 1
    # a cópia é de ANTES: ainda tem os nomes velhos
    c = sqlite3.connect(copias[0])
    try:
        assert c.execute("SELECT nome FROM modelo_treino WHERE id = 4").fetchone()[0] == "TREINO ABC HOMEM BÁSICO"
    finally:
        c.close()
    c = conectar(banco_em_arquivo)
    try:
        assert _nome_do_padrao(c, 4) == "TREINO HOMEM 1" and _nome_do_padrao(c, 5) == "TREINO MULHER 1"
        assert [r.mudancas for r in ajustar_padroes.calcular_todos(c)] == [[]] * 11
    finally:
        c.close()


def test_rodar_depois_de_aplicado_diz_que_nao_ha_o_que_fazer_e_nao_pede_senha(banco_em_arquivo, tmp_path, capsys):
    _comando(banco_em_arquivo, tmp_path, digitando=_digitando(SENHA))
    capsys.readouterr()
    digitando = _digitando()
    assert _comando(banco_em_arquivo, tmp_path, digitando=digitando) == 0
    assert "Nada a fazer" in capsys.readouterr().out
    assert digitando.perguntas == []


def test_senha_errada_nao_grava_nem_faz_copia(banco_em_arquivo, tmp_path, capsys):
    antes = _conteudos(banco_em_arquivo)
    assert _comando(banco_em_arquivo, tmp_path, digitando=_digitando("senha errada 123")) == 2
    assert "Senha incorreta. Nada foi alterado." in capsys.readouterr().err
    assert _conteudos(banco_em_arquivo) == antes
    assert not (tmp_path / "copias").exists()


def test_sem_senha_definida_o_comando_fica_fechado(tmp_path, capsys):
    caminho = tmp_path / "app.db"
    c = conectar(caminho)
    criar_tabelas(c)
    m = Montador(c)
    for plano in PLANOS:
        _estado_de_antes(m, plano)
    c.close()
    antes = _conteudos(caminho)
    assert _comando(caminho, tmp_path, digitando=_digitando(SENHA)) == 2
    assert "ainda não foi definida" in capsys.readouterr().err
    assert _conteudos(caminho) == antes


def test_travado_por_senhas_erradas_nao_grava(banco_em_arquivo, tmp_path, capsys):
    for _ in range(administrador.LIMITE_DE_FALHAS):
        _comando(banco_em_arquivo, tmp_path, digitando=_digitando("errada-errada"))
    capsys.readouterr()
    antes = _conteudos(banco_em_arquivo)
    assert _comando(banco_em_arquivo, tmp_path, digitando=_digitando(SENHA)) == 2
    assert "Senhas erradas demais" in capsys.readouterr().err
    assert _conteudos(banco_em_arquivo) == antes


def test_padrao_diferente_do_esperado_para_com_mensagem_e_sem_pedir_senha(banco_em_arquivo, tmp_path, capsys):
    c = sqlite3.connect(banco_em_arquivo)
    c.execute("UPDATE modelo_treino SET nome = 'OUTRO NOME' WHERE id = 4")
    c.commit()
    c.close()
    antes = _conteudos(banco_em_arquivo)
    digitando = _digitando(SENHA)
    assert _comando(banco_em_arquivo, tmp_path, digitando=digitando) == 1
    erro = capsys.readouterr().err
    assert "NADA foi gravado" in erro and 'esperava o nome "TREINO ABC HOMEM BÁSICO"' in erro
    assert digitando.perguntas == []
    assert _conteudos(banco_em_arquivo) == antes


def test_falha_na_copia_de_seguranca_nao_grava(banco_em_arquivo, tmp_path, capsys, monkeypatch):
    def falha(*_args, **_kwargs):
        raise ajustar_padroes.BackupFalhou("disco cheio")

    monkeypatch.setattr(ajustar_padroes, "fazer_backup", falha)
    antes = _conteudos(banco_em_arquivo)
    assert _comando(banco_em_arquivo, tmp_path, digitando=_digitando(SENHA)) == 1
    assert "Cópia de segurança NÃO feita (disco cheio). Nada foi alterado." in capsys.readouterr().err
    assert _conteudos(banco_em_arquivo) == antes


def test_banco_que_nao_existe_para_com_mensagem(tmp_path):
    with pytest.raises(SystemExit, match="não encontrado"):
        _comando(tmp_path / "nao-existe.db", tmp_path)
