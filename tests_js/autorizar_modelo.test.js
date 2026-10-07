import { describe, expect, it } from "vitest";
import { MENSAGEM_SEM_REDE, descreverResposta } from "../app/static/autorizar_modelo.js";

describe("descreverResposta", () => {
  it("200 com ok: autorizado, citando o nome do computador", () => {
    expect(descreverResposta(200, { ok: true, nome: "Computador da recepção" })).toEqual({
      ok: true,
      mensagem: "Computador da recepção foi autorizado. Abrindo o app…",
    });
  });

  it("200 sem nome: usa um texto genérico", () => {
    expect(descreverResposta(200, { ok: true }).mensagem).toBe("Este computador foi autorizado. Abrindo o app…");
    expect(descreverResposta(200, { ok: true, nome: "" }).mensagem).toContain("Este computador");
    expect(descreverResposta(200, { ok: true, nome: 42 }).mensagem).toContain("Este computador");
  });

  it("200 sem ok:true NÃO conta como autorizado (ex.: página qualquer devolvida por um proxy)", () => {
    expect(descreverResposta(200, null).ok).toBe(false);
    expect(descreverResposta(200, {}).ok).toBe(false);
    expect(descreverResposta(200, { ok: false }).ok).toBe(false);
  });

  it("código errado (400) mostra a explicação do servidor", () => {
    expect(descreverResposta(400, { erro: "Código inválido ou vencido." })).toEqual({
      ok: false,
      mensagem: "Código inválido ou vencido.",
    });
  });

  it("travado por excesso de erros (429) mostra a explicação do servidor", () => {
    const r = descreverResposta(429, { erro: "Muitos códigos errados seguidos. Tente de novo em 12 min." });
    expect(r.ok).toBe(false);
    expect(r.mensagem).toContain("Tente de novo em 12 min");
  });

  it("erro com status de sucesso e campo erro continua sendo erro", () => {
    expect(descreverResposta(200, { erro: "algo" })).toEqual({ ok: false, mensagem: "algo" });
  });

  it("resposta que não é JSON ou sem campo erro vira mensagem genérica com o código", () => {
    expect(descreverResposta(502, null).mensagem).toContain("código 502");
    expect(descreverResposta(500, {}).mensagem).toContain("código 500");
    expect(descreverResposta(500, { erro: 5 }).mensagem).toContain("código 500");
    expect(descreverResposta(500, { erro: "" }).mensagem).toContain("código 500");
  });

  it("a mensagem de falta de rede explica o que fazer", () => {
    expect(MENSAGEM_SEM_REDE).toContain("tente de novo");
  });
});
