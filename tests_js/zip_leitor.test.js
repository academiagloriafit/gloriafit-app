import { crc32, deflateRawSync } from "node:zlib";
import { describe, expect, it } from "vitest";
import { ZipInvalido, lerEntrada, listarEntradas } from "../app/static/zip_leitor.js";

// ---- monta um .zip de verdade (o mesmo formato do base_total.zip) só para os testes ----

function u16(n) {
  const b = Buffer.alloc(2);
  b.writeUInt16LE(n);
  return b;
}
function u32(n) {
  const b = Buffer.alloc(4);
  b.writeUInt32LE(n >>> 0);
  return b;
}

// entradas: [{ nome, conteudo (Buffer), metodo: 8|0, bits?: number }]
function montarZip(entradas, { comentario = "" } = {}) {
  const partes = [];
  const central = [];
  let posicao = 0;
  for (const e of entradas) {
    const nome = Buffer.from(e.nome, "utf-8");
    const original = Buffer.from(e.conteudo);
    const dados = e.metodo === 0 ? original : deflateRawSync(original);
    const bits = e.bits ?? 0;
    const local = Buffer.concat([
      u32(0x04034b50), u16(20), u16(bits), u16(e.metodo), u16(0), u16(0),
      u32(crc32(original)), u32(dados.length), u32(original.length),
      u16(nome.length), u16(0), nome, dados,
    ]);
    central.push(
      Buffer.concat([
        u32(0x02014b50), u16(20), u16(20), u16(bits), u16(e.metodo), u16(0), u16(0),
        u32(crc32(original)), u32(dados.length), u32(original.length),
        u16(nome.length), u16(0), u16(0), u16(0), u16(0), u32(0), u32(posicao), nome,
      ]),
    );
    partes.push(local);
    posicao += local.length;
  }
  const indice = Buffer.concat(central);
  const textoComentario = Buffer.from(comentario, "utf-8");
  const fim = Buffer.concat([
    u32(0x06054b50), u16(0), u16(0), u16(entradas.length), u16(entradas.length),
    u32(indice.length), u32(posicao), u16(textoComentario.length), textoComentario,
  ]);
  return new Uint8Array(Buffer.concat([...partes, indice, fim]));
}

const LIMITE = 10 * 1024 * 1024;
const texto = (bytes) => new TextDecoder().decode(bytes);

describe("listarEntradas", () => {
  it("lista as entradas pelo nome", () => {
    const zip = montarZip([
      { nome: "PESSOA.jsonl", conteudo: "a", metodo: 8 },
      { nome: "_manifesto.json", conteudo: "{}", metodo: 0 },
    ]);

    const entradas = listarEntradas(zip);

    expect([...entradas.keys()]).toEqual(["PESSOA.jsonl", "_manifesto.json"]);
    expect(entradas.get("PESSOA.jsonl").metodo).toBe(8);
    expect(entradas.get("_manifesto.json").metodo).toBe(0);
  });

  it("acha o índice mesmo com comentário no fim do arquivo", () => {
    const zip = montarZip([{ nome: "a.txt", conteudo: "oi", metodo: 8 }], { comentario: "x".repeat(500) });

    expect([...listarEntradas(zip).keys()]).toEqual(["a.txt"]);
  });

  it("lê nomes com acento (UTF-8)", () => {
    const zip = montarZip([{ nome: "relatório.txt", conteudo: "oi", metodo: 8 }]);

    expect(listarEntradas(zip).has("relatório.txt")).toBe(true);
  });

  it("zip sem nenhuma entrada é um índice vazio", () => {
    expect(listarEntradas(montarZip([])).size).toBe(0);
  });

  it.each([
    ["arquivo vazio", new Uint8Array(0)],
    ["arquivo pequeno demais", new Uint8Array(10)],
    ["texto qualquer", new TextEncoder().encode("isto não é um zip, é só uma frase comprida o bastante")],
  ])("%s não é zip", (_nome, bytes) => {
    expect(() => listarEntradas(bytes)).toThrow(ZipInvalido);
    expect(() => listarEntradas(bytes)).toThrow(/não parece ser um \.zip/);
  });

  it("zip cortado no meio é recusado", () => {
    const zip = montarZip([{ nome: "a.txt", conteudo: "x".repeat(2000), metodo: 8 }]);

    expect(() => listarEntradas(zip.slice(0, zip.length - 30))).toThrow(ZipInvalido);
  });

  it("índice que aponta para fora do arquivo é recusado", () => {
    const zip = montarZip([{ nome: "a.txt", conteudo: "oi", metodo: 8 }]);
    const fim = zip.length - 22;
    new DataView(zip.buffer).setUint32(fim + 16, zip.length + 1000, true);

    expect(() => listarEntradas(zip)).toThrow(/índice do \.zip está danificado/);
  });

  it("ZIP64 é recusado com mensagem clara", () => {
    const zip = montarZip([{ nome: "a.txt", conteudo: "oi", metodo: 8 }]);
    new DataView(zip.buffer).setUint16(zip.length - 22 + 10, 0xffff, true);

    expect(() => listarEntradas(zip)).toThrow(/ZIP64/);
  });
});

describe("lerEntrada", () => {
  it("descompacta uma entrada comprimida (deflate)", async () => {
    const conteudo = "linha 1\nlinha 2 com acento: coração\n".repeat(50);
    const zip = montarZip([{ nome: "T.jsonl", conteudo, metodo: 8 }]);

    const bytes = await lerEntrada(zip, listarEntradas(zip), "T.jsonl", LIMITE);

    expect(texto(bytes)).toBe(conteudo);
  });

  it("devolve uma entrada sem compressão como está", async () => {
    const zip = montarZip([{ nome: "_manifesto.json", conteudo: '{"a":1}', metodo: 0 }]);

    const bytes = await lerEntrada(zip, listarEntradas(zip), "_manifesto.json", LIMITE);

    expect(texto(bytes)).toBe('{"a":1}');
  });

  it("lê só a entrada pedida, mesmo com outras quebradas", async () => {
    const zip = montarZip([
      { nome: "BOA.txt", conteudo: "boa", metodo: 8 },
      { nome: "OUTRA.txt", conteudo: "outra", metodo: 8 },
    ]);
    const entradas = listarEntradas(zip);
    // estraga os bytes comprimidos da outra: ler a "BOA" não pode tocar nela
    const outra = entradas.get("OUTRA.txt");
    const inicio = outra.posicaoLocal + 30 + "OUTRA.txt".length;
    zip.fill(0xff, inicio, inicio + outra.tamanhoComprimido);

    expect(texto(await lerEntrada(zip, entradas, "BOA.txt", LIMITE))).toBe("boa");
  });

  it("entrada vazia (tabela sem linhas) funciona", async () => {
    const zip = montarZip([{ nome: "VAZIA.jsonl", conteudo: "", metodo: 8 }]);

    const bytes = await lerEntrada(zip, listarEntradas(zip), "VAZIA.jsonl", LIMITE);

    expect(bytes.length).toBe(0);
  });

  it("entrada que não existe diz o nome", async () => {
    const zip = montarZip([{ nome: "A.txt", conteudo: "a", metodo: 8 }]);

    await expect(lerEntrada(zip, listarEntradas(zip), "PESSOA.jsonl", LIMITE)).rejects.toThrow(
      /Não achei PESSOA\.jsonl/,
    );
  });

  it("entrada com senha é recusada", async () => {
    const zip = montarZip([{ nome: "A.txt", conteudo: "a", metodo: 8, bits: 1 }]);

    await expect(lerEntrada(zip, listarEntradas(zip), "A.txt", LIMITE)).rejects.toThrow(/senha/);
  });

  it("compressão desconhecida é recusada", async () => {
    const zip = montarZip([{ nome: "A.txt", conteudo: "a", metodo: 8 }]);
    const entradas = listarEntradas(zip);
    entradas.get("A.txt").metodo = 14; // LZMA

    await expect(lerEntrada(zip, entradas, "A.txt", LIMITE)).rejects.toThrow(/compressão que a tela não lê/);
  });

  it("recusa entrada que diz ser maior que o limite, sem descompactar", async () => {
    const zip = montarZip([{ nome: "A.txt", conteudo: "x".repeat(5000), metodo: 8 }]);

    await expect(lerEntrada(zip, listarEntradas(zip), "A.txt", 1000)).rejects.toThrow(/grande demais/);
  });

  it("recusa 'bomba de zip': entrada que mente o tamanho e cresce além do limite", async () => {
    const zip = montarZip([{ nome: "A.txt", conteudo: "x".repeat(200_000), metodo: 8 }]);
    const entradas = listarEntradas(zip);
    entradas.get("A.txt").tamanhoOriginal = 10; // mente: diz que é pequena

    await expect(lerEntrada(zip, entradas, "A.txt", 1000)).rejects.toThrow(/grande demais/);
  });

  it("tamanho diferente do declarado vira arquivo danificado", async () => {
    const zip = montarZip([{ nome: "A.txt", conteudo: "x".repeat(100), metodo: 8 }]);
    const entradas = listarEntradas(zip);
    entradas.get("A.txt").tamanhoOriginal = 99;

    await expect(lerEntrada(zip, entradas, "A.txt", LIMITE)).rejects.toThrow(/tamanho diferente/);
  });

  it("bytes comprimidos estragados viram arquivo danificado, não erro solto", async () => {
    const zip = montarZip([{ nome: "A.txt", conteudo: "texto qualquer ".repeat(100), metodo: 8 }]);
    const entradas = listarEntradas(zip);
    const e = entradas.get("A.txt");
    const inicio = e.posicaoLocal + 30 + "A.txt".length;
    zip.fill(0xff, inicio, inicio + e.tamanhoComprimido);

    await expect(lerEntrada(zip, entradas, "A.txt", LIMITE)).rejects.toThrow(ZipInvalido);
  });

  it("cabeçalho local danificado é recusado", async () => {
    const zip = montarZip([{ nome: "A.txt", conteudo: "oi", metodo: 8 }]);
    const entradas = listarEntradas(zip);
    zip[0] = 0; // estraga a assinatura do cabeçalho local

    await expect(lerEntrada(zip, entradas, "A.txt", LIMITE)).rejects.toThrow(/índice do \.zip está danificado/);
  });

  it("dados que passam do fim do arquivo (zip cortado) são recusados", async () => {
    const zip = montarZip([{ nome: "A.txt", conteudo: "oi", metodo: 0 }]);
    const entradas = listarEntradas(zip);
    entradas.get("A.txt").tamanhoComprimido = 5000;

    await expect(lerEntrada(zip, entradas, "A.txt", LIMITE)).rejects.toThrow(/cortado/);
  });
});
