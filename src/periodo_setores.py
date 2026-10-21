"""Periodo juntando todos os setores do TESS de uma estrela.

Um setor so nao separa 2P de 4P: eclipses fundos de uma binaria de 21 d caem uma vez por
setor de 27 d, e o periodo medido dentro do setor pode ser um harmonico. Os instantes dos
minimos fundos em setores diferentes (separados por centenas de dias) fecham o periodo.
Funcoes puras: recebem listas de (tempo, fluxo) ja achatadas e nao tocam em disco nem rede.
"""

import numpy as np
from astropy.timeseries import LombScargle
from scipy.optimize import curve_fit

ALERTA_UM_SETOR = "periodo medido em um so setor"
# separacao que divide grupos de pontos em eclipse (e o mesmo criterio da duracao dos eventos)
SEPARACAO_D = 0.5
JANELA_MINIMO_D = 0.3
TOL_ALINHAMENTO_D = 0.02
TOL_DADO_D = 0.05
PASSO_P_D = 2e-4
LIMITE_OC_MIN = 10.0


def _gaussiana(x, a, mu, sigma):
    return 1 - a * np.exp(-(x - mu) ** 2 / (2 * sigma ** 2))


def eventos_eclipses(tempo, fluxo) -> list[dict]:
    """Minimos de uma curva: grupos abaixo de 1 - 0,3*profundidade_max, instante por
    gaussiana em +-0,3 d. So entram eventos com dado dos dois lados do minimo (um evento
    cortado pela borda do setor nao tem o centro medido)."""
    tempo = np.asarray(tempo, dtype=float)
    fluxo = np.asarray(fluxo, dtype=float)
    prof_max = 1 - np.nanmin(fluxo)
    idx = np.flatnonzero(fluxo < 1 - 0.3 * prof_max)
    if not idx.size:
        return []
    grupos = np.split(idx, np.flatnonzero(np.diff(tempo[idx]) > SEPARACAO_D) + 1)
    eventos = []
    for g in grupos:
        i = g[np.argmin(fluxo[g])]
        tm = float(tempo[i])
        janela = (tempo > tm - JANELA_MINIMO_D) & (tempo < tm + JANELA_MINIMO_D)
        tw, fw = tempo[janela], fluxo[janela]
        if not (np.any(tw < tm) and np.any(tw > tm)):
            continue
        try:
            p, cov = curve_fit(_gaussiana, tw, fw, p0=[1 - np.nanmin(fw), tm, 0.1],
                               bounds=([0, tw.min(), 1e-4], [1, tw.max(), SEPARACAO_D]),
                               maxfev=10000)
            t_min, prof, erro = float(p[1]), float(p[0]), float(np.sqrt(cov[1, 1]))
        except (RuntimeError, ValueError):
            t_min, prof, erro = tm, float(1 - np.nanmin(fw)), np.nan
        eventos.append({"t": t_min, "prof": prof, "erro": erro})
    return eventos


def _refinar(tempos, erros, p_ini) -> tuple[float, float, float, np.ndarray]:
    """Minimos quadrados ponderados de t = epoca + n*P; devolve P, erro de P, epoca e O-C
    em minutos."""
    tempos = np.asarray(tempos, dtype=float)
    n = np.round((tempos - tempos[0]) / p_ini)
    erros = np.asarray(erros, dtype=float)
    if not np.any(np.isfinite(erros) & (erros > 0)):
        erros = np.full(tempos.size, 0.01)
    erros = np.where(np.isfinite(erros) & (erros > 0), erros, np.nanmedian(erros[np.isfinite(erros)]))
    a = np.column_stack([np.ones_like(n), n])
    pesos = 1 / erros ** 2
    cov = np.linalg.inv(a.T @ (pesos[:, None] * a))
    b = cov @ (a.T @ (pesos * tempos))
    oc = (tempos - (b[0] + n * b[1])) * 1440
    return float(b[1]), float(np.sqrt(cov[1, 1])), float(b[0]), oc


def _fase_secundario(rasos, epoca, periodo) -> float:
    if not rasos:
        return np.nan
    return float(np.median([(e["t"] - epoca) / periodo % 1 for e in rasos]))


def _periodo_eclipse(curvas, p_um_setor) -> dict:
    eventos = []
    for i, (tempo, fluxo) in enumerate(curvas):
        for e in eventos_eclipses(tempo, fluxo):
            eventos.append({**e, "setor": i})
    if not eventos:
        return {"periodo_d": p_um_setor, "periodo_erro_d": np.nan, "epoca": np.nan,
                "fase_secundario": np.nan, "alerta_periodo": ALERTA_UM_SETOR,
                "metodo": "eclipse"}
    fundos = [e for e in eventos if e["prof"] > 0.6 * max(e["prof"] for e in eventos)]
    setores = {e["setor"] for e in fundos}
    if len(setores) < 2:
        epoca = min((e["t"] for e in fundos), default=np.nan)
        return {"periodo_d": p_um_setor, "periodo_erro_d": np.nan, "epoca": epoca,
                "fase_secundario": np.nan, "alerta_periodo": ALERTA_UM_SETOR,
                "metodo": "eclipse"}

    fundos.sort(key=lambda e: e["t"])
    t_fund = np.array([e["t"] for e in fundos])
    erros = np.array([e["erro"] for e in fundos])
    tempo = np.sort(np.concatenate([np.asarray(t, dtype=float) for t, _ in curvas]))

    # todos os P que alinham os minimos fundos, e entre eles o maior que nao inventa
    # eclipses em instantes com dado (P/2 preve eclipses onde a curva e plana)
    grade = np.arange(0.3 * p_um_setor, 3 * p_um_setor, PASSO_P_D)
    r = (t_fund[None, :] - t_fund[0] + grade[:, None] / 2) % grade[:, None] - grade[:, None] / 2
    candidatos = grade[np.all(np.abs(r) < TOL_ALINHAMENTO_D, axis=1)]
    melhores = []
    for p in candidatos:
        n = np.arange(np.floor((tempo[0] - t_fund[0]) / p) - 1,
                      np.ceil((tempo[-1] - t_fund[0]) / p) + 2)
        previsto = t_fund[0] + n * p
        j = np.clip(np.searchsorted(tempo, previsto), 1, tempo.size - 1)
        perto = np.minimum(np.abs(tempo[j] - previsto), np.abs(tempo[j - 1] - previsto))
        if int(np.sum(perto < TOL_DADO_D)) == t_fund.size:
            melhores.append(p)

    alerta = ""
    if melhores:
        p_ini = float(max(melhores))
    else:
        p_ini = float(p_um_setor)
        alerta = "periodos dos setores nao alinham: conferir a figura"
    periodo, erro, epoca, oc = _refinar(t_fund, erros, p_ini)
    if np.any(np.abs(oc) > LIMITE_OC_MIN) and not alerta:
        alerta = "algum O-C passa de 10 min: conferir a figura"
    profundidade = max(e["prof"] for e in eventos)
    rasos = [e for e in eventos if e["prof"] <= 0.6 * profundidade]
    return {"periodo_d": periodo, "periodo_erro_d": erro, "epoca": epoca,
            "fase_secundario": _fase_secundario(rasos, epoca, periodo),
            "alerta_periodo": alerta, "metodo": "eclipse"}


def _periodo_ls(curvas, p_um_setor) -> dict:
    """Pulsante/rotacao: LS com os setores juntos e grade fina em torno de 1/P (+-3%)."""
    tempo = np.concatenate([np.asarray(t, dtype=float) for t, _ in curvas])
    fluxo = np.concatenate([np.asarray(f, dtype=float) for _, f in curvas])
    f0 = 1 / p_um_setor
    freq = np.linspace(0.97 * f0, 1.03 * f0, 2001)
    pico = freq[int(np.argmax(LombScargle(tempo, fluxo).power(freq)))]
    periodo = float(1 / pico)
    alerta = ("pico a mais de 1% do periodo de um setor: conferir a figura"
              if abs(periodo / p_um_setor - 1) > 0.01 else "")
    return {"periodo_d": periodo, "periodo_erro_d": np.nan, "epoca": np.nan,
            "fase_secundario": np.nan, "alerta_periodo": alerta, "metodo": "ls"}


def medir_periodo_setores(curvas, p_um_setor: float, eclipse: bool) -> dict:
    """Periodo com todos os setores. `curvas` e uma lista de (tempo, fluxo) por setor,
    `p_um_setor` o periodo sugerido no setor da candidata."""
    if not curvas:
        raise ValueError("sem curvas para medir o periodo")
    return _periodo_eclipse(curvas, p_um_setor) if eclipse else _periodo_ls(curvas, p_um_setor)
