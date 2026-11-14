"""Pipeline pelo app: busca de candidatas (Fase 2 a 7) e geracao das fichas do VSX (Fase 8).

Busca e geracao rodam em segundo plano e uma bloqueia a outra. A busca fica na barra lateral
da Fila; a geracao das fichas, no topo da pagina Fichas.
"""

from datetime import datetime

import streamlit as st

from app import dados, execucao
from config import VSX_DIR


def buscar():
    st.session_state.confirmar_busca = False
    if not execucao.rodando():  # clique duplo nao abre duas buscas
        execucao.iniciar()


def pedir_confirmacao(sim: bool):
    st.session_state.confirmar_busca = sim


def esquecer_busca():
    execucao.LOG.unlink(missing_ok=True)


def esquecer_ficha():
    execucao.FICHA_LOG.unlink(missing_ok=True)


def iniciar_fichas():
    st.session_state.confirmar_fichas = False
    if not execucao.rodando() and not execucao.rodando_ficha():
        execucao.iniciar_ficha(bool(st.session_state.get("fichas_duvidas", False)))


def pedir_confirmacao_fichas(sim: bool):
    st.session_state.confirmar_fichas = sim


def pedir_cancelar_fichas(sim: bool):
    st.session_state.confirmar_cancelar_ficha = sim


def cancelar_fichas():
    execucao.cancelar_ficha()
    st.session_state.confirmar_cancelar_ficha = False


def botao_buscar(chave: str):
    if execucao.rodando_ficha():
        st.button("Buscar mais candidatas", disabled=True, key=f"{chave}_espera")
        st.info("A geração das fichas do VSX está rodando: espere terminar para buscar mais "
                "candidatas.")
        return
    # dois passos: um clique sem querer nao dispara 1 a 2 horas de rede
    if st.session_state.get("confirmar_busca"):
        st.warning("A busca leva 1 a 2 horas e baixa curvas de ~500 estrelas. Começar agora?")
        sim, nao = st.columns(2)
        sim.button("Sim, buscar", type="primary", on_click=buscar, key=f"{chave}_sim",
                   width="stretch")
        nao.button("Não", on_click=pedir_confirmacao, args=(False,), key=f"{chave}_nao",
                   width="stretch")
    else:
        st.button("Buscar mais candidatas", type="primary", on_click=pedir_confirmacao,
                  args=(True,), key=chave)
    st.caption("Escolhe sozinho uma região do céu ainda não varrida e roda o pipeline "
               "inteiro (1 a 2 horas). Pode fechar a página: a busca continua. "
               "Pelo terminal, na pasta do projeto:")
    st.code(execucao.COMANDO, language="bash")


@st.fragment(run_every=5)
def progresso():
    if not execucao.rodando():
        st.rerun()  # terminou: recarrega a pagina inteira com as candidatas novas
    log = execucao.ler_log()
    e = execucao.estado(log)
    # sem log, ou log de uma rodada anterior: veio do terminal (log vazio = acabou de comecar)
    if not execucao.LOG.exists() or e["terminou"] or e["erro"] or e["cancelada"]:
        st.info("Uma busca de candidatas está rodando, iniciada pelo terminal: o progresso "
                "aparece lá. As candidatas novas entram na fila quando ela terminar.")
        return
    minutos = execucao.minutos_desde_inicio()
    with st.container(border=True):
        st.markdown("**Buscando mais candidatas**"
                    + (f" no campo {e['campo']}" if e["campo"] else ""))
        texto = e["fase"] or "Escolhendo o campo"
        if e["progresso"]:
            i, n = e["progresso"]
            st.progress(min(i / n, 1.0), text=f"{texto}: {i} de {n}")
        else:
            st.progress(0.0, text=texto)
        st.caption(("" if minutos is None else f"{minutos:.0f} min desde o início. ")
                   + "Pode fechar a página: a busca continua e as candidatas novas entram na fila.")
        with st.expander("Ver o log"):
            st.code("\n".join(execucao.ler_log().splitlines()[-15:]) or "(vazio)")
        st.button("Cancelar busca", on_click=execucao.cancelar,
                  help="Encerra agora. Esta região é refeita do início na próxima busca; "
                       "suas decisões não são tocadas.")


@st.fragment(run_every=5)
def progresso_ficha():
    if not execucao.rodando_ficha():
        st.rerun()
    log = execucao.ler_log_ficha()
    e = execucao.estado_ficha(log)
    if not execucao.FICHA_LOG.exists() or e["erro"] or e["cancelada"] or e["terminou"]:
        st.info("A geração das fichas do VSX está rodando, iniciada pelo terminal: o progresso "
                "aparece lá. As fichas entram na página Fichas quando ela terminar.")
        return
    minutos = execucao.minutos_desde_inicio(execucao.FICHA_LOG)
    with st.container(border=True):
        st.markdown("**Gerando as fichas do VSX**"
                    + (f" na TIC {e['tic']}" if e["tic"] else ""))
        texto = e["etapa"] or "Preparando"
        if e["progresso"]:
            i, n = e["progresso"]
            st.progress(min(i / n, 1.0), text=f"{texto}: {i} de {n}")
        else:
            st.progress(0.0, text=texto)
        st.caption(("" if minutos is None else f"{minutos:.0f} min desde o início. ")
                   + "Pode fechar a página: as fichas continuam e ficam salvas.")
        with st.expander("Ver o log"):
            st.code("\n".join(log.splitlines()[-15:]) or "(vazio)")
        if st.session_state.get("confirmar_cancelar_ficha"):
            st.warning("Cancelar agora? As fichas já gravadas ficam salvas.")
            sim, nao = st.columns(2)
            sim.button("Sim, cancelar", type="primary", on_click=cancelar_fichas,
                       key="ficha_cancelar_sim", width="stretch")
            nao.button("Não", on_click=pedir_cancelar_fichas, args=(False,),
                       key="ficha_cancelar_nao", width="stretch")
        else:
            st.button("Cancelar geração", on_click=pedir_cancelar_fichas, args=(True,),
                      key="ficha_cancelar",
                      help="Encerra agora. As fichas já gravadas não são apagadas; rodar de "
                           "novo retoma.")


@st.cache_data(ttl=1800, show_spinner="Testando o VizieR...")
def vizier_no_ar() -> tuple[bool, str]:
    return execucao.vizier_no_ar(), datetime.now().strftime("%H:%M")


def aviso_vizier():
    """Ficha incompleta depende do VizieR de Estrasburgo: diz se ele voltou."""
    no_ar, hora = vizier_no_ar()
    if no_ar:
        st.success(f"O VizieR está respondendo (testado às {hora}): gere as fichas de novo para "
                   "completar a busca que faltou.")
    else:
        st.info(f"O VizieR de Estrasburgo ainda está fora do ar (testado às {hora}; o app testa "
                "de novo a cada 30 min). Gerar agora deve falhar de novo na mesma busca.")
        st.button("Testar agora", on_click=vizier_no_ar.clear, key="vizier_testar")


def botao_fichas(sem_ficha: int):
    if execucao.rodando():
        st.button("Gerar fichas do VSX", disabled=True, key="fichas_gerar_espera")
        st.info("A busca de candidatas está rodando: espere terminar para gerar as fichas.")
        return
    st.checkbox("Incluir as marcadas como dúvida", key="fichas_duvidas")
    if st.session_state.get("confirmar_fichas"):
        st.warning(f"Gerar ou completar {sem_ficha} ficha(s) do VSX? Leva alguns minutos por estrela.")
        sim, nao = st.columns(2)
        sim.button("Sim, gerar", type="primary", on_click=iniciar_fichas,
                   key="fichas_sim", width="stretch")
        nao.button("Não", on_click=pedir_confirmacao_fichas, args=(False,),
                   key="fichas_nao", width="stretch")
    else:
        st.button("Gerar fichas do VSX", type="primary", on_click=pedir_confirmacao_fichas,
                  args=(True,), key="fichas_gerar")
    st.caption("Mede o período com todos os setores do TESS, sugere o tipo e grava "
               "`data/vsx/fichas.md`. Pelo terminal, na pasta do projeto:")
    st.code(execucao.FICHA_COMANDO, language="bash")


def painel_ficha(sem_ficha: int, incompletas: int = 0):
    """Fase 8 pelo app: progresso se roda, resultado da ultima e botao quando falta ficha."""
    if execucao.rodando_ficha():
        progresso_ficha()
        return
    e = execucao.estado_ficha(execucao.ler_log_ficha())
    if e["erro"]:
        st.error(f"A geração das fichas parou ({e['erro']}). Tentar de novo retoma as prontas.")
        st.button("Ok", on_click=esquecer_ficha, key="ficha_erro_ok")
    elif e["cancelada"]:
        st.info("Geração de fichas cancelada. As fichas prontas ficaram salvas; rodar de novo "
                "retoma.")
        st.button("Ok", on_click=esquecer_ficha, key="ficha_cancelada_ok")
    elif e["terminou"]:
        total = len(dados.com_ficha(VSX_DIR / "fichas.csv"))
        faltam = len(dados.fichas_com_aviso(VSX_DIR / "fichas.csv"))
        if faltam:
            st.warning(f"Geração terminada: {total - faltam} de {total} fichas prontas e {faltam} "
                       "ainda incompleta(s), porque a busca num servidor externo (VizieR ou Gaia) "
                       "não respondeu. Gere de novo mais tarde: só essa busca é refeita. Os "
                       "avisos de cada uma estão na lista abaixo.")
        else:
            st.success(f"Geração terminada: as {total} fichas estão prontas.")
        st.button("Ok", on_click=esquecer_ficha, key="ficha_fim_ok")
    if incompletas:
        aviso_vizier()
    if sem_ficha + incompletas:
        botao_fichas(sem_ficha + incompletas)


def contagens_fichas(confirmadas: set[int]) -> tuple[int, int, int]:
    """(sem ficha, incompletas que bloqueiam, parciais so com aviso brando) das confirmadas."""
    csv = VSX_DIR / "fichas.csv"
    bloqueiam = dados.fichas_com_aviso(csv)
    brandas = dados.fichas_com_aviso(csv, so_bloqueio=False) - bloqueiam
    return len(dados.sem_ficha(confirmadas, csv)), len(confirmadas & bloqueiam), len(confirmadas & brandas)


def painel_ficha_pagina(confirmadas: set[int]):
    """Topo da pagina Fichas: gerar ou completar as fichas das confirmadas."""
    sem_ficha, incompletas, parciais = contagens_fichas(confirmadas)
    if parciais and not (sem_ficha or incompletas) and not execucao.rodando_ficha():
        st.caption(f"{parciais} ficha(s) prontas para submeter. A busca no VizieR foi feita nos "
                   "principais catálogos de variáveis, não em todos, porque o VizieR de "
                   "Estrasburgo está fora. Quando ele voltar, gerar de novo faz a busca "
                   "completa (opcional).")
        if vizier_no_ar()[0]:
            incompletas = parciais
    if sem_ficha or incompletas or execucao.rodando_ficha() or execucao.rodando():
        with st.container(border=True):
            st.markdown("**Gerar fichas do VSX**")
            painel_ficha(sem_ficha, incompletas)
    else:
        painel_ficha(sem_ficha, incompletas)


def painel_busca(pendentes: int):
    """Busca de mais candidatas (barra lateral da Fila): progresso se roda, resultado da
    ultima e o botao."""
    if execucao.rodando():
        progresso()
        return
    if execucao.rodando_ficha():
        botao_buscar("buscar")  # mostra o botao desligado e o motivo
        return
    e = execucao.estado(execucao.ler_log())
    if e["fim_da_grade"]:
        st.info("A grade de regiões do céu acabou: todas foram varridas. Para continuar, "
                "acrescente faixas em `FAIXAS_B_DEG` (src/campos.py).")
        return
    if e["erro"]:
        st.error(f"A última busca parou ({e['erro']}). Tentar de novo refaz a mesma região.")
    elif e["cancelada"]:
        st.info("Busca cancelada. A região interrompida é refeita do início na próxima busca.")
        st.button("Ok", on_click=esquecer_busca)
    elif e["terminou"]:
        st.success(f"Busca terminou{' no campo ' + e['campo'] if e['campo'] else ''}. "
                   "As candidatas novas já estão na fila.")
        st.button("Ok", on_click=esquecer_busca)
    if pendentes:
        st.caption(f"Ainda há {pendentes} pendente(s): o ideal é revisar antes.")
    botao_buscar("buscar")

