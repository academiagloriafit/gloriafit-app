// Cartão "Treino sob medida (IA)" da tela de lançar treino: o professor responde 4 perguntas, o servidor pede um
// RASCUNHO ao Claude e o rascunho entra na tela de montar, como um treino importado. Nada é gravado para o aluno.
//
// A IA leva dezenas de segundos para responder (e o servidor não segura um pedido tão longo), então são dois passos:
// 1) POST /api/alunos/<id>/treino-ia devolve na hora o número do pedido;
// 2) esta tela pergunta de 2 em 2 segundos (GET .../treino-ia/<pedido>) até o rascunho ficar pronto, dar erro ou passar do prazo.
// A lógica sem tela (conferir o formulário, ler as respostas, escrever o aviso) está em treino_ia_modelo.js.
import { buscarJson, enviarJson } from "./api.js";
import * as T from "./treino_ia_modelo.js";

const SEM_REDE = "Não consegui falar com o servidor (sem resposta ou sem rede). Confira a rede e tente de novo.";
const pegar = (id) => document.getElementById(id);
const esperar = (ms) => new Promise((resolver) => setTimeout(resolver, ms));

// alunoId: o aluno da tela.
// temTreinoNaTela(): true se já há exercícios na tela (o rascunho vai substituí-los: pede confirmação antes de gastar).
// aoCarregar(resultado): põe o rascunho na tela; `resultado` = { treino, resumo, alertas, removidos } (o que o servidor devolveu).
// Devolve null se deu certo ou o texto do problema.
export function iniciarTreinoIa({ alunoId, temTreinoNaTela, aoCarregar }) {
  const botaoAbrir = pegar("abrir-ia");
  const painel = pegar("painel-ia");
  const botaoGerar = pegar("gerar-ia");
  const botaoFechar = pegar("fechar-ia");
  const aviso = pegar("aviso-ia");
  const confirmacao = pegar("confirmar-ia");
  const campos = {
    objetivo: pegar("ia-objetivo"),
    nivel: pegar("ia-nivel"),
    dias: pegar("ia-dias"),
    minutos: pegar("ia-minutos"),
    observacoes: pegar("ia-observacoes"),
  };
  const aEscolha = () => Object.fromEntries(Object.entries(campos).map(([nome, campo]) => [nome, campo.value]));

  let ocupado = false; // um pedido por vez: clique duplo não gasta duas vezes

  function avisar(texto, erro = false) {
    aviso.textContent = texto;
    aviso.classList.toggle("aviso-erro", erro);
  }

  function marcarInvalidos(problemas) {
    const invalidos = new Set(problemas.map((p) => p.campo));
    for (const campo of Object.values(campos)) campo.setAttribute("aria-invalid", String(invalidos.has(campo.id)));
  }

  function travar(travado) {
    ocupado = travado;
    botaoGerar.disabled = travado;
    botaoFechar.disabled = travado;
    for (const campo of Object.values(campos)) campo.disabled = travado;
  }

  // ---------------------------------------------------------------- abrir e fechar

  function abrir() {
    painel.hidden = false;
    botaoAbrir.setAttribute("aria-expanded", "true");
    campos.objetivo.focus();
  }

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

  async function esperarOResultado(pedidoId) {
    const inicio = Date.now();
    let falhas = 0;
    for (;;) {
      avisar(T.textoDeEspera(Math.round((Date.now() - inicio) / 1000)));
      await esperar(T.INTERVALO_DA_CONSULTA_MS);
      if (Date.now() - inicio > T.TEMPO_MAXIMO_DA_ESPERA_MS) {
        return { tipo: "erro", mensagem: "A IA demorou demais. Tente de novo (se repetir, avise o Thiago)." };
      }
      let resposta;
      try {
        resposta = await buscarJson(`/api/alunos/${encodeURIComponent(alunoId)}/treino-ia/${encodeURIComponent(pedidoId)}`);
      } catch {
        resposta = null;
      }
      const lida = resposta === null ? { tipo: "falha", mensagem: SEM_REDE } : T.interpretarConsulta(resposta);
      if (lida.tipo !== "falha") {
        falhas = 0;
        if (lida.tipo !== "andando") return lida;
      } else if (++falhas >= T.FALHAS_SEGUIDAS_PARA_DESISTIR) {
        return { tipo: "erro", mensagem: `${lida.mensagem} O rascunho pode ter ficado pronto no servidor, mas não consegui buscar.` };
      }
    }
  }

  async function gerar() {
    if (ocupado) return;
    confirmacao.hidden = true;
    const escolha = aEscolha();
    const problemas = T.validarPedido(escolha);
    marcarInvalidos(problemas);
    if (problemas.length) {
      avisar(problemas[0].mensagem, true);
      pegar(problemas[0].campo).focus();
      return;
    }
    travar(true);
    avisar(T.textoDeEspera(0));
    try {
      let resposta;
      try {
        resposta = await enviarJson(`/api/alunos/${encodeURIComponent(alunoId)}/treino-ia`, T.montarPedido(escolha));
      } catch {
        avisar(SEM_REDE, true);
        return;
      }
      const pedido = T.interpretarPedido(resposta);
      if (pedido.tipo !== "aceito") {
        avisar(pedido.mensagem, true);
        return;
      }
      const resultado = await esperarOResultado(pedido.pedidoId);
      if (resultado.tipo !== "pronto") {
        avisar(resultado.mensagem, true);
        return;
      }
      const problema = aoCarregar(resultado);
      if (problema !== null) {
        avisar(problema, true);
        return;
      }
      fechar();
    } finally {
      travar(false);
    }
  }

  // Já há exercícios na tela? Pergunta antes de pedir (assim não se gasta com um rascunho que seria recusado).
  botaoGerar.addEventListener("click", () => {
    if (temTreinoNaTela()) {
      confirmacao.hidden = false;
      pegar("confirmar-gerar-ia").focus();
    } else {
      gerar();
    }
  });
  pegar("confirmar-gerar-ia").addEventListener("click", gerar);
  pegar("cancelar-gerar-ia").addEventListener("click", () => {
    confirmacao.hidden = true;
    botaoGerar.focus();
  });
}
