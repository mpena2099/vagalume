"""Acesso a dados da revisao visual: sem Streamlit, testavel offline."""

import sqlite3
from datetime import datetime
from urllib.parse import quote

import pandas as pd

from config import DESLOCAMENTO_MAX_PX

DECISOES = ("confirmado", "duvida", "descartado")

# Tabela propria: candidatos_fase7 e refeita a cada execucao do pipeline
# (to_sql replace) e apagaria as decisoes humanas.
_SCHEMA_REVISAO = """
CREATE TABLE IF NOT EXISTS revisao_humana (
    tic INTEGER PRIMARY KEY,
    decisao TEXT NOT NULL,
    nota TEXT,
    atualizado_em TEXT NOT NULL
)"""


def ler_revisoes(conn: sqlite3.Connection) -> pd.DataFrame:
    conn.execute(_SCHEMA_REVISAO)
    return pd.read_sql("SELECT tic, decisao, nota FROM revisao_humana", conn)


def carregar_candidatos(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM candidatos_fase7", conn)
    df = df.merge(ler_revisoes(conn), on="tic", how="left")
    df["decisao"] = df["decisao"].fillna("pendente")
    return df


def salvar_revisao(conn: sqlite3.Connection, tic: int, decisao: str, nota: str = "") -> None:
    if decisao not in DECISOES:
        raise ValueError(f"decisao invalida: {decisao!r} (use {DECISOES})")
    conn.execute(_SCHEMA_REVISAO)
    conn.execute("INSERT OR REPLACE INTO revisao_humana VALUES (?, ?, ?, ?)",
                 (int(tic), decisao, nota, datetime.now().isoformat(timespec="seconds")))
    conn.commit()


def apagar_revisao(conn: sqlite3.Connection, tic: int) -> None:
    conn.execute(_SCHEMA_REVISAO)
    conn.execute("DELETE FROM revisao_humana WHERE tic = ?", (int(tic),))
    conn.commit()


def _sim(v) -> bool:
    """Booleano vindo do SQLite: None e NaN contam como falso (NaN e truthy em Python)."""
    return v is not None and not pd.isna(v) and bool(v)


def _texto(v) -> str:
    return "" if v is None or pd.isna(v) else str(v)


def checklist(r: dict) -> list[dict]:
    """O que olhar na candidata, em linguagem simples, com os numeros do caso."""
    itens = []

    d = r.get("deslocamento_px")
    if d is None or pd.isna(d):
        itens.append({"estado": "atencao", "titulo": "Sinal no alvo",
                      "explicacao": "Não foi possível medir o pico do sinal no mapa de pixels."})
    elif d > DESLOCAMENTO_MAX_PX:
        itens.append({"estado": "problema", "titulo": "Sinal no alvo",
                      "explicacao": f"O sinal é mais forte a {d:.1f} px do alvo (limite "
                                    f"{DESLOCAMENTO_MAX_PX:.1f} px): pode vir de outra estrela."})
    else:
        itens.append({"estado": "ok", "titulo": "Sinal no alvo",
                      "explicacao": f"O sinal é mais forte a {d:.1f} px do alvo, dentro do "
                                    f"limite de {DESLOCAMENTO_MAX_PX:.1f} px."})

    p = r.get("persistente")
    setores = _texto(r.get("setores_extra")) or "nenhum"
    periodos = _texto(r.get("periodos_extra")) or "sem período"
    if p is None or pd.isna(p):
        itens.append({"estado": "atencao", "titulo": "Repete em outros setores",
                      "explicacao": "Sem outro setor para comparar: não dá para saber se o "
                                    "sinal se repete."})
    elif _sim(p):
        itens.append({"estado": "ok", "titulo": "Repete em outros setores",
                      "explicacao": f"O sinal se repete nos setores {setores}, com "
                                    f"períodos {periodos} d."})
    else:
        itens.append({"estado": "problema", "titulo": "Repete em outros setores",
                      "explicacao": f"O sinal não se repete: nos setores {setores} o "
                                    f"período medido foi {periodos} d."})

    n = r.get("n_ciclos")
    if n is None or pd.isna(n) or n < 4:
        texto = "sem medida" if n is None or pd.isna(n) else f"só {n:.1f} ciclos"
        itens.append({"estado": "atencao", "titulo": "Ciclos no setor",
                      "explicacao": f"Há {texto} no setor (o ideal é 4 ou mais): o período "
                                    "fica menos preciso."})
    else:
        itens.append({"estado": "ok", "titulo": "Ciclos no setor",
                      "explicacao": f"Há {n:.1f} ciclos no setor, suficientes para medir o "
                                    "período."})

    f = r.get("forca")
    if f is None or pd.isna(f) or f < 5:
        texto = "sem medida" if f is None or pd.isna(f) else f"{f:.1f} vezes o ruído"
        itens.append({"estado": "atencao", "titulo": "Força do sinal",
                      "explicacao": f"A amplitude é {texto} (o ideal é 5 vezes ou mais)."})
    else:
        itens.append({"estado": "ok", "titulo": "Força do sinal",
                      "explicacao": f"A amplitude é {f:.1f} vezes o ruído: o sinal está bem "
                                    "acima do ruído."})

    if _sim(r.get("suspeito_blend")):
        amp = r.get("amp_necessaria_min")
        amp_txt = ("amplitude desconhecida" if amp is None or pd.isna(amp)
                   else f"{amp * 100:.0f}%")
        itens.append({"estado": "atencao", "titulo": "Vizinha brilhante (blend)",
                      "explicacao": "Há uma vizinha brilhante a menos de 42\": ela precisaria "
                                    f"variar {amp_txt} para gerar o sinal."})
    else:
        itens.append({"estado": "ok", "titulo": "Vizinha brilhante (blend)",
                      "explicacao": "Nenhuma vizinha brilhante explica o sinal."})

    if _sim(r.get("gaia_candidata")):
        classe = r.get("gaia_classe")
        classe_txt = f" ({classe})" if classe is not None and not pd.isna(classe) else ""
        itens.append({"estado": "atencao", "titulo": "Já no Gaia",
                      "explicacao": f"O Gaia DR3 já lista a estrela como candidata a variável"
                                    f"{classe_txt}. Ainda dá para submeter, mas o mérito é menor."})
    else:
        itens.append({"estado": "ok", "titulo": "Já no Gaia",
                      "explicacao": "Não está no Gaia DR3 como candidata a variável."})
    return itens


def sugestao(itens: list[dict]) -> str:
    """Decisao que o pipeline sugere a partir do checklist."""
    estados = {i["estado"] for i in itens}
    if "problema" in estados:
        return "descartado"
    if "atencao" in estados:
        return "duvida"
    return "confirmado"


def alertas(r: dict) -> list[str]:
    """Pontos que pesam contra a candidata, em linguagem de revisao."""
    saida = []
    d = r.get("deslocamento_px")
    if d is not None and pd.notna(d) and d > DESLOCAMENTO_MAX_PX:
        saida.append(f"O sinal é mais forte a {d:.1f} px do alvo: pode vir de outra estrela.")
    if _sim(r.get("suspeito_blend")):
        saida.append(f"Vizinha Gaia brilhante a menos de 42\": precisaria variar "
                     f"{r['amp_necessaria_min'] * 100:.0f}% para gerar o sinal.")
    if r.get("n_ciclos") is not None and pd.notna(r["n_ciclos"]) and r["n_ciclos"] < 4:
        saida.append(f"Só {r['n_ciclos']:.1f} ciclos no setor: período pouco preciso.")
    if r.get("persistente") is None or pd.isna(r.get("persistente")):
        saida.append("Sem outro setor para confirmar que o sinal se repete.")
    if _sim(r.get("gaia_candidata")):
        saida.append(f"Gaia DR3 já lista como candidata a variável ({r.get('gaia_classe')}). "
                     "Ainda dá para submeter, mas o mérito é menor.")
    return saida


def links(ra: float, dec: float, tic: int) -> dict[str, str]:
    coord = quote(f"{ra:.6f} {dec:+.6f}")
    return {
        "VSX (2')": f"https://www.aavso.org/vsx/index.php?view=results.get&coords={coord}"
                    f"&format=d&size=2&unit=2",
        "SIMBAD (1')": f"https://simbad.cds.unistra.fr/simbad/sim-coo?Coord={coord}"
                       f"&Radius=1&Radius.unit=arcmin",
        "Aladin (DSS2)": f"https://aladin.cds.unistra.fr/AladinLite/?target={coord}"
                         f"&fov=0.1&survey=P%2FDSS2%2Fcolor",
        "ExoFOP": f"https://exofop.ipac.caltech.edu/tess/target.php?id={tic}",
    }


# Historico do quiz: uma linha por resposta, para acompanhar a evolucao entre sessoes
_SCHEMA_TREINO = """
CREATE TABLE IF NOT EXISTS treino_historico (
    respondido_em TEXT NOT NULL,
    caso TEXT NOT NULL,
    pergunta TEXT NOT NULL,
    escolha TEXT NOT NULL,
    certa TEXT NOT NULL,
    pontos REAL NOT NULL
)"""


def salvar_tentativa(conn: sqlite3.Connection, caso: str, escolha: str, certa: str,
                     pontos: float, pergunta: str = "decisao") -> None:
    conn.execute(_SCHEMA_TREINO)
    conn.execute("INSERT INTO treino_historico VALUES (?, ?, ?, ?, ?, ?)",
                 (datetime.now().isoformat(timespec="seconds"), caso, pergunta, escolha, certa,
                  float(pontos)))
    conn.commit()


def ler_tentativas(conn: sqlite3.Connection) -> pd.DataFrame:
    conn.execute(_SCHEMA_TREINO)
    return pd.read_sql("SELECT * FROM treino_historico ORDER BY respondido_em", conn)


def resumo_treino(h: pd.DataFrame, recentes: int = 20) -> dict:
    """Aproveitamento geral, nas ultimas respostas e por resposta certa.

    O corte por resposta certa mostra vies: quem confirma quase tudo acerta os casos
    "confirmado" e erra os "descartado". Vazio se ainda nao ha resposta.
    """
    d = h[h["pergunta"] == "decisao"]
    if d.empty:
        return {}

    def taxa(x: pd.DataFrame) -> float:
        return float(x["pontos"].mean())

    r = {"respostas": len(d), "dias": int(d["respondido_em"].str[:10].nunique()),
         "geral": taxa(d), "recentes": taxa(d.tail(recentes)),
         "n_recentes": min(recentes, len(d)),
         "por_certa": {c: (taxa(g), len(g)) for c, g in d.groupby("certa")}}
    p = h[h["pergunta"] == "periodo"]
    if not p.empty:
        r["periodo"] = (taxa(p), len(p))
    return r
