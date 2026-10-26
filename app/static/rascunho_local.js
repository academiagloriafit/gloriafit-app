// Rascunho do treino NOVO guardado no navegador (pedido do Thiago, 26/10/2026): antes ficava no sessionStorage e sumia ao fechar a
// aba; agora fica no localStorage, sobrevive a fechar a aba e o navegador, e vale por VALIDADE_MS. Passou disso, é apagado na
// próxima abertura (um rascunho velho atrapalharia quem for montar outro treino para o mesmo aluno no mesmo computador).
// Guarda só o que está na tela (exercícios, nome do treino, professor, datas): nada de CPF nem de texto da IA.
// Testado em tests_js/rascunho_local.test.js; quem usa é montar.js.

export const VALIDADE_MS = 3 * 24 * 60 * 60 * 1000; // 3 dias
const TOLERANCIA_DO_RELOGIO_MS = 60 * 1000; // relógio do computador acertado para trás: até 1 minuto "no futuro" ainda vale

export function chavesDoAluno(alunoId) {
  return {
    rascunho: "rascunho-treino-" + alunoId,
    dados: "rascunho-dados-" + alunoId,
    quando: "rascunho-quando-" + alunoId,
  };
}

// O localStorage, ou null se o navegador não deixa usar (aba anônima com bloqueio, cota cheia...): a tela funciona sem rascunho.
export function armazenamentoDoNavegador() {
  try {
    const arm = globalThis.localStorage;
    return arm ?? null;
  } catch {
    return null;
  }
}

export function apagar(arm, chaves) {
  if (!arm) return;
  try {
    for (const chave of Object.values(chaves)) arm.removeItem(chave);
  } catch {
    /* sem armazenamento: nada a apagar */
  }
}

// { rascunho: texto | null, dados: texto | null, guardadoEm: ms | null }. Vencido, sem data ou com data estranha: apaga e volta vazio.
export function ler(arm, chaves, agora = Date.now()) {
  const vazio = { rascunho: null, dados: null, guardadoEm: null };
  if (!arm) return vazio;
  try {
    const quando = Number(arm.getItem(chaves.quando));
    const valido = Number.isFinite(quando) && quando > 0 && agora - quando <= VALIDADE_MS && quando <= agora + TOLERANCIA_DO_RELOGIO_MS;
    if (!valido) {
      apagar(arm, chaves);
      return vazio;
    }
    return { rascunho: arm.getItem(chaves.rascunho), dados: arm.getItem(chaves.dados), guardadoEm: quando };
  } catch {
    return vazio;
  }
}

export function gravar(arm, chaves, rascunho, dados, agora = Date.now()) {
  if (!arm) return false;
  try {
    arm.setItem(chaves.rascunho, rascunho);
    arm.setItem(chaves.dados, dados);
    arm.setItem(chaves.quando, String(agora));
    return true;
  } catch {
    return false; // cota cheia ou bloqueado: segue sem rascunho
  }
}

// 1761515400000 -> "26/10 às 19:10" (hora deste computador).
export function textoDoQuando(ms) {
  const d = new Date(ms);
  const dois = (n) => String(n).padStart(2, "0");
  return `${dois(d.getDate())}/${dois(d.getMonth() + 1)} às ${dois(d.getHours())}:${dois(d.getMinutes())}`;
}
