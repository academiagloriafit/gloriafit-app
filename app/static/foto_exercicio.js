// Imagem pequena do exercício (visual novo da tela de lançar treino, 11/11/2026).
// O servidor (app/fotos_exercicios.py) diz qual imagem usar: a ilustração (static/ilustracoes/<nome>.jpg, gerada no Canva)
// ou, se o exercício ainda não tem ilustração, a foto de "como fazer" (static/exercicios/<nome>_0.jpg).
// Exercício sem nenhuma das duas mostra o desenho de um halter no lugar.

// Só estes dois formatos de caminho são aceitos: assim um texto estranho nunca vira endereço de outro lugar (ex.: "../").
const CAMINHO_VALIDO = /^(ilustracoes\/[A-Za-z0-9_-]{1,80}\.jpg|exercicios\/[A-Za-z0-9_-]{1,80}_0\.jpg)$/;

// O endereço da imagem, ou null quando não há imagem (ou o caminho não é válido).
export function caminhoDaMiniatura(pasta, caminho) {
  if (typeof pasta !== "string" || !pasta.endsWith("/")) return null;
  if (typeof caminho !== "string" || !CAMINHO_VALIDO.test(caminho)) return null;
  return pasta + caminho;
}

// Lê o mapa {id do exercício: caminho} que a página entrega num atributo. Texto quebrado vira mapa vazio (sem imagens).
export function lerMapaDeFotos(texto) {
  try {
    const mapa = JSON.parse(texto || "{}");
    return mapa && typeof mapa === "object" && !Array.isArray(mapa) ? mapa : {};
  } catch {
    return {};
  }
}

// As imagens de um exercício, como vieram do servidor: uma lista (combinado = uma por parte) ou, nos dados antigos, um texto só.
export function listaDeImagens(valor) {
  const lista = Array.isArray(valor) ? valor : valor ? [valor] : [];
  return lista.filter((c) => typeof c === "string" && CAMINHO_VALIDO.test(c)).slice(0, 3);
}

// O elemento da miniatura: as imagens lado a lado (combinado), ou o halter quando não há. As imagens são decorativas
// (alt vazio): o nome do exercício já está escrito ao lado. `classeExtra`: tamanho maior na tela do exercício do aluno.
export function criarMiniatura(pasta, valor, classeExtra = "") {
  const caixa = document.createElement("span");
  caixa.className = "miniatura-exercicio" + (classeExtra ? " " + classeExtra : "");
  const enderecos = listaDeImagens(valor).map((c) => caminhoDaMiniatura(pasta, c)).filter(Boolean);
  if (enderecos.length > 1) caixa.classList.add("miniatura-combinada");
  for (const endereco of enderecos) {
    const img = document.createElement("img");
    img.src = endereco;
    img.alt = "";
    img.loading = "lazy";
    img.decoding = "async";
    // imagem que não carregou: some; sem nenhuma, volta o halter
    img.addEventListener("error", () => { img.remove(); if (!caixa.querySelector("img")) caixa.classList.add("sem-foto"); });
    caixa.append(img);
  }
  if (!enderecos.length) caixa.classList.add("sem-foto");
  return caixa;
}
