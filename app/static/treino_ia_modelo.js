// Treino sob medida (IA): a parte da tela que não depende do navegador (testada à parte, em tests_js/treino_ia.test.js).
// O servidor confere tudo de novo (app/ia_treino.py); aqui só se evita mandar um pedido que já se sabe que será recusado,
// e se transforma a resposta do servidor no que a tela mostra.
import { textoDoErro } from "./api.js";
import { limparEspacos, tamanho } from "./treino_modelo.js";

export const LIMITE_DAS_OBSERVACOES = 300; // o mesmo de app/ia_treino.py (tests/test_contrato_js_python.py confere)
export const INTERVALO_DA_CONSULTA_MS = 2000;
export const TEMPO_MAXIMO_DA_ESPERA_MS = 5 * 60 * 1000; // o servidor cancela o pedido que passa de 4 minutos
export const FALHAS_SEGUIDAS_PARA_DESISTIR = 4; // consultas seguidas sem resposta do servidor

// 8 ou mais algarismos seguidos (só com espaço, ponto, traço, parêntese ou barra no meio): CPF, telefone, documento.
// Igual ao do servidor: a IA nunca recebe número que identifique o aluno.
const NUMERO_LONGO = /\d(?:[\s.\-()/]*\d){7,}/;

// Confere o que o professor escolheu. Devolve [{ campo (id do campo na tela), mensagem }], vazio se está tudo certo.
export function validarPedido({ objetivo = "", nivel = "", dias = "", minutos = "", observacoes = "" } = {}) {
  const problemas = [];
  if (!objetivo) problemas.push({ campo: "ia-objetivo", mensagem: "Escolha o objetivo do aluno." });
  if (!nivel) problemas.push({ campo: "ia-nivel", mensagem: "Escolha o nível do aluno." });
  if (!dias) problemas.push({ campo: "ia-dias", mensagem: "Escolha quantos dias por semana o aluno treina." });
  if (!minutos) problemas.push({ campo: "ia-minutos", mensagem: "Escolha o tempo de cada treino." });
  const texto = limparEspacos(observacoes);
  if (tamanho(texto) > LIMITE_DAS_OBSERVACOES) {
    problemas.push({
      campo: "ia-observacoes",
      mensagem: `As observações têm ${tamanho(texto)} letras; o máximo é ${LIMITE_DAS_OBSERVACOES}.`,
    });
  } else if (NUMERO_LONGO.test(texto)) {
    problemas.push({
      campo: "ia-observacoes",
      mensagem: "Tire das observações números de CPF, telefone ou documento: a IA não precisa deles.",
    });
  } else if (texto.includes("@")) {
    problemas.push({ campo: "ia-observacoes", mensagem: "Tire das observações o e-mail: a IA não precisa dele." });
  }
  return problemas;
}

// O corpo do pedido ao servidor (POST /api/alunos/<id>/treino-ia). Dias e minutos vão como número.
export function montarPedido({ objetivo, nivel, dias, minutos, observacoes = "" }) {
  return {
    objetivo,
    nivel,
    dias: Number(dias),
    minutos: Number(minutos),
    observacoes: limparEspacos(observacoes),
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
//   | { tipo: "falha", mensagem } (o servidor não respondeu direito: vale tentar de novo).
export function interpretarConsulta(resposta) {
  if (resposta?.status === 404) return { tipo: "erro", mensagem: "O pedido sumiu do servidor. Peça o rascunho de novo." };
  if (resposta?.status === 401) return { tipo: "erro", mensagem: textoDoErro(resposta, "") };
  const corpo = resposta?.status === 200 ? resposta.corpo : null;
  if (corpo?.situacao === "andando") return { tipo: "andando" };
  if (corpo?.situacao === "erro" && typeof corpo.erro === "string") return { tipo: "erro", mensagem: corpo.erro };
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

export function textoDeEspera(segundos) {
  return `Montando o treino… ${segundos} s. Pode levar cerca de um minuto; não feche esta tela.`;
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
