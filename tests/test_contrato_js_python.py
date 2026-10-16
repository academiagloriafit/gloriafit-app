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

from app import (
    acesso,
    administrador,
    filas,
    importar_alunos,
    importar_treinos,
    modelos,
    treinos,
)
from app.db import conectar, criar_tabelas
from app.web import criar_app

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


FILAS_DO_TREINO = (RAIZ / "app" / "static" / "filas_modelo.js").as_uri()


def test_pedidos_das_filas_montados_pelo_navegador_sao_aceitos_pelo_servidor():
    """Treino padrão com fila e número, aluno na fila (com liberação) e treino salvo pela fila: o que o JavaScript manda o servidor aceita."""
    pedidos = _node(f"""
        import * as M from "{MODELO_DO_TREINO}";
        import * as F from "{FILAS_DO_TREINO}";
        let e = M.criarEstado();
        e = M.adicionarItem(e, 0, {{ id: 1, nome: "SUPINO" }});
        e = M.atualizarItem(e, 0, 1, "series", "3");
        e = M.atualizarItem(e, 0, 1, "repeticoes", "12");
        const posicao = M.lerPosicaoNaFila({{ filaId: "4", numero: "2" }});
        if (!posicao.ok) throw new Error("a tela recusaria a posição");
        const dadosPadrao = {{ nomePadrao: " Gestante   2 ", montadoPor: "Ana Paula", sessoesPorFicha: "", filaId: "4", numero: "2" }};
        const dadosFila = {{ filaId: "4", professor: " Bia  Souza ", exigeLiberacao: true, conferida: true, liberacaoEm: "2026-10-01", hoje: "2026-10-13" }};
        if (F.validarColocarNaFila(dadosFila).length) throw new Error("a ficha recusaria estes dados");
        console.log(JSON.stringify({{
          padrao: M.montarPedidoDePadrao(e, dadosPadrao),
          fila: F.montarPedidoDaFila(dadosFila),
          salvar: M.montarPedido(e, {{ nomeTreino: "GESTANTE TREINO 2 13/10/26", montadoPor: "Bia", inicio: "2026-10-13", filaModeloId: 1 }}),
        }}));
    """)
    conn = conectar()
    criar_tabelas(conn)
    conn.execute("INSERT INTO aluno (id, nome) VALUES (1, 'ALUNA')")
    conn.execute("INSERT INTO exercicio (id, nome, origem, ativo) VALUES (1, 'SUPINO', 'app', 1)")

    modelo_id = modelos.criar_modelo(conn, pedidos["padrao"])
    filas.definir_fila(conn, 1, pedidos["fila"])
    treino_id = treinos.salvar_treino(conn, 1, {**pedidos["salvar"], "fila_modelo_id": modelo_id})  # (o id do padrão só se sabe aqui)

    assert pedidos["padrao"]["fila_id"] == 4 and pedidos["padrao"]["numero"] == 2
    assert pedidos["padrao"]["nome"] == "Gestante 2"
    assert conn.execute("SELECT fila_id, numero FROM modelo_treino WHERE id = ?", (modelo_id,)).fetchone()[:] == (4, 2)
    assert conn.execute("SELECT fila_id, numero_atual, definida_por, liberacao_em, liberacao_por FROM aluno_fila").fetchone()[:] == (
        4, 2, "Bia Souza", "2026-10-01", "Bia Souza",
    )
    assert treinos.obter_treino(conn, treino_id)["nome"] == "GESTANTE TREINO 2 13/10/26"
    assert "fila_modelo_id" in pedidos["salvar"]
    conn.close()


def test_pedido_de_treino_padrao_com_senha_montado_pelo_navegador_passa_pelo_servidor(tmp_path):
    """O JavaScript manda `senha_admin` onde o servidor a procura: com a senha certa o padrão é guardado, sem ela não."""
    pedidos = _node(f"""
        import * as M from "{MODELO_DO_TREINO}";
        let e = M.criarEstado();
        e = M.adicionarItem(e, 0, {{ id: 1, nome: "SUPINO" }});
        e = M.atualizarItem(e, 0, 1, "series", "3");
        e = M.atualizarItem(e, 0, 1, "repeticoes", "12");
        const dados = {{ nomePadrao: "Homem 6", montadoPor: "Academia Glória Fit", filaId: "1", numero: "6" }};
        if (M.problemaDaSenhaDeAdmin("Uma senha 123")) throw new Error("a tela recusaria a senha");
        console.log(JSON.stringify({{
          certa: M.montarPedidoDePadrao(e, {{ ...dados, senhaAdmin: "Uma senha 123" }}),
          errada: M.montarPedidoDePadrao(e, {{ ...dados, nomePadrao: "Outro", numero: "5", senhaAdmin: "outra senha 999" }}),
          vazia: M.montarPedidoDePadrao(e, {{ ...dados, nomePadrao: "Terceiro", numero: "4" }}),
        }}));
    """)
    caminho = tmp_path / "contrato.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.execute("INSERT INTO exercicio (id, nome, origem, ativo) VALUES (1, 'SUPINO', 'app', 1)")
    conn.commit()
    administrador.definir_senha(conn, "Uma senha 123")
    token = acesso.autorizar(conn, acesso.gerar_codigo(conn, "Computador de teste").codigo).token
    conn.close()
    cliente = criar_app(caminho).test_client()
    cliente.set_cookie(acesso.NOME_DO_COOKIE, token)

    assert cliente.post("/api/modelos", json=pedidos["certa"]).status_code == 201
    errada = cliente.post("/api/modelos", json=pedidos["errada"])
    vazia = cliente.post("/api/modelos", json=pedidos["vazia"])

    assert (errada.status_code, errada.get_json()["senha"]) == (403, "incorreta")
    assert (vazia.status_code, vazia.get_json()["senha"]) == (403, "incorreta")
    conn = conectar(caminho)
    assert [tuple(l) for l in conn.execute("SELECT nome, fila_id, numero FROM modelo_treino")] == [("Homem 6", 1, 6)]
    conn.close()


# ------------------------------------------------------------------ treino sob medida (IA)

MODULO_IA = (RAIZ / "app" / "static" / "treino_ia_modelo.js").as_uri()


def test_ia_o_limite_das_observacoes_e_o_mesmo_nos_dois_lados():
    from app import ia_treino

    js = _node(f"""
        import * as m from "{MODULO_IA}";
        console.log(JSON.stringify({{ limite: m.LIMITE_DAS_OBSERVACOES }}));
    """)

    assert js["limite"] == ia_treino.LIMITE_DAS_OBSERVACOES


def test_ia_os_limites_da_conversa_sao_os_mesmos_nos_dois_lados():
    from app import ia_treino

    js = _node(f"""
        import * as m from "{MODULO_IA}";
        console.log(JSON.stringify({{ respostas: m.LIMITE_DAS_RESPOSTAS, rodadas: m.MAXIMO_DE_RODADAS }}));
    """)

    assert js["respostas"] == ia_treino.LIMITE_DAS_RESPOSTAS
    assert js["rodadas"] == ia_treino.MAXIMO_DE_RODADAS_DE_PERGUNTAS


# Textos para o JavaScript e o Python julgarem. Onde um recusa e o outro não, ou o professor vê um aviso que o
# servidor não daria (confusão), ou passa na tela e é barrado depois de esperar (pior).
_OBSERVACOES = [
    "",
    "dor no joelho direito; prefere máquinas",
    "faz 3 series de 12",
    "treina ha 10 anos, 2 dias",
    "peso 80 kg, 1,75 m",
    "dor 7 de 10",
    "cpf 123.456.789-09",
    "zap 27 98888-7777",
    "123456789",
    "tel (27)98888-7777",
    "doc 12 345 678 9",
    "1234567",
    "12345678",
    "1234 5678",
    "123-4567",
    "ano 2026 e 2027",
    "manda para ana@exemplo.com",
    "a" * 300,
    "a" * 301,
    "💪" * 300,
    "💪" * 301,
    "dor   no\n\njoelho" + " " * 400,
]


def test_ia_o_navegador_e_o_servidor_recusam_as_mesmas_observacoes(tmp_path):
    from app import ia_treino

    js = _node(f"""
        import * as m from "{MODULO_IA}";
        const textos = {json.dumps(_OBSERVACOES)};
        const base = {{ objetivo: "hipertrofia", nivel: "iniciante", dias: "3", minutos: "60" }};
        console.log(JSON.stringify(textos.map((t) => m.validarPedido({{ ...base, observacoes: t }}).length > 0)));
    """)

    caminho = tmp_path / "ia.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.execute("INSERT INTO aluno (id, nome) VALUES (1, 'ZULEICA FICTICIA')")
    conn.commit()
    python = []
    for texto in _OBSERVACOES:
        try:
            ia_treino.conferir_pedido(
                conn, 1, {"objetivo": "hipertrofia", "nivel": "iniciante", "dias": 3, "minutos": 60, "observacoes": texto}
            )
            python.append(False)
        except ia_treino.PedidoInvalido:
            python.append(True)
    conn.close()

    assert js == python, [(t, j, p) for t, j, p in zip(_OBSERVACOES, js, python) if j != p]


def test_ia_o_pedido_que_o_navegador_monta_e_aceito_pelo_servidor_em_todas_as_combinacoes(tmp_path):
    """As opções do cartão (objetivo, nível, dias, minutos) saem do servidor para o HTML; o que o navegador devolve tem de passar."""
    import html
    import re

    from app import ia_treino

    caminho = tmp_path / "ia.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.execute("INSERT INTO aluno (id, nome) VALUES (1, 'ZULEICA FICTICIA')")
    conn.commit()
    token = acesso.autorizar(conn, acesso.gerar_codigo(conn, "Computador de teste").codigo).token
    conn.close()
    app = criar_app(caminho)
    cliente = app.test_client()
    cliente.set_cookie(acesso.NOME_DO_COOKIE, token)

    pagina = html.unescape(cliente.get("/alunos/1/montar").get_data(as_text=True))

    def opcoes(id_do_campo):
        trecho = re.search(rf'<select id="{id_do_campo}".*?</select>', pagina, re.DOTALL)
        assert trecho, id_do_campo
        return [v for v in re.findall(r'<option value="([^"]*)"', trecho.group(0)) if v]

    objetivos, niveis, dias, minutos = (opcoes(i) for i in ("ia-objetivo", "ia-nivel", "ia-dias", "ia-minutos"))
    assert set(objetivos) == set(ia_treino.OBJETIVOS)
    assert set(niveis) == set(ia_treino.NIVEIS)
    assert [int(d) for d in dias] == list(range(ia_treino.MINIMO_DE_DIAS, ia_treino.MAXIMO_DE_DIAS + 1))
    assert {int(m) for m in minutos} == set(ia_treino.EXERCICIOS_POR_FICHA)

    combinacoes = [
        {"objetivo": o, "nivel": n, "dias": d, "minutos": m, "observacoes": "  dor   no joelho \n"}
        for o in objetivos for n in niveis for d in dias for m in minutos
    ]
    montados = _node(f"""
        import * as m from "{MODULO_IA}";
        const escolhas = {json.dumps(combinacoes)};
        console.log(JSON.stringify(escolhas.map((e) => ({{ problemas: m.validarPedido(e), pedido: m.montarPedido(e) }}))));
    """)

    conn = conectar(caminho)
    try:
        for resultado in montados:
            assert resultado["problemas"] == []
            pedido = ia_treino.conferir_pedido(conn, 1, resultado["pedido"])
            assert pedido.observacoes == "dor no joelho"
    finally:
        conn.close()


# Respostas do professor às perguntas da IA: o navegador e o servidor recusam as mesmas (menos o nome do aluno, que só o servidor sabe).
_RESPOSTAS = [x for x in _OBSERVACOES if "💪" not in x] + ["", "Mais peito e braço.", "💪" * 300, "💪" * 301]


def test_ia_o_navegador_e_o_servidor_recusam_as_mesmas_respostas(tmp_path):
    from app import ia_treino

    js = _node(f"""
        import * as m from "{MODULO_IA}";
        const textos = {json.dumps(_RESPOSTAS)};
        console.log(JSON.stringify(textos.map((t) => m.validarRespostas([t]).length > 0)));
    """)

    caminho = tmp_path / "ia.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.execute("INSERT INTO aluno (id, nome) VALUES (1, 'ZULEICA FICTICIA')")
    conn.commit()
    base = {"objetivo": "hipertrofia", "nivel": "iniciante", "dias": 3, "minutos": 60}
    python = []
    for texto in _RESPOSTAS:
        try:
            ia_treino.conferir_pedido(conn, 1, {**base, "rodadas": [{"perguntas": ["Alguma lesão?"], "respostas": [texto]}]})
            python.append(False)
        except ia_treino.PedidoInvalido:
            python.append(True)
    conn.close()

    assert js == python, [(t, j, p) for t, j, p in zip(_RESPOSTAS, js, python) if j != p]


def test_ia_a_conversa_que_o_navegador_monta_e_aceita_pelo_servidor(tmp_path):
    """Uma ida e volta de verdade: o que `montarPedido` produz com perguntar e rodadas passa em `conferir_pedido`."""
    from app import ia_treino

    montados = _node(f"""
        import * as m from "{MODULO_IA}";
        const escolha = {{ objetivo: "forca", nivel: "intermediario", dias: "4", minutos: "45", observacoes: "  evitar   impacto " }};
        const r1 = {{ perguntas: ["  O que mudar? ", "Alguma lesão?"], respostas: ["  mais   peito ", ""] }};
        const r2 = {{ perguntas: ["Prefere halteres?"], respostas: ["Prefiro máquinas."] }};
        console.log(JSON.stringify({{
          comecando: m.montarPedido(escolha, {{ perguntar: true }}),
          segunda: m.montarPedido(escolha, {{ perguntar: true, rodadas: [r1] }}),
          ultima: m.montarPedido(escolha, {{ perguntar: false, rodadas: [r1, r2] }}),
          problemas: m.validarRespostas([...r1.respostas, ...r2.respostas]),
        }}));
    """)

    assert montados["problemas"] == []
    caminho = tmp_path / "ia.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.execute("INSERT INTO aluno (id, nome) VALUES (1, 'ZULEICA FICTICIA')")
    conn.commit()
    try:
        comecando = ia_treino.conferir_pedido(conn, 1, montados["comecando"])
        segunda = ia_treino.conferir_pedido(conn, 1, montados["segunda"])
        ultima = ia_treino.conferir_pedido(conn, 1, montados["ultima"])
    finally:
        conn.close()

    assert comecando.perguntar and comecando.rodadas == () and comecando.pode_perguntar
    assert segunda.rodadas == ((("O que mudar?", "mais peito"), ("Alguma lesão?", "")),) and segunda.pode_perguntar
    assert len(ultima.rodadas) == 2 and not ultima.perguntar and not ultima.pode_perguntar


def test_ia_as_perguntas_que_o_servidor_devolve_sao_lidas_pelo_navegador(tmp_path):
    """O JSON que `consultar_pedido` entrega (perguntas) é o que `interpretarConsulta` espera."""
    from app import ia_treino

    caminho = tmp_path / "ia.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.execute("INSERT INTO aluno (id, nome) VALUES (1, 'ZULEICA FICTICIA')")
    resultado = ia_treino.conferir_perguntas({"perguntas": ["Qual o foco?", "Tem lesão?"]}, 2)
    conn.execute(
        "INSERT INTO ia_pedido (aluno_id, criado_em, dia, situacao, modelo, resultado) VALUES (1, '2026-10-13 15:00:00', '2026-10-13', 'pronto', 'm', ?)",
        (json.dumps(resultado, ensure_ascii=False),),
    )
    conn.commit()
    corpo = ia_treino.consultar_pedido(conn, 1, 1, datetime(2026, 10, 13, 15, 1, tzinfo=timezone.utc))
    conn.close()

    lido = _node(f"""
        import * as m from "{MODULO_IA}";
        console.log(JSON.stringify(m.interpretarConsulta({{ status: 200, corpo: {json.dumps(corpo)} }})));
    """)

    assert lido == {"tipo": "perguntas", "perguntas": ["Qual o foco?", "Tem lesão?"], "rodada": 2, "maximoDeRodadas": 2}


# ------------------------------------------------------------------ comentários do aluno (celular -> servidor)

MODULO_DO_ALUNO = (RAIZ / "app" / "static" / "aluno_modelo.js").as_uri()


def test_o_pedido_de_comentario_montado_pelo_javascript_e_aceito_pelo_servidor(tmp_path):
    """O celular monta o pedido com o treino que o SERVIDOR mandou; o servidor tem que aceitar sem reclamar."""
    from app import comentarios
    from app.aluno_treino import treino_do_aluno

    conn = conectar(tmp_path / "contrato.db")
    criar_tabelas(conn)
    conn.execute("INSERT INTO aluno (id, nome, cpf, situacao) VALUES (1, 'ANA SOUZA', '11144477735', 'A')")
    for nome in ("SUPINO RETO", "(15) CADEIRA ABDUTORA"):
        conn.execute("INSERT INTO exercicio (nome, origem) VALUES (?, 'app')", (nome,))
    conn.commit()
    treinos.salvar_treino(
        conn,
        1,
        {
            "nome_treino": "TREINO ABC",
            "montado_por": "ANA",
            "fichas": [
                {"nome": "A PEITO", "itens": [{"exercicio_id": 1, "series": "4", "repeticoes": "12"}]},
                {"nome": "B PERNA", "itens": [{"exercicio_id": 2, "series": "3", "repeticoes": "15"}]},
            ],
        },
    )
    treino = json.loads(json.dumps(treino_do_aluno(conn, 1)))  # o que o celular recebe
    js = _node(f"""
        import * as m from "{MODULO_DO_ALUNO}";
        const treino = {json.dumps(treino)};
        const ficha = treino.fichas[1];
        const exercicio = ficha.grupos[0].exercicios[0];
        console.log(JSON.stringify({{
          inteiro: m.pedidoDoComentario(treino, "Está leve demais"),
          exercicio: m.pedidoDoComentario(treino, "Dói o ombro", ficha, exercicio),
          limite: m.LIMITE_DO_COMENTARIO,
        }}));
    """)

    assert js["limite"] == comentarios.LIMITE_DO_TEXTO
    inteiro, exercicio = js["inteiro"], js["exercicio"]
    assert comentarios.enviar_comentario(conn, 1, inteiro["treino"], inteiro["texto"]) == {"repetido": False}
    assert comentarios.enviar_comentario(
        conn, 1, exercicio["treino"], exercicio["texto"],
        ficha=exercicio["ficha"], item=exercicio["item"], exercicio=exercicio["exercicio"],
    ) == {"repetido": False}
    linhas = [dict(linha) for linha in conn.execute("SELECT ficha_nome, exercicio_nome, texto FROM comentario ORDER BY id")]
    assert linhas == [
        {"ficha_nome": None, "exercicio_nome": None, "texto": "Está leve demais"},
        {"ficha_nome": "B PERNA", "exercicio_nome": "CADEIRA ABDUTORA", "texto": "Dói o ombro"},
    ]
    conn.close()


# ------------------------------------------------------------------ respostas do professor (computador -> servidor -> celular)

MODULO_DO_PROFESSOR = (RAIZ / "app" / "static" / "comentarios_modelo.js").as_uri()


def _banco_com_comentarios(tmp_path):
    from app import comentarios

    conn = conectar(tmp_path / "respostas.db")
    criar_tabelas(conn)
    conn.execute("INSERT INTO aluno (id, nome, cpf, situacao) VALUES (1, 'ANA SOUZA', '11144477735', 'A')")
    conn.execute("INSERT INTO aluno (id, nome, cpf, situacao) VALUES (2, 'BRUNO LIMA', '52998224725', 'A')")
    conn.execute("INSERT INTO exercicio (nome, origem) VALUES ('SUPINO RETO', 'app')")
    conn.commit()
    treinos.salvar_treino(
        conn,
        1,
        {
            "nome_treino": "TREINO ABC",
            "montado_por": "ANA",
            "fichas": [{"nome": "A PEITO", "itens": [{"exercicio_id": 1, "series": "4", "repeticoes": "12"}]}],
        },
    )
    comentarios.enviar_comentario(conn, 1, "TREINO ABC", "Está leve demais")
    comentarios.enviar_comentario(
        conn, 1, "TREINO ABC", "Dói o ombro", ficha=1, item=1, exercicio="SUPINO RETO"
    )
    return conn


def test_os_limites_da_resposta_sao_os_mesmos_nos_dois_lados():
    from app import comentarios

    js = _node(f"""
        import * as m from "{MODULO_DO_PROFESSOR}";
        console.log(JSON.stringify({{ resposta: m.LIMITE_DA_RESPOSTA, nome: m.LIMITE_DO_NOME }}));
    """)

    assert js["resposta"] == comentarios.LIMITE_DO_TEXTO
    assert js["nome"] == treinos.LIMITE_QUEM_MONTOU


def test_a_resposta_montada_pelo_javascript_e_aceita_pelo_servidor(tmp_path):
    from app import comentarios

    conn = _banco_com_comentarios(tmp_path)
    js = _node(f"""
        import * as m from "{MODULO_DO_PROFESSOR}";
        const pronta = m.respostaPronta("  Thiago ", "  Pode trocar por 💪 supino inclinado.  ");
        console.log(JSON.stringify({{ pronta, pedido: m.pedidoDaResposta(pronta.professor, pronta.resposta) }}));
    """)

    assert js["pronta"]["ok"] is True
    pedido = js["pedido"]
    resultado = comentarios.responder(conn, 2, pedido["professor"], pedido["resposta"])
    assert resultado["respondido_por"] == "Thiago"
    linha = conn.execute("SELECT resposta, respondido_por, lido_em FROM comentario WHERE id = 2").fetchone()
    assert linha["resposta"] == "Pode trocar por 💪 supino inclinado."
    assert linha["respondido_por"] == "Thiago"
    assert linha["lido_em"] is not None  # responder também marca como lido
    conn.close()


def test_o_que_o_javascript_recusa_o_servidor_tambem_recusa(tmp_path):
    """Os dois lados concordam sobre nome/resposta vazios ou grandes demais (a tela só poupa uma ida ao servidor)."""
    from app import comentarios

    conn = _banco_com_comentarios(tmp_path)
    casos = [
        ["", "Oi"],
        ["   ", "Oi"],
        ["Thiago", ""],
        ["Thiago", "  \n "],
        ["a" * 61, "Oi"],
        ["Thiago", "a" * 501],
    ]
    js = _node(f"""
        import * as m from "{MODULO_DO_PROFESSOR}";
        const casos = {json.dumps(casos)};
        console.log(JSON.stringify(casos.map(([nome, texto]) => m.respostaPronta(nome, texto).ok)));
    """)

    assert js == [False] * len(casos)
    for nome, texto in casos:
        with pytest.raises(comentarios.ComentarioInvalido) as erro:
            comentarios.responder(conn, 1, nome, texto)
        assert erro.value.status == 400
    assert conn.execute("SELECT COUNT(*) FROM comentario WHERE resposta IS NOT NULL").fetchone()[0] == 0
    conn.close()


def test_os_limites_no_tamanho_exato_valem_nos_dois_lados(tmp_path):
    from app import comentarios

    conn = _banco_com_comentarios(tmp_path)
    nome, texto = "n" * 60, "💪" * 500  # 500 emojis: 1.000 no .length do JavaScript, 500 letras para o servidor
    js = _node(f"""
        import * as m from "{MODULO_DO_PROFESSOR}";
        console.log(JSON.stringify(m.respostaPronta({json.dumps(nome)}, {json.dumps(texto)}).ok));
    """)

    assert js is True
    comentarios.responder(conn, 1, nome, texto)
    assert conn.execute("SELECT resposta FROM comentario WHERE id = 1").fetchone()[0] == texto
    conn.close()


def test_a_lista_do_servidor_e_lida_pelo_celular_e_os_vistos_voltam_aceitos(tmp_path):
    """Servidor -> celular: a lista de 'Seus comentários' é entendida; celular -> servidor: os ids dos 'vistos' são aceitos."""
    from app import comentarios

    conn = _banco_com_comentarios(tmp_path)
    comentarios.responder(conn, 2, "Thiago", "Troque por supino inclinado.")
    treinos.salvar_treino(
        conn,
        2,
        {
            "nome_treino": "TREINO X",
            "montado_por": "ANA",
            "fichas": [{"nome": "A", "itens": [{"exercicio_id": 1, "series": "3", "repeticoes": "10"}]}],
        },
    )
    comentarios.enviar_comentario(conn, 2, "TREINO X", "Outro aluno")  # não pode aparecer na lista da Ana
    lista = json.loads(json.dumps(comentarios.listar_do_aluno(conn, 1)))  # o que o celular recebe
    js = _node(f"""
        import * as m from "{MODULO_DO_ALUNO}";
        const lista = {json.dumps(lista)};
        const lida = m.descreverMeusComentarios(200, lista);
        console.log(JSON.stringify({{
          lida,
          aviso: m.textoDoAvisoDeResposta(lida.respostasNovas),
          botao: m.textoDoBotaoMeusComentarios(lida.total, lida.respostasNovas, false),
          lugares: lida.comentarios.map(m.textoDoLugar),
          ids: m.idsDasRespostasNovas(lida.comentarios),
        }}));
    """)

    assert js["lida"]["tipo"] == "ok"
    assert js["lida"]["total"] == 2
    assert js["lida"]["respostasNovas"] == 1
    assert js["aviso"] == "Você tem 1 resposta nova do professor."
    assert js["botao"] == "Ver seus comentários (2) · 1 resposta nova"
    assert js["lugares"] == ["A PEITO · SUPINO RETO", "Treino inteiro"]  # a resposta nova vem primeiro; depois o mais novo
    assert js["ids"] == [2]

    resultado = comentarios.marcar_respostas_vistas(conn, 1, js["ids"])
    assert resultado["respostas_novas"] == 0
    depois = _node(f"""
        import * as m from "{MODULO_DO_ALUNO}";
        const corpo = {json.dumps({"ok": True, **resultado})};
        console.log(JSON.stringify(m.descreverVistos(200, corpo)));
    """)
    assert depois == {"tipo": "ok", "respostasNovas": 0}
    conn.close()
