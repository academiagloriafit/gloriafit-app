"""Histórico do treino feito com a IA (app/ia_historico.py): "Por que este treino foi montado assim".

A API da Anthropic é sempre uma falsa; dados inventados. O que estes testes protegem:
- o que o professor escreveu para o robô e a justificativa do robô ficam LIGADOS ao treino e aparecem na ficha do aluno;
- "nenhuma observação" aparece escrito quando o professor não escreveu nada;
- o aluno e a impressão nunca recebem esse texto;
- guardar o histórico nunca estraga o "Salvar treino".
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app import acesso, aluno_acesso, cupom, ia_historico, ia_retorno, ia_treino
from app.aluno_treino import treino_do_aluno
from app.db import conectar, criar_tabelas
from app.web import criar_app

CHAVE = "sk-ant-chave-de-teste-0123456789abcdef"
OBSERVACOES = "Hérnia de disco lombar, 52 anos, 1,70 m, 80 kg, treina há 2 anos"
JUSTIFICATIVA = [
    "Duas fichas (peito e costas) porque o aluno pediu 2 dias por semana.",
    "Uma ficha de 1 exercício foi um teste: o tempo de 60 minutos permitiria mais.",
]
PEDIDO = {"objetivo": "hipertrofia", "nivel": "iniciante", "dias": 2, "minutos": 60, "observacoes": OBSERVACOES}


def _rascunho(justificativa=JUSTIFICATIVA, alertas=("Avaliar a lombar antes de aplicar.",), resumo="Duas fichas simples."):
    entrada = {
        "fichas": [
            {"nome": "A - PEITO", "itens": [{"exercicio_id": 1, "series": "3", "repeticoes": "12"}]},
            {"nome": "B - COSTAS", "itens": [{"exercicio_id": 2, "series": "3", "repeticoes": "10"}]},
        ],
        "resumo": resumo,
        "alertas": list(alertas),
    }
    if justificativa is not None:
        entrada["justificativa"] = justificativa
    return {
        "stop_reason": "tool_use",
        "content": [{"type": "tool_use", "name": "montar_treino", "input": entrada}],
        "usage": {"input_tokens": 5000, "output_tokens": 700},
    }


class IAFalsa:
    def __init__(self, devolve=None):
        self.devolve = devolve or _rascunho()

    def __call__(self, chave, corpo, *_a, **_k):
        return self.devolve


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "ia.db"
    c = conectar(caminho)
    criar_tabelas(c)
    c.execute("INSERT INTO aluno (id, nome, cpf) VALUES (1, 'ANA FICTICIA', '12345678909'), (2, 'BRUNO FICTICIO', NULL)")
    c.execute(
        "INSERT INTO exercicio (id, nome, origem, usos_ultimo_ano) VALUES"
        " (1, '(3) SUPINO RETO', 'app', 50), (2, 'REMADA', 'app', 50), (3, 'LEG PRESS', 'app', 50)"
    )
    c.commit()
    c.close()
    ia_treino.guardar_chave(tmp_path / "ia_chave", CHAVE)
    return caminho


@pytest.fixture
def app(caminho):
    aplicativo = criar_app(caminho)
    aplicativo.config["IA_CHAMADA"] = IAFalsa()
    aplicativo.config["IA_EM_SEGUNDO_PLANO"] = False
    return aplicativo


@pytest.fixture
def cliente(app, caminho):
    navegador = app.test_client()
    c = conectar(caminho)
    codigo = acesso.gerar_codigo(c, "Computador de teste").codigo
    token = acesso.autorizar(c, codigo).token
    c.close()
    navegador.set_cookie(acesso.NOME_DO_COOKIE, token)
    return navegador


def _pedir(cliente, aluno=1, **extras) -> int:
    resposta = cliente.post(f"/api/alunos/{aluno}/treino-ia", json={**PEDIDO, **extras})
    assert resposta.status_code == 202, resposta.get_json()
    return resposta.get_json()["pedido_id"]


def _treino_final(exercicio_b=3, nome="TREINO DA ANA"):
    """O que o professor salva: o rascunho com o exercício 2 (REMADA) da ficha B trocado pelo 3 (LEG PRESS) e as séries da A mudadas."""
    return {
        "nome_treino": nome,
        "montado_por": "PROFESSOR TESTE",
        "fichas": [
            {"nome": "A - PEITO", "itens": [{"exercicio_id": 1, "series": "4", "repeticoes": "12"}]},
            {"nome": "B - COSTAS", "itens": [{"exercicio_id": exercicio_b, "series": "3", "repeticoes": "10"}]},
        ],
    }


def _salvar(cliente, pedido_id, aluno=1, **extras):
    return cliente.post(f"/api/alunos/{aluno}/treinos", json={**_treino_final(**extras), "ia": {"pedido_id": pedido_id}})


def _linhas(caminho, sql="SELECT * FROM treino_ia ORDER BY treino_id"):
    c = conectar(caminho)
    try:
        return [dict(l) for l in c.execute(sql)]
    finally:
        c.close()


# ------------------------------------------------------------------ o que o robô escreve: a justificativa


def _conferir(entrada_extra):
    base = {"fichas": [{"nome": "A", "itens": [{"exercicio_id": 1, "series": "3", "repeticoes": "12"}]}], "resumo": "Ok."}
    c = conectar()
    criar_tabelas(c)
    c.execute("INSERT INTO exercicio (id, nome, origem) VALUES (1, 'SUPINO RETO', 'app')")
    pedido = ia_treino.Pedido("hipertrofia", "iniciante", 1, 60, "", None)
    try:
        return ia_treino.conferir_rascunho(c, {**base, **entrada_extra}, {1}, pedido)
    finally:
        c.close()


def test_a_justificativa_do_robo_vai_no_resultado_limpa_e_cortada():
    longo = "x" * (ia_treino.LIMITE_DE_CADA_PONTO_DA_JUSTIFICATIVA + 50)

    resultado = _conferir({"justificativa": ["  Primeiro   ponto  ", "", "   ", 7, longo] + [f"ponto {n}" for n in range(10)]})

    pontos = resultado["justificativa"]
    assert pontos[0] == "Primeiro ponto"
    assert len(pontos[1]) == ia_treino.LIMITE_DE_CADA_PONTO_DA_JUSTIFICATIVA
    assert len(pontos) == ia_treino.MAXIMO_DE_PONTOS_DA_JUSTIFICATIVA  # o resto é descartado


def test_justificativa_como_texto_solto_vira_um_ponto_e_lixo_vira_lista_vazia():
    assert _conferir({"justificativa": "Um texto só."})["justificativa"] == ["Um texto só."]
    for lixo in (None, 5, {"a": 1}, [None, 3]):
        assert _conferir({"justificativa": lixo})["justificativa"] == []
    assert _conferir({})["justificativa"] == []


def test_a_ferramenta_pede_a_justificativa_e_a_regra_16_explica_o_que_escrever():
    propriedade = ia_treino.FERRAMENTA["input_schema"]["properties"]["justificativa"]

    assert propriedade["type"] == "array" and propriedade["items"] == {"type": "string"}
    assert "maxItems" not in propriedade  # a API não aceita (os limites ficam na conferência do servidor)
    assert "justificativa" in ia_treino.FERRAMENTA["input_schema"]["required"]
    regras = ia_treino.REGRAS_DA_CASA
    assert "16. JUSTIFICATIVA" in regras
    for assunto in ("divididas", "quantidade de exercícios", "séries, repetições e pausas", "nunca invente", "Sem nome do aluno"):
        assert assunto in regras


# ------------------------------------------------------------------ guardar ao salvar o treino


def test_ao_salvar_o_historico_fica_ligado_ao_treino(cliente, caminho):
    pedido_id = _pedir(cliente, rodadas=[{"perguntas": ["Treina há quanto tempo?"], "respostas": ["Há 2 anos"]}])

    resposta = _salvar(cliente, pedido_id)

    assert resposta.status_code == 201
    treino_id = resposta.get_json()["id"]
    [linha] = _linhas(caminho)
    assert linha["treino_id"] == treino_id
    assert (linha["objetivo"], linha["nivel"], linha["dias"], linha["minutos"], linha["fila"]) == ("hipertrofia", "iniciante", 2, 60, None)
    assert linha["observacoes"] == OBSERVACOES
    assert json.loads(linha["conversa"]) == [[{"pergunta": "Treina há quanto tempo?", "resposta": "Há 2 anos"}]]
    assert json.loads(linha["justificativa"]) == JUSTIFICATIVA
    assert json.loads(linha["alertas"]) == ["Avaliar a lombar antes de aplicar."]
    ajustes = json.loads(linha["ajustes"])
    assert ajustes["tirados"] == [{"ficha": 2, "exercicio": "REMADA"}]
    assert ajustes["incluidos"] == [{"ficha": 2, "exercicio": "LEG PRESS"}]
    assert {(a["campo"], a["de"], a["para"]) for a in ajustes["alterados"]} == {("series", "3", "4")}
    assert linha["regras"] == ia_treino.VERSAO_DAS_REGRAS and linha["modelo"] == ia_treino.modelo_em_uso()


def test_sem_observacoes_e_sem_perguntas_fica_registrado_que_nao_havia(cliente, caminho):
    pedido_id = _pedir(cliente, observacoes="")

    _salvar(cliente, pedido_id)

    [linha] = _linhas(caminho)
    assert linha["observacoes"] == "" and linha["conversa"] is None


def test_se_o_robo_nao_escreveu_justificativa_vale_o_resumo(cliente, caminho, app):
    app.config["IA_CHAMADA"] = IAFalsa(_rascunho(justificativa=None, resumo="Treino simples de duas fichas."))
    pedido_id = _pedir(cliente)

    _salvar(cliente, pedido_id)

    assert json.loads(_linhas(caminho)[0]["justificativa"]) == ["Treino simples de duas fichas."]


def test_treino_salvo_exatamente_como_o_rascunho_diz_que_nada_mudou(cliente, caminho):
    pedido_id = _pedir(cliente)
    igual = {
        "nome_treino": "TREINO IGUAL",
        "montado_por": "PROFESSOR TESTE",
        "fichas": [
            {"nome": "A - PEITO", "itens": [{"exercicio_id": 1, "series": "3", "repeticoes": "12"}]},
            {"nome": "B - COSTAS", "itens": [{"exercicio_id": 2, "series": "3", "repeticoes": "10"}]},
        ],
    }

    assert cliente.post("/api/alunos/1/treinos", json={**igual, "ia": {"pedido_id": pedido_id}}).status_code == 201

    ajustes = ia_historico.texto_dos_ajustes(json.loads(_linhas(caminho)[0]["ajustes"]))
    assert ajustes == {"igual": True, "linhas": []}


def test_o_mesmo_rascunho_so_gera_um_historico(cliente, caminho):
    pedido_id = _pedir(cliente)
    primeiro = _salvar(cliente, pedido_id).get_json()["id"]

    c = conectar(caminho)
    try:
        assert ia_historico.registrar(c, 1, pedido_id, primeiro) is False  # já registrado
    finally:
        c.close()
    assert len(_linhas(caminho)) == 1


def test_rascunho_de_outro_aluno_nao_gera_historico_mas_o_treino_e_salvo(cliente, caminho):
    pedido_do_ana = _pedir(cliente, aluno=1)

    resposta = _salvar(cliente, pedido_do_ana, aluno=2, nome="TREINO DO BRUNO")

    assert resposta.status_code == 201
    assert _linhas(caminho) == []


def test_rascunho_ja_apagado_depois_de_3_dias_nao_gera_historico_mas_o_treino_e_salvo(cliente, caminho):
    pedido_id = _pedir(cliente)
    c = conectar(caminho)
    c.execute("UPDATE ia_pedido SET resultado = NULL")
    c.commit()
    c.close()

    assert _salvar(cliente, pedido_id).status_code == 201
    assert _linhas(caminho) == []


def test_rascunho_de_antes_desta_funcao_nao_tem_o_que_guardar_e_o_treino_e_salvo(cliente, caminho):
    pedido_id = _pedir(cliente)
    c = conectar(caminho)
    resultado = json.loads(c.execute("SELECT resultado FROM ia_pedido").fetchone()["resultado"])
    del resultado["_historico"]  # como era um pedido feito antes desta versão
    c.execute("UPDATE ia_pedido SET resultado = ?", (json.dumps(resultado),))
    c.commit()
    c.close()

    assert _salvar(cliente, pedido_id).status_code == 201
    assert _linhas(caminho) == []


def test_se_guardar_o_historico_falhar_o_treino_continua_salvo(cliente, caminho, monkeypatch):
    pedido_id = _pedir(cliente)

    def quebra(*_a, **_k):
        raise RuntimeError("falha de teste")

    monkeypatch.setattr(ia_historico, "registrar", quebra)

    resposta = _salvar(cliente, pedido_id)

    assert resposta.status_code == 201
    c = conectar(caminho)
    try:
        assert c.execute("SELECT COUNT(*) FROM treino").fetchone()[0] == 1
    finally:
        c.close()
    assert _linhas(caminho) == []


def test_o_historico_continua_depois_que_o_resultado_do_pedido_e_apagado(cliente, caminho):
    pedido_id = _pedir(cliente)
    _salvar(cliente, pedido_id)
    c = conectar(caminho)
    try:
        ia_treino.limpar_pedidos_antigos(c, datetime.now(timezone.utc) + timedelta(days=4))
        assert c.execute("SELECT resultado FROM ia_pedido").fetchone()["resultado"] is None  # o texto saiu do pedido
    finally:
        c.close()

    [linha] = _linhas(caminho)
    assert linha["observacoes"] == OBSERVACOES  # mas continua no histórico do treino


def test_a_tela_do_rascunho_nao_recebe_a_area_do_historico(cliente):
    pedido_id = _pedir(cliente)

    corpo = cliente.get(f"/api/alunos/1/treino-ia/{pedido_id}").get_json()

    assert corpo["situacao"] == "pronto" and "_historico" not in corpo and "_retorno" not in corpo
    assert "Hérnia" not in json.dumps(corpo, ensure_ascii=False)


def test_o_pedido_guarda_o_que_o_robo_recebeu_inclusive_as_rodadas(cliente, caminho):
    _pedir(cliente, rodadas=[{"perguntas": ["Já treinou antes?"], "respostas": [""]}])

    [linha] = _linhas(caminho, "SELECT resultado FROM ia_pedido")
    historico = json.loads(linha["resultado"])["_historico"]
    assert historico == {
        "observacoes": OBSERVACOES,
        "conversa": [[{"pergunta": "Já treinou antes?", "resposta": ""}]],
        "gravado": False,
    }


# ------------------------------------------------------------------ o texto para a tela (ficha do aluno)


def test_texto_dos_ajustes_conta_o_que_o_professor_mudou():
    mudancas = {
        "fichas": {"ia": 3, "final": 2},
        "tirados": [{"ficha": 1, "exercicio": "REMADA"}, {"ficha": 2, "exercicio": "LEG PRESS"}],
        "incluidos": [{"ficha": 1, "exercicio": "AGACHAMENTO"}],
        "alterados": [{"ficha": 1, "exercicio": "SUPINO", "campo": "series", "de": "3", "para": "4"}, {"ficha": 1, "exercicio": "SUPINO", "campo": "pausa", "de": "60", "para": ""}],
        "observacoes_mudadas": 2,
        "fichas_com_ordem_mudada": 1,
        "fichas_renomeadas": 1,
        "cortados": 0,
    }

    resultado = ia_historico.texto_dos_ajustes(mudancas)

    assert resultado["igual"] is False
    assert resultado["linhas"] == [
        "Número de fichas: o robô fez 3 e o treino ficou com 2.",
        "Tirou: REMADA (ficha 1); LEG PRESS (ficha 2).",
        "Incluiu: AGACHAMENTO (ficha 1).",
        "SUPINO (ficha 1): séries de 3 para 4.",
        "SUPINO (ficha 1): pausa (segundos) de 60 para em branco.",
        "Mudou o texto de observação de 2 exercícios.",
        "Mudou a ordem dos exercícios em 1 ficha.",
        "Mudou o nome de 1 ficha.",
    ]


def test_texto_dos_ajustes_limita_as_linhas_de_series_e_aguenta_lixo():
    alterados = [{"ficha": 1, "exercicio": f"EX {n}", "campo": "series", "de": "3", "para": "4"} for n in range(15)]

    resultado = ia_historico.texto_dos_ajustes({"fichas": {"ia": 1, "final": 1}, "alterados": alterados})

    assert len(resultado["linhas"]) == ia_historico.MAXIMO_DE_MUDANCAS_NA_TELA + 1
    assert resultado["linhas"][-1] == "E mais 5 mudanças de séries, repetições ou pausa."
    assert ia_historico.texto_dos_ajustes(None) == {"igual": False, "linhas": []}
    assert ia_historico.texto_dos_ajustes({"tirados": "x", "alterados": [1, None]})["igual"] is True


def test_do_aluno_so_devolve_os_treinos_do_proprio_aluno(cliente, caminho):
    _salvar(cliente, _pedir(cliente, aluno=1), aluno=1)
    c = conectar(caminho)
    try:
        assert list(ia_historico.do_aluno(c, 1)) != []
        assert ia_historico.do_aluno(c, 2) == {}
        assert ia_historico.do_aluno(c, 999) == {}
    finally:
        c.close()


def test_do_aluno_aguenta_json_torto_no_banco(cliente, caminho):
    _salvar(cliente, _pedir(cliente))
    c = conectar(caminho)
    c.execute("UPDATE treino_ia SET conversa = 'nao-e-json', justificativa = '{', alertas = '5', ajustes = '[]'")
    c.commit()
    try:
        [historico] = ia_historico.do_aluno(c, 1).values()
    finally:
        c.close()

    assert historico["conversa"] == [] and historico["justificativa"] == [] and historico["alertas"] == []
    assert historico["ajustes"] == {"igual": False, "linhas": []}


def _ficha(cliente, aluno=1) -> str:
    resposta = cliente.get(f"/alunos/{aluno}")
    assert resposta.status_code == 200
    return resposta.get_data(as_text=True)


def test_a_ficha_mostra_o_que_o_professor_escreveu_e_a_justificativa_do_robo(cliente):
    pedido_id = _pedir(cliente, rodadas=[{"perguntas": ["Treina há quanto tempo?"], "respostas": ["Há 2 anos"]}])
    _salvar(cliente, pedido_id)

    pagina = _ficha(cliente)

    assert "Ver por que este treino foi montado assim" in pagina
    for texto in (
        OBSERVACOES,
        "Treina há quanto tempo?",
        "Há 2 anos",
        JUSTIFICATIVA[0],
        JUSTIFICATIVA[1],
        "Avaliar a lombar antes de aplicar.",
        "Ganhar massa muscular",  # o objetivo com o nome para ler, não o código "hipertrofia"
        "Iniciante",
        "60 minutos",
        "Tirou: REMADA (ficha 2).",
        "Incluiu: LEG PRESS (ficha 2).",
        "PROFESSOR TESTE",
    ):
        assert texto in pagina, texto


def test_sem_observacoes_a_ficha_diz_que_nenhuma_foi_escrita(cliente):
    _salvar(cliente, _pedir(cliente, observacoes=""))

    pagina = _ficha(cliente)

    assert "Nenhuma observação foi escrita para o robô." in pagina
    assert "Perguntas do robô e respostas do professor" not in pagina


def test_treino_salvo_sem_mudar_nada_diz_que_foi_como_o_robo_montou(cliente):
    pedido_id = _pedir(cliente)
    igual = {
        "nome_treino": "TREINO IGUAL",
        "montado_por": "PROFESSOR TESTE",
        "fichas": [
            {"nome": "A - PEITO", "itens": [{"exercicio_id": 1, "series": "3", "repeticoes": "12"}]},
            {"nome": "B - COSTAS", "itens": [{"exercicio_id": 2, "series": "3", "repeticoes": "10"}]},
        ],
    }
    cliente.post("/api/alunos/1/treinos", json={**igual, "ia": {"pedido_id": pedido_id}})

    assert "Nada: o treino foi salvo como o robô montou." in _ficha(cliente)


def test_texto_com_html_sai_escapado_na_ficha(cliente, app):
    app.config["IA_CHAMADA"] = IAFalsa(_rascunho(justificativa=['<img src=x onerror="alert(1)">'], alertas=["<script>alert(2)</script>"]))
    _salvar(cliente, _pedir(cliente, observacoes="<b>negrito</b> e <script>alert(3)</script>"))

    pagina = _ficha(cliente)

    for perigoso in ("<b>negrito</b>", "<script>alert(2)", "<script>alert(3)", '<img src=x onerror="alert(1)">'):
        assert perigoso not in pagina, perigoso
    assert "&lt;b&gt;negrito&lt;/b&gt;" in pagina and "&lt;script&gt;alert(2)&lt;/script&gt;" in pagina


def test_treino_montado_sem_a_ia_diz_que_nao_ha_historico_e_o_do_data4u_fica_quieto(cliente, caminho):
    cliente.post("/api/alunos/1/treinos", json=_treino_final(nome="TREINO A MAO"))
    c = conectar(caminho)
    c.execute(
        "INSERT INTO treino (aluno_id, nome, montado_por, ativo, origem, data4u_id) VALUES (1, 'TREINO ANTIGO', 'DATA4U', 0, 'data4u', 99)"
    )
    c.commit()
    c.close()

    pagina = _ficha(cliente)

    assert pagina.count("Sem histórico do robô") == 1  # só o treino feito no app; o copiado do Data4U não leva a frase
    assert "por que este treino foi montado assim" not in pagina


# ------------------------------------------------------------------ o aluno e a impressão nunca recebem isto


def _guardar_historico_com_segredos(cliente, caminho):
    treino_id = _salvar(cliente, _pedir(cliente)).get_json()["id"]
    return treino_id


def test_o_celular_do_aluno_nao_recebe_o_historico(cliente, caminho, app):
    _guardar_historico_com_segredos(cliente, caminho)
    c = conectar(caminho)
    try:
        texto_direto = json.dumps(treino_do_aluno(c, 1), ensure_ascii=False)
        with c:
            token = aluno_acesso._criar_sessao(c, 1, datetime.now(timezone.utc))
    finally:
        c.close()
    celular = app.test_client()
    celular.set_cookie(aluno_acesso.NOME_DO_COOKIE, token)
    resposta = celular.get("/api/aluno/treino")
    pagina = celular.get("/aluno")

    assert resposta.status_code == 200
    todos = texto_direto + resposta.get_data(as_text=True) + pagina.get_data(as_text=True)
    for segredo in (OBSERVACOES, "Hérnia", JUSTIFICATIVA[0], "lombar", "justificativa", "Por que este treino"):
        assert segredo not in todos, segredo


def test_a_impressao_nao_leva_o_historico(cliente, caminho):
    treino_id = _guardar_historico_com_segredos(cliente, caminho)
    c = conectar(caminho)
    try:
        conteudo = json.dumps(cupom.montar_cupom(c, treino_id, "app.exemplo.com.br", None), ensure_ascii=False)
    finally:
        c.close()
    pagina = cliente.get(f"/treinos/{treino_id}/imprimir").get_data(as_text=True)

    for segredo in (OBSERVACOES, "Hérnia", JUSTIFICATIVA[0], "lombar"):
        assert segredo not in conteudo and segredo not in pagina, segredo


def test_a_rota_da_ficha_exige_computador_autorizado(app, cliente):
    _guardar_historico_com_segredos(cliente, app.config["CAMINHO_BANCO"])

    resposta = app.test_client().get("/alunos/1")

    assert resposta.status_code in (302, 401, 403)
    assert "Hérnia" not in resposta.get_data(as_text=True)


# ------------------------------------------------------------------ o relatório do que o robô aprende continua sem aluno nem texto


def test_o_relatorio_do_retorno_continua_sem_o_texto_do_historico(cliente, caminho):
    pedido_id = _pedir(cliente)
    cliente.post(f"/api/alunos/1/treino-ia/{pedido_id}/avaliacao", json={"nota": "com_ajustes", "motivo": "Faltou posterior de coxa"})
    _salvar(cliente, pedido_id)

    c = conectar(caminho)
    try:
        relatorio = ia_retorno.relatorio(c)
        retorno = json.dumps([dict(l) for l in c.execute("SELECT * FROM ia_retorno")], ensure_ascii=False)
    finally:
        c.close()

    for segredo in (OBSERVACOES, "Hérnia", JUSTIFICATIVA[0], "lombar", "ANA", "FICTICIA", "PROFESSOR TESTE"):
        assert segredo not in relatorio and segredo not in retorno, segredo


# ------------------------------------------------------------------ "Editar treino" e "Concluído" não apagam o histórico


def test_editar_o_treino_no_lugar_nao_apaga_o_historico(cliente, caminho):
    treino_id = _salvar(cliente, _pedir(cliente)).get_json()["id"]

    resposta = cliente.post(f"/api/treinos/{treino_id}/editar", json=_treino_final(nome="TREINO DA ANA EDITADO"))

    assert resposta.status_code == 200, resposta.get_json()
    [linha] = _linhas(caminho)
    assert linha["treino_id"] == treino_id and linha["observacoes"] == OBSERVACOES
    pagina = _ficha(cliente)
    assert "TREINO DA ANA EDITADO" in pagina and OBSERVACOES in pagina  # o treino mudou de nome, o histórico continua
    assert 'Editar treino' in pagina and "Ver por que este treino foi montado assim" in pagina


def test_treino_concluido_continua_com_o_historico_na_ficha(cliente):
    treino_id = _salvar(cliente, _pedir(cliente)).get_json()["id"]

    assert cliente.post(f"/api/treinos/{treino_id}/concluir", json={}).status_code == 200

    pagina = _ficha(cliente)
    assert OBSERVACOES in pagina and JUSTIFICATIVA[0] in pagina


# ------------------------------------------------------------------ o botão "Ver / Esconder" (pedido do Thiago, 23/10)


def test_o_quadro_comeca_fechado_e_tem_um_botao_para_ver_e_esconder(cliente):
    _salvar(cliente, _pedir(cliente))

    pagina = _ficha(cliente)

    inicio = pagina.index('<details class="porque-treino"')
    marca = pagina[inicio : pagina.index(">", inicio) + 1]
    assert " open" not in marca  # sempre fechado ao abrir a ficha: só aparece o botão
    assert "Ver por que este treino foi montado assim" in pagina
    assert "Esconder por que este treino foi montado assim" in pagina  # o texto do botão quando está aberto (a tela troca por CSS)
    assert pagina.index("<summary><span class=\"porque-ver\">", inicio) < pagina.index("O que o professor passou para o robô")
