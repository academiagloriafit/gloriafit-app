// Cronômetro de descanso da tela /aluno (pedido do Thiago, 22/10/2026: "descanso com toque").
// O aluno toca em "Descansar 1 min 30 s" num exercício; uma barra fica no pé da tela contando, e no fim toca um aviso
// (som + vibração, onde o celular deixa). Só um descanso por vez: tocar em outro recomeça.
//
// A conta é pelo RELÓGIO (hora em que o descanso acaba), não por tique: se o celular segurar o JavaScript em segundo plano,
// ao voltar o tempo certo aparece na hora. Com a tela bloqueada o celular pode não tocar o aviso (limite do navegador);
// por isso a tela é mantida acesa enquanto o descanso corre (quando o celular permite).
import { el } from "./dom.js";
import { TEXTO_DESCANSO_ACABOU, segundosRestantes, textoDoTempo } from "./aluno_modelo.js";

let barra = null;
let rotulo = null;
let tempo = null;
let botao = null;
let anuncio = null;
let fimEmMs = 0;
let relogio = null;
let travaDeTela = null;
let audio = null;

function montarBarra() {
  rotulo = el("span", { classe: "meu-descanso-rotulo" });
  tempo = el("span", { classe: "meu-descanso-tempo", role: "timer", "aria-live": "off" });
  botao = el("button", { type: "button", classe: "botao-link meu-descanso-botao", texto: "Parar", aoClicar: pararDescanso });
  // O tempo muda a cada segundo (o leitor de tela não deve ler cada um); só o fim é anunciado, por aqui.
  anuncio = el("p", { classe: "so-leitor", role: "status" });
  barra = el("div", { classe: "meu-descanso", role: "region", "aria-label": "Descanso entre as séries", hidden: true }, el("div", { classe: "meu-descanso-texto" }, rotulo, tempo), botao, anuncio);
  document.body.append(barra);
}

// O navegador só deixa o som começar depois de um toque do aluno: por isso isto roda DENTRO do toque que inicia o descanso.
function prepararSom() {
  try {
    const Contexto = window.AudioContext || window.webkitAudioContext;
    if (!Contexto) return;
    audio ??= new Contexto();
    if (audio.state === "suspended") audio.resume();
  } catch {
    /* sem som: a barra e a vibração avisam */
  }
}

function tocarAviso() {
  try {
    if (audio) {
      const comeco = audio.currentTime;
      for (let i = 0; i < 3; i += 1) {
        const inicio = comeco + i * 0.35;
        const oscilador = audio.createOscillator();
        const volume = audio.createGain();
        oscilador.type = "sine";
        oscilador.frequency.value = 880;
        volume.gain.setValueAtTime(0.0001, inicio);
        volume.gain.exponentialRampToValueAtTime(0.4, inicio + 0.02);
        volume.gain.exponentialRampToValueAtTime(0.0001, inicio + 0.25);
        oscilador.connect(volume).connect(audio.destination);
        oscilador.start(inicio);
        oscilador.stop(inicio + 0.3);
      }
    }
  } catch {
    /* sem som */
  }
  try {
    navigator.vibrate?.([300, 150, 300, 150, 600]);
  } catch {
    /* sem vibração (o iPhone não tem) */
  }
}

async function manterTelaAcesa() {
  try {
    if (!travaDeTela && navigator.wakeLock && document.visibilityState === "visible") {
      travaDeTela = await navigator.wakeLock.request("screen");
      travaDeTela.addEventListener("release", () => {
        travaDeTela = null;
      });
    }
  } catch {
    /* o celular não deixou: a tela pode apagar sozinha */
  }
}

function soltarTela() {
  try {
    travaDeTela?.release();
  } catch {
    /* já tinha sido solta */
  }
  travaDeTela = null;
}

function parouDeContar() {
  clearInterval(relogio);
  relogio = null;
  soltarTela();
}

function atualizar() {
  const falta = segundosRestantes(fimEmMs, Date.now());
  tempo.textContent = textoDoTempo(falta);
  if (falta > 0) return;
  parouDeContar();
  barra.classList.add("meu-descanso-acabou");
  rotulo.textContent = TEXTO_DESCANSO_ACABOU;
  botao.textContent = "Fechar";
  anuncio.textContent = TEXTO_DESCANSO_ACABOU;
  tocarAviso();
}

// Começa (ou recomeça) o descanso. `segundos` vem do intervalo que o professor escreveu no exercício.
export function iniciarDescanso(segundos, nomeDoExercicio) {
  if (!Number.isFinite(segundos) || segundos <= 0) return;
  if (!barra) montarBarra();
  prepararSom();
  parouDeContar();
  fimEmMs = Date.now() + segundos * 1000;
  barra.classList.remove("meu-descanso-acabou");
  barra.hidden = false;
  document.body.classList.add("com-descanso");
  rotulo.textContent = `Descanso · ${nomeDoExercicio}`;
  botao.textContent = "Parar";
  anuncio.textContent = "";
  atualizar();
  relogio = setInterval(atualizar, 250);
  manterTelaAcesa();
}

// "Parar" (no meio) ou "Fechar" (depois do aviso): some com a barra.
export function pararDescanso() {
  if (!barra) return;
  parouDeContar();
  barra.hidden = true;
  document.body.classList.remove("com-descanso"); // devolve o espaço que a barra tomava no pé da página
  anuncio.textContent = "";
}

// O celular solta a trava de tela quando o app sai de cena; ao voltar com o descanso ainda correndo, pede de novo e corrige o tempo.
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState !== "visible" || !relogio) return;
  atualizar();
  if (relogio) manterTelaAcesa();
});
