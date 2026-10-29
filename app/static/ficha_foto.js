// Ficha do aluno: o professor tira a foto que o aluno escolheu no app (ex.: não é o rosto dele) e volta a valer a da catraca
// (29/10/2026). Pergunta antes, na própria página (o navegador do app não mostra janelas de confirmação).
import { enviarJson, MENSAGEM_NAO_AUTORIZADO } from "./api.js";

const aviso = document.getElementById("foto-do-aluno-aviso");
if (aviso) {
  const alunoId = aviso.dataset.aluno;
  const texto = document.getElementById("foto-do-aluno-texto");
  const botao = document.getElementById("foto-voltar-catraca");
  const confirma = document.getElementById("foto-voltar-confirma");
  const sim = document.getElementById("foto-voltar-sim");
  const nao = document.getElementById("foto-voltar-nao");

  const perguntar = (ligado) => {
    confirma.hidden = !ligado;
    botao.hidden = ligado;
  };
  botao.addEventListener("click", () => perguntar(true));
  nao.addEventListener("click", () => perguntar(false));
  sim.addEventListener("click", async () => {
    sim.disabled = true;
    try {
      const { status, corpo } = await enviarJson(`/api/alunos/${encodeURIComponent(alunoId)}/foto/catraca`, {});
      if (status === 401) {
        texto.textContent = MENSAGEM_NAO_AUTORIZADO;
      } else if (status === 200 && corpo && corpo.ok) {
        // troca as fotos da página pela da catraca (ou pelas iniciais, se não houver): recarregar é o jeito mais simples
        window.location.reload();
        return;
      } else {
        texto.textContent = "Não deu para tirar a foto agora. Tente de novo.";
      }
    } catch {
      texto.textContent = "Sem conexão. A foto não foi tirada; tente de novo.";
    }
    sim.disabled = false;
    perguntar(false);
  });
}
