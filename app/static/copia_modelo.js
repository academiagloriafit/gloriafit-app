// Prepara, no navegador, o que a tela "Atualizar alunos" envia ao servidor.
//
// Regras (LGPD, princípio da necessidade): do base_total.zip (258 tabelas, com RG, nascimento,
// e-mail, pagamentos, digitais...) só saem daqui 3 tabelas, e delas só as colunas que o app usa.
// E-mail e telefones que não são celular nem chegam a ser enviados.
// A conferência da cópia contra o _manifesto.json (data, número de linhas, colunas) acontece
// aqui, porque é aqui que o arquivo inteiro está.

export const COLUNAS_ENVIADAS = {
  PESSOA: ["ID", "NM_PESSOA", "TP_PESSOA", "NR_CPF", "ST_DELETED"],
  PESSOA_STATUS: ["ID_PESSOA", "DT_INI_STATUS", "DT_FIM_STATUS", "CD_STATUS"],
  CONTATO_PESSOA: ["ID_CONTATO", "ID_PESSOA", "ID_TIPO_CONTATO", "DS_CONTATO"],
};
// Colunas de texto: o Data4U às vezes guarda número (ex.: CPF); o servidor quer texto.
const COLUNAS_DE_TEXTO = new Set(["NM_PESSOA", "TP_PESSOA", "NR_CPF", "ST_DELETED", "DT_INI_STATUS", "DT_FIM_STATUS", "CD_STATUS", "DS_CONTATO"]);
export const TIPO_CONTATO_CELULAR = 30; // tabela TIPO_CONTATO do Data4U: 30 = Celular
export const ARQUIVOS_NECESSARIOS = ["_manifesto.json", ...Object.keys(COLUNAS_ENVIADAS).map((t) => t + ".jsonl")];
// Teto de cada arquivo lido do .zip (as maiores tabelas usadas têm poucos MB).
export const TAMANHO_MAXIMO_DA_TABELA = 200 * 1024 * 1024;
export const HORAS_ATE_AVISAR = 36; // cópia mais velha que isto ganha um aviso na tela

export class CopiaInvalida extends Error {
  constructor(mensagem) {
    super(mensagem);
    this.name = "CopiaInvalida";
  }
}

const decodificador = new TextDecoder("utf-8", { fatal: true });

function linhasJson(bytes, tabela) {
  let texto;
  try {
    texto = decodificador.decode(bytes);
  } catch {
    throw new CopiaInvalida(`${tabela}.jsonl não está em UTF-8.`);
  }
  const linhas = [];
  let numero = 0;
  for (const bruta of texto.split("\n")) {
    numero++;
    if (!bruta.trim()) continue;
    let linha;
    try {
      linha = JSON.parse(bruta);
    } catch {
      throw new CopiaInvalida(`${tabela}.jsonl, linha ${numero}: não é JSON válido.`);
    }
    if (linha === null || typeof linha !== "object" || Array.isArray(linha)) {
      throw new CopiaInvalida(`${tabela}.jsonl, linha ${numero}: esperava um objeto JSON.`);
    }
    linhas.push(linha);
  }
  return linhas;
}

function lerManifesto(bytes) {
  try {
    const manifesto = JSON.parse(decodificador.decode(bytes));
    if (typeof manifesto.extracao !== "string" || typeof manifesto.tabelas !== "object" || manifesto.tabelas === null) {
      throw new Error("formato");
    }
    return manifesto;
  } catch {
    throw new CopiaInvalida("O _manifesto.json não está no formato esperado.");
  }
}

function paraTexto(valor) {
  return valor === null || valor === undefined ? null : typeof valor === "string" ? valor : String(valor);
}

function reduzir(tabela, linhas) {
  const colunas = COLUNAS_ENVIADAS[tabela];
  return linhas.map((linha) =>
    colunas.map((coluna) => (COLUNAS_DE_TEXTO.has(coluna) ? paraTexto(linha[coluna]) : linha[coluna])),
  );
}

// `arquivos`: { "_manifesto.json": Uint8Array, "PESSOA.jsonl": Uint8Array, ... }.
// Devolve { pacote, resumo }. `pacote` é o que vai ao servidor; `resumo` é o que a tela mostra.
export function montarPacote(arquivos) {
  const manifesto = lerManifesto(arquivos["_manifesto.json"]);
  const pacote = { extracao: manifesto.extracao, tabelas: {} };
  const resumo = { extracao: manifesto.extracao, linhas: {} };

  for (const [tabela, colunas] of Object.entries(COLUNAS_ENVIADAS)) {
    const dadosDoManifesto = manifesto.tabelas[tabela];
    if (!dadosDoManifesto || !Array.isArray(dadosDoManifesto.colunas) || typeof dadosDoManifesto.linhas !== "number") {
      throw new CopiaInvalida(`O manifesto não descreve a tabela ${tabela}.`);
    }
    const faltam = colunas.filter((c) => !dadosDoManifesto.colunas.includes(c));
    if (faltam.length) throw new CopiaInvalida(`A tabela ${tabela} da cópia não tem a(s) coluna(s) ${faltam.join(", ")}.`);

    const linhas = linhasJson(arquivos[tabela + ".jsonl"], tabela);
    if (linhas.length !== dadosDoManifesto.linhas) {
      throw new CopiaInvalida(
        `${tabela}: o manifesto diz ${dadosDoManifesto.linhas} linhas e o arquivo tem ${linhas.length}. ` +
          "A cópia pode ter sido cortada: gere de novo no PC da recepção.",
      );
    }
    resumo.linhas[tabela] = linhas.length;
    const aproveitadas =
      tabela === "CONTATO_PESSOA" ? linhas.filter((l) => l.ID_TIPO_CONTATO === TIPO_CONTATO_CELULAR) : linhas;
    pacote.tabelas[tabela] = { colunas: [...colunas], linhas: reduzir(tabela, aproveitadas) };
  }
  return { pacote, resumo };
}

// "07/10/2026 05:00:17" (horário local do PC) -> Date; null se o texto não for isso.
export function dataDaExtracao(texto) {
  const m = /^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2}):(\d{2})$/.exec(texto || "");
  if (!m) return null;
  const [, dia, mes, ano, hora, minuto, segundo] = m.map(Number);
  const data = new Date(ano, mes - 1, dia, hora, minuto, segundo);
  return data.getMonth() === mes - 1 && data.getDate() === dia ? data : null;
}

export function idadeEmHoras(extracao, agora = new Date()) {
  const data = dataDaExtracao(extracao);
  return data === null ? null : (agora.getTime() - data.getTime()) / 3600000;
}

function formatarNumero(n) {
  return n.toLocaleString("pt-BR");
}

// Texto da tela depois de o arquivo ser lido.
export function descreverCopia(resumo, agora = new Date()) {
  const horas = idadeEmHoras(resumo.extracao, agora);
  const quando = (dataDaExtracao(resumo.extracao) ? resumo.extracao.slice(0, 16) : resumo.extracao);
  let texto =
    `Cópia do Data4U de ${quando}: ${formatarNumero(resumo.linhas.PESSOA)} pessoas, ` +
    `${formatarNumero(resumo.linhas.PESSOA_STATUS)} períodos de situação e ${formatarNumero(resumo.linhas.CONTATO_PESSOA)} contatos.`;
  let aviso = null;
  if (horas === null) {
    aviso = "Não consegui entender a data da cópia.";
  } else if (horas < 0) {
    aviso = "A data da cópia está no futuro. Confira a data deste computador.";
  } else if (horas > HORAS_ATE_AVISAR) {
    aviso = `Esta cópia tem ${Math.floor(horas / 24)} dia(s). Se a extração das 05:00 de hoje já rodou, escolha o arquivo mais novo.`;
  }
  return { texto, aviso };
}

export const MENSAGEM_SEM_REDE =
  "Não consegui falar com o servidor. Não sei se os alunos foram atualizados: abra a busca para conferir e, se precisar, envie de novo (enviar de novo não duplica nada).";

// Resposta do servidor -> o que a tela faz. Só 200 com o relatório conta como sucesso.
export function interpretarResposta(status, corpo) {
  if (status === 200 && corpo && typeof corpo.texto === "string") {
    return { tipo: "ok", texto: corpo.texto, importadas: corpo.importadas };
  }
  if (status === 401) {
    return { tipo: "nao_autorizado" };
  }
  if (status === 413) {
    return { tipo: "erro", mensagem: "O arquivo enviado ficou grande demais para o servidor." };
  }
  if (status === 400 && corpo && typeof corpo.erro === "string") {
    return { tipo: "erro", mensagem: corpo.erro + " Nada foi alterado." };
  }
  return { tipo: "erro", mensagem: "O servidor não conseguiu atualizar os alunos. Nada foi confirmado: tente de novo." };
}
