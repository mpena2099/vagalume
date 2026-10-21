"""Proximo campo do ceu a varrer: o pipeline escolhe sozinho, sem lista fixa.

Grade no plano da Via Lactea (muitas estrelas por campo), ordenada a partir de Cygnus
(l=80): primeiro b=0, depois faixas cada vez mais longe do plano. Pula ponto a menos de
SEPARACAO_MIN_DEG de um campo ja feito (campos de 1 grau de raio nao se sobrepoem) e ponto
sem setor do TESS com cadencia de 200 s (setor >= SETOR_MIN). Os campos feitos ficam na
tabela campos_feitos; campo que falha no meio nao e gravado e volta na proxima rodada.

    python -u pipeline.py --proximo
"""

import sqlite3
from datetime import datetime

import numpy as np
from astropy.coordinates import SkyCoord

# FFIs de 200 s comecam na 2a missao estendida; o setor 55 do campo inicial ja tem
SETOR_MIN = 55
PASSO_L_DEG = 2.5
FAIXAS_B_DEG = (0, 3, -3, 6, -6, 9, -9)
L_INICIO_DEG = 80.0
SEPARACAO_MIN_DEG = 2.0

_SCHEMA = """
CREATE TABLE IF NOT EXISTS campos_feitos (
    nome TEXT PRIMARY KEY,
    setor INTEGER NOT NULL,
    ra REAL NOT NULL,
    dec REAL NOT NULL,
    alvos INTEGER,
    feito_em TEXT NOT NULL
)"""


def grade() -> list[tuple[float, float]]:
    """(l, b) na ordem de visita: faixa por faixa, do mais perto ao mais longe de l=80."""
    pontos = []
    for b in FAIXAS_B_DEG:
        ls = np.arange(0, 360, PASSO_L_DEG)
        dist = np.abs((ls - L_INICIO_DEG + 180) % 360 - 180)
        pontos += [(float(l), float(b)) for l in ls[np.argsort(dist, kind="stable")]]
    return pontos


def ler_feitos(con: sqlite3.Connection) -> list[dict]:
    con.execute(_SCHEMA)
    cur = con.execute("SELECT nome, setor, ra, dec FROM campos_feitos")
    return [dict(zip(("nome", "setor", "ra", "dec"), linha)) for linha in cur]


def registrar(con: sqlite3.Connection, campo: dict, alvos: int | None) -> None:
    con.execute(_SCHEMA)
    con.execute("INSERT OR REPLACE INTO campos_feitos VALUES (?, ?, ?, ?, ?, ?)",
                (campo["nome"], int(campo["setor"]), float(campo["ra"]), float(campo["dec"]),
                 alvos, datetime.now().isoformat(timespec="seconds")))
    con.commit()


def proximo(feitos: list[dict], setores_de) -> dict | None:
    """Primeiro ponto da grade longe dos feitos e com setor >= SETOR_MIN; None se acabou.

    setores_de(SkyCoord) -> lista de setores (TESScut na rodada real, falso nos testes).
    """
    usados = (SkyCoord([f["ra"] for f in feitos], [f["dec"] for f in feitos], unit="deg")
              if feitos else None)
    for l, b in grade():
        c = SkyCoord(l=l, b=b, unit="deg", frame="galactic").icrs
        if usados is not None and c.separation(usados).deg.min() < SEPARACAO_MIN_DEG:
            continue
        setores = sorted(s for s in setores_de(c) if s >= SETOR_MIN)
        if not setores:
            continue
        return {"nome": f"l{l:05.1f}b{b:+.0f}_s{setores[0]}", "setor": setores[0],
                "ra": round(float(c.ra.deg), 4), "dec": round(float(c.dec.deg), 4)}
    return None


def setores_tesscut(c: SkyCoord) -> list[int]:
    from astroquery.mast import Tesscut

    from src.util import retry
    return [int(s) for s in retry(lambda: Tesscut.get_sectors(coordinates=c), "TESScut")["sector"]]
