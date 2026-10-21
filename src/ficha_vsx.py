"""Fase 8: ficha de submissao ao VSX para as candidatas confirmadas na revisao.

Manual, como a revisao: nao entra no pipeline.py. Para cada estrela, junta o que o
formulario do VSX pede (checklist na secao 11 da especificacao): fonte Gaia DR3, magnitude V
estimada, periodo sugerido (P ou 2P), tipo sugerido, epoca do minimo em BJD, amplitude em
magnitude TESS e uma nova busca no VizieR inteiro. O VSX nao tem API: os campos sao copiados
a mao para o New Star Wizard. Tipo e periodo sao sugestoes, conferir na figura.

    python src/ficha_vsx.py              # confirmadas
    python src/ficha_vsx.py --duvidas    # confirmadas e duvidas
    python src/ficha_vsx.py --todas      # todas as candidatas da Fase 7 (antes da revisao)
"""

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import astropy.units as u
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from astropy.coordinates import SkyCoord
from astroquery.vizier import Vizier

from app.dados import carregar_candidatos
from config import BLS_FLATTEN_D, LS_FLATTEN_D, SQLITE_PATH, VSX_DIR
from src.curvas import baixar_curva
from src.detectar_sinal import _arrays, _flatten
from src.util import retry

BTJD_PARA_BJD = 2457000.0
# Descricao de catalogo VizieR que indica variabilidade: onde a estrela pode ter entrado
# depois da varredura (a Fase 5 cobre so a lista fixa dela)
PALAVRAS_VARIAVEL = ("variab", "eclips", "binar", "periodic", "pulsat", "rotation",
                     "light curve", "light-curve")


def v_de_gaia(g: float, bp_rp: float) -> float:
    """Magnitude V a partir de G e BP-RP (Riello+2021, valida para -0,5 < BP-RP < 5)."""
    c = bp_rp
    return g - (-0.02704 + 0.01424 * c - 0.2156 * c ** 2 + 0.01426 * c ** 3)


def curva_binada(tempo: np.ndarray, fluxo: np.ndarray, periodo: float, n_bins: int):
    """Medianas e erro da mediana por bin de fase (fase 0 = primeiro ponto)."""
    fase = ((tempo - tempo.min()) / periodo) % 1
    idx = np.minimum((fase * n_bins).astype(int), n_bins - 1)
    med = np.array([np.nanmedian(fluxo[idx == k]) if np.any(idx == k) else np.nan
                    for k in range(n_bins)])
    ruido = 1.4826 * np.nanmedian(np.abs(fluxo - np.nanmedian(fluxo)))
    n = np.bincount(idx, minlength=n_bins)
    return med, ruido / np.sqrt(np.maximum(n, 1))


def amplitude_dobrada_mag(tempo: np.ndarray, fluxo: np.ndarray, periodo: float,
                          n_bins: int = 200) -> float:
    """Pico a pico da curva dobrada, em magnitude. Bins finos: eclipse estreito some em 50 bins
    (a amplitude do LS da Fase 4 dava 0,008 mag para eclipses de 0,28 mag)."""
    med, _ = curva_binada(tempo, fluxo, periodo, n_bins)
    return float(2.5 * np.log10(np.nanmax(med) / np.nanmin(med)))


def fracao_variando(tempo: np.ndarray, fluxo: np.ndarray, periodo: float,
                    n_bins: int = 200) -> float:
    """Fracao da fase em que o brilho cai mais de 10% da amplitude abaixo do nivel de topo.
    Pequena (eclipses estreitos e brilho plano no resto) indica binaria destacada (EA)."""
    med, _ = curva_binada(tempo, fluxo, periodo, n_bins)
    topo = np.nanpercentile(med, 90)
    return float(np.nanmean(topo - med > 0.1 * (topo - np.nanmin(med))))


def sugerir(metodo: str, periodo: float, tempo: np.ndarray, fluxo: np.ndarray,
            n_bins: int = 40) -> tuple[float, str, str]:
    """(periodo, tipo VSX sugerido, motivo). Binaria no LS costuma sair com metade do periodo."""
    if metodo == "bls":
        return periodo, "EA", "eclipses curtos achados pelo BLS"
    if fracao_variando(tempo, fluxo, 2 * periodo) < 0.3:
        return (2 * periodo, "EA",
                "dobrada em 2P, dois eclipses estreitos e brilho plano entre eles: o periodo real e 2P")
    med, erro = curva_binada(tempo, fluxo, 2 * periodo, n_bins)
    base = np.nanmedian(med)
    k1 = int(np.nanargmin(med))
    perto = [(k1 + n_bins // 2 + d) % n_bins for d in range(-n_bins // 10, n_bins // 10 + 1)]
    k2 = perto[int(np.nanargmin(med[perto]))]
    p1, p2 = base - med[k1], base - med[k2]
    diferenca = abs(p1 - p2)
    sigma = np.hypot(erro[k1], erro[k2])
    if diferenca > 3 * sigma and diferenca > 0.15 * p1:
        return (2 * periodo, "EB",
                f"dobrada em 2P, os minimos diferem ({p1:.4f} x {p2:.4f}) e o brilho varia o tempo "
                "todo: o periodo real e 2P")
    return (periodo, "ROT, EW ou pulsante",
            "minimos iguais em 2P: senoide com o periodo do LS (ROT/pulsante) ou EW com 2P; "
            "decidir pela forma da curva")


def epoca_minimo(tempo: np.ndarray, fluxo: np.ndarray, periodo: float, n_bins: int = 50) -> float:
    """Instante de minimo (mesma escala de `tempo`) mais perto do meio dos dados."""
    med, _ = curva_binada(tempo, fluxo, periodo, n_bins)
    t0 = tempo.min() + (np.nanargmin(med) + 0.5) / n_bins * periodo
    meio = (tempo.min() + tempo.max()) / 2
    return t0 + round((meio - t0) / periodo) * periodo


def eh_catalogo_variavel(descricao: str) -> bool:
    d = descricao.lower()
    # "Variability Upper Limits for Non-Variable Sources" casa com "variab" e diz o contrario
    return "non-variable" not in d and any(p in d for p in PALAVRAS_VARIAVEL)


def _gaia(alvo: SkyCoord) -> dict:
    res = retry(lambda: Vizier(columns=["Source", "RA_ICRS", "DE_ICRS", "Gmag", "BP-RP", "_r"],
                               row_limit=-1)
                .query_region(alvo, radius=5 * u.arcsec, catalog="I/355/gaiadr3"), "VizieR")
    if not len(res):
        return {}
    t = res[0].to_pandas().dropna(subset=["Gmag"])
    # o alvo e a fonte mais brilhante a ate 3" (G costuma ficar ~0,5 acima de T)
    t = t[t["_r"] < 3].sort_values("Gmag")
    if t.empty:
        return {}
    # Source antes do iloc: a linha mista vira float64 e o ID de 19 digitos perde os ultimos
    fonte = int(t["Source"].iloc[0])
    g = t.iloc[0]
    v = v_de_gaia(g["Gmag"], g["BP-RP"]) if pd.notna(g["BP-RP"]) else np.nan
    return {"gaia_dr3": fonte, "gaia_ra": float(g["RA_ICRS"]),
            "gaia_dec": float(g["DE_ICRS"]), "gaia_g": float(g["Gmag"]), "v_estimada": float(v),
            "gaia_sep_arcsec": float(g["_r"])}


def _vizier(alvo: SkyCoord) -> list[str]:
    """Catalogos de variaveis a ate 30" (o pixel do TESS tem 21")."""
    res = retry(lambda: Vizier(columns=["_r"], row_limit=5, timeout=180)
                .query_region(alvo, radius=30 * u.arcsec), "VizieR")
    achados = []
    for nome in res.keys():
        descricao = str(res[nome].meta.get("description", ""))
        if eh_catalogo_variavel(descricao):
            achados.append(f'{nome} ({descricao[:70]}) a {float(np.min(res[nome]["_r"])):.1f}"')
    return achados


def _figura(tic: int, tempo, fluxo, periodo: float, epoca: float, saida: Path):
    fase = ((tempo - epoca) / periodo + 0.25) % 1 - 0.25
    mag = -2.5 * np.log10(np.clip(fluxo, 1e-6, None))
    # so pontos, sem linha de mediana: eclipses estreitos (<1% da fase) sumiam na mediana,
    # e a figura vai anexada ao VSX
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(np.concatenate([fase, fase + 1]), np.concatenate([mag, mag]), ".", ms=1.5,
            color="0.3", rasterized=True)
    ax.invert_yaxis()
    ax.set_xlabel(f"fase (P = {periodo:.5f} d, epoca BJD {epoca + BTJD_PARA_BJD:.4f})")
    ax.set_ylabel("delta mag (TESS)")
    ax.set_title(f"TIC {tic}")
    fig.tight_layout()
    fig.savefig(saida, dpi=110)
    plt.close(fig)


def montar_ficha(s) -> dict:
    alvo = SkyCoord(s.ra, s.dec, unit="deg")
    lc, _ = baixar_curva(int(s.tic), int(s.setor), s.autor)
    tempo, fluxo = _arrays(_flatten(lc, BLS_FLATTEN_D if s.metodo == "bls" else LS_FLATTEN_D))
    periodo, tipo, motivo = sugerir(s.metodo, s.periodo_d, tempo, fluxo)
    epoca = epoca_minimo(tempo, fluxo, periodo)
    figura = VSX_DIR / f"{s.tic}_fase.png"
    _figura(int(s.tic), tempo, fluxo, periodo, epoca, figura)
    ficha = {"tic": int(s.tic), "decisao": s.decisao, "periodo_d": periodo, "tipo_sugerido": tipo,
             "motivo_tipo": motivo, "epoca_bjd": epoca + BTJD_PARA_BJD,
             "amplitude_mag_tess": amplitude_dobrada_mag(tempo, fluxo, periodo),
             "setores": ",".join(str(x) for x in [s.setor, s.setores_extra] if pd.notna(x)),
             "suspeito_blend": bool(s.suspeito_blend), "figura_fase": str(figura),
             "figura_triagem": s.figura}
    ficha.update(_gaia(alvo))
    try:
        ficha["vizier_variaveis"] = "; ".join(_vizier(alvo)) or "nenhum catalogo de variaveis a 30\""
    except Exception as e:
        ficha["vizier_variaveis"] = f"consulta falhou: {str(e)[:80]}"
    return ficha


def _markdown(f: dict) -> str:
    def num(chave, fmt):
        v = f.get(chave)
        return "?" if v is None or pd.isna(v) else format(v, fmt)
    ztf = ("amplitude grande o bastante: juntar a curva do ZTF/ASAS-SN e usar a magnitude deles"
           if f["amplitude_mag_tess"] > 0.05 else "amplitude pequena para o ZTF: so TESS")
    return f"""## TIC {f['tic']} ({f['decisao']})

| Campo do VSX | Valor |
|---|---|
| Posicao (Gaia DR3) | RA {num('gaia_ra', '.6f')}, Dec {num('gaia_dec', '+.6f')} |
| Outros nomes | TIC {f['tic']}, Gaia DR3 {f.get('gaia_dr3', '?')} |
| Tipo (sugestao) | {f['tipo_sugerido']}: {f['motivo_tipo']} |
| Periodo | {f['periodo_d']:.5f} d |
| Epoca do minimo | BJD {f['epoca_bjd']:.4f} |
| Magnitude maxima | V {num('v_estimada', '.2f')} (estimada de Gaia G {num('gaia_g', '.2f')} e BP-RP) |
| Magnitude minima | {f['amplitude_mag_tess']:.3f}, marcar "Minimum is an amplitude", banda "TESS" |
| Dados | TESS QLP, setores {f['setores']} |
| Anexos | `{f['figura_fase']}` (curva em fase) e `{f['figura_triagem']}` |

- VizieR (catalogos de variaveis a 30"): {f['vizier_variaveis']}
- Fonte Gaia escolhida a {num('gaia_sep_arcsec', '.1f')}" do TIC; suspeito_blend: {'sim' if f['suspeito_blend'] else 'nao'}
- {ztf}
"""


def run(decisoes=("confirmado",)) -> Path | None:
    with sqlite3.connect(SQLITE_PATH) as con:
        cand = carregar_candidatos(con)
    sel = cand if decisoes is None else cand[cand["decisao"].isin(decisoes)]
    if sel.empty:
        print("Nenhuma candidata confirmada. Revise no app (streamlit run app/revisao.py).")
        return None
    VSX_DIR.mkdir(parents=True, exist_ok=True)
    fichas = []
    for i, s in enumerate(sel.itertuples(), 1):
        try:
            f = montar_ficha(s)
        except Exception as e:
            print(f"  {i}/{len(sel)} TIC {s.tic}: falhou ({str(e)[:100]})")
            continue
        fichas.append(f)
        print(f"  {i}/{len(sel)} TIC {s.tic}: {f['tipo_sugerido']} P={f['periodo_d']:.5f} d, "
              f"V~{f.get('v_estimada', float('nan')):.2f}, amp {f['amplitude_mag_tess']:.3f} mag")
    df = pd.DataFrame(fichas)
    df.to_csv(VSX_DIR / "fichas.csv", index=False)
    saida = VSX_DIR / "fichas.md"
    saida.write_text("# Fichas para o VSX\n\nChecklist completo na secao 11 de `especificacao.md`. "
                     "Tipo e periodo sao sugestoes: conferir na curva em fase antes de enviar.\n\n"
                     + "\n".join(_markdown(f) for f in fichas), encoding="utf-8")
    print(f"  Fichas em {saida}")
    return saida


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--duvidas", action="store_true", help="inclui as marcadas como duvida")
    g.add_argument("--todas", action="store_true", help="todas as candidatas, revisadas ou nao")
    a = ap.parse_args()
    run(None if a.todas else ("confirmado", "duvida") if a.duvidas else ("confirmado",))
