import threading
import time


def com_prazo(fn, segundos: float):
    """fn() com prazo de relogio; TimeoutError se passar dele.

    Para chamadas que ignoram o timeout do astroquery (o download do TESScut pelo
    lightkurve ficou 15 min parado numa conexao morta). Roda em thread daemon: a que
    travou fica para tras sem segurar o fim do processo.
    """
    saida = {}

    def alvo():
        try:
            saida["valor"] = fn()
        except BaseException as e:  # repassa qualquer erro para quem chamou
            saida["erro"] = e

    t = threading.Thread(target=alvo, daemon=True)
    t.start()
    t.join(segundos)
    if t.is_alive():
        raise TimeoutError(f"sem resposta em {segundos:.0f} s")
    if "erro" in saida:
        raise saida["erro"]
    return saida.get("valor")


def descrever_erro(e: BaseException) -> str:
    """Motivo curto de uma falha de rede, para a mensagem de retry."""
    import requests
    resposta = getattr(e, "response", None)
    codigo = getattr(resposta, "status_code", None)
    if isinstance(e, requests.exceptions.HTTPError) and codigo and codigo >= 500:
        return f"erro no servidor ({codigo})"
    if isinstance(e, (TimeoutError, requests.exceptions.Timeout)) or "timeout" in type(e).__name__.lower():
        return "tempo esgotado"
    if isinstance(e, (ConnectionError, requests.exceptions.ConnectionError)):
        return "sem conexão"
    return type(e).__name__


def retry(fn, servico: str, retries: int = 4, delay: float = 5.0):
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            if attempt < retries - 1:
                # espera crescente (5, 10, 20 s): queda do MAST costuma durar mais que 5 s
                espera = delay * 2 ** attempt
                print(f"  {servico} não respondeu (tentativa {attempt+1} de {retries}: "
                      f"{descrever_erro(e)}). Nova tentativa em {espera:.0f} s.", flush=True)
                time.sleep(espera)
            else:
                raise
    return None


def usar_espelho_simbad(prazo_s: float = 8.0):
    """Se o SIMBAD de Estrasburgo nao responde, usa o espelho de Harvard.

    So o SIMBAD: o VizieR de Harvard nao tem o Gaia DR3 e devolve 0 linhas sem erro,
    o que apagaria os blends da Fase 6.
    """
    import socket
    from astroquery.simbad import conf
    try:
        socket.create_connection((conf.server, 443), timeout=prazo_s).close()
    except OSError:
        conf.server = "simbad.harvard.edu"
        print("  SIMBAD do CDS fora do ar: usando o espelho de Harvard.")


usar_espelho_simbad()


def _cds_responde(url: str, prazo_s: float = 15.0) -> bool:
    import requests
    try:
        return requests.get(url, timeout=prazo_s).status_code == 200
    except requests.RequestException:
        return False


def usar_espelhos_cds():
    """Se o CDS de Estrasburgo nao entrega consultas, aponta SIMBAD e VizieR para espelhos.

    O VizieR de Harvard nao tem o Gaia DR3 e devolve 0 linhas sem erro, o que apagaria os
    blends da Fase 6. So o espelho do IDIA (Africa do Sul) e usado, e antes confere que ele
    devolve fontes do Gaia DR3 numa regiao conhecida; se nao devolver, nada muda.
    """
    from astroquery.simbad import conf as simbad_conf
    from astroquery.vizier import VizierClass, conf as vizier_conf

    if not _cds_responde(f"https://{simbad_conf.server}/simbad/sim-id?Ident=Vega&output.format=ASCII"):
        simbad_conf.server = "simbad.harvard.edu"
        print("  SIMBAD do CDS fora do ar: usando o espelho de Harvard.")

    if _cds_responde(f"https://{vizier_conf.server}/viz-bin/votable?-source=I/239/hip_main&-out.max=1"):
        return
    espelho = "vizier.idia.ac.za"
    try:
        from astropy import units as u
        from astropy.coordinates import SkyCoord
        r = VizierClass(columns=["Source"], row_limit=1, timeout=60, vizier_server=espelho).query_region(
            SkyCoord(300 * u.deg, 35 * u.deg), radius=3 * u.arcmin, catalog="I/355/gaiadr3")
        if not len(r) or not len(r[0]):
            raise ValueError("espelho sem Gaia DR3")
    except Exception as e:
        print(f"  VizieR do CDS fora do ar e o espelho {espelho} nao serve ({type(e).__name__}).")
        return
    # o astroquery le conf.server uma vez, no default do __init__
    VizierClass.__init__.__kwdefaults__["vizier_server"] = espelho
    print(f"  VizieR do CDS fora do ar: usando o espelho {espelho}.")


usar_espelhos_cds()
