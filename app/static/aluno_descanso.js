// Cronômetro de descanso da tela /aluno (pedido do Thiago, 22/10/2026: "descanso com toque").
// O aluno digita os segundos na tela do exercício e toca em "Descansar"; uma barra fica no pé da tela contando, e no fim toca um aviso
// (som + vibração, onde o celular deixa). Só um descanso por vez: tocar em outro recomeça.
//
// A conta é pelo RELÓGIO (hora em que o descanso acaba), não por tique: se o celular segurar o JavaScript em segundo plano,
// ao voltar o tempo certo aparece na hora. Com a tela bloqueada o celular pode não tocar o aviso (limite do navegador);
// por isso a tela é mantida acesa enquanto o descanso corre (quando o celular permite).
import { el } from "./dom.js";
import { SEGUNDOS_A_MAIS_NO_DESCANSO, TEXTO_DESCANSO_ACABOU, segundosRestantes, textoDoTempo } from "./aluno_modelo.js";

let barra = null;
let rotulo = null;
let tempo = null;
let botao = null;
let botaoMais = null;
let anuncio = null;
let fimEmMs = 0;
let relogio = null;
let travaDeTela = null;
let audio = null;

function montarBarra() {
  rotulo = el("span", { classe: "meu-descanso-rotulo" });
  tempo = el("span", { classe: "meu-descanso-tempo", role: "timer", "aria-live": "off" });
  botao = el("button", { type: "button", classe: "botao-link meu-descanso-botao", texto: "Parar", aoClicar: pararDescanso });
  botaoMais = el("button", {
    type: "button",
    classe: "botao-link meu-descanso-botao",
    texto: `+${SEGUNDOS_A_MAIS_NO_DESCANSO} s`,
    "aria-label": `Somar ${SEGUNDOS_A_MAIS_NO_DESCANSO} segundos ao descanso`,
    aoClicar: somarAoDescanso,
  });
  // O tempo muda a cada segundo (o leitor de tela não deve ler cada um); só o fim é anunciado, por aqui.
  anuncio = el("p", { classe: "so-leitor", role: "status" });
  barra = el("div", { classe: "meu-descanso", role: "region", "aria-label": "Descanso entre as séries", hidden: true }, el("div", { classe: "meu-descanso-texto" }, rotulo, tempo), el("div", { classe: "meu-descanso-botoes" }, botaoMais, botao), anuncio);
  document.body.append(barra);
}

// O navegador só deixa o som começar depois de um toque do aluno: por isso isto roda DENTRO do toque que inicia o descanso.
function prepararSom() {
  try {
    const Contexto = window.AudioContext || window.webkitAudioContext;
    if (!Contexto) return;
    audio ??= new Contexto();
    if (audio.state === "suspended") audio.resume()?.catch?.(() => {});
  } catch {
    /* sem som: a barra e a vibração avisam */
  }
}

function tocarAviso() {
  try {
    if (audio) {
      // No iPhone o som pode ficar suspenso quando a tela bloqueia ou o app sai de cena: acorda antes de tocar.
      if (audio.state !== "running") audio.resume()?.catch?.(() => {});
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

let pedindoATrava = false;

async function manterTelaAcesa() {
  if (travaDeTela || pedindoATrava || !navigator.wakeLock || document.visibilityState !== "visible") return;
  pedindoATrava = true;
  try {
    const trava = await navigator.wakeLock.request("screen");
    if (!relogio) {
      // O descanso acabou (ou foi parado) enquanto o celular decidia: solta já, ninguém mais vai soltar.
      trava.release().catch(() => {});
      return;
    }
    travaDeTela = trava;
    trava.addEventListener("release", () => {
      if (travaDeTela === trava) travaDeTela = null; // só zera se ainda é esta trava (uma mais nova pode ter entrado no lugar)
    });
  } catch {
    /* o celular não deixou: a tela pode apagar sozinha */
  } finally {
    pedindoATrava = false;
  }
}

function soltarTela() {
  const trava = travaDeTela;
  travaDeTela = null;
  try {
    trava?.release()?.catch?.(() => {});
  } catch {
    /* já tinha sido solta */
  }
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
  botaoMais.hidden = true; // acabou: não há o que somar (para mais tempo, é só tocar em "Descansar" de novo)
  anuncio.textContent = TEXTO_DESCANSO_ACABOU;
  tocarAviso();
}

// Começa (ou recomeça) o descanso. `segundos` é o que o aluno digitou (já conferido por `conferirDescanso`).
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
  botaoMais.hidden = false;
  anuncio.textContent = "";
  atualizar();
  relogio = setInterval(atualizar, 250);
  manterTelaAcesa();
}

// "+15 s": soma tempo ao descanso que está correndo (a conta continua pelo relógio).
function somarAoDescanso() {
  if (!relogio) return;
  fimEmMs += SEGUNDOS_A_MAIS_NO_DESCANSO * 1000;
  atualizar();
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
  if (document.visibilityState !== "visible") return;
  if (audio && audio.state !== "running" && !barra?.hidden) audio.resume()?.catch?.(() => {}); // volta o som se o celular o tinha suspendido
  if (!relogio) return;
  atualizar();
  if (relogio) manterTelaAcesa();
});
