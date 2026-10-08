// Lista de exercícios: busca por nome + filtro por grupo muscular.
// Pede os resultados ao servidor (/api/exercicios) e desenha a lista.
// Usada na página /exercicios (só consulta) e na tela de montar treino (com o
// botão "Adicionar" em cada exercício).
import { MENSAGEM_NAO_AUTORIZADO } from "./api.js";

// `raiz`: o bloco da página com os elementos marcados [data-busca], [data-grupos],
// [data-resumo] e [data-lista] (veja _biblioteca.html).
// `opcoes.aoAdicionar(exercicio)`: se vier, cada exercício ganha o botão "Adicionar".
export function iniciarBiblioteca(raiz, opcoes = {}) {
  const aoAdicionar = opcoes.aoAdicionar || null;
  const campoBusca = raiz.querySelector("[data-busca]");
  const blocoGrupos = raiz.querySelector("[data-grupos]");
  const resumo = raiz.querySelector("[data-resumo]");
  const lista = raiz.querySelector("[data-lista]");

  let grupoAtual = ""; // "" = todos
  let temporizador = null;
  let pedidoAtual = null; // para cancelar a busca anterior se o usuário digitar mais

  function desenharItem(ex) {
    const li = document.createElement("li");
    li.className = "item";

    const texto = document.createElement("div");
    texto.className = "item-texto";

    const nome = document.createElement("span");
    nome.className = "item-nome";
    // textContent (e não innerHTML): o texto nunca é interpretado como HTML,
    // então um nome com "<script>" apareceria como texto, sem executar nada.
    nome.textContent = ex.nome;
    if (ex.combinado) {
      const selo = document.createElement("span");
      selo.className = "selo";
      selo.textContent = "Combinado";
      nome.appendChild(selo);
    }

    const detalhe = document.createElement("span");
    detalhe.className = "item-detalhe";
    detalhe.textContent = ex.grupos.length ? ex.grupos.join(" · ") : "Sem grupo ainda";

    texto.appendChild(nome);
    texto.appendChild(detalhe);
    li.appendChild(texto);

    if (aoAdicionar) {
      const botao = document.createElement("button");
      botao.type = "button";
      botao.className = "botao-adicionar";
      botao.textContent = "Adicionar";
      botao.setAttribute("aria-label", "Adicionar " + ex.nome);
      botao.addEventListener("click", () => aoAdicionar(ex));
      li.appendChild(botao);
    }
    return li;
  }

  function desenhar(resultado) {
    lista.textContent = ""; // limpa a lista
    resultado.exercicios.forEach((ex) => lista.appendChild(desenharItem(ex)));

    if (resultado.total === 0) {
      resumo.textContent = "";
      const vazio = document.createElement("li");
      vazio.className = "vazio";
      vazio.textContent = "Nenhum exercício encontrado.";
      lista.appendChild(vazio);
    } else if (resultado.total > resultado.exercicios.length) {
      resumo.textContent =
        "Mostrando " + resultado.exercicios.length + " de " + resultado.total +
        ". Digite mais letras para afinar.";
    } else {
      resumo.textContent = resultado.total === 1 ? "1 exercício" : resultado.total + " exercícios";
    }
  }

  function buscar() {
    if (pedidoAtual) pedidoAtual.abort();
    pedidoAtual = new AbortController();

    const parametros = new URLSearchParams();
    if (grupoAtual) parametros.set("grupo", grupoAtual);
    if (campoBusca.value.trim()) parametros.set("q", campoBusca.value.trim());

    fetch("/api/exercicios?" + parametros.toString(), { signal: pedidoAtual.signal })
      .then((resposta) => {
        if (resposta.status === 401) throw new Error("nao-autorizado");
        if (!resposta.ok) throw new Error("Erro " + resposta.status);
        return resposta.json();
      })
      .then(desenhar)
      .catch((erro) => {
        if (erro.name === "AbortError") return; // busca antiga cancelada: normal
        lista.textContent = "";
        resumo.textContent =
          erro.message === "nao-autorizado"
            ? MENSAGEM_NAO_AUTORIZADO
            : "Não consegui carregar os exercícios. Tente de novo.";
      });
  }

  campoBusca.addEventListener("input", () => {
    // Espera 200 ms sem digitar antes de buscar (evita um pedido a cada letra).
    clearTimeout(temporizador);
    temporizador = setTimeout(buscar, 200);
  });

  blocoGrupos.addEventListener("click", (evento) => {
    const botao = evento.target.closest("button[data-grupo]");
    if (!botao) return;
    grupoAtual = botao.getAttribute("data-grupo");
    blocoGrupos.querySelectorAll("button").forEach((b) => {
      b.setAttribute("aria-pressed", b === botao ? "true" : "false");
    });
    // Quando os grupos ficam recolhidos ("Parte do corpo: ..."), a escolha aparece no título
    // e a lista de grupos fecha sozinha.
    const nomeDoGrupo = raiz.querySelector("[data-grupo-atual]");
    if (nomeDoGrupo) nomeDoGrupo.textContent = grupoAtual === "" ? "Todas" : botao.textContent;
    const filtro = raiz.querySelector("[data-filtro-grupos]");
    if (filtro) {
      filtro.open = false;
      filtro.querySelector("summary").focus();
    }
    buscar();
  });

  buscar();
}
