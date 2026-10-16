// Regras puras da tela "Comentários" do professor (sem tocar na página, para testar no Vitest).
import { MENSAGEM_NAO_AUTORIZADO } from "./api.js";

export const MENSAGEM_SEM_REDE = "Não consegui falar com o servidor (sem resposta ou sem internet). Confira a internet e tente de novo.";
export const MENSAGEM_COMENTARIO_SUMIU = "Este comentário não existe mais. Atualize a página.";

// O que fazer com a resposta de "marcar como lido" (um comentário ou todos de um aluno):
//   {tipo: "ok", naoLidos, marcados}   deu certo (`naoLidos` = quantos faltam ler no total; `marcados` só vem no "todos")
//   {tipo: "nao-autorizado", mensagem} o computador perdeu a autorização
//   {tipo: "erro", mensagem}           qualquer outra coisa, com a frase pronta para mostrar
export function descreverLeitura(status, corpo) {
  if (status === 200 && corpo && corpo.ok === true) {
    return {
      tipo: "ok",
      naoLidos: Number.isInteger(corpo.nao_lidos) ? corpo.nao_lidos : null,
      marcados: Number.isInteger(corpo.marcados) ? corpo.marcados : null,
    };
  }
  if (status === 401) return { tipo: "nao-autorizado", mensagem: MENSAGEM_NAO_AUTORIZADO };
  if (status === 404) return { tipo: "erro", mensagem: MENSAGEM_COMENTARIO_SUMIU };
  if (corpo && typeof corpo.erro === "string" && corpo.erro) return { tipo: "erro", mensagem: corpo.erro };
  return { tipo: "erro", mensagem: `Não consegui marcar como lido (código ${status}). Tente de novo.` };
}

// "1 comentário", "5 comentários" e, se a lista está cortada, "(mostrando os 3 mais novos)".
export function textoDoTotal(total, mostrados) {
  const base = `${total} ${total === 1 ? "comentário" : "comentários"}`;
  return mostrados < total ? `${base} (mostrando os ${mostrados} mais novos)` : base;
}

// O resumo do quadro da ficha: "2 sem ler · 5 no total".
export function textoDoResumoDaFicha(semLer, total) {
  return `${semLer} sem ler · ${total} no total`;
}

// O texto do botão "Novos" do filtro.
export function textoDoFiltroNovos(naoLidos) {
  return `Novos (${naoLidos})`;
}

// ------------------------------------------------------------------ responder ao aluno

export const LIMITE_DA_RESPOSTA = 500; // o servidor aceita até isto (LIMITE_DO_TEXTO em app/comentarios.py)
export const LIMITE_DO_NOME = 60; // o mesmo do campo "Professor" ao lançar treino

// Conta letras como o servidor (Python): um emoji vale 1, não 2 como no `.length` do JavaScript.
function contarLetras(texto) {
  return [...(typeof texto === "string" ? texto : "")].length;
}

// "37 de 500", embaixo da caixa da resposta.
export function textoDoContadorDaResposta(texto) {
  return `${contarLetras(texto)} de ${LIMITE_DA_RESPOSTA}`;
}

export function estourouOLimiteDaResposta(texto) {
  return contarLetras(texto) > LIMITE_DA_RESPOSTA;
}

// O nome e a resposta estão prontos para enviar? { ok: true, professor, resposta } (sem as bordas em branco) ou
// { ok: false, mensagem, campo } ("professor" ou "resposta": onde pôr o cursor). O servidor confere tudo de novo.
export function respostaPronta(professor, resposta) {
  const nome = typeof professor === "string" ? professor.trim() : "";
  const texto = typeof resposta === "string" ? resposta.trim() : "";
  if (!nome) return { ok: false, campo: "professor", mensagem: "Digite o seu nome, para o aluno saber quem respondeu." };
  if (contarLetras(nome) > LIMITE_DO_NOME) {
    return { ok: false, campo: "professor", mensagem: `O nome pode ter até ${LIMITE_DO_NOME} letras.` };
  }
  if (!texto) return { ok: false, campo: "resposta", mensagem: "Escreva a resposta para o aluno." };
  if (contarLetras(texto) > LIMITE_DA_RESPOSTA) {
    return { ok: false, campo: "resposta", mensagem: `A resposta pode ter até ${LIMITE_DA_RESPOSTA} letras.` };
  }
  return { ok: true, professor: nome, resposta: texto };
}

export function pedidoDaResposta(professor, resposta) {
  return { professor, resposta };
}

// O que fazer com a resposta do servidor ao responder:
//   {tipo: "ok", naoLidos, respondidoPor, quando}   deu certo (responder também marca como lido)
//   {tipo: "nao-autorizado", mensagem}              o computador perdeu a autorização
//   {tipo: "erro", mensagem}                        qualquer outra coisa, com a frase pronta para mostrar
export function descreverResposta(status, corpo) {
  if (status === 200 && corpo && corpo.ok === true && typeof corpo.respondido_por === "string") {
    return {
      tipo: "ok",
      naoLidos: Number.isInteger(corpo.nao_lidos) ? corpo.nao_lidos : null,
      respondidoPor: corpo.respondido_por,
      quando: typeof corpo.respondido_quando === "string" ? corpo.respondido_quando : "",
    };
  }
  if (status === 401) return { tipo: "nao-autorizado", mensagem: MENSAGEM_NAO_AUTORIZADO };
  if (status === 404) return { tipo: "erro", mensagem: MENSAGEM_COMENTARIO_SUMIU };
  if (corpo && typeof corpo.erro === "string" && corpo.erro) return { tipo: "erro", mensagem: corpo.erro };
  return { tipo: "erro", mensagem: `Não consegui enviar a resposta (código ${status}). Tente de novo.` };
}
