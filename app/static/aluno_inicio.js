// Tela /aluno: o botão Sair.
import { enviarJson } from "./api.js";
import { MENSAGEM_SEM_REDE } from "./aluno_modelo.js";

const botao = document.getElementById("botao-sair");
const aviso = document.getElementById("aviso-sair");

botao.addEventListener("click", async () => {
  if (botao.disabled) return;
  botao.disabled = true;
  try {
    const { status } = await enviarJson("/api/aluno/sair", {});
    if (status === 200) {
      window.location.assign("/aluno/entrar");
      return; // o botão continua travado: a página está sendo trocada
    }
    aviso.textContent = `Não consegui sair (código ${status}). Tente de novo.`;
  } catch {
    aviso.textContent = MENSAGEM_SEM_REDE;
  }
  aviso.classList.add("aviso-erro");
  botao.disabled = false;
});
