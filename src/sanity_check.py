import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from config import IMG_DIR, SANITY_TARGETS
from src.curvas import baixar_curva
from src.periodo import comparar_periodo, medir_periodo_bls, medir_periodo_ls


def _arrays(lc):
    tempo = np.asarray(lc.time.value, dtype=float)
    fluxo = np.asarray(lc.flux.value.filled(np.nan) if hasattr(lc.flux.value, "filled")
                       else lc.flux.value, dtype=float)
    ok = np.isfinite(tempo) & np.isfinite(fluxo)
    return tempo[ok], fluxo[ok]


def _janela_flatten(lc, dias: float = 1.5) -> int:
    cadencia = float(np.median(np.diff(lc.time.value)))
    n = int(dias / cadencia)
    return n + 1 if n % 2 == 0 else n


def _salvar_figura(nome, tic, tempo, fluxo, periodo):
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    epoca = tempo[np.argmin(fluxo)]
    fase = ((tempo - epoca) / periodo + 0.5) % 1 - 0.5

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 6))
    a1.plot(tempo, fluxo, ".", ms=1.5, color="0.3")
    a1.set_xlabel("Tempo (BTJD, dias)")
    a1.set_ylabel("Fluxo normalizado")
    a2.plot(fase, fluxo, ".", ms=1.5, color="tab:orange")
    a2.set_xlabel("Fase")
    a2.set_ylabel("Fluxo normalizado")
    fig.suptitle(f"TIC {tic}, P = {periodo:.5f} d")
    fig.tight_layout()
    caminho = IMG_DIR / "curva_binaria_eclipsante.png"
    fig.savefig(caminho, dpi=150)
    plt.close(fig)
    print(f"  Figura salva em {caminho}")


def check_target(nome: str, params: dict) -> bool:
    lc, meta = baixar_curva(params["tic"])
    bruto_t, bruto_f = _arrays(lc)
    if params["metodo"] == "bls":
        tempo, fluxo = _arrays(lc.flatten(window_length=_janela_flatten(lc)))
        medido = medir_periodo_bls(tempo, fluxo)["periodo_d"]
    else:
        medido = medir_periodo_ls(bruto_t, bruto_f)["periodo_d"]

    ok, razao = comparar_periodo(medido, params["periodo_ref_d"], params["tolerancia_rel"])
    status = "OK" if ok else "FALHA"
    print(f"  {status} {nome}: medido {medido:.6f} d, ref {params['periodo_ref_d']:.6f} d, "
          f"razao {razao}, {meta['autor']} setor {meta['setor']}, {meta['n_pontos']} pontos")
    if ok and params["figura"]:
        _salvar_figura(nome, params["tic"], bruto_t, bruto_f, params["periodo_ref_d"])
    return ok


def run():
    print("=" * 50)
    print("Fase 1 — Teste de sanidade")
    print("=" * 50)

    falhas = []
    for nome, params in SANITY_TARGETS.items():
        print(f"\n[{nome}] TIC {params['tic']} ({params['metodo']})")
        try:
            if not check_target(nome, params):
                falhas.append(nome)
        except Exception as e:
            print(f"  FALHA {nome}: {e}")
            falhas.append(nome)

    print()
    if falhas:
        print(f"Sanity check falhou: {', '.join(falhas)}")
        sys.exit(1)
    print("Sanity check OK")


if __name__ == "__main__":
    run()
