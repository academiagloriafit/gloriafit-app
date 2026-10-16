import { describe, expect, it } from "vitest";
import {
  DICA_DO_COMENTARIO_DO_EXERCICIO,
  DICA_DO_COMENTARIO_DO_TREINO,
  LIMITE_DO_COMENTARIO,
  MENSAGEM_SEM_REDE,
  MINIMO_DA_SENHA,
  TAMANHO_DO_CODIGO,
  TEXTO_COMENTARIO_ENVIADO,
  TEXTO_COMENTARIO_REPETIDO,
  TEXTO_COMENTARIO_VAZIO,
  TEXTO_FICHA_FEITA_HOJE,
  TEXTO_JA_MARCADA,
  TEXTO_SEM_EXERCICIOS,
  TEXTO_SEM_TREINO,
  chaveDoRascunho,
  comentarioPronto,
  conferirCodigo,
  conferirCpf,
  conferirSenhaNova,
  descreverComentario,
  dicaDoComentario,
  descreverMarcacao,
  descreverResposta,
  descreverTreino,
  estourouOLimite,
  fichaEscolhida,
  formatarCpf,
  linhasDoExercicio,
  pedidoDoComentario,
  soNumeros,
  textoDasDatas,
  textoDoAndamento,
  textoDoContador,
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

describe("comentários do aluno", () => {
  const treino = { nome: "TREINO ABC" };
  const ficha = { ordem: 2, nome: "B PERNA" };
  const exercicio = { ordem: 3, exercicio: "CADEIRA ABDUTORA" };

  it("o limite combina com o do servidor (500)", () => {
    expect(LIMITE_DO_COMENTARIO).toBe(500);
  });

  describe("textoDoContador", () => {
    it("mostra quantas letras já tem", () => {
      expect(textoDoContador("")).toBe("0 de 500");
      expect(textoDoContador("Dói o ombro")).toBe("11 de 500");
    });
    it("conta emoji como uma letra só, como o servidor", () => {
      expect(textoDoContador("💪💪")).toBe("2 de 500");
    });
    it("lixo vira zero", () => {
      expect(textoDoContador(null)).toBe("0 de 500");
      expect(textoDoContador(undefined)).toBe("0 de 500");
    });
  });

  describe("comentarioPronto", () => {
    it("tira as bordas em branco e aceita", () => {
      expect(comentarioPronto("  Está leve demais \n")).toEqual({ ok: true, texto: "Está leve demais" });
    });
    it.each([[""], ["   "], ["\n\t"], [null], [undefined], [7]])("recusa vazio (%j)", (texto) => {
      expect(comentarioPronto(texto)).toEqual({ ok: false, mensagem: TEXTO_COMENTARIO_VAZIO });
    });
    it("aceita 500 letras e recusa 501", () => {
      expect(comentarioPronto("x".repeat(500)).ok).toBe(true);
      const longo = comentarioPronto("x".repeat(501));
      expect(longo.ok).toBe(false);
      expect(longo.mensagem).toContain("500");
    });
    it("o limite conta letras, não bytes: 500 emojis passam", () => {
      expect(comentarioPronto("💪".repeat(500)).ok).toBe(true);
      expect(comentarioPronto("💪".repeat(501)).ok).toBe(false);
    });
  });

  describe("pedidoDoComentario", () => {
    it("treino inteiro: só o nome do treino e o texto", () => {
      expect(pedidoDoComentario(treino, "oi")).toEqual({ treino: "TREINO ABC", texto: "oi" });
    });
    it("exercício: ficha, número do exercício e o nome que o aluno viu", () => {
      expect(pedidoDoComentario(treino, "oi", ficha, exercicio)).toEqual({
        treino: "TREINO ABC",
        texto: "oi",
        ficha: 2,
        item: 3,
        exercicio: "CADEIRA ABDUTORA",
      });
    });
    it("ficha sem exercício (ou ao contrário) vale como treino inteiro: nunca manda o pedido pela metade", () => {
      expect(pedidoDoComentario(treino, "oi", ficha, null)).toEqual({ treino: "TREINO ABC", texto: "oi" });
      expect(pedidoDoComentario(treino, "oi", null, exercicio)).toEqual({ treino: "TREINO ABC", texto: "oi" });
    });
    it("não leva ids nem nada além do combinado", () => {
      const chaves = Object.keys(pedidoDoComentario(treino, "oi", ficha, exercicio)).sort();
      expect(chaves).toEqual(["exercicio", "ficha", "item", "texto", "treino"]);
    });
  });

  describe("chaveDoRascunho", () => {
    it("treino inteiro e cada exercício têm chaves diferentes", () => {
      expect(chaveDoRascunho()).toBe("treino");
      expect(chaveDoRascunho(ficha, exercicio)).toBe("2:3");
      expect(chaveDoRascunho({ ordem: 1 }, { ordem: 3 })).toBe("1:3");
    });
  });

  describe("descreverComentario", () => {
    it("401 manda entrar de novo", () => {
      expect(descreverComentario(401, { erro: "x" })).toEqual({ tipo: "entrar" });
    });
    it("200 é ok, com e sem repetição", () => {
      expect(descreverComentario(200, { ok: true, repetido: false })).toEqual({ tipo: "ok", repetido: false });
      expect(descreverComentario(200, { ok: true, repetido: true })).toEqual({ tipo: "ok", repetido: true });
      expect(descreverComentario(200, { ok: true })).toEqual({ tipo: "ok", repetido: false });
    });
    it("409 pede para atualizar a página, com a frase do servidor", () => {
      expect(descreverComentario(409, { erro: "O seu treino mudou." })).toEqual({ tipo: "atualizar", mensagem: "O seu treino mudou." });
    });
    it.each([
      [400, { erro: "Escreva o seu comentário." }, "Escreva o seu comentário."],
      [429, { erro: "Você já enviou muitos comentários hoje." }, "Você já enviou muitos comentários hoje."],
    ])("%s mostra a explicação do servidor", (status, corpo, esperado) => {
      expect(descreverComentario(status, corpo)).toEqual({ tipo: "erro", mensagem: esperado });
    });
    it.each([
      [500, null],
      [500, {}],
      [500, { erro: "" }],
      [200, { ok: false }],
      [200, null],
    ])("resposta estranha (%s, %j) vira erro com o código na frase", (status, corpo) => {
      const r = descreverComentario(status, corpo);
      expect(r.tipo).toBe("erro");
      expect(r.mensagem).toContain(`código ${status}`);
    });
  });

  it("as frases fixas são diferentes entre si", () => {
    expect(TEXTO_COMENTARIO_ENVIADO).not.toBe(TEXTO_COMENTARIO_REPETIDO);
    expect(TEXTO_COMENTARIO_ENVIADO).toContain("professor");
  });
});


describe("estourouOLimite", () => {
  it("é falso até 500 letras e verdadeiro a partir de 501", () => {
    expect(estourouOLimite("a".repeat(LIMITE_DO_COMENTARIO))).toBe(false);
    expect(estourouOLimite("a".repeat(LIMITE_DO_COMENTARIO + 1))).toBe(true);
  });

  it("conta emoji como 1 letra (como o servidor), não como 2", () => {
    expect(estourouOLimite("💪".repeat(LIMITE_DO_COMENTARIO))).toBe(false); // 500 emojis = 1.000 no .length
    expect(estourouOLimite("💪".repeat(LIMITE_DO_COMENTARIO + 1))).toBe(true);
  });

  it("não quebra com o que não é texto", () => {
    expect(estourouOLimite(undefined)).toBe(false);
    expect(estourouOLimite(null)).toBe(false);
    expect(estourouOLimite(42)).toBe(false);
  });
});

describe("dicaDoComentario (a frase cinza da caixa)", () => {
  it("cada caixa tem a sua frase", () => {
    expect(dicaDoComentario(true)).toBe(DICA_DO_COMENTARIO_DO_EXERCICIO);
    expect(dicaDoComentario(false)).toBe(DICA_DO_COMENTARIO_DO_TREINO);
    expect(DICA_DO_COMENTARIO_DO_EXERCICIO).not.toBe(DICA_DO_COMENTARIO_DO_TREINO);
  });

  it("diz que é para o professor e dá exemplos do que contar", () => {
    for (const dica of [DICA_DO_COMENTARIO_DO_EXERCICIO, DICA_DO_COMENTARIO_DO_TREINO]) {
      expect(dica).toContain("Conte ao professor");
      expect(dica.length).toBeLessThan(80); // a caixa do exercício é estreita: precisa caber em umas 3 linhas
    }
    expect(DICA_DO_COMENTARIO_DO_EXERCICIO).toContain("dor");
    expect(DICA_DO_COMENTARIO_DO_EXERCICIO).toContain("dúvida");
    expect(DICA_DO_COMENTARIO_DO_TREINO).toContain("do treino");
  });
});
