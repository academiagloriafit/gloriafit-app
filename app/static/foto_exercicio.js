// Foto pequena do exercício (visual novo da tela de lançar treino, 11/11/2026).
// As fotos são as de "como fazer" que já estão no app (base aberta free-exercise-db, domínio público):
// app/static/exercicios/<nome>_0.jpg. Exercício sem foto mostra o desenho de um halter no lugar.

// Mesmo formato que o servidor aceita (app/fotos_exercicios.py): só letras, números, _ e -. Assim um nome estranho
// nunca vira um caminho para outro lugar (ex.: "../").
const NOME_VALIDO = /^[A-Za-z0-9_-]{1,80}$/;

// O endereço da foto, ou null quando não há foto (ou o nome não é válido).
export function caminhoDaMiniatura(pasta, foto) {
  if (typeof pasta !== "string" || !pasta.endsWith("/")) return null;
  if (typeof foto !== "string" || !NOME_VALIDO.test(foto)) return null;
  return `${pasta}${foto}_0.jpg`;
}

// Lê o mapa {id do exercício: foto} que a página entrega num atributo. Texto quebrado vira mapa vazio (sem fotos).
export function lerMapaDeFotos(texto) {
  try {
    const mapa = JSON.parse(texto || "{}");
    return mapa && typeof mapa === "object" && !Array.isArray(mapa) ? mapa : {};
  } catch {
    return {};
  }
}

// O elemento da miniatura: a foto, ou o halter quando não há foto. A imagem é decorativa (alt vazio):
// o nome do exercício já está escrito ao lado.
export function criarMiniatura(pasta, foto) {
  const caixa = document.createElement("span");
  caixa.className = "miniatura-exercicio";
  const caminho = caminhoDaMiniatura(pasta, foto);
  if (caminho) {
    const img = document.createElement("img");
    img.src = caminho;
    img.alt = "";
    img.loading = "lazy";
    img.decoding = "async";
    // foto que não carregou: volta para o halter
    img.addEventListener("error", () => { img.remove(); caixa.classList.add("sem-foto"); });
    caixa.append(img);
  } else {
    caixa.classList.add("sem-foto");
  }
  return caixa;
}
