"""O navegador (JavaScript) e o servidor (Python) combinam o formato do pacote de importação.

Cada lado tem os seus testes, mas o defeito perigoso mora na junção: o JavaScript manda uma
coluna a mais, ou um número onde o servidor quer texto, e só se descobriria com o arquivo de
verdade na mão do Thiago. Estes testes rodam o JavaScript de verdade (Node) e entregam o que
ele produz ao servidor. Sem Node instalado, são pulados (o GitHub tem Node nas máquinas dos testes).
"""

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app import importar_alunos, importar_treinos, treinos
from app.db import conectar, criar_tabelas

RAIZ = Path(__file__).resolve().parent.parent
MODULO = (RAIZ / "app" / "static" / "copia_modelo.js").as_uri()
AGORA = datetime(2026, 10, 8, 11, 30, 15, tzinfo=timezone.utc)

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node não está instalado")


def _node(codigo: str):
    """Roda um trecho de JavaScript (módulo) e devolve o que ele escreveu no stdout, lido como JSON."""
    resultado = subprocess.run(
        ["node", "--input-type=module", "-e", codigo],
        capture_output=True, text=True, timeout=60, check=False, cwd=RAIZ,
    )
    assert resultado.returncode == 0, resultado.stderr
    return json.loads(resultado.stdout)


def test_as_colunas_combinam_nos_dois_lados():
    js = _node(f"""
        import * as m from "{MODULO}";
        console.log(JSON.stringify({{ alunos: m.COLUNAS_ENVIADAS, treinos: m.COLUNAS_DOS_TREINOS }}));
    """)

    assert {t: tuple(c) for t, c in js["alunos"].items()} == importar_alunos.COLUNAS_NECESSARIAS
    assert {t: tuple(c) for t, c in js["treinos"].items()} == importar_treinos.COLUNAS_NECESSARIAS


# Um pedaço de cópia do Data4U como ela é de verdade: colunas a mais, número onde o app quer texto,
# lançamentos que não são de treino, professores e pessoas que não montaram treino.
_CODIGO_DO_PACOTE_DE_TREINOS = f"""
import * as m from "{MODULO}";
const enc = new TextEncoder();
const jsonl = (linhas) => enc.encode(linhas.map((l) => JSON.stringify(l)).join("\\n") + "\\n");
const tabelas = {{
  PESSOA: [
    {{ ID: 101, NM_PESSOA: "ANA FICTICIA", TP_PESSOA: "F", NR_CPF: 11144477735, NR_RG: "9", ST_DELETED: "F" }},
    {{ ID: 900, NM_PESSOA: "PROF ANA", TP_PESSOA: "F", NR_CPF: null, NR_RG: null, ST_DELETED: "F" }},
    {{ ID: 901, NM_PESSOA: "PROF QUE NAO MONTOU", TP_PESSOA: "F", NR_CPF: null, NR_RG: null, ST_DELETED: "F" }},
  ],
  TREINO: [
    {{ ID_TREINO: 1, ID_LANCAMENTO: 5001, ID_PROFESSOR: 900, NM_TREINO: "TREINO ABC", DT_INICIO: "2026-03-02", DS_OBS: "x", ST_DELETED: "F" }},
    {{ ID_TREINO: 2, ID_LANCAMENTO: null, ID_PROFESSOR: null, NM_TREINO: "MODELO", DT_INICIO: null, DS_OBS: null, ST_DELETED: "F" }},
    {{ ID_TREINO: 3, ID_LANCAMENTO: 5002, ID_PROFESSOR: 900, NM_TREINO: "APAGADO", DT_INICIO: "2026-03-05", DS_OBS: null, ST_DELETED: "T" }},
  ],
  TREINO_FICHA: [
    {{ ID_TREINO_FICHA: 11, ID_TREINO: 1, NR_FICHA: 1, NM_TREINO_FICHA: "A", DT_ULTIMA_SESSAO: null }},
    {{ ID_TREINO_FICHA: 12, ID_TREINO: 1, NR_FICHA: 2, NM_TREINO_FICHA: "B", DT_ULTIMA_SESSAO: null }},
    {{ ID_TREINO_FICHA: 21, ID_TREINO: 2, NR_FICHA: 1, NM_TREINO_FICHA: "A", DT_ULTIMA_SESSAO: null }},
  ],
  TREINO_PRESCRICAO: [
    {{ ID_TREINO_PRESCRICAO: 101, ID_TREINO_FICHA: 11, ID_TREINO_EXERCICIO: -5, NR_ORDEM: 1, NR_SERIE: "3", DS_REPETICAO: "12", DS_PESO: 20, TM_PAUSA: "00:01:00", DS_PRESCRICAO_OBS: "devagar" }},
    {{ ID_TREINO_PRESCRICAO: 102, ID_TREINO_FICHA: 11, ID_TREINO_EXERCICIO: 7, NR_ORDEM: 2, NR_SERIE: null, DS_REPETICAO: "10", DS_PESO: null, TM_PAUSA: null, DS_PRESCRICAO_OBS: null }},
    {{ ID_TREINO_PRESCRICAO: 103, ID_TREINO_FICHA: 12, ID_TREINO_EXERCICIO: 555, NR_ORDEM: 1, NR_SERIE: "4", DS_REPETICAO: "8", DS_PESO: "12,5", TM_PAUSA: "00:00:30", DS_PRESCRICAO_OBS: null }},
    {{ ID_TREINO_PRESCRICAO: 201, ID_TREINO_FICHA: 21, ID_TREINO_EXERCICIO: 7, NR_ORDEM: 1, NR_SERIE: "3", DS_REPETICAO: "12", DS_PESO: null, TM_PAUSA: null, DS_PRESCRICAO_OBS: null }},
    {{ ID_TREINO_PRESCRICAO: 104, ID_TREINO_FICHA: 12, ID_TREINO_EXERCICIO: null, NR_ORDEM: 2, NR_SERIE: "3", DS_REPETICAO: "15", DS_PESO: "MODERADO", TM_PAUSA: "00:00:00", DS_PRESCRICAO_OBS: null }},
    {{ ID_TREINO_PRESCRICAO: 105, ID_TREINO_FICHA: 12, ID_TREINO_EXERCICIO: null, NR_ORDEM: 3, NR_SERIE: null, DS_REPETICAO: null, DS_PESO: null, TM_PAUSA: "00:00:00", DS_PRESCRICAO_OBS: null }},
  ],
  TREINO_EXERCICIO: [
    {{ ID_TREINO_EXERCICIO: -5, NM_EXERCICIO: "<b>SUPINO RETO</b> APAGADO", DS_ANIMACAO: "a.gif", ST_DELETED: "T" }},
    {{ ID_TREINO_EXERCICIO: 7, NM_EXERCICIO: "REMADA BAIXA", DS_ANIMACAO: null, ST_DELETED: "F" }},
    {{ ID_TREINO_EXERCICIO: 8, NM_EXERCICIO: "NUNCA USADO", DS_ANIMACAO: null, ST_DELETED: "F" }},
  ],
  LANCAMENTO_OBJ: [
    {{ ID_LANCAMENTO: 5001, ID_OBJ: 101, TP_LANCAMENTO: -510, DT_LANCAMENTO: "2026-03-02 14:03:24", ID_PESSOA: 900, VL_LANCAMENTO: 0 }},
    {{ ID_LANCAMENTO: 5002, ID_OBJ: 101, TP_LANCAMENTO: -510, DT_LANCAMENTO: "2026-03-05 09:00:00", ID_PESSOA: 900, VL_LANCAMENTO: 0 }},
    {{ ID_LANCAMENTO: 7777, ID_OBJ: 101, TP_LANCAMENTO: 1, DT_LANCAMENTO: "2026-03-05 09:00:00", ID_PESSOA: 1, VL_LANCAMENTO: 150 }},
  ],
}};
const colunasReais = (linhas) => Object.keys(linhas[0]);
const manifesto = {{ extracao: "08/10/2026 05:00:19", tabelas: {{}} }};
const arquivos = {{}};
for (const [nome, linhas] of Object.entries(tabelas)) {{
  manifesto.tabelas[nome] = {{ linhas: linhas.length, colunas: colunasReais(linhas) }};
  arquivos[nome + ".jsonl"] = jsonl(linhas);
}}
// o manifesto de verdade também descreve as tabelas dos alunos
for (const nome of ["PESSOA_STATUS", "CONTATO_PESSOA"]) {{
  const linhas = nome === "PESSOA_STATUS"
    ? [{{ ID_PESSOA: 101, DT_INI_STATUS: "2026-01-01", DT_FIM_STATUS: "7777-07-07", CD_STATUS: "A" }}]
    : [{{ ID_CONTATO: 1, ID_PESSOA: 101, ID_TIPO_CONTATO: 30, DS_CONTATO: 27988887766 }}];
  manifesto.tabelas[nome] = {{ linhas: linhas.length, colunas: colunasReais(linhas) }};
  arquivos[nome + ".jsonl"] = jsonl(linhas);
}}
arquivos["_manifesto.json"] = enc.encode(JSON.stringify(manifesto));
console.log(JSON.stringify({{ alunos: m.montarPacote(arquivos).pacote, treinos: m.montarPacoteDeTreinos(arquivos).pacote }}));
"""


@pytest.fixture(scope="module")
def pacotes():
    return _node(_CODIGO_DO_PACOTE_DE_TREINOS)


def test_o_pacote_dos_alunos_feito_pelo_navegador_passa_no_servidor(pacotes):
    copia = importar_alunos.copia_de_pacote(pacotes["alunos"], agora=AGORA)

    assert [p["ID"] for p in copia.pessoas] == [101, 900, 901]
    assert copia.pessoas[0]["NR_CPF"] == "11144477735"  # veio número do Data4U, chegou texto
    assert copia.contatos[101][0]["DS_CONTATO"] == "27988887766"


def test_o_pacote_dos_treinos_feito_pelo_navegador_passa_no_servidor(pacotes):
    copia = importar_treinos.copia_de_pacote(pacotes["treinos"], agora=AGORA)

    assert len(copia.linhas["TREINO"]) == 3
    assert [linha[0] for linha in copia.linhas["PESSOA"]] == [900]  # só o professor que montou treino
    assert len(copia.linhas["LANCAMENTO_OBJ"]) == 2  # o lançamento 7777 (não é de treino) nem foi enviado
    assert len(copia.linhas["TREINO_EXERCICIO"]) == 2  # o exercício que ninguém usa nem foi enviado


def test_pacote_do_navegador_vira_historico_no_banco(pacotes):
    conn = conectar()
    criar_tabelas(conn)
    conn.execute("INSERT INTO aluno (id, nome, data4u_id, situacao) VALUES (1, 'ANA FICTICIA', 101, 'A')")
    conn.commit()
    copia = importar_treinos.copia_de_pacote(pacotes["treinos"], agora=AGORA)

    relatorio = importar_treinos.importar(conn, copia)

    assert (relatorio.treinos_novos, relatorio.fora_apagados, relatorio.fora_sem_aluno) == (1, 1, 1)
    assert [tuple(l) for l in conn.execute("SELECT nome, montado_por, criado_em FROM treino")] == [
        ("TREINO ABC", "PROF ANA", "2026-03-02 17:03:24")
    ]
    itens = [
        tuple(l)
        for l in conn.execute(
            "SELECT e.nome, i.series, i.repeticoes, i.carga, i.pausa, i.observacao FROM ficha_item i"
            " JOIN exercicio e ON e.id = i.exercicio_id ORDER BY i.ficha_id, i.ordem"
        )
    ]
    assert itens == [
        ("SUPINO RETO APAGADO", "3", "12", "20", 60, "devagar"),  # peso veio número, tags HTML saíram
        ("REMADA BAIXA", None, "10", None, None, None),
        (importar_treinos.NOME_DO_EXERCICIO_REMOVIDO, "4", "8", "12,5", 30, None),  # exercício 555 não existe no Data4U
        (importar_treinos.NOME_DO_EXERCICIO_NAO_INFORMADO, "3", "15", "MODERADO", 0, None),  # sem exercício, com dose: entra
    ]  # (e a linha 105, sem exercício e em branco, ficou de fora)
    assert relatorio.itens_vazios_ignorados == 1
    conn.close()


# ---------------------------------------------------------------- tela de montar -> servidor

MODELO_DO_TREINO = (RAIZ / "app" / "static" / "treino_modelo.js").as_uri()


def test_pedido_montado_pelo_navegador_com_intervalo_e_observacao_e_gravado_pelo_servidor():
    """O que a tela de montar manda (intervalo em minutos e segundos -> segundos, observação) é o que o servidor grava."""
    pedido = _node(f"""
        import * as M from "{MODELO_DO_TREINO}";
        let e = M.criarEstado();
        e = M.adicionarItem(e, 0, {{ id: 1, nome: "SUPINO" }});
        e = M.adicionarItem(e, 0, {{ id: 2, nome: "REMADA" }});
        for (const uid of [1, 2]) {{
          e = M.atualizarItem(e, 0, uid, "series", "3");
          e = M.atualizarItem(e, 0, uid, "repeticoes", "12");
        }}
        e = M.atualizarItem(e, 0, 1, "pausaMin", "1");
        e = M.atualizarItem(e, 0, 1, "pausaSeg", "30");
        e = M.atualizarItem(e, 0, 1, "observacao", "  descer   devagar ");
        if (M.validar(e).length) throw new Error("a tela recusaria este treino");
        console.log(JSON.stringify(M.montarPedido(e, {{ nomeTreino: "TREINO A", montadoPor: "Ana Paula" }})));
    """)
    conn = conectar()
    criar_tabelas(conn)
    conn.execute("INSERT INTO aluno (id, nome) VALUES (1, 'ALUNO')")
    conn.executemany("INSERT INTO exercicio (id, nome, origem, ativo) VALUES (?, ?, 'app', 1)", [(1, "SUPINO"), (2, "REMADA")])

    treino_id = treinos.salvar_treino(conn, 1, pedido)

    itens = treinos.obter_treino(conn, treino_id)["fichas"][0]["itens"]
    assert [(i["pausa"], i["observacao"]) for i in itens] == [(90, "descer devagar"), (None, None)]
    conn.close()


def test_pedido_com_inicio_fim_e_meta_montado_pelo_navegador_e_gravado_pelo_servidor():
    """Início, fim e "treinos por ficha" que a tela manda são exatamente o que o servidor aceita e grava."""
    pedido = _node(f"""
        import * as M from "{MODELO_DO_TREINO}";
        let e = M.criarEstado();
        e = M.adicionarItem(e, 0, {{ id: 1, nome: "SUPINO" }});
        e = M.atualizarItem(e, 0, 1, "series", "3");
        e = M.atualizarItem(e, 0, 1, "repeticoes", "12");
        const dados = {{ nomeTreino: "TREINO A", montadoPor: "Ana Paula", inicio: "2026-10-10", fim: "2026-12-31", sessoesPorFicha: " 15 " }};
        if (M.validarDadosDoTreino(dados).length) throw new Error("a tela recusaria estes dados");
        const vazio = {{ nomeTreino: "TREINO B", montadoPor: "Ana Paula", inicio: "2026-10-10", fim: "", sessoesPorFicha: "" }};
        console.log(JSON.stringify([M.montarPedido(e, dados), M.montarPedido(e, vazio)]));
    """)
    conn = conectar()
    criar_tabelas(conn)
    conn.execute("INSERT INTO aluno (id, nome) VALUES (1, 'ALUNO')")
    conn.execute("INSERT INTO exercicio (id, nome, origem, ativo) VALUES (1, 'SUPINO', 'app', 1)")

    primeiro = treinos.salvar_treino(conn, 1, pedido[0])
    segundo = treinos.salvar_treino(conn, 1, pedido[1])  # fim e meta vazios: o servidor aceita os null

    linhas = conn.execute("SELECT id, inicio, fim, sessoes_por_ficha, ativo FROM treino ORDER BY id").fetchall()
    assert [tuple(l) for l in linhas] == [
        (primeiro, "2026-10-10", "2026-12-31", 15, 0),  # o segundo treino concluiu o primeiro
        (segundo, "2026-10-10", None, None, 1),
    ]
    conn.close()
