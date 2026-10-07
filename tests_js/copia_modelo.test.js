import { describe, expect, it } from "vitest";
import {
  ARQUIVOS_NECESSARIOS,
  COLUNAS_ENVIADAS,
  CopiaInvalida,
  HORAS_ATE_AVISAR,
  MENSAGEM_SEM_REDE,
  TIPO_CONTATO_CELULAR,
  dataDaExtracao,
  descreverCopia,
  idadeEmHoras,
  interpretarResposta,
  montarPacote,
} from "../app/static/copia_modelo.js";

// ---- cópia de teste (dados inventados) ----

const jsonl = (linhas) => new TextEncoder().encode(linhas.map((l) => JSON.stringify(l)).join("\n") + "\n");
const json = (valor) => new TextEncoder().encode(JSON.stringify(valor));

// Colunas "de verdade" têm muito mais do que o app usa: o teste confere que o resto não sai.
const COLUNAS_REAIS = {
  PESSOA: ["ID", "CD_PESSOA", "NM_PESSOA", "TP_PESSOA", "NR_CPF", "NR_RG", "DT_NASCIMENTO", "DS_EMAIL", "SENHA_APP", "ST_DELETED"],
  PESSOA_STATUS: ["ID_PESSOA", "DT_INI_STATUS", "DT_FIM_STATUS", "CD_STATUS", "VL_MENSALIDADE"],
  CONTATO_PESSOA: ["ID_CONTATO", "ID_PESSOA", "ID_TIPO_CONTATO", "DS_CONTATO", "ST_PRINCIPAL"],
};

function pessoa(id, nome, cpf = "11144477735") {
  return {
    ID: id, CD_PESSOA: id, NM_PESSOA: nome, TP_PESSOA: "F", NR_CPF: cpf,
    NR_RG: "9999999", DT_NASCIMENTO: "1990-01-01", DS_EMAIL: "segredo@exemplo.test", SENHA_APP: "hash-secreto", ST_DELETED: "F",
  };
}

function copia({ pessoas, periodos, contatos, extracao = "07/10/2026 05:00:17", manifesto } = {}) {
  pessoas ??= [pessoa(101, "ANA FICTICIA"), pessoa(102, "BRUNO FICTICIO", 52998224725)];
  periodos ??= [
    { ID_PESSOA: 101, DT_INI_STATUS: "2026-01-01", DT_FIM_STATUS: "2026-12-31", CD_STATUS: "A", VL_MENSALIDADE: 99 },
    { ID_PESSOA: 102, DT_INI_STATUS: "2026-01-01", DT_FIM_STATUS: "7777-07-07", CD_STATUS: "D", VL_MENSALIDADE: 0 },
  ];
  contatos ??= [
    { ID_CONTATO: 1, ID_PESSOA: 101, ID_TIPO_CONTATO: 30, DS_CONTATO: "27988887766", ST_PRINCIPAL: "T" },
    { ID_CONTATO: 2, ID_PESSOA: 101, ID_TIPO_CONTATO: 10, DS_CONTATO: "2733334444", ST_PRINCIPAL: "F" },
    { ID_CONTATO: 3, ID_PESSOA: 101, ID_TIPO_CONTATO: 20, DS_CONTATO: "ana@exemplo.test", ST_PRINCIPAL: "F" },
  ];
  manifesto ??= {
    extracao,
    tabelas: {
      PESSOA: { linhas: pessoas.length, colunas: COLUNAS_REAIS.PESSOA },
      PESSOA_STATUS: { linhas: periodos.length, colunas: COLUNAS_REAIS.PESSOA_STATUS },
      CONTATO_PESSOA: { linhas: contatos.length, colunas: COLUNAS_REAIS.CONTATO_PESSOA },
    },
  };
  return {
    "_manifesto.json": json(manifesto),
    "PESSOA.jsonl": jsonl(pessoas),
    "PESSOA_STATUS.jsonl": jsonl(periodos),
    "CONTATO_PESSOA.jsonl": jsonl(contatos),
  };
}

describe("o que a tela precisa abrir do .zip", () => {
  it("só o manifesto e as 3 tabelas usadas (de 258)", () => {
    expect(ARQUIVOS_NECESSARIOS).toEqual(["_manifesto.json", "PESSOA.jsonl", "PESSOA_STATUS.jsonl", "CONTATO_PESSOA.jsonl"]);
  });
});

describe("montarPacote: o que sai do computador", () => {
  it("monta o pacote com a data da cópia e as 3 tabelas", () => {
    const { pacote, resumo } = montarPacote(copia());

    expect(pacote.extracao).toBe("07/10/2026 05:00:17");
    expect(Object.keys(pacote.tabelas)).toEqual(["PESSOA", "PESSOA_STATUS", "CONTATO_PESSOA"]);
    expect(resumo).toEqual({ extracao: "07/10/2026 05:00:17", linhas: { PESSOA: 2, PESSOA_STATUS: 2, CONTATO_PESSOA: 3 } });
  });

  it("envia SÓ as colunas que o app usa (nada de RG, nascimento, e-mail, senha, valores)", () => {
    const { pacote } = montarPacote(copia());

    for (const tabela of Object.keys(COLUNAS_ENVIADAS)) {
      expect(pacote.tabelas[tabela].colunas).toEqual(COLUNAS_ENVIADAS[tabela]);
      for (const linha of pacote.tabelas[tabela].linhas) expect(linha).toHaveLength(COLUNAS_ENVIADAS[tabela].length);
    }
    const enviado = JSON.stringify(pacote);
    for (const proibido of ["9999999", "1990-01-01", "segredo@exemplo.test", "hash-secreto", "ana@exemplo.test", "2733334444", "VL_MENSALIDADE"]) {
      expect(enviado).not.toContain(proibido);
    }
  });

  it("as colunas vão na mesma ordem dos valores", () => {
    const { pacote } = montarPacote(copia());

    expect(pacote.tabelas.PESSOA.linhas[0]).toEqual([101, "ANA FICTICIA", "F", "11144477735", "F"]);
    expect(pacote.tabelas.PESSOA_STATUS.linhas[1]).toEqual([102, "2026-01-01", "7777-07-07", "D"]);
  });

  it("de contatos só vai o celular (tipo 30): telefone fixo e e-mail ficam", () => {
    const { pacote, resumo } = montarPacote(copia());

    expect(TIPO_CONTATO_CELULAR).toBe(30);
    expect(pacote.tabelas.CONTATO_PESSOA.linhas).toEqual([[1, 101, 30, "27988887766"]]);
    expect(resumo.linhas.CONTATO_PESSOA).toBe(3); // o resumo conta o que veio no arquivo
  });

  it("CPF e telefone guardados como número no Data4U viram texto", () => {
    const { pacote } = montarPacote(
      copia({
        contatos: [{ ID_CONTATO: 1, ID_PESSOA: 102, ID_TIPO_CONTATO: 30, DS_CONTATO: 27977776666 }],
      }),
    );

    expect(pacote.tabelas.PESSOA.linhas[1][3]).toBe("52998224725"); // veio como número no arquivo
    expect(pacote.tabelas.CONTATO_PESSOA.linhas[0][3]).toBe("27977776666");
  });

  it("valores vazios continuam vazios (não viram o texto 'null')", () => {
    const { pacote } = montarPacote(copia({ pessoas: [{ ...pessoa(101, "ANA FICTICIA"), NR_CPF: null }] }));

    expect(pacote.tabelas.PESSOA.linhas[0][3]).toBeNull();
  });

  it("os ids continuam números (o servidor recusa id escrito como texto)", () => {
    const { pacote } = montarPacote(copia());

    expect(typeof pacote.tabelas.PESSOA.linhas[0][0]).toBe("number");
    expect(typeof pacote.tabelas.CONTATO_PESSOA.linhas[0][2]).toBe("number");
  });

  it("aceita tabelas vazias", () => {
    const { pacote, resumo } = montarPacote(copia({ contatos: [] }));

    expect(pacote.tabelas.CONTATO_PESSOA.linhas).toEqual([]);
    expect(resumo.linhas.CONTATO_PESSOA).toBe(0);
  });

  it("ignora linhas em branco e quebras de linha do Windows", () => {
    const arquivos = copia();
    const texto = new TextDecoder().decode(arquivos["PESSOA.jsonl"]).replaceAll("\n", "\r\n") + "\r\n\r\n";
    arquivos["PESSOA.jsonl"] = new TextEncoder().encode(texto);

    expect(montarPacote(arquivos).pacote.tabelas.PESSOA.linhas).toHaveLength(2);
  });

  it("lê acentos em UTF-8", () => {
    const { pacote } = montarPacote(copia({ pessoas: [pessoa(101, "JOÃO DA CONCEIÇÃO")] }));

    expect(pacote.tabelas.PESSOA.linhas[0][1]).toBe("JOÃO DA CONCEIÇÃO");
  });
});

describe("montarPacote: cópia com defeito é recusada antes de enviar qualquer coisa", () => {
  it("cópia cortada: o manifesto diz mais linhas do que o arquivo tem", () => {
    const arquivos = copia();
    const manifesto = JSON.parse(new TextDecoder().decode(arquivos["_manifesto.json"]));
    manifesto.tabelas.PESSOA.linhas = 5000;
    arquivos["_manifesto.json"] = json(manifesto);

    expect(() => montarPacote(arquivos)).toThrow(CopiaInvalida);
    expect(() => montarPacote(arquivos)).toThrow(/PESSOA: o manifesto diz 5000 linhas e o arquivo tem 2/);
  });

  it("cópia cortada: o arquivo tem menos linhas do que o manifesto", () => {
    const arquivos = copia();
    arquivos["PESSOA_STATUS.jsonl"] = jsonl([{ ID_PESSOA: 101, DT_INI_STATUS: "x", DT_FIM_STATUS: "y", CD_STATUS: "A" }]);

    expect(() => montarPacote(arquivos)).toThrow(/PESSOA_STATUS: o manifesto diz 2 linhas e o arquivo tem 1/);
  });

  it.each([
    ["PESSOA", "NR_CPF"],
    ["PESSOA_STATUS", "DT_FIM_STATUS"],
    ["CONTATO_PESSOA", "DS_CONTATO"],
  ])("coluna %s.%s que o Data4U tirou do manifesto", (tabela, coluna) => {
    const arquivos = copia();
    const manifesto = JSON.parse(new TextDecoder().decode(arquivos["_manifesto.json"]));
    manifesto.tabelas[tabela].colunas = manifesto.tabelas[tabela].colunas.filter((c) => c !== coluna);
    arquivos["_manifesto.json"] = json(manifesto);

    expect(() => montarPacote(arquivos)).toThrow(new RegExp(`${tabela} da cópia não tem a\\(s\\) coluna\\(s\\) ${coluna}`));
  });

  it.each([
    ["não é JSON", new TextEncoder().encode("isto não é json")],
    ["é uma lista", json([1, 2])],
    ["não tem a data", json({ tabelas: {} })],
    ["não tem tabelas", json({ extracao: "07/10/2026 05:00:17" })],
    ["tabelas é nulo", json({ extracao: "07/10/2026 05:00:17", tabelas: null })],
    ["é o valor null", json(null)],
  ])("manifesto que %s", (_nome, bytes) => {
    const arquivos = copia();
    arquivos["_manifesto.json"] = bytes;

    expect(() => montarPacote(arquivos)).toThrow(/manifesto\.json não está no formato esperado/);
  });

  it("manifesto sem uma das tabelas", () => {
    const arquivos = copia();
    const manifesto = JSON.parse(new TextDecoder().decode(arquivos["_manifesto.json"]));
    delete manifesto.tabelas.CONTATO_PESSOA;
    arquivos["_manifesto.json"] = json(manifesto);

    expect(() => montarPacote(arquivos)).toThrow(/não descreve a tabela CONTATO_PESSOA/);
  });

  it("linha que não é JSON diz a tabela e o número da linha", () => {
    const arquivos = copia();
    arquivos["PESSOA.jsonl"] = new TextEncoder().encode('{"ID":1}\n{quebrada\n');

    expect(() => montarPacote(arquivos)).toThrow(/PESSOA\.jsonl, linha 2: não é JSON válido/);
  });

  it.each([["lista", "[1,2]"], ["número", "7"], ["null", "null"], ["texto", '"x"']])(
    "linha JSON que é %s e não um objeto",
    (_nome, linha) => {
      const arquivos = copia();
      arquivos["PESSOA.jsonl"] = new TextEncoder().encode(linha + "\n");

      expect(() => montarPacote(arquivos)).toThrow(/esperava um objeto JSON/);
    },
  );

  it("arquivo que não está em UTF-8", () => {
    const arquivos = copia();
    arquivos["PESSOA.jsonl"] = new Uint8Array([0x7b, 0xff, 0xfe, 0x7d, 0x0a]); // bytes inválidos em UTF-8

    expect(() => montarPacote(arquivos)).toThrow(/PESSOA\.jsonl não está em UTF-8/);
  });
});

describe("datas da cópia", () => {
  it("entende dd/mm/aaaa hh:mm:ss", () => {
    const data = dataDaExtracao("07/10/2026 05:00:17");

    expect([data.getFullYear(), data.getMonth(), data.getDate(), data.getHours(), data.getMinutes(), data.getSeconds()]).toEqual([
      2026, 9, 7, 5, 0, 17,
    ]);
  });

  it.each([null, undefined, "", "ontem", "2026-10-07 05:00:17", "07/10/2026", "31/02/2026 05:00:00", "07/10/2026 05:00"])(
    "texto %j não é data",
    (texto) => {
      expect(dataDaExtracao(texto)).toBeNull();
    },
  );

  it("idade em horas", () => {
    const agora = new Date(2026, 9, 7, 17, 0, 17);

    expect(idadeEmHoras("07/10/2026 05:00:17", agora)).toBeCloseTo(12, 5);
    expect(idadeEmHoras("lixo", agora)).toBeNull();
  });
});

describe("descreverCopia: o que a tela mostra antes de enviar", () => {
  const resumo = { extracao: "07/10/2026 05:00:17", linhas: { PESSOA: 7123, PESSOA_STATUS: 51234, CONTATO_PESSOA: 9000 } };

  it("cópia de hoje: mostra data e números, sem aviso", () => {
    const { texto, aviso } = descreverCopia(resumo, new Date(2026, 9, 7, 8, 30));

    expect(texto).toContain("07/10/2026 05:00");
    expect(texto).not.toContain("05:00:17"); // sem os segundos
    expect(texto).toContain((7123).toLocaleString("pt-BR"));
    expect(texto).toContain("períodos de situação");
    expect(aviso).toBeNull();
  });

  it("cópia de fim de semana (2 a 3 dias) avisa com o número de dias", () => {
    const { aviso } = descreverCopia(resumo, new Date(2026, 9, 10, 8, 30));

    expect(aviso).toMatch(/3 dia\(s\)/);
  });

  it("o aviso começa depois de 36 horas, não antes", () => {
    const extracao = new Date(2026, 9, 7, 5, 0, 17);
    const antes = new Date(extracao.getTime() + (HORAS_ATE_AVISAR - 1) * 3600000);
    const depois = new Date(extracao.getTime() + (HORAS_ATE_AVISAR + 1) * 3600000);

    expect(descreverCopia(resumo, antes).aviso).toBeNull();
    expect(descreverCopia(resumo, depois).aviso).not.toBeNull();
  });

  it("data no futuro manda conferir a data do computador", () => {
    expect(descreverCopia(resumo, new Date(2026, 9, 6, 8, 0)).aviso).toMatch(/futuro/);
  });

  it("data ilegível não quebra a tela", () => {
    const { texto, aviso } = descreverCopia({ ...resumo, extracao: "lixo" }, new Date());

    expect(texto).toContain("lixo");
    expect(aviso).toMatch(/Não consegui entender a data/);
  });
});

describe("interpretarResposta: o que fazer com a resposta do servidor", () => {
  it("200 com o relatório é sucesso", () => {
    expect(interpretarResposta(200, { texto: "Relatório", importadas: 12 })).toEqual({
      tipo: "ok",
      texto: "Relatório",
      importadas: 12,
    });
  });

  it.each([
    ["sem corpo", null],
    ["sem texto", { importadas: 1 }],
    ["texto que não é texto", { texto: 5 }],
  ])("200 %s NÃO conta como sucesso (talvez seja uma página de erro do proxy)", (_nome, corpo) => {
    expect(interpretarResposta(200, corpo).tipo).toBe("erro");
  });

  it("401 pede para autorizar o computador", () => {
    expect(interpretarResposta(401, { erro: "x" })).toEqual({ tipo: "nao_autorizado" });
  });

  it("400 mostra o motivo do servidor e diz que nada foi alterado", () => {
    const r = interpretarResposta(400, { erro: "A cópia é velha demais." });

    expect(r.tipo).toBe("erro");
    expect(r.mensagem).toBe("A cópia é velha demais. Nada foi alterado.");
  });

  it("413 explica que o arquivo ficou grande demais", () => {
    expect(interpretarResposta(413, { erro: "x" }).mensagem).toMatch(/grande demais/);
  });

  it.each([500, 502, 504, 400, 404])("status %i sem explicação clara pede para tentar de novo, sem prometer nada", (status) => {
    const r = interpretarResposta(status, null);

    expect(r.tipo).toBe("erro");
    expect(r.mensagem).toMatch(/Nada foi confirmado/);
  });

  it("a mensagem de rede caída avisa que enviar de novo não duplica", () => {
    expect(MENSAGEM_SEM_REDE).toMatch(/não duplica/);
    expect(MENSAGEM_SEM_REDE).toMatch(/Não sei se/);
  });
});
