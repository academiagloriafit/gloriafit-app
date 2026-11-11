import { describe, expect, it } from "vitest";
import { andamentoDoAluno, filtroValido, parametrosDaBusca, textoDoUltimoTreino, ultimoTreinoEmAlerta } from "../app/static/painel_alunos_modelo.js";

describe("tela Alunos do professor (11/11/2026)", () => {
  it("só aceita filtros conhecidos", () => {
    expect(filtroValido("trocar")).toBe("trocar");
    expect(filtroValido("<script>")).toBe("");
    expect(filtroValido(undefined)).toBe("");
  });
  it("texto do último treino", () => {
    expect(textoDoUltimoTreino(0)).toBe("Hoje");
    expect(textoDoUltimoTreino(1)).toBe("Ontem");
    expect(textoDoUltimoTreino(9)).toBe("Há 9 dias");
    expect(textoDoUltimoTreino(null)).toBe("Nunca registrou");
  });
  it("alerta a partir de 7 dias (e quem nunca registrou)", () => {
    expect(ultimoTreinoEmAlerta(6)).toBe(false);
    expect(ultimoTreinoEmAlerta(7)).toBe(true);
    expect(ultimoTreinoEmAlerta(null)).toBe(true);
  });
  it("andamento com e sem meta", () => {
    expect(andamentoDoAluno({ treino_atual: "ABC", sessoes_feitas: 18, sessoes_meta: 30 })).toEqual({ texto: "18 de 30 sessões", fracao: 0.6 });
    expect(andamentoDoAluno({ treino_atual: "ABC", sessoes_feitas: 40, sessoes_meta: 30 }).fracao).toBe(1);
    expect(andamentoDoAluno({ treino_atual: "ABC", sessoes_feitas: 1, sessoes_meta: null })).toEqual({ texto: "1 sessão", fracao: null });
    expect(andamentoDoAluno({ treino_atual: null })).toEqual({ texto: "", fracao: null });
  });
  it("parâmetros da busca", () => {
    expect(parametrosDaBusca(" ana ", "trocar")).toBe("q=ana&filtro=trocar");
    expect(parametrosDaBusca("", "xx")).toBe("");
  });
});
