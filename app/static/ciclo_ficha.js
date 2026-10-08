// Ficha do aluno: botões "Concluído" (o treino ativo vai para o histórico) e "Reativar" (desfaz).
// A regra de verdade está no servidor (app/ciclo.py); aqui só pedimos e recarregamos a página.
import { enviarJson, MENSAGEM_NAO_AUTORIZADO } from "./api.js";

const SEM_REDE =
  "Não consegui falar com o servidor (sem resposta ou sem rede). Confira a rede, atualize a página e veja se o treino mudou antes de tentar de novo.";

// Faz o pedido e devolve null se deu certo, ou o texto do erro para mostrar.
async function pedir(treinoId, acao) {
  let resposta;
  try {
    resposta = await enviarJson(`/api/treinos/${encodeURIComponent(treinoId)}/${acao}`, {});
  } catch {
    return SEM_REDE;
  }
  if (resposta.status === 200) return null;
  if (resposta.status === 401) return MENSAGEM_NAO_AUTORIZADO;
  return typeof resposta.corpo?.erro === "string"
    ? resposta.corpo.erro
    : `O servidor devolveu um erro (código ${resposta.status}). Nada foi alterado.`;
}

// Cada treino tem a sua barra de ações (.acoes-treino).
for (const barra of document.querySelectorAll(".acoes-treino")) {
  const botaoConcluir = barra.querySelector(".botao-concluir");
  const botaoReativar = barra.querySelector(".botao-reativar");
  const confirmacao = barra.querySelector(".confirmar-concluir");
  const aviso = barra.querySelector(".aviso-acao");
  let enviando = false;

  async function executar(botao, treinoId, acao) {
    if (enviando) return; // clique duplo não manda duas vezes
    enviando = true;
    botao.disabled = true;
    aviso.classList.remove("aviso-erro");
    aviso.textContent = "Salvando…";
    const erro = await pedir(treinoId, acao);
    if (erro === null) {
      window.location.reload(); // a tabela, os selos e o aviso de troca são redesenhados pelo servidor
      return;
    }
    aviso.textContent = erro;
    aviso.classList.add("aviso-erro");
    botao.disabled = false;
    enviando = false;
  }

  if (botaoConcluir) {
    // Dois passos: o primeiro clique só pergunta (um clique errado tiraria o treino do aluno).
    botaoConcluir.addEventListener("click", () => {
      botaoConcluir.hidden = true;
      confirmacao.hidden = false;
      confirmacao.querySelector(".nao-concluir").focus();
    });
    confirmacao.querySelector(".nao-concluir").addEventListener("click", () => {
      confirmacao.hidden = true;
      botaoConcluir.hidden = false;
      botaoConcluir.focus();
    });
    const sim = confirmacao.querySelector(".sim-concluir");
    sim.addEventListener("click", () => executar(sim, sim.dataset.treino, "concluir"));
  }
  if (botaoReativar) {
    botaoReativar.addEventListener("click", () => executar(botaoReativar, botaoReativar.dataset.treino, "reativar"));
  }
}
