// Telas do professor com comentários dos alunos: a página "Comentários" e o quadro na ficha do aluno.
// Aqui só se marca como lido (um comentário, ou todos de um aluno) e se atualiza o que está na tela.
// O texto dos comentários vem pronto do servidor, já escapado: este arquivo nunca monta HTML a partir dele.
import { enviarJson } from "./api.js";
import { el } from "./dom.js";
import {
  MENSAGEM_SEM_REDE,
  descreverLeitura,
  textoDoFiltroNovos,
  textoDoResumoDaFicha,
  textoDoTotal,
} from "./comentarios_modelo.js";

const tela = document.getElementById("tela-comentarios"); // só existe na página "Comentários"
const quadroDaFicha = document.getElementById("comentarios-do-aluno"); // só existe na ficha de quem tem comentário
const menu = document.getElementById("menu-comentarios");
const lista = document.getElementById("lista-comentarios");

// O número vermelho do menu: mostra, troca ou tira.
function mostrarContadorDoMenu(naoLidos) {
  if (!menu || naoLidos === null) return;
  menu.querySelector(".contador-menu")?.remove();
  if (naoLidos > 0) {
    menu.append(
      el(
        "span",
        { classe: "contador-menu", "data-comentarios-novos": String(naoLidos) },
        String(naoLidos),
        el("span", { classe: "so-leitor", texto: " sem ler" }),
      ),
    );
  }
}

// Troca o botão "Marcar como lido" por "Lido" e tira o destaque.
function virarLido(item) {
  item.classList.remove("comentario-novo");
  item.removeAttribute("data-comentario-novo");
  const botao = item.querySelector("[data-marcar-lido]");
  if (botao) botao.replaceWith(el("span", { classe: "comentario-lido", texto: "Lido" }));
}

function mostrarErro(local, mensagem) {
  if (local) local.textContent = mensagem;
}

// Depois de ler um: na página "Comentários" (só novos) a linha some; em "Todos" ela fica, como lida.
function atualizarTelaDepoisDeLer(item, naoLidos) {
  if (tela && tela.dataset.soNovos === "1") {
    item.remove();
    const restantes = lista.querySelectorAll("li.comentario").length;
    const resumo = document.getElementById("resumo-comentarios");
    if (resumo && naoLidos !== null) resumo.textContent = textoDoTotal(naoLidos, restantes);
    const vazio = document.getElementById("comentarios-vazio");
    if (vazio) vazio.hidden = restantes > 0;
  } else {
    virarLido(item);
  }
  const filtro = tela && tela.querySelector(".filtro-comentarios a");
  if (filtro && naoLidos !== null) filtro.textContent = textoDoFiltroNovos(naoLidos);
  mostrarContadorDoMenu(naoLidos);
}

async function marcarUm(botao) {
  if (botao.disabled) return;
  const item = botao.closest("li.comentario");
  const aviso = item.querySelector("[data-erro-do-comentario]");
  mostrarErro(aviso, "");
  botao.disabled = true;
  try {
    const { status, corpo } = await enviarJson(`/api/comentarios/${encodeURIComponent(botao.dataset.marcarLido)}/lido`, {});
    const resultado = descreverLeitura(status, corpo);
    if (resultado.tipo === "ok") {
      atualizarTelaDepoisDeLer(item, resultado.naoLidos);
      if (quadroDaFicha) umLidoNaFicha();
      return;
    }
    mostrarErro(aviso, resultado.mensagem);
  } catch {
    mostrarErro(aviso, MENSAGEM_SEM_REDE);
  }
  botao.disabled = false;
}

// O resumo do quadro da ficha ("2 sem ler · 5 no total"). Os números vêm do servidor (data-sem-ler e data-total):
// o quadro mostra só os 30 mais novos, então contar as linhas da tela estaria errado para quem tem muitos comentários.
function definirSemLerDaFicha(semLer) {
  const resumo = document.getElementById("resumo-comentarios-aluno");
  if (resumo) {
    resumo.dataset.semLer = String(semLer);
    resumo.textContent = textoDoResumoDaFicha(semLer, Number(resumo.dataset.total));
  }
  // O botão vale para os comentários que estão na tela: some quando não resta nenhum sem ler ali.
  if (semLer === 0 || !lista.querySelector("li[data-comentario-novo]")) {
    quadroDaFicha.querySelector("[data-marcar-todos-do-aluno]")?.remove();
  }
}

function umLidoNaFicha() {
  const resumo = document.getElementById("resumo-comentarios-aluno");
  if (resumo) definirSemLerDaFicha(Math.max(0, Number(resumo.dataset.semLer) - 1));
}

async function marcarTodosDoAluno(botao) {
  if (botao.disabled) return;
  const aviso = document.getElementById("erro-comentarios-aluno");
  mostrarErro(aviso, "");
  // Só os comentários que estão na tela agora: o que o aluno mandou depois de a ficha abrir (ou os antigos que o quadro
  // não mostra) não pode virar "lido" sem ninguém ter lido.
  const ids = [...lista.querySelectorAll("li[data-comentario-novo]")].map((li) => Number(li.dataset.comentario));
  if (!ids.length) return;
  botao.disabled = true;
  try {
    const { status, corpo } = await enviarJson(
      `/api/alunos/${encodeURIComponent(botao.dataset.marcarTodosDoAluno)}/comentarios/lidos`,
      { ids },
    );
    const resultado = descreverLeitura(status, corpo);
    if (resultado.tipo === "ok") {
      lista.querySelectorAll("li[data-comentario-novo]").forEach(virarLido);
      const resumo = document.getElementById("resumo-comentarios-aluno");
      const semLer = Number(resumo?.dataset.semLer ?? 0);
      definirSemLerDaFicha(Math.max(0, semLer - (resultado.marcados ?? ids.length)));
      botao.remove(); // o que estava na tela foi lido; sobrou só o que a tela não mostra (o aviso acima explica)
      mostrarContadorDoMenu(resultado.naoLidos);
      return;
    }
    mostrarErro(aviso, resultado.mensagem);
  } catch {
    mostrarErro(aviso, MENSAGEM_SEM_REDE);
  }
  botao.disabled = false;
}

document.addEventListener("click", (evento) => {
  const botao = evento.target.closest("button");
  if (!botao) return;
  if (botao.dataset.marcarLido !== undefined) marcarUm(botao);
  else if (botao.dataset.marcarTodosDoAluno !== undefined) marcarTodosDoAluno(botao);
});
