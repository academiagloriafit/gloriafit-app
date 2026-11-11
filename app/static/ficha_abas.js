// Abas da ficha do aluno (visual novo, 11/11/2026): Visão geral, Treinos, Comentários e Fila.
// Um link para um quadro de outra aba (ex.: "Ver comentários" -> #comentarios-do-aluno) abre a aba certa antes de rolar até ele.
const abas = [...document.querySelectorAll('.ficha-abas [role="tab"]')];

function abrirAba(aba, focar = false) {
  for (const outra of abas) {
    const escolhida = outra === aba;
    outra.setAttribute("aria-selected", String(escolhida));
    outra.tabIndex = escolhida ? 0 : -1;
    document.getElementById(outra.getAttribute("aria-controls")).hidden = !escolhida;
  }
  if (focar) aba.focus();
}

// Abre a aba que contém o elemento de id `alvo` (se ele estiver numa aba) e rola até ele.
function irPara(alvo) {
  const elemento = alvo ? document.getElementById(alvo) : null;
  const painel = elemento?.closest('[role="tabpanel"]');
  if (!painel) return false;
  const aba = abas.find((a) => a.getAttribute("aria-controls") === painel.id);
  if (aba) abrirAba(aba);
  elemento.scrollIntoView({ block: "start" });
  return true;
}

abas.forEach((aba, i) => {
  aba.addEventListener("click", () => abrirAba(aba));
  // teclado: setas esquerda/direita andam entre as abas (padrão de abas acessíveis)
  aba.addEventListener("keydown", (evento) => {
    if (evento.key !== "ArrowRight" && evento.key !== "ArrowLeft") return;
    evento.preventDefault();
    const proxima = abas[(i + (evento.key === "ArrowRight" ? 1 : abas.length - 1)) % abas.length];
    abrirAba(proxima, true);
  });
});

document.addEventListener("click", (evento) => {
  const link = evento.target.closest('a[href^="#"]');
  if (link && irPara(decodeURIComponent(link.getAttribute("href").slice(1)))) evento.preventDefault();
});
if (location.hash) irPara(decodeURIComponent(location.hash.slice(1)));

// O círculo das sessões: a fração vai pelo CSSOM (a política de segurança da página não deixa estilo escrito no HTML).
for (const anel of document.querySelectorAll(".ficha-anel[data-progresso]")) {
  const valor = Number(anel.dataset.progresso);
  anel.style.setProperty("--progresso", String(Number.isFinite(valor) ? Math.max(0, Math.min(100, valor)) / 100 : 0));
}
