// Leitor mínimo de .zip para o navegador: acha uma entrada pelo nome e a descompacta,
// sem biblioteca e SEM tocar nas outras entradas (o base_total.zip tem 258 tabelas; a tela
// "Atualizar alunos" só abre 4). Usa o DecompressionStream, que já vem no Chrome e no Edge.
//
// Só entende o que o base_total.zip tem: deflate ou sem compressão, sem criptografia e sem
// ZIP64 (que só aparece com arquivos acima de 4 GB). Qualquer outra coisa vira ZipInvalido,
// com uma mensagem clara, em vez de ler lixo.

const ASSINATURA_FIM = 0x06054b50;
const ASSINATURA_CENTRAL = 0x02014b50;
const ASSINATURA_LOCAL = 0x04034b50;
const TAMANHO_MAXIMO_DO_FIM = 22 + 0xffff; // fim fixo + comentário mais longo possível

export class ZipInvalido extends Error {
  constructor(mensagem) {
    super(mensagem);
    this.name = "ZipInvalido";
  }
}

function visao(bytes) {
  return new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
}

// Lista as entradas pelo índice (diretório central) no fim do arquivo.
// Devolve Map: nome -> { metodo, tamanhoComprimido, tamanhoOriginal, posicaoLocal }.
export function listarEntradas(bytes) {
  const v = visao(bytes);
  const limite = Math.max(0, bytes.length - TAMANHO_MAXIMO_DO_FIM);
  let fim = -1;
  for (let i = bytes.length - 22; i >= limite; i--) {
    if (v.getUint32(i, true) === ASSINATURA_FIM) {
      fim = i;
      break;
    }
  }
  if (fim < 0) throw new ZipInvalido("Este arquivo não parece ser um .zip (ou está cortado).");

  const total = v.getUint16(fim + 10, true);
  const posicaoCentral = v.getUint32(fim + 16, true);
  if (total === 0xffff || posicaoCentral === 0xffffffff) {
    throw new ZipInvalido("Este .zip usa o formato ZIP64, que a tela não lê.");
  }

  const entradas = new Map();
  const texto = new TextDecoder("utf-8");
  let p = posicaoCentral;
  for (let n = 0; n < total; n++) {
    if (p + 46 > bytes.length || v.getUint32(p, true) !== ASSINATURA_CENTRAL) {
      throw new ZipInvalido("O índice do .zip está danificado.");
    }
    const bits = v.getUint16(p + 8, true);
    const metodo = v.getUint16(p + 10, true);
    const tamanhoComprimido = v.getUint32(p + 20, true);
    const tamanhoOriginal = v.getUint32(p + 24, true);
    const tamanhoNome = v.getUint16(p + 28, true);
    const tamanhoExtra = v.getUint16(p + 30, true);
    const tamanhoComentario = v.getUint16(p + 32, true);
    const posicaoLocal = v.getUint32(p + 42, true);
    if (p + 46 + tamanhoNome > bytes.length) throw new ZipInvalido("O índice do .zip está danificado.");
    const nome = texto.decode(bytes.subarray(p + 46, p + 46 + tamanhoNome));
    entradas.set(nome, { metodo, tamanhoComprimido, tamanhoOriginal, posicaoLocal, criptografada: (bits & 1) === 1 });
    p += 46 + tamanhoNome + tamanhoExtra + tamanhoComentario;
  }
  return entradas;
}

async function descompactar(dados, tamanhoEsperado, limite) {
  if (typeof DecompressionStream === "undefined") {
    throw new ZipInvalido("Este navegador é antigo demais para abrir o arquivo. Use o Chrome atualizado.");
  }
  const fluxo = new Blob([dados]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
  const leitor = fluxo.getReader();
  const pedacos = [];
  let total = 0;
  try {
    for (;;) {
      const { done, value } = await leitor.read();
      if (done) break;
      total += value.length;
      if (total > limite) {
        await leitor.cancel();
        throw new ZipInvalido("Uma das tabelas é grande demais para ser a esperada.");
      }
      pedacos.push(value);
    }
  } catch (erro) {
    if (erro instanceof ZipInvalido) throw erro;
    throw new ZipInvalido("O arquivo está danificado (não foi possível descompactar).");
  }
  if (total !== tamanhoEsperado) throw new ZipInvalido("O arquivo está danificado (tamanho diferente do esperado).");
  const saida = new Uint8Array(total);
  let posicao = 0;
  for (const pedaco of pedacos) {
    saida.set(pedaco, posicao);
    posicao += pedaco.length;
  }
  return saida;
}

// Devolve os bytes (já descompactados) da entrada `nome`. `limite` = máximo de bytes aceito.
export async function lerEntrada(bytes, entradas, nome, limite) {
  const entrada = entradas.get(nome);
  if (!entrada) throw new ZipInvalido(`Não achei ${nome} dentro do arquivo.`);
  if (entrada.criptografada) throw new ZipInvalido(`${nome} está protegido por senha.`);
  if (entrada.tamanhoOriginal > limite) throw new ZipInvalido(`${nome} é grande demais para ser a tabela esperada.`);

  const v = visao(bytes);
  const p = entrada.posicaoLocal;
  if (p + 30 > bytes.length || v.getUint32(p, true) !== ASSINATURA_LOCAL) {
    throw new ZipInvalido("O índice do .zip está danificado.");
  }
  const inicio = p + 30 + v.getUint16(p + 26, true) + v.getUint16(p + 28, true);
  const dados = bytes.subarray(inicio, inicio + entrada.tamanhoComprimido);
  if (dados.length !== entrada.tamanhoComprimido) throw new ZipInvalido("O .zip está cortado.");

  if (entrada.metodo === 0) return dados;
  if (entrada.metodo === 8) return descompactar(dados, entrada.tamanhoOriginal, limite);
  throw new ZipInvalido(`${nome} usa uma compressão que a tela não lê.`);
}
