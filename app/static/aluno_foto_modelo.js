// Foto escolhida pelo aluno (29/10/2026): as contas da tela, sem mexer na página (tests_js/aluno_foto_modelo.test.js).

export const LADO_MAXIMO_DO_ENVIO = 1280; // o celular reduz a foto antes de mandar (uma foto de celular tem 3 a 12 MB)
export const QUALIDADE_DO_ENVIO = 0.86;
export const TAMANHO_MAXIMO_DO_ARQUIVO = 30 * 1024 * 1024; // acima disso nem tenta abrir

// Largura e altura para mandar: no máximo LADO_MAXIMO_DO_ENVIO no lado maior, sem aumentar foto pequena.
export function medidasDoEnvio(largura, altura, ladoMaximo = LADO_MAXIMO_DO_ENVIO) {
  if (!(largura > 0) || !(altura > 0)) return null;
  const escala = Math.min(1, ladoMaximo / Math.max(largura, altura));
  return { largura: Math.max(1, Math.round(largura * escala)), altura: Math.max(1, Math.round(altura * escala)) };
}

// O quadrado que aparece no círculo (o mesmo recorte do servidor: um pouco acima do centro, onde fica o rosto).
export function recorteQuadrado(largura, altura) {
  const lado = Math.min(largura, altura);
  const x = Math.round((largura - lado) / 2);
  const y = Math.round(Math.min(Math.max((altura - lado) * 0.38, 0), altura - lado));
  return { x, y, lado };
}

// O texto embaixo da foto.
export function textoDaSituacao(situacao) {
  if (!situacao || !situacao.tem_foto) return "Você ainda não tem foto. Escolha uma foto do seu rosto: ela aparece aqui e para o professor.";
  if (situacao.propria) return "Esta é a foto que você escolheu. O professor também vê esta foto.";
  return "Esta é a foto tirada na recepção. Se quiser, troque por uma foto do seu rosto: o professor também vê a foto que você escolher.";
}

// A resposta do servidor ao trocar ou apagar a foto.
export function descreverEnvioDaFoto(status, corpo) {
  if (status === 200 && corpo && corpo.ok) return { tipo: "ok", situacao: corpo };
  if (status === 401) return { tipo: "sair" };
  if (status === 413) return { tipo: "erro", texto: "A foto ficou grande demais. Tente outra foto." };
  const texto = corpo && typeof corpo.erro === "string" ? corpo.erro : "Não deu para salvar a foto agora. Tente de novo.";
  return { tipo: "erro", texto };
}
