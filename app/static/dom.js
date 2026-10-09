// Ajudante para montar pedaços de tela sem innerHTML (usado por montar.js e importar_treino.js).
//
// el("button", { classe: "botao-escuro", texto: "Salvar", aoClicar: fazer }, filho1, filho2)
// Texto sempre via textContent / nó de texto: nada do que vem do banco ou do teclado é interpretado
// como HTML. `false`, `null` e `undefined` entre os filhos são ignorados (dá para usar `condicao && el(...)`).
export function el(tag, props = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [chave, valor] of Object.entries(props)) {
    if (chave === "texto") e.textContent = valor;
    else if (chave === "classe") e.className = valor;
    else if (chave === "aoClicar") e.addEventListener("click", valor);
    else if (chave === "aoDigitar") e.addEventListener("input", valor);
    else if (chave === "aoMudar") e.addEventListener("change", valor);
    else if (valor === true) e.setAttribute(chave, "");
    else if (valor !== false && valor != null) e.setAttribute(chave, valor);
  }
  filhos.flat().forEach((f) => f && e.append(f));
  return e;
}
