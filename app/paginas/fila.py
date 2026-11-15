"""Revisao visual das candidatas da Fase 7 (pagina do app)."""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app import dados, estilo, execucao, guia, paineis
from config import SQLITE_PATH, VSX_DIR

ORDENACOES = {
    "Sinal mais forte primeiro (amplitude / ruído)": [("forca", False)],
    "Sinal mais centrado no alvo primeiro": [("deslocamento_px", True)],
    "Mais brilhante primeiro (Tmag)": [("tmag", True)],
}
DESCRICAO = "Olhe a curva em P e o mapa de cada candidata e decida. As confirmadas viram fichas."
ROTULOS = {"confirmado": "Confirmado", "duvida": "Dúvida", "descartado": "Descartado",
           "pendente": "Pendente"}


def conectar() -> sqlite3.Connection:
    return sqlite3.connect(str(SQLITE_PATH))


def mover(delta: int, total: int):
    st.session_state.pos = max(0, min(total - 1, st.session_state.pos + delta))
    st.session_state.tab_n = st.session_state.get("tab_n", 0) + 1


def registrar(tic: int, decisao: str, total: int, fica_na_lista: bool):
    nota = st.session_state.get(f"nota_{tic}", "")
    with conectar() as conn:
        dados.salvar_revisao(conn, tic, decisao, nota)
    # Se a decisao tira a candidata da lista (filtro Pendente), a proxima sobe pra posicao
    # atual: avancar aqui pularia uma sem mostrar.
    if fica_na_lista:
        mover(+1, total)
    else:
        st.session_state.tab_n = st.session_state.get("tab_n", 0) + 1
    st.session_state.subir = True


def rever(tic: int):
    with conectar() as conn:
        dados.rever_auto(conn, tic)


def limpar(tic: int):
    with conectar() as conn:
        dados.apagar_revisao(conn, tic)


# ---------------------------------------------------------------- dados
try:
    with conectar() as conn:
        dados.descartar_automaticos(conn)  # idempotente; nunca toca em decisao existente
        todos = dados.carregar_candidatos(conn)
except Exception:
    # primeiro uso: o banco ainda nao tem as tabelas do pipeline; a busca abaixo as cria
    todos = pd.DataFrame(columns=["decisao"])

_pendentes = int((todos["decisao"] == "pendente").sum()) if not todos.empty else 0
with st.sidebar.expander("Buscar novas candidatas", icon=":material/travel_explore:",
                         expanded=execucao.rodando() or _pendentes == 0):
    paineis.painel_busca(_pendentes)

if todos.empty:
    estilo.cabecalho("Revisão", descricao=DESCRICAO)
    st.info("**Ainda não há candidatas.** Para a primeira busca, abra **Buscar novas "
            "candidatas** na barra lateral e clique em **Buscar mais candidatas** (duas vezes, "
            "para confirmar). Ela escolhe sozinha uma região do céu, baixa as curvas do TESS e "
            "leva de 1 a 2 horas; pode fechar o navegador, ela continua. Quando terminar, as "
            "candidatas aparecem aqui.")
    st.stop()

revisados = int((todos["decisao"] != "pendente").sum())
pendentes = len(todos) - revisados
estilo.cabecalho("Revisão", (revisados, len(todos)), "revisados", DESCRICAO)
with conectar() as conn:
    dados.migrar_envios(conn, VSX_DIR / "fichas.csv")
    estilo.trilha_html(dados.marcos(conn, VSX_DIR / "fichas.csv"))
confirmadas = set(todos.loc[todos["decisao"] == "confirmado", "tic"].astype(int))
sem_ficha = len(dados.sem_ficha(confirmadas, VSX_DIR / "fichas.csv"))

resumo = st.columns([1, 3], vertical_alignment="center")
resumo[0].markdown(f"**{pendentes} pendentes**" if pendentes else "**Fila revisada**")
if sem_ficha:
    with resumo[1]:
        st.page_link("paginas/fichas.py", icon=":material/menu_book:",
                     label=f"{sem_ficha} confirmada(s) sem ficha: gerar na página Fichas")
elif not pendentes:
    resumo[1].caption("Nenhuma candidata pendente.")

auto = todos[todos["origem"] == "auto"]
if not auto.empty:
    with st.expander(f"{len(auto)} descartada{'s' if len(auto) != 1 else ''} automaticamente"):
        st.caption("Descartadas só por evidência direta: pico do sinal longe demais do alvo. "
                   "Rever devolve a candidata para a fila de pendentes.")
        for a in auto.sort_values("tic").to_dict("records"):
            c = st.columns([2, 8, 2], vertical_alignment="center")
            c[0].markdown(f"**TIC {int(a['tic'])}**")
            c[1].caption(a["motivo_auto"])
            c[2].button("Rever", key=f"rever_{int(a['tic'])}", on_click=rever,
                        args=(int(a["tic"]),), width="stretch")

# ---------------------------------------------------------------- filtros
st.sidebar.markdown("##### Filtros")
situacao = st.sidebar.selectbox("Situação", ["todas"] + list(ROTULOS),
                                index=1 + list(ROTULOS).index("pendente"),
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
    st.session_state.tab_n = st.session_state.get("tab_n", 0) + 1
st.session_state.pos = max(0, min(total - 1, st.session_state.get("pos", 0)))

# ---------------------------------------------------------------- tabela
tabela = pd.DataFrame({
    "TIC": lista["tic"].astype(int),
    "P (d)": lista["periodo_d"].round(5),
    "Amplitude (%)": (lista["amplitude"] * 100).round(2),
    "Força (x ruído)": lista["forca"].round(1),
    "Pico (px do alvo)": lista["deslocamento_px"].round(1),
    "Sugestão": [{"confirmado": "Confirmar", "duvida": "Dúvida", "descartado": "Descartar"}[
        dados.sugestao(dados.checklist(r))] for r in lista.to_dict("records")],
    "Decisão": lista["decisao"].map(ROTULOS),
})
chave_tab = f"fila_tabela_{st.session_state.get('tab_n', 0)}"


def clicar_tabela():
    """Clique em qualquer celula da linha abre a candidata."""
    celulas = st.session_state[chave_tab]["selection"].get("cells", [])
    if celulas:
        st.session_state.pos = min(total - 1, celulas[0][0])
        st.session_state.tab_n = st.session_state.get("tab_n", 0) + 1


aberta = st.session_state.pos
tabela.insert(0, " ", ["▶" if i == aberta else "" for i in range(total)])
destaque = tabela.style.apply(
    lambda linha: ["background-color: rgba(255, 196, 0, 0.18); font-weight: 600"
                   if linha.name == aberta else "" for _ in linha], axis=1)
st.dataframe(
    destaque, hide_index=True, width="stretch", height=min(36 * (total + 1) + 3, 215),
    on_select=clicar_tabela, selection_mode="single-cell", key=chave_tab,
    column_config={" ": st.column_config.TextColumn(width=30)})

# ---------------------------------------------------------------- candidata
r = lista.iloc[st.session_state.pos].to_dict()
tic = int(r["tic"])

estilo.ancora_caso()
if st.session_state.pop("subir", False):
    estilo.subir_ao_caso()
nav = st.columns([1, 1, 5], vertical_alignment="center")
nav[0].button("◀ Anterior", on_click=mover, args=(-1, total), width="stretch")
nav[1].button("Próximo ▶", on_click=mover, args=(+1, total), width="stretch")
nav[2].markdown(
    f"**{st.session_state.pos + 1} de {total}** &nbsp;·&nbsp; TIC {tic} "
    f"&nbsp;·&nbsp; RA {r['ra']:.5f} &nbsp;·&nbsp; Dec {r['dec']:+.5f} &nbsp;·&nbsp; "
    + "  |  ".join(f"[{nome}]({url})" for nome, url in dados.links(r["ra"], r["dec"], tic).items()),
    unsafe_allow_html=True)

try:
    with conectar() as conn:
        _treino = pd.read_sql("SELECT * FROM treino WHERE resposta != 'ambiguo'", conn)
except Exception:
    _treino = None
guia.mostrar_guia(st, _treino, aberto=False)


def _texto(v) -> str:
    return "" if v is None or pd.isna(v) else str(v)


desloc = r.get("deslocamento_px")
itens = dados.checklist(r)
figura = Path(r["figura"]) if r.get("figura") else None
tem_paineis = bool(figura and figura.exists() and figura.with_name(f"{tic}_p.png").exists())

esquerda, direita = st.columns([5, 2], gap="medium")
with esquerda:
    if tem_paineis:
        legendas = {k: f"**{titulo}.** {pergunta}" for k, (titulo, pergunta) in guia.ROTEIRO.items()}
        for col, nome in zip(st.columns(2), ("p", "mapa")):
            caminho = figura.with_name(f"{tic}_{nome}.png")
            if caminho.exists():
                with col.container(key=f"figura_{nome}"):
                    st.image(caminho, width="stretch")
                col.caption(legendas[nome])
            else:
                col.caption("Painel indisponível.")
        caminho_2p = figura.with_name(f"{tic}_2p.png")
        if caminho_2p.exists():
            with st.expander("Antes de confirmar, olhe a curva em 2P",
                             expanded=r.get("metodo") == "bls"):
                with st.columns(2)[0].container(key="figura_2p"):
                    st.image(caminho_2p, width="stretch")
                st.markdown("Dois vales diferentes, ou um vale só e o resto plano: binária, o "
                            "período da ficha é 2P. A mesma onda duas vezes: pulsante ou "
                            "rotação, o período é P. Detalhes e figura no guia acima.")
    elif figura and figura.exists():
        with st.container(key="figura_unica"):
            st.image(figura, width="stretch")
    else:
        st.error(f"Sem figura para esta candidata: {r.get('erro') or 'rode a Fase 7 de novo'}")

with direita:
    with st.container(border=True):
        st.markdown("**Na curva dobrada em P, os pontos caem uns sobre os outros "
                    "formando uma linha clara?**")
        if r["decisao"] != "pendente":
            st.success(f"Já marcada como **{ROTULOS[r['decisao']]}**"
                       + (" (automático)." if r.get("origem") == "auto" else ".")
                       + (f" Nota: {r['nota']}" if pd.notna(r["nota"]) and r["nota"] else ""))
            if r.get("origem") == "auto":
                st.caption(r["motivo_auto"])
                st.button("Rever", key=f"rever_caso_{tic}", on_click=rever, args=(tic,))
            else:
                st.button("Limpar decisão", on_click=limpar, args=(tic,))
        st.text_area("Nota (opcional)", key=f"nota_{tic}", height=70,
                     value=r["nota"] if pd.notna(r["nota"]) else "",
                     placeholder="Tipo provável, período real, o que chamou atenção")
        st.button("Confirmar (parece real)", type="primary", on_click=registrar,
                  args=(tic, "confirmado", total, situacao in ("todas", "confirmado")),
                  width="stretch")
        b = st.columns(2)
        b[0].button("Dúvida", on_click=registrar,
                    args=(tic, "duvida", total, situacao in ("todas", "duvida")),
                    width="stretch")
        b[1].button("Descartar", on_click=registrar,
                    args=(tic, "descartado", total, situacao in ("todas", "descartado")),
                    width="stretch")

c_ficha, c_check = st.columns([3, 2], gap="medium")
with c_ficha:
    estilo.ficha([
        ("Período", f"{r['periodo_d']:.5f} d", r["metodo"].upper()),
        ("Amplitude", f"{r['amplitude'] * 100:.2f}%", f"{r['forca']:.1f}x o ruído"),
        ("Tmag", f"{r['tmag']:.2f}", None),
        ("Pico do sinal", "—" if pd.isna(desloc) else f"{desloc:.1f} px do alvo", None),
        ("Outros setores", _texto(r.get("setores_extra")) or "—",
         _texto(r.get("periodos_extra")) or None),
    ])
    st.caption(f"Todos os sinais da estrela: {r.get('sinais_todos')}")
with c_check:
    estilo.checklist_html(itens, dados.sugestao(itens))

if tem_paineis:
    with st.expander("Figura completa (curva no tempo, periodograma, campo)"):
        st.image(figura, width="stretch")
