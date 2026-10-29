"""Testes do programa que roda no PC da recepção e manda os alunos sozinho (app/static/recepcao/enviar_alunos.py).

Três tipos de teste:
- unitários: cada peça sozinha (ler o .zip, conferir contra o manifesto, decidir o que enviar, tentar de novo...);
- de contrato: roda o JavaScript de verdade (Node) e o Python sobre o MESMO .zip e exige pacotes iguais, porque o
  defeito perigoso mora na junção (uma coluna a mais, um número onde o servidor quer texto);
- de ponta a ponta: sobe o servidor de verdade (Flask) e roda o programa contra ele, com autorização, envio e banco.

Todos os dados são inventados: nomes, CPFs, telefones e matrículas.
"""

import ast
import builtins
import importlib.util
import json
import shutil
import subprocess
import sys
import threading
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from werkzeug.serving import make_server

from app import acesso, importar_alunos, importar_treinos
from app.datas import FUSO_DA_ACADEMIA
from app.db import conectar, criar_tabelas
from app.web import criar_app

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_DO_PROGRAMA = RAIZ / "app" / "static" / "recepcao" / "enviar_alunos.py"
MODULO_JS = (RAIZ / "app" / "static" / "copia_modelo.js").as_uri()
ZIP_JS = (RAIZ / "app" / "static" / "zip_leitor.js").as_uri()

_especificacao = importlib.util.spec_from_file_location("enviar_alunos", CAMINHO_DO_PROGRAMA)
ea = importlib.util.module_from_spec(_especificacao)
sys.modules["enviar_alunos"] = ea
_especificacao.loader.exec_module(ea)

AGORA_DA_COPIA = "14/10/2026 05:00:17"


# ------------------------------------------------------------------ uma cópia do Data4U de mentira


def dados_do_data4u() -> dict[str, list[dict]]:
    """Um pedaço de cópia do Data4U como ela é de verdade: colunas a mais, número onde o app quer texto, CPF como
    número, e-mail e telefone fixo, lançamentos que não são de treino, professores e exercícios que ninguém usou."""
    return {
        "PESSOA": [
            {"ID": 101, "NM_PESSOA": "ANA FICTICIA", "TP_PESSOA": "F", "NR_CPF": 11144477735, "NR_RG": "9", "ST_DELETED": "F",
             "NR_CEP": 29122300, "CD_UF": "ES", "DS_LOCALIDADE": "VILA VELHA", "DS_BAIRRO": "GLÓRIA", "DS_LOGRADOURO": "RUA DAS FLORES, 10",
             "DS_COMPLEMENTO": None, "DT_NASCIMENTO": "1990-01-01"},
            {"ID": 102, "NM_PESSOA": "BRUNO FICTICIO", "TP_PESSOA": "F", "NR_CPF": 52998224725, "NR_RG": "8", "ST_DELETED": "F",
             "NR_CEP": None, "CD_UF": None, "DS_LOCALIDADE": None, "DS_BAIRRO": None, "DS_LOGRADOURO": None, "DS_COMPLEMENTO": None,
             "DT_NASCIMENTO": None},
            {"ID": 900, "NM_PESSOA": "PROF ANA", "TP_PESSOA": "F", "NR_CPF": None, "NR_RG": None, "ST_DELETED": "F",
             "NR_CEP": None, "CD_UF": None, "DS_LOCALIDADE": None, "DS_BAIRRO": None, "DS_LOGRADOURO": None, "DS_COMPLEMENTO": None,
             "DT_NASCIMENTO": None},
            {"ID": 901, "NM_PESSOA": "PROF QUE NAO MONTOU", "TP_PESSOA": "F", "NR_CPF": None, "NR_RG": None, "ST_DELETED": "F",
             "NR_CEP": None, "CD_UF": None, "DS_LOCALIDADE": None, "DS_BAIRRO": None, "DS_LOGRADOURO": None, "DS_COMPLEMENTO": None,
             "DT_NASCIMENTO": None},
        ],
        "PESSOA_STATUS": [
            {"ID_PESSOA": 101, "DT_INI_STATUS": "2026-01-01", "DT_FIM_STATUS": "7777-07-07", "CD_STATUS": "A"},
            {"ID_PESSOA": 102, "DT_INI_STATUS": "2026-01-01", "DT_FIM_STATUS": "7777-07-07", "CD_STATUS": "A"},
        ],
        "CONTATO_PESSOA": [
            {"ID_CONTATO": 1, "ID_PESSOA": 101, "ID_TIPO_CONTATO": 30, "DS_CONTATO": 27988887766},
            {"ID_CONTATO": 2, "ID_PESSOA": 101, "ID_TIPO_CONTATO": 100, "DS_CONTATO": "ana@exemplo.com.br"},
            {"ID_CONTATO": 3, "ID_PESSOA": 102, "ID_TIPO_CONTATO": 20, "DS_CONTATO": "2733334444"},
        ],
        "TREINO": [
            {"ID_TREINO": 1, "ID_LANCAMENTO": 5001, "ID_PROFESSOR": 900, "NM_TREINO": "TREINO ABC", "DT_INICIO": "2026-03-02", "DS_OBS": "x", "ST_DELETED": "F"},
            {"ID_TREINO": 2, "ID_LANCAMENTO": None, "ID_PROFESSOR": None, "NM_TREINO": "MODELO", "DT_INICIO": None, "DS_OBS": None, "ST_DELETED": "F"},
            {"ID_TREINO": 3, "ID_LANCAMENTO": 5002, "ID_PROFESSOR": 900, "NM_TREINO": "APAGADO", "DT_INICIO": "2026-03-05", "DS_OBS": None, "ST_DELETED": "T"},
        ],
        "TREINO_FICHA": [
            {"ID_TREINO_FICHA": 11, "ID_TREINO": 1, "NR_FICHA": 1, "NM_TREINO_FICHA": "A", "DT_ULTIMA_SESSAO": None},
            {"ID_TREINO_FICHA": 12, "ID_TREINO": 1, "NR_FICHA": 2, "NM_TREINO_FICHA": "B", "DT_ULTIMA_SESSAO": None},
            {"ID_TREINO_FICHA": 21, "ID_TREINO": 2, "NR_FICHA": 1, "NM_TREINO_FICHA": "A", "DT_ULTIMA_SESSAO": None},
        ],
        "TREINO_PRESCRICAO": [
            {"ID_TREINO_PRESCRICAO": 101, "ID_TREINO_FICHA": 11, "ID_TREINO_EXERCICIO": -5, "NR_ORDEM": 1, "NR_SERIE": 3, "DS_REPETICAO": "12", "DS_PESO": 20.0, "TM_PAUSA": "00:01:00", "DS_PRESCRICAO_OBS": "devagar"},
            {"ID_TREINO_PRESCRICAO": 102, "ID_TREINO_FICHA": 11, "ID_TREINO_EXERCICIO": 7, "NR_ORDEM": 2, "NR_SERIE": None, "DS_REPETICAO": "10", "DS_PESO": None, "TM_PAUSA": None, "DS_PRESCRICAO_OBS": None},
            {"ID_TREINO_PRESCRICAO": 103, "ID_TREINO_FICHA": 12, "ID_TREINO_EXERCICIO": 555, "NR_ORDEM": 1, "NR_SERIE": "4", "DS_REPETICAO": "8", "DS_PESO": 12.5, "TM_PAUSA": "00:00:30", "DS_PRESCRICAO_OBS": None},
            {"ID_TREINO_PRESCRICAO": 201, "ID_TREINO_FICHA": 21, "ID_TREINO_EXERCICIO": 7, "NR_ORDEM": 1, "NR_SERIE": "3", "DS_REPETICAO": "12", "DS_PESO": None, "TM_PAUSA": None, "DS_PRESCRICAO_OBS": None},
            {"ID_TREINO_PRESCRICAO": 104, "ID_TREINO_FICHA": 12, "ID_TREINO_EXERCICIO": None, "NR_ORDEM": 2, "NR_SERIE": "3", "DS_REPETICAO": "15", "DS_PESO": "MODERADO", "TM_PAUSA": "00:00:00", "DS_PRESCRICAO_OBS": None},
            {"ID_TREINO_PRESCRICAO": 105, "ID_TREINO_FICHA": 12, "ID_TREINO_EXERCICIO": None, "NR_ORDEM": 3, "NR_SERIE": None, "DS_REPETICAO": None, "DS_PESO": None, "TM_PAUSA": "00:00:00", "DS_PRESCRICAO_OBS": None},
        ],
        "TREINO_EXERCICIO": [
            {"ID_TREINO_EXERCICIO": -5, "NM_EXERCICIO": "<b>SUPINO RETO</b> APAGADO", "DS_ANIMACAO": "a.gif", "ST_DELETED": "T"},
            {"ID_TREINO_EXERCICIO": 7, "NM_EXERCICIO": "REMADA BAIXA", "DS_ANIMACAO": None, "ST_DELETED": "F"},
            {"ID_TREINO_EXERCICIO": 8, "NM_EXERCICIO": "NUNCA USADO", "DS_ANIMACAO": None, "ST_DELETED": "F"},
        ],
        "LANCAMENTO_OBJ": [
            {"ID_LANCAMENTO": 5001, "ID_OBJ": 101, "TP_LANCAMENTO": -510, "DT_LANCAMENTO": "2026-03-02 14:03:24", "ID_PESSOA": 900, "VL_LANCAMENTO": 0},
            {"ID_LANCAMENTO": 5002, "ID_OBJ": 101, "TP_LANCAMENTO": -510, "DT_LANCAMENTO": "2026-03-05 09:00:00", "ID_PESSOA": 900, "VL_LANCAMENTO": 0},
            {"ID_LANCAMENTO": 7777, "ID_OBJ": 101, "TP_LANCAMENTO": 1, "DT_LANCAMENTO": "2026-03-05 09:00:00", "ID_PESSOA": 1, "VL_LANCAMENTO": 150},
        ],
    }


def escrever_base(pasta: Path, extracao: str = AGORA_DA_COPIA, tabelas=None, nome=ea.NOME_DO_ZIP, manifesto=None) -> Path:
    """Escreve um base_total.zip de mentira (com deflate, como o de verdade) e uma tabela grande que NUNCA deve ser lida."""
    tabelas = dados_do_data4u() if tabelas is None else tabelas
    if manifesto is None:
        manifesto = {
            "extracao": extracao,
            "tabelas": {t: {"linhas": len(l), "colunas": list(l[0]) if l else []} for t, l in tabelas.items()},
        }
    caminho = pasta / nome
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as arquivo:
        arquivo.writestr("_manifesto.json", json.dumps(manifesto))
        for tabela, linhas in tabelas.items():
            arquivo.writestr(tabela + ".jsonl", "".join(json.dumps(l, ensure_ascii=False) + "\n" for l in linhas))
        arquivo.writestr("OCORRENCIA.jsonl", "isto nao e json e nao deve ser lido\n")
    return caminho


def agora_em_brasilia() -> datetime:
    return datetime.now(timezone.utc).astimezone(FUSO_DA_ACADEMIA).replace(microsecond=0)


def texto_da_extracao(momento: datetime) -> str:
    return f"{momento:%d/%m/%Y %H:%M:%S}"


# ------------------------------------------------------------------ só biblioteca padrão


def test_o_programa_so_usa_a_biblioteca_padrao_do_python():
    """No PC da recepção não há como instalar nada: qualquer import de fora quebraria o envio em silêncio."""
    arvore = ast.parse(CAMINHO_DO_PROGRAMA.read_text(encoding="utf-8"))
    modulos = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            modulos.update(a.name.split(".")[0] for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.level == 0:
            modulos.add(no.module.split(".")[0])

    assert modulos <= set(sys.stdlib_module_names), modulos - set(sys.stdlib_module_names)


# ------------------------------------------------------------------ as colunas combinam com o servidor e com o navegador


def test_as_colunas_combinam_com_o_servidor():
    assert {t: tuple(c) for t, c in ea.COLUNAS_ENVIADAS.items()} == importar_alunos.COLUNAS_NECESSARIAS
    assert {t: tuple(c) for t, c in ea.COLUNAS_DOS_TREINOS.items()} == importar_treinos.COLUNAS_NECESSARIAS


@pytest.mark.skipif(shutil.which("node") is None, reason="Node não está instalado")
def test_as_colunas_e_o_tipo_de_contato_combinam_com_o_navegador():
    saida = subprocess.run(
        ["node", "--input-type=module", "-e", f"""
            import * as m from "{MODULO_JS}";
            console.log(JSON.stringify({{ alunos: m.COLUNAS_ENVIADAS, treinos: m.COLUNAS_DOS_TREINOS, celular: m.TIPO_CONTATO_CELULAR }}));
        """],
        capture_output=True, text=True, timeout=60, check=False, cwd=RAIZ,
    )
    assert saida.returncode == 0, saida.stderr
    js = json.loads(saida.stdout)

    assert js["alunos"] == ea.COLUNAS_ENVIADAS
    assert js["treinos"] == ea.COLUNAS_DOS_TREINOS
    assert js["celular"] == ea.TIPO_CONTATO_CELULAR


# ------------------------------------------------------------------ contrato: o mesmo .zip dá o mesmo pacote no JavaScript e no Python


def _pacotes_do_javascript(caminho_do_zip: Path) -> dict:
    codigo = f"""
        import fs from "node:fs";
        import * as Z from "{ZIP_JS}";
        import * as M from "{MODULO_JS}";
        const bytes = new Uint8Array(fs.readFileSync({json.dumps(str(caminho_do_zip))}));
        const entradas = Z.listarEntradas(bytes);
        const nomes = [...M.ARQUIVOS_NECESSARIOS, ...M.ARQUIVOS_DOS_TREINOS];  // os mesmos que a tela do navegador abre
        const arquivos = {{}};
        for (const nome of nomes) arquivos[nome] = await Z.lerEntrada(bytes, entradas, nome, M.TAMANHO_MAXIMO_DA_TABELA);
        const a = M.montarPacote(arquivos);
        const t = M.montarPacoteDeTreinos(arquivos);
        console.log(JSON.stringify({{ alunos: a.pacote, treinos: t.pacote, resumoAlunos: a.resumo, resumoTreinos: t.resumo }}));
    """
    resultado = subprocess.run(
        ["node", "--input-type=module", "-e", codigo], capture_output=True, text=True, timeout=120, check=False, cwd=RAIZ
    )
    assert resultado.returncode == 0, resultado.stderr
    return json.loads(resultado.stdout)


def _pacotes_do_python(caminho_do_zip: Path):
    alunos = ea.montar_pacote(ea.ler_arquivos_do_zip(caminho_do_zip, ea.TABELAS_DOS_ALUNOS))
    treinos = ea.montar_pacote_de_treinos(ea.ler_arquivos_do_zip(caminho_do_zip, ea.TABELAS_DOS_TREINOS))
    return alunos, treinos


@pytest.mark.skipif(shutil.which("node") is None, reason="Node não está instalado")
def test_o_pacote_do_python_e_igual_ao_do_navegador_para_o_mesmo_zip(tmp_path):
    caminho = escrever_base(tmp_path)

    js = _pacotes_do_javascript(caminho)
    (alunos, resumo_alunos), (treinos, resumo_treinos) = _pacotes_do_python(caminho)

    assert alunos == js["alunos"]
    assert treinos == js["treinos"]
    assert resumo_alunos == js["resumoAlunos"]
    assert resumo_treinos == js["resumoTreinos"]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node não está instalado")
def test_o_pacote_do_python_e_igual_ao_do_navegador_com_numeros_e_nulos_estranhos(tmp_path):
    tabelas = dados_do_data4u()
    tabelas["PESSOA"][0]["NR_CPF"] = 1234567890.0  # número com ".0"
    tabelas["PESSOA"][1]["NM_PESSOA"] = "JOÃO ÇÃO — 日本"  # acentos e fora do alfabeto latino
    tabelas["PESSOA"][2]["ST_DELETED"] = True  # booleano onde o app quer texto
    tabelas["TREINO_PRESCRICAO"][0]["DS_PESO"] = 100.0
    tabelas["TREINO_PRESCRICAO"][2]["DS_PESO"] = 0.00001
    tabelas["TREINO_PRESCRICAO"][3]["DS_PESO"] = -3.0
    tabelas["TREINO_PRESCRICAO"][3]["NR_SERIE"] = 0.0
    tabelas["CONTATO_PESSOA"][0]["ID_TIPO_CONTATO"] = 30.0  # o JavaScript lê 30.0 como 30
    tabelas["CONTATO_PESSOA"][1]["ID_TIPO_CONTATO"] = "30"  # texto: não é celular
    caminho = escrever_base(tmp_path, tabelas=tabelas)

    js = _pacotes_do_javascript(caminho)
    (alunos, _), (treinos, _) = _pacotes_do_python(caminho)

    assert alunos == js["alunos"]
    assert treinos == js["treinos"]
    celulares = alunos["tabelas"]["CONTATO_PESSOA"]["linhas"]
    assert [l[0] for l in celulares] == [1]  # só o contato 1 (30.0)
    assert alunos["tabelas"]["PESSOA"]["linhas"][0][3] == "1234567890"


def test_o_pacote_do_python_so_leva_o_que_o_app_usa(tmp_path):
    caminho = escrever_base(tmp_path)

    (alunos, resumo_alunos), (treinos, resumo_treinos) = _pacotes_do_python(caminho)

    assert alunos["extracao"] == treinos["extracao"] == AGORA_DA_COPIA
    assert alunos["tabelas"]["PESSOA"]["colunas"] == [  # sem RG e sem nascimento; com o endereço ("Meu perfil", 29/10/2026)
        "ID", "NM_PESSOA", "TP_PESSOA", "NR_CPF", "ST_DELETED", "NR_CEP", "CD_UF", "DS_LOCALIDADE", "DS_BAIRRO", "DS_LOGRADOURO", "DS_COMPLEMENTO"]
    assert alunos["tabelas"]["PESSOA"]["linhas"][0] == [  # CPF e CEP viraram texto
        101, "ANA FICTICIA", "F", "11144477735", "F", "29122300", "ES", "VILA VELHA", "GLÓRIA", "RUA DAS FLORES, 10", None]
    assert alunos["tabelas"]["CONTATO_PESSOA"]["linhas"] == [  # celular e e-mail; sem telefone fixo
        [1, 101, 30, "27988887766"], [2, 101, 100, "ana@exemplo.com.br"]]
    assert resumo_alunos["linhas"] == {"PESSOA": 4, "PESSOA_STATUS": 2, "CONTATO_PESSOA": 3}
    assert [l[0] for l in treinos["tabelas"]["PESSOA"]["linhas"]] == [900]  # só o professor que montou treino
    assert [l[0] for l in treinos["tabelas"]["LANCAMENTO_OBJ"]["linhas"]] == [5001, 5002]  # o 7777 não é de treino
    assert [l[0] for l in treinos["tabelas"]["TREINO_EXERCICIO"]["linhas"]] == [-5, 7]  # o 8 ninguém usou
    assert resumo_treinos == {"treinos": 3, "fichas": 3, "prescricoes": 6}
    assert "OCORRENCIA" not in json.dumps(alunos) + json.dumps(treinos)


def test_os_pacotes_do_python_passam_no_servidor(tmp_path):
    caminho = escrever_base(tmp_path, extracao=texto_da_extracao(agora_em_brasilia()))

    (alunos, _), (treinos, _) = _pacotes_do_python(caminho)

    copia = importar_alunos.copia_de_pacote(alunos)
    assert len(copia.pessoas) == 4 and copia.com_perfil
    assert len(importar_treinos.copia_de_pacote(treinos).linhas["TREINO"]) == 3


def test_copia_sem_as_colunas_do_endereco_vai_sem_elas_e_o_servidor_aceita(tmp_path):
    dados = dados_do_data4u()
    for pessoa in dados["PESSOA"]:
        for coluna in ea.COLUNAS_DO_ENDERECO:
            pessoa.pop(coluna)
    caminho = escrever_base(tmp_path, extracao=texto_da_extracao(agora_em_brasilia()), tabelas=dados)

    (alunos, _), _ = _pacotes_do_python(caminho)

    assert alunos["tabelas"]["PESSOA"]["colunas"] == ["ID", "NM_PESSOA", "TP_PESSOA", "NR_CPF", "ST_DELETED"]
    assert importar_alunos.copia_de_pacote(alunos).com_perfil is False


# ------------------------------------------------------------------ ler o .zip e conferir contra o manifesto


def _arquivos(tmp_path, **mudancas) -> dict:
    caminho = escrever_base(tmp_path, **mudancas)
    return ea.ler_arquivos_do_zip(caminho, ea.TABELAS_DOS_TREINOS)


def test_so_as_tabelas_pedidas_sao_abertas_do_zip(tmp_path):
    caminho = escrever_base(tmp_path)

    arquivos = ea.ler_arquivos_do_zip(caminho, ["PESSOA"])

    assert sorted(arquivos) == ["PESSOA.jsonl", "_manifesto.json"]  # a OCORRENCIA (que nem é JSON) nem foi lida


def test_zip_cortado_ou_estragado_e_recusado(tmp_path):
    caminho = escrever_base(tmp_path)
    caminho.write_bytes(caminho.read_bytes()[:-40])

    with pytest.raises(ea.CopiaInvalida, match="danificado"):
        ea.ler_arquivos_do_zip(caminho, ["PESSOA"])


def test_zip_que_nao_e_zip_e_recusado(tmp_path):
    (tmp_path / "base_total.zip").write_text("nada a ver", encoding="utf-8")

    with pytest.raises(ea.CopiaInvalida, match="danificado"):
        ea.ler_arquivos_do_zip(tmp_path / "base_total.zip", ["PESSOA"])


def test_tabela_que_falta_no_zip_e_recusada(tmp_path):
    tabelas = dados_do_data4u()
    del tabelas["TREINO_FICHA"]
    caminho = escrever_base(tmp_path, tabelas=tabelas)

    with pytest.raises(ea.CopiaInvalida, match=r"Não achei TREINO_FICHA\.jsonl"):
        ea.ler_arquivos_do_zip(caminho, ea.TABELAS_DOS_TREINOS)


def test_tabela_grande_demais_e_recusada(tmp_path, monkeypatch):
    caminho = escrever_base(tmp_path)
    monkeypatch.setattr(ea, "TAMANHO_MAXIMO_DA_TABELA", 10)

    with pytest.raises(ea.CopiaInvalida, match="grande demais"):
        ea.ler_arquivos_do_zip(caminho, ["PESSOA"])


def test_manifesto_com_menos_linhas_que_o_arquivo_acusa_copia_cortada(tmp_path):
    tabelas = dados_do_data4u()
    manifesto = {"extracao": AGORA_DA_COPIA, "tabelas": {t: {"linhas": len(l), "colunas": list(l[0])} for t, l in tabelas.items()}}
    manifesto["tabelas"]["PESSOA"]["linhas"] = 5  # o arquivo tem 4
    arquivos = _arquivos(tmp_path, tabelas=tabelas, manifesto=manifesto)

    with pytest.raises(ea.CopiaInvalida, match=r"PESSOA: o manifesto diz 5 linhas e o arquivo tem 4"):
        ea.montar_pacote(arquivos)


def test_coluna_que_falta_na_copia_e_recusada(tmp_path):
    tabelas = dados_do_data4u()
    for linha in tabelas["PESSOA"]:
        del linha["NR_CPF"]
    arquivos = _arquivos(tmp_path, tabelas=tabelas)

    with pytest.raises(ea.CopiaInvalida, match=r"PESSOA .* NR_CPF"):
        ea.montar_pacote(arquivos)


def test_tabela_fora_do_manifesto_e_recusada(tmp_path):
    manifesto = {"extracao": AGORA_DA_COPIA, "tabelas": {}}
    arquivos = _arquivos(tmp_path, manifesto=manifesto)

    with pytest.raises(ea.CopiaInvalida, match="O manifesto não descreve a tabela PESSOA"):
        ea.montar_pacote(arquivos)


@pytest.mark.parametrize("manifesto", [b"nao e json", b"[]", b'{"extracao": 5, "tabelas": {}}', b'{"extracao": "x"}', b"\xff\xfe"])
def test_manifesto_fora_do_formato_e_recusado(manifesto):
    with pytest.raises(ea.CopiaInvalida, match="manifesto"):
        ea.montar_pacote({"_manifesto.json": manifesto})


@pytest.mark.parametrize(
    ("conteudo", "mensagem"),
    [
        (b"{nao json}\n", "linha 1: não é JSON válido"),
        (b'{"ID": 1}\n[1, 2]\n', "linha 2: esperava um objeto JSON"),
        (b'{"ID": NaN}\n', "não é JSON válido"),
        (b'{"ID": Infinity}\n', "não é JSON válido"),
        (b"\xff\xfe\n", "não está em UTF-8"),
    ],
)
def test_linha_estragada_e_recusada_com_o_numero_da_linha(conteudo, mensagem):
    with pytest.raises(ea.CopiaInvalida, match=mensagem):
        ea._linhas_json(conteudo, "PESSOA")


def test_linhas_em_branco_sao_ignoradas():
    assert ea._linhas_json(b'\n{"ID": 1}\n\n   \n{"ID": 2}\n', "PESSOA") == [{"ID": 1}, {"ID": 2}]


def test_valor_composto_onde_se_espera_texto_e_recusado(tmp_path):
    tabelas = dados_do_data4u()
    tabelas["PESSOA"][0]["NM_PESSOA"] = ["lista"]
    arquivos = _arquivos(tmp_path, tabelas=tabelas)

    with pytest.raises(ea.CopiaInvalida, match="valor composto"):
        ea.montar_pacote(arquivos)


@pytest.mark.parametrize(
    ("valor", "texto"),
    [(None, None), ("x", "x"), (5, "5"), (-7, "-7"), (20.0, "20"), (12.5, "12.5"), (0.00001, "0.00001"), (-3.0, "-3"), (0.0, "0"), (True, "true"), (False, "false"), (1e20, "100000000000000000000")],
)
def test_numero_vira_o_mesmo_texto_que_o_javascript_faria(valor, texto):
    assert ea._para_texto(valor) == texto


@pytest.mark.parametrize("valor", [1e21, 1e-7, float("inf"), float("nan")])
def test_numero_que_o_javascript_escreveria_diferente_e_recusado(valor):
    with pytest.raises(ea.CopiaInvalida):
        ea._para_texto(valor)


# ------------------------------------------------------------------ decidir o que enviar


def test_data_da_extracao():
    assert ea.data_da_extracao("07/10/2026 05:00:17") == datetime(2026, 10, 7, 5, 0, 17)  # noqa: DTZ001
    for ruim in ["2026-10-07 05:00:17", "31/02/2026 05:00:00", "07/10/2026", "", None, 5]:
        assert ea.data_da_extracao(ruim) is None


def test_sem_nada_enviado_os_dois_assuntos_estao_pendentes():
    assert ea.etapas_pendentes({}, AGORA_DA_COPIA) == ["alunos", "treinos"]


def test_copia_ja_enviada_nao_e_enviada_de_novo():
    assert ea.etapas_pendentes({"alunos": AGORA_DA_COPIA, "treinos": AGORA_DA_COPIA}, AGORA_DA_COPIA) == []


def test_copia_mais_nova_e_enviada_e_mais_velha_nao():
    estado = {"alunos": "14/10/2026 05:00:17", "treinos": "14/10/2026 05:00:17"}

    assert ea.etapas_pendentes(estado, "14/10/2026 08:00:20") == ["alunos", "treinos"]
    assert ea.etapas_pendentes(estado, "13/10/2026 12:00:00") == []  # uma cópia mais velha não desfaz a mais nova


def test_so_o_assunto_que_falhou_fica_pendente():
    assert ea.etapas_pendentes({"alunos": AGORA_DA_COPIA}, AGORA_DA_COPIA) == ["treinos"]


def test_forcar_envia_tudo_de_novo():
    assert ea.etapas_pendentes({"alunos": AGORA_DA_COPIA, "treinos": AGORA_DA_COPIA}, AGORA_DA_COPIA, forcar=True) == ["alunos", "treinos"]


def test_data_da_copia_que_nao_se_entende_e_recusada():
    with pytest.raises(ea.CopiaInvalida, match="Não entendi a data"):
        ea.etapas_pendentes({}, "ontem")


def test_estado_estragado_vale_como_nada_enviado(tmp_path):
    (tmp_path / ea.ARQUIVO_DO_ESTADO).write_text("{isto nao e json", encoding="utf-8")
    assert ea.ler_estado(tmp_path) == {}
    (tmp_path / ea.ARQUIVO_DO_ESTADO).write_text('["lista"]', encoding="utf-8")
    assert ea.ler_estado(tmp_path) == {}
    (tmp_path / ea.ARQUIVO_DO_ESTADO).write_text('{"alunos": "x", "treinos": 5, "outro": "y"}', encoding="utf-8")
    assert ea.ler_estado(tmp_path) == {"alunos": "x"}


def test_estado_gravado_e_lido_de_volta(tmp_path):
    ea.gravar_estado(tmp_path, {"alunos": AGORA_DA_COPIA})

    assert ea.ler_estado(tmp_path) == {"alunos": AGORA_DA_COPIA}
    assert [p.name for p in tmp_path.iterdir()] == [ea.ARQUIVO_DO_ESTADO]  # o arquivo temporário não fica


# ------------------------------------------------------------------ endereço e resposta do servidor


@pytest.mark.parametrize("endereco", ["https://app.gloriafit.com.br", "https://app.gloriafit.com.br/", "http://localhost:8000", "http://127.0.0.1:5000"])
def test_enderecos_aceitos(endereco):
    assert ea.endereco_valido(endereco).startswith("http")


@pytest.mark.parametrize("endereco", ["http://app.gloriafit.com.br", "ftp://x.com", "app.gloriafit.com.br", "https://x.com/api", "https://x.com?a=1", "https://"])
def test_enderecos_recusados(endereco):
    with pytest.raises(ValueError):
        ea.endereco_valido(endereco)


def test_so_200_com_relatorio_e_sucesso():
    assert ea.interpretar_resposta(200, {"texto": "Pronto."}, "os alunos") == "Pronto."
    for status, corpo in [(200, {}), (200, None), (200, {"texto": 5})]:
        with pytest.raises(ea.SemRede, match="Nada foi confirmado"):
            ea.interpretar_resposta(status, corpo, "os alunos")


def test_401_pede_para_autorizar_de_novo():
    with pytest.raises(ea.NaoAutorizado, match="--autorizar"):
        ea.interpretar_resposta(401, {"erro": "x"}, "os alunos")


def test_400_repete_o_motivo_do_servidor_e_diz_que_nada_mudou():
    with pytest.raises(ea.CopiaInvalida, match="A cópia é velha demais. Nada foi alterado."):
        ea.interpretar_resposta(400, {"erro": "A cópia é velha demais."}, "os alunos")


def test_413_e_erros_do_servidor():
    with pytest.raises(ea.CopiaInvalida, match="grande demais"):
        ea.interpretar_resposta(413, None, "os alunos")
    for status in (302, 500, 502):
        with pytest.raises(ea.SemRede, match=str(status)):
            ea.interpretar_resposta(status, None, "o histórico de treinos")


# ------------------------------------------------------------------ o registro do que aconteceu


def test_registro_escreve_com_data_e_hora_e_nao_quebra_sem_pasta(tmp_path, capsys):
    registro = ea.Registro(tmp_path, agora=lambda: datetime(2026, 10, 14, 5, 15, 3))  # noqa: DTZ001
    registro("primeira\nsegunda")

    texto = (tmp_path / ea.ARQUIVO_DO_LOG).read_text(encoding="utf-8")
    assert texto == "14/10/2026 05:15:03  primeira\n14/10/2026 05:15:03  segunda\n"
    assert "primeira" in capsys.readouterr().out

    ea.Registro(tmp_path / "nao" / "existe")("não pode escrever, mas não pode quebrar")  # não levanta erro


def test_registro_gira_o_arquivo_quando_fica_grande(tmp_path, monkeypatch):
    monkeypatch.setattr(ea, "TAMANHO_MAXIMO_DO_LOG", 50)
    registro = ea.Registro(tmp_path)
    registro("x" * 100)

    registro("depois")

    assert (tmp_path / "enviar_alunos_log.antigo.txt").exists()
    assert "depois" in (tmp_path / ea.ARQUIVO_DO_LOG).read_text(encoding="utf-8")
    assert "xxxx" not in (tmp_path / ea.ARQUIVO_DO_LOG).read_text(encoding="utf-8")


# ------------------------------------------------------------------ esperar a extração e tentar de novo


def test_extracao_em_andamento_so_conta_se_o_arquivo_for_recente(tmp_path):
    assert ea.extracao_em_andamento(tmp_path) is False
    (tmp_path / ea.NOME_DO_ZIP_EM_CONSTRUCAO).write_bytes(b"x")
    assert ea.extracao_em_andamento(tmp_path) is True
    antigo = (tmp_path / ea.NOME_DO_ZIP_EM_CONSTRUCAO).stat().st_mtime + 31 * 60
    assert ea.extracao_em_andamento(tmp_path, agora=antigo) is False  # sobra de uma extração que falhou


def test_espera_a_extracao_terminar_e_segue(tmp_path):
    em_construcao = tmp_path / ea.NOME_DO_ZIP_EM_CONSTRUCAO
    em_construcao.write_bytes(b"x")
    mensagens, esperas = [], []

    def dormir(segundos):
        esperas.append(segundos)
        if len(esperas) == 3:
            em_construcao.unlink()  # a extração terminou

    ea.esperar_extracao(tmp_path, mensagens.append, dormir=dormir)

    assert esperas == [20, 20, 20]
    assert len(mensagens) == 1 and "espero ela terminar" in mensagens[0]


def test_desiste_de_esperar_a_extracao_depois_do_limite(tmp_path):
    (tmp_path / ea.NOME_DO_ZIP_EM_CONSTRUCAO).write_bytes(b"x")
    relogio_falso = {"agora": 0.0}
    mensagens = []

    def dormir(segundos):
        relogio_falso["agora"] += segundos

    # o arquivo "parece" sempre recente: o relógio de mentira é o mtime do arquivo
    mtime = (tmp_path / ea.NOME_DO_ZIP_EM_CONSTRUCAO).stat().st_mtime
    ea.esperar_extracao(tmp_path, mensagens.append, dormir=dormir, relogio=lambda: mtime + relogio_falso["agora"])

    assert relogio_falso["agora"] >= ea.MINUTOS_DE_ESPERA_PELA_EXTRACAO * 60
    assert "ainda não terminou" in mensagens[-1]


def test_tenta_de_novo_so_quando_nao_houve_conversa_com_o_servidor():
    chamadas, esperas, mensagens = [], [], []

    def enviar(*args):
        chamadas.append(args)
        if len(chamadas) < 3:
            raise ea.SemRede("internet ainda subindo")
        return 200, {"texto": "ok"}

    resposta = ea.enviar_com_tentativas(enviar, "http://x", "/r", {}, "chave", mensagens.append, dormir=esperas.append)

    assert resposta == (200, {"texto": "ok"})
    assert len(chamadas) == 3 and esperas == [ea.SEGUNDOS_ENTRE_TENTATIVAS] * 2


def test_depois_da_ultima_tentativa_o_erro_sobe():
    esperas = []

    def enviar(*_):
        raise ea.SemRede("sem internet")

    with pytest.raises(ea.SemRede):
        ea.enviar_com_tentativas(enviar, "http://x", "/r", {}, "chave", lambda _t: None, dormir=esperas.append)

    assert len(esperas) == ea.TENTATIVAS_SEM_REDE - 1


# ------------------------------------------------------------------ a tarefa agendada do Windows


def test_xml_da_tarefa_tem_os_tres_horarios_e_o_que_executar():
    xml = ea.xml_da_tarefa(r"C:\Python\pythonw.exe", r'"C:\Users\Atendimento\Desktop\NFSE\enviar_alunos.py"', r"C:\Users\Atendimento\Desktop\NFSE", r"PCRECEPCAO\Atendimento", datetime(2026, 10, 14))  # noqa: DTZ001
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    raiz = ET.fromstring(xml)

    assert [e.text for e in raiz.findall(".//t:StartBoundary", ns)] == [
        "2026-10-14T05:15:00", "2026-10-14T08:15:00", "2026-10-14T12:15:00",
    ]
    assert raiz.find(".//t:Exec/t:Command", ns).text == r"C:\Python\pythonw.exe"
    assert raiz.find(".//t:Exec/t:Arguments", ns).text == r'"C:\Users\Atendimento\Desktop\NFSE\enviar_alunos.py"'
    assert raiz.find(".//t:Exec/t:WorkingDirectory", ns).text == r"C:\Users\Atendimento\Desktop\NFSE"
    assert raiz.find(".//t:StartWhenAvailable", ns).text == "true"  # PC desligado na hora: roda quando ligar
    assert raiz.find(".//t:RunLevel", ns).text == "LeastPrivilege"  # não pede administrador
    assert raiz.find(".//t:UserId", ns).text == r"PCRECEPCAO\Atendimento"


def test_xml_da_tarefa_escapa_caracteres_especiais_e_aceita_sem_usuario():
    xml = ea.xml_da_tarefa(r"C:\A & B\pythonw.exe", "<arg>", r"C:\x", None, datetime(2026, 10, 14))  # noqa: DTZ001
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    raiz = ET.fromstring(xml)

    assert raiz.find(".//t:Exec/t:Command", ns).text == r"C:\A & B\pythonw.exe"
    assert raiz.find(".//t:Exec/t:Arguments", ns).text == "<arg>"
    assert raiz.find(".//t:UserId", ns) is None


def test_horarios_da_tarefa_sao_quinze_minutos_depois_das_copias_do_data4u():
    copias = ["05:00", "08:00", "12:00"]
    esperado = [(datetime.strptime(h, "%H:%M") + timedelta(minutes=15)).strftime("%H:%M") for h in copias]  # noqa: DTZ007

    assert list(ea.HORARIOS_DA_TAREFA) == esperado


@pytest.mark.skipif(sys.platform == "win32", reason="só testa a recusa fora do Windows")
def test_instalar_tarefa_fora_do_windows_avisa_e_nao_faz_nada(tmp_path):
    mensagens = []

    assert ea.instalar_tarefa(tmp_path, mensagens.append) == 1
    assert "só existe no Windows" in mensagens[0]


# ------------------------------------------------------------------ o envio do dia, com um servidor de mentira


class ServidorDeMentira:
    """Guarda o que recebeu e responde como o servidor responderia."""

    def __init__(self, respostas=None):
        self.recebidos = []  # (rota, pacote, chave)
        self.respostas = respostas or {}

    def __call__(self, endereco, rota, pacote, chave):
        self.recebidos.append((rota, pacote, chave))
        padrao = (200, {"texto": f"Relatório de {rota}"})
        resposta = self.respostas.get(rota, padrao)
        if isinstance(resposta, list):  # uma resposta por chamada; acabaram, volta ao normal
            resposta = resposta.pop(0) if resposta else padrao
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


@pytest.fixture
def pasta(tmp_path):
    escrever_base(tmp_path)
    ea.gravar_chave(tmp_path, "CHAVE-SECRETA-DE-TESTE")
    return tmp_path


def _log(pasta) -> str:
    return (pasta / ea.ARQUIVO_DO_LOG).read_text(encoding="utf-8")


def _executar(pasta, servidor, **extra):
    return ea.executar(pasta, "http://x", enviar=servidor, dormir=lambda _s: None, **extra)


def test_primeiro_envio_manda_alunos_e_depois_treinos_com_a_chave(pasta):
    servidor = ServidorDeMentira()

    assert _executar(pasta, servidor) == 0

    assert [r[0] for r in servidor.recebidos] == ["/api/alunos/importar", "/api/treinos/importar"]  # nesta ordem
    assert {r[2] for r in servidor.recebidos} == {"CHAVE-SECRETA-DE-TESTE"}
    assert ea.ler_estado(pasta) == {"alunos": AGORA_DA_COPIA, "treinos": AGORA_DA_COPIA}
    log = _log(pasta)
    assert "enviando alunos e treinos" in log and "Relatório de /api/alunos/importar" in log
    assert "CHAVE-SECRETA-DE-TESTE" not in log  # a chave nunca vai para o log


def test_segundo_envio_da_mesma_copia_nao_manda_nada(pasta):
    servidor = ServidorDeMentira()
    _executar(pasta, servidor)
    servidor.recebidos.clear()

    assert _executar(pasta, servidor) == 0

    assert servidor.recebidos == []
    assert "Nada novo" in _log(pasta)


def test_copia_nova_do_dia_seguinte_e_enviada(pasta):
    servidor = ServidorDeMentira()
    _executar(pasta, servidor)
    servidor.recebidos.clear()
    escrever_base(pasta, extracao="15/10/2026 05:00:09")

    assert _executar(pasta, servidor) == 0

    assert len(servidor.recebidos) == 2
    assert ea.ler_estado(pasta)["alunos"] == "15/10/2026 05:00:09"


def test_se_o_historico_de_treinos_falha_os_alunos_ficam_enviados_e_so_o_historico_e_refeito(pasta):
    servidor = ServidorDeMentira({"/api/treinos/importar": [(400, {"erro": "Treino sem aluno."})]})

    assert _executar(pasta, servidor) == 1

    assert ea.ler_estado(pasta) == {"alunos": AGORA_DA_COPIA}
    assert "NÃO ENVIADO: Treino sem aluno. Nada foi alterado." in _log(pasta)

    servidor.recebidos.clear()
    assert _executar(pasta, servidor) == 0  # a próxima rodada

    assert [r[0] for r in servidor.recebidos] == ["/api/treinos/importar"]  # os alunos não vão de novo
    assert ea.ler_estado(pasta) == {"alunos": AGORA_DA_COPIA, "treinos": AGORA_DA_COPIA}


def test_se_os_alunos_falham_o_historico_nem_e_tentado(pasta):
    servidor = ServidorDeMentira({"/api/alunos/importar": (400, {"erro": "Cópia velha demais."})})

    assert _executar(pasta, servidor) == 1

    assert [r[0] for r in servidor.recebidos] == ["/api/alunos/importar"]
    assert ea.ler_estado(pasta) == {}


def test_sem_autorizacao_no_pc_o_envio_nem_comeca(tmp_path):
    escrever_base(tmp_path)
    servidor = ServidorDeMentira()

    assert _executar(tmp_path, servidor) == 1

    assert servidor.recebidos == []
    assert "--autorizar" in _log(tmp_path)


def test_chave_recusada_pelo_servidor_manda_autorizar_de_novo(pasta):
    servidor = ServidorDeMentira({"/api/alunos/importar": (401, {"erro": "Este computador não está autorizado."})})

    assert _executar(pasta, servidor) == 1

    assert "NÃO ENVIADO: O servidor não reconhece este PC" in _log(pasta)
    assert ea.ler_estado(pasta) == {}


def test_sem_internet_tenta_tres_vezes_e_deixa_para_o_proximo_horario(pasta):
    servidor = ServidorDeMentira({"/api/alunos/importar": ea.SemRede("sem internet")})

    assert _executar(pasta, servidor) == 1

    assert len(servidor.recebidos) == ea.TENTATIVAS_SEM_REDE
    assert "próximo horário" in _log(pasta)
    assert ea.ler_estado(pasta) == {}


def test_sem_o_zip_avisa_e_segue_para_o_proximo_horario(tmp_path):
    ea.gravar_chave(tmp_path, "CHAVE")
    servidor = ServidorDeMentira()

    assert _executar(tmp_path, servidor) == 1

    assert servidor.recebidos == []
    assert "Não achei o base_total.zip" in _log(tmp_path)


def test_zip_cortado_nao_envia_nada_e_explica(pasta):
    caminho = pasta / ea.NOME_DO_ZIP
    caminho.write_bytes(caminho.read_bytes()[:-40])
    servidor = ServidorDeMentira()

    assert _executar(pasta, servidor) == 1

    assert servidor.recebidos == []
    assert "NÃO ENVIADO: O base_total.zip está danificado" in _log(pasta)


def test_copia_incompleta_nao_envia_nem_os_alunos(pasta):
    tabelas = dados_do_data4u()
    manifesto = {"extracao": AGORA_DA_COPIA, "tabelas": {t: {"linhas": len(l), "colunas": list(l[0])} for t, l in tabelas.items()}}
    manifesto["tabelas"]["TREINO_PRESCRICAO"]["linhas"] = 999
    escrever_base(pasta, tabelas=tabelas, manifesto=manifesto)
    servidor = ServidorDeMentira()

    assert _executar(pasta, servidor) == 1

    # os alunos até seriam válidos, mas o pacote deles só é montado na vez deles; o de treinos falha na conferência
    assert [r[0] for r in servidor.recebidos] == ["/api/alunos/importar"]
    assert "o manifesto diz 999 linhas" in _log(pasta)


def test_forcar_manda_de_novo_a_mesma_copia(pasta):
    servidor = ServidorDeMentira()
    _executar(pasta, servidor)
    servidor.recebidos.clear()

    assert _executar(pasta, servidor, forcar=True) == 0

    assert len(servidor.recebidos) == 2


def test_espera_a_extracao_antes_de_olhar_o_zip(pasta):
    em_construcao = pasta / ea.NOME_DO_ZIP_EM_CONSTRUCAO
    em_construcao.write_bytes(b"x")
    servidor = ServidorDeMentira()
    esperas = []

    def dormir(segundos):
        esperas.append(segundos)
        em_construcao.unlink()
        escrever_base(pasta, extracao="15/10/2026 05:00:09")  # a extração terminou e trocou o zip

    assert ea.executar(pasta, "http://x", enviar=servidor, dormir=dormir) == 0

    assert esperas == [20]
    assert ea.ler_estado(pasta)["alunos"] == "15/10/2026 05:00:09"  # mandou a cópia NOVA, não a velha


# ------------------------------------------------------------------ a linha de comando


def test_conferir_mostra_o_resumo_e_nao_envia_nem_grava_nada(tmp_path, capsys):
    escrever_base(tmp_path)

    assert ea.main(["--conferir", "--pasta", str(tmp_path)]) == 0

    saida = capsys.readouterr().out
    assert "Cópia do Data4U de 14/10/2026 05:00:17" in saida
    assert "4 pessoas" in saida and "1 celulares, 1 e-mails" in saida and "endereço incluído" in saida
    assert "3 treinos" in saida and "Nada foi enviado" in saida
    assert sorted(p.name for p in tmp_path.iterdir()) == [ea.NOME_DO_ZIP]  # nem log, nem estado


def test_conferir_com_copia_estragada_diz_que_nao_serve(tmp_path, capsys):
    caminho = escrever_base(tmp_path)
    caminho.write_bytes(b"lixo")

    assert ea.main(["--conferir", "--pasta", str(tmp_path)]) == 1
    assert "A cópia não serve" in capsys.readouterr().out


def test_endereco_sem_https_e_recusado_antes_de_qualquer_coisa(tmp_path, capsys):
    assert ea.main(["--endereco", "http://app.gloriafit.com.br", "--pasta", str(tmp_path)]) == 1
    assert "https" in capsys.readouterr().out


# ------------------------------------------------------------------ ponta a ponta: o servidor de verdade


@pytest.fixture
def servidor_de_verdade(tmp_path):
    caminho = tmp_path / "servidor" / "app.db"
    caminho.parent.mkdir()
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.commit()
    conn.close()
    servidor = make_server("127.0.0.1", 0, criar_app(caminho), threaded=True)
    fio = threading.Thread(target=servidor.serve_forever, daemon=True)
    fio.start()
    yield SimpleNamespace(endereco=f"http://127.0.0.1:{servidor.server_port}", caminho=caminho)
    servidor.shutdown()
    fio.join(timeout=5)


def _codigo_novo(caminho) -> str:
    conn = conectar(caminho)
    try:
        return acesso.gerar_codigo(conn, "PC da recepção (envio automático)").codigo
    finally:
        conn.close()


def _consultar(caminho, sql):
    conn = conectar(caminho)
    try:
        return [tuple(l) for l in conn.execute(sql)]
    finally:
        conn.close()


@pytest.fixture
def pc_da_recepcao(tmp_path):
    pasta = tmp_path / "pc"
    pasta.mkdir()
    escrever_base(pasta, extracao=texto_da_extracao(agora_em_brasilia()))
    return pasta


def test_ponta_a_ponta_autoriza_envia_e_o_app_fica_com_os_alunos_os_treinos_e_o_registro(servidor_de_verdade, pc_da_recepcao):
    chave = ea.autorizar_pc(servidor_de_verdade.endereco, _codigo_novo(servidor_de_verdade.caminho))
    ea.gravar_chave(pc_da_recepcao, chave)

    assert ea.executar(pc_da_recepcao, servidor_de_verdade.endereco) == 0

    banco = servidor_de_verdade.caminho
    assert _consultar(banco, "SELECT nome, cpf, whatsapp, situacao FROM aluno ORDER BY data4u_id") == [
        ("ANA FICTICIA", "11144477735", "27988887766", "A"),
        ("BRUNO FICTICIO", "52998224725", None, "A"),  # o telefone fixo não virou WhatsApp
    ]
    assert _consultar(banco, "SELECT nome, origem FROM treino") == [("TREINO ABC", "data4u")]
    assert [r[0] for r in _consultar(banco, "SELECT tipo FROM importacao ORDER BY tipo")] == ["alunos", "treinos"]
    log = _log(pc_da_recepcao)
    assert "Enviado: os alunos." in log and "Enviado: o histórico de treinos." in log
    assert chave not in log


def test_ponta_a_ponta_reenviar_nao_duplica(servidor_de_verdade, pc_da_recepcao):
    ea.gravar_chave(pc_da_recepcao, ea.autorizar_pc(servidor_de_verdade.endereco, _codigo_novo(servidor_de_verdade.caminho)))
    ea.executar(pc_da_recepcao, servidor_de_verdade.endereco)

    assert ea.executar(pc_da_recepcao, servidor_de_verdade.endereco, forcar=True) == 0

    assert _consultar(servidor_de_verdade.caminho, "SELECT COUNT(*) FROM aluno") == [(2,)]
    assert _consultar(servidor_de_verdade.caminho, "SELECT COUNT(*) FROM treino") == [(1,)]


def test_ponta_a_ponta_pc_revogado_recebe_401_e_nao_grava(servidor_de_verdade, pc_da_recepcao):
    ea.gravar_chave(pc_da_recepcao, ea.autorizar_pc(servidor_de_verdade.endereco, _codigo_novo(servidor_de_verdade.caminho)))
    conn = conectar(servidor_de_verdade.caminho)
    assert acesso.revogar(conn, 1)
    conn.close()

    assert ea.executar(pc_da_recepcao, servidor_de_verdade.endereco) == 1

    assert "O servidor não reconhece este PC" in _log(pc_da_recepcao)
    assert _consultar(servidor_de_verdade.caminho, "SELECT COUNT(*) FROM aluno") == [(0,)]


def test_ponta_a_ponta_chave_inventada_e_recusada(servidor_de_verdade, pc_da_recepcao):
    ea.gravar_chave(pc_da_recepcao, "chave-que-nao-existe")

    assert ea.executar(pc_da_recepcao, servidor_de_verdade.endereco) == 1

    assert _consultar(servidor_de_verdade.caminho, "SELECT COUNT(*) FROM aluno") == [(0,)]


def test_ponta_a_ponta_copia_velha_demais_e_recusada_pelo_servidor_com_o_motivo(servidor_de_verdade, tmp_path):
    pasta = tmp_path / "pc_velho"
    pasta.mkdir()
    escrever_base(pasta, extracao=texto_da_extracao(agora_em_brasilia() - timedelta(days=9)))
    ea.gravar_chave(pasta, ea.autorizar_pc(servidor_de_verdade.endereco, _codigo_novo(servidor_de_verdade.caminho)))

    assert ea.executar(pasta, servidor_de_verdade.endereco) == 1

    assert "NÃO ENVIADO:" in _log(pasta) and "Nada foi alterado." in _log(pasta)
    assert _consultar(servidor_de_verdade.caminho, "SELECT COUNT(*) FROM aluno") == [(0,)]
    assert ea.ler_estado(pasta) == {}


def test_ponta_a_ponta_codigo_errado_nao_autoriza(servidor_de_verdade):
    with pytest.raises(ea.NaoAutorizado, match="Código inválido ou vencido"):
        ea.autorizar_pc(servidor_de_verdade.endereco, "AAAAA-22222")


def test_ponta_a_ponta_servidor_fora_do_ar_vira_sem_rede(tmp_path):
    with pytest.raises(ea.SemRede):
        ea.enviar_http("http://127.0.0.1:9", "/api/alunos/importar", {"extracao": "x", "tabelas": {}}, "chave")


def test_autorizar_pela_linha_de_comando_grava_a_chave(servidor_de_verdade, tmp_path, monkeypatch, capsys):
    pasta = tmp_path / "pc_novo"
    pasta.mkdir()
    codigo = _codigo_novo(servidor_de_verdade.caminho)
    monkeypatch.setattr(builtins, "input", lambda _pergunta: codigo)

    assert ea.main(["--autorizar", "--endereco", servidor_de_verdade.endereco, "--pasta", str(pasta)]) == 0

    chave = ea.ler_chave(pasta)
    assert chave and chave not in capsys.readouterr().out  # a chave não aparece na tela
    assert "foi autorizado" in _log(pasta)


def test_autorizar_com_codigo_errado_nao_grava_chave(servidor_de_verdade, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(builtins, "input", lambda _pergunta: "AAAAA-22222")

    assert ea.main(["--autorizar", "--endereco", servidor_de_verdade.endereco, "--pasta", str(tmp_path)]) == 1

    assert ea.ler_chave(tmp_path) is None
    assert "Não autorizou" in capsys.readouterr().out


def test_o_programa_pode_ser_baixado_do_app_pelo_pc_sem_autorizacao(servidor_de_verdade):
    """O PC ainda não tem chave quando baixa o programa: a pasta /static é pública (e o programa não tem segredo nenhum)."""
    import urllib.request

    with urllib.request.urlopen(servidor_de_verdade.endereco + "/static/recepcao/enviar_alunos.py", timeout=10) as resposta:
        baixado = resposta.read()

    assert resposta.status == 200
    assert baixado == CAMINHO_DO_PROGRAMA.read_bytes()


# ------------------------------------------------------------------ fotos dos alunos (29/10/2026)


def _foto(cor=(200, 120, 80)) -> bytes:
    import io

    from PIL import Image

    saida = io.BytesIO()
    Image.new("RGB", (120, 160), cor).save(saida, "JPEG")
    return saida.getvalue()


@pytest.mark.parametrize(
    "chave, esperado",
    [("foto/4257_im_foto", 4257), ("foto/1_im_foto", 1), ("foto/_im_foto", None), ("foto/12a_im_foto", None),
     ("lancamento_avaliacao/3_im_foto", None), ("pessoa/472_ds_observacoes", None), ("foto/4257_ds_face", None), (None, None)],
)
def test_id_da_chave_da_foto(chave, esperado):
    assert ea.id_da_chave_da_foto(chave) == esperado


def test_planejar_fotos_manda_so_aluno_em_uso_com_foto_nova_ou_trocada():
    import hashlib

    igual, trocada, nova, de_fora = _foto((1, 1, 1)), _foto((2, 2, 2)), _foto((3, 3, 3)), _foto((4, 4, 4))
    estado = {"alunos": [{"id": 1, "sha256": hashlib.sha256(igual).hexdigest()}, {"id": 2, "sha256": "0" * 64}, {"id": 3, "sha256": None},
                         {"id": 5, "sha256": None}]}

    mandar, presentes = ea.planejar_fotos(estado, {1: igual, 2: trocada, 3: nova, 9: de_fora})

    assert [i for i, _ in mandar] == [2, 3]
    assert presentes == [1, 2, 3]  # o 9 não está em uso; o 5 está em uso mas não tem foto no Data4U


def test_planejar_fotos_sem_lista_do_servidor_e_erro():
    with pytest.raises(ea.SemRede):
        ea.planejar_fotos({"erro": "x"}, {1: b"x"})


def test_pacotes_de_fotos_respeitam_o_limite_e_todos_levam_os_presentes(monkeypatch):
    monkeypatch.setattr(ea, "BYTES_DE_FOTO_POR_PACOTE", 25)
    mandar = [(i, b"x" * 10) for i in range(1, 8)]

    pacotes = ea.pacotes_de_fotos(mandar, [1, 2, 3, 4, 5, 6, 7], por_pacote=5)

    assert [[f["id"] for f in p["fotos"]] for p in pacotes] == [[1, 2], [3, 4], [5, 6], [7]]  # 2 x 10 bytes cabem em 25
    assert all(p["presentes"] == [1, 2, 3, 4, 5, 6, 7] for p in pacotes)
    assert ea.pacotes_de_fotos([], [1, 2], por_pacote=5) == [{"fotos": [], "presentes": [1, 2]}]


def test_sem_cache_ou_sem_leitor_as_fotos_ficam_para_depois(tmp_path):
    assert ea.ler_fotos_do_cache(tmp_path, origem=tmp_path / "nao_existe.D4U", cliente=tmp_path / "fbclient.dll") is None


class ServidorDeFotos(ServidorDeMentira):
    def __init__(self, alunos, respostas=None):
        super().__init__(respostas)
        self.alunos = alunos

    def __call__(self, endereco, rota, pacote, chave):
        if rota == ea.ROTA_DO_ESTADO_DAS_FOTOS and rota not in self.respostas:
            self.recebidos.append((rota, pacote, chave))
            return 200, {"alunos": self.alunos, "fotos_por_pacote": 2}
        if rota == ea.ROTA_DAS_FOTOS and rota not in self.respostas:
            self.recebidos.append((rota, pacote, chave))
            return 200, {"gravadas": len(pacote["fotos"]), "recusadas": 0, "sem_aluno": 0, "vistas": len(pacote["presentes"]), "apagadas": 0}
        return super().__call__(endereco, rota, pacote, chave)


def test_fotos_vao_depois_dos_alunos_e_so_uma_vez_por_dia(pasta):
    servidor = ServidorDeFotos([{"id": 10, "sha256": None}, {"id": 11, "sha256": None}, {"id": 12, "sha256": None}])
    cache = {10: _foto(), 11: _foto((9, 9, 9)), 12: _foto((5, 5, 5)), 99: _foto()}

    assert _executar(pasta, servidor, ler_fotos=lambda _p: cache) == 0

    rotas = [r[0] for r in servidor.recebidos]
    assert rotas == ["/api/alunos/importar", "/api/treinos/importar", ea.ROTA_DO_ESTADO_DAS_FOTOS, ea.ROTA_DAS_FOTOS, ea.ROTA_DAS_FOTOS]
    enviados = [f["id"] for r in servidor.recebidos if r[0] == ea.ROTA_DAS_FOTOS for f in r[1]["fotos"]]
    assert enviados == [10, 11, 12]  # o 99 não está em uso: não sai do PC
    assert "Fotos: 3 alunos em uso têm foto no Data4U; 3 novas ou trocadas enviadas." in _log(pasta)
    assert "fotos" in ea.ler_estado(pasta)

    servidor.recebidos.clear()
    assert _executar(pasta, servidor, ler_fotos=lambda _p: cache) == 0
    assert servidor.recebidos == []  # mesmo dia, mesma cópia: nada


def test_fotos_que_falham_contam_como_falha_e_ficam_para_o_proximo_horario(pasta):
    servidor = ServidorDeFotos([{"id": 10, "sha256": None}], {ea.ROTA_DAS_FOTOS: (400, {"erro": "pacote ruim"})})

    assert _executar(pasta, servidor, ler_fotos=lambda _p: {10: _foto()}) == 1

    assert "fotos" not in ea.ler_estado(pasta) and ea.ler_estado(pasta)["alunos"] == AGORA_DA_COPIA
    assert "Fotos: o servidor recusou um pacote (resposta 400: pacote ruim)" in _log(pasta)


def test_fotos_que_nao_dao_para_ler_nao_derrubam_o_envio(pasta):
    servidor = ServidorDeFotos([])

    assert _executar(pasta, servidor, ler_fotos=lambda _p: None) == 0

    assert ea.ROTA_DO_ESTADO_DAS_FOTOS not in [r[0] for r in servidor.recebidos]
    assert "fotos" not in ea.ler_estado(pasta)


def test_os_pacotes_de_fotos_passam_no_servidor_de_verdade():
    from app import fotos

    conn = conectar()
    criar_tabelas(conn)
    conn.execute("INSERT INTO aluno (id, nome, situacao, data4u_id) VALUES (1, 'ANA SOUZA', 'A', 501), (2, 'BRUNO LIMA', 'P', 502)")
    conn.commit()
    cache = {501: _foto(), 502: _foto((1, 2, 3)), 777: _foto()}

    mandar, presentes = ea.planejar_fotos(fotos.estado(conn), cache)
    for pacote in ea.pacotes_de_fotos(mandar, presentes, fotos.FOTOS_POR_PACOTE):
        assert fotos.importar(conn, json.loads(json.dumps(pacote)))["gravadas"] == 2

    assert fotos.alunos_com_foto(conn) == {1, 2}
    assert ea.planejar_fotos(fotos.estado(conn), cache)[0] == []  # na rodada seguinte não há o que mandar
    conn.close()


def test_conferir_mostra_quantas_fotos_ha_no_cache(tmp_path):
    escrever_base(tmp_path)
    mensagens = []

    assert ea.conferir(tmp_path, mensagens.append, ler_fotos=lambda _p: {1: b"x" * 1024, 2: b"y" * 1024}) == 0

    assert any(m.startswith("Fotos: 2 pessoas com foto no CACHE.D4U") for m in mensagens)


def test_acessos_pela_catraca_so_os_recentes_e_so_a_data(tmp_path):
    agora = agora_em_brasilia()
    dados = dados_do_data4u()
    dados["ACC_PESSOA"] = [
        {"ID_PESSOA": 101, "DT_LAST_ACCESS": f"{agora - timedelta(days=3):%Y-%m-%d %H:%M:%S}", "ID_ACC_LOCAL": -1, "NR_ACCESS_DAY": 1},
        {"ID_PESSOA": 102, "DT_LAST_ACCESS": f"{agora - timedelta(days=90):%Y-%m-%d %H:%M:%S}", "ID_ACC_LOCAL": -1, "NR_ACCESS_DAY": 0},
        {"ID_PESSOA": 900, "DT_LAST_ACCESS": None, "ID_ACC_LOCAL": -1, "NR_ACCESS_DAY": 0},
    ]
    caminho = escrever_base(tmp_path, extracao=texto_da_extracao(agora), tabelas=dados)

    alunos, resumo = ea.montar_pacote(ea.ler_arquivos_do_zip(caminho, ea.TABELAS_DOS_ALUNOS, ea.TABELAS_OPCIONAIS_DOS_ALUNOS))

    assert alunos["tabelas"]["ACC_PESSOA"] == {"colunas": ["ID_PESSOA", "DT_LAST_ACCESS"],
                                               "linhas": [[101, f"{agora - timedelta(days=3):%Y-%m-%d %H:%M:%S}"]]}
    assert resumo["linhas"]["ACC_PESSOA"] == 1
    copia = importar_alunos.copia_de_pacote(alunos)
    assert copia.acessos == {101: f"{agora - timedelta(days=3):%Y-%m-%d}"}
    assert ea.DIAS_DE_ACESSO == importar_alunos.DIAS_DE_ACESSO_RECENTE


def test_copia_sem_a_tabela_de_acessos_vai_sem_ela(tmp_path):
    caminho = escrever_base(tmp_path, extracao=texto_da_extracao(agora_em_brasilia()))
    alunos, _ = ea.montar_pacote(ea.ler_arquivos_do_zip(caminho, ea.TABELAS_DOS_ALUNOS, ea.TABELAS_OPCIONAIS_DOS_ALUNOS))
    assert "ACC_PESSOA" not in alunos["tabelas"] and importar_alunos.copia_de_pacote(alunos).acessos is None
