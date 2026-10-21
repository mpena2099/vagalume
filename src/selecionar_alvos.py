import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from astroquery.mast import Catalogs, Observations

from config import (ALVO_CONTRATIO_MAX, ALVO_DEC_DEG, ALVO_MAX, ALVO_RA_DEG, ALVO_RAIO_DEG,
                    ALVO_SEMENTE, ALVO_SETOR, ALVO_TMAG_MAX, ALVO_TMAG_MIN, AUTORES_PREFERIDOS,
                    SQLITE_PATH)
from src.util import retry


def filtrar_alvos(tic: pd.DataFrame, obs: pd.DataFrame, setor: int) -> pd.DataFrame:
    tic = tic[tic["Tmag"].between(ALVO_TMAG_MIN, ALVO_TMAG_MAX)
              & (tic["contratio"] < ALVO_CONTRATIO_MAX)]

    obs = obs[obs["provenance_name"].isin(AUTORES_PREFERIDOS)
              & (obs["sequence_number"] == setor)].copy()
    obs["tic"] = pd.to_numeric(obs["target_name"], errors="coerce")
    obs["ordem"] = obs["provenance_name"].map(AUTORES_PREFERIDOS.index)
    autor = obs.dropna(subset=["tic"]).sort_values("ordem").drop_duplicates("tic")
    autor = autor.astype({"tic": "int64"}).set_index("tic")["provenance_name"]

    df = pd.DataFrame({
        "tic": tic["ID"].astype("int64"),
        "ra": tic["ra"], "dec": tic["dec"],
        "tmag": tic["Tmag"], "contratio": tic["contratio"],
    })
    df["autor"] = df["tic"].map(autor)
    df = df.dropna(subset=["autor"]).drop_duplicates("tic")
    df["setor"] = setor

    if len(df) > ALVO_MAX:
        df = df.sample(ALVO_MAX, random_state=ALVO_SEMENTE)
    return df.sort_values("tmag").reset_index(drop=True)


def run(campo: dict | None = None) -> int:
    """campo: {"setor", "ra", "dec"} de src.campos; sem ele, o campo fixo do config."""
    setor = campo["setor"] if campo else ALVO_SETOR
    ra, dec = (campo["ra"], campo["dec"]) if campo else (ALVO_RA_DEG, ALVO_DEC_DEG)
    coord = f"{ra} {dec}"
    print(f"  Campo RA={ra} Dec={dec} raio={ALVO_RAIO_DEG} deg, setor {setor}")

    print("  Consultando TIC...")
    tic = retry(lambda: Catalogs.query_criteria(
        catalog="Tic", coordinates=coord, radius=ALVO_RAIO_DEG,
        Tmag=[ALVO_TMAG_MIN, ALVO_TMAG_MAX], contratio=[0, ALVO_CONTRATIO_MAX]), "MAST")
    tic = tic["ID", "ra", "dec", "Tmag", "contratio"].to_pandas()
    tic["ID"] = pd.to_numeric(tic["ID"])
    print(f"  {len(tic)} estrelas no TIC com T {ALVO_TMAG_MIN}-{ALVO_TMAG_MAX} e contratio < {ALVO_CONTRATIO_MAX}")

    print("  Consultando curvas no MAST...")
    obs = retry(lambda: Observations.query_criteria(
        coordinates=coord, radius=ALVO_RAIO_DEG,
        provenance_name=AUTORES_PREFERIDOS, sequence_number=setor), "MAST")
    obs = obs["target_name", "provenance_name", "sequence_number"].to_pandas()
    print(f"  {len(obs)} curvas no setor {setor}")

    df = filtrar_alvos(tic, obs, setor)
    print(f"  {len(df)} alvos selecionados (limite {ALVO_MAX})")
    print(f"  Por autor: {df['autor'].value_counts().to_dict()}")
    print(f"  Tmag mediana {df['tmag'].median():.2f}")

    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(SQLITE_PATH) as con:
        df.to_sql("alvos", con, if_exists="replace", index=False)
    print(f"  Tabela 'alvos' gravada em {SQLITE_PATH}")
    return len(df)


if __name__ == "__main__":
    run()
