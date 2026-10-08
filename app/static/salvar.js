// Envio do treino ao servidor e tela "Treino salvo". O nome do treino e o professor
// ficam no alto da tela de montagem (montar.js); a lógica de conferir e de montar o
// pedido está em treino_modelo.js (testada à parte). Aqui só falamos com o servidor.
import { enviarJson } from "./api.js";
import * as M from "./treino_modelo.js";

const pegar = (id) => document.getElementById(id);

// alunoId, alunoNome: de quem é o treino.
// obterEstado(): o treino que está na tela de montagem.
// obterDados(): { nomeTreino, montadoPor } como estão nos campos do alto.
// aoTravar(travado): a tela desliga (ou religa) os campos e o botão enquanto envia.
// aoErros(mensagens, { nomeJaUsado }): a tela mostra o que deu errado.
// aoSalvar(): chamada depois que o servidor confirmou (a tela apaga o rascunho).
export function iniciarSalvar({ alunoId, alunoNome, obterEstado, obterDados, aoTravar, aoErros, aoSalvar }) {
  const areaMontagem = pegar("area-montagem");
  const painelSalvo = pegar("treino-salvo");
  let salvando = false;

  function travar(travado) {
    salvando = travado;
    aoTravar(travado);
  }

  // Confere os dados do alto (nome e professor) e, se estiver tudo certo, envia.
  // Devolve os problemas dos dados (lista vazia = foi enviado ou está enviando).
  async function enviar() {
    if (salvando) return []; // clique duplo ou Enter repetido não manda duas vezes
    const dados = obterDados();

    travar(true);
    let resposta;
    try {
      resposta = await enviarJson(`/api/alunos/${encodeURIComponent(alunoId)}/treinos`, M.montarPedido(obterEstado(), dados));
    } catch {
      travar(false);
      aoErros(
        [
          "Não consegui confirmar com o servidor se o treino foi salvo (sem resposta ou sem rede). " +
            "Confira a rede e clique em Salvar treino de novo: se ele já tiver sido salvo, o app avisará que o nome já existe.",
        ],
        { nomeJaUsado: false },
      );
      return [];
    }

    if (resposta.status === 201) {
      sucesso(
        M.limparEspacos(dados.nomeTreino),
        M.limparEspacos(dados.montadoPor),
        M.enderecoDeImpressao(resposta.corpo),
        resposta.corpo?.concluido_anterior,
      );
      return [];
    }

    const corpo = resposta.corpo; // null se não for JSON (ex.: página de erro): cai na mensagem genérica
    travar(false);
    let mensagens = Array.isArray(corpo?.erros) ? corpo.erros.filter((m) => typeof m === "string") : [];
    if (mensagens.length === 0) {
      mensagens = [
        typeof corpo?.erro === "string"
          ? corpo.erro
          : `O servidor devolveu um erro (código ${resposta.status}). O treino não foi salvo.`,
      ];
    }
    aoErros(mensagens, { nomeJaUsado: resposta.status === 409 }); // 409: nome já usado por este aluno
    return [];
  }

  // concluidoAnterior: o nome do treino que estava ativo e foi concluído junto (ou nada, se não havia).
  function sucesso(nomeTreino, montadoPor, enderecoDeImpressao, concluidoAnterior) {
    aoSalvar();
    areaMontagem.hidden = true;
    const linkImprimir = pegar("imprimir-treino");
    if (enderecoDeImpressao) linkImprimir.href = enderecoDeImpressao;
    linkImprimir.hidden = !enderecoDeImpressao;
    pegar("texto-salvo").textContent =
      `O treino "${nomeTreino}" foi salvo para ${alunoNome}. Professor: ${montadoPor}.`;
    const textoConcluido = pegar("texto-concluido");
    const houveConclusao = typeof concluidoAnterior === "string" && concluidoAnterior !== "";
    textoConcluido.textContent = houveConclusao
      ? `O treino anterior, "${concluidoAnterior}", foi concluído e está no histórico (inativo).`
      : "";
    textoConcluido.hidden = !houveConclusao;
    painelSalvo.hidden = false;
    window.scrollTo(0, 0);
    pegar("titulo-salvo").focus();
  }

  pegar("montar-outro").addEventListener("click", () => window.location.reload());

  return { enviar };
}
