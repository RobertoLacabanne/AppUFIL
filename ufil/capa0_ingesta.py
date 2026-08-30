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
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

from . import config
from .db import ahora

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


# Los PDF que sale del generador de prueba llevan esta marca en sus metadatos. Se la
# busca al ingerir para poder avisar en toda pantalla que no son contratos reales,
# vengan por donde vengan —incluida la pantalla de carga, donde la ruta de origen ya
# no dice nada—.
MARCA_SINTETICO = "UFIL-CORPUS-SINTETICO-DE-PRUEBA"


def _metadatos_pdf(ruta: Path) -> tuple[int, list[tuple[float, float, bool]], bool]:
    """Devuelve (páginas, [(ancho_pt, alto_pt, tiene_texto), ...], es_de_prueba)."""
    paginas = []
    with fitz.open(ruta) as doc:
        for p in doc:
            texto = p.get_text("text").strip()
            # Una capa de texto de cuatro caracteres sueltos no es una capa de texto.
            paginas.append((p.rect.width, p.rect.height, len(texto) >= 40))
        meta = " ".join(str(v) for v in (doc.metadata or {}).values() if v)
        return doc.page_count, paginas, MARCA_SINTETICO in meta


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
        for i, (ancho, alto, con_texto) in enumerate(paginas, start=1):
            cx.execute(
                """INSERT INTO pagina (sha256, nro, ancho_pt, alto_pt, tiene_texto)
                   VALUES (?,?,?,?,?)""",
                (sha, i, ancho, alto, 1 if con_texto else 0),
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
