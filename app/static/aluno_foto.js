// Foto do aluno no app (pedido do Thiago, 29/10/2026): o aluno vê a foto dele e pode trocar a foto tirada na recepção por uma foto do rosto
// que ele prefira. Vale na hora, aqui e para o professor. "Voltar para a foto da recepção" apaga a foto escolhida.
// A foto escolhida é reduzida AQUI, no celular, antes de ir (uma foto de celular tem vários MB); o servidor refaz as versões e descarta o resto
// (inclusive dados escondidos na foto, como o local onde foi tirada). Prévia num <canvas>: a página não aceita imagem de "blob:".
import { buscarJson, enviarJson } from "./api.js";
import {
  QUALIDADE_DO_ENVIO,
  TAMANHO_MAXIMO_DO_ARQUIVO,
  descreverEnvioDaFoto,
  medidasDoEnvio,
  recorteQuadrado,
  textoDaSituacao,
} from "./aluno_foto_modelo.js";

const secao = document.getElementById("minha-foto");
const atual = document.getElementById("minha-foto-atual");
const vazia = document.getElementById("minha-foto-vazia");
const texto = document.getElementById("minha-foto-texto");
const previa = document.getElementById("minha-foto-previa");
const arquivo = document.getElementById("minha-foto-arquivo");
const botaoTrocar = document.getElementById("minha-foto-trocar");
const botaoSalvar = document.getElementById("minha-foto-salvar");
const botaoCancelar = document.getElementById("minha-foto-cancelar");
const botaoApagar = document.getElementById("minha-foto-apagar");
const aviso = document.getElementById("minha-foto-aviso");

let escolhida = null; // a foto reduzida, pronta para mandar (base64)

function mostrar(situacao) {
  const temFoto = Boolean(situacao && situacao.tem_foto);
  if (temFoto) atual.src = "/aluno/foto?v=" + Date.now(); // força buscar de novo depois de trocar
  atual.hidden = !temFoto;
  vazia.hidden = temFoto;
  texto.textContent = textoDaSituacao(situacao);
  botaoTrocar.textContent = temFoto ? "Trocar foto" : "Escolher foto";
  botaoApagar.hidden = !(situacao && situacao.propria);
  botaoApagar.textContent = situacao && situacao.tem_catraca ? "Voltar para a foto da recepção" : "Apagar minha foto";
  secao.hidden = false;
}

function modoEscolha(ligado) {
  previa.hidden = !ligado;
  botaoSalvar.hidden = !ligado;
  botaoCancelar.hidden = !ligado;
  botaoTrocar.hidden = ligado;
  atual.hidden = ligado || atual.hidden;
  if (!ligado) escolhida = null;
}

async function carregar() {
  try {
    const { status, corpo } = await buscarJson("/api/aluno/foto");
    if (status === 401) return window.location.assign("/aluno/entrar");
    if (status === 200 && corpo) mostrar(corpo);
  } catch {
    /* sem rede: a seção fica escondida; o treino continua funcionando */
  }
}

function lerComoBase64(blob) {
  return new Promise((resolver, recusar) => {
    const leitor = new FileReader();
    leitor.onload = () => resolver(String(leitor.result).split(",")[1] || "");
    leitor.onerror = () => recusar(leitor.error);
    leitor.readAsDataURL(blob);
  });
}

async function prepararFoto(escolha) {
  aviso.textContent = "";
  if (!escolha) return;
  if (!escolha.type.startsWith("image/") || escolha.size > TAMANHO_MAXIMO_DO_ARQUIVO) {
    aviso.textContent = "Escolha uma foto (JPG ou PNG).";
    return;
  }
  let imagem;
  try {
    imagem = await createImageBitmap(escolha, { imageOrientation: "from-image" });
  } catch {
    aviso.textContent = "Não deu para abrir esta foto. Tente outra.";
    return;
  }
  const medidas = medidasDoEnvio(imagem.width, imagem.height);
  const tela = document.createElement("canvas");
  tela.width = medidas.largura;
  tela.height = medidas.altura;
  tela.getContext("2d").drawImage(imagem, 0, 0, medidas.largura, medidas.altura);
  // a prévia: o mesmo recorte quadrado que vai aparecer no círculo
  const recorte = recorteQuadrado(medidas.largura, medidas.altura);
  previa.getContext("2d").drawImage(tela, recorte.x, recorte.y, recorte.lado, recorte.lado, 0, 0, previa.width, previa.height);
  imagem.close?.();
  const blob = await new Promise((resolver) => tela.toBlob(resolver, "image/jpeg", QUALIDADE_DO_ENVIO));
  if (!blob) {
    aviso.textContent = "Não deu para preparar esta foto. Tente outra.";
    return;
  }
  escolhida = await lerComoBase64(blob);
  modoEscolha(true);
  texto.textContent = "Confira a foto nova. Ela só vale depois que você tocar em \u201cUsar esta foto\u201d.";
}

async function enviar(rota, corpo, textoDeEspera) {
  botaoSalvar.disabled = true;
  botaoApagar.disabled = true;
  aviso.textContent = textoDeEspera;
  try {
    const { status, corpo: resposta } = await enviarJson(rota, corpo, 60000);
    const resultado = descreverEnvioDaFoto(status, resposta);
    if (resultado.tipo === "sair") return window.location.assign("/aluno/entrar");
    if (resultado.tipo === "erro") {
      aviso.textContent = resultado.texto;
      return;
    }
    modoEscolha(false);
    mostrar(resultado.situacao);
    aviso.textContent = resultado.situacao.propria ? "Foto salva." : "Pronto.";
  } catch {
    aviso.textContent = "Sem conexão. A foto não foi salva; tente de novo.";
  } finally {
    botaoSalvar.disabled = false;
    botaoApagar.disabled = false;
  }
}

if (secao) {
  botaoTrocar.addEventListener("click", () => arquivo.click());
  arquivo.addEventListener("change", () => {
    prepararFoto(arquivo.files && arquivo.files[0]);
    arquivo.value = ""; // escolher a mesma foto de novo também dispara
  });
  botaoCancelar.addEventListener("click", () => {
    modoEscolha(false);
    aviso.textContent = "";
    carregar();
  });
  botaoSalvar.addEventListener("click", () => {
    if (escolhida) enviar("/api/aluno/foto", { jpg: escolhida }, "Salvando a foto…");
  });
  botaoApagar.addEventListener("click", () => enviar("/api/aluno/foto/apagar", {}, "Um momento…"));
  carregar();
}
