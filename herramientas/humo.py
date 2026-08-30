#!/usr/bin/env python3
"""
Prueba de humo de la interfaz: abre todas las pantallas en un navegador sin ventana y
avisa si alguna falla.

Las pruebas de `pruebas/` cubren las reglas del pliego; esto cubre lo otro: que la
interfaz no se rompa. Una vista que tira un error o se queda cargando no la agarra
ningún test de Python, y en una demostración se ve enseguida.

    python3 herramientas/humo.py                    # contra el servidor en 8713
    python3 herramientas/humo.py --url http://127.0.0.1:9000
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

RUTAS = [
    "panel", "ingesta", "buscar", "buscar/maestranza", "contratos", "personas",
    "persona/1", "superposiciones", "cola", "identidad", "interpretacion",
    "consultas", "consultas/01_superposicion", "documento/1", "como-funciona",
]

CANDIDATOS = [
    os.environ.get("UFIL_CHROMIUM", ""),
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "chromium", "chromium-browser", "google-chrome",
]


def navegador() -> str | None:
    for c in CANDIDATOS:
        if c and (os.path.isfile(c) or shutil.which(c)):
            return c if os.path.isfile(c) else shutil.which(c)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default="http://127.0.0.1:8713")
    ap.add_argument("--espera", type=int, default=6000, help="ms por pantalla")
    a = ap.parse_args()

    ch = navegador()
    if not ch:
        print("No encontré un navegador sin ventana. Definí UFIL_CHROMIUM con la ruta.")
        return 2

    print(f"{'pantalla':<34}estado")
    print("-" * 62)
    fallas = 0
    for r in RUTAS:
        try:
            dom = subprocess.run(
                [ch, "--headless=new", "--disable-gpu", "--no-sandbox",
                 f"--virtual-time-budget={a.espera}", "--dump-dom", f"{a.url}/#/{r}"],
                capture_output=True, text=True, timeout=90).stdout
        except subprocess.TimeoutExpired:
            print(f"{r:<34}SE COLGÓ"); fallas += 1; continue

        problemas = []
        if 'class="sello alerta">Error' in dom:
            problemas.append("la vista tiró un error")
        if 'class="esqueleto"' in dom:
            problemas.append("se quedó cargando")
        for palabra in ("undefined", "NaN", "[object Object]"):
            if palabra in dom:
                problemas.append(f"muestra «{palabra}»")
        if problemas:
            fallas += 1
            print(f"{r:<34}✗ " + " · ".join(problemas))
        else:
            print(f"{r:<34}ok")

    print("-" * 62)
    print(f"{len(RUTAS) - fallas}/{len(RUTAS)} pantallas sin problemas")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
