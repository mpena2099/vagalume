import sqlite3
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import astropy.units as u
import lightkurve as lk
import numpy as np
import pandas as pd
from astropy.coordinates import SkyCoord
from astroquery.vizier import Vizier

from config import (BLEND_AMP_MAX, BLS_FLATTEN_D, CATALOGOS_GAIA, CATALOGOS_VIZIER,
                    CONTAMINACAO_WORKERS, LS_FLATTEN_D, PERIODO_MATCH_TOL_REL,
                    PERSISTENCIA_MAX_SETORES, RAIO_MESMA_ESTRELA_ARCSEC,
                    RAIO_VIZINHA_GAIA_ARCSEC, RAIO_VIZINHA_VARIAVEL_ARCSEC, SQLITE_PATH,
                    VIZINHA_DMAG_MAX)
from src.baixar_curvas import resumir_curva
from src.cruzar_conhecidos import _consultar_vizier
from src.curvas import SemCurva, baixar_curva, setores_observados
from src.detectar_sinal import _arrays, _flatten
from src.periodo import comparar_periodo, medir_periodo_bls, medir_periodo_ls
from src.util import retry


def amp_necessaria(amplitude: float, dmag: float) -> float:
    """Amplitude intrinseca que uma vizinha dmag mais fraca precisa ter para gerar a observada."""
    razao = 10 ** (-0.4 * dmag)
    return amplitude * (1 + razao) / razao


def veredito(vizinha_mesmo_periodo: bool, persistente: bool | None) -> tuple[str, str | None]:
    if vizinha_mesmo_periodo:
        return "descartado", "vizinha_variavel"
    if persistente is False:
        return "descartado", "nao_persiste"
    return "candidato", None


def _vizinhas_variaveis(alvo: SkyCoord, periodo_d: float) -> dict:
    matches = _consultar_vizier(alvo, RAIO_VIZINHA_VARIAVEL_ARCSEC)
    vizinhas = [m for m in matches if m["dist_arcsec"] > RAIO_MESMA_ESTRELA_ARCSEC]
    mesmo = [m for m in vizinhas
             if m["periodo"] and comparar_periodo(periodo_d, m["periodo"], PERIODO_MATCH_TOL_REL)[0]]
    mesmo.sort(key=lambda m: m["dist_arcsec"])
    return {
        "n_vizinhas_variaveis": len({(m["catalogo"], m["nome"]) for m in vizinhas}),
        "vizinha_mesmo_periodo": mesmo[0]["nome"] if mesmo else None,
        "vizinha_mesmo_periodo_catalogo": mesmo[0]["catalogo"] if mesmo else None,
        "vizinha_mesmo_periodo_dist": mesmo[0]["dist_arcsec"] if mesmo else None,
    }


def _vizinhas_gaia(alvo: SkyCoord, tmag: float, amplitude: float) -> dict:
    res = retry(lambda: Vizier(columns=["Source", "RA_ICRS", "DE_ICRS", "Gmag"], row_limit=-1)
                .query_region(alvo, radius=RAIO_VIZINHA_GAIA_ARCSEC * u.arcsec,
                              catalog="I/355/gaiadr3"), "VizieR")
    if not len(res):
        return {"gaia_g": None, "n_vizinhas_brilhantes": 0, "amp_necessaria_min": None}
    t = res[0].to_pandas().dropna(subset=["Gmag"])
    t["dist"] = alvo.separation(SkyCoord(t["RA_ICRS"], t["DE_ICRS"], unit="deg")).arcsec
    # alvo = fonte mais brilhante a ate 3" (G costuma ficar ~0,5 acima de T)
    perto = t[t["dist"] < 3]
    g = float(perto["Gmag"].min()) if len(perto) else tmag + 0.5
    viz = t[(t["dist"] > 1) & (t["Gmag"] < g + VIZINHA_DMAG_MAX) & (t["Gmag"] != g)]
    amps = [amp_necessaria(amplitude, gm - g) for gm in viz["Gmag"]]
    return {"gaia_g": g, "n_vizinhas_brilhantes": len(viz),
            "amp_necessaria_min": float(min(amps)) if amps else None}


def _medir(lc, metodo: str) -> float:
    if metodo == "ls":
        return medir_periodo_ls(*_arrays(_flatten(lc, LS_FLATTEN_D)))["periodo_d"]
    tempo, fluxo = _arrays(_flatten(lc, BLS_FLATTEN_D))
    ruido = resumir_curva(tempo, fluxo)["ruido_ptp"]
    return medir_periodo_bls(tempo, fluxo, dy=np.full(tempo.size, ruido))["periodo_d"]


def _setores(tic: int, autor: str, ra: float, dec: float) -> set[int]:
    if autor == "QLP":
        # TESScut lista os setores em ~1 s; a busca do lightkurve passa pelo Portal do MAST,
        # que as vezes leva minutos. Setor sem QLP cai em SemCurva no download
        return set(setores_observados(ra, dec))
    busca = retry(lambda: lk.search_lightcurve(f"TIC {tic}", author=autor), "MAST")
    return {int(s) for s in busca.table["sequence_number"]} if len(busca) else set()


def _persistencia(tic: int, setor: int, autor: str, metodo: str, periodo_d: float,
                  ra: float, dec: float) -> dict:
    # mesmo produto do setor original: estrela sem QLP (so SPOC) caia em "erro" aqui
    setores = _setores(tic, autor, ra, dec)
    # o lightkurve devolve busca vazia quando a rede cai
    if setor not in setores:
        raise RuntimeError(f"busca {autor} sem o setor {setor}, MAST fora do ar?")
    # setores mais proximos primeiro: mesma geometria de campo, sistematicos parecidos
    outros = sorted(setores - {setor}, key=lambda s: abs(s - setor))
    medidos = []
    # setor listado pelo TESScut pode nao ter QLP: pula e tenta o proximo
    for s in outros[:3 * PERSISTENCIA_MAX_SETORES]:
        if len(medidos) == PERSISTENCIA_MAX_SETORES:
            break
        try:
            lc, _ = baixar_curva(tic, s, autor)
            medidos.append((s, _medir(lc, metodo)))
        except SemCurva:
            continue
        except Exception as e:
            print(f"  TIC {tic} setor {s}: {str(e)[:80]}")
    ok = [s for s, p in medidos if comparar_periodo(p, periodo_d, PERIODO_MATCH_TOL_REL)[0]]
    return {
        "setores_extra": ",".join(str(s) for s, _ in medidos) or None,
        "periodos_extra": ",".join(f"{p:.5f}" for _, p in medidos) or None,
        "persistente": bool(ok) if medidos else None,
    }


def _checar(sinal: dict) -> dict:
    alvo = SkyCoord(sinal["ra"], sinal["dec"], unit="deg")
    linha = dict(sinal)
    try:
        linha.update(_vizinhas_variaveis(alvo, sinal["periodo_d"]))
        linha.update(_vizinhas_gaia(alvo, sinal["tmag"], sinal["amplitude"]))
        linha.update(_persistencia(int(sinal["tic"]), int(sinal["setor"]), sinal["autor"],
                                   sinal["metodo"], sinal["periodo_d"], sinal["ra"],
                                   sinal["dec"]))
    except Exception as e:
        linha.update(veredito="erro", motivo_descarte=str(e)[:200])
        return linha
    amp = linha["amp_necessaria_min"]
    linha["suspeito_blend"] = amp is not None and amp < BLEND_AMP_MAX
    linha["veredito"], linha["motivo_descarte"] = veredito(
        linha["vizinha_mesmo_periodo"] is not None, linha["persistente"])
    return linha


def run():
    with sqlite3.connect(SQLITE_PATH) as con:
        sinais = pd.read_sql("SELECT s.*, a.autor FROM sinais_fase5 s JOIN alvos a USING (tic) "
                             "WHERE s.status = 'novo'", con)
    print(f"  {len(sinais)} sinais novos em {sinais['tic'].nunique()} estrelas")

    linhas = []
    with ProcessPoolExecutor(CONTAMINACAO_WORKERS) as ex:
        futuros = [ex.submit(_checar, s) for s in sinais.to_dict("records")]
        for i, f in enumerate(as_completed(futuros), 1):
            l = f.result()
            linhas.append(l)
            extra = l.get("vizinha_mesmo_periodo") or l.get("periodos_extra") or ""
            print(f"  {i}/{len(futuros)} TIC {l['tic']} {l['metodo']} P={l['periodo_d']:.4f}: "
                  f"{l['veredito']} {l.get('motivo_descarte') or ''} {extra}")

    df = pd.DataFrame(linhas).sort_values(["tic", "metodo"]).reset_index(drop=True)
    print(f"  Veredito por sinal: {df['veredito'].value_counts().to_dict()}")
    print(f"  Motivos: {df['motivo_descarte'].value_counts().to_dict()}")
    cand = df[df["veredito"] == "candidato"]
    print(f"  Estrelas candidatas: {cand['tic'].nunique()} "
          f"({int(cand.drop_duplicates('tic')['suspeito_blend'].sum())} com suspeito_blend)")

    with sqlite3.connect(SQLITE_PATH) as con:
        df.to_sql("candidatos", con, if_exists="replace", index=False)
    print(f"  Tabela 'candidatos' gravada em {SQLITE_PATH}")


if __name__ == "__main__":
    run()
