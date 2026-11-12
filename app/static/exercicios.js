// Página /exercicios: só consulta a lista (sem montar treino), com a ilustração de cada exercício (visual novo, 12/11/2026).
import { iniciarBiblioteca } from "./biblioteca.js";

const pagina = document.querySelector(".exercicios-nova");
iniciarBiblioteca(document.querySelector("[data-biblioteca]"), { pastaDasFotos: pagina?.dataset.pastaFotos });
