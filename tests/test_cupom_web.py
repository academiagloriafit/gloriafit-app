"""Tela de impressão do cupom (app/web.py + templates/imprimir.html). Dados inventados."""

import re
from pathlib import Path

import pytest

from app import acesso, treinos
from app.db import conectar, criar_tabelas
from app.web import criar_app

PASTA_ESTATICA = Path(__file__).resolve().parent.parent / "app" / "static"


@pytest.fixture
def caminho(tmp_path):
    caminho = tmp_path / "cupom.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.execute("INSERT INTO aluno (nome, cpf) VALUES ('MARIANA COSTA', '52998224725')")
    conn.execute("INSERT INTO aluno (nome, cpf) VALUES ('<b>ALUNO NEGRITO</b>', '11144477735')")
    for nome in ("SUPINO RETO COM BARRA", "CRUCIFIXO COM HALTERES", "TRICEPS <i>TESTA</i>"):
        conn.execute("INSERT INTO exercicio (nome, origem) VALUES (?, 'app')", (nome,))
    conn.commit()
    itens = [
        {"exercicio_id": 1, "series": "4", "repeticoes": "12", "carga": "30 KG", "bloco": 1},
        {"exercicio_id": 2, "series": "4", "repeticoes": "12", "carga": "10 KG", "bloco": 1},
        {"exercicio_id": 3, "series": "3", "repeticoes": "12", "carga": None, "bloco": None},
    ]
    treinos.salvar_treino(conn, 1, {"nome_treino": "TREINO ABC", "montado_por": "Ana", "fichas": [{"nome": "TREINO A", "itens": itens}]})
    treinos.salvar_treino(conn, 2, {"nome_treino": "<script>x</script>", "montado_por": "Ana", "fichas": [{"nome": "<u>F</u>", "itens": itens}]})
    conn.close()
    return caminho


def _autorizar(navegador, caminho):
    conn = conectar(caminho)
    codigo = acesso.gerar_codigo(conn, "Computador de teste").codigo
    token = acesso.autorizar(conn, codigo).token
    conn.close()
    navegador.set_cookie(acesso.NOME_DO_COOKIE, token)


@pytest.fixture
def cliente(caminho):
    navegador = criar_app(caminho).test_client()
    _autorizar(navegador, caminho)
    return navegador


def _pagina(cliente, treino_id=1):
    resposta = cliente.get(f"/treinos/{treino_id}/imprimir")
    assert resposta.status_code == 200
    return resposta.get_data(as_text=True)


def test_mostra_o_cupom_do_desenho(cliente):
    html = _pagina(cliente)

    # (as letras viram maiúsculas na tela e no papel pelo estilo; no HTML ficam como foram digitadas)
    # O cabeçalho leva só o nome da ficha que está sendo impressa ("TREINO A"), não o do treino inteiro ("TREINO ABC").
    for texto in ("Academia Glória Fit", "ALUNO: MARIANA COSTA", "TREINO: TREINO A<", "PROF.: Ana"):
        assert texto in html
    assert "TREINO ABC" not in html
    assert "SUPINO RETO COM BARRA" in html
    assert "BI-SET: FAÇA A1 E A2 SEGUIDOS" in html
    assert "4 X 12" in html and "30 KG" in html
    assert 'id="botao-imprimir"' in html
    assert "imprimir.css" in html and "imprimir.js" in html


def test_tem_o_botao_voltar_para_a_ficha_do_aluno_certo(cliente):
    assert 'class="botao-link botao-link-grande" href="/alunos/1"' in _pagina(cliente, 1)
    assert 'class="botao-link botao-link-grande" href="/alunos/2"' in _pagina(cliente, 2)


def test_nao_fala_do_app_do_aluno_enquanto_nao_houver_endereco(cliente):
    assert "ENTRE NO APP" not in _pagina(cliente)


def test_com_endereco_configurado_o_cupom_termina_com_o_aviso(caminho, monkeypatch):
    monkeypatch.setenv("GLORIAFIT_ENDERECO_DO_APP", "treino.exemplo.com.br")
    navegador = criar_app(caminho).test_client()
    _autorizar(navegador, caminho)

    html = _pagina(navegador)

    assert "ENTRE NO APP COM O SEU CPF:" in html
    assert "treino.exemplo.com.br" in html


def test_texto_com_html_aparece_como_texto(cliente):
    html = _pagina(cliente, 2)

    assert "<b>ALUNO NEGRITO</b>" not in html and "&lt;b&gt;ALUNO NEGRITO&lt;/b&gt;" in html
    assert "<script>x</script>" not in html
    assert "<u>F</u>" not in html and "&lt;u&gt;F&lt;/u&gt;" in html
    assert "<i>TESTA</i>" not in html


def test_treino_que_nao_existe_e_404(cliente):
    assert cliente.get("/treinos/999/imprimir").status_code == 404


def test_numero_que_nao_e_inteiro_e_404(cliente):
    assert cliente.get("/treinos/abc/imprimir").status_code == 404


def test_sem_autorizacao_manda_para_autorizar_e_nao_mostra_nada(caminho):
    anonimo = criar_app(caminho).test_client()

    resposta = anonimo.get("/treinos/1/imprimir")

    assert resposta.status_code == 302 and "/autorizar" in resposta.headers["Location"]
    assert b"MARIANA" not in resposta.data


def test_a_pagina_nao_fica_em_cache(cliente):
    assert cliente.get("/treinos/1/imprimir").headers["Cache-Control"] == "no-store"


def test_so_aceita_get(cliente):
    assert cliente.post("/treinos/1/imprimir", json={}).status_code == 405


def test_a_ficha_do_aluno_tem_o_link_para_imprimir_cada_treino(cliente):
    html = cliente.get("/alunos/1").get_data(as_text=True)

    assert 'href="/treinos/1/imprimir"' in html
    assert 'href="/treinos/2/imprimir"' not in html  # o treino 2 é de outro aluno
    assert 'href="/treinos/2/imprimir"' in cliente.get("/alunos/2").get_data(as_text=True)


def test_a_tela_de_montar_tem_o_link_de_imprimir_escondido_ate_salvar(cliente):
    html = cliente.get("/alunos/1/montar").get_data(as_text=True)

    assert re.search(r'<a id="imprimir-treino"[^>]*\bhidden\b', html)


def test_a_regra_de_pagina_so_vale_para_a_tela_de_impressao():
    # @page (margem zero) afeta TODA impressão da página que carrega o arquivo: não pode vazar para o estilo geral.
    assert "@page" in (PASTA_ESTATICA / "imprimir.css").read_text(encoding="utf-8")
    assert "@page" not in (PASTA_ESTATICA / "estilo.css").read_text(encoding="utf-8")


def test_o_cupom_so_usa_preto_no_papel():
    # Impressora térmica é preta e branca: cinza some ou vira pontilhado ilegível.
    css = (PASTA_ESTATICA / "imprimir.css").read_text(encoding="utf-8")
    cupom = css[css.index("/* ------------------------------------------------------------ o cupom */") :]

    cores = set(re.findall(r"(?<![\w-])color:\s*([^;]+);", cupom))

    assert cores == {"#000"}


def test_intervalo_e_observacao_aparecem_na_tela_de_impressao_e_texto_perigoso_nao_executa(caminho):
    conn = conectar(caminho)
    treinos.salvar_treino(
        conn,
        1,
        {
            "nome_treino": "TREINO COM DETALHE",
            "montado_por": "Ana",
            "fichas": [
                {
                    "nome": "TREINO A",
                    "itens": [
                        {"exercicio_id": 1, "series": "4", "repeticoes": "12", "carga": None, "bloco": None,
                         "pausa": 75, "observacao": "<b>devagar</b>"},
                    ],
                }
            ],
        },
    )
    conn.close()
    navegador = criar_app(caminho).test_client()
    _autorizar(navegador, caminho)

    html = _pagina(navegador, treino_id=3)

    assert '<div class="cupom-linha cupom-detalhe">INTERVALO: 1 MIN 15 S</div>' in html
    assert '<div class="cupom-linha cupom-detalhe">OBS: &lt;b&gt;devagar&lt;/b&gt;</div>' in html
    assert "<b>devagar</b>" not in html


def test_cupom_tem_o_simbolo_da_academia_no_topo_em_preto_e_branco(cliente):
    """Pedido do Thiago (20/10/2026): o símbolo no topo, e depois invertido (opção B: disco preto com o F branco, fora do círculo papel).
    A térmica só imprime preto: o arquivo é de 1 bit, 192 pontos."""
    import struct

    html = cliente.get("/treinos/1/imprimir").get_data(as_text=True)
    assert html.index("cupom-logo") < html.index("cupom-titulo")  # o símbolo vem antes do nome da academia
    assert "marca/logo-cupom-invertido.png" in html
    # lê cabeçalho do PNG à mão (a CI não tem Pillow): largura, altura, bits por ponto, tipo de cor
    cabecalho = (PASTA_ESTATICA / "marca" / "logo-cupom-invertido.png").read_bytes()[16:26]
    largura, altura, bits, _tipo_de_cor = struct.unpack(">IIBB", cabecalho)
    assert (largura, altura) == (192, 192)
    assert bits == 1  # 1 bit por ponto: só preto e branco, sem cinza que a térmica borraria
    assert cliente.get("/static/marca/logo-cupom-invertido.png").status_code == 200


def test_o_simbolo_do_cupom_e_o_mesmo_que_o_thiago_aprovou_na_folha_de_teste():
    """Opção B (invertido, redondo) da folha de teste = o símbolo que vai no cupom, ponto por ponto."""
    cupom = (PASTA_ESTATICA / "marca" / "logo-cupom-invertido.png").read_bytes()
    folha = (PASTA_ESTATICA / "teste_impressao" / "logo-invertido-redondo.png").read_bytes()
    assert cupom == folha


def test_css_do_cupom_pede_letra_forte_e_grande_para_a_termica():
    css = (PASTA_ESTATICA / "imprimir.css").read_text(encoding="utf-8")
    assert "-webkit-text-stroke: 0.07mm" in css  # o texto normal ganha contorno para não sair fraco
    forte = re.search(r"\.cupom-forte\s*\{([^}]*)\}", css).group(1)
    assert "font-weight: 700" in forte  # aluno, treino, ficha e nome do exercício em negrito (opção A)
    assert re.search(r"\.cupom\s*\{[^}]*font-weight: 400", css)  # o resto normal: tudo em negrito ficava preto demais
    tamanho = float(re.search(r"font-size:\s*([\d.]+)mm", css).group(1))
    assert tamanho >= 3.4  # era 2,5 mm, depois 3,1 mm: o Thiago pediu "um pouco mais" em 20/10/2026


# ------------------------------------------------------------ escolher a ficha a imprimir (20/10/2026)


@pytest.fixture
def cliente_com_duas_fichas(tmp_path):
    caminho = tmp_path / "fichas.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.execute("INSERT INTO aluno (nome, cpf) VALUES ('ANA', '52998224725')")
    conn.execute("INSERT INTO exercicio (nome, origem) VALUES ('SUPINO RETO', 'app'), ('AGACHAMENTO LIVRE', 'app')")
    conn.commit()
    itens = lambda i: [{"exercicio_id": i, "series": "3", "repeticoes": "10"}]
    treinos.salvar_treino(conn, 1, {"nome_treino": "T", "montado_por": "P", "fichas": [
        {"nome": "A PEITO", "itens": itens(1)}, {"nome": "B PERNAS", "itens": itens(2)}]})
    conn.close()
    navegador = criar_app(caminho).test_client()
    _autorizar(navegador, caminho)
    return navegador


def _cupom_html(html):
    return html[html.index('class="cupom"'):]


def test_sem_escolha_imprime_so_a_primeira_ficha_e_mostra_os_botoes(cliente_com_duas_fichas):
    html = cliente_com_duas_fichas.get("/treinos/1/imprimir").get_data(as_text=True)
    cupom = _cupom_html(html)
    assert "A PEITO" in cupom and "SUPINO RETO" in cupom
    assert "B PERNAS" not in cupom and "AGACHAMENTO" not in cupom  # não imprime o treino inteiro por padrão
    assert 'class="escolha-ficha"' in html
    assert "ficha=2" in html and "ficha=todas" in html


def test_escolher_a_ficha_b_imprime_so_a_b(cliente_com_duas_fichas):
    cupom = _cupom_html(cliente_com_duas_fichas.get("/treinos/1/imprimir?ficha=2").get_data(as_text=True))
    assert "B PERNAS" in cupom and "AGACHAMENTO LIVRE" in cupom
    assert "A PEITO" not in cupom and "SUPINO" not in cupom


def test_cabecalho_da_ficha_escolhida_leva_so_o_nome_dela_uma_vez(cliente_com_duas_fichas):
    # Pedido do Thiago em 20/10/2026: nada de listar o treino todo no cabeçalho.
    cupom = _cupom_html(cliente_com_duas_fichas.get("/treinos/1/imprimir?ficha=2").get_data(as_text=True))
    assert "TREINO: B PERNAS" in cupom
    assert "TREINO: T<" not in cupom  # o nome do treino inteiro ("T") não aparece
    assert cupom.count("B PERNAS") == 1  # e o nome da ficha não se repete embaixo


def test_todas_as_fichas_continua_possivel(cliente_com_duas_fichas):
    cupom = _cupom_html(cliente_com_duas_fichas.get("/treinos/1/imprimir?ficha=todas").get_data(as_text=True))
    assert "A PEITO" in cupom and "B PERNAS" in cupom
    assert "TREINO: T<" in cupom  # com todas as fichas o cabeçalho leva o nome do treino, como antes


@pytest.mark.parametrize("pedido", ["9", "0", "abc", "-1", "1.5", "99999", "%3Cscript%3E", "２"])
def test_ficha_invalida_na_tela_de_imprimir_da_404(cliente_com_duas_fichas, pedido):
    assert cliente_com_duas_fichas.get(f"/treinos/1/imprimir?ficha={pedido}").status_code == 404


def test_treino_de_uma_ficha_so_nao_mostra_os_botoes(cliente):
    # o treino 1 da fixture `caminho` tem uma ficha só: não há o que escolher
    assert 'class="escolha-ficha"' not in cliente.get("/treinos/1/imprimir").get_data(as_text=True)
