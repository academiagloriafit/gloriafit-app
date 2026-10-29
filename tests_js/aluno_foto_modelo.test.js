import { describe, expect, it } from "vitest";
import { descreverEnvioDaFoto, medidasDoEnvio, recorteQuadrado, textoDaSituacao } from "../app/static/aluno_foto_modelo.js";

describe("medidasDoEnvio", () => {
  it("reduz o lado maior para 1280 sem distorcer", () => {
    expect(medidasDoEnvio(4032, 3024)).toEqual({ largura: 1280, altura: 960 });
    expect(medidasDoEnvio(3024, 4032)).toEqual({ largura: 960, altura: 1280 });
  });
  it("não aumenta foto pequena e recusa medida inválida", () => {
    expect(medidasDoEnvio(600, 800)).toEqual({ largura: 600, altura: 800 });
    expect(medidasDoEnvio(0, 800)).toBeNull();
    expect(medidasDoEnvio(NaN, 800)).toBeNull();
  });
});

describe("recorteQuadrado", () => {
  it("foto em pé: quadrado um pouco acima do centro (onde fica o rosto)", () => {
    expect(recorteQuadrado(960, 1280)).toEqual({ x: 0, y: 122, lado: 960 });
  });
  it("foto deitada: quadrado no meio", () => {
    expect(recorteQuadrado(1280, 960)).toEqual({ x: 160, y: 0, lado: 960 });
  });
});

describe("textoDaSituacao", () => {
  it("explica de onde vem a foto", () => {
    expect(textoDaSituacao({ tem_foto: false })).toMatch(/ainda não tem foto/);
    expect(textoDaSituacao({ tem_foto: true, propria: true })).toMatch(/você escolheu/);
    expect(textoDaSituacao({ tem_foto: true, propria: false })).toMatch(/tirada na recepção/);
  });
});

describe("descreverEnvioDaFoto", () => {
  it("ok, sair e os erros", () => {
    expect(descreverEnvioDaFoto(200, { ok: true, propria: true })).toEqual({ tipo: "ok", situacao: { ok: true, propria: true } });
    expect(descreverEnvioDaFoto(401, null)).toEqual({ tipo: "sair" });
    expect(descreverEnvioDaFoto(413, null).texto).toMatch(/grande demais/);
    expect(descreverEnvioDaFoto(429, { erro: "Você já trocou a foto 10 vezes hoje." }).texto).toMatch(/10 vezes/);
    expect(descreverEnvioDaFoto(500, null).texto).toMatch(/Tente de novo/);
  });
});
