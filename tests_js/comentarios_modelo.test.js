import { describe, expect, it } from "vitest";
import { MENSAGEM_NAO_AUTORIZADO } from "../app/static/api.js";
import {
  LIMITE_DA_RESPOSTA,
  LIMITE_DO_NOME,
  MENSAGEM_COMENTARIO_SUMIU,
  descreverLeitura,
  descreverResposta,
  estourouOLimiteDaResposta,
  pedidoDaResposta,
  respostaPronta,
  textoDoContadorDaResposta,
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

describe("o contador da resposta", () => {
  it("mostra quantas letras já tem", () => {
    expect(textoDoContadorDaResposta("")).toBe("0 de 500");
    expect(textoDoContadorDaResposta("Bom treino")).toBe("10 de 500");
  });

  it("conta emoji como 1 letra (como o servidor)", () => {
    expect(textoDoContadorDaResposta("💪💪")).toBe("2 de 500");
  });

  it("não quebra com o que não é texto", () => {
    expect(textoDoContadorDaResposta(undefined)).toBe("0 de 500");
    expect(textoDoContadorDaResposta(null)).toBe("0 de 500");
  });

  it("estourou só a partir de 501 letras", () => {
    expect(estourouOLimiteDaResposta("a".repeat(LIMITE_DA_RESPOSTA))).toBe(false);
    expect(estourouOLimiteDaResposta("a".repeat(LIMITE_DA_RESPOSTA + 1))).toBe(true);
    expect(estourouOLimiteDaResposta("💪".repeat(LIMITE_DA_RESPOSTA))).toBe(false);
    expect(estourouOLimiteDaResposta("💪".repeat(LIMITE_DA_RESPOSTA + 1))).toBe(true);
    expect(estourouOLimiteDaResposta(undefined)).toBe(false);
  });
});

describe("respostaPronta", () => {
  it("devolve o nome e a resposta sem as bordas em branco", () => {
    expect(respostaPronta("  Thiago ", "  Troque por leg press.\n")).toEqual({
      ok: true,
      professor: "Thiago",
      resposta: "Troque por leg press.",
    });
  });

  it("sem nome, pede o nome e põe o cursor no campo do nome", () => {
    for (const nome of ["", "   ", undefined, null, 7]) {
      const r = respostaPronta(nome, "Oi");
      expect(r.ok).toBe(false);
      expect(r.campo).toBe("professor");
      expect(r.mensagem).toContain("nome");
    }
  });

  it("sem resposta, pede a resposta e põe o cursor na caixa", () => {
    for (const texto of ["", "  \n ", undefined, null]) {
      const r = respostaPronta("Thiago", texto);
      expect(r).toEqual({ ok: false, campo: "resposta", mensagem: "Escreva a resposta para o aluno." });
    }
  });

  it("o nome tem limite, e a resposta também", () => {
    const nome = respostaPronta("a".repeat(LIMITE_DO_NOME + 1), "Oi");
    expect(nome.ok).toBe(false);
    expect(nome.campo).toBe("professor");
    expect(respostaPronta("a".repeat(LIMITE_DO_NOME), "Oi").ok).toBe(true);

    const longa = respostaPronta("Thiago", "a".repeat(LIMITE_DA_RESPOSTA + 1));
    expect(longa.ok).toBe(false);
    expect(longa.campo).toBe("resposta");
    expect(respostaPronta("Thiago", "a".repeat(LIMITE_DA_RESPOSTA)).ok).toBe(true);
  });

  it("o limite é em letras, não em unidades do JavaScript (emoji vale 1)", () => {
    expect(respostaPronta("Thiago", "💪".repeat(LIMITE_DA_RESPOSTA)).ok).toBe(true);
    expect(respostaPronta("Thiago", "💪".repeat(LIMITE_DA_RESPOSTA + 1)).ok).toBe(false);
  });
});

describe("pedidoDaResposta", () => {
  it("monta o corpo que o servidor espera", () => {
    expect(pedidoDaResposta("Thiago", "Oi")).toEqual({ professor: "Thiago", resposta: "Oi" });
  });
});

describe("descreverResposta", () => {
  it("200 com ok traz quem respondeu, quando e quantos faltam ler", () => {
    expect(
      descreverResposta(200, { ok: true, respondido_por: "Thiago", respondido_quando: "15/10/2026 21:30", nao_lidos: 2 }),
    ).toEqual({ tipo: "ok", naoLidos: 2, respondidoPor: "Thiago", quando: "15/10/2026 21:30" });
  });

  it("200 sem os números ainda é ok (o contador só não muda)", () => {
    expect(descreverResposta(200, { ok: true, respondido_por: "Thiago" })).toEqual({
      tipo: "ok",
      naoLidos: null,
      respondidoPor: "Thiago",
      quando: "",
    });
  });

  it("401 manda pedir a autorização do computador", () => {
    expect(descreverResposta(401, { erro: "x" })).toEqual({ tipo: "nao-autorizado", mensagem: MENSAGEM_NAO_AUTORIZADO });
  });

  it("404 diz que o comentário sumiu", () => {
    expect(descreverResposta(404, { erro: "Comentário não encontrado." })).toEqual({
      tipo: "erro",
      mensagem: MENSAGEM_COMENTARIO_SUMIU,
    });
  });

  it("409 e 400 mostram a frase do servidor", () => {
    expect(descreverResposta(409, { erro: "Este comentário já foi respondido. Atualize a página." })).toEqual({
      tipo: "erro",
      mensagem: "Este comentário já foi respondido. Atualize a página.",
    });
    expect(descreverResposta(400, { erro: "Digite o seu nome." }).mensagem).toBe("Digite o seu nome.");
  });

  it.each([
    [500, { erro: "" }],
    [500, null],
    [200, { ok: false }],
    [200, { ok: true }],
    [200, null],
  ])("resposta estranha (%s, %j) vira erro com o código na frase", (status, corpo) => {
    const r = descreverResposta(status, corpo);
    expect(r.tipo).toBe("erro");
    expect(r.mensagem).toContain(`código ${status}`);
  });
});
