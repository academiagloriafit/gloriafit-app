// Ficha do aluno: botão "Salvar como treino padrão" em cada treino. O treino vira um treino padrão (aparece em
// "Importar treino" na tela de lançar treino) com o nome que o professor escolher. A regra de verdade está no
// servidor (app/modelos.py); aqui só pedimos e mostramos a resposta.
import { enviarJson, textoDoErro } from "./api.js";
import { LIMITE_NOME_TREINO, limparEspacos, tamanho } from "./treino_modelo.js";

const SEM_REDE =
  "Não consegui confirmar com o servidor se o treino padrão foi guardado (sem resposta ou sem rede). " +
  'Confira em "Importar treino", aba "Treino padrão", antes de tentar de novo.';

for (const barra of document.querySelectorAll(".acoes-treino")) {
  const botao = barra.querySelector(".botao-padrao");
  const formulario = barra.querySelector(".form-padrao-ficha");
  const campo = barra.querySelector(".campo-padrao");
  const guardar = barra.querySelector(".sim-padrao");
  const aviso = barra.querySelector(".aviso-padrao");
  if (!botao || !formulario || !campo || !guardar || !aviso) continue;
  let enviando = false;

  function avisar(texto, erro = false) {
    aviso.textContent = texto;
    aviso.classList.toggle("aviso-erro", erro);
  }

  function fechar() {
    formulario.hidden = true;
    botao.hidden = false;
  }

  async function enviar() {
    if (enviando) return; // clique duplo ou Enter repetido não manda duas vezes
    const nome = limparEspacos(campo.value);
    if (nome === "") {
      avisar("Dê um nome ao treino padrão.", true);
      campo.focus();
      return;
    }
    if (tamanho(nome) > LIMITE_NOME_TREINO) {
      avisar(`O nome tem ${tamanho(nome)} letras; o máximo é ${LIMITE_NOME_TREINO}.`, true);
      campo.focus();
      return;
    }
    enviando = true;
    guardar.disabled = true;
    avisar("Guardando…");
    let resposta;
    try {
      resposta = await enviarJson(`/api/treinos/${encodeURIComponent(guardar.dataset.treino)}/modelo`, { nome });
    } catch {
      avisar(SEM_REDE, true);
      return;
    } finally {
      enviando = false;
      guardar.disabled = false;
    }
    if (resposta.status === 201) {
      fechar();
      avisar(`Guardado como treino padrão "${nome}". Ele aparece em "Importar treino", na tela de lançar treino.`);
      botao.focus();
      return;
    }
    avisar(textoDoErro(resposta, "O servidor não guardou o treino padrão"), true);
    if (resposta.status === 409) campo.focus(); // já existe um padrão com esse nome
  }

  botao.addEventListener("click", () => {
    avisar("");
    botao.hidden = true;
    formulario.hidden = false;
    campo.focus();
    campo.select();
  });
  barra.querySelector(".nao-padrao").addEventListener("click", () => {
    fechar();
    avisar("");
    botao.focus();
  });
  guardar.addEventListener("click", enviar);
  campo.addEventListener("keydown", (evento) => {
    if (evento.key === "Enter" && !evento.isComposing) {
      evento.preventDefault();
      enviar();
    }
  });
}
