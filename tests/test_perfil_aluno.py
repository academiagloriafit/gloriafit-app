"""O "Meu perfil" do aluno: os dados na tela e a saudação (app/perfil_aluno.py)."""

from datetime import datetime, timezone

import pytest

from app import perfil_aluno as p


@pytest.mark.parametrize("hora_utc, esperado", [(7, "Boa noite"), (8, "Bom dia"), (14, "Bom dia"), (15, "Boa tarde"), (20, "Boa tarde"),
                                                (21, "Boa noite"), (2, "Boa noite")])
def test_saudacao_pelo_horario_de_vila_velha(hora_utc, esperado):
    # Vila Velha = UTC-3: 08h UTC são 5h lá
    assert p.saudacao_da_hora(datetime(2026, 10, 29, hora_utc, 0, tzinfo=timezone.utc)) == esperado


def test_formatos_na_tela():
    assert p.cpf_na_tela("11144477735") == "111.444.777-35" and p.cpf_na_tela("123") is None and p.cpf_na_tela(None) is None
    assert p.telefone_na_tela("27988887766") == "(27) 98888-7766" and p.telefone_na_tela("2733334444") == "(27) 3333-4444"
    assert p.telefone_na_tela("") is None and p.cep_na_tela("29122300") == "29122-300" and p.cep_na_tela("291") is None


def _cadastro(**mudar):
    base = {"nome": "MARIANA DE SOUZA", "cpf": "11144477735", "whatsapp": "27988887766", "email": None, "cep": None, "uf": None,
            "cidade": None, "bairro": None, "logradouro": None, "complemento": None}
    return {**base, **mudar}


def test_sem_endereco_e_sem_email_aparece_nao_informado():
    tela = p.para_tela(_cadastro())
    assert tela["nome"] == "Mariana de Souza" and tela["email"] == p.NAO_INFORMADO and tela["endereco"] == [p.NAO_INFORMADO]


def test_endereco_completo_e_pela_metade():
    completo = p.para_tela(_cadastro(logradouro="RUA DAS FLORES, 10", complemento="CASA 2", bairro="GLÓRIA", cidade="VILA VELHA", uf="ES", cep="29122300"))
    assert completo["endereco"] == ["Rua das Flores, 10 – Casa 2", "Glória – Vila Velha/ES", "CEP 29122-300"]
    so_rua = p.para_tela(_cadastro(logradouro="RUA DAS FLORES, 10"))
    assert so_rua["endereco"] == ["Rua das Flores, 10"]
    sem_rua = p.para_tela(_cadastro(bairro="GLÓRIA", cidade="VILA VELHA"))
    assert sem_rua["endereco"] == [p.NAO_INFORMADO]  # sem a rua, o resto sozinho não serve de endereço
