"""Estilo visual do app: CSS global e blocos HTML do cabecalho, ficha e checklist."""

import html

import streamlit as st

PROJECT = "Vagalume"
ICON = "✨"
TAGLINE = "Estrelas variáveis novas nas curvas de luz do TESS"
ACCENT = "#C6E84A"

_FUNDO = "#0B0F17"
_CARTAO = "#151B26"
_TEXTO = "#E6E9EF"
_SUAVE = "#9AA4B2"
_BORDA = "rgba(230, 233, 239, 0.12)"
_ICONES = {"ok": "✅", "atencao": "⚠️", "problema": "❌"}
_SUGESTOES = {
    "confirmado": ("Confirmado", "var(--vl-ok)"),
    "duvida": ("Dúvida", "var(--vl-atencao)"),
    "descartado": ("Descartado", "var(--vl-problema)"),
}


def css() -> str:
    return f"""<style>
:root {{
  --vl-fundo: {_FUNDO}; --vl-cartao: {_CARTAO}; --vl-texto: {_TEXTO};
  --vl-suave: {_SUAVE}; --vl-borda: {_BORDA}; --vl-destaque: {ACCENT};
  --vl-ok: #7BD88F; --vl-atencao: #E8C468; --vl-problema: #E8746E;
}}
/* texto branco sobre o destaque claro fica ilegivel */
button[kind="primary"], button[kind="primary"] p {{ color: var(--vl-fundo) !important; font-weight: 600; }}
.block-container {{ padding-top: 1rem; max-width: 1400px; }}
[data-testid="stAppDeployButton"], [data-testid="stDeployButton"] {{ display: none; }}
[data-testid="stMetricValue"] {{ font-size: 1.15rem; }}
.vl-cabecalho {{ display: flex; justify-content: space-between; align-items: center;
  gap: 1rem; background: var(--vl-cartao); border: 1px solid var(--vl-borda);
  border-radius: .8rem; padding: .85rem 1.1rem; margin-bottom: .8rem; }}
.vl-marca {{ color: var(--vl-destaque); font-size: 1.6rem; font-weight: 700; line-height: 1.2; }}
.vl-tagline {{ color: var(--vl-suave); font-size: .82rem; }}
.vl-subtitulo {{ font-size: 1rem; font-weight: 600; margin-top: .25rem; }}
.vl-descricao {{ color: var(--vl-suave); font-size: .85rem; margin-top: .2rem; max-width: 46rem; }}
.vl-progresso {{ min-width: 170px; text-align: right; }}
.vl-progresso-texto {{ font-size: .9rem; margin-bottom: .35rem; }}
.vl-barra {{ height: 5px; background: var(--vl-borda); border-radius: 999px; overflow: hidden; }}
.vl-barra span {{ display: block; height: 100%; background: var(--vl-destaque); }}
.vl-ficha {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: .45rem; }}
.vl-item {{ background: var(--vl-cartao); border: 1px solid var(--vl-borda);
  border-radius: .6rem; padding: .5rem .65rem; min-width: 0; }}
.vl-rotulo {{ color: var(--vl-suave); font-size: .68rem; text-transform: uppercase;
  letter-spacing: .04em; }}
.vl-valor {{ font-size: 1.15rem; font-weight: 600; overflow-wrap: anywhere; }}
.vl-detalhe {{ color: var(--vl-suave); font-size: .75rem; overflow-wrap: anywhere; }}
.vl-checklist {{ background: var(--vl-cartao); border: 1px solid var(--vl-borda);
  border-radius: .8rem; padding: .6rem .8rem; margin-top: .45rem; }}
.vl-linha {{ display: flex; flex-wrap: wrap; gap: .4rem; align-items: baseline;
  font-size: .85rem; padding: .15rem 0; }}
.vl-icone {{ flex: none; }}
.vl-linha b {{ white-space: nowrap; }}
.vl-explica {{ color: var(--vl-suave); flex: 1; min-width: 0; }}
.vl-pilula {{ display: inline-block; margin-top: .5rem; padding: .12rem .55rem;
  border-radius: 999px; font-size: .78rem; font-weight: 600; }}
.vl-nota {{ color: var(--vl-suave); font-size: .75rem; margin-top: .35rem; }}
.vl-trilha {{ display: flex; align-items: flex-start; background: var(--vl-cartao);
  border: 1px solid var(--vl-borda); border-radius: .8rem; padding: .55rem .4rem;
  margin-bottom: .8rem; }}
.vl-etapa {{ flex: 1; min-width: 0; text-align: center; padding: 0 .35rem; position: relative; }}
.vl-etapa + .vl-etapa::before {{ content: ""; position: absolute; top: .36rem; left: -50%;
  width: 100%; height: 2px; background: var(--vl-borda); }}
.vl-etapa.feito::before {{ background: var(--vl-destaque); }}
.vl-ponto {{ width: .72rem; height: .72rem; border-radius: 50%; margin: 0 auto .3rem;
  border: 2px solid var(--vl-suave); position: relative; z-index: 1; }}
.vl-etapa.feito .vl-ponto {{ background: var(--vl-destaque); border-color: var(--vl-destaque); }}
.vl-etapa-nome {{ font-size: .76rem; font-weight: 600; }}
.vl-etapa-detalhe {{ color: var(--vl-suave); font-size: .68rem; overflow-wrap: anywhere; }}
.st-key-figura_p, .st-key-figura_2p, .st-key-figura_mapa, .st-key-figura_unica {{
  background: #F2F4F7; padding: .4rem; border-radius: .6rem; }}
[data-testid="stImageCaption"] {{ color: var(--vl-suave); font-size: .72rem; }}
</style>"""


def cabecalho(subtitulo: str, progresso: tuple[float, int] | None = None,
              rotulo_progresso: str = "", descricao: str = "") -> None:
    barra = ""
    if progresso:
        atual, total = progresso
        valor = f"{atual:g}".replace(".", ",")
        texto = (f"Acertos {valor} de {total:g}" if rotulo_progresso == "acertos"
                 else f"{valor} de {total:g} {rotulo_progresso}".strip())
        pct = 100 * atual / total if total else 0
        barra = (f'<div class="vl-progresso"><div class="vl-progresso-texto">'
                 f'{html.escape(texto)}</div><div class="vl-barra">'
                 f'<span style="width:{pct:.1f}%"></span></div></div>')
    st.markdown(
        f'<div class="vl-cabecalho"><div>'
        f'<div class="vl-marca">{ICON} {PROJECT}</div>'
        f'<div class="vl-tagline">{html.escape(TAGLINE)}</div>'
        f'<div class="vl-subtitulo">{html.escape(subtitulo)}</div>'
        + (f'<div class="vl-descricao">{html.escape(descricao)}</div>' if descricao else "")
        + f'</div>{barra}</div>', unsafe_allow_html=True)


def ficha(itens: list[tuple[str, str, str | None]]) -> None:
    cartoes = []
    for rotulo, valor, detalhe in itens:
        extra = (f'<div class="vl-detalhe">{html.escape(str(detalhe))}</div>'
                 if detalhe else "")
        cartoes.append(
            f'<div class="vl-item"><div class="vl-rotulo">{html.escape(rotulo)}</div>'
            f'<div class="vl-valor">{html.escape(str(valor))}</div>{extra}</div>')
    st.markdown(f'<div class="vl-ficha">{"".join(cartoes)}</div>', unsafe_allow_html=True)


def checklist_html(itens: list[dict], sugestao: str) -> None:
    linhas = "".join(
        f'<div class="vl-linha"><span class="vl-icone">{_ICONES[i["estado"]]}</span>'
        f'<b>{html.escape(str(i["titulo"]))}</b>'
        f'<span class="vl-explica">{html.escape(str(i["explicacao"]))}</span></div>'
        for i in itens)
    rotulo, cor = _SUGESTOES[sugestao]
    st.markdown(
        f'<div class="vl-checklist">{linhas}'
        f'<div class="vl-pilula" style="color:{cor}; border:1px solid {cor}">'
        f'Sugestão do pipeline: {rotulo}</div>'
        f'<div class="vl-nota">A sugestão vale só se a conferência humana da curva dobrada '
        f'em P passar.</div></div>', unsafe_allow_html=True)


def trilha_html(marcos: list[dict]) -> None:
    etapas = "".join(
        f'<div class="vl-etapa{" feito" if m["feito"] else ""}"><div class="vl-ponto"></div>'
        f'<div class="vl-etapa-nome">{html.escape(str(m["nome"]))}</div>'
        f'<div class="vl-etapa-detalhe">{html.escape(str(m["detalhe"]))}</div></div>'
        for m in marcos)
    st.markdown(f'<div class="vl-trilha">{etapas}</div>', unsafe_allow_html=True)


def ancora_caso() -> None:
    """Marca o ponto da tela para onde subir depois de uma decisao (logo acima das imagens)."""
    st.markdown('<div id="topo-caso"></div>', unsafe_allow_html=True)


def subir_ao_caso() -> None:
    """Rola a pagina ate a ancora: depois de decidir, as imagens do proximo caso ficam a vista."""
    import time
    # o comentario com a hora faz o navegador executar o script a cada decisao
    st.iframe(
        f"<!-- {time.time()} --><script>const d = window.parent.document;"
        "const a = d.getElementById('topo-caso');"
        "if (a) { a.scrollIntoView({block: 'start'}); }"
        "else { const m = d.querySelector('[data-testid=\"stMain\"]'); if (m) m.scrollTo(0, 0); }"
        "</script>", height=1)
