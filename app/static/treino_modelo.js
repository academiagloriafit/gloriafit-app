// Modelo do treino na tela de montagem: fichas (Treino A, B, C...), exercícios,
// bi-set/tri-set e validação. É lógica pura, sem nada de tela: recebe um "estado"
// e devolve um estado NOVO (o antigo nunca é alterado), o que facilita testar.
//
// Estado:
//   { proximoUid, proximoBloco,
//     fichas: [ { nome, itens: [ { uid, exercicioId, nome, series, repeticoes, carga,
//                                  pausaMin, pausaSeg, observacao, bloco } ] } ] }
// Um item que veio de "Importar treino" pode ter também  indisponivel: true  (o exercício saiu da lista de
// exercícios: a tela pede para trocar, e o treino não salva enquanto ele estiver lá).
// ("carga" é o campo "Peso" da tela; o nome interno não muda porque é o do servidor e do banco.
//  O Intervalo é digitado em minutos e segundos, como no Data4U, e vai ao servidor em segundos.)
// "bloco": itens vizinhos com o mesmo número formam um bi-set (2) ou tri-set (3);
// null = exercício sozinho.

export const LIMITE_NOME_FICHA = 15; // NM_TREINO_FICHA no Data4U (corta sem avisar)
export const LIMITE_CAMPO = 11; // NR_SERIE, DS_REPETICAO, DS_PESO no Data4U
export const LIMITE_NOME_TREINO = 40; // NM_TREINO no Data4U
export const LIMITE_QUEM_MONTOU = 60; // limite nosso (o nome de quem montou é digitado)
export const LIMITE_OBSERVACAO = 200; // limite nosso (a maior observação real do Data4U tem 131 letras)
export const MAXIMO_PAUSA = 59; // minutos e segundos do intervalo vão de 0 a 59 (máximo 59 min 59 s)
export const MAXIMO_SESSOES_POR_FICHA = 999; // "Treinos por ficha": quantas vezes o aluno faz CADA ficha
export const ANO_MINIMO_DO_TREINO = 2020; // início/fim fora destes anos é erro de digitação
export const ANO_MAXIMO_DO_TREINO = 2100;
export const MAXIMO_FICHAS = 26; // uma letra de A a Z para cada
export const MAXIMO_ITENS_POR_FICHA = 100; // trava de segurança do rascunho, não é regra da academia
export const MINIMO_NO_BLOCO = 2;
export const MAXIMO_NO_BLOCO = 3;

const LETRAS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const CAMPOS_EDITAVEIS = ["series", "repeticoes", "carga", "pausaMin", "pausaSeg", "observacao"];
// Campos que o rascunho de uma versão anterior da tela não tem: entram vazios.
const CAMPOS_NOVOS = ["pausaMin", "pausaSeg", "observacao"];

function copiar(estado) {
  return structuredClone(estado);
}

// Mesmas palavras do Data4U: o TREINO tem um nome e várias FICHAS (A, B, C...).
function nomePadraoDaFicha(indice) {
  return "FICHA " + LETRAS[indice];
}

export function criarEstado() {
  return { proximoUid: 1, proximoBloco: 1, fichas: [{ nome: nomePadraoDaFicha(0), itens: [] }] };
}

// ------------------------------------------------------------------ fichas

export function adicionarFicha(estado) {
  if (estado.fichas.length >= MAXIMO_FICHAS) return estado;
  const novo = copiar(estado);
  const usados = new Set(novo.fichas.map((f) => f.nome.trim().toUpperCase()));
  let nome = nomePadraoDaFicha(0);
  for (let i = 0; i < LETRAS.length; i++) {
    if (!usados.has(nomePadraoDaFicha(i))) {
      nome = nomePadraoDaFicha(i);
      break;
    }
  }
  novo.fichas.push({ nome, itens: [] });
  return novo;
}

export function renomearFicha(estado, f, nome) {
  if (!estado.fichas[f]) return estado;
  const novo = copiar(estado);
  novo.fichas[f].nome = String(nome);
  return novo;
}

// Não deixa o treino sem nenhuma ficha.
export function removerFicha(estado, f) {
  if (!estado.fichas[f] || estado.fichas.length <= 1) return estado;
  const novo = copiar(estado);
  novo.fichas.splice(f, 1);
  return novo;
}

// ------------------------------------------------------------------ exercícios

export function adicionarItem(estado, f, exercicio) {
  const ficha = estado.fichas[f];
  if (!ficha || ficha.itens.length >= MAXIMO_ITENS_POR_FICHA) return estado;
  const novo = copiar(estado);
  novo.fichas[f].itens.push({
    uid: novo.proximoUid++,
    exercicioId: exercicio.id,
    nome: exercicio.nome,
    series: "",
    repeticoes: "",
    carga: "",
    pausaMin: "",
    pausaSeg: "",
    observacao: "",
    bloco: null,
  });
  return novo;
}

export function atualizarItem(estado, f, uid, campo, valor) {
  if (!CAMPOS_EDITAVEIS.includes(campo)) return estado;
  const ficha = estado.fichas[f];
  if (!ficha || !ficha.itens.some((i) => i.uid === uid)) return estado;
  const novo = copiar(estado);
  novo.fichas[f].itens.find((i) => i.uid === uid)[campo] = campo.startsWith("pausa") ? soDigitos(valor) : String(valor);
  return novo;
}

// Minutos e segundos do intervalo: só números, no máximo 2 dígitos.
function soDigitos(valor) {
  return String(valor).replace(/\D/g, "").slice(0, 2);
}

export function removerItem(estado, f, uid) {
  const ficha = estado.fichas[f];
  if (!ficha || !ficha.itens.some((i) => i.uid === uid)) return estado;
  const novo = copiar(estado);
  novo.fichas[f].itens = novo.fichas[f].itens.filter((i) => i.uid !== uid);
  desfazerBlocosIncompletos(novo.fichas[f]);
  return novo;
}

// Um bloco que ficou com 1 só exercício deixa de ser bi-set.
function desfazerBlocosIncompletos(ficha) {
  for (const u of unidades(ficha)) {
    if (u.tipo === "bloco" && u.itens.length < MINIMO_NO_BLOCO) {
      u.itens.forEach((i) => (i.bloco = null));
    }
  }
}

// ------------------------------------------------------------------ ordem e blocos

// A ficha vista como uma lista de "unidades": ou um exercício sozinho, ou um
// bloco inteiro (bi-set/tri-set). Mover e numerar trabalham com unidades, para
// que um bi-set nunca seja separado sem querer.
export function unidades(ficha) {
  const lista = [];
  for (const item of ficha.itens) {
    const ultima = lista[lista.length - 1];
    if (item.bloco === null) {
      lista.push({ tipo: "item", item });
    } else if (ultima && ultima.tipo === "bloco" && ultima.bloco === item.bloco) {
      ultima.itens.push(item);
    } else {
      lista.push({ tipo: "bloco", bloco: item.bloco, itens: [item] });
    }
  }
  return lista;
}

function achatar(lista) {
  return lista.flatMap((u) => (u.tipo === "bloco" ? u.itens : [u.item]));
}

// direcao: -1 sobe, +1 desce.
export function moverUnidade(estado, f, indiceDaUnidade, direcao) {
  if (!estado.fichas[f]) return estado;
  const novo = copiar(estado);
  const lista = unidades(novo.fichas[f]);
  const destino = indiceDaUnidade + direcao;
  if (indiceDaUnidade < 0 || indiceDaUnidade >= lista.length) return estado;
  if (destino < 0 || destino >= lista.length) return estado;
  [lista[indiceDaUnidade], lista[destino]] = [lista[destino], lista[indiceDaUnidade]];
  novo.fichas[f].itens = achatar(lista);
  return novo;
}

export function nomeDoBloco(quantidade) {
  return quantidade === 3 ? "Tri-set" : "Bi-set";
}

// Junta exercícios que estão sozinhos e um embaixo do outro. Devolve
// { ok: true, estado } ou { ok: false, erro: "mensagem para mostrar" }.
export function unirEmBloco(estado, f, uids) {
  const ficha = estado.fichas[f];
  const unicos = [...new Set(uids)];
  if (!ficha || unicos.length < MINIMO_NO_BLOCO || unicos.length > MAXIMO_NO_BLOCO) {
    return { ok: false, erro: "Selecione 2 exercícios para um bi-set ou 3 para um tri-set." };
  }
  const posicoes = unicos.map((uid) => ficha.itens.findIndex((i) => i.uid === uid)).sort((a, b) => a - b);
  if (posicoes.includes(-1)) {
    return { ok: false, erro: "Exercício não encontrado nesta ficha." };
  }
  if (posicoes.some((p) => ficha.itens[p].bloco !== null)) {
    return { ok: false, erro: "Só dá para juntar exercícios que ainda não estão em um bi-set ou tri-set." };
  }
  for (let i = 1; i < posicoes.length; i++) {
    if (posicoes[i] !== posicoes[i - 1] + 1) {
      return {
        ok: false,
        erro: "Os exercícios precisam estar um embaixo do outro. Use as setas para aproximá-los.",
      };
    }
  }
  const novo = copiar(estado);
  const numero = novo.proximoBloco++;
  posicoes.forEach((p) => (novo.fichas[f].itens[p].bloco = numero));
  return { ok: true, estado: novo };
}

export function desfazerBloco(estado, f, bloco) {
  const ficha = estado.fichas[f];
  if (!ficha || !ficha.itens.some((i) => i.bloco === bloco)) return estado;
  const novo = copiar(estado);
  novo.fichas[f].itens.filter((i) => i.bloco === bloco).forEach((i) => (i.bloco = null));
  return novo;
}

// ------------------------------------------------------------------ apresentação

// Etiqueta de cada exercício, como no desenho: os de um bi-set/tri-set levam a
// letra do bloco e a posição (A1, A2, B1...); os sozinhos levam o número da
// posição na ficha (3, 4, 5...). Devolve um Map: uid -> etiqueta.
export function etiquetas(ficha) {
  const mapa = new Map();
  let posicao = 0;
  let letra = 0;
  for (const u of unidades(ficha)) {
    if (u.tipo === "item") {
      posicao += 1;
      mapa.set(u.item.uid, String(posicao));
    } else {
      const l = LETRAS[letra++ % LETRAS.length];
      u.itens.forEach((item, i) => {
        posicao += 1;
        mapa.set(item.uid, l + (i + 1));
      });
    }
  }
  return mapa;
}

function plural(n, singular, pluralTexto) {
  return n + " " + (n === 1 ? singular : pluralTexto);
}

// "5 exercícios, 1 bi-set" (texto do desenho).
export function descreverFicha(ficha) {
  const partes = [plural(ficha.itens.length, "exercício", "exercícios")];
  const blocos = unidades(ficha).filter((u) => u.tipo === "bloco");
  const bis = blocos.filter((b) => b.itens.length === 2).length;
  const tris = blocos.filter((b) => b.itens.length === 3).length;
  if (bis) partes.push(plural(bis, "bi-set", "bi-sets"));
  if (tris) partes.push(plural(tris, "tri-set", "tri-sets"));
  return partes.join(", ");
}

// ------------------------------------------------------------------ validação

// Intervalo (minutos e segundos, de 0 a 59 cada) e observação (opcionais).
function problemasDoIntervaloEDaObservacao(item, f, rotulo) {
  const problemas = [];
  const de = (campo, mensagem) => problemas.push({ ficha: f, uid: item.uid, campo, mensagem: `${rotulo}: ${mensagem}` });
  for (const [campo, nomeDoCampo] of [["pausaMin", "minutos"], ["pausaSeg", "segundos"]]) {
    const valor = item[campo].trim();
    if (valor !== "" && (!/^\d{1,2}$/.test(valor) || Number(valor) > MAXIMO_PAUSA)) {
      de(campo, `no intervalo de ${item.nome}, os ${nomeDoCampo} vão de 0 a ${MAXIMO_PAUSA}.`);
    }
  }
  const observacao = limparEspacos(item.observacao);
  if (CARACTERE_INVALIDO.test(observacao)) {
    de("observacao", `a observação de ${item.nome} tem caracteres inválidos (invisíveis ou de controle).`);
  } else if (tamanho(observacao) > LIMITE_OBSERVACAO) {
    de("observacao", `a observação de ${item.nome} tem ${tamanho(observacao)} letras; o máximo é ${LIMITE_OBSERVACAO}.`);
  }
  return problemas;
}

// Lista o que impede de salvar. Cada problema: { ficha, uid, campo, mensagem }
// (uid = null quando o problema é da ficha toda).
export function validar(estado) {
  const problemas = [];
  estado.fichas.forEach((ficha, f) => {
    const nome = ficha.nome.trim();
    const rotulo = nome || "ficha " + (f + 1);
    if (!nome) {
      problemas.push({ ficha: f, uid: null, campo: "nome", mensagem: "Dê um nome à ficha " + (f + 1) + "." });
    } else if (nome.length > LIMITE_NOME_FICHA) {
      problemas.push({
        ficha: f,
        uid: null,
        campo: "nome",
        mensagem: `O nome "${nome}" tem ${nome.length} letras; o Data4U aceita no máximo ${LIMITE_NOME_FICHA}.`,
      });
    }
    if (ficha.itens.length === 0) {
      problemas.push({ ficha: f, uid: null, campo: "itens", mensagem: `${rotulo}: adicione pelo menos um exercício.` });
    }
    ficha.itens.forEach((item) => {
      if (item.indisponivel) {
        problemas.push({
          ficha: f,
          uid: item.uid,
          campo: "exercicio",
          mensagem: `${rotulo}: "${item.nome}" não está mais na lista de exercícios. Remova-o e escolha outro.`,
        });
      }
      problemas.push(...problemasDoIntervaloEDaObservacao(item, f, rotulo));
      for (const [campo, nomeDoCampo, obrigatorio] of [
        ["series", "séries", false], // em branco vale (cardio: o professor escreve o tempo, ou nada)
        ["repeticoes", "repetições", false],
        ["carga", "peso", false],
      ]) {
        const valor = item[campo].trim();
        if (obrigatorio && valor === "") {
          problemas.push({
            ficha: f,
            uid: item.uid,
            campo,
            mensagem: `${rotulo}: preencha as ${nomeDoCampo} de ${item.nome}.`,
          });
        } else if (valor.length > LIMITE_CAMPO) {
          problemas.push({
            ficha: f,
            uid: item.uid,
            campo,
            mensagem: `${rotulo}: ${nomeDoCampo} de ${item.nome} passa de ${LIMITE_CAMPO} caracteres (o Data4U corta sem avisar).`,
          });
        }
      }
    });
  });
  return problemas;
}

// ------------------------------------------------------------------ envio e rascunho

// Intervalo do exercício em segundos (minutos e segundos digitados), ou null quando não há
// intervalo (campos vazios ou 0:00). Só chame com valores já conferidos por validar().
export function pausaEmSegundos(item) {
  const total = Number(item.pausaMin || 0) * 60 + Number(item.pausaSeg || 0);
  return total > 0 ? total : null;
}

// Formato que o servidor vai receber: textos aparados, ordem 1..n e os blocos
// renumerados 1, 2, 3... em cada ficha.
export function paraEnvio(estado) {
  return {
    fichas: estado.fichas.map((ficha, f) => {
      const numeros = new Map();
      return {
        nome: ficha.nome.trim(),
        ordem: f + 1,
        itens: ficha.itens.map((item, j) => {
          let bloco = null;
          if (item.bloco !== null) {
            if (!numeros.has(item.bloco)) numeros.set(item.bloco, numeros.size + 1);
            bloco = numeros.get(item.bloco);
          }
          return {
            exercicio_id: item.exercicioId,
            ordem: j + 1,
            bloco,
            series: item.series.trim(),
            repeticoes: item.repeticoes.trim(),
            carga: item.carga.trim(),
            pausa: pausaEmSegundos(item),
            observacao: limparEspacos(item.observacao),
          };
        }),
      };
    }),
  };
}

// ------------------------------------------------------------------ nome do treino e quem montou

// Mesma regra do servidor: tira espaços das pontas e troca qualquer sequência de
// espaços/quebras de linha por um espaço só.
export function limparEspacos(texto) {
  return String(texto).split(/\s+/).filter(Boolean).join(" ");
}

// Tamanho em "letras" como o servidor conta (Python conta caracteres, não pedaços
// UTF-16: um emoji conta 1, e não 2 como em texto.length).
export function tamanho(texto) {
  return [...texto].length;
}

const CARACTERE_INVALIDO = /\p{C}/u; // controle, invisíveis (mesma ideia do servidor)

// Data curta do jeito brasileiro, dia/mês/ano com 2 dígitos: 07/10/26.
export function formatarData(data) {
  const dois = (n) => String(n).padStart(2, "0");
  return `${dois(data.getDate())}/${dois(data.getMonth() + 1)}/${dois(data.getFullYear() % 100)}`;
}

// Sugestão de nome para o treino inteiro (o Data4U exige um nome por treino, até 40
// letras, e não aceita dois iguais para o mesmo aluno). O professor pode trocar.
//   fichas "FICHA A", "FICHA B", "FICHA C" (ou "TREINO A"...) -> "TREINO ABC 07/10/26"
//   outros nomes -> "A POST/CORRIDA + B SUP/POSTURA 07/10/26" (cortado para caber)
// `dataTexto` vem de fora (ex.: "07/10/26") para esta função continuar pura e testável.
export function sugerirNomeDoTreino(estado, dataTexto) {
  const nomes = estado.fichas.map((f) => limparEspacos(f.nome)).filter(Boolean);
  const letras = nomes.map((n) => /^(?:FICHA|TREINO) ([A-Z])$/i.exec(n));
  let base;
  if (nomes.length === 0) {
    base = "TREINO";
  } else if (letras.every(Boolean)) {
    base = "TREINO " + letras.map((m) => m[1].toUpperCase()).join("");
  } else {
    base = nomes.join(" + ");
  }
  const data = limparEspacos(dataTexto || "");
  const sufixo = data ? " " + data : "";
  const espaco = Math.max(0, LIMITE_NOME_TREINO - tamanho(sufixo));
  const cortada = [...base].slice(0, espaco).join("").trimEnd();
  return (cortada + sufixo).trim();
}

// 'AAAA-MM-DD' (o que o campo de data entrega) -> o texto de volta se for uma data de verdade nos anos
// aceitos (2026-02-30 não é), senão null. Só algarismos comuns: é o mesmo rigor do servidor.
export function lerDia(texto) {
  const partes = /^(\d{4})-(\d{2})-(\d{2})$/.exec(typeof texto === "string" ? texto : "");
  if (!partes) return null;
  const [ano, mes, dia] = [Number(partes[1]), Number(partes[2]), Number(partes[3])];
  if (ano < ANO_MINIMO_DO_TREINO || ano > ANO_MAXIMO_DO_TREINO) return null;
  const data = new Date(Date.UTC(ano, mes - 1, dia));
  const confere = data.getUTCFullYear() === ano && data.getUTCMonth() === mes - 1 && data.getUTCDate() === dia;
  return confere ? texto : null;
}

// "Treinos por ficha": vazio (sem meta) ou um inteiro de 1 a 999. Devolve o número, null (vazio) ou
// undefined (inválido).
export function lerSessoesPorFicha(texto) {
  const limpo = limparEspacos(texto ?? "");
  if (limpo === "") return null;
  if (!/^\d{1,3}$/.test(limpo)) return undefined;
  const n = Number(limpo);
  return n >= 1 && n <= MAXIMO_SESSOES_POR_FICHA ? n : undefined;
}

// Confere um campo de texto de uma linha (nome do treino, professor...): obrigatório, sem caractere
// invisível e até `maximo` letras. Acrescenta o problema a `problemas`.
function conferirTexto(problemas, campo, valor, vazio, nomeDoCampo, maximo, aviso) {
  const limpo = limparEspacos(valor);
  if (!limpo) {
    problemas.push({ campo, mensagem: vazio });
  } else if (CARACTERE_INVALIDO.test(limpo)) {
    problemas.push({ campo, mensagem: `${nomeDoCampo} tem caracteres inválidos (invisíveis ou de controle).` });
  } else if (tamanho(limpo) > maximo) {
    problemas.push({ campo, mensagem: `${nomeDoCampo} tem ${tamanho(limpo)} letras; o máximo é ${maximo}${aviso}.` });
  }
}

// Confere os campos do alto que o professor preenche ao salvar. Cada problema:
// { campo: "nome-treino" | "quem-montou" | "data-inicio" | "data-fim" | "sessoes-por-ficha", mensagem }.
// `inicio` e `fim` são 'AAAA-MM-DD' (ou vazio); `sessoesPorFicha` é o texto do campo.
export function validarDadosDoTreino({ nomeTreino, montadoPor, inicio = "", fim = "", sessoesPorFicha = "" }) {
  const problemas = [];
  conferirTexto(problemas, "nome-treino", nomeTreino, "Dê um nome ao treino.", "O nome do treino", LIMITE_NOME_TREINO, " (limite do Data4U)");
  conferirTexto(problemas, "quem-montou", montadoPor, "Informe o professor que montou o treino.", "O nome do professor", LIMITE_QUEM_MONTOU, "");

  const anos = `de ${ANO_MINIMO_DO_TREINO} a ${ANO_MAXIMO_DO_TREINO}`;
  const diaInicio = lerDia(inicio);
  if (!inicio) problemas.push({ campo: "data-inicio", mensagem: "Informe a data de início do treino." });
  else if (!diaInicio) problemas.push({ campo: "data-inicio", mensagem: `A data de início é inválida (anos ${anos}).` });
  const diaFim = lerDia(fim);
  if (fim && !diaFim) problemas.push({ campo: "data-fim", mensagem: `A data do fim é inválida (anos ${anos}).` });
  else if (diaInicio && diaFim && diaFim < diaInicio) {
    // 'AAAA-MM-DD' compara como texto
    problemas.push({ campo: "data-fim", mensagem: "A data do fim não pode ser antes da data do início." });
  }
  if (lerSessoesPorFicha(sessoesPorFicha) === undefined) {
    problemas.push({
      campo: "sessoes-por-ficha",
      mensagem: `Treinos por ficha: digite um número inteiro de 1 a ${MAXIMO_SESSOES_POR_FICHA}, ou deixe em branco.`,
    });
  }
  return problemas;
}

// O pedido completo que vai para o servidor ao salvar.
export function montarPedido(estado, { nomeTreino, montadoPor, inicio = "", fim = "", sessoesPorFicha = "" }) {
  return {
    nome_treino: limparEspacos(nomeTreino),
    montado_por: limparEspacos(montadoPor),
    inicio: inicio || null,
    fim: fim || null,
    sessoes_por_ficha: lerSessoesPorFicha(sessoesPorFicha) ?? null,
    fichas: paraEnvio(estado).fichas,
  };
}

// ------------------------------------------------------------------ importar treino e treino padrão

const MAXIMO_PAUSA_EM_SEGUNDOS = MAXIMO_PAUSA * 60 + MAXIMO_PAUSA; // 59 min 59 s

// Transforma o treino que o servidor devolveu em "Importar treino" (ver app/modelos.py, `para_montar`) no
// estado da tela de montar. Devolve null se o formato não serve (nada é carregado). O intervalo vem em
// segundos e entra em minutos e segundos (90 -> 1 : 30); textos que faltam entram vazios.
export function estadoDeImportacao(treino) {
  if (!treino || typeof treino !== "object" || !Array.isArray(treino.fichas)) return null;
  const texto = (valor) => (typeof valor === "string" ? valor : "");
  let uid = 1;
  const fichas = [];
  for (const ficha of treino.fichas) {
    if (!ficha || typeof ficha.nome !== "string" || !Array.isArray(ficha.itens)) return null;
    const itens = [];
    for (const item of ficha.itens) {
      if (!item || !ehInteiro(item.exercicio_id) || typeof item.nome !== "string") return null;
      const pausa = Number.isInteger(item.pausa) && item.pausa > 0 && item.pausa <= MAXIMO_PAUSA_EM_SEGUNDOS ? item.pausa : 0;
      itens.push({
        uid: uid++,
        exercicioId: item.exercicio_id,
        nome: item.nome,
        series: texto(item.series),
        repeticoes: texto(item.repeticoes),
        carga: texto(item.carga),
        pausaMin: pausa ? String(Math.floor(pausa / 60)) : "",
        pausaSeg: pausa ? String(pausa % 60).padStart(2, "0") : "",
        observacao: texto(item.observacao),
        bloco: ehInteiro(item.bloco) ? item.bloco : null,
        ...(item.indisponivel === true ? { indisponivel: true } : {}),
      });
    }
    fichas.push({ nome: ficha.nome, itens });
  }
  // lerRascunho confere de novo tudo (quantidade de fichas e de exercícios, uids, blocos) e numera os próximos
  return lerRascunho(serializar({ proximoUid: uid, proximoBloco: 1, fichas }));
}

// A "meta" (treinos por ficha) que vem junto na importação, como texto para o campo da tela ("" = sem meta).
export function metaDaImportacao(treino) {
  const n = treino?.sessoes_por_ficha;
  return Number.isInteger(n) && n >= 1 && n <= MAXIMO_SESSOES_POR_FICHA ? String(n) : "";
}

// Quantos exercícios do treino ainda precisam ser trocados (saíram da lista de exercícios).
export function contarIndisponiveis(estado) {
  return estado.fichas.reduce((total, ficha) => total + ficha.itens.filter((i) => i.indisponivel).length, 0);
}

// Quantos exercícios há no treino todo.
export function contarExercicios(estado) {
  return estado.fichas.reduce((total, ficha) => total + ficha.itens.length, 0);
}

// Confere o nome e o professor do treino padrão (a conferência das fichas é a de `validar`).
// Cada problema: { campo: "nome-padrao" | "quem-montou", mensagem }.
export function validarDadosDoPadrao({ nomePadrao, montadoPor }) {
  const problemas = [];
  conferirTexto(problemas, "nome-padrao", nomePadrao, "Dê um nome ao treino padrão.", "O nome do treino padrão", LIMITE_NOME_TREINO, "");
  conferirTexto(problemas, "quem-montou", montadoPor, "Informe o professor que montou o treino (campo Professor).", "O nome do professor", LIMITE_QUEM_MONTOU, "");
  return problemas;
}

// O pedido que guarda o treino da tela como treino padrão (não grava nada para o aluno).
export function montarPedidoDePadrao(estado, { nomePadrao, montadoPor, sessoesPorFicha = "" }) {
  return {
    nome: limparEspacos(nomePadrao),
    montado_por: limparEspacos(montadoPor),
    sessoes_por_ficha: lerSessoesPorFicha(sessoesPorFicha) ?? null,
    fichas: paraEnvio(estado).fichas,
  };
}

// Endereço da tela de impressão do treino recém-salvo, a partir da resposta do servidor
// ({ id }). Só aceita um número inteiro positivo: qualquer outra coisa devolve null e o
// botão de imprimir não aparece (o texto da resposta nunca vira parte de um endereço).
export function enderecoDeImpressao(corpo) {
  const id = corpo?.id;
  return Number.isInteger(id) && id > 0 ? "/treinos/" + id + "/imprimir" : null;
}

export function serializar(estado) {
  return JSON.stringify(estado);
}

const ehInteiro = (x) => Number.isInteger(x) && x >= 1;

// Lê um rascunho guardado no navegador. Qualquer coisa fora do formato (arquivo
// corrompido, versão antiga, texto inventado) devolve null em vez de quebrar a tela.
export function lerRascunho(texto) {
  let dados;
  try {
    dados = JSON.parse(texto);
  } catch {
    return null;
  }
  if (!dados || typeof dados !== "object" || !Array.isArray(dados.fichas)) return null;
  if (dados.fichas.length < 1 || dados.fichas.length > MAXIMO_FICHAS) return null;

  let maiorUid = 0;
  let maiorBloco = 0;
  const uidsVistos = new Set(); // cada exercício precisa de um uid próprio
  const fichas = [];
  for (const f of dados.fichas) {
    if (!f || typeof f.nome !== "string" || !Array.isArray(f.itens)) return null;
    if (f.itens.length > MAXIMO_ITENS_POR_FICHA) return null;
    const itens = [];
    for (const i of f.itens) {
      const valido =
        i &&
        ehInteiro(i.uid) &&
        !uidsVistos.has(i.uid) &&
        ehInteiro(i.exercicioId) &&
        typeof i.nome === "string" &&
        CAMPOS_EDITAVEIS.every((c) => typeof i[c] === "string" || (CAMPOS_NOVOS.includes(c) && i[c] === undefined)) &&
        (i.bloco === null || ehInteiro(i.bloco));
      if (!valido) return null;
      uidsVistos.add(i.uid);
      maiorUid = Math.max(maiorUid, i.uid);
      if (i.bloco !== null) maiorBloco = Math.max(maiorBloco, i.bloco);
      itens.push({
        uid: i.uid,
        exercicioId: i.exercicioId,
        nome: i.nome,
        series: i.series,
        repeticoes: i.repeticoes,
        carga: i.carga,
        pausaMin: i.pausaMin ?? "",
        pausaSeg: i.pausaSeg ?? "",
        observacao: i.observacao ?? "",
        bloco: i.bloco,
        ...(i.indisponivel === true ? { indisponivel: true } : {}),
      });
    }
    const ficha = { nome: f.nome, itens };
    desfazerBlocosIncompletos(ficha);
    fichas.push(ficha);
  }
  return { proximoUid: maiorUid + 1, proximoBloco: maiorBloco + 1, fichas };
}
