"""Foto do aluno (29/10/2026): a foto que a recepção tirou no Data4U (cadastro da catraca), em miniatura, para o professor
reconhecer o aluno nas telas do computador autorizado.

DE ONDE VEM: o Data4U guarda as fotos num banco à parte, o CACHE.D4U (tabela BLOB_CACHE, chave "foto/<id da pessoa>_im_foto").
O envio diário do PC da recepção (static/recepcao/enviar_alunos.py) lê esse cache e manda só as fotos dos alunos que o servidor pede:
  1. POST /api/fotos/estado    -> o servidor diz quais alunos estão em uso (situação A ou P) e o "resumo" (sha256) da foto que já tem.
  2. POST /api/fotos/importar  -> o PC manda, em pacotes, só as fotos novas ou trocadas, mais a lista de quem tem foto no cache hoje.

O QUE O SERVIDOR GUARDA: uma miniatura quadrada (LADO x LADO, JPEG) para as listas e, desde a versão 20 do banco, a foto inteira reduzida
(no máximo LADO_GRANDE no lado maior) para abrir quando o professor clica. As duas são refeitas aqui; a original é descartada.
Nada de reconhecimento facial: o dado de biometria do Data4U nunca sai do PC.

QUANTO TEMPO: a cada envio, quem continua ativo e com foto é "visto". Foto que passa DIAS_SEM_CONFIRMACAO dias sem ser vista (o aluno
saiu, ou a foto foi apagada no Data4U) é apagada. Decisão do Thiago (29/10/2026): 90 dias, caso o aluno volte.

QUEM VÊ: só computador autorizado (rota /alunos/<id>/foto, protegida pela guarda da área do professor). Nunca no app do aluno.
"""

import base64
import binascii
import hashlib
import io
import sqlite3
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageOps, UnidentifiedImageError

LADO_GRANDE = 640  # pixels no lado maior da foto que abre ao clicar (ver quem é a pessoa)
QUALIDADE_GRANDE = 84
LADO = 160  # pixels: a maior miniatura na tela tem 56 px; 160 fica nítido em tela de alta densidade
QUALIDADE = 82
TAMANHO_MAXIMO_DA_ORIGINAL = 3 * 1024 * 1024  # as fotos do Data4U têm 30 a 50 KB
PIXELS_MAXIMOS = 40_000_000  # trava contra imagem "bomba" (pequena no arquivo, gigante na memória)
FOTOS_POR_PACOTE = 150  # o PC manda em pacotes; 150 fotos de 50 KB em base64 ~ 10 MB
PRESENTES_MAXIMOS = 20_000
DIAS_SEM_CONFIRMACAO = 90
SITUACOES_COM_FOTO = ("A", "P")  # ativo e pendente (plano vencido, ainda treinando)
FORMATOS_ACEITOS = ("JPEG", "PNG")


class PacoteInvalido(Exception):
    """O pacote de fotos está fora do formato. Nada é gravado."""


def _agora(agora: datetime | None) -> datetime:
    return (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)


def _texto_utc(momento: datetime) -> str:
    return momento.strftime("%Y-%m-%d %H:%M:%S")


def miniatura(original: bytes) -> bytes:
    """A miniatura quadrada (JPEG) de uma foto. Levanta PacoteInvalido se não for uma imagem JPEG/PNG que dê para abrir."""
    return _refazer(original, grande=False)


def foto_grande(original: bytes) -> bytes:
    """A foto inteira, sem recorte, com no máximo LADO_GRANDE no lado maior (nunca aumenta uma foto pequena)."""
    return _refazer(original, grande=True)


def _refazer(original: bytes, grande: bool) -> bytes:
    if not original or len(original) > TAMANHO_MAXIMO_DA_ORIGINAL:
        raise PacoteInvalido("foto vazia ou grande demais")
    try:
        with Image.open(io.BytesIO(original)) as imagem:
            if imagem.format not in FORMATOS_ACEITOS:
                raise PacoteInvalido(f"formato {imagem.format!r} não aceito")
            if imagem.width * imagem.height > PIXELS_MAXIMOS:
                raise PacoteInvalido("foto com pixels demais")
            alvo = LADO_GRANDE if grande else LADO * 2
            imagem.draft("RGB", (alvo, alvo))  # JPEG: já abre reduzida (mais rápido, menos memória)
            imagem = ImageOps.exif_transpose(imagem).convert("RGB")
            saida = io.BytesIO()
            if grande:
                imagem.thumbnail((LADO_GRANDE, LADO_GRANDE), Image.Resampling.LANCZOS)  # mantém a proporção; não aumenta
                imagem.save(saida, "JPEG", quality=QUALIDADE_GRANDE, optimize=True)
            else:
                # recorte quadrado um pouco acima do centro: em foto de cadastro o rosto fica na parte de cima
                quadrada = ImageOps.fit(imagem, (LADO, LADO), method=Image.Resampling.LANCZOS, centering=(0.5, 0.38))
                quadrada.save(saida, "JPEG", quality=QUALIDADE, optimize=True)
            return saida.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as erro:
        raise PacoteInvalido(f"não deu para abrir a foto ({type(erro).__name__})") from None


def estado(conn: sqlite3.Connection) -> dict:
    """O que o PC da recepção precisa saber: os alunos em uso (pelo id do Data4U) e o resumo da foto que o servidor já tem.
    Foto sem a versão grande (gravada antes da versão 20) volta sem resumo: o PC entende que precisa mandar de novo."""
    linhas = conn.execute(
        f"""
        SELECT a.data4u_id, CASE WHEN f.grande IS NOT NULL THEN f.origem_sha256 END
        FROM aluno a LEFT JOIN foto_aluno f ON f.aluno_id = a.id
        WHERE a.data4u_id IS NOT NULL AND a.situacao IN ({",".join("?" * len(SITUACOES_COM_FOTO))})
        ORDER BY a.data4u_id
        """,
        SITUACOES_COM_FOTO,
    ).fetchall()
    return {
        "alunos": [{"id": linha[0], "sha256": linha[1]} for linha in linhas],
        "fotos_por_pacote": FOTOS_POR_PACOTE,
    }


def _inteiros(valor, nome: str, maximo: int) -> list[int]:
    if not isinstance(valor, list) or len(valor) > maximo:
        raise PacoteInvalido(f"'{nome}' precisa ser uma lista de até {maximo} números")
    if not all(isinstance(v, int) and not isinstance(v, bool) and 0 < v < 2**53 for v in valor):
        raise PacoteInvalido(f"'{nome}' só pode ter números inteiros positivos")
    return valor


def _fotos_do_pacote(pacote) -> list[tuple[int, bytes]]:
    if not isinstance(pacote, dict):
        raise PacoteInvalido("o pacote precisa ser um objeto JSON")
    fotos = pacote.get("fotos")
    if not isinstance(fotos, list) or len(fotos) > FOTOS_POR_PACOTE:
        raise PacoteInvalido(f"'fotos' precisa ser uma lista de até {FOTOS_POR_PACOTE} fotos")
    saida = []
    for foto in fotos:
        if not isinstance(foto, dict) or set(foto) != {"id", "jpg"}:
            raise PacoteInvalido("cada foto precisa ter só 'id' e 'jpg'")
        (identificador,) = _inteiros([foto["id"]], "id", 1)
        if not isinstance(foto["jpg"], str):
            raise PacoteInvalido("'jpg' precisa ser texto em base64")
        try:
            dados = base64.b64decode(foto["jpg"], validate=True)
        except (binascii.Error, ValueError):
            raise PacoteInvalido("'jpg' não é base64 válido") from None
        saida.append((identificador, dados))
    return saida


def importar(conn: sqlite3.Connection, pacote, agora: datetime | None = None) -> dict:
    """Grava as fotos de um pacote e marca como "vistos" os alunos que têm foto no cache hoje. Tudo ou nada.

    Foto de quem não é aluno conhecido é ignorada (contada em "sem_aluno"); foto que não abre é recusada (contada em "recusadas")
    sem derrubar o pacote: uma foto estragada no Data4U não pode travar as outras.
    """
    fotos = _fotos_do_pacote(pacote)
    presentes = _inteiros(pacote.get("presentes", []), "presentes", PRESENTES_MAXIMOS)
    momento = _texto_utc(_agora(agora))
    limite = _texto_utc(_agora(agora) - timedelta(days=DIAS_SEM_CONFIRMACAO))

    por_data4u = {
        linha[0]: linha[1]
        for linha in conn.execute("SELECT data4u_id, id FROM aluno WHERE data4u_id IS NOT NULL")
    }
    relatorio = {"gravadas": 0, "recusadas": 0, "sem_aluno": 0, "vistas": 0, "apagadas": 0}
    miniaturas = []
    for data4u_id, original in fotos:
        aluno_id = por_data4u.get(data4u_id)
        if aluno_id is None:
            relatorio["sem_aluno"] += 1
            continue
        try:
            miniaturas.append((aluno_id, miniatura(original), foto_grande(original), hashlib.sha256(original).hexdigest()))
        except PacoteInvalido:
            relatorio["recusadas"] += 1

    with conn:
        for aluno_id, dados, grande, resumo in miniaturas:
            conn.execute(
                """
                INSERT INTO foto_aluno (aluno_id, miniatura, grande, origem_sha256, atualizada_em, vista_em) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (aluno_id) DO UPDATE SET miniatura = excluded.miniatura, grande = excluded.grande,
                    origem_sha256 = excluded.origem_sha256, atualizada_em = excluded.atualizada_em, vista_em = excluded.vista_em
                """,
                (aluno_id, dados, grande, resumo, momento, momento),
            )
            relatorio["gravadas"] += 1
        vistos = [por_data4u[i] for i in presentes if i in por_data4u]
        for inicio in range(0, len(vistos), 500):
            parte = vistos[inicio : inicio + 500]
            relatorio["vistas"] += conn.execute(
                f"UPDATE foto_aluno SET vista_em = ? WHERE aluno_id IN ({','.join('?' * len(parte))})", [momento, *parte]
            ).rowcount
        relatorio["apagadas"] = conn.execute("DELETE FROM foto_aluno WHERE vista_em < ?", (limite,)).rowcount
    return relatorio


def ler(conn: sqlite3.Connection, aluno_id: int, grande: bool = False) -> bytes | None:
    """A miniatura (ou, com grande=True, a foto grande; se ela ainda não chegou, a miniatura). None se o aluno não tem foto."""
    linha = conn.execute("SELECT miniatura, grande FROM foto_aluno WHERE aluno_id = ?", (aluno_id,)).fetchone()
    if linha is None:
        return None
    return bytes(linha[1] if grande and linha[1] is not None else linha[0])


def alunos_com_foto(conn: sqlite3.Connection) -> frozenset[int]:
    """Os ids (do app) de quem tem foto. Poucas centenas de números: as telas consultam uma vez por pedido."""
    return frozenset(linha[0] for linha in conn.execute("SELECT aluno_id FROM foto_aluno"))
