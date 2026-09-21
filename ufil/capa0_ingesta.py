"""
Capa 0 — Ingesta.

Recorre un lote en SOLO LECTURA. Calcula SHA-256, detecta duplicados exactos,
registra procedencia y metadatos técnicos.

Restricción 2, cumplida por construcción: este módulo abre los archivos del corpus
con modo "rb" y nada más. No hay una sola llamada de escritura, renombrado o
movimiento sobre el árbol de origen. Los derivados van a datos/derivados/, indexados
por el hash del original del que salieron.
"""
from __future__ import annotations

import hashlib
import mimetypes
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF

from . import config
from . import huella as hu
from .db import ahora
from .exclusion import conexion_carga

EXTENSIONES = {".pdf"}


def sha256_de(ruta: Path, bloque: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:                      # solo lectura, siempre
        for trozo in iter(lambda: f.read(bloque), b""):
            h.update(trozo)
    return h.hexdigest()


def carpeta_derivados(sha: str) -> Path:
    d = config.DERIVADOS / sha[:2] / sha
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class ResultadoIngesta:
    nuevos: int = 0
    duplicados: int = 0
    fallidos: int = 0
    paginas: int = 0
    # El mismo papel adentro de otro archivo: mismo documento, otro SHA-256. No se
    # guarda —no aporta una sola foja— pero tiene que contarse aparte del duplicado
    # exacto, porque son dos cosas distintas y la segunda es la que sorprende.
    mismo_papel: int = 0
    # Archivos que traen ALGUNAS fojas que ya estaban. Se guardan igual: dos partes de
    # un expediente comparten la foja del empalme y eso es correcto. Se avisa.
    solapados: list = field(default_factory=list)


# Los PDF que sale del generador de prueba llevan esta marca en sus metadatos. Se la
# busca al ingerir para poder avisar en toda pantalla que no son contratos reales,
# vengan por donde vengan —incluida la pantalla de carga, donde la ruta de origen ya
# no dice nada—.
MARCA_SINTETICO = "UFIL-CORPUS-SINTETICO-DE-PRUEBA"


def _metadatos_pdf(ruta: Path) -> tuple[int, list[tuple[float, float, bool, str]], bool]:
    """
    Devuelve (páginas, [(ancho_pt, alto_pt, tiene_texto, huella), ...], es_de_prueba).

    La huella se saca ACÁ, en la misma pasada que ya abre el PDF y recorre sus páginas.
    Es lo que después permite reconocer el mismo papel adentro de otro archivo, y hay
    que tenerla ANTES de guardar nada: avisar de un duplicado después de ingerirlo es
    avisar tarde. Medido sobre un expediente de 88 fojas: 0,53 s, contra 119 s que
    cuesta leerlo.
    """
    from .huella import de_pagina
    paginas = []
    with fitz.open(ruta) as doc:
        for p in doc:
            texto = p.get_text("text").strip()
            # Una capa de texto de cuatro caracteres sueltos no es una capa de texto.
            paginas.append((p.rect.width, p.rect.height, len(texto) >= 40, de_pagina(p)))
        meta = " ".join(str(v) for v in (doc.metadata or {}).values() if v)
        return doc.page_count, paginas, MARCA_SINTETICO in meta


@conexion_carga
def ingerir(
    cx: sqlite3.Connection,
    origen: Path,
    *,
    lote: str,
    legajo: str | None = None,
    acta: str | None = None,
    domicilio: str | None = None,
    dispositivo: str | None = None,
    fecha_secuestro: str | None = None,
    operador: str | None = None,
) -> ResultadoIngesta:
    origen = Path(origen).resolve()
    res = ResultadoIngesta()
    archivos = sorted(p for p in origen.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSIONES)

    for ruta in archivos:
        try:
            sha = sha256_de(ruta)
        except OSError as e:
            res.fallidos += 1
            cx.execute(
                "INSERT INTO excepcion (sha256, clase, detalle, creado_en) VALUES (?,?,?,?)",
                (None, "ingesta_ilegible", f"{ruta}: {e}", ahora()),
            )
            continue

        ya = cx.execute("SELECT sha256 FROM archivo WHERE sha256=?", (sha,)).fetchone()
        if cx.execute('SELECT 1 FROM papelera_archivo WHERE sha256=?', (sha,)).fetchone():
            raise ValueError('El archivo está en papelera: restauralo antes de ingerirlo.')
        if ya:
            # Copia exacta. Se registra el hecho; no se borra ni se toca nada.
            cx.execute(
                "INSERT OR IGNORE INTO duplicado (sha256, ruta_original, visto_en) VALUES (?,?,?)",
                (sha, str(ruta), ahora()),
            )
            res.duplicados += 1
            continue

        try:
            n_pag, paginas, de_prueba = _metadatos_pdf(ruta)
        except Exception as e:
            res.fallidos += 1
            cx.execute(
                "INSERT INTO excepcion (sha256, clase, detalle, creado_en) VALUES (?,?,?,?)",
                (sha, "pdf_ilegible", f"{ruta}: {type(e).__name__}: {e}", ahora()),
            )
            continue

        # ¿El mismo papel adentro de otro archivo? Ver ufil/huella.py. Si todas sus
        # fojas legibles ya están, el archivo no aporta nada y no se guarda.
        cot = hu.cotejar(cx, [h for _, _, _, h in paginas])
        v = hu.veredicto(cot)
        if v == "repetido":
            # Va a `excepcion` y no a `duplicado`: `duplicado` dice «este archivo que
            # TENGO apareció de nuevo», y éste no está —no se guarda—. Y va con estado
            # abierto a propósito, para que aparezca en «Quedaron afuera»: un archivo
            # que entró y no dejó rastro tiene que poder explicarse después.
            cx.execute(
                "INSERT INTO excepcion (sha256, clase, detalle, creado_en) VALUES (?,?,?,?)",
                (None, "mismo_papel",
                 f"{ruta}: es copia entera de {cot['mismo_que']} "
                 f"({cot['total']} fojas)", ahora()),
            )
            res.mismo_papel += 1
            continue
        if v == "parcial":
            res.solapados.append({"archivo": ruta.name, **cot})

        st = ruta.stat()
        cx.execute(
            """INSERT INTO archivo (sha256, ruta_original, nombre, bytes, mtime, mime,
                                    paginas, ingerido_en)
               VALUES (?,?,?,?,?,?,?,?)""",
            (sha, str(ruta), ruta.name, st.st_size, st.st_mtime,
             mimetypes.guess_type(ruta.name)[0] or "application/pdf", n_pag, ahora()),
        )
        cx.execute(
            """INSERT INTO procedencia (sha256, legajo, acta, domicilio, dispositivo,
                                        fecha_secuestro, operador, lote)
               VALUES (?,?,?,?,?,?,?,?)""",
            (sha, legajo, acta, domicilio, dispositivo, fecha_secuestro, operador, lote),
        )
        for i, (ancho, alto, con_texto, hue) in enumerate(paginas, start=1):
            cx.execute(
                """INSERT INTO pagina (sha256, nro, ancho_pt, alto_pt, tiene_texto, huella)
                   VALUES (?,?,?,?,?,?)""",
                (sha, i, ancho, alto, 1 if con_texto else 0, hue),
            )
        if de_prueba:
            # Basta un archivo de prueba para que la base entera quede marcada. El error
            # a evitar es el otro: mostrar contratos inventados sin decirlo.
            from .db import ajuste
            ajuste(cx, "demostracion", "1")
        res.nuevos += 1
        res.paginas += n_pag

    cx.commit()
    return res
