"""
¿Lo que se guarda sobrevive a un reinicio? Comprobado, no deducido.

EL PROBLEMA
-----------
Es la única falla del sistema que no se ve venir. Un servicio de nube sin
almacenamiento persistente anda perfecto: guarda los PDF, arma las bases, muestra los
totales bien, deja revisar campo por campo durante dos días. Y en el próximo despliegue
la carpeta vuelve a estar vacía. Pasó de verdad, con material de una causa: se creaba
un legajo, al otro día no estaba, y se volvía a crear otro.

POR QUÉ NO ALCANZA CON MIRAR LOS MONTAJES
-----------------------------------------
La primera versión de esto miraba `/proc/self/mounts`: si la carpeta de datos estaba
debajo de un punto de montaje propio, había un volumen atrás. Suena razonable y **es
falso**, de la peor manera: da tranquilidad donde hay peligro.

El `Dockerfile` declara `VOLUME ["/app/datos"]`. Eso hace que el motor de contenedores
cree ahí un **volumen anónimo**, que aparece en `/proc/self/mounts` como cualquier
otro montaje… y que se destruye junto con el contenedor, o sea en cada despliegue. El
chequeo contestaba «está en un disco propio: sobrevive a los reinicios» sobre un
almacenamiento que no sobrevive a ninguno.

Un instrumento mal calibrado es peor que no medir: sin chequeo alguien desconfía y baja
un respaldo; con un chequeo que miente, se queda tranquilo.

LO QUE SE HACE EN CAMBIO
------------------------
Se deja una marca en la carpeta de datos y se cuenta cuántos arranques sobrevivió. Eso
no se puede falsear: o el archivo sigue ahí después de reiniciar, o no sigue.

  arranques = 1   todavía no se sabe. Puede ser la primera vez que se levanta sobre un
                  disco nuevo y flamante, o puede ser que la carpeta se borre en cada
                  arranque. Desde adentro, en el primer arranque, las dos se ven igual
                  —y decir que no se sabe es lo único honesto—.
  arranques > 1   comprobado: la carpeta sobrevivió a N arranques. Es la única
                  afirmación de permanencia que este sistema puede hacer con pruebas.

La manera de confirmarlo en dos minutos: reiniciar el servicio y volver a mirar. Si el
número no sube, los datos se están borrando.
"""
from __future__ import annotations

import json
import os
import socket
import uuid
from pathlib import Path

from . import config
from .db import ahora

ARCHIVO = ".permanencia.json"

# Cuántos arranques se recuerdan con fecha y hora. Sirve para ver el patrón: si las
# fechas son todas de hoy y hay ocho, algo reinicia el servicio todo el tiempo.
HISTORIAL = 12


def ruta() -> Path:
    return Path(config.DATOS) / ARCHIVO


def leer() -> dict:
    try:
        d = json.loads(ruta().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def registrar_arranque() -> dict:
    """
    Anota que el sistema arrancó. Se llama una vez, al levantar el servidor.

    Si falla la escritura NO se interrumpe el arranque: quedarse sin sistema es peor
    que quedarse sin la marca. El estado lo va a reportar igual, como falla.
    """
    d = leer()
    ahora_ = ahora()
    d["id"] = d.get("id") or uuid.uuid4().hex
    d["creado_en"] = d.get("creado_en") or ahora_
    d["arranques"] = int(d.get("arranques") or 0) + 1
    d["ultimo_arranque"] = ahora_
    historial = list(d.get("historial") or [])
    historial.append(ahora_)
    d["historial"] = historial[-HISTORIAL:]
    d["ultimo_host"] = socket.gethostname()
    try:
        p = ruta()
        p.parent.mkdir(parents=True, exist_ok=True)
        # Escritura atómica: un corte de luz en el medio no puede dejar el archivo a
        # medio escribir y llevarse la cuenta con él.
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        pass
    return d


def en_contenedor() -> bool:
    return Path("/.dockerenv").exists() or os.environ.get("RENDER") is not None


def _montaje_propio(real: Path) -> str | None:
    """
    El punto de montaje que contiene la carpeta, si no es la raíz.

    Se conserva SÓLO como dato de contexto, nunca como veredicto: un volumen anónimo
    de Docker también aparece acá y no sobrevive a nada.
    """
    try:
        with open("/proc/self/mounts", encoding="utf-8") as f:
            montajes = [l.split()[1] for l in f if len(l.split()) > 1]
    except OSError:
        return None
    cubre = [m for m in montajes
             if str(real) == m or str(real).startswith(m.rstrip("/") + "/")]
    punto = max(cubre, key=len) if cubre else "/"
    return None if punto == "/" else punto


def estado() -> dict:
    """
    Qué se puede afirmar hoy sobre la permanencia de los datos.

    Devuelve `estado` en el vocabulario del diagnóstico: ok / aviso / falla.
    """
    datos = Path(config.DATOS)
    try:
        datos.mkdir(parents=True, exist_ok=True)
        real = datos.resolve()
    except OSError as e:                                     # noqa: BLE001
        return {"estado": "falla", "arranques": 0,
                "detalle": f"no se pudo abrir la carpeta de datos: {e}",
                "arreglo": "revisar permisos de la carpeta de datos"}

    d = leer()
    n = int(d.get("arranques") or 0)
    montaje = _montaje_propio(real)
    contexto = (f" El sistema de archivos dice que {real} está bajo «{montaje}», pero "
                f"eso no alcanza para saberlo: un volumen anónimo de contenedor también "
                f"aparece así y se borra igual.") if montaje and en_contenedor() else ""

    if not d:
        return {"estado": "falla", "arranques": 0,
                "detalle": f"no se pudo dejar una marca en {real}, así que no hay manera "
                           f"de saber si lo que se guarda sobrevive.",
                "arreglo": "revisar permisos de escritura sobre la carpeta de datos"}

    if n >= 2:
        return {"estado": "ok", "arranques": n,
                "detalle": f"comprobado: la carpeta {real} sobrevivió a "
                           f"{n} arranques desde el {_fecha(d.get('creado_en'))}.",
                "arreglo": None}

    if en_contenedor():
        return {
            "estado": "aviso", "arranques": n,
            "detalle": (f"todavía no se puede afirmar que los datos sobrevivan. Este es "
                        f"el primer arranque sobre {real}, y desde adentro un disco "
                        f"nuevo y una carpeta que se borra en cada despliegue se ven "
                        f"igual.{contexto}"),
            "arreglo": ("reiniciá el servicio y volvé a mirar acá. Si el número de "
                        "arranques no sube, los datos SE ESTÁN BORRANDO y hay que "
                        "montar un disco persistente antes de cargar material de una "
                        "causa (en Render: Settings → Disks, con el mismo camino que "
                        "UFIL_DATOS). Mientras tanto, bajá una copia de respaldo al "
                        "terminar cada jornada."),
        }

    return {"estado": "ok", "arranques": n,
            "detalle": f"{real} está en el disco de esta máquina.",
            "arreglo": None}


def _fecha(iso: str | None) -> str:
    if not iso:
        return "primer arranque"
    return f"{iso[8:10]}/{iso[5:7]}/{iso[0:4]}"
