"""
Cómo se escriben los números en castellano, en un solo lugar.

Existe por una sola razón: «1 archivo(s)». Ese paréntesis aparecía en la interfaz, en la
terminal, en el informe .rtf y en la portada de la planilla, y es la marca de un sistema
que no se terminó de escribir. Un organismo que le manda a un juez un documento que dice
«1 contrato(s)» está diciendo, sin querer, que nadie lo leyó antes de mandarlo.

No es sólo el paréntesis: también «1 pares de contratos se pisan» y «1 contratos
quedaron afuera». Concordar bien cuesta una función.
"""
from __future__ import annotations


def plural(n: int, uno: str, muchos: str) -> str:
    """
    El número con la palabra que le corresponde.

        plural(1, "archivo", "archivos")  ->  «1 archivo»
        plural(3, "archivo", "archivos")  ->  «3 archivos»

    Se pasan las dos formas enteras y no un sufijo: en castellano el plural no siempre
    es agregar una «s» —«mes/meses», «lápiz/lápices»— y adivinarlo produce exactamente
    la clase de error que esto viene a arreglar.
    """
    return f"{miles(n)} {uno if abs(n) == 1 else muchos}"


def concordar(n: int, uno: str, muchos: str) -> str:
    """La palabra sola, sin el número. Para cuando el número ya se dijo antes."""
    return uno if abs(n) == 1 else muchos


def miles(n: int) -> str:
    """
    Separador de miles con punto, como se escribe acá: 1.234.567.

    `f"{n:,}"` da comas, que en castellano son el separador decimal: «1,234» se lee
    como uno coma doscientos treinta y cuatro.
    """
    return f"{n:,}".replace(",", ".")


def pesos(centavos: int | None) -> str:
    """Un importe en pesos, con coma decimal y punto de miles. `None` no se inventa."""
    if centavos is None:
        return "—"
    signo = "-" if centavos < 0 else ""
    entero, resto = divmod(abs(int(centavos)), 100)
    return f"{signo}${miles(entero)},{resto:02d}"


def fecha(iso: str | None) -> str:
    """
    Una fecha ISO como se escribe acá: 2023-03-01 -> 01/03/2023.

    La base guarda ISO porque ordena bien de forma nativa. Eso es una decisión de
    almacenamiento y no tiene por qué asomarse a una pantalla ni a un informe.
    """
    if not iso:
        return "—"
    s = str(iso)[:10]
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"
    return str(iso)


# Las cámaras se guardan como «A» y «B» porque así lo escribe el perfil de extracción.
# «Cámara A» en un informe obliga al lector a saber cuál es cuál.
CAMARA = {"A": "Diputados", "B": "Senadores"}


def camara(clave: str | None) -> str:
    return CAMARA.get(clave, clave or "sin cámara")
