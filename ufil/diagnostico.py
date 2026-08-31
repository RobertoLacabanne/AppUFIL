"""
Diagnóstico del entorno: ¿está todo lo que hace falta para trabajar?

Por qué existe. El sistema se instala en una máquina sin internet, y el momento de
descubrir que falta el paquete de castellano de Tesseract no puede ser la página 300 de
un lote de dos mil. Esto se corre el primer día, antes de cargar nada, y dice
exactamente qué falta y cómo se arregla.

Cada chequeo devuelve uno de tres estados:

  ok        anda
  aviso     anda, pero hay algo que conviene mirar (poco disco, un solo núcleo)
  falla     NO se puede trabajar así, y se dice qué instalar

Ningún chequeo sale a la red: son todas comprobaciones locales.
"""
from __future__ import annotations

import os
import shutil
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path

from . import config
from .castellano import miles, plural

# Debajo de esto un lote mediano no entra: los derivados (PNG de página) pesan más que
# los PDF originales. Medido: alrededor de 1,2 MB de derivados por página a 200 DPI.
DISCO_MINIMO_GB = 5
DISCO_COMODO_GB = 20


def _r(nombre, estado, detalle, arreglo=None):
    return {"nombre": nombre, "estado": estado, "detalle": detalle, "arreglo": arreglo}


def _python():
    v = sys.version_info
    txt = f"Python {v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) < (3, 11):
        return _r("Python", "falla", f"{txt} — hace falta 3.11 o posterior",
                  "instalar python3.11")
    return _r("Python", "ok", txt)


def _libreria(modulo, nombre_paquete):
    try:
        m = __import__(modulo)
    except ImportError:
        return _r(nombre_paquete, "falla", "no está instalada",
                  f"pip install --no-index --find-links ruedas/ {nombre_paquete}")
    ver = getattr(m, "__version__", None) or getattr(m, "version", None) or "?"
    return _r(nombre_paquete, "ok", f"versión {ver}")


def _tesseract():
    exe = shutil.which("tesseract")
    if not exe:
        return [_r("Tesseract", "falla", "no está en el PATH",
                   "instalar el paquete tesseract-ocr")]
    try:
        v = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20)
        version = v.stdout.splitlines()[0].strip() if v.stdout else "desconocida"
    except Exception as e:                                   # noqa: BLE001
        return [_r("Tesseract", "falla", f"no responde: {e}", "reinstalar tesseract-ocr")]

    salidas = [_r("Tesseract", "ok", f"{version} en {exe}")]

    try:
        li = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, timeout=20)
        idiomas = {l.strip() for l in (li.stdout + li.stderr).splitlines()[1:] if l.strip()}
    except Exception:                                        # noqa: BLE001
        idiomas = set()

    idioma = config.OCR_IDIOMA
    if idioma in idiomas:
        salidas.append(_r(f"Idioma «{idioma}»", "ok", "instalado"))
    else:
        salidas.append(_r(f"Idioma «{idioma}»", "falla",
                          f"no está. Idiomas disponibles: {', '.join(sorted(idiomas)) or 'ninguno'}",
                          f"instalar el paquete tesseract-ocr-{idioma}"))

    # `osd` es el que endereza las hojas que entraron de costado al escáner. Sin él la
    # app funciona igual, pero una hoja rotada se pierde entera.
    if "osd" in idiomas:
        salidas.append(_r("Detector de orientación (osd)", "ok",
                          "instalado — las hojas de costado se enderezan solas"))
    else:
        salidas.append(_r("Detector de orientación (osd)", "aviso",
                          "no está: una hoja escaneada de costado se va a leer mal",
                          "instalar el paquete tesseract-ocr-osd"))
    return salidas


def _fuentes():
    if not config.FUENTES.exists():
        return _r("Fuentes de la interfaz", "aviso", "falta la carpeta assets/fuentes",
                  "correr scripts/descargar-fuentes.sh en una máquina con internet")
    n = len(list(config.FUENTES.glob("*.ttf"))) + len(list(config.FUENTES.glob("*.woff2")))
    if n == 0:
        return _r("Fuentes de la interfaz", "aviso",
                  "la carpeta está vacía: la interfaz va a usar la tipografía del sistema",
                  "correr scripts/descargar-fuentes.sh en una máquina con internet")
    return _r("Fuentes de la interfaz", "ok", f"{n} archivos, servidos desde el disco")


def _escritura():
    salidas = []
    for etiqueta, carpeta in (("Carpeta de datos", config.DATOS),
                              ("Carpeta de derivados", config.DERIVADOS)):
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
            prueba = carpeta / ".escritura"
            prueba.write_text("x", encoding="utf-8")
            prueba.unlink()
            salidas.append(_r(etiqueta, "ok", f"se puede escribir en {carpeta}"))
        except Exception as e:                               # noqa: BLE001
            salidas.append(_r(etiqueta, "falla", f"no se puede escribir en {carpeta}: {e}",
                              f"dar permiso de escritura sobre {carpeta}"))
    return salidas


def _disco():
    try:
        u = shutil.disk_usage(config.DATOS if config.DATOS.exists() else config.RAIZ)
    except Exception as e:                                   # noqa: BLE001
        return _r("Espacio en disco", "aviso", f"no se pudo medir: {e}")
    libre = u.free / 1_000_000_000
    # Cuentas para que el número signifique algo: los derivados pesan alrededor de
    # 1,2 MB por página, así que el disco libre se traduce directo a páginas.
    paginas = int(libre * 1000 / 1.2)
    txt = f"{libre:.1f} GB libres — alcanza para unas {paginas:,} páginas".replace(",", ".")
    if libre < DISCO_MINIMO_GB:
        return _r("Espacio en disco", "falla", txt, "liberar espacio antes de cargar el lote")
    if libre < DISCO_COMODO_GB:
        return _r("Espacio en disco", "aviso", txt + " (justo para un lote grande)")
    return _r("Espacio en disco", "ok", txt)


def _cpu():
    n = os.cpu_count() or 1
    # 1,7 s por página con un núcleo; el paralelismo escala casi lineal hasta la
    # cantidad de núcleos. Traducirlo a horas es lo que le sirve a quien planifica.
    pag_hora = int(3600 / (1.7 / max(1, min(n, 8))))
    txt = (f"{plural(n, 'núcleo', 'núcleos')} · lee unas {miles(pag_hora)} páginas por hora"
           .replace(",", "."))
    if n == 1:
        return _r("Procesador", "aviso", txt + " — un lote de mil páginas tarda media jornada")
    return _r("Procesador", "ok", txt)


def _sqlite():
    v = sqlite3.sqlite_version
    cx = sqlite3.connect(":memory:")
    try:
        cx.execute("CREATE VIRTUAL TABLE p USING fts5(t)")
        fts = True
    except sqlite3.OperationalError:
        fts = False
    finally:
        cx.close()
    if not fts:
        return _r("SQLite", "falla", f"versión {v}, SIN el módulo FTS5: la búsqueda por "
                  "texto no va a funcionar", "instalar un Python con SQLite compilado con FTS5")
    return _r("SQLite", "ok", f"versión {v}, con búsqueda de texto (FTS5)")


def _puerto(puerto=8713):
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", puerto))
        return _r("Puerto de la interfaz", "ok", f"{puerto} libre en 127.0.0.1")
    except OSError:
        return _r("Puerto de la interfaz", "aviso",
                  f"{puerto} está ocupado (puede ser esta misma app ya andando)",
                  f"cerrar lo que esté usando el puerto, o levantar con --puerto otro")
    finally:
        s.close()


def _sin_red():
    """La restricción 1 en forma de chequeo, no de promesa."""
    url = os.environ.get("UFIL_VLM_URL", "")
    if url and not any(h in url for h in ("127.0.0.1", "localhost", "::1", "0.0.0.0")):
        return _r("Aislamiento de red", "falla",
                  f"UFIL_VLM_URL apunta fuera de esta máquina: {url}",
                  "borrar la variable UFIL_VLM_URL o apuntarla a 127.0.0.1")
    detalle = "ninguna salida configurada" if not url else f"modelo local en {url}"
    return _r("Aislamiento de red", "ok", detalle)


def _perfiles():
    n = list(config.PERFILES.glob("*.json"))
    if not n:
        return _r("Perfiles de formulario", "falla", "no hay ninguno en ufil/perfiles/",
                  "restaurar la carpeta ufil/perfiles del repositorio")
    return _r("Perfiles de formulario", "ok",
              f"{len(n)}: {', '.join(sorted(p.stem for p in n))}")


def correr(desde_web: bool = False) -> list[dict]:
    """
    Todos los chequeos, en orden de importancia para poder trabajar.

    `desde_web` saltea el chequeo de puerto: si estás mirando esta pantalla, el puerto
    anda, y avisar de que está "ocupado" —por esta misma app— sólo confunde.
    """
    salidas: list[dict] = [_python()]
    for modulo, paquete in (("fitz", "PyMuPDF"), ("PIL", "Pillow"),
                            ("pytesseract", "pytesseract"), ("openpyxl", "openpyxl")):
        salidas.append(_libreria(modulo, paquete))
    salidas.extend(_tesseract())
    salidas.append(_sqlite())
    salidas.extend(_escritura())
    salidas.append(_disco())
    salidas.append(_cpu())
    salidas.append(_perfiles())
    salidas.append(_fuentes())
    if not desde_web:
        salidas.append(_puerto())
    salidas.append(_sin_red())
    return salidas


def resumen(salidas: list[dict]) -> dict:
    fallas = [s for s in salidas if s["estado"] == "falla"]
    avisos = [s for s in salidas if s["estado"] == "aviso"]
    return {"puede_trabajar": not fallas, "fallas": len(fallas), "avisos": len(avisos),
            "chequeos": salidas}


def informe_texto(salidas: list[dict]) -> str:
    simbolo = {"ok": "  ok  ", "aviso": " AVISO", "falla": " FALLA"}
    L = ["DIAGNÓSTICO DEL ENTORNO", "=" * 84, ""]
    for s in salidas:
        L.append(f"[{simbolo[s['estado']]}]  {s['nombre']:<32} {s['detalle']}")
        if s["arreglo"] and s["estado"] != "ok":
            L.append(f"{'':>10}  {'':<32} → {s['arreglo']}")
    r = resumen(salidas)
    L.append("")
    L.append("-" * 84)
    if r["puede_trabajar"]:
        extra = (f" ({plural(r['avisos'], 'aviso que conviene mirar', 'avisos que conviene mirar')})"
                 if r["avisos"] else "")
        L.append("LISTO PARA TRABAJAR" + extra)
    else:
        L.append(f"NO SE PUEDE TRABAJAR TODAVÍA: "
                 f"{plural(r['fallas'], 'cosa que falta', 'cosas que faltan')}, "
                 "listadas arriba con su arreglo")
    return "\n".join(L)
