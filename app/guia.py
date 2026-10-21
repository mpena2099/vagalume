"""O que procurar em cada painel: roteiro, exemplos bom x ruim e a pista de cada caso.

Sem Streamlit nas funcoes de texto (testaveis offline); `mostrar_guia` desenha o guia.
"""

import json
from pathlib import Path

import pandas as pd

from config import DESLOCAMENTO_MAX_PX, IMG_DIR

# Como ler a curva dobrada, mostrado no topo do guia
LEITURA = ("**Como ler as curvas dobradas.** Cada ponto laranja é uma medida de brilho do TESS "
           "(uma a cada 200 s, por umas 4 semanas). Dobrar é colocar cada medida na posição do "
           "ciclo em que ela caiu (fase, de 0 a 1), empilhando todos os ciclos. A linha preta é a "
           "mediana dos pontos em 50 fatias: a forma média da variação. Eixo vertical: brilho "
           "relativo (1,00 é o normal da estrela, 0,95 é 5% mais fraca). Eixo horizontal: fase, "
           "com 0 no momento mais fraco. Período certo: os ciclos se encaixam e os pontos colam "
           "na linha. Período errado ou ruído: faixa espalhada e linha tremida.\n\n"
           "**O que decide.** Confirmar ou Descartar depende só dos painéis 1 (a curva em P "
           "tem forma clara que se repete?) e 2 (o sinal sai da estrela alvo?). A curva em 2P "
           "fica para depois de confirmar: serve só para escolher o período da ficha do VSX.")

# painel -> (titulo, pergunta que o revisor responde olhando a imagem)
ROTEIRO = {
    "p": ("1. Curva dobrada em P",
          "Os pontos formam uma linha fina com desenho que se repete (um vale, uma onda), "
          "ou uma faixa larga e sem forma? Olhe também a escala do eixo vertical: de 0,994 "
          "a 1,006 é uma variação de 0,6%, perto do ruído."),
    "mapa": ("2. Mapa do sinal por pixel",
             "O x vermelho (onde o sinal é mais forte) está em cima do + verde (a estrela "
             "alvo)? Se está sobre outro círculo azul, o sinal vem da vizinha."),
}

# depois de confirmar: a curva em 2P so escolhe o periodo (P ou 2P) da ficha do VSX
PERIODO = ("Depois de confirmar: o período (P ou 2P)",
           "Dobrar em P é cortar a curva em pedaços de P dias e empilhar os pedaços. Dobrar em "
           "2P é cortar em pedaços duas vezes maiores: cada pedaço leva dois ciclos de P lado a "
           "lado.\n\n"
           "Por que olhar: numa binária a estrela escurece duas vezes por volta, num eclipse "
           "fundo e num raso. O programa costuma ver \"um escurecimento a cada meia volta\" e "
           "acha metade do período verdadeiro. Na figura abaixo (curvas simuladas), os ciclos de "
           "P se alternam em laranja e azul:\n"
           "- **Binária.** Em P, o eclipse fundo (laranja) e o raso (azul) caem no mesmo lugar, "
           "um por cima do outro. Em 2P cada um vai para o seu lugar: dois vales diferentes. "
           "O período certo é 2P.\n"
           "- **Pulsante.** Laranja e azul fazem o mesmo desenho. Em 2P aparece só a mesma onda "
           "duas vezes, nada novo. O período certo é P.\n\n"
           "Dois casos especiais. Se em 2P sobra um vale só e o resto plano (e, em P, pontos "
           "atravessam o vale em 1,00), o segundo eclipse é raso demais para aparecer: binária, "
           "período 2P. Se em 2P aparecem dois vales iguais com variação acima de ~10% e 2P "
           "acima de ~0,22 d, pode ser binária de contato, também 2P.\n\n"
           "A curva em 2P não decide se a variação é real: serve só para anotar o período na "
           "ficha do VSX (a Fase 8 sugere sozinha, aqui você confere).")
FIGURA_PERIODO = IMG_DIR / "p_vs_2p.png"  # tools/gerar_figura_periodo.py


def mostrar_figura_periodo(st) -> None:
    if FIGURA_PERIODO.exists():
        st.image(str(FIGURA_PERIODO), width="stretch",
                 caption="Curvas simuladas. Ciclos de P alternados em laranja e azul.")

# painel -> (o que ver no exemplo bom, o que ver no exemplo ruim)
CONTRASTE = {
    "p": ("Linha preta com forma clara e pontos colados nela: os ciclos caem uns sobre os "
          "outros.",
          "Nuvem de pontos da mesma largura em todas as fases e linha preta tremida sem "
          "desenho: é ruído que o ajuste organizou."),
    "2p": ("Dois vales separados por meia fase: com a dobra em 2P, cada eclipse cai no seu "
           "lugar.",
           "Mesma nuvem sem forma em P e em 2P: dobrar de novo não cria sinal."),
    "mapa": ("O x vermelho em cima do + verde: o sinal sai da estrela alvo.",
             "O x vermelho longe do + verde, sobre outra estrela: o sinal é da vizinha."),
}


def _dados(figura: str) -> dict:
    caminho = Path(figura).with_suffix(".json")
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}


def exemplos(treino: pd.DataFrame, excluir: str | None = None) -> dict[str, tuple[str | None, str | None]]:
    """Painel -> (figura do exemplo bom, figura do ruim), escolhidos no proprio treino.

    excluir: figura do caso na tela, que nao pode servir de exemplo (entregaria a resposta).
    """
    treino = treino[treino["figura"] != excluir]
    numeros = pd.DataFrame([_dados(f) for f in treino["figura"]], index=treino.index)
    t = pd.concat([treino, numeros.reindex(columns=["forca", "deslocamento_px"])], axis=1)
    bons, ruins = t[t["resposta"] == "confirmado"], t[t["resposta"] == "descartado"]

    def topo(df, coluna, maior):
        df = df.dropna(subset=[coluna])
        return None if df.empty else df.sort_values(coluna, ascending=not maior).iloc[0]["figura"]

    ruido = ruins[ruins["explicacao"].str.contains("ruído", na=False)]
    # catalogo com o dobro do periodo medido: o periodo real e 2P
    dobro = bons[bons["explicacao"].str.contains(r"razão 2\.0", na=False)]
    return {
        "p": (topo(bons, "forca", True), topo(ruido if not ruido.empty else ruins, "forca", False)),
        "2p": (topo(dobro if not dobro.empty else bons, "forca", True),
               topo(ruido if not ruido.empty else ruins, "forca", False)),
        # ruim do mapa: so descarte por vizinha (em ruido o pico longe nao e outra estrela)
        "mapa": (topo(bons, "deslocamento_px", False),
                 topo(ruins[ruins["explicacao"].str.contains("vizinha", na=False)],
                      "deslocamento_px", True)),
    }


def pista(r: dict, resposta: str, explicacao: str) -> str:
    """Em qual painel estava a resposta deste caso, com os numeros dele."""
    d, forca = r.get("deslocamento_px"), r.get("forca")
    # sem sinal real o pico do mapa cai num pixel qualquer: o mapa so e a pista quando o
    # motivo do descarte e a vizinha (ou quando nao ha outro motivo)
    longe = d is not None and d > DESLOCAMENTO_MAX_PX
    if "própria nave" in explicacao:
        return ("Olhe o período: ele cai sobre um período da própria nave (1 d, 13,7 d ou "
                "metades). A curva pode até ter forma, mas não dá para provar que vem da estrela.")
    if "ruído" in explicacao:
        f = "" if forca is None else f" (amplitude {forca:.1f} vezes o ruído)"
        extra = (" O mapa também não aponta o alvo: sem sinal, o pico cai em qualquer pixel."
                 if longe else "")
        return (f"Olhe a curva dobrada em P: faixa larga sem desenho{f}. Repare também na "
                f"escala vertical, muito estreita.{extra}")
    if "ciclos" in explicacao:
        return ("Olhe a curva no tempo (figura completa): só dois ou três eventos isolados. "
                "Sem repetição não há período confiável para submeter.")
    if "não se repete" in explicacao:
        extra = (f" O mapa ajuda: o x vermelho está a {d:.1f} px do + verde." if longe else "")
        return ("O motivo está nos outros setores: o período não volta neles, então o sinal "
                f"não é estável.{extra}")
    if "vizinha" in explicacao:
        txt = (f"Olhe o mapa: o x vermelho está a {d:.1f} px do + verde, fora do alvo."
               if longe else "Olhe os círculos azuis no mapa: há uma vizinha perto do alvo.")
        return txt + " Uma variável catalogada ali tem o mesmo período."
    if longe and resposta == "descartado":
        return f"Olhe o mapa: o x vermelho está a {d:.1f} px do + verde, fora do alvo."
    if resposta == "confirmado" and "razão 0.50" in explicacao:
        return ("O catálogo dá o dobro do período medido: o real é 2P. Olhe o painel 2P: "
                "dois vales (iguais numa binária de contato, diferentes numa binária "
                "destacada) ou, se o segundo eclipse é raso demais, um vale só e o resto plano.")
    if resposta == "confirmado":
        return ("Repare na curva em P: linha fina e com forma, x vermelho sobre o + verde. "
                "É o aspecto de uma variável real; compare com a próxima candidata.")
    return "Compare cada painel com o roteiro acima."


def periodo_certo(explicacao: str, r: dict | None = None) -> str | None:
    """'P' ou '2P' pelo periodo do catalogo; None se o catalogo nao tem periodo comparavel.

    razao = periodo medido / periodo do catalogo: 0,50 quer dizer que o real e o dobro.
    So periodo do VSX: rotacao (manchas mudam de forma, 2P nao fica identico) e catalogos
    que discordam entre si ensinariam a regra errada. Os casos do VSX foram conferidos
    um a um nos paineis.
    """
    if not explicacao.startswith("VSX"):
        return None
    # resposta P com variacao grande: em 2P dois vales iguais e profundos, que so com o TESS
    # nao se distinguem de binaria de estrelas gemeas (periodo 2P); o VSX decidiu com outros dados
    if "razão 1.00" in explicacao and r and (r.get("amplitude") or 0) >= 0.10:
        return None
    if "razão 0.50" in explicacao:
        return "2P"
    if "razão 1.00" in explicacao:
        return "P"
    return None


def explicar_periodo(certo: str, r: dict) -> str:
    """Por que P ou 2P, com os numeros: dois vales iguais em 2P aparecem tanto em pulsante
    (resposta P) quanto em binaria de contato (resposta 2P), e so amplitude e periodo separam."""
    per, amp = r.get("periodo_d"), r.get("amplitude")
    if certo == "2P":
        # sem amplitude aqui: em eclipse estreito a do Lomb-Scargle fica bem abaixo da
        # profundidade real (3,5% para um eclipse de 20%) e confundiria com a regra da EW
        num = "" if per is None else f" Aqui 2P = {2 * per:.3f} d."
        return ("O catálogo dá o dobro do período medido: o real é 2P. No painel 2P aparecem "
                "dois vales (diferentes numa binária destacada; iguais numa binária de contato, "
                "que varia mais de ~10% e tem 2P acima de ~0,22 d) ou um vale só e o resto "
                f"plano, quando o segundo eclipse é raso demais.{num}")
    num = ("" if per is None or amp is None
           else f" Aqui a variação é de {amp * 100:.1f}% e 2P = {2 * per:.3f} d.")
    return ("O catálogo dá o mesmo período medido: o real é P. Em 2P a mesma forma aparece "
            "duas vezes, sem nada novo. Se forem dois vales iguais, não é binária de contato "
            "quando a variação é pequena (abaixo de ~10%) ou 2P fica abaixo de ~0,22 d: aí é "
            f"pulsante.{num}")


def mostrar_guia(st, treino: pd.DataFrame | None, aberto: bool, excluir: str | None = None) -> None:
    """Expander com o roteiro e, se houver treino, os exemplos bom x ruim de cada painel."""
    with st.expander("O que procurar em cada painel (com exemplos)", expanded=aberto):
        st.markdown(LEITURA)
        figs = exemplos(treino, excluir) if treino is not None and not treino.empty else {}
        secoes = [(painel, titulo, pergunta) for painel, (titulo, pergunta) in ROTEIRO.items()]
        for painel, titulo, pergunta in secoes + [("2p", *PERIODO)]:
            if painel == "2p":
                st.divider()
            st.markdown(f"**{titulo}.** {pergunta}")
            if painel == "2p":
                mostrar_figura_periodo(st)
            bom, ruim = figs.get(painel, (None, None))
            if not (bom or ruim):
                continue
            cols = st.columns(3)  # a terceira fica vazia: exemplos menores
            for col, fig, rotulo, texto in ((cols[0], bom, "✅ Bom", CONTRASTE[painel][0]),
                                            (cols[1], ruim, "❌ Ruim", CONTRASTE[painel][1])):
                arquivo = Path(fig).with_name(f"{Path(fig).stem}_{painel}.png") if fig else None
                if arquivo is not None and arquivo.exists():
                    col.image(str(arquivo), width="stretch")
                    col.caption(f"**{rotulo}.** {texto}")
