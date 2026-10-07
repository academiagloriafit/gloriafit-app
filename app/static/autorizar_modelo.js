// Tela /autorizar: o que mostrar para cada resposta do servidor.
// Fica separado de autorizar.js (que mexe na página) para poder ser testado sozinho.

// Resposta de POST /api/autorizar -> { ok, mensagem }.
// `corpo` é o JSON da resposta, ou null se a resposta não era JSON.
export function descreverResposta(status, corpo) {
  if (status === 200 && corpo && corpo.ok === true) {
    const nome = typeof corpo.nome === "string" && corpo.nome ? corpo.nome : "Este computador";
    return { ok: true, mensagem: `${nome} foi autorizado. Abrindo o app…` };
  }
  // 400 (código errado ou vencido) e 429 (travado por excesso de erros) trazem a
  // explicação pronta no campo "erro".
  if (corpo && typeof corpo.erro === "string" && corpo.erro) {
    return { ok: false, mensagem: corpo.erro };
  }
  return {
    ok: false,
    mensagem: `O servidor devolveu um erro (código ${status}). Tente de novo em instantes.`,
  };
}

export const MENSAGEM_SEM_REDE =
  "Não consegui falar com o servidor (sem resposta ou sem rede). Confira a rede e tente de novo.";
