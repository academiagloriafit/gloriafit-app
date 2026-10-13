import { describe, expect, it } from "vitest";
import {
  camposDoTreinoExistente,
  estadoDeImportacao,
  modoDaTela,
  montarPedido,
  treinoServeParaOModo,
} from "../app/static/treino_modelo.js";

// O que GET /api/treinos/<id>/para-editar devolve (dados inventados).
function treinoDoServidor(mudancas = {}) {
  return {
    id: 7,
    aluno_id: 3,
    nome: "TREINO ABC",
    montado_por: "Bia",
    inicio: "2026-10-01",
    fim: "2026-12-01",
    sessoes_por_ficha: 12,
    ativo: true,
    origem: "app",
    indisponiveis: 0,
    fichas: [
      {
        nome: "FICHA A",
        itens: [
          { exercicio_id: 1, nome: "SUPINO RETO", series: "3", repeticoes: "12", carga: "20kg", pausa: 90, observacao: "devagar", bloco: null, indisponivel: false },
          { exercicio_id: 2, nome: "REMADA", series: "3", repeticoes: "10", carga: "", pausa: null, observacao: "", bloco: null, indisponivel: false },
        ],
      },
    ],
    ...mudancas,
  };
}

describe("modoDaTela (o que o endereço pede)", () => {
  it("?editar=ID e ?copiar=ID", () => {
    expect(modoDaTela("?editar=7")).toEqual({ tipo: "editar", treinoId: 7 });
    expect(modoDaTela("?copiar=12")).toEqual({ tipo: "copiar", treinoId: 12 });
  });

  it("sem pedido nenhum é tela de treino novo", () => {
    expect(modoDaTela("")).toBeNull();
    expect(modoDaTela("?outra=1")).toBeNull();
    expect(modoDaTela(undefined)).toBeNull();
    expect(modoDaTela(null)).toBeNull();
  });

  it("só aceita número inteiro positivo; o resto é ignorado", () => {
    for (const ruim of ["0", "-3", "1.5", "abc", "", "007", "99999999999", "1e3", " 4", "4 "]) {
      expect(modoDaTela("?editar=" + encodeURIComponent(ruim))).toBeNull();
    }
  });

  it("se vierem os dois, vale o editar", () => {
    expect(modoDaTela("?copiar=2&editar=5")).toEqual({ tipo: "editar", treinoId: 5 });
  });
});

describe("treinoServeParaOModo", () => {
  const editar = { tipo: "editar", treinoId: 7 };
  const copiar = { tipo: "copiar", treinoId: 7 };

  it("editar no lugar: só treino do app, ativo e deste aluno", () => {
    expect(treinoServeParaOModo(editar, treinoDoServidor(), 3)).toBe(true);
    expect(treinoServeParaOModo(editar, treinoDoServidor(), "3")).toBe(true); // o id da tela vem como texto
    expect(treinoServeParaOModo(editar, treinoDoServidor({ origem: "data4u" }), 3)).toBe(false);
    expect(treinoServeParaOModo(editar, treinoDoServidor({ ativo: false }), 3)).toBe(false);
    expect(treinoServeParaOModo(editar, treinoDoServidor(), 4)).toBe(false);
  });

  it("copiar: qualquer origem e situação, mas só do próprio aluno", () => {
    expect(treinoServeParaOModo(copiar, treinoDoServidor({ origem: "data4u" }), 3)).toBe(true);
    expect(treinoServeParaOModo(copiar, treinoDoServidor({ ativo: false }), 3)).toBe(true);
    expect(treinoServeParaOModo(copiar, treinoDoServidor(), 4)).toBe(false);
  });

  it("resposta fora do formato não serve", () => {
    for (const ruim of [null, undefined, "texto", 5, []]) {
      expect(treinoServeParaOModo(editar, ruim, 3)).toBe(false);
      expect(treinoServeParaOModo(copiar, ruim, 3)).toBe(false);
    }
  });
});

describe("camposDoTreinoExistente", () => {
  it("devolve nome, datas e meta como texto e guarda o professor anterior só para a dica", () => {
    const campos = camposDoTreinoExistente(treinoDoServidor());
    expect(campos).toEqual({ nome: "TREINO ABC", professorAnterior: "Bia", inicio: "2026-10-01", fim: "2026-12-01", sessoes: "12" });
  });

  it("sem fim e sem meta ficam em branco", () => {
    const campos = camposDoTreinoExistente(treinoDoServidor({ fim: null, sessoes_por_ficha: null }));
    expect(campos.fim).toBe("");
    expect(campos.sessoes).toBe("");
  });

  it("data fora do formato vira em branco (o campo de data não aceitaria)", () => {
    expect(camposDoTreinoExistente(treinoDoServidor({ inicio: "01/10/2026", fim: "2026-1-5" }))).toMatchObject({ inicio: "", fim: "" });
  });

  it("aguenta lixo sem quebrar", () => {
    expect(camposDoTreinoExistente(null)).toEqual({ nome: "", professorAnterior: "", inicio: "", fim: "", sessoes: "" });
    expect(camposDoTreinoExistente({ nome: 5, montado_por: {}, sessoes_por_ficha: "x" })).toMatchObject({ nome: "", professorAnterior: "", sessoes: "" });
  });
});

describe("abrir um treino e mandá-lo de volta", () => {
  it("sem mexer em nada, o pedido de salvar leva o mesmo treino (com o professor de quem edita)", () => {
    const treino = treinoDoServidor();
    const estado = estadoDeImportacao(treino);
    const campos = camposDoTreinoExistente(treino);

    const pedido = montarPedido(estado, {
      nomeTreino: campos.nome,
      montadoPor: "Carlos",
      inicio: campos.inicio,
      fim: campos.fim,
      sessoesPorFicha: campos.sessoes,
    });

    expect(pedido).toMatchObject({
      nome_treino: "TREINO ABC",
      montado_por: "Carlos",
      inicio: "2026-10-01",
      fim: "2026-12-01",
      sessoes_por_ficha: 12,
    });
    expect(pedido.fichas).toHaveLength(1);
    const [primeiro, segundo] = pedido.fichas[0].itens;
    expect(primeiro).toMatchObject({ exercicio_id: 1, series: "3", repeticoes: "12", carga: "20kg", pausa: 90, observacao: "devagar" });
    expect(segundo).toMatchObject({ exercicio_id: 2, series: "3", repeticoes: "10" });
  });

  it("exercício que saiu da lista chega marcado, para o professor trocar", () => {
    const treino = treinoDoServidor();
    treino.fichas[0].itens[1].indisponivel = true;

    const estado = estadoDeImportacao(treino);

    expect(estado.fichas[0].itens[1].indisponivel).toBe(true);
    expect(estado.fichas[0].itens[0].indisponivel).toBeUndefined();
  });
});
