"""Importa os alunos da cópia diária do Data4U para o banco do app.

A cópia é o arquivo `base_total.zip` que o PC da recepção gera todo dia às 05:00:
uma pasta de tabelas em linhas de JSON (`PESSOA.jsonl`, ...) mais um `_manifesto.json`
com a data e a quantidade de linhas de cada tabela.

Uso (cria as tabelas se o banco ainda não existir):

    python -m app.importar_alunos base_total_2026-10-07.zip app.db

Regras (as decisões são do Thiago, de 07/10/2026, salvo onde dito o contrário):

- Entra no app toda pessoa física, não apagada, com ID positivo e que tenha uma
  situação no Data4U na data da cópia (ativo, trancado, pendente, desistente, inativo
  ou cancelado). Pessoa sem situação nenhuma não entra.
- A matrícula do aluno é o ID da pessoa no Data4U: vai para `aluno.data4u_id`.
- Rodar de novo atualiza quem já existe (nome, CPF, situação) e acrescenta quem é novo.
  Ninguém é apagado, porque pode ter treino. O WhatsApp só é atualizado se a recepção
  ainda não o corrigiu no app (`whatsapp_corrigido_no_app`).
- Aluno provisório (cadastrado no app no primeiro dia, ver app/provisorios.py): quando a
  pessoa aparece pela primeira vez na cópia, o importador a junta ao provisório que tem o
  MESMO CPF. A linha do provisório é a que fica (os treinos continuam nela): ela ganha a
  matrícula, a situação e o nome do Data4U e deixa de ser provisória. Só junta se for sem
  dúvida: exatamente um provisório com aquele CPF e exatamente uma pessoa do Data4U com
  aquele CPF (no Data4U há CPF em mais de uma pessoa). Na dúvida, não junta: o provisório
  continua provisório e o relatório conta quantos ficaram assim.
- Tudo ou nada: se algo der errado no meio, o banco fica como estava.
- Nada é adivinhado: CPF que não tem 11 números fica vazio; WhatsApp que não tem
  10 ou 11 números com DDD fica vazio (não se "completa" o DDD); situação que não é
  uma das seis letras conhecidas deixa a pessoa de fora. Cada um desses casos é contado
  no relatório.
"""

import argparse
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.alunos import FUSO_DA_ACADEMIA, SITUACOES, WhatsappInvalido, validar_whatsapp
from app.datas import ler_dia
from app.db import conectar, criar_tabelas

TABELAS_USADAS = ("PESSOA", "PESSOA_STATUS", "CONTATO_PESSOA")
# Colunas de que o importador depende. Se o Data4U mudar alguma, a importação para com
# uma mensagem clara em vez de falhar no meio.
COLUNAS_NECESSARIAS = {
    "PESSOA": ("ID", "NM_PESSOA", "TP_PESSOA", "NR_CPF", "ST_DELETED"),
    "PESSOA_STATUS": ("ID_PESSOA", "DT_INI_STATUS", "DT_FIM_STATUS", "CD_STATUS"),
    "CONTATO_PESSOA": ("ID_CONTATO", "ID_PESSOA", "ID_TIPO_CONTATO", "DS_CONTATO"),
}
TIPO_CONTATO_CELULAR = 30  # tabela TIPO_CONTATO do Data4U: 30 = Celular
TIPO_CONTATO_EMAIL = 100  # 100 = e-mail
# "Meu perfil" (29/10/2026): o endereço vem de PESSOA. É opcional no pacote: o PC da recepção com o programa antigo ainda manda
# só as colunas de cima, e aí o importador não mexe em e-mail nem endereço (para não apagar o que já estava).
COLUNAS_DO_ENDERECO = ("NR_CEP", "CD_UF", "DS_LOCALIDADE", "DS_BAIRRO", "DS_LOGRADOURO", "DS_COMPLEMENTO")
# E-mail e endereço só ficam guardados de quem está em uso (ativo, pendente, trancado): de ex-aluno o app não precisa (LGPD).
SITUACOES_COM_PERFIL = ("A", "P", "T")
CAMPOS_DO_PERFIL = ("email", "cep", "uf", "cidade", "bairro", "logradouro", "complemento")
# Último acesso pela catraca (29/10/2026): decide quem tem foto mesmo inativo (app/fotos.py). Tabela opcional no pacote (o programa
# antigo do PC não manda); só se guarda o dia, e só se foi nos últimos DIAS_DE_ACESSO_RECENTE dias.
TABELA_DE_ACESSOS = "ACC_PESSOA"
COLUNAS_DE_ACESSOS = ("ID_PESSOA", "DT_LAST_ACCESS")
DIAS_DE_ACESSO_RECENTE = 60
# Teto de tamanho de cada tabela lida do .zip. As maiores têm ~8 MB; o teto só impede
# que um arquivo estranho encha a memória.
TAMANHO_MAXIMO_TABELA = 200 * 1024 * 1024


class CopiaInvalida(Exception):
    """A cópia do Data4U está incompleta ou fora do formato esperado. Nada foi importado."""


# ------------------------------------------------------------------ leitura da cópia


@dataclass
class Copia:
    extraido_em: datetime  # quando o PC da recepção tirou a cópia
    pessoas: list[dict]
    periodos: dict[int, list[dict]]  # situação por pessoa (PESSOA_STATUS)
    contatos: dict[int, list[dict]]  # telefones e e-mails por pessoa (CONTATO_PESSOA)
    com_perfil: bool = False  # a cópia trouxe endereço e e-mail (programa novo do PC); sem isso, não se mexe neles
    acessos: dict[int, str] | None = None  # último acesso pela catraca por pessoa; None = a cópia não trouxe (não se mexe)

    @property
    def dia(self) -> str:
        """A data da cópia como 'AAAA-MM-DD' (o formato das datas do Data4U)."""
        return self.extraido_em.strftime("%Y-%m-%d")


def _linhas_do_zip(arquivo: zipfile.ZipFile, nome: str) -> bytes:
    try:
        info = arquivo.getinfo(nome)
    except KeyError:
        raise CopiaInvalida(f"Não achei {nome} dentro do arquivo.") from None
    if info.file_size > TAMANHO_MAXIMO_TABELA:
        raise CopiaInvalida(f"{nome} é grande demais ({info.file_size} bytes) para ser a tabela esperada.")
    return arquivo.read(info)


def _ler_bytes(origem: Path, nome: str) -> bytes:
    if origem.is_dir():
        caminho = origem / nome
        if not caminho.is_file():
            raise CopiaInvalida(f"Não achei {nome} na pasta {origem}.")
        if caminho.stat().st_size > TAMANHO_MAXIMO_TABELA:
            raise CopiaInvalida(f"{nome} é grande demais para ser a tabela esperada.")
        return caminho.read_bytes()
    with zipfile.ZipFile(origem) as arquivo:  # só lê os nomes pedidos: nada é extraído para o disco
        return _linhas_do_zip(arquivo, nome)


def _linhas_json(conteudo: bytes, tabela: str) -> list[dict]:
    try:
        texto_todo = conteudo.decode("utf-8")
    except UnicodeDecodeError:
        raise CopiaInvalida(f"{tabela}.jsonl não está em UTF-8.") from None
    linhas = []
    for numero, texto in enumerate(io.StringIO(texto_todo), start=1):
        if not texto.strip():
            continue
        try:
            linha = json.loads(texto)
        except json.JSONDecodeError as erro:
            raise CopiaInvalida(f"{tabela}.jsonl, linha {numero}: não é JSON válido ({erro.msg}).") from None
        if not isinstance(linha, dict):
            raise CopiaInvalida(f"{tabela}.jsonl, linha {numero}: esperava um objeto JSON.")
        linhas.append(linha)
    return linhas


def carregar_copia(origem: str | Path) -> Copia:
    """Lê as três tabelas e confere se a cópia está inteira (contra o manifesto)."""
    origem = Path(origem)
    if not origem.exists():
        raise CopiaInvalida(f"Não achei {origem}.")

    try:
        manifesto = json.loads(_ler_bytes(origem, "_manifesto.json"))
        extraido_em = datetime.strptime(manifesto["extracao"], "%d/%m/%Y %H:%M:%S")
        esperado = {t: manifesto["tabelas"][t]["linhas"] for t in TABELAS_USADAS}
        colunas = {t: set(manifesto["tabelas"][t]["colunas"]) for t in TABELAS_USADAS}
    except (KeyError, ValueError, TypeError) as erro:
        raise CopiaInvalida(f"O _manifesto.json não está no formato esperado ({erro!r}).") from None
    except zipfile.BadZipFile:
        raise CopiaInvalida(f"{origem} não é um arquivo .zip válido.") from None

    for nome, necessarias in COLUNAS_NECESSARIAS.items():
        faltam = [c for c in necessarias if c not in colunas[nome]]
        if faltam:
            raise CopiaInvalida(f"A tabela {nome} da cópia não tem a(s) coluna(s) {', '.join(faltam)}.")

    tabelas = {}
    for nome in TABELAS_USADAS:
        linhas = _linhas_json(_ler_bytes(origem, f"{nome}.jsonl"), nome)
        if len(linhas) != esperado[nome]:
            raise CopiaInvalida(
                f"{nome}: o manifesto diz {esperado[nome]} linhas e o arquivo tem {len(linhas)}. "
                "A cópia pode ter sido cortada: gere de novo no PC da recepção."
            )
        tabelas[nome] = linhas

    copia = _montar_copia(extraido_em, tabelas, all(c in colunas["PESSOA"] for c in COLUNAS_DO_ENDERECO))
    dados_acessos = manifesto["tabelas"].get(TABELA_DE_ACESSOS)
    if isinstance(dados_acessos, dict) and all(c in dados_acessos.get("colunas", []) for c in COLUNAS_DE_ACESSOS):
        copia.acessos = _acessos(_linhas_json(_ler_bytes(origem, f"{TABELA_DE_ACESSOS}.jsonl"), TABELA_DE_ACESSOS))
    return copia


def _acessos(linhas: list[dict]) -> dict[int, str]:
    """{pessoa: 'AAAA-MM-DD'} do último acesso. Data fora do formato fica de fora (não se adivinha)."""
    saida = {}
    for linha in linhas:
        pessoa, momento = linha.get("ID_PESSOA"), linha.get("DT_LAST_ACCESS")
        if isinstance(pessoa, int) and not isinstance(pessoa, bool) and isinstance(momento, str) and ler_dia(momento[:10]):
            saida[pessoa] = momento[:10]
    return saida


def _montar_copia(extraido_em: datetime, tabelas: dict[str, list[dict]], com_perfil: bool = False) -> Copia:
    periodos: dict[int, list[dict]] = defaultdict(list)
    for linha in tabelas["PESSOA_STATUS"]:
        if not isinstance(linha["DT_INI_STATUS"], str) or not isinstance(linha["DT_FIM_STATUS"], str):
            raise CopiaInvalida(
                f"PESSOA_STATUS: período sem data (pessoa {linha['ID_PESSOA']}). "
                "Não vou adivinhar a situação: gere a cópia de novo."
            )
        periodos[linha["ID_PESSOA"]].append(linha)
    contatos: dict[int, list[dict]] = defaultdict(list)
    for linha in tabelas["CONTATO_PESSOA"]:
        contatos[linha["ID_PESSOA"]].append(linha)
    return Copia(extraido_em, tabelas["PESSOA"], dict(periodos), dict(contatos), com_perfil)


# ------------------------------------------------------------------ pacote enviado pelo navegador
#
# Na tela "Atualizar alunos", o navegador do computador autorizado abre o base_total.zip,
# confere a cópia contra o manifesto e envia SÓ as três tabelas e SÓ as colunas de que o app
# precisa (nada de RG, nascimento, senha, e-mail, pagamentos, digitais...). O formato:
#
#   {"extracao": "07/10/2026 05:00:17",
#    "tabelas": {"PESSOA": {"colunas": ["ID", ...], "linhas": [[1, ...], ...]}, ...}}

IDADE_MAXIMA_DA_COPIA = timedelta(days=5)  # fim de semana com o PC desligado cabe; cópia velha demais, não
TOLERANCIA_DE_RELOGIO = timedelta(days=1)
LIMITE_DE_LINHAS_POR_TABELA = 1_000_000

_TIPOS_DAS_COLUNAS = {
    # (tipo obrigatório, aceita vazio?). int não aceita bool (True seria 1).
    "PESSOA": {"ID": (int, False), "NM_PESSOA": (str, True), "TP_PESSOA": (str, True), "NR_CPF": (str, True), "ST_DELETED": (str, True),
               # as do endereço só são conferidas quando vêm (o CEP é número no Data4U; o programa do PC manda como texto)
               "NR_CEP": ((int, str), True), "CD_UF": (str, True), "DS_LOCALIDADE": (str, True), "DS_BAIRRO": (str, True),
               "DS_LOGRADOURO": (str, True), "DS_COMPLEMENTO": (str, True)},
    "PESSOA_STATUS": {"ID_PESSOA": (int, False), "DT_INI_STATUS": (str, False), "DT_FIM_STATUS": (str, False), "CD_STATUS": (str, True)},
    "CONTATO_PESSOA": {"ID_CONTATO": (int, False), "ID_PESSOA": (int, False), "ID_TIPO_CONTATO": (int, True), "DS_CONTATO": (str, True)},
}


def valor_serve(valor, tipo, aceita_vazio: bool) -> bool:
    if valor is None:
        return aceita_vazio
    return isinstance(valor, tipo) and not isinstance(valor, bool)


def conferir_data_do_pacote(pacote, agora: datetime | None = None) -> datetime:
    """Confere o formato do pacote e a data da cópia (não pode ser do futuro nem velha demais).

    Devolve quando o PC da recepção tirou a cópia (horário de Vila Velha, sem fuso). Também é
    usada pela importação dos treinos (app/importar_treinos.py), que recebe o mesmo tipo de pacote.
    """
    agora = agora or datetime.now(timezone.utc)
    if not isinstance(pacote, dict) or not isinstance(pacote.get("tabelas"), dict):
        raise CopiaInvalida("O pacote enviado não está no formato esperado.")
    try:
        extraido_em = datetime.strptime(pacote["extracao"], "%d/%m/%Y %H:%M:%S")
    except (KeyError, ValueError, TypeError):
        raise CopiaInvalida("O pacote não informa direito a data e a hora da cópia do Data4U.") from None
    agora_local = agora.astimezone(FUSO_DA_ACADEMIA).replace(tzinfo=None)
    if extraido_em > agora_local + TOLERANCIA_DE_RELOGIO:
        raise CopiaInvalida(f"A cópia diz ser de {extraido_em:%d/%m/%Y %H:%M}, que ainda não chegou. Confira a data do computador.")
    if agora_local - extraido_em > IDADE_MAXIMA_DA_COPIA:
        raise CopiaInvalida(
            f"A cópia é de {extraido_em:%d/%m/%Y %H:%M}, velha demais "
            f"(mais de {IDADE_MAXIMA_DA_COPIA.days} dias). Gere uma cópia nova no PC da recepção."
        )
    return extraido_em


def copia_de_pacote(pacote, agora: datetime | None = None) -> Copia:
    """Valida o pacote enviado pelo navegador e o transforma em `Copia`. Nada é gravado aqui."""
    extraido_em = conferir_data_do_pacote(pacote, agora)
    if set(pacote["tabelas"]) not in (set(TABELAS_USADAS), set(TABELAS_USADAS) | {TABELA_DE_ACESSOS}):
        raise CopiaInvalida("O pacote precisa ter exatamente as tabelas " + ", ".join(TABELAS_USADAS) + ".")

    tabelas: dict[str, list[dict]] = {}
    for nome in TABELAS_USADAS:
        bloco = pacote["tabelas"][nome]
        colunas = bloco.get("colunas") if isinstance(bloco, dict) else None
        linhas = bloco.get("linhas") if isinstance(bloco, dict) else None
        if not isinstance(colunas, list) or not isinstance(linhas, list):
            raise CopiaInvalida(f"{nome}: formato inesperado.")
        # Exatamente as colunas usadas: coluna a mais seria dado pessoal que o app não precisa. Em PESSOA, o endereço vem inteiro
        # (programa novo do PC) ou não vem (programa antigo).
        aceitas = [set(COLUNAS_NECESSARIAS[nome])]
        if nome == "PESSOA":
            aceitas.append(set(COLUNAS_NECESSARIAS[nome]) | set(COLUNAS_DO_ENDERECO))
        if len(colunas) != len(set(colunas)) or set(colunas) not in aceitas:
            raise CopiaInvalida(f"{nome}: as colunas enviadas precisam ser exatamente {', '.join(COLUNAS_NECESSARIAS[nome])}.")
        if len(linhas) > LIMITE_DE_LINHAS_POR_TABELA:
            raise CopiaInvalida(f"{nome}: linhas demais.")
        tipos = _TIPOS_DAS_COLUNAS[nome]
        convertidas = []
        for numero, linha in enumerate(linhas, start=1):
            if not isinstance(linha, list) or len(linha) != len(colunas):
                raise CopiaInvalida(f"{nome}, linha {numero}: formato inesperado.")
            registro = dict(zip(colunas, linha))
            for coluna, (tipo, aceita_vazio) in tipos.items():
                if coluna in registro and not valor_serve(registro[coluna], tipo, aceita_vazio):
                    raise CopiaInvalida(f"{nome}, linha {numero}: a coluna {coluna} está num formato inesperado.")
            convertidas.append(registro)
        tabelas[nome] = convertidas
    com_perfil = all(c in pacote["tabelas"]["PESSOA"]["colunas"] for c in COLUNAS_DO_ENDERECO)
    copia = _montar_copia(extraido_em, tabelas, com_perfil)
    if TABELA_DE_ACESSOS in pacote["tabelas"]:
        bloco = pacote["tabelas"][TABELA_DE_ACESSOS]
        colunas = bloco.get("colunas") if isinstance(bloco, dict) else None
        linhas = bloco.get("linhas") if isinstance(bloco, dict) else None
        if colunas != list(COLUNAS_DE_ACESSOS) or not isinstance(linhas, list) or len(linhas) > LIMITE_DE_LINHAS_POR_TABELA:
            raise CopiaInvalida(f"{TABELA_DE_ACESSOS}: as colunas enviadas precisam ser exatamente {', '.join(COLUNAS_DE_ACESSOS)}.")
        for numero, linha in enumerate(linhas, start=1):
            if (not isinstance(linha, list) or len(linha) != 2 or not valor_serve(linha[0], int, False)
                    or not valor_serve(linha[1], str, True)):
                raise CopiaInvalida(f"{TABELA_DE_ACESSOS}, linha {numero}: formato inesperado.")
        copia.acessos = _acessos([dict(zip(COLUNAS_DE_ACESSOS, linha)) for linha in linhas])
    return copia


# ------------------------------------------------------------------ regras (funções puras)


def situacao_do_dia(periodos: list[dict], dia: str) -> tuple[str | None, bool]:
    """A letra da situação no `dia` ('AAAA-MM-DD') e se ela é ambígua.

    O Data4U grava a situação como períodos seguidos e já escreve o FUTURO (um plano
    novo gera "A", depois "P" por 30 dias, depois "D" sem fim). Por isso a situação de
    hoje é o período que COBRE hoje, e não o último da lista.

    Devolve (letra, False); (None, False) se nenhum período cobre o dia; ou
    (None, True) se mais de uma letra diferente cobre o dia (não se escolhe no palpite).
    """
    letras = {
        p["CD_STATUS"] for p in periodos if p["DT_INI_STATUS"] <= dia <= p["DT_FIM_STATUS"]
    }
    if not letras:
        return None, False
    if len(letras) > 1:
        return None, True
    return letras.pop(), False


def limpar_cpf(valor) -> tuple[str | None, bool]:
    """(cpf só com os 11 números, ou None; se o CPF estava preenchido mas não serve).

    Não se completa nem se corta CPF: um CPF com número de dígitos errado ficaria
    parecendo de outra pessoa.
    """
    if valor is None or str(valor).strip() == "":
        return None, False
    digitos = re.sub(r"[^0-9]", "", str(valor))  # [0-9], não \D: só algarismos comuns
    if len(digitos) == 11:
        return digitos, False
    return None, True


@dataclass
class EscolhaDeWhatsapp:
    numero: str | None
    tinha_celular: bool  # havia algum celular preenchido (mesmo que não sirva)
    varios_validos: bool  # havia mais de um número diferente que serve


def escolher_whatsapp(contatos: list[dict]) -> EscolhaDeWhatsapp:
    """O primeiro celular (por ordem de cadastro) que passa na mesma regra da correção na ficha.

    Mesma regra de `app.alunos.validar_whatsapp`: 10 ou 11 números com DDD de 11 a 99,
    sem +55. Números de 9 números (sem DDD) não servem: o DDD não é adivinhado.
    """
    celulares = sorted(
        (c for c in contatos if c.get("ID_TIPO_CONTATO") == TIPO_CONTATO_CELULAR and (c.get("DS_CONTATO") or "").strip()),
        key=lambda c: c["ID_CONTATO"],
    )
    validos = []
    for contato in celulares:
        try:
            numero = validar_whatsapp(contato["DS_CONTATO"])
        except WhatsappInvalido:
            continue
        if numero not in validos:
            validos.append(numero)
    return EscolhaDeWhatsapp(
        numero=validos[0] if validos else None,
        tinha_celular=bool(celulares),
        varios_validos=len(validos) > 1,
    )


def _nome_limpo(valor) -> str:
    return " ".join(str(valor or "").split())


_EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}")


def escolher_email(contatos: list[dict]) -> str | None:
    """O primeiro e-mail (por ordem de cadastro) que tem cara de e-mail. Nada é corrigido: o que não serve fica de fora."""
    for contato in sorted((c for c in contatos if c.get("ID_TIPO_CONTATO") == TIPO_CONTATO_EMAIL), key=lambda c: c["ID_CONTATO"]):
        texto = "".join(str(contato.get("DS_CONTATO") or "").split())
        if len(texto) <= 254 and _EMAIL.fullmatch(texto):
            return texto
    return None


def _texto_curto(valor, limite: int) -> str | None:
    texto = _nome_limpo(valor)
    return texto[:limite] if texto else None


def limpar_cep(valor) -> str | None:
    """8 números, ou None. CEP com outro tamanho (no Data4U há alguns com 9) fica vazio: não se adivinha qual número sobra."""
    if valor is None:
        return None
    digitos = re.sub(r"[^0-9]", "", str(valor))
    if len(digitos) == 7:  # o Data4U guarda o CEP como número: "29122-300" fica 29122300, mas "01310-100" perde o zero
        digitos = "0" + digitos
    return digitos if len(digitos) == 8 else None


def perfil_da_pessoa(pessoa: dict, contatos: list[dict]) -> dict:
    """E-mail e endereço que vão para o "Meu perfil" do aluno."""
    uf = _nome_limpo(pessoa.get("CD_UF")).upper()
    return {
        "email": escolher_email(contatos),
        "cep": limpar_cep(pessoa.get("NR_CEP")),
        "uf": uf if len(uf) == 2 and uf.isalpha() else None,
        "cidade": _texto_curto(pessoa.get("DS_LOCALIDADE"), 120),
        "bairro": _texto_curto(pessoa.get("DS_BAIRRO"), 120),
        "logradouro": _texto_curto(pessoa.get("DS_LOGRADOURO"), 200),
        "complemento": _texto_curto(pessoa.get("DS_COMPLEMENTO"), 120),
    }


PERFIL_VAZIO = dict.fromkeys(CAMPOS_DO_PERFIL)


# ------------------------------------------------------------------ importação


@dataclass
class Relatorio:
    extraido_em: datetime
    pessoas_na_copia: int = 0
    novos: int = 0
    atualizados: int = 0
    iguais: int = 0
    por_situacao: Counter = field(default_factory=Counter)
    # quem ficou de fora, e por quê
    fora_pessoa_juridica: int = 0
    fora_apagadas: int = 0
    fora_id_interno: int = 0  # ID zero ou negativo (cadastros internos do Data4U)
    fora_sem_situacao: int = 0
    fora_situacao_ambigua: int = 0
    fora_situacao_desconhecida: Counter = field(default_factory=Counter)
    fora_sem_nome: int = 0
    # qualidade dos dados de quem entrou
    sem_cpf: int = 0
    cpf_invalido: int = 0
    sem_celular: int = 0
    celular_que_nao_serve: int = 0  # tinha celular, mas sem DDD ou fora do formato
    whatsapp_varios: int = 0
    whatsapp_mantido_do_app: int = 0  # a recepção corrigiu no app: a cópia não sobrescreveu
    com_perfil: bool = False  # a cópia trouxe e-mail e endereço
    em_uso_com_email: int = 0
    em_uso_com_endereco: int = 0
    em_uso: int = 0
    com_acesso_recente: int | None = None  # None: a cópia não trouxe os acessos
    # já estavam no app com matrícula, mas não vieram nesta cópia (ficam como estão)
    no_app_e_fora_da_copia: int = 0
    # alunos provisórios (cadastrados no app antes de chegarem pelo Data4U)
    provisorios_juntados: int = 0  # acharam o par pelo CPF nesta cópia
    provisorios_com_cpf_duvidoso: int = 0  # o CPF existe no Data4U, mas sem certeza de que é a mesma pessoa
    provisorios_sem_par: int = 0  # ainda provisórios depois desta importação (inclui os da linha acima)

    @property
    def importadas(self) -> int:
        return self.novos + self.provisorios_juntados + self.atualizados + self.iguais

    def como_dicionario(self) -> dict:
        """Para a tela "Atualizar alunos": só contagens e o texto do relatório (sem nome, CPF ou telefone)."""
        return {
            "extraido_em": f"{self.extraido_em:%d/%m/%Y %H:%M}",
            "importadas": self.importadas,
            "novos": self.novos,
            "atualizados": self.atualizados,
            "iguais": self.iguais,
            "provisorios_juntados": self.provisorios_juntados,
            "texto": self.texto(),
        }

    def texto(self) -> str:
        linhas = [
            f"Cópia do Data4U de {self.extraido_em:%d/%m/%Y %H:%M}",
            f"  Pessoas na cópia: {self.pessoas_na_copia}",
            f"  Alunos no app a partir da cópia: {self.importadas} "
            f"({self.novos} novos, {self.atualizados} atualizados, {self.iguais} sem mudança, "
            f"{self.provisorios_juntados} provisórios do app juntados pelo CPF)",
            "  Por situação: "
            + ", ".join(f"{SITUACOES[letra]} {self.por_situacao[letra]}" for letra in SITUACOES if self.por_situacao[letra]),
            "  Ficaram de fora:",
            f"    pessoa jurídica: {self.fora_pessoa_juridica}",
            f"    cadastro apagado no Data4U: {self.fora_apagadas}",
            f"    ID interno do Data4U (zero ou negativo): {self.fora_id_interno}",
            f"    sem situação no dia da cópia: {self.fora_sem_situacao}",
            f"    situação ambígua: {self.fora_situacao_ambigua}",
            f"    sem nome: {self.fora_sem_nome}",
        ]
        linhas.append(
            f"  Passaram pela catraca nos últimos {DIAS_DE_ACESSO_RECENTE} dias: {self.com_acesso_recente}"
            if self.com_acesso_recente is not None
            else "  Acessos pela catraca: não vieram nesta cópia (programa antigo no PC da recepção); ficaram como estavam"
        )
        for letra, quantos in sorted(self.fora_situacao_desconhecida.items()):
            linhas.append(f"    situação desconhecida '{letra}': {quantos}")
        linhas += [
            "  Dados que faltam em quem entrou:",
            f"    sem CPF: {self.sem_cpf}",
            f"    CPF preenchido mas inválido (deixado vazio): {self.cpf_invalido}",
            f"    sem nenhum celular: {self.sem_celular}",
            f"    com celular que não serve de WhatsApp (sem DDD ou fora do formato): {self.celular_que_nao_serve}",
            f"    com mais de um celular válido (usei o primeiro cadastrado): {self.whatsapp_varios}",
            f"    WhatsApp mantido porque foi digitado ou corrigido no app: {self.whatsapp_mantido_do_app}",
            (
                f"  E-mail e endereço (só de quem está em uso, {self.em_uso}): {self.em_uso_com_email} com e-mail, "
                f"{self.em_uso_com_endereco} com endereço"
                if self.com_perfil
                else "  E-mail e endereço: não vieram nesta cópia (programa antigo no PC da recepção); ficaram como estavam"
            ),
            f"  Já estavam no app e não vieram nesta cópia (mantidos): {self.no_app_e_fora_da_copia}",
            f"  Alunos provisórios que continuam sem par no Data4U: {self.provisorios_sem_par} "
            f"(desses, {self.provisorios_com_cpf_duvidoso} têm o CPF de alguém do Data4U, mas sem certeza para juntar)",
        ]
        return "\n".join(linhas)


def _inserir(conn, aluno: dict, cadastrado_em: str) -> None:
    conn.execute(
        "INSERT INTO aluno (nome, cpf, whatsapp, data4u_id, situacao, criado_em, email, cep, uf, cidade, bairro, logradouro, complemento)"
        " VALUES (:nome, :cpf, :whatsapp, :data4u_id, :situacao, :criado_em,"
        " :email, :cep, :uf, :cidade, :bairro, :logradouro, :complemento)",
        {**PERFIL_VAZIO, **aluno, "criado_em": cadastrado_em},
    )
    if "ultimo_acesso" in aluno:
        conn.execute("UPDATE aluno SET ultimo_acesso = ? WHERE data4u_id = ?", (aluno["ultimo_acesso"], aluno["data4u_id"]))


def _gravar_perfil(conn, aluno_id: int, aluno: dict) -> None:
    if "ultimo_acesso" in aluno:  # só quando a cópia trouxe os acessos
        conn.execute("UPDATE aluno SET ultimo_acesso = ? WHERE id = ?", (aluno["ultimo_acesso"], aluno_id))
    if "email" in aluno:  # só quando a cópia trouxe e-mail e endereço
        conn.execute(
            "UPDATE aluno SET email = ?, cep = ?, uf = ?, cidade = ?, bairro = ?, logradouro = ?, complemento = ? WHERE id = ?",
            (*(aluno[c] for c in CAMPOS_DO_PERFIL), aluno_id),
        )


def _juntar_ao_provisorio(conn, provisorio, aluno: dict, relatorio: "Relatorio") -> None:
    """A pessoa do Data4U passa a ser o aluno provisório (a linha dele, com os treinos, é a que fica).

    Nome e situação vêm do Data4U (é o cadastro oficial). O WhatsApp digitado no app vale mais
    que o do Data4U; se o provisório foi cadastrado sem WhatsApp, entra o do Data4U.
    """
    whatsapp = aluno["whatsapp"]
    if provisorio["whatsapp_corrigido_no_app"]:
        whatsapp = provisorio["whatsapp"]
        relatorio.whatsapp_mantido_do_app += 1
    conn.execute(
        "UPDATE aluno SET nome = ?, whatsapp = ?, data4u_id = ?, situacao = ?, provisorio = 0"
        " WHERE id = ? AND provisorio = 1 AND data4u_id IS NULL",
        (aluno["nome"], whatsapp, aluno["data4u_id"], aluno["situacao"], provisorio["id"]),
    )
    _gravar_perfil(conn, provisorio["id"], aluno)


def importar(conn, copia: Copia, agora: datetime | None = None) -> Relatorio:
    """Grava os alunos da cópia no banco, tudo ou nada. Devolve o relatório."""
    agora = agora or datetime.now(timezone.utc)
    cadastrado_em = agora.strftime("%Y-%m-%d %H:%M:%S")  # UTC, como o banco guarda
    relatorio = Relatorio(extraido_em=copia.extraido_em, pessoas_na_copia=len(copia.pessoas), com_perfil=copia.com_perfil)
    if copia.acessos is not None:
        relatorio.com_acesso_recente = 0
        desde = (copia.extraido_em - timedelta(days=DIAS_DE_ACESSO_RECENTE)).strftime("%Y-%m-%d")

    alunos_da_copia: list[dict] = []
    for pessoa in sorted(copia.pessoas, key=lambda p: p["ID"]):
        if pessoa["ID"] <= 0:
            relatorio.fora_id_interno += 1
            continue
        if pessoa.get("ST_DELETED") == "T":
            relatorio.fora_apagadas += 1
            continue
        if pessoa.get("TP_PESSOA") != "F":
            relatorio.fora_pessoa_juridica += 1
            continue
        letra, ambigua = situacao_do_dia(copia.periodos.get(pessoa["ID"], []), copia.dia)
        if ambigua:
            relatorio.fora_situacao_ambigua += 1
            continue
        if letra is None:
            relatorio.fora_sem_situacao += 1
            continue
        if letra not in SITUACOES:
            relatorio.fora_situacao_desconhecida[letra] += 1
            continue
        nome = _nome_limpo(pessoa.get("NM_PESSOA"))
        if not nome:
            relatorio.fora_sem_nome += 1
            continue

        cpf, cpf_invalido = limpar_cpf(pessoa.get("NR_CPF"))
        zap = escolher_whatsapp(copia.contatos.get(pessoa["ID"], []))
        relatorio.por_situacao[letra] += 1
        relatorio.sem_cpf += cpf is None and not cpf_invalido
        relatorio.cpf_invalido += cpf_invalido
        relatorio.sem_celular += not zap.tinha_celular
        relatorio.celular_que_nao_serve += zap.tinha_celular and zap.numero is None
        relatorio.whatsapp_varios += zap.varios_validos
        aluno = {"data4u_id": pessoa["ID"], "nome": nome, "cpf": cpf, "whatsapp": zap.numero, "situacao": letra}
        if copia.acessos is not None:
            dia = copia.acessos.get(pessoa["ID"])
            aluno["ultimo_acesso"] = dia if dia is not None and desde <= dia <= copia.dia else None
            relatorio.com_acesso_recente += aluno["ultimo_acesso"] is not None
        if copia.com_perfil:
            em_uso = letra in SITUACOES_COM_PERFIL
            perfil = perfil_da_pessoa(pessoa, copia.contatos.get(pessoa["ID"], [])) if em_uso else PERFIL_VAZIO
            aluno.update(perfil)
            relatorio.em_uso += em_uso
            relatorio.em_uso_com_email += perfil["email"] is not None
            relatorio.em_uso_com_endereco += perfil["logradouro"] is not None
        alunos_da_copia.append(aluno)

    ids_da_copia = {a["data4u_id"] for a in alunos_da_copia}

    with conn:  # uma transação só: se algo falhar, nada do que veio antes fica gravado
        existentes = {
            linha["data4u_id"]: linha
            for linha in conn.execute(
                "SELECT id, data4u_id, nome, cpf, whatsapp, whatsapp_corrigido_no_app, situacao,"
                " email, cep, uf, cidade, bairro, logradouro, complemento, ultimo_acesso"
                " FROM aluno WHERE data4u_id IS NOT NULL"
            )
        }

        # Para juntar provisórios: quem tem cada CPF, no Data4U e entre os provisórios.
        pessoas_por_cpf: dict[str, set[int]] = defaultdict(set)
        for matricula, linha in existentes.items():
            if matricula not in ids_da_copia and linha["cpf"]:
                pessoas_por_cpf[linha["cpf"]].add(matricula)
        for aluno in alunos_da_copia:
            if aluno["cpf"]:
                pessoas_por_cpf[aluno["cpf"]].add(aluno["data4u_id"])
        provisorios_por_cpf: dict[str, list] = defaultdict(list)
        for linha in conn.execute(
            "SELECT id, cpf, whatsapp, whatsapp_corrigido_no_app FROM aluno"
            " WHERE provisorio = 1 AND data4u_id IS NULL AND cpf IS NOT NULL ORDER BY id"
        ):
            provisorios_por_cpf[linha["cpf"]].append(linha)
        juntados: set[int] = set()  # ids dos provisórios que acharam o par nesta importação

        for aluno in alunos_da_copia:
            atual = existentes.get(aluno["data4u_id"])
            if atual is None:
                candidatos = provisorios_por_cpf.get(aluno["cpf"], [])  # sem CPF não há como ligar: lista vazia
                # Só junta com certeza: um provisório e uma pessoa do Data4U com este CPF.
                if len(candidatos) == 1 and len(pessoas_por_cpf[aluno["cpf"]]) == 1:
                    _juntar_ao_provisorio(conn, candidatos[0], aluno, relatorio)
                    juntados.add(candidatos[0]["id"])
                    relatorio.provisorios_juntados += 1
                else:
                    _inserir(conn, aluno, cadastrado_em)
                    relatorio.novos += 1
                continue

            whatsapp = aluno["whatsapp"]
            if atual["whatsapp_corrigido_no_app"]:
                whatsapp = atual["whatsapp"]  # o número do app prevalece (decisão de 07/10/2026)
                relatorio.whatsapp_mantido_do_app += 1
            novos_valores = (aluno["nome"], aluno["cpf"], whatsapp, aluno["situacao"])
            perfil_igual = ("email" not in aluno or all(aluno[c] == atual[c] for c in CAMPOS_DO_PERFIL)) and (
                "ultimo_acesso" not in aluno or aluno["ultimo_acesso"] == atual["ultimo_acesso"]
            )
            if novos_valores == (atual["nome"], atual["cpf"], atual["whatsapp"], atual["situacao"]) and perfil_igual:
                relatorio.iguais += 1
                continue
            conn.execute(
                "UPDATE aluno SET nome = ?, cpf = ?, whatsapp = ?, situacao = ? WHERE id = ?",
                (*novos_valores, atual["id"]),
            )
            _gravar_perfil(conn, atual["id"], aluno)
            relatorio.atualizados += 1

        relatorio.no_app_e_fora_da_copia = sum(1 for i in existentes if i not in ids_da_copia)
        relatorio.provisorios_sem_par = conn.execute(
            "SELECT COUNT(*) FROM aluno WHERE provisorio = 1 AND data4u_id IS NULL"
        ).fetchone()[0]
        # Provisório que tem o mesmo CPF de alguém do Data4U mas não foi juntado: não deu para ter certeza.
        relatorio.provisorios_com_cpf_duvidoso = sum(
            1
            for cpf, lista in provisorios_por_cpf.items()
            if cpf in pessoas_por_cpf
            for provisorio in lista
            if provisorio["id"] not in juntados
        )
    return relatorio


# ------------------------------------------------------------------ linha de comando


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Importa os alunos da cópia diária do Data4U.")
    parser.add_argument("copia", help="o base_total.zip (ou a pasta já extraída)")
    parser.add_argument("banco", help="o arquivo do banco do app (criado se não existir)")
    args = parser.parse_args(argv)

    try:
        copia = carregar_copia(args.copia)
    except CopiaInvalida as erro:
        print(f"Importação cancelada, nada foi gravado: {erro}", file=sys.stderr)
        return 1

    conn = conectar(args.banco)
    try:
        criar_tabelas(conn)
        print(importar(conn, copia).texto())
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
