import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from src.sanity_check import run as fase1
from src.selecionar_alvos import run as fase2
from src.baixar_curvas import run as fase3
from src.detectar_sinal import run as fase4
from src.cruzar_conhecidos import run as fase5
from src.checar_contaminacao import run as fase6
from src.triagem import run as fase7


def run_all():
    fases = [
        ("Fase 1 - Sanity check", fase1),
        ("Fase 2 - Selecionar alvos", fase2),
        ("Fase 3 - Baixar curvas", fase3),
        ("Fase 4 - Detectar sinal", fase4),
        ("Fase 5 - Cruzar conhecidos", fase5),
        ("Fase 6 - Checar contaminacao", fase6),
        ("Fase 7 - Triagem", fase7),
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


if __name__ == "__main__":
    run_all()
