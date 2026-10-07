// Ficha do aluno: salvar o número de WhatsApp corrigido pela recepção.
import { enviarJson } from "./api.js";

const raiz = document.querySelector("[data-aluno]");
const campo = document.getElementById("whatsapp");
const botao = document.getElementById("salvar-whatsapp");
const aviso = document.getElementById("aviso-whatsapp");

let salvando = false;

function mostrar(texto, erro) {
  aviso.textContent = texto;
  aviso.classList.toggle("aviso-erro", erro);
  if (erro) campo.setAttribute("aria-invalid", "true");
  else campo.removeAttribute("aria-invalid");
}

async function salvar() {
  if (salvando) return; // clique duplo não manda duas vezes
  salvando = true;
  botao.disabled = true;
  mostrar("Salvando…", false);

  try {
    const { status, corpo } = await enviarJson(
      `/api/alunos/${encodeURIComponent(raiz.dataset.aluno)}/whatsapp`,
      { whatsapp: campo.value },
    );
    if (status === 200 && corpo && typeof corpo.whatsapp === "string") {
      campo.value = corpo.whatsapp; // o servidor devolve o número já formatado
      mostrar("Número salvo. Já vale para o código de acesso.", false);
    } else {
      const mensagem =
        corpo && typeof corpo.erro === "string"
          ? corpo.erro
          : `O servidor devolveu um erro (código ${status}). O número não foi salvo.`;
      mostrar(mensagem, true);
    }
  } catch {
    mostrar(
      "Não consegui falar com o servidor (sem resposta ou sem rede). Confira a rede e tente de novo; não sei se o número foi salvo.",
      true,
    );
  } finally {
    salvando = false;
    botao.disabled = false;
  }
}

botao.addEventListener("click", salvar);
campo.addEventListener("keydown", (evento) => {
  if (evento.key === "Enter" && !evento.isComposing) {
    evento.preventDefault();
    salvar();
  }
});
