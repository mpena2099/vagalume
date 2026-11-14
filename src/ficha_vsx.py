"""Fase 8: ficha de submissao ao VSX para as candidatas confirmadas na revisao.

Manual, como a revisao: nao entra no pipeline.py. Para cada estrela, junta o que o
formulario do VSX pede (checklist na secao 11 da especificacao): fonte Gaia DR3, magnitude V
estimada, periodo sugerido (P ou 2P), tipo sugerido, epoca do minimo em BJD, amplitude em
magnitude TESS e uma nova busca no VizieR inteiro. O VSX nao tem API: os campos sao copiados
a mao para o New Star Wizard. Tipo e periodo sao sugestoes, conferir na figura.

    python src/ficha_vsx.py              # confirmadas
    python src/ficha_vsx.py --duvidas    # confirmadas e duvidas
    python src/ficha_vsx.py --todas      # todas as candidatas da Fase 7 (antes da revisao)
    python src/ficha_vsx.py --refazer    # ignora fichas.csv e refaz tudo (combina com os outros)

Rodar de novo retoma: ficha pronta e mantida e ficha incompleta refaz so a busca que faltou.
"""

import argparse
import sqlite3
import sys
import time
import warnings
from pathlib import Path

# aviso inofensivo do lightkurve (oktopus nao instalado); tem de vir antes do import dele
warnings.filterwarnings("ignore", message=".*tpfmodel submodule.*", category=UserWarning,
                        module=r"lightkurve.*")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import astropy.units as u
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from astropy.coordinates import SkyCoord
from astroquery.vizier import Vizier

from app.dados import carregar_candidatos
from config import (BLEND_AMP_MAX, BLS_FLATTEN_D, CATALOGOS_VARIAVEIS_ESPELHO, LS_FLATTEN_D,
                    MARCA_PODE_SUBMETER, RAIO_VIZINHA_GAIA_ARCSEC, SQLITE_PATH, VIZINHA_DMAG_MAX,
                    VSX_DIR)
from src.curvas import baixar_curva
from src.detectar_sinal import _arrays, _flatten
from src.checar_contaminacao import amp_necessaria
from src.periodo_setores import medir_periodo_setores, oc_setores
from src import util
from src.util import retry

BTJD_PARA_BJD = 2457000.0
# Gaia e VizieR inteiro nao podem segurar a rodada: poucas tentativas e prazo curto
CONSULTA_TENTATIVAS = 2
CONSULTA_TIMEOUT_S = 90
AVISO_VIZIER = ("Busca em todos os catálogos do VizieR não feita (servidor sem resposta). Ela "
                "acha artigos que já publicaram a estrela e que a Fase 5 não cobre. Não submeta "
                "antes de rodar a Fase 8 de novo com o VizieR respondendo ou de conferir à mão: "
                "busque as coordenadas desta ficha com raio de 30\" em vizier.cds.unistra.fr ou "
                "em vizier.idia.ac.za.")
AVISO_VIZIER_LISTA = (f"Busca no VizieR feita nos {len(CATALOGOS_VARIAVEIS_ESPELHO)} principais "
                      "catálogos de variáveis, não em todos (o VizieR de Estrasburgo estava fora "
                      f"e o espelho não faz a busca completa). {MARCA_PODE_SUBMETER} assim. "
                      "Opcional: quando o VizieR voltar, rodar a Fase 8 de novo faz a busca "
                      "completa, que cobre também catálogos pequenos.")
AVISO_GAIA = ("Fonte Gaia DR3 não obtida (servidor sem resposta): posição, V estimada e nome "
              "Gaia ficam em branco; confira à mão no Gaia ou no VizieR antes de submeter.")
# Descricao de catalogo VizieR que indica variabilidade: onde a estrela pode ter entrado
# depois da varredura (a Fase 5 cobre so a lista fixa dela)
PALAVRAS_VARIAVEL = ("variab", "eclips", "binar", "periodic", "pulsat", "rotation",
                     "light curve", "light-curve")


def v_de_gaia(g: float, bp_rp: float) -> float:
    """Magnitude V a partir de G e BP-RP (Riello+2021, valida para -0,5 < BP-RP < 5)."""
    c = bp_rp
    return g - (-0.02704 + 0.01424 * c - 0.2156 * c ** 2 + 0.01426 * c ** 3)


def curva_binada(tempo: np.ndarray, fluxo: np.ndarray, periodo: float, n_bins: int):
    """Medianas e erro da mediana por bin de fase (fase 0 = primeiro ponto)."""
    fase = ((tempo - tempo.min()) / periodo) % 1
    idx = np.minimum((fase * n_bins).astype(int), n_bins - 1)
    med = np.array([np.nanmedian(fluxo[idx == k]) if np.any(idx == k) else np.nan
                    for k in range(n_bins)])
    ruido = 1.4826 * np.nanmedian(np.abs(fluxo - np.nanmedian(fluxo)))
    n = np.bincount(idx, minlength=n_bins)
    return med, ruido / np.sqrt(np.maximum(n, 1))


def amplitude_dobrada_mag(tempo: np.ndarray, fluxo: np.ndarray, periodo: float,
                          n_bins: int = 200) -> float:
    """Pico a pico da curva dobrada, em magnitude. Bins finos: eclipse estreito some em 50 bins
    (a amplitude do LS da Fase 4 dava 0,008 mag para eclipses de 0,28 mag)."""
    med, _ = curva_binada(tempo, fluxo, periodo, n_bins)
    return float(2.5 * np.log10(np.nanmax(med) / np.nanmin(med)))


def fracao_variando(tempo: np.ndarray, fluxo: np.ndarray, periodo: float,
                    n_bins: int = 200) -> float:
    """Fracao da fase em que o brilho cai mais de 10% da amplitude abaixo do nivel de topo.
    Pequena (eclipses estreitos e brilho plano no resto) indica binaria destacada (EA)."""
    med, _ = curva_binada(tempo, fluxo, periodo, n_bins)
    topo = np.nanpercentile(med, 90)
    return float(np.nanmean(topo - med > 0.1 * (topo - np.nanmin(med))))


def profundidades_minimos(tempo: np.ndarray, fluxo: np.ndarray, periodo2: float,
                          n_bins: int = 40) -> tuple[float, float, float]:
    """Curva dobrada em `periodo2` (2P): profundidade do minimo mais fundo, do minimo perto da
    fase oposta e o erro da diferenca entre os dois."""
    med, erro = curva_binada(tempo, fluxo, periodo2, n_bins)
    base = np.nanmedian(med)
    k1 = int(np.nanargmin(med))
    perto = [(k1 + n_bins // 2 + d) % n_bins for d in range(-n_bins // 10, n_bins // 10 + 1)]
    k2 = perto[int(np.nanargmin(med[perto]))]
    return float(base - med[k1]), float(base - med[k2]), float(np.hypot(erro[k1], erro[k2]))


def sugerir(metodo: str, periodo: float, tempo: np.ndarray, fluxo: np.ndarray,
            n_bins: int = 40) -> tuple[float, str, str]:
    """(periodo, tipo VSX sugerido, motivo). Binaria no LS costuma sair com metade do periodo."""
    if metodo == "bls":
        return periodo, "EA", "eclipses curtos achados pelo BLS"
    if fracao_variando(tempo, fluxo, 2 * periodo) < 0.3:
        return (2 * periodo, "EA",
                "dobrada em 2P, dois eclipses estreitos e brilho plano entre eles: o periodo real e 2P")
    p1, p2, sigma = profundidades_minimos(tempo, fluxo, 2 * periodo, n_bins)
    diferenca = abs(p1 - p2)
    if diferenca > 3 * sigma and diferenca > 0.15 * p1:
        return (2 * periodo, "EB",
                f"dobrada em 2P, os minimos diferem ({p1:.4f} x {p2:.4f}) e o brilho varia o tempo "
                "todo: o periodo real e 2P")
    return (periodo, "ROT, EW ou pulsante",
            "minimos iguais em 2P: senoide com o periodo do LS (ROT/pulsante) ou EW com 2P; "
            "decidir pela forma da curva")


def epoca_minimo(tempo: np.ndarray, fluxo: np.ndarray, periodo: float, n_bins: int = 50) -> float:
    """Instante de minimo (mesma escala de `tempo`) mais perto do meio dos dados."""
    med, _ = curva_binada(tempo, fluxo, periodo, n_bins)
    t0 = tempo.min() + (np.nanargmin(med) + 0.5) / n_bins * periodo
    meio = (tempo.min() + tempo.max()) / 2
    return t0 + round((meio - t0) / periodo) * periodo


def eh_catalogo_variavel(descricao: str) -> bool:
    d = descricao.lower()
    # "Variability Upper Limits for Non-Variable Sources" casa com "variab" e diz o contrario
    return "non-variable" not in d and any(p in d for p in PALAVRAS_VARIAVEL)

PIXEL_ARCSEC = 21.0
BLEND_TOL_PX = 1.0
BLEND_SEM_CONSULTA = "vizinhas Gaia não consultadas"


def veredito_blend(desloc_px: float | None, suspeitas: list[dict]) -> tuple[str, str]:
    """('ok' | 'atencao' | 'bloqueia', motivo) para o blend. `desloc_px` e a distancia do pico do
    mapa por pixel ao alvo (triagem); `suspeitas`, as vizinhas Gaia que poderiam gerar o sinal
    (dicts com `dist_arcsec` e `dmag`). So ha distancias, sem direcao: o pico "compativel" com
    uma vizinha e o que fica a distancia dela do alvo, com folga de 1 px. Vizinha a menos de 1 px
    nao se separa do alvo no pixel do TESS."""
    if not suspeitas:
        return "ok", "sem vizinha Gaia que explique o sinal"
    perto = min(suspeitas, key=lambda v: v["dist_arcsec"])
    if perto["dist_arcsec"] < PIXEL_ARCSEC:
        return ("atencao", f"vizinha Gaia a {perto['dist_arcsec']:.0f}\" (menos de 1 px) do alvo, "
                           f"G {perto['dmag']:+.1f} mag: o pixel não separa os dois")
    if desloc_px is None or not np.isfinite(desloc_px):
        return "atencao", "sem o deslocamento do pico no mapa por pixel para comparar com a vizinha"
    if desloc_px < BLEND_TOL_PX:
        return ("ok", f"pico no alvo ({desloc_px:.1f} px); vizinha a "
                      f"{perto['dist_arcsec']:.0f}\" não explica o sinal")
    compativeis = [v for v in suspeitas
                   if abs(v["dist_arcsec"] / PIXEL_ARCSEC - desloc_px) <= BLEND_TOL_PX]
    if compativeis:
        v = min(compativeis, key=lambda v: abs(v["dist_arcsec"] / PIXEL_ARCSEC - desloc_px))
        return ("bloqueia", f"sinal parece da vizinha: pico a {desloc_px:.1f} px do alvo, vizinha "
                            f"Gaia a {v['dist_arcsec']:.0f}\" ({v['dist_arcsec'] / PIXEL_ARCSEC:.1f} px), "
                            f"G {v['dmag']:+.1f} mag")
    return ("atencao", f"pico a {desloc_px:.1f} px do alvo não bate com nenhuma vizinha suspeita "
                       f"(a mais próxima está a {perto['dist_arcsec']:.0f}\"): confira o mapa")


def vizinhas_suspeitas(tabela: pd.DataFrame, alvo: SkyCoord, g_alvo: float,
                       amplitude: float) -> list[dict]:
    """Vizinhas Gaia (colunas RA_ICRS, DE_ICRS, Gmag) que pelo criterio da Fase 6 poderiam gerar
    o sinal: mais fracas ate VIZINHA_DMAG_MAX e com amplitude intrinseca necessaria abaixo de
    BLEND_AMP_MAX."""
    if tabela.empty:
        return []
    t = tabela.dropna(subset=["Gmag"]).copy()
    t["dist"] = alvo.separation(SkyCoord(t["RA_ICRS"].to_numpy(), t["DE_ICRS"].to_numpy(),
                                         unit="deg")).arcsec
    t = t[(t["dist"] > 1) & (t["Gmag"] < g_alvo + VIZINHA_DMAG_MAX) & (t["Gmag"] != g_alvo)]
    achadas = []
    for _, v in t.iterrows():
        dmag = float(v["Gmag"] - g_alvo)
        if amp_necessaria(amplitude, dmag) < BLEND_AMP_MAX:
            achadas.append({"dist_arcsec": float(v["dist"]), "dmag": dmag})
    return achadas


def razao_harmonicos(tempo: np.ndarray, fluxo: np.ndarray, periodo: float) -> float:
    """Amplitude do 2o harmonico sobre a do 1o, ajustados em `periodo`. Perto de 0: onda unica."""
    x = 2 * np.pi * (tempo - tempo.mean()) / periodo
    a = np.column_stack([np.ones_like(x), np.cos(x), np.sin(x), np.cos(2 * x), np.sin(2 * x)])
    c, *_ = np.linalg.lstsq(a, fluxo, rcond=None)
    return float(np.hypot(c[3], c[4]) / max(np.hypot(c[1], c[2]), 1e-12))


def tipo_provavel(periodo_d: float, teff: float | None, minimos_iguais: bool,
                  onda_unica: bool, logg: float | None = None) -> tuple[str | None, str]:
    """(tipo, motivo). Sugere so com evidencia direta: cada regra exige periodo, Teff do Gaia DR3
    e (EW, ROT) a forma da curva. Duas regras que valem juntas, Teff ou logg ausente ou nenhuma
    regra: sem sugestao. `periodo_d` e o da ficha (o do LS para o tipo ambiguo, 2P = 2x ele)."""
    if teff is None or not np.isfinite(teff):
        return None, "sem sugestão: o Gaia DR3 não tem Teff desta estrela"
    if logg is not None and np.isfinite(logg) and logg < 3.0:
        return None, f"sem sugestão: logg {logg:.1f} (gigante), as regras são para anãs"
    p, dp = periodo_d, 2 * periodo_d
    regras = []
    if p < 0.25 and teff > 6500:
        regras.append(("DSCT", f"P {p:.3f} d < 0,25 d e Teff {teff:.0f} K > 6500 K"))
    if teff > 10000 and 0.3 <= p <= 3:
        regras.append(("SPB", f"Teff {teff:.0f} K > 10000 K e P {p:.2f} d entre 0,3 e 3 d"))
    if 6800 <= teff <= 7800 and 0.3 <= p <= 3:
        regras.append(("GDOR", f"Teff {teff:.0f} K entre 6800 e 7800 K e P {p:.2f} d entre 0,3 e 3 d"))
    if teff < 6000 and onda_unica and p > 0.5:
        regras.append(("ROT", f"Teff {teff:.0f} K < 6000 K, onda única e P {p:.2f} d > 0,5 d"))
    if minimos_iguais and 0.2 <= dp <= 1 and 4000 <= teff <= 7000:
        regras.append(("EW", f"dobrada em 2P ({dp:.3f} d) os dois mínimos são iguais, a curva é "
                             f"contínua e Teff {teff:.0f} K"))
    if len(regras) == 1:
        return regras[0]
    if not regras:
        return None, f"sem sugestão: Teff {teff:.0f} K e P {p:.3f} d não bastam para escolher"
    return None, ("sem sugestão: evidências em conflito (" + " x ".join(r[0] for r in regras) + ")")


def formatar_oc(rotulos, oc_fase) -> str:
    return ", ".join(f"{r} {o:+.3f}" for r, o in zip(rotulos, oc_fase))


def aplicar_oc(ficha: dict, oc: dict) -> dict:
    """Passa o resultado de `oc_setores` para a ficha: com os setores alinhados o alerta some e
    periodo, erro e epoca sao os do ajuste; senao o alerta ganha o O-C de cada setor. Devolve o
    dict `ficha` alterado."""
    texto = formatar_oc(oc["setores"], oc["oc_fase"])
    if oc["alinhado"] is None:
        ficha["oc_fases"] = "um setor"
        ficha["oc_max_fase"] = np.nan
        return ficha
    ficha["oc_fases"] = texto
    ficha["oc_max_fase"] = oc["oc_max_fase"]
    if oc["alinhado"]:
        ficha["alerta_periodo"] = ""
        ficha["periodo_d"] = oc["periodo_d"]
        ficha["periodo_erro_d"] = oc["periodo_erro_d"]
        ficha["epoca_bjd"] = oc["epoca"] + BTJD_PARA_BJD
    else:
        ficha["alerta_periodo"] = ("periodos dos setores nao alinham (O-C em fase por setor: "
                                   f"{texto}): conferir a figura")
    return ficha


def _gaia(alvo: SkyCoord) -> dict:
    res = retry(lambda: Vizier(columns=["Source", "RA_ICRS", "DE_ICRS", "Gmag", "BP-RP", "_r"],
                               row_limit=-1, timeout=CONSULTA_TIMEOUT_S)
                .query_region(alvo, radius=5 * u.arcsec, catalog="I/355/gaiadr3"),
                "VizieR", retries=CONSULTA_TENTATIVAS)
    if not len(res):
        return {}
    t = res[0].to_pandas().dropna(subset=["Gmag"])
    # o alvo e a fonte mais brilhante a ate 3" (G costuma ficar ~0,5 acima de T)
    t = t[t["_r"] < 3].sort_values("Gmag")
    if t.empty:
        return {}
    # Source antes do iloc: a linha mista vira float64 e o ID de 19 digitos perde os ultimos
    fonte = int(t["Source"].iloc[0])
    g = t.iloc[0]
    v = v_de_gaia(g["Gmag"], g["BP-RP"]) if pd.notna(g["BP-RP"]) else np.nan
    return {"gaia_dr3": fonte, "gaia_ra": float(g["RA_ICRS"]),
            "gaia_dec": float(g["DE_ICRS"]), "gaia_g": float(g["Gmag"]), "v_estimada": float(v),
            "gaia_sep_arcsec": float(g["_r"])}


def _vizier(alvo: SkyCoord) -> list[str]:
    """Catalogos de variaveis a ate 30" (o pixel do TESS tem 21")."""
    res = retry(lambda: Vizier(columns=["_r"], row_limit=5, timeout=CONSULTA_TIMEOUT_S)
                .query_region(alvo, radius=30 * u.arcsec), "VizieR", retries=CONSULTA_TENTATIVAS)
    achados = []
    for nome in res.keys():
        descricao = str(res[nome].meta.get("description", ""))
        if eh_catalogo_variavel(descricao):
            achados.append(f'{nome} ({descricao[:70]}) a {float(np.min(res[nome]["_r"])):.1f}"')
    return achados


def _figura(tic: int, tempo, fluxo, periodo: float, epoca: float, saida: Path):
    fase = ((tempo - epoca) / periodo + 0.25) % 1 - 0.25
    mag = -2.5 * np.log10(np.clip(fluxo, 1e-6, None))
    # so pontos, sem linha de mediana: eclipses estreitos (<1% da fase) sumiam na mediana,
    # e a figura vai anexada ao VSX
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(np.concatenate([fase, fase + 1]), np.concatenate([mag, mag]), ".", ms=1.5,
            color="0.3", rasterized=True)
    ax.invert_yaxis()
    ax.set_xlabel(f"fase (P = {periodo:.5f} d, epoca BJD {epoca + BTJD_PARA_BJD:.4f})")
    ax.set_ylabel("delta mag (TESS)")
    ax.set_title(f"TIC {tic}")
    fig.tight_layout()
    fig.savefig(saida, dpi=110)
    plt.close(fig)


def setores_da_candidata(s) -> list[int]:
    """Setor da candidata mais os extras ("41,75"), sem repetir."""
    extras = []
    if pd.notna(s.setores_extra) and str(s.setores_extra).strip():
        extras = [int(float(x)) for x in str(s.setores_extra).replace(";", ",").split(",")
                  if x.strip()]
    return list(dict.fromkeys([int(s.setor), *extras]))


def _carregar_setores(s) -> list[tuple[int, object]]:
    """Curvas cruas por setor. Setor extra sem produto e pulado, nao derruba a ficha."""
    curvas = []
    setores = setores_da_candidata(s)
    print(f"  baixando {len(setores)} setor{'es' if len(setores) != 1 else ''} do TESS...", flush=True)
    for k, setor in enumerate(setores, 1):
        print(f"    setor {setor} ({k}/{len(setores)})", flush=True)
        try:
            lc, _ = baixar_curva(int(s.tic), setor, s.autor)
        except Exception as e:
            print(f"    setor {setor} falhou ({str(e)[:80]}), pulando", flush=True)
            continue
        curvas.append((setor, lc))
    if not curvas:
        raise ValueError("nenhum setor disponivel")
    return curvas


def _juntar(curvas) -> tuple[np.ndarray, np.ndarray]:
    tempo = np.concatenate([t for t, _ in curvas])
    fluxo = np.concatenate([f for _, f in curvas])
    ordem = np.argsort(tempo)
    return tempo[ordem], fluxo[ordem]


def _medir(s) -> dict:
    """Parte local da ficha: curvas, periodo, tipo, epoca, amplitude e figura (sem rede de catalogos)."""
    brutas = _carregar_setores(s)
    print("  medindo o período", flush=True)
    janela = BLS_FLATTEN_D if s.metodo == "bls" else LS_FLATTEN_D
    curvas = [_arrays(_flatten(lc, janela)) for _, lc in brutas]
    tempo, fluxo = _juntar(curvas)
    periodo, tipo, motivo = sugerir(s.metodo, s.periodo_d, tempo, fluxo)
    eclipse = s.metodo == "bls" or tipo in ("EA", "EB")
    if eclipse and janela != BLS_FLATTEN_D:
        curvas = [_arrays(_flatten(lc, BLS_FLATTEN_D)) for _, lc in brutas]
        tempo, fluxo = _juntar(curvas)
    medido = medir_periodo_setores(curvas, periodo, eclipse)
    periodo = medido["periodo_d"]
    epoca = (medido["epoca"] if np.isfinite(medido["epoca"])
             else epoca_minimo(tempo, fluxo, periodo))
    if eclipse and not medido["alerta_periodo"]:
        # o periodo ja vem dos instantes dos eclipses: o tipo sai dele, sem o teste de 2P do
        # sugerir (que dobrava de novo um periodo ja certo e via "EB" onde e EA)
        plano = fracao_variando(tempo, fluxo, periodo) < 0.3
        tipo = "EA" if plano else "EB"
        sec = medido["fase_secundario"]
        motivo = (("eclipses estreitos e brilho plano entre eles" if plano
                   else "brilho varia o tempo todo entre os eclipses")
                  + ("" if sec is None or not np.isfinite(sec)
                     else f"; secundario na fase {sec:.3f}"
                     + (" (orbita excentrica)" if abs(sec - 0.5) > 0.02 else ""))
                  + f"; periodo pelos instantes dos eclipses em {len(brutas)} setores")
    print("  gerando a curva em fase", flush=True)
    figura = VSX_DIR / f"{s.tic}_fase.png"
    _figura(int(s.tic), tempo, fluxo, periodo, epoca, figura)
    ficha = {"tic": int(s.tic), "decisao": s.decisao, "periodo_d": periodo,
            "periodo_erro_d": medido["periodo_erro_d"],
            "alerta_periodo": medido["alerta_periodo"],
            "fase_secundario": medido["fase_secundario"],
            "tipo_sugerido": tipo, "motivo_tipo": motivo, "epoca_bjd": epoca + BTJD_PARA_BJD,
            "amplitude_mag_tess": amplitude_dobrada_mag(tempo, fluxo, periodo),
            "setores": ",".join(str(x) for x in [s.setor, s.setores_extra] if pd.notna(x)),
            "setores_usados": ",".join(str(setor) for setor, _ in brutas),
            "suspeito_blend": bool(s.suspeito_blend), "figura_fase": str(figura),
            "figura_triagem": s.figura}
    _buscar_oc(ficha, s, brutas)
    return ficha


def _buscar_oc(ficha: dict, s, brutas=None) -> None:
    """O-C do minimo por setor com o periodo que a ficha ja escolheu (so curvas em cache)."""
    brutas = brutas or _carregar_setores(s)
    eclipse = s.metodo == "bls" or ficha["tipo_sugerido"] in ("EA", "EB")
    janela = BLS_FLATTEN_D if eclipse else LS_FLATTEN_D
    curvas = [_arrays(_flatten(lc, janela)) for _, lc in brutas]
    oc = oc_setores(curvas, ficha["periodo_d"], eclipse, [setor for setor, _ in brutas],
                    epoca=ficha["epoca_bjd"] - BTJD_PARA_BJD)
    aplicar_oc(ficha, oc)
    print(f"  O-C por setor (fase): {ficha['oc_fases']}"
          + ("" if oc["alinhado"] is None else
             f"; máximo {oc['oc_max_fase']:.3f}, " + ("alinhado" if oc["alinhado"] else "NÃO alinha")),
          flush=True)
    if oc["alinhado"]:
        tempo, fluxo = _juntar(curvas)
        ficha["amplitude_mag_tess"] = amplitude_dobrada_mag(tempo, fluxo, ficha["periodo_d"])
        _figura(int(s.tic), tempo, fluxo, ficha["periodo_d"], ficha["epoca_bjd"] - BTJD_PARA_BJD,
                Path(ficha["figura_fase"]))


def _buscar_gaia(ficha: dict, s) -> str | None:
    """Preenche a fonte Gaia DR3 e o que deriva dela (posicao, G, V estimada). Devolve o aviso
    se o servidor nao respondeu."""
    print("  buscando a fonte no Gaia DR3", flush=True)
    try:
        ficha.update(_gaia(SkyCoord(s.ra, s.dec, unit="deg")))
    except Exception as e:
        print(f"  Gaia sem resposta ({type(e).__name__}); seguindo sem a fonte", flush=True)
        return AVISO_GAIA
    return None


def _vizier_lista(alvo: SkyCoord) -> list[str]:
    """Os catalogos de CATALOGOS_VARIAVEIS_ESPELHO a ate 30", numa consulta so."""
    # ~1 min no espelho, as vezes mais: prazo maior que o das outras consultas
    res = retry(lambda: Vizier(columns=["_r"], row_limit=5, timeout=3 * CONSULTA_TIMEOUT_S)
                .query_region(alvo, radius=30 * u.arcsec, catalog=CATALOGOS_VARIAVEIS_ESPELHO),
                "VizieR", retries=CONSULTA_TENTATIVAS)
    return [f'{nome} ({str(res[nome].meta.get("description", ""))[:70]}) a '
            f'{float(np.min(res[nome]["_r"])):.1f}"' for nome in res.keys()]


def _buscar_vizier(ficha: dict, s) -> str | None:
    """Preenche a busca em todos os catalogos do VizieR. Devolve o aviso se nao respondeu, ou
    o aviso brando se, com o CDS fora, so deu para buscar na lista de catalogos."""
    alvo = SkyCoord(s.ra, s.dec, unit="deg")
    if util.VIZIER_ESPELHO:
        print(f"  VizieR de Estrasburgo fora: buscando nos {len(CATALOGOS_VARIAVEIS_ESPELHO)} "
              f"catálogos de variáveis da lista, em {util.VIZIER_ESPELHO}", flush=True)
        busca, aviso = _vizier_lista, AVISO_VIZIER_LISTA
    else:
        print("  buscando em todos os catálogos do VizieR (pode levar minutos)", flush=True)
        busca, aviso = _vizier, None
    try:
        ficha["vizier_variaveis"] = ("; ".join(busca(alvo))
                                     or "nenhum catalogo de variaveis a 30\"")
    except Exception as e:
        print(f"  VizieR sem resposta ({type(e).__name__}); seguindo sem essa busca", flush=True)
        ficha["vizier_variaveis"] = "busca não feita"
        return AVISO_VIZIER
    return aviso


def _vizinhas_gaia_tabela(alvo: SkyCoord) -> pd.DataFrame:
    res = retry(lambda: Vizier(columns=["Source", "RA_ICRS", "DE_ICRS", "Gmag"], row_limit=-1,
                               timeout=CONSULTA_TIMEOUT_S)
                .query_region(alvo, radius=RAIO_VIZINHA_GAIA_ARCSEC * u.arcsec,
                              catalog="I/355/gaiadr3"), "VizieR", retries=CONSULTA_TENTATIVAS)
    return res[0].to_pandas() if len(res) else pd.DataFrame()


def _buscar_blend(ficha: dict, s) -> None:
    """Veredito do blend: Fase 6 sem vizinha suspeita resolve sem rede; com suspeita, consulta as
    vizinhas Gaia (separacao e delta G) e compara com o deslocamento do pico da triagem."""
    print("  conferindo o blend", flush=True)
    desloc = getattr(s, "deslocamento_px", None)
    if not bool(s.suspeito_blend):
        veredito, motivo = "ok", "a Fase 6 não achou vizinha Gaia que explique o sinal"
    else:
        try:
            g = ficha.get("gaia_g")
            g = float(s.gaia_g) if g is None or pd.isna(g) else float(g)
            alvo = SkyCoord(s.ra, s.dec, unit="deg")
            suspeitas = vizinhas_suspeitas(_vizinhas_gaia_tabela(alvo), alvo, g, float(s.amplitude))
            veredito, motivo = veredito_blend(None if pd.isna(desloc) else float(desloc), suspeitas)
        except Exception as e:
            print(f"  Gaia sem resposta ({type(e).__name__}); blend fica para conferir à mão",
                  flush=True)
            veredito, motivo = "atencao", BLEND_SEM_CONSULTA + ": confira o mapa por pixel"
    ficha["blend_veredito"], ficha["blend_motivo"] = veredito, motivo
    print(f"  blend: {veredito}, {motivo}", flush=True)


def _parametros_gaia(alvo: SkyCoord, fonte: int) -> dict:
    """Teff, logg e raio da fonte: GSP-Phot do I/355/gaiadr3 e, se vazio, I/355/paramp."""
    def linha(catalogo, colunas):
        res = retry(lambda: Vizier(columns=colunas, row_limit=-1, timeout=CONSULTA_TIMEOUT_S)
                    .query_region(alvo, radius=3 * u.arcsec, catalog=catalogo), "VizieR",
                    retries=CONSULTA_TENTATIVAS)
        if not len(res):
            return None
        t = res[0].to_pandas()
        t = t[t["Source"].astype("int64") == fonte]
        return t.iloc[0] if len(t) else None

    def valor(l, *nomes):
        for n in nomes:
            if l is not None and n in l.index and pd.notna(l[n]):
                return float(l[n])
        return np.nan

    g = linha("I/355/gaiadr3", ["Source", "Teff", "logg"])
    teff, logg, raio, origem = valor(g, "Teff"), valor(g, "logg"), np.nan, "gaiadr3"
    p = linha("I/355/paramp", ["Source", "Teff", "logg", "Rad", "Rad-Flame", "Teff-HS", "Teff-S"])
    if not np.isfinite(teff):
        teff = valor(p, "Teff", "Teff-HS", "Teff-S")
        origem = "paramp"
    if not np.isfinite(logg):
        logg = valor(p, "logg")
    raio = valor(p, "Rad-Flame", "Rad")
    return {"gaia_teff": teff, "gaia_logg": logg, "gaia_raio": raio,
            "gaia_params_fonte": origem if np.isfinite(teff) else "sem"}


def _buscar_params(ficha: dict, s) -> None:
    """Teff/logg/raio do Gaia DR3. Sem resposta do servidor a chave fica ausente e a proxima
    rodada tenta de novo; resposta sem Teff grava 'sem'."""
    print("  buscando Teff/logg/raio no Gaia DR3 (gaiadr3, paramp)", flush=True)
    for k in ("gaia_teff", "gaia_logg", "gaia_raio", "gaia_params_fonte"):
        ficha.pop(k, None)
    if "gaia_dr3" not in ficha:
        print("  sem fonte Gaia na ficha; parâmetros ficam para depois", flush=True)
        return
    try:
        ficha.update(_parametros_gaia(SkyCoord(ficha["gaia_ra"], ficha["gaia_dec"], unit="deg"),
                                      int(ficha["gaia_dr3"])))
    except Exception as e:
        print(f"  Gaia sem resposta ({type(e).__name__}); seguindo sem Teff", flush=True)
        return
    print(f"  Teff {ficha['gaia_teff']:.0f} K" if np.isfinite(ficha["gaia_teff"])
          else "  Gaia DR3 sem Teff para esta estrela", flush=True)


def _buscar_tipo(ficha: dict, s) -> None:
    """tipo_provavel/motivo_provavel para o tipo ambiguo (periodo, forma em 2P, Teff do Gaia)."""
    if "," not in str(ficha.get("tipo_sugerido") or ""):
        ficha["tipo_provavel"], ficha["motivo_provavel"] = "", "não se aplica: o tipo já é único"
        return
    print("  procurando o tipo provável", flush=True)
    teff = ficha.get("gaia_teff")
    teff = None if teff is None or pd.isna(teff) else float(teff)
    logg = ficha.get("gaia_logg")
    logg = None if logg is None or pd.isna(logg) else float(logg)
    brutas = _carregar_setores(s)
    tempo, fluxo = _juntar([_arrays(_flatten(lc, LS_FLATTEN_D)) for _, lc in brutas])
    p1, p2, sigma = profundidades_minimos(tempo, fluxo, 2 * ficha["periodo_d"])
    iguais = abs(p1 - p2) < 3 * sigma
    unica = razao_harmonicos(tempo, fluxo, ficha["periodo_d"]) < 0.3
    tipo, motivo = tipo_provavel(ficha["periodo_d"], teff, iguais, unica, logg)
    ficha["tipo_provavel"], ficha["motivo_provavel"] = tipo or "", motivo
    print(f"  tipo provável: {tipo or 'nenhum'} ({motivo})", flush=True)


BUSCAS = {"gaia": _buscar_gaia, "vizier": _buscar_vizier, "oc": _buscar_oc,
          "blend": _buscar_blend, "params": _buscar_params, "tipo": _buscar_tipo}
ORDEM = ("gaia", "vizier", "oc", "blend", "params", "tipo")
NOMES_BUSCA = {"gaia": "fonte Gaia DR3", "vizier": "busca no VizieR", "oc": "O-C dos setores",
               "blend": "blend", "params": "Teff do Gaia DR3", "tipo": "tipo provável"}


def tipo_aviso(aviso: str) -> str | None:
    """'gaia', 'vizier' ou None. Pelo tipo, nao pelo texto exato: fichas antigas tem outra
    redacao do aviso."""
    aviso = aviso.strip()
    if aviso.startswith("Fonte Gaia DR3"):
        return "gaia"
    if aviso.startswith("Busca") and "VizieR" in aviso:
        return "vizier"
    return None


def bloqueia(avisos) -> bool:
    """A ficha tem aviso que impede a submissao (o da busca so na lista de catalogos nao)."""
    return any(a.strip() and MARCA_PODE_SUBMETER not in a for a in str(avisos or "").split(" | "))


def completar_buscas(ficha: dict, s, faltas: list[str]) -> dict:
    """Refaz so as buscas em `faltas` e atualiza `avisos`; o resto da ficha fica como esta."""
    restantes = [a for a in str(ficha.get("avisos") or "").split(" | ")
                 if a and tipo_aviso(a) not in faltas]
    for k in faltas:
        aviso = BUSCAS[k](ficha, s)
        if aviso:
            restantes.append(aviso)
    ficha["avisos"] = " | ".join(restantes)
    return ficha


def montar_ficha(s) -> dict:
    ficha = _medir(s)
    ficha["avisos"] = ""
    return completar_buscas(ficha, s, ["gaia", "vizier", "blend", "params", "tipo"])


def pendente(anterior: dict, busca: str) -> bool:
    """A busca local ou de rede nova ainda nao foi feita (ou ficou sem resposta) nesta ficha."""
    if busca == "oc":
        return "oc_fases" not in anterior
    if busca == "blend":
        return ("blend_veredito" not in anterior
                or str(anterior.get("blend_motivo", "")).startswith(BLEND_SEM_CONSULTA))
    if busca == "params":
        return "gaia_params_fonte" not in anterior and "gaia_dr3" in anterior
    return "motivo_provavel" not in anterior


def plano(anterior: dict | None, refazer: bool = False) -> str:
    """O que fazer com uma estrela: 'nova', 'manter' ou 'completar:<buscas faltantes>'."""
    if anterior is None or refazer:
        return "nova"
    faltas = set()
    for aviso in filter(None, (x.strip() for x in str(anterior.get("avisos") or "").split("|"))):
        tipo = tipo_aviso(aviso)
        if tipo is None:
            return "nova"  # aviso que esta logica nao sabe completar
        faltas.add(tipo)
    faltas |= {k for k in ("oc", "blend", "params") if pendente(anterior, k)}
    if "gaia" in faltas and "gaia_params_fonte" not in anterior:
        faltas.add("params")  # a fonte Gaia vem agora; o Teff e dela
    # o tipo provavel depende do periodo (oc) e do Teff (params)
    if pendente(anterior, "tipo") or faltas & {"oc", "params"}:
        faltas.add("tipo")
    if not faltas:
        return "manter"
    return "completar:" + ",".join(k for k in ORDEM if k in faltas)


NUMERICAS = ["periodo_d", "periodo_erro_d", "fase_secundario", "epoca_bjd", "amplitude_mag_tess",
             "gaia_ra", "gaia_dec", "gaia_g", "v_estimada", "gaia_sep_arcsec", "oc_max_fase",
             "gaia_teff", "gaia_logg", "gaia_raio"]


def ler_fichas(caminho: Path) -> dict[int, dict]:
    """Fichas de rodadas anteriores por tic. Tudo lido como texto (o ID Gaia de 19 digitos nao
    cabe em float) e convertido aqui; coluna vazia vira chave ausente."""
    if not caminho.exists():
        return {}
    try:
        df = pd.read_csv(caminho, dtype=str, keep_default_na=False)
    except Exception:
        return {}
    fichas = {}
    for linha in df.to_dict("records"):
        f = {k: v for k, v in linha.items() if v != ""}
        try:
            f["tic"] = int(f["tic"])
            for k in NUMERICAS:
                if k in f:
                    f[k] = float(f[k])
            if "gaia_dr3" in f:
                f["gaia_dr3"] = int(float(f["gaia_dr3"])) if "e" in f["gaia_dr3"].lower() \
                    else int(f["gaia_dr3"])
            f["suspeito_blend"] = f.get("suspeito_blend", "False") == "True"
            f.setdefault("avisos", "")
            f.setdefault("vizier_variaveis", "")
        except (KeyError, ValueError):
            continue
        fichas[f["tic"]] = f
    return fichas


def _markdown(f: dict) -> str:
    def num(chave, fmt):
        v = f.get(chave)
        return "?" if v is None or pd.isna(v) else format(v, fmt)
    ztf = ("amplitude grande o bastante: juntar a curva do ZTF/ASAS-SN e usar a magnitude deles"
           if f["amplitude_mag_tess"] > 0.05 else "amplitude pequena para o ZTF: so TESS")
    periodo = f"{f['periodo_d']:.5f} d"
    if pd.notna(f.get("periodo_erro_d")):
        periodo += f" +- {f['periodo_erro_d']:.6f}"
    secundario = (f"| Secundario | fase {f['fase_secundario']:.3f} |\n"
                  if pd.notna(f.get("fase_secundario")) else "")
    alerta = f"**Alerta: {f['alerta_periodo']}**\n\n" if f.get("alerta_periodo") else ""
    for aviso in str(f.get("avisos") or "").split(" | "):
        if aviso:
            alerta += f"**Aviso: {aviso}**\n\n"
    blend = (f"- Blend ({f['blend_veredito']}): {f['blend_motivo']}\n"
             if f.get("blend_veredito") else "")
    oc = f"- O-C do mínimo por setor, em fase: {f['oc_fases']}\n" if f.get("oc_fases") else ""
    prov = (f"- Tipo provável: {f['tipo_provavel']} ({f['motivo_provavel']})\n"
            if f.get("tipo_provavel") else
            (f"- Tipo provável: nenhum ({f['motivo_provavel']})\n"
             if "," in str(f.get("tipo_sugerido")) and f.get("motivo_provavel") else ""))
    return f"""## TIC {f['tic']} ({f['decisao']})

{alerta}| Campo do VSX | Valor |
|---|---|
| Posicao (Gaia DR3) | RA {num('gaia_ra', '.6f')}, Dec {num('gaia_dec', '+.6f')} |
| Outros nomes | TIC {f['tic']}, Gaia DR3 {f.get('gaia_dr3', '?')} |
| Tipo (sugestao) | {f['tipo_sugerido']}: {f['motivo_tipo']} |
| Periodo | {periodo} |
{secundario}| Epoca do minimo | BJD {f['epoca_bjd']:.4f} |
| Magnitude maxima | V {num('v_estimada', '.2f')} (estimada de Gaia G {num('gaia_g', '.2f')} e BP-RP) |
| Magnitude minima | {f['amplitude_mag_tess']:.3f}, marcar "Minimum is an amplitude", banda "TESS" |
| Dados | TESS QLP, setores {f.get('setores_usados', f['setores'])} |
| Anexos | `{f['figura_fase']}` (curva em fase) e `{f['figura_triagem']}` |

- VizieR (catalogos de variaveis a 30"): {f['vizier_variaveis']}
- Fonte Gaia escolhida a {num('gaia_sep_arcsec', '.1f')}" do TIC; suspeito_blend: {'sim' if f['suspeito_blend'] else 'nao'}
- {ztf}
{blend}{oc}{prov}"""


def _gravar(fichas: list[dict]) -> Path:
    df = pd.DataFrame(fichas)
    if "gaia_dr3" in df:  # com linhas sem o ID o pandas faria float e perderia os ultimos digitos
        df["gaia_dr3"] = pd.array([f.get("gaia_dr3") for f in fichas], dtype="Int64")
    df.to_csv(VSX_DIR / "fichas.csv", index=False)
    saida = VSX_DIR / "fichas.md"
    saida.write_text("# Fichas para o VSX\n\nChecklist completo na secao 11 de `especificacao.md`. "
                     "Tipo e periodo sao sugestoes: conferir na curva em fase antes de enviar.\n\n"
                     + "\n".join(_markdown(f) for f in fichas), encoding="utf-8")
    return saida


def _tempo(segundos: float) -> str:
    m, s = divmod(int(round(segundos)), 60)
    return f"{m} min {s} s" if m else f"{s} s"


def _caminho(p: Path) -> str:
    try:
        return str(p.relative_to(Path(__file__).resolve().parent.parent))
    except ValueError:
        return str(p)


def run(decisoes=("confirmado",), refazer: bool = False) -> Path | None:
    with sqlite3.connect(SQLITE_PATH) as con:
        cand = carregar_candidatos(con)
    sel = cand if decisoes is None else cand[cand["decisao"].isin(decisoes)]
    if sel.empty:
        print("Nenhuma candidata confirmada. Revise no app (python iniciar.py).")
        return None
    VSX_DIR.mkdir(parents=True, exist_ok=True)
    n = len(sel)
    quais = ("candidatas da Fase 7" if decisoes is None
             else " e ".join("em dúvida" if d == "duvida" else f"{d}s".replace("ados", "adas")
                        for d in decisoes))
    print(f"Fase 8: fichas do VSX de {n} estrela{'s' if n != 1 else ''} ({quais}). "
          "Leva alguns minutos por estrela.", flush=True)
    anteriores = {} if refazer else ler_fichas(VSX_DIR / "fichas.csv")
    if refazer:
        print("--refazer: fichas anteriores ignoradas.", flush=True)
    elif anteriores:
        print(f"{len(anteriores)} ficha(s) de rodadas anteriores em fichas.csv: ficha pronta é "
              "mantida, ficha incompleta só refaz a busca que faltou.", flush=True)
    print("Ctrl+C a qualquer momento: as fichas já prontas ficam salvas.", flush=True)
    tics = [int(t) for t in sel["tic"]]
    # fichas.csv/.md refletem a selecao atual; estrela ainda nao tratada nesta rodada
    # continua com a ficha anterior, para uma interrupcao nao apagar trabalho feito
    atuais: dict[int, dict] = {t: anteriores[t] for t in tics if t in anteriores}
    contagem = {"mantida": 0, "completada": 0, "incompleta": 0, "nova": 0}
    falhas, saida = [], None

    def gravar():
        return _gravar([atuais[t] for t in tics if t in atuais])

    try:
        for i, s in enumerate(sel.itertuples(), 1):
            tic = int(s.tic)
            acao = plano(anteriores.get(tic), refazer)
            if acao == "manter":
                atuais[tic]["decisao"] = s.decisao
                contagem["mantida"] += 1
                print(f"\n[{i}/{n}] TIC {tic}: ficha já pronta, mantida", flush=True)
                continue
            t0 = time.monotonic()
            try:
                if acao.startswith("completar"):
                    faltas = acao.split(":")[1].split(",")
                    print(f"\n[{i}/{n}] TIC {tic}: completando a ficha (faltava: "
                          + ", ".join(NOMES_BUSCA[k] for k in faltas) + ")", flush=True)
                    f = completar_buscas(dict(anteriores[tic]), s, faltas)
                    f["decisao"] = s.decisao
                    contagem["incompleta" if bloqueia(f.get("avisos")) else "completada"] += 1
                else:
                    print(f"\n[{i}/{n}] TIC {tic}", flush=True)
                    f = montar_ficha(s)
                    contagem["nova"] += 1
            except Exception as e:
                print(f"  falhou: {str(e)[:100] or type(e).__name__}. Seguindo para a próxima.",
                      flush=True)
                falhas.append(tic)
                continue
            atuais[tic] = f
            saida = gravar()
            print(f"  {'ainda incompleta' if bloqueia(f.get('avisos')) else 'pronta'}: período {f['periodo_d']:.5f} d, tipo sugerido {f['tipo_sugerido']} "
                  f"({_tempo(time.monotonic() - t0)})", flush=True)
            print(f"    blend: {f.get('blend_veredito')} ({f.get('blend_motivo')})\n"
                  f"    período: {'alerta: ' + f['alerta_periodo'] if f.get('alerta_periodo') else 'consistente'}"
                  f" (O-C máx {f.get('oc_max_fase', float('nan')):.3f} em fase)\n"
                  f"    tipo provável: {f.get('tipo_provavel') or 'nenhum'} ({f.get('motivo_provavel')})",
                  flush=True)
    except KeyboardInterrupt:
        print("\nInterrompido.", flush=True)
    print()
    fichas = [atuais[t] for t in tics if t in atuais]
    if not fichas:
        print("Nenhuma ficha pronta.", flush=True)
        return None
    saida = gravar()
    pend = [f for f in fichas if bloqueia(f.get("avisos"))]
    so_lista = [f for f in fichas if AVISO_VIZIER_LISTA in str(f.get("avisos"))]
    feitas = sum(contagem.values())
    print(f"{len(fichas)} ficha{'s' if len(fichas) != 1 else ''} em {_caminho(saida)} "
          f"(curvas em {_caminho(VSX_DIR)}/<tic>_fase.png): {contagem['mantida']} "
          f"mantida{'s' if contagem['mantida'] != 1 else ''}, {contagem['completada']} "
          f"completada{'s' if contagem['completada'] != 1 else ''}, "
          + (f"{contagem['incompleta']} ainda incompleta{'s' if contagem['incompleta'] != 1 else ''}"
             " (a busca não respondeu de novo), " if contagem["incompleta"] else "")
          + f"{contagem['nova']} "
          f"nova{'s' if contagem['nova'] != 1 else ''}.", flush=True)
    if feitas + len(falhas) < n:
        print(f"Faltaram {n - feitas - len(falhas)} estrela(s) por causa da interrupção: "
              "rode de novo para continuar.", flush=True)
    if falhas:
        print("Falharam: " + ", ".join(f"TIC {t}" for t in falhas)
              + " (rode de novo para tentar outra vez).", flush=True)
    sem_vizier = [f for f in pend if AVISO_VIZIER in str(f.get("avisos"))]
    sem_gaia = [f for f in pend if AVISO_GAIA in str(f.get("avisos"))]
    if pend:
        print("\nATENÇÃO: ficha incompleta em " + ", ".join(f"TIC {f['tic']}" for f in pend)
              + ". Não submeta essas ainda.", flush=True)
    if sem_vizier:
        print(f"  Em {len(sem_vizier)}, a busca em todos os catálogos do VizieR não respondeu. Essa "
              "busca acha artigos que já publicaram a estrela e que a Fase 5 não cobre.", flush=True)
    if sem_gaia:
        print(f"  Em {len(sem_gaia)}, a fonte Gaia DR3 não veio: posição, V e nome Gaia ficaram "
              "em branco.", flush=True)
    if pend:
        print("  O que fazer: rode `python -u src/ficha_vsx.py` de novo mais tarde (o servidor do "
              "VizieR oscila; só a busca que faltou é refeita), ou confira à mão como diz o "
              "aviso no topo de cada ficha em data/vsx/fichas.md.", flush=True)
    if so_lista:
        print(f"\n{len(so_lista)} prontas para submeter, com a busca no VizieR feita nos "
              f"{len(CATALOGOS_VARIAVEIS_ESPELHO)} principais catálogos de variáveis (o VizieR "
              "de Estrasburgo está fora). Opcional: quando ele voltar, rodar de novo faz a busca "
              "completa.", flush=True)
    print("\nPróximo passo" + (" para as fichas completas" if pend else "") + ": conferir cada "
          "estrela no VSX online (vsx.aavso.org) e submeter; veja o Passo a passo no README.",
          flush=True)
    return saida


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--duvidas", action="store_true", help="inclui as marcadas como duvida")
    g.add_argument("--todas", action="store_true", help="todas as candidatas, revisadas ou nao")
    ap.add_argument("--refazer", action="store_true",
                    help="ignora fichas.csv e refaz tudo (por padrão a ficha pronta é mantida)")
    a = ap.parse_args()
    run(None if a.todas else ("confirmado", "duvida") if a.duvidas else ("confirmado",),
        refazer=a.refazer)
