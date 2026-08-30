"""
Parsers de campo. Cada uno devuelve (literal, normalizado, motivo_si_falla).

REGLA QUE GOBIERNA TODO ESTE ARCHIVO (restricción 3): ante la duda, se devuelve
`ambiguo`. Nunca se completa, nunca se corrige un carácter, nunca se elige la
interpretación más probable. Un monto "corregido" contamina todos los acumulados
sin que nadie se entere; un monto marcado ambiguo cuesta treinta segundos de
revisión. La asimetría es deliberada.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

from . import config


def sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def normalizar_cotejo(s: str) -> str:
    """Forma canónica para COMPARAR (rótulos, cotejo entre rutas). No se guarda."""
    s = sin_tildes(s).upper()
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ───────────────────────────────────────────────────────────────────── texto ──
def parse_texto(bruto: str):
    limpio = re.sub(r"\s+", " ", bruto).strip(" .,;:_-|")
    if len(limpio) < 2:
        return None, None, "ilegible"
    return limpio, normalizar_cotejo(limpio), None


def parse_nombre(bruto: str):
    literal, _, motivo = parse_texto(bruto)
    if motivo:
        return None, None, motivo
    # La forma normalizada colapsa tildes, puntuación y espacios. El literal NO se toca.
    norm = normalizar_cotejo(literal)
    if not re.search(r"[A-Z]{2}", norm):
        return None, None, "ilegible"
    return literal, norm, None


# ──────────────────────────────────────────────────────────────── documento ──
def parse_documento(bruto: str):
    """CUIL/CUIT (11 dígitos) o DNI (7-8). Sin relleno ni recorte: o es, o es ambiguo."""
    literal = re.sub(r"\s+", " ", bruto).strip(" .,;:_-|")
    if not literal:
        return None, None, "ausente"
    digitos = re.sub(r"\D", "", literal)
    if not digitos:
        return None, None, "ilegible"
    if len(digitos) == 11:
        return literal, f"CUIL:{digitos}", None
    if len(digitos) in (7, 8):
        return literal, f"DNI:{digitos}", None
    # 10 o 12 dígitos: falta o sobra uno. NO se completa ni se recorta.
    return literal, None, "ambiguo"


# ─────────────────────────────────────────────────── CUIT, CUIL y el DNI adentro ──
# Un CUIL de persona se construye como PREFIJO + DNI + DÍGITO VERIFICADOR: en
# 27-27200341-1, los ocho del medio SON el DNI 27200341. No es una inferencia ni un
# parecido: es cómo se arma el número.
#
# Eso importa mucho acá. El contrato identifica al contratado por DNI y la factura lo
# identifica por CUIT. Sin esta equivalencia, la misma persona entra dos veces y el
# pago nunca se cruza con el contrato que lo justifica, que es exactamente el cruce que
# el caso necesita.
#
# Los prefijos 30, 33 y 34 son de PERSONA JURÍDICA y no llevan DNI adentro: ahí no hay
# nada que extraer y la clave sigue siendo el CUIT entero.
PREFIJOS_PERSONA = {"20", "23", "24", "27"}
PREFIJOS_EMPRESA = {"30", "33", "34"}


def dni_de_cuil(digitos: str) -> str | None:
    """El DNI que lleva adentro un CUIL de persona. None si es de empresa o no calza."""
    if len(digitos) != 11 or digitos[:2] not in PREFIJOS_PERSONA:
        return None
    return digitos[2:10].lstrip("0") or None


def cuit_valido(digitos: str) -> bool:
    """
    ¿El dígito verificador cierra?

    Es la misma idea que el monto escrito en números y en letras: el documento trae
    consigo con qué comprobarse. Un CUIT que no cierra casi siempre es un dígito mal
    leído, y usarlo como clave de identidad uniría o separaría personas por un error de
    OCR. Acá NO se corrige: se informa, y el campo va a revisión.
    """
    if len(digitos) != 11 or not digitos.isdigit():
        return False
    pesos = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    suma = sum(int(d) * p for d, p in zip(digitos, pesos))
    resto = 11 - (suma % 11)
    esperado = 0 if resto == 11 else (9 if resto == 10 else resto)
    return esperado == int(digitos[10])


def clave_de_persona(doc_norm: str | None) -> str | None:
    """
    La clave con la que dos documentos hablan de la misma persona.

    Colapsa el CUIL de una factura y el DNI de un contrato al MISMO valor, que es lo
    que permite que el pago encuentre al contrato. Para una empresa devuelve el CUIT
    entero, porque ahí no hay DNI.
    """
    if not doc_norm or ":" not in doc_norm:
        return None
    tipo, numero = doc_norm.split(":", 1)
    if tipo in ("CUIL", "CUIT"):
        dni = dni_de_cuil(numero)
        return f"DNI:{dni}" if dni else f"CUIT:{numero}"
    if tipo == "DNI":
        return f"DNI:{numero.lstrip('0') or numero}"
    return doc_norm


# ───────────────────────────────────────────────────────────────────── fecha ──
_FECHA = re.compile(r"\b(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{2,4})\b")


def parse_fecha(bruto: str):
    """Formato dd/mm/aaaa. No se sustituye ningún carácter: si trae letras, es ambigua."""
    limpio = re.sub(r"\s+", " ", bruto).strip(" .,;:_-|")
    if not limpio:
        return None, None, "ausente"
    m = _FECHA.search(limpio)
    if not m:
        return limpio, None, "ambiguo"
    d, mes, a = (int(g) for g in m.groups())
    if len(m.group(3)) == 2:
        # Un año de dos dígitos es genuinamente ambiguo. No se decide el siglo.
        return limpio, None, "ambiguo"
    try:
        f = date(a, mes, d)
    except ValueError:
        return limpio, None, "ambiguo"
    if not (config.ANIO_MIN <= a <= config.ANIO_MAX):
        # Fuera de rango plausible: NO se corrige. Se guarda y se marca sospechosa
        # más adelante, en la consulta de fechas imposibles.
        return limpio, f.isoformat(), None
    return limpio, f.isoformat(), None


# ───────────────────────────────────────────────────────────────────── monto ──
_MONTO = re.compile(r"[\d][\d.,\s]*")


def parse_monto(bruto: str):
    """
    Devuelve el monto en CENTAVOS (entero) para que no haya coma flotante en ningún
    acumulado. Separadores ambiguos -> `ambiguo`, nunca una suposición.
    """
    limpio = re.sub(r"\s+", " ", bruto).strip(" .,;:_-|")
    if not limpio:
        return None, None, "ausente"
    sin_signo = limpio.replace("$", " ").strip()
    m = _MONTO.search(sin_signo)
    if not m:
        return limpio, None, "ilegible"
    crudo = re.sub(r"\s", "", m.group(0)).strip(".,")
    if not re.fullmatch(r"[\d.,]+", crudo) or not any(c.isdigit() for c in crudo):
        return limpio, None, "ambiguo"

    seps = [c for c in crudo if c in ".,"]
    if not seps:
        return limpio, str(int(crudo) * 100), None

    ultimo = crudo.rfind(seps[-1])
    decimales = len(crudo) - ultimo - 1
    hay_mas_de_uno = len(seps) > 1

    if decimales == 2 and (hay_mas_de_uno or seps[-1] == ","):
        entero = re.sub(r"\D", "", crudo[:ultimo])
        cent = crudo[ultimo + 1:]
        if not entero:
            return limpio, None, "ambiguo"
        return limpio, str(int(entero) * 100 + int(cent)), None
    if decimales == 3 and seps[-1] in ".,":
        # Separador de miles: 74.200 son setenta y cuatro mil doscientos pesos.
        return limpio, str(int(re.sub(r"\D", "", crudo)) * 100), None
    # 74.20 / 74,2 / 1.234.5 -> no se decide.
    return limpio, None, "ambiguo"


# ─────────────────────────────────────────────── fecha escrita con palabras ──
# Los contratos de la Legislatura no traen la fecha en un casillero dd/mm/aaaa: la
# escriben adentro del texto, «el día 01 de julio de 2016». Es igual de exacta —más,
# incluso, porque el mes en letras no se confunde con otro número— pero hay que saber
# leerla. Los meses se escriben como los escribe el documento, sin tildes, porque el
# OCR se las come la mitad de las veces.
MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_FECHA_PALABRAS = re.compile(
    r"(\d{1,2})\s*(?:\([^)]*\)\s*)?(?:d[ií]as?\s+)?del?\s+(?:mes\s+de\s+)?"
    r"([a-zA-ZáéíóúÁÉÍÓÚ]+)\s+(?:del?\s+)?(?:año\s+)?(\d{4})", re.I)


def parse_fecha_texto(bruto: str):
    """
    «01 de julio de 2016», «01 (uno) días del mes de julio del año 2016».

    Si el mes no está entre los doce, es ambigua: no se elige el más parecido. Un mes
    adivinado corre un contrato entero de lugar en la línea de tiempo, y la
    superposición que buscamos se calcula con eso.
    """
    limpio = re.sub(r"\s+", " ", bruto).strip(" .,;:_-|")
    if not limpio:
        return None, None, "ausente"
    m = _FECHA_PALABRAS.search(limpio)
    if not m:
        # Puede venir igual en dd/mm/aaaa; se prueba con el parser de siempre.
        return parse_fecha(limpio)
    dia, mes_txt, anio = m.group(1), sin_tildes(m.group(2)).lower(), m.group(3)
    mes = MESES.get(mes_txt)
    if not mes:
        return limpio, None, "ambiguo"
    try:
        f = date(int(anio), mes, int(dia))
    except ValueError:
        return limpio, None, "ambiguo"
    return limpio, f.isoformat(), None


# El encabezado del contrato escribe también el AÑO en palabras: «del año dos mil
# dieciseis». Se lee con la misma tabla de números que el monto en letras.
_FECHA_ANIO_LETRAS = re.compile(
    r"(\d{1,2})\s*(?:\([^)]*\)\s*)?d[ií]as?\s+del?\s+mes\s+de\s+"
    r"([a-zA-ZáéíóúÁÉÍÓÚ]+)\s+del?\s+a[nñ]o\s+([a-zA-ZáéíóúÁÉÍÓÚ\s]{6,40}?)\s*[,.]", re.I)


def parse_fecha_anio_en_letras(bruto: str):
    """«a los 01 (uno) días del mes de julio del año dos mil dieciseis,»"""
    limpio = re.sub(r"\s+", " ", bruto).strip()
    m = _FECHA_ANIO_LETRAS.search(limpio)
    if not m:
        return parse_fecha_texto(limpio)
    dia, mes_txt, anio_txt = m.group(1), sin_tildes(m.group(2)).lower(), m.group(3)
    mes = MESES.get(mes_txt)
    centavos = monto_en_letras(anio_txt)          # misma tabla de números
    if not mes or centavos is None:
        return limpio, None, "ambiguo"
    anio = centavos // 100
    try:
        f = date(anio, mes, int(dia))
    except ValueError:
        return limpio, None, "ambiguo"
    if not (config.ANIO_MIN <= anio <= config.ANIO_MAX):
        return limpio, None, "ambiguo"
    return limpio, f.isoformat(), None


# ─────────────────────────────────────────────── monto escrito con palabras ──
# El contrato escribe el monto DOS VECES: «$72000.- (Pesos, Setenta y dos mil)». Eso
# es una verificación cruzada que el documento trae de fábrica, y es más fuerte que
# cotejar dos rutas de OCR: si los dígitos y las letras coinciden, el número es ese.
# Si discrepan, hay un conflicto de verdad y lo mira una persona.
UNIDADES = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19,
    "veinte": 20, "veintiuno": 21, "veintiun": 21, "veintidos": 22,
    "veintitres": 23, "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26,
    "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
    "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
    "setenta": 70, "ochenta": 80, "noventa": 90,
    "cien": 100, "ciento": 100, "doscientos": 200, "trescientos": 300,
    "cuatrocientos": 400, "quinientos": 500, "seiscientos": 600,
    "setecientos": 700, "ochocientos": 800, "novecientos": 900,
}
MULTIPLICA = {"mil": 1000, "millon": 1000000, "millones": 1000000}


def monto_en_letras(bruto: str) -> int | None:
    """
    «Setenta y dos mil» -> 7200000 centavos. None si no se entiende del todo.

    No adivina: cualquier palabra que no esté en la tabla invalida la lectura entera.
    Esta función existe para CONFIRMAR el número escrito en dígitos, y una confirmación
    que se inventa la mitad no confirma nada.
    """
    limpio = sin_tildes(re.sub(r"[^\w\s]", " ", bruto)).lower()
    palabras = [p for p in limpio.split() if p not in ("y", "pesos", "peso", "con")]
    if not palabras:
        return None
    total, parcial = 0, 0
    for p in palabras:
        if p in UNIDADES:
            parcial += UNIDADES[p]
        elif p in MULTIPLICA:
            factor = MULTIPLICA[p]
            if factor == 1000:
                parcial = (parcial or 1) * 1000
            else:
                total += (parcial or 1) * factor
                parcial = 0
        elif p in ("centavos", "ctvos"):
            break
        else:
            return None                       # una palabra desconocida invalida todo
    valor = total + parcial
    return valor * 100 if valor else None


def parse_monto_letras(bruto: str):
    """Devuelve el monto en centavos leído de las palabras, o ambiguo."""
    limpio = re.sub(r"\s+", " ", bruto).strip(" .,;:_-|()")
    if not limpio:
        return None, None, "ausente"
    v = monto_en_letras(limpio)
    if v is None:
        return limpio, None, "ambiguo"
    return limpio, str(v), None


PARSERS = {
    "texto": parse_texto,
    "nombre": parse_nombre,
    "documento": parse_documento,
    "fecha": parse_fecha,
    "monto": parse_monto,
    "fecha_texto": parse_fecha_texto,
    "monto_letras": parse_monto_letras,
    "fecha_anio_letras": parse_fecha_anio_en_letras,
}
PARSERS["texto"] = parse_texto
