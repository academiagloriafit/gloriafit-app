import { describe, expect, it } from "vitest";
import {
  CAMPOS,
  MENSAGEM_SEM_REDE,
  descreverExistente,
  interpretarResposta,
} from "../app/static/novo_aluno_modelo.js";

describe("interpretarResposta: aluno criado", () => {
  it("201 com id válido -> criado", () => {
    expect(interpretarResposta(201, { id: 42 })).toEqual({ tipo: "criado", id: 42 });
  });

  it.each([
    ["sem corpo", null],
    ["sem id", {}],
    ["id texto (poderia virar parte de um endereço)", { id: "42" }],
    ["id com caminho", { id: "../x" }],
    ["id zero", { id: 0 }],
    ["id negativo", { id: -3 }],
    ["id decimal", { id: 1.5 }],
  ])("201 mas %s NÃO conta como criado (não abre outra tela)", (_nome, corpo) => {
    expect(interpretarResposta(201, corpo).tipo).toBe("falha");
  });

  it("200 com id não é criado (só 201 é)", () => {
    expect(interpretarResposta(200, { id: 42 }).tipo).toBe("falha");
  });
});

describe("interpretarResposta: erros de campo (400)", () => {
  it("mantém a mensagem de cada campo conhecido", () => {
    const r = interpretarResposta(400, {
      erros: { nome: "Digite o nome completo do aluno.", cpf: "Digite o CPF." },
    });
    expect(r).toEqual({
      tipo: "erros",
      erros: { nome: "Digite o nome completo do aluno.", cpf: "Digite o CPF." },
    });
  });

  it("campo desconhecido vira 'geral'", () => {
    const r = interpretarResposta(400, { erros: { outro: "algo errado" } });
    expect(r).toEqual({ tipo: "erros", erros: { geral: "algo errado" } });
  });

  it("'geral' vindo do servidor é mantido", () => {
    const r = interpretarResposta(400, { erros: { geral: "Formato do pedido inválido." } });
    expect(r.erros.geral).toBe("Formato do pedido inválido.");
  });

  it("ignora mensagens vazias ou que não são texto", () => {
    const r = interpretarResposta(400, { erros: { nome: "", cpf: 5, whatsapp: "WhatsApp inválido." } });
    expect(r).toEqual({ tipo: "erros", erros: { whatsapp: "WhatsApp inválido." } });
  });

  it("erros vazios ou em formato errado caem em falha, com a explicação do servidor se houver", () => {
    expect(interpretarResposta(400, { erros: {} }).tipo).toBe("falha");
    expect(interpretarResposta(400, { erros: ["nome"] }).tipo).toBe("falha");
    expect(interpretarResposta(400, { erros: "texto" }).tipo).toBe("falha");
    expect(interpretarResposta(400, { erro: "O JSON enviado é inválido" })).toEqual({
      tipo: "falha",
      mensagem: "O JSON enviado é inválido",
    });
  });

  it("os campos conhecidos são exatamente nome, cpf e whatsapp", () => {
    expect(CAMPOS).toEqual(["nome", "cpf", "whatsapp"]);
  });
});

describe("interpretarResposta: CPF que já existe (409)", () => {
  const corpo = {
    erro: "Já existe um aluno com este CPF.",
    existentes: [
      { id: 7, nome: "ANA SOUZA", provisorio: false, situacao_nome: "Ativo" },
      { id: 9, nome: "ANA S. SOUZA", provisorio: true, situacao_nome: null },
    ],
  };

  it("devolve a mensagem e a lista de quem já tem o CPF", () => {
    const r = interpretarResposta(409, corpo);
    expect(r.tipo).toBe("cpf_existente");
    expect(r.mensagem).toBe("Já existe um aluno com este CPF.");
    expect(r.existentes).toEqual([
      { id: 7, nome: "ANA SOUZA", provisorio: false, situacao_nome: "Ativo" },
      { id: 9, nome: "ANA S. SOUZA", provisorio: true, situacao_nome: null },
    ]);
  });

  it("descarta itens estragados (id que não é número, sem nome) e mantém os bons", () => {
    const r = interpretarResposta(409, {
      erro: "x",
      existentes: [
        { id: "7", nome: "TEXTO NO ID" },
        { id: 8 },
        null,
        { id: 3, nome: "BOA", provisorio: true },
      ],
    });
    expect(r.existentes).toEqual([{ id: 3, nome: "BOA", provisorio: true, situacao_nome: null }]);
  });

  it("'provisorio' só vale se for exatamente true", () => {
    const r = interpretarResposta(409, { existentes: [{ id: 3, nome: "A", provisorio: "sim" }] });
    expect(r.existentes[0].provisorio).toBe(false);
  });

  it("sem mensagem do servidor usa a padrão", () => {
    const r = interpretarResposta(409, { existentes: [] });
    expect(r.mensagem).toBe("Já existe um aluno com este CPF.");
  });

  it("409 sem lista 'existentes' é falha comum", () => {
    expect(interpretarResposta(409, { erro: "conflito" })).toEqual({ tipo: "falha", mensagem: "conflito" });
  });
});

describe("interpretarResposta: outras falhas", () => {
  it("resposta que não é JSON mostra o código", () => {
    const r = interpretarResposta(500, null);
    expect(r.tipo).toBe("falha");
    expect(r.mensagem).toContain("500");
    expect(r.mensagem).toContain("não foi cadastrado");
  });

  it("usa o 'erro' do servidor quando houver (ex.: 415, 429)", () => {
    expect(interpretarResposta(415, { erro: "Envie o pedido como JSON." }).mensagem).toBe("Envie o pedido como JSON.");
  });

  it("'erro' vazio ou não-texto é ignorado", () => {
    expect(interpretarResposta(500, { erro: "" }).mensagem).toContain("500");
    expect(interpretarResposta(500, { erro: 7 }).mensagem).toContain("500");
  });
});

describe("descreverExistente", () => {
  it("mostra a situação do Data4U", () => {
    expect(descreverExistente({ nome: "ANA", provisorio: false, situacao_nome: "Desistente" })).toBe(
      "ANA — Desistente",
    );
  });

  it("aluno provisório aparece como 'Provisório'", () => {
    expect(descreverExistente({ nome: "ANA", provisorio: true, situacao_nome: null })).toBe("ANA — Provisório");
  });

  it("sem situação mostra só o nome", () => {
    expect(descreverExistente({ nome: "ANA", provisorio: false, situacao_nome: null })).toBe("ANA");
  });
});

describe("MENSAGEM_SEM_REDE", () => {
  it("avisa que não dá para saber se salvou e diz o que fazer", () => {
    expect(MENSAGEM_SEM_REDE).toContain("Não consegui confirmar");
    expect(MENSAGEM_SEM_REDE).toContain("CPF já existe");
  });
});
