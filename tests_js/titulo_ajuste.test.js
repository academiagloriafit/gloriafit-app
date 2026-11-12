import { describe, expect, it } from "vitest";
import { tamanhoQueCabe } from "../app/static/titulo_ajuste.js";

describe("tamanhoQueCabe", () => {
  it("devolve o maior tamanho quando já cabe", () => {
    expect(tamanhoQueCabe(46, 24, 2, () => true)).toBe(46);
  });
  it("desce de 2 em 2 até caber", () => {
    // palavra comprida que só cabe com 36px ou menos
    expect(tamanhoQueCabe(46, 24, 2, (t) => t <= 36)).toBe(36);
  });
  it("devolve null quando nem o mínimo cabe", () => {
    expect(tamanhoQueCabe(46, 24, 2, () => false)).toBeNull();
  });
  it("testa o mínimo também", () => {
    expect(tamanhoQueCabe(46, 24, 2, (t) => t === 24)).toBe(24);
  });
});
