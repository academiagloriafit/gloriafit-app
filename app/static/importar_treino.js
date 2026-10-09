// Botão "Importar treino" da tela de lançar treino: o professor começa de um treino pronto em vez de
// partir do zero. Duas origens (abas):
//   - Treino padrão: os treinos guardados com "Salvar como treino padrão";
//   - Treino de outro aluno: busca o aluno, escolhe um dos treinos dele.
// O servidor só LÊ (nada é gravado para o aluno). O treino escolhido é entregue a quem chamou
// (`aoCarregar`), que o coloca na tela de montar; o professor confere, ajusta e salva como sempre.
import { buscarJson, enviarJson, textoDoErro } from "./api.js";
import { el } from "./dom.js";

const SEM_REDE = "Não consegui falar com o servidor (sem resposta ou sem rede). Confira a rede e tente de novo.";
const LIMITE_DE_ALUNOS = 30;
const PAUSA_DA_BUSCA_MS = 250;

const pegar = (id) => document.getElementById(id);

// temTreinoNaTela(): true se já há exercícios na tela (copiar vai substituí-los: pede confirmação).
// aoCarregar(treino, origem): põe o treino na tela; devolve null se deu certo ou o texto do problema.
export function iniciarImportacao({ temTreinoNaTela, aoCarregar }) {
  const botaoAbrir = pegar("abrir-importar");
  const painel = pegar("painel-importar");
  const abaPadrao = pegar("aba-padrao");
  const abaAluno = pegar("aba-aluno");
  const conteudoPadrao = pegar("conteudo-padrao");
  const conteudoAluno = pegar("conteudo-aluno");
  const estadoPadroes = pegar("estado-padroes");
  const listaPadroes = pegar("lista-padroes");
  const campoBusca = pegar("busca-aluno-importar");
  const estadoAlunos = pegar("estado-alunos");
  const listaAlunos = pegar("lista-alunos-importar");
  const blocoBusca = pegar("bloco-busca-aluno");
  const blocoTreinos = pegar("treinos-do-aluno");
  const tituloTreinos = pegar("titulo-treinos-do-aluno");
  const estadoTreinos = pegar("estado-treinos");
  const listaTreinos = pegar("lista-treinos-importar");
  const aviso = pegar("aviso-importar");

  let ocupado = false; // um pedido por vez: clique duplo não manda duas vezes
  let buscaAtual = null; // para cancelar a busca de aluno anterior se o professor digitar mais
  let temporizador = null;

  // ---------------------------------------------------------------- aviso do painel

  function avisar(texto, erro = false) {
    aviso.textContent = texto;
    aviso.classList.toggle("aviso-erro", erro);
  }

  // ---------------------------------------------------------------- abrir, fechar, trocar de aba

  function mostrarAba(qual) {
    const padrao = qual === "padrao";
    abaPadrao.classList.toggle("aba-ativa", padrao);
    abaPadrao.setAttribute("aria-selected", String(padrao));
    abaAluno.classList.toggle("aba-ativa", !padrao);
    abaAluno.setAttribute("aria-selected", String(!padrao));
    conteudoPadrao.hidden = !padrao;
    conteudoAluno.hidden = padrao;
    avisar("");
    if (padrao) carregarPadroes();
    else if (listaAlunos.children.length === 0) buscarAlunos();
  }

  function abrir() {
    painel.hidden = false;
    botaoAbrir.setAttribute("aria-expanded", "true");
    mostrarAba("padrao");
    abaPadrao.focus();
  }

  function fechar() {
    painel.hidden = true;
    botaoAbrir.setAttribute("aria-expanded", "false");
    clearTimeout(temporizador);
    buscaAtual?.abort();
  }

  botaoAbrir.addEventListener("click", () => (painel.hidden ? abrir() : fechar()));
  pegar("fechar-importar").addEventListener("click", () => {
    fechar();
    botaoAbrir.focus();
  });
  abaPadrao.addEventListener("click", () => mostrarAba("padrao"));
  abaAluno.addEventListener("click", () => mostrarAba("aluno"));

  // ---------------------------------------------------------------- uma linha de lista (com botões que viram confirmação)

  // `botoes()` devolve os botões normais da linha. `confirmar(area, voltar)` troca os botões por uma pergunta
  // (devolvem o foco para quem faz sentido).
  function linhaDeLista({ titulo, selos = [], detalhe, botoes }) {
    const acoes = el("div", { classe: "importar-acoes" });
    const mostrarBotoes = () => acoes.replaceChildren(...botoes(acoes, mostrarBotoes));
    mostrarBotoes();
    return el(
      "li",
      { classe: "linha-importar" },
      el(
        "div",
        { classe: "importar-texto" },
        el("span", { classe: "importar-titulo" }, titulo, selos.map((s) => el("span", { classe: s.classe, texto: s.texto }))),
        el("span", { classe: "dica", texto: detalhe }),
      ),
      acoes,
    );
  }

  function perguntar(acoes, voltar, { texto, sim, textoDoSim, classeDoSim = "botao-perigo" }) {
    const nao = el("button", { type: "button", classe: "botao-discreto", texto: "Não", aoClicar: () => { voltar(); acoes.querySelector("button")?.focus(); } });
    acoes.replaceChildren(
      el(
        "span",
        { classe: "confirmacao" },
        el("span", { texto }),
        el("button", { type: "button", classe: classeDoSim, texto: textoDoSim, aoClicar: sim }),
        nao,
      ),
    );
    nao.focus();
  }

  // ---------------------------------------------------------------- usar um treino (padrão ou de aluno)

  async function usar(url, origem) {
    if (ocupado) return;
    ocupado = true;
    avisar("Abrindo o treino…");
    let resposta;
    try {
      resposta = await buscarJson(url);
    } catch {
      avisar(SEM_REDE, true);
      ocupado = false;
      return;
    }
    ocupado = false;
    if (resposta.status !== 200) {
      avisar(textoDoErro(resposta, "O servidor não conseguiu abrir o treino"), true);
      return;
    }
    const problema = aoCarregar(resposta.corpo, origem);
    if (problema) {
      avisar(problema, true);
      return;
    }
    avisar("");
    fechar();
  }

  // Botão "Usar este treino": se já há exercícios na tela, antes pergunta se pode substituir.
  function botaoUsar(url, origem) {
    return (acoes, voltar) => {
      const botao = el("button", {
        type: "button",
        classe: "botao-escuro",
        texto: "Usar este treino",
        "aria-label": `Usar o treino ${origem}`,
        aoClicar: () => {
          if (!temTreinoNaTela()) return usar(url, origem);
          perguntar(acoes, voltar, {
            texto: "Isto substitui o treino que está na tela. Continuar?",
            textoDoSim: "Sim, substituir",
            sim: () => usar(url, origem),
          });
        },
      });
      return [botao];
    };
  }

  // ---------------------------------------------------------------- aba "Treino padrão"

  async function carregarPadroes() {
    estadoPadroes.textContent = "Carregando…";
    listaPadroes.textContent = "";
    let resposta;
    try {
      resposta = await buscarJson("/api/modelos");
    } catch {
      estadoPadroes.textContent = SEM_REDE;
      return;
    }
    if (resposta.status !== 200 || !Array.isArray(resposta.corpo?.modelos)) {
      estadoPadroes.textContent = textoDoErro(resposta, "Não consegui carregar os treinos padrão");
      return;
    }
    const modelos = resposta.corpo.modelos.filter((m) => Number.isInteger(m?.id));
    estadoPadroes.textContent = modelos.length
      ? ""
      : 'Ainda não há treino padrão. Monte um treino e use "Salvar como treino padrão" para guardar o primeiro.';
    listaPadroes.textContent = "";
    modelos.forEach((m) => listaPadroes.append(linhaDoPadrao(m)));
  }

  function linhaDoPadrao(m) {
    const detalhe = [m.resumo, m.sessoes_por_ficha ? `${m.sessoes_por_ficha} treinos por ficha` : null, m.montado_por ? `por ${m.montado_por}` : null]
      .filter((parte) => typeof parte === "string" && parte)
      .join(" · ");
    const usarEsteTreino = botaoUsar(`/api/modelos/${encodeURIComponent(m.id)}`, m.nome);
    return linhaDeLista({
      titulo: m.nome,
      detalhe,
      botoes: (acoes, voltar) => [
        ...usarEsteTreino(acoes, voltar),
        el("button", {
          type: "button",
          classe: "botao-discreto",
          texto: "Excluir",
          "aria-label": `Excluir o treino padrão ${m.nome}`,
          aoClicar: () =>
            perguntar(acoes, voltar, {
              texto: `Excluir o padrão "${m.nome}"? Os treinos que já foram copiados para alunos não mudam.`,
              textoDoSim: "Sim, excluir",
              sim: () => excluirPadrao(m),
            }),
        }),
      ],
    });
  }

  async function excluirPadrao(m) {
    if (ocupado) return;
    ocupado = true;
    avisar("Excluindo…");
    let resposta;
    try {
      resposta = await enviarJson(`/api/modelos/${encodeURIComponent(m.id)}/excluir`, {});
    } catch {
      ocupado = false;
      avisar("Não consegui confirmar se o treino padrão foi excluído (sem resposta ou sem rede). Confira a lista.", true);
      carregarPadroes();
      return;
    }
    ocupado = false;
    if (resposta.status === 200 || resposta.status === 404) {
      avisar(`Treino padrão "${m.nome}" excluído.`);
    } else {
      avisar(textoDoErro(resposta, "O servidor não conseguiu excluir"), true);
    }
    carregarPadroes();
  }

  // ---------------------------------------------------------------- aba "Treino de outro aluno"

  function desenharAlunos(resultado, haviaTexto) {
    listaAlunos.textContent = "";
    const alunos = resultado.alunos.filter((a) => Number.isInteger(a?.id) && typeof a.nome === "string");
    alunos.forEach((aluno) => {
      const detalhe = [
        Number.isInteger(aluno.matricula) ? `Matrícula ${aluno.matricula}` : null,
        aluno.provisorio ? "Provisório" : aluno.situacao_nome,
        aluno.ultimo_treino ? `Último treino: ${aluno.ultimo_treino}` : "Sem treino",
      ]
        .filter((parte) => typeof parte === "string" && parte)
        .join(" · ");
      listaAlunos.append(
        linhaDeLista({
          titulo: aluno.nome,
          detalhe,
          botoes: () => [
            el("button", {
              type: "button",
              classe: "botao-escuro",
              texto: "Ver treinos",
              "aria-label": `Ver os treinos de ${aluno.nome}`,
              aoClicar: () => escolherAluno(aluno),
            }),
          ],
        }),
      );
    });
    if (resultado.total === 0) {
      estadoAlunos.textContent = haviaTexto ? "Nenhum aluno encontrado." : "Ainda não há alunos cadastrados.";
    } else if (resultado.total > alunos.length) {
      estadoAlunos.textContent = `Mostrando ${alunos.length} de ${resultado.total}. Digite mais letras ou números para afinar.`;
    } else {
      estadoAlunos.textContent = resultado.total === 1 ? "1 aluno" : `${resultado.total} alunos`;
    }
  }

  async function buscarAlunos() {
    buscaAtual?.abort();
    const controle = new AbortController();
    buscaAtual = controle;
    const texto = campoBusca.value.trim();
    const parametros = new URLSearchParams({ limite: String(LIMITE_DE_ALUNOS) });
    if (texto) parametros.set("q", texto);
    estadoAlunos.textContent = "Buscando…";
    let resposta;
    try {
      resposta = await buscarJson("/api/alunos?" + parametros.toString(), controle.signal);
    } catch (erro) {
      if (controle.signal.aborted) return; // busca antiga cancelada (digitou mais ou fechou o painel): normal
      listaAlunos.textContent = "";
      estadoAlunos.textContent = SEM_REDE;
      return;
    }
    if (resposta.status !== 200 || !Array.isArray(resposta.corpo?.alunos)) {
      listaAlunos.textContent = "";
      estadoAlunos.textContent = textoDoErro(resposta, "Não consegui carregar os alunos");
      return;
    }
    desenharAlunos(resposta.corpo, texto !== "");
  }

  campoBusca.addEventListener("input", () => {
    // Espera um pouco sem digitar antes de buscar (evita um pedido a cada letra).
    clearTimeout(temporizador);
    temporizador = setTimeout(buscarAlunos, PAUSA_DA_BUSCA_MS);
  });

  async function escolherAluno(aluno) {
    blocoBusca.hidden = true;
    blocoTreinos.hidden = false;
    tituloTreinos.textContent = `Treinos de ${aluno.nome}`;
    listaTreinos.textContent = "";
    estadoTreinos.textContent = "Carregando…";
    pegar("voltar-alunos").focus();
    let resposta;
    try {
      resposta = await buscarJson(`/api/alunos/${encodeURIComponent(aluno.id)}/treinos-para-copiar`);
    } catch {
      estadoTreinos.textContent = SEM_REDE;
      return;
    }
    if (resposta.status !== 200 || !Array.isArray(resposta.corpo?.treinos)) {
      estadoTreinos.textContent = textoDoErro(resposta, "Não consegui carregar os treinos do aluno");
      return;
    }
    const treinos = resposta.corpo.treinos.filter((t) => Number.isInteger(t?.id));
    estadoTreinos.textContent = treinos.length ? "" : "Este aluno ainda não tem treino para copiar.";
    treinos.forEach((t) => listaTreinos.append(linhaDoTreino(aluno, t)));
  }

  function linhaDoTreino(aluno, t) {
    const selos = [{ classe: "selo-treino " + (t.ativo ? "selo-treino-ativo" : "selo-treino-inativo"), texto: t.ativo ? "Ativo" : "Inativo" }];
    if (t.do_data4u) selos.push({ classe: "selo-origem", texto: "Data4U" });
    const detalhe = [t.inicio ? `desde ${t.inicio}` : null, t.resumo, t.montado_por ? `por ${t.montado_por}` : null]
      .filter((parte) => typeof parte === "string" && parte)
      .join(" · ");
    return linhaDeLista({
      titulo: t.nome,
      selos,
      detalhe,
      botoes: botaoUsar(`/api/treinos/${encodeURIComponent(t.id)}/para-montar`, `${t.nome} (${aluno.nome})`),
    });
  }

  pegar("voltar-alunos").addEventListener("click", () => {
    blocoTreinos.hidden = true;
    blocoBusca.hidden = false;
    avisar("");
    campoBusca.focus();
  });

  return { abrir, fechar };
}
