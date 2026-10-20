import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlite3

import numpy as np
import pandas as pd

from app import dados
from src.baixar_curvas import resumir_curva
from src.checar_contaminacao import amp_necessaria, veredito
from src.cruzar_conhecidos import classificar
from src.detectar_sinal import avaliar_sinal
from src.triagem import amplitude_dobrada, profundidade_eclipse
from src.periodo import comparar_periodo, medir_periodo_bls, medir_periodo_ls
from src.selecionar_alvos import filtrar_alvos

RNG = np.random.default_rng(42)
TEMPO = np.arange(0, 27, 30 / 1440)


def test_ls_senoide():
    fluxo = 1 + 0.01 * np.sin(2 * np.pi * TEMPO / 2.3) + RNG.normal(0, 0.001, TEMPO.size)
    medido = medir_periodo_ls(TEMPO, fluxo)["periodo_d"]
    assert abs(medido / 2.3 - 1) < 0.001, medido


def test_bls_caixa():
    fase = (TEMPO % 1.7) / 1.7
    fluxo = 1 - 0.01 * (fase < 0.1 / 1.7) + RNG.normal(0, 0.001, TEMPO.size)
    medido = medir_periodo_bls(TEMPO, fluxo)["periodo_d"]
    ok, razao = comparar_periodo(medido, 1.7, 0.001)
    assert ok, (medido, razao)


def test_comparar_periodo():
    assert comparar_periodo(1.0, 1.0, 0.001) == (True, 1.0)
    assert comparar_periodo(2.0, 1.0, 0.001) == (True, 2.0)
    assert comparar_periodo(0.5, 1.0, 0.001) == (True, 0.5)
    assert comparar_periodo(1.5, 1.0, 0.001) == (False, None)
    assert comparar_periodo(1.01, 1.0, 0.001) == (False, None)


def test_ficha_vsx():
    from src.ficha_vsx import (amplitude_dobrada_mag, eh_catalogo_variavel, epoca_minimo, sugerir,
                               v_de_gaia)
    assert abs(v_de_gaia(10.0, 0.0) - 10.02704) < 1e-6
    rng = np.random.default_rng(1)
    ruido = rng.normal(0, 0.0005, TEMPO.size)
    # binaria destacada, P = 4 d, eclipses de 20% e 8%: o LS acha 2 d
    fase = (TEMPO % 4.0) / 4.0
    ea = 1 - 0.2 * (np.abs(fase - 0.1) < 0.01) - 0.08 * (np.abs(fase - 0.6) < 0.01) + ruido
    p, tipo, _ = sugerir("ls", 2.0, TEMPO, ea)
    assert tipo == "EA" and abs(p - 4.0) < 1e-9, (p, tipo)
    assert abs(amplitude_dobrada_mag(TEMPO, ea, 4.0) - 2.5 * np.log10(1 / 0.8)) < 0.03
    assert abs((epoca_minimo(TEMPO, ea, 4.0) - 0.4) / 4.0 % 1) < 0.02 or \
        abs((epoca_minimo(TEMPO, ea, 4.0) - 0.4) / 4.0 % 1 - 1) < 0.02
    # senoide: fica no periodo do LS e o tipo fica em aberto
    sen = 1 + 0.01 * np.sin(2 * np.pi * TEMPO / 1.3) + ruido
    assert sugerir("ls", 1.3, TEMPO, sen)[:2] == (1.3, "ROT, EW ou pulsante")
    # contato com minimos desiguais: varia o tempo todo, P real = 2x o do LS
    eb = 1 - 0.03 * np.cos(4 * np.pi * TEMPO / 3.0) ** 2 - 0.01 * np.cos(2 * np.pi * TEMPO / 3.0) + ruido
    p, tipo, _ = sugerir("ls", 1.5, TEMPO, eb)
    assert tipo == "EB" and abs(p - 3.0) < 1e-9, (p, tipo)
    assert eh_catalogo_variavel("The catalog of new slowly pulsating B-type (SPB) stars")
    assert not eh_catalogo_variavel("Variability Upper Limits for Non-Variable Sources")


def test_teste_llm_visao():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    from teste_llm_visao import classe_vsx, ler_resposta
    assert classe_vsx("EA/DM") == "EA" and classe_vsx("BY") == "ROT" and classe_vsx("RRAB") == "RR"
    assert classe_vsx("EW:") is None and classe_vsx("DSCT|GDOR") is None and classe_vsx("SR") is None
    assert ler_resposta("TIPO: EW\nPAINEL: B\nMOTIVO: minimos iguais") == ("EW", "B", "minimos iguais")
    assert ler_resposta("**TIPO:** EA\n**PAINEL:** A") [:2] == ("EA", "A")
    assert ler_resposta("nada") == (None, None, "")


def test_url_qlp():
    from src.curvas import url_qlp
    assert url_qlp(16625529, 41) == (
        "https://archive.stsci.edu/hlsps/qlp/s0041/0000/0000/1662/5529/"
        "hlsp_qlp_tess_ffi_s0041-0000000016625529_tess_v01_llc.fits")



def test_filtrar_alvos():
    tic = pd.DataFrame({
        "ID": [1, 2, 3, 4, 5],
        "ra": [0.0] * 5, "dec": [0.0] * 5,
        "Tmag": [10.0, 8.0, 12.0, 11.0, 13.0],
        "contratio": [0.1, 0.1, 0.5, np.nan, 0.05],
    })
    obs = pd.DataFrame({
        "target_name": ["1", "1", "2", "5", "5", "TESS FFI"],
        "provenance_name": ["TESS-SPOC", "QLP", "QLP", "QLP", "QLP", "TESS-SPOC"],
        "sequence_number": [55, 55, 55, 54, 55, 55],
    })
    df = filtrar_alvos(tic, obs, 55)
    assert df["tic"].tolist() == [1, 5], df
    assert df["autor"].tolist() == ["QLP", "QLP"]



def test_resumir_curva():
    fluxo = 1 + RNG.normal(0, 0.002, TEMPO.size)
    fluxo[5] = np.nan
    r = resumir_curva(TEMPO, fluxo)
    assert r["n_pontos"] == TEMPO.size - 1
    assert abs(r["cadencia_min"] - 30) < 1e-6
    assert abs(r["ruido_ptp"] / 0.002 - 1) < 0.1, r



def test_avaliar_sinal():
    assert avaliar_sinal("ls", 2.3, 0.01, 1e-10, 27, 0.002) is None
    assert avaliar_sinal("ls", 2.3, 0.01, 1e-2, 27, 0.002) == "fap"
    assert avaliar_sinal("bls", 2.3, 0.01, 5, 27, 0.002) == "snr"
    assert avaliar_sinal("ls", 20, 0.01, 1e-10, 27, 0.002) == "ciclos"
    assert avaliar_sinal("bls", 11.2, 0.01, 20, 27, 0.002) == "ciclos"
    assert avaliar_sinal("ls", 1.01, 0.01, 1e-10, 27, 0.002) == "sistematico"
    assert avaliar_sinal("bls", 2.3, 0.004, 20, 27, 0.002) == "amplitude"



def test_classificar():
    def m(cat, dist, periodo=None, gaia=False):
        return {"catalogo": cat, "nome": cat, "dist_arcsec": dist, "periodo": periodo,
                "gaia": gaia, "classe": "ECL" if gaia else None}

    assert classificar([], 1.0)["status"] == "novo"
    r = classificar([m("SIMBAD", 2), m("VSX", 3, 2.0)], 1.0)
    assert (r["status"], r["match_catalogo"], r["razao_periodo"]) == ("conhecido", "VSX", 0.5)
    r = classificar([m("VSX", 20, 1.0), m("Gaia-EB", 1, gaia=True)], 1.0)
    assert (r["status"], r["gaia_candidata"], r["gaia_classe"]) == ("conhecido_vizinho", True, "ECL")
    r = classificar([m("Gaia-EB", 1, 1.0, gaia=True)], 1.0)
    assert (r["status"], r["gaia_candidata"]) == ("novo", True)



def test_amp_necessaria():
    assert abs(amp_necessaria(0.01, 0) - 0.02) < 1e-12
    assert abs(amp_necessaria(0.01, 2.5) - 0.11) < 1e-12


def test_veredito():
    assert veredito(True, True) == ("descartado", "vizinha_variavel")
    assert veredito(False, False) == ("descartado", "nao_persiste")
    assert veredito(False, None) == ("candidato", None)
    assert veredito(False, True) == ("candidato", None)



def test_revisao_humana():
    conn = sqlite3.connect(":memory:")
    pd.DataFrame({"tic": [1, 2], "periodo_d": [1.0, 2.0]}).to_sql("candidatos_fase7", conn)
    dados.salvar_revisao(conn, 1, "confirmado", "eclipse claro")
    df = dados.carregar_candidatos(conn).set_index("tic")
    assert df.loc[1, "decisao"] == "confirmado" and df.loc[2, "decisao"] == "pendente"
    dados.apagar_revisao(conn, 1)
    assert dados.carregar_candidatos(conn)["decisao"].tolist() == ["pendente", "pendente"]
    try:
        dados.salvar_revisao(conn, 1, "talvez")
        assert False
    except ValueError:
        pass


def test_alertas():
    r = {"deslocamento_px": 2.0, "suspeito_blend": True, "amp_necessaria_min": 0.2,
         "n_ciclos": 2.5, "persistente": None, "gaia_candidata": False}
    assert len(dados.alertas(r)) == 4
    assert dados.alertas({"deslocamento_px": 0.2, "n_ciclos": 20, "persistente": True}) == []
    # NaN vindo do SQLite nao pode virar alerta
    assert dados.alertas({"deslocamento_px": 0.2, "n_ciclos": 20, "persistente": True,
                          "suspeito_blend": float("nan"), "gaia_candidata": float("nan")}) == []


def test_checklist_sugestao():
    def caso(**mudancas):
        r = {"deslocamento_px": 0.3, "persistente": True, "setores_extra": "41,75",
             "periodos_extra": "2.20,2.19", "n_ciclos": 12.0, "forca": 8.0,
             "suspeito_blend": False, "gaia_candidata": False, "amp_necessaria_min": 0.2}
        r.update(mudancas)
        return r

    itens = dados.checklist(caso())
    assert [i["estado"] for i in itens] == ["ok"] * 6
    assert dados.sugestao(itens) == "confirmado"

    itens = dados.checklist(caso(deslocamento_px=2.5))
    assert itens[0]["estado"] == "problema" and dados.sugestao(itens) == "descartado"

    itens = dados.checklist(caso(persistente=None))
    assert itens[1]["estado"] == "atencao" and dados.sugestao(itens) == "duvida"

    itens = dados.checklist(caso(persistente=0))
    assert itens[1]["estado"] == "problema" and dados.sugestao(itens) == "descartado"

    itens = dados.checklist(caso(deslocamento_px=float("nan")))
    assert itens[0]["estado"] == "atencao" and dados.sugestao(itens) == "duvida"

    itens = dados.checklist(caso(n_ciclos=3.5))
    assert itens[2]["estado"] == "atencao" and dados.sugestao(itens) == "duvida"


def test_escolher_sinal():
    from src.triagem import escolher_sinal
    s = pd.DataFrame([
        {"tic": 1, "metodo": "bls", "periodo_d": 11.2, "amplitude": 0.05, "ruido_ptp": 0.001,
         "veredito": "descartado", "motivo_descarte": "nao_persiste"},
        {"tic": 1, "metodo": "ls", "periodo_d": 1.35, "amplitude": 0.01, "ruido_ptp": 0.001,
         "veredito": "candidato", "motivo_descarte": None},
        {"tic": 2, "metodo": "ls", "periodo_d": 2.0, "amplitude": 0.01, "ruido_ptp": 0.001,
         "veredito": "descartado", "motivo_descarte": "nao_persiste"},
    ])
    e = escolher_sinal(s)
    assert e["tic"].tolist() == [1] and e.loc[0, "metodo"] == "ls"
    assert "BLS 11.2000 d" in e.loc[0, "sinais_todos"]



def test_mapas_triagem():
    fluxo = np.column_stack([np.sin(2 * np.pi * TEMPO / 2.0), np.zeros(TEMPO.size)])
    amp = amplitude_dobrada(TEMPO, fluxo, 2.0)
    assert abs(amp[0] - 2) < 0.05 and amp[1] == 0
    fase = ((TEMPO - 0.5) / 3.0 + 0.5) % 1 - 0.5
    caixa = np.column_stack([-0.1 * (np.abs(fase * 3.0) < 0.05), np.zeros(TEMPO.size)])
    prof = profundidade_eclipse(TEMPO, caixa, 3.0, 0.5, 0.1)
    assert abs(prof[0] - 0.1) < 1e-9 and prof[1] == 0


def test_pista_treino():
    from app.guia import pista
    assert "mapa" in pista({"deslocamento_px": 5.0}, "descartado", "o sinal vem da vizinha")
    ruido = pista({"deslocamento_px": 5.0, "forca": 1.5}, "descartado", "mal passa do ruído")
    assert "qualquer pixel" in ruido and "outra estrela" not in ruido
    assert "nave" in pista({"deslocamento_px": 0.2}, "descartado", "período da própria nave")
    assert "faixa larga" in pista({"forca": 1.5}, "descartado", "mal passa do ruído")
    assert "linha fina" in pista({"deslocamento_px": 0.3, "forca": 20}, "confirmado", "VSX")


if __name__ == "__main__":
    for nome, fn in list(globals().items()):
        if nome.startswith("test_"):
            fn()
            print(f"OK {nome}")
