// Telas do aluno (/aluno/entrar): o que mostrar para cada resposta do servidor e as conferências rápidas antes de enviar.
// Fica separado de aluno_entrar.js (que mexe na página) para poder ser testado sozinho. Quem decide de verdade é o servidor:
// estas conferências só poupam uma ida e volta.

export const TAMANHO_DO_CODIGO = 6;
export const MINIMO_DA_SENHA = 8;

export const MENSAGEM_SEM_REDE =
  "Não consegui falar com o servidor (sem resposta ou sem internet). Confira a internet e tente de novo.";

// Só os algarismos comuns do texto, até `maximo` deles.
export function soNumeros(texto, maximo = Infinity) {
  return String(texto ?? "")
    .replace(/[^0-9]/g, "")
    .slice(0, maximo);
}

// '12345678909' -> '123.456.789-09' (aos poucos, enquanto a pessoa digita).
export function formatarCpf(texto) {
  const d = soNumeros(texto, 11);
  if (d.length <= 3) return d;
  if (d.length <= 6) return `${d.slice(0, 3)}.${d.slice(3)}`;
  if (d.length <= 9) return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6)}`;
  return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
}

// "" se o CPF tem 11 números; senão a frase para a tela. (Os dígitos verificadores quem confere é o servidor.)
export function conferirCpf(texto) {
  const n = soNumeros(texto).length;
  return n === 11 ? "" : "Digite o CPF com os 11 números.";
}

// "" se o código tem 6 números; senão a frase para a tela.
export function conferirCodigo(texto) {
  return soNumeros(texto).length === TAMANHO_DO_CODIGO ? "" : "Digite os 6 números do código que chegou no WhatsApp.";
}

// "" se a senha nova e a repetição servem; senão a frase para a tela.
export function conferirSenhaNova(senha, repetida) {
  if (typeof senha !== "string" || senha.length < MINIMO_DA_SENHA) {
    return `A senha precisa ter pelo menos ${MINIMO_DA_SENHA} letras ou números.`;
  }
  if (senha !== repetida) return "As duas senhas não são iguais.";
  return "";
}

// Resposta do servidor ({ status, corpo }) -> { ok, mensagem }. 400, 401, 429 e 503 trazem a explicação pronta em `erro`.
export function descreverResposta(status, corpo) {
  if (status === 200 && corpo && corpo.ok === true) return { ok: true, mensagem: "" };
  if (corpo && typeof corpo.erro === "string" && corpo.erro) return { ok: false, mensagem: corpo.erro };
  return { ok: false, mensagem: `O servidor devolveu um erro (código ${status}). Tente de novo em instantes.` };
}

// Texto do botão de reenviar: com a contagem enquanto não pode, e sem ela quando pode.
export function textoDoReenvio(segundosRestantes) {
  const s = Math.ceil(Number(segundosRestantes));
  return s > 0 ? `Enviar o código de novo (em ${s} s)` : "Enviar o código de novo";
}

// ------------------------------------------------------------------ tela "Meu treino" (/aluno)

// Resposta de GET /api/aluno/treino ({ status, corpo }) -> o que a tela faz:
//   { tipo: "entrar" }               sessão perdida: ir para a tela de entrar
//   { tipo: "sem-treino" }           o aluno não tem treino ativo
//   { tipo: "sem-exercicios" }       tem treino ativo, mas nenhuma ficha com exercício
//   { tipo: "treino", treino }       mostrar o treino
//   { tipo: "erro", mensagem }       qualquer outra coisa
export function descreverTreino(status, corpo) {
  if (status === 401) return { tipo: "entrar" };
  if (status === 200 && corpo && "treino" in corpo) {
    const treino = corpo.treino;
    if (treino === null) return { tipo: "sem-treino" };
    if (treino && typeof treino === "object" && Array.isArray(treino.fichas)) {
      return treino.fichas.length ? { tipo: "treino", treino } : { tipo: "sem-exercicios" };
    }
  }
  return { tipo: "erro", mensagem: `Não consegui buscar o seu treino (código ${status}). Tente de novo em instantes.` };
}

export const TEXTO_SEM_TREINO = "Você ainda não tem um treino ativo. Fale com o seu professor na academia.";
export const TEXTO_SEM_EXERCICIOS = "O seu treino ainda não tem exercícios. Fale com o seu professor na academia.";

// "Início 06/10/2026 · Fim 06/11/2026" (só o que existe; sem nenhuma das duas datas, vazio).
export function textoDasDatas(treino) {
  const partes = [];
  if (treino.inicio) partes.push(`Início ${treino.inicio}`);
  if (treino.fim) partes.push(`Fim ${treino.fim}`);
  return partes.join(" · ");
}

// "4 × 12 · 20 kg · Intervalo: 1 min 30 s" (só o que existe) -> lista de linhas curtas do exercício.
export function linhasDoExercicio(exercicio) {
  const linhas = [];
  const dose = [exercicio.dose, exercicio.carga].filter((parte) => parte && String(parte).trim());
  if (dose.length) linhas.push(dose.join(" · "));
  if (exercicio.intervalo) linhas.push(`Intervalo: ${exercicio.intervalo}`);
  if (exercicio.observacao) linhas.push(`Obs.: ${exercicio.observacao}`);
  return linhas;
}

// Qual ficha mostrar: a pedida, se existir; senão a primeira. Número fora da lista não quebra nada.
export function fichaEscolhida(fichas, indice) {
  return Number.isInteger(indice) && indice >= 0 && indice < fichas.length ? indice : 0;
}
