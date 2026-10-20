"""Modo treino: quiz com casos de resposta conhecida (app multipagina do Streamlit)."""

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app import dados
from config import SQLITE_PATH

ROTULOS = {"confirmado": "Confirmado", "duvida": "Dúvida", "descartado": "Descartado"}
ICONES = {"ok": "✅", "atencao": "⚠️", "problema": "❌"}

st.set_page_config(page_title="Vagalume: treino", layout="wide")
st.title("Modo treino")


def _painel(figura: Path, nome: str) -> Path:
    return figura.with_name(f"{figura.stem}_{nome}.png")


def _texto(v, formato: str) -> str:
    return "—" if v is None or pd.isna(v) else formato.format(v)


def comecar(treino: pd.DataFrame):
    st.session_state.treino_ordem = treino.sample(frac=1, random_state=42).reset_index(drop=True)
    st.session_state.treino_pos = 0
    st.session_state.treino_acertos = 0.0
    st.session_state.treino_total = 0
    st.session_state.treino_resultado = None


try:
    with sqlite3.connect(SQLITE_PATH) as conn:
        treino = pd.read_sql("SELECT * FROM treino", conn)
except Exception:
    st.info("A tabela `treino` ainda não existe. Crie o conjunto com:\n\n"
            "```bash\npython -u tools/gerar_treino.py\n```")
    st.stop()

if treino.empty:
    st.info("A tabela `treino` está vazia. Rode `python -u tools/gerar_treino.py` "
            "para gerar os casos.")
    st.stop()

if "treino_ordem" not in st.session_state:
    comecar(treino)

ordem = st.session_state.treino_ordem
pos = st.session_state.treino_pos
if st.session_state.treino_total:
    feitos = st.session_state.treino_total
    st.caption(f"Acertos: {st.session_state.treino_acertos:g} de {feitos} "
               f"{'caso' if feitos == 1 else 'casos'} (dúvida vale 0,5)")

if pos >= len(ordem):
    total = st.session_state.treino_total
    st.success(f"Fim do treino: {st.session_state.treino_acertos:g} pontos em "
               f"{total} {'caso' if total == 1 else 'casos'}.")
    if st.button("Começar de novo"):
        comecar(treino)
        st.rerun()
    st.stop()

caso = ordem.iloc[pos]
st.subheader(f"TIC {int(caso['tic'])} ({caso['metodo'].upper()})")

figura = Path(caso["figura"])
dados_json = figura.with_suffix(".json")
r = json.loads(dados_json.read_text(encoding="utf-8")) if dados_json.exists() else {}

m = st.columns(5)
m[0].metric("Período", _texto(r.get("periodo_d"), "{:.5f} d"),
            _texto(r.get("metodo"), "{}").upper(), delta_color="off")
forca = r.get("forca")
m[1].metric("Amplitude", _texto(r.get("amplitude"), "{:.2%}"),
            "sem força medida" if forca is None or pd.isna(forca)
            else f"{forca:.0f}x o ruído", delta_color="off")
m[2].metric("Tmag", _texto(r.get("tmag"), "{:.2f}"))
m[3].metric("Pico do sinal", _texto(r.get("deslocamento_px"), "{:.1f} px do alvo"))
m[4].metric("Outros setores", _texto(r.get("setores_extra"), "{}") or "—",
            _texto(r.get("periodos_extra"), "{}"), delta_color="off")

if _painel(figura, "p").exists():
    cols = st.columns(3)
    legendas = {
        "p": "Dobrada em P: procure os ciclos sobrepostos formando uma linha clara.",
        "2p": "Dobrada em 2P: mínimos de profundidades diferentes indicam período 2P.",
        "mapa": "Sinal por pixel: o x vermelho (pico) deve cair sobre o + verde (alvo).",
    }
    for col, nome in zip(cols, ("p", "2p", "mapa")):
        caminho = _painel(figura, nome)
        if caminho.exists():
            col.image(caminho, caption=legendas[nome], width="stretch")
        else:
            col.caption("Painel indisponível.")
else:
    st.image(figura, width="stretch")

for item in dados.checklist(r):
    st.markdown(f"{ICONES[item['estado']]} **{item['titulo']}**: {item['explicacao']}")

res = st.session_state.treino_resultado
if res is None:
    st.markdown("**Qual é a sua decisão?**")
    b = st.columns(3)
    escolha = None
    if b[0].button("Confirmar (parece real)", type="primary", width="stretch"):
        escolha = "confirmado"
    if b[1].button("Dúvida", width="stretch"):
        escolha = "duvida"
    if b[2].button("Descartar (falso alarme)", width="stretch"):
        escolha = "descartado"
    if escolha:
        certa = caso["resposta"]
        pontos = 1.0 if escolha == certa else (0.5 if escolha == "dúvida" else 0.0)
        st.session_state.treino_acertos += pontos
        st.session_state.treino_total += 1
        st.session_state.treino_resultado = {"escolha": escolha, "pontos": pontos}
        st.rerun()
else:
    certa = caso["resposta"]
    if res["pontos"] == 1.0:
        st.success("Você acertou.")
    elif res["pontos"] == 0.5:
        st.warning("Meio ponto: você respondeu dúvida.")
    else:
        st.error(f"Você errou: a resposta era {ROTULOS[certa]}.")
    st.markdown(f"**Resposta certa: {ROTULOS[certa]}.** {caso['explicacao']}")
    if st.button("Próximo ▶", type="primary"):
        st.session_state.treino_pos += 1
        st.session_state.treino_resultado = None
        st.rerun()
