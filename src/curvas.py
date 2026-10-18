import re
from pathlib import Path

import lightkurve as lk

from config import AUTORES_PREFERIDOS, CURVAS_DIR
from src.util import retry


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
