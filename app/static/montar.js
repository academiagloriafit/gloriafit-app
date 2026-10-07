// Tela "Montar treino" do professor. A lógica do treino está em treino_modelo.js
// (testada à parte); aqui só desenhamos a tela e ligamos os botões.
import { iniciarBiblioteca } from "./biblioteca.js";
import { iniciarPainelDeSalvar } from "./salvar.js";
import * as M from "./treino_modelo.js";

const raiz = document.querySelector("[data-aluno]");
const CHAVE_RASCUNHO = "rascunho-treino-" + raiz.dataset.aluno;

const elAbas = document.getElementById("abas");
const elMontagem = document.getElementById("montagem");
const elProblemas = document.getElementById("problemas");
const elAviso = document.getElementById("aviso");
const botaoSalvar = document.getElementById("salvar");

// ------------------------------------------------------------------ estado da tela

let estado = lerRascunhoGuardado() || M.criarEstado();
let fichaAtual = 0;
let selecionados = new Set(); // uids marcados para juntar em bi-set
let confirmandoExclusao = false;
let mostrarProblemas = false; // vira true depois de clicar em "Salvar treino"
let erroDeBloco = "";
let focoPendente = null; // onde devolver o foco depois de redesenhar
let refs = {}; // pedaços da tela que atualizamos sem redesenhar tudo

// ------------------------------------------------------------------ rascunho

// O rascunho fica no sessionStorage do navegador: sobrevive a recarregar a página,
// mas some quando a aba é fechada. Se o navegador não deixar usar, a tela funciona igual.
function lerRascunhoGuardado() {
  try {
    const texto = sessionStorage.getItem(CHAVE_RASCUNHO);
    return texto ? M.lerRascunho(texto) : null;
  } catch {
    return null;
  }
}

function guardarRascunho() {
  try {
    sessionStorage.setItem(CHAVE_RASCUNHO, M.serializar(estado));
  } catch {
    /* sem armazenamento: segue sem rascunho */
  }
}

// Depois que o servidor confirmou o treino, o rascunho não serve mais: o próximo
// treino começa em branco.
function apagarRascunho() {
  try {
    sessionStorage.removeItem(CHAVE_RASCUNHO);
  } catch {
    /* sem armazenamento: nada a apagar */
  }
}

// ------------------------------------------------------------------ ajudantes de tela

// Cria um elemento. Texto sempre via textContent: nada do que vem do banco ou do
// teclado é interpretado como HTML.
function el(tag, props = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [chave, valor] of Object.entries(props)) {
    if (chave === "texto") e.textContent = valor;
    else if (chave === "classe") e.className = valor;
    else if (chave === "aoClicar") e.addEventListener("click", valor);
    else if (chave === "aoDigitar") e.addEventListener("input", valor);
    else if (chave === "aoMudar") e.addEventListener("change", valor);
    else if (valor === true) e.setAttribute(chave, "");
    else if (valor !== false && valor != null) e.setAttribute(chave, valor);
  }
  filhos.flat().forEach((f) => f && e.append(f));
  return e;
}

function anunciar(texto) {
  elAviso.textContent = texto;
}

function fichaDaTela() {
  return estado.fichas[fichaAtual];
}

function mudar(novoEstado, foco = null) {
  estado = novoEstado;
  focoPendente = foco;
  guardarRascunho();
  desenhar();
}

// ------------------------------------------------------------------ abas (as fichas)

function desenharAbas() {
  elAbas.textContent = "";
  estado.fichas.forEach((ficha, i) => {
    elAbas.append(
      el("button", {
        type: "button",
        role: "tab",
        classe: "aba" + (i === fichaAtual ? " aba-ativa" : ""),
        "aria-selected": i === fichaAtual ? "true" : "false",
        texto: ficha.nome.trim() || "Sem nome",
        aoClicar: () => {
          fichaAtual = i;
          selecionados.clear();
          confirmandoExclusao = false;
          erroDeBloco = "";
          desenhar();
        },
      }),
    );
  });
  if (estado.fichas.length < M.MAXIMO_FICHAS) {
    elAbas.append(
      el("button", {
        type: "button",
        classe: "aba aba-nova",
        texto: "+ Novo treino",
        aoClicar: () => {
          mudar(M.adicionarFicha(estado));
          fichaAtual = estado.fichas.length - 1;
          selecionados.clear();
          confirmandoExclusao = false;
          erroDeBloco = "";
          desenhar();
          anunciar("Criado: " + fichaDaTela().nome);
        },
      }),
    );
  }
}

// ------------------------------------------------------------------ nome da ficha

function desenharNomeDaFicha() {
  const ficha = fichaDaTela();
  const contador = el("p", { classe: "dica" });
  const atualizarContador = () => {
    const n = fichaDaTela().nome.trim().length;
    contador.textContent = `${n} de ${M.LIMITE_NOME_FICHA} letras. O Data4U aceita no máximo ${M.LIMITE_NOME_FICHA}.`;
  };
  atualizarContador();

  const campo = el("input", {
    id: "nome-ficha",
    type: "text",
    maxlength: M.LIMITE_NOME_FICHA,
    value: ficha.nome,
    autocomplete: "off",
    "data-campo": "nome",
    aoDigitar: (evento) => {
      estado = M.renomearFicha(estado, fichaAtual, evento.target.value);
      guardarRascunho();
      atualizarContador();
      desenharAbas(); // o nome aparece na aba
      atualizarProblemas();
    },
  });

  let botaoExcluir = null;
  if (estado.fichas.length > 1) {
    if (!confirmandoExclusao) {
      botaoExcluir = el("button", {
        type: "button",
        classe: "botao-discreto",
        texto: "Excluir este treino",
        aoClicar: () => {
          if (fichaDaTela().itens.length === 0) return excluirFicha();
          confirmandoExclusao = true;
          desenhar();
        },
      });
    } else {
      botaoExcluir = el(
        "span",
        { classe: "confirmacao" },
        el("span", { texto: `Excluir ${ficha.nome.trim() || "este treino"} e seus exercícios?` }),
        el("button", { type: "button", classe: "botao-perigo", texto: "Sim, excluir", aoClicar: excluirFicha }),
        el("button", {
          type: "button",
          classe: "botao-discreto",
          texto: "Não",
          aoClicar: () => {
            confirmandoExclusao = false;
            desenhar();
          },
        }),
      );
    }
  }

  return el(
    "div",
    { classe: "bloco-nome" },
    el("div", { classe: "campo campo-nome" }, el("label", { for: "nome-ficha", texto: "Nome do treino" }), campo),
    el("div", { classe: "nome-lateral" }, contador, botaoExcluir),
  );
}

function excluirFicha() {
  const nome = fichaDaTela().nome.trim() || "treino";
  estado = M.removerFicha(estado, fichaAtual);
  fichaAtual = Math.max(0, Math.min(fichaAtual, estado.fichas.length - 1));
  selecionados.clear();
  confirmandoExclusao = false;
  guardarRascunho();
  desenhar();
  anunciar("Excluído: " + nome);
}

// ------------------------------------------------------------------ lista de exercícios

function botaoDeAcao(texto, rotulo, foco, aoClicar, desligado = false) {
  return el("button", {
    type: "button",
    classe: "botao-icone",
    texto,
    "aria-label": rotulo,
    "data-foco": foco,
    disabled: desligado,
    aoClicar,
  });
}

function campoDePrescricao(item, campo, rotulo) {
  return el("input", {
    type: "text",
    classe: "campo-prescricao",
    maxlength: M.LIMITE_CAMPO,
    value: item[campo],
    autocomplete: "off",
    "aria-label": `${rotulo} de ${item.nome}`,
    "data-uid": item.uid,
    "data-campo": campo,
    aoDigitar: (evento) => {
      estado = M.atualizarItem(estado, fichaAtual, item.uid, campo, evento.target.value);
      guardarRascunho();
      atualizarProblemas();
    },
  });
}

function desenharLinha(item, etiqueta, dentroDeBloco) {
  const marcador = dentroDeBloco
    ? el("span", { classe: "celula-vazia" })
    : el(
        "label",
        { classe: "celula-marcar" },
        el("input", {
          type: "checkbox",
          "aria-label": "Selecionar " + item.nome,
          checked: selecionados.has(item.uid),
          aoMudar: (evento) => {
            if (evento.target.checked) selecionados.add(item.uid);
            else selecionados.delete(item.uid);
            erroDeBloco = "";
            atualizarBarraDeSelecao();
          },
        }),
      );

  return el(
    "li",
    { classe: "linha" + (dentroDeBloco ? " linha-bloco" : "") },
    marcador,
    el("span", { classe: "etiqueta", texto: etiqueta }),
    el("span", { classe: "linha-nome", texto: item.nome }),
    campoDePrescricao(item, "series", "Séries"),
    campoDePrescricao(item, "repeticoes", "Repetições"),
    campoDePrescricao(item, "carga", "Carga"),
    el("span", { classe: "celula-acoes" }, [
      botaoDeAcao("✕", "Remover " + item.nome, "remover", () => {
        selecionados.delete(item.uid);
        mudar(M.removerItem(estado, fichaAtual, item.uid), { tipo: "lista" });
        anunciar("Removido: " + item.nome);
      }),
    ]),
  );
}

function desenharLista() {
  const ficha = fichaDaTela();
  const etiquetas = M.etiquetas(ficha);
  const lista = M.unidades(ficha);
  const itens = el("ul", { classe: "linhas" });

  lista.forEach((unidade, indice) => {
    const primeiroUid = unidade.tipo === "item" ? unidade.item.uid : unidade.itens[0].uid;
    const ehPrimeira = indice === 0;
    const ehUltima = indice === lista.length - 1;
    const subir = () => mudar(M.moverUnidade(estado, fichaAtual, indice, -1), { tipo: "mover", uid: primeiroUid, direcao: -1 });
    const descer = () => mudar(M.moverUnidade(estado, fichaAtual, indice, 1), { tipo: "mover", uid: primeiroUid, direcao: 1 });

    if (unidade.tipo === "item") {
      const linha = desenharLinha(unidade.item, etiquetas.get(unidade.item.uid), false);
      linha.querySelector(".celula-acoes").prepend(
        botaoDeAcao("↑", "Subir " + unidade.item.nome, `mover-${primeiroUid}--1`, subir, ehPrimeira),
        botaoDeAcao("↓", "Descer " + unidade.item.nome, `mover-${primeiroUid}-1`, descer, ehUltima),
      );
      itens.append(linha);
    } else {
      const titulo = M.nomeDoBloco(unidade.itens.length);
      itens.append(
        el(
          "li",
          { classe: "cabecalho-bloco" },
          el("span", { classe: "bloco-titulo", texto: titulo }),
          el("span", { classe: "bloco-acoes" }, [
            botaoDeAcao("↑", `Subir o ${titulo.toLowerCase()}`, `mover-${primeiroUid}--1`, subir, ehPrimeira),
            botaoDeAcao("↓", `Descer o ${titulo.toLowerCase()}`, `mover-${primeiroUid}-1`, descer, ehUltima),
            el("button", {
              type: "button",
              classe: "botao-discreto",
              texto: "Desfazer",
              "aria-label": `Desfazer o ${titulo.toLowerCase()}`,
              aoClicar: () => mudar(M.desfazerBloco(estado, fichaAtual, unidade.bloco), { tipo: "lista" }),
            }),
          ]),
        ),
      );
      unidade.itens.forEach((item) => itens.append(desenharLinha(item, etiquetas.get(item.uid), true)));
    }
  });
  return itens;
}

function desenharCabecalhoDaLista() {
  const ficha = fichaDaTela();
  refs.contador = el("span", { classe: "contador-selecao" });
  refs.botaoJuntar = el("button", {
    type: "button",
    classe: "botao-escuro",
    texto: "Juntar em bi-set",
    aoClicar: () => {
      const r = M.unirEmBloco(estado, fichaAtual, [...selecionados]);
      if (!r.ok) {
        erroDeBloco = r.erro;
        atualizarBarraDeSelecao();
        return;
      }
      selecionados.clear();
      erroDeBloco = "";
      mudar(r.estado, { tipo: "lista" });
    },
  });
  refs.erroDeBloco = el("p", { classe: "erro-bloco", role: "alert" });
  atualizarBarraDeSelecao();

  return el(
    "div",
    { classe: "cabecalho-lista" },
    el(
      "h2",
      { tabindex: "-1", id: "titulo-exercicios" },
      "Exercícios ",
      el("span", { classe: "titulo-suave", texto: "· " + M.descreverFicha(ficha) }),
    ),
    el("div", { classe: "selecao" }, refs.contador, refs.botaoJuntar),
    refs.erroDeBloco,
  );
}

// Atualiza só o "2 selecionados" e o botão de juntar, sem redesenhar a lista
// (assim o foco do teclado fica onde está).
function atualizarBarraDeSelecao() {
  const n = selecionados.size;
  refs.contador.textContent = n === 1 ? "1 selecionado" : n + " selecionados";
  refs.botaoJuntar.textContent = n === 3 ? "Juntar em tri-set" : "Juntar em bi-set";
  refs.botaoJuntar.disabled = n < M.MINIMO_NO_BLOCO || n > M.MAXIMO_NO_BLOCO;
  refs.erroDeBloco.textContent = erroDeBloco;
}

function desenharMontagem() {
  elMontagem.textContent = "";
  const ficha = fichaDaTela();
  elMontagem.append(
    desenharNomeDaFicha(),
    el(
      "div",
      { classe: "cartao-lista" },
      desenharCabecalhoDaLista(),
      el(
        "div",
        { classe: "titulos-colunas", "aria-hidden": "true" },
        el("span", { classe: "coluna-nome", texto: "Exercício" }),
        el("span", { classe: "coluna-pequena", texto: "Séries" }),
        el("span", { classe: "coluna-pequena", texto: "Repetições" }),
        el("span", { classe: "coluna-pequena", texto: "Carga" }),
      ),
      ficha.itens.length
        ? desenharLista()
        : el("p", { classe: "lista-vazia", texto: "Escolha um exercício na lista ao lado para adicionar." }),
    ),
  );
}

// ------------------------------------------------------------------ problemas (botão "Salvar treino")

function atualizarProblemas() {
  const problemas = mostrarProblemas ? M.validar(estado) : [];
  elProblemas.textContent = "";
  elProblemas.hidden = problemas.length === 0;
  problemas.forEach((p) => elProblemas.append(el("li", { texto: p.mensagem })));

  // marca os campos com problema na ficha que está na tela
  const naTela = problemas.filter((p) => p.ficha === fichaAtual);
  elMontagem.querySelectorAll("[data-campo]").forEach((campo) => {
    const uid = campo.dataset.uid ? Number(campo.dataset.uid) : null;
    const ruim = naTela.some((p) => p.campo === campo.dataset.campo && p.uid === uid);
    if (ruim) campo.setAttribute("aria-invalid", "true");
    else campo.removeAttribute("aria-invalid");
  });
  return problemas;
}

const painelDeSalvar = iniciarPainelDeSalvar({
  alunoId: raiz.dataset.aluno,
  alunoNome: document.querySelector(".aluno-nome strong").textContent,
  obterEstado: () => estado,
  aoSalvar: apagarRascunho,
});

botaoSalvar.addEventListener("click", () => {
  mostrarProblemas = true;
  const problemas = M.validar(estado);
  if (problemas.length) {
    if (problemas[0].ficha !== fichaAtual) {
      fichaAtual = problemas[0].ficha;
      selecionados.clear();
      confirmandoExclusao = false;
    }
    anunciar("");
    desenhar();
    elProblemas.scrollIntoView({ block: "nearest" });
    return;
  }
  mostrarProblemas = false; // tudo certo: só volta a cobrar no próximo "Salvar treino"
  anunciar("");
  desenhar();
  painelDeSalvar.abrir(); // próxima etapa: nome do treino e quem montou
});

// ------------------------------------------------------------------ desenho geral

function devolverFoco() {
  const foco = focoPendente;
  focoPendente = null;
  if (!foco) return;
  if (foco.tipo === "lista") {
    document.getElementById("titulo-exercicios")?.focus();
  } else if (foco.tipo === "mover") {
    // volta ao mesmo botão; se ele ficou desligado (chegou na ponta), vai ao botão oposto
    const igual = elMontagem.querySelector(`[data-foco="mover-${foco.uid}-${foco.direcao}"]:not([disabled])`);
    const oposto = elMontagem.querySelector(`[data-foco="mover-${foco.uid}-${-foco.direcao}"]:not([disabled])`);
    (igual || oposto)?.focus();
  }
}

function desenhar() {
  desenharAbas();
  desenharMontagem();
  atualizarProblemas();
  devolverFoco();
}

iniciarBiblioteca(document.querySelector("[data-biblioteca]"), {
  aoAdicionar: (exercicio) => {
    const antes = estado;
    const novo = M.adicionarItem(estado, fichaAtual, exercicio);
    if (novo === antes) {
      anunciar(`Limite de ${M.MAXIMO_ITENS_POR_FICHA} exercícios por treino.`);
      return;
    }
    mudar(novo);
    anunciar(`Adicionado: ${exercicio.nome} (${fichaDaTela().nome.trim() || "treino"})`);
    // leva o novo exercício à vista, sem tirar o foco da lista de exercícios
    const linhas = elMontagem.querySelectorAll(".linha");
    linhas[linhas.length - 1]?.scrollIntoView({ block: "nearest" });
  },
});

desenhar();
