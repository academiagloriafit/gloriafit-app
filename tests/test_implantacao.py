"""Guardas dos arquivos de implantação (Dockerfile, entrypoint, .dockerignore).

Não dá para construir a imagem aqui, então estes testes só travam o que já deu para conferir
a olho e que seria grave perder numa edição futura: rodar sem ser administrador, não levar
banco/segredo/dado de aluno para dentro da imagem e não gravar CPF digitado nos registros.
"""

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DOCKERFILE = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
ENTRADA = (RAIZ / "deploy" / "entrypoint.sh").read_text(encoding="utf-8")
IGNORADOS = {l.strip() for l in (RAIZ / ".dockerignore").read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")}


def test_o_contêiner_nao_roda_como_administrador():
    usuarios = re.findall(r"^USER\s+(\S+)", DOCKERFILE, re.M)

    assert usuarios and usuarios[-1] != "root"
    assert DOCKERFILE.index("useradd") < DOCKERFILE.index("USER " + usuarios[-1])  # o usuário existe antes de ser usado


def test_a_imagem_copia_so_o_necessario_e_nao_a_pasta_inteira():
    copias = re.findall(r"^COPY\s+(.+)$", DOCKERFILE, re.M)

    assert not any(c.split()[0] in (".", "./", "*") for c in copias)
    origens = {c.split()[0] for c in copias}
    assert {"app", "dados"} <= origens


def test_banco_segredo_e_copia_do_data4u_nao_entram_na_imagem():
    for padrao in ("*.db", "*.db-wal", ".env", "*.zip", ".git", "tests"):
        assert padrao in IGNORADOS, padrao


def test_registro_de_acessos_nao_grava_o_texto_depois_do_ponto_de_interrogacao():
    # A busca manda o que o professor digitou (pode ser um CPF) na parte depois do "?".
    formato = re.search(r"--access-logformat\s+'([^']+)'", ENTRADA).group(1)

    assert "%(U)s" in formato  # só o caminho
    for com_texto_da_busca in ("%(r)s", "%(q)s", "%(R)s", "%({"):
        assert com_texto_da_busca not in formato
    assert "--access-logfile -" in ENTRADA


def test_o_servidor_e_chamado_pela_fabrica_de_apps_que_existe():
    from app.web import criar_app  # o nome usado no entrypoint precisa existir

    assert '"app.web:criar_app()"' in ENTRADA and callable(criar_app)


def test_o_proxy_so_e_ligado_no_contêiner_e_nao_por_padrao_no_app():
    assert "GLORIAFIT_ATRAS_DE_PROXY=1" in DOCKERFILE
    web = (RAIZ / "app" / "web.py").read_text(encoding="utf-8")
    assert 'os.environ.get("GLORIAFIT_ATRAS_DE_PROXY") == "1"' in web


def test_a_porta_do_contêiner_nao_e_publicada_direto_so_exposta():
    # Quem publica a porta (e deixa o app acessível sem o proxy) invalida a confiança nos cabeçalhos X-Forwarded.
    assert re.search(r"^EXPOSE\s+8000", DOCKERFILE, re.M)
    assert "-p " not in DOCKERFILE and "ports:" not in DOCKERFILE


# ------------------------------------------------------------------ docker-compose (servidor)

import yaml  # noqa: E402

COMPOSE = yaml.safe_load((RAIZ / "deploy" / "docker-compose.yml").read_text(encoding="utf-8"))
SERVICO = COMPOSE["services"]["app"]
ROTULOS = dict(r.split("=", 1) for r in SERVICO["labels"] if "=" in r)


def test_compose_nao_abre_porta_no_servidor():
    # Sem "ports", só o Traefik alcança o app; com porta aberta, qualquer um poderia
    # falar direto com ele e mentir o endereço/https (GLORIAFIT_ATRAS_DE_PROXY=1).
    assert "ports" not in SERVICO
    assert "network_mode" not in SERVICO


def test_compose_endereco_e_o_mesmo_no_app_e_no_traefik():
    dominio = SERVICO["environment"]["GLORIAFIT_DOMINIO"]

    assert dominio == "app.gloriafit.com.br"
    assert ROTULOS["traefik.http.routers.gloriafitapp.rule"] == f"Host(`{dominio}`)"
    assert str(SERVICO["environment"]["GLORIAFIT_ATRAS_DE_PROXY"]) == "1"


def test_compose_segue_o_jeito_do_traefik_do_servidor():
    # Valores lidos do Traefik real (painel da Hostinger, 07/10/2026).
    assert ROTULOS["traefik.enable"] == "true"
    assert ROTULOS["traefik.http.routers.gloriafitapp.entrypoints"] == "websecure"
    assert ROTULOS["traefik.http.routers.gloriafitapp.tls.certresolver"] == "letsencrypt"
    assert ROTULOS["traefik.http.services.gloriafitapp.loadbalancer.server.port"] == "8000"


def test_compose_nome_do_roteador_nao_colide_com_os_do_site():
    nomes = {k.split(".")[3] for k in ROTULOS if k.startswith("traefik.http.routers.")}

    assert nomes == {"gloriafitapp"}
    assert not nomes & {"gloriafit", "gloriafit-web", "gloriafit-www", "gloriafit-raiz", "gloriafit-painel"}


def test_compose_guarda_banco_e_copias_em_volumes_que_sobrevivem_a_atualizacao():
    assert set(SERVICO["volumes"]) == {"app-dados:/dados", "app-backups:/backups"}
    assert set(COMPOSE["volumes"]) == {"app-dados", "app-backups"}
    assert SERVICO["restart"] == "unless-stopped"


def test_compose_nao_tem_senha_nem_token_escritos():
    texto = (RAIZ / "deploy" / "docker-compose.yml").read_text(encoding="utf-8").lower()

    assert not re.search(r"token|senha|password|secret|x-access-token", texto)


def test_compose_usa_imagem_pronta_do_ghcr_com_commit_fixo_e_nao_constroi_no_servidor():
    # O servidor tem 1 vCPU e metade da memória em uso: quem constrói é o GitHub.
    assert "build" not in SERVICO
    repositorio, _, etiqueta = SERVICO["image"].rpartition(":")

    assert repositorio == "ghcr.io/academiagloriafit/gloriafit-app"
    assert etiqueta != "latest" and etiqueta  # "latest" mudaria sozinho num reinício


# ------------------------------------------------------------------ verificação de saúde do contêiner

import importlib.util  # noqa: E402


def _carregar_healthcheck():
    caminho = RAIZ / "deploy" / "healthcheck.py"
    especificacao = importlib.util.spec_from_file_location("healthcheck_do_conteiner", caminho)
    modulo = importlib.util.module_from_spec(especificacao)
    especificacao.loader.exec_module(modulo)
    return modulo


def test_healthcheck_leva_o_endereco_do_app_no_host(monkeypatch):
    # Lição de 07/10/2026: com o Host "127.0.0.1:8000" o app recusava a própria verificação (400),
    # o Docker marcava o contêiner como doente e o Traefik o ignorava (site fora do ar).
    pedido = _carregar_healthcheck().montar_pedido({"GLORIAFIT_DOMINIO": "app.gloriafit.com.br"})

    assert pedido.full_url == "http://127.0.0.1:8000/saude"
    assert pedido.get_header("Host") == "app.gloriafit.com.br"


def test_healthcheck_sem_dominio_configurado_usa_o_endereco_local():
    pedido = _carregar_healthcheck().montar_pedido({})

    assert pedido.get_header("Host") == "127.0.0.1:8000"


def test_o_app_aceita_o_pedido_que_o_healthcheck_monta(tmp_path, monkeypatch):
    # Mesmas variáveis do compose de produção: domínio fixo + atrás do proxy.
    from app.db import conectar, criar_tabelas
    from app.web import criar_app

    monkeypatch.setenv("GLORIAFIT_DOMINIO", SERVICO["environment"]["GLORIAFIT_DOMINIO"])
    monkeypatch.setenv("GLORIAFIT_ATRAS_DE_PROXY", "1")
    caminho = tmp_path / "saude.db"
    conn = conectar(caminho)
    criar_tabelas(conn)
    conn.close()
    pedido = _carregar_healthcheck().montar_pedido({"GLORIAFIT_DOMINIO": SERVICO["environment"]["GLORIAFIT_DOMINIO"]})

    resposta = criar_app(caminho).test_client().get("/saude", headers={"Host": pedido.get_header("Host")})

    assert resposta.status_code == 200


def test_dockerfile_copia_e_usa_o_healthcheck_e_ele_nao_e_ignorado():
    assert re.search(r"^COPY\s+deploy/healthcheck\.py\s+\./healthcheck\.py", DOCKERFILE, re.M)
    assert re.search(r"^HEALTHCHECK\b.*\\\n\s+CMD \[\"python\", \"healthcheck\.py\"\]", DOCKERFILE, re.M)
    assert not any(p in IGNORADOS for p in ("deploy", "deploy/healthcheck.py", "*.py"))
