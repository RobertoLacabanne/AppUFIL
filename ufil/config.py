"""Configuración y constantes. Todo por ruta relativa: el proyecto es portable."""
from __future__ import annotations
import os
import threading
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Los derivados NUNCA se escriben adentro del corpus (restricción 2).
DATOS      = Path(os.environ.get("UFIL_DATOS", RAIZ / "datos"))

# Lo que es del programa y no del legajo: mismo lugar siempre, no se mueve al cambiar
# de causa. Son constantes de verdad y por eso quedan acá arriba, lejos del bloque de
# rutas dinámicas: si alguna de estas se resolviera por hilo, un pedido sin legajo
# activo se quedaría sin esquema y sin interfaz.
ESQUEMA    = RAIZ / "ufil" / "esquema.sql"
CONSULTAS  = RAIZ / "ufil" / "consultas"
PERFILES   = RAIZ / "ufil" / "perfiles"
WEB        = RAIZ / "ufil" / "web"
FUENTES    = RAIZ / "assets" / "fuentes"
MARCA      = RAIZ / "assets" / "marca"

# ── El legajo activo ────────────────────────────────────────────────────────
# Cada legajo tiene su propia base y su propia carpeta de derivados (ver
# ufil/legajos.py). Cuál está activo se guarda POR HILO, no en una variable global:
# el servidor atiende pedidos en varios hilos y el procesamiento corre en otro, así
# que un valor compartido significaría que abrir un legajo en una pestaña le cambia
# el legajo al trabajo que está corriendo en otra. Eso es exactamente la mezcla que la
# separación por archivo existe para evitar.
#
# `config.BASE` y `config.DERIVADOS` se siguen leyendo como siempre desde todo el
# código: el `__getattr__` de abajo las resuelve al vuelo según el hilo. Ningún
# llamador tuvo que cambiar.
_local = threading.local()
LEGAJO_POR_OMISION: str | None = os.environ.get("UFIL_LEGAJO", "").strip() or None
_BASE_FIJA = os.environ.get("UFIL_BASE", "").strip()


def legajo_activo() -> str | None:
    return getattr(_local, "legajo", LEGAJO_POR_OMISION)


def activar_legajo(slug: str | None) -> None:
    """Cambia el legajo sobre el que trabaja ESTE hilo. Base y derivados se mueven juntos."""
    _local.legajo = slug or None


def fijar_legajo_por_omision(slug: str | None) -> None:
    """
    El legajo con el que arranca cualquier hilo que no diga otra cosa.

    Es lo que fija `ufil --legajo X servir`: el proceso entero trabaja sobre ese legajo,
    incluidos los hilos de petición que nacen después. Se hace con una variable de
    módulo y no con la de hilo justamente porque tiene que alcanzar a hilos que todavía
    no existen.
    """
    global LEGAJO_POR_OMISION
    LEGAJO_POR_OMISION = slug or None


def carpeta_legajo(slug: str) -> Path:
    return DATOS / "legajos" / slug


def _base() -> Path:
    # UFIL_BASE fija manda sobre todo: es lo que usan las pruebas y las instalaciones
    # anteriores a los legajos, que trabajan con una base suelta.
    if _BASE_FIJA:
        return Path(_BASE_FIJA)
    slug = legajo_activo()
    return carpeta_legajo(slug) / "ufil.sqlite" if slug else DATOS / "ufil.sqlite"


def _derivados() -> Path:
    slug = legajo_activo()
    if slug and not _BASE_FIJA:
        return carpeta_legajo(slug) / "derivados"
    return _base().parent / "derivados"


def _originales() -> Path:
    """Dónde se guardan los PDF que entran por la interfaz, para ESTE legajo."""
    return _por_legajo("originales")


def _respaldos() -> Path:
    """
    Los respaldos también son por legajo.

    Con una sola carpeta común, `respaldo-2026-08-31.sqlite` de dos causas distintas se
    pisan entre sí, y el que restaure el archivo equivocado se entera cuando ya
    trabajó media mañana sobre la causa que no era.
    """
    return _por_legajo("respaldos")


def _export() -> Path:
    return _por_legajo("export")


def _por_legajo(sub: str) -> Path:
    slug = legajo_activo()
    if slug and not _BASE_FIJA:
        return carpeta_legajo(slug) / sub
    return DATOS / sub


_DINAMICAS = {"BASE": _base, "DERIVADOS": _derivados, "ORIGINALES": _originales,
              "RESPALDOS": _respaldos, "EXPORT": _export}


def __getattr__(nombre: str):
    """Resuelve BASE, DERIVADOS y ORIGINALES según el legajo activo en este hilo."""
    fn = _DINAMICAS.get(nombre)
    if fn is None:
        raise AttributeError(f"module {__name__!r} has no attribute {nombre!r}")
    return fn()


# Renderizado de páginas para el visor y para el OCR.
DPI_RENDER = int(os.environ.get("UFIL_DPI_RENDER", 200))
PT_POR_PULGADA = 72.0
ESCALA_RENDER = DPI_RENDER / PT_POR_PULGADA          # px por punto PDF

# Cuántas páginas se leen en paralelo. Medido en una máquina de cuatro núcleos:
# 1 hilo 1,04 s por página · 2 hilos 0,46 · 4 hilos 0,25 · 8 hilos 0,27.
# Más allá de la cantidad de núcleos no rinde: los procesos se pelean por el mismo CPU.
NUCLEOS_OCR = int(os.environ.get("UFIL_NUCLEOS", os.cpu_count() or 2))

# Cada cuántas páginas se confirma lo leído a la base. Menos que esto castiga el
# rendimiento por escribir de más; más que esto arriesga perder trabajo si se corta.
CONFIRMAR_CADA = 10

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
