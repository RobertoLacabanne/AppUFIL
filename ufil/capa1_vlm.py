"""
Capa 1 — Ruta del modelo de visión local. NO IMPLEMENTADA TODAVÍA.

Este archivo define el contrato que el modelo tiene que cumplir para enchufarse al
pipeline; no simula la funcionalidad. Llamarlo sin un servidor configurado levanta
una excepción explícita, que la Capa 1 registra como excepción y sigue de largo con
las rutas de CPU.

Está así a propósito: todavía no sé qué GPU hay (ver docs/00-fase-0.md §1) y elegir
el modelo sin correr el banco de prueba con documentos reales sería adivinar.

QUÉ TIENE QUE DEVOLVER EL MODELO
--------------------------------
Una lista de palabras con recuadro en píxeles de la imagen que se le pasó. El
adaptador las convierte a puntos PDF dividiendo por `escala`. Un modelo que devuelva
texto SIN coordenadas no sirve para este pipeline: sus valores no se pueden anclar y,
por la restricción 4, un campo sin anclaje no es un dato (va a la cola de excepciones).

CANDIDATOS A EVALUAR (banco-de-prueba/)
---------------------------------------
  * PaddleOCR-VL (~0,9B, Apache-2.0) — el más chico; corre incluso sin GPU dedicada
  * Qwen3-VL 4B / 8B Instruct (Apache-2.0) — grounding con coordenadas
  * dots.ocr (~3B) o Surya 2 (~650M) — según cómo venga el manuscrito y el sello

Se elige por tres números medidos sobre el corpus real: exactitud por campo, tasa de
error silencioso y segundos por página. No por reputación.

CÓMO SE ENCHUFA
---------------
Definir UFIL_VLM_URL (por ejemplo http://127.0.0.1:8000/v1) apuntando a un vLLM o un
Ollama corriendo EN LA MISMA MÁQUINA, e implementar `_pedir_al_modelo`. Es
localhost: no viola la restricción 1, no sale de la máquina.
"""
from __future__ import annotations

import os
from pathlib import Path

from .capa1_texto import Lectura, Palabra

VLM_URL = os.environ.get("UFIL_VLM_URL", "").strip()
VLM_MODELO = os.environ.get("UFIL_VLM_MODELO", "").strip()


class VLMNoConfigurado(RuntimeError):
    pass


def disponible() -> bool:
    return bool(VLM_URL and VLM_MODELO)


def leer_vlm(png: Path, escala: float) -> Lectura:
    if not disponible():
        raise VLMNoConfigurado(
            "La ruta VLM no está configurada (faltan UFIL_VLM_URL y UFIL_VLM_MODELO). "
            "El pipeline sigue con las rutas de CPU. Ver ufil/capa1_vlm.py."
        )
    raise NotImplementedError(
        "El adaptador del modelo de visión está sin implementar a propósito: falta "
        "elegir el modelo con el banco de prueba sobre documentos reales. "
        "Ver docs/00-fase-0.md §5."
    )


def _a_palabras(items: list[dict], escala: float) -> list[Palabra]:
    """Convierte la salida del modelo (píxeles) a Palabra en puntos PDF.

    Se espera cada item como {"texto": str, "bbox": [x0,y0,x1,y1], "conf": float}.
    Un item sin bbox se descarta: sin anclaje no es un dato.
    """
    salida = []
    for it in items:
        caja = it.get("bbox")
        if not caja or len(caja) != 4:
            continue
        x0, y0, x1, y1 = (float(v) / escala for v in caja)
        salida.append(Palabra(str(it.get("texto", "")).strip(), x0, y0, x1, y1,
                              float(it.get("conf", 0.0))))
    return [p for p in salida if p.texto]
