import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MENSAGEM_NAO_AUTORIZADO, TEMPO_MAXIMO_MS, buscarJson, enviarJson, textoDoErro } from "../app/static/api.js";

function resposta(status, corpoTexto) {
  return { status, json: async () => JSON.parse(corpoTexto) };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("enviarJson", () => {
  it("manda POST com o corpo em JSON e o tipo certo", async () => {
    const fetchFalso = vi.fn().mockResolvedValue(resposta(201, '{"id": 7}'));
    vi.stubGlobal("fetch", fetchFalso);

    const r = await enviarJson("/api/alunos/1/treinos", { nome: "Ana", n: 1 });

    expect(r).toEqual({ status: 201, corpo: { id: 7 } });
    const [url, opcoes] = fetchFalso.mock.calls[0];
    expect(url).toBe("/api/alunos/1/treinos");
    expect(opcoes.method).toBe("POST");
    expect(opcoes.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(opcoes.body)).toEqual({ nome: "Ana", n: 1 });
    expect(opcoes.credentials).toBe("same-origin");
  });

  it("devolve o status e o corpo também nos erros do servidor", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(resposta(400, '{"erros": ["faltou algo"]}')));

    expect(await enviarJson("/x", {})).toEqual({ status: 400, corpo: { erros: ["faltou algo"] } });
  });

  it("resposta que não é JSON (página de erro) vira corpo null, sem quebrar", async () => {
    const naoJson = { status: 500, json: async () => { throw new SyntaxError("Unexpected token <"); } };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(naoJson));

    expect(await enviarJson("/x", {})).toEqual({ status: 500, corpo: null });
  });

  it("se a rede cair, rejeita (quem chama precisa avisar que não sabe se gravou)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(enviarJson("/x", {})).rejects.toThrow("Failed to fetch");
  });

  it("se o servidor não responder a tempo, cancela o pedido e rejeita", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((_url, opcoes) =>
        new Promise((_ok, falha) => {
          opcoes.signal.addEventListener("abort", () => falha(new DOMException("aborted", "AbortError")));
        }),
      ),
    );

    const pedido = enviarJson("/x", {});
    const verificacao = expect(pedido).rejects.toThrow("aborted");
    await vi.advanceTimersByTimeAsync(TEMPO_MAXIMO_MS + 1);
    await verificacao;
  });

  it("não cancela antes do tempo", async () => {
    let cancelado = false;
    vi.stubGlobal(
      "fetch",
      vi.fn((_url, opcoes) =>
        new Promise((ok, falha) => {
          opcoes.signal.addEventListener("abort", () => {
            cancelado = true;
            falha(new DOMException("aborted", "AbortError"));
          });
          setTimeout(() => ok(resposta(200, "{}")), TEMPO_MAXIMO_MS - 1000);
        }),
      ),
    );

    const pedido = enviarJson("/x", {});
    await vi.advanceTimersByTimeAsync(TEMPO_MAXIMO_MS - 500);

    expect(await pedido).toEqual({ status: 200, corpo: {} });
    expect(cancelado).toBe(false);
  });

  it("depois de responder, o relógio é desligado (nada é cancelado depois)", async () => {
    let sinal;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url, opcoes) => {
        sinal = opcoes.signal;
        return resposta(200, "{}");
      }),
    );

    await enviarJson("/x", {});
    await vi.advanceTimersByTimeAsync(TEMPO_MAXIMO_MS * 2);

    expect(sinal.aborted).toBe(false);
  });

  it("o tempo máximo é de 20 segundos", () => {
    expect(TEMPO_MAXIMO_MS).toBe(20000);
  });
});

describe("buscarJson", () => {
  it("faz GET com o cookie do site e devolve status e corpo", async () => {
    const fetchFalso = vi.fn().mockResolvedValue(resposta(200, '{"modelos": []}'));
    vi.stubGlobal("fetch", fetchFalso);

    const r = await buscarJson("/api/modelos");

    expect(r).toEqual({ status: 200, corpo: { modelos: [] } });
    const [url, opcoes] = fetchFalso.mock.calls[0];
    expect(url).toBe("/api/modelos");
    expect(opcoes.method).toBeUndefined(); // GET
    expect(opcoes.credentials).toBe("same-origin");
  });

  it("devolve o status também nos erros, e corpo null se não for JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(resposta(404, '{"erro": "Aluno não encontrado."}')));
    expect(await buscarJson("/x")).toEqual({ status: 404, corpo: { erro: "Aluno não encontrado." } });

    const naoJson = { status: 502, json: async () => { throw new SyntaxError("Unexpected token <"); } };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(naoJson));
    expect(await buscarJson("/x")).toEqual({ status: 502, corpo: null });
  });

  it("se a rede cair, rejeita", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(buscarJson("/x")).rejects.toThrow("Failed to fetch");
  });

  it("quem pediu pode cancelar a busca antiga", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((_url, opcoes) =>
        new Promise((_ok, falha) => {
          opcoes.signal.addEventListener("abort", () => falha(new DOMException("aborted", "AbortError")));
        }),
      ),
    );
    const cancelador = new AbortController();

    const busca = buscarJson("/x", cancelador.signal);
    const verificacao = expect(busca).rejects.toThrow("aborted");
    cancelador.abort();

    await verificacao;
  });

  it("sinal já cancelado nem chega a esperar a rede", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((_url, opcoes) =>
        opcoes.signal.aborted
          ? Promise.reject(new DOMException("aborted", "AbortError"))
          : new Promise(() => {}),
      ),
    );
    const cancelador = new AbortController();
    cancelador.abort();

    await expect(buscarJson("/x", cancelador.signal)).rejects.toThrow("aborted");
  });

  it("se o servidor não responder a tempo, cancela e rejeita", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((_url, opcoes) =>
        new Promise((_ok, falha) => {
          opcoes.signal.addEventListener("abort", () => falha(new DOMException("aborted", "AbortError")));
        }),
      ),
    );

    const busca = buscarJson("/x");
    const verificacao = expect(busca).rejects.toThrow("aborted");
    await vi.advanceTimersByTimeAsync(TEMPO_MAXIMO_MS + 1);
    await verificacao;
  });
});

describe("textoDoErro", () => {
  it("401 pede um código novo", () => {
    expect(textoDoErro({ status: 401, corpo: { erro: "qualquer" } }, "falhou")).toBe(MENSAGEM_NAO_AUTORIZADO);
  });

  it("junta as mensagens da lista `erros`", () => {
    expect(textoDoErro({ status: 400, corpo: { erros: ["Primeiro.", "Segundo."] } }, "falhou")).toBe("Primeiro. Segundo.");
  });

  it("ignora o que não é texto na lista e cai no `erro` ou na frase padrão", () => {
    expect(textoDoErro({ status: 400, corpo: { erros: [1, null], erro: "Um só." } }, "falhou")).toBe("Um só.");
    expect(textoDoErro({ status: 500, corpo: { erros: [] } }, "O servidor falhou")).toBe("O servidor falhou (código 500).");
  });

  it("resposta que não é JSON usa a frase padrão com o código", () => {
    expect(textoDoErro({ status: 502, corpo: null }, "O servidor não respondeu")).toBe("O servidor não respondeu (código 502).");
  });
});
