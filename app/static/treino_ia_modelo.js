// Treino sob medida (IA): a parte da tela que não depende do navegador (testada à parte, em tests_js/treino_ia.test.js).
// O servidor confere tudo de novo (app/ia_treino.py); aqui só se evita mandar um pedido que já se sabe que será recusado,
// e se transforma a resposta do servidor no que a tela mostra.
import { textoDoErro } from "./api.js";
import { limparEspacos, tamanho } from "./treino_modelo.js";

export const LIMITE_DAS_OBSERVACOES = 1000; // o mesmo de app/ia_treino.py (tests/test_contrato_js_python.py confere)
export const LIMITE_DAS_RESPOSTAS = 300; // letras por resposta do professor às perguntas da IA (também conferido contra o Python)
export const LIMITE_DO_MOTIVO = 300; // letras do motivo da avaliação do rascunho (o mesmo de app/ia_retorno.py; também conferido)
export const MAXIMO_DE_RODADAS = 2; // quantas vezes a IA pode perguntar antes de entregar o treino (o servidor é quem manda; isto é o padrão)
export const INTERVALO_DA_CONSULTA_MS = 2000;
export const TEMPO_MAXIMO_DA_ESPERA_MS = 5 * 60 * 1000; // o servidor cancela o pedido que passa de 4 minutos
export const FALHAS_SEGUIDAS_PARA_DESISTIR = 4; // consultas seguidas sem resposta do servidor

// 8 ou mais algarismos seguidos (só com espaço, ponto, traço, parêntese ou barra no meio): CPF, telefone, documento.
// Uma data completa (15/03/2024) também tem 8: o professor escreve só mês e ano, ou a idade.
// Igual ao do servidor: a IA nunca recebe número que identifique o aluno.
const NUMERO_LONGO = /\d(?:[\s.\-()/]*\d){7,}/;
const COMPLEMENTO_DO_NUMERO_LONGO = "números de CPF, telefone ou documento, e datas completas como 15/03/2024 (escreva só o mês e o ano, ou a idade): a IA não precisa deles.";

// Confere o que o professor escolheu. Devolve [{ campo (id do campo na tela), mensagem }], vazio se está tudo certo.
export function validarPedido({ objetivo = "", nivel = "", dias = "", minutos = "", fichas = "", observacoes = "" } = {}) {
  const problemas = [];
  if (!objetivo) problemas.push({ campo: "ia-objetivo", mensagem: "Escolha o objetivo do aluno." });
  if (!nivel) problemas.push({ campo: "ia-nivel", mensagem: "Escolha o nível do aluno." });
  if (!dias) problemas.push({ campo: "ia-dias", mensagem: "Escolha quantos dias por semana o aluno treina." });
  if (!minutos) problemas.push({ campo: "ia-minutos", mensagem: "Escolha o tempo de cada treino." });
  // Fichas diferentes é opcional ("" = o robô decide); escolhidas, não podem passar dos dias (o servidor confere de novo).
  if (fichas && dias && Number(fichas) > Number(dias)) {
    problemas.push({ campo: "ia-fichas", mensagem: "As fichas diferentes não podem ser mais do que os dias por semana." });
  }
  const texto = limparEspacos(observacoes);
  if (tamanho(texto) > LIMITE_DAS_OBSERVACOES) {
    problemas.push({
      campo: "ia-observacoes",
      mensagem: `As observações têm ${tamanho(texto)} letras; o máximo é ${LIMITE_DAS_OBSERVACOES}.`,
    });
  } else if (NUMERO_LONGO.test(texto)) {
    problemas.push({
      campo: "ia-observacoes",
      mensagem: `Tire das observações ${COMPLEMENTO_DO_NUMERO_LONGO}`,
    });
  } else if (texto.includes("@")) {
    problemas.push({ campo: "ia-observacoes", mensagem: "Tire das observações o e-mail: a IA não precisa dele." });
  }
  return problemas;
}

// Confere as respostas do professor às perguntas da IA (uma por pergunta; resposta em branco vale).
// Devolve [{ indice (0 = primeira pergunta), mensagem }], vazio se está tudo certo. Mesmas regras de privacidade das observações.
export function validarRespostas(respostas = []) {
  const problemas = [];
  respostas.forEach((resposta, indice) => {
    const texto = limparEspacos(resposta ?? "");
    const n = indice + 1;
    if (tamanho(texto) > LIMITE_DAS_RESPOSTAS) {
      problemas.push({ indice, mensagem: `A resposta ${n} tem ${tamanho(texto)} letras; o máximo é ${LIMITE_DAS_RESPOSTAS}.` });
    } else if (NUMERO_LONGO.test(texto)) {
      problemas.push({ indice, mensagem: `Tire da resposta ${n} ${COMPLEMENTO_DO_NUMERO_LONGO}` });
    } else if (texto.includes("@")) {
      problemas.push({ indice, mensagem: `Tire da resposta ${n} o e-mail: a IA não precisa dele.` });
    }
  });
  return problemas;
}

// O corpo do pedido ao servidor (POST /api/alunos/<id>/treino-ia). Dias e minutos vão como número; `fichas_diferentes` vai
// como número ou null (null = o robô decide).
// `perguntar`: a IA pode fazer perguntas antes de montar. `rodadas`: o que já foi perguntado e respondido,
// [{ perguntas: [texto], respostas: [texto] }] (o servidor não guarda a conversa: o navegador manda tudo de novo a cada chamada).
export function montarPedido({ objetivo, nivel, dias, minutos, fichas = "", observacoes = "" }, { perguntar = false, rodadas = [] } = {}) {
  return {
    objetivo,
    nivel,
    dias: Number(dias),
    minutos: Number(minutos),
    fichas_diferentes: fichas ? Number(fichas) : null,
    observacoes: limparEspacos(observacoes),
    perguntar: perguntar === true,
    rodadas: rodadas.map((r) => ({
      perguntas: r.perguntas.map((p) => limparEspacos(p)),
      respostas: r.respostas.map((x) => limparEspacos(x ?? "")),
    })),
  };
}

// A resposta ao pedido de um rascunho. { tipo: "aceito", pedidoId } ou { tipo: "recusado", mensagem }.
export function interpretarPedido(resposta) {
  if (resposta?.status === 202 && Number.isInteger(resposta.corpo?.pedido_id) && resposta.corpo.pedido_id > 0) {
    return { tipo: "aceito", pedidoId: resposta.corpo.pedido_id };
  }
  return { tipo: "recusado", mensagem: textoDoErro(resposta ?? { status: 0, corpo: null }, "Não consegui pedir o rascunho") };
}

const textos = (lista) => (Array.isArray(lista) ? lista.filter((t) => typeof t === "string" && t.trim() !== "") : []);

// A resposta de uma consulta (GET /api/alunos/<id>/treino-ia/<pedido>):
//   { tipo: "andando" } | { tipo: "pronto", treino, resumo, alertas, removidos } | { tipo: "erro", mensagem }
//   | { tipo: "perguntas", perguntas, rodada, maximoDeRodadas } (a IA quer saber mais antes de montar)
//   | { tipo: "falha", mensagem } (o servidor não respondeu direito: vale tentar de novo).
export function interpretarConsulta(resposta) {
  if (resposta?.status === 404) return { tipo: "erro", mensagem: "O pedido sumiu do servidor. Peça o rascunho de novo." };
  if (resposta?.status === 401) return { tipo: "erro", mensagem: textoDoErro(resposta, "") };
  const corpo = resposta?.status === 200 ? resposta.corpo : null;
  if (corpo?.situacao === "andando") return { tipo: "andando" };
  if (corpo?.situacao === "erro" && typeof corpo.erro === "string") return { tipo: "erro", mensagem: corpo.erro };
  if (corpo?.situacao === "pronto" && Array.isArray(corpo.perguntas)) {
    const perguntas = textos(corpo.perguntas);
    if (perguntas.length > 0 && Number.isInteger(corpo.rodada) && corpo.rodada >= 1) {
      const maximo = Number.isInteger(corpo.maximo_de_rodadas) && corpo.maximo_de_rodadas >= corpo.rodada ? corpo.maximo_de_rodadas : MAXIMO_DE_RODADAS;
      return { tipo: "perguntas", perguntas, rodada: corpo.rodada, maximoDeRodadas: maximo };
    }
    return { tipo: "falha", mensagem: "O servidor mandou perguntas num formato inesperado" };
  }
  if (corpo?.situacao === "pronto" && corpo.treino && typeof corpo.treino === "object" && Array.isArray(corpo.treino.fichas)) {
    return {
      tipo: "pronto",
      treino: corpo.treino,
      resumo: typeof corpo.resumo === "string" ? corpo.resumo : "",
      alertas: textos(corpo.alertas),
      removidos: Number.isInteger(corpo.removidos) && corpo.removidos > 0 ? corpo.removidos : 0,
    };
  }
  return { tipo: "falha", mensagem: textoDoErro(resposta ?? { status: 0, corpo: null }, "O servidor respondeu algo inesperado") };
}

// `perguntando`: a IA ainda pode fazer perguntas, então ninguém sabe se ela vai perguntar ou entregar o treino.
export function textoDeEspera(segundos, perguntando = false) {
  const frase = perguntando ? "A IA está analisando o pedido" : "Montando o treino";
  return `${frase}… ${segundos} s. Pode levar cerca de um minuto; não feche esta tela.`;
}

// O que a IA já perguntou e o professor já respondeu, para mostrar na tela: [{ pergunta, resposta ("" = sem resposta) }].
export function historicoDaConversa(rodadas = []) {
  return rodadas.flatMap((r) => r.perguntas.map((pergunta, i) => ({ pergunta, resposta: limparEspacos(r.respostas[i] ?? "") })));
}

// O selo da rodada de perguntas na tela: "Rodada 1 de 2" ou, na última, "Última rodada (2 de 2)".
export function textoDaRodada({ rodada, maximoDeRodadas }) {
  return rodada >= maximoDeRodadas ? `Última rodada (${rodada} de ${maximoDeRodadas})` : `Rodada ${rodada} de ${maximoDeRodadas}`;
}

const plural = (n, singular, pluralTexto) => `${n} ${n === 1 ? singular : pluralTexto}`;

// A faixa que fica no alto da montagem depois de o rascunho entrar na tela. `atencao` = true quando há algo que o professor
// precisa ver (alerta da IA ou exercício que a IA inventou e foi tirado): a faixa fica laranja em vez de verde.
export function avisoDoRascunho({ treino, resumo = "", alertas = [], removidos = 0 }) {
  const fichas = treino.fichas.length;
  const exercicios = treino.fichas.reduce((soma, ficha) => soma + ficha.itens.length, 0);
  let texto =
    `Rascunho montado pela IA (${plural(fichas, "ficha", "fichas")}, ${plural(exercicios, "exercício", "exercícios")}). ` +
    "Ele pode ter erro: confira tudo e ajuste antes de salvar.";
  if (resumo) texto += ` ${resumo}`;
  if (alertas.length) texto += ` Atenção: ${alertas.join(" ")}`;
  if (removidos > 0) {
    texto +=
      removidos === 1
        ? " A IA sugeriu 1 exercício que não existe na academia; ele foi tirado."
        : ` A IA sugeriu ${removidos} exercícios que não existem na academia; eles foram tirados.`;
  }
  return { texto, atencao: alertas.length > 0 || removidos > 0 };
}

// ------------------------------------------------------------------ avaliar o rascunho (app/ia_retorno.py)
// Depois de salvar, o professor diz se o rascunho da IA ajudou. O servidor não guarda aluno nem professor junto da nota.

// As três notas, na ordem da tela. `pedeMotivo`: nas duas que apontam um defeito a tela abre a caixa do motivo (opcional).
export const NOTAS_DA_AVALIACAO = [
  { valor: "serviu", rotulo: "Serviu", pedeMotivo: false },
  { valor: "com_ajustes", rotulo: "Serviu com ajustes", pedeMotivo: true },
  { valor: "nao_serviu", rotulo: "Não serviu", pedeMotivo: true },
];

// Confere o motivo escrito pelo professor (opcional). Devolve o texto do problema, ou "" se está tudo certo.
// Mesmas regras do servidor: nada que identifique o aluno (o nome dele só o servidor sabe conferir).
export function validarMotivo(motivo = "") {
  const texto = limparEspacos(motivo);
  if (tamanho(texto) > LIMITE_DO_MOTIVO) return `O motivo tem ${tamanho(texto)} letras; o máximo é ${LIMITE_DO_MOTIVO}.`;
  if (NUMERO_LONGO.test(texto)) {
    return "Tire do motivo números de CPF, telefone ou documento, e datas completas como 15/03/2024: ele não deve identificar o aluno.";
  }
  if (texto.includes("@")) return "Tire do motivo o e-mail: ele não deve identificar o aluno.";
  return "";
}

// O corpo da avaliação (POST /api/alunos/<id>/treino-ia/<pedido>/avaliacao). Motivo em branco não vai.
export function montarAvaliacao(nota, motivo = "") {
  const texto = limparEspacos(motivo);
  return texto ? { nota, motivo: texto } : { nota };
}

// A resposta ao envio da avaliação: { tipo: "enviada" } | { tipo: "ja_avaliado", mensagem } | { tipo: "recusada", mensagem }.
// "recusada" deixa o professor tentar de novo (motivo a corrigir, rede, computador sem autorização); "ja_avaliado" e a falta do rascunho encerram.
export function interpretarAvaliacao(resposta) {
  if (resposta?.status === 201) return { tipo: "enviada" };
  const lida = resposta ?? { status: 0, corpo: null };
  if (lida.status === 409) return { tipo: "ja_avaliado", mensagem: textoDoErro(lida, "Este rascunho já foi avaliado") };
  if (lida.status === 404) {
    return { tipo: "sem_rascunho", mensagem: textoDoErro(lida, "Este rascunho não existe mais, então não dá para avaliar") };
  }
  return { tipo: "recusada", mensagem: textoDoErro(lida, "Não consegui enviar a avaliação") };
}

export function textoDaAvaliacaoEnviada(nota) {
  const rotulo = NOTAS_DA_AVALIACAO.find((n) => n.valor === nota)?.rotulo ?? "";
  return `Avaliação enviada${rotulo ? ` (${rotulo})` : ""}. Obrigado: é assim que o robô aprende a montar treinos melhores.`;
}
