"""O "Meu perfil" do app do aluno (29/10/2026): os dados do cadastro do jeito que aparecem na tela, e a saudação da tela inicial.

Os dados são só para ver. Quem muda é a recepção, no Data4U (decisão do Thiago): a base oficial continua sendo a do Data4U e toda
mudança passa pela conferência da academia. Nada é adivinhado: o que não está no cadastro aparece como "Não informado".
"""

from datetime import datetime

from app import datas
from app.nomes import nome_de_pessoa

# WhatsApp da academia (o único canal telefônico desde jul/2026): (27) 99288-2112.
WHATSAPP_DA_ACADEMIA = "5527992882112"
WHATSAPP_DA_ACADEMIA_NA_TELA = "(27) 99288-2112"
NAO_INFORMADO = "Não informado"


def saudacao_da_hora(agora: datetime | None = None) -> str:
    """"Bom dia" das 5h ao meio-dia, "Boa tarde" do meio-dia às 18h, "Boa noite" no resto (horário de Vila Velha)."""
    hora = (agora or datas.agora_utc()).astimezone(datas.FUSO_DA_ACADEMIA).hour
    if 5 <= hora < 12:
        return "Bom dia"
    if 12 <= hora < 18:
        return "Boa tarde"
    return "Boa noite"


def cpf_na_tela(cpf: str | None) -> str | None:
    """'11144477735' -> '111.444.777-35'."""
    if not cpf or len(cpf) != 11 or not cpf.isdigit():
        return None
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def telefone_na_tela(numero: str | None) -> str | None:
    """'27988887766' -> '(27) 98888-7766'; '2733334444' -> '(27) 3333-4444'."""
    if not numero or not numero.isdigit() or len(numero) not in (10, 11):
        return None
    return f"({numero[:2]}) {numero[2:-4]}-{numero[-4:]}"


def cep_na_tela(cep: str | None) -> str | None:
    """'29122300' -> '29122-300'."""
    if not cep or len(cep) != 8 or not cep.isdigit():
        return None
    return f"{cep[:5]}-{cep[5:]}"


def _endereco(cadastro) -> list[str]:
    """As linhas do endereço, na ordem de um envelope. Vazio se não tem rua."""
    if not cadastro["logradouro"]:
        return []
    linhas = [nome_de_pessoa(cadastro["logradouro"])]
    if cadastro["complemento"]:
        linhas[0] += f" – {nome_de_pessoa(cadastro['complemento'])}"
    cidade = nome_de_pessoa(cadastro["cidade"]) if cadastro["cidade"] else ""
    lugar = " – ".join(p for p in (nome_de_pessoa(cadastro["bairro"]) if cadastro["bairro"] else "", cidade) if p)
    if lugar and cadastro["uf"]:
        lugar += f"/{cadastro['uf']}"
    if lugar:
        linhas.append(lugar)
    cep = cep_na_tela(cadastro["cep"])
    if cep:
        linhas.append(f"CEP {cep}")
    return linhas


def para_tela(cadastro) -> dict:
    """Os dados do aluno prontos para a tela "Meu perfil"."""
    return {
        "nome": nome_de_pessoa(cadastro["nome"]),
        "cpf": cpf_na_tela(cadastro["cpf"]) or NAO_INFORMADO,
        "whatsapp": telefone_na_tela(cadastro["whatsapp"]) or NAO_INFORMADO,
        "email": cadastro["email"] or NAO_INFORMADO,
        "endereco": _endereco(cadastro) or [NAO_INFORMADO],
    }
