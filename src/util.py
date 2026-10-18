import time


def retry(fn, servico: str, retries: int = 3, delay: float = 5.0):
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            if attempt < retries - 1:
                print(f"  {servico} retry {attempt+1}/{retries}: {e}")
                time.sleep(delay)
            else:
                raise
    return None
