import { describe, expect, it } from "vitest";
import { enderecoDaFotoGrande, textoDaLegenda } from "../app/static/foto_grande_modelo.js";

describe("enderecoDaFotoGrande", () => {
  it("pede a foto grande do mesmo aluno", () => {
    expect(enderecoDaFotoGrande("/alunos/12/foto")).toBe("/alunos/12/foto?tamanho=grande");
    expect(enderecoDaFotoGrande("https://app.gloriafit.com.br/alunos/7/foto")).toBe("/alunos/7/foto?tamanho=grande");
    expect(enderecoDaFotoGrande("/alunos/7/foto?x=1")).toBe("/alunos/7/foto?tamanho=grande");
  });

  it("recusa qualquer outro endereço", () => {
    for (const ruim of ["/static/x.png", "/alunos/abc/foto", "//outro.site/alunos/1/foto", "/alunos/1/foto/../..", "javascript:alert(1)", null, 5]) {
      expect(enderecoDaFotoGrande(ruim)).toBeNull();
    }
  });
});

describe("textoDaLegenda", () => {
  it("usa o nome ou um texto genérico", () => {
    expect(textoDaLegenda(" Mariana Souza ")).toBe("Mariana Souza");
    expect(textoDaLegenda("")).toBe("Foto do aluno");
    expect(textoDaLegenda(undefined)).toBe("Foto do aluno");
  });
});
