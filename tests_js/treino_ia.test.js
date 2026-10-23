import { describe, expect, it } from "vitest";
import {
  FALHAS_SEGUIDAS_PARA_DESISTIR,
  INTERVALO_DA_CONSULTA_MS,
  LIMITE_DAS_OBSERVACOES,
  LIMITE_DAS_RESPOSTAS,
  LIMITE_DO_MOTIVO,
  MAXIMO_DE_RODADAS,
  NOTAS_DA_AVALIACAO,
  TEMPO_MAXIMO_DA_ESPERA_MS,
  avisoDoRascunho,
  historicoDaConversa,
  interpretarAvaliacao,
  interpretarConsulta,
  interpretarPedido,
  montarAvaliacao,
  montarPedido,
  textoDaAvaliacaoEnviada,
  textoDaRodada,
  textoDeEspera,
  validarMotivo,
  validarPedido,
  validarRespostas,
} from "../app/static/treino_ia_modelo.js";
import { MENSAGEM_NAO_AUTORIZADO } from "../app/static/api.js";

const COMPLETO = { objetivo: "hipertrofia", nivel: "iniciante", dias: "3", minutos: "60", observacoes: "" };

describe("validarPedido", () => {
  it("aceita o formulário completo, com ou sem observações", () => {
    expect(validarPedido(COMPLETO)).toEqual([]);
    expect(validarPedido({ ...COMPLETO, observacoes: "dor no joelho direito; prefere máquinas" })).toEqual([]);
  });

  it("aponta cada campo que falta, na ordem da tela, com o id do campo", () => {
    const problemas = validarPedido({});

    expect(problemas.map((p) => p.campo)).toEqual(["ia-objetivo", "ia-nivel", "ia-dias", "ia-minutos"]);
    expect(problemas.every((p) => typeof p.mensagem === "string" && p.mensagem.endsWith("."))).toBe(true);
  });

  it("fichas diferentes é opcional: vazio vale, e escolhida não pode passar dos dias", () => {
    expect(validarPedido({ ...COMPLETO, dias: "5", fichas: "" })).toEqual([]);
    expect(validarPedido({ ...COMPLETO, dias: "5", fichas: "3" })).toEqual([]);
    expect(validarPedido({ ...COMPLETO, dias: "3", fichas: "3" })).toEqual([]);

    const problemas = validarPedido({ ...COMPLETO, dias: "3", fichas: "4" });

    expect(problemas).toHaveLength(1);
    expect(problemas[0].campo).toBe("ia-fichas");
    expect(problemas[0].mensagem).toBe("As fichas diferentes não podem ser mais do que os dias por semana.");
  });

  it("sem argumento nenhum também não quebra", () => {
    expect(validarPedido()).toHaveLength(4);
  });

  it("recusa observações acima do limite, contando letras como o servidor (emoji vale 1)", () => {
    expect(validarPedido({ ...COMPLETO, observacoes: "a".repeat(LIMITE_DAS_OBSERVACOES) })).toEqual([]);
    const passou = validarPedido({ ...COMPLETO, observacoes: "a".repeat(LIMITE_DAS_OBSERVACOES + 1) });
    expect(passou).toHaveLength(1);
    expect(passou[0].campo).toBe("ia-observacoes");
    expect(passou[0].mensagem).toContain(String(LIMITE_DAS_OBSERVACOES + 1));
    expect(validarPedido({ ...COMPLETO, observacoes: "💪".repeat(LIMITE_DAS_OBSERVACOES) })).toEqual([]);
  });

  it("espaços e quebras de linha a mais não contam", () => {
    const texto = "dor   no\n\njoelho" + " ".repeat(400);
    expect(validarPedido({ ...COMPLETO, observacoes: texto })).toEqual([]);
  });

  it.each(["cpf 123.456.789-09", "zap 27 98888-7777", "123456789", "tel (27)98888-7777", "doc 12 345 678 9"])(
    "recusa número de documento ou telefone nas observações: %s",
    (texto) => {
      const [problema] = validarPedido({ ...COMPLETO, observacoes: texto });
      expect(problema.campo).toBe("ia-observacoes");
      expect(problema.mensagem).toContain("CPF");
    },
  );

  it.each(["faz 3 series de 12", "treina ha 10 anos, 2 dias", "peso 80 kg, 1,75 m", "dor 7 de 10"])(
    "deixa passar números normais de treino: %s",
    (texto) => {
      expect(validarPedido({ ...COMPLETO, observacoes: texto })).toEqual([]);
    },
  );

  it("recusa e-mail nas observações", () => {
    const [problema] = validarPedido({ ...COMPLETO, observacoes: "manda para ana@exemplo.com" });
    expect(problema.mensagem).toContain("e-mail");
  });

  it("o limite das observações é 1000 letras (cabe a descrição completa do aluno)", () => {
    expect(LIMITE_DAS_OBSERVACOES).toBe(1000);
    const descricao =
      "35 anos, 1,75 m, 82 kg, pressão 130/85. Trabalha sentado o dia todo. Dor no joelho direito ao agachar, " +
      "operou o menisco em 03/2024. Treinou 2 anos e parou há 1 ano. Não gosta de esteira; prefere máquinas. ";
    const texto = descricao.repeat(4).trim();
    expect(texto.length).toBeGreaterThan(300);
    expect(validarPedido({ ...COMPLETO, observacoes: texto })).toEqual([]);
  });

  it.each(["operou em 15/03/2024", "nasceu 12/03/1985", "nasceu em 12 03 1985"])(
    "recusa data completa e a mensagem explica o que escrever no lugar: %s",
    (texto) => {
      const [problema] = validarPedido({ ...COMPLETO, observacoes: texto });
      expect(problema.campo).toBe("ia-observacoes");
      expect(problema.mensagem).toContain("datas completas");
      expect(problema.mensagem).toContain("mês e o ano");
    },
  );

  it.each(["operou em 03/2024", "operou em março de 2024", "nasceu em 85", "operou 15/03/24"])(
    "deixa passar mês e ano ou idade: %s",
    (texto) => {
      expect(validarPedido({ ...COMPLETO, observacoes: texto })).toEqual([]);
    },
  );
});

describe("montarPedido", () => {
  it("manda dias e minutos como número e as observações limpas", () => {
    expect(montarPedido({ ...COMPLETO, observacoes: "  dor   no  joelho \n" })).toEqual({
      objetivo: "hipertrofia",
      nivel: "iniciante",
      dias: 3,
      minutos: 60,
      fichas_diferentes: null,
      observacoes: "dor no joelho",
      perguntar: false,
      rodadas: [],
    });
  });

  it("fichas diferentes vai como número quando o professor escolheu e como null quando o robô decide", () => {
    expect(montarPedido({ ...COMPLETO, fichas: "3" }).fichas_diferentes).toBe(3);
    expect(montarPedido({ ...COMPLETO, fichas: "" }).fichas_diferentes).toBeNull();
    expect(montarPedido(COMPLETO).fichas_diferentes).toBeNull();
  });

  it("por padrão a IA não pergunta e não leva conversa nenhuma", () => {
    const pedido = montarPedido(COMPLETO);

    expect(pedido.perguntar).toBe(false);
    expect(pedido.rodadas).toEqual([]);
  });

  it("deixa a IA perguntar e leva a conversa até agora, com os textos limpos", () => {
    const rodadas = [{ perguntas: ["  O que  mudar? "], respostas: ["  mais   peito \n"] }];

    const pedido = montarPedido(COMPLETO, { perguntar: true, rodadas });

    expect(pedido.perguntar).toBe(true);
    expect(pedido.rodadas).toEqual([{ perguntas: ["O que mudar?"], respostas: ["mais peito"] }]);
  });

  it("resposta em branco ou ausente vai como texto vazio, nunca como undefined", () => {
    const pedido = montarPedido(COMPLETO, { rodadas: [{ perguntas: ["a?", "b?"], respostas: ["", undefined] }] });

    expect(pedido.rodadas[0].respostas).toEqual(["", ""]);
  });

  it("só aceita verdadeiro de verdade em perguntar (texto \"false\" não vira sim)", () => {
    expect(montarPedido(COMPLETO, { perguntar: "false" }).perguntar).toBe(false);
  });

  it("não mexe nas rodadas que recebeu", () => {
    const rodadas = [{ perguntas: [" a? "], respostas: [" b "] }];
    montarPedido(COMPLETO, { rodadas });

    expect(rodadas).toEqual([{ perguntas: [" a? "], respostas: [" b "] }]);
  });

  it("sem observações manda texto vazio, nunca undefined", () => {
    const { observacoes } = montarPedido({ objetivo: "forca", nivel: "avancado", dias: "5", minutos: "90" });
    expect(observacoes).toBe("");
  });
});

describe("interpretarPedido", () => {
  it("202 com o número do pedido", () => {
    expect(interpretarPedido({ status: 202, corpo: { pedido_id: 12 } })).toEqual({ tipo: "aceito", pedidoId: 12 });
  });

  it.each([
    [{ status: 202, corpo: {} }],
    [{ status: 202, corpo: { pedido_id: "12" } }],
    [{ status: 202, corpo: { pedido_id: 0 } }],
    [{ status: 202, corpo: null }],
    [null],
  ])("202 sem número de pedido que sirva é recusado: %j", (resposta) => {
    expect(interpretarPedido(resposta).tipo).toBe("recusado");
  });

  it("devolve o motivo em português que o servidor mandou", () => {
    expect(interpretarPedido({ status: 409, corpo: { erro: "Este aluno está na fila Gestante.", bloqueio: "fila_com_liberacao" } })).toEqual({
      tipo: "recusado",
      mensagem: "Este aluno está na fila Gestante.",
    });
    expect(interpretarPedido({ status: 400, corpo: { erros: ["Escolha o objetivo do aluno.", "Escolha o nível do aluno."] } }).mensagem).toBe(
      "Escolha o objetivo do aluno. Escolha o nível do aluno.",
    );
    expect(interpretarPedido({ status: 429, corpo: { erro: "Já foram feitos 40 pedidos à IA hoje (o limite do dia)." } }).mensagem).toContain("40 pedidos");
  });

  it("computador sem autorização pede o código novo", () => {
    expect(interpretarPedido({ status: 401, corpo: { erro: "x" } }).mensagem).toBe(MENSAGEM_NAO_AUTORIZADO);
  });

  it("resposta sem mensagem vira frase com o código", () => {
    expect(interpretarPedido({ status: 500, corpo: null }).mensagem).toContain("código 500");
  });
});

describe("interpretarConsulta", () => {
  const treino = { nome: "", sessoes_por_ficha: null, indisponiveis: 0, fichas: [{ nome: "A", itens: [] }] };

  it("andando", () => {
    expect(interpretarConsulta({ status: 200, corpo: { situacao: "andando" } })).toEqual({ tipo: "andando" });
  });

  it("pronto traz o treino, o resumo, os alertas e quantos exercícios foram tirados", () => {
    const lida = interpretarConsulta({
      status: 200,
      corpo: { situacao: "pronto", treino, resumo: "Divisão simples.", alertas: ["Joelho."], removidos: 2 },
    });

    expect(lida).toEqual({ tipo: "pronto", treino, resumo: "Divisão simples.", alertas: ["Joelho."], removidos: 2 });
  });

  it("pronto com campos estranhos usa valores seguros", () => {
    const lida = interpretarConsulta({
      status: 200,
      corpo: { situacao: "pronto", treino, resumo: 5, alertas: ["ok", "", 7, null, "  "], removidos: -3 },
    });

    expect(lida).toMatchObject({ tipo: "pronto", resumo: "", alertas: ["ok"], removidos: 0 });
  });

  it("pronto com perguntas: a IA quer saber mais, com a rodada e o máximo", () => {
    const lida = interpretarConsulta({
      status: 200,
      corpo: { situacao: "pronto", perguntas: ["Qual o foco?", "Tem lesão?"], rodada: 1, maximo_de_rodadas: 2 },
    });

    expect(lida).toEqual({ tipo: "perguntas", perguntas: ["Qual o foco?", "Tem lesão?"], rodada: 1, maximoDeRodadas: 2 });
  });

  it("perguntas vazias ou em branco são tiradas; sobrando nenhuma é falha, não tela vazia", () => {
    const comLixo = { situacao: "pronto", perguntas: ["ok?", "", "  ", 3, null], rodada: 2, maximo_de_rodadas: 2 };
    expect(interpretarConsulta({ status: 200, corpo: comLixo })).toMatchObject({ tipo: "perguntas", perguntas: ["ok?"] });
    for (const perguntas of [[], ["", " "], [1, 2]]) {
      expect(interpretarConsulta({ status: 200, corpo: { situacao: "pronto", perguntas, rodada: 1, maximo_de_rodadas: 2 } }).tipo).toBe("falha");
    }
  });

  it.each([[{ rodada: 0 }], [{ rodada: "1" }], [{ rodada: null }], [{}]])("perguntas sem rodada que sirva é falha: %j", (extra) => {
    expect(interpretarConsulta({ status: 200, corpo: { situacao: "pronto", perguntas: ["a?"], ...extra } }).tipo).toBe("falha");
  });

  it("máximo de rodadas estranho cai no padrão", () => {
    for (const maximo of [undefined, "2", 0, null]) {
      const lida = interpretarConsulta({ status: 200, corpo: { situacao: "pronto", perguntas: ["a?"], rodada: 1, maximo_de_rodadas: maximo } });
      expect(lida.maximoDeRodadas).toBe(MAXIMO_DE_RODADAS);
    }
  });

  it("perguntas têm prioridade só quando o resultado traz a lista; treino continua sendo rascunho", () => {
    const comTreino = { situacao: "pronto", treino, resumo: "", alertas: [], removidos: 0 };
    expect(interpretarConsulta({ status: 200, corpo: comTreino }).tipo).toBe("pronto");
  });

  it("pronto sem treino de verdade é falha, não rascunho vazio", () => {
    for (const corpo of [{ situacao: "pronto" }, { situacao: "pronto", treino: "x" }, { situacao: "pronto", treino: {} }]) {
      expect(interpretarConsulta({ status: 200, corpo }).tipo).toBe("falha");
    }
  });

  it("erro traz a frase em português do servidor", () => {
    expect(interpretarConsulta({ status: 200, corpo: { situacao: "erro", erro: "A IA está fora do ar." } })).toEqual({
      tipo: "erro",
      mensagem: "A IA está fora do ar.",
    });
  });

  it("pedido que sumiu (404) é erro e não vale tentar de novo", () => {
    expect(interpretarConsulta({ status: 404, corpo: { erro: "Pedido não encontrado." } }).tipo).toBe("erro");
  });

  it("computador sem autorização é erro com a mensagem de sempre", () => {
    expect(interpretarConsulta({ status: 401, corpo: null })).toEqual({ tipo: "erro", mensagem: MENSAGEM_NAO_AUTORIZADO });
  });

  it.each([[{ status: 500, corpo: null }], [{ status: 200, corpo: null }], [{ status: 200, corpo: { situacao: "outra" } }], [null]])(
    "resposta que não se entende é falha (vale tentar de novo): %j",
    (resposta) => {
      expect(interpretarConsulta(resposta).tipo).toBe("falha");
    },
  );
});

describe("avisoDoRascunho", () => {
  const treino = { fichas: [{ itens: [1, 2, 3] }, { itens: [1, 2] }] };

  it("diz quantas fichas e exercícios, pede para conferir e fica verde se não há nada especial", () => {
    const { texto, atencao } = avisoDoRascunho({ treino });

    expect(texto).toBe(
      "Rascunho montado pela IA (2 fichas, 5 exercícios). Ele pode ter erro: confira tudo e ajuste antes de salvar.",
    );
    expect(atencao).toBe(false);
  });

  it("usa o singular", () => {
    expect(avisoDoRascunho({ treino: { fichas: [{ itens: [1] }] } }).texto).toContain("(1 ficha, 1 exercício)");
  });

  it("leva o resumo e os alertas da IA e fica laranja por causa dos alertas", () => {
    const { texto, atencao } = avisoDoRascunho({ treino, resumo: "Divisão simples.", alertas: ["Joelho.", "Ombro."] });

    expect(texto).toContain("Divisão simples.");
    expect(texto).toContain("Atenção: Joelho. Ombro.");
    expect(atencao).toBe(true);
  });

  it("avisa dos exercícios inventados que foram tirados, no singular e no plural, e fica laranja", () => {
    expect(avisoDoRascunho({ treino, removidos: 1 })).toMatchObject({ atencao: true });
    expect(avisoDoRascunho({ treino, removidos: 1 }).texto).toContain("1 exercício que não existe na academia; ele foi tirado");
    expect(avisoDoRascunho({ treino, removidos: 3 }).texto).toContain("3 exercícios que não existem na academia; eles foram tirados");
  });
});

describe("espera", () => {
  it("o texto da espera mostra os segundos", () => {
    expect(textoDeEspera(0)).toContain("0 s");
    expect(textoDeEspera(42)).toContain("42 s");
  });

  it("enquanto a IA ainda pode perguntar, o texto não promete que o treino está sendo montado", () => {
    expect(textoDeEspera(5)).toContain("Montando o treino");
    expect(textoDeEspera(5, true)).toContain("analisando");
    expect(textoDeEspera(5, true)).not.toContain("Montando");
  });

  it("o prazo da tela é maior que o prazo em que o servidor cancela o pedido (4 minutos)", () => {
    expect(TEMPO_MAXIMO_DA_ESPERA_MS).toBeGreaterThan(4 * 60 * 1000);
    expect(INTERVALO_DA_CONSULTA_MS).toBeGreaterThanOrEqual(1000);
    expect(FALHAS_SEGUIDAS_PARA_DESISTIR).toBeGreaterThanOrEqual(2);
  });
});

describe("validarRespostas", () => {
  it("aceita respostas normais, em branco e números de treino", () => {
    expect(validarRespostas(["Mais peito e braço.", "", "3 dias, séries de 4 x 12, 60 min", "dor 7 de 10"])).toEqual([]);
  });

  it("sem argumento nem respostas não quebra", () => {
    expect(validarRespostas()).toEqual([]);
    expect(validarRespostas([undefined, null])).toEqual([]);
  });

  it("recusa resposta acima do limite, contando como o servidor (emoji vale 1) e dizendo qual é", () => {
    expect(validarRespostas(["a".repeat(LIMITE_DAS_RESPOSTAS), "💪".repeat(LIMITE_DAS_RESPOSTAS)])).toEqual([]);
    const [problema] = validarRespostas(["ok", "a".repeat(LIMITE_DAS_RESPOSTAS + 1)]);

    expect(problema.indice).toBe(1);
    expect(problema.mensagem).toContain("resposta 2");
    expect(problema.mensagem).toContain(String(LIMITE_DAS_RESPOSTAS + 1));
  });

  it.each(["cpf 123.456.789-09", "zap 27 98888-7777", "123456789"])("recusa número de documento ou telefone: %s", (texto) => {
    const [problema] = validarRespostas([texto]);

    expect(problema).toMatchObject({ indice: 0 });
    expect(problema.mensagem).toContain("CPF");
  });

  it("recusa data completa na resposta, com a mesma explicação das observações", () => {
    const [problema] = validarRespostas(["operou em 15/03/2024"]);

    expect(problema.mensagem).toContain("resposta 1");
    expect(problema.mensagem).toContain("datas completas");
  });

  it("recusa e-mail", () => {
    expect(validarRespostas(["ok", "ana@exemplo.com"])[0].mensagem).toContain("e-mail");
  });

  it("aponta todas as respostas com problema, na ordem", () => {
    expect(validarRespostas(["a@b.com", "ok", "123456789"]).map((p) => p.indice)).toEqual([0, 2]);
  });

  it("espaços e quebras de linha a mais não contam", () => {
    expect(validarRespostas(["dor   no\n\njoelho" + " ".repeat(400)])).toEqual([]);
  });
});

describe("a conversa na tela", () => {
  it("o histórico junta as rodadas na ordem, com resposta em branco como texto vazio", () => {
    const rodadas = [
      { perguntas: ["O que mudar?", "Alguma lesão?"], respostas: ["  mais   peito ", ""] },
      { perguntas: ["Prefere halteres?"], respostas: ["Sim."] },
    ];

    expect(historicoDaConversa(rodadas)).toEqual([
      { pergunta: "O que mudar?", resposta: "mais peito" },
      { pergunta: "Alguma lesão?", resposta: "" },
      { pergunta: "Prefere halteres?", resposta: "Sim." },
    ]);
    expect(historicoDaConversa()).toEqual([]);
  });

  it("o selo da rodada avisa quando é a última", () => {
    expect(textoDaRodada({ rodada: 1, maximoDeRodadas: 2 })).toBe("Rodada 1 de 2");
    expect(textoDaRodada({ rodada: 2, maximoDeRodadas: 2 })).toBe("Última rodada (2 de 2)");
  });

  it("o máximo de rodadas é 2, como no servidor", () => {
    expect(MAXIMO_DE_RODADAS).toBe(2);
  });
});


describe("avaliar o rascunho", () => {
  it("tem as três notas, na ordem da tela; só as que apontam defeito pedem o motivo", () => {
    expect(NOTAS_DA_AVALIACAO.map((n) => n.valor)).toEqual(["serviu", "com_ajustes", "nao_serviu"]);
    expect(NOTAS_DA_AVALIACAO.map((n) => n.pedeMotivo)).toEqual([false, true, true]);
    expect(NOTAS_DA_AVALIACAO.every((n) => n.rotulo.length > 0)).toBe(true);
  });

  it("validarMotivo aceita texto sobre o treino, em branco ou até o limite", () => {
    expect(validarMotivo("")).toBe("");
    expect(validarMotivo()).toBe("");
    expect(validarMotivo("Faltou exercício de posterior de coxa")).toBe("");
    expect(validarMotivo("a".repeat(LIMITE_DO_MOTIVO))).toBe("");
    expect(validarMotivo("💪".repeat(LIMITE_DO_MOTIVO))).toBe(""); // emoji vale 1 letra, como no servidor
  });

  it("validarMotivo recusa o que passa do limite, número longo, data completa e e-mail", () => {
    expect(validarMotivo("a".repeat(LIMITE_DO_MOTIVO + 1))).toContain(`o máximo é ${LIMITE_DO_MOTIVO}`);
    expect(validarMotivo("cpf 123.456.789-09")).toMatch(/Tire do motivo números/);
    expect(validarMotivo("zap 27 98888-7777")).toMatch(/Tire do motivo números/);
    expect(validarMotivo("operou em 15/03/2024")).toMatch(/datas completas/);
    expect(validarMotivo("fale com ana@exemplo.com")).toMatch(/e-mail/);
  });

  it("validarMotivo conta as letras depois de limpar os espaços (como o servidor)", () => {
    expect(validarMotivo("a".repeat(LIMITE_DO_MOTIVO) + " ".repeat(500))).toBe("");
    expect(validarMotivo("  faltou \n\n  posterior  ")).toBe("");
  });

  it("montarAvaliacao limpa o motivo e não manda motivo em branco", () => {
    expect(montarAvaliacao("serviu")).toEqual({ nota: "serviu" });
    expect(montarAvaliacao("serviu", "   \n ")).toEqual({ nota: "serviu" });
    expect(montarAvaliacao("com_ajustes", "  faltou   posterior\n de coxa ")).toEqual({ nota: "com_ajustes", motivo: "faltou posterior de coxa" });
  });

  it("interpretarAvaliacao: enviada, já avaliada, rascunho que sumiu, recusada e sem resposta", () => {
    expect(interpretarAvaliacao({ status: 201, corpo: { ok: true } })).toEqual({ tipo: "enviada" });
    expect(interpretarAvaliacao({ status: 409, corpo: { erro: "Este rascunho já foi avaliado. Obrigado!" } })).toEqual({
      tipo: "ja_avaliado",
      mensagem: "Este rascunho já foi avaliado. Obrigado!",
    });
    expect(interpretarAvaliacao({ status: 404, corpo: { erro: "Este rascunho não existe mais." } })).toEqual({
      tipo: "sem_rascunho",
      mensagem: "Este rascunho não existe mais.",
    });
    expect(interpretarAvaliacao({ status: 400, corpo: { erros: ["Tire do motivo o e-mail.", "Outro problema."] } })).toEqual({
      tipo: "recusada",
      mensagem: "Tire do motivo o e-mail. Outro problema.",
    });
    expect(interpretarAvaliacao({ status: 401, corpo: null })).toEqual({ tipo: "recusada", mensagem: MENSAGEM_NAO_AUTORIZADO });
    expect(interpretarAvaliacao({ status: 500, corpo: null }).mensagem).toBe("Não consegui enviar a avaliação (código 500).");
    expect(interpretarAvaliacao(undefined)).toEqual({ tipo: "recusada", mensagem: "Não consegui enviar a avaliação (código 0)." });
  });

  it("textoDaAvaliacaoEnviada agradece e diz qual nota foi", () => {
    expect(textoDaAvaliacaoEnviada("nao_serviu")).toContain("(Não serviu)");
    expect(textoDaAvaliacaoEnviada("serviu")).toMatch(/^Avaliação enviada \(Serviu\)\. Obrigado/);
    expect(textoDaAvaliacaoEnviada("qualquer")).toMatch(/^Avaliação enviada\. Obrigado/);
  });
});
