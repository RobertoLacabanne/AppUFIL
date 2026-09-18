"""
Qué etapa produjo cada resultado, con qué versión y con qué configuración.

Por qué existe
--------------
El sistema va a recibir documentación durante años, y cada tanto va a aprender a hacer
algo que antes no hacía: un tipo documental nuevo, un extractor mejor, otra forma de
leer una tabla. Cuando eso pasa, los PDF que ya están cargados tienen que poder
aprovecharlo **sin volver a subirlos y sin volver a leerlos enteros**.

Para eso hace falta poder responder una pregunta que hoy el sistema no se puede hacer:
*«esto que está guardado, ¿lo produjo el algoritmo que tengo ahora?»*. Hasta acá la
respuesta era «hay una fila, así que sí», y eso es distinto: una fila dice que ALGUNA
vez se procesó, no que siga vigente. Con ese criterio, mejorar el OCR no vuelve a leer
nada y agregar un extractor no alcanza a lo viejo.

Cada etapa lleva entonces dos cosas:

  * `version` — un número que sube UNA PERSONA cuando cambia el algoritmo a propósito.
  * `firma()` — una huella de la configuración que de verdad altera el resultado.

Las dos juntas forman el **sello** de la etapa. Un resultado guardado con otro sello es
un resultado viejo, y eso se sabe sin adivinarlo.

Cómo se calcula la firma, y por qué no es igual para todas
----------------------------------------------------------
Hay dos maneras de saber que un algoritmo cambió, y cada una se paga distinto:

  * **Por configuración declarada.** Se listan las perillas que afectan la salida
    (idioma del OCR, DPI, versión del motor) y se las resume. Es precisa: no se dispara
    porque alguien corrigió un comentario.
  * **Por el código fuente del módulo.** Se resume el archivo que implementa la etapa.
    Atrapa cualquier cambio real, incluido el que nadie se acordó de declarar, pero
    también se dispara con un comentario.

La lectura —el OCR— usa la primera, porque es lo caro: volver a leer cinco mil fojas
porque alguien tocó una docstring es exactamente lo que este módulo existe para evitar.
Las etapas derivadas usan la segunda, porque recalcularlas cuesta segundos y el riesgo
que importa es el otro: que una mejora quede sin aplicarse y nadie se entere.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from . import config

# Estados de una etapa sobre un resultado. Son los del pliego (§22): hacen falta los
# siete porque un lote grande se corta, se reanuda y falla de a pedazos.
PENDIENTE = "pendiente"
CORRIENDO = "corriendo"
PARCIAL = "parcial"
TERMINADO = "terminado"
DESACTUALIZADO = "desactualizado"
FALLIDO = "fallido"
DETENIDO = "detenido"

# Marca de un resultado que YA estaba en la base antes de que existiera el sellado. No
# se volvió a calcular: se adoptó. Ver `adoptar_lo_que_ya_estaba` en actualizacion.py.
HEREDADO = "heredado"


def _resumen(datos) -> str:
    """Huella corta y estable de cualquier cosa serializable."""
    crudo = json.dumps(datos, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:16]


def _fuente(*nombres: str) -> str:
    """
    Huella del código fuente de uno o varios módulos de `ufil/`.

    Se lee el archivo, no el módulo importado: lo que interesa es si el algoritmo
    cambió entre dos instalaciones, y eso está en el texto. Si el archivo no está
    —instalación empaquetada de otra forma— se devuelve una marca que NO cambia sola,
    para no desactualizar todo el acervo por no haber podido leer un `.py`.
    """
    h = hashlib.sha256()
    for nombre in sorted(nombres):
        ruta = Path(__file__).resolve().parent / nombre
        try:
            h.update(ruta.read_bytes())
        except OSError:
            h.update(b"__sin_fuente__" + nombre.encode("utf-8"))
    return h.hexdigest()[:16]


def _version_motor(que: str) -> str:
    """
    Versión del motor externo, sin hacer caer nada si el motor no está.

    En una máquina sin Tesseract esto devuelve `desconocido` en vez de reventar. Que
    falte el OCR es un problema de instalación que ya informa `ufil diagnostico`; no
    tiene por qué impedir mirar en qué estado quedó el acervo.
    """
    try:
        if que == "tesseract":
            import pytesseract
            return str(pytesseract.get_tesseract_version()).split()[0]
        if que == "pymupdf":
            import fitz
            return str(fitz.VersionBind)
    except Exception:
        return "desconocido"
    return "desconocido"


# ──────────────────────────────────────────────────────── las firmas por etapa ──
def _firma_lectura() -> str:
    """
    Lo que de verdad cambia lo que el OCR lee. Declarado a mano y a propósito.

    Cada entrada de acá vale horas de trabajo de máquina sobre un acervo grande, así
    que no se pone nada que no altere el resultado. Y al revés: lo que sí lo altera
    tiene que estar, porque lo que no está acá es una mejora que nunca se aplica.
    """
    return _resumen({
        "idioma": config.OCR_IDIOMA,
        "ocr": config.OCR_CONFIG,
        "dpi": config.DPI_RENDER,
        "orientacion": config.CONFIANZA_ORIENTACION,
        "giro": config.MEJORA_MINIMA_GIRO,
        "sospecha": config.CONFIANZA_SOSPECHA,
        "tesseract": _version_motor("tesseract"),
        "pymupdf": _version_motor("pymupdf"),
    })


def _firma_ingesta() -> str:
    return _fuente("capa0_ingesta.py", "huella.py")


def _firma_clasificacion() -> str:
    return _fuente("clasificacion.py")


def _firma_segmentacion() -> str:
    """
    La segmentación depende de las reglas de tramo Y de qué perfiles existen: un perfil
    nuevo que declara un tipo de foja cambia dónde empieza y termina cada pieza.
    """
    perfiles = {}
    try:
        for p in sorted(config.PERFILES.glob("*.json")):
            perfiles[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()[:12]
    except OSError:
        pass
    return _resumen({"reglas": _fuente("clasificacion.py"), "perfiles": perfiles})


def _firma_extraccion() -> str:
    perfiles = {}
    try:
        for p in sorted(config.PERFILES.glob("*.json")):
            perfiles[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()[:12]
    except OSError:
        pass
    return _resumen({
        "codigo": _fuente("capa2_extraccion.py", "capa2_campos.py", "manuscrito.py"),
        "perfiles": perfiles,
        "umbral": config.UMBRAL_CONFIANZA,
        "focal": (config.RELECTURA_FOCAL, config.UMBRAL_FOCAL_CONFLICTO),
        "criticos": list(config.CAMPOS_CRITICOS),
        "anios": (config.ANIO_MIN, config.ANIO_MAX),
    })


def _firma_foliatura() -> str:
    return _fuente("foliatura.py")


def _firma_tablas() -> str:
    return _fuente("tablas.py")


def _firma_cotejo() -> str:
    return _fuente("cotejo_letras.py", "castellano.py")


def _firma_normalizacion() -> str:
    return _fuente("capa2_campos.py", "castellano.py")


def _firma_identidad() -> str:
    return _fuente("capa3_identidad.py", "identidad.py")


def _firma_cronologia() -> str:
    return _fuente("cronologia.py")


def _firma_indice() -> str:
    return _fuente("busqueda.py")


def _firma_interpretacion() -> str:
    return _fuente("capa5_interpretacion.py")


@dataclass(frozen=True)
class Etapa:
    clave: str
    nombre: str                     # cómo se llama en la pantalla, en castellano
    alcance: str                    # archivo | pagina | documento | legajo
    version: int                    # la sube una persona al cambiar el algoritmo
    _firma: object                  # función que devuelve la huella de configuración
    depende_de: tuple = ()
    caro: bool = False              # ¿cuesta minutos u horas rehacerlo?
    # ¿Se adopta lo que ya está cuando no tiene sello, en vez de rehacerlo?
    #
    # Vale para dos casos y nada más: lo que no se puede rehacer —los originales son
    # inmutables, volver a ingerirlos no produce nada distinto— y lo que cuesta horas.
    # En una etapa que cuesta segundos adoptar no ahorra nada y cuesta la verdad: es
    # mejor recalcularla y saber con qué se hizo.
    adopta: bool = False
    explica: str = ""               # qué se pierde y qué se gana al rehacerla

    def firma(self) -> str:
        return self._firma()

    def sello(self) -> str:
        """Versión y configuración, juntas. Es lo que se guarda y lo que se compara."""
        return f"{self.version}:{self.firma()}"


# ─────────────────────────────────────────────────────────── el registro real ──
# El orden es el de dependencia: cada etapa sólo puede depender de las de más arriba.
#
# Estas son las etapas que HOY existen en el código, no las que nos gustaría tener. El
# pliego (§8) enumera quince conceptos; varios todavía no tienen implementación
# separada —layout, foliatura, tablas, relaciones, cronología— y registrarlos acá
# vacíos sería decir que el sistema los versiona cuando no los hace. Se agregan cuando
# existan, que es justamente lo que este módulo vuelve barato.
ETAPAS: tuple[Etapa, ...] = (
    Etapa("ingesta", "Incorporación del archivo", "archivo", 1, _firma_ingesta,
          depende_de=(), caro=False, adopta=True,
          explica="Qué archivos entraron, con su hash y sus fojas."),
    Etapa("lectura", "Lectura de las fojas (OCR)", "pagina", 1, _firma_lectura,
          depende_de=("ingesta",), caro=True, adopta=True,
          explica="Lo caro. Sobre un acervo grande son horas: no se rehace sin motivo."),
    Etapa("clasificacion", "Qué es cada foja", "archivo", 1, _firma_clasificacion,
          depende_de=("lectura",), caro=False,
          explica="Contrato, factura, decreto, foja en blanco. Se recalcula en segundos."),
    Etapa("segmentacion", "Dónde empieza y termina cada pieza", "archivo", 1,
          _firma_segmentacion, depende_de=("clasificacion",), caro=False,
          explica="Un PDF puede traer varias piezas; una pieza puede ocupar varias fojas."),
    Etapa("foliatura", "La foliatura que tiene el papel", "archivo", 1, _firma_foliatura,
          depende_de=("lectura",), caro=False,
          explica="El número escrito en la foja, que NO es la página del PDF."),
    Etapa("tablas", "Las tablas del documento", "archivo", 1, _firma_tablas,
          depende_de=("lectura", "segmentacion"), caro=False,
          explica="Filas, columnas y celdas, cada una con su lugar en la foja."),
    Etapa("cotejo", "El número escrito dos veces", "archivo", 1, _firma_cotejo,
          depende_de=("lectura", "clasificacion"), caro=False,
          explica="Letras contra dígitos, sobre el texto de cada foja."),
    Etapa("extraccion", "Los campos de cada pieza", "archivo", 1, _firma_extraccion,
          depende_de=("segmentacion",), caro=False,
          explica="Lo que se lee de cada pieza, con su anclaje al folio."),
    Etapa("normalizacion", "Fechas, importes y documentos normalizados", "archivo", 1,
          _firma_normalizacion, depende_de=("extraccion",), caro=False,
          explica="No pisa el literal: vive al lado."),
    Etapa("identidad", "Personas y empresas consolidadas", "legajo", 1, _firma_identidad,
          depende_de=("normalizacion",), caro=False,
          explica="Quién es quién. Las fusiones dudosas se proponen, no se deciden solas."),
    Etapa("cronologia", "La línea de tiempo", "legajo", 1, _firma_cronologia,
          depende_de=("normalizacion",), caro=False,
          explica="Qué pasó y cuándo, que no es el orden en que están las fojas."),
    Etapa("indice", "Índice de búsqueda", "legajo", 1, _firma_indice,
          depende_de=("lectura",), caro=False,
          explica="Se rehace sobre lo ya leído: no vuelve a pasar el OCR."),
    Etapa("interpretacion", "Patrones y señalamientos", "legajo", 1, _firma_interpretacion,
          depende_de=("identidad", "extraccion"), caro=False,
          explica="El carril de conjeturas. Siempre con su fuente."),
)

POR_CLAVE: dict[str, Etapa] = {e.clave: e for e in ETAPAS}
CLAVES: tuple[str, ...] = tuple(e.clave for e in ETAPAS)


class EtapaDesconocida(ValueError):
    """
    Pidieron rehacer una etapa que no existe.

    Es `ValueError` y no `KeyError` por una razón que se ve del lado de quien lo usa:
    `str()` de un `KeyError` devuelve el mensaje entre comillas —es el `repr` de su
    argumento— y eso llega tal cual a la pantalla, que termina mostrando
    «'etapa desconocida: x'» con comillas de más. El mensaje es para una persona.
    """


def etapa(clave: str) -> Etapa:
    try:
        return POR_CLAVE[clave]
    except KeyError:
        raise EtapaDesconocida(
            f"etapa desconocida: {clave}. Las que hay son: "
            + ", ".join(CLAVES)) from None


def dependientes(clave: str) -> tuple[str, ...]:
    """
    Todas las etapas que dependen de ésta, directa o indirectamente, en orden.

    Es lo que permite la invalidación SELECTIVA: si cambia el OCR hay que rehacer lo que
    se apoya en la lectura, y nada más. Si cambia la interpretación, no se toca el OCR.
    """
    alcanzadas: list[str] = []
    frente = {clave}
    for e in ETAPAS:                       # en orden de dependencia, una sola pasada
        if e.clave in frente:
            continue
        if any(d in frente for d in e.depende_de):
            frente.add(e.clave)
            alcanzadas.append(e.clave)
    return tuple(alcanzadas)


def cadena(clave: str) -> tuple[str, ...]:
    """La etapa y todo lo que depende de ella, en orden de ejecución."""
    return (clave,) + dependientes(clave)


def sellos() -> dict[str, str]:
    """El sello vigente de cada etapa. Se calcula una vez por corrida: `firma()` lee
    archivos del disco y no tiene sentido pagarlo por página."""
    return {e.clave: e.sello() for e in ETAPAS}
