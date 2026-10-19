"""Mede se uma LLM com visao classifica o tipo de variavel olhando a curva em fase.

Gabarito: estrelas do VSX com tipo firme (sem ":") perto do campo do setor 55. Para cada
uma, baixa uma curva QLP, dobra num periodo de referencia (o verdadeiro ou a metade, sorteado,
que e o erro tipico do LS) e desenha dois paineis: A em P e B em 2P. A LLM responde o tipo e
qual painel mostra o periodo verdadeiro; a heuristica `sugerir` da Fase 8 responde o mesmo,
como base de comparacao. Usa rede (VizieR, MAST, LLM). Rodar da raiz do repositorio:

    python -u tools/teste_llm_visao.py              # 12 estrelas por classe
    python -u tools/teste_llm_visao.py --por-classe 4 --modelo gemini-2.5-flash-lite

Grava o CSV a cada estrela e retoma de onde parou: o plano gratis do Gemini da ~20 pedidos
por dia em alguns modelos, e a cota acaba no meio.
"""

import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import astropy.units as u
import httpx
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from astropy.coordinates import SkyCoord
from astroquery.vizier import Vizier

from config import (ALVO_DEC_DEG, ALVO_RA_DEG, ALVO_TMAG_MAX, LLM_VISAO_BASE_URL,
                    LLM_VISAO_CHAVE_ENV, LLM_VISAO_CHAVE_PROVEDOR, LLM_VISAO_INTERVALO_S,
                    LLM_VISAO_MODELO, ROOT as RAIZ)
from src.curvas import SemCurva, baixar_curva, setores_observados
from src.detectar_sinal import _arrays
from src.ficha_vsx import sugerir
from src.util import retry

SAIDA = RAIZ / "data" / "teste_llm"
# tipo do VSX (sem ":" e sem tipo composto) -> classe do teste
CLASSES = {"EA": "EA", "EB": "EB", "EW": "EW", "ROT": "ROT", "BY": "ROT",
           "DSCT": "DSCT", "HADS": "DSCT", "RRAB": "RR", "RRC": "RR"}
ROTULOS = sorted(set(CLASSES.values()))

PROMPT = """You are classifying a variable star from its TESS light curve (QLP photometry).
The image has two panels with the same data folded at two trial periods:
panel A at P, panel B at 2P (period values in the panel titles). Brightness is in delta
magnitude, so dips (eclipses, minima) point DOWN.

Variability classes (AAVSO VSX):
- EA: detached eclipsing binary. Flat light outside narrow eclipses.
- EB: beta Lyrae eclipsing binary. Brightness changes all the time, clearly unequal minima.
- EW: W UMa contact binary. Continuous change, nearly equal minima, period usually < 1 d.
- ROT: rotating spotted star. Quasi-sinusoidal single wave per period, shape may change.
- DSCT: delta Scuti pulsator. Period < 0.3 d, often multiperiodic, low amplitude.
- RR: RR Lyrae pulsator. Period 0.2 to 1 d, large amplitude, fast rise and slow decline
  (RRab) or nearly sinusoidal (RRc).

For an eclipsing binary the true period contains both eclipses (primary and secondary),
so the right panel shows one primary and one secondary per cycle. For a pulsator or a
rotator the true period shows one clean cycle.

Answer exactly in three lines:
TIPO: <EA|EB|EW|ROT|DSCT|RR>
PAINEL: <A|B>
MOTIVO: <one short sentence>"""


def classe_vsx(tipo: str) -> str | None:
    """Classe do teste para o tipo do VSX, ou None se incerto (':') ou composto."""
    tipo = str(tipo).strip()
    if not tipo or any(c in tipo for c in ":|+"):
        return None
    return CLASSES.get(tipo.split("/")[0])


def ler_resposta(texto: str) -> tuple[str | None, str | None, str]:
    tipo = re.search(r"TIPO:\s*\**\s*([A-Z]+)", texto or "")
    painel = re.search(r"PAINEL:\s*\**\s*([AB])\b", texto or "")
    motivo = re.search(r"MOTIVO:\s*(.+)", texto or "")
    tipo = tipo.group(1) if tipo and tipo.group(1) in ROTULOS else None
    return tipo, painel.group(1) if painel else None, motivo.group(1).strip() if motivo else ""


def _chave() -> str:
    if os.environ.get(LLM_VISAO_CHAVE_ENV):
        return os.environ[LLM_VISAO_CHAVE_ENV]
    auth = Path.home() / ".local" / "share" / "opencode" / "auth.json"
    return json.loads(auth.read_text())[LLM_VISAO_CHAVE_PROVEDOR]["key"]


class CotaEsgotada(Exception):
    pass


def perguntar(png: bytes, chave: str, modelo: str) -> str:
    corpo = {"model": modelo, "messages": [{"role": "user", "content": [
        {"type": "text", "text": PROMPT},
        {"type": "image_url",
         "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}}]}]}
    for tentativa in range(4):
        r = httpx.post(f"{LLM_VISAO_BASE_URL}/chat/completions", json=corpo, timeout=120,
                       headers={"Authorization": f"Bearer {chave}"})
        # 429: limite por minuto ou cota do dia; 503: modelo sobrecarregado
        if r.status_code in (429, 503) and tentativa < 3:
            print(f"    {r.status_code}, esperando {30 * (tentativa + 1)} s")
            time.sleep(30 * (tentativa + 1))
            continue
        if r.status_code in (429, 503):
            raise CotaEsgotada(r.text[:200])
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"] or ""
    return ""


def amostra(por_classe: int, semente: int) -> pd.DataFrame:
    res = retry(lambda: Vizier(columns=["Name", "RAJ2000", "DEJ2000", "Type", "max", "Period"],
                               row_limit=-1, timeout=180)
                .query_region(SkyCoord(ALVO_RA_DEG, ALVO_DEC_DEG, unit="deg"),
                              radius=5 * u.deg, catalog="B/vsx/vsx"), "VizieR")
    vsx = res[0].to_pandas()
    vsx["classe"] = vsx["Type"].map(classe_vsx)
    vsx = vsx.dropna(subset=["classe", "Period", "max"])
    vsx = vsx[vsx["Period"].between(0.1, 13) & vsx["max"].between(8, 13.5)]
    print(f"VSX: {len(vsx)} estrelas utilizaveis por classe: {vsx['classe'].value_counts().to_dict()}")
    # sobra para repor as que nao tem curva QLP
    return (vsx.groupby("classe", group_keys=False)
            .apply(lambda g: g.sample(min(len(g), 3 * por_classe), random_state=semente))
            .reset_index(drop=True))


def _tic(ra: float, dec: float) -> tuple[int, float] | None:
    res = retry(lambda: Vizier(columns=["TIC", "Tmag", "_r"], row_limit=-1)
                .query_region(SkyCoord(ra, dec, unit="deg"), radius=3 * u.arcsec,
                              catalog="IV/39/tic82"), "VizieR")
    if not len(res):
        return None
    t = res[0].to_pandas().sort_values("Tmag")
    return int(t.iloc[0]["TIC"]), float(t.iloc[0]["Tmag"])


def _curva(tic: int, ra: float, dec: float):
    """Primeiro setor com curva QLP, comecando pelo 55 (o do pipeline)."""
    for setor in sorted(setores_observados(ra, dec), key=lambda s: abs(s - 55))[:6]:
        try:
            lc, _ = baixar_curva(tic, setor, "QLP")
            return lc, setor
        except SemCurva:
            continue
    return None, None


def _destendencia(lc, periodo: float):
    """Achata variacoes lentas sem apagar o sinal: janela de pelo menos 6 periodos."""
    janela = max(1.0, 6 * periodo)
    tempo = np.asarray(lc.time.value, dtype=float)
    if janela >= 0.5 * (tempo.max() - tempo.min()):
        return _arrays(lc)
    n = int(janela / float(np.median(np.diff(tempo))))
    return _arrays(lc.flatten(window_length=n + 1 if n % 2 == 0 else n))


def figura(tempo, fluxo, periodo: float) -> bytes:
    mag = -2.5 * np.log10(np.clip(fluxo, 1e-6, None))
    fig, eixos = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
    for ax, (rotulo, p) in zip(eixos, (("A", periodo), ("B", 2 * periodo))):
        fase = ((tempo - tempo.min()) / p) % 1
        idx = np.minimum((fase * 100).astype(int), 99)
        med = [np.nanmedian(mag[idx == k]) if np.any(idx == k) else np.nan for k in range(100)]
        ax.plot(fase, mag, ".", ms=1, color="0.6", rasterized=True)
        ax.plot((np.arange(100) + 0.5) / 100, med, "-", color="C3", lw=1)
        ax.set_title(f"{rotulo}: folded at {p:.5f} d")
        ax.set_xlabel("phase")
    eixos[0].set_ylabel("delta mag (TESS)")
    eixos[0].invert_yaxis()
    fig.tight_layout()
    import io
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=90)
    plt.close(fig)
    return buf.getvalue()


def run(por_classe: int, modelo: str, semente: int = 7):
    SAIDA.mkdir(parents=True, exist_ok=True)
    csv = SAIDA / f"resultados_{modelo}.csv"
    rng = np.random.default_rng(semente)
    chave = _chave()
    linhas = pd.read_csv(csv).to_dict("records") if csv.exists() else []
    feitos = {c: sum(l["classe"] == c for l in linhas) for c in ROTULOS}
    ja = {l["nome"] for l in linhas}
    for s in amostra(por_classe, semente).itertuples():
        # sorteio sempre consumido, para a metade/inteiro de cada estrela nao mudar ao retomar
        metade = bool(rng.random() < 0.5)
        if feitos[s.classe] >= por_classe or s.Name in ja:
            continue
        try:
            achado = _tic(s.RAJ2000, s.DEJ2000)
            if achado is None or achado[1] > ALVO_TMAG_MAX:
                continue
            tic, tmag = achado
            lc, setor = _curva(tic, s.RAJ2000, s.DEJ2000)
            if lc is None:
                continue
            tempo, fluxo = _destendencia(lc, s.Period)
            p_ref = s.Period / 2 if metade else s.Period
            png = figura(tempo, fluxo, p_ref)
            (SAIDA / f"{tic}.png").write_bytes(png)
            p_heur, tipo_heur, _ = sugerir("ls", p_ref, tempo, fluxo)
            texto = perguntar(png, chave, modelo)
            tipo_llm, painel_llm, motivo = ler_resposta(texto)
        except CotaEsgotada as e:
            print(f"  cota do {modelo} esgotada, parando (rode de novo amanha para continuar): {e}")
            break
        except Exception as e:
            print(f"  {s.Name}: falhou ({str(e)[:100]})")
            continue
        feitos[s.classe] += 1
        certo = "B" if metade else "A"
        linhas.append({
            "nome": s.Name, "tic": tic, "tmag": tmag, "setor": setor, "tipo_vsx": s.Type,
            "classe": s.classe, "periodo_vsx": s.Period, "periodo_ref": p_ref,
            "painel_certo": certo, "tipo_llm": tipo_llm, "painel_llm": painel_llm,
            "motivo_llm": motivo, "tipo_heur": tipo_heur,
            "painel_heur": "B" if abs(p_heur - 2 * p_ref) < 1e-9 else "A"})
        print(f"  {sum(feitos.values())}: {s.Name} ({s.classe}, P={s.Period:.4f}) -> LLM "
              f"{tipo_llm}/{painel_llm} (certo {s.classe}/{certo}); heuristica {tipo_heur}")
        pd.DataFrame(linhas).to_csv(csv, index=False)
        time.sleep(LLM_VISAO_INTERVALO_S)
    resumo(pd.DataFrame(linhas))


def resumo(df: pd.DataFrame):
    n = len(df)
    tipo_llm = (df["tipo_llm"] == df["classe"]).mean()
    painel_llm = (df["painel_llm"] == df["painel_certo"]).mean()
    painel_heur = (df["painel_heur"] == df["painel_certo"]).mean()
    # a heuristica so afirma EA ou EB; o resto ela deixa em aberto
    afirma = df[df["tipo_heur"].isin(["EA", "EB"])]
    print(f"\n{n} estrelas ({df['classe'].value_counts().to_dict()})")
    print(f"Tipo certo:   LLM {tipo_llm:.0%}  |  heuristica afirma o tipo em {len(afirma)} "
          f"e acerta {(afirma['tipo_heur'] == afirma['classe']).mean():.0%} delas")
    print(f"Painel certo: LLM {painel_llm:.0%}  |  heuristica {painel_heur:.0%}")
    print("\nAcerto do tipo pela LLM por classe:")
    print(df.assign(ok=df["tipo_llm"] == df["classe"]).groupby("classe")["ok"].mean()
          .map("{:.0%}".format).to_string())
    print("\nMatriz de confusao (linha = VSX, coluna = LLM):")
    print(pd.crosstab(df["classe"], df["tipo_llm"].fillna("sem resposta")).to_string())


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--por-classe", type=int, default=12)
    ap.add_argument("--modelo", default=LLM_VISAO_MODELO)
    a = ap.parse_args()
    run(a.por_classe, a.modelo)
