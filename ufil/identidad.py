"""
Quién firma esto.

Los nombres de la casa estaban repartidos en once archivos: el encabezado HTML, la
portada del Excel, la pantalla de acceso, el título de la pestaña, el pie de los
informes. Cambiar de fiscal significaba buscarlos todos, y el que quedaba sin
cambiar era el que después aparecía impreso en una presentación.

Acá están una sola vez. Se pueden cambiar de tres maneras, de la más general a la
más particular:

  1. los valores de abajo, que son los que corresponden hoy;
  2. un archivo `identidad.json` en la carpeta de datos, que pisa lo que nombre;
  3. variables de entorno `UFIL_ORGANISMO`, `UFIL_UNIDAD`, `UFIL_FISCALES`…, que
     pisan a las dos anteriores —así se cambia en un despliegue sin tocar el código.

La jerarquía es deliberada y se respeta en todas las pantallas:

    Ministerio Público Fiscal de Entre Ríos      ← el organismo
      UFIL Paraná                                ← la unidad
        Área Anticorrupción                      ← el área
          Análisis documental                    ← esta herramienta

Los fiscales van en segundo plano —acceso, «Acerca del sistema», encabezado de lo
que se exporta— y nunca compitiendo con el dato de la pantalla.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# Los valores de la casa. Cambiarlos acá cambia todo el sistema.
BASE: dict[str, object] = {
    "organismo": "Ministerio Público Fiscal",
    "jurisdiccion": "Provincia de Entre Ríos",
    "organismo_corto": "MPF Entre Ríos",
    "unidad": "UFIL Paraná",
    "unidad_larga": "Unidad Fiscal de Investigación y Litigación de Paraná",
    "area": "Área Anticorrupción",
    "sistema": "Análisis documental",
    "fiscales": ["Gonzalo A. Badano", "Juan Francisco Ramírez Montrull"],
    "rotulo_fiscales": "Fiscales",
}

# Cada clave, con la variable de entorno que la pisa.
_ENTORNO = {clave: "UFIL_" + clave.upper() for clave in BASE}

_ARCHIVO = "identidad.json"


def _del_archivo() -> dict:
    """
    `identidad.json` de la carpeta de datos, si está y si se puede leer.

    Un archivo roto no puede dejar la aplicación sin encabezado: si no se entiende,
    se ignora y se sigue con los valores de la casa. Que falte el nombre del área es
    un problema menor; que no arranque el sistema es un problema mayor.
    """
    from ufil import config
    try:
        ruta = Path(config.DATOS) / _ARCHIVO
        if not ruta.is_file():
            return {}
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        return datos if isinstance(datos, dict) else {}
    except Exception:
        return {}


def _del_entorno() -> dict:
    fuera = {}
    for clave, variable in _ENTORNO.items():
        v = os.environ.get(variable)
        if not v:
            continue
        # Varios fiscales se separan con punto y coma: los nombres llevan coma adentro
        # («Pérez, Juan»), así que la coma no sirve de separador.
        fuera[clave] = [x.strip() for x in v.split(";") if x.strip()] \
            if clave == "fiscales" else v
    return fuera


def actual() -> dict:
    """La identidad ya resuelta, con las tres capas aplicadas en orden."""
    d = dict(BASE)
    for capa in (_del_archivo(), _del_entorno()):
        for clave, valor in capa.items():
            if clave in BASE and valor not in (None, "", []):
                d[clave] = valor
    return d


def linea_organismo(d: dict | None = None) -> str:
    """«Ministerio Público Fiscal de la Provincia de Entre Ríos»."""
    d = d or actual()
    return f"{d['organismo']} de la {d['jurisdiccion']}"


def firma(d: dict | None = None) -> str:
    """
    El pie de un documento exportado, en una línea.

    Un solo fiscal no lleva «y»; dos llevan «y»; tres o más llevan comas y una «y»
    final. Es la misma regla del castellano de siempre, y escrita mal se nota.
    """
    d = d or actual()
    f = list(d.get("fiscales") or [])
    if not f:
        return ""
    if len(f) == 1:
        nombres = f[0]
    else:
        nombres = ", ".join(f[:-1]) + " y " + f[-1]
    rotulo = d["rotulo_fiscales"] if len(f) > 1 else "Fiscal"
    return f"{rotulo}: {nombres}"


def encabezado_export(d: dict | None = None) -> list[str]:
    """Las líneas que van arriba de todo lo que sale del sistema."""
    d = d or actual()
    lineas = [linea_organismo(d), f"{d['unidad']} · {d['area']}", d["sistema"]]
    f = firma(d)
    if f:
        lineas.append(f)
    return lineas
