"""
Barrido visual de todas las pantallas, en un Chrome real, contra una base dada.

    python herramientas/qa/barrer.py --base <ufil.sqlite> --salida <carpeta>
           [--puerto 8812] [--cdp 9222] [--anchos 1920x1080,1366x768] [--solo panel,precios]
           [--modo barrido|flujo|ambos]

Levanta el servidor de ESTE árbol de trabajo sobre la base indicada, abre un Chrome
sin ventana con su propio perfil, corre `barrido.cjs` en cada resolución y cierra
todo al terminar. Deja, por resolución, una captura por pantalla y un
`informe-<ancho>.json` con el alto real, los monoespaciados, las mayúsculas, las
marcas de ausencia, los controles y los errores de consola de cada una.

Los números de cualquier informe de QA salen de ese JSON, no de una estimación.

La base se usa como está: si el código trae un esquema más nuevo, el servidor la
migra. Por eso se pasa SIEMPRE una copia de trabajo, nunca el original del legajo.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
AQUI = Path(__file__).resolve().parent
CHROMES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "google-chrome", "chromium",
]


def esperar(url: str, segundos: float = 90, proceso=None) -> None:
    fin = time.time() + segundos
    while time.time() < fin:
        if proceso is not None and proceso.poll() is not None:
            raise SystemExit(f"el proceso terminó antes de responder en {url}; "
                             "mirá servidor.log en la carpeta de salida")
        try:
            urllib.request.urlopen(url, timeout=2).read()
            return
        except Exception:
            time.sleep(0.5)
    raise SystemExit(f"no respondió a tiempo: {url}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True, help="copia de trabajo de ufil.sqlite")
    p.add_argument("--salida", required=True)
    p.add_argument("--puerto", type=int, default=8812)
    p.add_argument("--cdp", type=int, default=9222)
    p.add_argument("--anchos", default="1920x1080,1366x768")
    p.add_argument("--solo", default="", help="rutas separadas por coma")
    p.add_argument("--tema", default="", help="claro u oscuro; vacío = el de fábrica")
    p.add_argument("--completa", action="store_true", help="capturas de la página entera")
    p.add_argument("--extra", default="", help="nombre=#/ruta,... rutas puntuales de más")
    p.add_argument("--modo", default="barrido", choices=["barrido", "flujo", "ambos"],
                   help="barrido: todas las pantallas; flujo: el recorrido de una persona (flujo.cjs)")
    a = p.parse_args()

    base = Path(a.base).resolve()
    if "produccion-original" in str(base):
        raise SystemExit("eso es el original del legajo: pasá una copia de trabajo")
    salida = Path(a.salida).resolve()
    salida.mkdir(parents=True, exist_ok=True)

    entorno = dict(os.environ, PYTHONIOENCODING="utf-8")
    tess = r"C:\Program Files\Tesseract-OCR"
    if Path(tess).exists():
        entorno["PATH"] = tess + os.pathsep + entorno.get("PATH", "")
    servidor = subprocess.Popen(
        [sys.executable, "-m", "ufil.cli", "--base", str(base), "servir",
         "--puerto", str(a.puerto)],
        cwd=RAIZ, env=entorno, stdout=subprocess.DEVNULL,
        stderr=open(salida / "servidor.log", "w", encoding="utf-8"))
    chrome_exe = next((c for c in CHROMES if shutil.which(c) or Path(c).exists()), None)
    if not chrome_exe:
        servidor.terminate()
        raise SystemExit("no encontré Chrome")
    perfil = tempfile.mkdtemp(prefix="ufil-qa-chrome-")
    chrome = subprocess.Popen(
        [chrome_exe, "--headless=new", f"--remote-debugging-port={a.cdp}",
         f"--user-data-dir={perfil}", "--no-first-run", "--disable-extensions",
         "--hide-scrollbars", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        origen = f"http://127.0.0.1:{a.puerto}"
        esperar(origen + "/", proceso=servidor)
        esperar(f"http://127.0.0.1:{a.cdp}/json/version")
        codigo = 0
        for par in a.anchos.split(","):
            ancho, alto = par.lower().split("x")
            env = dict(os.environ, ORIGEN=origen, SALIDA=str(salida), ANCHO=ancho,
                       ALTO=alto, CDP_PORT=str(a.cdp), SOLO=a.solo, TEMA=a.tema, EXTRA=a.extra, COMPLETA='1' if a.completa else '')
            print(f"== {ancho}x{alto}", flush=True)
            guiones = {"barrido": ["barrido.cjs"], "flujo": ["flujo.cjs"],
                       "ambos": ["barrido.cjs", "flujo.cjs"]}[a.modo]
            for guion in guiones:
                r = subprocess.run(["node", str(AQUI / guion)], env=env)
                codigo = codigo or r.returncode
        return codigo
    finally:
        chrome.terminate()
        servidor.terminate()
        try:
            chrome.wait(10)
        except Exception:
            chrome.kill()
        shutil.rmtree(perfil, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
