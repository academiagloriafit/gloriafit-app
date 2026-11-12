// Regras puras da "caixa de entrada" da tela Comentários (visual novo, 11/11/2026), separadas para o Vitest.

// Qual comentário abrir depois que o aberto saiu da lista (na tela "Novos" o comentário lido some):
// o que estava logo abaixo dele; se ele era o último, o de cima; sem nenhum, null.
export function proximoAberto(idsAntes, idsAgora, idAberto) {
  if (idsAgora.includes(idAberto)) return idAberto;
  if (!idsAgora.length) return null;
  const posicao = idsAntes.indexOf(idAberto);
  const depois = idsAntes.slice(posicao + 1).find((id) => idsAgora.includes(id));
  if (depois !== undefined) return depois;
  const antes = idsAntes.slice(0, Math.max(posicao, 0)).reverse().find((id) => idsAgora.includes(id));
  return antes ?? idsAgora[0];
}
