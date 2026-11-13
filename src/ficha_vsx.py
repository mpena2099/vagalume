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
from config import BLS_FLATTEN_D, LS_FLATTEN_D, SQLITE_PATH, VSX_DIR
from src.curvas import baixar_curva
from src.detectar_sinal import _arrays, _flatten
from src.periodo_setores import medir_periodo_setores
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


def sugerir(metodo: str, periodo: float, tempo: np.ndarray, fluxo: np.ndarray,
            n_bins: int = 40) -> tuple[float, str, str]:
    """(periodo, tipo VSX sugerido, motivo). Binaria no LS costuma sair com metade do periodo."""
    if metodo == "bls":
        return periodo, "EA", "eclipses curtos achados pelo BLS"
    if fracao_variando(tempo, fluxo, 2 * periodo) < 0.3:
        return (2 * periodo, "EA",
                "dobrada em 2P, dois eclipses estreitos e brilho plano entre eles: o periodo real e 2P")
    med, erro = curva_binada(tempo, fluxo, 2 * periodo, n_bins)
    base = np.nanmedian(med)
    k1 = int(np.nanargmin(med))
    perto = [(k1 + n_bins // 2 + d) % n_bins for d in range(-n_bins // 10, n_bins // 10 + 1)]
    k2 = perto[int(np.nanargmin(med[perto]))]
    p1, p2 = base - med[k1], base - med[k2]
    diferenca = abs(p1 - p2)
    sigma = np.hypot(erro[k1], erro[k2])
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
    return {"tic": int(s.tic), "decisao": s.decisao, "periodo_d": periodo,
            "periodo_erro_d": medido["periodo_erro_d"],
            "alerta_periodo": medido["alerta_periodo"],
            "fase_secundario": medido["fase_secundario"],
            "tipo_sugerido": tipo, "motivo_tipo": motivo, "epoca_bjd": epoca + BTJD_PARA_BJD,
            "amplitude_mag_tess": amplitude_dobrada_mag(tempo, fluxo, periodo),
            "setores": ",".join(str(x) for x in [s.setor, s.setores_extra] if pd.notna(x)),
            "setores_usados": ",".join(str(setor) for setor, _ in brutas),
            "suspeito_blend": bool(s.suspeito_blend), "figura_fase": str(figura),
            "figura_triagem": s.figura}


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


def _buscar_vizier(ficha: dict, s) -> str | None:
    """Preenche a busca em todos os catalogos do VizieR. Devolve o aviso se nao respondeu."""
    print("  buscando em todos os catálogos do VizieR (pode levar minutos)", flush=True)
    try:
        ficha["vizier_variaveis"] = ("; ".join(_vizier(SkyCoord(s.ra, s.dec, unit="deg")))
                                     or "nenhum catalogo de variaveis a 30\"")
    except Exception as e:
        print(f"  VizieR sem resposta ({type(e).__name__}); seguindo sem essa busca", flush=True)
        ficha["vizier_variaveis"] = "busca não feita"
        return AVISO_VIZIER
    return None


BUSCAS = {"gaia": _buscar_gaia, "vizier": _buscar_vizier}
AVISO_DE = {"gaia": AVISO_GAIA, "vizier": AVISO_VIZIER}


def completar_buscas(ficha: dict, s, faltas: list[str]) -> dict:
    """Refaz so as buscas em `faltas` e atualiza `avisos`; o resto da ficha fica como esta."""
    restantes = [a for a in str(ficha.get("avisos") or "").split(" | ")
                 if a and a not in [AVISO_DE[k] for k in faltas]]
    for k in faltas:
        aviso = BUSCAS[k](ficha, s)
        if aviso:
            restantes.append(aviso)
    ficha["avisos"] = " | ".join(restantes)
    return ficha


def montar_ficha(s) -> dict:
    ficha = _medir(s)
    ficha["avisos"] = ""
    return completar_buscas(ficha, s, ["gaia", "vizier"])


def plano(anterior: dict | None, refazer: bool = False) -> str:
    """O que fazer com uma estrela: 'nova', 'manter' ou 'completar:<buscas faltantes>'."""
    if anterior is None or refazer:
        return "nova"
    avisos = str(anterior.get("avisos") or "")
    if not avisos:
        return "manter"
    faltas = set()
    for aviso in filter(None, (x.strip() for x in avisos.split("|"))):
        # pelo tipo, nao pelo texto exato: fichas antigas tem outra redacao do aviso
        if aviso.startswith("Fonte Gaia DR3"):
            faltas.add("gaia")
        elif aviso.startswith("Busca") and "VizieR" in aviso:
            faltas.add("vizier")
        else:
            return "nova"  # aviso que esta logica nao sabe completar
    if not faltas:
        return "nova"
    return "completar:" + ",".join(k for k in ("gaia", "vizier") if k in faltas)


NUMERICAS = ["periodo_d", "periodo_erro_d", "fase_secundario", "epoca_bjd", "amplitude_mag_tess",
             "gaia_ra", "gaia_dec", "gaia_g", "v_estimada", "gaia_sep_arcsec"]


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
"""


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
    contagem = {"mantida": 0, "completada": 0, "nova": 0}
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
                    nomes = {"vizier": "busca no VizieR", "gaia": "fonte Gaia DR3"}
                    print(f"\n[{i}/{n}] TIC {tic}: completando a ficha (faltava: "
                          + " e ".join(nomes[k] for k in faltas) + ")", flush=True)
                    f = completar_buscas(dict(anteriores[tic]), s, faltas)
                    f["decisao"] = s.decisao
                    contagem["completada"] += 1
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
            print(f"  pronta: período {f['periodo_d']:.5f} d, tipo sugerido {f['tipo_sugerido']} "
                  f"({_tempo(time.monotonic() - t0)})", flush=True)
    except KeyboardInterrupt:
        print("\nInterrompido.", flush=True)
    print()
    fichas = [atuais[t] for t in tics if t in atuais]
    if not fichas:
        print("Nenhuma ficha pronta.", flush=True)
        return None
    saida = gravar()
    pend = [f for f in fichas if f.get("avisos")]
    feitas = sum(contagem.values())
    print(f"{len(fichas)} ficha{'s' if len(fichas) != 1 else ''} em {_caminho(saida)} "
          f"(curvas em {_caminho(VSX_DIR)}/<tic>_fase.png): {contagem['mantida']} "
          f"mantida{'s' if contagem['mantida'] != 1 else ''}, {contagem['completada']} "
          f"completada{'s' if contagem['completada'] != 1 else ''}, {contagem['nova']} "
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
