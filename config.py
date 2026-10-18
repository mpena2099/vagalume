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

# Fase 3: downloads em paralelo no MAST
CURVAS_WORKERS = 6

# Fase 4: cortes para virar sinal
SINAIS_WORKERS = 4
# janelas de flatten: LS mais longa para preservar periodos de ate ~4 d
LS_FLATTEN_D = 4.0
BLS_FLATTEN_D = 1.5
LS_FAP_MAX = 1e-4
BLS_SNR_MIN = 10
N_CICLOS_MIN = 2
# amplitude pico a pico (LS) ou profundidade (BLS) contra o ruido ponto a ponto
AMP_RUIDO_MIN = 3
# orbita do TESS (13,7 d), harmonicos e ~1 d
PERIODOS_SISTEMATICOS_D = [13.7, 6.85, 4.57, 1.0]
SISTEMATICO_TOL_REL = 0.03

# Fase 5: cross-match com catalogos de variaveis conhecidas
RAIO_MATCH_ARCSEC = 30
RAIO_MESMA_ESTRELA_ARCSEC = 10
PERIODO_MATCH_TOL_REL = 0.01
TOI_URL = "https://exofop.ipac.caltech.edu/tess/download_toi.php?sort=toi&output=csv"
TOI_PATH = ROOT / "data" / "toi.csv"
# catalogo VizieR -> (nome curto, coluna de periodo ou None)
CATALOGOS_VIZIER = {
    "B/vsx/vsx": ("VSX", "Period"),
    "J/ApJS/258/16": ("TESS-EBs", "Per"),
    "J/ApJS/249/18": ("ZTF", "Per"),
    "II/366": ("ASAS-SN", "Per"),
}
# Gaia DR3 nao bloqueia submissao ao VSX, so reduz o merito
CATALOGOS_GAIA = {
    "I/358/vclassre": "Gaia-classe",
    "I/358/veb": "Gaia-EB",
}
# Fase 6: contaminacao e persistencia
RAIO_VIZINHA_VARIAVEL_ARCSEC = 120
RAIO_VIZINHA_GAIA_ARCSEC = 42
VIZINHA_DMAG_MAX = 4
# amplitude intrinseca que a vizinha precisaria ter; abaixo disso o blend e plausivel
BLEND_AMP_MAX = 0.5
PERSISTENCIA_MAX_SETORES = 2
CONTAMINACAO_WORKERS = 4

# Fase 7: triagem (figuras por candidata) e revisao no app/revisao.py
TRIAGEM_DIR = ROOT / "data" / "triagem"
TRIAGEM_RECORTE_PX = 11
# pico do mapa de amplitude a mais que isso do alvo sugere outra fonte
DESLOCAMENTO_MAX_PX = 1.0

# tipos de objeto do SIMBAD que indicam variavel
SIMBAD_VARIAVEIS = {"V*", "Pu*", "EB*", "RR*", "Ce*", "cC*", "dS*", "gD*", "BY*", "RS*",
                    "Ro*", "Mi*", "LP*", "sr*", "Ir*", "Er*", "Fl*", "El*", "a2*", "bC*",
                    "sv*", "WV*", "RV*", "ZZ*", "BE*", "Or*", "CV*", "No*", "XB*"}

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
