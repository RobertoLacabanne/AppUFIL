"""
El mismo número, escrito dos veces por el mismo papel.

Un acto administrativo escribe cada cantidad dos veces, y eso no es una redundancia
burocrática: es una salvaguarda de trescientos años. «PESOS OCHO MILLONES TRESCIENTOS
DOCE MIL CIENTO UNO CON 91/100 ($8.312.101,91)» dice lo mismo en letras y en dígitos
justamente para que un cero de más no pase desapercibido.

Para este sistema eso es **una segunda lectura gratis y del propio documento**. El §12
exige dos rutas de lectura para dar un dato por firme; acá las dos rutas ya están
escritas en el papel, y no hace falta un segundo motor de OCR para tenerlas: alcanza
con leer las dos y compararlas.

Y cuando NO coinciden, es un hallazgo. En la memoria descriptiva del expediente 201.602
—iluminación LED sobre la Ruta Provincial 22— dice, dos veces:

    «Se prevé la instalación de 21 (VEINTIOCHO) luminarias del tipo LED»
    «Se instalarán 21 (VEINTIOCHO) columnas con un brazo de 2,50m»

El presupuesto de la misma obra cotiza 21 luminarias y 21 columnas. Alguien escribió
veintiocho donde dice veintiuno, en el documento que describe qué se compra, y nadie lo
vio. Esa clase de diferencia es exactamente lo que este sistema tiene que poner arriba
de la mesa, y no la puede encontrar un OCR: la encuentra quien compara las dos formas.

Lo que esto NO hace, y es la parte importante: NO elige cuál de las dos tiene razón.
Devuelve las dos, con lo que está escrito en cada una, y deja que decida una persona
mirando la foja. Un sistema que «corrige» veintiocho por veintiuno estaría inventando
un dato en un expediente penal.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .capa2_campos import monto_en_letras, parse_monto


@dataclass(frozen=True)
class Cotejo:
    """Un número escrito dos veces, y si las dos dicen lo mismo."""
    clase: str              # "monto" | "cantidad"
    letras: str             # tal como está en el papel
    digitos: str            # tal como está en el papel
    valor_letras: int | None    # centavos, o unidades×100 para una cantidad
    valor_digitos: int | None
    desde: int              # dónde empieza en el texto, para poder anclarlo

    @property
    def coinciden(self) -> bool | None:
        """`None` cuando alguna de las dos no se pudo leer: eso no es un desacuerdo."""
        if self.valor_letras is None or self.valor_digitos is None:
            return None
        return self.valor_letras == self.valor_digitos


# ── Las dos formas en que un acto administrativo escribe un número dos veces ──
#
# 1. EL IMPORTE. Las letras primero y los dígitos entre paréntesis:
#       «PESOS OCHO MILLONES … CON 91/100 ($8.312.101,91)»
#    El «PESOS» de arranque es lo que la distingue de una frase cualquiera que tenga
#    un número entre paréntesis.
_MONTO = re.compile(
    r"\bPESOS\s+(?P<letras>[A-ZÁÉÍÓÚÑa-záéíóúñ\s]{4,140}?"
    r"(?:CON\s+(?:\d{1,2}\s*/\s*100|[A-ZÁÉÍÓÚÑa-záéíóúñ\s]{1,40}?\s*CENTAVOS?))?)"
    r"\s*\(\s*(?P<digitos>\$?\s*[\d][\d.,]{0,20})\s*\.?\-?\s*\)",
    re.I | re.S)

# 2. LA CANTIDAD. Al revés: los dígitos primero y las letras entre paréntesis.
#       «21 (VEINTIOCHO) luminarias»   «1 (UNO) tableros generales»
#    Es la forma de escribir cantidades en un pliego, y es donde apareció la
#    diferencia de este expediente.
_CANTIDAD = re.compile(
    r"(?<![\d.,])(?P<digitos>\d{1,6})\s*\(\s*(?P<letras>[A-ZÁÉÍÓÚÑa-záéíóúñ\s]{3,60}?)\s*\)",
    re.I)


def _valor_digitos(bruto: str) -> int | None:
    """Los dígitos leídos en centavos, con el mismo parser que el resto del sistema."""
    _, norm, _ = parse_monto(bruto)
    try:
        return int(norm) if norm is not None else None
    except (TypeError, ValueError):
        return None


def cotejar(texto: str) -> list[Cotejo]:
    """
    Todos los números que el papel escribe dos veces, con su veredicto.

    El orden es el del texto: quien revisa lee la foja de arriba abajo, y una lista que
    saltea de un lado al otro de la página obliga a buscar cada uno.
    """
    fuera: list[Cotejo] = []
    for m in _MONTO.finditer(texto or ""):
        letras = re.sub(r"\s+", " ", m.group("letras")).strip(" .,;:-")
        digitos = re.sub(r"\s+", "", m.group("digitos"))
        fuera.append(Cotejo("monto", letras, digitos,
                            monto_en_letras(letras), _valor_digitos(digitos),
                            m.start()))
    for m in _CANTIDAD.finditer(texto or ""):
        letras = re.sub(r"\s+", " ", m.group("letras")).strip()
        # «(UNO)» sí; «(ver plano adjunto)» no. Si las palabras no son un número, esto
        # no es una cantidad escrita dos veces: es un paréntesis cualquiera.
        v = monto_en_letras(letras)
        if v is None:
            continue
        digitos = m.group("digitos")
        fuera.append(Cotejo("cantidad", letras, digitos, v, int(digitos) * 100,
                            m.start()))
    fuera.sort(key=lambda c: c.desde)
    return fuera


def discrepancias(texto: str) -> list[Cotejo]:
    """Sólo los que NO coinciden. Los que no se pudieron leer no son discrepancias."""
    return [c for c in cotejar(texto) if c.coinciden is False]
