import { describe, expect, it } from "vitest";
import {
  FALHAS_SEGUIDAS_PARA_DESISTIR,
  INTERVALO_DA_CONSULTA_MS,
  LIMITE_DAS_OBSERVACOES,
  TEMPO_MAXIMO_DA_ESPERA_MS,
  avisoDoRascunho,
  interpretarConsulta,
  interpretarPedido,
  montarPedido,
  textoDeEspera,
  validarPedido,
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
});

describe("montarPedido", () => {
  it("manda dias e minutos como número e as observações limpas", () => {
    expect(montarPedido({ ...COMPLETO, observacoes: "  dor   no  joelho \n" })).toEqual({
      objetivo: "hipertrofia",
      nivel: "iniciante",
      dias: 3,
      minutos: 60,
      observacoes: "dor no joelho",
    });
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
    expect(interpretarPedido({ status: 429, corpo: { erro: "Já foram feitos 20 rascunhos hoje." } }).mensagem).toContain("20 rascunhos");
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

  it("o prazo da tela é maior que o prazo em que o servidor cancela o pedido (4 minutos)", () => {
    expect(TEMPO_MAXIMO_DA_ESPERA_MS).toBeGreaterThan(4 * 60 * 1000);
    expect(INTERVALO_DA_CONSULTA_MS).toBeGreaterThanOrEqual(1000);
    expect(FALHAS_SEGUIDAS_PARA_DESISTIR).toBeGreaterThanOrEqual(2);
  });
});
