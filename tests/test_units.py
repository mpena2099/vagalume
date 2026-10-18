import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from src.periodo import comparar_periodo, medir_periodo_bls, medir_periodo_ls
from src.selecionar_alvos import filtrar_alvos

RNG = np.random.default_rng(42)
TEMPO = np.arange(0, 27, 30 / 1440)


def test_ls_senoide():
    fluxo = 1 + 0.01 * np.sin(2 * np.pi * TEMPO / 2.3) + RNG.normal(0, 0.001, TEMPO.size)
    medido = medir_periodo_ls(TEMPO, fluxo)["periodo_d"]
    assert abs(medido / 2.3 - 1) < 0.001, medido


def test_bls_caixa():
    fase = (TEMPO % 1.7) / 1.7
    fluxo = 1 - 0.01 * (fase < 0.1 / 1.7) + RNG.normal(0, 0.001, TEMPO.size)
    medido = medir_periodo_bls(TEMPO, fluxo)["periodo_d"]
    ok, razao = comparar_periodo(medido, 1.7, 0.001)
    assert ok, (medido, razao)


def test_comparar_periodo():
    assert comparar_periodo(1.0, 1.0, 0.001) == (True, 1.0)
    assert comparar_periodo(2.0, 1.0, 0.001) == (True, 2.0)
    assert comparar_periodo(0.5, 1.0, 0.001) == (True, 0.5)
    assert comparar_periodo(1.5, 1.0, 0.001) == (False, None)
    assert comparar_periodo(1.01, 1.0, 0.001) == (False, None)



def test_filtrar_alvos():
    tic = pd.DataFrame({
        "ID": [1, 2, 3, 4, 5],
        "ra": [0.0] * 5, "dec": [0.0] * 5,
        "Tmag": [10.0, 8.0, 12.0, 11.0, 13.0],
        "contratio": [0.1, 0.1, 0.5, np.nan, 0.05],
    })
    obs = pd.DataFrame({
        "target_name": ["1", "1", "2", "5", "5", "TESS FFI"],
        "provenance_name": ["TESS-SPOC", "QLP", "QLP", "QLP", "QLP", "TESS-SPOC"],
        "sequence_number": [55, 55, 55, 54, 55, 55],
    })
    df = filtrar_alvos(tic, obs, 55)
    assert df["tic"].tolist() == [1, 5], df
    assert df["autor"].tolist() == ["QLP", "QLP"]


if __name__ == "__main__":
    for nome, fn in list(globals().items()):
        if nome.startswith("test_"):
            fn()
            print(f"OK {nome}")
