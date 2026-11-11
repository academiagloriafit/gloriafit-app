// Textos da tela "Alunos" do professor (visual novo, 11/11/2026). Sem DOM: os testes (Vitest) rodam aqui.

// Os filtros que a tela conhece (os mesmos de app/painel_alunos.py). Outro valor = sem filtro.
export const FILTROS = ["ativos", "hoje", "trocar", "comentarios", "sumiram", "sem_treino"];

// A partir de quantos dias sem treinar a data fica em laranja (o aluno está sumindo).
export const DIAS_PARA_ALERTA = 7;

export function filtroValido(filtro) {
  return FILTROS.includes(filtro) ? filtro : "";
}

// "hoje", "ontem", "há 5 dias"; null/negativo = nunca registrou.
export function textoDoUltimoTreino(dias) {
  if (!Number.isInteger(dias) || dias < 0) return "Nunca registrou";
  if (dias === 0) return "Hoje";
  if (dias === 1) return "Ontem";
  return `Há ${dias} dias`;
}

export function ultimoTreinoEmAlerta(dias) {
  return !Number.isInteger(dias) || dias >= DIAS_PARA_ALERTA;
}

// A barra de andamento: "18 de 30 sessões" e a largura (0 a 1). Sem meta: só quantas foram feitas, sem barra.
export function andamentoDoAluno(aluno) {
  const feitas = Number.isInteger(aluno?.sessoes_feitas) && aluno.sessoes_feitas > 0 ? aluno.sessoes_feitas : 0;
  const meta = Number.isInteger(aluno?.sessoes_meta) && aluno.sessoes_meta > 0 ? aluno.sessoes_meta : null;
  if (!aluno?.treino_atual) return { texto: "", fracao: null };
  if (meta) return { texto: `${feitas} de ${meta} sessões`, fracao: Math.min(1, feitas / meta) };
  return { texto: feitas === 1 ? "1 sessão" : `${feitas} sessões`, fracao: null };
}

// Os parâmetros da busca no servidor.
export function parametrosDaBusca(texto, filtro) {
  const parametros = new URLSearchParams();
  const limpo = String(texto ?? "").trim();
  if (limpo) parametros.set("q", limpo);
  const valido = filtroValido(filtro);
  if (valido) parametros.set("filtro", valido);
  return parametros.toString();
}
