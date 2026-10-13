// Ficha do aluno: botão "Salvar como treino padrão" em cada treino. O treino vira um treino padrão (aparece em
// "Importar treino" na tela de lançar treino) com o nome que o professor escolher. Opcionalmente ele entra numa fila
// (Homem, Mulher...) com um número (Treino 1, 2, 3...). A regra de verdade está no servidor (app/modelos.py,
// app/filas.py); aqui só pedimos e mostramos a resposta.
import { enviarJson, motivoDaSenha, textoDoErro } from "./api.js";
import { ligarSeletorDeFila } from "./fila_padrao.js";
import { LIMITE_NOME_TREINO, lerPosicaoNaFila, limparEspacos, problemaDaSenhaDeAdmin, tamanho } from "./treino_modelo.js";

const SEM_REDE =
  "Não consegui confirmar com o servidor se o treino padrão foi guardado (sem resposta ou sem rede). " +
  'Confira em "Importar treino", aba "Treino padrão", antes de tentar de novo.';

for (const barra of document.querySelectorAll(".acoes-treino")) {
  const botao = barra.querySelector(".botao-padrao");
  const formulario = barra.querySelector(".form-padrao-ficha");
  const campo = barra.querySelector(".campo-padrao");
  const guardar = barra.querySelector(".sim-padrao");
  const aviso = barra.querySelector(".aviso-padrao");
  const selecaoDaFila = barra.querySelector(".campo-fila-padrao");
  const campoNumero = barra.querySelector(".campo-numero-padrao");
  const dicaDaFila = barra.querySelector(".dica-fila-padrao");
  const campoSenha = barra.querySelector(".campo-senha-admin");
  if (!botao || !formulario || !campo || !guardar || !aviso || !selecaoDaFila || !campoNumero || !dicaDaFila || !campoSenha) continue;
  const fila = ligarSeletorDeFila({ select: selecaoDaFila, campoNumero, dica: dicaDaFila });
  let enviando = false;

  function avisar(texto, erro = false) {
    aviso.textContent = texto;
    aviso.classList.toggle("aviso-erro", erro);
  }

  function fechar() {
    campoSenha.value = ""; // a senha não fica na tela
    formulario.hidden = true;
    botao.hidden = false;
  }

  async function enviar() {
    if (enviando) return; // clique duplo ou Enter repetido não manda duas vezes
    const nome = limparEspacos(campo.value);
    if (nome === "") {
      avisar("Dê um nome ao treino padrão.", true);
      campo.focus();
      return;
    }
    if (tamanho(nome) > LIMITE_NOME_TREINO) {
      avisar(`O nome tem ${tamanho(nome)} letras; o máximo é ${LIMITE_NOME_TREINO}.`, true);
      campo.focus();
      return;
    }
    const posicao = lerPosicaoNaFila({ filaId: selecaoDaFila.value, numero: campoNumero.value });
    if (!posicao.ok) {
      avisar(posicao.mensagem, true);
      (posicao.campo === "fila" ? selecaoDaFila : campoNumero).focus();
      return;
    }
    // Os treinos padrão são fixos: guardar um novo exige a senha de administrador (o servidor confere).
    const problemaDaSenha = problemaDaSenhaDeAdmin(campoSenha.value);
    if (problemaDaSenha) {
      avisar(problemaDaSenha, true);
      campoSenha.focus();
      return;
    }
    const senhaAdmin = campoSenha.value;
    campoSenha.value = ""; // a senha sai da tela assim que é enviada; se o servidor recusar, o professor digita de novo
    enviando = true;
    guardar.disabled = true;
    avisar("Guardando…");
    let resposta;
    try {
      resposta = await enviarJson(`/api/treinos/${encodeURIComponent(guardar.dataset.treino)}/modelo`, {
        senha_admin: senhaAdmin,
        nome,
        fila_id: posicao.filaId,
        numero: posicao.numero,
      });
    } catch {
      avisar(SEM_REDE, true);
      return;
    } finally {
      enviando = false;
      guardar.disabled = false;
    }
    if (resposta.status === 201) {
      fechar();
      const textoDaFila =
        posicao.filaId === null ? "" : ` Ele é o Treino ${posicao.numero} da fila ${selecaoDaFila.selectedOptions[0].textContent}.`;
      avisar(`Guardado como treino padrão "${nome}".${textoDaFila} Ele aparece em "Importar treino", na tela de lançar treino.`);
      if (posicao.filaId !== null) fila.registrarUsado(posicao.numero);
      botao.focus();
      return;
    }
    const erro = textoDoErro(resposta, "O servidor não guardou o treino padrão");
    avisar(erro, true);
    if (motivoDaSenha(resposta)) campoSenha.focus(); // senha errada, travada ou ainda não definida
    // 409: o nome já existe ou o número já tem treino na fila (a mensagem do servidor diz qual dos dois)
    else if (resposta.status === 409) (erro.includes("Escolha outro número") ? campoNumero : campo).focus();
  }

  botao.addEventListener("click", () => {
    avisar("");
    botao.hidden = true;
    formulario.hidden = false;
    campo.focus();
    campo.select();
  });
  barra.querySelector(".nao-padrao").addEventListener("click", () => {
    fechar();
    avisar("");
    botao.focus();
  });
  guardar.addEventListener("click", enviar);
  for (const entrada of [campo, campoSenha]) {
    entrada.addEventListener("keydown", (evento) => {
      if (evento.key === "Enter" && !evento.isComposing) {
        evento.preventDefault();
        enviar();
      }
    });
  }
}
