"""Rodar `pipeline.py --proximo` ou a Fase 8 pelo app, em segundo plano, e ler o progresso.

Sem Streamlit (testavel offline). O processo roda em sessao propria: fechar a pagina ou
parar o Streamlit nao o interrompe. Cada trabalho tem o seu log (data/pipeline.log e
data/vsx/ficha.log); a pagina relê o log a cada poucos segundos.
"""

import os
import re
import subprocess
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "pipeline.log"
COMANDO = "python -u pipeline.py --proximo"
FIM = "registrado em campos_feitos"
CANCELADA = "Busca cancelada pelo app."

FICHA_LOG = ROOT / "data" / "vsx" / "ficha.log"
FICHA_COMANDO = "python -u src/ficha_vsx.py"
CANCELADA_FICHA = "Fichas canceladas pelo app."


def _processos(script: str = "pipeline.py") -> list[int]:
    """PIDs do script rodando a partir deste projeto (do app ou do terminal).

    psutil em vez de /proc: funciona tambem no macOS e no Windows.
    """
    achados = []
    for proc in psutil.process_iter(["cmdline", "cwd"]):
        try:
            cmd = proc.info["cmdline"] or []
            cwd = proc.info["cwd"]
            if any(p.endswith(script) for p in cmd) and cwd and Path(cwd) == ROOT:
                achados.append(proc.pid)
        except (psutil.Error, OSError, ValueError):
            continue
    return achados


def rodando() -> bool:
    return bool(_processos("pipeline.py"))


def rodando_ficha() -> bool:
    return bool(_processos("src/ficha_vsx.py"))


def _sessao_propria() -> dict:
    """Processo desligado do Streamlit: parar o app nao interrompe a busca."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _iniciar(script: str, argumentos: list[str], log: Path) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "w", encoding="utf-8") as saida:
        subprocess.Popen([sys.executable, "-u", script, *argumentos], cwd=ROOT,
                         stdout=saida, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         env={**os.environ, "PYTHONIOENCODING": "utf-8"}, **_sessao_propria())


def iniciar() -> None:
    _iniciar("pipeline.py", ["--proximo"], LOG)


def iniciar_ficha(duvidas: bool = False) -> None:
    _iniciar("src/ficha_vsx.py", ["--duvidas"] if duvidas else [], FICHA_LOG)


def _cancelar(script: str, log: Path, mensagem: str) -> None:
    for pid in _processos(script):
        try:
            # leva junto os downloads paralelos que o script abriu
            proc = psutil.Process(pid)
            for filho in proc.children(recursive=True):
                filho.terminate()
            proc.terminate()
        except psutil.Error:
            continue
    with open(log, "a", encoding="utf-8") as saida:
        saida.write(f"\n{mensagem}\n")


def cancelar() -> None:
    """Encerra a busca e o que ela abriu. O campo nao entra em campos_feitos: na proxima
    busca ele e refeito do inicio, e as decisoes da revisao nao sao tocadas."""
    _cancelar("pipeline.py", LOG, CANCELADA)


def cancelar_ficha() -> None:
    """Encerra a Fase 8. As fichas ja gravadas ficam: rodar de novo retoma."""
    _cancelar("src/ficha_vsx.py", FICHA_LOG, CANCELADA_FICHA)


def ler_log(log: Path = LOG) -> str:
    try:
        return log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def ler_log_ficha() -> str:
    return ler_log(FICHA_LOG)


def minutos_desde_inicio(log: Path = LOG) -> float | None:
    try:
        return (time.time() - log.stat().st_ctime) / 60
    except OSError:
        return None


def estado(log: str) -> dict:
    """Fase atual, progresso (i de N), campo, erro e fim, tirados do texto do log."""
    linhas = [x.strip() for x in log.splitlines() if x.strip()]
    e = {"fase": None, "progresso": None, "campo": None, "erro": None,
         "terminou": any(FIM in x for x in linhas), "fim_da_grade": False,
         "cancelada": any(x.startswith(CANCELADA) for x in linhas)}
    for x in linhas:
        if x.startswith("Executando:"):
            e["fase"], e["progresso"] = x.split(":", 1)[1].strip(), None
        elif m := re.match(r"(\d+)/(\d+)\b", x):
            e["progresso"] = (int(m.group(1)), int(m.group(2)))
        elif x.startswith("Proximo campo:"):
            e["campo"] = x.split(":", 1)[1].strip()
        elif x.startswith("ERRO em"):
            e["erro"] = x
        elif x.startswith("A grade de campos acabou"):
            e["fim_da_grade"] = True
    return e


def estado_ficha(log: str) -> dict:
    """Progresso da Fase 8: estrela atual, ultima etapa, erro e resumo final."""
    e = {"progresso": None, "tic": None, "etapa": None, "erro": None, "fim": None,
         "terminou": False, "cancelada": False}
    erro = False
    for bruta in log.splitlines():
        x = bruta.strip()
        if not x:
            continue
        if x.startswith(CANCELADA_FICHA):
            e["cancelada"] = True
        if m := re.match(r"\[(\d+)/(\d+)\]\s+TIC\s+(\d+)", x):
            e["progresso"], e["tic"], e["etapa"] = (
                (int(m.group(1)), int(m.group(2))), int(m.group(3)), None)
            continue
        if "Traceback" in x:
            erro = True
        if erro:
            e["erro"] = x
        # etapa e a linha indentada do script (busca, medida, figura)
        if bruta[:1].isspace() and e["progresso"]:
            e["etapa"] = x
        if (re.search(r"\b\d+ (mantida|mantidas|completada|completadas|nova|novas)\b", x)
                and "anteriores" not in x):
            e["fim"] = x
    e["terminou"] = bool(e["fim"])
    return e


# consulta de verdade: com o CDS fora, a pagina inicial responde 200 e as consultas 404
SONDA_VIZIER = "https://vizier.cds.unistra.fr/viz-bin/votable?-source=I/239/hip_main&-out.max=1"


def vizier_no_ar(prazo_s: float = 20.0) -> bool:
    """O VizieR de Estrasburgo responde consultas? Sem ele, a busca no VizieR inteiro da
    Fase 8 falha: o espelho do IDIA corta essa busca (erro 502) depois de ~2 min."""
    import requests
    try:
        r = requests.get(SONDA_VIZIER, timeout=prazo_s)
        return r.status_code == 200 and "<TABLE" in r.text
    except requests.RequestException:
        return False

