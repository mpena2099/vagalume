"""Carta de identificacao (DSS2 Red) do alvo, anexo da submissao ao VSX."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle


def escala_px(lado_arcmin: float, pixels: int) -> float:
    """Segundos de arco por pixel de uma imagem de `lado_arcmin` com `pixels` de lado."""
    return lado_arcmin * 60 / pixels


def gerar_carta(tic: int, ra: float, dec: float, vizinhas: list[tuple[float, float]],
                saida: Path, lado_arcmin: float = 5) -> Path | None:
    """Salva em `saida` a imagem DSS2 Red com o alvo e as vizinhas marcados; None se o SkyView
    nao responder."""
    import astropy.units as u
    from astropy.coordinates import SkyCoord
    from astropy.wcs import WCS
    from astroquery.skyview import SkyView

    from src.util import retry

    alvo = SkyCoord(ra, dec, unit="deg")
    pixels = 500
    try:
        hdus = retry(lambda: SkyView.get_images(position=alvo, survey=["DSS2 Red"],
                                                width=lado_arcmin * u.arcmin,
                                                height=lado_arcmin * u.arcmin,
                                                pixels=pixels), "SkyView")
    except Exception as e:
        print(f"  SkyView nao respondeu para a TIC {tic}: {e}")
        return None

    wcs = WCS(hdus[0][0].header)
    fig = plt.figure(figsize=(6, 6))
    ax = fig.add_subplot(1, 1, 1, projection=wcs)
    ax.imshow(hdus[0][0].data, cmap="gray_r")
    ax.set_xlabel("RA")
    ax.set_ylabel("Dec")

    raio = 10 / escala_px(lado_arcmin, pixels)
    x0, y0 = wcs.all_world2pix([[ra, dec]], 0)[0]
    ax.add_patch(Circle((x0, y0), raio, edgecolor="red", facecolor="none", lw=1.5))
    ax.annotate(f"TIC {tic}", (x0, y0), xytext=(x0 + 1.6 * raio, y0 + 1.6 * raio),
                color="red", fontsize=9,
                arrowprops={"arrowstyle": "-", "color": "red"})
    for vra, vdec in vizinhas:
        xv, yv = wcs.all_world2pix([[vra, vdec]], 0)[0]
        ax.add_patch(Circle((xv, yv), 0.6 * raio, edgecolor="blue", facecolor="none", lw=1))

    ax.text(0.03, 0.95, "N para cima, E para a esquerda", transform=ax.transAxes, fontsize=9,
            color="black", va="top",
            bbox={"facecolor": "white", "alpha": 0.7, "edgecolor": "none"})
    barra = 60 / escala_px(lado_arcmin, pixels)
    ax.plot([20, 20 + barra], [20, 20], color="black", lw=3)
    ax.text(20 + barra / 2, 30, "1'", ha="center", fontsize=9,
            bbox={"facecolor": "white", "alpha": 0.7, "edgecolor": "none"})
    ax.set_title(f"TIC {tic}  DSS2 Red  {lado_arcmin:.0f}'x{lado_arcmin:.0f}'")

    saida.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(saida, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return saida
