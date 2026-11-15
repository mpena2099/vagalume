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


def test_vizier_so_lista():
    from unittest import mock
    import types
    from src import ficha_vsx as fv
    from src import util
    s = types.SimpleNamespace(ra=309.5, dec=41.3)
    # CDS fora: busca so na lista, com aviso brando que nao bloqueia
    with mock.patch.object(util, "VIZIER_ESPELHO", "vizier.idia.ac.za"), \
            mock.patch.object(fv, "_vizier_lista", return_value=['J/ApJS/268/16/table1 (SPB) a 1.0"']) as lista, \
            mock.patch.object(fv, "_vizier") as inteiro:
        f = {}
        assert fv._buscar_vizier(f, s) == fv.AVISO_VIZIER_LISTA
        assert lista.called and not inteiro.called and "268/16" in f["vizier_variaveis"]
    assert not fv.bloqueia(fv.AVISO_VIZIER_LISTA)
    assert fv.bloqueia(fv.AVISO_VIZIER) and fv.bloqueia(fv.AVISO_VIZIER_LISTA + " | " + fv.AVISO_GAIA)
    assert not fv.bloqueia("")
    # na volta do CDS a busca completa e refeita
    assert fv.plano({**NOVAS_FICHA, "avisos": fv.AVISO_VIZIER_LISTA}) == "completar:vizier"
    # CDS no ar: busca em todos; completar troca o aviso antigo (outra redacao) pelo novo
    antigo = "Busca no VizieR inteiro não feita (servidor sem resposta): confira à mão."
    with mock.patch.object(util, "VIZIER_ESPELHO", None), \
            mock.patch.object(fv, "_vizier", return_value=[]):
        f = fv.completar_buscas({"avisos": antigo + " | " + fv.AVISO_GAIA}, s, ["vizier"])
    assert f["avisos"] == fv.AVISO_GAIA
    with tempfile.TemporaryDirectory() as d:
        csv = Path(d) / "fichas.csv"
        pd.DataFrame({"tic": [1, 2, 3], "avisos": [fv.AVISO_VIZIER, fv.AVISO_VIZIER_LISTA, ""]}
                     ).to_csv(csv, index=False)
        assert dados.fichas_com_aviso(csv) == {1}
        assert dados.fichas_com_aviso(csv, so_bloqueio=False) == {1, 2}


NOVAS_FICHA = {"oc_fases": "55 +0.000, 56 +0.001", "blend_veredito": "ok", "blend_motivo": "m",
               "gaia_params_fonte": "sem", "motivo_provavel": "m", "duracao_eclipse_pct": 2.5,
               "par_impar_prof": "par 1.00% / ímpar 1.00%"}


def test_ficha_vsx_retoma():
    from src.ficha_vsx import plano as _plano
    antigo = "Busca no VizieR inteiro não feita (servidor sem resposta): confira à mão em vizier.cds.unistra.fr ou num espelho antes de submeter."
    assert _plano({**NOVAS_FICHA, "avisos": antigo}) == "completar:vizier"
    assert _plano({**NOVAS_FICHA, "avisos": "outro aviso qualquer"}) == "nova"
    import tempfile
    import types
    from pathlib import Path
    from unittest import mock
    import pandas as pd
    from src import ficha_vsx as fv
    assert fv.plano(None) == "nova"
    assert fv.plano({**NOVAS_FICHA, "avisos": ""}) == "manter"
    assert fv.plano({**NOVAS_FICHA, "avisos": ""}, refazer=True) == "nova"
    assert fv.plano({**NOVAS_FICHA, "avisos": fv.AVISO_VIZIER}) == "completar:vizier"
    assert fv.plano({**NOVAS_FICHA, "avisos": fv.AVISO_GAIA + " | " + fv.AVISO_VIZIER}
                    ) == "completar:gaia,vizier"
    sem_params = {k: v for k, v in NOVAS_FICHA.items() if k != "gaia_params_fonte"}
    assert fv.plano({**sem_params, "avisos": fv.AVISO_GAIA}) == "completar:gaia,params,tipo"
    assert fv.plano({**sem_params, "avisos": "", "gaia_dr3": 1}) == "completar:params,tipo"
    assert fv.plano({"avisos": "", "gaia_dr3": 1, "duracao_eclipse_pct": 2.5}
                    ) == "completar:oc,parimpar,blend,params,tipo"
    assert fv.plano({**NOVAS_FICHA, "blend_motivo": fv.BLEND_SEM_CONSULTA + ": x"}
                    ) == "completar:blend"
    assert fv.plano({**NOVAS_FICHA, "avisos": "aviso desconhecido"}) == "nova"
    antiga = {k: v for k, v in NOVAS_FICHA.items() if k != "par_impar_prof"}
    assert fv.plano({**antiga, "avisos": ""}) == "completar:parimpar,tipo"
    assert fv.plano({**antiga, "avisos": fv.AVISO_VIZIER}) == "completar:vizier,parimpar,tipo"
    # ficha anterior sem a duracao do eclipse: so essa coluna e completada
    sem_duracao = {k: v for k, v in NOVAS_FICHA.items() if k != "duracao_eclipse_pct"}
    assert fv.plano({**sem_duracao, "avisos": ""}) == "completar:duracao"

    # o CSV volta igual, inclusive o ID Gaia de 19 digitos e as colunas vazias
    tmp_path = Path(tempfile.mkdtemp())
    mock.patch.object(fv, "VSX_DIR", tmp_path).start()
    ficha = {"tic": 7, "decisao": "confirmado", "periodo_d": 1.23456, "periodo_erro_d": float("nan"),
             "alerta_periodo": "", "fase_secundario": 0.5, "tipo_sugerido": "EA",
             "motivo_tipo": "m", "epoca_bjd": 2460000.1, "amplitude_mag_tess": 0.3,
             "setores": "55", "setores_usados": "55", "suspeito_blend": False,
             "figura_fase": "f.png", "figura_triagem": "t.png",
             "vizier_variaveis": "busca não feita", "avisos": fv.AVISO_VIZIER, **NOVAS_FICHA}
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
    from src import util
    mock.patch.object(util, "VIZIER_ESPELHO", None).start()  # CDS no ar: busca em todos
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
    assert [m["nome"] for m in lista] == ["Treino (opcional)", "Fila revisada", "Ficha pronta",
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


def _resp_vsx(corpo):
    from unittest import mock
    r = mock.Mock()
    r.json.return_value = corpo
    r.raise_for_status.return_value = None
    return r


def test_consultar_vsx():
    from unittest import mock
    from app import vsx
    with mock.patch("requests.get", return_value=_resp_vsx({"VSXObjects": []})):
        assert vsx.consultar_vsx(10.0, 20.0) == []
    um = {"Name": "V1", "RA2000": "10.0", "Declination2000": "20.001",
          "VariabilityType": "L", "MaxMag": "17 G", "MinMag": "18 G", "OID": "5"}
    with mock.patch("requests.get", return_value=_resp_vsx({"VSXObjects": {"VSXObject": um}})) as g:
        r = vsx.consultar_vsx(10.0, 20.0)
        assert g.call_args.kwargs["params"]["radius"] == 60 / 3600
    assert len(r) == 1 and r[0]["periodo"] == "" and abs(r[0]["dist_arcsec"] - 3.6) < 0.05
    assert r[0]["url"].endswith("oid=5")
    longe = dict(um, Name="V2", Declination2000="20.01", Period="1.5", OID="6")
    with mock.patch("requests.get",
                    return_value=_resp_vsx({"VSXObjects": {"VSXObject": [longe, um]}})):
        r = vsx.consultar_vsx(10.0, 20.0)
    assert [a["nome"] for a in r] == ["V1", "V2"] and r[1]["periodo"] == "1.5"


def test_aceite_detectado():
    from app import vsx
    assert vsx.aceite_detectado(None) is None and vsx.aceite_detectado([]) is None
    longe = {"nome": "V9", "dist_arcsec": 25.0, "oid": "1"}
    assert vsx.aceite_detectado([longe]) is None
    perto = {"nome": "TIC 5 b", "dist_arcsec": 3.0, "oid": "2"}
    medio = {"nome": "V8", "dist_arcsec": 9.0, "oid": "3"}
    assert vsx.aceite_detectado([perto, medio, longe]) == "TIC 5 b"
    assert vsx.aceite_detectado([medio]) == "V8"
    assert vsx.aceite_detectado([{"nome": "", "dist_arcsec": 1.0, "oid": "7"}]) == "OID 7"
    assert vsx.aceite_detectado([{"nome": "X", "dist_arcsec": 10.5, "oid": "1"}]) is None
    assert vsx.aceite_detectado([{"nome": "X", "dist_arcsec": 10.5, "oid": "1"}], raio=11) == "X"


def _banco_cand(linhas):
    conn = sqlite3.connect(":memory:")
    pd.DataFrame(linhas).to_sql("candidatos_fase7", conn)
    return conn


def test_descarte_automatico():
    from config import DESLOCAMENTO_MAX_PX as L
    conn = _banco_cand([
        {"tic": 1, "deslocamento_px": 3 * L, "persistente": 1},    # longe: descarta
        {"tic": 2, "deslocamento_px": 1.5 * L, "persistente": 0},  # fora e nao repete: descarta
        {"tic": 3, "deslocamento_px": 1.5 * L, "persistente": 1},  # fora mas repete: humano
        {"tic": 4, "deslocamento_px": 0.5 * L, "persistente": 0},  # dentro: humano
        {"tic": 5, "deslocamento_px": None, "persistente": None},  # sem medida: humano
        {"tic": 6, "deslocamento_px": 5 * L, "persistente": 1},    # humano ja confirmou
        {"tic": 7, "deslocamento_px": 5 * L, "persistente": 1},    # humano ja pos duvida
        {"tic": 8, "deslocamento_px": 1.5 * L, "persistente": None},  # sem outro setor: humano
    ])
    dados.salvar_revisao(conn, 6, "confirmado", "parece real")
    dados.salvar_revisao(conn, 7, "duvida")
    assert dados.descartar_automaticos(conn) == [1, 2]
    assert dados.descartar_automaticos(conn) == []  # idempotente
    df = dados.carregar_candidatos(conn).set_index("tic")
    assert df["decisao"].to_dict() == {1: "descartado", 2: "descartado", 3: "pendente",
                                       4: "pendente", 5: "pendente", 6: "confirmado",
                                       7: "duvida", 8: "pendente"}
    assert df.loc[1, "origem"] == "auto" and "outra estrela" in df.loc[1, "motivo_auto"]
    assert "não se repete" in df.loc[2, "motivo_auto"]
    assert pd.isna(df.loc[6, "origem"]) and df.loc[6, "nota"] == "parece real"
    assert dados.ler_descartes_auto(conn)["tic"].tolist() == [1, 2]

    # Rever: volta a pendente e nao e descartada de novo; decisao humana nao e apagada
    assert dados.rever_auto(conn, 1) is True
    assert dados.rever_auto(conn, 6) is False
    assert dados.descartar_automaticos(conn) == []
    df = dados.carregar_candidatos(conn).set_index("tic")
    assert df.loc[1, "decisao"] == "pendente" and df.loc[6, "decisao"] == "confirmado"
    # o humano pode decidir sobre uma descartada automaticamente: vira decisao humana
    dados.salvar_revisao(conn, 2, "confirmado")
    df = dados.carregar_candidatos(conn).set_index("tic")
    assert df.loc[2, "decisao"] == "confirmado" and pd.isna(df.loc[2, "origem"])
    assert dados.descartar_automaticos(conn) == []
    # "Limpar decisao" num descarte automatico tambem nao o refaz sozinho
    conn2 = _banco_cand([{"tic": 9, "deslocamento_px": 9.0, "persistente": 1}])
    assert dados.descartar_automaticos(conn2) == [9]
    dados.apagar_revisao(conn2, 9)
    assert dados.descartar_automaticos(conn2) == []


def test_revisao_tabela_antiga_ganha_colunas():
    conn = _banco_cand([{"tic": 1, "deslocamento_px": 9.0, "persistente": 1},
                        {"tic": 2, "deslocamento_px": 0.1, "persistente": 1}])
    conn.execute("CREATE TABLE revisao_humana (tic INTEGER PRIMARY KEY, decisao TEXT NOT NULL, "
                 "nota TEXT, atualizado_em TEXT NOT NULL)")
    conn.execute("INSERT INTO revisao_humana VALUES (2, 'confirmado', 'x', '2026-01-01T00:00:00')")
    conn.commit()
    assert dados.descartar_automaticos(conn) == [1]
    df = dados.carregar_candidatos(conn).set_index("tic")
    assert df.loc[2, "decisao"] == "confirmado" and pd.isna(df.loc[2, "origem"])
    assert df.loc[1, "origem"] == "auto"


def test_fichas_usam_duvidas():
    with tempfile.TemporaryDirectory() as d:
        a = Path(d) / "a.csv"
        a.write_text("tic,decisao\n1,confirmado\n2,duvida\n")
        b = Path(d) / "b.csv"
        b.write_text("tic,decisao\n1,confirmado\n")
        assert dados.fichas_usam_duvidas(a) and not dados.fichas_usam_duvidas(b)
        assert not dados.fichas_usam_duvidas(Path(d) / "nao_existe.csv")


def test_vsx_online_fase5():
    from unittest import mock
    from src import cruzar_conhecidos as cc
    achados = [
        {"nome": "V1 Cyg", "periodo": "2.5:", "dist_arcsec": 4.0, "oid": "1"},
        {"nome": "V2", "periodo": "", "dist_arcsec": 12.0, "oid": "2"},
        {"nome": "V3", "periodo": "1.0", "dist_arcsec": 45.0, "oid": "3"},  # fora do raio
    ]
    m = cc.vsx_para_matches(achados)
    assert [x["nome"] for x in m] == ["V1 Cyg", "V2"]
    assert m[0]["catalogo"] == "VSX (online)" and m[0]["periodo"] == 2.5 and m[1]["periodo"] is None
    assert classificar(m, 2.5)["status"] == "conhecido"
    assert classificar(m, 2.5)["match_catalogo"] == "VSX (online)"
    assert classificar(cc.vsx_para_matches([achados[2]]), 1.0)["status"] == "novo"

    resp = _resp_vsx({"VSXObjects": {"VSXObject": {
        "Name": "V1 Cyg", "RA2000": "10.0", "Declination2000": "20.001", "Period": "2.5",
        "VariabilityType": "EA", "OID": "1"}}})
    cc._vsx_falhas["seguidas"] = 0
    with mock.patch("requests.get", return_value=resp):
        r = cc._consultar_vsx_online(10.0, 20.0)
    assert len(r) == 1 and r[0]["nome"] == "V1 Cyg" and r[0]["dist_arcsec"] < 5

    # API fora do ar: segue sem ela, anota e desiste depois de 3 falhas seguidas
    import requests
    cc._vsx_falhas["seguidas"] = 0
    with mock.patch("requests.get", side_effect=requests.ConnectionError), \
            mock.patch("time.sleep"):
        for _ in range(4):
            assert cc._consultar_vsx_online(10.0, 20.0) == []
    assert cc._vsx_falhas["seguidas"] == cc.VSX_FALHAS_MAX
    cc._vsx_falhas["seguidas"] = 0


def _ficha(**extra):
    f = {"tic": 1, "avisos": "", "periodo_d": 1.23456, "periodo_erro_d": 0.00002,
         "epoca_bjd": 2459000.1234, "amplitude_mag_tess": 0.25, "setores_usados": "55, 56",
         "tipo_sugerido": "EA", "gaia_dr3": 123, "gaia_ra": 309.59941949996,
         "gaia_dec": 41.05187172336, "vizier_variaveis": "nenhum", "suspeito_blend": False}
    f.update(extra)
    return f


def test_pendencias_vsx():
    from app import vsx
    from config import MARCA_PODE_SUBMETER

    def niveis(p):
        return [n for n, _ in p]
    assert "bloqueia" not in niveis(vsx.pendencias(_ficha(), "EA", []))
    p = vsx.pendencias(_ficha(avisos=f"Nao submeta ainda | {MARCA_PODE_SUBMETER}: x"), "EA", [])
    assert ("bloqueia", "Nao submeta ainda") in p
    amb = _ficha(tipo_sugerido="ROT, EW ou pulsante")
    assert ("bloqueia", "Escolha o tipo pela forma da curva") in vsx.pendencias(amb, None, [])
    assert "bloqueia" not in niveis(vsx.pendencias(amb, "EW", []))
    perto = [{"nome": "V1", "dist_arcsec": 10.0}]
    assert "bloqueia" in niveis(vsx.pendencias(_ficha(), "EA", perto))
    medio = [{"nome": "V1", "dist_arcsec": 45.0}]
    p = vsx.pendencias(_ficha(), "EA", medio)
    assert "bloqueia" not in niveis(p) and any("45" in t for _, t in p)
    assert ("atencao", "VSX online não conferido") in vsx.pendencias(_ficha(), "EA", None)
    assert "atencao" in niveis(vsx.pendencias(_ficha(alerta_periodo="x", suspeito_blend=True),
                                              "EA", []))


def _setores_sintetico(deslocamentos, periodo=1.3, t0=0.4):
    rng = np.random.default_rng(1)
    curvas = []
    for k, (inicio, extra) in enumerate(zip((0.0, 300.0, 700.0), deslocamentos)):
        t = np.arange(inicio, inicio + 27, 0.01)
        f = 1 - 0.01 * np.cos(2 * np.pi * (t - t0 - extra * periodo) / periodo)
        curvas.append((t, f + rng.normal(0, 0.001, t.size)))
    return curvas


def test_oc_setores():
    from src.periodo_setores import oc_setores
    # alinhado: o O-C cai a zero e o periodo refinado fica perto do verdadeiro
    oc = oc_setores(_setores_sintetico((0, 0, 0)), 1.3, False, [41, 55, 75])
    assert oc["alinhado"] is True and oc["oc_max_fase"] < 0.02 and oc["setores"] == [41, 55, 75]
    assert abs(oc["periodo_d"] - 1.3) < 1e-4 and np.isfinite(oc["periodo_erro_d"])
    # desalinhado: um setor 0,3 em fase fora, sem periodo refinado
    oc = oc_setores(_setores_sintetico((0, 0.3, 0)), 1.3, False, [41, 55, 75])
    assert oc["alinhado"] is False and oc["oc_max_fase"] > 0.02
    assert oc["periodo_d"] == 1.3 and np.isnan(oc["epoca"])
    # dois setores: o desencontro dos dois decide
    assert oc_setores(_setores_sintetico((0, 0, 0))[:2], 1.3, False)["alinhado"] is True
    assert oc_setores(_setores_sintetico((0, 0.3, 0))[:2], 1.3, False)["alinhado"] is False
    # binaria de minimos quase iguais: com a epoca, cada setor usa o minimo da fase certa
    rng = np.random.default_rng(3)
    eb = []
    for inicio, fundo2 in ((0.0, 1.0), (300.0, 1.1), (700.0, 0.95)):
        t = np.arange(inicio, inicio + 27, 0.01)
        fase = ((t - 0.4) / 2.6) % 1
        prim = np.exp(-0.5 * (((fase + 0.5) % 1 - 0.5) / 0.02) ** 2)
        sec = np.exp(-0.5 * ((fase - 0.5) / 0.02) ** 2)
        eb.append((t, 1 - 0.02 * prim - 0.02 * fundo2 * sec + rng.normal(0, 0.0005, t.size)))
    sem_epoca = oc_setores(eb, 2.6, True)
    assert sem_epoca["alinhado"] is False  # o minimo mais fundo muda de eclipse entre setores
    com = oc_setores(eb, 2.6, True, epoca=0.4)
    assert com["alinhado"] is True, com
    # um setor so: nada a conferir
    um = oc_setores(_setores_sintetico((0, 0, 0))[:1], 1.3, False)
    assert um["alinhado"] is None and um["oc_fase"] == []


def test_aplicar_oc():
    from src import ficha_vsx as fv
    ok = {"alinhado": True, "setores": [41, 55], "oc_fase": [0.001, -0.001], "oc_max_fase": 0.001,
          "periodo_d": 1.30001, "periodo_erro_d": 2e-6, "epoca": 100.0}
    f = fv.aplicar_oc({"periodo_d": 1.3, "alerta_periodo": "nao alinham"}, ok)
    assert f["alerta_periodo"] == "" and f["periodo_d"] == 1.30001
    assert f["epoca_bjd"] == 100.0 + fv.BTJD_PARA_BJD and f["periodo_erro_d"] == 2e-6
    ruim = dict(ok, alinhado=False, oc_fase=[0.0, 0.26], oc_max_fase=0.26)
    f = fv.aplicar_oc({"periodo_d": 1.3, "alerta_periodo": ""}, ruim)
    assert "55 +0.260" in f["alerta_periodo"] and f["periodo_d"] == 1.3
    f = fv.aplicar_oc({"periodo_d": 1.3, "alerta_periodo": "um so setor"},
                      {"alinhado": None, "setores": [], "oc_fase": []})
    assert f["alerta_periodo"] == "um so setor" and f["oc_fases"] == "um setor"


def test_blend_veredito():
    from src.ficha_vsx import veredito_blend
    longe = [{"dist_arcsec": 40.0, "dmag": 1.5}]
    # pico no alvo e vizinha a mais de 1 px: resolvido
    v, m = veredito_blend(0.5, longe)
    assert v == "ok" and "pico no alvo" in m and '40"' in m
    assert veredito_blend(0.5, [])[0] == "ok"
    # pico deslocado na distancia da vizinha (40" = 1,9 px): o sinal e dela
    v, m = veredito_blend(1.8, longe)
    assert v == "bloqueia" and "vizinha" in m
    # pico deslocado que nao bate com a vizinha: indefinido
    assert veredito_blend(4.5, longe)[0] == "atencao"
    # vizinha a menos de 1 px (21"), ou sem deslocamento medido: atencao
    assert veredito_blend(0.3, [{"dist_arcsec": 12.0, "dmag": 1.0}])[0] == "atencao"
    assert veredito_blend(None, longe)[0] == "atencao"


def test_vizinhas_suspeitas():
    from astropy.coordinates import SkyCoord
    from src.ficha_vsx import vizinhas_suspeitas
    alvo = SkyCoord(10.0, 20.0, unit="deg")
    tab = pd.DataFrame({"RA_ICRS": [10.0, 10.0, 10.0], "DE_ICRS": [20.0, 20.0 + 30 / 3600, 20.0 + 30 / 3600],
                        "Gmag": [12.0, 13.0, 18.0]})
    # a vizinha de dG=1 precisa de amplitude 0.01*(1+0.4)/0.4 = 0.035 < 0.5; a de dG=6 nao cabe no corte
    viz = vizinhas_suspeitas(tab, alvo, 12.0, 0.01)
    assert len(viz) == 1 and abs(viz[0]["dist_arcsec"] - 30) < 0.1 and viz[0]["dmag"] == 1.0
    assert vizinhas_suspeitas(tab, alvo, 12.0, 0.9) == []


def test_tipo_provavel():
    from src.ficha_vsx import tipo_provavel as tp
    assert tp(0.1, 7500, False, True)[0] == "DSCT"
    assert tp(0.1, 6000, False, True)[0] is None  # Teff baixo demais para DSCT
    assert tp(1.0, 12000, False, True)[0] == "SPB"
    assert tp(1.0, 7200, False, True)[0] == "GDOR"
    assert tp(1.2, 5000, False, True)[0] == "ROT"
    assert tp(1.2, 5000, False, False)[0] is None  # curva nao e onda unica
    t, m = tp(0.3, 5500, True, False)
    assert t == "EW" and "iguais" in m
    assert tp(0.3, 5500, False, False)[0] is None  # minimos diferentes
    assert tp(0.45, 5500, True, True)[0] == "EW"  # EW vale e ROT nao (P < 0,5)
    # conflito: DSCT e EW valem juntas
    t, m = tp(0.2, 6700, True, True)
    assert t is None and "conflito" in m
    # sem Teff ou gigante: sem sugestao
    assert tp(0.1, None, True, True)[0] is None and "Teff" in tp(0.1, None, True, True)[1]
    assert tp(1.2, 5000, False, True, logg=2.0)[0] is None
    # limites das faixas do VSX
    assert tp(0.25, 7500, False, True)[0] == "GDOR"  # acima de 0,2 d nao e DSCT
    assert tp(0.35, 12000, False, True)[0] is None  # SPB comeca em 0,4 d
    assert tp(4.5, 12000, False, True)[0] == "SPB"
    assert tp(3.5, 6400, False, True)[0] == "GDOR"
    assert tp(4.5, 7000, False, True)[0] is None


def test_razao_harmonicos():
    from src.ficha_vsx import razao_harmonicos
    t = np.arange(0, 20, 0.01)
    onda = np.cos(2 * np.pi * t / 1.7)
    assert razao_harmonicos(t, onda, 1.7) < 0.05
    assert razao_harmonicos(t, onda + 0.8 * np.cos(4 * np.pi * t / 1.7), 1.7) > 0.7


def test_pendencias_blend_oc_tipo():
    from app import vsx

    def niveis(p):
        return dict((t, n) for n, t in p)

    def tem(p, nivel, trecho):
        return any(n == nivel and trecho in t for n, t in p)
    # blend: os tres vereditos
    assert tem(vsx.pendencias(_ficha(blend_veredito="ok", blend_motivo="pico no alvo"), "EA", []),
               "ok", "Blend resolvido: pico no alvo")
    assert tem(vsx.pendencias(_ficha(blend_veredito="bloqueia", blend_motivo="x", suspeito_blend=True),
                              "EA", []), "bloqueia", "Blend: x")
    assert tem(vsx.pendencias(_ficha(blend_veredito="atencao", blend_motivo="y"), "EA", []),
               "atencao", "Blend: y")
    # ficha antiga, sem as colunas novas: regra de antes
    assert tem(vsx.pendencias(_ficha(suspeito_blend=True), "EA", []), "atencao", "Vizinha Gaia")
    assert tem(vsx.pendencias(_ficha(), "EA", []), "ok", "Sem vizinha Gaia")
    # periodo com O-C
    assert tem(vsx.pendencias(_ficha(alerta_periodo="x", oc_fases="55 +0.2"), "EA", []),
               "atencao", "55 +0.2")
    assert tem(vsx.pendencias(_ficha(oc_fases="55 +0.0", oc_max_fase=0.004), "EA", []),
               "ok", "0.004")
    assert tem(vsx.pendencias(_ficha(), "EA", []), "ok", "Período consistente entre setores")
    # tipo provavel: nao bloqueia mais, pede confirmacao; sem ele continua bloqueando
    amb = _ficha(tipo_sugerido="ROT, EW ou pulsante")
    prov = dict(amb, tipo_provavel="EW", motivo_provavel="minimos iguais")
    p = vsx.pendencias(prov, None, [])
    assert tem(p, "atencao", "Confirme o tipo provável EW (minimos iguais)") and not tem(p, "bloqueia", "tipo")
    assert tem(vsx.pendencias(prov, "EW", [], confirmado=False), "atencao", "Confirme o tipo provável EW")
    assert not tem(vsx.pendencias(prov, "EW", [], confirmado=True), "atencao", "Confirme")
    assert not tem(vsx.pendencias(prov, "ROT", [], confirmado=False), "atencao", "Confirme")
    assert tem(vsx.pendencias(amb, None, []), "bloqueia", "Escolha o tipo")
    assert tem(vsx.pendencias(dict(amb, tipo_provavel=""), None, []), "bloqueia", "Escolha o tipo")


def _eclipses(depths, n_ciclos=60, ruido=0.004, periodo=1.9939, dur=0.09, cad=10 / 1440, seed=1):
    """Curva com eclipses de profundidade alternada `depths` (um por ciclo de `periodo`)."""
    rng = np.random.default_rng(seed)
    t = np.arange(0, n_ciclos * periodo, cad)
    n = np.round(t / periodo).astype(int)
    fase_d = (t - n * periodo)
    prof = np.array(depths)[n % len(depths)]
    f = 1 - prof * np.exp(-fase_d ** 2 / (2 * (dur / 2.355) ** 2))
    return t, f + rng.normal(0, ruido, t.size)


def test_par_impar():
    from src.periodo_setores import largura_eclipse, par_impar_setores, teste_par_impar
    # eclipses iguais: mantem P
    t, f = _eclipses([0.012, 0.012])
    larg = largura_eclipse(t, f, 1.9939, 0.0)
    assert 0.02 < larg < 0.08  # FWHM 0,09 d = 0,045 em fase, medido na curva
    assert largura_eclipse(*_eclipses([0.012, 0.012], dur=0.3), 1.9939, 0.0) > 2 * larg
    r = teste_par_impar(t, f, 1.9939, 0.0)
    assert r["decide"] and abs(r["sigma"]) < 3
    # 1,2% x 1,0%: dobra, par mais fundo (epoca no fundo)
    t, f = _eclipses([0.012, 0.010])
    r = teste_par_impar(t, f, 1.9939, 0.0)
    assert r["sigma"] > 3 and r["prof_par"] > r["prof_impar"]
    assert abs(r["prof_par"] - 0.012) < 0.0015 and abs(r["prof_impar"] - 0.010) < 0.0015
    # tres setores sinteticos (ruido 0,3%), mesmo sinal em todos
    t, f = _eclipses([0.012, 0.010], n_ciclos=300, ruido=0.003)
    cs = [(t[(t > a) & (t < a + 150)], f[(t > a) & (t < a + 150)]) for a in (0, 200, 400)]
    res = par_impar_setores(cs, 1.9939, 0.0, [1, 2, 3])
    assert res["dobrar"] and res["par_mais_fundo"] and res["consistente"]
    # epoca no ciclo impar: o par (relativo a ela) fica mais raso
    res = par_impar_setores(cs, 1.9939, 1.9939, [1, 2, 3])
    assert res["dobrar"] and not res["par_mais_fundo"]
    # poucos eclipses: sem decisao
    t, f = _eclipses([0.012, 0.010], n_ciclos=4)
    r = teste_par_impar(t, f, 1.9939, 0.0)
    assert not r["decide"]
    assert not par_impar_setores([(t, f)], 1.9939, 0.0)["dobrar"]
    # sinais opostos entre setores: nao dobra
    t, f = _eclipses([0.012, 0.010], n_ciclos=100, ruido=0.003)
    t2, f2 = _eclipses([0.010, 0.012], n_ciclos=100, ruido=0.003, seed=2)
    r = par_impar_setores([(t, f), (t2 + 150 * 1.9939, f2)], 1.9939, 0.0)
    assert not r["consistente"] and not r["dobrar"]


def test_duracao_eclipse():
    from src.periodo_setores import duracao_eclipse
    rng = np.random.default_rng(0)
    t = np.arange(0, 30, 4 / 1440)
    fase = (t / 2.5) % 1
    caixa = 1 - 0.01 * (fase < 0.03) + rng.normal(0, 0.0002, t.size)
    d = duracao_eclipse(t, caixa, 2.5, 0.0)
    assert 0.025 < d < 0.04, d
    plano = np.ones_like(t)
    assert np.isnan(duracao_eclipse(t, plano, 2.5, 0.0))


def test_par_impar_ficha_e_comentario():
    from app import vsx
    from src import ficha_vsx as fv
    dobrada = _ficha(par_impar_dobrado=True, par_impar_sigma=4.1,
                     par_impar_prof="par 0.87% / ímpar 1.04%")
    p = vsx.pendencias(dobrada, "EA", [])
    assert ("ok", "Período dobrado: eclipses pares e ímpares diferem 4.1 σ (par 0.87% / ímpar 1.04%)") in p
    c = vsx.comentario(dobrada, "EA", [])
    assert ("Odd/even eclipse depths differ (1.04% vs 0.87%), so the orbital period is 2x "
            "the BLS period.") in c and "—" not in c
    igual = _ficha(par_impar_dobrado=False, par_impar_sigma=0.8,
                   par_impar_prof="par 1.00% / ímpar 1.00%")
    assert any(t.startswith("Eclipses pares e ímpares iguais") for _, t in vsx.pendencias(igual, "EA", []))
    assert "Odd/even" not in vsx.comentario(igual, "EA", [])
    sem = _ficha(par_impar_prof="sem decisão: poucos eclipses")
    assert any(n == "atencao" and "sem decisão" in t for n, t in vsx.pendencias(sem, "EA", []))
    assert fv.formatar_par_impar({"geral": {"decide": False}}) == "sem decisão: poucos eclipses"


def test_comentario_vsx():
    from app import vsx
    c = vsx.comentario(_ficha(), "EA", [])
    assert "1.23456" in c and "TESS" in c and "—" not in c
    assert "Epoch of minimum: HJD 2459000.1226 (converted from TESS BJD_TDB 2459000.1234)." in c
    assert "BJD_TDB 2459000.1234 (TESS times are BJD_TDB" not in c
    assert "Eclipse duration: 2.5% of the period." in vsx.comentario(
        _ficha(duracao_eclipse_pct=2.5), "EA", [])
    assert "Eclipse duration" not in vsx.comentario(
        _ficha(duracao_eclipse_pct="não se aplica"), "EA", [])
    sem_coord = {k: v for k, v in _ficha().items() if k not in ("gaia_ra", "gaia_dec")}
    assert "BJD_TDB 2459000.1234" in vsx.comentario(sem_coord, "EA", [])
    assert "No known VSX variable within 2'" in c and "identifiers from Gaia DR3" in c
    assert c.startswith("Found with the Vagalume search pipeline") and "Type:" not in c
    assert "brighter Gaia neighbour" not in c
    assert "Gaia neighbour (less than 4 mag fainter)" in vsx.comentario(_ficha(suspeito_blend=True), "EA", [])
    assert "No known VSX" not in vsx.comentario(_ficha(), "EA", None)
    assert "epoca" not in vsx.comentario({"tic": 1}, None, None).lower()


def test_tipo_final_envio():
    conn = sqlite3.connect(":memory:")
    dados.marcar_tipo(conn, 3, "EW")
    dados.marcar_envio(conn, 3, enviada=True, nome_vsx="V9")
    e = dados.ler_envios(conn).set_index("tic").loc[3]
    assert e["tipo_final"] == "EW" and e["nome_vsx"] == "V9" and isinstance(e["enviada_em"], str)
    dados.marcar_tipo(conn, 3, "EA")
    e = dados.ler_envios(conn).set_index("tic").loc[3]
    assert e["tipo_final"] == "EA" and e["nome_vsx"] == "V9" and isinstance(e["enviada_em"], str)
    dados.marcar_tipo(conn, 4, "ROT")
    assert pd.isna(dados.ler_envios(conn).set_index("tic").loc[4, "enviada_em"])


def test_migrar_envio_antigo():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE envio_vsx (tic INTEGER PRIMARY KEY, enviada_em TEXT, "
                 "aceita_em TEXT, nome_vsx TEXT)")
    conn.execute("INSERT INTO envio_vsx VALUES (1, '2026-01-01T00:00:00', NULL, 'V1')")
    conn.commit()
    e = dados.ler_envios(conn).set_index("tic")
    assert e.loc[1, "nome_vsx"] == "V1" and pd.isna(e.loc[1, "tipo_final"])
    dados.marcar_tipo(conn, 1, "EB")
    dados.marcar_envio(conn, 1, aceita=True)
    e = dados.ler_envios(conn).set_index("tic").loc[1]
    assert e["tipo_final"] == "EB" and e["nome_vsx"] == "V1" and isinstance(e["aceita_em"], str)


def test_limite_envio():
    import datetime as dt
    from app import vsx
    hoje = dt.date(2026, 11, 15)
    assert vsx.limite_envio(1, [], hoje) is None
    pend = [{"tic": 2, "enviada_em": "2026-11-10T10:00:00", "aceita_em": None}]
    r = vsx.limite_envio(1, pend, hoje)
    assert r[0] == "bloqueia" and "TIC 2" in r[1]
    assert vsx.limite_envio(2, pend, hoje) is None
    aceita = [{"tic": 2, "enviada_em": "2026-11-01", "aceita_em": "2026-11-12"}]
    assert vsx.limite_envio(1, aceita + pend[:0], hoje) is None
    cinco = aceita + [{"tic": 10 + i, "enviada_em": "2026-11-13", "aceita_em": None}
                      for i in range(5)]
    assert vsx.limite_envio(1, cinco, hoje)[1].startswith("Limite do VSX")
    velhas = aceita + [{"tic": 10 + i, "enviada_em": "2026-11-01", "aceita_em": None}
                       for i in range(5)]
    assert vsx.limite_envio(1, velhas, hoje) is None
    assert vsx.limite_envio(1, [{"tic": 3, "enviada_em": float("nan"), "aceita_em": None}],
                            hoje) is None


def test_hjd_de_bjd():
    from app.vsx import hjd_de_bjd
    bjd = 2459696.0136660584
    hjd = hjd_de_bjd(bjd, 309.59941949996, 41.05187172336)
    assert abs(hjd - 2459696.01289) < 1e-4, hjd
    minutos = abs(bjd - hjd) * 1440
    assert 0.5 < minutos < 1.5, minutos


def test_coordenadas_j2000():
    from app.vsx import coordenadas_j2000
    assert coordenadas_j2000(309.59941949996, 41.05187172336) == (
        "309.599419 +41.051872", "20 38 23.861 +41 03 06.738")
    sexagesimal = coordenadas_j2000(309.59941949996, -41.05187172336)[1]
    assert sexagesimal.split()[3] == "-41", sexagesimal


def test_escala_px():
    from src.carta import escala_px
    assert escala_px(5, 500) == 0.6
    assert abs(escala_px(10, 1000) - 0.6) < 1e-12


def test_vsx_vizinha_120():
    from app import vsx
    f = {"periodo_d": 3.98776, "blend_motivo": "pico no alvo (0.7 px); vizinha a 27\""}
    rot = {"nome": "Gaia DR3 2064819310104461440", "tipo": "ROT", "periodo": "",
           "max": "14.82 G", "min": "14.86 G", "dist_arcsec": 98.8}
    p = vsx.pendencias(f, "EA", [rot])
    assert ("ok", next(t for n, t in p if "98\"" in t or "99\"" in t)) in p
    c = vsx.comentario(f, "EA", [rot])
    assert "lies 99\" away (about 5 TESS pixels); the pixel map peaks on the target." in c
    assert "ROT, 14.82-14.86 G)" in c
    mesmo = dict(rot, periodo="7.9755")
    assert any(n == "bloqueia" and "mesmo período" in t for n, t in vsx.pendencias(f, "EA", [mesmo]))
    medio = dict(rot, dist_arcsec=45.0)
    assert any(n == "atencao" for n, t in vsx.pendencias(f, "EA", [medio]))
    assert "VSX variable within" not in vsx.comentario(f, "EA", [dict(rot, dist_arcsec=10.0)])


def test_nomes_catalogo():
    from app import vsx
    linha = {"GAIA": "2064816282152023680", "TWOMASS": "20382386+4103066",
             "UCAC": "656-090678", "ALLWISE": "J203823.88+410306.3", "TYC": "--", "HIP": None}
    assert vsx.nomes_catalogo(linha) == ["Gaia DR3 2064816282152023680",
                                         "2MASS J20382386+4103066", "UCAC4 656-090678",
                                         "WISEA J203823.88+410306.3"]
    assert vsx.nomes_catalogo({}) == []


def _ficha_tic64710105(**extra):
    f = {"tic": 64710105, "periodo_d": 3.98776029, "epoca_bjd": 2459696.0136660584,
         "gaia_ra": 309.59941949996, "gaia_dec": 41.05187172336, "v_estimada": 12.495,
         "amplitude_mag_tess": 0.013, "duracao_eclipse_pct": 3.2,
         "setores_usados": "55,56,41", "par_impar_dobrado": True,
         "par_impar_prof": "par 0.87% / ímpar 1.04%", "tipo_sugerido": "EA",
         "figura_triagem": "data/triagem/64710105.png",
         "blend_motivo": 'pico no alvo (0.7 px); vizinha a 27"',
         "gaia_dr3": 2064816282152023680}
    f.update(extra)
    return f


def campos_tela(telas, n):
    return {r: (v, c) for r, v, c, _ in telas[n]["campos"]}


def test_telas_wizard():
    from app import vsx
    telas = vsx.telas_wizard(_ficha_tic64710105(), "EA", None, [], confirmado=True,
                             descobridor="Mauricio O. Pena")
    assert [t["tela"] for t in telas] == [
        "Submission method",
        "Do you want to submit a new variable star based on your observations only?",
        "What is the position of this new variable object?",
        "What names is this new variable object known by?",
        "What is the variability type for this variable object?",
        "What is the spectral type for this variable object?",
        "What is the magnitude range for variability of this object?",
        "What is the period of variability for this object?",
        "Are there any supporting files to accompany this submission?",
        "Who was the original discoverer of this variable object?",
        "Is there a reference to literature for this object?",
        "Are there any remarks to be added to this submission?",
        "Is all the information provided correct?",
    ]
    assert campos_tela(telas, 11)["Remarks"][0].startswith("Found with the Vagalume")

    def campos(n):
        return {r: (v, c) for r, v, c, _ in telas[n]["campos"]}
    assert campos(7)["Epoch (HJD)"][0] == "2459696.0129"
    assert campos(7)["Rise/eclipse duration Uncertain"][0] == "marcado"
    assert campos(4)["Uncertain"][0] == "desmarcado"
    descricoes = [v for _, v, c, _ in telas[8]["campos"] if c and v.startswith("TESS QLP")]
    assert "sectors 41, 55, 56" in descricoes[0] and "1.04% and 0.87%" in descricoes[0]
    pixel = [v for _, v, _, _ in telas[8]["campos"] if v.startswith("Detection figure")]
    assert "0.7 px" in pixel[0]
    assert campos(9)["Discoverer"][0] == "Mauricio O. Pena"
    amb = _ficha_tic64710105(tipo_sugerido="ROT, EW ou pulsante", tipo_provavel="EW")
    marcado = vsx.telas_wizard(amb, "EW", None, [], confirmado=False, descobridor="X")
    assert dict((r, v) for r, v, *_ in marcado[4]["campos"])["Uncertain"] == "marcado"
    confirmado = vsx.telas_wizard(amb, "EW", None, [], confirmado=True, descobridor="X")
    assert dict((r, v) for r, v, *_ in confirmado[4]["campos"])["Uncertain"] == "desmarcado"


def test_telas_wizard_sem_valores():
    from app import vsx
    f = {k: v for k, v in _ficha_tic64710105().items()
         if k not in ("v_estimada", "duracao_eclipse_pct")}
    telas = vsx.telas_wizard(f, "EA", None, [], confirmado=True, descobridor="X")
    assert len(telas) == 13
    assert "Maximum magnitude" not in [r for r, *_ in telas[6]["campos"]]
    assert dict((r, v) for r, v, *_ in telas[7]["campos"])["Rise/eclipse duration (%)"] == "vazio"


if __name__ == "__main__":
    for nome, fn in list(globals().items()):
        if nome.startswith("test_"):
            fn()
            print(f"OK {nome}")
