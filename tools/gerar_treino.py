"""Gera o conjunto de treino do modo quiz do app (tabela `treino`).

Usa casos com resposta conhecida: variaveis ja catalogadas (confirmado), sinais que a
Fase 6 descartou e uma amostra dos que a Fase 4 rejeitou (descartado). Sem a amostra da
Fase 4 o treino ficava com 35 confirmados e 6 descartados: confirmar tudo acertava 85%. As figuras saem da mesma triagem da Fase 7 e vao para
data/treino/. Usa rede (MAST, TESScut, VizieR) e o banco da varredura. Rodar da raiz:

    python -u tools/gerar_treino.py

Retoma de onde parou: casos (tic, metodo) que ja estao na tabela sao pulados.
"""

import json
import shutil
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from config import SQLITE_PATH, TREINO_DIR
from src.triagem import _triar

PAINEIS = ("curva", "p", "2p", "periodograma", "campo", "mapa")
CAMPOS = ("tic", "metodo", "periodo_d", "amplitude", "tmag", "n_ciclos", "deslocamento_px",
          "persistente", "setores_extra", "periodos_extra", "suspeito_blend",
          "amp_necessaria_min", "gaia_candidata", "gaia_classe")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS treino (
    tic INTEGER,
    metodo TEXT,
    figura TEXT,
    resposta TEXT,
    explicacao TEXT
)"""

MOTIVOS = {
    "vizinha_variavel": "Há uma variável catalogada perto, com o mesmo período: o sinal "
                        "vem da vizinha.",
    "nao_persiste": "O sinal não se repete nos outros setores: o mesmo método não confirma "
                    "o período.",
}

# amostra da Fase 4 por motivo de rejeicao: periodo de sistematico do TESS, sinal fraco
# contra o ruido e poucos ciclos no setor
AMOSTRA_FASE4 = {"sistematico": 12, "amplitude": 6, "ciclos": 6}
MOTIVOS_FASE4 = {
    "sistematico": "O período cai sobre um sistemático do TESS (1 d, 13,7 d ou harmônicos): "
                   "o sinal vem da nave, não da estrela.",
    "amplitude": "A amplitude mal passa do ruído ponto a ponto: a curva dobrada é ruído "
                 "organizado pelo próprio ajuste.",
    "ciclos": "Menos de 3 ciclos no setor: dois ou três eventos isolados não definem um período.",
}
SEMENTE = 42


def _explicacao_conhecido(r) -> str:
    if pd.isna(r.get("periodo_catalogo")):
        return (f"{r['match_catalogo']} já lista esta estrela como variável "
                f"({r['match_nome']}), sem período comparável no catálogo.")
    razao = r.get("razao_periodo")
    extra = "" if pd.isna(razao) else f", razão {float(razao):.2f} com o período medido"
    return (f"{r['match_catalogo']} já lista {r['match_nome']} com período "
            f"{float(r['periodo_catalogo']):.4f} d{extra}: é uma variável conhecida.")


def _explicacao_descartado(r) -> str:
    motivo = r.get("motivo_descarte")
    base = MOTIVOS.get(motivo, f"O pipeline descartou este sinal ({motivo}).")
    if pd.isna(r.get("setores_extra")):
        return base
    return f"{base} Setores comparados: {r['setores_extra']}."


def _casos(con) -> list[tuple]:
    conhecidos = pd.read_sql(
        "SELECT s.*, a.autor FROM sinais_fase5 s JOIN alvos a USING (tic) "
        "WHERE s.status = 'conhecido' ORDER BY s.tic, s.metodo", con)
    descartados = pd.read_sql(
        "SELECT * FROM candidatos WHERE veredito != 'candidato' ORDER BY tic, metodo", con)
    casos = [(r, "confirmado", _explicacao_conhecido(r)) for _, r in conhecidos.iterrows()]
    casos += [(r, "descartado", _explicacao_descartado(r)) for _, r in descartados.iterrows()]
    rejeitados = pd.read_sql(
        "SELECT s.*, a.ra, a.dec, a.tmag, a.autor FROM sinais s JOIN alvos a USING (tic) "
        "WHERE s.sinal = 0 ORDER BY s.tic, s.metodo", con)
    for motivo, n in AMOSTRA_FASE4.items():
        grupo = rejeitados[rejeitados["motivo"] == motivo]
        for _, r in grupo.sample(min(n, len(grupo)), random_state=SEMENTE).iterrows():
            casos.append((r, "descartado", MOTIVOS_FASE4[motivo]))
    return casos


def _dados(r, extra: dict) -> dict:
    dados = {}
    for campo in CAMPOS:
        v = extra.get(campo, r.get(campo))
        dados[campo] = None if v is None or pd.isna(v) else v
    try:
        dados["forca"] = float(r["amplitude"]) / float(r["ruido_ptp"])
    except (KeyError, TypeError, ValueError):
        dados["forca"] = None
    return dados


def main():
    TREINO_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(SQLITE_PATH) as con:
        con.execute(_SCHEMA)
        feitos = {(int(tic), metodo) for tic, metodo in con.execute("SELECT tic, metodo FROM treino")}
        casos = _casos(con)
        novos = 0
        for i, (r, resposta, explicacao) in enumerate(casos, 1):
            tic, metodo = int(r["tic"]), r["metodo"]
            if (tic, metodo) in feitos:
                print(f"  {i}/{len(casos)} TIC {tic} {metodo}: já no treino")
                continue
            try:
                extra = _triar(SimpleNamespace(**r.to_dict()))
            except Exception as e:
                print(f"  {i}/{len(casos)} TIC {tic} {metodo}: figura falhou "
                      f"({str(e)[:120]}); pulando")
                continue
            origem = Path(extra["figura"])
            destino = TREINO_DIR / f"{tic}_{metodo}.png"
            shutil.copy(origem, destino)
            for nome in PAINEIS[1:]:
                painel = origem.with_name(f"{tic}_{nome}.png")
                if painel.exists():
                    shutil.copy(painel, destino.with_name(f"{destino.stem}_{nome}.png"))
            destino.with_suffix(".json").write_text(
                json.dumps(_dados(r, extra), ensure_ascii=False), encoding="utf-8")
            con.execute("INSERT INTO treino VALUES (?, ?, ?, ?, ?)",
                        (tic, metodo, str(destino), resposta, explicacao))
            con.commit()
            feitos.add((tic, metodo))
            novos += 1
            print(f"  {i}/{len(casos)} TIC {tic} {metodo}: {resposta}")
    print(f"  {novos} casos novos em {TREINO_DIR}")


if __name__ == "__main__":
    main()
