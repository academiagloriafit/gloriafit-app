// Telas do professor com comentários dos alunos: a página "Comentários" e o quadro na ficha do aluno.
// Aqui só se marca como lido (um comentário, ou todos de um aluno) e se atualiza o que está na tela.
// O texto dos comentários vem pronto do servidor, já escapado: este arquivo nunca monta HTML a partir dele.
import { MENSAGEM_NAO_AUTORIZADO, enviarJson } from "./api.js";
import { el } from "./dom.js";
import {
  MENSAGEM_SEM_REDE,
  descreverLeitura,
  descreverResposta,
  estourouOLimiteDaResposta,
  LIMITE_DO_NOME,
  pedidoDaResposta,
  respostaPronta,
  textoDoContadorDaResposta,
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
  // Com a caixa de resposta aberta a linha não some (senão o texto que o professor estava escrevendo se perderia): vira "Lido".
  const respondendo = item.querySelector("[data-responder-area]")?.childElementCount > 0;
  if (tela && tela.dataset.soNovos === "1" && !respondendo) {
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

// ------------------------------------------------------------------ responder ao aluno

// O último nome digitado NESTA página, só para não digitar de novo a cada resposta seguinte. Não é guardado em lugar
// nenhum: ao recarregar a página começa vazio (o computador da recepção é de todos os professores).
let nomeDoProfessor = "";

// A resposta já enviada, no mesmo desenho que o servidor monta (texto sempre via textContent).
function desenharResposta(respondidoPor, quando, texto) {
  return el(
    "div",
    { classe: "comentario-resposta", tabindex: "-1" }, // tabindex -1: o foco vai para cá quando o botão "Enviar resposta" some
    el("p", {
      classe: "comentario-resposta-cabecalho",
      texto: `Respondido por ${respondidoPor} · ${quando} · o aluno ainda não viu`,
    }),
    el("p", { classe: "comentario-resposta-texto", texto }),
  );
}

// Depois de responder: o comentário vira "lido" (responder já conta como ler) e os números se acertam. A linha NÃO some
// da página de "Novos", para o professor ver a resposta que acabou de mandar.
function atualizarTelaDepoisDeResponder(item, naoLidos) {
  const eraNovo = item.hasAttribute("data-comentario-novo");
  virarLido(item);
  mostrarContadorDoMenu(naoLidos);
  const filtro = tela && tela.querySelector(".filtro-comentarios a");
  if (filtro && naoLidos !== null) filtro.textContent = textoDoFiltroNovos(naoLidos);
  if (eraNovo && quadroDaFicha) umLidoNaFicha();
}

function abrirFormularioDeResposta(botao) {
  const item = botao.closest("li.comentario");
  const id = botao.dataset.responder;
  const area = item.querySelector("[data-responder-area]");
  if (area.childElementCount) {
    area.querySelector("textarea")?.focus();
    return;
  }
  const aviso = item.querySelector("[data-erro-do-comentario]");
  mostrarErro(aviso, "");

  const campoNome = el("input", {
    type: "text",
    id: `responder-nome-${id}`,
    maxlength: String(LIMITE_DO_NOME),
    autocomplete: "off",
  });
  campoNome.value = nomeDoProfessor;
  const campoTexto = el("textarea", { id: `responder-texto-${id}`, rows: "3" });
  const contador = el("p", { classe: "comentario-contador", texto: textoDoContadorDaResposta("") });
  const erro = el("p", { classe: "aviso-campo aviso-erro", role: "alert" });
  const enviar = el("button", { type: "button", classe: "botao-link botao-link-forte", texto: "Enviar resposta" });
  const cancelar = el("button", { type: "button", classe: "botao-link", texto: "Cancelar" });

  campoTexto.addEventListener("input", () => {
    contador.textContent = textoDoContadorDaResposta(campoTexto.value);
    contador.classList.toggle("comentario-contador-estouro", estourouOLimiteDaResposta(campoTexto.value));
  });
  cancelar.addEventListener("click", () => {
    area.replaceChildren();
    botao.hidden = false;
    botao.focus();
  });
  enviar.addEventListener("click", async () => {
    if (enviar.disabled) return;
    erro.textContent = "";
    const pronto = respostaPronta(campoNome.value, campoTexto.value);
    if (!pronto.ok) {
      erro.textContent = pronto.mensagem;
      (pronto.campo === "professor" ? campoNome : campoTexto).focus();
      return;
    }
    enviar.disabled = true;
    try {
      const { status, corpo } = await enviarJson(
        `/api/comentarios/${encodeURIComponent(id)}/responder`,
        pedidoDaResposta(pronto.professor, pronto.resposta),
      );
      const resultado = descreverResposta(status, corpo);
      if (resultado.tipo === "ok") {
        nomeDoProfessor = resultado.respondidoPor;
        const bloco = desenharResposta(resultado.respondidoPor, resultado.quando, pronto.resposta);
        area.replaceChildren(bloco);
        bloco.focus();
        botao.remove();
        atualizarTelaDepoisDeResponder(item, resultado.naoLidos);
        return;
      }
      erro.textContent = resultado.mensagem;
    } catch {
      erro.textContent = MENSAGEM_SEM_REDE;
    }
    enviar.disabled = false;
  });

  area.replaceChildren(
    el("div", { classe: "comentario-form-resposta" },
      el("div", { classe: "campo" }, el("label", { for: campoNome.id, texto: "Seu nome (quem está respondendo)" }), campoNome),
      el("div", { classe: "campo" }, el("label", { for: campoTexto.id, texto: "Resposta para o aluno" }), campoTexto),
      contador,
      el("div", { classe: "comentario-form-botoes" }, enviar, cancelar),
      erro,
    ),
  );
  botao.hidden = true;
  (campoNome.value ? campoTexto : campoNome).focus();
}

document.addEventListener("click", (evento) => {
  const botao = evento.target.closest("button");
  if (!botao) return;
  if (botao.dataset.marcarLido !== undefined) marcarUm(botao);
  else if (botao.dataset.marcarTodosDoAluno !== undefined) marcarTodosDoAluno(botao);
  else if (botao.dataset.responder !== undefined) abrirFormularioDeResposta(botao);
});
