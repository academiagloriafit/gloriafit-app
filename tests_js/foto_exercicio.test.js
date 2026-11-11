import { describe, expect, it } from "vitest";
import { caminhoDaMiniatura, lerMapaDeFotos } from "../app/static/foto_exercicio.js";

describe("caminhoDaMiniatura", () => {
  it("monta o endereço da foto inicial", () => {
    expect(caminhoDaMiniatura("/static/exercicios/", "Barbell_Squat")).toBe("/static/exercicios/Barbell_Squat_0.jpg");
  });
  it("sem foto ou nome estranho: null (nunca vira caminho para outra pasta)", () => {
    expect(caminhoDaMiniatura("/static/exercicios/", null)).toBeNull();
    expect(caminhoDaMiniatura("/static/exercicios/", "")).toBeNull();
    expect(caminhoDaMiniatura("/static/exercicios/", "../segredo")).toBeNull();
    expect(caminhoDaMiniatura("/static/exercicios/", "a b")).toBeNull();
    expect(caminhoDaMiniatura("/static/exercicios/", "x".repeat(81))).toBeNull();
    expect(caminhoDaMiniatura(undefined, "Barbell_Squat")).toBeNull();
  });
});

describe("lerMapaDeFotos", () => {
  it("lê o mapa da página", () => {
    expect(lerMapaDeFotos('{"7": "Butterfly"}')).toEqual({ 7: "Butterfly" });
  });
  it("texto vazio, quebrado ou lista: mapa vazio", () => {
    expect(lerMapaDeFotos("")).toEqual({});
    expect(lerMapaDeFotos("{quebrado")).toEqual({});
    expect(lerMapaDeFotos("[1,2]")).toEqual({});
    expect(lerMapaDeFotos("null")).toEqual({});
  });
});
