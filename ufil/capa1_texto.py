"""
Capa 1 — Extracción de texto con coordenadas.

Clasificador de ruta por página:
  * capa de texto nativa  -> se lee directo del PDF (exacto, confianza 1,0)
  * escaneo               -> OCR clásico en CPU, en DOS configuraciones distintas
  * página compleja       -> modelo de visión local (ver capa1_vlm.py)

Toda ruta devuelve lo mismo: una lista de `Palabra` con su recuadro en PUNTOS PDF,
origen arriba-izquierda. Esa unidad común es lo que hace posible comparar rutas
entre sí y anclar cualquier dato a su lugar en la imagen (restricción 4).
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import fitz
import pytesseract
from PIL import Image

from . import config
from .capa0_ingesta import carpeta_derivados
from .db import ahora


@dataclass
class Palabra:
    texto: str
    x0: float; y0: float; x1: float; y1: float   # puntos PDF
    conf: float                                   # 0..1


@dataclass
class Lectura:
    ruta: str
    motor: str
    version: str
    palabras: list[Palabra]
    confianza: float
    ms: int


# ─────────────────────────────────────────────────────────── render de página ──
def render_pagina(ruta_pdf: Path, sha: str, nro: int) -> tuple[Path, float]:
    """Renderiza la página a PNG en datos/derivados/. El original no se toca."""
    destino = carpeta_derivados(sha) / f"p{nro:04d}.png"
    if destino.exists():
        return destino, config.ESCALA_RENDER
    with fitz.open(ruta_pdf) as doc:
        pag = doc[nro - 1]
        pix = pag.get_pixmap(matrix=fitz.Matrix(config.ESCALA_RENDER, config.ESCALA_RENDER))
        pix.save(destino)
    return destino, config.ESCALA_RENDER


# ────────────────────────────────────────────────────────────── ruta: nativa ──
def leer_nativo(ruta_pdf: Path, nro: int) -> Lectura:
    t0 = time.perf_counter()
    palabras: list[Palabra] = []
    with fitz.open(ruta_pdf) as doc:
        for x0, y0, x1, y1, w, *_ in doc[nro - 1].get_text("words"):
            if w.strip():
                palabras.append(Palabra(w, x0, y0, x1, y1, 1.0))
    return Lectura("nativo", "pymupdf", fitz.VersionBind, palabras, 1.0,
                   int((time.perf_counter() - t0) * 1000))


# ───────────────────────────────────────────────────────────────── ruta: OCR ──
_VER_TESS = str(pytesseract.get_tesseract_version()).split()[0]


def leer_ocr(png: Path, escala: float, ruta: str) -> Lectura:
    t0 = time.perf_counter()
    cfg = config.OCR_CONFIG[ruta]
    with Image.open(png) as im:
        datos = pytesseract.image_to_data(
            im, lang=config.OCR_IDIOMA, config=cfg,
            output_type=pytesseract.Output.DICT,
        )
    palabras: list[Palabra] = []
    confs: list[float] = []
    for i, texto in enumerate(datos["text"]):
        texto = (texto or "").strip()
        if not texto:
            continue
        try:
            c = float(datos["conf"][i])
        except (TypeError, ValueError):
            c = -1.0
        if c < 0:
            continue
        conf = c / 100.0
        x, y = datos["left"][i] / escala, datos["top"][i] / escala
        w, h = datos["width"][i] / escala, datos["height"][i] / escala
        palabras.append(Palabra(texto, x, y, x + w, y + h, conf))
        confs.append(conf)
    media = sum(confs) / len(confs) if confs else 0.0
    return Lectura(ruta, "tesseract", _VER_TESS, palabras, media,
                   int((time.perf_counter() - t0) * 1000))


# ─────────────────────────────────────────────────────────────── orquestación ──
def rutas_para(tiene_texto: bool, con_vlm: bool) -> list[str]:
    """
    Qué rutas se corren sobre esta página.

    Siempre al menos dos, para que la comparación exista (doble lectura). Cuando hay
    capa de texto nativa, la segunda lectura es OCR sobre el render: son motores
    genuinamente distintos y la comparación vale mucho.
    """
    rutas = ["nativo", "ocr_a"] if tiene_texto else ["ocr_a", "ocr_b"]
    if con_vlm:
        rutas.append("vlm")
    return rutas


def leer_documento(cx: sqlite3.Connection, sha: str, *, con_vlm: bool = False) -> int:
    """Lee todas las páginas de un archivo por todas sus rutas. Devuelve nº de lecturas."""
    fila = cx.execute("SELECT ruta_original FROM archivo WHERE sha256=?", (sha,)).fetchone()
    if not fila:
        raise KeyError(f"archivo no ingerido: {sha}")
    ruta_pdf = Path(fila["ruta_original"])

    hechas = 0
    for pag in cx.execute(
        "SELECT id, nro, tiene_texto FROM pagina WHERE sha256=? ORDER BY nro", (sha,)
    ).fetchall():
        png, escala = render_pagina(ruta_pdf, sha, pag["nro"])
        cx.execute("UPDATE pagina SET render=?, render_escala=? WHERE id=?",
                   (str(png), escala, pag["id"]))

        for ruta in rutas_para(bool(pag["tiene_texto"]), con_vlm):
            if cx.execute("SELECT 1 FROM lectura WHERE pagina_id=? AND ruta=?",
                          (pag["id"], ruta)).fetchone():
                continue
            try:
                if ruta == "nativo":
                    lec = leer_nativo(ruta_pdf, pag["nro"])
                elif ruta == "vlm":
                    from .capa1_vlm import leer_vlm
                    lec = leer_vlm(png, escala)
                else:
                    lec = leer_ocr(png, escala, ruta)
            except Exception as e:
                cx.execute(
                    "INSERT INTO excepcion (sha256, clase, detalle, creado_en) VALUES (?,?,?,?)",
                    (sha, "lectura_fallida",
                     f"pág {pag['nro']} ruta {ruta}: {type(e).__name__}: {e}", ahora()),
                )
                continue

            cur = cx.execute(
                """INSERT INTO lectura (pagina_id, ruta, motor, version, confianza, ms, creado_en)
                   VALUES (?,?,?,?,?,?,?)""",
                (pag["id"], lec.ruta, lec.motor, lec.version, lec.confianza, lec.ms, ahora()),
            )
            lid = cur.lastrowid
            cx.executemany(
                """INSERT INTO palabra (lectura_id, orden, texto, x0, y0, x1, y1, conf)
                   VALUES (?,?,?,?,?,?,?,?)""",
                [(lid, i, p.texto, p.x0, p.y0, p.x1, p.y1, p.conf)
                 for i, p in enumerate(lec.palabras)],
            )
            hechas += 1
    cx.commit()
    return hechas


def palabras_de(cx: sqlite3.Connection, lectura_id: int) -> list[Palabra]:
    return [Palabra(r["texto"], r["x0"], r["y0"], r["x1"], r["y1"], r["conf"])
            for r in cx.execute(
                "SELECT texto,x0,y0,x1,y1,conf FROM palabra WHERE lectura_id=? ORDER BY orden",
                (lectura_id,))]
