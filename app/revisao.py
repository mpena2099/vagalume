"""Revisao visual das candidatas da Fase 7 (app local em Streamlit).

    streamlit run app/revisao.py

Mostra a figura de triagem e os numeros de cada candidata e grava a decisao
humana na tabela revisao_humana do mesmo banco. Rodar a partir da raiz do repositorio.
As paginas ficam em app/paginas/.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st

from app.estilo import css

st.set_page_config(page_title="Vagalume", page_icon="✨", layout="wide")
st.markdown(css(), unsafe_allow_html=True)

st.navigation([
    st.Page("paginas/fila.py", title="Revisão", icon=":material/fact_check:", default=True),
    st.Page("paginas/treino.py", title="Treino", icon=":material/school:"),
]).run()
