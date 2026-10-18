import numpy as np
from astropy.timeseries import BoxLeastSquares, LombScargle

from config import BLS_DURACOES_D, PERIODO_MAX_D, PERIODO_MIN_D


def medir_periodo_ls(tempo, fluxo) -> dict:
    ls = LombScargle(tempo, fluxo)
    freq, potencia = ls.autopower(
        minimum_frequency=1 / PERIODO_MAX_D,
        maximum_frequency=1 / PERIODO_MIN_D,
        samples_per_peak=10,
    )
    i = int(np.argmax(potencia))
    # Refina em volta do pico: a grade grossa erra ~1% em 27 dias de dados
    passo = freq[1] - freq[0]
    fino = np.linspace(freq[i] - 2 * passo, freq[i] + 2 * passo, 2001)
    potencia_fina = ls.power(fino)
    j = int(np.argmax(potencia_fina))
    _, a, b = ls.model_parameters(fino[j])
    return {
        "periodo_d": float(1 / fino[j]),
        "amplitude_pp": float(2 * np.hypot(a, b)),
        "potencia": float(potencia_fina[j]),
        "fap": float(ls.false_alarm_probability(potencia_fina[j])),
    }


def medir_periodo_bls(tempo, fluxo, dy=None) -> dict:
    baseline = float(np.max(tempo) - np.min(tempo))
    duracoes = [d for d in BLS_DURACOES_D if d < PERIODO_MIN_D]
    bls = BoxLeastSquares(tempo, fluxo, dy=dy)
    periodos = bls.autoperiod(
        duracoes,
        minimum_period=PERIODO_MIN_D,
        maximum_period=min(PERIODO_MAX_D, baseline / 2),
        frequency_factor=0.5,
    )
    r = bls.power(periodos, duracoes, objective="snr")
    i = int(np.argmax(r.power))
    fino = np.linspace(r.period[i] * 0.995, r.period[i] * 1.005, 2001)
    r = bls.power(fino, duracoes, objective="snr")
    i = int(np.argmax(r.power))
    return {
        "periodo_d": float(r.period[i]),
        "profundidade": float(r.depth[i]),
        "duracao_d": float(r.duration[i]),
        "snr": float(r.depth_snr[i]),
    }


def comparar_periodo(medido: float, ref: float, tol_rel: float):
    for razao in (1.0, 0.5, 2.0):
        if abs(medido / ref - razao) <= tol_rel * razao:
            return True, razao
    return False, None
