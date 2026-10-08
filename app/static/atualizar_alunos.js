// Tela "Atualizar alunos": o computador escolhe o base_total.zip, o navegador separa as tabelas
// e as colunas de que o app precisa (alunos e histórico de treinos) e envia só isso ao servidor.
import { enviarJson, MENSAGEM_NAO_AUTORIZADO } from "./api.js";
import {
  ARQUIVOS_DOS_TREINOS,
  ARQUIVOS_NECESSARIOS,
  CopiaInvalida,
  TAMANHO_MAXIMO_DA_TABELA,
  criarEtapas,
  descreverCopia,
  descreverTreinos,
  enviarEtapas,
  juntarRelatorios,
  montarPacote,
  montarPacoteDeTreinos,
} from "./copia_modelo.js";
import { ZipInvalido, lerEntrada, listarEntradas } from "./zip_leitor.js";

const TEMPO_MAXIMO_DO_ENVIO_MS = 120000; // pacote de alguns MB, numa internet que pode estar lenta
// Modo de teste (para quem administra): /alunos/atualizar?simular_treinos=1 faz o servidor
// contar o que faria com o histórico de treinos, sem gravar nada. Os alunos são atualizados normalmente.
const SIMULAR_TREINOS = new URLSearchParams(location.search).get("simular_treinos") === "1";

const campoArquivo = document.getElementById("arquivo");
const botao = document.getElementById("botao-enviar");
const resumo = document.getElementById("resumo");
const erroGeral = document.getElementById("erro-geral");
const relatorio = document.getElementById("relatorio");
const modoTeste = document.getElementById("modo-teste");

let etapas = null; // [alunos, treinos], criadas quando o arquivo é lido
let ocupado = false;

if (SIMULAR_TREINOS) modoTeste.hidden = false;

function limpar() {
  etapas = null;
  botao.disabled = true;
  resumo.textContent = ""; // textContent: o texto nunca é interpretado como HTML
  erroGeral.textContent = "";
  relatorio.hidden = true;
  relatorio.textContent = "";
}

function mostrarRelatorio() {
  const texto = juntarRelatorios(etapas);
  relatorio.textContent = texto;
  relatorio.hidden = texto === "";
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
    for (const nome of [...ARQUIVOS_NECESSARIOS, ...ARQUIVOS_DOS_TREINOS]) {
      arquivos[nome] = await lerEntrada(bytes, entradas, nome, TAMANHO_MAXIMO_DA_TABELA);
    }
    const alunos = montarPacote(arquivos);
    const treinos = montarPacoteDeTreinos(arquivos);
    if (SIMULAR_TREINOS) treinos.pacote.simular = true;
    const { texto, aviso } = descreverCopia(alunos.resumo);
    resumo.textContent = `${texto} ${descreverTreinos(treinos.resumo)}`;
    if (aviso) erroGeral.textContent = aviso;
    etapas = criarEtapas(alunos.pacote, treinos.pacote);
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
  if (ocupado || etapas === null) return; // clique duplo não manda duas vezes
  ocupado = true;
  botao.disabled = true;
  erroGeral.textContent = "";
  const lista = etapas; // a tela pode ser limpa (outro arquivo) enquanto o envio anda
  try {
    const resultado = await enviarEtapas(
      lista,
      (rota, pacote) => enviarJson(rota, pacote, TEMPO_MAXIMO_DO_ENVIO_MS),
      (etapa) => {
        resumo.textContent =
          etapa.chave === "alunos"
            ? "Enviando e atualizando os alunos... pode levar alguns segundos."
            : "Enviando o histórico de treinos... isto leva alguns segundos a mais.";
      },
    );
    mostrarRelatorio();
    if (resultado.completo) {
      resumo.textContent = SIMULAR_TREINOS
        ? "Pronto: os alunos foram atualizados. O histórico de treinos foi só simulado (nada foi gravado)."
        : "Pronto: os alunos e o histórico de treinos foram atualizados.";
      etapas = null; // enviado: para enviar de novo, escolha o arquivo outra vez
      return;
    }
    const alunosJaForam = lista[0].enviado;
    resumo.textContent = alunosJaForam ? "Os alunos foram atualizados, mas o histórico de treinos ainda não." : "";
    erroGeral.textContent =
      resultado.resultado.tipo === "nao_autorizado" ? MENSAGEM_NAO_AUTORIZADO : resultado.resultado.mensagem;
    botao.disabled = false; // tentar de novo manda só o que faltou
  } finally {
    ocupado = false;
  }
});
