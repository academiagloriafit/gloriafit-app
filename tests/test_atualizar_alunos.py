"""Testes da tela "Atualizar alunos": o pacote que o navegador envia e a rota que o recebe.

Cobre `copia_de_pacote` (app/importar_alunos.py) e `POST /api/alunos/importar` (app/web.py).
Todos os dados aqui são inventados: nomes, CPFs, telefones e matrículas.
"""

import copy
import json
from datetime import datetime, timezone

import pytest

from app import acesso
from app.db import conectar, criar_tabelas
from app.importar_alunos import (
    COLUNAS_NECESSARIAS,
    CopiaInvalida,
    LIMITE_DE_LINHAS_POR_TABELA,
    copia_de_pacote,
)
from app.web import TAMANHO_MAXIMO_DA_IMPORTACAO, TAMANHO_MAXIMO_DO_PEDIDO, criar_app

# "Agora" fixo: 07/10/2026 08:30 em Vila Velha (UTC-3), um pouco depois da cópia das 05:00.
AGORA = datetime(2026, 10, 7, 11, 30, 15, tzinfo=timezone.utc)
EXTRACAO = "07/10/2026 05:00:17"

COLUNAS = {nome: list(colunas) for nome, colunas in COLUNAS_NECESSARIAS.items()}


def pacote_basico(**mudancas):
    """Pacote válido com 2 alunos (um ativo com celular, um desistente sem celular)."""
    pacote = {
        "extracao": EXTRACAO,
        "tabelas": {
            "PESSOA": {
                "colunas": list(COLUNAS["PESSOA"]),
                "linhas": [
                    [101, "ANA FICTICIA", "F", "11144477735", "F"],
                    [102, "BRUNO FICTICIO", "F", "52998224725", "F"],
                ],
            },
            "PESSOA_STATUS": {
                "colunas": list(COLUNAS["PESSOA_STATUS"]),
                "linhas": [
                    [101, "2026-01-01", "2026-12-31", "A"],
                    [102, "2026-01-01", "7777-07-07", "D"],
                ],
            },
            "CONTATO_PESSOA": {
                "colunas": list(COLUNAS["CONTATO_PESSOA"]),
                "linhas": [[1, 101, 30, "27988887766"]],
            },
        },
    }
    pacote.update(mudancas)
    return pacote


# ------------------------------------------------------------------ copia_de_pacote


def test_pacote_valido_vira_copia_com_os_mesmos_dados():
    copia = copia_de_pacote(pacote_basico(), agora=AGORA)

    assert copia.extraido_em == datetime(2026, 10, 7, 5, 0, 17)
    assert [p["NM_PESSOA"] for p in copia.pessoas] == ["ANA FICTICIA", "BRUNO FICTICIO"]
    assert copia.pessoas[0]["ID"] == 101
    assert copia.periodos[101][0]["CD_STATUS"] == "A"
    assert copia.contatos[101][0]["DS_CONTATO"] == "27988887766"


def test_a_ordem_das_colunas_no_pacote_nao_importa():
    pacote = pacote_basico()
    bloco = pacote["tabelas"]["PESSOA"]
    bloco["colunas"] = list(reversed(bloco["colunas"]))
    bloco["linhas"] = [list(reversed(l)) for l in bloco["linhas"]]

    copia = copia_de_pacote(pacote, agora=AGORA)

    assert copia.pessoas[0]["NM_PESSOA"] == "ANA FICTICIA"
    assert copia.pessoas[0]["ID"] == 101


def test_tabela_vazia_serve():
    pacote = pacote_basico()
    pacote["tabelas"]["CONTATO_PESSOA"]["linhas"] = []

    copia = copia_de_pacote(pacote, agora=AGORA)

    assert copia.contatos == {}


@pytest.mark.parametrize(
    "pacote",
    [None, [], "texto", 42, {}, {"extracao": EXTRACAO}, {"extracao": EXTRACAO, "tabelas": []}, {"tabelas": {}}],
)
def test_pacote_que_nao_tem_o_formato_esperado(pacote):
    with pytest.raises(CopiaInvalida):
        copia_de_pacote(pacote, agora=AGORA)


@pytest.mark.parametrize("extracao", [None, 5, "", "ontem", "2026-10-07 05:00:17", "31/02/2026 05:00:00", "07/10/2026"])
def test_data_da_copia_ilegivel(extracao):
    with pytest.raises(CopiaInvalida, match="data e a hora"):
        copia_de_pacote(pacote_basico(extracao=extracao), agora=AGORA)


def test_copia_de_fim_de_semana_ainda_serve():
    # Cópia de sábado 03/10 05:00, vista na quarta 07/10 08:30: 4 dias e pouco, dentro dos 5 dias.
    copia = copia_de_pacote(pacote_basico(extracao="03/10/2026 05:00:00"), agora=AGORA)

    assert copia.extraido_em.day == 3


def test_copia_velha_demais_e_recusada_e_diz_a_idade():
    with pytest.raises(CopiaInvalida, match="velha demais"):
        copia_de_pacote(pacote_basico(extracao="01/10/2026 05:00:00"), agora=AGORA)


def test_copia_do_futuro_e_recusada():
    with pytest.raises(CopiaInvalida, match="ainda não chegou"):
        copia_de_pacote(pacote_basico(extracao="09/10/2026 05:00:00"), agora=AGORA)


def test_pequena_diferenca_de_relogio_para_o_futuro_e_tolerada():
    # O relógio do PC da recepção pode estar adiantado algumas horas.
    copia = copia_de_pacote(pacote_basico(extracao="07/10/2026 20:00:00"), agora=AGORA)

    assert copia.extraido_em.hour == 20


def test_o_fuso_e_o_de_vila_velha_e_nao_o_do_servidor():
    # 08/10 01:00 em Vila Velha ainda é 08/10 04:00 UTC: 5 min depois de "agora" em UTC seria futuro.
    agora = datetime(2026, 10, 7, 23, 0, tzinfo=timezone.utc)  # 20:00 em Vila Velha

    copia = copia_de_pacote(pacote_basico(extracao="07/10/2026 19:59:00"), agora=agora)

    assert copia.extraido_em.hour == 19


def test_tabela_a_mais_ou_a_menos_e_recusada():
    sobra = pacote_basico()
    sobra["tabelas"]["PAGAMENTO"] = {"colunas": ["ID"], "linhas": [[1]]}
    falta = pacote_basico()
    del falta["tabelas"]["CONTATO_PESSOA"]

    for pacote in (sobra, falta):
        with pytest.raises(CopiaInvalida, match="exatamente as tabelas"):
            copia_de_pacote(pacote, agora=AGORA)


def test_coluna_a_mais_e_recusada_porque_seria_dado_pessoal_desnecessario():
    pacote = pacote_basico()
    pacote["tabelas"]["PESSOA"]["colunas"].append("NR_RG")
    for linha in pacote["tabelas"]["PESSOA"]["linhas"]:
        linha.append("1234567")

    with pytest.raises(CopiaInvalida, match="PESSOA: as colunas"):
        copia_de_pacote(pacote, agora=AGORA)


def test_coluna_que_falta_e_recusada():
    pacote = pacote_basico()
    pacote["tabelas"]["PESSOA_STATUS"]["colunas"].pop()
    for linha in pacote["tabelas"]["PESSOA_STATUS"]["linhas"]:
        linha.pop()

    with pytest.raises(CopiaInvalida, match="PESSOA_STATUS: as colunas"):
        copia_de_pacote(pacote, agora=AGORA)


def test_coluna_repetida_e_recusada():
    pacote = pacote_basico()
    pacote["tabelas"]["CONTATO_PESSOA"]["colunas"][1] = "ID_CONTATO"

    with pytest.raises(CopiaInvalida, match="CONTATO_PESSOA: as colunas"):
        copia_de_pacote(pacote, agora=AGORA)


@pytest.mark.parametrize("bloco", [None, [], "x", {"colunas": []}, {"linhas": []}, {"colunas": "x", "linhas": []}, {"colunas": [], "linhas": "x"}])
def test_bloco_de_tabela_mal_formado(bloco):
    pacote = pacote_basico()
    pacote["tabelas"]["PESSOA"] = bloco

    with pytest.raises(CopiaInvalida, match="PESSOA: formato inesperado"):
        copia_de_pacote(pacote, agora=AGORA)


@pytest.mark.parametrize("linha", [None, "texto", {"ID": 1}, [101], [101, "A", "F", "1", "F", "extra"]])
def test_linha_com_formato_errado_diz_a_tabela_e_o_numero_da_linha(linha):
    pacote = pacote_basico()
    pacote["tabelas"]["PESSOA"]["linhas"].append(linha)

    with pytest.raises(CopiaInvalida, match=r"PESSOA, linha 3: formato inesperado"):
        copia_de_pacote(pacote, agora=AGORA)


@pytest.mark.parametrize(
    "tabela, posicao, valor, coluna",
    [
        ("PESSOA", 0, "101", "ID"),  # número escrito como texto
        ("PESSOA", 0, True, "ID"),  # bool não é número (True viraria 1)
        ("PESSOA", 0, None, "ID"),  # id vazio
        ("PESSOA", 0, 1.5, "ID"),
        ("PESSOA", 1, 123, "NM_PESSOA"),  # nome tem que ser texto
        ("PESSOA", 3, 11144477735, "NR_CPF"),  # CPF como número: o navegador converte antes de enviar
        ("PESSOA", 4, ["F"], "ST_DELETED"),
        ("PESSOA_STATUS", 0, None, "ID_PESSOA"),
        ("PESSOA_STATUS", 1, None, "DT_INI_STATUS"),
        ("PESSOA_STATUS", 2, None, "DT_FIM_STATUS"),
        ("PESSOA_STATUS", 3, 7, "CD_STATUS"),
        ("CONTATO_PESSOA", 0, "1", "ID_CONTATO"),
        ("CONTATO_PESSOA", 1, None, "ID_PESSOA"),
        ("CONTATO_PESSOA", 2, "30", "ID_TIPO_CONTATO"),
        ("CONTATO_PESSOA", 3, 27988887766, "DS_CONTATO"),
    ],
)
def test_valor_de_tipo_errado_e_recusado_dizendo_a_coluna(tabela, posicao, valor, coluna):
    pacote = pacote_basico()
    colunas = pacote["tabelas"][tabela]["colunas"]
    # `posicao` é o lugar na ordem de COLUNAS_NECESSARIAS; acha a coluna certa mesmo se a ordem mudar.
    assert COLUNAS[tabela][posicao] == coluna
    pacote["tabelas"][tabela]["linhas"][0][colunas.index(coluna)] = valor

    with pytest.raises(CopiaInvalida, match=f"{tabela}, linha 1: a coluna {coluna}"):
        copia_de_pacote(pacote, agora=AGORA)


@pytest.mark.parametrize(
    "tabela, coluna",
    [
        ("PESSOA", "NM_PESSOA"),
        ("PESSOA", "TP_PESSOA"),
        ("PESSOA", "NR_CPF"),
        ("PESSOA", "ST_DELETED"),
        ("PESSOA_STATUS", "CD_STATUS"),
        ("CONTATO_PESSOA", "ID_TIPO_CONTATO"),
        ("CONTATO_PESSOA", "DS_CONTATO"),
    ],
)
def test_estas_colunas_aceitam_vazio(tabela, coluna):
    pacote = pacote_basico()
    colunas = pacote["tabelas"][tabela]["colunas"]
    pacote["tabelas"][tabela]["linhas"][0][colunas.index(coluna)] = None

    copia_de_pacote(pacote, agora=AGORA)  # não levanta


def test_tabela_com_linhas_demais_e_recusada(monkeypatch):
    monkeypatch.setattr("app.importar_alunos.LIMITE_DE_LINHAS_POR_TABELA", 1)

    with pytest.raises(CopiaInvalida, match="PESSOA: linhas demais"):
        copia_de_pacote(pacote_basico(), agora=AGORA)


def test_o_limite_de_linhas_cabe_a_base_real_com_folga():
    # A base real tem ~51 mil linhas na maior das tabelas usadas.
    assert LIMITE_DE_LINHAS_POR_TABELA >= 10 * 51_000


def test_o_pacote_original_nao_e_alterado():
    pacote = pacote_basico()
    antes = copy.deepcopy(pacote)

    copia_de_pacote(pacote, agora=AGORA)

    assert pacote == antes


# ------------------------------------------------------------------ POST /api/alunos/importar


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "importar.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.commit()
    conn.close()
    return caminho


@pytest.fixture
def app(caminho):
    return criar_app(caminho)


@pytest.fixture
def anonimo(app):
    return app.test_client()


@pytest.fixture
def cliente(app, caminho):
    navegador = app.test_client()
    conn = conectar(caminho)
    codigo = acesso.gerar_codigo(conn, "Computador de teste").codigo
    token = acesso.autorizar(conn, codigo).token
    conn.close()
    navegador.set_cookie(acesso.NOME_DO_COOKIE, token)
    return navegador


def _alunos(caminho):
    conn = conectar(caminho)
    try:
        return [dict(l) for l in conn.execute("SELECT * FROM aluno ORDER BY data4u_id")]
    finally:
        conn.close()


@pytest.fixture
def pacote_de_hoje():
    """Pacote com a data de "agora" de verdade (a rota usa o relógio real)."""
    from app.alunos import FUSO_DA_ACADEMIA

    agora = datetime.now(timezone.utc).astimezone(FUSO_DA_ACADEMIA)
    pacote = pacote_basico(extracao=f"{agora:%d/%m/%Y %H:%M:%S}")
    hoje = f"{agora:%Y-%m-%d}"
    pacote["tabelas"]["PESSOA_STATUS"]["linhas"] = [
        [101, "2000-01-01", "7777-07-07", "A"],
        [102, "2000-01-01", "7777-07-07", "D"],
    ]
    assert hoje  # só para deixar claro que os períodos cobrem qualquer dia
    return pacote


def test_sem_autorizacao_a_rota_devolve_401_e_nao_grava(anonimo, caminho, pacote_de_hoje):
    resposta = anonimo.post("/api/alunos/importar", json=pacote_de_hoje)

    assert resposta.status_code == 401
    assert _alunos(caminho) == []


def test_pagina_sem_autorizacao_leva_para_autorizar(anonimo):
    resposta = anonimo.get("/alunos/atualizar")

    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/autorizar")


def test_pagina_autorizada_tem_campo_botao_e_script_externo(cliente):
    resposta = cliente.get("/alunos/atualizar")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert 'type="file"' in html
    assert 'id="botao-enviar"' in html
    assert 'src="/static/atualizar_alunos.js"' in html
    assert "<script>" not in html  # a CSP só aceita script de arquivo próprio
    assert resposta.headers["Cache-Control"] == "no-store"


def test_pagina_fala_do_historico_e_o_aviso_do_modo_teste_comeca_escondido(cliente):
    html = cliente.get("/alunos/atualizar").get_data(as_text=True)

    assert "histórico de treinos" in html
    assert '<p id="modo-teste"' in html and 'hidden>MODO TESTE' in html  # só o script o mostra, com ?simular_treinos=1


def test_o_script_da_tela_le_o_modo_teste_so_do_endereco():
    from pathlib import Path

    script = (Path(__file__).resolve().parent.parent / "app" / "static" / "atualizar_alunos.js").read_text(encoding="utf-8")

    assert 'get("simular_treinos") === "1"' in script
    assert "innerHTML" not in script  # texto do servidor só entra na tela por textContent


def test_menu_do_app_leva_para_a_tela(cliente):
    html = cliente.get("/alunos").get_data(as_text=True)

    assert 'href="/alunos/atualizar"' in html


def test_importa_e_responde_so_com_contagens_e_texto(cliente, caminho, pacote_de_hoje):
    resposta = cliente.post("/api/alunos/importar", json=pacote_de_hoje)
    corpo = resposta.get_json()

    assert resposta.status_code == 200
    assert corpo["novos"] == 2
    assert corpo["importadas"] == 2
    assert corpo["atualizados"] == 0
    assert set(corpo) == {"extraido_em", "importadas", "novos", "atualizados", "iguais", "provisorios_juntados", "texto"}
    texto = resposta.get_data(as_text=True)
    for segredo in ("ANA FICTICIA", "BRUNO FICTICIO", "11144477735", "52998224725", "27988887766"):
        assert segredo not in texto


def test_os_alunos_importados_ficam_no_banco_com_celular_e_situacao(cliente, caminho, pacote_de_hoje):
    cliente.post("/api/alunos/importar", json=pacote_de_hoje)

    ana, bruno = _alunos(caminho)
    assert (ana["data4u_id"], ana["nome"], ana["cpf"], ana["situacao"]) == (101, "ANA FICTICIA", "11144477735", "A")
    assert ana["whatsapp"] == "27988887766"
    assert (bruno["data4u_id"], bruno["situacao"], bruno["whatsapp"]) == (102, "D", None)


def test_enviar_de_novo_nao_duplica_nada(cliente, caminho, pacote_de_hoje):
    cliente.post("/api/alunos/importar", json=pacote_de_hoje)
    segunda = cliente.post("/api/alunos/importar", json=pacote_de_hoje)

    assert segunda.status_code == 200
    assert segunda.get_json()["novos"] == 0
    assert segunda.get_json()["iguais"] == 2
    assert len(_alunos(caminho)) == 2


def test_a_busca_do_app_enxerga_os_alunos_importados(cliente, pacote_de_hoje):
    cliente.post("/api/alunos/importar", json=pacote_de_hoje)

    achados = cliente.get("/api/alunos?q=ana").get_json()

    assert "ANA FICTICIA" in json.dumps(achados)


def test_pacote_ruim_devolve_400_com_o_motivo_e_nao_grava(cliente, caminho, pacote_de_hoje):
    pacote_de_hoje["tabelas"]["PESSOA"]["colunas"].append("NR_RG")
    for linha in pacote_de_hoje["tabelas"]["PESSOA"]["linhas"]:
        linha.append("123")

    resposta = cliente.post("/api/alunos/importar", json=pacote_de_hoje)

    assert resposta.status_code == 400
    assert "colunas" in resposta.get_json()["erro"]
    assert _alunos(caminho) == []


def test_copia_velha_devolve_400_e_nao_grava(cliente, caminho, pacote_de_hoje):
    pacote_de_hoje["extracao"] = "01/01/2020 05:00:00"

    resposta = cliente.post("/api/alunos/importar", json=pacote_de_hoje)

    assert resposta.status_code == 400
    assert "velha demais" in resposta.get_json()["erro"]
    assert _alunos(caminho) == []


def test_pacote_ruim_nao_apaga_nem_muda_o_que_ja_estava_la(cliente, caminho, pacote_de_hoje):
    cliente.post("/api/alunos/importar", json=pacote_de_hoje)
    antes = _alunos(caminho)
    ruim = copy.deepcopy(pacote_de_hoje)
    ruim["tabelas"]["PESSOA"]["linhas"][0][1] = 999  # nome como número

    resposta = cliente.post("/api/alunos/importar", json=ruim)

    assert resposta.status_code == 400
    assert _alunos(caminho) == antes


def test_corpo_que_nao_e_json_e_recusado(cliente):
    resposta = cliente.post("/api/alunos/importar", data="x=1", content_type="application/x-www-form-urlencoded")

    assert resposta.status_code == 415


def test_json_quebrado_e_recusado(cliente):
    resposta = cliente.post("/api/alunos/importar", data="{nao e json", content_type="application/json")

    assert resposta.status_code == 400


def test_json_que_nao_e_objeto_vira_400_e_nao_erro_500(cliente):
    resposta = cliente.post("/api/alunos/importar", json=[1, 2, 3])

    assert resposta.status_code == 400


def test_a_rota_aceita_pedido_maior_que_o_limite_comum_mas_so_ela(app, cliente, pacote_de_hoje):
    # Enche o pacote até passar do limite das outras rotas (512 KB) sem passar do limite desta.
    base = pacote_de_hoje["tabelas"]["PESSOA"]
    base["linhas"] = [[1000 + i, f"ALUNO {i:06d} FICTICIO", "F", None, "F"] for i in range(20_000)]
    pacote_de_hoje["tabelas"]["PESSOA_STATUS"]["linhas"] = []
    pacote_de_hoje["tabelas"]["CONTATO_PESSOA"]["linhas"] = []
    tamanho = len(json.dumps(pacote_de_hoje))
    assert TAMANHO_MAXIMO_DO_PEDIDO < tamanho < TAMANHO_MAXIMO_DA_IMPORTACAO

    grande = cliente.post("/api/alunos/importar", json=pacote_de_hoje)
    comum = cliente.post("/api/alunos/1/treinos", json={"nome": "x" * tamanho})

    assert grande.status_code == 200
    assert grande.get_json()["importadas"] == 0  # sem situação no dia, ninguém entra; o que importa é o pedido ter sido lido
    assert comum.status_code == 413


def test_o_limite_maior_nao_vaza_para_o_pedido_seguinte(cliente, pacote_de_hoje):
    cliente.post("/api/alunos/importar", json=pacote_de_hoje)

    resposta = cliente.post("/api/alunos/1/treinos", json={"nome": "x" * (TAMANHO_MAXIMO_DO_PEDIDO + 10)})

    assert resposta.status_code == 413


def test_pedido_acima_do_limite_da_importacao_e_recusado_com_413(cliente, monkeypatch, pacote_de_hoje):
    monkeypatch.setattr("app.web.TAMANHO_MAXIMO_DA_IMPORTACAO", 1024)
    pacote_de_hoje["tabelas"]["PESSOA"]["linhas"] = [[i, "N" * 50, "F", None, "F"] for i in range(100)]

    resposta = cliente.post("/api/alunos/importar", json=pacote_de_hoje)

    assert resposta.status_code == 413
    assert resposta.is_json


def test_a_rota_tambem_confere_a_origem_do_pedido(cliente, pacote_de_hoje):
    resposta = cliente.post(
        "/api/alunos/importar", json=pacote_de_hoje, headers={"Origin": "https://site-malicioso.example"}
    )

    assert resposta.status_code == 403


def test_a_rota_esta_protegida_por_padrao(app, anonimo):
    regras = {r.rule for r in app.url_map.iter_rules()}

    assert "/api/alunos/importar" in regras and "/alunos/atualizar" in regras
    from app.web import ENDPOINTS_PUBLICOS

    assert "api_importar_alunos" not in ENDPOINTS_PUBLICOS
    assert "pagina_atualizar_alunos" not in ENDPOINTS_PUBLICOS
