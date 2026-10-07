// Tela "Atualizar alunos": o computador escolhe o base_total.zip, o navegador separa as 3
// tabelas e as colunas de que o app precisa e envia só isso ao servidor.
import { enviarJson, MENSAGEM_NAO_AUTORIZADO } from "./api.js";
import {
  ARQUIVOS_NECESSARIOS,
  CopiaInvalida,
  MENSAGEM_SEM_REDE,
  TAMANHO_MAXIMO_DA_TABELA,
  descreverCopia,
  interpretarResposta,
  montarPacote,
} from "./copia_modelo.js";
import { ZipInvalido, lerEntrada, listarEntradas } from "./zip_leitor.js";

const TEMPO_MAXIMO_DO_ENVIO_MS = 120000; // pacote de alguns MB, numa internet que pode estar lenta

const campoArquivo = document.getElementById("arquivo");
const botao = document.getElementById("botao-enviar");
const resumo = document.getElementById("resumo");
const erroGeral = document.getElementById("erro-geral");
const relatorio = document.getElementById("relatorio");

let pacote = null;
let ocupado = false;

function limpar() {
  pacote = null;
  botao.disabled = true;
  resumo.textContent = ""; // textContent: o texto nunca é interpretado como HTML
  erroGeral.textContent = "";
  relatorio.hidden = true;
  relatorio.textContent = "";
}

campoArquivo.addEventListener("change", async () => {
  limpar();
  const arquivo = campoArquivo.files[0];
  if (!arquivo) return;
  ocupado = true;
  resumo.textContent = "Lendo o arquivo...";
  try {
    const bytes = new Uint8Array(await arquivo.arrayBuffer());
    const entradas = listarEntradas(bytes);
    const arquivos = {};
    for (const nome of ARQUIVOS_NECESSARIOS) {
      arquivos[nome] = await lerEntrada(bytes, entradas, nome, TAMANHO_MAXIMO_DA_TABELA);
    }
    const preparado = montarPacote(arquivos);
    const { texto, aviso } = descreverCopia(preparado.resumo);
    resumo.textContent = texto;
    if (aviso) erroGeral.textContent = aviso;
    pacote = preparado.pacote;
    botao.disabled = false;
  } catch (erro) {
    resumo.textContent = "";
    if (erro instanceof ZipInvalido || erro instanceof CopiaInvalida) {
      erroGeral.textContent = erro.message;
    } else {
      erroGeral.textContent = "Não consegui ler este arquivo. Escolha o base_total.zip da pasta NFSE.";
    }
  } finally {
    ocupado = false;
  }
});

botao.addEventListener("click", async () => {
  if (ocupado || pacote === null) return; // clique duplo não manda duas vezes
  ocupado = true;
  botao.disabled = true;
  erroGeral.textContent = "";
  resumo.textContent = "Enviando e atualizando... pode levar alguns segundos.";
  try {
    const { status, corpo } = await enviarJson("/api/alunos/importar", pacote, TEMPO_MAXIMO_DO_ENVIO_MS);
    const resultado = interpretarResposta(status, corpo);
    if (resultado.tipo === "ok") {
      resumo.textContent = "Pronto: os alunos foram atualizados.";
      relatorio.textContent = resultado.texto;
      relatorio.hidden = false;
      pacote = null; // enviado: para enviar de novo, escolha o arquivo outra vez
      return;
    }
    resumo.textContent = "";
    erroGeral.textContent = resultado.tipo === "nao_autorizado" ? MENSAGEM_NAO_AUTORIZADO : resultado.mensagem;
    botao.disabled = false;
  } catch {
    resumo.textContent = "";
    erroGeral.textContent = MENSAGEM_SEM_REDE;
    botao.disabled = false;
  } finally {
    ocupado = false;
  }
});
