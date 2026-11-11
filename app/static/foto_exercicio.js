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

// O elemento da miniatura: a imagem, ou o halter quando não há. A imagem é decorativa (alt vazio):
// o nome do exercício já está escrito ao lado.
export function criarMiniatura(pasta, caminho) {
  const caixa = document.createElement("span");
  caixa.className = "miniatura-exercicio";
  const endereco = caminhoDaMiniatura(pasta, caminho);
  if (endereco) {
    const img = document.createElement("img");
    img.src = endereco;
    img.alt = "";
    img.loading = "lazy";
    img.decoding = "async";
    // imagem que não carregou: volta para o halter
    img.addEventListener("error", () => { img.remove(); caixa.classList.add("sem-foto"); });
    caixa.append(img);
  } else {
    caixa.classList.add("sem-foto");
  }
  return caixa;
}
