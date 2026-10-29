// Nome de pessoa para a tela (visual novo, 28/10/2026): "MARIANA DE SOUZA" -> "Mariana de Souza".
// Igual ao app/nomes.py do servidor. Só muda o jeito de mostrar: o nome gravado continua como veio do Data4U.

const LIGACOES = new Set(["da", "das", "de", "do", "dos", "e", "di", "du", "del", "la", "le", "van", "von"]);
const SIGLAS = new Set(["ii", "iii", "iv"]);

function palavra(texto, primeira) {
  const minuscula = texto.toLocaleLowerCase("pt-BR");
  if (!primeira && LIGACOES.has(minuscula)) return minuscula;
  if (SIGLAS.has(minuscula.replace(/[.,;:]+$/, ""))) return minuscula.toLocaleUpperCase("pt-BR");
  // hífen e apóstrofo: cada pedaço com maiúscula ("Ana-Maria", "D'Ávila")
  return minuscula.replace(/\p{L}+/gu, (pedaco) => pedaco.charAt(0).toLocaleUpperCase("pt-BR") + pedaco.slice(1));
}

export function nomeDePessoa(texto) {
  if (typeof texto !== "string") return "";
  return texto.split(/\s+/).filter(Boolean).map((p, i) => palavra(p, i === 0)).join(" ");
}

// As iniciais do círculo ao lado do nome: primeira e última palavra que não são "de", "da"...
export function iniciais(texto) {
  const partes = nomeDePessoa(texto).split(" ").filter((p) => p && !LIGACOES.has(p));
  if (!partes.length) return "";
  const primeira = partes[0].charAt(0);
  const ultima = partes.length > 1 ? partes[partes.length - 1].charAt(0) : "";
  return (primeira + ultima).toLocaleUpperCase("pt-BR");
}
