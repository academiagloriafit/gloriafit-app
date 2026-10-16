// Tela /aluno: a lista "Seus comentários" com as respostas do professor e o aviso de resposta nova.
// Texto sempre via textContent (o helper `el`): o que o professor e o aluno escreveram nunca é interpretado como HTML.
// A lista é um extra: se não carregar, a tela do treino segue funcionando sem ela.
import { buscarJson, enviarJson } from "./api.js";
import { el } from "./dom.js";
import {
  TEXTO_SEM_RESPOSTA,
  descreverMeusComentarios,
  descreverVistos,
  idsDasRespostasNovas,
  textoDaNotaDaLista,
  textoDoAvisoDeResposta,
  textoDoBotaoMeusComentarios,
  textoDoLugar,
} from "./aluno_modelo.js";

const secao = document.getElementById("meus-comentarios");
const botaoAviso = document.getElementById("aviso-resposta-nova");
const botaoLista = document.getElementById("botao-meus-comentarios");
const lista = document.getElementById("lista-meus-comentarios");

const estado = { total: 0, respostasNovas: 0, comentarios: [], aberta: false };

// As respostas que o aluno acabou de ver NESTA visita continuam com a etiqueta "Nova" (para ele achar a resposta), mesmo
// depois de o servidor já tê-las como vistas. Ao recarregar a página a lista começa vazia e elas deixam de ser "Nova".
const vistasNestaVisita = new Set();
const MINIMO_ENTRE_BUSCAS = 30_000; // ao voltar para o app, busca de novo no máximo a cada 30 segundos
let ultimaBusca = 0;

function ehNova(c) {
  return c.resposta.nova === true || vistasNestaVisita.has(c.id);
}

function desenharItem(c) {
  const resposta = c.resposta
    ? el(
        "div",
        { classe: ehNova(c) ? "meu-c-resposta meu-c-resposta-nova" : "meu-c-resposta" },
        el(
          "p",
          { classe: "meu-c-resposta-cabecalho", texto: `Resposta de ${c.resposta.por} · ${c.resposta.quando}` },
          ehNova(c) && el("span", { classe: "meu-c-nova", texto: "Nova" }),
        ),
        el("p", { classe: "meu-c-resposta-texto", texto: c.resposta.texto }),
      )
    : el("p", { classe: "meu-c-sem-resposta", texto: TEXTO_SEM_RESPOSTA });
  return el(
    "li",
    { classe: "meu-c" },
    el("p", { classe: "meu-c-lugar", texto: `${c.quando} · ${textoDoLugar(c)}` }),
    el("p", { classe: "meu-c-texto", texto: c.texto }),
    resposta,
  );
}

function desenhar() {
  const temComentarios = estado.total > 0;
  secao.hidden = !temComentarios;
  botaoAviso.hidden = !(temComentarios && estado.respostasNovas > 0);
  if (!temComentarios) return;
  botaoAviso.textContent = `${textoDoAvisoDeResposta(estado.respostasNovas)} Toque para ver.`;
  botaoLista.textContent = textoDoBotaoMeusComentarios(estado.total, estado.respostasNovas, estado.aberta);
  botaoLista.setAttribute("aria-expanded", estado.aberta ? "true" : "false");
  lista.hidden = !estado.aberta;
  const nota = textoDaNotaDaLista(estado.total, estado.comentarios.length);
  lista.replaceChildren(...estado.comentarios.map(desenharItem), nota && el("li", { classe: "meu-c-nota", texto: nota }));
}

// Manda ao servidor as respostas novas que a lista aberta está mostrando: só então elas contam como vistas. Vão só as que a tela mostra.
async function marcarVistas() {
  const novas = idsDasRespostasNovas(estado.comentarios).filter((id) => !vistasNestaVisita.has(id));
  if (!novas.length) return;
  try {
    const { status, corpo } = await enviarJson("/api/aluno/comentarios/vistos", { ids: novas });
    const resultado = descreverVistos(status, corpo);
    if (resultado.tipo === "entrar") {
      window.location.assign("/aluno/entrar");
      return;
    }
    if (resultado.tipo === "ok") {
      for (const id of novas) vistasNestaVisita.add(id);
      // Se ainda sobrou resposta nova (chegou depois de a lista ser buscada), o aviso do alto continua e, ao tocar nele, a lista é buscada de novo.
      estado.respostasNovas = resultado.respostasNovas;
      desenhar();
    }
  } catch {
    /* sem rede: elas continuam "novas" e o aviso volta na próxima vez */
  }
}

// Abrir a lista: mostra o que já tem e busca de novo (pode ter chegado resposta depois de a página abrir); a busca marca como vistas as novas.
async function abrir() {
  estado.aberta = true;
  desenhar();
  secao.scrollIntoView({ behavior: "smooth", block: "start" });
  botaoLista.focus({ preventScroll: true }); // o botão do aviso some ao abrir: o foco vai para o botão da lista
  await atualizarMeusComentarios();
}

function fechar() {
  estado.aberta = false;
  desenhar();
}

// Busca de novo no servidor (ao abrir a página, ao abrir a lista, ao voltar para o app e depois de o aluno mandar um comentário).
// Com a lista aberta, as respostas novas que chegarem já contam como vistas.
export async function atualizarMeusComentarios() {
  ultimaBusca = Date.now();
  try {
    const { status, corpo } = await buscarJson("/api/aluno/comentarios");
    const resultado = descreverMeusComentarios(status, corpo);
    if (resultado.tipo === "entrar") {
      window.location.assign("/aluno/entrar");
      return;
    }
    if (resultado.tipo === "ok") {
      Object.assign(estado, {
        total: resultado.total,
        respostasNovas: resultado.respostasNovas,
        comentarios: resultado.comentarios,
      });
      desenhar();
    }
  } catch {
    /* a lista é um extra: sem rede, a tela segue sem ela (com a lista aberta, ainda marca o que ela já mostrava) */
  }
  if (estado.aberta) await marcarVistas();
}

botaoAviso.addEventListener("click", abrir);
botaoLista.addEventListener("click", () => (estado.aberta ? fechar() : abrir()));

// O app do celular costuma ficar aberto em segundo plano: ao voltar para ele, olha se chegou resposta.
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && Date.now() - ultimaBusca > MINIMO_ENTRE_BUSCAS) atualizarMeusComentarios();
});
