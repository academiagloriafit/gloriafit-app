// Tela "Aluno provisório": o que mostrar para cada resposta do servidor.
// Fica separado de novo_aluno.js (que mexe na página) para poder ser testado sozinho.

// Campos do formulário que o servidor pode acusar. Qualquer outro nome vira "geral".
export const CAMPOS = ["nome", "cpf", "whatsapp"];

// Resposta de POST /api/alunos -> um destes formatos:
//   { tipo: "criado", id }
//   { tipo: "erros", erros: { nome?, cpf?, whatsapp?, geral? } }
//   { tipo: "cpf_existente", mensagem, existentes: [{ id, nome, provisorio, situacao_nome }] }
//   { tipo: "falha", mensagem }
// `corpo` é o JSON da resposta, ou null se a resposta não era JSON.
export function interpretarResposta(status, corpo) {
  if (status === 201 && corpo && Number.isInteger(corpo.id) && corpo.id > 0) {
    return { tipo: "criado", id: corpo.id };
  }

  if (status === 409 && corpo && Array.isArray(corpo.existentes)) {
    const existentes = corpo.existentes
      .filter((e) => e && Number.isInteger(e.id) && e.id > 0 && typeof e.nome === "string")
      .map((e) => ({
        id: e.id,
        nome: e.nome,
        provisorio: e.provisorio === true,
        situacao_nome: typeof e.situacao_nome === "string" ? e.situacao_nome : null,
      }));
    const mensagem =
      typeof corpo.erro === "string" && corpo.erro ? corpo.erro : "Já existe um aluno com este CPF.";
    return { tipo: "cpf_existente", mensagem, existentes };
  }

  if (status === 400 && corpo && corpo.erros && typeof corpo.erros === "object" && !Array.isArray(corpo.erros)) {
    const erros = {};
    for (const [campo, mensagem] of Object.entries(corpo.erros)) {
      if (typeof mensagem !== "string" || !mensagem) continue;
      erros[CAMPOS.includes(campo) ? campo : "geral"] = mensagem;
    }
    if (Object.keys(erros).length > 0) return { tipo: "erros", erros };
  }

  if (corpo && typeof corpo.erro === "string" && corpo.erro) {
    return { tipo: "falha", mensagem: corpo.erro };
  }
  return {
    tipo: "falha",
    mensagem: `O servidor devolveu um erro (código ${status}). O aluno não foi cadastrado.`,
  };
}

export const MENSAGEM_SEM_REDE =
  "Não consegui confirmar com o servidor se o aluno foi cadastrado (sem resposta ou sem rede). " +
  "Confira a rede e toque em Salvar de novo: se ele já tiver sido salvo, o app avisará que o CPF já existe " +
  "e você poderá abrir a ficha dele.";

// Descrição curta de quem já tem o CPF, para a lista de links: "NOME — Desistente".
export function descreverExistente(existente) {
  const situacao = existente.provisorio ? "Provisório" : existente.situacao_nome;
  return situacao ? `${existente.nome} — ${situacao}` : existente.nome;
}
