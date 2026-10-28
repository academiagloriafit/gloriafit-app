import { describe, expect, it } from "vitest";
import { iniciais, nomeDePessoa } from "../app/static/nomes.js";

describe("nomeDePessoa (igual ao app/nomes.py)", () => {
  it.each([
    ["MARIANA SOUZA", "Mariana Souza"],
    ["MARIANA DE SOUZA", "Mariana de Souza"],
    ["JOÃO PEDRO DOS SANTOS E SILVA", "João Pedro dos Santos e Silva"],
    ["ÂNGELA  D'ÁVILA", "Ângela D'Ávila"],
    ["ANA-MARIA LIMA", "Ana-Maria Lima"],
    ["PEDRO ALVES II", "Pedro Alves II"],
    ["DE LIMA", "De Lima"],
    ["", ""],
  ])("%s -> %s", (entrada, saida) => {
    expect(nomeDePessoa(entrada)).toBe(saida);
  });

  it("valor que não é texto vira vazio", () => {
    expect(nomeDePessoa(null)).toBe("");
    expect(nomeDePessoa(42)).toBe("");
  });
});

describe("iniciais", () => {
  it("primeira e última palavra, sem as de ligação", () => {
    expect(iniciais("MARIANA DE SOUZA")).toBe("MS");
    expect(iniciais("JOÃO PEDRO DOS SANTOS")).toBe("JS");
    expect(iniciais("ÉRICA")).toBe("É");
    expect(iniciais("")).toBe("");
  });
});
