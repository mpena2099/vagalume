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


def baixar_curva(tic: int, setor: int | None = None):
    resultado = retry(lambda: lk.search_lightcurve(f"TIC {tic}", sector=setor), "MAST")
    if resultado is None or len(resultado) == 0:
        raise ValueError(f"TIC {tic} sem curvas no MAST")
    autor, setor, linha = _escolher(resultado, setor)

    CURVAS_DIR.mkdir(parents=True, exist_ok=True)
    caminho = CURVAS_DIR / f"{tic}_s{setor}_{autor}.fits"
    if caminho.exists():
        lc = lk.read(caminho)
    else:
        lc = retry(lambda: linha.download(), "MAST")
        lc.to_fits(caminho, overwrite=True)

    if "quality" in lc.colnames:
        lc = lc[lc.quality == 0]
    lc = lc.remove_nans().normalize()
    meta = {"tic": tic, "autor": autor, "setor": setor, "n_pontos": len(lc)}
    return lc, meta
