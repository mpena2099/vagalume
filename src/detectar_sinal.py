import sqlite3
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config import (AMP_RUIDO_MIN, BLS_FLATTEN_D, BLS_SNR_MIN, LS_FLATTEN_D, LS_FAP_MAX, N_CICLOS_MIN,
                    PERIODOS_SISTEMATICOS_D, ROOT, SINAIS_WORKERS, SISTEMATICO_TOL_REL,
                    SQLITE_PATH)
from src.curvas import baixar_curva
from src.periodo import medir_periodo_bls, medir_periodo_ls

FIG_PATH = ROOT / "data" / "figuras" / "fase4_sinais.png"


def _arrays(lc):
    tempo = np.asarray(lc.time.value, dtype=float)
    fluxo = np.ma.filled(np.ma.asarray(lc.flux.value, dtype=float), np.nan)
    ok = np.isfinite(tempo) & np.isfinite(fluxo)
    return tempo[ok], fluxo[ok]


def _flatten(lc, dias: float):
    n = int(dias / float(np.median(np.diff(lc.time.value))))
    return lc.flatten(window_length=n + 1 if n % 2 == 0 else n)


def avaliar_sinal(metodo: str, periodo_d: float, amplitude: float, estatistica: float,
                  duracao_d: float, ruido_ptp: float) -> str | None:
    """Devolve o motivo da rejeicao, ou None se passou em todos os cortes."""
    if metodo == "ls" and not estatistica < LS_FAP_MAX:
        return "fap"
    if metodo == "bls" and not estatistica >= BLS_SNR_MIN:
        return "snr"
    if duracao_d / periodo_d < N_CICLOS_MIN:
        return "ciclos"
    for p in PERIODOS_SISTEMATICOS_D:
        if abs(periodo_d / p - 1) < SISTEMATICO_TOL_REL:
            return "sistematico"
    if amplitude < AMP_RUIDO_MIN * ruido_ptp:
        return "amplitude"
    return None


def _uma(tic: int, setor: int, autor: str, duracao_d: float, ruido_ptp: float) -> list[dict]:
    base = {"tic": tic, "setor": setor, "ruido_ptp": ruido_ptp}
    try:
        lc, _ = baixar_curva(tic, setor, autor)
        ls = medir_periodo_ls(*_arrays(_flatten(lc, LS_FLATTEN_D)))
        tempo, fluxo = _arrays(_flatten(lc, BLS_FLATTEN_D))
        bls = medir_periodo_bls(tempo, fluxo, dy=np.full(tempo.size, ruido_ptp))
    except Exception as e:
        return [{**base, "metodo": "erro", "motivo": str(e)[:200], "sinal": False}]

    linhas = [
        {**base, "metodo": "ls", "periodo_d": ls["periodo_d"], "amplitude": ls["amplitude_pp"],
         "potencia": ls["potencia"], "fap": ls["fap"],
         "motivo": avaliar_sinal("ls", ls["periodo_d"], ls["amplitude_pp"], ls["fap"],
                                 duracao_d, ruido_ptp)},
        {**base, "metodo": "bls", "periodo_d": bls["periodo_d"], "amplitude": bls["profundidade"],
         "snr": bls["snr"], "duracao_eclipse_d": bls["duracao_d"],
         "motivo": avaliar_sinal("bls", bls["periodo_d"], bls["profundidade"], bls["snr"],
                                 duracao_d, ruido_ptp)},
    ]
    for l in linhas:
        l["n_ciclos"] = duracao_d / l["periodo_d"]
        l["sinal"] = l["motivo"] is None
    return linhas


def _figura(df: pd.DataFrame, curvas: pd.DataFrame, n: int = 12):
    top = df[df["sinal"]].assign(forca=lambda d: d["amplitude"] / d["ruido_ptp"])
    top = top.sort_values("forca", ascending=False).drop_duplicates("tic").head(n)
    if top.empty:
        return
    FIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig, eixos = plt.subplots(3, 4, figsize=(14, 9))
    autores = curvas.set_index("tic")["autor"]
    for ax, s in zip(eixos.flat, top.itertuples()):
        lc, _ = baixar_curva(int(s.tic), int(s.setor), autores[s.tic])
        tempo, fluxo = _arrays(_flatten(lc, LS_FLATTEN_D))
        epoca = tempo[np.argmin(fluxo)]
        fase = ((tempo - epoca) / s.periodo_d + 0.25) % 1 - 0.25
        ax.plot(fase, fluxo, ".", ms=1, color="tab:orange")
        ax.set_title(f"TIC {s.tic} {s.metodo.upper()} P={s.periodo_d:.4f} d", fontsize=9)
    for ax in eixos.flat[len(top):]:
        ax.axis("off")
    fig.supxlabel("Fase")
    fig.supylabel("Fluxo normalizado")
    fig.tight_layout()
    fig.savefig(FIG_PATH, dpi=120)
    plt.close(fig)
    print(f"  Figura dos {len(top)} sinais mais fortes em {FIG_PATH}")


def run():
    with sqlite3.connect(SQLITE_PATH) as con:
        curvas = pd.read_sql("SELECT * FROM curvas WHERE status = 'ok'", con)
    print(f"  {len(curvas)} curvas, {SINAIS_WORKERS} processos")

    linhas = []
    with ProcessPoolExecutor(SINAIS_WORKERS) as ex:
        futuros = [ex.submit(_uma, int(c.tic), int(c.setor), c.autor, c.duracao_d, c.ruido_ptp)
                   for c in curvas.itertuples()]
        for i, f in enumerate(as_completed(futuros), 1):
            linhas.extend(f.result())
            if i % 50 == 0 or i == len(futuros):
                print(f"  {i}/{len(futuros)}")

    df = pd.DataFrame(linhas).sort_values(["tic", "metodo"]).reset_index(drop=True)
    print(f"  Motivos de rejeicao: {df['motivo'].value_counts().to_dict()}")
    for metodo in ("ls", "bls"):
        print(f"  Sinais {metodo.upper()}: {int(df[(df['metodo'] == metodo) & df['sinal']].shape[0])}")
    print(f"  Estrelas com pelo menos um sinal: {df[df['sinal']]['tic'].nunique()}")

    with sqlite3.connect(SQLITE_PATH) as con:
        df.to_sql("sinais", con, if_exists="replace", index=False)
    print(f"  Tabela 'sinais' gravada em {SQLITE_PATH}")
    _figura(df, curvas)


if __name__ == "__main__":
    run()
