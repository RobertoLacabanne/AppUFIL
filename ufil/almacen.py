"""
Almacén de originales.

Cuando un PDF llega por la interfaz, en algún lado hay que guardarlo. Ese archivo pasa
a ser EL original a los efectos del sistema, así que se escribe una sola vez y después
no se toca nunca más:

  * se guarda bajo su propio SHA-256, no bajo el nombre que traía. Dos personas pueden
    subir "contrato.pdf" el mismo día;
  * el nombre original se conserva en la base, no en el sistema de archivos;
  * se le sacan los permisos de escritura (modo 0444). No es infalible —root puede
    todo— pero convierte un accidente en un error explícito;
  * si el contenido ya estaba, no se vuelve a escribir: se registra como copia exacta.

`ufil verificar` rehashea una muestra y avisa si alguno cambió.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import fitz

from . import config
from . import huella as hu
from .capa0_ingesta import _metadatos_pdf
from .db import ahora
from .exclusion import conexion

MAX_BYTES = 200 * 1024 * 1024          # un PDF de más de 200 MB no es un contrato


class ArchivoInvalido(ValueError):
    pass


@dataclass
class Guardado:
    sha256: str
    nombre: str
    paginas: int
    duplicado: bool
    ruta: Path
    # Por qué se consideró repetido: `archivo` cuando es el mismo byte a byte, `papel`
    # cuando es el mismo documento adentro de otro archivo. Vacío si es nuevo.
    motivo: str = ""
    # El cotejo de fojas contra lo que ya hay. Ver ufil/huella.py.
    cotejo: dict | None = None


def raiz_originales() -> Path:
    """
    Dónde se guardan los originales del legajo activo.

    Sale de `config.ORIGINALES`, que se resuelve por hilo: los PDF de un legajo se
    escriben adentro de la carpeta de ESE legajo. Si no hay legajo activo —instalación
    vieja, o pruebas— cae en `datos/originales`, como antes.
    """
    d = Path(os.environ.get("UFIL_ORIGINALES") or config.ORIGINALES)
    d.mkdir(parents=True, exist_ok=True)
    return d


@conexion
def guardar(cx: sqlite3.Connection, datos: bytes, nombre: str, *, lote: str,
            legajo: str | None = None, acta: str | None = None,
            domicilio: str | None = None, operador: str | None = None,
            fecha_secuestro: str | None = None) -> Guardado:
    if not datos:
        raise ArchivoInvalido("el archivo llegó vacío")
    if len(datos) > MAX_BYTES:
        raise ArchivoInvalido(f"pesa más de {MAX_BYTES // (1024*1024)} MB")
    if not datos.lstrip()[:5].startswith(b"%PDF"):
        raise ArchivoInvalido("no es un PDF (no empieza con %PDF)")

    nombre = Path(nombre).name.strip() or "sin-nombre.pdf"
    sha = hashlib.sha256(datos).hexdigest()

    if cx.execute('SELECT 1 FROM papelera_archivo WHERE sha256=?', (sha,)).fetchone():
        raise ArchivoInvalido('El archivo está en papelera: restauralo antes de volver a subirlo.')

    ya = cx.execute("SELECT ruta_original FROM archivo WHERE sha256=?", (sha,)).fetchone()
    if ya:
        cx.execute("""INSERT OR IGNORE INTO duplicado (sha256, ruta_original, visto_en)
                      VALUES (?,?,?)""", (sha, f"(subido de nuevo como {nombre})", ahora()))
        cx.commit()
        n = cx.execute("SELECT paginas FROM archivo WHERE sha256=?", (sha,)).fetchone()["paginas"]
        return Guardado(sha, nombre, n or 0, True, Path(ya["ruta_original"]),
                        motivo="archivo")

    destino = raiz_originales() / sha[:2] / f"{sha}.pdf"
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(".parcial")
    parcial.write_bytes(datos)

    try:
        n_pag, paginas, de_prueba = _metadatos_pdf(parcial)
    except Exception as e:
        parcial.unlink(missing_ok=True)
        raise ArchivoInvalido(f"el PDF no se puede abrir: {type(e).__name__}") from e
    if n_pag == 0:
        parcial.unlink(missing_ok=True)
        raise ArchivoInvalido("el PDF no tiene páginas")

    # ── ¿Es el mismo papel adentro de otro archivo? ───────────────────────────
    # El SHA-256 de arriba sólo reconoce el MISMO ARCHIVO. Reexportar el mismo PDF
    # —lo que hace cualquier programa al guardarlo, y lo que hace un portal al rearmar
    # la descarga— cambia los bytes y no cambia una sola foja. Medido: el expediente
    # 201.602 entró dos veces y el legajo quedó con 176 fojas, sin un aviso.
    #
    # Si TODAS las fojas legibles ya están, el archivo no aporta nada por definición y
    # no se guarda. Si están ALGUNAS, se guarda y se avisa: dos partes de un mismo
    # expediente comparten la foja del empalme, y eso es correcto en el papel. Quién
    # sabe cuál de las dos cosas es, es quien carga; el sistema avisa, no elige.
    cot = hu.cotejar(cx, [h for _, _, _, h in paginas])
    if hu.veredicto(cot) == "repetido":
        parcial.unlink(missing_ok=True)
        cx.execute("""INSERT INTO excepcion (sha256, clase, detalle, creado_en)
                      VALUES (NULL,?,?,?)""",
                   ("mismo_papel",
                    f"{nombre}: es copia entera de {cot['mismo_que']} "
                    f"({cot['total']} fojas)", ahora()))
        cx.commit()
        return Guardado(sha, nombre, n_pag, True, Path(), motivo="papel", cotejo=cot)

    parcial.rename(destino)
    try:
        destino.chmod(0o444)                 # a partir de acá, sólo lectura
    except OSError:
        pass

    st = destino.stat()
    cx.execute("""INSERT INTO archivo (sha256, ruta_original, nombre, bytes, mtime, mime,
                                       paginas, ingerido_en)
                  VALUES (?,?,?,?,?,'application/pdf',?,?)""",
               (sha, str(destino), nombre, st.st_size, st.st_mtime, n_pag, ahora()))
    cx.execute("""INSERT INTO procedencia (sha256, legajo, acta, domicilio, dispositivo,
                                           fecha_secuestro, operador, lote)
                  VALUES (?,?,?,?,NULL,?,?,?)""",
               (sha, legajo, acta, domicilio, fecha_secuestro, operador, lote))
    for i, (ancho, alto, con_texto, hue) in enumerate(paginas, start=1):
        cx.execute("""INSERT INTO pagina (sha256, nro, ancho_pt, alto_pt, tiene_texto, huella)
                      VALUES (?,?,?,?,?,?)""",
                   (sha, i, ancho, alto, 1 if con_texto else 0, hue))
    if de_prueba:
        # Los PDF del generador de prueba llevan una marca en sus metadatos. Acá es
        # donde más importa reconocerla: subidos por la pantalla de carga, la ruta de
        # origen ya no dice «corpus-sintetico» y sin esto pasarían por contratos reales
        # en medio de una demostración.
        from .db import ajuste
        ajuste(cx, "demostracion", "1")
    cx.commit()
    return Guardado(sha, nombre, n_pag, False, destino,
                    motivo="parcial" if cot["repetidas"] else "", cotejo=cot)
