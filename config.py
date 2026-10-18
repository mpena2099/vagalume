from pathlib import Path

ROOT = Path(__file__).parent
SQLITE_PATH = ROOT / "data" / "vagalume.db"
CURVAS_DIR = ROOT / "data" / "curvas"
IMG_DIR = ROOT / "docs" / "img"

# Ordem de preferencia dos produtos de curva de luz no MAST (coluna author)
AUTORES_PREFERIDOS = ["QLP", "TESS-SPOC", "SPOC"]

# Grade de busca de periodo
PERIODO_MIN_D = 0.1
PERIODO_MAX_D = 13.0
BLS_DURACOES_D = [0.04, 0.08, 0.16]

# Fase 2: campo no plano da Via Lactea (Cygnus, l=80 b=0), setor com 200 s de cadencia
ALVO_SETOR = 55
ALVO_RA_DEG = 308.9712
ALVO_DEC_DEG = 40.6636
ALVO_RAIO_DEG = 1.0
ALVO_TMAG_MIN = 9
ALVO_TMAG_MAX = 13.5
ALVO_CONTRATIO_MAX = 0.2
ALVO_MAX = 500
ALVO_SEMENTE = 42

# Fase 1 — sanity check targets
SANITY_TARGETS = {
    # Shporer et al. 2019
    "WASP_18b": {
        "tic": 100100827,
        "periodo_ref_d": 0.9414526,
        "metodo": "bls",
        "tolerancia_rel": 0.001,
        "figura": False,
    },
    # TESS-EBs (Prsa et al. 2022, VizieR J/ApJS/258/16), Tmag 11.62, destacada
    "EB_DESTACADA": {
        "tic": 142979644,
        "periodo_ref_d": 4.1790314,
        "metodo": "bls",
        "tolerancia_rel": 0.001,
        "figura": True,
    },
    # TESS-EBs, Tmag 11.80, contato
    "EB_CONTATO": {
        "tic": 121213501,
        "periodo_ref_d": 0.4738341,
        "metodo": "ls",
        "tolerancia_rel": 0.001,
        "figura": False,
    },
}
