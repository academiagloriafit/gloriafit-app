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

function partesDaDose(exercicio) {
  return [exercicio.dose, exercicio.carga].filter((parte) => parte && String(parte).trim());
}

// O exercício tem séries × repetições e/ou carga? Se tem, essa é a PRIMEIRA linha de `linhasDoExercicio`
// (a tela a desenha em letra grande); sem isso (um cardio só com observação), a primeira linha é outra coisa.
export function temDose(exercicio) {
  return partesDaDose(exercicio).length > 0;
}

// "4 × 12 · 20 kg · Intervalo: 1 min 30 s" (só o que existe) -> lista de linhas curtas do exercício.
export function linhasDoExercicio(exercicio) {
  const linhas = [];
  const dose = partesDaDose(exercicio);
  if (dose.length) linhas.push(dose.join(" · "));
  if (exercicio.intervalo) linhas.push(`Intervalo: ${exercicio.intervalo}`);
  if (exercicio.observacao) linhas.push(`Obs.: ${exercicio.observacao}`);
  return linhas;
}

// Qual ficha mostrar: a pedida, se existir; senão a primeira. Número fora da lista não quebra nada.
export function fichaEscolhida(fichas, indice) {
  return Number.isInteger(indice) && indice >= 0 && indice < fichas.length ? indice : 0;
}

// ------------------------------------------------------------------ "Treino concluído"

// "Você fez esta ficha 3 de 15 vezes" (com meta) / "Você fez esta ficha 1 vez" / "Você ainda não fez esta ficha".
export function textoDoAndamento(ficha, meta) {
  const feitas = Number.isInteger(ficha?.feitas) && ficha.feitas > 0 ? ficha.feitas : 0;
  if (Number.isInteger(meta) && meta > 0) return `Você fez esta ficha ${feitas} de ${meta} vezes`;
  if (feitas === 0) return "Você ainda não fez esta ficha";
  return feitas === 1 ? "Você fez esta ficha 1 vez" : `Você fez esta ficha ${feitas} vezes`;
}

// Resposta do servidor ao marcar ou desfazer ({ status, corpo }) -> o que a tela faz:
//   { tipo: "entrar" }                        sessão perdida
//   { tipo: "ok", feitas, jaMarcada }         deu certo (`jaMarcada`: já estava marcada hoje; só no "feito")
//   { tipo: "erro", mensagem }                qualquer outra coisa (com a explicação do servidor, se ela veio)
export function descreverMarcacao(status, corpo) {
  if (status === 401) return { tipo: "entrar" };
  if (status === 200 && corpo && corpo.ok === true && Number.isInteger(corpo.feitas)) {
    return { tipo: "ok", feitas: corpo.feitas, jaMarcada: corpo.ja_marcada === true };
  }
  if (corpo && typeof corpo.erro === "string" && corpo.erro) return { tipo: "erro", mensagem: corpo.erro };
  return { tipo: "erro", mensagem: `Não consegui salvar (código ${status}). Tente de novo em instantes.` };
}

export const TEXTO_FICHA_FEITA_HOJE = "Anotado. Parabéns!";
export const TEXTO_JA_MARCADA = "Você já tinha marcado esta ficha hoje.";

// ------------------------------------------------------------------ comentários do aluno

export const LIMITE_DO_COMENTARIO = 500; // o servidor aceita até isto (LIMITE_DO_TEXTO em app/comentarios.py)
export const TEXTO_COMENTARIO_VAZIO = "Escreva o seu comentário.";
export const TEXTO_COMENTARIO_ENVIADO = "Comentário enviado. O professor vai ler.";
export const TEXTO_COMENTARIO_REPETIDO = "Este comentário já tinha sido enviado.";

// A frase cinza dentro da caixa (some quando o aluno começa a escrever): diz para que serve o comentário e dá exemplos
// do que contar, porque o aluno não sabe de antemão o que o professor quer ler.
// Curtas de propósito: a caixa do exercício é estreita no celular e só cabem umas 3 linhas.
export const DICA_DO_COMENTARIO_DO_EXERCICIO = "Conte ao professor o que achou: leve, pesado, dor ou dúvida.";
export const DICA_DO_COMENTARIO_DO_TREINO = "Conte ao professor o que achou do treino: fácil, difícil, alguma dúvida.";

export function dicaDoComentario(deExercicio) {
  return deExercicio ? DICA_DO_COMENTARIO_DO_EXERCICIO : DICA_DO_COMENTARIO_DO_TREINO;
}

// Conta letras como o servidor (Python): um emoji vale 1, não 2 como no `.length` do JavaScript.
function contarLetras(texto) {
  return [...texto].length;
}

// "37 de 500", embaixo da caixa de comentário.
export function textoDoContador(texto) {
  return `${contarLetras(typeof texto === "string" ? texto : "")} de ${LIMITE_DO_COMENTARIO}`;
}

// O texto passou do limite? (a caixa não trava a digitação: o contador fica vermelho e o envio explica o motivo)
export function estourouOLimite(texto) {
  return contarLetras(typeof texto === "string" ? texto : "") > LIMITE_DO_COMENTARIO;
}

// O texto está pronto para enviar? { ok: true, texto } (sem as bordas em branco) ou { ok: false, mensagem }.
export function comentarioPronto(texto) {
  const limpo = typeof texto === "string" ? texto.trim() : "";
  if (!limpo) return { ok: false, mensagem: TEXTO_COMENTARIO_VAZIO };
  if (contarLetras(limpo) > LIMITE_DO_COMENTARIO) {
    return { ok: false, mensagem: `O comentário pode ter até ${LIMITE_DO_COMENTARIO} letras.` };
  }
  return { ok: true, texto: limpo };
}

// O corpo do pedido. Sem `ficha`/`exercicio` é o comentário do treino inteiro. O nome do treino e o do exercício
// vão junto de propósito: se o professor mudou o treino enquanto o aluno escrevia, o servidor percebe e não deixa o
// comentário cair no lugar errado (responde 409).
export function pedidoDoComentario(treino, texto, ficha = null, exercicio = null) {
  const pedido = { treino: treino.nome, texto };
  if (ficha && exercicio) {
    pedido.ficha = ficha.ordem;
    pedido.item = exercicio.ordem;
    pedido.exercicio = exercicio.exercicio;
  }
  return pedido;
}

// Cada caixa de comentário guarda o rascunho com esta chave: "treino" ou "ficha:exercício" (ex.: "2:3").
export function chaveDoRascunho(ficha = null, exercicio = null) {
  return ficha && exercicio ? `${ficha.ordem}:${exercicio.ordem}` : "treino";
}

// Resposta do servidor ao enviar ({ status, corpo }) -> o que a tela faz:
//   { tipo: "entrar" }                  sessão perdida
//   { tipo: "ok", repetido }            enviado (`repetido`: o mesmo texto acabou de ser enviado; não gravou duas vezes)
//   { tipo: "atualizar", mensagem }     o treino mudou (409): o aluno precisa atualizar a página
//   { tipo: "erro", mensagem }          qualquer outra coisa, com a explicação do servidor se ela veio
export function descreverComentario(status, corpo) {
  if (status === 401) return { tipo: "entrar" };
  if (status === 200 && corpo && corpo.ok === true) return { tipo: "ok", repetido: corpo.repetido === true };
  const mensagem =
    corpo && typeof corpo.erro === "string" && corpo.erro
      ? corpo.erro
      : `Não consegui enviar (código ${status}). Tente de novo em instantes.`;
  return { tipo: status === 409 ? "atualizar" : "erro", mensagem };
}

// ------------------------------------------------------------------ "Seus comentários" e as respostas do professor

export const TEXTO_SEM_RESPOSTA = "Ainda sem resposta do professor.";

// Resposta de GET /api/aluno/comentarios ({ status, corpo }) -> o que a tela faz:
//   { tipo: "entrar" }                                          sessão perdida
//   { tipo: "ok", total, respostasNovas, comentarios }          mostrar a lista
//   { tipo: "erro" }                                            qualquer outra coisa (a lista é um extra: a tela segue sem ela)
export function descreverMeusComentarios(status, corpo) {
  if (status === 401) return { tipo: "entrar" };
  if (status === 200 && corpo && Array.isArray(corpo.comentarios) && Number.isInteger(corpo.total)) {
    return {
      tipo: "ok",
      total: corpo.total,
      respostasNovas: Number.isInteger(corpo.respostas_novas) ? corpo.respostas_novas : 0,
      comentarios: corpo.comentarios,
    };
  }
  return { tipo: "erro" };
}

// "Você tem 1 resposta nova do professor." / "Você tem 3 respostas novas do professor."
export function textoDoAvisoDeResposta(quantas) {
  return quantas === 1 ? "Você tem 1 resposta nova do professor." : `Você tem ${quantas} respostas novas do professor.`;
}

// O botão que abre e fecha a lista: "Ver seus comentários (3)", com as respostas novas quando há.
export function textoDoBotaoMeusComentarios(total, respostasNovas, aberta) {
  const base = `${aberta ? "Esconder" : "Ver"} seus comentários (${total})`;
  if (!aberta && respostasNovas > 0) return `${base} · ${respostasNovas === 1 ? "1 resposta nova" : `${respostasNovas} respostas novas`}`;
  return base;
}

// Embaixo da lista, quando ela é mais curta que o total (o servidor manda só os mais novos): "Mostrando só os 30 comentários mais novos."
export function textoDaNotaDaLista(total, mostrados) {
  return mostrados < total ? `Mostrando só os ${mostrados} comentários mais novos.` : "";
}

// "A PEITO · SUPINO RETO" ou, no comentário do treino inteiro, "Treino inteiro".
export function textoDoLugar(comentario) {
  return comentario.exercicio ? `${comentario.ficha} · ${comentario.exercicio}` : "Treino inteiro";
}

// Os ids das respostas que o aluno ainda não tinha visto (os que se mandam ao servidor ao abrir a lista).
export function idsDasRespostasNovas(comentarios) {
  return comentarios.filter((c) => c.resposta && c.resposta.nova === true).map((c) => c.id);
}

// Resposta do servidor ao marcar como vistas ({ status, corpo }) -> { tipo: "entrar" } | { tipo: "ok", respostasNovas } | { tipo: "erro" }.
export function descreverVistos(status, corpo) {
  if (status === 401) return { tipo: "entrar" };
  if (status === 200 && corpo && corpo.ok === true && Number.isInteger(corpo.respostas_novas)) {
    return { tipo: "ok", respostasNovas: corpo.respostas_novas };
  }
  return { tipo: "erro" };
}
