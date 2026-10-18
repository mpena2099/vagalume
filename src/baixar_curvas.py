import sqlite3
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from config import CURVAS_WORKERS, SQLITE_PATH
from src.curvas import baixar_curva


def resumir_curva(tempo: np.ndarray, fluxo: np.ndarray) -> dict:
    ok = np.isfinite(tempo) & np.isfinite(fluxo)
    tempo, fluxo = tempo[ok], fluxo[ok]
    # desvio ponto a ponto robusto (MAD das diferencas sucessivas)
    ruido = 1.4826 * np.median(np.abs(np.diff(fluxo))) / np.sqrt(2)
    return {
        "n_pontos": int(tempo.size),
        "duracao_d": float(tempo.max() - tempo.min()),
        "cadencia_min": float(np.median(np.diff(tempo)) * 1440),
        "ruido_ptp": float(ruido),
        "desvio": float(np.std(fluxo)),
    }


def _uma(tic: int, setor: int, autor: str) -> dict:
    linha = {"tic": tic, "setor": setor, "autor": autor}
    try:
        lc, meta = baixar_curva(linha["tic"], linha["setor"], linha["autor"])
        tempo = np.asarray(lc.time.value, dtype=float)
        fluxo = np.ma.filled(np.ma.asarray(lc.flux.value, dtype=float), np.nan)
        linha.update(resumir_curva(tempo, fluxo), caminho=meta["caminho"], status="ok", erro=None)
    except Exception as e:
        linha.update(status="erro", erro=str(e)[:200])
    return linha


def run():
    with sqlite3.connect(SQLITE_PATH) as con:
        alvos = pd.read_sql("SELECT tic, setor, autor FROM alvos", con)
    print(f"  {len(alvos)} alvos, {CURVAS_WORKERS} downloads em paralelo")

    linhas = []
    # processos, nao threads: o lightkurve troca sys.stdout global durante o download
    with ProcessPoolExecutor(CURVAS_WORKERS) as ex:
        futuros = [ex.submit(_uma, int(a.tic), int(a.setor), a.autor) for a in alvos.itertuples()]
        for i, f in enumerate(as_completed(futuros), 1):
            linhas.append(f.result())
            if i % 25 == 0 or i == len(futuros):
                erros = sum(l["status"] == "erro" for l in linhas)
                print(f"  {i}/{len(futuros)} ({erros} erros)")

    df = pd.DataFrame(linhas).sort_values("tic").reset_index(drop=True)
    ok = df[df["status"] == "ok"]
    print(f"  {len(ok)} curvas ok, {len(df) - len(ok)} com erro")
    if len(ok):
        print(f"  Pontos (mediana) {ok['n_pontos'].median():.0f}, cadencia {ok['cadencia_min'].median():.1f} min, "
              f"ruido ponto a ponto (mediana) {ok['ruido_ptp'].median() * 1e3:.2f} ppt")
    for erro, n in df["erro"].value_counts().head(5).items():
        print(f"  erro x{n}: {erro}")

    with sqlite3.connect(SQLITE_PATH) as con:
        df.to_sql("curvas", con, if_exists="replace", index=False)
    print(f"  Tabela 'curvas' gravada em {SQLITE_PATH}")


if __name__ == "__main__":
    run()
