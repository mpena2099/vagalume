"""Acesso a dados da revisao visual: sem Streamlit, testavel offline."""

import sqlite3
from datetime import datetime
from urllib.parse import quote

import pandas as pd

from config import DESLOCAMENTO_MAX_PX

DECISOES = ("confirmado", "duvida", "descartado")

# Tabela propria: candidatos_fase7 e refeita a cada execucao do pipeline
# (to_sql replace) e apagaria as decisoes humanas.
_SCHEMA_REVISAO = """
CREATE TABLE IF NOT EXISTS revisao_humana (
    tic INTEGER PRIMARY KEY,
    decisao TEXT NOT NULL,
    nota TEXT,
    atualizado_em TEXT NOT NULL
)"""


def ler_revisoes(conn: sqlite3.Connection) -> pd.DataFrame:
    conn.execute(_SCHEMA_REVISAO)
    return pd.read_sql("SELECT tic, decisao, nota FROM revisao_humana", conn)


def carregar_candidatos(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM candidatos_fase7", conn)
    df = df.merge(ler_revisoes(conn), on="tic", how="left")
    df["decisao"] = df["decisao"].fillna("pendente")
    return df


def salvar_revisao(conn: sqlite3.Connection, tic: int, decisao: str, nota: str = "") -> None:
    if decisao not in DECISOES:
        raise ValueError(f"decisao invalida: {decisao!r} (use {DECISOES})")
    conn.execute(_SCHEMA_REVISAO)
    conn.execute("INSERT OR REPLACE INTO revisao_humana VALUES (?, ?, ?, ?)",
                 (int(tic), decisao, nota, datetime.now().isoformat(timespec="seconds")))
    conn.commit()


def apagar_revisao(conn: sqlite3.Connection, tic: int) -> None:
    conn.execute(_SCHEMA_REVISAO)
    conn.execute("DELETE FROM revisao_humana WHERE tic = ?", (int(tic),))
    conn.commit()


def _sim(v) -> bool:
    """Booleano vindo do SQLite: None e NaN contam como falso (NaN e truthy em Python)."""
    return v is not None and not pd.isna(v) and bool(v)


def alertas(r: dict) -> list[str]:
    """Pontos que pesam contra a candidata, em linguagem de revisao."""
    saida = []
    d = r.get("deslocamento_px")
    if d is not None and pd.notna(d) and d > DESLOCAMENTO_MAX_PX:
        saida.append(f"O sinal é mais forte a {d:.1f} px do alvo: pode vir de outra estrela.")
    if _sim(r.get("suspeito_blend")):
        saida.append(f"Vizinha Gaia brilhante a menos de 42\": precisaria variar "
                     f"{r['amp_necessaria_min'] * 100:.0f}% para gerar o sinal.")
    if r.get("n_ciclos") is not None and pd.notna(r["n_ciclos"]) and r["n_ciclos"] < 4:
        saida.append(f"Só {r['n_ciclos']:.1f} ciclos no setor: período pouco preciso.")
    if r.get("persistente") is None or pd.isna(r.get("persistente")):
        saida.append("Sem outro setor para confirmar que o sinal se repete.")
    if _sim(r.get("gaia_candidata")):
        saida.append(f"Gaia DR3 já lista como candidata a variável ({r.get('gaia_classe')}). "
                     "Ainda dá para submeter, mas o mérito é menor.")
    return saida


def links(ra: float, dec: float, tic: int) -> dict[str, str]:
    coord = quote(f"{ra:.6f} {dec:+.6f}")
    return {
        "VSX (2')": f"https://www.aavso.org/vsx/index.php?view=results.get&coords={coord}"
                    f"&format=d&size=2&unit=2",
        "SIMBAD (1')": f"https://simbad.cds.unistra.fr/simbad/sim-coo?Coord={coord}"
                       f"&Radius=1&Radius.unit=arcmin",
        "Aladin (DSS2)": f"https://aladin.cds.unistra.fr/AladinLite/?target={coord}"
                         f"&fov=0.1&survey=P%2FDSS2%2Fcolor",
        "ExoFOP": f"https://exofop.ipac.caltech.edu/tess/target.php?id={tic}",
    }
