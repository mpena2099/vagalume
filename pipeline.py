import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from config import ALVO_DEC_DEG, ALVO_RA_DEG, ALVO_SETOR, SQLITE_PATH
from src import campos
from src.sanity_check import run as fase1
from src.selecionar_alvos import run as fase2
from src.baixar_curvas import run as fase3
from src.detectar_sinal import run as fase4
from src.cruzar_conhecidos import run as fase5
from src.checar_contaminacao import run as fase6
from src.triagem import run as fase7
from tools.gerar_treino import main as gerar_treino


def run_all(campo: dict | None = None):
    alvos = {}
    fases = [
        ("Fase 1 - Sanity check", fase1),
        ("Fase 2 - Selecionar alvos", lambda: alvos.update(n=fase2(campo))),
        ("Fase 3 - Baixar curvas", fase3),
        ("Fase 4 - Detectar sinal", fase4),
        ("Fase 5 - Cruzar conhecidos", fase5),
        ("Fase 6 - Checar contaminacao", fase6),
        ("Fase 7 - Triagem", fase7),
        ("Casos novos para o treino", gerar_treino),
    ]

    for nome, fn in fases:
        print(f"\n{'=' * 60}")
        print(f"  Executando: {nome}")
        print(f"{'=' * 60}")
        try:
            fn()
        except Exception as e:
            print(f"\nERRO em {nome}: {e}")
            sys.exit(1)

    # so campo completo entra em campos_feitos: o que falhou volta na proxima rodada
    feito = campo or {"nome": f"inicial_s{ALVO_SETOR}", "setor": ALVO_SETOR,
                      "ra": ALVO_RA_DEG, "dec": ALVO_DEC_DEG}
    with sqlite3.connect(SQLITE_PATH) as con:
        campos.registrar(con, feito, alvos.get("n"))
    print(f"\n  Campo {feito['nome']} registrado em campos_feitos.")
    print("  Revisao: streamlit run app/revisao.py")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Pipeline do Vagalume (fases 1 a 7 e treino)")
    ap.add_argument("--proximo", action="store_true",
                    help="escolhe sozinho o proximo campo do ceu ainda nao varrido")
    a = ap.parse_args()
    campo = None
    if a.proximo:
        with sqlite3.connect(SQLITE_PATH) as con:
            feitos = campos.ler_feitos(con)
        print(f"  {len(feitos)} campo(s) ja feito(s). Procurando o proximo...")
        campo = campos.proximo(feitos, campos.setores_tesscut)
        if campo is None:
            print("  A grade de campos acabou: todos os pontos de src/campos.py foram varridos. "
                  "Para continuar, acrescente faixas em FAIXAS_B_DEG.")
            sys.exit(0)
        print(f"  Proximo campo: {campo['nome']} (RA {campo['ra']}, Dec {campo['dec']}, "
              f"setor {campo['setor']})")
    run_all(campo)
