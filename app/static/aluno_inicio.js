// Tela /aluno: o treino do aluno (fichas e exercícios) e o botão Sair.
// Texto sempre via textContent (o helper `el`): nada que vem do banco é interpretado como HTML.
import { buscarJson, enviarJson } from "./api.js";
import { atualizarMeusComentarios } from "./aluno_comentarios.js";
import { iniciarDescanso } from "./aluno_descanso.js";
import { el } from "./dom.js";
import {
  ESFORCOS,
  MENSAGEM_FEITO_NAO_SALVOU,
  MENSAGEM_SEM_REDE,
  TEXTO_COMENTARIO_ENVIADO,
  TEXTO_COMENTARIO_REPETIDO,
  TEXTO_CONCLUIDO_HOJE,
  TEXTO_ESCOLHA_O_TREINO,
  TEXTO_ESFORCO_OPCIONAL,
  TEXTO_FICHA_FEITA_HOJE,
  TEXTO_JA_MARCADA,
  TEXTO_SEM_EXERCICIOS,
  TEXTO_SEM_TREINO,
  TEXTO_PERGUNTA_DO_ESFORCO,
  TEXTO_TREINO_DE_HOJE,
  chaveDoRascunho,
  comentarioPronto,
  conferirCarga,
  decidirAtualizacaoDoTreino,
  descreverComentario,
  descreverEsforco,
  descreverExercicio,
  descreverMarcacao,
  descreverTreino,
  dicaDoComentario,
  ehFichaDoDia,
  estourouOLimite,
  fichaEscolhida,
  linhasDoExercicio,
  pedidoDoComentario,
  pedidoDoEsforco,
  pedidoDoExercicio,
  proximoEsforco,
  temDescanso,
  temDose,
  textoDaUltimaCarga,
  textoDasDatas,
  textoDoAndamento,
  textoDoBotaoDeDescanso,
  textoDoContador,
  textoDoFeito,
  textoDoProgresso,
  textoDosExercicios,
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
const cabecalhoDoTreino = document.getElementById("treino-cabecalho");
const dicaDoTreino = document.getElementById("treino-dica");
const topoDaFicha = document.getElementById("ficha-topo");
const tituloDaFicha = document.getElementById("ficha-titulo");
const etiquetaDaFicha = document.getElementById("ficha-etiqueta");
const botaoVoltar = document.getElementById("botao-voltar");
const paginaDoAluno = document.querySelector(".pagina-aluno");

// Os rascunhos ficam aqui (e não dentro da caixa): a ficha é desenhada de novo ao trocar de A para B e ao marcar
// "Treino concluído", e o aluno não pode perder o que estava escrevendo nem a confirmação de que enviou.
// Cada rascunho também guarda `enviando` (há um envio no ar) e `redesenhar` (a função da caixa que está NA TELA agora):
// se a ficha for redesenhada no meio de um envio, a resposta atualiza a caixa nova, não uma que já saiu da tela.
const rascunhos = new Map();
// Quantos pedidos de "feito", carga ou nota estão no ar agora: a tela não se redesenha no meio deles (ver `alunoEstaEscrevendo`).
let pedidosNoAr = 0;
// Salvamentos de carga em andamento. "Treino concluído" e "voltar" esperam por eles (ver `terminarSalvamentos`): sem isso a tela era
// redesenhada antes da resposta e o campo voltava vazio, ou o valor digitado se perdia.
const salvamentosDeCarga = new Set();

// Tira o cursor do campo que estiver aberto (isso salva o que foi digitado: no iPhone, tocar num botão NÃO tira o cursor do campo)
// e espera os salvamentos de carga acabarem.
async function terminarSalvamentos() {
  document.activeElement?.blur?.();
  await Promise.allSettled([...salvamentosDeCarga]);
}

// O que está na tela agora, para saber se o treino mudou quando o aluno voltar para o app (ver `atualizarTreinoAoVoltar`).
let treinoNaTela = null; // null: a tela mostra um aviso (carregando, sem treino, erro), não um treino
let fichaNaTela = 0; // a ficha (A, B...) que o aluno abriu por último: continua nela depois de atualizar
let verFicha = false; // false: a lista de fichas (tela 1); true: os exercícios de uma ficha (tela 2)
let buscandoOTreino = false;
let ultimaBuscaDoTreino = 0;
const MINIMO_ENTRE_BUSCAS = 30_000; // ao voltar para o app, busca de novo no máximo a cada 30 segundos (igual à lista de comentários)

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

// O que o aluno faz DURANTE o treino num exercício: marcar como feito, anotar a carga que usou e (se o professor informou o
// intervalo) tocar para descansar. Tudo é gravado pelo servidor na hora (vale por dia: amanhã volta limpo). O modelo
// (`exercicio.feito`, `exercicio.carga_hoje`) só muda DEPOIS que o servidor confirma, e mexe nas chaves que já existem, para a
// comparação "o treino mudou?" ao voltar para o app continuar certa.
function desenharAcoesDoExercicio(exercicio, treino, ficha, cartao) {
  const idDaCarga = `carga-${ficha.ordem}-${exercicio.ordem}`;
  let mensagem = "";
  let deuErro = false;
  let precisaAtualizar = false;
  let marcando = false;
  let gravandoCarga = false;
  let cargaPendente = false;
  let cargaNaoSalvou = false; // o último envio falhou: sair do campo de novo tenta outra vez, mesmo sem o aluno mudar o número

  const aviso = el("p", { classe: "aviso-campo", role: "status" });
  const botaoAtualizar = el("button", { type: "button", classe: "botao-link", texto: "Atualizar a página", aoClicar: () => window.location.reload() });
  const botaoFeito = el("button", { type: "button", classe: "meu-feito", aoClicar: () => alternarFeito() });
  const campo = el("input", {
    id: idDaCarga,
    type: "text",
    classe: "meu-carga-campo",
    inputmode: "decimal",
    autocomplete: "off",
    maxlength: "6",
    placeholder: "kg",
    "aria-describedby": `${idDaCarga}-nota`,
    aoMudar: () => salvarEAcompanhar(),
  });
  campo.addEventListener("blur", () => {
    // O "change" só dispara quando o número mudou. Se o envio anterior falhou, o número já está no campo: sair dele de novo reenvia.
    if (cargaNaoSalvou) salvarEAcompanhar();
  });
  campo.addEventListener("keydown", (evento) => {
    if (evento.key === "Enter") {
      evento.preventDefault();
      campo.blur(); // o "change" do campo faz o resto
    }
  });
  const nota = el("p", { id: `${idDaCarga}-nota`, classe: "meu-carga-nota", role: "status" });

  function pintar() {
    cartao.classList.toggle("meu-exercicio-feito", exercicio.feito === true);
    botaoFeito.textContent = textoDoFeito(exercicio.feito);
    botaoFeito.setAttribute("aria-pressed", exercicio.feito === true ? "true" : "false");
    botaoFeito.setAttribute("aria-label", `${textoDoFeito(exercicio.feito)}: ${exercicio.exercicio}`);
    botaoFeito.disabled = marcando;
    aviso.textContent = mensagem;
    aviso.className = deuErro ? "aviso-campo aviso-erro" : "aviso-campo";
    botaoAtualizar.hidden = !precisaAtualizar;
  }

  // Resposta que não é "ok": 401 troca de tela; o resto vira mensagem embaixo do exercício. Devolve true se tratou.
  function trataFalha(resultado) {
    if (resultado.tipo === "entrar") {
      window.location.assign("/aluno/entrar");
      return true;
    }
    if (resultado.tipo === "ok") return false;
    mensagem = resultado.mensagem;
    deuErro = true;
    precisaAtualizar = resultado.tipo === "atualizar";
    return true;
  }

  async function alternarFeito() {
    if (marcando) return;
    marcando = true;
    pedidosNoAr += 1;
    mensagem = "";
    deuErro = false;
    precisaAtualizar = false;
    pintar();
    try {
      const resposta = await enviarJson("/api/aluno/exercicio", pedidoDoExercicio(ficha, exercicio, { feito: exercicio.feito !== true }));
      const resultado = descreverExercicio(resposta.status, resposta.corpo);
      if (!trataFalha(resultado)) exercicio.feito = resultado.feito;
    } catch {
      mensagem = `${MENSAGEM_FEITO_NAO_SALVOU} ${MENSAGEM_SEM_REDE}`;
      deuErro = true;
    }
    pedidosNoAr -= 1;
    marcando = false;
    pintar();
  }

  function salvarEAcompanhar() {
    const andamento = salvarCarga();
    salvamentosDeCarga.add(andamento);
    const terminou = () => salvamentosDeCarga.delete(andamento);
    andamento.then(terminou, terminou);
    return andamento;
  }

  async function salvarCarga() {
    if (gravandoCarga) {
      cargaPendente = true; // o aluno mexeu de novo durante o envio: depois que terminar, confere de novo
      return;
    }
    const conferida = conferirCarga(campo.value);
    if (!conferida.ok) {
      nota.textContent = conferida.mensagem;
      nota.classList.add("meu-carga-erro");
      return;
    }
    const novo = conferida.valor ?? "";
    campo.value = novo;
    if (novo === exercicio.carga_hoje) {
      nota.textContent = "";
      nota.classList.remove("meu-carga-erro");
      cargaNaoSalvou = false;
      return;
    }
    gravandoCarga = true;
    pedidosNoAr += 1;
    nota.textContent = "Salvando…";
    nota.classList.remove("meu-carga-erro");
    try {
      const resposta = await enviarJson("/api/aluno/exercicio", pedidoDoExercicio(ficha, exercicio, { carga: conferida.valor }));
      const resultado = descreverExercicio(resposta.status, resposta.corpo);
      if (resultado.tipo === "ok") {
        exercicio.carga_hoje = resultado.cargaHoje;
        cargaNaoSalvou = false;
        if (!cargaPendente) campo.value = resultado.cargaHoje; // não atropela o que o aluno digitou enquanto salvava
        nota.textContent = resultado.cargaHoje ? "✓ Anotado" : "Carga apagada";
      } else if (resultado.tipo === "entrar") {
        window.location.assign("/aluno/entrar");
      } else {
        cargaNaoSalvou = true;
        nota.textContent = resultado.mensagem;
        nota.classList.add("meu-carga-erro");
        if (resultado.tipo === "atualizar") {
          mensagem = resultado.mensagem;
          deuErro = true;
          precisaAtualizar = true;
          pintar();
        }
      }
    } catch {
      cargaNaoSalvou = true;
      nota.textContent = `Não salvou. ${MENSAGEM_SEM_REDE}`;
      nota.classList.add("meu-carga-erro");
    }
    pedidosNoAr -= 1;
    gravandoCarga = false;
    if (cargaPendente) {
      cargaPendente = false;
      await salvarCarga();
    }
  }

  campo.value = exercicio.carga_hoje;
  const ultima = textoDaUltimaCarga(exercicio);
  pintar();
  return el(
    "div",
    { classe: "meu-acoes" },
    ultima && el("p", { classe: "meu-ultima-carga", texto: ultima }),
    el(
      "div",
      { classe: "meu-carga" },
      el("label", { for: idDaCarga, classe: "meu-carga-rotulo", texto: "Carga que usei (kg)" }),
      campo,
    ),
    nota,
    el(
      "div",
      { classe: "meu-acoes-botoes" },
      botaoFeito,
      temDescanso(exercicio) &&
        el("button", {
          type: "button",
          classe: "botao-link meu-descansar",
          texto: textoDoBotaoDeDescanso(exercicio),
          "aria-label": `${textoDoBotaoDeDescanso(exercicio)} (começa a contar)`,
          aoClicar: () => iniciarDescanso(exercicio.pausa_segundos, exercicio.exercicio),
        }),
    ),
    aviso,
    botaoAtualizar,
  );
}

function desenharExercicio(exercicio, treino, ficha) {
  const cartao = el("li", { classe: "meu-exercicio" });
  cartao.append(
    el("span", { classe: "meu-exercicio-etiqueta", texto: exercicio.etiqueta, "aria-hidden": "true" }),
    el(
      "div",
      { classe: "meu-exercicio-corpo" },
      el("p", { classe: "meu-exercicio-nome", texto: exercicio.exercicio }),
      linhasDoExercicio(exercicio).map((linha, posicao) =>
        el("p", { classe: posicao === 0 && temDose(exercicio) ? "meu-exercicio-dose" : "meu-exercicio-detalhe", texto: linha }),
      ),
      desenharAcoesDoExercicio(exercicio, treino, ficha, cartao),
      desenharComentario(treino, ficha, exercicio),
    ),
  );
  return cartao;
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
    await terminarSalvamentos(); // a carga que o aluno acabou de digitar é salva ANTES de a ficha ser desenhada de novo
    const resposta = await enviarJson(`/api/aluno/treino/${rota}`, { ficha: ficha.ordem });
    const resultado = descreverMarcacao(resposta.status, resposta.corpo);
    if (resultado.tipo === "entrar") {
      window.location.assign("/aluno/entrar");
      return; // o botão continua travado: a página está sendo trocada
    }
    if (resultado.tipo === "ok") {
      ficha.feitas = resultado.feitas;
      ficha.feita_hoje = rota === "feito";
      if (rota === "desfazer") ficha.esforco_hoje = null; // a nota ficava na marcação de hoje, que o servidor apagou
      if (Number.isInteger(resultado.fichaDoDia)) treino.ficha_do_dia = resultado.fichaDoDia; // o servidor decide quem fica circulada
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

// "Como foi o treino?": Leve / Ideal / Pesado, opcional, só depois de "Treino concluído". Tocar na nota escolhida tira a escolha.
function desenharEsforco(ficha) {
  const raiz = el("div", { classe: "meu-esforco", role: "group", "aria-labelledby": `esforco-titulo-${ficha.ordem}` });
  let enviando = false;
  let mensagem = "";
  let deuErro = false;

  async function escolher(valor) {
    if (enviando) return;
    enviando = true;
    pedidosNoAr += 1;
    mensagem = "";
    deuErro = false;
    redesenhar(valor);
    try {
      const resposta = await enviarJson("/api/aluno/treino/esforco", pedidoDoEsforco(ficha, proximoEsforco(ficha.esforco_hoje, valor)));
      const resultado = descreverEsforco(resposta.status, resposta.corpo);
      if (resultado.tipo === "entrar") {
        window.location.assign("/aluno/entrar");
        return; // a página está sendo trocada
      }
      if (resultado.tipo === "ok") {
        // Se enquanto isso o aluno desfez a ficha, o servidor já apagou a nota: a resposta velha não pode pôr uma nota de volta na tela.
        if (ficha.feita_hoje) ficha.esforco_hoje = resultado.esforco;
      } else {
        mensagem = resultado.mensagem;
        deuErro = true;
      }
    } catch {
      mensagem = MENSAGEM_SEM_REDE;
      deuErro = true;
    }
    pedidosNoAr -= 1;
    enviando = false;
    redesenhar(valor);
  }

  // Redesenha os botões. `foco`: o valor do botão que o aluno acabou de tocar: o teclado/leitor de tela continua nele
  // (desenhar de novo destrói o botão que tinha o foco).
  function redesenhar(foco = null) {
    const tinhaFoco = foco !== null && raiz.contains(document.activeElement);
    raiz.replaceChildren(
      el("p", { id: `esforco-titulo-${ficha.ordem}`, classe: "meu-esforco-titulo", texto: TEXTO_PERGUNTA_DO_ESFORCO }),
      el(
        "div",
        { classe: "meu-esforco-botoes" },
        ESFORCOS.map((opcao) =>
          el("button", {
            type: "button",
            classe: ficha.esforco_hoje === opcao.valor ? "botao-link meu-esforco-escolhido" : "botao-link",
            texto: opcao.texto,
            "aria-pressed": ficha.esforco_hoje === opcao.valor ? "true" : "false",
            "data-esforco": String(opcao.valor),
            // aria-disabled (e não disabled): um botão desabilitado perde o foco do teclado/leitor de tela; o clique é ignorado em `escolher`
            "aria-disabled": enviando ? "true" : false,
            aoClicar: () => escolher(opcao.valor),
          }),
        ),
      ),
      el("p", { classe: deuErro ? "aviso-campo aviso-erro" : "meu-esforco-dica", role: "status", texto: mensagem || TEXTO_ESFORCO_OPCIONAL }),
    );
    if (tinhaFoco) raiz.querySelector(`[data-esforco="${foco}"]`)?.focus({ preventScroll: true });
  }

  redesenhar();
  return raiz;
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
    ficha.feita_hoje && desenharEsforco(ficha),
    botaoFeito,
    botaoDesfazer,
    aviso,
    el("button", { type: "button", classe: "botao-link botao-largo", texto: "Voltar aos treinos", aoClicar: voltarParaALista }),
  );
}

// Os exercícios de UMA ficha (tela 2). Também redesenha depois de "Treino concluído" e quando o treino é atualizado.
function mostrarFicha(treino, indice, mensagem = "", deuErro = false) {
  const escolhida = fichaEscolhida(treino.fichas, indice);
  fichaNaTela = escolhida;
  const ficha = treino.fichas[escolhida];
  tituloDaFicha.textContent = ficha.nome;
  etiquetaDaFicha.textContent = ehFichaDoDia(treino, ficha) ? TEXTO_TREINO_DE_HOJE : "";
  etiquetaDaFicha.hidden = !etiquetaDaFicha.textContent;
  areaDaFicha.replaceChildren(
    ...ficha.grupos.map((grupo) => desenharGrupo(grupo, treino, ficha)),
    desenharRodape(treino, escolhida, mensagem, deuErro),
  );
}

// A lista de botões (tela 1): um por ficha. A do dia vem circulada e com a etiqueta "Treino de hoje".
// Os exercícios NÃO aparecem aqui: o aluno toca na ficha para vê-los.
function desenharCartoes(treino) {
  botoesDasFichas.replaceChildren(
    ...treino.fichas.map((ficha, i) => {
      const doDia = ehFichaDoDia(treino, ficha);
      return el(
        "button",
        {
          type: "button",
          classe: doDia ? "meu-cartao-ficha meu-cartao-do-dia" : "meu-cartao-ficha",
          "aria-current": doDia ? "true" : null,
          aoClicar: () => abrirFicha(treino, i),
        },
        el(
          "span",
          { classe: "meu-cartao-texto" },
          doDia && el("span", { classe: "meu-etiqueta-hoje", texto: TEXTO_TREINO_DE_HOJE }),
          el("span", { classe: "meu-cartao-nome", texto: ficha.nome }),
          el(
            "span",
            { classe: "meu-cartao-detalhe" },
            el("span", { texto: textoDosExercicios(ficha) }),
            ficha.feita_hoje && el("span", { classe: "meu-cartao-feita", texto: TEXTO_CONCLUIDO_HOJE }),
            textoDoProgresso(ficha) && el("span", { classe: "meu-cartao-progresso", texto: textoDoProgresso(ficha) }),
          ),
        ),
        el("span", { classe: "meu-cartao-seta", texto: "\u203A", "aria-hidden": "true" }),
      );
    }),
  );
}

// Troca entre as duas telas só mostrando e escondendo (nada é buscado de novo).
function trocarTela(mostrarAFicha) {
  verFicha = mostrarAFicha;
  cabecalhoDoTreino.hidden = mostrarAFicha;
  botoesDasFichas.hidden = mostrarAFicha;
  topoDaFicha.hidden = !mostrarAFicha;
  areaDaFicha.hidden = !mostrarAFicha;
  areaDoComentarioDoTreino.hidden = !mostrarAFicha;
  paginaDoAluno.classList.toggle("modo-ficha", mostrarAFicha); // na tela 2, o resto da página (olá, comentários, sair) sai de cena
}

// O aluno tocou numa ficha. O "estado" no histórico faz o botão voltar do celular voltar para a lista (em vez de sair do app).
function abrirFicha(treino, indice) {
  history.pushState({ tela: "ficha" }, "");
  mostrarFicha(treino, indice);
  trocarTela(true);
  window.scrollTo(0, 0);
  tituloDaFicha.focus({ preventScroll: true });
}

function irParaALista() {
  if (!treinoNaTela) return;
  desenharCartoes(treinoNaTela); // pode ter mudado: "concluído hoje" e quem é a ficha do dia
  trocarTela(false);
  window.scrollTo(0, 0);
  botoesDasFichas.children[fichaNaTela]?.focus({ preventScroll: true });
}

// "Voltar": se a ficha foi aberta por toque, volta no histórico (e o `popstate` abaixo mostra a lista); senão mostra a lista direto.
function voltarParaALista() {
  document.activeElement?.blur?.(); // salva a carga que estava sendo digitada (o campo vai sair da tela)
  if (history.state && history.state.tela === "ficha") history.back();
  else irParaALista();
}

botaoVoltar.addEventListener("click", voltarParaALista);
window.addEventListener("popstate", () => {
  document.activeElement?.blur?.(); // o gesto de voltar do celular também salva a carga que estava sendo digitada
  if (!treinoNaTela) return;
  if (history.state && history.state.tela === "ficha") {
    mostrarFicha(treinoNaTela, fichaNaTela);
    trocarTela(true);
  } else {
    irParaALista();
  }
});

// `indiceDaFicha` null: mostra a lista (é o que o aluno vê ao entrar); um número: mostra os exercícios daquela ficha.
function mostrarTreino(treino, indiceDaFicha = null) {
  treinoNaTela = treino;
  tituloDoTreino.textContent = treino.nome;
  datasDoTreino.textContent = textoDasDatas(treino);
  datasDoTreino.hidden = !datasDoTreino.textContent;
  dicaDoTreino.textContent = TEXTO_ESCOLHA_O_TREINO;
  desenharCartoes(treino);
  areaDoComentarioDoTreino.replaceChildren(desenharComentario(treino));
  if (indiceDaFicha === null) {
    trocarTela(false);
  } else {
    mostrarFicha(treino, indiceDaFicha);
    trocarTela(true);
  }
  areaDoTreino.hidden = false;
  avisoTreino.hidden = true;
  botaoDeNovo.hidden = true; // pode ter ficado visível se a tela estava num erro quando o treino chegou
}

function mostrarAviso(texto, comBotaoDeNovo) {
  treinoNaTela = null;
  verFicha = false;
  paginaDoAluno.classList.remove("modo-ficha"); // a saudação (onde o aviso aparece) tem que estar visível
  areaDoTreino.hidden = true;
  avisoTreino.hidden = false;
  avisoTreino.textContent = texto;
  botaoDeNovo.hidden = !comBotaoDeNovo;
}

async function carregarTreino() {
  botaoDeNovo.hidden = true;
  mostrarAviso("Buscando o seu treino…", false);
  buscandoOTreino = true;
  ultimaBuscaDoTreino = Date.now();
  let resposta;
  try {
    resposta = await buscarJson("/api/aluno/treino");
  } catch {
    mostrarAviso(MENSAGEM_SEM_REDE, true);
    return;
  } finally {
    buscandoOTreino = false;
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

// Há uma caixa de comentário aberta (mesmo vazia), um campo de carga com o cursor ou um envio no ar?
function alunoEstaEscrevendo() {
  const digitandoCarga = document.activeElement?.classList?.contains("meu-carga-campo") === true;
  return pedidosNoAr > 0 || digitandoCarga || [...rascunhos.values()].some((estado) => estado.aberto || estado.enviando);
}

// O app do celular fica aberto em segundo plano por horas ou dias (principalmente guardado na tela inicial): ao voltar para ele,
// busca o treino de novo, para o aluno não treinar pelo treino velho nem ver "treino concluído hoje" de ontem.
// Só mexe na tela se algo mudou, e nunca enquanto o aluno escreve (ver `decidirAtualizacaoDoTreino`).
async function atualizarTreinoAoVoltar() {
  if (buscandoOTreino) return;
  buscandoOTreino = true;
  ultimaBuscaDoTreino = Date.now();
  try {
    let resposta;
    try {
      resposta = await buscarJson("/api/aluno/treino");
    } catch {
      return; // sem rede: a tela fica como está (o treino que o aluno já tem continua valendo)
    }
    // Perguntado só DEPOIS da resposta: o aluno pode ter aberto uma caixa enquanto a busca andava.
    const decisao = decidirAtualizacaoDoTreino(treinoNaTela, resposta.status, resposta.corpo, alunoEstaEscrevendo());
    if (decisao.acao === "entrar") {
      window.location.assign("/aluno/entrar");
    } else if (decisao.acao === "mostrar") {
      rascunhos.clear(); // os rascunhos são de "ficha:exercício" do treino velho: no treino novo apontariam para outro exercício
      mostrarTreino(decisao.treino, verFicha ? fichaNaTela : null); // continua na tela em que o aluno estava
    } else if (decisao.acao === "aviso") {
      rascunhos.clear();
      mostrarAviso(decisao.texto, false);
    }
  } finally {
    buscandoOTreino = false;
  }
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && Date.now() - ultimaBuscaDoTreino > MINIMO_ENTRE_BUSCAS) atualizarTreinoAoVoltar();
});

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

// Ao recarregar a página o histórico pode guardar o "estado" de uma ficha aberta antes; a página sempre começa na lista.
if (history.state && history.state.tela) history.replaceState(null, "");
carregarTreino();
atualizarMeusComentarios();
