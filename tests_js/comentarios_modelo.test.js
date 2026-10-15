import { describe, expect, it } from "vitest";
import { MENSAGEM_NAO_AUTORIZADO } from "../app/static/api.js";
import {
  MENSAGEM_COMENTARIO_SUMIU,
  descreverLeitura,
  textoDoFiltroNovos,
  textoDoResumoDaFicha,
  textoDoTotal,
} from "../app/static/comentarios_modelo.js";

describe("descreverLeitura", () => {
  it("200 com ok traz quantos faltam ler (e quantos foram marcados, no 'todos do aluno')", () => {
    expect(descreverLeitura(200, { ok: true, nao_lidos: 4 })).toEqual({ tipo: "ok", naoLidos: 4, marcados: null });
    expect(descreverLeitura(200, { ok: true, marcados: 2, nao_lidos: 0 })).toEqual({ tipo: "ok", naoLidos: 0, marcados: 2 });
  });

  it("200 sem os números ainda é ok (o contador só não muda)", () => {
    expect(descreverLeitura(200, { ok: true })).toEqual({ tipo: "ok", naoLidos: null, marcados: null });
    expect(descreverLeitura(200, { ok: true, nao_lidos: "3" })).toEqual({ tipo: "ok", naoLidos: null, marcados: null });
  });

  it("401: o computador perdeu a autorização", () => {
    expect(descreverLeitura(401, { erro: "x" })).toEqual({ tipo: "nao-autorizado", mensagem: MENSAGEM_NAO_AUTORIZADO });
  });

  it("404: o comentário não existe mais", () => {
    expect(descreverLeitura(404, { erro: "Comentário não encontrado." })).toEqual({ tipo: "erro", mensagem: MENSAGEM_COMENTARIO_SUMIU });
  });

  it("outro erro mostra a frase do servidor", () => {
    expect(descreverLeitura(403, { erro: "Origem não permitida." })).toEqual({ tipo: "erro", mensagem: "Origem não permitida." });
  });

  it.each([
    [500, null],
    [500, {}],
    [500, { erro: "" }],
    [200, { ok: false }],
    [200, null],
  ])("resposta estranha (%s, %j) vira erro com o código na frase", (status, corpo) => {
    const r = descreverLeitura(status, corpo);
    expect(r.tipo).toBe("erro");
    expect(r.mensagem).toContain(`código ${status}`);
  });
});

describe("os textos da tela", () => {
  it("textoDoTotal usa singular e plural", () => {
    expect(textoDoTotal(0, 0)).toBe("0 comentários");
    expect(textoDoTotal(1, 1)).toBe("1 comentário");
    expect(textoDoTotal(5, 5)).toBe("5 comentários");
  });

  it("textoDoTotal avisa quando a lista está cortada", () => {
    expect(textoDoTotal(250, 200)).toBe("250 comentários (mostrando os 200 mais novos)");
  });

  it("textoDoResumoDaFicha", () => {
    expect(textoDoResumoDaFicha(2, 5)).toBe("2 sem ler · 5 no total");
    expect(textoDoResumoDaFicha(0, 5)).toBe("0 sem ler · 5 no total");
  });

  it("textoDoFiltroNovos", () => {
    expect(textoDoFiltroNovos(3)).toBe("Novos (3)");
  });
});
