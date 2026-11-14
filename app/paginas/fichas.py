"""Fichas de submissao ao VSX (Fase 8) e envio por estrela (pagina do app)."""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app import dados, estilo, paineis, vsx
from config import DEMO, MARCA_PODE_SUBMETER, SQLITE_PATH, VSX_DIR
from src.ficha_vsx import ler_fichas

DESCRICAO = "Confira cada estrela confirmada, copie os campos no VSX e marque o envio."
FILTROS = ["A enviar", "Todas", "Enviadas", "Aceitas"]
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
        envios = dados.ler_envios(conn)
    if origem == "env" and enviada:
        # segue para a proxima estrela ainda nao enviada
        ficha_aberta(proxima_a_enviar(tic, set(envios.loc[envios["enviada_em"].notna(), "tic"])))


def ficha_aberta(tic: int | None):
    """Abre a estrela na pagina; a tabela volta ao estado sem selecao."""
    if tic is not None:
        st.session_state["ficha_sel"] = tic
        st.session_state["ficha_tab_n"] = st.session_state.get("ficha_tab_n", 0) + 1


def proxima_a_enviar(atual: int, enviadas: set[int]) -> int | None:
    """Proxima estrela (depois da atual, dando a volta) que ainda nao foi enviada."""
    tics = sorted(st.session_state.get("ficha_tics", []))
    depois = [t for t in tics if t > atual] + [t for t in tics if t < atual]
    return next((t for t in depois if t not in enviadas), None)


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
    return itens


if DEMO:
    st.stop()

ICONES = {"ok": "✅", "atencao": "⚠️", "bloqueia": "❌"}

estilo.cabecalho("Fichas do VSX", descricao=DESCRICAO)

try:
    with conectar() as conn:
        _cand = dados.carregar_candidatos(conn)
    confirmadas = set(_cand.loc[_cand["decisao"] == "confirmado", "tic"].astype(int))
except Exception:
    confirmadas = set()
paineis.painel_ficha_pagina(confirmadas)

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
    st.info("Nenhuma ficha ainda. Confirme candidatas na página **Revisão** e use **Gerar fichas "
            "do VSX** acima. Pelo terminal, na pasta do projeto, o mesmo comando é "
            "`python -u src/ficha_vsx.py` (`--duvidas` inclui as dúvidas).")
    st.stop()

try:
    with conectar() as conn:
        dados.migrar_envios(conn, caminho)
        envios = dados.ler_envios(conn)
except Exception as e:
    st.error(f"Não consegui ler os envios em {SQLITE_PATH}: {e}")
    envios = pd.DataFrame(columns=["tic", "enviada_em", "aceita_em", "nome_vsx", "tipo_final"])
tics = sorted(fichas)
st.session_state["ficha_tics"] = tics


def detectar_aceites(envios: pd.DataFrame) -> list[tuple[int, str]]:
    """Estrelas enviadas e ainda nao aceitas que ja aparecem no VSX a ate 10": marca o aceite
    e guarda o nome. So essas estrelas sao consultadas (cache de 1 h por coordenada)."""
    if envios.empty:
        return []
    esperando = envios[envios["enviada_em"].notna() & envios["aceita_em"].isna()]
    novos = []
    for t in esperando["tic"].astype(int):
        f = fichas.get(t)
        if not f or "gaia_ra" not in f or "gaia_dec" not in f:
            continue
        try:
            nome = vsx.aceite_detectado(consultar(f["gaia_ra"], f["gaia_dec"]))
        except Exception:
            continue  # VSX fora do ar: tenta de novo na proxima abertura
        if nome:
            with conectar() as conn:
                dados.marcar_envio(conn, t, aceita=True, nome_vsx=nome)
            st.session_state[f"ace_{t}"], st.session_state[f"nome_{t}"] = True, nome
            novos.append((t, nome))
    return novos


_aceites = detectar_aceites(envios)
for _t, _nome in _aceites:
    st.toast(f"TIC {_t} aceita no VSX como {_nome}", icon=":material/check_circle:")
    st.success(f"TIC {_t} aceita no VSX como {_nome}.")
if _aceites:
    with conectar() as conn:
        envios = dados.ler_envios(conn)
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


def tipo_salvo(tic: int) -> str | None:
    salvo = por_tic.get(tic, {}).get("tipo_final")
    return salvo if pd.notna(salvo) and salvo else None


def tipo_inicial(tic: int) -> str | None:
    """Tipo salvo ou, sem ele, a sugestao da ficha quando e um tipo unico do VSX ou o tipo
    provavel (que ainda pede confirmacao)."""
    sugerido = str(fichas[tic].get("tipo_sugerido") or "").strip()
    provavel = str(fichas[tic].get("tipo_provavel") or "").strip()
    return tipo_salvo(tic) or (sugerido if sugerido in vsx.TIPOS_VSX else None) or (
        provavel if provavel in vsx.TIPOS_VSX else None)


def pendencias_de(tic: int, achados) -> list[tuple[str, str]]:
    atual = tipo_de(tic)
    return vsx.pendencias(fichas[tic], atual, achados, confirmado=atual == tipo_salvo(tic))


def tipo_de(tic: int) -> str | None:
    return st.session_state[f"tipo_{tic}"] if f"tipo_{tic}" in st.session_state else tipo_inicial(tic)


def o_que_falta(tic: int) -> str:
    """Resumo curto das pendencias locais, para a tabela."""
    curtos = []
    for nivel, texto in pendencias_de(tic, []):
        if nivel == "ok":
            continue
        if texto.startswith("Escolha o tipo"):
            curtos.append("Escolher o tipo")
        elif texto.startswith("Confirme o tipo"):
            curtos.append("Confirmar o tipo provável")
        elif texto.startswith("Períodos"):
            curtos.append("Conferir período")
        elif texto.startswith("Blend: sinal parece"):
            curtos.append("Blend: sinal da vizinha")
        elif texto.startswith(("Vizinha", "Blend")):
            curtos.append("Conferir vizinha (blend)")
        elif nivel == "bloqueia":
            curtos.append("Aviso da ficha")
    return ", ".join(dict.fromkeys(curtos)) or "Nada"


def situacao_local(tic: int) -> str:
    """Situacao so com dados locais (ficha, tipo, envio): nenhuma consulta de rede."""
    e = por_tic.get(tic, {})
    if pd.notna(e.get("aceita_em")) and e.get("aceita_em"):
        return "aceita"
    if pd.notna(e.get("enviada_em")) and e.get("enviada_em"):
        return "enviada"
    pend = pendencias_de(tic, [])
    return "falta resolver" if any(n == "bloqueia" for n, _ in pend) else "pronta"


def vizinha(lista: list[int], atual: int, passo: int) -> int | None:
    """Estrela anterior (passo -1) ou seguinte (+1) na lista, dando a volta."""
    if not lista:
        return None
    if atual not in lista:
        return lista[0] if passo > 0 else lista[-1]
    return lista[(lista.index(atual) + passo) % len(lista)]


def clicar_tabela(chave: str, lista: list[int]):
    """Clique em qualquer celula da linha abre a estrela."""
    celulas = st.session_state[chave]["selection"].get("cells", [])
    if celulas:
        ficha_aberta(lista[celulas[0][0]])


def andar(passo: int):
    filtro = st.session_state.get("ficha_filtro") or "A enviar"
    ficha_aberta(vizinha(grupos[filtro], st.session_state["ficha_sel"], passo))


situacoes = {t: situacao_local(t) for t in tics}
enviadas_ou_aceitas = {"enviada", "aceita"}
grupos = {
    "A enviar": [t for t in tics if situacoes[t] not in enviadas_ou_aceitas],
    "Todas": tics,
    "Enviadas": [t for t in tics if situacoes[t] == "enviada"],
    "Aceitas": [t for t in tics if situacoes[t] == "aceita"],
}
if st.session_state.get("ficha_sel") not in tics:
    st.session_state["ficha_sel"] = (grupos["A enviar"] or tics)[0]

# ---------------------------------------------------------------- lista
topo = st.columns([4, 1, 1], vertical_alignment="bottom")
filtro = topo[0].segmented_control(
    "Mostrar", FILTROS, key="ficha_filtro", default="A enviar", selection_mode="single",
    format_func=lambda k: f"{k} ({len(grupos[k])})") or "A enviar"
visiveis = grupos[filtro]
topo[1].button("Anterior", icon=":material/skip_previous:", on_click=andar, args=(-1,),
               disabled=not visiveis, width="stretch")
topo[2].button("Próxima", icon=":material/skip_next:", on_click=andar, args=(1,),
               disabled=not visiveis, width="stretch")
if visiveis:
    aberta = st.session_state.get("ficha_sel")
    tabela = pd.DataFrame({
        " ": ["▶" if t == aberta else "" for t in visiveis],
        "TIC": visiveis,
        "Tipo": [tipo_de(t) or "?" for t in visiveis],
        "Situação": [situacoes[t].capitalize() for t in visiveis],
        "O que falta": ["" if situacoes[t] in enviadas_ou_aceitas else o_que_falta(t)
                        for t in visiveis],
        "P (d)": [fichas[t].get("periodo_d") for t in visiveis],
        "V": [fichas[t].get("v_estimada") for t in visiveis],
    })
    chave_tab = f"ficha_tabela_{filtro}_{st.session_state.get('ficha_tab_n', 0)}"
    destaque = tabela.style.apply(
        lambda linha: ["background-color: rgba(255, 196, 0, 0.18); font-weight: 600"
                       if linha["TIC"] == aberta else "" for _ in linha], axis=1)
    st.dataframe(
        destaque, hide_index=True, width="stretch", height=min(36 * (len(visiveis) + 1) + 3, 215),
        on_select=lambda: clicar_tabela(chave_tab, visiveis), selection_mode="single-cell",
        key=chave_tab,
        column_config={" ": st.column_config.TextColumn(width=30),
                       "TIC": st.column_config.NumberColumn(format="%d"),
                       "P (d)": st.column_config.NumberColumn(format="%.5f"),
                       "V": st.column_config.NumberColumn(format="%.2f")})
else:
    st.caption("Nenhuma estrela nesse filtro.")

tic = st.session_state["ficha_sel"]
f = fichas[tic]
e = por_tic.get(tic, {})
st.session_state.setdefault(f"tipo_{tic}", tipo_inicial(tic))
achados, falhou = vsx_da_ficha(f)
pend = pendencias_de(tic, achados)
if falhou:
    pend.append(("atencao", "VSX não respondeu agora"))
abertas = [(n, t) for n, t in pend if n != "ok"]
bloqueadas = [(n, t) for n, t in abertas if n == "bloqueia"] + [
    (n, t) for n, t in abertas if n != "bloqueia"]

figura = VSX_DIR / f"{tic}_fase.png"
triagem = Path(f["figura_triagem"]) if f.get("figura_triagem") else None
if triagem is not None and not triagem.is_absolute():
    triagem = ROOT / triagem

st.subheader(f"TIC {tic}" + (f" · {f['decisao'].capitalize()}" if f.get("decisao") else "")
             + f" · {situacoes[tic].capitalize()}")
aba_conferir, aba_enviar = st.tabs(["Conferir", "Enviar"])

with aba_conferir:
    st.info(f"**Próximo passo:** {bloqueadas[0][1]}" if bloqueadas
            else "**Próximo passo:** Tudo certo: siga para a aba Enviar.")
    for nivel, texto in bloqueadas[1:]:
        st.markdown(f"{ICONES[nivel]} {texto}")
    if MARCA_PODE_SUBMETER in (f.get("avisos") or ""):
        with st.expander("Por que posso enviar com o VizieR do CDS fora do ar?"):
            st.markdown(
                "- **O VSX está no ar** (é da AAVSO, outro servidor). Esta página consulta o VSX "
                "ao vivo em volta da estrela: é a checagem que evita enviar uma estrela já submetida.\n"
                "- **Os principais catálogos de variáveis foram consultados** no espelho do VizieR "
                "(VSX, GCVS, Gaia DR3, ATLAS, ASAS-SN, TESS, ZTF e outros, 25 no total), sem nada a 30\".\n"
                "- **Falta só a varredura nos milhares de catálogos restantes** do VizieR, a maioria "
                "sem relação com variáveis. É um pente-fino extra; o moderador do VSX confere de "
                "qualquer forma antes de aceitar.\n\n"
                "Quando o CDS voltar, gerar as fichas de novo refaz a busca completa sozinho. "
                "No pior caso, o moderador responde que a estrela já era conhecida.")
    if figura.exists():
        st.image(figura, width="stretch")
    else:
        st.caption("Curva em fase não encontrada em data/vsx.")
    st.selectbox("Tipo de variável", list(vsx.TIPOS_VSX), key=f"tipo_{tic}", index=None,
                 placeholder="Escolha pela forma da curva",
                 format_func=lambda t: f"{t}: {vsx.TIPOS_VSX[t]}",
                 on_change=salvar_tipo, args=(tic,))
    provavel = f.get("tipo_provavel")
    if provavel and st.session_state.get(f"tipo_{tic}") == provavel and tipo_salvo(tic) != provavel:
        st.button(f"Confirmar o tipo provável {provavel}", key=f"conf_tipo_{tic}",
                  on_click=salvar_tipo, args=(tic,), help=f.get("motivo_provavel"))
    with st.expander("Detalhes"):
        if f.get("motivo_tipo"):
            st.markdown("**Motivo do tipo**")
            st.write(f["motivo_tipo"])
        if f.get("motivo_provavel"):
            st.markdown("**Tipo provável**")
            st.write((f"{provavel}: " if provavel else "") + f["motivo_provavel"]
                     + (f" (Teff {f['gaia_teff']:.0f} K"
                        + (f", logg {f['gaia_logg']:.1f}" if "gaia_logg" in f else "")
                        + (f", raio {f['gaia_raio']:.2f} R☉" if "gaia_raio" in f else "") + ")"
                        if "gaia_teff" in f else ""))
        if f.get("oc_fases"):
            st.markdown("**O-C do mínimo por setor (em fase)**")
            st.write(f["oc_fases"] + (f"; máximo {f['oc_max_fase']:.3f}, limite 0,02"
                                      if "oc_max_fase" in f else ""))
        if f.get("alerta_periodo"):
            st.write(f["alerta_periodo"])
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
        st.markdown("**Mapa por pixel e curvas da triagem**")
        if triagem is not None and triagem.exists():
            st.image(triagem, width="stretch")
        else:
            st.caption("Figura da triagem não encontrada.")
        if f.get("avisos"):
            st.markdown("**Avisos da ficha**")
            st.write(f["avisos"])
        if "suspeito_blend" in f:
            st.markdown("**Blend**")
            if f.get("blend_motivo"):
                st.write(f"{f['blend_veredito'].capitalize()}: {f['blend_motivo']}")
            else:
                st.write("Suspeito: vizinha Gaia brilhante perto." if f["suspeito_blend"]
                         else "Sem vizinha Gaia brilhante suspeita.")
        if f.get("vizier_variaveis"):
            st.markdown('**VizieR a 30"**')
            st.write(f["vizier_variaveis"])

with aba_enviar:
    tipo_atual = st.session_state.get(f"tipo_{tic}")
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
    st.divider()
    st.session_state.setdefault(f"env_{tic}", bool(pd.notna(e.get("enviada_em")) and e.get("enviada_em")))
    st.session_state.setdefault(f"ace_{tic}", bool(pd.notna(e.get("aceita_em")) and e.get("aceita_em")))
    st.session_state.setdefault(f"nome_{tic}", e.get("nome_vsx") if pd.notna(e.get("nome_vsx")) else "")
    c1, c2, c3 = st.columns([1, 1, 2], vertical_alignment="center")
    c1.checkbox("Enviada ao VSX", key=f"env_{tic}",
                on_change=salvar_envio, args=(tic, "env"))
    c2.checkbox("Aceita no VSX", key=f"ace_{tic}",
                on_change=salvar_envio, args=(tic, "ace"),
                disabled=not st.session_state[f"env_{tic}"])
    c3.text_input("Nome no VSX", key=f"nome_{tic}",
                  on_change=salvar_envio, args=(tic, "nome"))
    if pd.notna(e.get("enviada_em")) and e.get("enviada_em"):
        st.caption(f"Enviada em {e['enviada_em']}"
                   + (f" · aceita em {e['aceita_em']}" if pd.notna(e.get("aceita_em")) and e.get("aceita_em") else ""))
