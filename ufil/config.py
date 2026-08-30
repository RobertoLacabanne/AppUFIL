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

# Cuántas páginas se leen en paralelo. Medido en una máquina de cuatro núcleos:
# 1 hilo 1,04 s por página · 2 hilos 0,46 · 4 hilos 0,25 · 8 hilos 0,27.
# Más allá de la cantidad de núcleos no rinde: los procesos se pelean por el mismo CPU.
NUCLEOS_OCR = int(os.environ.get("UFIL_NUCLEOS", os.cpu_count() or 2))

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

# Confianza mínima del detector de orientación para tomar en cuenta su sugerencia. Es
# baja a propósito: la decisión no la toma el detector sino el resultado de releer la
# página girada (ver `enderezar_si_mejora`), así que acá alcanza con una pista.
CONFIANZA_ORIENTACION = 0.6

# Cuánto tiene que mejorar la confianza de la lectura para quedarse con la página
# girada. Sin este margen, el ruido decidiría la orientación.
MEJORA_MINIMA_GIRO = 0.12

# Debajo de esta confianza, una página con tinta se considera mal leída y se sospecha
# que esté de costado. Medido: página derecha 0,91–0,96; rotada 0,40–0,54.
CONFIANZA_SOSPECHA = 0.75

# Umbral por debajo del cual la celda se marca con trama en la interfaz.
UMBRAL_CONFIANZA = 0.85

# Confianza mínima que le exigimos a la relectura focalizada para que su discrepancia
# levante un CONFLICTO. Por debajo de esto, discrepar sólo castiga la confianza del
# campo y lo manda a revisión. El motivo es empírico: con el alfabeto restringido la
# relectura es muy buena cuando está segura y bastante ruidosa cuando no, y un
# conflicto por ruido le cuesta al equipo el mismo tiempo que uno de verdad.
UMBRAL_FOCAL_CONFLICTO = 0.80

# Relectura focalizada de campos dudosos. Medida sobre el corpus sintético de 200 DPI:
# como tercera opinión de rutina PIERDE contra la lectura de página (84,6% contra
# 94,7%), porque agrandar y binarizar un recorte no agrega información que no esté en
# el píxel. Queda encendida sólo como DESEMPATE de campos ya dudosos y de alfabeto
# restringido, donde no cuesta exactitud y ofrece una segunda candidata para elegir.
# Sobre escaneos reales de 300 DPI puede rendir distinto: hay que volver a medirlo.
RELECTURA_FOCAL = True

# Campos críticos: los únicos que exigen doble lectura y tolerancia cero al
# error silencioso (ver docs/00-fase-0.md §6).
CAMPOS_CRITICOS = ("nombre", "documento", "fecha_inicio", "fecha_fin", "monto")

# Rango de años considerado plausible para una fecha de contrato. Fuera de esto
# NO se corrige nada: se marca como sospechosa y la mira una persona.
ANIO_MIN, ANIO_MAX = 1983, 2100
