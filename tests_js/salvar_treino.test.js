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
  const bons = { nomeTreino: "TREINO ABC 07/10/26", montadoPor: "Ana Paula" };
  const campos = (dados) => validarDadosDoTreino(dados).map((p) => p.campo);

  it("dados bons não têm problema", () => {
    expect(validarDadosDoTreino(bons)).toEqual([]);
  });

  it("'quem montou' vazio ou só com espaços é obrigatório", () => {
    for (const vazio of ["", "   ", "\n\t "]) {
      const problemas = validarDadosDoTreino({ ...bons, montadoPor: vazio });
      expect(problemas).toHaveLength(1);
      expect(problemas[0].campo).toBe("quem-montou");
      expect(problemas[0].mensagem).toBe("Informe quem montou este treino.");
    }
  });

  it("nome do treino vazio é obrigatório", () => {
    const problemas = validarDadosDoTreino({ ...bons, nomeTreino: " " });
    expect(problemas).toEqual([{ campo: "nome-treino", mensagem: "Dê um nome ao treino." }]);
  });

  it("os dois vazios dão dois problemas, um por campo", () => {
    expect(campos({ nomeTreino: "", montadoPor: "" })).toEqual(["nome-treino", "quem-montou"]);
  });

  it("aceita exatamente 40 no nome do treino e 60 em quem montou", () => {
    expect(validarDadosDoTreino({ nomeTreino: "T".repeat(40), montadoPor: "P".repeat(60) })).toEqual([]);
  });

  it("recusa 41 e 61, dizendo quantas letras tem e o máximo", () => {
    const problemas = validarDadosDoTreino({ nomeTreino: "T".repeat(41), montadoPor: "P".repeat(61) });
    expect(problemas.map((p) => p.campo)).toEqual(["nome-treino", "quem-montou"]);
    expect(problemas[0].mensagem).toContain("41");
    expect(problemas[0].mensagem).toContain("40");
    expect(problemas[0].mensagem).toContain("Data4U");
    expect(problemas[1].mensagem).toContain("61");
    expect(problemas[1].mensagem).toContain("60");
  });

  it("os espaços a mais não contam (o servidor também os junta)", () => {
    const dados = { nomeTreino: "  " + "T".repeat(40) + "   ", montadoPor: "Ana     Paula" };
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

    expect(Object.keys(pedido).sort()).toEqual(["fichas", "montado_por", "nome_treino"]);
    expect(pedido.nome_treino).toBe("TREINO A 07/10/26");
    expect(pedido.montado_por).toBe("Ana Paula");
    expect(pedido.fichas).toHaveLength(1);
    expect(pedido.fichas[0].nome).toBe("TREINO A");
    expect(pedido.fichas[0].itens.map((i) => [i.exercicio_id, i.series, i.repeticoes, i.carga, i.bloco])).toEqual([
      [11, "3", "12", "20", 1],
      [22, "3", "12", "", 1],
      [33, "4", "10", "15 kg", null],
    ]);
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
