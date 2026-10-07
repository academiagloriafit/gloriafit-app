// Tela "Buscar aluno": pede a lista ao servidor (/api/alunos) a cada pausa na
// digitação e desenha as linhas. Cada linha é um link para a ficha do aluno.
import { MENSAGEM_NAO_AUTORIZADO } from "./api.js";

const campo = document.getElementById("busca-aluno");
const lista = document.getElementById("lista-alunos");
const resumo = document.getElementById("resumo-alunos");

let temporizador = null;
let pedidoAtual = null; // para cancelar a busca anterior se o usuário digitar mais

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

function desenharLinha(aluno) {
  if (!Number.isInteger(aluno.id)) return null; // não monta link com id estranho

  const li = document.createElement("li");
  const link = document.createElement("a");
  link.className = "linha-aluno";
  link.href = "/alunos/" + aluno.id;

  link.append(
    celula("aluno-nome-lista", aluno.nome),
    Number.isInteger(aluno.matricula)
      ? celula("aluno-matricula", String(aluno.matricula))
      : celula("aluno-matricula", "—", true),
    celula("aluno-treino", aluno.ultimo_treino || "Sem treino"),
    aluno.atualizado_em ? celula("aluno-data", aluno.atualizado_em) : celula("aluno-data", "—", true),
    celulaDaSituacao(aluno),
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
  const parametros = new URLSearchParams();
  if (texto) parametros.set("q", texto);

  fetch("/api/alunos?" + parametros.toString(), { signal: pedidoAtual.signal })
    .then((resposta) => {
      if (resposta.status === 401) throw new Error("nao-autorizado");
      if (!resposta.ok) throw new Error("Erro " + resposta.status);
      return resposta.json();
    })
    .then((resultado) => desenhar(resultado, texto !== ""))
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

buscar();
