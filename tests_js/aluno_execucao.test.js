import { textoDaSemana } from "../app/static/aluno_modelo.js";
import { describe, expect, it } from "vitest";
import {
  ESFORCOS,
  MENSAGEM_CARGA_NAO_E_NUMERO,
  MENSAGEM_CARGA_ZERO,
  TEXTO_FEITO,
  TEXTO_MARCAR_FEITO,
  MAXIMO_DO_DESCANSO,
  MENSAGEM_DESCANSO_INVALIDO,
  MENSAGEM_DESCANSO_VAZIO,
  conferirCarga,
  conferirDescanso,
  decidirAtualizacaoDoTreino,
  descansoSugerido,
  descreverEsforco,
  descreverExercicio,
  exerciciosDaFicha,
  grupoDoExercicio,
  pedidoDoEsforco,
  pedidoDoExercicio,
  posicaoSeContinuaIgual,
  proximoDaLista,
  proximoEsforco,
  proximoSemFazer,
  segundosRestantes,
  temDescanso,
  textoDaPosicao,
  textoDaUltimaCarga,
  textoDeTodosFeitos,
  textoDoExercicioFeito,
  textoDoFeito,
  textoDoProgresso,
  textoDoTempo,
} from "../app/static/aluno_modelo.js";

const exercicio = (extras = {}) => ({
  ordem: 1,
  etiqueta: "1",
  exercicio: "SUPINO RETO",
  dose: "4 × 12",
  carga: "20 kg",
  intervalo: "1 min 30 s",
  observacao: "",
  pausa_segundos: 90,
  feito: false,
  carga_hoje: "",
  ultima_carga: "",
  ultima_data: "",
  ...extras,
});

const ficha = (exercicios, extras = {}) => ({
  nome: "A PEITO",
  ordem: 1,
  feitas: 0,
  feita_hoje: false,
  esforco_hoje: null,
  grupos: exercicios.map((e) => ({ nome: null, instrucao: "", exercicios: [e] })),
  ...extras,
});

describe("exercícios da ficha e progresso", () => {
  it("junta os exercícios dos grupos numa lista só", () => {
    const f = { grupos: [{ exercicios: [exercicio({ ordem: 1 }), exercicio({ ordem: 2 })] }, { exercicios: [exercicio({ ordem: 3 })] }] };

    expect(exerciciosDaFicha(f).map((e) => e.ordem)).toEqual([1, 2, 3]);
  });

  it("não quebra com ficha sem grupos ou fora do formato", () => {
    expect(exerciciosDaFicha(undefined)).toEqual([]);
    expect(exerciciosDaFicha({})).toEqual([]);
    expect(exerciciosDaFicha({ grupos: [null, {}, { exercicios: null }] })).toEqual([]);
  });

  it("mostra '3 de 8 feitos' só no meio do treino", () => {
    const oito = Array.from({ length: 8 }, (_, i) => exercicio({ ordem: i + 1, feito: i < 3 }));

    expect(textoDoProgresso(ficha(oito))).toBe("3 de 8 feitos");
  });

  it("não mostra nada quando nenhum foi marcado", () => {
    expect(textoDoProgresso(ficha([exercicio(), exercicio({ ordem: 2 })]))).toBe("");
  });

  it("não mostra nada quando a ficha já foi concluída hoje (aparece 'Concluído hoje')", () => {
    expect(textoDoProgresso(ficha([exercicio({ feito: true })], { feita_hoje: true }))).toBe("");
  });

  it("conta 1 de 1", () => {
    expect(textoDoProgresso(ficha([exercicio({ feito: true })]))).toBe("1 de 1 feitos");
  });
});

describe("botão de feito", () => {
  it("diz o que vai acontecer ao tocar", () => {
    expect(textoDoFeito(false)).toBe(TEXTO_MARCAR_FEITO);
    expect(textoDoFeito(true)).toBe(TEXTO_FEITO);
    expect(textoDoFeito(undefined)).toBe(TEXTO_MARCAR_FEITO);
  });
});

describe("conferirCarga", () => {
  it.each([
    ["12,5", "12,5"],
    ["12.5", "12,5"],
    ["30", "30"],
    ["030", "30"],
    ["  7  ", "7"],
    ["12,50", "12,5"],
    ["12,00", "12"],
    ["0,5", "0,5"],
    ["0,01", "0,01"],
    ["100", "100"],
    ["999,99", "999,99"],
    ["007,10", "7,1"],
  ])("aceita %j e guarda %j", (digitado, guardado) => {
    expect(conferirCarga(digitado)).toEqual({ ok: true, valor: guardado });
  });

  it.each([null, undefined, "", "   ", "\n"])("campo vazio (%j) significa apagar", (vazio) => {
    expect(conferirCarga(vazio)).toEqual({ ok: true, valor: null });
  });

  it.each(["abc", "20 kg", "20kg", "-5", "1000", "1.000", "1.000,5", "12,555", "1e3", ",5", "5,", "NaN", "Infinity", "12;5", "١٢", "1 2"])(
    "recusa %j: não é um número em kg",
    (ruim) => {
      expect(conferirCarga(ruim)).toEqual({ ok: false, mensagem: MENSAGEM_CARGA_NAO_E_NUMERO });
    },
  );

  it.each(["0", "0,0", "0,00", "000"])("recusa %j: precisa ser maior que zero", (zero) => {
    expect(conferirCarga(zero)).toEqual({ ok: false, mensagem: MENSAGEM_CARGA_ZERO });
  });

  it("o que não é texto (nunca acontece num campo digitado) é tratado como vazio", () => {
    expect(conferirCarga(12)).toEqual({ ok: true, valor: null });
  });
});

describe("última vez", () => {
  it("mostra a carga e o dia/mês", () => {
    expect(textoDaUltimaCarga(exercicio({ ultima_carga: "30", ultima_data: "20/10/2026" }))).toBe("Última vez: 30 kg · 20/10");
  });

  it("sem data, mostra só a carga", () => {
    expect(textoDaUltimaCarga(exercicio({ ultima_carga: "12,5", ultima_data: "" }))).toBe("Última vez: 12,5 kg");
  });

  it("vazio quando nunca anotou", () => {
    expect(textoDaUltimaCarga(exercicio())).toBe("");
    expect(textoDaUltimaCarga(undefined)).toBe("");
  });
});

describe("pedido e resposta do exercício", () => {
  it("monta o pedido com o lugar e o nome que o celular mostra", () => {
    const f = ficha([exercicio({ ordem: 3, exercicio: "CRUCIFIXO" })], { ordem: 2 });

    expect(pedidoDoExercicio(f, f.grupos[0].exercicios[0], { feito: true })).toEqual({ ficha: 2, item: 3, exercicio: "CRUCIFIXO", feito: true });
    expect(pedidoDoExercicio(f, f.grupos[0].exercicios[0], { carga: null })).toEqual({ ficha: 2, item: 3, exercicio: "CRUCIFIXO", carga: null });
  });

  it("entende a resposta boa", () => {
    expect(descreverExercicio(200, { ok: true, feito: true, carga_hoje: "30" })).toEqual({ tipo: "ok", feito: true, cargaHoje: "30" });
    expect(descreverExercicio(200, { ok: true, feito: false, carga_hoje: "" })).toEqual({ tipo: "ok", feito: false, cargaHoje: "" });
  });

  it("sessão perdida manda entrar de novo", () => {
    expect(descreverExercicio(401, { erro: "x" })).toEqual({ tipo: "entrar" });
  });

  it("409 pede para atualizar a página", () => {
    expect(descreverExercicio(409, { erro: "O seu treino mudou. Atualize a página." })).toEqual({
      tipo: "atualizar",
      mensagem: "O seu treino mudou. Atualize a página.",
    });
  });

  it("400 mostra a explicação do servidor", () => {
    expect(descreverExercicio(400, { erro: "Digite só o número, em kg. Exemplo: 12,5" })).toEqual({
      tipo: "erro",
      mensagem: "Digite só o número, em kg. Exemplo: 12,5",
    });
  });

  it.each([
    [200, null],
    [200, {}],
    [200, { ok: true }],
    [200, { ok: true, feito: "sim", carga_hoje: "" }],
    [200, { ok: true, feito: true, carga_hoje: 30 }],
    [500, null],
    [503, "x"],
  ])("resposta estranha (%j, %j) vira erro com código", (status, corpo) => {
    const resultado = descreverExercicio(status, corpo);

    expect(resultado.tipo).toBe("erro");
    expect(resultado.mensagem).toContain(String(status));
  });
});

describe("descanso", () => {
  it("sabe se o professor informou o intervalo do exercício", () => {
    expect(temDescanso(exercicio())).toBe(true);
    expect(temDescanso(exercicio({ pausa_segundos: 0 }))).toBe(false);
    expect(temDescanso(exercicio({ pausa_segundos: null }))).toBe(false);
    expect(temDescanso(exercicio({ pausa_segundos: "90" }))).toBe(false);
    expect(temDescanso(exercicio({ pausa_segundos: -5 }))).toBe(false);
    expect(temDescanso(undefined)).toBe(false);
  });

  it("o campo do tempo vem preenchido só com o intervalo que o professor lançou", () => {
    expect(descansoSugerido(exercicio())).toBe("90");
    expect(descansoSugerido(exercicio({ pausa_segundos: 45, intervalo: "45 s" }))).toBe("45");
  });

  it("sem intervalo do professor o campo fica EM BRANCO (nada de tempo inventado)", () => {
    for (const sem of [{ pausa_segundos: 0, intervalo: "" }, { pausa_segundos: null, intervalo: "" }, { pausa_segundos: "90", intervalo: "" }, { pausa_segundos: -5 }]) {
      expect(descansoSugerido(exercicio(sem))).toBe("");
    }
    expect(descansoSugerido(undefined)).toBe("");
  });

  it.each([
    ["60", 60],
    [" 90 ", 90],
    ["1", 1],
    ["045", 45],
    ["3600", 3600],
  ])("o tempo digitado %j vale %i segundos", (texto, segundos) => {
    expect(conferirDescanso(texto)).toEqual({ ok: true, segundos });
  });

  it.each([[""], ["   "], [null], [undefined]])("tempo em branco (%j) pede para digitar", (texto) => {
    expect(conferirDescanso(texto)).toEqual({ ok: false, mensagem: MENSAGEM_DESCANSO_VAZIO });
  });

  it.each([["0"], ["000"], ["3601"], ["9999"], ["1,5"], ["1.5"], ["-30"], ["1:30"], ["abc"], ["30 s"], ["12345"], ["+30"]])(
    "tempo inválido (%j) é recusado com a explicação",
    (texto) => {
      expect(conferirDescanso(texto)).toEqual({ ok: false, mensagem: MENSAGEM_DESCANSO_INVALIDO });
    },
  );

  it("o limite do descanso é uma hora, e a mensagem diz o limite", () => {
    expect(MAXIMO_DO_DESCANSO).toBe(3600);
    expect(MENSAGEM_DESCANSO_INVALIDO).toContain("3600");
  });

  it.each([
    [90, "1:30"],
    [5, "0:05"],
    [0, "0:00"],
    [60, "1:00"],
    [599, "9:59"],
    [600, "10:00"],
    [3600, "1:00:00"],
    [3661, "1:01:01"],
    [-3, "0:00"],
    [2.9, "0:02"],
    [NaN, "0:00"],
    [undefined, "0:00"],
  ])("escreve %j segundos como %j", (segundos, texto) => {
    expect(textoDoTempo(segundos)).toBe(texto);
  });

  it("conta os segundos que faltam pelo relógio, arredondando para cima", () => {
    expect(segundosRestantes(10_000, 0)).toBe(10);
    expect(segundosRestantes(10_000, 9_001)).toBe(1);
    expect(segundosRestantes(10_000, 9_999)).toBe(1);
    expect(segundosRestantes(10_000, 10_000)).toBe(0);
    expect(segundosRestantes(10_000, 50_000)).toBe(0);
  });
});

describe("nota de esforço", () => {
  it("são três opções, na ordem leve, ideal, pesado", () => {
    expect(ESFORCOS).toEqual([
      { valor: 1, texto: "Leve" },
      { valor: 2, texto: "Ideal" },
      { valor: 3, texto: "Pesado" },
    ]);
  });

  it("tocar na que já está escolhida tira; tocar em outra troca", () => {
    expect(proximoEsforco(null, 2)).toBe(2);
    expect(proximoEsforco(2, 2)).toBeNull();
    expect(proximoEsforco(2, 3)).toBe(3);
  });

  it("monta o pedido (null apaga)", () => {
    expect(pedidoDoEsforco({ ordem: 2 }, 3)).toEqual({ ficha: 2, esforco: 3 });
    expect(pedidoDoEsforco({ ordem: 2 }, null)).toEqual({ ficha: 2, esforco: null });
  });

  it("entende as respostas", () => {
    expect(descreverEsforco(200, { ok: true, ficha: 1, esforco: 2 })).toEqual({ tipo: "ok", esforco: 2 });
    expect(descreverEsforco(200, { ok: true, ficha: 1, esforco: null })).toEqual({ tipo: "ok", esforco: null });
    expect(descreverEsforco(401, {})).toEqual({ tipo: "entrar" });
    expect(descreverEsforco(409, { erro: "Conclua o treino primeiro, depois escolha como foi." })).toEqual({
      tipo: "erro",
      mensagem: "Conclua o treino primeiro, depois escolha como foi.",
    });
  });

  it.each([
    [200, { ok: true, esforco: 9 }],
    [200, { ok: true, esforco: "2" }],
    [200, { ok: true }],
    [200, null],
    [500, null],
  ])("resposta estranha (%j, %j) vira erro", (status, corpo) => {
    expect(descreverEsforco(status, corpo).tipo).toBe("erro");
  });
});

describe("o que o aluno marcou não faz o treino parecer 'mudado' quando o celular e o servidor concordam", () => {
  const treino = (e) => ({ nome: "TREINO ABC", inicio: null, fim: null, meta_por_ficha: null, ficha_do_dia: 1, fichas: [ficha([e])] });

  it("mudar o exercício no lugar (mesmas chaves) e buscar de novo dá 'nada'", () => {
    const naTela = treino(exercicio());
    const alvo = naTela.fichas[0].grupos[0].exercicios[0];
    alvo.feito = true; // o que o celular faz ao tocar
    alvo.carga_hoje = "30";
    const doServidor = treino(exercicio({ feito: true, carga_hoje: "30" }));

    expect(decidirAtualizacaoDoTreino(naTela, 200, { treino: doServidor }, false)).toEqual({ acao: "nada" });
  });

  it("se outro celular marcou, o treino novo é mostrado", () => {
    const naTela = treino(exercicio());
    const doServidor = treino(exercicio({ feito: true }));

    expect(decidirAtualizacaoDoTreino(naTela, 200, { treino: doServidor }, false).acao).toBe("mostrar");
  });
});


describe("tela de cada exercício: ir de um para outro", () => {
  const ex = (nome, feito = false) => exercicio({ exercicio: nome, feito });
  const tres = [ex("A"), ex("B"), ex("C")];

  it("a posição aparece como 'Exercício 3 de 8'", () => {
    expect(textoDaPosicao(0, 8)).toBe("Exercício 1 de 8");
    expect(textoDaPosicao(2, 8)).toBe("Exercício 3 de 8");
  });

  it("depois de marcar um exercício, vai para o primeiro AINDA NÃO FEITO que vem depois dele", () => {
    expect(proximoSemFazer([ex("A", true), ex("B"), ex("C")], 0)).toBe(1);
    expect(proximoSemFazer([ex("A", true), ex("B", true), ex("C")], 0)).toBe(2); // pula o que já está feito
  });

  it("se adiante está tudo feito, volta para o que ficou para trás", () => {
    expect(proximoSemFazer([ex("A"), ex("B", true), ex("C", true)], 2)).toBe(0);
    expect(proximoSemFazer([ex("A", true), ex("B"), ex("C", true)], 2)).toBe(1);
  });

  it("com tudo feito não há próximo (-1): a tela volta para a lista", () => {
    expect(proximoSemFazer([ex("A", true), ex("B", true), ex("C", true)], 1)).toBe(-1);
    expect(proximoSemFazer([ex("A", true)], 0)).toBe(-1);
    expect(proximoSemFazer([], 0)).toBe(-1);
  });

  it("só 'feito === true' conta como feito (valor estranho conta como não feito)", () => {
    expect(proximoSemFazer([ex("A"), exercicio({ feito: "sim" }), ex("C")], 0)).toBe(1);
  });

  it("o botão 'Próximo exercício' vai para o da posição seguinte, feito ou não; o último não tem próximo", () => {
    expect(proximoDaLista(tres, 0)).toBe(1);
    expect(proximoDaLista([ex("A"), ex("B", true), ex("C")], 0)).toBe(1);
    expect(proximoDaLista(tres, 2)).toBe(-1);
    expect(proximoDaLista([], 0)).toBe(-1);
  });

  it("ao buscar o treino de novo, só continua no exercício se ele ainda está naquele lugar", () => {
    const ficha = { grupos: [{ nome: null, exercicios: [ex("A"), ex("B")] }, { nome: "Bi-set", exercicios: [ex("C"), ex("D")] }] };
    expect(posicaoSeContinuaIgual(ficha, 2, "C")).toBe(2);
    expect(posicaoSeContinuaIgual(ficha, 1, "C")).toBe(-1); // o professor trocou a ordem: outro exercício ocuparia o lugar
    expect(posicaoSeContinuaIgual(ficha, 9, "C")).toBe(-1);
    expect(posicaoSeContinuaIgual(ficha, -1, "A")).toBe(-1);
    expect(posicaoSeContinuaIgual(undefined, 0, "A")).toBe(-1);
  });

  it("acha o bi-set ou tri-set do exercício (e nada para o exercício sozinho)", () => {
    const biset = { nome: "Bi-set", instrucao: "Faça A1 e A2 seguidos", exercicios: [ex("C"), ex("D")] };
    const ficha = { grupos: [{ nome: null, instrucao: "", exercicios: [ex("A"), ex("B")] }, biset] };
    expect(grupoDoExercicio(ficha, 0)).toBeNull();
    expect(grupoDoExercicio(ficha, 1)).toBeNull();
    expect(grupoDoExercicio(ficha, 2)).toBe(biset);
    expect(grupoDoExercicio(ficha, 3)).toBe(biset);
    expect(grupoDoExercicio(ficha, 4)).toBeNull();
    expect(grupoDoExercicio(undefined, 0)).toBeNull();
  });

  it("as frases que o app mostra ao levar o aluno sozinho", () => {
    expect(textoDoExercicioFeito("SUPINO RETO")).toBe("✓ SUPINO RETO feito.");
    expect(textoDeTodosFeitos({ feita_hoje: false })).toContain("Treino concluído");
    expect(textoDeTodosFeitos({ feita_hoje: true })).toBe("Todos os exercícios feitos!");
  });
});

describe("linha das últimas cargas (26/10/2026: uma linha só)", () => {
  it("com duas ou mais cargas mostra a evolução, da mais antiga para a mais nova", () => {
    expect(textoDaUltimaCarga(exercicio({ ultima_carga: "25", ultima_data: "20/10/2026", cargas_recentes: ["20", "22,5", "25"] }))).toBe(
      "Últimas: 20 → 22,5 → 25 kg",
    );
    expect(textoDaUltimaCarga(exercicio({ ultima_carga: "25", ultima_data: "20/10/2026", cargas_recentes: ["22,5", "25"] }))).toBe(
      "Últimas: 22,5 → 25 kg",
    );
  });

  it("com uma só, ou com dado estranho, continua como era", () => {
    expect(textoDaUltimaCarga(exercicio({ ultima_carga: "30", ultima_data: "20/10/2026", cargas_recentes: ["30"] }))).toBe("Última vez: 30 kg · 20/10");
    expect(textoDaUltimaCarga(exercicio({ ultima_carga: "30", ultima_data: "20/10/2026", cargas_recentes: "x" }))).toBe("Última vez: 30 kg · 20/10");
    expect(textoDaUltimaCarga(exercicio({ ultima_carga: "30", ultima_data: "20/10/2026", cargas_recentes: [null, ""] }))).toBe("Última vez: 30 kg · 20/10");
    expect(textoDaUltimaCarga(exercicio({ ultima_carga: "", cargas_recentes: ["20", "25"] }))).toBe("");
  });
});

describe("textoDaSemana (26/10/2026)", () => {
  it("mostra os treinos da semana e some quando não há nenhum", () => {
    expect(textoDaSemana({ treinos_na_semana: 1 })).toBe("Esta semana: 1 treino");
    expect(textoDaSemana({ treinos_na_semana: 3 })).toBe("Esta semana: 3 treinos");
    expect(textoDaSemana({ treinos_na_semana: 0 })).toBe("");
    expect(textoDaSemana({})).toBe("");
    expect(textoDaSemana({ treinos_na_semana: "2" })).toBe("");
    expect(textoDaSemana(null)).toBe("");
  });
});
