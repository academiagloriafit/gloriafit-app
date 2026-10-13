// Filas numeradas de treino (Homem, Mulher, Adolescente, Gestante, Grupos de risco): a lógica das telas, sem nada de tela
// (testada à parte). Quem decide de verdade é o servidor (app/filas.py); aqui só ajudamos o professor a preencher certo
// antes de enviar e montamos os pedidos.
import { MAXIMO_NUMERO_NA_FILA, lerDia, limparEspacos, problemaDoNomeDoProfessor } from "./treino_modelo.js";

// "1,2,4" (o que a página traz em data-usados) -> [1, 2, 4]. Só vale 1 a 6; o resto é ignorado.
export function lerUsados(texto) {
  const numeros = new Set();
  for (const parte of String(texto ?? "").split(",")) {
    const limpo = parte.trim();
    if (/^[0-9]{1,3}$/.test(limpo)) {
      const n = Number(limpo);
      if (n >= 1 && n <= MAXIMO_NUMERO_NA_FILA) numeros.add(n);
    }
  }
  return [...numeros].sort((a, b) => a - b);
}

// O número que o app sugere para o próximo treino da fila: o seguinte ao maior que já existe (fila vazia = 1).
// Se a fila já chegou ao 6, o primeiro buraco; null se não sobra número.
export function proximoNumeroLivre(usados) {
  const jaUsados = new Set(usados);
  const maior = usados.length ? Math.max(...usados) : 0;
  if (maior < MAXIMO_NUMERO_NA_FILA) return maior + 1;
  for (let n = 1; n <= MAXIMO_NUMERO_NA_FILA; n++) if (!jaUsados.has(n)) return n;
  return null;
}

// Texto "Já existem na fila: Treino 1, Treino 2" (ou que a fila está vazia).
export function descreverUsados(usados) {
  return usados.length ? `Já existem nesta fila: ${usados.map((n) => `Treino ${n}`).join(", ")}.` : "Esta fila ainda não tem nenhum treino.";
}

// Confere o que o professor preencheu para colocar o aluno numa fila. Cada problema: { campo, mensagem }, com `campo`
// igual ao id do campo na ficha. `hoje` é 'AAAA-MM-DD' (o dia que o servidor deu à página). Gestante e Grupos de risco
// (`exigeLiberacao`) pedem a confirmação de que o professor conferiu a liberação e a data dela.
export function validarColocarNaFila({ filaId, professor, exigeLiberacao = false, conferida = false, liberacaoEm = "", hoje = "" }) {
  const problemas = [];
  if (!/^[1-9][0-9]{0,9}$/.test(limparEspacos(filaId ?? ""))) problemas.push({ campo: "fila-escolhida", mensagem: "Escolha a fila." });
  const doProfessor = problemaDoNomeDoProfessor(professor, "Digite o seu nome (professor que está colocando o aluno na fila).");
  if (doProfessor) problemas.push({ campo: "fila-professor", mensagem: doProfessor });
  if (exigeLiberacao) {
    if (conferida !== true) {
      problemas.push({
        campo: "fila-liberacao-conferida",
        mensagem: "Esta fila só aceita aluno com a liberação conferida: marque que você viu o atestado/triagem.",
      });
    }
    if (!liberacaoEm) {
      problemas.push({ campo: "fila-liberacao-em", mensagem: "Informe a data da liberação." });
    } else if (!lerDia(liberacaoEm)) {
      problemas.push({ campo: "fila-liberacao-em", mensagem: "A data da liberação é inválida." });
    } else if (lerDia(hoje) && liberacaoEm > hoje) {
      // 'AAAA-MM-DD' compara como texto
      problemas.push({ campo: "fila-liberacao-em", mensagem: "A data da liberação não pode ser no futuro." });
    }
  }
  return problemas;
}

// O pedido de POST /api/alunos/<id>/fila. Nas filas sem liberação só vão a fila e o professor.
export function montarPedidoDaFila({ filaId, professor, exigeLiberacao = false, conferida = false, liberacaoEm = "" }) {
  return {
    fila_id: Number(limparEspacos(filaId ?? "")),
    professor: limparEspacos(professor ?? ""),
    ...(exigeLiberacao ? { liberacao_conferida: conferida === true, liberacao_em: liberacaoEm || null } : {}),
  };
}
