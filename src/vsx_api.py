"""Consulta a API do VSX (AAVSO): usada pela Fase 5 e pela pagina Fichas. Sem Streamlit."""

import math

import requests

URL_API = "https://vsx.aavso.org/index.php"
URL_DETALHE = "https://vsx.aavso.org/index.php?view=detail.top&oid={oid}"


def _distancia_arcsec(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    r1, d1, r2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    c = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(r1 - r2)
    return math.degrees(math.acos(max(-1.0, min(1.0, c)))) * 3600


def consultar_vsx(ra: float, dec: float, raio_arcsec: float = 60,
                 prazo_s: float = 30) -> list[dict]:
    """Variaveis do VSX no raio, da mais proxima para a mais longe. Erro de rede levanta."""
    r = requests.get(URL_API, params=dict(view="api.list", ra=ra, dec=dec,
                                          radius=raio_arcsec / 3600, format="json"), timeout=prazo_s)
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
