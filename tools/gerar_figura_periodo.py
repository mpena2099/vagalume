"""Figura didatica do guia: a mesma curva dobrada em P e em 2P, com ciclos alternados em cores.

Curvas simuladas (so ilustracao, nao e caso do treino): uma binaria eclipsante em que o
programa acha metade do periodo e uma pulsante em que P ja e o certo. Pintar os ciclos
de P alternando laranja e azul mostra de onde vem cada vale.

    python tools/gerar_figura_periodo.py    # grava docs/img/p_vs_2p.png
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from config import IMG_DIR

P = 1.0  # o periodo que o programa achou (dias)
LARANJA, AZUL = "#E8743B", "#3B7DD8"


def _binaria(t):
    """Orbita de 2P: eclipse fundo (30%) em fase 0 e raso (10%) em fase 0,5."""
    fase = (t / (2 * P)) % 1
    largura = 0.025
    fundo = 0.30 * np.exp(-0.5 * (np.minimum(fase, 1 - fase) / largura) ** 2)
    raso = 0.10 * np.exp(-0.5 * ((fase - 0.5) / largura) ** 2)
    return 1 - fundo - raso


def _pulsante(t):
    return 1 - 0.08 * np.cos(2 * np.pi * t / P)


def _painel(ax, t, fluxo, periodo, titulo):
    # desloca fase e contagem de ciclos juntas: o vale nao cai cortado na borda nem
    # fica metade de cada cor
    ciclo_par = (np.floor(t / P + 0.25) % 2) == 0
    fase = (t / periodo + 0.25) % 1
    for mascara, cor, rotulo in ((ciclo_par, LARANJA, "ciclos 1, 3, 5..."),
                                 (~ciclo_par, AZUL, "ciclos 2, 4, 6...")):
        ax.plot(fase[mascara], fluxo[mascara], ".", ms=2.5, color=cor, label=rotulo)
    ax.set_title(titulo, fontsize=10)
    ax.set_xlabel("fase")
    ax.set_xlim(0, 1)


def main():
    rng = np.random.default_rng(1)
    t = np.sort(rng.uniform(0, 26, 5000))
    ruido = rng.normal(0, 0.006, t.size)
    fig, eixos = plt.subplots(2, 2, figsize=(10, 6.4), sharey="row")
    for linha, (nome, f, certo) in enumerate((("Binária", _binaria, "2P"),
                                              ("Pulsante", _pulsante, "P"))):
        fluxo = f(t) + ruido
        _painel(eixos[linha, 0], t, fluxo, P,
                f"{nome}: dobrada em P\n" + ("os dois vales caem no mesmo lugar" if certo == "2P"
                                              else "laranja e azul fazem o mesmo desenho"))
        _painel(eixos[linha, 1], t, fluxo, 2 * P,
                f"{nome}: dobrada em 2P\n" + ("vale fundo e vale raso separados: período 2P"
                                               if certo == "2P"
                                               else "a mesma onda duas vezes: período P"))
        eixos[linha, 0].set_ylabel("brilho relativo")
    eixos[0, 0].legend(loc="lower left", fontsize=8, markerscale=3)
    fig.tight_layout()
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    saida = IMG_DIR / "p_vs_2p.png"
    fig.savefig(saida, dpi=110)
    print(f"  {saida}")


if __name__ == "__main__":
    main()
