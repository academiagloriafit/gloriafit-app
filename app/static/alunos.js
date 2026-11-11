// Tela "Buscar aluno": pede a lista ao servidor (/api/alunos) a cada pausa na
// digitação e desenha as linhas. Cada linha é um link para a ficha do aluno.
import { MENSAGEM_NAO_AUTORIZADO } from "./api.js";
import { iniciais, nomeDePessoa } from "./nomes.js";
import { andamentoDoAluno, filtroValido, parametrosDaBusca, textoDoUltimoTreino, ultimoTreinoEmAlerta } from "./painel_alunos_modelo.js";

const campo = document.getElementById("busca-aluno");
const lista = document.getElementById("lista-alunos");
const resumo = document.getElementById("resumo-alunos");

let temporizador = null;
let pedidoAtual = null; // para cancelar a busca anterior se o usuário digitar mais
let filtroAtual = ""; // (11/11/2026) o cartão ou a aba escolhida: só aqueles alunos aparecem na lista
const botoesDeFiltro = [...document.querySelectorAll("[data-filtro]")];

// valor ausente: a célula mostra "—" e ganha a classe "sem-valor" (no celular ela some)
function celula(classe, texto, ausente = false) {
  const span = document.createElement("span");
  span.className = ausente ? classe + " sem-valor" : classe;
  span.textContent = texto; // textContent: o texto nunca é interpretado como HTML
  return span;
}

// A situação vira uma etiqueta colorida. A letra só vira nome de classe se for uma das
// letras conhecidas (nunca se monta classe ou HTML com texto vindo do servidor).
const LETRAS_DE_SITUACAO = /^[ATPDIC]$/;

function celulaDaSituacao(aluno) {
  const caixa = celula("aluno-situacao", "");
  if (aluno.provisorio) {
    caixa.append(celula("selo-situacao", "Provisório"));
  } else if (typeof aluno.situacao_nome === "string" && aluno.situacao_nome) {
    const etiqueta = celula("selo-situacao", aluno.situacao_nome);
    if (LETRAS_DE_SITUACAO.test(aluno.situacao)) etiqueta.classList.add("situacao-" + aluno.situacao);
    caixa.append(etiqueta);
  } else {
    caixa.textContent = "—";
    caixa.classList.add("sem-valor");
  }
  return caixa;
}

// O nome com a foto do aluno (a da catraca) ou, sem foto, o círculo das iniciais na frente. O nome aparece "Mariana de Souza".
// A foto vem de /alunos/<id>/foto (só abre em computador autorizado); o id já foi conferido como número inteiro.
function celulaDoNome(aluno) {
  const caixa = celula("aluno-nome-lista", "");
  let circulo;
  if (aluno.foto === true) {
    circulo = document.createElement("img");
    circulo.className = "avatar-aluno avatar-foto";
    circulo.src = "/alunos/" + aluno.id + "/foto";
    circulo.alt = "";
    circulo.width = 40;
    circulo.height = 40;
    circulo.loading = "lazy";
    circulo.decoding = "async";
    circulo.dataset.nome = nomeDePessoa(aluno.nome); // a legenda da foto ampliada (foto_grande.js)
    circulo.title = "Clique para ampliar";
  } else {
    circulo = celula("avatar-aluno", iniciais(aluno.nome));
    circulo.setAttribute("aria-hidden", "true");
  }
  const texto = celula("aluno-nome-texto", "");
  texto.append(celula("aluno-nome-principal", nomeDePessoa(aluno.nome)));
  texto.append(celula("aluno-nome-matricula", Number.isInteger(aluno.matricula) ? `Matrícula ${aluno.matricula}` : aluno.provisorio ? "Provisório" : "Sem matrícula"));
  caixa.append(circulo, texto);
  return caixa;
}

// A barra "18 de 30 sessões" do treino ativo (a largura vai pelo CSSOM: a política de segurança não bloqueia).
function celulaDoAndamento(aluno) {
  const andamento = andamentoDoAluno(aluno);
  if (!andamento.texto) return celula("aluno-andamento", "—", true);
  const caixa = celula("aluno-andamento", "");
  if (andamento.fracao !== null) {
    const barra = celula("aluno-barra", "");
    barra.append(celula("aluno-barra-cheia", ""));
    barra.style.setProperty("--progresso", String(andamento.fracao));
    caixa.append(barra);
  }
  caixa.append(celula("aluno-andamento-texto", andamento.texto));
  return caixa;
}

// "Há 9 dias" em laranja quando o aluno está sumindo; só aparece para quem tem treino.
function celulaDoUltimo(aluno) {
  if (!aluno.treino_atual && !Number.isInteger(aluno.dias_sem_treinar)) return celula("aluno-ultimo", "—", true);
  const caixa = celula("aluno-ultimo", textoDoUltimoTreino(aluno.dias_sem_treinar));
  if (ultimoTreinoEmAlerta(aluno.dias_sem_treinar)) caixa.classList.add("aluno-ultimo-alerta");
  return caixa;
}

function desenharLinha(aluno) {
  if (!Number.isInteger(aluno.id)) return null; // não monta link com id estranho

  const li = document.createElement("li");
  const link = document.createElement("a");
  link.className = "linha-aluno";
  link.href = "/alunos/" + aluno.id;

  link.append(
    celulaDoNome(aluno),
    aluno.treino_atual ? celula("aluno-treino", aluno.treino_atual) : celula("aluno-treino", "Sem treino ativo", true),
    celulaDoAndamento(aluno),
    celulaDoUltimo(aluno),
    celulaDaSituacao(aluno),
    celula("aluno-abrir", "Abrir ficha"),
  );
  li.append(link);
  return li;
}

function desenhar(resultado, havia_texto) {
  lista.textContent = "";
  resultado.alunos.forEach((aluno) => {
    const linha = desenharLinha(aluno);
    if (linha) lista.append(linha);
  });

  if (resultado.total === 0) {
    resumo.textContent = havia_texto ? "Nenhum aluno encontrado." : "Ainda não há alunos cadastrados.";
  } else if (resultado.total > resultado.alunos.length) {
    resumo.textContent = `Mostrando ${resultado.alunos.length} de ${resultado.total}. Digite mais letras ou números para afinar.`;
  } else {
    resumo.textContent = resultado.total === 1 ? "1 aluno" : `${resultado.total} alunos`;
  }
}

function buscar() {
  if (pedidoAtual) pedidoAtual.abort();
  pedidoAtual = new AbortController();
  const texto = campo.value.trim();

  fetch("/api/alunos?" + parametrosDaBusca(texto, filtroAtual), { signal: pedidoAtual.signal })
    .then((resposta) => {
      if (resposta.status === 401) throw new Error("nao-autorizado");
      if (!resposta.ok) throw new Error("Erro " + resposta.status);
      return resposta.json();
    })
    .then((resultado) => desenhar(resultado, texto !== "" || filtroAtual !== ""))
    .catch((erro) => {
      if (erro.name === "AbortError") return; // busca antiga cancelada: normal
      lista.textContent = "";
      resumo.textContent =
        erro.message === "nao-autorizado" ? MENSAGEM_NAO_AUTORIZADO : "Não consegui carregar os alunos. Tente de novo.";
    });
}

campo.addEventListener("input", () => {
  // Espera 200 ms sem digitar antes de buscar (evita um pedido a cada letra).
  clearTimeout(temporizador);
  temporizador = setTimeout(buscar, 200);
});

// Cartões do alto e abas: um clique filtra; clicar de novo no mesmo cartão volta para "Todos".
function escolherFiltro(filtro) {
  filtroAtual = filtro === filtroAtual ? "" : filtroValido(filtro);
  for (const botao of botoesDeFiltro) botao.setAttribute("aria-pressed", String(botao.dataset.filtro === filtroAtual));
  buscar();
}
for (const botao of botoesDeFiltro) botao.addEventListener("click", () => escolherFiltro(botao.dataset.filtro));

buscar();
