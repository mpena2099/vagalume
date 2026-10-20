"""Modo treino: quiz com casos de resposta conhecida (pagina do app)."""

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app import dados, estilo, guia
from config import SQLITE_PATH

ROTULOS = {"confirmado": "Confirmado", "duvida": "Dúvida", "descartado": "Descartado"}


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
        treino = pd.read_sql("SELECT * FROM treino WHERE resposta != 'ambiguo'", conn)
except Exception:
    estilo.cabecalho("Treino")
    st.info("A tabela `treino` ainda não existe. Crie o conjunto com:\n\n"
            "```bash\npython -u tools/gerar_treino.py\n```")
    st.stop()

if treino.empty:
    estilo.cabecalho("Treino")
    st.info("A tabela `treino` está vazia. Rode `python -u tools/gerar_treino.py` "
            "para gerar os casos.")
    st.stop()

if "treino_ordem" not in st.session_state:
    comecar(treino)

ordem = st.session_state.treino_ordem
pos = st.session_state.treino_pos
feitos = st.session_state.treino_total
estilo.cabecalho("Treino", (st.session_state.treino_acertos, feitos), "acertos")

if pos >= len(ordem):
    st.success(f"Fim do treino: {st.session_state.treino_acertos:g} pontos em "
               f"{feitos} {'caso' if feitos == 1 else 'casos'}.")
    if st.button("Começar de novo"):
        comecar(treino)
        st.rerun()
    st.stop()

caso = ordem.iloc[pos]
st.markdown(f"**Caso {pos + 1} de {len(ordem)}** &nbsp;·&nbsp; "
            f"TIC {int(caso['tic'])} &nbsp;·&nbsp; {caso['metodo'].upper()}",
            unsafe_allow_html=True)

figura = Path(caso["figura"])
dados_json = figura.with_suffix(".json")
r = json.loads(dados_json.read_text(encoding="utf-8")) if dados_json.exists() else {}

guia.mostrar_guia(st, treino, aberto=pos == 0, excluir=caso["figura"])

if _painel(figura, "p").exists():
    cols = st.columns(3)
    legendas = {k: f"**{titulo}.** {pergunta}" for k, (titulo, pergunta) in guia.ROTEIRO.items()}
    for col, nome in zip(cols, ("p", "2p", "mapa")):
        caminho = _painel(figura, nome)
        if caminho.exists():
            with col.container(key=f"figura_{nome}"):
                st.image(caminho, width="stretch")
            col.caption(legendas[nome])
        else:
            col.caption("Painel indisponível.")
else:
    with st.container(key="figura_unica"):
        st.image(figura, width="stretch")

itens = dados.checklist(r)
esquerda, direita = st.columns([3, 2], gap="medium")
with esquerda:
    estilo.ficha([
        ("Período", _texto(r.get("periodo_d"), "{:.5f} d"), _texto(r.get("metodo"), "{}").upper()),
        ("Amplitude", _texto(r.get("amplitude"), "{:.2%}"),
         "sem força medida" if r.get("forca") is None or pd.isna(r.get("forca"))
         else f"{r['forca']:.1f}x o ruído"),
        ("Tmag", _texto(r.get("tmag"), "{:.2f}"), None),
        ("Pico do sinal", _texto(r.get("deslocamento_px"), "{:.1f} px do alvo"), None),
        ("Outros setores", _texto(r.get("setores_extra"), "{}") or "—",
         _texto(r.get("periodos_extra"), "{}") or None),
    ])
    estilo.checklist_html(itens, dados.sugestao(itens))

with direita:
    with st.container(border=True):
        res = st.session_state.treino_resultado
        if res is None:
            st.markdown("**Qual é a sua decisão?**")
            escolha = None
            if st.button("Confirmar (parece real)", type="primary", width="stretch"):
                escolha = "confirmado"
            b = st.columns(2)
            if b[0].button("Dúvida", width="stretch"):
                escolha = "duvida"
            if b[1].button("Descartar", width="stretch"):
                escolha = "descartado"
            if escolha:
                certa = caso["resposta"]
                pontos = 1.0 if escolha == certa else (0.5 if escolha == "duvida" else 0.0)
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
            st.info(f"**Onde estava a pista.** {guia.pista(r, certa, caso['explicacao'])}")
            if st.button("Próximo ▶", type="primary"):
                st.session_state.treino_pos += 1
                st.session_state.treino_resultado = None
                st.rerun()
