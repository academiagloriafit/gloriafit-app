// Foto ampliada (29/10/2026): as contas da tela, sem mexer na página (testadas em tests_js/foto_grande_modelo.test.js).

// "/alunos/12/foto" -> "/alunos/12/foto?tamanho=grande". Só aceita o endereço da foto do aluno (nunca monta outro endereço).
export function enderecoDaFotoGrande(endereco) {
  if (typeof endereco !== "string") return null;
  const caminho = endereco.replace(/^https?:\/\/[^/]+/, "").split(/[?#]/)[0];
  return /^\/alunos\/[0-9]{1,18}\/foto$/.test(caminho) ? caminho + "?tamanho=grande" : null;
}

// A legenda embaixo da foto: o nome como se escreve; sem nome, um texto genérico.
export function textoDaLegenda(nome) {
  return typeof nome === "string" && nome.trim() ? nome.trim() : "Foto do aluno";
}
