"""Revisao visual das candidatas da Fase 7 (pagina do app)."""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app import dados, estilo, guia
from config import SQLITE_PATH

ORDENACOES = {
    "Sinal mais forte primeiro (amplitude / ruído)": [("forca", False)],
    "Sinal mais centrado no alvo primeiro": [("deslocamento_px", True)],
    "Mais brilhante primeiro (Tmag)": [("tmag", True)],
}
ROTULOS = {"confirmado": "Confirmado", "duvida": "Dúvida", "descartado": "Descartado",
           "pendente": "Pendente"}


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
    estilo.cabecalho("Revisão visual")
    st.error(f"Não consegui ler as candidatas em {SQLITE_PATH}: {e}\n\n"
             "Rode `python pipeline.py` (ou as fases 2 a 7) antes de abrir o app.")
    st.stop()

if todos.empty:
    estilo.cabecalho("Revisão visual")
    st.warning("A tabela candidatos_fase7 está vazia.")
    st.stop()

revisados = int((todos["decisao"] != "pendente").sum())
estilo.cabecalho("Revisão visual", (revisados, len(todos)), "revisados")

# ---------------------------------------------------------------- barra lateral
st.sidebar.markdown("##### Filtros")
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

# ---------------------------------------------------------------- candidata
r = lista.iloc[st.session_state.pos].to_dict()
tic = int(r["tic"])

nav = st.columns([1, 1, 5], vertical_alignment="center")
nav[0].button("◀ Anterior", on_click=mover, args=(-1, total), width="stretch")
nav[1].button("Próximo ▶", on_click=mover, args=(+1, total), width="stretch")
nav[2].markdown(
    f"**{st.session_state.pos + 1} de {total}** &nbsp;·&nbsp; TIC {tic} "
    f"&nbsp;·&nbsp; RA {r['ra']:.5f} &nbsp;·&nbsp; Dec {r['dec']:+.5f}",
    unsafe_allow_html=True)

try:
    with conectar() as conn:
        _treino = pd.read_sql("SELECT * FROM treino WHERE resposta != 'ambiguo'", conn)
except Exception:
    _treino = None
guia.mostrar_guia(st, _treino, aberto=False)

figura = Path(r["figura"]) if r.get("figura") else None
if figura and figura.exists():
    if figura.with_name(f"{tic}_p.png").exists():
        cols = st.columns(2)
        legendas = {k: f"**{titulo}.** {pergunta}" for k, (titulo, pergunta) in guia.ROTEIRO.items()}
        for col, nome in zip(cols, ("p", "mapa")):
            caminho = figura.with_name(f"{tic}_{nome}.png")
            if caminho.exists():
                with col.container(key=f"figura_{nome}"):
                    st.image(caminho, width="stretch")
                col.caption(legendas[nome])
            else:
                col.caption("Painel indisponível.")
        caminho_2p = figura.with_name(f"{tic}_2p.png")
        if caminho_2p.exists():
            with st.expander("Período: P ou 2P? (depois de confirmar, para a ficha do VSX)"):
                st.markdown(f"**{guia.PERIODO[0]}.** {guia.PERIODO[1]}")
                with st.columns(2)[0].container(key="figura_2p"):
                    st.image(caminho_2p, width="stretch")
    else:
        with st.container(key="figura_unica"):
            st.image(figura, width="stretch")
else:
    st.error(f"Sem figura para esta candidata: {r.get('erro') or 'rode a Fase 7 de novo'}")

st.markdown("  |  ".join(f"[{nome}]({url})" for nome, url in dados.links(r["ra"], r["dec"], tic).items()))

# ---------------------------------------------------------------- ficha e decisao
desloc = r.get("deslocamento_px")
def _texto(v) -> str:
    return "" if v is None or pd.isna(v) else str(v)


itens = dados.checklist(r)
esquerda, direita = st.columns([3, 2], gap="medium")
with esquerda:
    estilo.ficha([
        ("Período", f"{r['periodo_d']:.5f} d", r["metodo"].upper()),
        ("Amplitude", f"{r['amplitude'] * 100:.2f}%", f"{r['forca']:.1f}x o ruído"),
        ("Tmag", f"{r['tmag']:.2f}", None),
        ("Pico do sinal", "—" if pd.isna(desloc) else f"{desloc:.1f} px do alvo", None),
        ("Outros setores", _texto(r.get("setores_extra")) or "—",
         _texto(r.get("periodos_extra")) or None),
    ])
    st.caption(f"Todos os sinais da estrela: {r.get('sinais_todos')}")
    estilo.checklist_html(itens, dados.sugestao(itens))

with direita:
    with st.container(border=True):
        st.markdown("**Na curva dobrada em P, os pontos caem uns sobre os outros "
                    "formando uma linha clara?**")
        st.caption("Olhe o painel P: a linha preta deve repetir uma forma estável, "
                   "não uma nuvem borrada sem desenho.")
        if r["decisao"] != "pendente":
            st.success(f"Já marcada como **{ROTULOS[r['decisao']]}**."
                       + (f" Nota: {r['nota']}" if pd.notna(r["nota"]) and r["nota"] else ""))
            st.button("Limpar decisão", on_click=limpar, args=(tic,))
        st.text_area("Nota (opcional): tipo provável, período real, o que chamou atenção",
                     key=f"nota_{tic}", value=r["nota"] if pd.notna(r["nota"]) else "", height=70)
        b = st.columns(2)
        b[0].button("Confirmar (parece real)", type="primary", on_click=registrar,
                    args=(tic, "confirmado", total, situacao in ("todas", "confirmado")),
                    width="stretch")
        b[1].button("Dúvida", on_click=registrar,
                    args=(tic, "duvida", total, situacao in ("todas", "duvida")),
                    width="stretch")
        st.button("Descartar (falso alarme)", on_click=registrar,
                  args=(tic, "descartado", total, situacao in ("todas", "descartado")),
                  width="stretch")

if figura and figura.exists() and figura.with_name(f"{tic}_p.png").exists():
    with st.expander("Figura completa (curva no tempo, periodograma, campo)"):
        st.image(figura, width="stretch")

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
- Depois de confirmar, abra "Período: P ou 2P?" e compare as curvas. Se em 2P aparecem dois mínimos de profundidades diferentes, é binária eclipsante e o período real é 2P. Se em 2P sobra um vale só e o resto plano (e em P metade dos pontos atravessa o vale em 1,00), também é binária com período 2P: o segundo eclipse é raso demais. Se os dois mínimos em 2P são iguais, há duas leituras: pulsante ou rotação com período P, ou binária de contato (EW) com período 2P. Amplitude grande (acima de ~10%) e 2P (o período orbital) acima de ~0,22 d favorecem EW; com 2P abaixo de ~0,22 d, só pulsante. Casos de referência no README.
- Eclipses estreitos e planos fora do eclipse: binária EA. Variação contínua com mínimos diferentes: EB. Mínimos quase iguais e variação contínua: EW (contato).
- Uma senoide com amplitude que muda de setor para setor costuma ser rotação (manchas).
- **Confirmar** não é descoberta: quer dizer que passa no olho. Antes de submeter ao VSX, refaça a busca de variáveis conhecidas e confira o checklist da especificação (seção 11).
- **Descartar** não apaga nada: a decisão fica gravada com a nota e dá para rever no filtro "Situação".
""")
