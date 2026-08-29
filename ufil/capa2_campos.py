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


PARSERS = {
    "texto": parse_texto,
    "nombre": parse_nombre,
    "documento": parse_documento,
    "fecha": parse_fecha,
    "monto": parse_monto,
}
PARSERS["texto"] = parse_texto
