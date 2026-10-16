"""Gera os ícones do app (tela inicial do celular e aba do navegador) a partir do logo oficial.

Uso, na pasta do projeto (precisa de Pillow e numpy; não fazem parte do app, só desta ferramenta):

    python3 ferramentas/gerar_icones.py

Por que este script existe: o único arquivo do logo que temos (app/static/marca/logo-gloria-fit.png)
tem só 192 px, está um pouco fora do centro, tem a borda de cima cortada e as bordas são serrilhadas
(sem suavização). O celular pede ícone de 512 px, centralizado. Então o script:

  1. mede o círculo do anel cinza do logo (ajuste de círculo pelos pontos cinza);
  2. alisa as bordas do "G" laranja, sem redesenhá-lo (borra levemente e amplia);
  3. refaz o anel e o fundo preto como círculos perfeitos (o original é um círculo);
  4. monta cada ícone a partir de uma imagem-mestra grande, o que dá bordas suaves em qualquer tamanho.

Se um dia existir o logo em tamanho grande (PDF/SVG), dá para exportar os ícones direto dele e este
script deixa de ser necessário.
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

PASTA_MARCA = Path(__file__).resolve().parent.parent / "app" / "static" / "marca"
LOGO = PASTA_MARCA / "logo-gloria-fit.png"

# Cores como estão no arquivo oficial do logo.
PRETO = (7, 7, 6)
LARANJA = (241, 83, 32)
CINZA_DO_ANEL = (60, 62, 64)

TAMANHO_MESTRA = 2048  # a mestra é grande; cada ícone é uma redução dela (as bordas ficam suaves)
SUAVIZACAO_DO_G = 1.6  # quanto alisar a borda do "G" laranja, em pixels do arquivo original

# Cada ícone: (arquivo, lado em pixels, quanto do quadrado o círculo ocupa, fundo)
#   fundo None = cantos transparentes; uma cor = quadrado cheio dessa cor.
# O ícone "maskable" é cortado pelo Android em formas variadas (círculo, gota, quadrado arredondado);
# só o círculo central de 80% do lado é garantido, por isso o logo ocupa exatamente 80%.
ICONES = [
    ("icone-192.png", 192, 0.96, None),
    ("icone-512.png", 512, 0.96, None),
    ("icone-maskable-512.png", 512, 0.80, PRETO),
    ("apple-touch-icon.png", 180, 0.86, PRETO),  # o iPhone não gosta de fundo transparente
    ("favicon-32.png", 32, 1.0, None),
]


def _ler_logo():
    a = np.asarray(Image.open(LOGO).convert("RGBA")).astype(int)
    alfa = a[..., 3]
    rgb = a[..., :3]
    opaco = alfa >= 128
    laranja = opaco & (rgb[..., 0] > 150)
    cinza = opaco & ~laranja & (rgb[..., 0] >= 30)
    return opaco, laranja, cinza


def _ajustar_circulo(mascara):
    """Círculo (centro e raio) que melhor passa pelos pontos da máscara (mínimos quadrados, Kasa)."""
    ys, xs = np.nonzero(mascara)
    x = xs + 0.5
    y = ys + 0.5
    matriz = np.column_stack([2 * x, 2 * y, np.ones_like(x)])
    alvo = x**2 + y**2
    (cx, cy, c), *_ = np.linalg.lstsq(matriz, alvo, rcond=None)
    return cx, cy, float(np.sqrt(c + cx**2 + cy**2))


def montar_mestra():
    """Desenha o logo limpo (círculo perfeito + G alisado) em TAMANHO_MESTRA, centro no meio."""
    opaco, laranja, cinza = _ler_logo()
    cx, cy, _ = _ajustar_circulo(cinza)

    # Raios medidos a partir do centro encontrado (em pixels do arquivo original).
    ys, xs = np.mgrid[0 : opaco.shape[0], 0 : opaco.shape[1]]
    r = np.hypot(xs + 0.5 - cx, ys + 0.5 - cy)
    anel_dentro, anel_fora = np.percentile(r[cinza], [1, 99])
    raio_total = float(np.percentile(r[opaco], 99.5))

    escala = (TAMANHO_MESTRA / 2) / raio_total  # pixels da mestra por pixel do original
    m = np.arange(TAMANHO_MESTRA) + 0.5
    rm = np.hypot(m[None, :] - TAMANHO_MESTRA / 2, m[:, None] - TAMANHO_MESTRA / 2) / escala

    quadro = np.zeros((TAMANHO_MESTRA, TAMANHO_MESTRA, 4), dtype=np.uint8)
    quadro[rm <= raio_total] = (*PRETO, 255)
    quadro[(rm >= anel_dentro) & (rm <= anel_fora)] = (*CINZA_DO_ANEL, 255)

    # O "G": máscara laranja alisada, levada para a mestra com o mesmo centro e escala.
    mascara = Image.fromarray((laranja * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(SUAVIZACAO_DO_G))
    mascara = mascara.transform(
        (TAMANHO_MESTRA, TAMANHO_MESTRA),
        Image.AFFINE,
        (1 / escala, 0, cx - TAMANHO_MESTRA / 2 / escala, 0, 1 / escala, cy - TAMANHO_MESTRA / 2 / escala),
        resample=Image.BICUBIC,
    )
    quadro[np.asarray(mascara) >= 128] = (*LARANJA, 255)
    return Image.fromarray(quadro, "RGBA")


def montar_icone(mestra, lado, ocupacao, fundo):
    tela = Image.new("RGBA", (lado, lado), (*fundo, 255) if fundo else (0, 0, 0, 0))
    diametro = round(lado * ocupacao)
    logo = mestra.resize((diametro, diametro), Image.LANCZOS)
    deslocamento = (lado - diametro) // 2
    tela.alpha_composite(logo, (deslocamento, deslocamento))
    return tela.convert("RGB") if fundo else tela


def main():
    mestra = montar_mestra()
    for arquivo, lado, ocupacao, fundo in ICONES:
        montar_icone(mestra, lado, ocupacao, fundo).save(PASTA_MARCA / arquivo, optimize=True)
        print("gerado", arquivo)


if __name__ == "__main__":
    main()
