import { describe, expect, it } from "vitest";
import { proximoAberto } from "../app/static/comentarios_caixa_modelo.js";

describe("proximoAberto", () => {
  it("o aberto continua na lista: fica ele", () => {
    expect(proximoAberto(["1", "2", "3"], ["1", "2", "3"], "2")).toBe("2");
  });
  it("o aberto saiu: abre o de baixo", () => {
    expect(proximoAberto(["1", "2", "3"], ["1", "3"], "2")).toBe("3");
  });
  it("o aberto era o último: abre o de cima", () => {
    expect(proximoAberto(["1", "2", "3"], ["1", "2"], "3")).toBe("2");
  });
  it("não sobrou nenhum: null", () => {
    expect(proximoAberto(["1"], [], "1")).toBeNull();
  });
  it("nada aberto ainda: o primeiro", () => {
    expect(proximoAberto([], ["5", "6"], null)).toBe("5");
  });
});
