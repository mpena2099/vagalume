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


OC_LIMITE_FASE = 0.02


def instante_minimo(tempo, fluxo, periodo: float, harmonicos: int,
                    epoca: float | None = None) -> tuple[float, float]:
    """Instante do minimo mais perto do meio do setor e seu erro (d). Ajusta uma serie de
    Fourier de `harmonicos` termos em `periodo`; o erro vem de 30 reamostragens com semente
    fixa. Com `epoca` (um minimo conhecido, mesma escala de `tempo`) so vale o minimo a menos de
    0,25 em fase do previsto por ela: numa binaria de minimos parecidos o mais fundo de cada
    setor pode ser o secundario."""
    tempo = np.asarray(tempo, dtype=float)
    fluxo = np.asarray(fluxo, dtype=float)
    meio = float(tempo.mean())
    fase_grade = np.linspace(-0.5, 0.5, 2001)
    if epoca is not None:
        previsto = ((epoca - meio) / periodo + 0.5) % 1 - 0.5
        valida = np.abs((fase_grade - previsto + 0.5) % 1 - 0.5) <= 0.25
    else:
        valida = np.ones(fase_grade.size, dtype=bool)

    def base(x):
        cols = [np.ones_like(x)]
        for k in range(1, harmonicos + 1):
            cols += [np.cos(2 * np.pi * k * x), np.sin(2 * np.pi * k * x)]
        return np.column_stack(cols)

    def minimo(t, f):
        coef, *_ = np.linalg.lstsq(base((t - meio) / periodo), f, rcond=None)
        modelo = np.where(valida, base(fase_grade) @ coef, np.inf)
        return meio + fase_grade[int(np.argmin(modelo))] * periodo

    t_min = minimo(tempo, fluxo)
    rng = np.random.default_rng(0)
    amostras = []
    for _ in range(30):
        i = rng.integers(0, tempo.size, tempo.size)
        amostras.append(minimo(tempo[i], fluxo[i]) - t_min)
    # mediana-MAD: uma reamostragem que cai no outro minimo nao estoura o erro
    mad = np.median(np.abs(np.array(amostras) - np.median(amostras)))
    return float(t_min), float(max(1.4826 * mad, periodo / 2000))


def oc_setores(curvas, periodo: float, eclipse: bool, rotulos=None, epoca=None) -> dict:
    """O-C do instante de minimo em cada setor contra T = T0 + n*P, juntando os setores.

    `curvas`: lista de (tempo, fluxo) por setor, ja achatadas. Com 3 setores ou mais o ajuste
    linear tem P livre e `oc_max_fase` e o maior residuo dele; com 2 setores nao ha residuo
    (a reta passa pelos dois pontos), entao o P fica o da ficha e o residuo e o desencontro
    dos dois minimos. `setores` segue a ordem do tempo, como `oc_fase`. `alinhado` = `oc_max_fase` < OC_LIMITE_FASE. Um setor so: `alinhado`
    None (nada a conferir). O periodo refinado so existe se alinhado. `epoca`: ver `instante_minimo`."""
    rotulos = list(rotulos) if rotulos is not None else list(range(len(curvas)))
    manter = [i for i, (t, _) in enumerate(curvas) if len(t) > 20]
    rotulos = [rotulos[i] for i in manter]
    curvas = [curvas[i] for i in manter]
    vazio = {"alinhado": None, "oc_fase": [], "setores": [], "oc_max_fase": np.nan, "periodo_d": periodo,
             "periodo_erro_d": np.nan, "epoca": np.nan}
    if len(curvas) < 2:
        return vazio
    harm = 8 if eclipse else 2
    medidas = sorted((*instante_minimo(t, f, periodo, harm, epoca), r)
                     for (t, f), r in zip(curvas, rotulos))
    tempos = np.array([m[0] for m in medidas])
    erros = np.array([m[1] for m in medidas])
    n = np.round((tempos - tempos[0]) / periodo)
    pesos = 1 / erros ** 2
    if len(tempos) >= 3:
        a = np.column_stack([np.ones_like(n), n])
        cov = np.linalg.inv(a.T @ (pesos[:, None] * a))
        b = cov @ (a.T @ (pesos * tempos))
        resid = tempos - a @ b
        qui2 = float(np.sum(pesos * resid ** 2)) / (len(tempos) - 2)
        p_ref, erro_p, t0 = float(b[1]), float(np.sqrt(cov[1, 1] * max(qui2, 1.0))), float(b[0])
    else:
        t0 = float(np.sum(pesos * (tempos - n * periodo)) / np.sum(pesos))
        resid = tempos - (t0 + n * periodo)
        p_ref = float((tempos[1] - tempos[0]) / n[1]) if n[1] else periodo
        erro_p = float(np.hypot(erros[0], erros[1]) / n[1]) if n[1] else np.nan
    oc_fase = resid / periodo
    maximo = float(np.max(np.abs(oc_fase)))
    alinhado = maximo < OC_LIMITE_FASE
    meio = float(np.mean([np.mean(t) for t, _ in curvas]))
    saida = {**vazio, "setores": [m[2] for m in medidas], "alinhado": bool(alinhado), "oc_fase": [float(x) for x in oc_fase],
             "oc_max_fase": maximo}
    if alinhado:
        saida.update(periodo_d=p_ref, periodo_erro_d=erro_p,
                     epoca=t0 + round((meio - t0) / p_ref) * p_ref)
    return saida


PAR_IMPAR_SIGMA_MIN = 3.0
PAR_IMPAR_MIN_PONTOS = 8
PAR_IMPAR_MIN_ECLIPSES = 3
PAR_IMPAR_BINS = 400


def _fase_centrada(tempo, periodo: float, epoca: float) -> np.ndarray:
    return ((np.asarray(tempo, dtype=float) - epoca) / periodo + 0.5) % 1 - 0.5


def largura_eclipse(tempo, fluxo, periodo: float, epoca: float,
                    n_bins: int = PAR_IMPAR_BINS) -> float:
    """Largura total a meia profundidade (FWHM, em fase) do eclipse em fase 0 da curva dobrada.
    Mediana por bin; a profundidade e medida contra a mediana da curva. NaN se nao houver eclipse
    mensuravel."""
    fluxo = np.asarray(fluxo, dtype=float)
    cadencia = float(np.median(np.diff(np.sort(tempo)))) if len(tempo) > 1 else periodo
    n_bins = int(max(20, min(n_bins, periodo / (2 * cadencia))))
    fase = _fase_centrada(tempo, periodo, epoca)
    idx = np.minimum(((fase + 0.5) * n_bins).astype(int), n_bins - 1)
    med = np.full(n_bins, np.nan)
    for k in np.unique(idx):
        med[k] = np.median(fluxo[idx == k])
    prof = np.nanmedian(med) - med
    centro = n_bins // 2
    janela = np.arange(centro - n_bins // 20, centro + n_bins // 20 + 1)
    # suaviza 3 bins para o pico nao ser um ponto ruidoso
    suave = np.convolve(np.nan_to_num(prof), np.ones(3) / 3, mode="same")
    k0 = janela[int(np.argmax(suave[janela]))]
    pico = suave[k0]
    if not np.isfinite(pico) or pico <= 0:
        return np.nan
    metade = pico / 2
    esq = k0
    while esq > 0 and suave[esq - 1] >= metade:
        esq -= 1
    dir_ = k0
    while dir_ < n_bins - 1 and suave[dir_ + 1] >= metade:
        dir_ += 1
    return float(max(dir_ - esq + 1, 1) / n_bins)


def duracao_eclipse(tempo, fluxo, periodo: float, epoca: float,
                    n_bins: int = PAR_IMPAR_BINS, fracao: float = 0.1) -> float:
    """Largura total do eclipse (em fase) onde a profundidade suavizada em 3 bins fica a
    >= fracao do pico perto da fase 0. NaN se nao houver pico positivo."""
    fluxo = np.asarray(fluxo, dtype=float)
    cadencia = float(np.median(np.diff(np.sort(tempo)))) if len(tempo) > 1 else periodo
    n_bins = int(max(20, min(n_bins, periodo / (2 * cadencia))))
    fase = _fase_centrada(tempo, periodo, epoca)
    idx = np.minimum(((fase + 0.5) * n_bins).astype(int), n_bins - 1)
    med = np.full(n_bins, np.nan)
    for k in np.unique(idx):
        med[k] = np.median(fluxo[idx == k])
    prof = np.nanmedian(med) - med
    centro = n_bins // 2
    janela = np.arange(centro - n_bins // 40, centro + n_bins // 40 + 1)
    suave = np.convolve(np.nan_to_num(prof), np.ones(3) / 3, mode="same")
    k0 = janela[int(np.argmax(suave[janela]))]
    pico = suave[k0]
    if not np.isfinite(pico) or pico <= 0:
        return np.nan
    limite = fracao * pico
    esq = k0
    while esq > 0 and suave[esq - 1] >= limite:
        esq -= 1
    dir_ = k0
    while dir_ < n_bins - 1 and suave[dir_ + 1] >= limite:
        dir_ += 1
    return float(max(dir_ - esq + 1, 1) / n_bins)


def _mediana_erro(x) -> tuple[float, float]:
    return float(np.median(x)), float(1.25 * 1.4826 * np.median(np.abs(x - np.median(x)))
                                      / np.sqrt(len(x)))


def teste_par_impar(tempo, fluxo, periodo: float, epoca: float,
                    largura_fase: float | None = None) -> dict:
    """Profundidade dos eclipses de ciclo par e de ciclo impar (n = round((t - epoca)/P)).

    Dentro do eclipse: |fase| < largura_fase/4 (nucleo); fora: entre 1,5 e 3 larguras da fase 0,
    limitado a 0,45. `largura_fase` (FWHM em fase) vem da propria curva se nao for dada.
    Profundidade = mediana(fora) - mediana(dentro), por paridade; erro = 1,25*sigma/sqrt(n) da
    mediana de cada lado, sigma pelo MAD. `sigma` = (par - impar)/erro combinado, com sinal.
    Sem decisao (`decide` False) se algum lado tem menos de PAR_IMPAR_MIN_PONTOS pontos ou
    PAR_IMPAR_MIN_ECLIPSES eclipses distintos."""
    tempo = np.asarray(tempo, dtype=float)
    fluxo = np.asarray(fluxo, dtype=float)
    if largura_fase is None:
        largura_fase = largura_eclipse(tempo, fluxo, periodo, epoca)
    vazio = {"prof_par": np.nan, "prof_impar": np.nan, "erro_par": np.nan, "erro_impar": np.nan,
             "sigma": np.nan, "n_par": 0, "n_impar": 0, "largura_fase": largura_fase,
             "decide": False}
    if not np.isfinite(largura_fase) or largura_fase <= 0:
        return vazio
    fase = _fase_centrada(tempo, periodo, epoca)
    n = np.round((tempo - epoca) / periodo).astype(int)
    af = np.abs(fase)
    cadencia = float(np.median(np.diff(np.sort(tempo))))
    dentro = af < max(largura_fase / 4, 0.75 * cadencia / periodo)
    fora = (af > 1.5 * largura_fase) & (af < min(3 * largura_fase, 0.45))
    saida = dict(vazio)
    profs = {}
    for nome, par in (("par", True), ("impar", False)):
        sel = (n % 2 == 0) == par
        d, o = fluxo[dentro & sel], fluxo[fora & sel]
        saida[f"n_{nome}"] = int(d.size)
        ciclos = np.unique(n[dentro & sel]).size
        if (d.size < PAR_IMPAR_MIN_PONTOS or o.size < PAR_IMPAR_MIN_PONTOS
                or ciclos < PAR_IMPAR_MIN_ECLIPSES):
            return saida
        md, ed = _mediana_erro(d)
        mo, eo = _mediana_erro(o)
        profs[nome] = (mo - md, float(np.hypot(ed, eo)))
    if min(profs["par"][0], profs["impar"][0]) <= 0:
        # a janela nao pega eclipse de verdade (epoca ou largura fora): sem decisao
        return saida
    saida.update(prof_par=profs["par"][0], prof_impar=profs["impar"][0],
                 erro_par=profs["par"][1], erro_impar=profs["impar"][1], decide=True)
    erro = float(np.hypot(profs["par"][1], profs["impar"][1]))
    saida["sigma"] = float((profs["par"][0] - profs["impar"][0]) / erro) if erro > 0 else np.nan
    return saida


def par_impar_setores(curvas, periodo: float, epoca: float, rotulos=None) -> dict:
    """Teste par/impar em cada setor (largura medida na curva juntada) e no conjunto.

    `curvas`: lista de (tempo, fluxo) achatadas. `dobrar` = diferenca >= PAR_IMPAR_SIGMA_MIN sigmas
    no conjunto, com o mesmo sinal em todo setor que decide (e pelo menos um setor decidindo).
    `par_mais_fundo`: o par e o mais fundo (sigma > 0), para escolher a epoca do 2P."""
    rotulos = list(rotulos) if rotulos is not None else list(range(len(curvas)))
    tempo = np.concatenate([np.asarray(t, dtype=float) for t, _ in curvas])
    fluxo = np.concatenate([np.asarray(f, dtype=float) for _, f in curvas])
    largura = largura_eclipse(tempo, fluxo, periodo, epoca)
    geral = teste_par_impar(tempo, fluxo, periodo, epoca, largura)
    por_setor = {r: teste_par_impar(t, f, periodo, epoca, largura)
                 for r, (t, f) in zip(rotulos, curvas)}
    decididos = [v for v in por_setor.values() if v["decide"]]
    sinais = {np.sign(v["sigma"]) for v in decididos if np.isfinite(v["sigma"])}
    consistente = len(decididos) >= 1 and len(sinais) == 1
    sigma = geral["sigma"]
    dobrar = bool(geral["decide"] and np.isfinite(sigma) and abs(sigma) >= PAR_IMPAR_SIGMA_MIN
                  and consistente)
    return {"geral": geral, "setores": por_setor, "consistente": consistente, "dobrar": dobrar,
            "par_mais_fundo": bool(sigma > 0) if np.isfinite(sigma) else True}
