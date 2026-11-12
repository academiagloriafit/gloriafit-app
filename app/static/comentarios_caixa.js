// Caixa de entrada da tela Comentários (visual novo, opção A, 11/11/2026): a lista de prévias à esquerda escolhe qual
// comentário da #lista-comentarios fica à mostra à direita. Ler, responder e marcar continuam com comentarios.js;
// aqui só se acompanha a lista (o comentário lido some na tela "Novos") para manter as prévias iguais a ela.
import { proximoAberto } from "./comentarios_caixa_modelo.js";

const previas = document.getElementById("caixa-previas");
const lista = document.getElementById("lista-comentarios");

if (previas && lista) {
  const idsDaLista = () => [...lista.querySelectorAll("li.comentario")].map((li) => li.dataset.comentario);
  let ids = idsDaLista();
  let aberto = ids[0] ?? null;

  function abrir(id, focar = false) {
    aberto = id;
    for (const li of lista.querySelectorAll("li.comentario")) li.classList.toggle("comentario-aberto", li.dataset.comentario === id);
    for (const botao of previas.querySelectorAll("[data-abrir-comentario]")) {
      botao.setAttribute("aria-pressed", String(botao.dataset.abrirComentario === id));
    }
    if (focar) lista.querySelector(`li.comentario[data-comentario="${CSS.escape(id ?? "")}"] .comentario-texto`)?.scrollIntoView({ block: "nearest" });
  }

  previas.addEventListener("click", (evento) => {
    const botao = evento.target.closest("[data-abrir-comentario]");
    if (botao) abrir(botao.dataset.abrirComentario, true);
  });

  // A lista mudou (comentário lido saiu, ou virou "lido"): a prévia acompanha.
  new MutationObserver(() => {
    const agora = idsDaLista();
    for (const botao of previas.querySelectorAll("[data-abrir-comentario]")) {
      const li = lista.querySelector(`li.comentario[data-comentario="${CSS.escape(botao.dataset.abrirComentario)}"]`);
      if (!li) { botao.closest("li").remove(); continue; }
      const novo = li.classList.contains("comentario-novo");
      botao.classList.toggle("previa-nova", novo);
      if (!novo) botao.querySelector(".previa-ponto")?.remove();
    }
    const proximo = proximoAberto(ids, agora, aberto);
    ids = agora;
    if (proximo !== aberto) abrir(proximo);
    if (!agora.length) previas.closest(".caixa-comentarios").hidden = true;
  }).observe(lista, { childList: true, subtree: true, attributes: true, attributeFilter: ["class"] });

  lista.classList.add("caixa-pronta");
  abrir(aberto);
}
