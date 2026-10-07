// Tela /autorizar: manda o código digitado ao servidor e, se for aceito, abre o app.
import { enviarJson } from "./api.js";
import { MENSAGEM_SEM_REDE, descreverResposta } from "./autorizar_modelo.js";

const formulario = document.getElementById("form-autorizar");
const campo = document.getElementById("codigo");
const botao = document.getElementById("botao-autorizar");
const aviso = document.getElementById("aviso-autorizar");

let enviando = false;

function mostrar(texto, erro) {
  aviso.textContent = texto; // textContent: o texto nunca é interpretado como HTML
  aviso.classList.toggle("aviso-erro", erro);
  if (erro) campo.setAttribute("aria-invalid", "true");
  else campo.removeAttribute("aria-invalid");
}

formulario.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  if (enviando) return; // clique duplo não manda duas vezes
  enviando = true;
  botao.disabled = true;
  mostrar("Conferindo…", false);

  try {
    const { status, corpo } = await enviarJson("/api/autorizar", { codigo: campo.value });
    const resultado = descreverResposta(status, corpo);
    mostrar(resultado.mensagem, !resultado.ok);
    if (resultado.ok) {
      window.location.assign("/alunos");
      return; // o botão continua travado: a página está sendo trocada
    }
    campo.select();
  } catch {
    mostrar(MENSAGEM_SEM_REDE, true);
  }
  enviando = false;
  botao.disabled = false;
});
