import { describe, expect, it } from "vitest";
import {
  MENSAGEM_SEM_REDE,
  MINIMO_DA_SENHA,
  TAMANHO_DO_CODIGO,
  conferirCodigo,
  conferirCpf,
  conferirSenhaNova,
  descreverResposta,
  formatarCpf,
  soNumeros,
  textoDoReenvio,
} from "../app/static/aluno_modelo.js";

describe("soNumeros", () => {
  it("tira tudo que não é algarismo comum", () => {
    expect(soNumeros("111.444.777-35")).toBe("11144477735");
    expect(soNumeros(" 12 34 ")).toBe("1234");
    expect(soNumeros("abc")).toBe("");
  });

  it("corta no máximo pedido", () => {
    expect(soNumeros("123456789012345", 11)).toBe("12345678901");
  });

  it("não aceita algarismos de outras escritas nem sai com o que não é texto", () => {
    expect(soNumeros("١٢٣")).toBe(""); // algarismos arábico-índicos
    expect(soNumeros("１２３")).toBe(""); // algarismos de largura total
    expect(soNumeros(null)).toBe("");
    expect(soNumeros(undefined)).toBe("");
    expect(soNumeros(12345)).toBe("12345");
  });
});

describe("formatarCpf", () => {
  it.each([
    ["", ""],
    ["1", "1"],
    ["111", "111"],
    ["1114", "111.4"],
    ["111444", "111.444"],
    ["1114447", "111.444.7"],
    ["111444777", "111.444.777"],
    ["1114447773", "111.444.777-3"],
    ["11144477735", "111.444.777-35"],
  ])("%s vira %s enquanto digita", (digitado, esperado) => {
    expect(formatarCpf(digitado)).toBe(esperado);
  });

  it("refaz a máscara de um CPF já formatado e corta o que passar de 11 números", () => {
    expect(formatarCpf("111.444.777-35")).toBe("111.444.777-35");
    expect(formatarCpf("111444777359999")).toBe("111.444.777-35");
  });

  it("ignora letras", () => {
    expect(formatarCpf("1a1b1")).toBe("111");
  });
});

describe("conferirCpf", () => {
  it("11 números servem, com ou sem enfeite", () => {
    expect(conferirCpf("11144477735")).toBe("");
    expect(conferirCpf("111.444.777-35")).toBe("");
  });

  it("menos ou mais que 11 não servem", () => {
    expect(conferirCpf("")).toContain("11 números");
    expect(conferirCpf("1114447773")).toContain("11 números");
    expect(conferirCpf("111444777355")).toContain("11 números");
  });
});

describe("conferirCodigo", () => {
  it("6 números servem, com espaço ou hífen no meio", () => {
    expect(TAMANHO_DO_CODIGO).toBe(6);
    expect(conferirCodigo("123456")).toBe("");
    expect(conferirCodigo("123 456")).toBe("");
    expect(conferirCodigo(" 123-456 ")).toBe("");
  });

  it("outro tamanho não serve", () => {
    expect(conferirCodigo("")).toContain("6 números");
    expect(conferirCodigo("12345")).toContain("6 números");
    expect(conferirCodigo("1234567")).toContain("6 números");
  });
});

describe("conferirSenhaNova", () => {
  it("senha de 8 ou mais, repetida igual, serve", () => {
    expect(MINIMO_DA_SENHA).toBe(8);
    expect(conferirSenhaNova("12345678", "12345678")).toBe("");
    expect(conferirSenhaNova("uma senha boa", "uma senha boa")).toBe("");
  });

  it("curta demais não serve (e a frase diz o mínimo)", () => {
    expect(conferirSenhaNova("1234567", "1234567")).toContain("pelo menos 8");
    expect(conferirSenhaNova("", "")).toContain("pelo menos 8");
    expect(conferirSenhaNova(undefined, undefined)).toContain("pelo menos 8");
  });

  it("repetição diferente não serve (inclusive só na maiúscula)", () => {
    expect(conferirSenhaNova("senha boa 1", "senha boa 2")).toBe("As duas senhas não são iguais.");
    expect(conferirSenhaNova("Senha boa 1", "senha boa 1")).toBe("As duas senhas não são iguais.");
  });
});

describe("descreverResposta", () => {
  it("200 com ok: certo, sem mensagem", () => {
    expect(descreverResposta(200, { ok: true, nome: "Ana" })).toEqual({ ok: true, mensagem: "" });
  });

  it("200 sem ok:true NÃO conta como certo (ex.: página qualquer devolvida por um proxy)", () => {
    expect(descreverResposta(200, null).ok).toBe(false);
    expect(descreverResposta(200, {}).ok).toBe(false);
    expect(descreverResposta(200, { ok: false }).ok).toBe(false);
  });

  it.each([
    [400, "Código inválido ou vencido."],
    [401, "CPF ou senha incorretos."],
    [429, "Muitas tentativas. Espere 40 segundos e tente de novo."],
    [503, "O envio do código ainda não está liberado. Fale com a recepção da academia."],
  ])("%i mostra a explicação pronta do servidor", (status, erro) => {
    expect(descreverResposta(status, { erro })).toEqual({ ok: false, mensagem: erro });
  });

  it("erro com status de sucesso e campo erro continua sendo erro", () => {
    expect(descreverResposta(200, { erro: "algo" })).toEqual({ ok: false, mensagem: "algo" });
  });

  it("resposta sem explicação (página de erro, corpo vazio) cai numa frase com o código", () => {
    for (const corpo of [null, {}, { erro: "" }, { erro: 42 }]) {
      const r = descreverResposta(502, corpo);
      expect(r.ok).toBe(false);
      expect(r.mensagem).toContain("código 502");
    }
  });
});

describe("textoDoReenvio", () => {
  it("mostra a contagem enquanto não pode", () => {
    expect(textoDoReenvio(45)).toBe("Enviar o código de novo (em 45 s)");
    expect(textoDoReenvio(0.2)).toBe("Enviar o código de novo (em 1 s)");
  });

  it("sem contagem quando já pode", () => {
    expect(textoDoReenvio(0)).toBe("Enviar o código de novo");
    expect(textoDoReenvio(-3)).toBe("Enviar o código de novo");
  });
});

describe("MENSAGEM_SEM_REDE", () => {
  it("fala de internet, não de servidor técnico", () => {
    expect(MENSAGEM_SEM_REDE).toContain("internet");
  });
});
