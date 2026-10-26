import { describe, expect, it } from "vitest";
import { lerGrupos, numeroCurto, resumoDaSemana, seriesDoItem, textoDaRotacao } from "../app/static/resumo_semana.js";

const GRUPOS = lerGrupos({ nomes: ["Peito", "Costas", "Tríceps", "Bíceps", "Quadríceps"], ex: { 1: [0], 2: [1], 3: [2], 4: [3, 2], 5: [4] } });

describe("seriesDoItem", () => {
  it.each([
    ["3", 3],
    ["3 a 4", 3],
    ["4x", 4],
    ["", 0],
    ["-", 0],
    [null, 0],
    ["30", 20],
  ])("%s -> %s", (texto, esperado) => {
    expect(seriesDoItem(texto)).toBe(esperado);
  });
});

describe("lerGrupos", () => {
  it("devolve os nomes dos grupos de cada exercício, sem repetir", () => {
    expect(GRUPOS(4)).toEqual(["Bíceps", "Tríceps"]);
    expect(GRUPOS(99)).toEqual([]);
  });

  it("dado estragado vira lista vazia, sem quebrar a tela", () => {
    expect(lerGrupos(null)(1)).toEqual([]);
    expect(lerGrupos({ nomes: ["Peito"], ex: { 1: [5, -1, "0"] } })(1)).toEqual([]);
    expect(lerGrupos({ nomes: "x", ex: [] })(1)).toEqual([]);
  });
});

describe("textoDaRotacao", () => {
  it("repete as fichas na ordem durante a semana", () => {
    expect(textoDaRotacao(3, 5)).toBe("A-B-C-A-B");
    expect(textoDaRotacao(2, 4)).toBe("A-B-A-B");
    expect(textoDaRotacao(5, 5)).toBe("A-B-C-D-E");
    expect(textoDaRotacao(0, 5)).toBe("");
  });
});

describe("resumoDaSemana", () => {
  const fichas = [
    { nome: "A - PEITO", itens: [{ exercicioId: 1, series: "4" }, { exercicioId: 1, series: "3" }, { exercicioId: 3, series: "3" }] },
    { nome: "B - COSTAS", itens: [{ exercicioId: 2, series: "4" }, { exercicioId: 4, series: "3" }] },
    { nome: "C - PERNAS", itens: [{ exercicioId: 5, series: "4" }, { exercicioId: 77, series: "" }] },
  ];

  it("soma as séries por ficha e faz a média da semana com as fichas repetindo", () => {
    const r = resumoDaSemana(fichas, GRUPOS, 5);

    expect(r.fichas).toEqual(["A - PEITO", "B - COSTAS", "C - PERNAS"]);
    expect(r.rotacao).toBe("A-B-C-A-B");
    expect(numeroCurto(r.vezesPorFicha)).toBe("1,7");
    expect(r.linhas).toEqual([
      { grupo: "Peito", porFicha: [7, 0, 0], semana: 12 }, // 7 x 5/3 = 11,7
      { grupo: "Tríceps", porFicha: [3, 3, 0], semana: 10 }, // o combinado (4) conta para bíceps e tríceps
      { grupo: "Costas", porFicha: [0, 4, 0], semana: 7 },
      { grupo: "Quadríceps", porFicha: [0, 0, 4], semana: 7 },
      { grupo: "Bíceps", porFicha: [0, 3, 0], semana: 5 },
    ]);
    expect(r.semGrupo).toBe(1);
  });

  it("uma ficha por dia: a semana é a soma", () => {
    const r = resumoDaSemana(fichas, GRUPOS, 3);

    expect(r.vezesPorFicha).toBe(1);
    expect(r.linhas.find((l) => l.grupo === "Peito").semana).toBe(7);
  });

  it("ficha vazia não conta como ficha da rotação", () => {
    const r = resumoDaSemana([...fichas, { nome: "D", itens: [] }], GRUPOS, 3);

    expect(r.fichas).toHaveLength(3);
    expect(r.rotacao).toBe("A-B-C");
  });

  it("sem exercício nenhum ou dias inválidos, resumo vazio", () => {
    expect(resumoDaSemana([{ nome: "A", itens: [] }], GRUPOS, 3).linhas).toEqual([]);
    expect(resumoDaSemana(fichas, GRUPOS, 0).linhas).toEqual([]);
    expect(resumoDaSemana(undefined, GRUPOS, 3).fichas).toEqual([]);
  });

  it("ficha sem nome aparece com a letra", () => {
    expect(resumoDaSemana([{ nome: "  ", itens: [{ exercicioId: 1, series: "3" }] }], GRUPOS, 2).fichas).toEqual(["A"]);
  });
});
