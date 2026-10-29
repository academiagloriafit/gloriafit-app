// Menu lateral das telas do aluno (29/10/2026): abre e fecha a gaveta e cuida do "Sair".
// A gaveta é um <dialog>: o navegador já cuida do fundo escurecido, do Esc e de prender o foco dentro dela.
import { enviarJson } from "./api.js";
import { MENSAGEM_SEM_REDE } from "./aluno_modelo.js";

const gaveta = document.getElementById("menu-aluno");
const abrir = document.getElementById("abrir-menu-aluno");
const fechar = document.getElementById("fechar-menu-aluno");
const botaoSair = document.getElementById("botao-sair");
const avisoSair = document.getElementById("aviso-sair");

if (gaveta && abrir) {
  abrir.addEventListener("click", () => gaveta.showModal());
  fechar.addEventListener("click", () => gaveta.close());
  // toque no fundo escuro (fora da gaveta) fecha
  gaveta.addEventListener("click", (evento) => {
    if (evento.target === gaveta) gaveta.close();
  });
  gaveta.addEventListener("close", () => abrir.focus());
}

if (botaoSair) {
  botaoSair.addEventListener("click", async () => {
    if (botaoSair.disabled) return;
    botaoSair.disabled = true;
    avisoSair.textContent = "";
    try {
      const { status } = await enviarJson("/api/aluno/sair", {});
      if (status === 200) {
        window.location.assign("/aluno/entrar");
        return; // o botão continua travado: a página está sendo trocada
      }
      avisoSair.textContent = `Não consegui sair (código ${status}). Tente de novo.`;
    } catch {
      avisoSair.textContent = MENSAGEM_SEM_REDE;
    }
    avisoSair.classList.add("aviso-erro");
    botaoSair.disabled = false;
  });
}
