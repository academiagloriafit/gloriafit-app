import { describe, expect, it } from "vitest";
import { VALIDADE_MS, apagar, chavesDoAluno, gravar, ler, textoDoQuando } from "../app/static/rascunho_local.js";

class Memoria {
  constructor() {
    this.dados = new Map();
  }
  getItem(k) {
    return this.dados.has(k) ? this.dados.get(k) : null;
  }
  setItem(k, v) {
    this.dados.set(k, String(v));
  }
  removeItem(k) {
    this.dados.delete(k);
  }
}

class Quebrado {
  getItem() {
    throw new Error("bloqueado");
  }
  setItem() {
    throw new Error("cota cheia");
  }
  removeItem() {
    throw new Error("bloqueado");
  }
}

const CHAVES = chavesDoAluno(7);
const AGORA = 1_761_500_000_000;

describe("rascunho no navegador", () => {
  it("as chaves são por aluno", () => {
    expect(CHAVES).toEqual({ rascunho: "rascunho-treino-7", dados: "rascunho-dados-7", quando: "rascunho-quando-7" });
  });

  it("grava e lê de volta dentro da validade", () => {
    const arm = new Memoria();

    expect(gravar(arm, CHAVES, "R", "D", AGORA)).toBe(true);

    expect(ler(arm, CHAVES, AGORA + VALIDADE_MS)).toEqual({ rascunho: "R", dados: "D", guardadoEm: AGORA });
  });

  it("vencido: apaga tudo e volta vazio", () => {
    const arm = new Memoria();
    gravar(arm, CHAVES, "R", "D", AGORA);

    expect(ler(arm, CHAVES, AGORA + VALIDADE_MS + 1)).toEqual({ rascunho: null, dados: null, guardadoEm: null });
    expect(arm.dados.size).toBe(0);
  });

  it("rascunho antigo, sem data (da versão do sessionStorage) ou com data estranha, é descartado", () => {
    for (const quando of [null, "abc", "-5", String(AGORA + 10 * 60 * 1000)]) {
      const arm = new Memoria();
      arm.setItem(CHAVES.rascunho, "R");
      if (quando !== null) arm.setItem(CHAVES.quando, quando);

      expect(ler(arm, CHAVES, AGORA).rascunho).toBeNull();
      expect(arm.getItem(CHAVES.rascunho)).toBeNull();
    }
  });

  it("navegador sem armazenamento ou que dá erro: a tela segue sem rascunho", () => {
    expect(ler(null, CHAVES)).toEqual({ rascunho: null, dados: null, guardadoEm: null });
    expect(ler(new Quebrado(), CHAVES)).toEqual({ rascunho: null, dados: null, guardadoEm: null });
    expect(gravar(new Quebrado(), CHAVES, "R", "D")).toBe(false);
    expect(gravar(null, CHAVES, "R", "D")).toBe(false);
    expect(() => apagar(new Quebrado(), CHAVES)).not.toThrow();
  });

  it("apagar tira as três chaves e não mexe nas de outro aluno", () => {
    const arm = new Memoria();
    gravar(arm, CHAVES, "R", "D", AGORA);
    gravar(arm, chavesDoAluno(8), "R8", "D8", AGORA);

    apagar(arm, CHAVES);

    expect(arm.getItem(CHAVES.rascunho)).toBeNull();
    expect(arm.getItem("rascunho-treino-8")).toBe("R8");
  });

  it("textoDoQuando escreve dia, mês e hora", () => {
    expect(textoDoQuando(new Date(2026, 9, 26, 9, 5).getTime())).toBe("26/10 às 09:05");
  });
});
