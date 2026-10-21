import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import astropy.units as u
import lightkurve as lk
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from astropy.coordinates import SkyCoord
from astropy.timeseries import LombScargle
from astroquery.vizier import Vizier

from config import (LS_FLATTEN_D, PERIODO_MAX_D, PERIODO_MIN_D, SQLITE_PATH, TRIAGEM_DIR,
                    TRIAGEM_RECORTE_PX, VIZINHA_DMAG_MAX)
from src.curvas import baixar_curva
from src.detectar_sinal import _arrays, _flatten
from src.util import retry

PIXEL_ARCSEC = 21.0


def escolher_sinal(sinais: pd.DataFrame) -> pd.DataFrame:
    """Um sinal por estrela candidata: o de maior amplitude/ruido entre os que passaram.

    `sinais_todos` lista tambem os descartados por nao persistir, como contexto. O
    escolhido sai so dos de veredito 'candidato': antes um BLS mais forte que nao
    persistia ganhava do LS que persistia, e a figura mostrava o periodo errado.
    """
    tics = sinais.loc[sinais["veredito"] == "candidato", "tic"].unique()
    s = sinais[sinais["tic"].isin(tics) & (sinais["motivo_descarte"] != "vizinha_variavel")]
    s = s.assign(forca=s["amplitude"] / s["ruido_ptp"]).sort_values("forca", ascending=False)
    outros = s.groupby("tic").apply(
        lambda g: ", ".join(f"{m.upper()} {p:.4f} d" for m, p in zip(g["metodo"], g["periodo_d"])),
        include_groups=False).rename("sinais_todos")
    escolhidos = s[s["veredito"] == "candidato"].drop_duplicates("tic")
    return escolhidos.join(outros, on="tic").reset_index(drop=True)


def destendencia_por_orbita(tempo: np.ndarray, fluxo: np.ndarray, grau: int = 2) -> np.ndarray:
    """Divide cada trecho entre lacunas > 1 d por um polinomio (fluxo: tempo x pixels)."""
    saida = np.full_like(fluxo, np.nan)
    cortes = np.concatenate([[0], np.where(np.diff(tempo) > 1)[0] + 1, [tempo.size]])
    for a, b in zip(cortes[:-1], cortes[1:]):
        t = tempo[a:b] - tempo[a:b].mean()
        if b - a <= grau + 1:
            continue
        for j in range(fluxo.shape[1]):
            f = fluxo[a:b, j]
            ok = np.isfinite(f)
            if ok.sum() <= grau + 1:
                continue
            saida[a:b, j] = f - np.polyval(np.polyfit(t[ok], f[ok], grau), t)
    return saida


def amplitude_dobrada(tempo: np.ndarray, fluxo: np.ndarray, periodo: float,
                      n_bins: int = 25) -> np.ndarray:
    """Amplitude pico a pico da curva dobrada em bins de fase, por coluna de fluxo."""
    fase = (tempo / periodo) % 1
    idx = np.minimum((fase * n_bins).astype(int), n_bins - 1)
    medias = np.array([np.nanmedian(fluxo[idx == k], axis=0) for k in range(n_bins)])
    return np.nanmax(medias, axis=0) - np.nanmin(medias, axis=0)


def profundidade_eclipse(tempo: np.ndarray, fluxo: np.ndarray, periodo: float, epoca: float,
                         duracao: float) -> np.ndarray:
    """Fora do eclipse menos dentro (medianas), por coluna de fluxo."""
    dist = np.abs(((tempo - epoca) / periodo + 0.5) % 1 - 0.5) * periodo
    dentro = dist < duracao / 2
    fora = dist > duracao
    return np.nanmedian(fluxo[fora], axis=0) - np.nanmedian(fluxo[dentro], axis=0)


def _mapa_pixels(tic: int, setor: int, s, epoca: float, alvo: SkyCoord):
    tpf = retry(lambda: lk.search_tesscut(f"TIC {tic}", sector=setor)
                .download(cutout_size=TRIAGEM_RECORTE_PX), "TESScut")
    tpf = tpf[tpf.quality == 0]
    cubo = np.asarray(tpf.flux.value, dtype=float)
    tempo = np.asarray(tpf.time.value, dtype=float)
    ok = np.isfinite(tempo) & np.all(np.isfinite(cubo), axis=(1, 2))
    cubo, tempo = cubo[ok], tempo[ok]
    n, ny, nx = cubo.shape
    resid = destendencia_por_orbita(tempo, cubo.reshape(n, -1))
    # eclipses curtos somem na mediana por bin de fase; para BLS compara dentro x fora
    if s.metodo == "bls":
        mapa = profundidade_eclipse(tempo, resid, s.periodo_d, epoca, s.duracao_eclipse_d)
    else:
        mapa = amplitude_dobrada(tempo, resid, s.periodo_d)
    mapa = mapa.reshape(ny, nx)
    x, y = tpf.wcs.world_to_pixel(alvo)
    pico = np.unravel_index(np.nanargmax(mapa), mapa.shape)
    desloc = float(np.hypot(pico[1] - x, pico[0] - y))
    return np.nanmedian(cubo, axis=0), mapa, tpf.wcs, (float(x), float(y)), pico, desloc


def _gaia_campo(alvo: SkyCoord, tmag: float) -> pd.DataFrame:
    raio = TRIAGEM_RECORTE_PX / 2 * PIXEL_ARCSEC * 1.42
    res = retry(lambda: Vizier(columns=["Source", "RA_ICRS", "DE_ICRS", "Gmag"], row_limit=-1)
                .query_region(alvo, radius=raio * u.arcsec, catalog="I/355/gaiadr3"), "VizieR")
    if not len(res):
        return pd.DataFrame(columns=["RA_ICRS", "DE_ICRS", "Gmag"])
    t = res[0].to_pandas().dropna(subset=["Gmag"])
    return t[t["Gmag"] < tmag + 0.5 + VIZINHA_DMAG_MAX]


def _marcar_campo(ax, wcs, gaia, alvo_xy, pico):
    if len(gaia):
        gx, gy = wcs.world_to_pixel(SkyCoord(gaia["RA_ICRS"], gaia["DE_ICRS"], unit="deg"))
        ax.scatter(gx, gy, s=np.clip((17 - gaia["Gmag"]) * 12, 5, 150), facecolors="none",
                   edgecolors="cyan", lw=0.8)
    ax.plot(*alvo_xy, "+", color="lime", ms=14, mew=2)
    ax.plot(pico[1], pico[0], "x", color="red", ms=10, mew=2)
    ax.set_xlim(-0.5, TRIAGEM_RECORTE_PX - 0.5)
    ax.set_ylim(-0.5, TRIAGEM_RECORTE_PX - 0.5)


def _figura(s, tempo, fluxo, campo, mapa, wcs, gaia, alvo_xy, pico, desloc, pasta: Path,
            nome: str) -> Path:
    fig, ax = plt.subplots(2, 3, figsize=(16, 9))
    epoca = tempo[np.argmin(fluxo)]
    ax[0, 0].plot(tempo, fluxo, ".", ms=1, color="0.3")
    ax[0, 0].set(xlabel="Tempo (BTJD, dias)", ylabel="Fluxo normalizado",
                 title="Curva de luz (flatten 4 d)")
    for a, mult in ((ax[0, 1], 1), (ax[0, 2], 2)):
        p = s.periodo_d * mult
        fase = ((tempo - epoca) / p + 0.25) % 1 - 0.25
        a.plot(fase, fluxo, ".", ms=1, color="tab:orange", alpha=0.6)
        bins = np.linspace(-0.25, 0.75, 51)
        idx = np.digitize(fase, bins) - 1
        med = [np.nanmedian(fluxo[idx == k]) if np.any(idx == k) else np.nan for k in range(50)]
        a.plot((bins[:-1] + bins[1:]) / 2, med, "-", color="k", lw=1.2)
        a.set(xlabel="Fase", title=f"Dobrada em {'P' if mult == 1 else '2P'} = {p:.5f} d")

    freq = np.linspace(1 / PERIODO_MAX_D, 1 / PERIODO_MIN_D, 20000)
    ax[1, 0].plot(1 / freq, LombScargle(tempo, fluxo).power(freq), lw=0.7)
    ax[1, 0].axvline(s.periodo_d, color="tab:red", ls="--", lw=1)
    ax[1, 0].set(xscale="log", xlabel="Período (d)", ylabel="Potência LS", title="Periodograma")

    ax[1, 1].imshow(np.log10(np.clip(campo, 1, None)), origin="lower", cmap="gray")
    _marcar_campo(ax[1, 1], wcs, gaia, alvo_xy, pico)
    ax[1, 1].set_title("Campo TESS (mediana)")
    ax[1, 2].imshow(mapa, origin="lower", cmap="magma")
    _marcar_campo(ax[1, 2], wcs, gaia, alvo_xy, pico)
    ax[1, 2].set_title(f"Amplitude do sinal por pixel (pico a {desloc:.1f} px do alvo)")

    fig.suptitle(f"TIC {s.tic}  T={s.tmag:.2f}  {s.metodo.upper()} P={s.periodo_d:.5f} d  "
                 f"amp={s.amplitude * 100:.2f}%   (+ alvo, x pico do sinal, o Gaia)")
    fig.tight_layout()
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"{nome}.png"
    fig.savefig(caminho, dpi=100)
    renderer = fig.canvas.get_renderer()
    paineis = {"curva": ax[0, 0], "p": ax[0, 1], "2p": ax[0, 2],
               "periodograma": ax[1, 0], "campo": ax[1, 1], "mapa": ax[1, 2]}
    for painel, a in paineis.items():
        bbox = a.get_tightbbox(renderer).transformed(fig.dpi_scale_trans.inverted())
        fig.savefig(pasta / f"{nome}_{painel}.png", dpi=100, bbox_inches=bbox.padded(0.1))
    plt.close(fig)
    return caminho


def _triar(s, pasta: Path = TRIAGEM_DIR, nome: str | None = None) -> dict:
    """pasta/nome: o treino e as referencias gravam fora de TRIAGEM_DIR; no mesmo nome
    sobrescreviam a figura da candidata quando usavam outro sinal da mesma estrela."""
    alvo = SkyCoord(s.ra, s.dec, unit="deg")
    lc, _ = baixar_curva(int(s.tic), int(s.setor), s.autor)
    tempo, fluxo = _arrays(_flatten(lc, LS_FLATTEN_D))
    epoca = tempo[np.argmin(fluxo)]
    campo, mapa, wcs, alvo_xy, pico, desloc = _mapa_pixels(int(s.tic), int(s.setor), s, epoca,
                                                          alvo)
    gaia = _gaia_campo(alvo, s.tmag)
    caminho = _figura(s, tempo, fluxo, campo, mapa, wcs, gaia, alvo_xy, pico, desloc, pasta,
                      nome or str(s.tic))
    return {"deslocamento_px": desloc, "figura": str(caminho)}


def run():
    with sqlite3.connect(SQLITE_PATH) as con:
        # autor (QLP/SPOC) vem da Fase 6, que o leu da tabela alvos
        sinais = pd.read_sql("SELECT * FROM candidatos", con)
    escolhidos = escolher_sinal(sinais)
    print(f"  {len(escolhidos)} estrelas candidatas")

    linhas = []
    for i, s in enumerate(escolhidos.itertuples(), 1):
        try:
            extra = _triar(s)
        except Exception as e:
            extra = {"deslocamento_px": None, "figura": None, "erro": str(e)[:200]}
        linhas.append({**s._asdict(), **extra})
        print(f"  {i}/{len(escolhidos)} TIC {s.tic} {s.metodo} P={s.periodo_d:.4f}: "
              f"pico a {extra['deslocamento_px'] if extra['deslocamento_px'] is None else round(extra['deslocamento_px'], 1)} px "
              f"{extra.get('erro', '')}")

    df = pd.DataFrame(linhas).drop(columns=["Index"])
    with sqlite3.connect(SQLITE_PATH) as con:
        # soma aos campos anteriores: a fila do app e a Fase 8 leem todas as candidatas
        try:
            antigas = pd.read_sql("SELECT * FROM candidatos_fase7", con)
            df = pd.concat([antigas[~antigas["tic"].isin(df["tic"])], df], ignore_index=True)
        except pd.errors.DatabaseError:
            pass
        df.to_sql("candidatos_fase7", con, if_exists="replace", index=False)
    print(f"  Tabela 'candidatos_fase7' gravada, figuras em {TRIAGEM_DIR}")
    print("  Revisao: streamlit run app/revisao.py")


if __name__ == "__main__":
    run()
