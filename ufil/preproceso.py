"""
Preparación de la imagen para el OCR.

Todo lo de acá opera sobre el DERIVADO renderizado, nunca sobre el original
(restricción 2). Y no cambia ningún dato: cambia cuán legible es el papel para
Tesseract, que es otra cosa.

Sin numpy ni OpenCV a propósito: son dos dependencias grandes para lo que hace falta,
y en una instalación offline cada dependencia es un archivo más que alguien tiene que
acordarse de llevar. El umbral de Otsu son quince líneas.
"""
from __future__ import annotations

from PIL import Image, ImageFilter, ImageOps


def umbral_otsu(im: Image.Image) -> int:
    """Umbral de binarización de Otsu, calculado del histograma. Sin dependencias."""
    h = im.convert("L").histogram()[:256]
    total = sum(h)
    if not total:
        return 128
    suma = sum(i * n for i, n in enumerate(h))
    suma_b = peso_b = 0.0
    mejor_var, mejor_u = -1.0, 128
    for u in range(256):
        peso_b += h[u]
        if peso_b == 0:
            continue
        peso_f = total - peso_b
        if peso_f == 0:
            break
        suma_b += u * h[u]
        media_b = suma_b / peso_b
        media_f = (suma - suma_b) / peso_f
        var = peso_b * peso_f * (media_b - media_f) ** 2
        if var > mejor_var:
            mejor_var, mejor_u = var, u
    return mejor_u


def para_pagina(im: Image.Image) -> Image.Image:
    """
    Limpieza suave de la página entera, antes del OCR de página completa.

    Deliberadamente conservadora: normaliza el gris y saca la mota fina de fotocopia.
    NO binariza. En una página completa, binarizar sirve cuando el papel está parejo y
    arruina el texto fino cuando no lo está, y no podemos saber de antemano cuál de las
    dos cosas nos van a subir.
    """
    g = im.convert("L")
    g = ImageOps.autocontrast(g, cutoff=(0.4, 0.2))
    return g.filter(ImageFilter.MedianFilter(size=3))


def para_campo(im: Image.Image, caja_px, *, escala: float = 3.0,
               margen: int = 6) -> Image.Image:
    """
    Recorte de un campo, agrandado y binarizado, para releerlo con atención.

    Acá sí se binariza: el recuadro de un campo es una zona chica y homogénea, y
    ampliarla antes de umbralizar es lo que le permite a Tesseract separar el 7 del 1
    o el 2 del 7 en un escaneo mediocre.
    """
    x0, y0, x1, y1 = (int(round(v)) for v in caja_px)
    x0 = max(0, x0 - margen); y0 = max(0, y0 - margen)
    x1 = min(im.width, x1 + margen); y1 = min(im.height, y1 + margen)
    if x1 <= x0 or y1 <= y0:
        raise ValueError("recuadro vacío")

    rec = im.convert("L").crop((x0, y0, x1, y1))
    rec = rec.resize((int(rec.width * escala), int(rec.height * escala)), Image.LANCZOS)
    rec = ImageOps.autocontrast(rec, cutoff=(0.5, 0.5))
    u = umbral_otsu(rec)
    # Un pelo por encima de Otsu engorda el trazo, que en texto chico ayuda más de lo
    # que ensucia.
    return rec.point(lambda v, u=u: 255 if v > u + 8 else 0, mode="L")
