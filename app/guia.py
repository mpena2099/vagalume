"""O que procurar em cada painel: roteiro, exemplos bom x ruim e a pista de cada caso.

Sem Streamlit nas funcoes de texto (testaveis offline); `mostrar_guia` desenha o guia.
"""

import json
from pathlib import Path

import pandas as pd

from config import DESLOCAMENTO_MAX_PX

# Como ler a curva dobrada, mostrado no topo do guia
LEITURA = ("**Como ler as curvas dobradas.** Cada ponto laranja é uma medida de brilho do TESS "
           "(uma a cada 200 s, por umas 4 semanas). Dobrar é colocar cada medida na posição do "
           "ciclo em que ela caiu (fase, de 0 a 1), empilhando todos os ciclos. A linha preta é a "
           "mediana dos pontos em 50 fatias: a forma média da variação. Eixo vertical: brilho "
           "relativo (1,00 é o normal da estrela, 0,95 é 5% mais fraca). Eixo horizontal: fase, "
           "com 0 no momento mais fraco. Período certo: os ciclos se encaixam e os pontos colam "
           "na linha. Período errado ou ruído: faixa espalhada e linha tremida.")

# painel -> (titulo, pergunta que o revisor responde olhando a imagem)
ROTEIRO = {
    "p": ("1. Curva dobrada em P",
          "Os pontos formam uma linha fina com desenho que se repete (um vale, uma onda), "
          "ou uma faixa larga e sem forma? Olhe também a escala do eixo vertical: de 0,994 "
          "a 1,006 é uma variação de 0,6%, perto do ruído."),
    "2p": ("2. Curva dobrada em 2P",
           "Aparecem dois vales? Se têm profundidades diferentes, é binária e o período "
           "real é 2P. Se são iguais, pode ser P (pulsante) ou 2P (binária de contato)."),
    "mapa": ("3. Mapa do sinal por pixel",
             "O x vermelho (onde o sinal é mais forte) está em cima do + verde (a estrela "
             "alvo)? Se está sobre outro círculo azul, o sinal vem da vizinha."),
}

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
        "mapa": (topo(bons, "deslocamento_px", False), topo(ruins, "deslocamento_px", True)),
    }


def pista(r: dict, resposta: str, explicacao: str) -> str:
    """Em qual painel estava a resposta deste caso, com os numeros dele."""
    d, forca = r.get("deslocamento_px"), r.get("forca")
    if d is not None and d > DESLOCAMENTO_MAX_PX and resposta == "descartado":
        return (f"Olhe o mapa: o x vermelho está a {d:.1f} px do + verde. Só isso já indica "
                "que o sinal vem de outra estrela.")
    if "sistemático" in explicacao:
        return ("Olhe o período: ele cai sobre um período da própria nave (1 d, 13,7 d ou "
                "metades). A curva pode até ter forma, mas a origem não é a estrela.")
    if "ruído" in explicacao or (forca is not None and forca < 3):
        f = "" if forca is None else f" (amplitude {forca:.1f} vezes o ruído)"
        return (f"Olhe a curva dobrada em P: faixa larga sem desenho{f}. Repare também na "
                "escala vertical, muito estreita.")
    if "ciclos" in explicacao:
        return ("Olhe a curva no tempo (figura completa): só dois ou três eventos isolados. "
                "Sem repetição não há período confiável.")
    if "não se repete" in explicacao:
        return ("Este caso só se resolve com os outros setores: no setor mostrado a curva "
                "parece boa, mas o período não volta nos setores seguintes.")
    if resposta == "confirmado":
        return ("Repare na curva em P: linha fina e com forma, x vermelho sobre o + verde. "
                "É o aspecto de uma variável real; compare com a próxima candidata.")
    return "Compare cada painel com o roteiro acima."


def mostrar_guia(st, treino: pd.DataFrame | None, aberto: bool, excluir: str | None = None) -> None:
    """Expander com o roteiro e, se houver treino, os exemplos bom x ruim de cada painel."""
    with st.expander("O que procurar em cada painel (com exemplos)", expanded=aberto):
        st.markdown(LEITURA)
        figs = exemplos(treino, excluir) if treino is not None and not treino.empty else {}
        for painel, (titulo, pergunta) in ROTEIRO.items():
            st.markdown(f"**{titulo}.** {pergunta}")
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
