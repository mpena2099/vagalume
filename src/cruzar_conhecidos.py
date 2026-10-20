import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import astropy.units as u
import httpx
import numpy as np
import pandas as pd
from astropy.coordinates import SkyCoord
from astroquery.simbad import Simbad
from astroquery.vizier import Vizier

from config import (CATALOGOS_GAIA, CATALOGOS_VIZIER, HTTP_TIMEOUT_S, PERIODO_MATCH_TOL_REL,
                    RAIO_MATCH_ARCSEC,
                    RAIO_MESMA_ESTRELA_ARCSEC, SIMBAD_VARIAVEIS, SQLITE_PATH, TOI_PATH, TOI_URL,
                    WANG_DIR, WANG_URLS)
from src.periodo import comparar_periodo
from src.util import retry

COLUNAS_NOME = ["Name", "ASASSN-V", "ID", "TIC", "Source"]


def _valor(linha, coluna):
    if coluna is None or coluna not in linha.colnames or np.ma.is_masked(linha[coluna]):
        return None
    return linha[coluna]


def classificar(matches: list[dict], periodo_d: float) -> dict:
    """matches: dicts com catalogo, nome, dist_arcsec, periodo, gaia, classe."""
    gaia = [m for m in matches if m["gaia"] and m["dist_arcsec"] <= RAIO_MESMA_ESTRELA_ARCSEC]
    saida = {
        "gaia_candidata": bool(gaia),
        "gaia_classe": ",".join(sorted({m["classe"] for m in gaia if m.get("classe")})) or None,
    }

    conhecidos = []
    for m in matches:
        if m["gaia"]:
            continue
        razao = None
        if m["periodo"]:
            _, razao = comparar_periodo(periodo_d, m["periodo"], PERIODO_MATCH_TOL_REL)
        conhecidos.append({**m, "razao": razao})
    if not conhecidos:
        return {**saida, "status": "novo", "match_catalogo": None, "match_nome": None,
                "match_dist_arcsec": None, "periodo_catalogo": None, "razao_periodo": None}

    # mais perto primeiro; no empate de faixa, quem tem periodo compativel
    conhecidos.sort(key=lambda m: (m["dist_arcsec"] > RAIO_MESMA_ESTRELA_ARCSEC,
                                   m["razao"] is None, m["dist_arcsec"]))
    m = conhecidos[0]
    status = "conhecido" if m["dist_arcsec"] <= RAIO_MESMA_ESTRELA_ARCSEC else "conhecido_vizinho"
    return {**saida, "status": status, "match_catalogo": m["catalogo"], "match_nome": m["nome"],
            "match_dist_arcsec": m["dist_arcsec"], "periodo_catalogo": m["periodo"],
            "razao_periodo": m["razao"]}


def _toi() -> pd.DataFrame:
    if not TOI_PATH.exists():
        TOI_PATH.parent.mkdir(parents=True, exist_ok=True)
        retry(lambda: pd.read_csv(TOI_URL).to_csv(TOI_PATH, index=False), "ExoFOP")
    return pd.read_csv(TOI_PATH)


def _baixar_wang(url: str, destino: Path):
    # o servidor recusa o user agent padrao do Python
    resp = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True,
                     timeout=HTTP_TIMEOUT_S)
    resp.raise_for_status()
    destino.write_bytes(resp.content)


def _wang() -> pd.DataFrame:
    WANG_DIR.mkdir(parents=True, exist_ok=True)
    tabelas = []
    for nome, url in WANG_URLS.items():
        caminho = WANG_DIR / f"{nome}.csv"
        if not caminho.exists():
            retry(lambda: _baixar_wang(url, caminho), "China-VO")
        tabelas.append(pd.read_csv(caminho, encoding="utf-8-sig",
                                   usecols=["name", "VI_class", "P", "RA", "DEC"]))
    return pd.concat(tabelas, ignore_index=True)


def _consultar_wang(alvo: SkyCoord, wang: pd.DataFrame) -> list[dict]:
    perto = wang[(np.abs(wang["DEC"] - alvo.dec.deg) < RAIO_MATCH_ARCSEC / 3600)]
    if perto.empty:
        return []
    dist = alvo.separation(SkyCoord(perto["RA"].values, perto["DEC"].values, unit="deg")).arcsec
    return [{"catalogo": "Wang2025", "nome": f"TIC {w.name} ({w.VI_class})",
             "dist_arcsec": float(d), "periodo": float(w.P) if pd.notna(w.P) else None,
             "gaia": False, "classe": None}
            for w, d in zip(perto.itertuples(), dist) if d <= RAIO_MATCH_ARCSEC]


def _consultar_vizier(alvo: SkyCoord, raio_arcsec: float) -> list[dict]:
    catalogos = list(CATALOGOS_VIZIER) + list(CATALOGOS_GAIA)
    # _RAJ2000/_DEJ2000: posicao calculada pelo VizieR, para catalogo sem coluna de RA/Dec
    res = retry(lambda: Vizier(columns=["**", "_RAJ2000", "_DEJ2000"], row_limit=-1).query_region(
        alvo, radius=raio_arcsec * u.arcsec, catalog=catalogos), "VizieR")

    matches = []
    for chave in res.keys():
        cat = next(c for c in catalogos if chave.startswith(c))
        gaia = cat in CATALOGOS_GAIA
        nome_cat, col_periodo = (CATALOGOS_GAIA[cat], None) if gaia else CATALOGOS_VIZIER[cat]
        for linha in res[chave]:
            col_ra = next(c for c in ("RAJ2000", "RA_ICRS", "_RAJ2000") if c in linha.colnames)
            col_dec = next(c for c in ("DEJ2000", "DE_ICRS", "_DEJ2000") if c in linha.colnames)
            ra_c, dec_c = _valor(linha, col_ra), _valor(linha, col_dec)
            periodo = _valor(linha, col_periodo)
            if cat == "I/358/veb" and _valor(linha, "Freq"):
                periodo = 1 / float(linha["Freq"])
            nome = next((_valor(linha, c) for c in COLUNAS_NOME if _valor(linha, c) is not None), None)
            matches.append({
                "catalogo": nome_cat, "nome": str(nome),
                "dist_arcsec": float(alvo.separation(SkyCoord(ra_c, dec_c, unit="deg")).arcsec),
                "periodo": float(periodo) if periodo else None,
                "gaia": gaia, "classe": str(_valor(linha, "Class") or "") if gaia else None,
            })
    return matches


def _consultar(tic: int, ra: float, dec: float, toi: pd.DataFrame,
               wang: pd.DataFrame) -> list[dict]:
    alvo = SkyCoord(ra, dec, unit="deg")
    raio = RAIO_MATCH_ARCSEC * u.arcsec
    matches = _consultar_vizier(alvo, RAIO_MATCH_ARCSEC) + _consultar_wang(alvo, wang)

    simbad = Simbad()
    simbad.add_votable_fields("otype")
    sim = retry(lambda: simbad.query_region(alvo, radius=raio), "SIMBAD")
    for linha in sim if sim is not None else []:
        if str(linha["otype"]) in SIMBAD_VARIAVEIS:
            matches.append({
                "catalogo": "SIMBAD", "nome": f"{linha['main_id']} ({linha['otype']})",
                "dist_arcsec": float(alvo.separation(
                    SkyCoord(linha["ra"], linha["dec"], unit="deg")).arcsec),
                "periodo": None, "gaia": False, "classe": None,
            })

    for _, t in toi[toi["TIC ID"] == tic].iterrows():
        periodo = t["Period (days)"]
        matches.append({"catalogo": "TOI", "nome": f"TOI {t['TOI']}", "dist_arcsec": 0.0,
                        "periodo": float(periodo) if pd.notna(periodo) and periodo > 0 else None,
                        "gaia": False, "classe": None})
    return matches


def run():
    with sqlite3.connect(SQLITE_PATH) as con:
        sinais = pd.read_sql(
            "SELECT s.*, a.ra, a.dec, a.tmag FROM sinais s JOIN alvos a USING (tic) "
            "WHERE s.sinal = 1", con)
    estrelas = sinais.drop_duplicates("tic")
    print(f"  {len(sinais)} sinais em {len(estrelas)} estrelas, raio {RAIO_MATCH_ARCSEC}\"")
    toi = _toi()
    wang = _wang()

    linhas = []
    for i, e in enumerate(estrelas.itertuples(), 1):
        matches = _consultar(int(e.tic), e.ra, e.dec, toi, wang)
        for s in sinais[sinais["tic"] == e.tic].to_dict("records"):
            linhas.append({**s, **classificar(matches, s["periodo_d"])})
        print(f"  {i}/{len(estrelas)} TIC {e.tic}: {linhas[-1]['status']} "
              f"{linhas[-1]['match_catalogo'] or ''} {linhas[-1]['match_nome'] or ''}")

    df = pd.DataFrame(linhas)
    por_estrela = df.sort_values("status").drop_duplicates("tic")
    print(f"  Status por estrela: {por_estrela['status'].value_counts().to_dict()}")
    print(f"  Match por catalogo: {por_estrela['match_catalogo'].value_counts().to_dict()}")
    print(f"  Gaia candidata: {int(por_estrela['gaia_candidata'].sum())}")

    with sqlite3.connect(SQLITE_PATH) as con:
        df.to_sql("sinais_fase5", con, if_exists="replace", index=False)
    print(f"  Tabela 'sinais_fase5' gravada em {SQLITE_PATH}")


if __name__ == "__main__":
    run()
