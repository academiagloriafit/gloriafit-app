"""Testes do servidor web: rotas, erros e cabeçalhos de segurança."""

import re
from pathlib import Path

import pytest

from app import acesso
from app.db import conectar, criar_tabelas
from app.importar_exercicios import importar_quadro
from app.web import criar_app

QUADRO_REAL = Path(__file__).resolve().parent.parent / "dados" / "quadro_exercicios_v2.xlsx"


def _criar_banco(caminho, grupos=("Peito", "Costas"), exercicios=(), alunos=()):
    """Cria um arquivo de banco com poucos dados.

    exercicios: (nome, [grupos]).  alunos: nomes (o CPF é inventado, só para teste).
    """
    conn = conectar(caminho)
    criar_tabelas(conn)
    for ordem, nome in enumerate(grupos, start=1):
        conn.execute("INSERT INTO grupo_muscular (nome, ordem) VALUES (?, ?)", (nome, ordem))
    for nome, grupos_do_exercicio in exercicios:
        ex_id = conn.execute(
            "INSERT INTO exercicio (nome, origem) VALUES (?, 'app')", (nome,)
        ).lastrowid
        for grupo in grupos_do_exercicio:
            conn.execute(
                "INSERT INTO exercicio_grupo (exercicio_id, grupo_id)"
                " SELECT ?, id FROM grupo_muscular WHERE nome = ?",
                (ex_id, grupo),
            )
    for i, nome in enumerate(alunos, start=1):
        conn.execute("INSERT INTO aluno (nome, cpf) VALUES (?, ?)", (nome, f"{i:011d}"))
    conn.commit()
    conn.close()


def _cliente_autorizado(caminho, nome="Computador de teste"):
    """Cliente de teste que já é um computador autorizado (como o da academia depois do
    /autorizar). Usa o caminho de verdade (gerar o código e trocá-lo pelo cookie)."""
    cliente = criar_app(caminho).test_client()
    conn = conectar(caminho)
    try:
        codigo = acesso.gerar_codigo(conn, nome).codigo
        token = acesso.autorizar(conn, codigo).token
    finally:
        conn.close()
    cliente.set_cookie(acesso.NOME_DO_COOKIE, token)
    return cliente


@pytest.fixture
def cliente(tmp_path):
    # Arquivo de verdade (e não ":memory:"): cada pedido abre a sua própria
    # conexão, e um banco na memória é diferente para cada conexão.
    caminho = tmp_path / "teste.db"
    _criar_banco(
        caminho,
        exercicios=[
            ("Supino reto com barra", ["Peito"]),
            ("Remada curvada", ["Costas"]),
            ("Flexão de braço", ["Peito"]),
        ],
    )
    return _cliente_autorizado(caminho)


# ------------------------------------------------------------------ inicialização


def test_banco_inexistente_falha_na_hora_e_nao_cria_arquivo_vazio(tmp_path):
    caminho = tmp_path / "nao_existe.db"

    with pytest.raises(FileNotFoundError, match="importar_exercicios"):
        criar_app(caminho)
    assert not caminho.exists()


def test_usa_a_variavel_de_ambiente_quando_nao_recebe_o_caminho(tmp_path, monkeypatch):
    caminho = tmp_path / "via_ambiente.db"
    _criar_banco(caminho)
    monkeypatch.setenv("GLORIAFIT_DB", str(caminho))

    assert criar_app().test_client().get("/saude").status_code == 200


# ------------------------------------------------------------------ rotas


def test_saude(cliente):
    resposta = cliente.get("/saude")

    assert resposta.status_code == 200
    assert resposta.get_json() == {"ok": True}


def test_api_grupos(cliente):
    resposta = cliente.get("/api/grupos")

    assert resposta.status_code == 200
    assert [(g["nome"], g["quantidade"]) for g in resposta.get_json()] == [
        ("Peito", 2),
        ("Costas", 1),
    ]


def test_api_exercicios_sem_filtro(cliente):
    dados = cliente.get("/api/exercicios").get_json()

    assert dados["total"] == 3
    assert {e["nome"] for e in dados["exercicios"]} == {
        "Supino reto com barra",
        "Remada curvada",
        "Flexão de braço",
    }


def test_api_exercicios_por_texto_sem_acento(cliente):
    dados = cliente.get("/api/exercicios", query_string={"q": "flexao"}).get_json()

    assert [e["nome"] for e in dados["exercicios"]] == ["Flexão de braço"]


def test_api_exercicios_por_grupo(cliente):
    grupo_costas = next(g["id"] for g in cliente.get("/api/grupos").get_json() if g["nome"] == "Costas")

    dados = cliente.get("/api/exercicios", query_string={"grupo": grupo_costas}).get_json()

    assert [e["nome"] for e in dados["exercicios"]] == ["Remada curvada"]
    assert dados["exercicios"][0]["grupos"] == ["Costas"]


def test_api_exercicios_respeita_o_limite(cliente):
    dados = cliente.get("/api/exercicios", query_string={"limite": 1}).get_json()

    assert len(dados["exercicios"]) == 1
    assert dados["total"] == 3


@pytest.mark.parametrize("parametro", ["grupo", "limite"])
def test_numero_invalido_devolve_400_em_json(cliente, parametro):
    resposta = cliente.get("/api/exercicios", query_string={parametro: "abc"})

    assert resposta.status_code == 400
    assert parametro in resposta.get_json()["erro"]


def test_grupo_vazio_na_url_equivale_a_todos(cliente):
    dados = cliente.get("/api/exercicios", query_string={"grupo": ""}).get_json()

    assert dados["total"] == 3


def test_rota_que_nao_existe_devolve_404(cliente):
    assert cliente.get("/api/qualquer-coisa").status_code == 404


def test_so_get_e_aceito_nas_rotas_da_api(cliente):
    assert cliente.post("/api/exercicios").status_code == 405
    assert cliente.delete("/api/grupos").status_code == 405


# ------------------------------------------------------------------ página


def test_pagina_mostra_titulo_busca_e_todos_os_grupos(cliente):
    html = cliente.get("/exercicios").get_data(as_text=True)

    assert "Lista de exercícios" in html
    assert "Buscar entre 3 exercícios" in html
    for grupo in ("Todos", "Peito", "Costas"):
        assert f">{grupo}</button>" in html


def test_pagina_escapa_nomes_de_grupo(tmp_path):
    caminho = tmp_path / "xss.db"
    _criar_banco(caminho, grupos=("<script>alert(1)</script>",))
    html = _cliente_autorizado(caminho).get("/exercicios").get_data(as_text=True)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_arquivos_estaticos_sao_servidos(cliente):
    assert cliente.get("/static/exercicios.js").status_code == 200
    assert cliente.get("/static/estilo.css").status_code == 200


def test_pagina_nao_usa_script_nem_estilo_embutido(cliente):
    # A política de segurança (CSP) proíbe isso; se aparecer, a página quebraria.
    html = cliente.get("/exercicios").get_data(as_text=True)

    assert "style=" not in html
    assert "<style" not in html
    assert "onclick=" not in html
    assert not re.search(r"<script(?![^>]*\bsrc=)", html)  # todo <script> tem src=


def test_pagina_nao_carrega_nada_de_outros_sites(cliente):
    html = cliente.get("/exercicios").get_data(as_text=True)

    assert "http://" not in html
    assert "https://" not in html


# ------------------------------------------------------------------ tela de montar treino


@pytest.fixture
def cliente_com_alunos(tmp_path):
    caminho = tmp_path / "alunos.db"
    _criar_banco(
        caminho,
        exercicios=[("Supino reto com barra", ["Peito"])],
        alunos=["MARIA DE TESTE", "<b>JOAO</b> & CIA"],
    )
    return _cliente_autorizado(caminho)


def test_montar_mostra_o_aluno_a_lista_de_exercicios_e_os_scripts(cliente_com_alunos):
    resposta = cliente_com_alunos.get("/alunos/1/montar")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "MARIA DE TESTE" in html
    assert 'data-aluno="1"' in html
    assert "Lançar treino" in html  # o mesmo nome do botão no Data4U
    assert "Lista de exercícios" in html
    assert "data-biblioteca" in html  # a mesma lista da página /exercicios
    assert 'type="module" src="/static/montar.js"' in html
    assert 'id="salvar"' in html and "Salvar treino" in html
    assert 'id="cancelar"' in html


def test_montar_escapa_o_nome_do_aluno(cliente_com_alunos):
    html = cliente_com_alunos.get("/alunos/2/montar").get_data(as_text=True)

    assert "<b>JOAO</b>" not in html
    assert "&lt;b&gt;JOAO&lt;/b&gt; &amp; CIA" in html


@pytest.mark.parametrize("caminho", ["/alunos/999/montar", "/alunos/0/montar", "/alunos/abc/montar", "/alunos/-1/montar"])
def test_montar_aluno_que_nao_existe_ou_id_invalido_devolve_404(cliente_com_alunos, caminho):
    assert cliente_com_alunos.get(caminho).status_code == 404


def test_montar_nao_tem_script_nem_estilo_embutido_nem_recurso_externo(cliente_com_alunos):
    html = cliente_com_alunos.get("/alunos/1/montar").get_data(as_text=True)

    assert not re.search(r"<script(?![^>]*\bsrc=)", html)
    assert "<style" not in html and "style=" not in html
    assert "http://" not in html and "https://" not in html


def test_montar_tem_nome_do_treino_e_professor_no_alto_com_os_limites_certos(cliente_com_alunos):
    html = cliente_com_alunos.get("/alunos/1/montar").get_data(as_text=True)

    # o painel de "treino salvo" começa escondido; a antiga segunda tela de salvar não existe mais
    assert re.search(r'<section[^>]*id="treino-salvo"[^>]*\bhidden\b', html)
    assert 'id="painel-salvar"' not in html
    # "Professor" é obrigatório e limitado a 60; o nome do treino a 40 (limite do Data4U)
    assert re.search(r'<label for="quem-montou">Professor', html)
    assert "(obrigatório)" in html
    assert re.search(r'<input[^>]*id="quem-montou"[^>]*maxlength="60"', html)
    assert re.search(r'<input[^>]*id="quem-montou"[^>]*aria-required="true"', html)
    assert re.search(r'<input[^>]*id="nome-treino"[^>]*maxlength="40"', html)
    # o campo do professor NÃO vem preenchido (cada professor digita o seu nome)
    assert not re.search(r'<input[^>]*id="quem-montou"[^>]*\bvalue=', html)
    # nome e professor ficam ANTES das fichas e da lista de exercícios, dentro da área de montagem
    assert html.index('id="area-montagem"') < html.index('id="nome-treino"') < html.index('id="quem-montou"') < html.index('id="abas"')
    for id_ in ("salvar", "cancelar", "confirmar-descarte", "descartar", "continuar-editando", "montar-outro", "problemas", "abas", "montagem"):
        assert f'id="{id_}"' in html


def test_montar_usa_as_palavras_do_data4u(cliente_com_alunos):
    html = cliente_com_alunos.get("/alunos/1/montar").get_data(as_text=True)

    # a lista de exercícios mostra os grupos recolhidos em "Parte do corpo", como o filtro do Data4U
    assert "data-filtro-grupos" in html and "Parte do corpo:" in html
    # a página de consulta de exercícios continua com os grupos sempre à vista
    consulta = cliente_com_alunos.get("/exercicios").get_data(as_text=True)
    assert "data-filtro-grupos" not in consulta and "data-grupos" in consulta


def test_scripts_nao_usam_funcoes_que_interpretam_html_ou_codigo():
    # Texto do banco e do teclado só entra na tela por textContent. Estas funções
    # transformariam texto em HTML/código e abririam a porta para XSS.
    pasta = Path(__file__).resolve().parent.parent / "app" / "static"
    proibidos = re.compile(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\(|new Function\(")
    for js in pasta.glob("*.js"):
        codigo = js.read_text(encoding="utf-8")
        codigo = re.sub(r"/\*.*?\*/", "", codigo, flags=re.DOTALL)  # comentários podem citar essas funções
        codigo = re.sub(r"//.*", "", codigo)
        achado = proibidos.search(codigo)
        assert achado is None, f"{js.name} usa {achado.group(0)}"


@pytest.mark.parametrize("arquivo", ["montar.js", "salvar.js", "api.js", "alunos.js", "ficha.js", "biblioteca.js", "exercicios.js", "treino_modelo.js"])
def test_scripts_sao_servidos_como_javascript(cliente, arquivo):
    # O navegador só aceita <script type="module"> se o tipo for JavaScript.
    resposta = cliente.get(f"/static/{arquivo}")

    assert resposta.status_code == 200
    assert "javascript" in resposta.headers["Content-Type"]


def test_todo_import_dos_scripts_aponta_para_um_arquivo_que_existe():
    pasta = Path(__file__).resolve().parent.parent / "app" / "static"
    importados = 0
    for js in pasta.glob("*.js"):
        for destino in re.findall(r'from "\./([^"]+)"', js.read_text(encoding="utf-8")):
            importados += 1
            assert (pasta / destino).is_file(), f"{js.name} importa {destino}, que não existe"
    assert importados >= 3


# ------------------------------------------------------------------ salvar treino (POST)


@pytest.fixture
def banco_treinos(tmp_path):
    caminho = tmp_path / "treinos.db"
    _criar_banco(
        caminho,
        exercicios=[("Supino reto", ["Peito"]), ("Remada curvada", ["Costas"])],
        alunos=["MARIA DE TESTE"],
    )
    return caminho


@pytest.fixture
def cliente_treinos(banco_treinos):
    return _cliente_autorizado(banco_treinos)


def _pedido_web(**mudancas):
    pedido = {
        "nome_treino": "TREINO AB",
        "montado_por": "Ana Paula",
        "fichas": [
            {"nome": "TREINO A", "itens": [{"exercicio_id": 1, "series": "3", "repeticoes": "12", "carga": "20", "bloco": None}]},
            {"nome": "TREINO B", "itens": [{"exercicio_id": 2, "series": "4", "repeticoes": "10", "carga": "", "bloco": None}]},
        ],
    }
    pedido.update(mudancas)
    return pedido


def _contar(banco, tabela):
    conn = conectar(banco)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
    finally:
        conn.close()


def test_salvar_treino_devolve_201_e_grava_com_quem_montou(cliente_treinos, banco_treinos):
    resposta = cliente_treinos.post("/api/alunos/1/treinos", json=_pedido_web())

    assert resposta.status_code == 201
    assert resposta.get_json() == {"id": 1}
    conn = conectar(banco_treinos)
    linha = conn.execute("SELECT aluno_id, nome, montado_por FROM treino").fetchone()
    conn.close()
    assert tuple(linha) == (1, "TREINO AB", "Ana Paula")
    assert _contar(banco_treinos, "ficha") == 2
    assert _contar(banco_treinos, "ficha_item") == 2


def test_salvar_sem_quem_montou_devolve_400_com_lista_de_erros_e_nao_grava(cliente_treinos, banco_treinos):
    resposta = cliente_treinos.post("/api/alunos/1/treinos", json=_pedido_web(montado_por="  "))

    assert resposta.status_code == 400
    assert any("quem montou" in e for e in resposta.get_json()["erros"])
    assert _contar(banco_treinos, "treino") == 0


def test_salvar_aluno_que_nao_existe_devolve_404_em_json(cliente_treinos):
    resposta = cliente_treinos.post("/api/alunos/999/treinos", json=_pedido_web())

    assert resposta.status_code == 404
    assert "erro" in resposta.get_json()


def test_salvar_nome_repetido_devolve_409(cliente_treinos, banco_treinos):
    cliente_treinos.post("/api/alunos/1/treinos", json=_pedido_web())

    resposta = cliente_treinos.post("/api/alunos/1/treinos", json=_pedido_web(nome_treino="treino ab"))

    assert resposta.status_code == 409
    assert "já tem um treino" in resposta.get_json()["erros"][0]
    assert _contar(banco_treinos, "treino") == 1


def test_salvar_sem_ser_json_devolve_415_e_nao_grava(cliente_treinos, banco_treinos):
    # É assim que um formulário de outro site chegaria: tipo "form", não JSON.
    resposta = cliente_treinos.post("/api/alunos/1/treinos", data={"nome_treino": "X"})

    assert resposta.status_code == 415
    assert resposta.get_json()["erro"]
    assert _contar(banco_treinos, "treino") == 0


def test_salvar_texto_puro_com_json_dentro_tambem_devolve_415(cliente_treinos):
    # Content-Type "text/plain" é o que um site de fora consegue mandar sem pedir licença.
    resposta = cliente_treinos.post(
        "/api/alunos/1/treinos", data='{"nome_treino": "X"}', content_type="text/plain"
    )

    assert resposta.status_code == 415


@pytest.mark.parametrize("corpo", ["{nao e json", "", "[1, 2"])
def test_salvar_json_quebrado_devolve_400(cliente_treinos, corpo):
    resposta = cliente_treinos.post("/api/alunos/1/treinos", data=corpo, content_type="application/json")

    assert resposta.status_code == 400
    assert resposta.get_json()["erro"]


@pytest.mark.parametrize("corpo", ["null", "[]", '"texto"', "5"])
def test_salvar_json_que_nao_e_objeto_devolve_400(cliente_treinos, corpo):
    resposta = cliente_treinos.post("/api/alunos/1/treinos", data=corpo, content_type="application/json")

    assert resposta.status_code == 400


def test_salvar_pedido_gigante_devolve_413_em_json(cliente_treinos, banco_treinos):
    enorme = _pedido_web(montado_por="x" * (600 * 1024))

    resposta = cliente_treinos.post("/api/alunos/1/treinos", json=enorme)

    assert resposta.status_code == 413
    assert resposta.get_json()["erro"]
    assert _contar(banco_treinos, "treino") == 0


@pytest.mark.parametrize("caminho", ["/api/alunos/abc/treinos", "/api/alunos/-1/treinos", "/api/alunos/1.5/treinos"])
def test_salvar_com_id_de_aluno_invalido_devolve_404(cliente_treinos, caminho):
    assert cliente_treinos.post(caminho, json=_pedido_web()).status_code == 404


def test_a_rota_de_salvar_so_aceita_post(cliente_treinos):
    assert cliente_treinos.get("/api/alunos/1/treinos").status_code == 405
    assert cliente_treinos.put("/api/alunos/1/treinos", json=_pedido_web()).status_code == 405
    assert cliente_treinos.delete("/api/alunos/1/treinos").status_code == 405


@pytest.mark.parametrize("pedido", [{}, {"nome_treino": 5}, {"fichas": "x"}])
def test_salvar_pedido_malformado_nunca_vira_erro_500(cliente_treinos, pedido):
    resposta = cliente_treinos.post("/api/alunos/1/treinos", json=pedido)

    assert resposta.status_code == 400


def test_resposta_de_salvar_nao_fica_em_cache(cliente_treinos):
    assert cliente_treinos.post("/api/alunos/1/treinos", json=_pedido_web()).headers["Cache-Control"] == "no-store"


def test_texto_com_html_e_guardado_como_texto(cliente_treinos, banco_treinos):
    cliente_treinos.post("/api/alunos/1/treinos", json=_pedido_web(montado_por="<script>alert(1)</script>"))

    conn = conectar(banco_treinos)
    guardado = conn.execute("SELECT montado_por FROM treino").fetchone()[0]
    conn.close()
    assert guardado == "<script>alert(1)</script>"  # o escape acontece na hora de MOSTRAR (textContent)


def test_app_recusa_subir_com_banco_de_versao_antiga(tmp_path):
    caminho = tmp_path / "velho.db"
    _criar_banco(caminho)
    conn = conectar(caminho)
    conn.execute("PRAGMA user_version = 1")
    conn.close()

    from app.db import BancoDesatualizado

    with pytest.raises(BancoDesatualizado, match="versão 1"):
        criar_app(caminho)


# ------------------------------------------------------------------ buscar aluno e ficha


@pytest.fixture
def banco_alunos(tmp_path):
    caminho = tmp_path / "busca.db"
    _criar_banco(
        caminho,
        exercicios=[("Supino reto", ["Peito"]), ("Remada curvada", ["Costas"]), ("Crucifixo", ["Peito"])],
        alunos=["MARIA DA SILVA", "JOÃO PEDRO LIMA", "<b>JOAO</b> & CIA"],
    )
    conn = conectar(caminho)
    conn.execute("UPDATE aluno SET whatsapp = '27988887766', data4u_id = 4412, situacao = 'A' WHERE id = 1")
    conn.execute("UPDATE aluno SET provisorio = 1 WHERE id = 2")
    conn.execute("UPDATE aluno SET cpf = NULL, data4u_id = 5022, situacao = 'D' WHERE id = 3")  # sem CPF no Data4U
    conn.commit()
    conn.close()
    return caminho


@pytest.fixture
def cliente_busca(banco_alunos):
    return _cliente_autorizado(banco_alunos)


def _salvar_treino_de_teste(cliente, aluno_id=1, nome="TREINO AB 07/10/26", montado_por="Ana Paula"):
    pedido = _pedido_web(nome_treino=nome, montado_por=montado_por)
    pedido["fichas"][0]["itens"].append({"exercicio_id": 3, "series": "3", "repeticoes": "12", "carga": "", "bloco": None})
    pedido["fichas"][0]["itens"][0]["bloco"] = 1
    pedido["fichas"][0]["itens"][1]["bloco"] = 1
    resposta = cliente.post(f"/api/alunos/{aluno_id}/treinos", json=pedido)
    assert resposta.status_code == 201
    return resposta.get_json()["id"]


def test_raiz_leva_para_a_busca_de_alunos(cliente_busca):
    resposta = cliente_busca.get("/")

    assert resposta.status_code == 302
    assert resposta.headers["Location"].endswith("/alunos")


def test_pagina_de_busca_tem_o_campo_e_o_script(cliente_busca):
    html = cliente_busca.get("/alunos").get_data(as_text=True)

    assert "Buscar aluno" in html
    assert re.search(r'<input[^>]*id="busca-aluno"[^>]*maxlength="100"', html)
    assert 'type="module" src="/static/alunos.js"' in html
    assert 'id="lista-alunos"' in html


def test_busca_api_por_nome_e_por_cpf(cliente_busca):
    por_nome = cliente_busca.get("/api/alunos", query_string={"q": "joao pedro"}).get_json()
    por_cpf = cliente_busca.get("/api/alunos", query_string={"q": "000.000.000-01"}).get_json()

    assert [a["nome"] for a in por_nome["alunos"]] == ["JOÃO PEDRO LIMA"]
    assert [a["nome"] for a in por_cpf["alunos"]] == ["MARIA DA SILVA"]


def test_busca_api_sem_texto_lista_todos_e_nao_expoe_cpf(cliente_busca):
    dados = cliente_busca.get("/api/alunos").get_json()

    assert dados["total"] == 3
    chaves = {"id", "nome", "provisorio", "matricula", "situacao", "situacao_nome", "ultimo_treino", "atualizado_em"}
    assert all(set(a) == chaves for a in dados["alunos"])
    assert "00000000001" not in cliente_busca.get("/api/alunos").get_data(as_text=True)


def test_busca_api_mostra_ultimo_treino(cliente_busca):
    _salvar_treino_de_teste(cliente_busca, aluno_id=1)

    maria = cliente_busca.get("/api/alunos", query_string={"q": "maria"}).get_json()["alunos"][0]

    assert maria["ultimo_treino"] == "TREINO AB 07/10/26"
    assert re.fullmatch(r"\d\d/\d\d/\d{4}", maria["atualizado_em"])


def test_busca_api_limite_invalido_devolve_400_e_nao_fica_em_cache(cliente_busca):
    resposta = cliente_busca.get("/api/alunos", query_string={"limite": "abc"})

    assert resposta.status_code == 400
    assert resposta.headers["Cache-Control"] == "no-store"
    assert cliente_busca.get("/api/alunos").headers["Cache-Control"] == "no-store"


def test_api_de_alunos_so_aceita_get_e_post(cliente_busca):
    # GET busca; POST cadastra aluno provisório (testes em tests/test_provisorios_web.py)
    assert cliente_busca.put("/api/alunos", json={}).status_code == 405
    assert cliente_busca.delete("/api/alunos").status_code == 405
    assert cliente_busca.patch("/api/alunos", json={}).status_code == 405


def test_ficha_mostra_dados_do_aluno(cliente_busca):
    resposta = cliente_busca.get("/alunos/1")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "MARIA DA SILVA" in html
    assert "000.000.000-01" in html  # CPF formatado
    assert 'value="(27) 98888-7766"' in html
    assert "Matrícula 4412" in html  # no alto da ficha
    assert "<dt>Matrícula</dt><dd>4412</dd>" in html  # e no cadastro
    assert re.search(r'class="selo-situacao situacao-A">Ativo<', html)
    assert "Provisório" not in html
    assert 'href="/alunos/1/montar"' in html
    assert 'href="/alunos"' in html  # voltar à busca
    assert 'type="module" src="/static/ficha.js"' in html


def test_busca_api_por_matricula(cliente_busca):
    achados = cliente_busca.get("/api/alunos", query_string={"q": "4412"}).get_json()["alunos"]

    assert [(a["nome"], a["matricula"], a["situacao_nome"]) for a in achados] == [("MARIA DA SILVA", 4412, "Ativo")]


def test_ficha_de_pessoa_sem_cpf_abre_e_explica(cliente_busca):
    resposta = cliente_busca.get("/alunos/3")
    html = resposta.get_data(as_text=True)

    assert resposta.status_code == 200
    assert "<dt>CPF</dt><dd>Não cadastrado</dd>" in html
    assert "não tem o CPF desta pessoa" in html
    assert "<b>JOAO</b>" not in html  # o nome com HTML sai como texto
    assert "&lt;b&gt;JOAO&lt;/b&gt;" in html
    assert re.search(r'class="selo-situacao situacao-D">Desistente<', html)


def test_ficha_provisoria_mostra_provisorio_e_nao_a_situacao(cliente_busca):
    html = cliente_busca.get("/alunos/2").get_data(as_text=True)

    assert "Provisório" in html
    assert "situacao-" not in html


def test_ficha_sem_treino_mostra_orientacao(cliente_busca):
    html = cliente_busca.get("/alunos/1").get_data(as_text=True)

    assert "ainda não tem treino" in html
    assert "Lançar treino" in html  # o botão tem o mesmo nome do Data4U
    assert 'class="titulos-treinos"' not in html  # sem treino, não há tabela


def test_ficha_de_provisorio_mostra_o_selo(cliente_busca):
    html = cliente_busca.get("/alunos/2").get_data(as_text=True)

    assert "Provisório" in html
    assert 'value=""' in html  # sem WhatsApp cadastrado


def test_ficha_lista_o_treino_salvo_com_quem_montou_e_os_exercicios(cliente_busca):
    _salvar_treino_de_teste(cliente_busca, montado_por="Ana Paula")

    html = cliente_busca.get("/alunos/1").get_data(as_text=True)

    assert "TREINO AB 07/10/26" in html
    assert 'class="treino-professor">Ana Paula<' in html  # coluna "Professor" da tabela de treinos
    assert "TREINO A" in html and "TREINO B" in html
    assert "2 exercícios, 1 bi-set" in html  # ficha A: supino + crucifixo em bi-set
    assert "1 exercício<" in html  # ficha B: só a remada
    assert "Supino reto" in html and "Remada curvada" in html and "Crucifixo" in html
    assert "3 × 12 · 20" in html  # séries × repetições · carga
    assert "A1" in html and "A2" in html
    assert "ainda não tem treino" not in html


def test_ficha_escapa_nome_do_aluno_e_de_quem_montou(cliente_busca):
    _salvar_treino_de_teste(cliente_busca, aluno_id=3, montado_por="<script>alert(1)</script>")

    html = cliente_busca.get("/alunos/3").get_data(as_text=True)

    assert "<b>JOAO</b>" not in html and "&lt;b&gt;JOAO&lt;/b&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


@pytest.mark.parametrize("caminho", ["/alunos/999", "/alunos/0", "/alunos/abc", "/alunos/-1"])
def test_ficha_de_aluno_que_nao_existe_devolve_404(cliente_busca, caminho):
    assert cliente_busca.get(caminho).status_code == 404


@pytest.mark.parametrize("caminho", ["/alunos", "/alunos/1", "/alunos/1/montar", "/exercicios"])
def test_telas_do_professor_tem_o_topo_com_link_para_alunos(cliente_busca, caminho):
    html = cliente_busca.get(caminho).get_data(as_text=True)

    assert 'href="/alunos"' in html
    # O topo mostra o nome que o computador recebeu ao ser autorizado.
    assert '<div class="topo-nota">Computador de teste</div>' in html


def test_telas_novas_nao_tem_script_estilo_embutido_nem_recurso_externo(cliente_busca):
    for caminho in ("/alunos", "/alunos/1", "/alunos/1/montar"):
        html = cliente_busca.get(caminho).get_data(as_text=True)
        assert not re.search(r"<script(?![^>]*\bsrc=)", html), caminho
        assert "<style" not in html and "style=" not in html, caminho
        assert "onclick=" not in html, caminho
        assert "http://" not in html and "https://" not in html, caminho


def test_montar_tem_link_de_volta_para_a_ficha_e_para_ver_a_ficha_depois_de_salvar(cliente_busca):
    html = cliente_busca.get("/alunos/1/montar").get_data(as_text=True)

    assert re.search(r'<a class="voltar" href="/alunos/1">', html)
    assert re.search(r'<a id="ver-ficha"[^>]*href="/alunos/1"', html)


# ---- corrigir WhatsApp


def test_corrigir_whatsapp_grava_e_devolve_formatado(cliente_busca, banco_alunos):
    resposta = cliente_busca.post("/api/alunos/2/whatsapp", json={"whatsapp": "27 9 9999-0000"})

    assert resposta.status_code == 200
    assert resposta.get_json() == {"whatsapp": "(27) 99999-0000"}
    conn = conectar(banco_alunos)
    linha = conn.execute("SELECT whatsapp, whatsapp_corrigido_no_app FROM aluno WHERE id = 2").fetchone()
    conn.close()
    assert tuple(linha) == ("27999990000", 1)
    assert 'value="(27) 99999-0000"' in cliente_busca.get("/alunos/2").get_data(as_text=True)


@pytest.mark.parametrize("valor", ["123", "", "abc", "98888-7766", "+55 27 98888-7766", None, 27988887766])
def test_corrigir_whatsapp_invalido_devolve_400_e_nao_grava(cliente_busca, banco_alunos, valor):
    resposta = cliente_busca.post("/api/alunos/1/whatsapp", json={"whatsapp": valor})

    assert resposta.status_code == 400
    assert resposta.get_json()["erro"]
    conn = conectar(banco_alunos)
    linha = conn.execute("SELECT whatsapp, whatsapp_corrigido_no_app FROM aluno WHERE id = 1").fetchone()
    conn.close()
    assert tuple(linha) == ("27988887766", 0)


def test_corrigir_whatsapp_sem_o_campo_devolve_400(cliente_busca):
    assert cliente_busca.post("/api/alunos/1/whatsapp", json={}).status_code == 400


def test_corrigir_whatsapp_com_json_que_nao_e_objeto_devolve_400(cliente_busca):
    resposta = cliente_busca.post("/api/alunos/1/whatsapp", data="[1]", content_type="application/json")

    assert resposta.status_code == 400


def test_corrigir_whatsapp_de_aluno_que_nao_existe_devolve_404(cliente_busca):
    assert cliente_busca.post("/api/alunos/999/whatsapp", json={"whatsapp": "27988887766"}).status_code == 404


def test_corrigir_whatsapp_exige_json(cliente_busca, banco_alunos):
    resposta = cliente_busca.post("/api/alunos/1/whatsapp", data={"whatsapp": "27911112222"})

    assert resposta.status_code == 415
    conn = conectar(banco_alunos)
    assert conn.execute("SELECT whatsapp FROM aluno WHERE id = 1").fetchone()[0] == "27988887766"
    conn.close()


def test_corrigir_whatsapp_so_aceita_post_e_nao_fica_em_cache(cliente_busca):
    assert cliente_busca.get("/api/alunos/1/whatsapp").status_code == 405
    assert cliente_busca.put("/api/alunos/1/whatsapp", json={"whatsapp": "27988887766"}).status_code == 405
    resposta = cliente_busca.post("/api/alunos/1/whatsapp", json={"whatsapp": "27988887766"})
    assert resposta.headers["Cache-Control"] == "no-store"


# ------------------------------------------------------------------ cabeçalhos de segurança


@pytest.mark.parametrize("caminho", ["/exercicios", "/api/grupos", "/saude", "/nao-existe", "/alunos", "/alunos/1", "/api/alunos"])
def test_cabecalhos_de_seguranca_em_todas_as_respostas(cliente, caminho):
    cabecalhos = cliente.get(caminho).headers

    assert cabecalhos["X-Content-Type-Options"] == "nosniff"
    assert cabecalhos["X-Frame-Options"] == "DENY"
    assert cabecalhos["Referrer-Policy"] == "same-origin"
    assert "default-src 'self'" in cabecalhos["Content-Security-Policy"]


def test_respostas_da_api_nao_ficam_guardadas_em_cache(cliente):
    assert cliente.get("/api/exercicios").headers["Cache-Control"] == "no-store"
    assert cliente.get("/api/exercicios", query_string={"limite": "x"}).headers["Cache-Control"] == "no-store"


# ------------------------------------------------------------------ com os dados reais


@pytest.fixture(scope="module")
def cliente_real(tmp_path_factory):
    caminho = tmp_path_factory.mktemp("real") / "real.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    importar_quadro(conn, QUADRO_REAL)
    conn.close()
    return _cliente_autorizado(caminho)


def test_real_pagina_mostra_1161_exercicios_e_15_grupos(cliente_real):
    html = cliente_real.get("/exercicios").get_data(as_text=True)

    assert "Buscar entre 1.161 exercícios" in html
    assert html.count('class="grupo"') == 16  # "Todos" + 15 grupos
    assert cliente_real.get("/api/grupos").get_json()[0]["nome"] == "Peito"


def test_real_busca_supino_so_traz_nomes_com_supino(cliente_real):
    dados = cliente_real.get("/api/exercicios", query_string={"q": "supino", "limite": 200}).get_json()

    assert dados["total"] > 0
    assert all("supino" in e["nome"].lower() for e in dados["exercicios"])


def test_real_filtro_peito_so_traz_exercicios_do_peito(cliente_real):
    peito = next(g for g in cliente_real.get("/api/grupos").get_json() if g["nome"] == "Peito")

    dados = cliente_real.get("/api/exercicios", query_string={"grupo": peito["id"], "limite": 200}).get_json()

    assert dados["total"] == peito["quantidade"]
    assert all("Peito" in e["grupos"] for e in dados["exercicios"])
