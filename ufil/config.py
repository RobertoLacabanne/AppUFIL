"""Configuración y constantes. Todo por ruta relativa: el proyecto es portable."""
from __future__ import annotations
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Los derivados NUNCA se escriben adentro del corpus (restricción 2).
DATOS      = Path(os.environ.get("UFIL_DATOS", RAIZ / "datos"))
DERIVADOS  = DATOS / "derivados"
BASE       = Path(os.environ.get("UFIL_BASE", DATOS / "ufil.sqlite"))
ESQUEMA    = RAIZ / "ufil" / "esquema.sql"
CONSULTAS  = RAIZ / "ufil" / "consultas"
PERFILES   = RAIZ / "ufil" / "perfiles"
WEB        = RAIZ / "ufil" / "web"
FUENTES    = RAIZ / "assets" / "fuentes"

# Renderizado de páginas para el visor y para el OCR.
DPI_RENDER = 200
PT_POR_PULGADA = 72.0
ESCALA_RENDER = DPI_RENDER / PT_POR_PULGADA          # px por punto PDF

# Idioma del OCR. El paquete `spa` de Tesseract se instala una sola vez.
OCR_IDIOMA = os.environ.get("UFIL_OCR_IDIOMA", "spa")

# Dos configuraciones de Tesseract que segmentan la página de forma distinta.
# NO son lecturas independientes de verdad —comparten motor de reconocimiento—,
# pero atrapan la familia de errores de segmentación y layout, que en formularios
# escaneados es la más común. La lectura verdaderamente independiente entra con
# el VLM cuando haya GPU (ver ufil/capa1_vlm.py).
OCR_CONFIG = {
    "ocr_a": "--oem 1 --psm 6",    # bloque uniforme de texto
    "ocr_b": "--oem 1 --psm 11",   # texto disperso, sin asumir estructura
}

# Umbral por debajo del cual la celda se marca con trama en la interfaz.
UMBRAL_CONFIANZA = 0.85

# Campos críticos: los únicos que exigen doble lectura y tolerancia cero al
# error silencioso (ver docs/00-fase-0.md §6).
CAMPOS_CRITICOS = ("nombre", "documento", "fecha_inicio", "fecha_fin", "monto")

# Rango de años considerado plausible para una fecha de contrato. Fuera de esto
# NO se corrige nada: se marca como sospechosa y la mira una persona.
ANIO_MIN, ANIO_MAX = 1983, 2100
