// A caixa "O rascunho da IA ajudou?" da tela "Treino salvo" (lançar treino). Só aparece quando o treino saiu de um rascunho da IA.
// O professor toca em "Serviu", "Serviu com ajustes" ou "Não serviu"; nas duas últimas pode escrever o motivo (opcional). O servidor
// guarda a nota SEM aluno e SEM professor (app/ia_retorno.py), para o Thiago rever de tempos em tempos as regras do robô.
// A lógica sem tela (as notas, o motivo, a resposta do servidor) está em treino_ia_modelo.js.
import { enviarJson } from "./api.js";
import { el } from "./dom.js";
import * as T from "./treino_ia_modelo.js";

const SEM_REDE = "Não consegui falar com o servidor (sem resposta ou sem rede). Confira a rede e tente de novo.";
const pegar = (id) => document.getElementById(id);

// alunoId: o aluno da tela (o endereço da avaliação leva o aluno só para o servidor conferir que o rascunho é dele).
// Devolve { mostrar(pedidoId) }: abre a caixa para o rascunho `pedidoId` (e a deixa em branco).
export function iniciarAvaliacaoIa({ alunoId }) {
  const caixa = pegar("avaliacao-ia");
  const grupoDeNotas = pegar("notas-ia");
  const areaDoMotivo = pegar("motivo-ia");
  const campoMotivo = pegar("motivo-ia-texto");
  const botaoEnviar = pegar("enviar-avaliacao-ia");
  const aviso = pegar("aviso-avaliacao-ia");
  let pedidoId = null;
  let escolhida = null; // { valor, rotulo, pedeMotivo }
  let enviando = false;

  const botoes = T.NOTAS_DA_AVALIACAO.map((nota) =>
    el("button", { type: "button", classe: "botao-discreto", "aria-pressed": "false", texto: nota.rotulo, aoClicar: () => escolher(nota) }),
  );
  grupoDeNotas.replaceChildren(...botoes);
  campoMotivo.maxLength = T.LIMITE_DO_MOTIVO;

  function avisar(texto, erro = false) {
    aviso.textContent = texto;
    aviso.classList.toggle("aviso-erro", erro);
  }

  function travar(travado) {
    enviando = travado;
    botoes.forEach((b) => (b.disabled = travado));
    campoMotivo.disabled = travado;
    botaoEnviar.disabled = travado;
  }

  function marcarEscolhida() {
    botoes.forEach((b, i) => b.setAttribute("aria-pressed", String(T.NOTAS_DA_AVALIACAO[i].valor === escolhida?.valor)));
  }

  function escolher(nota) {
    if (enviando) return;
    escolhida = nota;
    marcarEscolhida();
    campoMotivo.removeAttribute("aria-invalid");
    avisar("");
    areaDoMotivo.hidden = !nota.pedeMotivo;
    if (nota.pedeMotivo) campoMotivo.focus();
    else enviar(); // "Serviu" não tem o que explicar: vai direto
  }

  // O fim da conversa (enviada, já avaliada, rascunho que sumiu): some o que dava para clicar e fica só o recado.
  function encerrar(texto, erro = false) {
    grupoDeNotas.hidden = true;
    areaDoMotivo.hidden = true;
    avisar(texto, erro);
    travar(false);
  }

  async function enviar() {
    if (enviando || pedidoId === null || escolhida === null) return;
    const motivo = escolhida.pedeMotivo ? campoMotivo.value : "";
    const problema = T.validarMotivo(motivo);
    if (problema) {
      campoMotivo.setAttribute("aria-invalid", "true");
      avisar(problema, true);
      campoMotivo.focus();
      return;
    }
    campoMotivo.removeAttribute("aria-invalid");
    travar(true);
    avisar("Enviando…");
    let resposta;
    try {
      resposta = await enviarJson(
        `/api/alunos/${encodeURIComponent(alunoId)}/treino-ia/${encodeURIComponent(pedidoId)}/avaliacao`,
        T.montarAvaliacao(escolhida.valor, motivo),
      );
    } catch {
      travar(false);
      avisar(SEM_REDE, true);
      return;
    }
    const lida = T.interpretarAvaliacao(resposta);
    if (lida.tipo === "enviada") encerrar(T.textoDaAvaliacaoEnviada(escolhida.valor));
    else if (lida.tipo === "ja_avaliado") encerrar(lida.mensagem);
    else if (lida.tipo === "sem_rascunho") encerrar(lida.mensagem, true);
    else {
      travar(false);
      avisar(lida.mensagem, true);
    }
  }

  botaoEnviar.addEventListener("click", enviar);

  return {
    mostrar(pedido) {
      pedidoId = pedido;
      escolhida = null;
      campoMotivo.value = "";
      campoMotivo.removeAttribute("aria-invalid");
      grupoDeNotas.hidden = false;
      areaDoMotivo.hidden = true;
      marcarEscolhida();
      travar(false);
      avisar("");
      caixa.hidden = false;
    },
  };
}
