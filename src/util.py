import time


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
