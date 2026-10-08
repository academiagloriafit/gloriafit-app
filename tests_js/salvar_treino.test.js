import { describe, expect, it } from "vitest";
import {
  LIMITE_NOME_TREINO,
  LIMITE_QUEM_MONTOU,
  adicionarFicha,
  adicionarItem,
  atualizarItem,
  criarEstado,
  formatarData,
  limparEspacos,
  montarPedido,
  renomearFicha,
  sugerirNomeDoTreino,
  tamanho,
  unirEmBloco,
  validarDadosDoTreino,
  lerDia,
  lerSessoesPorFicha,
} from "../app/static/treino_modelo.js";

const DATA = "07/10/26";

function comFichas(...nomes) {
  let e = criarEstado();
  nomes.forEach((nome, i) => {
    if (i > 0) e = adicionarFicha(e);
    e = renomearFicha(e, i, nome);
  });
  return e;
}

describe("limites", () => {
  it("são os do Data4U (40) e o nosso (60)", () => {
    expect(LIMITE_NOME_TREINO).toBe(40);
    expect(LIMITE_QUEM_MONTOU).toBe(60);
  });
});

describe("limparEspacos e tamanho", () => {
  it("tira espaços das pontas e junta os do meio", () => {
    expect(limparEspacos("  Ana \n  Paula\t ")).toBe("Ana Paula");
    expect(limparEspacos("   ")).toBe("");
  });

  it("conta caracteres como o servidor: emoji vale 1", () => {
    expect(tamanho("abc")).toBe(3);
    expect(tamanho("😀😀")).toBe(2);
    expect("😀😀".length).toBe(4); // é por isso que não dá para usar .length
  });
});

describe("formatarData", () => {
  it("dia/mês/ano com 2 dígitos cada", () => {
    expect(formatarData(new Date(2026, 9, 7))).toBe("07/10/26");
    expect(formatarData(new Date(2027, 0, 31))).toBe("31/01/27");
    expect(formatarData(new Date(2100, 11, 1))).toBe("01/12/00");
  });
});

describe("sugerirNomeDoTreino", () => {
  it("fichas Treino A, B, C viram 'TREINO ABC' com a data", () => {
    const e = comFichas("TREINO A", "TREINO B", "TREINO C");
    expect(sugerirNomeDoTreino(e, DATA)).toBe("TREINO ABC 07/10/26");
  });

  it("fichas FICHA A, B, C (nomes que o app dá sozinho) viram 'TREINO ABC' com a data", () => {
    const e = comFichas("FICHA A", "FICHA B", "FICHA C");
    expect(sugerirNomeDoTreino(e, DATA)).toBe("TREINO ABC 07/10/26");
  });

  it("FICHA e TREINO misturados também valem; 'FICHA AB' (duas letras) entra como nome", () => {
    expect(sugerirNomeDoTreino(comFichas("ficha a", "TREINO B"), DATA)).toBe("TREINO AB 07/10/26");
    expect(sugerirNomeDoTreino(comFichas("FICHA AB"), DATA)).toBe("FICHA AB 07/10/26");
  });

  it("uma ficha só: 'TREINO A'", () => {
    expect(sugerirNomeDoTreino(criarEstado(), DATA)).toBe("TREINO A 07/10/26");
  });

  it("aceita minúsculas e espaços a mais nos nomes padrão", () => {
    const e = comFichas("treino  a", " Treino B ");
    expect(sugerirNomeDoTreino(e, DATA)).toBe("TREINO AB 07/10/26");
  });

  it("segue a ordem das fichas, não a ordem alfabética", () => {
    const e = comFichas("TREINO C", "TREINO A");
    expect(sugerirNomeDoTreino(e, DATA)).toBe("TREINO CA 07/10/26");
  });

  it("se um nome não é do padrão, junta os nomes com ' + '", () => {
    const e = comFichas("A PEITO", "TREINO B");
    expect(sugerirNomeDoTreino(e, DATA)).toBe("A PEITO + TREINO B 07/10/26");
  });

  it("'TREINO AB' (duas letras) não é padrão: entra como nome", () => {
    const e = comFichas("TREINO AB");
    expect(sugerirNomeDoTreino(e, DATA)).toBe("TREINO AB 07/10/26");
  });

  it("nunca passa de 40 letras e a data fica inteira", () => {
    const e = comFichas("A POSTERIOR/CORRIDA", "B SUPERIOR/POSTURA", "C QUADRICEPS/CORE");
    const nome = sugerirNomeDoTreino(e, DATA);
    expect(tamanho(nome)).toBeLessThanOrEqual(LIMITE_NOME_TREINO);
    expect(nome.endsWith(" 07/10/26")).toBe(true);
    expect(nome.startsWith("A POSTERIOR/CORRIDA + B SUPERIO ")).toBe(true);
  });

  it("usa exatamente 40 quando precisa cortar", () => {
    const e = comFichas("X".repeat(15), "Y".repeat(15), "Z".repeat(15));
    const nome = sugerirNomeDoTreino(e, DATA);
    expect(tamanho(nome)).toBe(40);
    const semData = nome.slice(0, -DATA.length - 1);
    // sobram 40 - 9 (" 07/10/26") = 31 letras para o nome: 15 + 3 (" + ") + 13
    expect(semData).toBe("X".repeat(15) + " + " + "Y".repeat(13));
  });

  it("corte que cai logo depois de um espaço não deixa espaço duplo antes da data", () => {
    // sobram 31 letras para o nome; "A"*15 + " + " + "B"*12 tem 30, então a 31ª é o espaço de " + "
    const e = comFichas("A".repeat(15), "B".repeat(12), "C".repeat(10));
    const nome = sugerirNomeDoTreino(e, DATA);
    expect(nome).toBe("A".repeat(15) + " + " + "B".repeat(12) + " 07/10/26");
  });

  it("corta por caractere inteiro (emoji não é partido ao meio)", () => {
    const e = comFichas("😀".repeat(15), "😀".repeat(15), "😀".repeat(15));
    const nome = sugerirNomeDoTreino(e, DATA);
    expect(tamanho(nome)).toBeLessThanOrEqual(40);
    expect(nome).not.toMatch(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])/); // sem metade de emoji
  });

  it("sem data, devolve só a base", () => {
    expect(sugerirNomeDoTreino(criarEstado(), "")).toBe("TREINO A");
    expect(sugerirNomeDoTreino(criarEstado(), undefined)).toBe("TREINO A");
  });

  it("fichas sem nome não quebram", () => {
    const e = comFichas("  ");
    expect(sugerirNomeDoTreino(e, DATA)).toBe("TREINO 07/10/26");
  });

  it("não altera o estado", () => {
    const e = comFichas("TREINO A", "TREINO B");
    const antes = JSON.stringify(e);
    sugerirNomeDoTreino(e, DATA);
    expect(JSON.stringify(e)).toBe(antes);
  });
});

describe("validarDadosDoTreino", () => {
  const bons = { nomeTreino: "TREINO ABC 07/10/26", montadoPor: "Ana Paula", inicio: "2026-10-08" };
  const campos = (dados) => validarDadosDoTreino(dados).map((p) => p.campo);

  it("dados bons não têm problema", () => {
    expect(validarDadosDoTreino(bons)).toEqual([]);
  });

  it("professor vazio ou só com espaços é obrigatório", () => {
    for (const vazio of ["", "   ", "\n\t "]) {
      const problemas = validarDadosDoTreino({ ...bons, montadoPor: vazio });
      expect(problemas).toHaveLength(1);
      expect(problemas[0].campo).toBe("quem-montou");
      expect(problemas[0].mensagem).toBe("Informe o professor que montou o treino.");
    }
  });

  it("nome do treino vazio é obrigatório", () => {
    const problemas = validarDadosDoTreino({ ...bons, nomeTreino: " " });
    expect(problemas).toEqual([{ campo: "nome-treino", mensagem: "Dê um nome ao treino." }]);
  });

  it("os dois vazios dão dois problemas, um por campo", () => {
    expect(campos({ ...bons, nomeTreino: "", montadoPor: "" })).toEqual(["nome-treino", "quem-montou"]);
  });

  it("aceita exatamente 40 no nome do treino e 60 em quem montou", () => {
    expect(validarDadosDoTreino({ ...bons, nomeTreino: "T".repeat(40), montadoPor: "P".repeat(60) })).toEqual([]);
  });

  it("recusa 41 e 61, dizendo quantas letras tem e o máximo", () => {
    const problemas = validarDadosDoTreino({ ...bons, nomeTreino: "T".repeat(41), montadoPor: "P".repeat(61) });
    expect(problemas.map((p) => p.campo)).toEqual(["nome-treino", "quem-montou"]);
    expect(problemas[0].mensagem).toContain("41");
    expect(problemas[0].mensagem).toContain("40");
    expect(problemas[0].mensagem).toContain("Data4U");
    expect(problemas[1].mensagem).toContain("61");
    expect(problemas[1].mensagem).toContain("60");
  });

  it("os espaços a mais não contam (o servidor também os junta)", () => {
    const dados = { ...bons, nomeTreino: "  " + "T".repeat(40) + "   ", montadoPor: "Ana     Paula" };
    expect(validarDadosDoTreino(dados)).toEqual([]);
  });

  it("conta por caractere: 60 emojis passam, 61 não", () => {
    expect(validarDadosDoTreino({ ...bons, montadoPor: "😀".repeat(60) })).toEqual([]);
    expect(campos({ ...bons, montadoPor: "😀".repeat(61) })).toEqual(["quem-montou"]);
  });

  it("recusa caracteres invisíveis e de controle", () => {
    for (const sujeira of ["Ana\u0000Paula", "Ana​Paula", "Ana\u0007", "Ana‮luaP"]) {
      const problemas = validarDadosDoTreino({ ...bons, montadoPor: sujeira });
      expect(problemas, JSON.stringify(sujeira)).toHaveLength(1);
      expect(problemas[0].mensagem).toContain("inválidos");
    }
  });

  it("aceita acentos, apóstrofo, hífen e ponto", () => {
    expect(validarDadosDoTreino({ ...bons, montadoPor: "João D'Ávila-Souza Jr." })).toEqual([]);
  });

  describe("início, fim e treinos por ficha", () => {
    it("fim e treinos por ficha são opcionais", () => {
      expect(validarDadosDoTreino({ ...bons, fim: "", sessoesPorFicha: "" })).toEqual([]);
      expect(validarDadosDoTreino({ ...bons, fim: "2026-12-31", sessoesPorFicha: "15" })).toEqual([]);
    });

    it("o início é obrigatório", () => {
      expect(validarDadosDoTreino({ ...bons, inicio: "" })).toEqual([
        { campo: "data-inicio", mensagem: "Informe a data de início do treino." },
      ]);
    });

    it("o fim pode ser o mesmo dia do início", () => {
      expect(validarDadosDoTreino({ ...bons, inicio: "2026-10-08", fim: "2026-10-08" })).toEqual([]);
    });

    it("o fim não pode ser antes do início", () => {
      const problemas = validarDadosDoTreino({ ...bons, inicio: "2026-10-08", fim: "2026-10-07" });
      expect(problemas.map((p) => p.campo)).toEqual(["data-fim"]);
      expect(problemas[0].mensagem).toContain("antes");
    });

    it.each(["2026-02-30", "2026-13-01", "2026-1-5", "08/10/2026", "2026-10-081", "ontem", "２０２６-10-08"])(
      "recusa a data inválida %s",
      (texto) => {
        expect(campos({ ...bons, inicio: texto })).toEqual(["data-inicio"]);
        expect(campos({ ...bons, fim: texto })).toEqual(["data-fim"]);
      },
    );

    it("recusa ano fora de 2020 a 2100 (erro de digitação)", () => {
      expect(campos({ ...bons, inicio: "0202-10-08" })).toEqual(["data-inicio"]);
      expect(campos({ ...bons, fim: "2206-10-08" })).toEqual(["data-fim"]);
      expect(campos({ ...bons, inicio: "2019-12-31" })).toEqual(["data-inicio"]);
      expect(campos({ ...bons, inicio: "2100-12-31", fim: "2100-12-31" })).toEqual([]);
    });

    it("aceita 29/02 só em ano bissexto", () => {
      expect(campos({ ...bons, inicio: "2028-02-29" })).toEqual([]);
      expect(campos({ ...bons, inicio: "2027-02-29" })).toEqual(["data-inicio"]);
    });

    it.each(["1", "15", " 15 ", "999", "007"])("aceita %j treinos por ficha", (texto) => {
      expect(campos({ ...bons, sessoesPorFicha: texto })).toEqual([]);
    });

    it.each(["0", "1000", "-1", "1.5", "1,5", "quinze", "15x", "1e2", "０５"])("recusa %j treinos por ficha", (texto) => {
      expect(campos({ ...bons, sessoesPorFicha: texto })).toEqual(["sessoes-por-ficha"]);
    });
  });
});

describe("lerDia e lerSessoesPorFicha", () => {
  it("lerDia devolve o próprio texto quando a data existe", () => {
    expect(lerDia("2026-10-08")).toBe("2026-10-08");
    expect(lerDia("2026-02-30")).toBeNull();
    expect(lerDia(null)).toBeNull();
    expect(lerDia(20261008)).toBeNull();
  });

  it("lerSessoesPorFicha: vazio é null, número é número, o resto é undefined", () => {
    expect(lerSessoesPorFicha("")).toBeNull();
    expect(lerSessoesPorFicha("   ")).toBeNull();
    expect(lerSessoesPorFicha(undefined)).toBeNull();
    expect(lerSessoesPorFicha("15")).toBe(15);
    expect(lerSessoesPorFicha("0")).toBeUndefined();
    expect(lerSessoesPorFicha("abc")).toBeUndefined();
  });
});

describe("montarPedido", () => {
  function treinoPronto() {
    let e = criarEstado();
    e = adicionarItem(e, 0, { id: 11, nome: "SUPINO" });
    e = adicionarItem(e, 0, { id: 22, nome: "CRUCIFIXO" });
    e = adicionarItem(e, 0, { id: 33, nome: "REMADA" });
    for (const [uid, series, reps, carga] of [
      [1, " 3 ", "12", "20"],
      [2, "3", "12", ""],
      [3, "4", "10", " 15 kg "],
    ]) {
      e = atualizarItem(e, 0, uid, "series", series);
      e = atualizarItem(e, 0, uid, "repeticoes", reps);
      e = atualizarItem(e, 0, uid, "carga", carga);
    }
    return unirEmBloco(e, 0, [1, 2]).estado;
  }

  it("monta exatamente o que o servidor espera", () => {
    const pedido = montarPedido(treinoPronto(), { nomeTreino: "TREINO A 07/10/26", montadoPor: "Ana Paula" });

    expect(Object.keys(pedido).sort()).toEqual([
      "fichas", "fim", "inicio", "montado_por", "nome_treino", "sessoes_por_ficha",
    ]);
    expect(pedido.nome_treino).toBe("TREINO A 07/10/26");
    expect(pedido.montado_por).toBe("Ana Paula");
    expect(pedido.fichas).toHaveLength(1);
    expect(pedido.fichas[0].nome).toBe("FICHA A");
    expect(pedido.fichas[0].itens.map((i) => [i.exercicio_id, i.series, i.repeticoes, i.carga, i.bloco])).toEqual([
      [11, "3", "12", "20", 1],
      [22, "3", "12", "", 1],
      [33, "4", "10", "15 kg", null],
    ]);
  });

  it("leva início, fim e treinos por ficha; vazio vira null", () => {
    const completo = montarPedido(treinoPronto(), {
      nomeTreino: "x", montadoPor: "y", inicio: "2026-10-08", fim: "2026-12-31", sessoesPorFicha: " 15 ",
    });
    expect([completo.inicio, completo.fim, completo.sessoes_por_ficha]).toEqual(["2026-10-08", "2026-12-31", 15]);

    const simples = montarPedido(treinoPronto(), { nomeTreino: "x", montadoPor: "y", inicio: "2026-10-08", fim: "", sessoesPorFicha: "" });
    expect([simples.inicio, simples.fim, simples.sessoes_por_ficha]).toEqual(["2026-10-08", null, null]);
  });

  it("limpa os espaços dos dois textos digitados", () => {
    const pedido = montarPedido(treinoPronto(), { nomeTreino: "  Meu   treino ", montadoPor: "  Ana   Paula " });
    expect(pedido.nome_treino).toBe("Meu treino");
    expect(pedido.montado_por).toBe("Ana Paula");
  });

  it("passa o texto digitado como está, sem interpretar (o servidor guarda como texto)", () => {
    const pedido = montarPedido(treinoPronto(), { nomeTreino: "x", montadoPor: "<b>Ana</b>'; DROP TABLE treino;--" });
    expect(pedido.montado_por).toBe("<b>Ana</b>'; DROP TABLE treino;--");
  });

  it("não altera o estado da tela", () => {
    const e = treinoPronto();
    const antes = JSON.stringify(e);
    montarPedido(e, { nomeTreino: "x", montadoPor: "y" });
    expect(JSON.stringify(e)).toBe(antes);
  });

  it("vira JSON sem perder nada", () => {
    const pedido = montarPedido(treinoPronto(), { nomeTreino: "x", montadoPor: "y" });
    expect(JSON.parse(JSON.stringify(pedido))).toEqual(pedido);
  });
});
