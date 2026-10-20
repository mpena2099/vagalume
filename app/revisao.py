"""Revisao visual das candidatas da Fase 7 (app local em Streamlit).

    streamlit run app/revisao.py

Mostra a figura de triagem e os numeros de cada candidata e grava a decisao
humana na tabela revisao_humana do mesmo banco. Rodar a partir da raiz do repositorio.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from app import dados
from config import SQLITE_PATH

ORDENACOES = {
    "Sinal mais forte primeiro (amplitude / ruído)": [("forca", False)],
    "Sinal mais centrado no alvo primeiro": [("deslocamento_px", True)],
    "Mais brilhante primeiro (Tmag)": [("tmag", True)],
}
ROTULOS = {"confirmado": "Confirmado", "duvida": "Dúvida", "descartado": "Descartado",
           "pendente": "Pendente"}

st.set_page_config(page_title="Vagalume: revisão visual", layout="wide")


def conectar() -> sqlite3.Connection:
    return sqlite3.connect(str(SQLITE_PATH))


def mover(delta: int, total: int):
    st.session_state.pos = max(0, min(total - 1, st.session_state.pos + delta))


def registrar(tic: int, decisao: str, total: int, fica_na_lista: bool):
    nota = st.session_state.get(f"nota_{tic}", "")
    with conectar() as conn:
        dados.salvar_revisao(conn, tic, decisao, nota)
    # Se a decisao tira a candidata da lista (ex: filtro Pendente), a proxima sobe
    # pra posicao atual: avancar aqui pularia uma sem mostrar.
    if fica_na_lista:
        mover(+1, total)


def limpar(tic: int):
    with conectar() as conn:
        dados.apagar_revisao(conn, tic)


# ---------------------------------------------------------------- dados
try:
    with conectar() as conn:
        todos = dados.carregar_candidatos(conn)
except Exception as e:
    st.error(f"Não consegui ler as candidatas em {SQLITE_PATH}: {e}\n\n"
             "Rode `python pipeline.py` (ou as fases 2 a 7) antes de abrir o app.")
    st.stop()

if todos.empty:
    st.warning("A tabela candidatos_fase7 está vazia.")
    st.stop()

# ---------------------------------------------------------------- barra lateral
st.sidebar.title("Vagalume")
contagem = todos["decisao"].value_counts()
st.sidebar.caption("  ·  ".join(f"{ROTULOS[k]}: {contagem.get(k, 0)}" for k in ROTULOS))
situacao = st.sidebar.selectbox("Situação", ["todas"] + list(ROTULOS), index=0,
                                format_func=lambda k: ROTULOS.get(k, "Todas"))
ordem = st.sidebar.selectbox("Ordenar por", list(ORDENACOES))
busca = st.sidebar.text_input("Buscar TIC")

lista = todos if situacao == "todas" else todos[todos["decisao"] == situacao]
if busca.strip():
    lista = lista[lista["tic"].astype(str).str.contains(busca.strip())]
cols, asc = zip(*ORDENACOES[ordem])
lista = lista.sort_values(list(cols), ascending=list(asc), na_position="last").reset_index(drop=True)

if lista.empty:
    st.info("Nenhuma candidata nesse filtro.")
    st.stop()

total = len(lista)
# Filtro novo = lista nova: volta pro inicio em vez de cair numa posicao qualquer.
assinatura = (situacao, ordem, busca.strip())
if st.session_state.get("assinatura") != assinatura:
    st.session_state.assinatura = assinatura
    st.session_state.pos = 0
st.session_state.pos = max(0, min(total - 1, st.session_state.get("pos", 0)))
nav = st.sidebar.columns(2)
nav[0].button("◀ Anterior", on_click=mover, args=(-1, total), width="stretch")
nav[1].button("Próxima ▶", on_click=mover, args=(+1, total), width="stretch")
st.sidebar.caption(f"{st.session_state.pos + 1} de {total}")

# ---------------------------------------------------------------- candidata
r = lista.iloc[st.session_state.pos].to_dict()
tic = int(r["tic"])
st.title(f"TIC {tic}")

m = st.columns(5)
m[0].metric("Período", f"{r['periodo_d']:.5f} d", r["metodo"].upper(), delta_color="off")
m[1].metric("Amplitude", f"{r['amplitude'] * 100:.2f}%",
            f"{r['forca']:.0f}x o ruído", delta_color="off")
m[2].metric("Tmag", f"{r['tmag']:.2f}")
desloc = r.get("deslocamento_px")
m[3].metric("Pico do sinal", "—" if pd.isna(desloc) else f"{desloc:.1f} px do alvo")
def _texto(v) -> str:
    return "" if v is None or pd.isna(v) else str(v)


m[4].metric("Outros setores", _texto(r.get("setores_extra")) or "—",
            _texto(r.get("periodos_extra")), delta_color="off")
st.caption(f"Todos os sinais da estrela: {r.get('sinais_todos')}  ·  "
           f"RA {r['ra']:.5f}  Dec {r['dec']:+.5f}")

for alerta in dados.alertas(r):
    st.warning(alerta)

if r.get("figura") and Path(r["figura"]).exists():
    st.image(r["figura"], width="stretch")
else:
    st.error(f"Sem figura para esta candidata: {r.get('erro') or 'rode a Fase 7 de novo'}")

st.markdown("  |  ".join(f"[{nome}]({url})" for nome, url in dados.links(r["ra"], r["dec"], tic).items()))

with st.expander("Como decidir (o que procurar na figura)"):
    st.markdown("""| O que você vê | Decisão |
|---|---|
| Curva dobrada limpa: os ciclos caem uns sobre os outros e a linha preta tem forma clara | segue para os outros itens |
| Curva dobrada borrada, sem forma, ou formada por um ou dois eventos isolados | **Descartar** ou **Dúvida** |
| Mapa de amplitude com o pico (x vermelho) sobre o alvo (+ verde) | a favor |
| Pico do sinal em outro pixel, sobre outra estrela | **Descartar** (o sinal é da vizinha) |
| Periodograma com um pico isolado e alto | a favor |
| Período perto de 1 d, 13,7 d ou 6,85 d, ou saltos na curva nas bordas das lacunas | **Descartar** (sistemático do TESS) |
| Links do VSX/SIMBAD mostram uma variável já catalogada com esse período a até ~2' | **Descartar** (já conhecida) |

**Detalhes que ajudam**
- Compare os painéis P e 2P. Se em 2P aparecem dois mínimos de profundidades diferentes, é binária eclipsante e o período real é 2P. Se os dois mínimos em 2P são iguais, há duas leituras: pulsante ou rotação com período P, ou binária de contato (EW) com período 2P. Amplitude grande (acima de ~10%) e P/2 acima de ~0,22 d favorecem EW; abaixo de ~0,2 d, só pulsante. Casos de referência no README.
- Eclipses estreitos e planos fora do eclipse: binária EA. Variação contínua com mínimos diferentes: EB. Mínimos quase iguais e variação contínua: EW (contato).
- Uma senoide com amplitude que muda de setor para setor costuma ser rotação (manchas).
- **Confirmar** não é descoberta: quer dizer que passa no olho. Antes de submeter ao VSX, refaça a busca de variáveis conhecidas e confira o checklist da especificação (seção 11).
- **Descartar** não apaga nada: a decisão fica gravada com a nota e dá para rever no filtro "Situação".
""")

st.subheader("Sua decisão")
if r["decisao"] != "pendente":
    st.success(f"Já marcada como **{ROTULOS[r['decisao']]}**."
               + (f" Nota: {r['nota']}" if pd.notna(r["nota"]) and r["nota"] else ""))
    st.button("Limpar decisão", on_click=limpar, args=(tic,))
st.text_area("Nota (opcional): tipo provável, período real, o que chamou atenção",
             key=f"nota_{tic}", value=r["nota"] if pd.notna(r["nota"]) else "", height=70)
b = st.columns(3)
b[0].button("Confirmar (parece real)", type="primary", on_click=registrar,
            args=(tic, "confirmado", total, situacao in ("todas", "confirmado")), width="stretch")
b[1].button("Dúvida", on_click=registrar, args=(tic, "duvida", total, situacao in ("todas", "duvida")), width="stretch")
b[2].button("Descartar (falso alarme)", on_click=registrar, args=(tic, "descartado", total, situacao in ("todas", "descartado")),
            width="stretch")
