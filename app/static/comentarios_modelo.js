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
