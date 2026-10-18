import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from src.periodo import comparar_periodo, medir_periodo_bls, medir_periodo_ls

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


if __name__ == "__main__":
    for nome, fn in list(globals().items()):
        if nome.startswith("test_"):
            fn()
            print(f"OK {nome}")
