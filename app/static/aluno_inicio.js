// Tela /aluno: o treino do aluno (fichas e exercícios) e o botão Sair.
// Texto sempre via textContent (o helper `el`): nada que vem do banco é interpretado como HTML.
import { buscarJson, enviarJson } from "./api.js";
import { atualizarMeusComentarios } from "./aluno_comentarios.js";
import { el } from "./dom.js";
import {
  MENSAGEM_SEM_REDE,
  TEXTO_COMENTARIO_ENVIADO,
  TEXTO_COMENTARIO_REPETIDO,
  TEXTO_FICHA_FEITA_HOJE,
  TEXTO_JA_MARCADA,
  TEXTO_SEM_EXERCICIOS,
  TEXTO_SEM_TREINO,
  chaveDoRascunho,
  comentarioPronto,
  descreverComentario,
  descreverMarcacao,
  descreverTreino,
  dicaDoComentario,
  estourouOLimite,
  fichaEscolhida,
  linhasDoExercicio,
  pedidoDoComentario,
  textoDasDatas,
  textoDoAndamento,
  textoDoContador,
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
const areaDoComentarioDoTreino = document.getElementById("comentario-treino");

// Os rascunhos ficam aqui (e não dentro da caixa): a ficha é desenhada de novo ao trocar de A para B e ao marcar
// "Treino concluído", e o aluno não pode perder o que estava escrevendo nem a confirmação de que enviou.
// Cada rascunho também guarda `enviando` (há um envio no ar) e `redesenhar` (a função da caixa que está NA TELA agora):
// se a ficha for redesenhada no meio de um envio, a resposta atualiza a caixa nova, não uma que já saiu da tela.
const rascunhos = new Map();

function estadoDoRascunho(chave) {
  if (!rascunhos.has(chave)) {
    rascunhos.set(chave, { aberto: false, texto: "", mensagem: "", deuErro: false, precisaAtualizar: false, enviando: false, redesenhar: null });
  }
  return rascunhos.get(chave);
}

// A caixa de comentário do treino inteiro (`ficha` e `exercicio` vazios) ou de um exercício. O texto do aluno só vai e
// volta como texto (value / textContent): nada é interpretado como HTML.
function desenharComentario(treino, ficha = null, exercicio = null) {
  const chave = chaveDoRascunho(ficha, exercicio);
  const estado = estadoDoRascunho(chave);
  const sobre = exercicio ? "este exercício" : "o treino";
  const raiz = el("div", { classe: "meu-comentario" });
  const idDaCaixa = `caixa-comentario-${chave.replace(":", "-")}`; // (o id "comentario-treino" já é o da área na página)

  // `foco`: "caixa" leva o cursor para o texto; "botao" devolve o foco ao botão de abrir (quem usa teclado ou leitor de tela não se perde).
  const redesenhar = (foco = "") => {
    raiz.replaceChildren(...montar());
    if (foco === "caixa") raiz.querySelector("textarea")?.focus();
    else if (foco === "botao") raiz.querySelector(".meu-comentario-abrir")?.focus();
  };
  estado.redesenhar = redesenhar; // a caixa criada por último é a que está na tela

  async function enviar(botao) {
    if (estado.enviando) return;
    const pronto = comentarioPronto(estado.texto);
    if (!pronto.ok) {
      Object.assign(estado, { mensagem: pronto.mensagem, deuErro: true, precisaAtualizar: false });
      estado.redesenhar("caixa");
      return;
    }
    estado.enviando = true;
    botao.disabled = true;
    try {
      const resposta = await enviarJson("/api/aluno/comentario", pedidoDoComentario(treino, pronto.texto, ficha, exercicio));
      const resultado = descreverComentario(resposta.status, resposta.corpo);
      if (resultado.tipo === "entrar") {
        window.location.assign("/aluno/entrar");
        return; // o botão continua travado: a página está sendo trocada
      }
      if (resultado.tipo === "ok") {
        Object.assign(estado, {
          aberto: false,
          texto: "",
          mensagem: resultado.repetido ? TEXTO_COMENTARIO_REPETIDO : TEXTO_COMENTARIO_ENVIADO,
          deuErro: false,
          precisaAtualizar: false,
        });
      } else {
        Object.assign(estado, { mensagem: resultado.mensagem, deuErro: true, precisaAtualizar: resultado.tipo === "atualizar" });
      }
    } catch {
      Object.assign(estado, { mensagem: MENSAGEM_SEM_REDE, deuErro: true, precisaAtualizar: false });
    }
    estado.enviando = false;
    estado.redesenhar(estado.aberto ? "" : "botao");
    if (!estado.aberto) atualizarMeusComentarios(); // o comentário novo entra na lista "Seus comentários"
  }

  function montar() {
    const aviso = el("p", {
      classe: estado.deuErro ? "aviso-campo aviso-erro" : "aviso-campo",
      role: "status",
      texto: estado.mensagem,
    });
    const atualizar = estado.precisaAtualizar
      ? el("button", { type: "button", classe: "botao-link", texto: "Atualizar a página", aoClicar: () => window.location.reload() })
      : null;
    if (!estado.aberto) {
      return [
        el("button", {
          type: "button",
          classe: "meu-comentario-abrir",
          texto: exercicio ? "Comentar" : "Comentar sobre o treino",
          // Só "Comentar" não diz sobre qual exercício; o leitor de tela lê o nome completo.
          "aria-label": exercicio ? `Comentar sobre ${exercicio.exercicio}` : "Comentar sobre o treino",
          aoClicar: () => {
            Object.assign(estado, { aberto: true, mensagem: "", deuErro: false, precisaAtualizar: false });
            estado.redesenhar("caixa");
          },
        }),
        aviso,
      ];
    }
    const contador = el("p", { classe: "meu-comentario-contador", texto: textoDoContador(estado.texto) });
    const atualizarContador = () => {
      contador.textContent = textoDoContador(estado.texto);
      contador.classList.toggle("meu-comentario-contador-estouro", estourouOLimite(estado.texto));
    };
    // Sem `maxlength`: ele conta de outro jeito que o servidor (um emoji vale 2 nele) e travaria o aluno antes da hora.
    // O contador mostra quanto falta e fica vermelho quando passa; o envio explica o motivo.
    const caixa = el("textarea", {
      id: idDaCaixa,
      classe: "meu-comentario-caixa",
      rows: "4",
      placeholder: dicaDoComentario(Boolean(exercicio)),
      aoDigitar: (evento) => {
        estado.texto = evento.currentTarget.value;
        atualizarContador();
      },
    });
    caixa.value = estado.texto; // por propriedade (texto puro), não como conteúdo HTML
    atualizarContador();
    return [
      el("div", { classe: "meu-comentario-form" },
        el("label", { for: idDaCaixa, classe: "meu-comentario-rotulo", texto: `Seu comentário sobre ${sobre}` }),
        caixa,
        contador,
        el("div", { classe: "meu-comentario-botoes" },
          // `disabled` enquanto há um envio no ar (também numa caixa redesenhada no meio do envio): sem toque duplo.
          el("button", { type: "button", classe: "botao-link botao-link-forte", texto: "Enviar", disabled: estado.enviando, aoClicar: (evento) => enviar(evento.currentTarget) }),
          el("button", {
            type: "button",
            classe: "botao-link",
            texto: "Cancelar",
            aoClicar: () => {
              Object.assign(estado, { aberto: false, mensagem: "", deuErro: false, precisaAtualizar: false });
              estado.redesenhar("botao");
            },
          }),
        ),
        aviso,
        atualizar,
      ),
    ];
  }

  raiz.replaceChildren(...montar());
  return raiz;
}

function desenharExercicio(exercicio, treino, ficha) {
  return el(
    "li",
    { classe: "meu-exercicio" },
    el("span", { classe: "meu-exercicio-etiqueta", texto: exercicio.etiqueta, "aria-hidden": "true" }),
    el(
      "div",
      { classe: "meu-exercicio-corpo" },
      el("p", { classe: "meu-exercicio-nome", texto: exercicio.exercicio }),
      linhasDoExercicio(exercicio).map((linha) => el("p", { classe: "meu-exercicio-detalhe", texto: linha })),
      desenharComentario(treino, ficha, exercicio),
    ),
  );
}

function desenharGrupo(grupo, treino, ficha) {
  const lista = el("ul", { classe: "meu-exercicios" }, grupo.exercicios.map((exercicio) => desenharExercicio(exercicio, treino, ficha)));
  if (!grupo.nome) return el("div", { classe: "meu-grupo-simples" }, lista);
  return el(
    "div",
    { classe: "meu-grupo-bloco" },
    el("p", { classe: "meu-bloco-titulo", texto: grupo.nome }),
    el("p", { classe: "meu-bloco-instrucao", texto: grupo.instrucao }),
    lista,
  );
}

// Marca ("fiz hoje") ou desfaz a ficha. `rota`: "feito" ou "desfazer". Depois atualiza a tela com o que o servidor disse.
async function marcarFicha(treino, indice, rota, botao) {
  if (botao.disabled) return;
  botao.disabled = true;
  const ficha = treino.fichas[indice];
  let mensagem = "";
  let deuErro = false;
  try {
    const resposta = await enviarJson(`/api/aluno/treino/${rota}`, { ficha: ficha.ordem });
    const resultado = descreverMarcacao(resposta.status, resposta.corpo);
    if (resultado.tipo === "entrar") {
      window.location.assign("/aluno/entrar");
      return; // o botão continua travado: a página está sendo trocada
    }
    if (resultado.tipo === "ok") {
      ficha.feitas = resultado.feitas;
      ficha.feita_hoje = rota === "feito";
      mensagem = rota === "feito" ? (resultado.jaMarcada ? TEXTO_JA_MARCADA : TEXTO_FICHA_FEITA_HOJE) : "";
    } else {
      mensagem = resultado.mensagem;
      deuErro = true;
    }
  } catch {
    mensagem = MENSAGEM_SEM_REDE;
    deuErro = true;
  }
  mostrarFicha(treino, indice, mensagem, deuErro);
}

function desenharRodape(treino, indice, mensagem, deuErro) {
  const ficha = treino.fichas[indice];
  const aviso = el("p", { classe: deuErro ? "aviso-campo aviso-erro" : "aviso-campo", role: "status", texto: mensagem });
  const botaoFeito = ficha.feita_hoje
    ? null
    : el("button", {
        type: "button",
        classe: "botao-link botao-link-forte botao-largo",
        texto: "✓ Treino concluído",
        aoClicar: (evento) => marcarFicha(treino, indice, "feito", evento.currentTarget),
      });
  const botaoDesfazer = ficha.feita_hoje
    ? el("button", {
        type: "button",
        classe: "botao-link botao-largo",
        texto: "Desfazer (marquei sem querer)",
        aoClicar: (evento) => marcarFicha(treino, indice, "desfazer", evento.currentTarget),
      })
    : null;
  return el(
    "div",
    { classe: "meu-ficha-rodape" },
    el("p", { classe: "meu-ficha-andamento", texto: textoDoAndamento(ficha, treino.meta_por_ficha) }),
    ficha.feita_hoje && el("p", { classe: "meu-ficha-feita", texto: "✓ Treino concluído hoje" }),
    botaoFeito,
    botaoDesfazer,
    aviso,
  );
}

function mostrarFicha(treino, indice, mensagem = "", deuErro = false) {
  const escolhida = fichaEscolhida(treino.fichas, indice);
  botoesDasFichas.querySelectorAll("button").forEach((botao, i) => {
    botao.setAttribute("aria-pressed", i === escolhida ? "true" : "false");
  });
  areaDaFicha.replaceChildren(
    ...treino.fichas[escolhida].grupos.map((grupo) => desenharGrupo(grupo, treino, treino.fichas[escolhida])),
    desenharRodape(treino, escolhida, mensagem, deuErro),
  );
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
  areaDoComentarioDoTreino.replaceChildren(desenharComentario(treino));
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
atualizarMeusComentarios();
