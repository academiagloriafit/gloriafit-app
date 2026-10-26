// Resumo da semana na tela "Lançar treino" (pedido do Thiago, 26/10/2026): quantas séries cada grupo muscular recebe em cada ficha e
// na semana, contando que as fichas se repetem na ordem (5 dias com 3 fichas = A-B-C-A-B, e a semana seguinte continua C-A-B...).
// Lógica pura (testada em tests_js/resumo_semana.test.js); a tela fica em montar.js.
//
// A conta da semana é a MÉDIA: com D dias e F fichas, cada ficha roda D/F vezes por semana. Exercício com dois grupos (os
// "combinados", ex.: rosca + tríceps) conta as séries para cada um deles. Item sem número de séries (cardio) não soma séries.

export const MAXIMO_DE_SERIES_POR_ITEM = 20; // "30" digitado por engano não pode virar 30 séries no resumo

// "3" -> 3; "3 a 4" -> 3; "4x" -> 4; "" ou "-" -> 0.
export function seriesDoItem(texto) {
  const achado = /\d+/.exec(String(texto ?? ""));
  if (!achado) return 0;
  return Math.min(Number(achado[0]), MAXIMO_DE_SERIES_POR_ITEM);
}

// O que o servidor manda no atributo data-grupos: { nomes: ["Peito", ...], ex: { "12": [0, 3] } } (índices em `nomes`).
// Devolve uma função id -> [nomes dos grupos] (lista vazia se o exercício não tem grupo ou o dado veio estragado).
export function lerGrupos(dados) {
  const nomes = Array.isArray(dados?.nomes) ? dados.nomes.filter((n) => typeof n === "string") : [];
  const ex = dados && typeof dados.ex === "object" && dados.ex !== null ? dados.ex : {};
  return (id) => {
    const lista = ex[String(id)];
    if (!Array.isArray(lista)) return [];
    return [...new Set(lista.filter((i) => Number.isInteger(i) && i >= 0 && i < nomes.length).map((i) => nomes[i]))];
  };
}

// A ordem da semana: 3 fichas e 5 dias -> "A-B-C-A-B". Usa as letras das fichas na ordem (A, B, C...).
export function textoDaRotacao(quantasFichas, dias) {
  if (quantasFichas < 1 || dias < 1) return "";
  const letras = [];
  for (let d = 0; d < dias; d += 1) letras.push(String.fromCharCode(65 + (d % quantasFichas)));
  return letras.join("-");
}

// fichas: [{ nome, itens: [{ exercicioId, series }] }]. gruposDe: id -> [nomes]. dias: 1 a 7.
// Devolve { fichas: [nomes das fichas com exercício], linhas: [{ grupo, porFicha: [séries], semana }], semGrupo, vezesPorFicha,
// rotacao }. `semana` é arredondada; as linhas vêm da maior para a menor semana (empate: nome do grupo).
export function resumoDaSemana(fichas, gruposDe, dias) {
  const comExercicio = (fichas ?? []).filter((f) => Array.isArray(f?.itens) && f.itens.length > 0);
  const quantas = comExercicio.length;
  const vazio = { fichas: [], linhas: [], semGrupo: 0, vezesPorFicha: 0, rotacao: "" };
  if (quantas === 0 || !Number.isInteger(dias) || dias < 1) return vazio;
  const porGrupo = new Map();
  let semGrupo = 0;
  comExercicio.forEach((ficha, i) => {
    for (const item of ficha.itens) {
      const grupos = gruposDe(item.exercicioId);
      if (grupos.length === 0) {
        semGrupo += 1;
        continue;
      }
      const series = seriesDoItem(item.series);
      for (const grupo of grupos) {
        if (!porGrupo.has(grupo)) porGrupo.set(grupo, new Array(quantas).fill(0));
        porGrupo.get(grupo)[i] += series;
      }
    }
  });
  const vezesPorFicha = dias / quantas;
  const linhas = [...porGrupo.entries()]
    .map(([grupo, porFicha]) => ({ grupo, porFicha, semana: Math.round(porFicha.reduce((a, b) => a + b, 0) * vezesPorFicha) }))
    .sort((a, b) => b.semana - a.semana || a.grupo.localeCompare(b.grupo, "pt-BR"));
  return {
    fichas: comExercicio.map((f, i) => (String(f.nome ?? "").trim() || String.fromCharCode(65 + i))),
    linhas,
    semGrupo,
    vezesPorFicha,
    rotacao: textoDaRotacao(quantas, dias),
  };
}

// 1.6666 -> "1,7"; 2 -> "2".
export function numeroCurto(valor) {
  const arredondado = Math.round(valor * 10) / 10;
  return String(arredondado).replace(".", ",");
}
