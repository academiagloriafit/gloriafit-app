// Senha de administrador nas telas: os treinos padrão são fixos, então guardar um novo ou excluir um pede a senha.
// Aqui só a parte sem tela (a conferência de verdade é do servidor). Dados inventados.
import { describe, expect, it } from "vitest";
import { motivoDaSenha, textoDoErro } from "../app/static/api.js";
import {
  MAXIMO_DA_SENHA_DE_ADMIN,
  adicionarItem,
  atualizarItem,
  criarEstado,
  montarPedidoDePadrao,
  problemaDaSenhaDeAdmin,
} from "../app/static/treino_modelo.js";

function treinoSimples() {
  let e = adicionarItem(criarEstado(), 0, { id: 1, nome: "SUPINO" });
  e = atualizarItem(e, 0, 1, "series", "3");
  return atualizarItem(e, 0, 1, "repeticoes", "12");
}

describe("problemaDaSenhaDeAdmin", () => {
  it("senha preenchida = sem problema (se está certa, só o servidor sabe)", () => {
    expect(problemaDaSenhaDeAdmin("qualquer coisa 123")).toBeNull();
    expect(problemaDaSenhaDeAdmin("a")).toBeNull();
  });

  it("vazia, ou que não é texto, pede a senha", () => {
    for (const ruim of ["", undefined, null, 123, {}]) {
      expect(problemaDaSenhaDeAdmin(ruim), String(ruim)).toBe("Digite a senha de administrador.");
    }
  });

  it("só espaços NÃO é vazia: espaço pode fazer parte da senha (nada é cortado)", () => {
    expect(problemaDaSenhaDeAdmin("   ")).toBeNull();
  });

  it("passou do tamanho máximo: nem vai ao servidor (não gasta uma das tentativas)", () => {
    expect(MAXIMO_DA_SENHA_DE_ADMIN).toBe(128);
    expect(problemaDaSenhaDeAdmin("x".repeat(128))).toBeNull();
    expect(problemaDaSenhaDeAdmin("x".repeat(129))).toContain("no máximo 128");
  });
});

describe("montarPedidoDePadrao leva a senha", () => {
  const dados = { nomePadrao: "Mulher 3", montadoPor: "Ana", filaId: "2", numero: "3" };

  it("senha_admin vai exatamente como foi digitada (sem cortar espaços)", () => {
    const pedido = montarPedidoDePadrao(treinoSimples(), { ...dados, senhaAdmin: "  Sen ha 1  " });
    expect(pedido.senha_admin).toBe("  Sen ha 1  ");
    expect(pedido).toMatchObject({ nome: "Mulher 3", fila_id: 2, numero: 3 });
  });

  it("sem senha informada a chave existe e vai vazia (o servidor recusa)", () => {
    expect(montarPedidoDePadrao(treinoSimples(), dados)).toHaveProperty("senha_admin", "");
  });
});

describe("motivoDaSenha: o servidor recusou por causa da senha?", () => {
  it("403 e 429 com o campo `senha`", () => {
    expect(motivoDaSenha({ status: 403, corpo: { erro: "x", senha: "incorreta" } })).toBe("incorreta");
    expect(motivoDaSenha({ status: 403, corpo: { erro: "x", senha: "nao_definida" } })).toBe("nao_definida");
    expect(motivoDaSenha({ status: 429, corpo: { erro: "x", senha: "travada" } })).toBe("travada");
  });

  it("qualquer outra resposta não é problema de senha", () => {
    const respostas = [
      { status: 403, corpo: { erro: "Origem não permitida" } }, // 403 de outro motivo (checagem de origem)
      { status: 403, corpo: null },
      { status: 400, corpo: { erro: "x", senha: "incorreta" } },
      { status: 403, corpo: { senha: "outra-coisa" } },
      { status: 200, corpo: {} },
      { status: 401, corpo: { erro: "x" } },
      null,
      undefined,
    ];
    for (const r of respostas) expect(motivoDaSenha(r), JSON.stringify(r)).toBeNull();
  });

  it("a mensagem que o professor lê é a do servidor", () => {
    const r = { status: 403, corpo: { erro: "Senha de administrador incorreta.", senha: "incorreta" } };
    expect(textoDoErro(r, "falhou")).toBe("Senha de administrador incorreta.");
  });
});
