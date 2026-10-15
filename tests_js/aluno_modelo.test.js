import { describe, expect, it } from "vitest";
import {
  MENSAGEM_SEM_REDE,
  MINIMO_DA_SENHA,
  TAMANHO_DO_CODIGO,
  TEXTO_FICHA_FEITA_HOJE,
  TEXTO_JA_MARCADA,
  TEXTO_SEM_EXERCICIOS,
  TEXTO_SEM_TREINO,
  conferirCodigo,
  conferirCpf,
  conferirSenhaNova,
  descreverMarcacao,
  descreverResposta,
  descreverTreino,
  fichaEscolhida,
  formatarCpf,
  linhasDoExercicio,
  soNumeros,
  textoDasDatas,
  textoDoAndamento,
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


describe("descreverTreino", () => {
  const treino = { nome: "TREINO ABC", inicio: "06/10/2026", fim: null, fichas: [{ nome: "A", grupos: [] }] };

  it("401 manda o aluno para a tela de entrar", () => {
    expect(descreverTreino(401, { erro: "Você precisa entrar de novo." })).toEqual({ tipo: "entrar" });
    expect(descreverTreino(401, null)).toEqual({ tipo: "entrar" });
  });

  it("treino nulo = sem treino ativo", () => {
    expect(descreverTreino(200, { treino: null })).toEqual({ tipo: "sem-treino" });
  });

  it("treino com fichas é mostrado", () => {
    expect(descreverTreino(200, { treino })).toEqual({ tipo: "treino", treino });
  });

  it("treino sem nenhuma ficha vira o aviso de treino sem exercícios", () => {
    expect(descreverTreino(200, { treino: { ...treino, fichas: [] } })).toEqual({ tipo: "sem-exercicios" });
  });

  it.each([
    [200, null],
    [200, {}],
    [200, { treino: "texto" }],
    [200, { treino: { nome: "X" } }],
    [200, { treino: { fichas: "A" } }],
    [500, null],
    [503, { erro: "x" }],
  ])("resposta estranha (%s, %j) vira erro com o código na frase", (status, corpo) => {
    const r = descreverTreino(status, corpo);
    expect(r.tipo).toBe("erro");
    expect(r.mensagem).toContain(`código ${status}`);
  });

  it("as frases de aviso mandam falar com o professor", () => {
    expect(TEXTO_SEM_TREINO).toContain("professor");
    expect(TEXTO_SEM_EXERCICIOS).toContain("professor");
  });
});

describe("textoDasDatas", () => {
  it("mostra início e fim", () => {
    expect(textoDasDatas({ inicio: "06/10/2026", fim: "06/11/2026" })).toBe("Início 06/10/2026 · Fim 06/11/2026");
  });

  it("mostra só o que existe", () => {
    expect(textoDasDatas({ inicio: "06/10/2026", fim: null })).toBe("Início 06/10/2026");
    expect(textoDasDatas({ inicio: null, fim: "06/11/2026" })).toBe("Fim 06/11/2026");
    expect(textoDasDatas({ inicio: null, fim: null })).toBe("");
  });
});

describe("linhasDoExercicio", () => {
  it("junta dose e carga numa linha, e põe intervalo e observação em linhas separadas", () => {
    expect(
      linhasDoExercicio({ dose: "4 × 12", carga: "20 kg", intervalo: "1 min 30 s", observacao: "Descer devagar" }),
    ).toEqual(["4 × 12 · 20 kg", "Intervalo: 1 min 30 s", "Obs.: Descer devagar"]);
  });

  it("não inventa linha para o que está vazio", () => {
    expect(linhasDoExercicio({ dose: "4 × 12", carga: "", intervalo: "", observacao: "" })).toEqual(["4 × 12"]);
    expect(linhasDoExercicio({ dose: "", carga: "20 kg", intervalo: "", observacao: "" })).toEqual(["20 kg"]);
    expect(linhasDoExercicio({ dose: "", carga: "", intervalo: "", observacao: "20 minutos" })).toEqual(["Obs.: 20 minutos"]);
    expect(linhasDoExercicio({ dose: "", carga: "", intervalo: "", observacao: "" })).toEqual([]);
  });

  it("ignora dose e carga só com espaços", () => {
    expect(linhasDoExercicio({ dose: "  ", carga: " ", intervalo: "", observacao: "" })).toEqual([]);
  });
});

describe("fichaEscolhida", () => {
  const fichas = [{}, {}, {}];

  it("usa a ficha pedida quando ela existe", () => {
    expect(fichaEscolhida(fichas, 0)).toBe(0);
    expect(fichaEscolhida(fichas, 2)).toBe(2);
  });

  it("cai na primeira quando o número não serve", () => {
    for (const ruim of [3, -1, 1.5, NaN, undefined, null, "1"]) expect(fichaEscolhida(fichas, ruim)).toBe(0);
  });
});


describe("textoDoAndamento", () => {
  it("com meta mostra feitas de meta", () => {
    expect(textoDoAndamento({ feitas: 3 }, 15)).toBe("Você fez esta ficha 3 de 15 vezes");
    expect(textoDoAndamento({ feitas: 0 }, 15)).toBe("Você fez esta ficha 0 de 15 vezes");
  });

  it("sem meta conta só o que foi feito", () => {
    expect(textoDoAndamento({ feitas: 0 }, null)).toBe("Você ainda não fez esta ficha");
    expect(textoDoAndamento({ feitas: 1 }, null)).toBe("Você fez esta ficha 1 vez");
    expect(textoDoAndamento({ feitas: 4 }, null)).toBe("Você fez esta ficha 4 vezes");
  });

  it("dado estranho não quebra nem mostra 'NaN'", () => {
    expect(textoDoAndamento({ feitas: "3" }, null)).toBe("Você ainda não fez esta ficha");
    expect(textoDoAndamento({}, undefined)).toBe("Você ainda não fez esta ficha");
    expect(textoDoAndamento(undefined, 0)).toBe("Você ainda não fez esta ficha");
    expect(textoDoAndamento({ feitas: -2 }, 10)).toBe("Você fez esta ficha 0 de 10 vezes");
  });
});

describe("descreverMarcacao", () => {
  it("401 manda para a tela de entrar", () => {
    expect(descreverMarcacao(401, { erro: "x" })).toEqual({ tipo: "entrar" });
  });

  it("200 com ok devolve quantas vezes e se já estava marcada", () => {
    expect(descreverMarcacao(200, { ok: true, ficha: 1, ja_marcada: false, feitas: 4 })).toEqual({ tipo: "ok", feitas: 4, jaMarcada: false });
    expect(descreverMarcacao(200, { ok: true, ficha: 1, ja_marcada: true, feitas: 4 })).toEqual({ tipo: "ok", feitas: 4, jaMarcada: true });
    expect(descreverMarcacao(200, { ok: true, ficha: 1, feitas: 0 })).toEqual({ tipo: "ok", feitas: 0, jaMarcada: false }); // desfazer
  });

  it("erro com explicação do servidor mostra a explicação", () => {
    expect(descreverMarcacao(409, { erro: "Você não tem um treino ativo. Atualize a página." })).toEqual({
      tipo: "erro",
      mensagem: "Você não tem um treino ativo. Atualize a página.",
    });
  });

  it.each([
    [200, null],
    [200, { ok: true }],
    [200, { ok: true, feitas: "3" }],
    [200, { ok: false, feitas: 1 }],
    [500, null],
    [500, { erro: "" }],
  ])("resposta estranha (%s, %j) vira erro com o código na frase", (status, corpo) => {
    const r = descreverMarcacao(status, corpo);
    expect(r.tipo).toBe("erro");
    expect(r.mensagem).toContain(`código ${status}`);
  });

  it("as frases fixas existem e são diferentes", () => {
    expect(TEXTO_FICHA_FEITA_HOJE).not.toBe(TEXTO_JA_MARCADA);
    expect(TEXTO_JA_MARCADA).toContain("já");
  });
});
