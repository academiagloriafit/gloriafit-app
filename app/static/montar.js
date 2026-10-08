// Tela "Lançar treino" do professor. A lógica do treino está em treino_modelo.js
// (testada à parte); aqui só desenhamos a tela e ligamos os botões.
// Palavras do Data4U: o TREINO tem um nome e várias FICHAS (A, B, C...); cada ficha
// tem exercícios com séries, repetições, peso, intervalo e observações.
import { iniciarBiblioteca } from "./biblioteca.js";
import { iniciarSalvar } from "./salvar.js";
import * as M from "./treino_modelo.js";

const raiz = document.querySelector("[data-aluno]");
const CHAVE_RASCUNHO = "rascunho-treino-" + raiz.dataset.aluno;
const CHAVE_DADOS = "rascunho-dados-" + raiz.dataset.aluno;

const elAbas = document.getElementById("abas");
const elMontagem = document.getElementById("montagem");
const elProblemas = document.getElementById("problemas");
const elAviso = document.getElementById("aviso");
const campoNome = document.getElementById("nome-treino");
const campoQuem = document.getElementById("quem-montou");
const dicaNome = document.getElementById("dica-nome-treino");
const botaoSalvar = document.getElementById("salvar");
const botaoCancelar = document.getElementById("cancelar");
const elConfirmarDescarte = document.getElementById("confirmar-descarte");
const areaMontagem = document.getElementById("area-montagem");

// ------------------------------------------------------------------ estado da tela

const MAXIMO_DE_MENSAGENS = 4; // problemas escritos na lista antes de "E mais N"

let estado = lerRascunhoGuardado() || M.criarEstado();
let fichaAtual = 0;
let selecionados = new Set(); // uids marcados para juntar em bi-set
let confirmandoExclusao = false;
let mostrarProblemas = false; // vira true depois de clicar em "Salvar treino"
let errosDoServidor = []; // o que o servidor recusou (ex.: nome de treino repetido)
let nomeEditadoPeloProfessor = false; // se sim, não trocamos o nome por outra sugestão
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
    sessionStorage.setItem(
      CHAVE_DADOS,
      JSON.stringify({ nome: campoNome.value, editado: nomeEditadoPeloProfessor, professor: campoQuem.value }),
    );
  } catch {
    /* sem armazenamento: segue sem rascunho */
  }
}

// Nome do treino e professor guardados junto com o rascunho (qualquer coisa fora do
// formato é ignorada).
function lerDadosGuardados() {
  try {
    const dados = JSON.parse(sessionStorage.getItem(CHAVE_DADOS) || "null");
    if (!dados || typeof dados !== "object") return;
    if (typeof dados.professor === "string") campoQuem.value = dados.professor.slice(0, 60);
    if (dados.editado === true && typeof dados.nome === "string") {
      campoNome.value = dados.nome.slice(0, 40);
      nomeEditadoPeloProfessor = true;
    }
  } catch {
    /* sem rascunho dos dados: campos começam em branco */
  }
}

// Depois que o servidor confirmou o treino (ou o professor descartou), o rascunho não
// serve mais: o próximo treino começa em branco.
function apagarRascunho() {
  try {
    sessionStorage.removeItem(CHAVE_RASCUNHO);
    sessionStorage.removeItem(CHAVE_DADOS);
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

// ------------------------------------------------------------------ nome do treino e professor

function atualizarDicaDoNome() {
  const n = M.tamanho(M.limparEspacos(campoNome.value));
  dicaNome.textContent = `${n} de ${M.LIMITE_NOME_TREINO} letras (limite do Data4U)`;
}

// Enquanto o professor não mexer no nome, ele acompanha as fichas ("TREINO ABC 08/10/26").
function atualizarNomeSugerido() {
  if (!nomeEditadoPeloProfessor) campoNome.value = M.sugerirNomeDoTreino(estado, M.formatarData(new Date()));
  atualizarDicaDoNome();
}

campoNome.addEventListener("input", () => {
  nomeEditadoPeloProfessor = true;
  errosDoServidor = [];
  atualizarDicaDoNome();
  guardarRascunho();
  atualizarProblemas();
});
campoQuem.addEventListener("input", () => {
  guardarRascunho();
  atualizarProblemas();
});
for (const campo of [campoNome, campoQuem]) {
  // Enter nestes dois campos salva, como no botão (os campos de uma linha só)
  campo.addEventListener("keydown", (evento) => {
    if (evento.key === "Enter" && !evento.isComposing) {
      evento.preventDefault();
      botaoSalvar.click();
    }
  });
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
        texto: "+ Nova ficha",
        aoClicar: () => {
          mudar(M.adicionarFicha(estado));
          fichaAtual = estado.fichas.length - 1;
          selecionados.clear();
          confirmandoExclusao = false;
          erroDeBloco = "";
          desenhar();
          anunciar("Criada: " + fichaDaTela().nome);
        },
      }),
    );
  }
}

// ------------------------------------------------------------------ nome da ficha

function desenharNomeDaFicha() {
  const ficha = fichaDaTela();
  const contador = el("span", { classe: "dica" });
  const atualizarContador = () => {
    const n = fichaDaTela().nome.trim().length;
    contador.textContent = `${n}/${M.LIMITE_NOME_FICHA} letras`; // o Data4U aceita no máximo 15
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
      atualizarNomeSugerido(); // e pode mudar o nome sugerido do treino
      atualizarProblemas();
    },
  });

  let botaoExcluir = null;
  if (estado.fichas.length > 1) {
    if (!confirmandoExclusao) {
      botaoExcluir = el("button", {
        type: "button",
        classe: "botao-discreto",
        texto: "Excluir ficha",
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
        el("span", { texto: `Excluir ${ficha.nome.trim() || "esta ficha"} e seus exercícios?` }),
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
    el("div", { classe: "campo campo-nome" }, el("label", { for: "nome-ficha", texto: "Nome da ficha" }), campo),
    contador,
    desenharSelecao(),
    el("div", { classe: "nome-lateral" }, botaoExcluir),
    refs.erroDeBloco,
  );
}

function excluirFicha() {
  const nome = fichaDaTela().nome.trim() || "ficha";
  estado = M.removerFicha(estado, fichaAtual);
  fichaAtual = Math.max(0, Math.min(fichaAtual, estado.fichas.length - 1));
  selecionados.clear();
  confirmandoExclusao = false;
  guardarRascunho();
  desenhar();
  anunciar("Excluída: " + nome);
}

// ------------------------------------------------------------------ lista de exercícios

function botaoDeAcao(texto, rotulo, foco, aoClicar, desligado = false, classe = "botao-icone") {
  return el("button", {
    type: "button",
    classe,
    texto,
    title: rotulo,
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

// Intervalo em minutos e segundos (como no Data4U). Só aceita números.
function campoDeIntervalo(item) {
  const campo = (nomeDoCampo, rotulo, dica) =>
    el("input", {
      type: "text",
      inputmode: "numeric",
      classe: "campo-prescricao campo-intervalo",
      maxlength: 2,
      value: item[nomeDoCampo],
      placeholder: dica,
      autocomplete: "off",
      "aria-label": `Intervalo (${rotulo}) de ${item.nome}`,
      "data-uid": item.uid,
      "data-campo": nomeDoCampo,
      aoDigitar: (evento) => {
        estado = M.atualizarItem(estado, fichaAtual, item.uid, nomeDoCampo, evento.target.value);
        // o modelo tira o que não é número: a caixa mostra o que ficou valendo
        evento.target.value = fichaDaTela().itens.find((i) => i.uid === item.uid)[nomeDoCampo];
        guardarRascunho();
        atualizarProblemas();
      },
    });
  return el(
    "span",
    { classe: "celula-intervalo", role: "group", "aria-label": `Intervalo de ${item.nome}` },
    campo("pausaMin", "minutos", "min"),
    el("span", { classe: "dois-pontos", texto: ":", "aria-hidden": "true" }),
    campo("pausaSeg", "segundos", "seg"),
  );
}

function campoDeObservacao(item) {
  return el("input", {
    type: "text",
    classe: "campo-observacao",
    maxlength: M.LIMITE_OBSERVACAO,
    value: item.observacao,
    placeholder: "Observação (opcional)",
    autocomplete: "off",
    "aria-label": `Observação de ${item.nome}`,
    "data-uid": item.uid,
    "data-campo": "observacao",
    aoDigitar: (evento) => {
      estado = M.atualizarItem(estado, fichaAtual, item.uid, "observacao", evento.target.value);
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
    campoDePrescricao(item, "carga", "Peso"),
    campoDeIntervalo(item),
    // segunda linha do exercício: observação (opcional) e os botões de mover e remover
    el(
      "div",
      { classe: "linha-segunda" },
      el("span", { classe: "rotulo-obs", texto: "Obs.", "aria-hidden": "true" }),
      campoDeObservacao(item),
      el("span", { classe: "celula-acoes" }, [
        botaoDeAcao("Remover", "Remover " + item.nome, "remover", () => {
          selecionados.delete(item.uid);
          mudar(M.removerItem(estado, fichaAtual, item.uid), { tipo: "lista" });
          anunciar("Removido: " + item.nome);
        }, false, "botao-texto"),
      ]),
    ),
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
              classe: "botao-texto",
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

// "5 exercícios, 1 bi-set", quantos estão marcados e o botão de juntar em bi-set/tri-set.
// Fica na mesma linha do nome da ficha para a tabela de exercícios subir na tela.
function desenharSelecao() {
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
    { classe: "selecao" },
    // título só para leitor de tela e para devolver o foco depois de mover ou remover
    el("h2", { tabindex: "-1", id: "titulo-exercicios", classe: "so-leitor", texto: "Exercícios da ficha" }),
    el("span", { classe: "so-leitor", texto: M.descreverFicha(ficha) }), // "5 exercícios, 1 bi-set", só para leitor de tela
    refs.contador,
    refs.botaoJuntar,
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
    el(
      "div",
      { classe: "cartao-lista" },
      desenharNomeDaFicha(),
      el(
        "div",
        { classe: "titulos-colunas", "aria-hidden": "true" },
        el("span", { classe: "coluna-nome", texto: "Exercício" }),
        el("span", { classe: "coluna-pequena", texto: "Séries" }),
        el("span", { classe: "coluna-pequena", texto: "Repetições" }),
        el("span", { classe: "coluna-pequena", texto: "Peso" }),
        el("span", { classe: "coluna-pequena", texto: "Intervalo" }),
      ),
      ficha.itens.length
        ? desenharLista()
        : el("p", { classe: "lista-vazia", texto: "Escolha um exercício na lista ao lado para adicionar a esta ficha." }),
    ),
  );
}

// ------------------------------------------------------------------ problemas (botão "Salvar treino")

// Tudo o que impede de salvar, na ordem da tela: nome do treino e professor (no alto),
// depois as fichas, e por fim o que o servidor recusou.
function listarProblemas() {
  const dados = M.validarDadosDoTreino({ nomeTreino: campoNome.value, montadoPor: campoQuem.value });
  return [
    ...dados.map((p) => ({ tipo: "dados", campo: p.campo, mensagem: p.mensagem })),
    ...M.validar(estado).map((p) => ({ tipo: "ficha", ...p })),
    ...errosDoServidor.map((mensagem) => ({ tipo: "servidor", campo: "nome-treino", mensagem })),
  ];
}

function atualizarProblemas() {
  const problemas = mostrarProblemas || errosDoServidor.length ? listarProblemas() : [];
  elProblemas.textContent = "";
  elProblemas.hidden = problemas.length === 0;
  // só as primeiras mensagens: a lista não pode tomar a tela quando faltam muitos campos
  problemas.slice(0, MAXIMO_DE_MENSAGENS).forEach((p) => elProblemas.append(el("li", { texto: p.mensagem })));
  if (problemas.length > MAXIMO_DE_MENSAGENS) {
    const resto = problemas.length - MAXIMO_DE_MENSAGENS;
    elProblemas.append(el("li", { texto: `E mais ${resto} ${resto === 1 ? "problema" : "problemas"}. Os campos que faltam estão em vermelho.` }));
  }

  // as abas das fichas com problema ganham uma bolinha vermelha
  const fichasComProblema = new Set(problemas.filter((p) => p.tipo === "ficha").map((p) => p.ficha));
  elAbas.querySelectorAll(".aba:not(.aba-nova)").forEach((aba, i) => aba.classList.toggle("aba-com-problema", fichasComProblema.has(i)));

  // campos do alto (nome do treino e professor)
  for (const campo of [campoNome, campoQuem]) {
    const ruim = problemas.some((p) => p.tipo !== "ficha" && p.campo === campo.id);
    if (ruim) campo.setAttribute("aria-invalid", "true");
    else campo.removeAttribute("aria-invalid");
  }

  // marca os campos com problema na ficha que está na tela
  const naTela = problemas.filter((p) => p.tipo === "ficha" && p.ficha === fichaAtual);
  elMontagem.querySelectorAll("[data-campo]").forEach((campo) => {
    const uid = campo.dataset.uid ? Number(campo.dataset.uid) : null;
    const ruim = naTela.some((p) => p.campo === campo.dataset.campo && p.uid === uid);
    if (ruim) campo.setAttribute("aria-invalid", "true");
    else campo.removeAttribute("aria-invalid");
  });
  return problemas;
}

// ------------------------------------------------------------------ salvar e cancelar

const salvar = iniciarSalvar({
  alunoId: raiz.dataset.aluno,
  alunoNome: document.querySelector(".aluno-nome strong").textContent,
  obterEstado: () => estado,
  obterDados: () => ({ nomeTreino: campoNome.value, montadoPor: campoQuem.value }),
  aoSalvar: apagarRascunho,
  aoTravar: (travado) => {
    areaMontagem.inert = travado; // nada se edita enquanto o servidor responde
    botaoSalvar.disabled = travado;
    botaoSalvar.textContent = travado ? "Salvando…" : "Salvar treino";
    if (!travado) botaoSalvar.focus();
  },
  aoErros: (mensagens, { nomeJaUsado }) => {
    errosDoServidor = mensagens;
    atualizarProblemas();
    elProblemas.scrollIntoView({ block: "nearest" });
    if (nomeJaUsado) campoNome.focus();
  },
});

botaoSalvar.addEventListener("click", () => {
  mostrarProblemas = true;
  errosDoServidor = [];
  const problemas = atualizarProblemas();
  if (problemas.length) {
    const primeiro = problemas[0];
    if (primeiro.tipo === "dados") {
      document.getElementById(primeiro.campo).focus();
    } else if (primeiro.ficha !== fichaAtual) {
      fichaAtual = primeiro.ficha;
      selecionados.clear();
      confirmandoExclusao = false;
      desenhar();
    }
    anunciar("");
    elProblemas.scrollIntoView({ block: "nearest" });
    return;
  }
  mostrarProblemas = false; // tudo certo: só volta a cobrar no próximo "Salvar treino"
  atualizarProblemas();
  anunciar("");
  salvar.enviar();
});

function temAlgoParaPerder() {
  return estado.fichas.some((f) => f.itens.length > 0) || campoQuem.value.trim() !== "" || nomeEditadoPeloProfessor;
}

function voltarParaAFicha() {
  window.location.href = document.querySelector("a.voltar").href;
}

// Um só aviso ao cancelar (no Data4U há dois, e num deles "Sim" grava). Aqui: "Sim, descartar"
// joga o treino fora, "Não, continuar" volta para a tela.
botaoCancelar.addEventListener("click", () => {
  if (!temAlgoParaPerder()) return voltarParaAFicha();
  botaoCancelar.hidden = true;
  elConfirmarDescarte.hidden = false;
  document.getElementById("continuar-editando").focus();
});
document.getElementById("descartar").addEventListener("click", () => {
  apagarRascunho();
  voltarParaAFicha();
});
document.getElementById("continuar-editando").addEventListener("click", () => {
  elConfirmarDescarte.hidden = true;
  botaoCancelar.hidden = false;
  botaoCancelar.focus();
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
  atualizarNomeSugerido();
  atualizarProblemas();
  devolverFoco();
}

iniciarBiblioteca(document.querySelector("[data-biblioteca]"), {
  aoAdicionar: (exercicio) => {
    const antes = estado;
    const novo = M.adicionarItem(estado, fichaAtual, exercicio);
    if (novo === antes) {
      anunciar(`Limite de ${M.MAXIMO_ITENS_POR_FICHA} exercícios por ficha.`);
      return;
    }
    mudar(novo);
    anunciar(`Adicionado: ${exercicio.nome} (${fichaDaTela().nome.trim() || "ficha"})`);
    // leva o novo exercício à vista, sem tirar o foco da lista de exercícios
    const linhas = elMontagem.querySelectorAll(".linha");
    linhas[linhas.length - 1]?.scrollIntoView({ block: "nearest" });
  },
});

lerDadosGuardados();
desenhar();
