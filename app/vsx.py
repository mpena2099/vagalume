"""Pendencias e comentario da submissao: sem Streamlit, testavel offline."""

import re

from config import DESCOBRIDOR, MARCA_PODE_SUBMETER

# abaixo disso o ASAS-SN e o ZTF nao veem a variacao (ruido de ~2 a 3%)
AMP_SOLO_MIN_MAG = 0.05
from src.vsx_api import URL_API, URL_DETALHE, _distancia_arcsec, consultar_vsx  # noqa: F401

TIPOS_VSX = {
    "EA": "binária eclipsante, mínimos bem separados (tipo Algol)",
    "EB": "binária eclipsante contínua, mínimos de profundidades diferentes (tipo Beta Lyrae)",
    "EW": "binária de contato, dois mínimos iguais (tipo W UMa)",
    "ELL": "variável elipsoidal, sem eclipse",
    "ROT": "rotacional, mancha na superfície",
    "BY": "rotacional com manchas, anã tipo BY Draconis",
    "DSCT": "pulsante Delta Scuti, período curto",
    "GDOR": "pulsante Gamma Doradus",
    "SPB": "pulsante B de pulsação lenta",
    "RRAB": "RR Lyrae, curva assimétrica",
    "RRC": "RR Lyrae, curva quase senoidal",
    "CEP": "Cefeida",
    "VAR": "variável sem tipo definido",
}


RAIO_ACEITE_ARCSEC = 10
URL_PROJETO = "https://github.com/mpena2099/vagalume"
# mesmo raio do Spot Check do formulario do VSX
RAIO_VSX_ARCSEC = 120
PIXEL_TESS_ARCSEC = 21


def _mesmo_periodo(p1, p2, tol=0.01) -> bool:
    try:
        p1, p2 = float(p1), float(p2)
    except (TypeError, ValueError):
        return False
    return p1 > 0 and p2 > 0 and any(abs(p1 / p2 - r) <= tol * r for r in (1.0, 0.5, 2.0))


def _faixa_mag(mx, mn) -> str:
    """', 14.82-14.86 G' a partir de '14.82 G' e '14.86 G' do VSX ('' sem os dois)."""
    if not mx or not mn:
        return ""
    a, b = str(mx).split(), str(mn).split()
    banda = a[1] if len(a) > 1 else "mag"
    return f", {a[0]}-{b[0]} {banda}"


def _rotulo_vsx(a: dict) -> str:
    extra = [x for x in (a.get("tipo"), f"P {a['periodo']} d" if a.get("periodo") else "") if x]
    return a["nome"] + (f" ({', '.join(extra)})" if extra else "")


def hjd_de_bjd(bjd_tdb: float, ra: float, dec: float) -> float:
    """HJD (UTC) a partir do BJD_TDB do TESS: tira o tempo de luz baricentrico e soma o
    heliocentrico, na posicao da estrela."""
    from astropy.coordinates import EarthLocation, SkyCoord
    from astropy.time import Time

    c = SkyCoord(ra, dec, unit="deg")
    t = Time(bjd_tdb, format="jd", scale="tdb",
             location=EarthLocation.from_geocentric(0, 0, 0, unit="m"))
    geo = t - t.light_travel_time(c, "barycentric")
    return float((geo + geo.light_travel_time(c, "heliocentric")).utc.jd)


def coordenadas_j2000(ra: float, dec: float) -> tuple[str, str]:
    """(graus, sexagesimal) da posicao, para colar no VSX."""
    from astropy.coordinates import SkyCoord

    c = SkyCoord(ra, dec, unit="deg")
    return f"{ra:.6f} {dec:+.6f}", c.to_string("hmsdms", sep=" ", precision=3)


def aceite_detectado(achados: list[dict] | None, raio: float = RAIO_ACEITE_ARCSEC) -> str | None:
    """Nome no VSX do objeto a ate `raio` arcsec da posicao Gaia da ficha, ou None.

    Vale so para estrela ja enviada: antes do envio a ficha bloqueia se houver variavel do VSX
    a 30" ou menos, entao um objeto a 10" que aparece depois do envio e a propria estrela.
    """
    if not achados:
        return None
    perto = [a for a in achados if a["dist_arcsec"] <= raio]
    if not perto:
        return None
    mais_perto = min(perto, key=lambda a: a["dist_arcsec"])
    return mais_perto.get("nome") or f"OID {mais_perto.get('oid')}"


LIMITE_SEMANA = 5


def nomes_catalogo(linha: dict) -> list[str]:
    """Designacoes no formato do Dictionary of Nomenclature, a partir de uma linha do TIC."""
    def v(k):
        x = linha.get(k)
        return None if x is None or str(x).strip() in ("", "--", "nan", "None") else str(x).strip()

    nomes = []
    if v("GAIA"):
        nomes.append(f"Gaia DR3 {v('GAIA')}")
    if v("TWOMASS"):
        nomes.append(f"2MASS J{v('TWOMASS')}")
    if v("UCAC"):
        nomes.append(f"UCAC4 {v('UCAC')}")
    if v("ALLWISE"):
        nomes.append(f"WISEA {v('ALLWISE')}")
    if v("TYC"):
        nomes.append(f"TYC {v('TYC')}")
    if v("HIP"):
        nomes.append(f"HIP {v('HIP')}")
    return nomes


def limite_envio(tic, envios: list[dict], hoje) -> tuple[str, str] | None:
    """Regra do VSX: usuario novo so tem uma submissao ate a primeira ser aprovada; depois,
    5 por semana. `envios`: dicts com tic, enviada_em, aceita_em (datas ISO ou vazio)."""
    import datetime as dt

    def data(v):
        try:
            return dt.date.fromisoformat(str(v)[:10]) if v and v == v else None
        except ValueError:
            return None

    outros = [e for e in envios if e.get("tic") != tic and data(e.get("enviada_em"))]
    if any(e.get("tic") == tic and data(e.get("enviada_em")) for e in envios):
        return None
    if not any(data(e.get("aceita_em")) for e in envios):
        abertas = [e["tic"] for e in outros if not data(e.get("aceita_em"))]
        if abertas:
            return ("bloqueia", f"Aguarde o aceite da TIC {abertas[0]}: usuário novo no VSX só "
                                "pode ter uma submissão até a primeira ser aprovada")
        return None
    semana = [e for e in outros if (hoje - data(e["enviada_em"])).days < 7]
    if len(semana) >= LIMITE_SEMANA:
        return ("bloqueia", f"Limite do VSX: {LIMITE_SEMANA} submissões por semana já usadas")
    return None


def pendencias(f: dict, tipo_final: str | None, vsx: list[dict] | None,
               confirmado: bool = True) -> list[tuple[str, str]]:
    """(nivel, texto) com nivel em ok, atencao ou bloqueia. `confirmado`: o `tipo_final` foi
    escolhido por quem revisa (salvo), nao so pre-selecionado com o tipo provavel da ficha."""
    itens = []
    for parte in str(f.get("avisos") or "").split(" | "):
        if not parte.strip():
            continue
        if MARCA_PODE_SUBMETER in parte:
            itens.append(("ok", "Busca no VizieR feita nos principais catálogos de variáveis"))
        else:
            itens.append(("bloqueia", parte.strip()))

    if f.get("alerta_periodo"):
        itens.append(("atencao", "Períodos dos setores não alinham: confira na curva em fase "
                                 "se os eclipses dos setores caem no mesmo lugar"
                                 + (f" (O-C em fase: {f['oc_fases']})" if f.get("oc_fases") else "")))
    elif f.get("oc_max_fase") == f.get("oc_max_fase") and f.get("oc_max_fase") is not None \
            and f.get("oc_fases") != "um setor":
        itens.append(("ok", f"Período consistente entre setores (O-C máximo {f['oc_max_fase']:.3f} "
                            "em fase)"))
    else:
        itens.append(("ok", "Período consistente entre setores"))

    sigma = f.get("par_impar_sigma")
    sigma = None if sigma is None or sigma != sigma else float(sigma)
    if f.get("par_impar_dobrado"):
        itens.append(("ok", f"Período dobrado: eclipses pares e ímpares diferem "
                            f"{sigma:.1f} σ ({f.get('par_impar_prof')})" if sigma is not None
                      else "Período dobrado: eclipses pares e ímpares diferem"))
    elif sigma is not None:
        itens.append(("ok", "Eclipses pares e ímpares iguais" + f" ({sigma:.1f} σ)"))
    elif str(f.get("par_impar_prof") or "").startswith("sem decisão"):
        itens.append(("atencao", "Eclipses pares x ímpares sem decisão (poucos eclipses): "
                                 "confira na curva em fase se os dois mínimos têm a mesma "
                                 "profundidade"))

    veredito = f.get("blend_veredito")
    motivo = f.get("blend_motivo") or ""
    if veredito == "ok":
        itens.append(("ok", f"Blend resolvido: {motivo}"))
    elif veredito == "bloqueia":
        itens.append(("bloqueia", f"Blend: {motivo}"))
    elif veredito == "atencao":
        itens.append(("atencao", f"Blend: {motivo}"))
    elif f.get("suspeito_blend"):
        itens.append(("atencao", "Vizinha Gaia brilhante perto: confira no mapa por pixel "
                                 "(figura da triagem) se o pico está no alvo e mencione a "
                                 "vizinha no comentário"))
    else:
        itens.append(("ok", "Sem vizinha Gaia brilhante suspeita"))

    if "," in str(f.get("tipo_sugerido") or ""):
        provavel = f.get("tipo_provavel")
        if provavel and (not tipo_final or (tipo_final == provavel and not confirmado)):
            itens.append(("atencao", f"Confirme o tipo provável {provavel} "
                                     f"({f.get('motivo_provavel') or 'ver Detalhes'})"))
        elif not tipo_final:
            itens.append(("bloqueia", "Escolha o tipo pela forma da curva"))

    if vsx is None:
        itens.append(("atencao", "VSX online não conferido"))
    elif not vsx:
        itens.append(("ok", "Nenhuma variável do VSX a 2'"))
    else:
        for a in vsx:
            d = a["dist_arcsec"]
            px = d / PIXEL_TESS_ARCSEC
            if d <= 30:
                itens.append(("bloqueia", f"Já está no VSX: {a['nome']} a {d:.0f}\""))
            elif _mesmo_periodo(a.get("periodo"), f.get("periodo_d")):
                itens.append(("bloqueia", f"Variável do VSX a {d:.0f}\" com o mesmo período: "
                                          f"{_rotulo_vsx(a)}; o sinal pode ser dela"))
            elif d <= 60:
                itens.append(("atencao", f"Variável do VSX a {d:.0f}\" ({_rotulo_vsx(a)}): "
                                         "confira se não é a mesma estrela"))
            else:
                itens.append(("ok", f"Variável do VSX a {d:.0f}\" ({px:.1f} pixels do TESS) é "
                                    f"outra estrela: {_rotulo_vsx(a)}, "
                                    + ("período diferente" if a.get("periodo") else
                                       "sem período no VSX")))
    return itens


def _num(f: dict, chave: str):
    """Float da ficha, ou None quando a chave falta ou nao e numero (NaN incluso)."""
    v = f.get(chave)
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if v != v else v


def _setores_txt(f: dict) -> str:
    setores = f.get("setores_usados") or f.get("setores")
    if not setores:
        return ""
    nums = [x.strip() for x in str(setores).split(",") if x.strip()]
    return ", ".join(sorted(nums, key=lambda x: int(float(x)) if x.replace(".", "").isdigit() else 0))


def telas_wizard(f: dict, tipo_final: str | None, outros: list[str] | None,
                 achados: list[dict] | None, confirmado: bool,
                 descobridor: str = DESCOBRIDOR) -> list[dict]:
    """Uma tela do New Star Wizard por item, na ordem do site, com (rotulo, valor, copiar,
    ajuda) de cada campo. `copiar` falso e instrucao (marcar, deixar vazio, menu)."""
    def campo(rotulo, valor, copiar, ajuda=""):
        return (rotulo, valor, copiar, ajuda)

    ra, dec = _num(f, "gaia_ra"), _num(f, "gaia_dec")
    periodo, bjd = _num(f, "periodo_d"), _num(f, "epoca_bjd")
    v, amp, dur = _num(f, "v_estimada"), _num(f, "amplitude_mag_tess"), _num(f, "duracao_eclipse_pct")
    hjd = hjd_de_bjd(bjd, ra, dec) if bjd is not None and ra is not None and dec is not None else None
    setores = _setores_txt(f)
    telas = []

    telas.append({"tela": "Submission method", "campos": [
        campo("Método", "New Star Wizard", False), campo("Remember my choice", "desmarcado", False)]})

    telas.append({"tela": "Do you want to submit a new variable star based on your observations "
                          "only?", "campos": [
        campo("Resposta", "Não", False,
              "descoberta em dados de levantamento (TESS), não fotometria própria"),
        campo("Novice discovery", "desmarcado", False)]})

    posicao = []
    if ra is not None and dec is not None:
        graus, sexagesimal = coordenadas_j2000(ra, dec)
        posicao += [campo("J2000.0 Coordinates", graus, True),
                    campo("Sexagesimal (alternativa)", sexagesimal, True)]
    posicao.append(campo("Spot Check", "clique; o resultado esperado está na aba Conferir "
                                       "(VSX a 2')", False))
    telas.append({"tela": "What is the position of this new variable object?", "campos": posicao})

    nomes = list(outros or [])
    if not nomes and f.get("gaia_dr3") not in (None, ""):
        nomes = [f"Gaia DR3 {f['gaia_dr3']}"]
    nomes_campos = []
    if _num(f, "tic") is not None:
        nomes_campos.append(campo("Primary name", f"TIC {int(_num(f, 'tic'))}", True,
                                  "depois clique em Check name: deve vir 0 records"))
    if nomes:
        nomes_campos.append(campo("Other names", "\n".join(nomes), True))
    telas.append({"tela": "What names is this new variable object known by?",
                  "campos": nomes_campos})

    ambiguo = "," in str(f.get("tipo_sugerido") or "")
    provavel = str(f.get("tipo_provavel") or "")
    incerto = ambiguo and not (provavel and tipo_final == provavel and confirmado)
    tipo = [campo("Standardized type", f"escolha {tipo_final} no menu" if tipo_final
                  else "escolha o tipo na aba Conferir primeiro", False),
            campo("Customized type", "vazio", False),
            campo("Uncertain", "marcado" if incerto else "desmarcado", False)]
    telas.append({"tela": "What is the variability type for this variable object?",
                  "campos": tipo})

    telas.append({"tela": "What is the spectral type for this variable object?", "campos": [
        campo("Spectral type", "vazio", False),
        campo("Uncertain", "desmarcado", False,
              "sem espectro publicado; a Teff do Gaia não é tipo espectral"),
    ]})

    mags = []
    if v is not None:
        mags.append(campo("Maximum magnitude", f"{v:.2f}", True,
                          "V média estimada do Gaia G e BP-RP; limitador em branco"))
    mags += [campo("Max. mag. passband", "V", False),
             campo("Max. mag. Uncertain", "desmarcado", False)]
    if amp is not None:
        mags += [campo("Minimum magnitude", f"{amp:.3f}", True,
                       "é a amplitude; limitador em branco"),
                 campo("Min. mag. passband", "TESS (se não houver no menu, escreva TESS em "
                                             "Custom min. passband)", False)]
    mags += [campo("Minimum is amplitude", "marcado", False),
             campo("Min. mag. Uncertain", "desmarcado", False)]
    telas.append({"tela": "What is the magnitude range for variability of this object?",
                  "campos": mags})

    per = []
    if periodo is not None:
        per.append(campo("Period (days)", f"{periodo:.5f}", True))
    if hjd is not None:
        per.append(campo("Epoch (HJD)", f"{hjd:.4f}", True, "convertida do BJD_TDB do TESS"))
    elif bjd is not None:
        per.append(campo("Epoch (HJD)", f"{bjd:.4f}", True,
                         "BJD_TDB do TESS (ficha sem coordenada Gaia para converter)"))
    per.append(campo("Rise/eclipse duration (%)", f"{dur:.1f}" if dur is not None else "vazio",
                     dur is not None))
    per.append(campo("Rise/eclipse duration Uncertain",
                     "marcado" if amp is not None and amp < AMP_SOLO_MIN_MAG else "desmarcado",
                     False))
    per += [campo("Outburst year", "vazio", False),
            campo("Period Uncertain", "desmarcado", False),
            campo("Epoch Uncertain", "desmarcado", False)]
    telas.append({"tela": "What is the period of variability for this object?", "campos": per})

    desc1 = "TESS QLP light curve" + (f" (sectors {setores})" if setores else "")
    if periodo is not None:
        desc1 += f" folded at P = {periodo:.5f} d"
    if hjd is not None:
        desc1 += f", epoch HJD {hjd:.4f}"
    desc1 += "."
    if f.get("par_impar_dobrado"):
        fundos = sorted((float(x) for x in re.findall(
            r"(\d+(?:\.\d+)?)%", str(f.get("par_impar_prof") or ""))), reverse=True)
        if len(fundos) == 2:
            desc1 += (f" Primary and secondary eclipses have different depths "
                      f"({fundos[0]:.2f}% and {fundos[1]:.2f}%).")
    desc2 = ('Detection figure (TESS QLP): light curve, periodogram, phase plots at the '
             'detection period and at twice it, and the per-pixel signal map (11x11 TESScut, '
             '21"/px; red x = signal peak, green + = target).')
    pico = re.search(r"pico no alvo \((\d+(?:\.\d+)?) px\)", str(f.get("blend_motivo") or ""))
    if pico:
        desc2 += f" The signal peaks {pico.group(1)} px from the target."
    arquivos = []
    if _num(f, "tic") is not None:
        arquivos.append(campo("Arquivo 1", f"data/vsx/{int(_num(f, 'tic'))}_fase.png", True))
    arquivos.append(campo("Title", f"TESS phase plot, P = {periodo:.5f} d" if periodo is not None
                          else "TESS phase plot", True))
    arquivos.append(campo("Description", desc1, True))
    arquivos.append(campo("Mark as private", "desmarcado", False))
    if f.get("figura_triagem"):
        arquivos.append(campo("Arquivo 2", f["figura_triagem"], True))
    arquivos += [campo("Title", "TESS pixel map and detection figure", True),
                 campo("Description", desc2, True),
                 campo("Mark as private", "marcado", False, "rótulos em português"),
                 campo("Depois do upload", "Clique Next uma vez e espere o upload; não dá para "
                                           "desfazer", False)]
    telas.append({"tela": "Are there any supporting files to accompany this submission?",
                  "campos": arquivos})

    nome = descobridor or "seu nome, como no cadastro do VSX"
    telas.append({"tela": "Who was the original discoverer of this variable object?", "campos": [
        campo("Discoverer", nome, bool(descobridor))]})

    telas.append({"tela": "Is there a reference to literature for this object?", "campos": [
        campo("Reference name, bibcode e link", "vazios", False,
              "a estrela não foi publicada antes; a fonte dos dados (TESS QLP) vai nas Remarks")]})

    telas.append({"tela": "Are there any remarks to be added to this submission?", "campos": [
        campo("Remarks", comentario(f, tipo_final, achados), True,
              "público: aparece na ficha da estrela. É o único campo de texto do Wizard, "
              "não há outro para o moderador")]})

    telas.append({"tela": "Is all the information provided correct?", "campos": [
        campo("Rascunho", "não há: Submit envia de vez", False),
        campo("Confira", "Spectral type sem \":\" (Uncertain desmarcado), Rise duration com \":\" "
              "se o eclipse é raso, e os dois arquivos enviados (o privado não aparece na lista)",
              False),
        campo("Depois do envio", "marque Enviada nesta página", False)]})
    return telas


def comentario(f: dict, tipo_final: str | None, vsx: list[dict] | None) -> str:
    """Texto do campo Remarks do Wizard, em ingles: e o unico campo de texto e e publico
    (aparece na ficha da estrela), entao serve ao moderador e a quem usar os dados."""
    frases = []
    setores = f.get("setores_usados") or f.get("setores")
    if setores:
        nums = [x.strip() for x in str(setores).split(",") if x.strip()]
        setores = ", ".join(sorted(nums, key=lambda x: int(float(x)) if x.replace(".", "").isdigit() else 0))
    frases.append("Found with the Vagalume search pipeline (BLS and Lomb-Scargle on TESS QLP "
                  "light curves" + (f", sectors {setores}" if setores else "") + f"; {URL_PROJETO}).")
    if "periodo_d" in f:
        p = f"Period measured from all sectors: {f['periodo_d']:.5f}"
        if "periodo_erro_d" in f:
            p += f" +- {f['periodo_erro_d']:.6f}"
        frases.append(p + " d.")
    if f.get("par_impar_dobrado"):
        fundos = sorted((float(x) for x in re.findall(r"(\d+(?:\.\d+)?)%",
                                                       str(f.get("par_impar_prof") or ""))),
                        reverse=True)
        if len(fundos) == 2:
            frases.append(f"Odd/even eclipse depths differ ({fundos[0]:.2f}% vs {fundos[1]:.2f}%), "
                          "so the orbital period is 2x the BLS period.")
    if "epoca_bjd" in f:
        bjd = f["epoca_bjd"]
        if "gaia_ra" in f and "gaia_dec" in f:
            hjd = hjd_de_bjd(float(bjd), float(f["gaia_ra"]), float(f["gaia_dec"]))
            frases.append(f"Epoch of minimum: HJD {hjd:.4f} (converted from TESS BJD_TDB "
                          f"{bjd:.4f}).")
        else:
            frases.append(f"Epoch of minimum: BJD_TDB {bjd:.4f} (TESS times are BJD_TDB; "
                          "the difference from HJD is about a minute).")
    d = f.get("duracao_eclipse_pct")
    if isinstance(d, (int, float)) and d == d:
        frases.append(f"Eclipse duration: {d:.1f}% of the period.")
    if "amplitude_mag_tess" in f:
        frases.append(f"Amplitude in the TESS band: {f['amplitude_mag_tess']:.3f} mag.")
        if f["amplitude_mag_tess"] < AMP_SOLO_MIN_MAG:
            frases.append("The variation is below the precision of ground-based surveys such as "
                          "ASAS-SN and ZTF for this star, so only TESS data were used.")
    if vsx == []:
        frases.append("No known VSX variable within 2'.")
    elif vsx:
        perto = min(vsx, key=lambda a: a["dist_arcsec"])
        if perto["dist_arcsec"] > 30:
            faixa = _faixa_mag(perto.get("max"), perto.get("min"))
            desc = ", ".join(x for x in (perto.get("tipo"), f"P {perto['periodo']} d"
                                         if perto.get("periodo") else "") if x)
            frase = (f"The nearest VSX variable, {perto['nome']}"
                     + (f" ({desc}{faixa})" if desc or faixa else "")
                     + f", lies {perto['dist_arcsec']:.0f}\" away (about "
                     f"{perto['dist_arcsec'] / PIXEL_TESS_ARCSEC:.0f} TESS pixels)")
            if "pico no alvo" in str(f.get("blend_motivo") or ""):
                frase += "; the pixel map peaks on the target"
            frases.append(frase + ".")
    if str(f.get("vizier_variaveis") or "").lower().startswith("nenhum"):
        if MARCA_PODE_SUBMETER in str(f.get("avisos") or ""):
            frases.append("No entry within 30\" in the 25 main variable-star catalogs in VizieR "
                          "(the full VizieR search was unavailable during the CDS outage).")
        else:
            frases.append("No variable-star catalog in VizieR has an entry within 30\".")
    if f.get("suspeito_blend") and f.get("blend_veredito") in (None, "ok"):
        frases.append('A Gaia neighbour (less than 4 mag fainter) lies within 42"; the pixel map peaks on the target.')
    if "gaia_dr3" in f:
        frases.append("Position and identifiers from Gaia DR3.")
    return " ".join(frases)
