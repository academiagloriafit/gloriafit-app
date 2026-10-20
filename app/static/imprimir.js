// Tela de impressão do treino: o botão abre a janela de impressão do navegador.
// Imprimir UMA ficha também conta como "treino feito hoje" (quem não usa o app pede um papel novo a cada treino:
// Thiago, 20/10/2026). O pedido ao servidor sai ANTES da janela de impressão abrir e não a atrasa: se falhar, a
// impressão continua normal e o aviso diz que o treino não foi registrado. A regra (uma vez por ficha por dia) é do servidor.
import { enviarJson } from "./api.js";
import { TEXTO_SEM_REDE, textoDoDesfazer, textoDoRegistro } from "./imprimir_modelo.js";

const botao = document.getElementById("botao-imprimir");
const aviso = document.getElementById("aviso-registro");
const botaoDesfazer = document.getElementById("botao-desfazer");

function mostrar(texto, erro) {
  if (!aviso) return;
  aviso.textContent = texto;
  aviso.classList.toggle("aviso-erro", erro);
}

async function registrar() {
  const url = `/api/treinos/${encodeURIComponent(botao.dataset.treino)}/impressao`;
  const nome = botao.dataset.nome;
  try {
    const resposta = await enviarJson(url, { ficha: Number(botao.dataset.ficha) });
    const resultado = textoDoRegistro(resposta, nome);
    mostrar(resultado.texto, resultado.erro);
    if (botaoDesfazer) botaoDesfazer.hidden = !resultado.podeDesfazer;
  } catch {
    mostrar(TEXTO_SEM_REDE, true);
  }
}

async function desfazer() {
  botaoDesfazer.disabled = true;
  const nome = botao.dataset.nome;
  try {
    const resposta = await enviarJson(`/api/treinos/${encodeURIComponent(botao.dataset.treino)}/impressao/desfazer`, {
      ficha: Number(botao.dataset.ficha),
    });
    const resultado = textoDoDesfazer(resposta, nome);
    mostrar(resultado.texto, resultado.erro);
    if (!resultado.erro) botaoDesfazer.hidden = true;
  } catch {
    mostrar("Não consegui desfazer (sem resposta do servidor). Tente de novo.", true);
  } finally {
    botaoDesfazer.disabled = false;
  }
}

botao.addEventListener("click", () => {
  if (botao.dataset.ficha) registrar(); // sem await: a janela de impressão não espera a rede
  window.print();
});
if (botaoDesfazer) botaoDesfazer.addEventListener("click", desfazer);
