import { describe, expect, it } from "vitest";
import {
  LIMITE_CAMPO,
  LIMITE_NOME_FICHA,
  LIMITE_OBSERVACAO,
  MAXIMO_FICHAS,
  MAXIMO_ITENS_POR_FICHA,
  adicionarFicha,
  adicionarItem,
  atualizarItem,
  contarExercicios,
  contarIndisponiveis,
  criarEstado,
  descreverFicha,
  enderecoDeImpressao,
  desfazerBloco,
  estadoDeImportacao,
  etiquetas,
  lerRascunho,
  metaDaImportacao,
  montarPedidoDePadrao,
  moverUnidade,
  paraEnvio,
  pausaEmSegundos,
  removerFicha,
  removerItem,
  renomearFicha,
  serializar,
  unidades,
  unirEmBloco,
  validar,
  validarDadosDoPadrao,
} from "../app/static/treino_modelo.js";

// ---------------------------------------------------------------- auxiliares

const ex = (id) => ({ id, nome: "EXERCICIO " + id });

// Estado com n exercícios (ids 1..n) na ficha 0. Os uids saem 1..n.
function comItens(n) {
  let e = criarEstado();
  for (let i = 1; i <= n; i++) e = adicionarItem(e, 0, ex(i));
  return e;
}

function preencher(estado) {
  let e = estado;
  e.fichas.forEach((ficha, f) =>
    ficha.itens.forEach((item) => {
      e = atualizarItem(e, f, item.uid, "series", "3");
      e = atualizarItem(e, f, item.uid, "repeticoes", "12");
    }),
  );
  return e;
}

const uids = (estado, f = 0) => estado.fichas[f].itens.map((i) => i.uid);
const blocos = (estado, f = 0) => estado.fichas[f].itens.map((i) => i.bloco);

// ---------------------------------------------------------------- fichas

describe("fichas", () => {
  it("começa com uma ficha vazia chamada FICHA A (palavras do Data4U: o treino tem fichas)", () => {
    const e = criarEstado();
    expect(e.fichas).toEqual([{ nome: "FICHA A", itens: [] }]);
  });

  it("novas fichas ganham a próxima letra livre", () => {
    let e = adicionarFicha(criarEstado());
    e = adicionarFicha(e);
    expect(e.fichas.map((f) => f.nome)).toEqual(["FICHA A", "FICHA B", "FICHA C"]);
  });

  it("não repete um nome padrão que já existe, mesmo depois de renomear", () => {
    let e = adicionarFicha(criarEstado()); // A, B
    e = renomearFicha(e, 0, "PERNAS"); // PERNAS, B
    e = adicionarFicha(e);
    expect(e.fichas.map((f) => f.nome)).toEqual(["PERNAS", "FICHA B", "FICHA A"]);
  });

  it("para em 26 fichas", () => {
    let e = criarEstado();
    for (let i = 0; i < 40; i++) e = adicionarFicha(e);
    expect(e.fichas).toHaveLength(MAXIMO_FICHAS);
    expect(new Set(e.fichas.map((f) => f.nome)).size).toBe(MAXIMO_FICHAS);
  });

  it("renomear guarda o texto como foi digitado", () => {
    const e = renomearFicha(criarEstado(), 0, "  Peito e tríceps ");
    expect(e.fichas[0].nome).toBe("  Peito e tríceps ");
  });

  it("remove uma ficha, mas nunca a última", () => {
    let e = adicionarFicha(criarEstado());
    e = removerFicha(e, 0);
    expect(e.fichas.map((f) => f.nome)).toEqual(["FICHA B"]);
    expect(removerFicha(e, 0)).toBe(e);
  });

  it("índice de ficha que não existe não faz nada", () => {
    const e = criarEstado();
    expect(renomearFicha(e, 5, "X")).toBe(e);
    expect(removerFicha(e, 5)).toBe(e);
    expect(adicionarItem(e, 5, ex(1))).toBe(e);
  });
});

// ---------------------------------------------------------------- imutabilidade

describe("imutabilidade", () => {
  it("as operações devolvem um estado novo e deixam o antigo como estava", () => {
    const original = comItens(3);
    const foto = JSON.stringify(original);

    adicionarFicha(original);
    renomearFicha(original, 0, "OUTRO");
    adicionarItem(original, 0, ex(9));
    atualizarItem(original, 0, 1, "series", "4");
    removerItem(original, 0, 1);
    moverUnidade(original, 0, 0, 1);
    unirEmBloco(original, 0, [1, 2]);

    expect(JSON.stringify(original)).toBe(foto);
  });
});

// ---------------------------------------------------------------- exercícios

describe("exercícios na ficha", () => {
  it("adiciona com campos vazios e uids crescentes", () => {
    const e = comItens(2);
    expect(e.fichas[0].itens[0]).toEqual({
      uid: 1,
      exercicioId: 1,
      nome: "EXERCICIO 1",
      series: "",
      repeticoes: "",
      carga: "",
      pausaMin: "",
      pausaSeg: "",
      observacao: "",
      bloco: null,
    });
    expect(uids(e)).toEqual([1, 2]);
  });

  it("o intervalo só aceita números, com no máximo 2 dígitos", () => {
    let e = comItens(1);
    e = atualizarItem(e, 0, 1, "pausaMin", "1a");
    expect(e.fichas[0].itens[0].pausaMin).toBe("1");
    e = atualizarItem(e, 0, 1, "pausaSeg", "123");
    expect(e.fichas[0].itens[0].pausaSeg).toBe("12");
    e = atualizarItem(e, 0, 1, "pausaSeg", "<b>");
    expect(e.fichas[0].itens[0].pausaSeg).toBe("");
  });

  it("a observação guarda o texto como foi digitado (a limpeza é no envio)", () => {
    const e = atualizarItem(comItens(1), 0, 1, "observacao", "  até  a falha ");
    expect(e.fichas[0].itens[0].observacao).toBe("  até  a falha ");
  });

  it("pausaEmSegundos converte minutos e segundos", () => {
    expect(pausaEmSegundos({ pausaMin: "1", pausaSeg: "30" })).toBe(90);
    expect(pausaEmSegundos({ pausaMin: "", pausaSeg: "45" })).toBe(45);
    expect(pausaEmSegundos({ pausaMin: "2", pausaSeg: "" })).toBe(120);
    expect(pausaEmSegundos({ pausaMin: "0", pausaSeg: "0" })).toBeNull();
    expect(pausaEmSegundos({ pausaMin: "", pausaSeg: "" })).toBeNull();
  });

  it("aceita o mesmo exercício duas vezes, com uids diferentes", () => {
    let e = adicionarItem(criarEstado(), 0, ex(7));
    e = adicionarItem(e, 0, ex(7));
    expect(uids(e)).toEqual([1, 2]);
    expect(e.fichas[0].itens.map((i) => i.exercicioId)).toEqual([7, 7]);
  });

  it("uid nunca é reaproveitado depois de remover", () => {
    let e = comItens(2);
    e = removerItem(e, 0, 2);
    e = adicionarItem(e, 0, ex(3));
    expect(uids(e)).toEqual([1, 3]);
  });

  it("para no limite de itens por ficha", () => {
    const e = comItens(MAXIMO_ITENS_POR_FICHA);
    expect(adicionarItem(e, 0, ex(999))).toBe(e);
  });

  it("atualiza séries, repetições e carga", () => {
    let e = comItens(1);
    e = atualizarItem(e, 0, 1, "series", "4");
    e = atualizarItem(e, 0, 1, "repeticoes", "10-12");
    e = atualizarItem(e, 0, 1, "carga", "30 kg");
    expect(e.fichas[0].itens[0]).toMatchObject({ series: "4", repeticoes: "10-12", carga: "30 kg" });
  });

  it("só deixa editar os três campos de prescrição", () => {
    const e = comItens(2);
    for (const campo of ["bloco", "uid", "nome", "exercicioId", "__proto__"]) {
      expect(atualizarItem(e, 0, 1, campo, "x")).toBe(e);
    }
  });

  it("uid inexistente não faz nada", () => {
    const e = comItens(1);
    expect(atualizarItem(e, 0, 99, "series", "4")).toBe(e);
    expect(removerItem(e, 0, 99)).toBe(e);
  });

  it("remove um exercício", () => {
    const e = removerItem(comItens(3), 0, 2);
    expect(uids(e)).toEqual([1, 3]);
  });
});

// ---------------------------------------------------------------- mover

describe("mover", () => {
  it("troca um exercício sozinho com o vizinho", () => {
    const e = moverUnidade(comItens(3), 0, 0, 1);
    expect(uids(e)).toEqual([2, 1, 3]);
    expect(uids(moverUnidade(e, 0, 2, -1))).toEqual([2, 3, 1]);
  });

  it("não sai da lista: subir o primeiro e descer o último não fazem nada", () => {
    const e = comItens(3);
    expect(moverUnidade(e, 0, 0, -1)).toBe(e);
    expect(moverUnidade(e, 0, 2, 1)).toBe(e);
    expect(moverUnidade(e, 0, 9, 1)).toBe(e);
  });

  it("um bi-set se move inteiro, sem ser separado", () => {
    let e = comItens(4);
    e = unirEmBloco(e, 0, [1, 2]).estado; // [bi(1,2), 3, 4]
    e = moverUnidade(e, 0, 0, 1); // desce o bi-set para depois do 3
    expect(uids(e)).toEqual([3, 1, 2, 4]);
    expect(blocos(e)).toEqual([null, 1, 1, null]);
  });

  it("um exercício sozinho passa por cima de um bi-set inteiro", () => {
    let e = comItens(3);
    e = unirEmBloco(e, 0, [2, 3]).estado; // [1, bi(2,3)]
    e = moverUnidade(e, 0, 0, 1); // desce o 1
    expect(uids(e)).toEqual([2, 3, 1]);
  });
});

// ---------------------------------------------------------------- bi-set e tri-set

describe("bi-set e tri-set", () => {
  it("junta 2 exercícios vizinhos em bi-set", () => {
    const r = unirEmBloco(comItens(3), 0, [1, 2]);
    expect(r.ok).toBe(true);
    expect(blocos(r.estado)).toEqual([1, 1, null]);
  });

  it("junta 3 em tri-set, na ordem que estão na ficha (não na ordem do clique)", () => {
    const r = unirEmBloco(comItens(3), 0, [3, 1, 2]);
    expect(r.ok).toBe(true);
    expect(blocos(r.estado)).toEqual([1, 1, 1]);
    expect(uids(r.estado)).toEqual([1, 2, 3]);
  });

  it("cada bloco novo recebe um número novo", () => {
    let e = comItens(4);
    e = unirEmBloco(e, 0, [1, 2]).estado;
    e = unirEmBloco(e, 0, [3, 4]).estado;
    expect(blocos(e)).toEqual([1, 1, 2, 2]);
  });

  it.each([
    ["nenhum", []],
    ["só 1", [1]],
    ["4 exercícios", [1, 2, 3, 4]],
    ["o mesmo exercício repetido", [1, 1]],
  ])("recusa quantidade errada: %s", (_nome, selecionados) => {
    const r = unirEmBloco(comItens(4), 0, selecionados);
    expect(r.ok).toBe(false);
    expect(r.erro).toMatch(/2 exercícios.*3/);
  });

  it("recusa exercícios que não estão um embaixo do outro", () => {
    const r = unirEmBloco(comItens(3), 0, [1, 3]);
    expect(r.ok).toBe(false);
    expect(r.erro).toMatch(/um embaixo do outro/);
  });

  it("depois de aproximar com as setas, aceita", () => {
    let e = moverUnidade(comItens(3), 0, 1, 1); // [1, 3, 2]
    expect(unirEmBloco(e, 0, [1, 2]).ok).toBe(false); // 1 e 2 ficaram separados
    e = moverUnidade(e, 0, 1, 1); // volta [1, 2, 3]
    expect(unirEmBloco(e, 0, [1, 2]).ok).toBe(true);
  });

  it("recusa quem já está em um bi-set", () => {
    const e = unirEmBloco(comItens(3), 0, [1, 2]).estado;
    const r = unirEmBloco(e, 0, [2, 3]);
    expect(r.ok).toBe(false);
    expect(r.erro).toMatch(/ainda não estão em um bi-set/);
  });

  it("recusa uid que não existe", () => {
    expect(unirEmBloco(comItens(2), 0, [1, 99]).ok).toBe(false);
  });

  it("desfazer devolve os exercícios a sozinhos", () => {
    const e = unirEmBloco(comItens(3), 0, [1, 2]).estado;
    expect(blocos(desfazerBloco(e, 0, 1))).toEqual([null, null, null]);
  });

  it("desfazer um bloco que não existe não faz nada", () => {
    const e = comItens(2);
    expect(desfazerBloco(e, 0, 5)).toBe(e);
  });

  it("remover um exercício de um bi-set desfaz o bi-set", () => {
    let e = unirEmBloco(comItens(3), 0, [1, 2]).estado;
    e = removerItem(e, 0, 1);
    expect(blocos(e)).toEqual([null, null]);
  });

  it("remover um exercício de um tri-set deixa um bi-set", () => {
    let e = unirEmBloco(comItens(3), 0, [1, 2, 3]).estado;
    e = removerItem(e, 0, 2);
    expect(blocos(e)).toEqual([1, 1]);
  });

  it("unidades agrupa os blocos e separa blocos vizinhos", () => {
    let e = comItens(5);
    e = unirEmBloco(e, 0, [2, 3]).estado;
    e = unirEmBloco(e, 0, [4, 5]).estado;
    const tipos = unidades(e.fichas[0]).map((u) => u.tipo);
    expect(tipos).toEqual(["item", "bloco", "bloco"]);
  });
});

// ---------------------------------------------------------------- etiquetas e resumo

describe("etiquetas e resumo", () => {
  const etiquetasEmLista = (e) => {
    const mapa = etiquetas(e.fichas[0]);
    return e.fichas[0].itens.map((i) => mapa.get(i.uid));
  };

  it("sem blocos: numera 1, 2, 3...", () => {
    expect(etiquetasEmLista(comItens(3))).toEqual(["1", "2", "3"]);
  });

  it("como no desenho: bi-set A1, A2 e depois 3, 4, 5", () => {
    const e = unirEmBloco(comItens(5), 0, [1, 2]).estado;
    expect(etiquetasEmLista(e)).toEqual(["A1", "A2", "3", "4", "5"]);
  });

  it("dois blocos levam letras diferentes", () => {
    let e = comItens(5);
    e = unirEmBloco(e, 0, [1, 2]).estado;
    e = unirEmBloco(e, 0, [3, 4, 5]).estado;
    expect(etiquetasEmLista(e)).toEqual(["A1", "A2", "B1", "B2", "B3"]);
  });

  it("bloco no meio: os sozinhos seguem a posição na ficha", () => {
    const e = unirEmBloco(comItens(5), 0, [3, 4]).estado;
    expect(etiquetasEmLista(e)).toEqual(["1", "2", "A1", "A2", "5"]);
  });

  it("a letra segue a ordem na tela, não o número interno do bloco", () => {
    let e = comItens(4);
    e = unirEmBloco(e, 0, [3, 4]).estado; // bloco 1
    e = unirEmBloco(e, 0, [1, 2]).estado; // bloco 2, mas aparece primeiro
    expect(etiquetasEmLista(e)).toEqual(["A1", "A2", "B1", "B2"]);
  });

  it("descreve a ficha como no desenho", () => {
    expect(descreverFicha(comItens(0).fichas[0])).toBe("0 exercícios");
    expect(descreverFicha(comItens(1).fichas[0])).toBe("1 exercício");
    const e = unirEmBloco(comItens(5), 0, [1, 2]).estado;
    expect(descreverFicha(e.fichas[0])).toBe("5 exercícios, 1 bi-set");
  });

  it("descreve vários bi-sets e tri-sets", () => {
    let e = comItens(7);
    e = unirEmBloco(e, 0, [1, 2]).estado;
    e = unirEmBloco(e, 0, [3, 4]).estado;
    e = unirEmBloco(e, 0, [5, 6, 7]).estado;
    expect(descreverFicha(e.fichas[0])).toBe("7 exercícios, 2 bi-sets, 1 tri-set");
  });
});

// ---------------------------------------------------------------- validação

describe("validar", () => {
  it("os limites são os do Data4U: nome da ficha 15, séries/repetições/carga 11", () => {
    // Valores fixos de propósito: vêm das colunas NM_TREINO_FICHA e NR_SERIE /
    // DS_REPETICAO / DS_PESO. Se alguém mudar a constante, este teste avisa.
    expect(LIMITE_NOME_FICHA).toBe(15);
    expect(LIMITE_CAMPO).toBe(11);
  });

  it("treino completo não tem problemas (carga é opcional)", () => {
    expect(validar(preencher(comItens(2)))).toEqual([]);
  });

  it("pede nome da ficha", () => {
    const e = renomearFicha(preencher(comItens(1)), 0, "   ");
    const p = validar(e);
    expect(p).toHaveLength(1);
    expect(p[0]).toMatchObject({ ficha: 0, uid: null, campo: "nome" });
  });

  it("aceita nome com exatamente 15 letras e recusa 16", () => {
    const base = preencher(comItens(1));
    expect(validar(renomearFicha(base, 0, "A".repeat(LIMITE_NOME_FICHA)))).toEqual([]);
    const p = validar(renomearFicha(base, 0, "A".repeat(LIMITE_NOME_FICHA + 1)));
    expect(p).toHaveLength(1);
    expect(p[0].mensagem).toMatch(/16 letras.*máximo 15/);
  });

  it("o tamanho do nome conta depois de tirar os espaços das pontas", () => {
    const base = preencher(comItens(1));
    expect(validar(renomearFicha(base, 0, " " + "A".repeat(15) + " "))).toEqual([]);
  });

  it("ficha sem exercício é problema", () => {
    const p = validar(criarEstado());
    expect(p).toHaveLength(1);
    expect(p[0]).toMatchObject({ campo: "itens", uid: null });
  });

  it("séries e repetições podem ficar em branco (cardio: o professor escreve o tempo, ou nada)", () => {
    let e = comItens(1);
    e = atualizarItem(e, 0, 1, "series", "   ");
    expect(validar(e)).toEqual([]);
  });

  it("a mensagem diz qual exercício tem o problema", () => {
    const e = atualizarItem(comItens(1), 0, 1, "repeticoes", "x".repeat(LIMITE_CAMPO + 1));
    const p = validar(e);
    expect(p).toHaveLength(1);
    expect(p[0].mensagem).toContain("EXERCICIO 1");
    expect(p[0].uid).toBe(1);
  });

  it("aceita 11 caracteres e recusa 12 em cada campo", () => {
    for (const campo of ["series", "repeticoes", "carga"]) {
      const base = preencher(comItens(1));
      const ok = atualizarItem(base, 0, 1, campo, "x".repeat(LIMITE_CAMPO));
      const longo = atualizarItem(base, 0, 1, campo, "x".repeat(LIMITE_CAMPO + 1));
      expect(validar(ok)).toEqual([]);
      const p = validar(longo);
      expect(p).toHaveLength(1);
      expect(p[0]).toMatchObject({ campo, uid: 1 });
    }
  });

  it("fala de 'ficha' e de 'peso' (as palavras do Data4U)", () => {
    let e = renomearFicha(comItens(1), 0, "  ");
    expect(validar(e).map((p) => p.mensagem)).toContain("Dê um nome à ficha 1.");
    e = renomearFicha(e, 0, "A");
    e = atualizarItem(e, 0, 1, "series", "3");
    e = atualizarItem(e, 0, 1, "repeticoes", "10");
    e = atualizarItem(e, 0, 1, "carga", "x".repeat(LIMITE_CAMPO + 1));
    const [problema] = validar(e);
    expect(problema.mensagem).toContain("peso de EXERCICIO 1");
    expect(problema.mensagem).not.toContain("carga");
  });

  it("intervalo e observação são opcionais", () => {
    let e = preencher(comItens(1));
    expect(validar(e)).toEqual([]);
    e = atualizarItem(e, 0, 1, "pausaMin", "1");
    e = atualizarItem(e, 0, 1, "observacao", "  ");
    expect(validar(e)).toEqual([]);
  });

  it("o intervalo vai de 0 a 59 minutos e de 0 a 59 segundos", () => {
    expect(LIMITE_OBSERVACAO).toBe(200);
    const base = preencher(comItens(1));
    for (const [min, seg] of [["0", "0"], ["59", "59"], ["", "30"], ["2", ""]]) {
      const ok = atualizarItem(atualizarItem(base, 0, 1, "pausaMin", min), 0, 1, "pausaSeg", seg);
      expect(validar(ok)).toEqual([]);
    }
    const seg60 = validar(atualizarItem(base, 0, 1, "pausaSeg", "60"));
    expect(seg60).toHaveLength(1);
    expect(seg60[0]).toMatchObject({ campo: "pausaSeg", uid: 1 });
    expect(seg60[0].mensagem).toMatch(/segundos vão de 0 a 59/);
    const min60 = validar(atualizarItem(base, 0, 1, "pausaMin", "60"));
    expect(min60).toHaveLength(1);
    expect(min60[0]).toMatchObject({ campo: "pausaMin", uid: 1 });
  });

  it("intervalo que veio estragado de um rascunho é apontado (só números)", () => {
    const e = preencher(comItens(1));
    e.fichas[0].itens[0].pausaSeg = "1a";
    expect(validar(e).map((p) => p.campo)).toEqual(["pausaSeg"]);
  });

  it("a observação aceita 200 letras e recusa 201", () => {
    const base = preencher(comItens(1));
    expect(validar(atualizarItem(base, 0, 1, "observacao", "x".repeat(LIMITE_OBSERVACAO)))).toEqual([]);
    const p = validar(atualizarItem(base, 0, 1, "observacao", "x".repeat(LIMITE_OBSERVACAO + 1)));
    expect(p).toHaveLength(1);
    expect(p[0]).toMatchObject({ campo: "observacao", uid: 1 });
    expect(p[0].mensagem).toMatch(/201 letras; o máximo é 200/);
  });

  it("a observação não pode ter caractere invisível ou de controle", () => {
    const base = preencher(comItens(1));
    const p = validar(atualizarItem(base, 0, 1, "observacao", "a\u202eb"));
    expect(p).toHaveLength(1);
    expect(p[0].campo).toBe("observacao");
  });

  it("aponta o problema na ficha certa", () => {
    let e = preencher(comItens(1));
    e = adicionarFicha(e); // ficha B vazia
    const p = validar(e);
    expect(p).toHaveLength(1);
    expect(p[0].ficha).toBe(1);
    expect(p[0].mensagem).toContain("FICHA B");
  });
});

// ---------------------------------------------------------------- envio

describe("paraEnvio", () => {
  it("apara os textos e numera as fichas e os exercícios de 1 a n", () => {
    let e = preencher(comItens(2));
    e = renomearFicha(e, 0, "  TREINO A  ");
    e = atualizarItem(e, 0, 1, "carga", " 30 kg ");
    const envio = paraEnvio(e);
    expect(envio.fichas[0]).toMatchObject({ nome: "TREINO A", ordem: 1 });
    expect(envio.fichas[0].itens).toEqual([
      { exercicio_id: 1, ordem: 1, bloco: null, series: "3", repeticoes: "12", carga: "30 kg", pausa: null, observacao: "" },
      { exercicio_id: 2, ordem: 2, bloco: null, series: "3", repeticoes: "12", carga: "", pausa: null, observacao: "" },
    ]);
  });

  it("manda o intervalo em segundos e a observação sem espaços sobrando", () => {
    let e = preencher(comItens(3));
    e = atualizarItem(e, 0, 1, "pausaMin", "1");
    e = atualizarItem(e, 0, 1, "pausaSeg", "30");
    e = atualizarItem(e, 0, 1, "observacao", "  descer   devagar ");
    e = atualizarItem(e, 0, 2, "pausaSeg", "45"); // só segundos
    e = atualizarItem(e, 0, 3, "pausaMin", "2"); // só minutos
    const itens = paraEnvio(e).fichas[0].itens;
    expect(itens.map((i) => i.pausa)).toEqual([90, 45, 120]);
    expect(itens[0].observacao).toBe("descer devagar");
  });

  it("intervalo vazio ou 0:00 vira null (sem intervalo)", () => {
    let e = preencher(comItens(2));
    e = atualizarItem(e, 0, 2, "pausaMin", "0");
    e = atualizarItem(e, 0, 2, "pausaSeg", "00");
    expect(paraEnvio(e).fichas[0].itens.map((i) => i.pausa)).toEqual([null, null]);
  });

  it("renumera os blocos 1, 2, 3... na ordem em que aparecem em cada ficha", () => {
    let e = comItens(4);
    e = unirEmBloco(e, 0, [3, 4]).estado; // bloco interno 1
    e = unirEmBloco(e, 0, [1, 2]).estado; // bloco interno 2, aparece primeiro
    e = adicionarFicha(e);
    e = adicionarItem(e, 1, ex(8));
    e = adicionarItem(e, 1, ex(9));
    e = unirEmBloco(e, 1, [5, 6]).estado; // bloco interno 3
    const envio = paraEnvio(e);
    expect(envio.fichas[0].itens.map((i) => i.bloco)).toEqual([1, 1, 2, 2]);
    expect(envio.fichas[1].itens.map((i) => i.bloco)).toEqual([1, 1]);
  });

  it("guarda o id do exercício, não o uid interno", () => {
    let e = adicionarItem(criarEstado(), 0, { id: 1234, nome: "X" });
    expect(paraEnvio(e).fichas[0].itens[0].exercicio_id).toBe(1234);
  });
});

// ---------------------------------------------------------------- rascunho

describe("rascunho", () => {
  it("guarda e lê de volta o mesmo treino", () => {
    let e = preencher(comItens(4));
    e = unirEmBloco(e, 0, [1, 2]).estado;
    e = adicionarFicha(e);
    const lido = lerRascunho(serializar(e));
    expect(lido).toEqual(e);
  });

  it("depois de ler, os próximos uids e blocos não repetem os antigos", () => {
    let e = unirEmBloco(comItens(3), 0, [1, 2]).estado;
    const lido = lerRascunho(serializar({ ...e, proximoUid: 1, proximoBloco: 1 }));
    expect(lido.proximoUid).toBe(4);
    expect(lido.proximoBloco).toBe(2);
    const depois = adicionarItem(lido, 0, ex(50));
    expect(uids(depois)).toEqual([1, 2, 3, 4]);
  });

  it("guarda e devolve o intervalo e a observação", () => {
    let e = comItens(1);
    e = atualizarItem(e, 0, 1, "pausaMin", "1");
    e = atualizarItem(e, 0, 1, "pausaSeg", "30");
    e = atualizarItem(e, 0, 1, "observacao", "descer devagar");
    const item = lerRascunho(serializar(e)).fichas[0].itens[0];
    expect([item.pausaMin, item.pausaSeg, item.observacao]).toEqual(["1", "30", "descer devagar"]);
  });

  it("rascunho de antes do intervalo e da observação ainda abre (os campos entram vazios)", () => {
    const antigo = JSON.stringify({
      fichas: [{ nome: "A", itens: [{ uid: 1, exercicioId: 1, nome: "X", series: "3", repeticoes: "10", carga: "", bloco: null }] }],
    });
    const item = lerRascunho(antigo).fichas[0].itens[0];
    expect([item.series, item.pausaMin, item.pausaSeg, item.observacao]).toEqual(["3", "", "", ""]);
  });

  it("desfaz bloco que veio com 1 exercício só", () => {
    const e = comItens(2);
    e.fichas[0].itens[0].bloco = 7;
    expect(lerRascunho(serializar(e)).fichas[0].itens[0].bloco).toBeNull();
  });

  const itemBom = { uid: 1, exercicioId: 1, nome: "X", series: "", repeticoes: "", carga: "", bloco: null };
  const comItem = (mudanca) => JSON.stringify({ fichas: [{ nome: "A", itens: [{ ...itemBom, ...mudanca }] }] });

  it.each([
    ["texto que não é JSON", "isto não é json"],
    ["null", "null"],
    ["número", "42"],
    ["objeto sem fichas", "{}"],
    ["fichas não é lista", '{"fichas": "x"}'],
    ["lista de fichas vazia", '{"fichas": []}'],
    ["ficha sem nome", '{"fichas": [{"itens": []}]}'],
    ["itens não é lista", '{"fichas": [{"nome": "A", "itens": 3}]}'],
    ["série como número", comItem({ series: 3 })],
    ["uid zero", comItem({ uid: 0 })],
    ["uid decimal", comItem({ uid: 1.5 })],
    ["exercicioId texto", comItem({ exercicioId: "1" })],
    ["bloco zero", comItem({ bloco: 0 })],
    ["bloco texto", comItem({ bloco: "1" })],
    ["nome do exercício ausente", comItem({ nome: undefined })],
    ["intervalo como número", comItem({ pausaSeg: 30 })],
    ["observação como lista", comItem({ observacao: ["x"] })],
  ])("rejeita rascunho inválido: %s", (_descricao, texto) => {
    expect(lerRascunho(texto)).toBeNull();
  });

  it("rejeita uid repetido", () => {
    const e = comItens(2);
    e.fichas[0].itens[1].uid = 1;
    expect(lerRascunho(serializar(e))).toBeNull();
  });

  it("rejeita fichas demais e itens demais", () => {
    const fichas = Array.from({ length: MAXIMO_FICHAS + 1 }, () => ({ nome: "A", itens: [] }));
    expect(lerRascunho(JSON.stringify({ fichas }))).toBeNull();

    const itens = Array.from({ length: MAXIMO_ITENS_POR_FICHA + 1 }, (_, i) => ({ ...itemBom, uid: i + 1 }));
    expect(lerRascunho(JSON.stringify({ fichas: [{ nome: "A", itens }] }))).toBeNull();
  });

  it("ignora campos extras que não fazem parte do treino", () => {
    const texto = JSON.stringify({
      fichas: [{ nome: "A", itens: [{ ...itemBom, perigo: "<script>" }], extra: 1 }],
      outro: true,
    });
    const lido = lerRascunho(texto);
    expect(lido.fichas[0].itens[0]).not.toHaveProperty("perigo");
    expect(lido.fichas[0]).not.toHaveProperty("extra");
    expect(lido).not.toHaveProperty("outro");
  });
});


describe("enderecoDeImpressao", () => {
  it("devolve a tela de impressão do treino salvo", () => {
    expect(enderecoDeImpressao({ id: 17 })).toBe("/treinos/17/imprimir");
  });

  it.each([
    ["sem corpo", null],
    ["corpo vazio", {}],
    ["id em texto (nunca vira parte de um endereço)", { id: "17" }],
    ["id com caminho", { id: "../x" }],
    ["id zero", { id: 0 }],
    ["id negativo", { id: -1 }],
    ["id decimal", { id: 1.5 }],
  ])("%s: devolve null e o botão não aparece", (_nome, corpo) => {
    expect(enderecoDeImpressao(corpo)).toBeNull();
  });
});

// ---------------------------------------------------------------- importar treino e treino padrão

// O que o servidor devolve em /api/modelos/<id> e /api/treinos/<id>/para-montar (app/modelos.py, `para_montar`).
function treinoDoServidor(mudancas = {}) {
  return {
    nome: "TREINO ABC",
    sessoes_por_ficha: 15,
    indisponiveis: 0,
    fichas: [
      {
        nome: "FICHA A",
        itens: [
          { exercicio_id: 10, nome: "SUPINO RETO", series: "4", repeticoes: "10", carga: "30", pausa: 90, observacao: "devagar", bloco: 1, indisponivel: false },
          { exercicio_id: 11, nome: "CRUCIFIXO", series: "4", repeticoes: "10", carga: "", pausa: null, observacao: "", bloco: 1, indisponivel: false },
          { exercicio_id: 12, nome: "ELÍPTICO", series: "", repeticoes: "", carga: "", pausa: null, observacao: "", bloco: null, indisponivel: false },
        ],
      },
      { nome: "FICHA B", itens: [{ exercicio_id: 13, nome: "AGACHAMENTO", series: "3", repeticoes: "12", carga: "", pausa: 60, observacao: "", bloco: null, indisponivel: false }] },
    ],
    ...mudancas,
  };
}

describe("estadoDeImportacao", () => {
  it("monta o estado da tela com o intervalo em minutos e segundos", () => {
    const e = estadoDeImportacao(treinoDoServidor());

    expect(e.fichas.map((f) => f.nome)).toEqual(["FICHA A", "FICHA B"]);
    const [supino, crucifixo, eliptico] = e.fichas[0].itens;
    expect([supino.exercicioId, supino.nome, supino.series, supino.repeticoes, supino.carga]).toEqual([10, "SUPINO RETO", "4", "10", "30"]);
    expect([supino.pausaMin, supino.pausaSeg, supino.observacao]).toEqual(["1", "30", "devagar"]);
    expect([crucifixo.pausaMin, crucifixo.pausaSeg]).toEqual(["", ""]);
    expect([eliptico.series, eliptico.repeticoes]).toEqual(["", ""]); // cardio: em branco
    expect(e.fichas[1].itens[0].pausaSeg).toBe("00"); // 60 s = 1 : 00
  });

  it("dá um uid diferente para cada exercício e conta os próximos uids e blocos", () => {
    const e = estadoDeImportacao(treinoDoServidor());

    const uids = e.fichas.flatMap((f) => f.itens.map((i) => i.uid));
    expect(uids).toEqual([1, 2, 3, 4]);
    expect(e.proximoUid).toBe(5);
    expect(e.proximoBloco).toBe(2);
  });

  it("mantém os bi-sets", () => {
    const e = estadoDeImportacao(treinoDoServidor());

    expect(e.fichas[0].itens.map((i) => i.bloco)).toEqual([1, 1, null]);
    expect(descreverFicha(e.fichas[0])).toBe("3 exercícios, 1 bi-set");
  });

  it("um treino sem problema passa na conferência da tela e vai ao servidor no formato certo", () => {
    const e = estadoDeImportacao(treinoDoServidor());

    expect(validar(e)).toEqual([]);
    const envio = paraEnvio(e).fichas[0].itens;
    expect(envio[0]).toMatchObject({ exercicio_id: 10, series: "4", repeticoes: "10", carga: "30", pausa: 90, observacao: "devagar", bloco: 1 });
    expect(envio[2]).toMatchObject({ series: "", repeticoes: "", pausa: null, bloco: null });
    expect(envio[0]).not.toHaveProperty("indisponivel");
  });

  it("exercício indisponível entra marcado e impede de salvar até ser removido", () => {
    const treino = treinoDoServidor();
    treino.fichas[0].itens[1].indisponivel = true;
    const e = estadoDeImportacao(treino);

    expect(contarIndisponiveis(e)).toBe(1);
    const problemas = validar(e);
    expect(problemas).toHaveLength(1);
    expect(problemas[0]).toMatchObject({ ficha: 0, uid: 2, campo: "exercicio" });
    expect(problemas[0].mensagem).toContain("CRUCIFIXO");
    expect(problemas[0].mensagem).toContain("FICHA A");

    const sem = removerItem(e, 0, 2); // o bi-set fica com 1 só e desfaz
    expect(validar(sem)).toEqual([]);
    expect(contarIndisponiveis(sem)).toBe(0);
    expect(sem.fichas[0].itens.map((i) => i.bloco)).toEqual([null, null]);
  });

  it("o aviso de indisponível sobrevive ao rascunho (recarregar a página)", () => {
    const treino = treinoDoServidor();
    treino.fichas[1].itens[0].indisponivel = true;
    const e = estadoDeImportacao(treino);

    const lido = lerRascunho(serializar(e));

    expect(contarIndisponiveis(lido)).toBe(1);
    expect(lido.fichas[1].itens[0].indisponivel).toBe(true);
    expect(lido.fichas[0].itens[0]).not.toHaveProperty("indisponivel");
  });

  it("exercício adicionado depois pela lista nunca vem marcado", () => {
    const e = adicionarItem(estadoDeImportacao(treinoDoServidor()), 0, ex(99));

    expect(e.fichas[0].itens.at(-1)).not.toHaveProperty("indisponivel");
  });

  it("textos que faltam entram vazios e intervalo estranho é ignorado", () => {
    const treino = treinoDoServidor();
    treino.fichas[0].itens[0] = { exercicio_id: 10, nome: "SUPINO RETO", series: null, pausa: 99999, bloco: 0 };
    treino.fichas[0].itens[1].pausa = -5;

    const e = estadoDeImportacao(treino);

    const [a, b] = e.fichas[0].itens;
    expect([a.series, a.repeticoes, a.carga, a.observacao, a.pausaMin, a.pausaSeg, a.bloco]).toEqual(["", "", "", "", "", "", null]);
    expect([b.pausaMin, b.pausaSeg]).toEqual(["", ""]);
  });

  it("aceita o intervalo máximo de 59 min 59 s", () => {
    const treino = treinoDoServidor();
    treino.fichas[1].itens[0].pausa = 3599;

    const item = estadoDeImportacao(treino).fichas[1].itens[0];

    expect([item.pausaMin, item.pausaSeg]).toEqual(["59", "59"]);
  });

  it.each([
    ["nada", null],
    ["texto", "treino"],
    ["sem fichas", { fichas: "A" }],
    ["lista de fichas vazia", { fichas: [] }],
    ["ficha sem nome", { fichas: [{ itens: [] }] }],
    ["ficha sem lista de exercícios", { fichas: [{ nome: "A" }] }],
    ["exercício sem id", { fichas: [{ nome: "A", itens: [{ nome: "X" }] }] }],
    ["exercício com id de texto", { fichas: [{ nome: "A", itens: [{ exercicio_id: "7", nome: "X" }] }] }],
    ["exercício sem nome", { fichas: [{ nome: "A", itens: [{ exercicio_id: 7 }] }] }],
  ])("formato que não serve (%s) não carrega nada", (_descricao, treino) => {
    expect(estadoDeImportacao(treino)).toBeNull();
  });

  it("recusa treino com fichas demais ou exercícios demais", () => {
    const muitasFichas = { fichas: Array.from({ length: MAXIMO_FICHAS + 1 }, (_, i) => ({ nome: "F" + i, itens: [] })) };
    const muitosItens = {
      fichas: [{ nome: "A", itens: Array.from({ length: MAXIMO_ITENS_POR_FICHA + 1 }, (_, i) => ({ exercicio_id: i + 1, nome: "X" })) }],
    };

    expect(estadoDeImportacao(muitasFichas)).toBeNull();
    expect(estadoDeImportacao(muitosItens)).toBeNull();
  });
});

describe("metaDaImportacao, contarIndisponiveis e contarExercicios", () => {
  it("a meta vira o texto do campo; sem meta (ou fora de 1 a 999), vazio", () => {
    expect(metaDaImportacao({ sessoes_por_ficha: 15 })).toBe("15");
    expect(metaDaImportacao({ sessoes_por_ficha: 999 })).toBe("999");
    for (const ruim of [null, 0, 1000, "15", 1.5, undefined]) expect(metaDaImportacao({ sessoes_por_ficha: ruim })).toBe("");
    expect(metaDaImportacao(null)).toBe("");
  });

  it("conta os exercícios do treino todo", () => {
    expect(contarExercicios(estadoDeImportacao(treinoDoServidor()))).toBe(4);
    expect(contarExercicios(criarEstado())).toBe(0);
  });
});

describe("treino padrão a partir da tela", () => {
  const dados = { nomePadrao: "Básico 1", montadoPor: "Ana Paula" };

  it("monta o pedido com as fichas e a meta, sem datas", () => {
    const e = preencher(comItens(2));

    const pedido = montarPedidoDePadrao(e, { ...dados, sessoesPorFicha: " 15 " });

    expect(pedido.nome).toBe("Básico 1");
    expect(pedido.montado_por).toBe("Ana Paula");
    expect(pedido.sessoes_por_ficha).toBe(15);
    expect(pedido.fichas).toEqual(paraEnvio(e).fichas);
    expect(pedido).not.toHaveProperty("inicio");
    expect(pedido).not.toHaveProperty("nome_treino");
  });

  it("sem meta vai null; nome e professor perdem os espaços sobrando", () => {
    const pedido = montarPedidoDePadrao(comItens(1), { nomePadrao: "  Básico   1 ", montadoPor: " Ana  Paula ", sessoesPorFicha: "" });

    expect(pedido.sessoes_por_ficha).toBeNull();
    expect(pedido.nome).toBe("Básico 1");
    expect(pedido.montado_por).toBe("Ana Paula");
  });

  it("confere nome e professor", () => {
    expect(validarDadosDoPadrao(dados)).toEqual([]);
    expect(validarDadosDoPadrao({ nomePadrao: "  ", montadoPor: "" }).map((p) => p.campo)).toEqual(["nome-padrao", "quem-montou"]);
    const longo = validarDadosDoPadrao({ nomePadrao: "X".repeat(41), montadoPor: "Y".repeat(61) });
    expect(longo.map((p) => p.campo)).toEqual(["nome-padrao", "quem-montou"]);
    expect(longo[0].mensagem).toContain("máximo é 40");
    expect(validarDadosDoPadrao({ nomePadrao: "X".repeat(40), montadoPor: "Y".repeat(60) })).toEqual([]);
  });

  it("recusa caractere invisível", () => {
    const [problema] = validarDadosDoPadrao({ nomePadrao: "Bom\u0000dia", montadoPor: "Ana" });

    expect(problema.campo).toBe("nome-padrao");
    expect(problema.mensagem).toContain("caracteres inválidos");
  });
});
