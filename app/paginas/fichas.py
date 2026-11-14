"""Fichas de submissao ao VSX (Fase 8) e envio por estrela (pagina do app)."""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app import dados, estilo, vsx
from config import DEMO, SQLITE_PATH, VSX_DIR
from src.ficha_vsx import ler_fichas

DESCRICAO = ("O que copiar para o formulário do VSX em cada estrela confirmada, com a curva em "
             "fase e os avisos da ficha. Marque aqui o envio e o aceite de cada uma.")
GUIA_VSX = "https://github.com/mpena2099/vagalume/blob/main/docs/submeter_vsx.md"


def conectar() -> sqlite3.Connection:
    return sqlite3.connect(str(SQLITE_PATH))


def salvar_tipo(tic: int):
    with conectar() as conn:
        dados.marcar_tipo(conn, tic, st.session_state.get(f"tipo_{tic}"))


@st.cache_data(ttl=3600, show_spinner=False)
def consultar(ra: float, dec: float) -> list[dict]:
    return vsx.consultar_vsx(ra, dec)


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


def campos(f: dict, tipo_final: str | None = None) -> list[tuple[str, str, str]]:
    """(rotulo, valor para copiar, ajuda) dos campos do formulario do VSX."""
    itens = []
    nomes = f"TIC {f['tic']}"
    if "gaia_dr3" in f:
        nomes += f", Gaia DR3 {f['gaia_dr3']}"
    itens.append(("Outros nomes", nomes, ""))
    if tipo_final:
        itens.append(("Tipo", tipo_final, f.get("motivo_tipo", "")))
    elif "tipo_sugerido" in f:
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
    return itens


if DEMO:
    st.stop()

ICONES = {"ok": "✅", "atencao": "⚠️", "bloqueia": "❌"}

estilo.cabecalho("Fichas do VSX", descricao=DESCRICAO)
with st.expander("Login e envio no VSX"):
    st.markdown(
        "**Login no VSX, uma vez:** "
        "1. [Register](https://vsx.aavso.org/index.php?view=registration.top) (confirme pelo e-mail). "
        "2. [Log In](https://vsx.aavso.org/index.php?view=login.top). "
        "3. [Submit](https://vsx.aavso.org/index.php?view=submit.top), **New Star Wizard**. "
        f"Envie uma estrela por vez. Qual campo vai onde: [guia de submissão]({GUIA_VSX}).")
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
    envios = pd.DataFrame(columns=["tic", "enviada_em", "aceita_em", "nome_vsx", "tipo_final"])
por_tic = envios.set_index("tic").to_dict("index") if not envios.empty else {}


def vsx_da_ficha(f: dict) -> tuple[list[dict] | None, bool]:
    """(achados, falhou): None sem coordenada ou com o VSX fora do ar."""
    if "gaia_ra" not in f or "gaia_dec" not in f:
        return None, False
    try:
        return consultar(f["gaia_ra"], f["gaia_dec"]), False
    except Exception:
        return None, True


def anexo(rotulo: str, caminho_img: Path, nome: str, chave: str):
    if caminho_img.exists():
        st.download_button(rotulo, caminho_img.read_bytes(), file_name=nome, mime="image/png",
                           key=chave)
    else:
        st.caption(f"{rotulo}: arquivo não encontrado ({caminho_img.name}).")


def situacao(tic: int) -> tuple[list[dict] | None, list[tuple[str, str]], bool]:
    """(achados do VSX, pendencias, pronta) da estrela, com o tipo atual salvo."""
    f, e = fichas[tic], por_tic.get(tic, {})
    achados, falhou = vsx_da_ficha(f)
    if f"tipo_{tic}" not in st.session_state:
        sugerido = str(f.get("tipo_sugerido") or "").strip()
        st.session_state[f"tipo_{tic}"] = (e.get("tipo_final") or None) or (
            sugerido if sugerido in vsx.TIPOS_VSX else None)
    pend = vsx.pendencias(f, st.session_state.get(f"tipo_{tic}"), achados)
    if falhou:
        pend.append(("atencao", "VSX não respondeu agora"))
    return achados, pend, not any(n == "bloqueia" for n, _ in pend)


situacoes = {tic: situacao(tic) for tic in sorted(fichas)}


def rotulo_estrela(tic: int) -> str:
    return f"{tic} ✅ pronta" if situacoes[tic][2] else f"{tic} ⚠️ falta resolver"


tics = list(situacoes)
if st.session_state.get("ficha_sel") not in tics:
    st.session_state["ficha_sel"] = tics[0]
st.segmented_control("Estrela", tics, key="ficha_sel", format_func=rotulo_estrela,
                     selection_mode="single", label_visibility="collapsed")
tic = st.session_state.get("ficha_sel") or tics[0]

f = fichas[tic]
e = por_tic.get(tic, {})
achados, pend, pronta = situacoes[tic]
tipo_atual = st.session_state.get(f"tipo_{tic}")

figura = VSX_DIR / f"{tic}_fase.png"
triagem = Path(f["figura_triagem"]) if f.get("figura_triagem") else None
if triagem is not None and not triagem.is_absolute():
    triagem = ROOT / triagem

st.subheader(f"TIC {tic}" + (f" · {f['decisao'].capitalize()}" if f.get("decisao") else ""))
aba_resumo, aba_copiar, aba_detalhes, aba_envio = st.tabs(
    ["Resumo", "Copiar", "Detalhes", "Envio"])

with aba_resumo:
    if pronta:
        st.badge("Pronta para enviar", color="green")
    else:
        st.badge("Falta resolver", color="orange")
    prox = next((t for n, t in pend if n == "bloqueia"), None) or next(
        (t for n, t in pend if n == "atencao"), None)
    st.info(f"**Próximo passo:** {prox}" if prox else "**Próximo passo:** Copie os campos na aba Copiar.")
    for nivel, texto in pend:
        st.markdown(f"{ICONES[nivel]} {texto}")
    if figura.exists():
        st.image(figura, width="stretch")
    else:
        st.caption("Curva em fase não encontrada em data/vsx.")
    st.selectbox("Tipo de variável", list(vsx.TIPOS_VSX), key=f"tipo_{tic}", index=None,
                 placeholder="Escolha pela forma da curva",
                 format_func=lambda t: f"{t}: {vsx.TIPOS_VSX[t]}",
                 on_change=salvar_tipo, args=(tic,))
    if f.get("motivo_tipo"):
        st.caption(f["motivo_tipo"])
    tipo_atual = st.session_state.get(f"tipo_{tic}")

with aba_copiar:
    st.markdown("**Campos do New Star Wizard**")
    colunas = st.columns(2)
    for i, (rotulo, valor, ajuda) in enumerate(campos(f, tipo_atual)):
        with colunas[i % 2]:
            st.markdown(f"**{rotulo}**")
            st.code(valor)
            if ajuda:
                st.caption(ajuda)
    st.markdown("**Comentário para o moderador (em inglês)**")
    st.code(vsx.comentario(f, tipo_atual, achados), language=None, wrap_lines=True)
    st.markdown("**Anexos**")
    c1, c2 = st.columns(2)
    with c1:
        anexo("Baixar curva em fase", figura, f"TIC{tic}_fase.png", f"dl_fase_{tic}")
    with c2:
        anexo("Baixar figura da triagem", triagem or Path("triagem"), f"TIC{tic}_triagem.png",
              f"dl_tri_{tic}")

with aba_detalhes:
    st.markdown("**Mapa por pixel e curvas da triagem**")
    if triagem is not None and triagem.exists():
        st.image(triagem, width="stretch")
    else:
        st.caption("Figura da triagem não encontrada.")
    st.markdown("**Achados no VSX**")
    if achados:
        for a in achados:
            st.markdown(f"- [{a['nome']}]({a['url']}) · {a['tipo'] or 'tipo ?'} · "
                        f"{a['dist_arcsec']:.0f}\" · P {a['periodo'] or '?'}")
    else:
        st.caption("Nenhum achado no VSX a até 60\".")
    if st.button("Conferir no VSX de novo", key=f"vsxbtn_{tic}"):
        consultar.clear()
        st.rerun()
    if f.get("avisos"):
        st.markdown("**Avisos da ficha**")
        st.write(f["avisos"])
    if f.get("motivo_tipo"):
        st.markdown("**Motivo do tipo**")
        st.write(f["motivo_tipo"])
    if f.get("vizier_variaveis"):
        st.markdown('**VizieR a 30"**')
        st.write(f["vizier_variaveis"])

with aba_envio:
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
