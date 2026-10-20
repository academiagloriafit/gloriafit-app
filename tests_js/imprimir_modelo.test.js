import { describe, expect, it } from "vitest";
import { MENSAGEM_NAO_AUTORIZADO } from "../app/static/api.js";
import { TEXTO_ANTES, TEXTO_SEM_REDE, textoDoDesfazer, textoDoRegistro } from "../app/static/imprimir_modelo.js";

describe("textoDoRegistro", () => {
  it("primeira impressão do dia: confirma e deixa desfazer", () => {
    const r = textoDoRegistro({ status: 200, corpo: { ok: true, ficha: 2, ja_marcada: false, feitas: 3 } }, "B PERNAS");
    expect(r.erro).toBe(false);
    expect(r.podeDesfazer).toBe(true);
    expect(r.texto).toBe("✓ B PERNAS registrado como treino feito hoje (total neste treino: 3).");
  });

  it("segunda via no mesmo dia: avisa que não conta de novo", () => {
    const r = textoDoRegistro({ status: 200, corpo: { ok: true, ficha: 2, ja_marcada: true, feitas: 3 } }, "B PERNAS");
    expect(r.erro).toBe(false);
    expect(r.texto).toContain("já estava registrado como feito hoje");
    expect(r.texto).toContain("não conta de novo");
    expect(r.podeDesfazer).toBe(true);
  });

  it("treino concluído (409): mostra o motivo do servidor e não oferece desfazer", () => {
    const r = textoDoRegistro({ status: 409, corpo: { erro: "Este treino está concluído (inativo)." } }, "A");
    expect(r.erro).toBe(true);
    expect(r.podeDesfazer).toBe(false);
    expect(r.texto).toContain("Este treino está concluído (inativo).");
    expect(r.texto).toContain("não foi registrado como feito");
  });

  it("computador sem autorização (401): usa a mensagem padrão do app", () => {
    const r = textoDoRegistro({ status: 401, corpo: { erro: "x" } }, "A");
    expect(r.erro).toBe(true);
    expect(r.texto).toContain(MENSAGEM_NAO_AUTORIZADO);
  });

  it("erro sem corpo (página de erro, servidor reiniciando) mostra o código", () => {
    const r = textoDoRegistro({ status: 502, corpo: null }, "A");
    expect(r.erro).toBe(true);
    expect(r.texto).toContain("código 502");
  });

  it("resposta 200 sem o número de vezes não é tratada como sucesso", () => {
    expect(textoDoRegistro({ status: 200, corpo: {} }, "A").erro).toBe(true);
  });

  it("o nome da ficha vai como texto (quem coloca na tela usa textContent)", () => {
    const r = textoDoRegistro({ status: 200, corpo: { ja_marcada: false, feitas: 1 } }, "<b>A</b>");
    expect(r.texto).toContain("<b>A</b>");
  });
});

describe("textoDoDesfazer", () => {
  it("sucesso", () => {
    expect(textoDoDesfazer({ status: 200, corpo: { ok: true, ficha: 1, feitas: 0 } }, "A")).toEqual({
      texto: "Desfeito: A não conta mais como treino feito hoje.",
      erro: false,
    });
  });

  it("erro do servidor", () => {
    const r = textoDoDesfazer({ status: 409, corpo: { erro: "Este treino não tem essa ficha." } }, "A");
    expect(r.erro).toBe(true);
    expect(r.texto).toContain("Este treino não tem essa ficha.");
  });
});

describe("textos fixos", () => {
  it("o aviso de antes diz o que o clique em Imprimir faz", () => {
    expect(TEXTO_ANTES).toContain("Imprimir");
    expect(TEXTO_ANTES).toContain("treino feito hoje");
  });

  it("falha de rede diz que a impressão não foi afetada", () => {
    expect(TEXTO_SEM_REDE).toContain("A impressão não foi afetada");
  });
});
