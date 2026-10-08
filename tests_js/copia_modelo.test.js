import { describe, expect, it } from "vitest";
import {
  ARQUIVOS_DOS_TREINOS,
  ARQUIVOS_NECESSARIOS,
  COLUNAS_DOS_TREINOS,
  COLUNAS_ENVIADAS,
  CopiaInvalida,
  HORAS_ATE_AVISAR,
  MENSAGEM_SEM_REDE,
  MENSAGEM_SEM_REDE_TREINOS,
  TIPO_CONTATO_CELULAR,
  criarEtapas,
  dataDaExtracao,
  descreverCopia,
  descreverTreinos,
  enviarEtapas,
  idadeEmHoras,
  interpretarResposta,
  juntarRelatorios,
  montarPacote,
  montarPacoteDeTreinos,
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


describe("interpretarResposta: o assunto entra na mensagem de erro", () => {
  it("por padrão fala dos alunos", () => {
    expect(interpretarResposta(500, null).mensagem).toMatch(/atualizar os alunos/);
  });

  it("para o histórico de treinos fala do histórico", () => {
    const r = interpretarResposta(502, null, "o histórico de treinos");

    expect(r.mensagem).toMatch(/atualizar o histórico de treinos\. Nada foi confirmado/);
  });

  it("200 do histórico devolve o número de treinos para a tela", () => {
    expect(interpretarResposta(200, { texto: "R", treinos: 6196 }, "o histórico de treinos")).toMatchObject({
      tipo: "ok",
      texto: "R",
      treinos: 6196,
    });
  });

  it("400 do histórico mostra o motivo e diz que nada foi alterado", () => {
    expect(interpretarResposta(400, { erro: "TREINO, linha 1: formato." }, "o histórico de treinos").mensagem).toBe(
      "TREINO, linha 1: formato. Nada foi alterado.",
    );
  });

  it("a mensagem de rede caída do histórico também avisa que enviar de novo não duplica", () => {
    expect(MENSAGEM_SEM_REDE_TREINOS).toMatch(/histórico de treinos/);
    expect(MENSAGEM_SEM_REDE_TREINOS).toMatch(/não duplica/);
  });
});

// ---- histórico de treinos ----

// Colunas "de verdade" do Data4U (mais do que o app usa): o teste confere que o resto não sai.
const COLUNAS_REAIS_DOS_TREINOS = {
  TREINO: ["ID_TREINO", "ID_LANCAMENTO", "ID_PROFESSOR", "NM_TREINO", "DT_INICIO", "DT_FIM", "DS_OBS", "ST_ATIVO", "ST_DELETED"],
  TREINO_FICHA: ["ID_TREINO_FICHA", "ID_TREINO", "NR_FICHA", "NM_TREINO_FICHA", "DT_ULTIMA_SESSAO"],
  TREINO_PRESCRICAO: [
    "ID_TREINO_PRESCRICAO", "ID_TREINO_FICHA", "ID_TREINO_EXERCICIO", "NR_ORDEM", "NR_SERIE",
    "DS_REPETICAO", "DS_PESO", "TM_PAUSA", "DS_PRESCRICAO_OBS",
  ],
  TREINO_EXERCICIO: ["ID_TREINO_EXERCICIO", "NM_EXERCICIO", "DS_ANIMACAO", "ST_DELETED"],
  LANCAMENTO_OBJ: ["ID_LANCAMENTO", "ID_OBJ", "TP_LANCAMENTO", "DT_LANCAMENTO", "ID_PESSOA", "VL_LANCAMENTO"],
};

function copiaComTreinos({ treinos, fichas, prescricoes, exercicios, lancamentos, pessoas, manifesto } = {}) {
  treinos ??= [
    { ID_TREINO: 1, ID_LANCAMENTO: 5001, ID_PROFESSOR: 900, NM_TREINO: "TREINO ABC", DT_INICIO: "2026-03-02", DT_FIM: null, DS_OBS: "obs particular do treino", ST_ATIVO: "T", ST_DELETED: "F" },
    { ID_TREINO: 2, ID_LANCAMENTO: null, ID_PROFESSOR: null, NM_TREINO: "MODELO", DT_INICIO: null, DT_FIM: null, DS_OBS: null, ST_ATIVO: "T", ST_DELETED: "F" },
  ];
  fichas ??= [
    { ID_TREINO_FICHA: 11, ID_TREINO: 1, NR_FICHA: 1, NM_TREINO_FICHA: "A", DT_ULTIMA_SESSAO: "2026-04-01" },
    { ID_TREINO_FICHA: 21, ID_TREINO: 2, NR_FICHA: 1, NM_TREINO_FICHA: "A", DT_ULTIMA_SESSAO: null },
  ];
  prescricoes ??= [
    { ID_TREINO_PRESCRICAO: 101, ID_TREINO_FICHA: 11, ID_TREINO_EXERCICIO: -5, NR_ORDEM: 1, NR_SERIE: "3", DS_REPETICAO: "12", DS_PESO: 20, TM_PAUSA: "00:01:00", DS_PRESCRICAO_OBS: null },
    { ID_TREINO_PRESCRICAO: 201, ID_TREINO_FICHA: 21, ID_TREINO_EXERCICIO: 7, NR_ORDEM: 1, NR_SERIE: null, DS_REPETICAO: "10", DS_PESO: null, TM_PAUSA: null, DS_PRESCRICAO_OBS: null },
  ];
  exercicios ??= [
    { ID_TREINO_EXERCICIO: -5, NM_EXERCICIO: "SUPINO RETO", DS_ANIMACAO: "supino.gif", ST_DELETED: "F" },
    { ID_TREINO_EXERCICIO: 7, NM_EXERCICIO: "REMADA BAIXA", DS_ANIMACAO: null, ST_DELETED: "F" },
    { ID_TREINO_EXERCICIO: 8, NM_EXERCICIO: "NUNCA USADO NO TREINO", DS_ANIMACAO: null, ST_DELETED: "F" },
  ];
  lancamentos ??= [
    { ID_LANCAMENTO: 5001, ID_OBJ: 101, TP_LANCAMENTO: -510, DT_LANCAMENTO: "2026-03-02 14:03:24", ID_PESSOA: 900, VL_LANCAMENTO: 0 },
    { ID_LANCAMENTO: 5002, ID_OBJ: 101, TP_LANCAMENTO: -300, DT_LANCAMENTO: "2026-03-02 14:04:00", ID_PESSOA: 900, VL_LANCAMENTO: 99.9 },
    { ID_LANCAMENTO: 5003, ID_OBJ: 555, TP_LANCAMENTO: -300, DT_LANCAMENTO: "2026-03-03 10:00:00", ID_PESSOA: 1, VL_LANCAMENTO: 150 },
  ];
  pessoas ??= [pessoa(101, "ANA FICTICIA"), pessoa(900, "PROF ANA"), pessoa(901, "PROF QUE NAO MONTOU TREINO")];

  const arquivos = copia({ pessoas });
  const tabelas = { TREINO: treinos, TREINO_FICHA: fichas, TREINO_PRESCRICAO: prescricoes, TREINO_EXERCICIO: exercicios, LANCAMENTO_OBJ: lancamentos };
  const manifestoBase = JSON.parse(new TextDecoder().decode(arquivos["_manifesto.json"]));
  for (const [nome, linhas] of Object.entries(tabelas)) {
    manifestoBase.tabelas[nome] = { linhas: linhas.length, colunas: COLUNAS_REAIS_DOS_TREINOS[nome] };
    arquivos[nome + ".jsonl"] = jsonl(linhas);
  }
  arquivos["_manifesto.json"] = json(manifesto ?? manifestoBase);
  return arquivos;
}

describe("o que a tela precisa abrir do .zip para o histórico de treinos", () => {
  it("as 5 tabelas de treino (a PESSOA já é lida para os alunos)", () => {
    expect(ARQUIVOS_DOS_TREINOS).toEqual([
      "TREINO.jsonl", "TREINO_FICHA.jsonl", "TREINO_PRESCRICAO.jsonl", "TREINO_EXERCICIO.jsonl", "LANCAMENTO_OBJ.jsonl",
    ]);
    expect(ARQUIVOS_NECESSARIOS).toContain("PESSOA.jsonl");
  });
});

describe("montarPacoteDeTreinos: o que sai do computador", () => {
  it("monta o pacote com a data da cópia e as 6 tabelas", () => {
    const { pacote, resumo } = montarPacoteDeTreinos(copiaComTreinos());

    expect(pacote.extracao).toBe("07/10/2026 05:00:17");
    expect(Object.keys(pacote.tabelas).sort()).toEqual(Object.keys(COLUNAS_DOS_TREINOS).sort());
    expect(resumo).toEqual({ treinos: 2, fichas: 2, prescricoes: 2 });
  });

  it("envia SÓ as colunas que o app usa (nada de observação do treino, datas de início, valores, animações)", () => {
    const { pacote } = montarPacoteDeTreinos(copiaComTreinos());

    for (const tabela of Object.keys(COLUNAS_DOS_TREINOS)) {
      expect(pacote.tabelas[tabela].colunas).toEqual(COLUNAS_DOS_TREINOS[tabela]);
      for (const linha of pacote.tabelas[tabela].linhas) expect(linha).toHaveLength(COLUNAS_DOS_TREINOS[tabela].length);
    }
    const enviado = JSON.stringify(pacote);
    for (const proibido of ["obs particular do treino", "supino.gif", "99.9", "150", "DT_INICIO", "VL_LANCAMENTO", "2026-04-01"]) {
      expect(enviado).not.toContain(proibido);
    }
  });

  it("de PESSOA vão só os professores dos treinos, só id e nome (nada de CPF, nascimento, e-mail)", () => {
    const { pacote } = montarPacoteDeTreinos(copiaComTreinos());

    expect(pacote.tabelas.PESSOA.linhas).toEqual([[900, "PROF ANA"]]);
    const enviado = JSON.stringify(pacote);
    for (const proibido of ["ANA FICTICIA", "PROF QUE NAO MONTOU TREINO", "11144477735", "segredo@exemplo.test", "1990-01-01"]) {
      expect(enviado).not.toContain(proibido);
    }
  });

  it("de LANCAMENTO_OBJ vão só os lançamentos dos treinos (os de pagamento e outros ficam)", () => {
    const { pacote } = montarPacoteDeTreinos(copiaComTreinos());

    expect(pacote.tabelas.LANCAMENTO_OBJ.linhas).toEqual([[5001, 101, -510, "2026-03-02 14:03:24"]]);
  });

  it("dos exercícios vão só os que alguma prescrição usa", () => {
    const { pacote } = montarPacoteDeTreinos(copiaComTreinos());

    expect(pacote.tabelas.TREINO_EXERCICIO.linhas).toEqual([[-5, "SUPINO RETO"], [7, "REMADA BAIXA"]]);
  });

  it("treinos, fichas e prescrições vão inteiros (quem entra no app o servidor decide)", () => {
    const { pacote } = montarPacoteDeTreinos(copiaComTreinos());

    expect(pacote.tabelas.TREINO.linhas).toEqual([
      [1, 5001, 900, "TREINO ABC", "F"],
      [2, null, null, "MODELO", "F"],
    ]);
    expect(pacote.tabelas.TREINO_FICHA.linhas).toHaveLength(2);
    expect(pacote.tabelas.TREINO_PRESCRICAO.linhas).toHaveLength(2);
  });

  it("peso guardado como número no Data4U vira texto; os ids continuam números; vazio continua vazio", () => {
    const { pacote } = montarPacoteDeTreinos(copiaComTreinos());
    const prescricoes = pacote.tabelas.TREINO_PRESCRICAO.linhas;

    expect(prescricoes[0]).toEqual([101, 11, -5, 1, "3", "12", "20", "00:01:00", null]);
    expect(prescricoes[1][4]).toBeNull(); // NR_SERIE vazio não vira o texto "null"
    expect(typeof prescricoes[0][0]).toBe("number");
    expect(typeof prescricoes[0][2]).toBe("number");
  });

  it("prescrição sem exercício escolhido (vazio no Data4U) vai no pacote e não leva exercício nenhum junto", () => {
    const { pacote } = montarPacoteDeTreinos(
      copiaComTreinos({
        prescricoes: [
          { ID_TREINO_PRESCRICAO: 101, ID_TREINO_FICHA: 11, ID_TREINO_EXERCICIO: null, NR_ORDEM: 1, NR_SERIE: "3", DS_REPETICAO: "15", DS_PESO: "MODERADO", TM_PAUSA: "00:00:00", DS_PRESCRICAO_OBS: null },
          { ID_TREINO_PRESCRICAO: 201, ID_TREINO_FICHA: 21, ID_TREINO_EXERCICIO: 7, NR_ORDEM: 1, NR_SERIE: null, DS_REPETICAO: "10", DS_PESO: null, TM_PAUSA: null, DS_PRESCRICAO_OBS: null },
        ],
      }),
    );

    expect(pacote.tabelas.TREINO_PRESCRICAO.linhas[0]).toEqual([101, 11, null, 1, "3", "15", "MODERADO", "00:00:00", null]);
    expect(pacote.tabelas.TREINO_EXERCICIO.linhas).toEqual([[7, "REMADA BAIXA"]]);
  });

  it("treino sem lançamento ou sem professor não quebra o filtro", () => {
    const { pacote } = montarPacoteDeTreinos(
      copiaComTreinos({
        treinos: [{ ID_TREINO: 2, ID_LANCAMENTO: null, ID_PROFESSOR: null, NM_TREINO: "MODELO", ST_DELETED: "F" }],
        fichas: [],
        prescricoes: [],
        exercicios: [],
      }),
    );

    expect(pacote.tabelas.LANCAMENTO_OBJ.linhas).toEqual([]);
    expect(pacote.tabelas.PESSOA.linhas).toEqual([]);
  });

  it("não mexe nos arquivos dos alunos: montarPacote continua devolvendo só as 3 tabelas", () => {
    const arquivos = copiaComTreinos();

    expect(Object.keys(montarPacote(arquivos).pacote.tabelas)).toEqual(["PESSOA", "PESSOA_STATUS", "CONTATO_PESSOA"]);
  });
});

describe("montarPacoteDeTreinos: cópia com defeito é recusada antes de enviar qualquer coisa", () => {
  it.each(Object.keys(COLUNAS_DOS_TREINOS).filter((t) => t !== "PESSOA"))("%s cortada: o manifesto diz mais linhas do que o arquivo", (tabela) => {
    const arquivos = copiaComTreinos();
    const manifesto = JSON.parse(new TextDecoder().decode(arquivos["_manifesto.json"]));
    manifesto.tabelas[tabela].linhas += 10;
    arquivos["_manifesto.json"] = json(manifesto);

    expect(() => montarPacoteDeTreinos(arquivos)).toThrow(new RegExp(`${tabela}: o manifesto diz`));
  });

  it.each([
    ["TREINO", "NM_TREINO"],
    ["TREINO_FICHA", "NR_FICHA"],
    ["TREINO_PRESCRICAO", "TM_PAUSA"],
    ["TREINO_EXERCICIO", "NM_EXERCICIO"],
    ["LANCAMENTO_OBJ", "DT_LANCAMENTO"],
  ])("coluna %s.%s que o Data4U tirou do manifesto", (tabela, coluna) => {
    const arquivos = copiaComTreinos();
    const manifesto = JSON.parse(new TextDecoder().decode(arquivos["_manifesto.json"]));
    manifesto.tabelas[tabela].colunas = manifesto.tabelas[tabela].colunas.filter((c) => c !== coluna);
    arquivos["_manifesto.json"] = json(manifesto);

    expect(() => montarPacoteDeTreinos(arquivos)).toThrow(new RegExp(`${tabela} da cópia não tem a\\(s\\) coluna\\(s\\) ${coluna}`));
  });

  it("manifesto sem uma das tabelas de treino", () => {
    const arquivos = copiaComTreinos();
    const manifesto = JSON.parse(new TextDecoder().decode(arquivos["_manifesto.json"]));
    delete manifesto.tabelas.TREINO_PRESCRICAO;
    arquivos["_manifesto.json"] = json(manifesto);

    expect(() => montarPacoteDeTreinos(arquivos)).toThrow(/não descreve a tabela TREINO_PRESCRICAO/);
  });

  it("linha quebrada diz a tabela e o número da linha", () => {
    const arquivos = copiaComTreinos();
    arquivos["TREINO_FICHA.jsonl"] = new TextEncoder().encode('{"ID_TREINO_FICHA":1}\n{quebrada\n');

    expect(() => montarPacoteDeTreinos(arquivos)).toThrow(/TREINO_FICHA\.jsonl, linha 2: não é JSON válido/);
  });

  it("a mesma exceção dos alunos (CopiaInvalida), para a tela mostrar a mensagem", () => {
    const arquivos = copiaComTreinos();
    arquivos["TREINO.jsonl"] = new Uint8Array([0x7b, 0xff, 0xfe, 0x7d]);

    expect(() => montarPacoteDeTreinos(arquivos)).toThrow(CopiaInvalida);
  });
});

describe("descreverTreinos", () => {
  it("mostra os números com ponto de milhar", () => {
    const texto = descreverTreinos({ treinos: 6206, fichas: 15566, prescricoes: 129471 });

    expect(texto).toContain((6206).toLocaleString("pt-BR"));
    expect(texto).toContain("fichas");
    expect(texto).toContain((129471).toLocaleString("pt-BR"));
  });
});


describe("enviar em etapas: alunos primeiro, depois o histórico", () => {
  const ok = (texto, extra = {}) => ({ status: 200, corpo: { texto, ...extra } });

  // Servidor de mentira que anota o que recebeu. `respostas`: rota -> lista de respostas (uma por tentativa).
  function servidor(respostas) {
    const chamadas = [];
    const enviar = async (rota, pacote) => {
      chamadas.push({ rota, pacote });
      const fila = respostas[rota];
      const resposta = fila.length > 1 ? fila.shift() : fila[0];
      if (resposta instanceof Error) throw resposta;
      return resposta;
    };
    return { chamadas, enviar };
  }

  it("manda os alunos e só depois o histórico, cada um para a sua rota", async () => {
    const etapas = criarEtapas({ id: "A" }, { id: "T" });
    const { chamadas, enviar } = servidor({
      "/api/alunos/importar": [ok("relatório dos alunos")],
      "/api/treinos/importar": [ok("relatório dos treinos")],
    });

    const resultado = await enviarEtapas(etapas, enviar);

    expect(resultado).toEqual({ completo: true });
    expect(chamadas).toEqual([
      { rota: "/api/alunos/importar", pacote: { id: "A" } },
      { rota: "/api/treinos/importar", pacote: { id: "T" } },
    ]);
    expect(juntarRelatorios(etapas)).toBe("relatório dos alunos\n\nrelatório dos treinos");
  });

  it("avisa a tela antes de cada etapa", async () => {
    const etapas = criarEtapas({}, {});
    const { enviar } = servidor({ "/api/alunos/importar": [ok("a")], "/api/treinos/importar": [ok("t")] });
    const avisos = [];

    await enviarEtapas(etapas, enviar, (etapa) => avisos.push(etapa.chave));

    expect(avisos).toEqual(["alunos", "treinos"]);
  });

  it("se os alunos falham, o histórico NÃO é enviado", async () => {
    const etapas = criarEtapas({}, {});
    const { chamadas, enviar } = servidor({
      "/api/alunos/importar": [{ status: 400, corpo: { erro: "A cópia é velha demais." } }],
      "/api/treinos/importar": [ok("t")],
    });

    const resultado = await enviarEtapas(etapas, enviar);

    expect(resultado.completo).toBe(false);
    expect(resultado.etapa.chave).toBe("alunos");
    expect(resultado.resultado.mensagem).toBe("A cópia é velha demais. Nada foi alterado.");
    expect(chamadas.map((c) => c.rota)).toEqual(["/api/alunos/importar"]);
    expect(juntarRelatorios(etapas)).toBe("");
  });

  it("se o histórico falha, os alunos ficam marcados como enviados e a mensagem fala do histórico", async () => {
    const etapas = criarEtapas({}, {});
    const { enviar } = servidor({
      "/api/alunos/importar": [ok("relatório dos alunos")],
      "/api/treinos/importar": [{ status: 502, corpo: null }],
    });

    const resultado = await enviarEtapas(etapas, enviar);

    expect(resultado.completo).toBe(false);
    expect(resultado.etapa.chave).toBe("treinos");
    expect(resultado.resultado.mensagem).toMatch(/atualizar o histórico de treinos/);
    expect(etapas[0].enviado).toBe(true);
    expect(etapas[1].enviado).toBe(false);
    expect(juntarRelatorios(etapas)).toBe("relatório dos alunos");
  });

  it("tentar de novo manda só o que faltou", async () => {
    const etapas = criarEtapas({ id: "A" }, { id: "T" });
    const { chamadas, enviar } = servidor({
      "/api/alunos/importar": [ok("a")],
      "/api/treinos/importar": [{ status: 500, corpo: null }, ok("t")],
    });

    await enviarEtapas(etapas, enviar);
    const segunda = await enviarEtapas(etapas, enviar);

    expect(segunda).toEqual({ completo: true });
    expect(chamadas.map((c) => c.rota)).toEqual(["/api/alunos/importar", "/api/treinos/importar", "/api/treinos/importar"]);
    expect(juntarRelatorios(etapas)).toBe("a\n\nt");
  });

  it("sem rede: a mensagem é a da etapa que estava indo (e a seguinte não sai)", async () => {
    const etapas = criarEtapas({}, {});
    const { chamadas, enviar } = servidor({
      "/api/alunos/importar": [ok("a")],
      "/api/treinos/importar": [new TypeError("Failed to fetch")],
    });

    const resultado = await enviarEtapas(etapas, enviar);

    expect(resultado.resultado.mensagem).toBe(MENSAGEM_SEM_REDE_TREINOS);
    expect(chamadas).toHaveLength(2);

    const outras = criarEtapas({}, {});
    const semRede = servidor({ "/api/alunos/importar": [new TypeError("Failed to fetch")], "/api/treinos/importar": [ok("t")] });
    const primeira = await enviarEtapas(outras, semRede.enviar);
    expect(primeira.resultado.mensagem).toBe(MENSAGEM_SEM_REDE);
    expect(semRede.chamadas).toHaveLength(1);
  });

  it("401 numa etapa para tudo e pede para autorizar o computador", async () => {
    const etapas = criarEtapas({}, {});
    const { chamadas, enviar } = servidor({
      "/api/alunos/importar": [{ status: 401, corpo: { erro: "x" } }],
      "/api/treinos/importar": [ok("t")],
    });

    const resultado = await enviarEtapas(etapas, enviar);

    expect(resultado.resultado).toEqual({ tipo: "nao_autorizado" });
    expect(chamadas).toHaveLength(1);
  });

  it("200 sem relatório (página de erro do proxy) não conta como enviado", async () => {
    const etapas = criarEtapas({}, {});
    const { enviar } = servidor({ "/api/alunos/importar": [{ status: 200, corpo: null }], "/api/treinos/importar": [ok("t")] });

    const resultado = await enviarEtapas(etapas, enviar);

    expect(resultado.completo).toBe(false);
    expect(etapas[0].enviado).toBe(false);
  });
});
