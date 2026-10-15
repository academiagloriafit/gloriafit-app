// Tela /aluno/entrar: entrar com CPF e senha, ou pedir o código por WhatsApp e criar a senha.
import { enviarJson } from "./api.js";
import {
  MENSAGEM_SEM_REDE,
  conferirCodigo,
  conferirCpf,
  conferirSenhaNova,
  descreverResposta,
  formatarCpf,
  soNumeros,
  textoDoReenvio,
} from "./aluno_modelo.js";

const $ = (id) => document.getElementById(id);

const telas = { entrar: $("tela-entrar"), cpf: $("tela-cpf"), codigo: $("tela-codigo") };
let cpfDoPedido = ""; // o CPF (só números) para o qual o código foi pedido
let relogio = null;

function mostrarTela(nome, campoParaFoco) {
  for (const [chave, secao] of Object.entries(telas)) secao.hidden = chave !== nome;
  if (campoParaFoco) $(campoParaFoco).focus();
}

function avisar(id, texto, erro) {
  const aviso = $(id);
  aviso.textContent = texto; // textContent: o texto nunca é interpretado como HTML
  aviso.classList.toggle("aviso-erro", erro);
}

// CPF com pontos e traço enquanto digita.
for (const id of ["entrar-cpf", "cpf-cpf"]) {
  $(id).addEventListener("input", (evento) => {
    evento.target.value = formatarCpf(evento.target.value);
  });
}

// "Mostrar a senha".
function ligarMostrarSenha(caixa, campos) {
  $(caixa).addEventListener("change", (evento) => {
    for (const id of campos) $(id).type = evento.target.checked ? "text" : "password";
  });
}
ligarMostrarSenha("entrar-mostrar", ["entrar-senha"]);
ligarMostrarSenha("codigo-mostrar", ["codigo-senha", "codigo-repetir"]);

// Um envio de cada vez por formulário (clique duplo não manda duas vezes).
async function enviarFormulario(botao, avisoId, quemEnvia) {
  if (botao.disabled) return null;
  botao.disabled = true;
  avisar(avisoId, "Conferindo…", false);
  try {
    const resposta = await quemEnvia();
    const resultado = descreverResposta(resposta.status, resposta.corpo);
    avisar(avisoId, resultado.ok ? "" : resultado.mensagem, !resultado.ok);
    return resultado.ok ? resposta.corpo : null;
  } catch {
    avisar(avisoId, MENSAGEM_SEM_REDE, true);
    return null;
  } finally {
    botao.disabled = false;
  }
}

// ---- entrar
$("form-entrar").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const erro = conferirCpf($("entrar-cpf").value);
  if (erro) return avisar("entrar-aviso", erro, true);
  if (!$("entrar-senha").value) return avisar("entrar-aviso", "Digite a sua senha.", true);
  const corpo = await enviarFormulario($("entrar-botao"), "entrar-aviso", () =>
    enviarJson("/api/aluno/entrar", { cpf: $("entrar-cpf").value, senha: $("entrar-senha").value }),
  );
  if (corpo) window.location.assign("/aluno");
});

$("abrir-primeiro-acesso").addEventListener("click", () => {
  $("cpf-cpf").value = $("entrar-cpf").value;
  avisar("cpf-aviso", "", false);
  mostrarTela("cpf", "cpf-cpf");
});

// ---- pedir o código
function contarParaReenviar(segundos) {
  clearInterval(relogio);
  const botao = $("codigo-reenviar");
  let restante = segundos;
  const atualizar = () => {
    botao.textContent = textoDoReenvio(restante);
    botao.disabled = restante > 0;
  };
  atualizar();
  relogio = setInterval(() => {
    restante -= 1;
    atualizar();
    if (restante <= 0) clearInterval(relogio);
  }, 1000);
}

async function pedirCodigo(avisoId, botao) {
  const corpo = await enviarFormulario(botao, avisoId, () => enviarJson("/api/aluno/codigo", { cpf: cpfDoPedido }));
  if (corpo) contarParaReenviar(Number.isFinite(corpo.espera) ? corpo.espera : 60);
  return corpo;
}

$("form-cpf").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const erro = conferirCpf($("cpf-cpf").value);
  if (erro) return avisar("cpf-aviso", erro, true);
  cpfDoPedido = soNumeros($("cpf-cpf").value, 11);
  if (await pedirCodigo("cpf-aviso", $("cpf-botao"))) {
    avisar("codigo-aviso", "", false);
    mostrarTela("codigo", "codigo-codigo");
  }
});

$("codigo-reenviar").addEventListener("click", async () => {
  if (await pedirCodigo("codigo-aviso", $("codigo-reenviar"))) avisar("codigo-aviso", "Pedido feito de novo. Use o código mais novo.", false);
});

// ---- criar a senha com o código
$("form-codigo").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const erro = conferirCodigo($("codigo-codigo").value) || conferirSenhaNova($("codigo-senha").value, $("codigo-repetir").value);
  if (erro) return avisar("codigo-aviso", erro, true);
  const corpo = await enviarFormulario($("codigo-botao"), "codigo-aviso", () =>
    enviarJson("/api/aluno/primeiro-acesso", {
      cpf: cpfDoPedido,
      codigo: soNumeros($("codigo-codigo").value, 6),
      senha: $("codigo-senha").value,
    }),
  );
  if (corpo) window.location.assign("/aluno");
});

// ---- voltar
$("cpf-voltar").addEventListener("click", () => mostrarTela("entrar", "entrar-cpf"));
$("codigo-voltar").addEventListener("click", () => {
  clearInterval(relogio);
  mostrarTela("cpf", "cpf-cpf");
});
