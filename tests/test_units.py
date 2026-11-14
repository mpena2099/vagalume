import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlite3

import numpy as np
import pandas as pd

from app import dados
from src.baixar_curvas import resumir_curva
from src.checar_contaminacao import amp_necessaria, veredito
from src.cruzar_conhecidos import classificar
from src.detectar_sinal import avaliar_sinal, resgatar_sistematicos
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


def test_ficha_vsx_retoma():
    from src.ficha_vsx import plano as _plano
    antigo = "Busca no VizieR inteiro não feita (servidor sem resposta): confira à mão em vizier.cds.unistra.fr ou num espelho antes de submeter."
    assert _plano({"avisos": antigo}) == "completar:vizier"
    assert _plano({"avisos": "outro aviso qualquer"}) == "nova"
    import tempfile
    import types
    from pathlib import Path
    from unittest import mock
    import pandas as pd
    from src import ficha_vsx as fv
    assert fv.plano(None) == "nova"
    assert fv.plano({"avisos": ""}) == "manter"
    assert fv.plano({"avisos": ""}, refazer=True) == "nova"
    assert fv.plano({"avisos": fv.AVISO_VIZIER}) == "completar:vizier"
    assert fv.plano({"avisos": fv.AVISO_GAIA + " | " + fv.AVISO_VIZIER}) == "completar:gaia,vizier"
    assert fv.plano({"avisos": "aviso desconhecido"}) == "nova"

    # o CSV volta igual, inclusive o ID Gaia de 19 digitos e as colunas vazias
    tmp_path = Path(tempfile.mkdtemp())
    mock.patch.object(fv, "VSX_DIR", tmp_path).start()
    ficha = {"tic": 7, "decisao": "confirmado", "periodo_d": 1.23456, "periodo_erro_d": float("nan"),
             "alerta_periodo": "", "fase_secundario": 0.5, "tipo_sugerido": "EA",
             "motivo_tipo": "m", "epoca_bjd": 2460000.1, "amplitude_mag_tess": 0.3,
             "setores": "55", "setores_usados": "55", "suspeito_blend": False,
             "figura_fase": "f.png", "figura_triagem": "t.png",
             "vizier_variaveis": "busca não feita", "avisos": fv.AVISO_VIZIER}
    outra = dict(ficha, tic=8, gaia_dr3=4_000_000_000_000_000_001, gaia_ra=1.0, gaia_dec=2.0,
                 gaia_g=12.0, v_estimada=12.5, gaia_sep_arcsec=0.4, avisos="")
    fv._gravar([ficha, outra])
    lidas = fv.ler_fichas(tmp_path / "fichas.csv")
    assert lidas[8]["gaia_dr3"] == 4_000_000_000_000_000_001
    assert "gaia_dr3" not in lidas[7] and "periodo_erro_d" not in lidas[7]
    assert lidas[7]["suspeito_blend"] is False and lidas[7]["setores"] == "55"
    assert fv.plano(lidas[7]) == "completar:vizier" and fv.plano(lidas[8]) == "manter"

    # completar so o VizieR preserva periodo, tipo, epoca e a fonte Gaia
    s = types.SimpleNamespace(ra=1.0, dec=2.0)
    def proibido(*a, **k):
        raise AssertionError("busca fora do plano")
    mock.patch.object(fv, "_vizier", lambda alvo: ['J/X/1 (Eclipsing binaries) a 2.0"']).start()
    mock.patch.object(fv, "_gaia", proibido).start()
    mock.patch.object(fv, "_medir", proibido).start()
    f = fv.completar_buscas(dict(lidas[7]), s, ["vizier"])
    assert f["avisos"] == "" and f["vizier_variaveis"].startswith("J/X/1")
    assert f["periodo_d"] == 1.23456 and f["tipo_sugerido"] == "EA" and f["epoca_bjd"] == 2460000.1
    assert "Aviso" not in fv._markdown(f)
    # servidor ainda fora: o aviso continua
    mock.patch.object(fv, "_vizier", proibido).start()  # AssertionError conta como falha da busca
    f = fv.completar_buscas(dict(lidas[7]), s, ["vizier"])
    assert f["avisos"] == fv.AVISO_VIZIER and f["periodo_d"] == 1.23456
    # so o Gaia: o aviso do VizieR fica
    mock.patch.object(fv, "_gaia", lambda alvo: {"gaia_dr3": 5, "v_estimada": 11.0}).start()
    dupla = dict(lidas[7], avisos=fv.AVISO_GAIA + " | " + fv.AVISO_VIZIER)
    f = fv.completar_buscas(dupla, s, ["gaia"])
    assert f["avisos"] == fv.AVISO_VIZIER and f["gaia_dr3"] == 5
    mock.patch.stopall()


def test_periodo_setores():
    from src.periodo_setores import medir_periodo_setores
    rng = np.random.default_rng(3)
    p_real, fase_sec = 21.3, 0.74
    curvas = []
    # setores separados por 18P e 43P: os ciclos nao tem divisor comum, entao nao surge
    # alias de ciclo inteiro dentro da faixa varrida (0,3 a 3 do periodo de um setor)
    for inicio in (0.0, 18 * p_real, 43 * p_real):
        t = np.arange(inicio, inicio + 27, 30 / 1440)
        fase = ((t - 8.0) / p_real) % 1
        fluxo = 1 - 0.23 * np.exp(-0.5 * (np.minimum(fase, 1 - fase) / 0.012) ** 2)
        fluxo -= 0.09 * np.exp(-0.5 * (((fase - fase_sec + 0.5) % 1 - 0.5) / 0.012) ** 2)
        curvas.append((t, fluxo + rng.normal(0, 0.0015, t.size)))

    r = medir_periodo_setores(curvas, 10.5, eclipse=True)
    assert abs(r["periodo_d"] / p_real - 1) < 1e-4, r
    assert 0 < r["periodo_erro_d"] < 1e-3, r
    assert r["alerta_periodo"] == ""
    assert abs(r["fase_secundario"] - fase_sec) < 0.02, r
    # fundos num so setor: nao ha como separar os harmonicos, mantem o periodo de entrada
    r1 = medir_periodo_setores(curvas[:1], 10.5, eclipse=True)
    assert r1["periodo_d"] == 10.5 and r1["alerta_periodo"] == "periodo medido em um so setor"


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
    # fraco e perto de 1 d: o motivo e o ruido, nao a nave
    assert avaliar_sinal("ls", 1.01, 0.004, 1e-10, 27, 0.002) == "amplitude"


def test_resgatar_sistematicos():
    def linha(tic, p, motivo):
        return {"tic": tic, "metodo": "ls", "periodo_d": p, "motivo": motivo,
                "sinal": motivo is None}
    sozinha = pd.DataFrame([linha(1, 0.98, "sistematico"), linha(2, 2.5, None),
                            linha(3, 0.98, "amplitude")])
    r = resgatar_sistematicos(sozinha)
    assert r.loc[0, "sinal"] and r.loc[0, "motivo"] is None and r.loc[0, "perto_sistematico"]
    campo = pd.DataFrame([linha(t, 1.0 + t / 1000, "sistematico") for t in range(1, 6)])
    r = resgatar_sistematicos(campo)
    assert not r["sinal"].any() and (r["motivo"] == "sistematico").all()



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


def test_periodo_certo():
    from app.guia import periodo_certo
    assert periodo_certo("VSX já lista X com período 5.3754 d, razão 0.50 com o período medido") == "2P"
    assert periodo_certo("VSX já lista X com período 0.1109 d, razão 1.00 com o período medido") == "P"
    assert periodo_certo("VSX já lista esta estrela como variável, sem período no catálogo") is None
    assert periodo_certo("VSX já lista X com período 5.3 d, razão 1.00 com o período medido",
                         {"amplitude": 0.19}) is None
    assert periodo_certo("TIC-rotacao já lista X com período 1.3482 d, razão 1.00 com o período medido") is None


def test_pista_treino():
    from app.guia import pista
    assert "mapa" in pista({"deslocamento_px": 5.0}, "descartado", "o sinal vem da vizinha")
    ruido = pista({"deslocamento_px": 5.0, "forca": 1.5}, "descartado", "mal passa do ruído")
    assert "qualquer pixel" in ruido and "outra estrela" not in ruido
    assert "faixa larga" in pista({"forca": 1.5}, "descartado", "mal passa do ruído")
    assert "2P" in pista({"deslocamento_px": 0.3}, "confirmado", "VSX já lista X com período 5 d, razão 0.50 com o período medido")
    assert "linha fina" in pista({"deslocamento_px": 0.3, "forca": 20}, "confirmado", "VSX")


def test_zerar_treino():
    from app.dados import ler_tentativas, salvar_tentativa, zerar_treino
    conn = sqlite3.connect(":memory:")
    salvar_tentativa(conn, "1_ls", "confirmado", "confirmado", 1.0)
    zerar_treino(conn)
    assert ler_tentativas(conn).empty


def test_resumo_treino():
    from app.dados import ler_tentativas, resumo_treino, salvar_tentativa
    conn = sqlite3.connect(":memory:")
    assert resumo_treino(ler_tentativas(conn)) == {}
    salvar_tentativa(conn, "1_ls", "confirmado", "confirmado", 1.0)
    salvar_tentativa(conn, "2_bls", "duvida", "descartado", 0.5)
    salvar_tentativa(conn, "1_ls", "P", "2P", 0.0, "periodo")
    r = resumo_treino(ler_tentativas(conn))
    # a pergunta de periodo fica fora do acerto geral
    assert r["respostas"] == 2 and abs(r["geral"] - 0.75) < 1e-9
    assert r["por_certa"] == {"confirmado": (1.0, 1), "descartado": (0.5, 1)}
    assert r["periodo"] == (0.0, 1)


def test_campos_proximo():
    from src import campos
    g = campos.grade()
    assert g[0] == (80.0, 0.0) and len(g) == 144 * len(campos.FAIXAS_B_DEG)
    assert {b for _, b in g[:144]} == {0.0}  # o plano inteiro antes de sair dele
    sempre = lambda c: [14, 55, 56]
    primeiro = campos.proximo([], sempre)
    assert primeiro["setor"] == 55 and primeiro["nome"] == "l080.0b+0_s55"
    # o campo inicial (Cygnus, l=80 b=0) ja feito: pula pra um ponto a 2,5 graus
    inicial = {"nome": "inicial_s55", "setor": 55, "ra": 308.9712, "dec": 40.6636}
    seg = campos.proximo([inicial], sempre)
    assert seg["nome"].startswith(("l082.5b+0", "l077.5b+0"))
    # so setor antigo (sem 200 s): o ponto e pulado
    assert campos.proximo([], lambda c: [14, 15])  is None
    conn = sqlite3.connect(":memory:")
    assert campos.ler_feitos(conn) == []
    campos.registrar(conn, seg, 480)
    assert campos.ler_feitos(conn)[0]["nome"] == seg["nome"]
    assert campos.proximo(campos.ler_feitos(conn) + [inicial], sempre)["nome"] != seg["nome"]


def test_estado_execucao():
    from app.execucao import estado
    vazio = estado("")
    assert vazio["fase"] is None and not vazio["terminou"] and vazio["erro"] is None
    log = """  Proximo campo: l082.5b+0_s55 (RA 1, Dec 2, setor 55)
  Executando: Fase 3 - Baixar curvas
  120/500 (0 erros)
  Executando: Fase 4 - Detectar sinal
"""
    e = estado(log)
    assert e["campo"].startswith("l082.5b+0_s55") and e["fase"] == "Fase 4 - Detectar sinal"
    assert e["progresso"] is None  # fase nova zera o progresso da anterior
    assert estado(log + "  50/500\n")["progresso"] == (50, 500)
    assert estado(log + "\nERRO em Fase 4 - Detectar sinal: timeout\n")["erro"].startswith("ERRO em")
    assert estado(log + "  Campo x registrado em campos_feitos.\n")["terminou"]
    assert estado("  A grade de campos acabou: todos\n")["fim_da_grade"]
    assert not e["cancelada"] and estado(log + "\nBusca cancelada pelo app.\n")["cancelada"]


def test_estado_ficha():
    from app.execucao import estado_ficha
    vazio = estado_ficha("")
    assert vazio["progresso"] is None and vazio["tic"] is None and vazio["etapa"] is None
    assert vazio["erro"] is None and vazio["fim"] is None and not vazio["terminou"]

    log = """Fase 8: fichas do VSX de 4 estrelas (confirmados). Leva alguns minutos por estrela.
[1/4] TIC 111: ficha já pronta, mantida

[2/4] TIC 222
  baixando 1 setor do TESS...
    setor 55 (1/1)
  medindo o período
"""
    e = estado_ficha(log)
    assert e["progresso"] == (2, 4) and e["tic"] == 222
    assert e["etapa"] == "medindo o período"

    com_erro = log + 'Traceback (most recent call last):\n  File "x", line 1\nValueError: boom\n'
    e = estado_ficha(com_erro)
    assert "ValueError: boom" in e["erro"]

    fim = ("4 fichas em data/vsx/fichas.csv (curvas em data/vsx/<tic>_fase.png): 2 mantidas, "
           "1 completada, 1 nova.")
    e = estado_ficha(log + fim + "\n")
    assert e["terminou"] and e["fim"] == fim
    assert not estado_ficha("Busca cancelada pelo app.")["cancelada"]
    assert estado_ficha("Fichas canceladas pelo app.")["cancelada"]


def test_vizier_no_ar():
    from unittest import mock
    import requests
    from app import execucao
    resp = lambda codigo, texto: mock.Mock(status_code=codigo, text=texto)
    with mock.patch("requests.get", return_value=resp(200, "<VOTABLE><TABLE>")):
        assert execucao.vizier_no_ar()
    # CDS fora: 404 nas consultas, ou 200 com pagina de aviso
    with mock.patch("requests.get", return_value=resp(404, "")):
        assert not execucao.vizier_no_ar()
    with mock.patch("requests.get", return_value=resp(200, "<html>aviso</html>")):
        assert not execucao.vizier_no_ar()
    with mock.patch("requests.get", side_effect=requests.ConnectionError):
        assert not execucao.vizier_no_ar()


def test_envios():
    conn = sqlite3.connect(":memory:")
    assert dados.ler_envios(conn).empty
    dados.marcar_envio(conn, 7, enviada=True, nome_vsx="V123")
    e = dados.ler_envios(conn).set_index("tic").loc[7]
    assert isinstance(e["enviada_em"], str) and pd.isna(e["aceita_em"])
    assert e["nome_vsx"] == "V123"
    enviada_em = e["enviada_em"]
    # aceita implica enviada, sem refazer a data do envio
    dados.marcar_envio(conn, 7, aceita=True)
    e = dados.ler_envios(conn).set_index("tic").loc[7]
    assert e["enviada_em"] == enviada_em and isinstance(e["aceita_em"], str)
    # desmarcar grava NULL
    dados.marcar_envio(conn, 7, enviada=False, aceita=False, nome_vsx="")
    e = dados.ler_envios(conn).set_index("tic").loc[7]
    assert pd.isna(e["enviada_em"]) and pd.isna(e["aceita_em"]) and pd.isna(e["nome_vsx"])
    # aceite numa estrela ainda sem envio ja grava as duas datas
    dados.marcar_envio(conn, 8, aceita=True)
    e = dados.ler_envios(conn).set_index("tic").loc[8]
    assert isinstance(e["enviada_em"], str) and isinstance(e["aceita_em"], str)
    # remarcar (a pagina manda enviada=True a cada mudanca) nao troca as datas
    antes = dados.ler_envios(conn).set_index("tic").loc[8].to_dict()
    dados.marcar_envio(conn, 8, enviada=True, aceita=True, nome_vsx="X")
    depois = dados.ler_envios(conn).set_index("tic").loc[8]
    assert depois["enviada_em"] == antes["enviada_em"] and depois["aceita_em"] == antes["aceita_em"]
    with tempfile.TemporaryDirectory() as d:
        csv = Path(d) / "fichas.csv"
        assert dados.fichas_com_aviso(csv) == set()
        pd.DataFrame({"tic": [1, 2], "avisos": ["Busca no VizieR...", ""]}).to_csv(csv, index=False)
        assert dados.fichas_com_aviso(csv) == {1}


def test_migrar_envios():
    import tempfile
    csv = Path(tempfile.mkdtemp()) / "fichas.csv"
    conn = sqlite3.connect(":memory:")
    pd.DataFrame({"tic": [1, 2, 3, 4], "periodo_d": [1.0, 2.0, 3.0, 4.0]}).to_sql(
        "candidatos_fase7", conn)
    for tic, decisao in [(1, "confirmado"), (2, "confirmado"), (3, "confirmado"),
                         (4, "descartado")]:
        dados.salvar_revisao(conn, tic, decisao)
    pd.DataFrame({"tic": [1, 2]}).to_csv(csv, index=False)
    dados.marcar(conn, "Enviada ao VSX", True)
    dados.marcar(conn, "Aceita no VSX", True)
    assert dados.migrar_envios(conn, csv) == 2
    e = dados.ler_envios(conn).set_index("tic")
    assert set(e.index) == {1, 2}  # a 3 nao tem ficha e a 4 nao foi confirmada
    assert isinstance(e.loc[1, "enviada_em"], str) and isinstance(e.loc[1, "aceita_em"], str)
    antes = e[["enviada_em", "aceita_em"]].copy()
    assert dados.migrar_envios(conn, csv) == 0  # nao duplica
    depois = dados.ler_envios(conn).set_index("tic")[["enviada_em", "aceita_em"]]
    assert depois.equals(antes)
    assert dados.ler_marcos_manuais(conn) == {"Enviada ao VSX", "Aceita no VSX"}


def test_com_prazo():
    import time
    from src.util import com_prazo
    assert com_prazo(lambda: 7, 1) == 7
    try:
        com_prazo(lambda: time.sleep(5), 0.2)
        assert False, "devia estourar o prazo"
    except TimeoutError:
        pass
    try:
        com_prazo(lambda: 1 / 0, 1)
        assert False
    except ZeroDivisionError:
        pass


def _historico(respostas):
    conn = sqlite3.connect(":memory:")
    for i, (certa, pontos) in enumerate(respostas):
        dados.salvar_tentativa(conn, str(i), "", certa, pontos)
    return dados.ler_tentativas(conn)


def test_nivel_treino():
    assert dados.nivel_treino(dados.ler_tentativas(sqlite3.connect(":memory:")))[0] == "Aprendiz"
    # menos de 20 respostas: Aprendiz mesmo acertando tudo
    nivel, falta = dados.nivel_treino(_historico([("confirmado", 1.0)] * 10))
    assert nivel == "Aprendiz" and "faltam 10" in falta
    # 60% nas ultimas 20: Revisor, e o que falta e o acerto recente
    nivel, falta = dados.nivel_treino(_historico(
        [("confirmado", 1.0)] * 12 + [("descartado", 0.0)] * 8))
    assert nivel == "Revisor" and "60%" in falta and "80%" in falta, (nivel, falta)
    # 80% no total, mas so 60% nos casos Descartado: vies de confirmar demais
    nivel, falta = dados.nivel_treino(_historico(
        [("confirmado", 1.0)] * 10 + [("descartado", 1.0)] * 6 + [("descartado", 0.0)] * 4))
    assert nivel == "Revisor" and "Descartado" in falta and "confirmar demais" in falta
    # 85% no total e pelo menos 70% em cada resposta certa
    nivel, falta = dados.nivel_treino(_historico(
        [("confirmado", 1.0)] * 10 + [("descartado", 1.0)] * 7 + [("descartado", 0.0)] * 3))
    assert nivel == "Revisor confiável" and falta == ""


def test_marcos():
    import tempfile
    csv = Path(tempfile.mkdtemp()) / "fichas.csv"
    conn = sqlite3.connect(":memory:")
    lista = dados.marcos(conn, csv)
    assert [m["nome"] for m in lista] == ["Treino em dia", "Fila revisada", "Ficha pronta",
                                          "Enviada ao VSX", "Aceita no VSX"]
    assert not any(m["feito"] for m in lista)
    assert lista[0]["detalhe"] == "faltam 20 respostas" and lista[1]["detalhe"] == "0 de 0"

    assert lista[3]["detalhe"] == "0 de 0" and lista[4]["detalhe"] == "0 de 0"

    pd.DataFrame({"tic": [1, 2, 3, 4], "periodo_d": [1.0, 2.0, 3.0, 4.0]}).to_sql(
        "candidatos_fase7", conn)
    for tic in (1, 2, 3, 4):
        dados.salvar_revisao(conn, tic, "confirmado")
    for i in range(20):
        dados.salvar_tentativa(conn, str(i), "confirmado", "confirmado", 1.0)
    pd.DataFrame({"tic": [1, 2, 3, 4]}).to_csv(csv, index=False)
    lista = dados.marcos(conn, csv)
    assert lista[0]["detalhe"] == "100% nas últimas 20" and lista[1]["detalhe"] == "4 de 4"
    assert lista[2]["detalhe"] == "4 confirmadas"
    assert lista[3]["detalhe"] == "0 de 4" and not lista[3]["feito"]

    dados.marcar_envio(conn, 1, enviada=True)
    dados.marcar_envio(conn, 2, enviada=True)
    dados.marcar_envio(conn, 1, aceita=True)
    lista = dados.marcos(conn, csv)
    assert lista[3]["detalhe"] == "2 de 4" and not lista[3]["feito"]
    assert lista[4]["detalhe"] == "1 de 4" and not lista[4]["feito"]

    for tic in (3, 4):
        dados.marcar_envio(conn, tic, enviada=True)
    for tic in (2, 3, 4):
        dados.marcar_envio(conn, tic, aceita=True)
    lista = dados.marcos(conn, csv)
    assert lista[3]["feito"] and lista[3]["detalhe"] == "4 de 4", lista
    assert lista[4]["feito"] and lista[4]["detalhe"] == "4 de 4", lista
    assert sum(m["feito"] for m in lista) == 5


def test_descrever_erro():
    import requests
    from src.util import descrever_erro
    assert descrever_erro(requests.exceptions.ReadTimeout()) == "tempo esgotado"
    assert descrever_erro(TimeoutError()) == "tempo esgotado"
    assert descrever_erro(requests.exceptions.ConnectionError()) == "sem conexão"
    r = requests.Response()
    r.status_code = 502
    assert descrever_erro(requests.exceptions.HTTPError(response=r)) == "erro no servidor (502)"
    assert descrever_erro(ValueError("x")) == "ValueError"


if __name__ == "__main__":
    for nome, fn in list(globals().items()):
        if nome.startswith("test_"):
            fn()
            print(f"OK {nome}")
