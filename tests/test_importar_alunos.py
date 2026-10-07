"""Testes da importação dos alunos a partir da cópia diária do Data4U (app/importar_alunos.py).

Todos os dados aqui são inventados: nomes, CPFs, telefones e matrículas.
"""

import json
import sqlite3
import zipfile
from datetime import datetime, timezone

import pytest

import app.importar_alunos as imp
from app.db import conectar, criar_tabelas
from app.importar_alunos import (
    CopiaInvalida,
    carregar_copia,
    escolher_whatsapp,
    importar,
    limpar_cpf,
    main,
    situacao_do_dia,
)

DIA = "2026-10-07"
AGORA = datetime(2026, 10, 7, 8, 30, 15, tzinfo=timezone.utc)

COLUNAS = {
    "PESSOA": ["ID", "CD_PESSOA", "NM_PESSOA", "TP_PESSOA", "NR_CPF", "ST_DELETED"],
    "PESSOA_STATUS": ["ID_PESSOA", "DT_INI_STATUS", "DT_FIM_STATUS", "CD_STATUS"],
    "CONTATO_PESSOA": ["ID_CONTATO", "ID_PESSOA", "ID_TIPO_CONTATO", "DS_CONTATO"],
}


# ------------------------------------------------------------------ montagem de cópias de teste


def pessoa(id, nome="FULANO DE TAL", cpf="11111111111", tipo="F", apagada="F", **extra):
    return {"ID": id, "CD_PESSOA": id, "NM_PESSOA": nome, "TP_PESSOA": tipo, "NR_CPF": cpf, "ST_DELETED": apagada, **extra}


def periodo(id_pessoa, letra, ini="2026-01-01", fim="2026-12-31"):
    return {"ID_PESSOA": id_pessoa, "DT_INI_STATUS": ini, "DT_FIM_STATUS": fim, "CD_STATUS": letra}


def contato(id_contato, id_pessoa, numero, tipo=30):
    return {"ID_CONTATO": id_contato, "ID_PESSOA": id_pessoa, "ID_TIPO_CONTATO": tipo, "DS_CONTATO": numero}


def _jsonl(linhas):
    return "".join(json.dumps(linha, ensure_ascii=False) + "\n" for linha in linhas).encode("utf-8")


def escrever_copia(
    destino, pessoas, periodos=(), contatos=(), extracao="07/10/2026 05:00:17", sobrescrever=None, tirar=(), manifesto=None
):
    """Cria um .zip no formato do base_total.zip. Devolve o caminho.

    sobrescrever: {"PESSOA.jsonl": b"..."} troca o conteúdo de um arquivo (para criar defeitos);
    tirar: nomes de arquivos que NÃO vão para o .zip; manifesto: troca o manifesto inteiro.
    """
    tabelas = {"PESSOA": list(pessoas), "PESSOA_STATUS": list(periodos), "CONTATO_PESSOA": list(contatos)}
    if manifesto is None:
        manifesto = {
            "extracao": extracao,
            "tabelas": {n: {"linhas": len(l), "colunas": COLUNAS[n]} for n, l in tabelas.items()},
        }
    arquivos = {f"{n}.jsonl": _jsonl(l) for n, l in tabelas.items()}
    arquivos["_manifesto.json"] = json.dumps(manifesto).encode("utf-8")
    arquivos.update(sobrescrever or {})
    caminho = destino / "copia.zip"
    with zipfile.ZipFile(caminho, "w") as z:
        for nome, conteudo in arquivos.items():
            if nome not in tirar:
                z.writestr(nome, conteudo)
    return caminho


@pytest.fixture
def conn():
    c = conectar()
    criar_tabelas(c)
    yield c
    c.close()


def alunos(conn):
    """Todos os alunos do banco como dicionários, na ordem da matrícula."""
    linhas = conn.execute("SELECT * FROM aluno ORDER BY data4u_id, id").fetchall()
    return [dict(l) for l in linhas]


def por_matricula(conn, matricula):
    linha = conn.execute("SELECT * FROM aluno WHERE data4u_id = ?", (matricula,)).fetchone()
    return dict(linha) if linha else None


def importar_de(conn, tmp_path, pessoas, periodos=(), contatos=(), **kw):
    copia = carregar_copia(escrever_copia(tmp_path, pessoas, periodos, contatos, **kw))
    return importar(conn, copia, agora=AGORA)


# ------------------------------------------------------------------ situacao_do_dia


def test_situacao_de_hoje_e_o_periodo_que_cobre_hoje_nao_o_ultimo():
    # O Data4U já grava o futuro: ativo agora, pendente depois, desistente sem fim.
    periodos = [
        periodo(1, "A", "2026-03-11", "2026-10-11"),
        periodo(1, "P", "2026-10-12", "2026-11-10"),
        periodo(1, "D", "2026-11-11", "7777-07-07"),
    ]

    assert situacao_do_dia(periodos, DIA) == ("A", False)


def test_os_dois_limites_do_periodo_valem():
    periodos = [periodo(1, "A", "2026-10-07", "2026-10-07")]

    assert situacao_do_dia(periodos, "2026-10-07") == ("A", False)
    assert situacao_do_dia(periodos, "2026-10-06") == (None, False)
    assert situacao_do_dia(periodos, "2026-10-08") == (None, False)


def test_datas_de_um_milenio_atras_e_sem_fim_funcionam():
    periodos = [periodo(1, "I", "0777-07-07", "7777-07-07")]

    assert situacao_do_dia(periodos, DIA) == ("I", False)


def test_sem_periodo_nenhum_nao_ha_situacao():
    assert situacao_do_dia([], DIA) == (None, False)


def test_duas_letras_diferentes_no_mesmo_dia_e_ambiguo_e_nao_se_escolhe():
    periodos = [periodo(1, "A"), periodo(1, "D")]

    assert situacao_do_dia(periodos, DIA) == (None, True)


def test_duas_vezes_a_mesma_letra_nao_e_ambiguo():
    periodos = [periodo(1, "A", "2026-01-01", "2026-12-31"), periodo(1, "A", "2026-06-01", "2026-06-30")]

    assert situacao_do_dia(periodos, DIA) == ("A", False)


# ------------------------------------------------------------------ limpar_cpf


@pytest.mark.parametrize("valor", ["12345678909", "123.456.789-09", " 12345678909 ", 12345678909])
def test_cpf_com_11_numeros_serve(valor):
    assert limpar_cpf(valor) == ("12345678909", False)


@pytest.mark.parametrize("valor", [None, "", "   "])
def test_cpf_vazio_e_so_vazio_nao_e_invalido(valor):
    assert limpar_cpf(valor) == (None, False)


@pytest.mark.parametrize(
    "valor", ["1234567890", "123456789012", "abc", "0", "12345678909x1", "１２３４５６７８９０９"]  # o último: algarismos de largura total
)
def test_cpf_preenchido_com_tamanho_errado_vira_vazio_e_e_marcado(valor):
    # Não se completa com zero à esquerda nem se corta: ficaria parecendo CPF de outra pessoa.
    assert limpar_cpf(valor) == (None, True)


# ------------------------------------------------------------------ escolher_whatsapp


def test_celular_com_11_numeros_serve():
    escolha = escolher_whatsapp([contato(1, 9, "27988887766")])

    assert (escolha.numero, escolha.tinha_celular, escolha.varios_validos) == ("27988887766", True, False)


def test_celular_com_enfeites_vira_so_numeros():
    assert escolher_whatsapp([contato(1, 9, "(27) 98888-7766")]).numero == "27988887766"
    assert escolher_whatsapp([contato(1, 9, "(27) 3888-7766")]).numero == "2738887766"  # 10 números


@pytest.mark.parametrize(
    "numero", ["988887766", "98887766", "12", "5527988887766", "+5527988887766", "0988887766", "27 9888 77 66 55", "abc"]
)
def test_celular_sem_ddd_ou_fora_do_formato_nao_serve_mas_conta_como_tendo_celular(numero):
    # 9 números = sem DDD: o DDD não é adivinhado. "+55" e DDD abaixo de 11 também não passam.
    escolha = escolher_whatsapp([contato(1, 9, numero)])

    assert escolha.numero is None
    assert escolha.tinha_celular is True


def test_so_celular_tipo_30_conta():
    contatos = [
        contato(1, 9, "27988887766", tipo=10),  # comercial
        contato(2, 9, "27988887766", tipo=20),  # residencial
        contato(3, 9, "27988887766", tipo=31),  # SMS de cobrança
        contato(4, 9, "27988887766", tipo=100),  # e-mail
    ]

    escolha = escolher_whatsapp(contatos)

    assert (escolha.numero, escolha.tinha_celular) == (None, False)


def test_celular_vazio_e_como_nao_ter():
    escolha = escolher_whatsapp([contato(1, 9, ""), contato(2, 9, "   "), contato(3, 9, None)])

    assert (escolha.numero, escolha.tinha_celular) == (None, False)


def test_sem_nenhum_contato():
    assert escolher_whatsapp([]).numero is None


def test_se_o_primeiro_nao_serve_usa_o_primeiro_que_serve():
    contatos = [contato(1, 9, "988887766"), contato(2, 9, "27977776655")]

    assert escolher_whatsapp(contatos).numero == "27977776655"


def test_com_dois_numeros_validos_usa_o_primeiro_cadastrado_e_avisa():
    # a lista vem fora de ordem de propósito: vale o ID_CONTATO, não a posição
    contatos = [contato(7, 9, "27977776655"), contato(3, 9, "27988887766")]

    escolha = escolher_whatsapp(contatos)

    assert (escolha.numero, escolha.varios_validos) == ("27988887766", True)


def test_o_mesmo_numero_escrito_de_dois_jeitos_nao_conta_como_dois():
    contatos = [contato(1, 9, "27988887766"), contato(2, 9, "(27) 98888-7766")]

    assert escolher_whatsapp(contatos).varios_validos is False


# ------------------------------------------------------------------ carregar_copia


def test_carrega_o_zip_e_usa_a_data_da_copia(tmp_path):
    caminho = escrever_copia(tmp_path, [pessoa(1)], [periodo(1, "A")], [contato(1, 1, "27988887766")])

    copia = carregar_copia(caminho)

    assert copia.extraido_em == datetime(2026, 10, 7, 5, 0, 17)
    assert copia.dia == "2026-10-07"
    assert [p["ID"] for p in copia.pessoas] == [1]
    assert list(copia.periodos) == [1] and list(copia.contatos) == [1]


def test_carrega_a_mesma_coisa_de_uma_pasta_ja_extraida(tmp_path):
    caminho = escrever_copia(tmp_path, [pessoa(1), pessoa(2)], [periodo(1, "A")])
    pasta = tmp_path / "extraida"
    with zipfile.ZipFile(caminho) as z:
        z.extractall(pasta)

    assert carregar_copia(pasta).pessoas == carregar_copia(caminho).pessoas


def test_cabecalhos_de_tabelas_vazias_nao_atrapalham(tmp_path):
    copia = carregar_copia(escrever_copia(tmp_path, [pessoa(1)]))

    assert copia.periodos == {} and copia.contatos == {}


def test_arquivo_que_nao_existe(tmp_path):
    with pytest.raises(CopiaInvalida, match="Não achei"):
        carregar_copia(tmp_path / "nao-existe.zip")


def test_arquivo_que_nao_e_zip(tmp_path):
    falso = tmp_path / "falso.zip"
    falso.write_text("isto não é um zip")

    with pytest.raises(CopiaInvalida, match="não é um arquivo .zip"):
        carregar_copia(falso)


def test_pasta_sem_as_tabelas(tmp_path):
    with pytest.raises(CopiaInvalida, match="Não achei _manifesto.json"):
        carregar_copia(tmp_path)


def test_tabela_que_falta_no_zip(tmp_path):
    caminho = escrever_copia(tmp_path, [pessoa(1)], tirar=("PESSOA_STATUS.jsonl",))

    with pytest.raises(CopiaInvalida, match="PESSOA_STATUS.jsonl"):
        carregar_copia(caminho)


def test_manifesto_que_falta_no_zip(tmp_path):
    caminho = escrever_copia(tmp_path, [pessoa(1)], tirar=("_manifesto.json",))

    with pytest.raises(CopiaInvalida, match="_manifesto.json"):
        carregar_copia(caminho)


@pytest.mark.parametrize(
    "manifesto",
    [
        {"extracao": "ontem", "tabelas": {}},
        {"extracao": "07/10/2026 05:00:17"},
        {"tabelas": {}},
        [],
    ],
)
def test_manifesto_fora_do_formato(tmp_path, manifesto):
    caminho = escrever_copia(tmp_path, [pessoa(1)], manifesto=manifesto)

    with pytest.raises(CopiaInvalida, match="manifesto"):
        carregar_copia(caminho)


def test_cabecalho_do_manifesto_que_nao_e_json(tmp_path):
    caminho = escrever_copia(tmp_path, [pessoa(1)], sobrescrever={"_manifesto.json": b"{nao e json"})

    with pytest.raises(CopiaInvalida, match="manifesto"):
        carregar_copia(caminho)


def test_copia_cortada_e_recusada_comparando_com_o_manifesto(tmp_path):
    # o manifesto diz 3 pessoas; o arquivo só tem 2 linhas (cópia interrompida)
    manifesto = {
        "extracao": "07/10/2026 05:00:17",
        "tabelas": {
            "PESSOA": {"linhas": 3, "colunas": COLUNAS["PESSOA"]},
            "PESSOA_STATUS": {"linhas": 0, "colunas": COLUNAS["PESSOA_STATUS"]},
            "CONTATO_PESSOA": {"linhas": 0, "colunas": COLUNAS["CONTATO_PESSOA"]},
        },
    }
    caminho = escrever_copia(tmp_path, [pessoa(1), pessoa(2)], manifesto=manifesto)

    with pytest.raises(CopiaInvalida, match="PESSOA: o manifesto diz 3 linhas e o arquivo tem 2"):
        carregar_copia(caminho)


@pytest.mark.parametrize("tabela, coluna", [("PESSOA", "NR_CPF"), ("PESSOA_STATUS", "CD_STATUS"), ("CONTATO_PESSOA", "DS_CONTATO")])
def test_coluna_que_o_data4u_tirou_para_a_importacao_com_mensagem_clara(tmp_path, tabela, coluna):
    manifesto = {
        "extracao": "07/10/2026 05:00:17",
        "tabelas": {n: {"linhas": 0, "colunas": [c for c in COLUNAS[n] if c != coluna]} for n in COLUNAS},
    }
    caminho = escrever_copia(tmp_path, [], manifesto=manifesto)

    with pytest.raises(CopiaInvalida, match=f"tabela {tabela}.*{coluna}"):
        carregar_copia(caminho)


def test_linha_que_nao_e_json_diz_a_tabela_e_o_numero_da_linha(tmp_path):
    ruim = _jsonl([pessoa(1)]) + b"{isto nao e json}\n"
    manifesto = {
        "extracao": "07/10/2026 05:00:17",
        "tabelas": {
            "PESSOA": {"linhas": 2, "colunas": COLUNAS["PESSOA"]},
            "PESSOA_STATUS": {"linhas": 0, "colunas": COLUNAS["PESSOA_STATUS"]},
            "CONTATO_PESSOA": {"linhas": 0, "colunas": COLUNAS["CONTATO_PESSOA"]},
        },
    }
    caminho = escrever_copia(tmp_path, [], manifesto=manifesto, sobrescrever={"PESSOA.jsonl": ruim})

    with pytest.raises(CopiaInvalida, match=r"PESSOA.jsonl, linha 2"):
        carregar_copia(caminho)


def test_linha_json_que_nao_e_objeto(tmp_path):
    manifesto = {
        "extracao": "07/10/2026 05:00:17",
        "tabelas": {n: {"linhas": 1 if n == "PESSOA" else 0, "colunas": COLUNAS[n]} for n in COLUNAS},
    }
    caminho = escrever_copia(tmp_path, [], manifesto=manifesto, sobrescrever={"PESSOA.jsonl": b"[1, 2]\n"})

    with pytest.raises(CopiaInvalida, match="esperava um objeto"):
        carregar_copia(caminho)


def test_arquivo_que_nao_esta_em_utf8(tmp_path):
    manifesto = {
        "extracao": "07/10/2026 05:00:17",
        "tabelas": {n: {"linhas": 0, "colunas": COLUNAS[n]} for n in COLUNAS},
    }
    caminho = escrever_copia(tmp_path, [], manifesto=manifesto, sobrescrever={"PESSOA.jsonl": b"\xff\xfe\x00"})

    with pytest.raises(CopiaInvalida, match="UTF-8"):
        carregar_copia(caminho)


def test_periodo_sem_data_para_a_importacao(tmp_path):
    ruim = {"ID_PESSOA": 1, "DT_INI_STATUS": None, "DT_FIM_STATUS": "2026-12-31", "CD_STATUS": "A"}
    caminho = escrever_copia(tmp_path, [pessoa(1)], [ruim])

    with pytest.raises(CopiaInvalida, match="período sem data"):
        carregar_copia(caminho)


def test_tabela_grande_demais_e_recusada(tmp_path, monkeypatch):
    caminho = escrever_copia(tmp_path, [pessoa(1)])
    monkeypatch.setattr(imp, "TAMANHO_MAXIMO_TABELA", 10)

    with pytest.raises(CopiaInvalida, match="grande demais"):
        carregar_copia(caminho)


# ------------------------------------------------------------------ importar: quem entra e quem fica de fora


def test_importa_a_matricula_que_e_o_id_e_nao_o_cd_pessoa(conn, tmp_path):
    # Caso real que o Thiago conferiu na tela do Data4U: a matrícula é o ID (5022), não o CD_PESSOA.
    pessoa_com_dois_numeros = pessoa(5022, "FULANO TESTE", CD_PESSOA=18295)
    importar_de(conn, tmp_path, [pessoa_com_dois_numeros], [periodo(5022, "A")])

    assert por_matricula(conn, 5022)["nome"] == "FULANO TESTE"
    assert por_matricula(conn, 18295) is None


def test_importa_os_dados_do_aluno(conn, tmp_path):
    relatorio = importar_de(
        conn,
        tmp_path,
        [pessoa(10, "  ANA   PAULA  SOUZA ", "123.456.789-09")],
        [periodo(10, "P")],
        [contato(1, 10, "(27) 98888-7766")],
    )

    aluno = por_matricula(conn, 10)
    assert aluno["nome"] == "ANA PAULA SOUZA"  # espaços das pontas e do meio arrumados
    assert aluno["cpf"] == "12345678909"
    assert aluno["whatsapp"] == "27988887766"
    assert aluno["situacao"] == "P"
    assert aluno["provisorio"] == 0
    assert aluno["whatsapp_corrigido_no_app"] == 0
    assert aluno["criado_em"] == "2026-10-07 08:30:15"  # o instante da importação, em UTC
    assert (relatorio.novos, relatorio.atualizados, relatorio.iguais) == (1, 0, 0)


def test_as_seis_situacoes_entram(conn, tmp_path):
    letras = "ATPDIC"
    pessoas = [pessoa(i, f"ALUNO {l}") for i, l in enumerate(letras, start=1)]
    periodos = [periodo(i, l) for i, l in enumerate(letras, start=1)]

    relatorio = importar_de(conn, tmp_path, pessoas, periodos)

    assert [a["situacao"] for a in alunos(conn)] == list(letras)
    assert dict(relatorio.por_situacao) == {l: 1 for l in letras}


def test_quem_fica_de_fora_e_por_que(conn, tmp_path):
    pessoas = [
        pessoa(1, "ENTRA"),
        pessoa(2, "EMPRESA", tipo="J"),
        pessoa(3, "APAGADO", apagada="T"),
        pessoa(0, "ID ZERO"),
        pessoa(-1, "ID NEGATIVO"),
        pessoa(4, "SEM SITUACAO"),
        pessoa(5, "AMBIGUO"),
        pessoa(6, "LETRA F"),
        pessoa(7, "   "),
        pessoa(8, None),
    ]
    periodos = [
        periodo(1, "A"), periodo(2, "A"), periodo(3, "A"), periodo(0, "A"), periodo(-1, "A"),
        periodo(5, "A"), periodo(5, "D"), periodo(6, "F"), periodo(7, "A"), periodo(8, "A"),
    ]

    relatorio = importar_de(conn, tmp_path, pessoas, periodos)

    assert [a["nome"] for a in alunos(conn)] == ["ENTRA"]
    assert relatorio.pessoas_na_copia == 10
    assert relatorio.fora_pessoa_juridica == 1
    assert relatorio.fora_apagadas == 1
    assert relatorio.fora_id_interno == 2
    assert relatorio.fora_sem_situacao == 1
    assert relatorio.fora_situacao_ambigua == 1
    assert dict(relatorio.fora_situacao_desconhecida) == {"F": 1}
    assert relatorio.fora_sem_nome == 2
    assert relatorio.importadas == 1


def test_a_situacao_vem_da_data_da_copia_e_nao_da_data_de_hoje(conn, tmp_path):
    # Cópia tirada em 2020: nessa data a pessoa era ativa, hoje seria desistente.
    pessoas = [pessoa(1)]
    periodos = [periodo(1, "A", "2020-01-01", "2020-12-31"), periodo(1, "D", "2021-01-01", "7777-07-07")]

    importar_de(conn, tmp_path, pessoas, periodos, extracao="15/06/2020 05:00:00")

    assert por_matricula(conn, 1)["situacao"] == "A"


# ------------------------------------------------------------------ importar: dados que faltam


def test_pessoa_sem_cpf_entra_com_cpf_vazio(conn, tmp_path):
    relatorio = importar_de(conn, tmp_path, [pessoa(1, cpf=None), pessoa(2, cpf="")], [periodo(1, "A"), periodo(2, "A")])

    assert [a["cpf"] for a in alunos(conn)] == [None, None]
    assert relatorio.sem_cpf == 2 and relatorio.cpf_invalido == 0


def test_cpf_invalido_entra_vazio_e_e_contado_a_parte(conn, tmp_path):
    relatorio = importar_de(conn, tmp_path, [pessoa(1, cpf="1234567890")], [periodo(1, "A")])

    assert por_matricula(conn, 1)["cpf"] is None
    assert relatorio.cpf_invalido == 1 and relatorio.sem_cpf == 0


def test_cpf_repetido_em_duas_pessoas_entra_nas_duas(conn, tmp_path):
    importar_de(
        conn, tmp_path, [pessoa(1, "IRMAO A", "12345678909"), pessoa(2, "IRMAO B", "12345678909")],
        [periodo(1, "A"), periodo(2, "A")],
    )

    assert [a["cpf"] for a in alunos(conn)] == ["12345678909", "12345678909"]


def test_contagens_de_celular(conn, tmp_path):
    pessoas = [pessoa(i) for i in (1, 2, 3, 4)]
    periodos = [periodo(i, "A") for i in (1, 2, 3, 4)]
    contatos = [
        contato(1, 1, "27988887766"),  # serve
        contato(2, 2, "988887766"),  # sem DDD: não serve
        # pessoa 3: sem celular nenhum
        contato(3, 4, "27988887766"), contato(4, 4, "27977776655"),  # dois números válidos
    ]

    relatorio = importar_de(conn, tmp_path, pessoas, periodos, contatos)

    assert [a["whatsapp"] for a in alunos(conn)] == ["27988887766", None, None, "27988887766"]
    assert relatorio.sem_celular == 1
    assert relatorio.celular_que_nao_serve == 1
    assert relatorio.whatsapp_varios == 1


def test_contagens_so_contam_quem_entrou(conn, tmp_path):
    # quem ficou de fora não pode inflar "sem CPF" nem "sem celular"
    relatorio = importar_de(conn, tmp_path, [pessoa(1, cpf=None), pessoa(2, cpf=None)], [periodo(1, "A")])

    assert relatorio.importadas == 1
    assert relatorio.sem_cpf == 1 and relatorio.sem_celular == 1


# ------------------------------------------------------------------ importar: rodar de novo


def _base():
    return (
        [pessoa(1, "ANA", "11111111111"), pessoa(2, "BRUNO", "22222222222")],
        [periodo(1, "A"), periodo(2, "D")],
        [contato(1, 1, "27988887766")],
    )


def test_rodar_duas_vezes_nao_duplica_nem_muda_nada(conn, tmp_path):
    importar_de(conn, tmp_path, *_base())
    antes = alunos(conn)

    segunda = importar_de(conn, tmp_path, *_base())

    assert alunos(conn) == antes
    assert (segunda.novos, segunda.atualizados, segunda.iguais) == (0, 0, 2)


def test_o_que_mudou_no_data4u_atualiza_o_app_e_aluno_novo_e_acrescentado(conn, tmp_path):
    importar_de(conn, tmp_path, *_base())
    id_ana = por_matricula(conn, 1)["id"]

    pessoas = [pessoa(1, "ANA MARIA", "99999999999"), pessoa(2, "BRUNO", "22222222222"), pessoa(3, "CAIO", "33333333333")]
    periodos = [periodo(1, "P"), periodo(2, "D"), periodo(3, "A")]
    contatos = [contato(1, 1, "27977776655")]
    relatorio = importar_de(conn, tmp_path, pessoas, periodos, contatos)

    ana = por_matricula(conn, 1)
    assert (ana["nome"], ana["cpf"], ana["whatsapp"], ana["situacao"]) == ("ANA MARIA", "99999999999", "27977776655", "P")
    assert ana["id"] == id_ana  # é o mesmo registro (os treinos continuam ligados a ele)
    assert por_matricula(conn, 3)["nome"] == "CAIO"
    assert (relatorio.novos, relatorio.atualizados, relatorio.iguais) == (1, 1, 1)


def test_se_o_data4u_apagar_o_celular_o_app_acompanha(conn, tmp_path):
    importar_de(conn, tmp_path, *_base())

    importar_de(conn, tmp_path, _base()[0], _base()[1], [])

    assert por_matricula(conn, 1)["whatsapp"] is None


def test_whatsapp_corrigido_no_app_nao_e_sobrescrito_mas_o_resto_atualiza(conn, tmp_path):
    importar_de(conn, tmp_path, *_base())
    conn.execute("UPDATE aluno SET whatsapp = '27911112222', whatsapp_corrigido_no_app = 1 WHERE data4u_id = 1")
    conn.commit()

    pessoas = [pessoa(1, "ANA NOVA", "11111111111"), pessoa(2, "BRUNO", "22222222222")]
    relatorio = importar_de(conn, tmp_path, pessoas, [periodo(1, "T"), periodo(2, "D")], [contato(1, 1, "27977776655")])

    ana = por_matricula(conn, 1)
    assert ana["whatsapp"] == "27911112222"  # o número corrigido pela recepção continua
    assert ana["whatsapp_corrigido_no_app"] == 1
    assert (ana["nome"], ana["situacao"]) == ("ANA NOVA", "T")  # o resto é atualizado
    assert relatorio.whatsapp_mantido_do_app == 1 and relatorio.atualizados == 1


def test_aluno_que_nao_veio_na_copia_continua_no_app_com_os_treinos(conn, tmp_path):
    importar_de(conn, tmp_path, *_base())
    ana = por_matricula(conn, 1)
    conn.execute("INSERT INTO exercicio (nome, origem) VALUES ('SUPINO', 'app')")
    conn.execute(
        "INSERT INTO treino (aluno_id, nome, montado_por) VALUES (?, 'TREINO A', 'Professor')", (ana["id"],)
    )
    conn.commit()

    relatorio = importar_de(conn, tmp_path, [pessoa(2, "BRUNO", "22222222222")], [periodo(2, "D")])

    assert por_matricula(conn, 1) == ana  # intacto
    assert conn.execute("SELECT COUNT(*) FROM treino WHERE aluno_id = ?", (ana["id"],)).fetchone()[0] == 1
    assert relatorio.no_app_e_fora_da_copia == 1


def test_aluno_provisorio_sem_par_no_data4u_nao_e_tocado(conn, tmp_path):
    conn.execute("INSERT INTO aluno (nome, cpf, provisorio) VALUES ('PROVISORIO', '12345678909', 1)")
    conn.commit()

    relatorio = importar_de(conn, tmp_path, *_base())

    provisorio = conn.execute("SELECT * FROM aluno WHERE provisorio = 1").fetchone()
    assert (provisorio["nome"], provisorio["data4u_id"], provisorio["situacao"]) == ("PROVISORIO", None, None)
    assert relatorio.no_app_e_fora_da_copia == 0  # o provisório não conta (não tem matrícula)
    assert conn.execute("SELECT COUNT(*) FROM aluno").fetchone()[0] == 3


# ------------------------------------------------------------------ importar: tudo ou nada


def test_se_der_erro_no_meio_nada_fica_gravado(conn, tmp_path):
    importar_de(conn, tmp_path, *_base())
    antes = alunos(conn)
    conn.execute(
        "CREATE TRIGGER explode BEFORE INSERT ON aluno WHEN NEW.nome = 'EXPLODE' "
        "BEGIN SELECT RAISE(ABORT, 'erro de teste'); END"
    )

    pessoas = [pessoa(1, "ANA MUDOU", "11111111111"), pessoa(2, "BRUNO"), pessoa(3, "CAIO NOVO"), pessoa(4, "EXPLODE")]
    periodos = [periodo(i, "A") for i in (1, 2, 3, 4)]
    with pytest.raises(sqlite3.IntegrityError, match="erro de teste"):
        importar_de(conn, tmp_path, pessoas, periodos)

    assert alunos(conn) == antes  # nem o aluno novo, nem a alteração da Ana


# ------------------------------------------------------------------ relatório


def test_relatorio_em_texto_nao_traz_dado_pessoal(conn, tmp_path):
    relatorio = importar_de(
        conn, tmp_path, [pessoa(77, "NOME SECRETO", "12345678909")], [periodo(77, "A")], [contato(1, 77, "27988887766")]
    )

    texto = relatorio.texto()

    assert "NOME SECRETO" not in texto and "12345678909" not in texto and "27988887766" not in texto
    assert "07/10/2026 05:00" in texto
    assert "1 novos" in texto and "Ativo 1" in texto


# ------------------------------------------------------------------ linha de comando


def test_linha_de_comando_cria_o_banco_importa_e_imprime_o_relatorio(tmp_path, capsys):
    caminho = escrever_copia(tmp_path, [pessoa(1, "ANA"), pessoa(2, "BRUNO")], [periodo(1, "A"), periodo(2, "D")])
    banco = tmp_path / "app.db"

    codigo = main([str(caminho), str(banco)])

    saida = capsys.readouterr().out
    assert codigo == 0
    assert "2 novos" in saida
    conn = conectar(banco)
    assert conn.execute("SELECT COUNT(*) FROM aluno").fetchone()[0] == 2
    conn.close()


def test_linha_de_comando_rodada_de_novo_diz_que_nao_mudou_nada(tmp_path, capsys):
    caminho = escrever_copia(tmp_path, [pessoa(1)], [periodo(1, "A")])
    banco = tmp_path / "app.db"
    main([str(caminho), str(banco)])
    capsys.readouterr()

    assert main([str(caminho), str(banco)]) == 0

    assert "0 novos, 0 atualizados, 1 sem mudança" in capsys.readouterr().out


def test_linha_de_comando_com_copia_ruim_nao_cria_banco_e_sai_com_erro(tmp_path, capsys):
    caminho = escrever_copia(tmp_path, [pessoa(1)], tirar=("PESSOA_STATUS.jsonl",))
    banco = tmp_path / "app.db"

    codigo = main([str(caminho), str(banco)])

    assert codigo == 1
    assert "nada foi gravado" in capsys.readouterr().err
    assert not banco.exists()
