// Foto ampliada (pedido do Thiago, 29/10/2026): clicar na foto de um aluno (busca, ficha, pendências, quem sumiu) abre a foto grande
// no meio da tela, para ver quem é a pessoa. Fecha com Esc, com o botão "Fechar" ou clicando fora da foto.
// A foto grande vem de /alunos/<id>/foto?tamanho=grande (só abre em computador autorizado, como a miniatura).
import { enderecoDaFotoGrande, textoDaLegenda } from "./foto_grande_modelo.js";

let dialogo = null;

function montarDialogo() {
  const caixa = document.createElement("dialog");
  caixa.className = "foto-ampliada";
  caixa.setAttribute("aria-label", "Foto do aluno");
  const figura = document.createElement("figure");
  const imagem = document.createElement("img");
  imagem.alt = "";
  const legenda = document.createElement("figcaption");
  const fechar = document.createElement("button");
  fechar.type = "button";
  fechar.className = "botao-link foto-ampliada-fechar";
  fechar.textContent = "Fechar";
  fechar.addEventListener("click", () => caixa.close());
  figura.append(imagem, legenda);
  caixa.append(figura, fechar);
  // clicar no fundo escuro (fora da foto) fecha
  caixa.addEventListener("click", (evento) => {
    if (evento.target === caixa) caixa.close();
  });
  document.body.append(caixa);
  return caixa;
}

function abrir(miniatura) {
  const endereco = enderecoDaFotoGrande(miniatura.getAttribute("src"));
  if (!endereco) return;
  dialogo = dialogo || montarDialogo();
  const imagem = dialogo.querySelector("img");
  const nome = textoDaLegenda(miniatura.dataset.nome);
  imagem.src = endereco;
  imagem.alt = "Foto de " + nome;
  dialogo.querySelector("figcaption").textContent = nome; // textContent: o nome nunca vira HTML
  dialogo.showModal();
  dialogo.querySelector(".foto-ampliada-fechar").focus();
}

// Um ouvinte só, na página inteira (pega também as fotos que a busca desenha depois). Na fase de captura e com preventDefault:
// a foto fica dentro do link da linha, e o clique na foto abre a foto em vez de abrir a ficha.
document.addEventListener(
  "click",
  (evento) => {
    const miniatura = evento.target instanceof Element ? evento.target.closest("img.avatar-foto") : null;
    if (!miniatura) return;
    evento.preventDefault();
    evento.stopPropagation();
    abrir(miniatura);
  },
  true,
);
