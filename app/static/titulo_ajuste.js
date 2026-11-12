// Título grande que encolhe até caber: usado no nome do exercício no app do aluno.
// Sem isso, uma palavra comprida ("DESENVOLVIMENTO") não cabia na largura do celular e era
// cortada no meio ("DESENVOLVIM / ENTO"). Agora a letra diminui até a palavra inteira caber;
// só se nem no tamanho mínimo couber é que a palavra pode quebrar.

// Parte pura (testável sem navegador): do maior tamanho para o menor, de `passo` em `passo`,
// devolve o primeiro em que `cabe(tamanho)` diz que sim. Se nenhum couber, devolve null.
export function tamanhoQueCabe(maior, menor, passo, cabe) {
  for (let tamanho = maior; tamanho >= menor; tamanho -= passo) {
    if (cabe(tamanho)) return tamanho;
  }
  return null;
}

// Parte da tela. `elemento` já precisa estar na página (senão não dá para medir).
// O tamanho vai numa variável CSS (--tamanho-titulo): a política de segurança da página (CSP)
// bloqueia style="" no HTML, mas aceita mudar a variável pelo JavaScript.
export function ajustarTitulo(elemento, { maior, menor, passo = 2 }) {
  if (!elemento || !elemento.isConnected) return;
  elemento.classList.remove("titulo-sem-espaco");
  const cabe = (tamanho) => {
    elemento.style.setProperty("--tamanho-titulo", tamanho + "px");
    return elemento.scrollWidth <= elemento.clientWidth + 1;
  };
  const tamanho = tamanhoQueCabe(maior, menor, passo, cabe);
  if (tamanho === null) {
    elemento.style.setProperty("--tamanho-titulo", menor + "px");
    elemento.classList.add("titulo-sem-espaco"); // aí sim a palavra pode quebrar
  }
}
