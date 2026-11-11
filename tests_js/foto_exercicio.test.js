import { describe, expect, it } from "vitest";
import { caminhoDaMiniatura, lerMapaDeFotos } from "../app/static/foto_exercicio.js";

describe("caminhoDaMiniatura", () => {
  it("monta o endereço da ilustração ou da foto", () => {
    expect(caminhoDaMiniatura("/static/", "ilustracoes/Barbell_Squat.jpg")).toBe("/static/ilustracoes/Barbell_Squat.jpg");
    expect(caminhoDaMiniatura("/static/", "exercicios/Barbell_Squat_0.jpg")).toBe("/static/exercicios/Barbell_Squat_0.jpg");
  });
  it("sem imagem ou caminho estranho: null (nunca vira endereço de outra pasta)", () => {
    expect(caminhoDaMiniatura("/static/", null)).toBeNull();
    expect(caminhoDaMiniatura("/static/", "")).toBeNull();
    expect(caminhoDaMiniatura("/static/", "ilustracoes/../segredo.jpg")).toBeNull();
    expect(caminhoDaMiniatura("/static/", "outra/Barbell_Squat.jpg")).toBeNull();
    expect(caminhoDaMiniatura("/static/", "ilustracoes/Barbell_Squat.svg")).toBeNull();
    expect(caminhoDaMiniatura("/static/", "https://x.com/a.jpg")).toBeNull();
    expect(caminhoDaMiniatura(undefined, "ilustracoes/Barbell_Squat.jpg")).toBeNull();
  });
});

describe("lerMapaDeFotos", () => {
  it("lê o mapa da página", () => {
    expect(lerMapaDeFotos('{"7": "ilustracoes/Butterfly.jpg"}')).toEqual({ 7: "ilustracoes/Butterfly.jpg" });
  });
  it("texto vazio, quebrado ou lista: mapa vazio", () => {
    expect(lerMapaDeFotos("")).toEqual({});
    expect(lerMapaDeFotos("{quebrado")).toEqual({});
    expect(lerMapaDeFotos("[1,2]")).toEqual({});
    expect(lerMapaDeFotos("null")).toEqual({});
  });
});
