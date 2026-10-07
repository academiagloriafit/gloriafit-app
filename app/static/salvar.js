// Tela "Salvar treino": o professor confere o nome do treino, digita o próprio nome
// (obrigatório) e confirma. A lógica de conferir e de montar o pedido está em
// treino_modelo.js (testada à parte); aqui só ligamos a tela e falamos com o servidor.
import { enviarJson } from "./api.js";
import * as M from "./treino_modelo.js";

const pegar = (id) => document.getElementById(id);

// Cria um elemento <li> só com texto (textContent: nada é interpretado como HTML).
function itemDeLista(texto) {
  const li = document.createElement("li");
  li.textContent = texto;
  return li;
}

// alunoId, alunoNome: de quem é o treino.
// obterEstado(): devolve o treino que está na tela de montagem.
// aoSalvar(): chamada depois que o servidor confirmou (a tela apaga o rascunho).
export function iniciarPainelDeSalvar({ alunoId, alunoNome, obterEstado, aoSalvar }) {
  const areaMontagem = pegar("area-montagem");
  const painel = pegar("painel-salvar");
  const painelSalvo = pegar("treino-salvo");
  const resumo = pegar("resumo-salvar");
  const campoNome = pegar("nome-treino");
  const campoQuem = pegar("quem-montou");
  const dicaNome = pegar("dica-nome-treino");
  const elErros = pegar("erros-salvar");
  const botaoConfirmar = pegar("confirmar-salvar");
  const botaoVoltar = pegar("voltar-ao-treino");

  let nomeEditadoPeloProfessor = false; // se sim, não trocamos o nome por outra sugestão
  let salvando = false;

  function atualizarDicaDoNome() {
    const n = M.tamanho(M.limparEspacos(campoNome.value));
    dicaNome.textContent =
      `${n} de ${M.LIMITE_NOME_TREINO} letras (limite do Data4U). ` +
      "Cada aluno só pode ter um treino com cada nome.";
  }

  function mostrarErros(mensagens) {
    elErros.textContent = "";
    mensagens.forEach((m) => elErros.append(itemDeLista(m)));
    elErros.hidden = mensagens.length === 0;
  }

  function marcarCampos(camposComProblema) {
    for (const campo of [campoNome, campoQuem]) {
      if (camposComProblema.includes(campo.id)) campo.setAttribute("aria-invalid", "true");
      else campo.removeAttribute("aria-invalid");
    }
  }

  function travar(travado) {
    salvando = travado;
    botaoConfirmar.disabled = travado;
    botaoVoltar.disabled = travado;
    campoNome.readOnly = travado;
    campoQuem.readOnly = travado;
    botaoConfirmar.textContent = travado ? "Salvando…" : "Confirmar e salvar";
  }

  // ---------------------------------------------------------------- abrir e voltar

  function abrir() {
    const estado = obterEstado();
    resumo.textContent = "";
    estado.fichas.forEach((ficha) =>
      resumo.append(itemDeLista(`${M.limparEspacos(ficha.nome)} — ${M.descreverFicha(ficha)}`)),
    );
    if (!nomeEditadoPeloProfessor) {
      campoNome.value = M.sugerirNomeDoTreino(estado, M.formatarData(new Date()));
    }
    atualizarDicaDoNome();
    mostrarErros([]);
    marcarCampos([]);
    areaMontagem.hidden = true;
    painel.hidden = false;
    window.scrollTo(0, 0);
    // o campo obrigatório é o que o professor precisa preencher: o cursor já vai para ele
    (campoQuem.value ? botaoConfirmar : campoQuem).focus();
  }

  function voltar() {
    if (salvando) return;
    painel.hidden = true;
    areaMontagem.hidden = false;
    pegar("salvar").focus();
  }

  // ---------------------------------------------------------------- enviar

  async function confirmar() {
    if (salvando) return; // clique duplo ou Enter repetido não manda duas vezes
    const dados = { nomeTreino: campoNome.value, montadoPor: campoQuem.value };
    const problemas = M.validarDadosDoTreino(dados);
    marcarCampos(problemas.map((p) => p.campo));
    mostrarErros(problemas.map((p) => p.mensagem));
    if (problemas.length) {
      pegar(problemas[0].campo).focus();
      return;
    }

    travar(true);
    let resposta;
    try {
      resposta = await enviarJson(
        `/api/alunos/${encodeURIComponent(alunoId)}/treinos`,
        M.montarPedido(obterEstado(), dados),
      );
    } catch {
      travar(false);
      mostrarErros([
        "Não consegui confirmar com o servidor se o treino foi salvo (sem resposta ou sem rede). " +
          "Confira a rede e toque em Confirmar e salvar de novo: se ele já tiver sido salvo, o app avisará que o nome já existe.",
      ]);
      return;
    }

    if (resposta.status === 201) {
      sucesso(M.limparEspacos(dados.nomeTreino), M.limparEspacos(dados.montadoPor), M.enderecoDeImpressao(resposta.corpo));
      return;
    }

    const corpo = resposta.corpo; // null se não for JSON (ex.: página de erro): cai na mensagem genérica
    travar(false);
    let mensagens = Array.isArray(corpo?.erros) ? corpo.erros.filter((m) => typeof m === "string") : [];
    if (mensagens.length === 0) {
      mensagens = [
        typeof corpo?.erro === "string"
          ? corpo.erro
          : `O servidor devolveu um erro (código ${resposta.status}). O treino não foi salvo.`,
      ];
    }
    mostrarErros(mensagens);
    if (resposta.status === 409) {
      marcarCampos(["nome-treino"]); // nome já usado por este aluno
      campoNome.focus();
    }
  }

  function sucesso(nomeTreino, montadoPor, enderecoDeImpressao) {
    aoSalvar();
    painel.hidden = true;
    const linkImprimir = pegar("imprimir-treino");
    if (enderecoDeImpressao) linkImprimir.href = enderecoDeImpressao;
    linkImprimir.hidden = !enderecoDeImpressao;
    pegar("texto-salvo").textContent =
      `O treino "${nomeTreino}" foi salvo para ${alunoNome}. Montado por: ${montadoPor}.`;
    painelSalvo.hidden = false;
    window.scrollTo(0, 0);
    pegar("titulo-salvo").focus();
  }

  // ---------------------------------------------------------------- ligações

  campoNome.addEventListener("input", () => {
    nomeEditadoPeloProfessor = true;
    atualizarDicaDoNome();
  });
  for (const campo of [campoNome, campoQuem]) {
    campo.addEventListener("keydown", (evento) => {
      if (evento.key === "Enter" && !evento.isComposing) {
        evento.preventDefault();
        confirmar();
      }
    });
  }
  botaoConfirmar.addEventListener("click", confirmar);
  botaoVoltar.addEventListener("click", voltar);
  pegar("montar-outro").addEventListener("click", () => window.location.reload());

  return { abrir };
}
