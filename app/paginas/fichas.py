"""Fichas de submissao ao VSX (Fase 8) e envio por estrela (pagina do app)."""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app import dados, estilo
from config import DEMO, SQLITE_PATH, VSX_DIR
from src.ficha_vsx import ler_fichas

DESCRICAO = ("O que copiar para o formulário do VSX em cada estrela confirmada, com a curva em "
             "fase e os avisos da ficha. Marque aqui o envio e o aceite de cada uma.")
GUIA_VSX = "https://github.com/mpena2099/vagalume/blob/main/docs/submeter_vsx.md"


def conectar() -> sqlite3.Connection:
    return sqlite3.connect(str(SQLITE_PATH))


def salvar_envio(tic: int, origem: str):
    enviada = bool(st.session_state.get(f"env_{tic}"))
    aceita = bool(st.session_state.get(f"ace_{tic}"))
    # aceita implica enviada; desmarcar o envio desmarca o aceite
    if origem == "env" and not enviada:
        aceita = False
    elif aceita:
        enviada = True
    st.session_state[f"env_{tic}"], st.session_state[f"ace_{tic}"] = enviada, aceita
    with conectar() as conn:
        dados.marcar_envio(conn, tic, enviada=enviada, aceita=aceita,
                           nome_vsx=st.session_state.get(f"nome_{tic}", ""))


def _fmt(valor, formato: str) -> str:
    return "?" if valor is None else format(valor, formato)


def campos(f: dict) -> list[tuple[str, str, str]]:
    """(rotulo, valor para copiar, ajuda) dos campos do formulario do VSX."""
    itens = []
    nomes = f"TIC {f['tic']}"
    if "gaia_dr3" in f:
        nomes += f", Gaia DR3 {f['gaia_dr3']}"
    itens.append(("Outros nomes", nomes, ""))
    if "tipo_sugerido" in f:
        itens.append(("Tipo (sugestão)", f["tipo_sugerido"], f.get("motivo_tipo", "")))
    if "periodo_d" in f:
        periodo = _fmt(f["periodo_d"], ".5f")
        if "periodo_erro_d" in f:
            periodo += f" +- {_fmt(f['periodo_erro_d'], '.6f')}"
        itens.append(("Período (d)", periodo, ""))
    if "fase_secundario" in f:
        itens.append(("Mínimo secundário (fase)", _fmt(f["fase_secundario"], ".3f"), ""))
    if "epoca_bjd" in f:
        itens.append(("Época do mínimo (BJD)", _fmt(f["epoca_bjd"], ".4f"), ""))
    if "gaia_ra" in f:
        itens.append(("RA (Gaia DR3, graus)", _fmt(f["gaia_ra"], ".6f"), ""))
    if "gaia_dec" in f:
        itens.append(("Dec (Gaia DR3, graus)", _fmt(f["gaia_dec"], "+.6f"), ""))
    if "v_estimada" in f:
        itens.append(("Magnitude V (máxima)", _fmt(f["v_estimada"], ".2f"),
                      f"estimada do Gaia G {_fmt(f.get('gaia_g'), '.2f')} e BP-RP"))
    if "amplitude_mag_tess" in f:
        itens.append(("Amplitude (mag, TESS)", _fmt(f["amplitude_mag_tess"], ".3f"),
                      'marcar "Minimum is an amplitude", banda TESS'))
    setores = f.get("setores_usados") or f.get("setores")
    if setores:
        itens.append(("Setores TESS", setores, "TESS QLP"))
    if "vizier_variaveis" in f:
        itens.append(('VizieR a 30"', f["vizier_variaveis"], ""))
    if "suspeito_blend" in f:
        itens.append(("Suspeito de blend", "sim" if f["suspeito_blend"] else "não", ""))
    if "figura_triagem" in f:
        itens.append(("Figuras para anexar", f"{f.get('figura_fase', '')}\n{f['figura_triagem']}",
                      ""))
    return itens


if DEMO:
    st.stop()

estilo.cabecalho("Fichas do VSX", descricao=DESCRICAO)
st.markdown(f"**Como submeter:** login em [vsx.aavso.org](https://vsx.aavso.org) (menu Register), "
            f"menu Submit, **New Star Wizard**. Passo a passo e qual campo vai onde: "
            f"[guia de submissão]({GUIA_VSX}).")
caminho = VSX_DIR / "fichas.csv"
fichas = ler_fichas(caminho)
if not fichas:
    st.info("Nenhuma ficha ainda. Na página **Revisão**, depois de revisar a fila, use o botão "
            "**Gerar fichas do VSX**. Pelo terminal, na pasta do projeto, o mesmo comando é "
            "`python -u src/ficha_vsx.py` (`--duvidas` inclui as dúvidas).")
    st.stop()

try:
    with conectar() as conn:
        dados.migrar_envios(conn, caminho)
        envios = dados.ler_envios(conn)
except Exception as e:
    st.error(f"Não consegui ler os envios em {SQLITE_PATH}: {e}")
    envios = pd.DataFrame(columns=["tic", "enviada_em", "aceita_em", "nome_vsx"])
por_tic = envios.set_index("tic").to_dict("index") if not envios.empty else {}

for tic in sorted(fichas):
    f = fichas[tic]
    e = por_tic.get(tic, {})
    with st.container(border=True):
        st.subheader(f"TIC {tic}"
                     + (f" · {f['decisao'].capitalize()}" if f.get("decisao") else ""))
        avisos = str(f.get("avisos") or "").strip()
        if f.get("alerta_periodo"):
            st.warning(f"Período: {f['alerta_periodo']}")
        if avisos:
            st.warning(avisos.replace(" | ", "\n\n"))
        figura = VSX_DIR / f"{tic}_fase.png"
        if figura.exists():
            st.image(figura, width="stretch")
        else:
            st.caption("Curva em fase não encontrada em data/vsx.")

        with st.container(border=True):
            st.markdown("**Envio ao VSX**")
            st.session_state.setdefault(f"env_{tic}", bool(e.get("enviada_em")))
            st.session_state.setdefault(f"ace_{tic}", bool(e.get("aceita_em")))
            st.session_state.setdefault(f"nome_{tic}", e.get("nome_vsx") or "")
            c1, c2, c3 = st.columns([1, 1, 2], vertical_alignment="center")
            c1.checkbox("Enviada ao VSX", key=f"env_{tic}",
                        on_change=salvar_envio, args=(tic, "env"))
            c2.checkbox("Aceita no VSX", key=f"ace_{tic}",
                        on_change=salvar_envio, args=(tic, "ace"),
                        disabled=not st.session_state[f"env_{tic}"])
            c3.text_input("Nome no VSX", key=f"nome_{tic}",
                          on_change=salvar_envio, args=(tic, "nome"))
            if e.get("enviada_em"):
                st.caption(f"Enviada em {e['enviada_em']}"
                           + (f" · aceita em {e['aceita_em']}" if e.get("aceita_em") else ""))

        st.markdown("**Campos para copiar no formulário**")
        colunas = st.columns(2)
        for i, (rotulo, valor, ajuda) in enumerate(campos(f)):
            with colunas[i % 2]:
                st.markdown(f"**{rotulo}**")
                st.code(valor)
                if ajuda:
                    st.caption(ajuda)
