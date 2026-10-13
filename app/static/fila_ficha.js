// Ficha do aluno, cartão "Fila de treino": o professor coloca o aluno numa fila (Homem, Mulher, Adolescente, Gestante,
// Grupos de risco), muda de fila ou tira o aluno da fila. Gestante e Grupos de risco pedem a liberação conferida
// (sim + data + nome do professor). A regra de verdade está no servidor (app/filas.py); aqui só pedimos e recarregamos.
import { enviarJson, textoDoErro } from "./api.js";
import { montarPedidoDaFila, validarColocarNaFila } from "./filas_modelo.js";

const SEM_REDE =
  "Não consegui falar com o servidor (sem resposta ou sem rede). Confira a rede, atualize a página e veja se a fila do aluno mudou antes de tentar de novo.";

const painel = document.getElementById("painel-fila");
if (painel) {
  const raiz = document.querySelector("[data-aluno]");
  const alunoId = raiz.dataset.aluno;
  const formulario = document.getElementById("form-fila");
  const selecao = document.getElementById("fila-escolhida");
  const campoProfessor = document.getElementById("fila-professor");
  const blocoLiberacao = document.getElementById("bloco-liberacao");
  const campoConferida = document.getElementById("fila-liberacao-conferida");
  const campoData = document.getElementById("fila-liberacao-em");
  const botaoColocar = document.getElementById("fila-colocar");
  const botaoCancelar = document.getElementById("fila-cancelar"); // só existe se o aluno já está numa fila
  const botaoAbrir = document.getElementById("abrir-form-fila");
  const botaoTirar = document.getElementById("fila-tirar");
  const confirmacaoTirar = document.getElementById("confirmar-tirar-fila");
  const aviso = document.getElementById("aviso-fila");
  let enviando = false;

  const camposDoFormulario = [selecao, campoProfessor, campoConferida, campoData];

  function avisar(texto, erro = false) {
    aviso.textContent = texto;
    aviso.classList.toggle("aviso-erro", erro);
  }

  const exigeLiberacao = () => selecao.selectedOptions[0]?.dataset.exige === "1";

  // A liberação só aparece nas filas que a pedem (Gestante e Grupos de risco).
  function mostrarLiberacao() {
    blocoLiberacao.hidden = !exigeLiberacao();
  }

  function dadosDoFormulario() {
    return {
      filaId: selecao.value,
      professor: campoProfessor.value,
      exigeLiberacao: exigeLiberacao(),
      conferida: campoConferida.checked,
      liberacaoEm: campoData.value,
      hoje: selecao.dataset.hoje,
    };
  }

  function travar(travado) {
    enviando = travado;
    botaoColocar.disabled = travado;
    if (botaoTirar) botaoTirar.disabled = travado;
  }

  // Faz o pedido e recarrega a página se deu certo: o cartão, o aviso de sugestão e a tabela são redesenhados pelo
  // servidor. Se deu certo, os botões ficam desligados até a página recarregar (clique duplo não manda duas vezes).
  async function enviarPedido(endereco, pedido, textoEnviando) {
    travar(true);
    avisar(textoEnviando);
    let resposta;
    try {
      resposta = await enviarJson(endereco, pedido);
    } catch {
      travar(false);
      avisar(SEM_REDE, true);
      return;
    }
    if (resposta.status === 200) {
      window.location.reload();
      return;
    }
    travar(false);
    avisar(textoDoErro(resposta, "O servidor não alterou a fila do aluno"), true);
  }

  async function colocar() {
    if (enviando) return; // clique duplo ou Enter repetido não manda duas vezes
    const dados = dadosDoFormulario();
    const problemas = validarColocarNaFila(dados);
    for (const campo of camposDoFormulario) campo.removeAttribute("aria-invalid");
    if (problemas.length) {
      for (const p of problemas) document.getElementById(p.campo)?.setAttribute("aria-invalid", "true");
      avisar(problemas[0].mensagem, true);
      document.getElementById(problemas[0].campo)?.focus();
      return;
    }
    await enviarPedido(`/api/alunos/${encodeURIComponent(alunoId)}/fila`, montarPedidoDaFila(dados), "Salvando…");
  }

  selecao.addEventListener("change", () => {
    mostrarLiberacao();
    avisar("");
  });
  botaoColocar.addEventListener("click", colocar);
  campoProfessor.addEventListener("keydown", (evento) => {
    if (evento.key === "Enter" && !evento.isComposing) {
      evento.preventDefault();
      colocar();
    }
  });
  mostrarLiberacao();

  // Aluno que já está numa fila: o formulário fica fechado até clicar em "Mudar de fila".
  if (botaoAbrir) {
    botaoAbrir.addEventListener("click", () => {
      formulario.hidden = false;
      botaoAbrir.setAttribute("aria-expanded", "true");
      botaoAbrir.hidden = true;
      avisar("");
      campoProfessor.focus();
    });
  }
  if (botaoCancelar) {
    botaoCancelar.addEventListener("click", () => {
      formulario.hidden = true;
      botaoAbrir.hidden = false;
      botaoAbrir.setAttribute("aria-expanded", "false");
      avisar("");
      botaoAbrir.focus();
    });
  }

  // Tirar da fila: dois passos (o primeiro clique só pergunta). O treino do aluno não muda.
  if (botaoTirar) {
    botaoTirar.addEventListener("click", () => {
      botaoTirar.hidden = true;
      confirmacaoTirar.hidden = false;
      document.getElementById("fila-tirar-nao").focus();
    });
    document.getElementById("fila-tirar-nao").addEventListener("click", () => {
      confirmacaoTirar.hidden = true;
      botaoTirar.hidden = false;
      botaoTirar.focus();
    });
    document.getElementById("fila-tirar-sim").addEventListener("click", () => {
      if (enviando) return;
      enviarPedido(`/api/alunos/${encodeURIComponent(alunoId)}/fila/tirar`, {}, "Tirando da fila…");
    });
  }
}
