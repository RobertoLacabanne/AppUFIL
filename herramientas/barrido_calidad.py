#!/usr/bin/env python3
"""
Mide hasta qué calidad de escaneo el sistema sigue sirviendo.

La pregunta que contesta es operativa, no académica: cuando la fiscalía le dice a la
Legislatura —o al escáner de la oficina— "mandámelos así", ¿así cómo? Hay dos perillas
que cualquiera puede tocar en un escáner y que deciden casi todo el resultado: la
RESOLUCIÓN (DPI) y el MODO DE COLOR (escala de grises contra blanco y negro puro).

Genera el MISMO corpus —la misma población, los mismos contratos, el mismo temblor de
papel— escaneado de distintas maneras, lo procesa entero en bases separadas y mide cada
una contra la misma transcripción de referencia. La única variable que cambia entre
corridas es el escaneo, así que la diferencia de exactitud es atribuible a él.

Uso:
    python herramientas/barrido_calidad.py --cantidad 30
    python herramientas/barrido_calidad.py --cantidad 30 --dpis 100,150,200,300 --salida informe.md

Tarda: aproximadamente (cantidad × fojas × 0,3 s) por variante, más el OCR de las
variantes de alta resolución, que es más lento porque hay más píxeles.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sqlite3
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))


def _correr(cmd: list[str], entorno: dict) -> None:
    r = subprocess.run(cmd, env=entorno, cwd=RAIZ, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"falló {' '.join(cmd)}\n{r.stdout}\n{r.stderr}")


def variante(nombre: str, dpi: int, binario: bool, calidad: str | None,
             cantidad: int, semilla: int, trabajo: Path,
             dpi_render: int | None = None) -> dict:
    """
    Genera, procesa y mide una sola variante. Devuelve sus números.

    `dpi` es a cuánto llegó el escaneo: no lo decidimos nosotros, lo decide quien pasa
    el papel por la máquina. `dpi_render` es a cuánto lo rasteriza la app antes de
    leerlo: eso SÍ lo decidimos nosotros, y por eso vale medirlo aparte.
    """
    corpus = trabajo / f"corpus-{nombre}"
    base = trabajo / f"{nombre}.sqlite"
    for p in (corpus,):
        shutil.rmtree(p, ignore_errors=True)
    for p in (base, Path(str(base) + "-wal"), Path(str(base) + "-shm")):
        p.unlink(missing_ok=True)

    gen = [sys.executable, "herramientas/generar_fixtures.py",
           "--destino", str(corpus), "--cantidad", str(cantidad), "--semilla", str(semilla),
           "--dpi", str(dpi)]
    if binario:
        gen.append("--binario")
    if calidad:
        gen += ["--calidad", calidad]

    entorno = dict(os.environ)
    entorno["UFIL_BASE"] = str(base)
    entorno["UFIL_DATOS"] = str(trabajo / f"datos-{nombre}")
    if dpi_render:
        entorno["UFIL_DPI_RENDER"] = str(dpi_render)

    _correr(gen, entorno)
    t0 = time.monotonic()
    _correr([sys.executable, "-m", "ufil.cli", "ingerir", str(corpus), "--lote", nombre], entorno)
    _correr([sys.executable, "-m", "ufil.cli", "leer"], entorno)
    _correr([sys.executable, "-m", "ufil.cli", "extraer"], entorno)
    segundos = time.monotonic() - t0

    from ufil.evaluacion import evaluar
    cx = sqlite3.connect(base)
    cx.row_factory = sqlite3.Row
    res = evaluar(cx, corpus / "referencia.csv")

    paginas = cx.execute("SELECT COUNT(*) FROM pagina").fetchone()[0]
    peso = sum(f.stat().st_size for f in corpus.glob("*.pdf"))
    cx.close()

    campos = res["por_campo"]
    con_ref = sum(c["con_referencia"] for c in campos.values())
    aciertos = sum(c["acierto"] for c in campos.values())
    return {
        "variante": nombre, "dpi": dpi, "binario": binario, "calidad": calidad,
        "dpi_render": dpi_render or 200,
        "exactitud_global": round(aciertos / con_ref, 4) if con_ref else 0.0,
        "silenciosos": sum(c["error_silencioso"] for c in campos.values()),
        "marcados": sum(c["error_marcado"] for c in campos.values()),
        "omisiones": sum(c["omision"] for c in campos.values()),
        "en_conflicto": sum(c["en_conflicto"] for c in campos.values()),
        "aprueba": res["aprueba"],
        "por_campo": {k: v["exactitud"] for k, v in campos.items()},
        "paginas": paginas,
        "segundos": round(segundos, 1),
        "seg_por_pagina": round(segundos / paginas, 2) if paginas else None,
        "mb_por_contrato": round(peso / cantidad / 1_000_000, 2),
    }


def informe(filas: list[dict]) -> str:
    L = ["BARRIDO DE CALIDAD DE ESCANEO", "=" * 96, ""]
    L.append(f"{'escaneo':<22}{'exact.':>8}{'ERR.SIL':>9}{'err.mar':>9}{'omis':>7}"
             f"{'confl':>7}{'s/pág':>8}{'MB/contr':>10}   veredicto")
    L.append("-" * 96)
    for f in filas:
        v = "sirve" if f["aprueba"] else "NO alcanza"
        L.append(f"{f['variante']:<22}{f['exactitud_global']*100:>7.1f}%"
                 f"{f['silenciosos']:>9}{f['marcados']:>9}{f['omisiones']:>7}"
                 f"{f['en_conflicto']:>7}{(f['seg_por_pagina'] or 0):>8.2f}"
                 f"{f['mb_por_contrato']:>10.2f}   {v}")
    L.append("-" * 96)
    L.append("")
    campos = list(filas[0]["por_campo"]) if filas else []
    L.append("exactitud por campo")
    L.append(f"{'escaneo':<22}" + "".join(f"{c:>14}" for c in campos))
    for f in filas:
        L.append(f"{f['variante']:<22}" +
                 "".join(f"{f['por_campo'][c]*100:>13.1f}%" for c in campos))
    L.append("")
    L.append("Un escaneo 'sirve' si alcanza los umbrales del §12 en los cinco campos")
    L.append("críticos Y no produce errores silenciosos por encima de lo tolerado.")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cantidad", type=int, default=30)
    ap.add_argument("--semilla", type=int, default=1974)
    ap.add_argument("--dpis", default="100,150,200,300")
    ap.add_argument("--calidad", default="regular",
                    help="calidad de papel fija para todas las variantes, "
                         "así la única diferencia es el escaneo")
    ap.add_argument("--render", default=None,
                    help="además, mide un original de 300 DPI leído a estas "
                         "resoluciones (ej: 150,200,300,400)")
    ap.add_argument("--trabajo", default=None, help="carpeta de trabajo (se borra al empezar)")
    ap.add_argument("--salida", default=None, help="además del informe, guarda el JSON acá")
    a = ap.parse_args()

    trabajo = Path(a.trabajo) if a.trabajo else RAIZ / "datos" / "barrido"
    trabajo.mkdir(parents=True, exist_ok=True)

    # Eje 1: la resolución con la que LLEGA el papel. No la decidimos nosotros.
    plan = [(f"{d} DPI grises", d, False, None) for d in
            (int(x) for x in a.dpis.split(","))]
    # El modo texto se mide a la resolución recomendada de la industria: si rompe ahí,
    # rompe en todos lados, y es el ajuste por defecto de media oficina.
    plan.append(("300 DPI byn (texto)", 300, True, None))
    # Eje 2: a cuánto rasteriza la app. Eso SÍ lo decidimos nosotros, así que si el
    # original trae más detalle del que estamos leyendo, es una pérdida evitable.
    if a.render:
        for r in (int(x) for x in a.render.split(",")):
            plan.append((f"300 DPI, leído a {r}", 300, False, r))

    filas = []
    for nombre, dpi, binario, render in plan:
        print(f"── {nombre} ", end="", flush=True)
        clave = "".join(c if c.isalnum() else "_" for c in nombre)
        f = variante(clave, dpi, binario, a.calidad, a.cantidad, a.semilla, trabajo,
                     dpi_render=render)
        f["variante"] = nombre
        filas.append(f)
        print(f"→ {f['exactitud_global']*100:.1f}% · {f['silenciosos']} silenciosos "
              f"· {f['segundos']}s")

    texto = informe(filas)
    print("\n" + texto)
    if a.salida:
        Path(a.salida).write_text(json.dumps(filas, indent=2, ensure_ascii=False),
                                  encoding="utf-8")
        print(f"\nJSON en {a.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
