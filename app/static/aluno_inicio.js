// Tela /aluno: o treino do aluno (fichas e exercícios) e o botão Sair.
// Texto sempre via textContent (o helper `el`): nada que vem do banco é interpretado como HTML.
import { buscarJson, enviarJson } from "./api.js";
import { el } from "./dom.js";
import {
  MENSAGEM_SEM_REDE,
  TEXTO_SEM_EXERCICIOS,
  TEXTO_SEM_TREINO,
  descreverTreino,
  fichaEscolhida,
  linhasDoExercicio,
  textoDasDatas,
} from "./aluno_modelo.js";

const botaoSair = document.getElementById("botao-sair");
const avisoSair = document.getElementById("aviso-sair");
const avisoTreino = document.getElementById("aviso-treino");
const botaoDeNovo = document.getElementById("botao-de-novo");
const areaDoTreino = document.getElementById("treino");
const tituloDoTreino = document.getElementById("titulo-treino");
const datasDoTreino = document.getElementById("treino-datas");
const botoesDasFichas = document.getElementById("fichas-botoes");
const areaDaFicha = document.getElementById("ficha-atual");

function desenharExercicio(exercicio) {
  return el(
    "li",
    { classe: "meu-exercicio" },
    el("span", { classe: "meu-exercicio-etiqueta", texto: exercicio.etiqueta, "aria-hidden": "true" }),
    el(
      "div",
      { classe: "meu-exercicio-corpo" },
      el("p", { classe: "meu-exercicio-nome", texto: exercicio.exercicio }),
      linhasDoExercicio(exercicio).map((linha) => el("p", { classe: "meu-exercicio-detalhe", texto: linha })),
    ),
  );
}

function desenharGrupo(grupo) {
  const lista = el("ul", { classe: "meu-exercicios" }, grupo.exercicios.map(desenharExercicio));
  if (!grupo.nome) return el("div", { classe: "meu-grupo-simples" }, lista);
  return el(
    "div",
    { classe: "meu-grupo-bloco" },
    el("p", { classe: "meu-bloco-titulo", texto: grupo.nome }),
    el("p", { classe: "meu-bloco-instrucao", texto: grupo.instrucao }),
    lista,
  );
}

function mostrarFicha(treino, indice) {
  const escolhida = fichaEscolhida(treino.fichas, indice);
  botoesDasFichas.querySelectorAll("button").forEach((botao, i) => {
    botao.setAttribute("aria-pressed", i === escolhida ? "true" : "false");
  });
  areaDaFicha.replaceChildren(...treino.fichas[escolhida].grupos.map(desenharGrupo));
}

function mostrarTreino(treino) {
  tituloDoTreino.textContent = treino.nome;
  datasDoTreino.textContent = textoDasDatas(treino);
  datasDoTreino.hidden = !datasDoTreino.textContent;
  botoesDasFichas.replaceChildren(
    ...treino.fichas.map((ficha, i) =>
      el("button", {
        type: "button",
        classe: "meu-ficha-botao",
        texto: ficha.nome,
        "aria-pressed": "false",
        aoClicar: () => mostrarFicha(treino, i),
      }),
    ),
  );
  botoesDasFichas.hidden = treino.fichas.length < 2; // uma ficha só: não precisa de botão
  mostrarFicha(treino, 0);
  areaDoTreino.hidden = false;
  avisoTreino.hidden = true;
}

function mostrarAviso(texto, comBotaoDeNovo) {
  areaDoTreino.hidden = true;
  avisoTreino.hidden = false;
  avisoTreino.textContent = texto;
  botaoDeNovo.hidden = !comBotaoDeNovo;
}

async function carregarTreino() {
  botaoDeNovo.hidden = true;
  mostrarAviso("Buscando o seu treino…", false);
  let resposta;
  try {
    resposta = await buscarJson("/api/aluno/treino");
  } catch {
    mostrarAviso(MENSAGEM_SEM_REDE, true);
    return;
  }
  const o_que_fazer = descreverTreino(resposta.status, resposta.corpo);
  switch (o_que_fazer.tipo) {
    case "entrar":
      window.location.assign("/aluno/entrar");
      return;
    case "sem-treino":
      mostrarAviso(TEXTO_SEM_TREINO, false);
      return;
    case "sem-exercicios":
      mostrarAviso(TEXTO_SEM_EXERCICIOS, false);
      return;
    case "treino":
      mostrarTreino(o_que_fazer.treino);
      return;
    default:
      mostrarAviso(o_que_fazer.mensagem, true);
  }
}

botaoDeNovo.addEventListener("click", carregarTreino);

botaoSair.addEventListener("click", async () => {
  if (botaoSair.disabled) return;
  botaoSair.disabled = true;
  try {
    const { status } = await enviarJson("/api/aluno/sair", {});
    if (status === 200) {
      window.location.assign("/aluno/entrar");
      return; // o botão continua travado: a página está sendo trocada
    }
    avisoSair.textContent = `Não consegui sair (código ${status}). Tente de novo.`;
  } catch {
    avisoSair.textContent = MENSAGEM_SEM_REDE;
  }
  avisoSair.classList.add("aviso-erro");
  botaoSair.disabled = false;
});

carregarTreino();
