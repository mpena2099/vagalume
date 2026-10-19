import re
import ssl
from pathlib import Path

import httpx
import lightkurve as lk
from astroquery.mast import conf as mast_conf

from config import AUTORES_PREFERIDOS, CURVAS_DIR, HTTP_TIMEOUT_S
from src.util import retry

# o Portal do MAST (por tras do search_lightcurve) as vezes leva minutos por consulta; com o
# default de 600 s uma rodada inteira travava. Falhar cedo deixa o retry agir
mast_conf.timeout = HTTP_TIMEOUT_S

TESSCUT_SETORES = "https://mast.stsci.edu/tesscut/api/v0.1/sector"
def url_qlp(tic: int, setor: int) -> str:
    t = f"{tic:016d}"
    return (f"https://archive.stsci.edu/hlsps/qlp/s{setor:04d}/{t[:4]}/{t[4:8]}/{t[8:12]}/"
            f"{t[12:]}/hlsp_qlp_tess_ffi_s{setor:04d}-{t}_tess_v01_llc.fits")


class SemCurva(Exception):
    """O produto nao existe nesse setor (404), diferente de falha de rede."""


def _get(url: str, **params) -> httpx.Response | None:
    # CAs do sistema: o archive.stsci.edu nao valida com o bundle do certifi
    r = httpx.get(url, params=params or None, timeout=HTTP_TIMEOUT_S, follow_redirects=True,
                  verify=ssl.create_default_context())
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r


def setores_observados(ra: float, dec: float) -> list[int]:
    """Setores em que o alvo caiu num detector, via TESScut (~1 s, sem o Portal do MAST)."""
    r = retry(lambda: _get(TESSCUT_SETORES, ra=ra, dec=dec, radius="0m"), "TESScut")
    return sorted({int(x["sector"]) for x in r.json()["results"]}) if r else []


def _baixar_qlp(tic: int, setor: int, caminho: Path):
    """Baixa o FITS do QLP direto do arquivo HLSP, sem passar pela busca do MAST."""
    r = retry(lambda: _get(url_qlp(tic, setor)), "MAST")
    if r is None:
        raise SemCurva(f"TIC {tic} sem QLP no setor {setor}")
    bruto = caminho.with_suffix(".part")
    bruto.write_bytes(r.content)
    try:
        lc = lk.read(bruto)
    finally:
        bruto.unlink(missing_ok=True)
    lc.to_fits(caminho, overwrite=True)
    return lc


def _escolher(resultado, setor):
    autores = [str(a) for a in resultado.author]
    for autor in AUTORES_PREFERIDOS:
        idx = [i for i, a in enumerate(autores) if a == autor]
        if idx:
            setores = [int(resultado.table["sequence_number"][i]) for i in idx]
            i = idx[setores.index(min(setores))] if setor is None else idx[0]
            return autor, int(resultado.table["sequence_number"][i]), resultado[i]
    raise ValueError(f"nenhum autor preferido entre {sorted(set(autores))}")


def _download(linha):
    try:
        return linha.download()
    except Exception as e:
        # download interrompido deixa FITS truncado no cache do lightkurve
        m = re.search(r"Data product (\S+\.fits)", str(e))
        if m:
            Path(m.group(1)).unlink(missing_ok=True)
        raise


def _caminho(tic, setor, autor):
    return CURVAS_DIR / f"{tic}_s{setor}_{autor}.fits"


def baixar_curva(tic: int, setor: int | None = None, autor: str | None = None):
    if setor is not None and autor is not None and _caminho(tic, setor, autor).exists():
        lc = lk.read(_caminho(tic, setor, autor))
    elif setor is not None and autor == "QLP":
        CURVAS_DIR.mkdir(parents=True, exist_ok=True)
        lc = _baixar_qlp(tic, setor, _caminho(tic, setor, autor))
    else:
        resultado = retry(lambda: lk.search_lightcurve(f"TIC {tic}", sector=setor, author=autor),
                          "MAST")
        if resultado is None or len(resultado) == 0:
            raise ValueError(f"TIC {tic} sem curvas no MAST")
        autor, setor, linha = _escolher(resultado, setor)

        CURVAS_DIR.mkdir(parents=True, exist_ok=True)
        caminho = _caminho(tic, setor, autor)
        if caminho.exists():
            lc = lk.read(caminho)
        else:
            lc = retry(lambda: _download(linha), "MAST")
            lc.to_fits(caminho, overwrite=True)

    if "quality" in lc.colnames:
        lc = lc[lc.quality == 0]
    lc = lc.remove_nans().normalize()
    meta = {"tic": tic, "autor": autor, "setor": setor, "n_pontos": len(lc),
            "caminho": str(_caminho(tic, setor, autor))}
    return lc, meta
