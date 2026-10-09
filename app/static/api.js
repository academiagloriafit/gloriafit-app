// Conversa com o servidor em JSON: enviarJson (POST) e buscarJson (GET).

export const TEMPO_MAXIMO_MS = 20000; // se o servidor não responder em 20 s, desistimos

// Mostrada quando o servidor responde 401: o computador perdeu a autorização (foi
// revogada, ou ficou muito tempo sem uso). Quem precisa de um código novo é o computador.
export const MENSAGEM_NAO_AUTORIZADO =
  "Este computador não está mais autorizado. Abra o endereço /autorizar e digite um código novo.";

// Faz um POST com `dados` em JSON. Devolve { status, corpo }, onde `corpo` é o JSON
// da resposta (ou null se a resposta não for JSON, como uma página de erro).
// `tempoMaximoMs` (opcional) troca o prazo padrão, para pedidos grandes como o de atualizar alunos.
// Se a rede cair ou o servidor não responder a tempo, a promessa é REJEITADA:
// quem chama precisa tratar, porque nesse caso não sabemos se o servidor gravou.
export async function enviarJson(url, dados, tempoMaximoMs = TEMPO_MAXIMO_MS) {
  const controle = new AbortController();
  const relogio = setTimeout(() => controle.abort(), tempoMaximoMs);
  try {
    const resposta = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(dados),
      credentials: "same-origin",
      signal: controle.signal,
    });
    let corpo = null;
    try {
      corpo = await resposta.json();
    } catch {
      /* não é JSON (ex.: página de erro): fica null */
    }
    return { status: resposta.status, corpo };
  } finally {
    clearTimeout(relogio);
  }
}

// Faz um GET e devolve { status, corpo }, como enviarJson. `sinal` (opcional) é o AbortSignal de quem quer poder
// cancelar a busca antiga (digitou mais uma letra); cancelar rejeita a promessa com AbortError. Se a rede cair ou o
// servidor não responder a tempo, a promessa é rejeitada: quem chama trata.
export async function buscarJson(url, sinal = null, tempoMaximoMs = TEMPO_MAXIMO_MS) {
  const controle = new AbortController();
  const relogio = setTimeout(() => controle.abort(), tempoMaximoMs);
  const aoCancelar = () => controle.abort();
  if (sinal) {
    if (sinal.aborted) controle.abort();
    else sinal.addEventListener("abort", aoCancelar, { once: true });
  }
  try {
    const resposta = await fetch(url, { credentials: "same-origin", signal: controle.signal });
    let corpo = null;
    try {
      corpo = await resposta.json();
    } catch {
      /* não é JSON (ex.: página de erro): fica null */
    }
    return { status: resposta.status, corpo };
  } finally {
    clearTimeout(relogio);
    if (sinal) sinal.removeEventListener("abort", aoCancelar);
  }
}

// Texto do erro para mostrar ao professor, a partir da resposta do servidor ({ status, corpo }):
// 401 -> pedir autorização; senão as mensagens em `erros` (lista) ou `erro` (uma só); senão a frase
// `quandoNaoDizNada` com o código.
export function textoDoErro(resposta, quandoNaoDizNada) {
  if (resposta.status === 401) return MENSAGEM_NAO_AUTORIZADO;
  const corpo = resposta.corpo;
  if (Array.isArray(corpo?.erros)) {
    const mensagens = corpo.erros.filter((m) => typeof m === "string");
    if (mensagens.length) return mensagens.join(" ");
  }
  if (typeof corpo?.erro === "string") return corpo.erro;
  return `${quandoNaoDizNada} (código ${resposta.status}).`;
}
