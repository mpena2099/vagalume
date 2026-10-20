"""Gera as figuras de referencia da revisao (docs/img/ref_*.jpg) com a mesma figura da Fase 7.

Os casos sao variaveis ja catalogadas (VSX) e sinais descartados pela Fase 6, nunca as
candidatas: candidata no README publico seria entregar a descoberta antes da submissao.
Usa rede (MAST, TESScut, VizieR) e o banco da varredura. Rodar da raiz do repositorio:

    python -u tools/gerar_referencias.py
"""

import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
from PIL import Image

from config import IMG_DIR, SQLITE_PATH, TREINO_DIR
from src.triagem import _triar

# nome do arquivo -> (tic, metodo, tabela de onde vem o sinal)
CASOS = {
    "confirmar_eb_2p": (64796843, "ls", "sinais_fase5"),
    "confirmar_ea": (64412402, "bls", "sinais_fase5"),
    "confirmar_pulsante": (17453401, "ls", "sinais_fase5"),
    "duvida_poucos_ciclos": (65121604, "bls", "sinais_fase5"),
    "descartar_vizinha": (63458827, "ls", "candidatos"),
    "descartar_nao_persiste": (17128693, "ls", "candidatos"),
}


def _sinal(con, tic: int, metodo: str, tabela: str) -> SimpleNamespace:
    if tabela == "sinais_fase5":
        q = ("SELECT s.*, a.autor FROM sinais_fase5 s JOIN alvos a USING (tic) "
             "WHERE s.tic = ? AND s.metodo = ?")
    else:
        q = "SELECT * FROM candidatos WHERE tic = ? AND metodo = ?"
    linha = pd.read_sql(q, con, params=(tic, metodo))
    if linha.empty:
        raise ValueError(f"TIC {tic} {metodo} nao esta em {tabela}")
    return SimpleNamespace(**linha.iloc[0].to_dict())


def main():
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(SQLITE_PATH) as con:
        for nome, (tic, metodo, tabela) in CASOS.items():
            figura = Path(_triar(_sinal(con, tic, metodo, tabela), TREINO_DIR, f"ref_{nome}")["figura"])
            saida = IMG_DIR / f"ref_{nome}.jpg"
            img = Image.open(figura).convert("RGB")
            img.thumbnail((1200, 1200))
            img.save(saida, quality=85)
            print(f"salvo {saida}")


if __name__ == "__main__":
    main()
