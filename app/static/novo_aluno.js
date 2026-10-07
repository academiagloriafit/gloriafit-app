// Tela "Aluno provisório": manda nome, CPF e WhatsApp ao servidor. Se der certo, abre a
// tela de montar o treino do aluno recém-cadastrado.
import { enviarJson, MENSAGEM_NAO_AUTORIZADO } from "./api.js";
import { CAMPOS, MENSAGEM_SEM_REDE, descreverExistente, interpretarResposta } from "./novo_aluno_modelo.js";

const formulario = document.getElementById("form-novo-aluno");
const botao = document.getElementById("botao-salvar-novo");
const erroGeral = document.getElementById("erro-geral");
const listaExistentes = document.getElementById("cpf-existentes");
const campos = Object.fromEntries(CAMPOS.map((c) => [c, document.getElementById(c)]));
const erros = Object.fromEntries(CAMPOS.map((c) => [c, document.getElementById("erro-" + c)]));

let enviando = false;

function limparErros() {
  for (const c of CAMPOS) {
    erros[c].textContent = ""; // textContent: o texto nunca é interpretado como HTML
    campos[c].removeAttribute("aria-invalid");
  }
  erroGeral.textContent = "";
  listaExistentes.textContent = "";
}

function marcarErro(campo, mensagem) {
  erros[campo].textContent = mensagem;
  campos[campo].setAttribute("aria-invalid", "true");
}

function mostrarExistentes(resultado) {
  marcarErro("cpf", resultado.mensagem);
  for (const existente of resultado.existentes) {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = "/alunos/" + existente.id; // o id é conferido como número em interpretarResposta
    link.textContent = descreverExistente(existente) + " · abrir a ficha";
    item.append(link);
    listaExistentes.append(item);
  }
}

formulario.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  if (enviando) return; // clique duplo não manda duas vezes
  enviando = true;
  botao.disabled = true;
  limparErros();

  try {
    const { status, corpo } = await enviarJson("/api/alunos", {
      nome: campos.nome.value,
      cpf: campos.cpf.value,
      whatsapp: campos.whatsapp.value,
    });
    if (status === 401) {
      erroGeral.textContent = MENSAGEM_NAO_AUTORIZADO;
    } else {
      const resultado = interpretarResposta(status, corpo);
      if (resultado.tipo === "criado") {
        window.location.assign("/alunos/" + resultado.id + "/montar");
        return; // o botão continua travado: a página está sendo trocada
      }
      if (resultado.tipo === "erros") {
        for (const [campo, mensagem] of Object.entries(resultado.erros)) {
          if (campo === "geral") erroGeral.textContent = mensagem;
          else marcarErro(campo, mensagem);
        }
        const primeiro = CAMPOS.find((c) => resultado.erros[c]);
        if (primeiro) campos[primeiro].focus();
      } else if (resultado.tipo === "cpf_existente") {
        mostrarExistentes(resultado);
        campos.cpf.focus();
      } else {
        erroGeral.textContent = resultado.mensagem;
      }
    }
  } catch {
    erroGeral.textContent = MENSAGEM_SEM_REDE;
  }
  enviando = false;
  botao.disabled = false;
});
