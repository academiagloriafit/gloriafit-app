import { describe, expect, it } from "vitest";
import {
  adicionarItem,
  atualizarItem,
  criarEstado,
  estadoDeImportacao,
  lerPosicaoNaFila,
  modoDaTela,
  montarPedido,
  montarPedidoDePadrao,
  nomeDoTreinoDaFila,
  posicaoDoModelo,
  problemaDoNomeDoProfessor,
  sugerirNomeDoTreino,
  textoDaPosicao,
} from "../app/static/treino_modelo.js";
import {
  descreverUsados,
  lerUsados,
  montarPedidoDaFila,
  proximoNumeroLivre,
  validarColocarNaFila,
} from "../app/static/filas_modelo.js";

// Estado com 1 exercício preenchido.
function treinoSimples() {
  let e = adicionarItem(criarEstado(), 0, { id: 1, nome: "SUPINO" });
  e = atualizarItem(e, 0, 1, "series", "3");
  return atualizarItem(e, 0, 1, "repeticoes", "12");
}

// O que GET /api/modelos/<id> devolve para um treino que está numa fila (dados inventados).
function modeloDaFila(mudancas = {}) {
  return {
    nome: "MULHER BASICO",
    sessoes_por_ficha: 12,
    fila_id: 2,
    fila: "Mulher",
    numero: 3,
    fichas: [
      {
        nome: "FICHA A",
        itens: [{ exercicio_id: 1, nome: "SUPINO RETO", series: "3", repeticoes: "12", carga: "", pausa: 60, observacao: "", bloco: null, indisponivel: false }],
      },
    ],
    ...mudancas,
  };
}

describe("modoDaTela: ?fila=ID", () => {
  it("abre o treino padrão da fila", () => {
    expect(modoDaTela("?fila=15")).toEqual({ tipo: "fila", modeloId: 15 });
  });

  it("só aceita número inteiro positivo; o resto vira tela de treino novo", () => {
    for (const ruim of ["0", "-3", "1.5", "abc", "", "007", "99999999999", "1e3", " 4"]) {
      expect(modoDaTela("?fila=" + encodeURIComponent(ruim))).toBeNull();
    }
  });

  it("editar e copiar têm prioridade sobre fila", () => {
    expect(modoDaTela("?fila=9&editar=2")).toEqual({ tipo: "editar", treinoId: 2 });
    expect(modoDaTela("?fila=9&copiar=2")).toEqual({ tipo: "copiar", treinoId: 2 });
  });

  it("fila inválida cai no pedido válido seguinte", () => {
    expect(modoDaTela("?fila=abc&copiar=4")).toEqual({ tipo: "copiar", treinoId: 4 });
  });
});

describe("lerPosicaoNaFila (fila e número do treino padrão)", () => {
  it("os dois vazios = treino padrão solto", () => {
    expect(lerPosicaoNaFila({ filaId: "", numero: "" })).toEqual({ ok: true, filaId: null, numero: null });
    expect(lerPosicaoNaFila()).toEqual({ ok: true, filaId: null, numero: null });
    expect(lerPosicaoNaFila({ filaId: null, numero: undefined })).toEqual({ ok: true, filaId: null, numero: null });
    expect(lerPosicaoNaFila({ filaId: "  ", numero: " " })).toEqual({ ok: true, filaId: null, numero: null });
  });

  it("fila e número juntos", () => {
    expect(lerPosicaoNaFila({ filaId: "2", numero: "3" })).toEqual({ ok: true, filaId: 2, numero: 3 });
    expect(lerPosicaoNaFila({ filaId: 5, numero: 99 })).toEqual({ ok: true, filaId: 5, numero: 99 });
    expect(lerPosicaoNaFila({ filaId: " 2 ", numero: " 07 " })).toEqual({ ok: true, filaId: 2, numero: 7 });
  });

  it("número sem fila: pede a fila", () => {
    const r = lerPosicaoNaFila({ filaId: "", numero: "3" });
    expect(r).toMatchObject({ ok: false, campo: "fila" });
    expect(r.mensagem).toContain("Escolha a fila");
  });

  it("fila sem número: pede o número", () => {
    const r = lerPosicaoNaFila({ filaId: "2", numero: "" });
    expect(r).toMatchObject({ ok: false, campo: "numero" });
    expect(r.mensagem).toContain("número");
  });

  it("número fora de 1 a 99 ou que não é inteiro", () => {
    for (const ruim of ["0", "100", "-1", "1.5", "abc", "1e1", "٣"]) {
      const r = lerPosicaoNaFila({ filaId: "2", numero: ruim });
      expect(r, ruim).toMatchObject({ ok: false, campo: "numero" });
      expect(r.mensagem).toContain("de 1 a 99");
    }
  });

  it("fila que não é um número de verdade", () => {
    for (const ruim of ["abc", "0", "-2", "1.5", "2; DROP"]) {
      expect(lerPosicaoNaFila({ filaId: ruim, numero: "1" }), ruim).toMatchObject({ ok: false, campo: "fila" });
    }
  });
});

describe("pedido do treino padrão com fila", () => {
  const dados = { nomePadrao: "Mulher 3", montadoPor: "Ana" };

  it("leva fila_id e numero como números", () => {
    const pedido = montarPedidoDePadrao(treinoSimples(), { ...dados, filaId: "2", numero: "3" });
    expect(pedido).toMatchObject({ nome: "Mulher 3", fila_id: 2, numero: 3 });
  });

  it("sem fila vão null (treino padrão solto)", () => {
    expect(montarPedidoDePadrao(treinoSimples(), dados)).toMatchObject({ fila_id: null, numero: null });
    expect(montarPedidoDePadrao(treinoSimples(), { ...dados, filaId: "", numero: "" })).toMatchObject({ fila_id: null, numero: null });
  });

  it("posição inválida não vai (quem chama já mostrou o problema)", () => {
    expect(montarPedidoDePadrao(treinoSimples(), { ...dados, filaId: "2", numero: "0" })).toMatchObject({ fila_id: null, numero: null });
  });
});

describe("pedido de salvar com o treino da fila", () => {
  const dados = { nomeTreino: "MULHER TREINO 3", montadoPor: "Carlos", inicio: "2026-10-13" };

  it("leva fila_modelo_id quando o treino foi aberto pela fila", () => {
    expect(montarPedido(treinoSimples(), { ...dados, filaModeloId: 7 })).toMatchObject({ nome_treino: "MULHER TREINO 3", fila_modelo_id: 7 });
  });

  it("sem fila o pedido nem tem a chave", () => {
    expect(montarPedido(treinoSimples(), dados)).not.toHaveProperty("fila_modelo_id");
    expect(montarPedido(treinoSimples(), { ...dados, filaModeloId: null })).not.toHaveProperty("fila_modelo_id");
  });

  it("id que não é inteiro positivo não vai", () => {
    for (const ruim of [0, -1, 1.5, "7", true, NaN]) {
      expect(montarPedido(treinoSimples(), { ...dados, filaModeloId: ruim }), String(ruim)).not.toHaveProperty("fila_modelo_id");
    }
  });
});

describe("o treino padrão aberto pela fila", () => {
  it("posicaoDoModelo: nome da fila e número", () => {
    expect(posicaoDoModelo(modeloDaFila())).toEqual({ fila: "Mulher", numero: 3 });
    expect(textoDaPosicao({ fila: "Mulher", numero: 3 })).toBe("Mulher · Treino 3");
  });

  it("padrão solto ou resposta fora do formato não é treino da fila", () => {
    expect(posicaoDoModelo(modeloDaFila({ fila_id: null, fila: null, numero: null }))).toBeNull();
    expect(posicaoDoModelo(modeloDaFila({ numero: 0 }))).toBeNull();
    expect(posicaoDoModelo(modeloDaFila({ numero: 100 }))).toBeNull();
    expect(posicaoDoModelo(modeloDaFila({ fila: "  " }))).toBeNull();
    expect(posicaoDoModelo(modeloDaFila({ fila: 5 }))).toBeNull();
    for (const ruim of [null, undefined, "texto", 5]) expect(posicaoDoModelo(ruim)).toBeNull();
  });

  it("os exercícios do padrão entram na tela como treino novo", () => {
    const estado = estadoDeImportacao(modeloDaFila());
    expect(estado.fichas).toHaveLength(1);
    expect(estado.fichas[0].itens[0]).toMatchObject({ exercicioId: 1, series: "3", repeticoes: "12", pausaMin: "1", pausaSeg: "00" });
  });
});

describe("nomeDoTreinoDaFila", () => {
  it("fila em maiúsculas, número e data", () => {
    expect(nomeDoTreinoDaFila("Mulher", 3, "13/10/26")).toBe("MULHER TREINO 3 13/10/26");
    expect(nomeDoTreinoDaFila("Grupos de risco", 12, "13/10/26")).toBe("GRUPOS DE RISCO TREINO 12 13/10/26");
  });

  it("sem data fica sem sufixo", () => {
    expect(nomeDoTreinoDaFila("Homem", 1, "")).toBe("HOMEM TREINO 1");
  });

  it("nunca passa de 40 letras e preserva a data", () => {
    const nome = nomeDoTreinoDaFila("A".repeat(60), 7, "13/10/26");
    expect([...nome].length).toBeLessThanOrEqual(40);
    expect(nome.endsWith(" 13/10/26")).toBe(true);
  });

  it("espaços e acentos", () => {
    expect(nomeDoTreinoDaFila("  Gestante ", 2, "13/10/26")).toBe("GESTANTE TREINO 2 13/10/26");
    expect(nomeDoTreinoDaFila("Adolescênte", 2, "13/10/26")).toBe("ADOLESCÊNTE TREINO 2 13/10/26");
  });

  it("o nome sugerido de sempre continua igual depois da refatoração", () => {
    let e = adicionarItem(criarEstado(), 0, { id: 1, nome: "X" });
    expect(sugerirNomeDoTreino(e, "07/10/26")).toBe("TREINO A 07/10/26");
    expect(sugerirNomeDoTreino(criarEstado(), "")).toBe("TREINO A");
  });
});

describe("problemaDoNomeDoProfessor", () => {
  it("nome certo = null", () => {
    expect(problemaDoNomeDoProfessor("Ana Paula", "vazio")).toBeNull();
  });
  it("vazio, grande demais ou com caractere invisível", () => {
    expect(problemaDoNomeDoProfessor("   ", "Digite o nome.")).toBe("Digite o nome.");
    expect(problemaDoNomeDoProfessor("X".repeat(61), "v")).toContain("máximo é 60");
    expect(problemaDoNomeDoProfessor("Ana\u0000", "v")).toContain("caracteres inválidos");
    expect(problemaDoNomeDoProfessor("Ana​", "v")).toContain("caracteres inválidos");
  });
});

describe("filas_modelo: números já usados", () => {
  it("lerUsados lê '1,2,4' e ignora lixo", () => {
    expect(lerUsados("1,2,4")).toEqual([1, 2, 4]);
    expect(lerUsados(" 3 , 1 ,3")).toEqual([1, 3]);
    expect(lerUsados("")).toEqual([]);
    expect(lerUsados(undefined)).toEqual([]);
    expect(lerUsados("0,100,abc,-1,1.5,2")).toEqual([2]);
  });

  it("proximoNumeroLivre: o seguinte ao maior", () => {
    expect(proximoNumeroLivre([])).toBe(1);
    expect(proximoNumeroLivre([1, 2, 3])).toBe(4);
    expect(proximoNumeroLivre([1, 2, 4])).toBe(5);
    expect(proximoNumeroLivre([3])).toBe(4);
  });

  it("proximoNumeroLivre: na ponta, o primeiro buraco; sem número livre, null", () => {
    expect(proximoNumeroLivre([1, 3, 99])).toBe(2);
    const todos = Array.from({ length: 99 }, (_, i) => i + 1);
    expect(proximoNumeroLivre(todos)).toBeNull();
  });

  it("descreverUsados", () => {
    expect(descreverUsados([])).toBe("Esta fila ainda não tem nenhum treino.");
    expect(descreverUsados([1, 2])).toBe("Já existem nesta fila: Treino 1, Treino 2.");
  });
});

describe("validarColocarNaFila", () => {
  const base = { filaId: "2", professor: "Bia", exigeLiberacao: false, conferida: false, liberacaoEm: "", hoje: "2026-10-13" };
  const campos = (dados) => validarColocarNaFila(dados).map((p) => p.campo);

  it("fila comum: só fila e professor", () => {
    expect(validarColocarNaFila(base)).toEqual([]);
  });

  it("sem fila ou sem professor", () => {
    expect(campos({ ...base, filaId: "" })).toEqual(["fila-escolhida"]);
    expect(campos({ ...base, professor: "  " })).toEqual(["fila-professor"]);
    expect(campos({ ...base, filaId: "", professor: "" })).toEqual(["fila-escolhida", "fila-professor"]);
  });

  it("a data e a caixa da liberação são ignoradas nas filas que não pedem liberação", () => {
    expect(validarColocarNaFila({ ...base, conferida: false, liberacaoEm: "lixo" })).toEqual([]);
  });

  describe("fila que pede liberação (Gestante, Grupos de risco)", () => {
    const risco = { ...base, filaId: "5", exigeLiberacao: true, conferida: true, liberacaoEm: "2026-10-13" };

    it("tudo certo", () => {
      expect(validarColocarNaFila(risco)).toEqual([]);
      expect(validarColocarNaFila({ ...risco, liberacaoEm: "2026-10-01" })).toEqual([]);
    });

    it("sem marcar que conferiu", () => {
      const p = validarColocarNaFila({ ...risco, conferida: false });
      expect(p.map((x) => x.campo)).toEqual(["fila-liberacao-conferida"]);
      expect(p[0].mensagem).toContain("liberação conferida");
    });

    it("só 'true' de verdade vale como conferido", () => {
      for (const ruim of ["true", 1, "sim", null, undefined]) {
        expect(campos({ ...risco, conferida: ruim }), String(ruim)).toEqual(["fila-liberacao-conferida"]);
      }
    });

    it("data em branco, inválida ou no futuro", () => {
      expect(campos({ ...risco, liberacaoEm: "" })).toEqual(["fila-liberacao-em"]);
      expect(campos({ ...risco, liberacaoEm: "2026-02-30" })).toEqual(["fila-liberacao-em"]);
      expect(campos({ ...risco, liberacaoEm: "13/10/2026" })).toEqual(["fila-liberacao-em"]);
      const futuro = validarColocarNaFila({ ...risco, liberacaoEm: "2026-10-14" });
      expect(futuro.map((x) => x.campo)).toEqual(["fila-liberacao-em"]);
      expect(futuro[0].mensagem).toContain("futuro");
    });

    it("os problemas vêm todos juntos, na ordem da tela", () => {
      expect(campos({ ...risco, filaId: "", professor: "", conferida: false, liberacaoEm: "" })).toEqual([
        "fila-escolhida",
        "fila-professor",
        "fila-liberacao-conferida",
        "fila-liberacao-em",
      ]);
    });
  });
});

describe("montarPedidoDaFila", () => {
  it("fila comum: só fila_id e professor (sem liberação)", () => {
    expect(montarPedidoDaFila({ filaId: "2", professor: "  Bia   Souza " })).toEqual({ fila_id: 2, professor: "Bia Souza" });
    expect(montarPedidoDaFila({ filaId: "2", professor: "Bia", conferida: true, liberacaoEm: "2026-10-13" })).not.toHaveProperty("liberacao_conferida");
  });

  it("fila com liberação: sim + data", () => {
    expect(montarPedidoDaFila({ filaId: "4", professor: "Bia", exigeLiberacao: true, conferida: true, liberacaoEm: "2026-10-01" })).toEqual({
      fila_id: 4,
      professor: "Bia",
      liberacao_conferida: true,
      liberacao_em: "2026-10-01",
    });
  });

  it("liberação não marcada vai false (o servidor recusa)", () => {
    expect(montarPedidoDaFila({ filaId: "4", professor: "Bia", exigeLiberacao: true, conferida: false, liberacaoEm: "2026-10-01" })).toMatchObject({
      liberacao_conferida: false,
    });
  });
});
