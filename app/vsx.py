"""Pendencias e comentario da submissao: sem Streamlit, testavel offline."""

import re

from config import MARCA_PODE_SUBMETER
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
        itens.append(("ok", "Nenhuma variável do VSX a 1'"))
    else:
        for a in vsx:
            d = a["dist_arcsec"]
            if d <= 30:
                itens.append(("bloqueia", f"Já está no VSX: {a['nome']} a {d:.0f}\""))
            elif d <= 60:
                itens.append(("atencao", f"Variável do VSX a {d:.0f}\" ({a['nome']}): "
                                         "confira se não é a mesma estrela"))
    return itens


def comentario(f: dict, tipo_final: str | None, vsx: list[dict] | None) -> str:
    """Comentario ao moderador, em ingles, com os numeros da ficha."""
    frases = []
    setores = f.get("setores_usados") or f.get("setores")
    frases.append("Found in TESS QLP light curves" + (f" (sectors {setores})." if setores else "."))
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
        frases.append(f"Epoch of minimum: BJD {f['epoca_bjd']:.4f}.")
    if "amplitude_mag_tess" in f:
        frases.append(f"Amplitude in the TESS band: {f['amplitude_mag_tess']:.3f} mag.")
    if tipo_final:
        frases.append(f"Type: {tipo_final}.")
    if vsx == []:
        frases.append("No known VSX variable within 1'.")
    if str(f.get("vizier_variaveis") or "").lower().startswith("nenhum"):
        frases.append("No variable-star catalog in VizieR has an entry within 30\".")
    if "gaia_dr3" in f:
        frases.append(f"Gaia DR3 {f['gaia_dr3']}.")
    if f.get("suspeito_blend") and f.get("blend_veredito") in (None, "ok"):
        frases.append('A brighter Gaia neighbour lies within 42"; the pixel map peaks on the target.')
    return " ".join(frases)
