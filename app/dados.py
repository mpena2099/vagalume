"""Acesso a dados da revisao visual: sem Streamlit, testavel offline."""

import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import pandas as pd

from config import DESLOCAMENTO_MAX_PX, MARCA_PODE_SUBMETER

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

    if _sim(r.get("perto_sistematico")):
        itens.append({"estado": "atencao", "titulo": "Período perto de um ritmo do satélite",
                      "explicacao": f"O período de {r.get('periodo_d', 0):.3f} d fica perto de um "
                                    "ritmo do TESS (1 d, 4,57 d, 6,85 d ou 13,7 d), mas nenhuma "
                                    "outra estrela forte do campo tem esse período. Confira no "
                                    "mapa se o sinal sai da estrela alvo."})

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


def zerar_treino(conn: sqlite3.Connection) -> None:
    """Apaga todas as respostas do treino (o nivel volta a Aprendiz)."""
    conn.execute(_SCHEMA_TREINO)
    conn.execute("DELETE FROM treino_historico")
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


# Marcos manuais ficam fora do to_sql replace pelo mesmo motivo das revisoes.
_SCHEMA_MARCOS = """
CREATE TABLE IF NOT EXISTS marcos_manuais (
    nome TEXT PRIMARY KEY,
    feito_em TEXT
)"""

MARCOS_MANUAIS = ("Enviada ao VSX", "Aceita no VSX")
_ROTULOS_CERTA = {"confirmado": "Confirmado", "duvida": "Dúvida", "descartado": "Descartado"}


def marcar(conn: sqlite3.Connection, nome: str, feito: bool) -> None:
    conn.execute(_SCHEMA_MARCOS)
    if feito:
        conn.execute("INSERT OR REPLACE INTO marcos_manuais VALUES (?, ?)",
                     (nome, datetime.now().isoformat(timespec="seconds")))
    else:
        conn.execute("DELETE FROM marcos_manuais WHERE nome = ?", (nome,))
    conn.commit()


def ler_marcos_manuais(conn: sqlite3.Connection) -> set[str]:
    conn.execute(_SCHEMA_MARCOS)
    return {r[0] for r in conn.execute("SELECT nome FROM marcos_manuais")}


# Envio por estrela: nunca to_sql replace, senao uma rodada apagaria as marcacoes.
_SCHEMA_ENVIO = """
CREATE TABLE IF NOT EXISTS envio_vsx (
    tic INTEGER PRIMARY KEY,
    enviada_em TEXT,
    aceita_em TEXT,
    nome_vsx TEXT,
    tipo_final TEXT
)"""


def _garantir_envio(conn: sqlite3.Connection) -> None:
    conn.execute(_SCHEMA_ENVIO)
    colunas = {r[1] for r in conn.execute("PRAGMA table_info(envio_vsx)")}
    if "tipo_final" not in colunas:
        conn.execute("ALTER TABLE envio_vsx ADD COLUMN tipo_final TEXT")


def ler_envios(conn: sqlite3.Connection) -> pd.DataFrame:
    _garantir_envio(conn)
    return pd.read_sql("SELECT tic, enviada_em, aceita_em, nome_vsx, tipo_final FROM envio_vsx",
                       conn)


def marcar_tipo(conn: sqlite3.Connection, tic: int, tipo: str | None) -> None:
    """Guarda o tipo escolhido para a estrela sem tocar nas marcacoes de envio."""
    _garantir_envio(conn)
    tic = int(tic)
    conn.execute("INSERT OR IGNORE INTO envio_vsx (tic) VALUES (?)", (tic,))
    conn.execute("UPDATE envio_vsx SET tipo_final = ? WHERE tic = ?", (tipo or None, tic))
    conn.commit()


def marcar_envio(conn: sqlite3.Connection, tic: int, enviada: bool | None = None,
                 aceita: bool | None = None, nome_vsx: str | None = None) -> None:
    """Marca envio/aceite da estrela. Marcar grava a data, desmarcar grava NULL;
    aceita implica enviada."""
    _garantir_envio(conn)
    tic = int(tic)
    linha = conn.execute("SELECT enviada_em, aceita_em, nome_vsx FROM envio_vsx WHERE tic = ?",
                         (tic,)).fetchone()
    enviada_em, aceita_em, nome = linha if linha else (None, None, None)
    agora = datetime.now().isoformat(timespec="seconds")
    if enviada is not None:
        enviada_em = (enviada_em or agora) if enviada else None
        if not enviada:
            aceita_em = None
    if aceita is not None:
        if aceita:
            aceita_em = aceita_em or agora
            enviada_em = enviada_em or agora
        else:
            aceita_em = None
    if nome_vsx is not None:
        nome = nome_vsx.strip() or None
    conn.execute("INSERT OR IGNORE INTO envio_vsx (tic) VALUES (?)", (tic,))
    conn.execute("UPDATE envio_vsx SET enviada_em = ?, aceita_em = ?, nome_vsx = ? WHERE tic = ?",
                 (enviada_em, aceita_em, nome, tic))
    conn.commit()


def migrar_envios(conn: sqlite3.Connection, fichas_csv: Path) -> int:
    """Leva as marcacoes globais antigas para envio_vsx, so nas confirmadas com ficha que
    ainda nao tem linha. Nao apaga marcos_manuais e pode rodar de novo sem duplicar."""
    conn.execute(_SCHEMA_MARCOS)
    antigos = dict(conn.execute("SELECT nome, feito_em FROM marcos_manuais WHERE nome IN (?, ?)",
                                MARCOS_MANUAIS))
    if not antigos:
        return 0
    try:
        cand = carregar_candidatos(conn)
        feitas = set(pd.read_csv(fichas_csv)["tic"].astype(int))
    except Exception:
        return 0
    confirmadas = set(cand.loc[cand["decisao"] == "confirmado", "tic"].astype(int))
    _garantir_envio(conn)
    existentes = {r[0] for r in conn.execute("SELECT tic FROM envio_vsx")}
    enviada_em = antigos.get("Enviada ao VSX")
    aceita_em = antigos.get("Aceita no VSX")
    enviada_em = enviada_em or aceita_em
    novos = 0
    for tic in sorted(confirmadas & (feitas - existentes)):
        conn.execute("INSERT INTO envio_vsx (tic, enviada_em, aceita_em) VALUES (?, ?, ?)",
                     (tic, enviada_em, aceita_em))
        novos += 1
    conn.commit()
    return novos


def fichas_com_aviso(fichas_csv: Path, so_bloqueio: bool = True) -> set[int]:
    """Fichas incompletas: com aviso que impede a submissao (com so_bloqueio=False, tambem as
    de aviso brando, como a busca so na lista de catalogos). Rodar a Fase 8 de novo refaz so
    a busca que faltou."""
    try:
        df = pd.read_csv(fichas_csv, dtype=str, keep_default_na=False)
    except Exception:
        return set()
    if "avisos" not in df:
        return set()

    def conta(avisos: str) -> bool:
        partes = [a for a in avisos.split(" | ") if a.strip()]
        return any(MARCA_PODE_SUBMETER not in a for a in partes) if so_bloqueio else bool(partes)

    return set(df.loc[df["avisos"].map(conta), "tic"].astype(int))


def com_ficha(fichas_csv: Path) -> set[int]:
    """TICs que ja tem ficha no fichas.csv da Fase 8."""
    try:
        return set(pd.read_csv(fichas_csv)["tic"].astype(int))
    except Exception:
        return set()


def sem_ficha(confirmadas: set[int], fichas_csv: Path) -> set[int]:
    """Confirmadas que ainda nao estao no fichas.csv da Fase 8."""
    return set(confirmadas) - com_ficha(fichas_csv)


def marcos(conn: sqlite3.Connection, fichas_csv: Path) -> list[dict]:
    """Etapas do trabalho: acerto e avanco contam, confirmar candidata nao."""
    r = resumo_treino(ler_tentativas(conn))
    n = r.get("respostas", 0)
    if n < 20:
        treino = {"nome": "Treino em dia", "feito": False, "detalhe": f"faltam {20 - n} respostas"}
    else:
        treino = {"nome": "Treino em dia", "feito": r["recentes"] >= 0.8,
                  "detalhe": f"{r['recentes']:.0%} nas últimas 20"}

    try:
        cand = carregar_candidatos(conn)
    except Exception:  # banco recem-criado, sem candidatos_fase7
        cand = pd.DataFrame()
    revisadas = int((cand["decisao"] != "pendente").sum()) if not cand.empty else 0
    fila = {"nome": "Fila revisada", "feito": bool(len(cand)) and revisadas == len(cand),
            "detalhe": f"{revisadas} de {len(cand)}"}

    confirmadas = set(cand.loc[cand["decisao"] == "confirmado", "tic"].astype(int)) if not cand.empty else set()
    faltam = sem_ficha(confirmadas, fichas_csv)
    if not confirmadas:
        detalhe_ficha = "rode a Fase 8 depois de confirmar"
    elif faltam:
        detalhe_ficha = f"faltam {len(faltam)}: rode python -u src/ficha_vsx.py"
    else:
        detalhe_ficha = f"{len(confirmadas)} confirmada{'s' if len(confirmadas) != 1 else ''}"
    ficha = {"nome": "Ficha pronta", "feito": bool(confirmadas) and not faltam, "detalhe": detalhe_ficha}

    envios = ler_envios(conn)
    enviadas = set(envios.loc[envios["enviada_em"].notna(), "tic"].astype(int))
    aceitas = set(envios.loc[envios["aceita_em"].notna(), "tic"].astype(int))

    def envio(nome: str, marcadas: set[int]) -> dict:
        feitas = len(confirmadas & marcadas)
        return {"nome": nome, "feito": bool(confirmadas) and feitas == len(confirmadas),
                "detalhe": f"{feitas} de {len(confirmadas)}"}

    return [treino, fila, ficha,
            envio("Enviada ao VSX", enviadas), envio("Aceita no VSX", aceitas)]


def nivel_treino(h: pd.DataFrame) -> tuple[str, str]:
    """Nivel pelo acerto recente e pela constancia entre as respostas certas."""
    d = h[h["pergunta"] == "decisao"]
    if len(d) < 20:
        return "Aprendiz", f"faltam {20 - len(d)} respostas para o próximo nível"
    recentes = d.tail(20)
    taxa = float(recentes["pontos"].mean())
    if taxa < 0.6:
        return "Aprendiz", (f"acerto nas últimas 20 em {taxa:.0%}: precisa de 60% para "
                            "o nível Revisor")
    fracas = {c: float(g["pontos"].mean()) for c, g in recentes.groupby("certa")}
    fracas = {c: t for c, t in fracas.items() if t < 0.7}
    if taxa >= 0.8 and not fracas:
        return "Revisor confiável", ""
    if taxa < 0.8:
        return "Revisor", (f"acerto nas últimas 20 em {taxa:.0%}: precisa de 80% para "
                           "Revisor confiável")
    c = min(fracas, key=fracas.get)
    dica = {"descartado": "cuidado com confirmar demais",
            "confirmado": "cuidado com descartar demais",
            "duvida": "use a dúvida só quando os painéis não decidem"}
    return "Revisor", (f"acerto nos casos {_ROTULOS_CERTA.get(c, c)} abaixo de 70%: "
                       f"{dica.get(c, 'equilibre as respostas')}")
