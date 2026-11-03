"""Gera demo/, os dados da demo online (app/demo.py): demo/treino_demo.db com a tabela
`treino` (sem os casos ambiguos, que ficam fora do quiz) e as figuras que o treino mostra
(paineis p, mapa e 2p, mais o .json de cada caso), com caminho relativo a raiz. Le o banco
real e data/treino/, sem rede. Rodar da raiz:

    python -u tools/gerar_demo.py
"""

import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from config import SQLITE_PATH

DESTINO = ROOT / "demo"
FIGURAS = DESTINO / "treino"

with sqlite3.connect(str(SQLITE_PATH)) as conn:
    treino = pd.read_sql("SELECT * FROM treino WHERE resposta != 'ambiguo'", conn)
shutil.rmtree(FIGURAS, ignore_errors=True)
FIGURAS.mkdir(parents=True)
novas = []
for f in treino["figura"]:
    f = Path(f)
    for nome in (f"{f.stem}_p.png", f"{f.stem}_mapa.png", f"{f.stem}_2p.png", f"{f.stem}.json"):
        if (f.parent / nome).exists():
            shutil.copy2(f.parent / nome, FIGURAS / nome)
    novas.append(str((FIGURAS / f.name).relative_to(ROOT)))
treino["figura"] = novas
banco = DESTINO / "treino_demo.db"
banco.unlink(missing_ok=True)
with sqlite3.connect(str(banco)) as conn:
    treino.to_sql("treino", conn, index=False)
tamanho = sum(p.stat().st_size for p in DESTINO.rglob("*") if p.is_file()) // 1024
print(f"{len(treino)} casos em {banco}; demo/ com {tamanho} KB")
