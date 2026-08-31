"""
Qué es cada foja.

Por qué hace falta. El material real no viene en pilas prolijas de un tipo de documento:
un PDF trae la carátula del expediente, dos o tres contratos de obra, el decreto que los
aprueba, una nota de la Dirección de Administración y después quince facturas y recibos
de los mismos contratados. Y puede venir ordenado o mezclado.

Si el sistema no sabe qué es cada foja, pasa lo que pasó la primera vez que corrí esto
sobre un expediente de verdad: el último contrato se quedó con las diecinueve fojas que
venían atrás, facturas incluidas, y quedó registrado como un documento de diecinueve
páginas que no es.

Cómo lo decide. Por frases de molde, no por adivinanza. Cada tipo trae las expresiones
que aparecen en su encabezado y sólo ahí. Una foja que no coincide con ninguna se marca
`continuacion`: es la segunda hoja de lo que venía antes, y ese es el caso normal, no
una falla.

Lo que NO hace: inventar. Si una foja no se parece a nada y no viene detrás de nada,
queda `desconocida`, se cuenta y se muestra. Una foja que el sistema no entiende tiene
que ser visible, no silenciosa.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .capa2_campos import normalizar_cotejo


@dataclass(frozen=True)
class Tipo:
    clave: str
    etiqueta: str
    # Frases que identifican el ARRANQUE de un documento de este tipo. Se comparan
    # sobre el texto normalizado (sin tildes, mayúsculas, sin puntuación).
    marcas: tuple[str, ...]
    # Si es True, este tipo arranca un documento nuevo. Si es False, es material de
    # contexto que se adjunta al documento con el que viaja.
    arranca: bool = True
    # Cuántas fojas suele tener. Sirve de tope de seguridad, no de regla: si el
    # documento sigue, sigue; pero no se traga media pila por un arranque no detectado.
    fojas_tipicas: int = 2


TIPOS: tuple[Tipo, ...] = (
    Tipo("contrato_obra", "Contrato de obra",
         ("CONTRATO DE OBRA", "CONTRATO DEOBRA"), fojas_tipicas=2),
    Tipo("contrato_locacion", "Contrato de locación",
         ("CONTRATO DE LOCACION DE SERVICIOS", "CONTRATO DE LOCACION"), fojas_tipicas=2),
    Tipo("factura", "Factura",
         ("FACTURA", "FACTURA C", "FACTURA B", "FACTURA A"), fojas_tipicas=1),
    Tipo("recibo", "Recibo", ("RECIBO",), fojas_tipicas=1),
    Tipo("remito", "Remito", ("REMITO",), fojas_tipicas=1),
    Tipo("rendicion", "Rendición",
         ("RENDICION DE CUENTAS", "RENDICION DE GASTOS"), fojas_tipicas=2),
    Tipo("decreto", "Decreto", ("DECRETO N",), fojas_tipicas=2),
    Tipo("resolucion", "Resolución", ("RESOLUCION N",), fojas_tipicas=2),
    # Contexto: no arrancan un documento, viajan con el que tienen al lado.
    Tipo("caratula", "Carátula",
         ("PERIODO LEGISLATIVO", "EXPEDIENTE N", "INICIADOR", "ANEXO I", "ANEXO II"),
         arranca=False, fojas_tipicas=1),
    Tipo("nota", "Nota",
         ("ME DIRIJO A USTED", "NOTA DE ELEVACION", "TENGO EL AGRADO"),
         arranca=False, fojas_tipicas=1),
)

TIPOS_POR_CLAVE = {t.clave: t for t in TIPOS}
ETIQUETAS = {t.clave: t.etiqueta for t in TIPOS}
ETIQUETAS["continuacion"] = "Continuación"
ETIQUETAS["desconocida"] = "Sin reconocer"


# ═══════════════════════════════════════════════════════════════════════════
# UN CONTRATO NO ES UNA FACTURA, Y SUS PLATAS NO SE SUMAN
# ═══════════════════════════════════════════════════════════════════════════
# Los dos traen un nombre, un CUIT y un monto, y los dos salen del mismo PDF. Pero
# dicen cosas distintas: el contrato dice cuánto se PACTÓ pagar, la factura dice cuánto
# se COBRÓ. Sumarlos no da un total más completo: da un número que no corresponde a
# nada. Y cuando la factura es el cobro de ese mismo contrato —que es el caso normal—
# sumarlos cuenta la misma plata dos veces.
#
# Medido sobre un legajo con un contrato de $10.000 y su factura de $2.500: el
# acumulado decía $12.500 y el panel decía «2 contratos». Ninguna de las dos cosas era
# cierta.
#
# `documento.tipo` sale del perfil que extrajo el documento. Estas familias son la
# única fuente de verdad sobre a qué carril va cada tipo; las vistas del esquema y las
# consultas las usan a través de las constantes SQL de abajo, para que agregar un tipo
# nuevo no obligue a acordarse de seis lugares.
FAMILIA_CONTRATO = "contrato"        # lo pactado
FAMILIA_COMPROBANTE = "comprobante"  # lo cobrado
FAMILIA_ACTO = "acto"                # decretos, resoluciones: ni una cosa ni la otra

TIPOS_CONTRATO = frozenset({"contrato_obra", "contrato_personal", "contrato_locacion"})
TIPOS_COMPROBANTE = frozenset({"factura", "recibo", "remito"})
TIPOS_ACTO = frozenset({"decreto", "resolucion", "rendicion"})

ETIQUETA_FAMILIA = {
    FAMILIA_CONTRATO: "Contrato",
    FAMILIA_COMPROBANTE: "Comprobante de pago",
    FAMILIA_ACTO: "Acto administrativo",
}


def familia(tipo: str | None) -> str | None:
    """
    A qué carril va un tipo de documento. `None` si no lo conocemos.

    Devolver `None` y no adivinar es la parte importante: un tipo que no está en
    ninguna familia NO se suma a ningún total ni se esconde. Se cuenta aparte y se
    muestra, porque un documento que el sistema no sabe clasificar tiene que ser
    visible. Meterlo en la familia más probable sería exactamente inventar un dato.
    """
    if tipo in TIPOS_CONTRATO:
        return FAMILIA_CONTRATO
    if tipo in TIPOS_COMPROBANTE:
        return FAMILIA_COMPROBANTE
    if tipo in TIPOS_ACTO:
        return FAMILIA_ACTO
    return None


def _sql(claves) -> str:
    return ",".join(f"'{c}'" for c in sorted(claves))


# Para embeber en el esquema y en las consultas .sql, que no pueden importar Python.
SQL_TIPOS_CONTRATO = _sql(TIPOS_CONTRATO)
SQL_TIPOS_COMPROBANTE = _sql(TIPOS_COMPROBANTE)
SQL_TIPOS_CONOCIDOS = _sql(TIPOS_CONTRATO | TIPOS_COMPROBANTE | TIPOS_ACTO)


def _puntos(plano: str, tipo: Tipo) -> int:
    """Cuántas de sus marcas aparecen. Más marcas, más seguro el tipo."""
    return sum(1 for m in tipo.marcas if m in plano)


def clasificar_pagina(texto_plano_normalizado: str) -> tuple[str, int]:
    """
    Devuelve (clave del tipo, cuántas marcas coincidieron).

    Se elige el tipo con MÁS marcas coincidentes. El desempate es el orden de la tabla,
    que va de lo más específico a lo más genérico: «CONTRATO DE OBRA» antes que
    «RECIBO», porque un contrato puede mencionar la palabra recibo y no al revés.
    """
    mejor, puntos_mejor = "desconocida", 0
    for t in TIPOS:
        p = _puntos(texto_plano_normalizado, t)
        if p > puntos_mejor:
            mejor, puntos_mejor = t.clave, p
    return mejor, puntos_mejor


def clasificar_documento(paginas: list[tuple[int, str]]) -> dict[int, str]:
    """
    Clasifica todas las fojas de un archivo.

    `paginas` es [(nro, texto plano normalizado), ...] en orden.

    Una foja sin marcas propias hereda `continuacion` si viene detrás de algo; si está
    al principio de todo y no se reconoce, queda `desconocida` y se ve.
    """
    fuera: dict[int, str] = {}
    ultimo_arranque: str | None = None
    for nro, plano in paginas:
        clave, puntos = clasificar_pagina(plano)
        if puntos == 0:
            fuera[nro] = "continuacion" if ultimo_arranque else "desconocida"
            continue
        fuera[nro] = clave
        if TIPOS_POR_CLAVE[clave].arranca:
            ultimo_arranque = clave
        elif ultimo_arranque is None:
            # Una carátula al principio: lo que venga después empieza documento igual.
            ultimo_arranque = None
    return fuera


def tramos_por_tipo(clases: dict[int, str], tipo: str) -> list[tuple[int, int]]:
    """
    Los tramos de fojas que corresponden a documentos de UN tipo.

    Un documento arranca en una foja de ese tipo y sigue mientras las siguientes sean
    `continuacion` —o del mismo tipo cuando el tipo ocupa una sola foja, como una
    factura, donde cada foja es un documento distinto—. Corta apenas aparece otra cosa.

    Ese corte es lo que evita que el último contrato de una pila se quede con todas las
    facturas que venían atrás.
    """
    if tipo not in TIPOS_POR_CLAVE:
        return []
    una_sola_foja = TIPOS_POR_CLAVE[tipo].fojas_tipicas == 1
    nros = sorted(clases)
    tramos: list[tuple[int, int]] = []
    i = 0
    while i < len(nros):
        n = nros[i]
        if clases[n] != tipo:
            i += 1
            continue
        fin = n
        if not una_sola_foja:
            j = i + 1
            while j < len(nros) and clases[nros[j]] == "continuacion":
                fin = nros[j]
                j += 1
            i = j
        else:
            i += 1
        tramos.append((n, fin))
    return tramos


def resumen(clases: dict[int, str]) -> dict[str, int]:
    """Cuántas fojas de cada tipo, para mostrarlo sin que nadie tenga que contar."""
    r: dict[str, int] = {}
    for c in clases.values():
        r[c] = r.get(c, 0) + 1
    return r
