// Campos "Fila" e "Número" do "Salvar como treino padrão" (tela de lançar treino e ficha do aluno): o professor pode
// colocar o treino padrão numa fila (Homem, Mulher...) com um número (Treino 1, 2, 3...). Ao escolher a fila, o app escreve
// o próximo número livre e lembra quais já existem. Quem confere de verdade é o servidor (app/filas.py).
import { descreverUsados, lerUsados, proximoNumeroLivre } from "./filas_modelo.js";

// select: a lista de filas (opção vazia = "Sem fila"; cada opção traz data-usados="1,2,4"); campoNumero: o número;
// dica: onde escrever os números que já existem.
export function ligarSeletorDeFila({ select, campoNumero, dica }) {
  let sugerido = ""; // o número que o app escreveu sozinho: se o professor não mexeu nele, ele acompanha a fila escolhida

  const usados = () => lerUsados(select.selectedOptions[0]?.dataset.usados ?? "");

  function atualizar() {
    if (!select.value) {
      if (campoNumero.value === sugerido) campoNumero.value = "";
      sugerido = "";
      campoNumero.disabled = true; // sem fila não há número
      dica.textContent = "";
      return;
    }
    campoNumero.disabled = false;
    if (campoNumero.value === "" || campoNumero.value === sugerido) {
      const proximo = proximoNumeroLivre(usados());
      sugerido = proximo === null ? "" : String(proximo);
      campoNumero.value = sugerido;
    }
    dica.textContent = descreverUsados(usados());
  }

  // Depois de guardar com sucesso: o número passa a estar usado e o campo sugere o seguinte.
  function registrarUsado(numero) {
    const opcao = select.selectedOptions[0];
    if (!opcao || !select.value) return;
    opcao.dataset.usados = [...new Set([...usados(), numero])].join(",");
    campoNumero.value = "";
    sugerido = "";
    atualizar();
  }

  // Só deixa algarismos no número (o servidor confere de novo).
  campoNumero.addEventListener("input", () => {
    const limpo = campoNumero.value.replace(/[^0-9]/g, "").slice(0, 2);
    if (limpo !== campoNumero.value) campoNumero.value = limpo;
  });
  select.addEventListener("change", atualizar);
  atualizar();
  return { atualizar, registrarUsado };
}
