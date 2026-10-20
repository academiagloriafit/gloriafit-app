// Tela de impressão: os textos do aviso "esta ficha conta como treino feito hoje". Sem DOM, para testar.
import { MENSAGEM_NAO_AUTORIZADO } from "./api.js";

export const TEXTO_ANTES = "Ao clicar em Imprimir, esta ficha conta como treino feito hoje.";
export const TEXTO_SEM_REDE =
  "A impressão não foi afetada, mas não consegui registrar o treino como feito (sem resposta do servidor).";

// O que mostrar depois de pedir ao servidor para registrar. `resposta` = { status, corpo } (como enviarJson devolve).
// Devolve { texto, erro, podeDesfazer }.
export function textoDoRegistro(resposta, nome) {
  const { status, corpo } = resposta;
  if (status === 200 && corpo && typeof corpo.feitas === "number") {
    if (corpo.ja_marcada) {
      return {
        texto: `${nome} já estava registrado como feito hoje: não conta de novo (total neste treino: ${corpo.feitas}).`,
        erro: false,
        podeDesfazer: true,
      };
    }
    return {
      texto: `✓ ${nome} registrado como treino feito hoje (total neste treino: ${corpo.feitas}).`,
      erro: false,
      podeDesfazer: true,
    };
  }
  if (status === 401) {
    return { texto: `${MENSAGEM_NAO_AUTORIZADO} O treino não foi registrado como feito.`, erro: true, podeDesfazer: false };
  }
  const motivo = corpo && typeof corpo.erro === "string" ? corpo.erro : `O servidor devolveu um erro (código ${status}).`;
  return { texto: `${motivo} O treino não foi registrado como feito.`, erro: true, podeDesfazer: false };
}

export function textoDoDesfazer(resposta, nome) {
  if (resposta.status === 200) {
    return { texto: `Desfeito: ${nome} não conta mais como treino feito hoje.`, erro: false };
  }
  const motivo =
    resposta.corpo && typeof resposta.corpo.erro === "string"
      ? resposta.corpo.erro
      : `O servidor devolveu um erro (código ${resposta.status}).`;
  return { texto: `Não consegui desfazer: ${motivo}`, erro: true };
}
