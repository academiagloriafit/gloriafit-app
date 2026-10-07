// Envio de JSON ao servidor (usado por salvar.js e ficha.js).

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
