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
from config import SQLITE_PATH, TREINO_DIR, VSX_DIR

DESCRICAO = ("Casos de resposta conhecida, para aprender a decidir antes da revisão de verdade. "
             "Você responde, vê a resposta certa com a explicação e onde estava a pista. Nada "
             "muda nas candidatas; só o seu histórico de acertos é gravado.")
ROTULOS = {"confirmado": "Confirmado", "duvida": "Dúvida", "descartado": "Descartado"}


def _painel(figura: Path, nome: str) -> Path:
    return figura.with_name(f"{figura.stem}_{nome}.png")


def _texto(v, formato: str) -> str:
    return "—" if v is None or pd.isna(v) else formato.format(v)


def _amplitude(r) -> float:
    try:
        return float(json.loads((TREINO_DIR / f"{r.tic}_{r.metodo}.json").read_text(encoding="utf-8"))["amplitude"])
    except (OSError, ValueError, KeyError, TypeError):
        return 0.0


def comecar(treino: pd.DataFrame):
    # mesmo numero de casos por resposta: senao responder sempre a classe maior pontua bem;
    # sem semente fixa, cada sessao sorteia outros casos
    n = int(treino["resposta"].value_counts().min())
    partes = []
    for _, grupo in treino.groupby("resposta"):
        if len(grupo) > n:
            # os confirmados tem sinal forte; sortear metade dos descartados entre os de maior
            # amplitude deixa o quiz mais parecido com a fila, onde o sinal fraco e a regra
            grupo = grupo.assign(amp=[_amplitude(r) for r in grupo.itertuples()]).sort_values("amp")
            fracos, fortes = grupo.iloc[:len(grupo) // 2], grupo.iloc[len(grupo) // 2:]
            n_fortes = min(len(fortes), (n + 1) // 2)
            grupo = pd.concat([fortes.sample(n_fortes), fracos.sample(n - n_fortes)])
        partes.append(grupo)
    equilibrado = pd.concat(partes)
    st.session_state.treino_ordem = equilibrado.sample(frac=1).reset_index(drop=True)
    st.session_state.treino_pos = 0
    st.session_state.treino_acertos = 0.0
    st.session_state.treino_total = 0
    # respostas por posicao: voltar a um caso mostra a resposta dada, sem pontuar de novo
    st.session_state.treino_respostas = {}
    st.session_state.treino_periodos = {}
    st.session_state.treino_periodo_acertos = 0
    st.session_state.treino_periodo_total = 0


try:
    with sqlite3.connect(SQLITE_PATH) as conn:
        treino = pd.read_sql("SELECT * FROM treino WHERE resposta != 'ambiguo'", conn)
except Exception:
    estilo.cabecalho("Treino", descricao=DESCRICAO)
    st.info("A tabela `treino` ainda não existe. Crie o conjunto com:\n\n"
            "```bash\npython -u tools/gerar_treino.py\n```")
    st.stop()

if treino.empty:
    estilo.cabecalho("Treino", descricao=DESCRICAO)
    st.info("A tabela `treino` está vazia. Rode `python -u tools/gerar_treino.py` "
            "para gerar os casos.")
    st.stop()

if "treino_respostas" not in st.session_state:  # sessao nova ou de versao antiga do app
    comecar(treino)

ordem = st.session_state.treino_ordem
pos = st.session_state.treino_pos
feitos = st.session_state.treino_total
estilo.cabecalho("Treino", (st.session_state.treino_acertos, feitos), "acertos", DESCRICAO)
# no treino so importa a primeira etapa da trilha: uma linha com o nivel e o que falta
with sqlite3.connect(SQLITE_PATH) as conn:
    _etapa = dados.marcos(conn, VSX_DIR / "fichas.csv")[0]
    _nivel, _falta = dados.nivel_treino(dados.ler_tentativas(conn))
st.info(f"**Nível: {_nivel}.** "
        + ("Treino em dia ✅" if _etapa["feito"]
           else f"Para \"Treino em dia\" (80% nas últimas 20): {_etapa['detalhe']}.")
        # com poucas respostas a dica do nivel repete o que falta para a etapa
        + (f" {_falta[0].upper()}{_falta[1:]}." if _falta and not _falta.startswith("faltam") else ""))


def mostrar_historico():
    """Aproveitamento de todas as sessoes, gravado no banco."""
    with sqlite3.connect(SQLITE_PATH) as conn:
        h = dados.ler_tentativas(conn)
    r = dados.resumo_treino(h)
    if r:
        titulo = (f"Seu histórico: {r['geral']:.0%} de acerto em {r['respostas']} "
                  f"{'resposta' if r['respostas'] == 1 else 'respostas'}")
    else:
        titulo = "Seu histórico: ainda sem respostas"
    with st.expander(titulo):
        if not r:
            st.caption("Responda os casos abaixo para subir de nível.")
            return
        metricas = [("Geral", f"{r['geral']:.0%}", None,
                     f"{r['respostas']} respostas em {r['dias']} dia(s)"),
                    (f"Últimas {r['n_recentes']}", f"{r['recentes']:.0%}",
                     f"{(r['recentes'] - r['geral']) * 100:+.0f} pontos", None)]
        metricas += [(f"Quando era {ROTULOS[certa]}", f"{taxa:.0%}", None, f"{n} casos")
                     for certa, (taxa, n) in r["por_certa"].items()]
        if "periodo" in r:
            metricas.append(("Período P ou 2P", f"{r['periodo'][0]:.0%}", None,
                             f"{r['periodo'][1]} respostas"))
        for col, (rotulo, valor, delta, ajuda) in zip(st.columns(len(metricas)), metricas):
            col.metric(rotulo, valor, delta=delta, help=ajuda)
        st.caption("Acerto muito diferente entre as colunas \"Quando era\" indica viés, por "
                   "exemplo confirmar quase tudo. Dúvida vale meio ponto.")


mostrar_historico()

if pos >= len(ordem):
    st.success(f"Fim do treino: {st.session_state.treino_acertos:g} pontos em "
               f"{feitos} {'caso' if feitos == 1 else 'casos'}.")
    fim = st.columns([1, 1, 6])
    if fim[0].button("◀ Voltar", width="stretch"):
        st.session_state.treino_pos -= 1
        st.rerun()
    if fim[1].button("Começar de novo", width="stretch"):
        comecar(treino)
        st.rerun()
    st.stop()

caso = ordem.iloc[pos]


def _gravar(escolha: str, certa: str, pontos: float, pergunta: str = "decisao"):
    with sqlite3.connect(SQLITE_PATH) as conn:
        dados.salvar_tentativa(conn, f"{int(caso['tic'])}_{caso['metodo']}", escolha, certa,
                               pontos, pergunta)


def mover(delta: int):
    st.session_state.treino_pos = max(0, min(len(ordem), st.session_state.treino_pos + delta))


# guia antes da navegacao: logo acima do caso ele parecia fazer parte dele
guia.mostrar_guia(st, treino, aberto=pos == 0, excluir=caso["figura"])
nav = st.columns([1, 1, 6])
nav[0].button("◀ Anterior", on_click=mover, args=(-1,), disabled=pos == 0, width="stretch")
nav[1].button("Próximo ▶", on_click=mover, args=(+1,), width="stretch")
st.markdown(f"**Caso {pos + 1} de {len(ordem)}** &nbsp;·&nbsp; "
            f"TIC {int(caso['tic'])} &nbsp;·&nbsp; {caso['metodo'].upper()}",
            unsafe_allow_html=True)

figura = Path(caso["figura"])
dados_json = figura.with_suffix(".json")
r = json.loads(dados_json.read_text(encoding="utf-8")) if dados_json.exists() else {}


if _painel(figura, "p").exists():
    cols = st.columns(2)
    legendas = {k: f"**{titulo}.** {pergunta}" for k, (titulo, pergunta) in guia.ROTEIRO.items()}
    for col, nome in zip(cols, ("p", "mapa")):
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
        res = st.session_state.treino_respostas.get(pos)
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
                st.session_state.treino_respostas[pos] = {"escolha": escolha, "pontos": pontos}
                _gravar(escolha, certa, pontos)
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
            per_certo = guia.periodo_certo(caso["explicacao"], r) if certa == "confirmado" else None
            if per_certo:
                st.markdown("**Segunda pergunta: o período certo é P ou 2P?** Compare a curva "
                            "em P, acima, com a curva em 2P:")
                with st.expander("Relembrar: o que muda entre P e 2P"):
                    st.markdown(guia.PERIODO[1])
                    guia.mostrar_figura_periodo(st)
                if _painel(figura, "2p").exists():
                    with st.container(key="figura_2p"):
                        st.image(_painel(figura, "2p"), width="stretch")
                escolha_p = st.session_state.treino_periodos.get(pos)
                if escolha_p is None:
                    bp = st.columns(2)
                    for col, opcao in zip(bp, ("P", "2P")):
                        if col.button(opcao, key=f"per_{opcao}", width="stretch"):
                            st.session_state.treino_periodos[pos] = opcao
                            st.session_state.treino_periodo_total += 1
                            st.session_state.treino_periodo_acertos += int(opcao == per_certo)
                            _gravar(opcao, per_certo, float(opcao == per_certo), "periodo")
                            st.rerun()
                else:
                    (st.success if escolha_p == per_certo else st.error)(
                        f"Período: você marcou {escolha_p}, o certo é {per_certo}.")
                    st.caption(guia.explicar_periodo(per_certo, r))
            if st.session_state.get("treino_periodo_total"):
                st.caption(f"Acertos de período: {st.session_state.treino_periodo_acertos} de "
                           f"{st.session_state.treino_periodo_total}")
            if st.button("Próximo ▶", type="primary"):
                st.session_state.treino_pos += 1
                st.rerun()
