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

// O aluno VOLTOU para o app (ele fica aberto em segundo plano por horas ou dias) e o treino foi buscado de novo.
// O que a tela faz com a resposta?
//   `naTela`      o treino que está desenhado agora (null se a tela mostra um aviso, como "sem treino")
//   `escrevendo`  há uma caixa de comentário aberta ou um envio no ar: o aluno não pode perder o que está fazendo,
//                 então nada muda (se o treino mudou, o servidor recusa o comentário e a caixa oferece "Atualizar a página")
// Devolve:
//   { acao: "nada" }                  deixa a tela como está (nada mudou, sem rede, erro do servidor ou aluno escrevendo)
//   { acao: "entrar" }                a sessão acabou: ir para a tela de entrar
//   { acao: "mostrar", treino }       desenhar o treino novo
//   { acao: "aviso", texto }          o aluno ficou sem treino (ou sem exercícios): mostrar o aviso
// Erro e falta de rede NUNCA apagam o treino da tela: o aluno pode estar na academia com a internet ruim.
export function decidirAtualizacaoDoTreino(naTela, status, corpo, escrevendo) {
  const novo = descreverTreino(status, corpo);
  if (novo.tipo === "erro" || escrevendo) return { acao: "nada" };
  if (novo.tipo === "entrar") return { acao: "entrar" };
  if (novo.tipo === "sem-treino") return { acao: "aviso", texto: TEXTO_SEM_TREINO };
  if (novo.tipo === "sem-exercicios") return { acao: "aviso", texto: TEXTO_SEM_EXERCICIOS };
  // Os dois vêm do mesmo servidor, com as chaves na mesma ordem: comparar o JSON basta (e pega até "treino concluído hoje" mudando).
  if (naTela && JSON.stringify(naTela) === JSON.stringify(novo.treino)) return { acao: "nada" };
  return { acao: "mostrar", treino: novo.treino };
}

// "Início 06/10/2026 · Fim 06/11/2026" (só o que existe; sem nenhuma das duas datas, vazio).
// "Esta semana: 2 treinos" (dias com treino registrado, de segunda a domingo). Sem treino na semana, nada (tela limpa).
export function textoDaSemana(treino) {
  const n = treino?.treinos_na_semana;
  if (!Number.isInteger(n) || n < 1) return "";
  return `Esta semana: ${n} ${n === 1 ? "treino" : "treinos"}`;
}

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

// ------------------------------------------------------------------ lista de fichas ("Treino de hoje")

// Ao entrar, o aluno vê um botão por ficha (e não os exercícios): a ficha do dia vem circulada. Quem escolhe qual é a ficha
// do dia é o servidor (`treino.ficha_do_dia`, a `ordem` da ficha; ver app/aluno_treino.py); aqui só se desenha.
export const TEXTO_TREINO_DE_HOJE = "Treino de hoje";
export const TEXTO_CONCLUIDO_HOJE = "✓ Concluído hoje";
export const TEXTO_ESCOLHA_O_TREINO = "Toque no treino que você vai fazer.";

// Quantos exercícios a ficha tem (um bi-set de dois conta 2).
export function quantosExercicios(ficha) {
  const grupos = Array.isArray(ficha?.grupos) ? ficha.grupos : [];
  return grupos.reduce((soma, grupo) => soma + (Array.isArray(grupo?.exercicios) ? grupo.exercicios.length : 0), 0);
}

// "1 exercício" / "8 exercícios".
export function textoDosExercicios(ficha) {
  const n = quantosExercicios(ficha);
  return n === 1 ? "1 exercício" : `${n} exercícios`;
}

// Esta ficha é a do dia? (sem `ficha_do_dia` no treino, nenhuma é)
export function ehFichaDoDia(treino, ficha) {
  return Number.isInteger(treino?.ficha_do_dia) && treino.ficha_do_dia === ficha?.ordem;
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
//   { tipo: "ok", feitas, jaMarcada, fichaDoDia? }  deu certo (`jaMarcada`: já estava marcada hoje; só no "feito")
//   { tipo: "erro", mensagem }                qualquer outra coisa (com a explicação do servidor, se ela veio)
export function descreverMarcacao(status, corpo) {
  if (status === 401) return { tipo: "entrar" };
  if (status === 200 && corpo && corpo.ok === true && Number.isInteger(corpo.feitas)) {
    // `fichaDoDia`: qual ficha fica circulada agora (o servidor decide; só vem se for um número)
    const resposta = { tipo: "ok", feitas: corpo.feitas, jaMarcada: corpo.ja_marcada === true };
    if (Number.isInteger(corpo.ficha_do_dia)) resposta.fichaDoDia = corpo.ficha_do_dia;
    return resposta;
  }
  if (corpo && typeof corpo.erro === "string" && corpo.erro) return { tipo: "erro", mensagem: corpo.erro };
  return { tipo: "erro", mensagem: `Não consegui salvar (código ${status}). Tente de novo em instantes.` };
}

export const TEXTO_FICHA_FEITA_HOJE = "Anotado. Parabéns!";
export const TEXTO_JA_MARCADA = "Você já tinha marcado esta ficha hoje.";

// ------------------------------------------------------------------ durante o treino: exercício feito, carga e descanso
// Pedido do Thiago (22/10/2026). Tudo vale por DIA (amanhã o treino volta limpo): quem guarda é o servidor (app/execucao.py).

// Os exercícios da ficha numa lista só (um bi-set de dois conta 2).
export function exerciciosDaFicha(ficha) {
  const grupos = Array.isArray(ficha?.grupos) ? ficha.grupos : [];
  return grupos.flatMap((grupo) => (Array.isArray(grupo?.exercicios) ? grupo.exercicios : []));
}

// "3 de 8 feitos" no botão da ficha, enquanto o aluno está no meio do treino. Vazio se ele não marcou nenhum ou se
// a ficha já está concluída hoje (aí aparece "Concluído hoje").
export function textoDoProgresso(ficha) {
  if (ficha?.feita_hoje) return "";
  const todos = exerciciosDaFicha(ficha);
  const feitos = todos.filter((e) => e.feito === true).length;
  return feitos > 0 ? `${feitos} de ${todos.length} feitos` : "";
}

// ---- a tela de cada exercício (pedido do Thiago, 22/10/2026): a ficha é uma lista; tocar num exercício abre a tela dele.
// "Posição" abaixo é o lugar do exercício na lista da ficha (0, 1, 2...), contando os bi-sets na ordem em que aparecem.

// "Exercício 3 de 8".
export function textoDaPosicao(posicao, total) {
  return `Exercício ${posicao + 1} de ${total}`;
}

// O exercício a abrir depois de marcar `atual` como feito: o primeiro AINDA NÃO FEITO depois dele; se não sobrou nenhum adiante,
// o primeiro que ficou para trás (o aluno pulou um aparelho ocupado). -1 se todos estão feitos.
export function proximoSemFazer(exercicios, atual) {
  const n = exercicios.length;
  for (let passo = 1; passo < n; passo += 1) {
    const posicao = (atual + passo) % n;
    if (exercicios[posicao]?.feito !== true) return posicao;
  }
  return -1;
}

// O botão "Próximo exercício": o da posição seguinte, feito ou não. -1 se este é o último (o botão não aparece).
export function proximoDaLista(exercicios, atual) {
  return atual + 1 < exercicios.length ? atual + 1 : -1;
}

// O treino foi buscado de novo (o professor pode ter mexido): a posição `posicao` ainda é o exercício `nome` desta ficha?
// Devolve a posição se sim; senão -1 e a tela volta para a lista, em vez de mostrar outro exercício no lugar.
export function posicaoSeContinuaIgual(ficha, posicao, nome) {
  return exerciciosDaFicha(ficha)[posicao]?.exercicio === nome ? posicao : -1;
}

// O bi-set/tri-set a que o exercício da posição pertence (null se ele está sozinho).
export function grupoDoExercicio(ficha, posicao) {
  const grupos = Array.isArray(ficha?.grupos) ? ficha.grupos : [];
  let passou = 0;
  for (const grupo of grupos) {
    const quantos = Array.isArray(grupo?.exercicios) ? grupo.exercicios.length : 0;
    if (posicao < passou + quantos) return grupo?.nome ? grupo : null;
    passou += quantos;
  }
  return null;
}

// Uma frase para o aluno saber o que aconteceu quando o app o leva sozinho ao próximo exercício.
export function textoDoExercicioFeito(nome) {
  return `✓ ${nome} feito.`;
}

// Quando o último exercício que faltava é marcado, o app volta para a lista com esta frase.
export function textoDeTodosFeitos(ficha) {
  return ficha?.feita_hoje ? "Todos os exercícios feitos!" : "Todos os exercícios feitos! Falta só tocar em “Treino concluído”.";
}

export const TEXTO_MARCAR_FEITO = "Marcar como feito";
export const TEXTO_FEITO = "✓ Feito";
export const MENSAGEM_FEITO_NAO_SALVOU = "Não consegui marcar. Tente de novo.";

// O que o botão de feito diz e anuncia, para o estado atual.
export function textoDoFeito(feito) {
  return feito === true ? TEXTO_FEITO : TEXTO_MARCAR_FEITO;
}

const NUMERO_DA_CARGA = /^[0-9]{1,3}(?:[.,][0-9]{1,2})?$/;
export const MENSAGEM_CARGA_NAO_E_NUMERO = "Digite só o número, em kg. Exemplo: 12,5";
export const MENSAGEM_CARGA_ZERO = "A carga precisa ser maior que zero. Se não usou peso, deixe em branco.";

// A carga digitada pelo aluno -> { ok: true, valor } (valor "12,5" como o servidor guarda; null = campo vazio, apaga)
// ou { ok: false, mensagem }. As mesmas regras de app/execucao.py (carga_limpa): até 3 algarismos, até 2 casas, ponto ou vírgula.
export function conferirCarga(texto) {
  const limpo = typeof texto === "string" ? texto.trim() : "";
  if (!limpo) return { ok: true, valor: null };
  if (!NUMERO_DA_CARGA.test(limpo)) return { ok: false, mensagem: MENSAGEM_CARGA_NAO_E_NUMERO };
  const [inteiro, decimais = ""] = limpo.replace(",", ".").split(".");
  const parteInteira = String(parseInt(inteiro, 10));
  const parteDecimal = decimais.replace(/0+$/, "");
  if (parteInteira === "0" && !parteDecimal) return { ok: false, mensagem: MENSAGEM_CARGA_ZERO };
  return { ok: true, valor: parteDecimal ? `${parteInteira},${parteDecimal}` : parteInteira };
}

// Uma linha só (pedido do Thiago, 26/10/2026: pouca informação na tela):
// com duas ou mais cargas em dias diferentes, "Últimas: 20 → 22,5 → 25 kg" (da mais antiga para a mais nova);
// com uma, "Última vez: 30 kg · 20/10"; sem nenhuma, vazio.
export function textoDaUltimaCarga(exercicio) {
  if (!exercicio?.ultima_carga) return "";
  const recentes = Array.isArray(exercicio.cargas_recentes)
    ? exercicio.cargas_recentes.filter((c) => typeof c === "string" && c.trim() !== "")
    : [];
  if (recentes.length >= 2) return `Últimas: ${recentes.join(" → ")} kg`;
  const dia = typeof exercicio.ultima_data === "string" ? exercicio.ultima_data.slice(0, 5) : "";
  return dia ? `Última vez: ${exercicio.ultima_carga} kg · ${dia}` : `Última vez: ${exercicio.ultima_carga} kg`;
}

// O corpo do pedido de POST /api/aluno/exercicio. O nome do exercício vai junto de propósito (como no comentário): se o professor
// mudou o treino enquanto o aluno treinava, o servidor percebe e não grava no exercício errado (responde 409).
// `campos`: { feito: true | false } e/ou { carga: "12,5" | null }.
export function pedidoDoExercicio(ficha, exercicio, campos) {
  return { ficha: ficha.ordem, item: exercicio.ordem, exercicio: exercicio.exercicio, ...campos };
}

// Resposta do servidor ({ status, corpo }) -> o que a tela faz:
//   { tipo: "entrar" }                      sessão perdida
//   { tipo: "ok", feito, cargaHoje }        gravou (`cargaHoje`: "" = nenhuma)
//   { tipo: "atualizar", mensagem }         o treino mudou (409): o aluno precisa atualizar a página
//   { tipo: "erro", mensagem }              qualquer outra coisa, com a explicação do servidor se ela veio
export function descreverExercicio(status, corpo) {
  if (status === 401) return { tipo: "entrar" };
  if (status === 200 && corpo && corpo.ok === true && typeof corpo.feito === "boolean" && typeof corpo.carga_hoje === "string") {
    return { tipo: "ok", feito: corpo.feito, cargaHoje: corpo.carga_hoje };
  }
  const mensagem =
    corpo && typeof corpo.erro === "string" && corpo.erro ? corpo.erro : `Não consegui salvar (código ${status}). Tente de novo em instantes.`;
  return { tipo: status === 409 ? "atualizar" : "erro", mensagem };
}

// ---- descanso (cronômetro). Pedido do Thiago (22/10/2026): o campo do tempo fica EM BRANCO e o aluno digita os segundos que
// quer descansar. Só vem preenchido quando o professor lançou o intervalo do exercício (o aluno pode trocar). Nada de tempo
// "padrão" inventado. Na barra de contagem, "+15 s" soma tempo quando o tempo digitado não basta.

export const SEGUNDOS_A_MAIS_NO_DESCANSO = 15;
export const MAXIMO_DO_DESCANSO = 3600; // uma hora: mais que isso, quase certo que foi engano de digitação
export const MENSAGEM_DESCANSO_VAZIO = "Digite quantos segundos você quer descansar.";
export const MENSAGEM_DESCANSO_INVALIDO = `Digite só o número de segundos, de 1 a ${MAXIMO_DO_DESCANSO}.`;

// O professor informou o intervalo deste exercício?
export function temDescanso(exercicio) {
  return Number.isInteger(exercicio?.pausa_segundos) && exercicio.pausa_segundos > 0;
}

// O que o campo do tempo mostra ao abrir o exercício: os segundos do professor ou, sem eles, nada ("" = em branco).
export function descansoSugerido(exercicio) {
  return temDescanso(exercicio) ? String(exercicio.pausa_segundos) : "";
}

// O tempo digitado pelo aluno -> { ok: true, segundos } ou { ok: false, mensagem }. Só segundos inteiros, de 1 a 3600.
export function conferirDescanso(texto) {
  const limpo = typeof texto === "string" ? texto.trim() : "";
  if (!limpo) return { ok: false, mensagem: MENSAGEM_DESCANSO_VAZIO };
  if (!/^[0-9]{1,4}$/.test(limpo)) return { ok: false, mensagem: MENSAGEM_DESCANSO_INVALIDO };
  const segundos = parseInt(limpo, 10);
  if (segundos < 1 || segundos > MAXIMO_DO_DESCANSO) return { ok: false, mensagem: MENSAGEM_DESCANSO_INVALIDO };
  return { ok: true, segundos };
}

// 90 -> "1:30"; 5 -> "0:05"; 3600 -> "1:00:00".
export function textoDoTempo(segundos) {
  const total = Math.max(0, Math.floor(Number(segundos) || 0));
  const horas = Math.floor(total / 3600);
  const minutos = Math.floor((total % 3600) / 60);
  const resto = String(total % 60).padStart(2, "0");
  return horas > 0 ? `${horas}:${String(minutos).padStart(2, "0")}:${resto}` : `${minutos}:${resto}`;
}

// Quantos segundos faltam (arredonda para cima: "0:01" até o último instante). Conta pelo relógio, não por tique:
// com o celular em segundo plano os tiques param, mas a hora que o descanso acaba continua valendo.
export function segundosRestantes(fimEmMs, agoraEmMs) {
  return Math.max(0, Math.ceil((fimEmMs - agoraEmMs) / 1000));
}

export const TEXTO_DESCANSO_ACABOU = "Acabou o descanso. Próxima série!";

// ---- nota de esforço, depois de "Treino concluído" (opcional)
export const ESFORCOS = [
  { valor: 1, texto: "Leve" },
  { valor: 2, texto: "Ideal" },
  { valor: 3, texto: "Pesado" },
];
export const TEXTO_PERGUNTA_DO_ESFORCO = "Como foi o treino?";
export const TEXTO_ESFORCO_OPCIONAL = "Opcional. Toque de novo para tirar.";

// Tocar na nota que já está escolhida tira a escolha (null); tocar em outra troca.
export function proximoEsforco(atual, escolhido) {
  return atual === escolhido ? null : escolhido;
}

export function pedidoDoEsforco(ficha, esforco) {
  return { ficha: ficha.ordem, esforco };
}

// Resposta do servidor ({ status, corpo }) -> { tipo: "entrar" } | { tipo: "ok", esforco (1, 2, 3 ou null) } | { tipo: "erro", mensagem }.
export function descreverEsforco(status, corpo) {
  if (status === 401) return { tipo: "entrar" };
  if (status === 200 && corpo && corpo.ok === true && (corpo.esforco === null || [1, 2, 3].includes(corpo.esforco))) {
    return { tipo: "ok", esforco: corpo.esforco };
  }
  if (corpo && typeof corpo.erro === "string" && corpo.erro) return { tipo: "erro", mensagem: corpo.erro };
  return { tipo: "erro", mensagem: `Não consegui salvar (código ${status}). Tente de novo em instantes.` };
}

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
