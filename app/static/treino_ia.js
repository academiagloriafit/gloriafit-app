// Cartão "Treino sob medida (IA)" da tela de lançar treino. O professor escolhe 4 coisas, a IA lê o treino anterior do aluno e
// pode fazer até 2 rodadas de PERGUNTAS ao professor antes de entregar um RASCUNHO, que entra na tela de montar como um treino
// importado. Nada é gravado para o aluno.
//
// A IA leva dezenas de segundos para responder (e o servidor não segura um pedido tão longo), então cada chamada tem dois passos:
// 1) POST /api/alunos/<id>/treino-ia devolve na hora o número do pedido;
// 2) esta tela pergunta de 2 em 2 segundos (GET .../treino-ia/<pedido>) até o resultado ficar pronto, dar erro ou passar do prazo.
// O resultado é o rascunho OU as perguntas da IA. O servidor NÃO guarda a conversa: quem guarda é esta tela (`rodadas`), que manda
// tudo de novo a cada chamada. Fechar ou recarregar a página apaga a conversa DESTA TELA. Mas, quando o professor salva o treino feito com o rascunho,
// o servidor guarda no histórico do treino (app/ia_historico.py) o que foi escrito e respondido, para ser consultado na ficha do aluno.
// A lógica sem tela (conferir o formulário, ler as respostas, escrever o aviso) está em treino_ia_modelo.js.
import { buscarJson, enviarJson } from "./api.js";
import * as T from "./treino_ia_modelo.js";

const SEM_REDE = "Não consegui falar com o servidor (sem resposta ou sem rede). Confira a rede e tente de novo.";
const pegar = (id) => document.getElementById(id);
const esperar = (ms) => new Promise((resolver) => setTimeout(resolver, ms));

// Cria um elemento com texto puro. Os textos das perguntas vêm da IA: nunca entram na tela como HTML.
function elemento(tag, classe, texto) {
  const el = document.createElement(tag);
  if (classe) el.className = classe;
  if (texto !== undefined) el.textContent = texto;
  return el;
}

// alunoId: o aluno da tela.
// temTreinoNaTela(): true se já há exercícios na tela (o rascunho vai substituí-los: pede confirmação antes de gastar).
// aoCarregar(resultado): põe o rascunho na tela; `resultado` = { treino, resumo, alertas, removidos, pedidoId } (o que o servidor devolveu
// e o número do pedido, que a tela guarda para o servidor comparar o rascunho com o treino salvo e para a avaliação).
// Devolve null se deu certo ou o texto do problema.
export function iniciarTreinoIa({ alunoId, temTreinoNaTela, aoCarregar }) {
  const botaoAbrir = pegar("abrir-ia");
  const painel = pegar("painel-ia");
  const botaoGerar = pegar("gerar-ia");
  const botaoDireto = pegar("montar-direto-ia");
  const botaoFechar = pegar("fechar-ia");
  const acoes = pegar("acoes-ia");
  const aviso = pegar("aviso-ia");
  const confirmacao = pegar("confirmar-ia");
  const conversa = pegar("conversa-ia");
  const historico = pegar("historico-ia");
  const listaDePerguntas = pegar("perguntas-ia");
  const seloDaRodada = pegar("rodada-ia");
  const botaoEnviar = pegar("enviar-respostas-ia");
  const botaoAgora = pegar("montar-agora-ia");
  const botaoRecomecar = pegar("mudar-pedido-ia");
  const campos = {
    objetivo: pegar("ia-objetivo"),
    nivel: pegar("ia-nivel"),
    dias: pegar("ia-dias"),
    minutos: pegar("ia-minutos"),
    fichas: pegar("ia-fichas"),
    observacoes: pegar("ia-observacoes"),
  };
  const aEscolha = () => Object.fromEntries(Object.entries(campos).map(([nome, campo]) => [nome, campo.value]));
  const urlDosPedidos = `/api/alunos/${encodeURIComponent(alunoId)}/treino-ia`;

  let ocupado = false; // um pedido por vez: clique duplo não gasta duas vezes
  let rodadas = []; // a conversa até agora: [{ perguntas, respostas }] (só as rodadas que o professor já respondeu)
  let atual = null; // as perguntas que a IA fez e esperam resposta: { perguntas, rodada, maximoDeRodadas }, ou null
  let modoPendente = true; // o que o professor clicou antes da pergunta "vai substituir?": true = Gerar rascunho, false = Montar direto
  let camposDasRespostas = []; // as caixas de resposta (uma por pergunta)

  function avisar(texto, erro = false) {
    aviso.textContent = texto;
    aviso.classList.toggle("aviso-erro", erro);
  }

  function marcarInvalidos(problemas) {
    const invalidos = new Set(problemas.map((p) => p.campo));
    for (const campo of Object.values(campos)) campo.setAttribute("aria-invalid", String(invalidos.has(campo.id)));
  }

  // Enquanto a IA espera as respostas, o pedido (objetivo, nível...) fica travado: a conversa é sobre ESTE pedido.
  function atualizarTravas() {
    for (const campo of Object.values(campos)) campo.disabled = ocupado || atual !== null;
    for (const botao of [botaoGerar, botaoDireto, botaoFechar, botaoEnviar, botaoAgora, botaoRecomecar]) botao.disabled = ocupado;
    for (const caixa of camposDasRespostas) caixa.disabled = ocupado;
  }

  function travar(travado) {
    ocupado = travado;
    atualizarTravas();
  }

  // ---------------------------------------------------------------- a conversa na tela

  function desenharConversa() {
    const conversando = atual !== null;
    conversa.hidden = !conversando;
    acoes.hidden = conversando;
    historico.replaceChildren();
    listaDePerguntas.replaceChildren();
    camposDasRespostas = [];
    if (conversando) {
      const jaRespondido = T.historicoDaConversa(rodadas);
      historico.hidden = jaRespondido.length === 0;
      for (const { pergunta, resposta } of jaRespondido) {
        const item = elemento("li", "historico-item");
        item.append(
          elemento("span", "historico-pergunta", pergunta),
          elemento("span", resposta ? "historico-resposta" : "historico-resposta historico-vazia", resposta || "(sem resposta)"),
        );
        historico.append(item);
      }
      atual.perguntas.forEach((pergunta, i) => {
        const campo = elemento("div", "campo");
        const rotulo = elemento("label", "", pergunta);
        const caixa = elemento("textarea");
        caixa.id = `ia-resposta-${i + 1}`;
        caixa.rows = 2;
        caixa.maxLength = T.LIMITE_DAS_RESPOSTAS;
        rotulo.htmlFor = caixa.id;
        campo.append(rotulo, caixa);
        listaDePerguntas.append(campo);
        camposDasRespostas.push(caixa);
      });
      seloDaRodada.textContent = T.textoDaRodada(atual);
      const ultima = atual.rodada >= atual.maximoDeRodadas;
      botaoAgora.hidden = ultima; // na última rodada a IA não pode mais perguntar: "Enviar" já manda montar
      botaoEnviar.textContent = ultima ? "Enviar respostas e montar o treino" : "Enviar respostas";
    }
    atualizarTravas();
  }

  function recomecar() {
    rodadas = [];
    atual = null;
    desenharConversa();
  }

  // ---------------------------------------------------------------- abrir e fechar

  function abrir() {
    painel.hidden = false;
    botaoAbrir.setAttribute("aria-expanded", "true");
    (camposDasRespostas[0] ?? campos.objetivo).focus();
  }

  // Fechar só esconde o cartão: a conversa em andamento continua lá quando o professor abrir de novo.
  function fechar() {
    painel.hidden = true;
    confirmacao.hidden = true;
    botaoAbrir.setAttribute("aria-expanded", "false");
    avisar("");
  }

  botaoAbrir.addEventListener("click", () => (painel.hidden ? abrir() : ocupado || fechar()));
  botaoFechar.addEventListener("click", () => {
    fechar();
    botaoAbrir.focus();
  });

  // ---------------------------------------------------------------- pedir e esperar

  async function esperarOResultado(pedidoId, perguntando) {
    const inicio = Date.now();
    let falhas = 0;
    for (;;) {
      avisar(T.textoDeEspera(Math.round((Date.now() - inicio) / 1000), perguntando));
      await esperar(T.INTERVALO_DA_CONSULTA_MS);
      if (Date.now() - inicio > T.TEMPO_MAXIMO_DA_ESPERA_MS) {
        return { tipo: "erro", mensagem: "A IA demorou demais. Tente de novo (se repetir, avise o Thiago)." };
      }
      let resposta;
      try {
        resposta = await buscarJson(`${urlDosPedidos}/${encodeURIComponent(pedidoId)}`);
      } catch {
        resposta = null;
      }
      const lida = resposta === null ? { tipo: "falha", mensagem: SEM_REDE } : T.interpretarConsulta(resposta);
      if (lida.tipo !== "falha") {
        falhas = 0;
        if (lida.tipo !== "andando") return { ...lida, pedidoId };
      } else if (++falhas >= T.FALHAS_SEGUIDAS_PARA_DESISTIR) {
        return { tipo: "erro", mensagem: `${lida.mensagem} O resultado pode ter ficado pronto no servidor, mas não consegui buscar.` };
      }
    }
  }

  // Uma chamada à IA com a conversa `rodadasDoPedido`. Devolve { tipo: "pronto", ... } | { tipo: "perguntas", ... } | { tipo: "erro", mensagem }.
  // `perguntar`: a IA pode perguntar (só vale se ainda sobrar rodada).
  async function conversar(perguntar, rodadasDoPedido) {
    const podePerguntar = perguntar && rodadasDoPedido.length < T.MAXIMO_DE_RODADAS;
    travar(true);
    avisar(T.textoDeEspera(0, podePerguntar));
    try {
      let resposta;
      try {
        resposta = await enviarJson(urlDosPedidos, T.montarPedido(aEscolha(), { perguntar, rodadas: rodadasDoPedido }));
      } catch {
        return { tipo: "erro", mensagem: SEM_REDE };
      }
      const pedido = T.interpretarPedido(resposta);
      if (pedido.tipo !== "aceito") return { tipo: "erro", mensagem: pedido.mensagem };
      return await esperarOResultado(pedido.pedidoId, podePerguntar);
    } finally {
      travar(false);
    }
  }

  // O que fazer com o resultado. `rodadasDoPedido`: a conversa que foi enviada (vira a conversa da tela se a IA perguntar mais).
  // Se deu erro, nada muda: as respostas digitadas continuam nas caixas para o professor tentar de novo.
  function tratar(resultado, rodadasDoPedido) {
    if (resultado.tipo === "perguntas") {
      rodadas = rodadasDoPedido;
      atual = { perguntas: resultado.perguntas, rodada: resultado.rodada, maximoDeRodadas: resultado.maximoDeRodadas };
      desenharConversa();
      const n = resultado.perguntas.length;
      avisar(`A IA fez ${n} ${n === 1 ? "pergunta" : "perguntas"}. Responda abaixo, sem escrever nome, CPF nem telefone do aluno.`);
      camposDasRespostas[0].focus();
      return;
    }
    if (resultado.tipo !== "pronto") {
      avisar(resultado.mensagem, true);
      return;
    }
    const problema = aoCarregar(resultado);
    if (problema !== null) {
      avisar(problema, true);
      return;
    }
    recomecar();
    fechar();
  }

  // Do formulário: a primeira chamada da conversa.
  async function comecar(perguntar) {
    if (ocupado || atual !== null) return;
    confirmacao.hidden = true;
    const escolha = aEscolha();
    const problemas = T.validarPedido(escolha);
    marcarInvalidos(problemas);
    if (problemas.length) {
      avisar(problemas[0].mensagem, true);
      pegar(problemas[0].campo).focus();
      return;
    }
    tratar(await conversar(perguntar, []), []);
  }

  // Das caixas de resposta: manda as respostas e deixa a IA perguntar de novo ou montar. `montarAgora`: sem mais perguntas.
  async function responder(montarAgora) {
    if (ocupado || atual === null) return;
    const respostas = camposDasRespostas.map((caixa) => caixa.value);
    const problemas = T.validarRespostas(respostas);
    camposDasRespostas.forEach((caixa, i) => caixa.setAttribute("aria-invalid", String(problemas.some((p) => p.indice === i))));
    if (problemas.length) {
      avisar(problemas[0].mensagem, true);
      camposDasRespostas[problemas[0].indice].focus();
      return;
    }
    const depois = [...rodadas, { perguntas: atual.perguntas, respostas }];
    tratar(await conversar(!montarAgora, depois), depois);
  }

  // Já há exercícios na tela? Pergunta antes de pedir (assim não se gasta com um rascunho que seria recusado).
  function iniciar(perguntar) {
    if (temTreinoNaTela()) {
      modoPendente = perguntar;
      confirmacao.hidden = false;
      pegar("confirmar-gerar-ia").focus();
    } else {
      comecar(perguntar);
    }
  }

  botaoGerar.addEventListener("click", () => iniciar(true));
  botaoDireto.addEventListener("click", () => iniciar(false));
  pegar("confirmar-gerar-ia").addEventListener("click", () => comecar(modoPendente));
  pegar("cancelar-gerar-ia").addEventListener("click", () => {
    confirmacao.hidden = true;
    botaoGerar.focus();
  });
  botaoEnviar.addEventListener("click", () => responder(false));
  botaoAgora.addEventListener("click", () => responder(true));
  botaoRecomecar.addEventListener("click", () => {
    recomecar();
    avisar("");
    campos.objetivo.focus();
  });
}
