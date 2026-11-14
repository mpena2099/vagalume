"""Consulta ao VSX, pendencias e comentario da submissao: sem Streamlit, testavel offline."""

import math

import requests

from config import MARCA_PODE_SUBMETER

URL_API = "https://vsx.aavso.org/index.php"
URL_DETALHE = "https://vsx.aavso.org/index.php?view=detail.top&oid={oid}"

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


def _distancia_arcsec(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    r1, d1, r2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    c = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(r1 - r2)
    return math.degrees(math.acos(max(-1.0, min(1.0, c)))) * 3600


def consultar_vsx(ra: float, dec: float, raio_arcsec: float = 60) -> list[dict]:
    """Variaveis do VSX no raio, da mais proxima para a mais longe. Erro de rede levanta."""
    r = requests.get(URL_API, params=dict(view="api.list", ra=ra, dec=dec,
                                          radius=raio_arcsec / 3600, format="json"), timeout=30)
    r.raise_for_status()
    objetos = r.json().get("VSXObjects") or {}
    itens = objetos.get("VSXObject", []) if isinstance(objetos, dict) else objetos
    if isinstance(itens, dict):
        itens = [itens]
    achados = []
    for o in itens:
        achados.append({
            "nome": o.get("Name", ""), "tipo": o.get("VariabilityType", ""),
            "periodo": o.get("Period", "") or "", "max": o.get("MaxMag", ""),
            "min": o.get("MinMag", ""), "oid": o.get("OID", ""),
            "dist_arcsec": _distancia_arcsec(ra, dec, float(o["RA2000"]),
                                             float(o["Declination2000"])),
            "url": URL_DETALHE.format(oid=o.get("OID", "")),
        })
    return sorted(achados, key=lambda a: a["dist_arcsec"])


def pendencias(f: dict, tipo_final: str | None, vsx: list[dict] | None) -> list[tuple[str, str]]:
    """(nivel, texto) com nivel em ok, atencao ou bloqueia."""
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
                                 "se os eclipses dos setores caem no mesmo lugar"))
    else:
        itens.append(("ok", "Período consistente entre setores"))
    if f.get("suspeito_blend"):
        itens.append(("atencao", "Vizinha Gaia brilhante perto: confira no mapa por pixel "
                                 "(figura da triagem) se o pico está no alvo e mencione a "
                                 "vizinha no comentário"))
    else:
        itens.append(("ok", "Sem vizinha Gaia brilhante suspeita"))

    if not tipo_final and "," in str(f.get("tipo_sugerido") or ""):
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
    if f.get("suspeito_blend"):
        frases.append('A brighter Gaia neighbour lies within 42"; the pixel map peaks on the target.')
    return " ".join(frases)
