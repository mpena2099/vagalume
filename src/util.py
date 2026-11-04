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


def retry(fn, servico: str, retries: int = 4, delay: float = 5.0):
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            if attempt < retries - 1:
                print(f"  {servico} retry {attempt+1}/{retries}: {e}")
                # espera crescente (5, 10, 20 s): queda do MAST costuma durar mais que 5 s
                time.sleep(delay * 2 ** attempt)
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
