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
    # Una resolución se identifica por su estructura, no sólo por su título: el
    # título está arriba a la derecha, que es justo donde se apilan los sellos de
    # mesa de entradas, y en un expediente fotocopiado ahí no se lee nada. VISTO y
    # RESUELVE, en cambio, están en el cuerpo y en limpio.
    Tipo("resolucion", "Resolución",
         ("RESOLUCION N", "VISTO", "RESUELVE", "ARTICULO 1"), fojas_tipicas=2),
    # Contexto: no arrancan un documento, viajan con el que tienen al lado.
    Tipo("caratula", "Carátula",
         ("PERIODO LEGISLATIVO", "EXPEDIENTE N", "INICIADOR", "ANEXO I", "ANEXO II"),
         arranca=False, fojas_tipicas=1),
    Tipo("nota", "Nota",
         ("ME DIRIJO A USTED", "NOTA DE ELEVACION", "TENGO EL AGRADO"),
         arranca=False, fojas_tipicas=1),

    # ── Lo que trae un expediente de obra pública ─────────────────────────────
    # Los de arriba salieron del material de la Legislatura, que son formularios. Un
    # expediente de obra es otra cosa: casi nada de lo que tiene adentro es un
    # formulario, y sin embargo cada foja ES algo. Medido sobre el expediente
    # 201.602 —88 fojas, parte 4 de un expediente de más de 850—: pliego de
    # condiciones, especificaciones técnicas, memoria descriptiva, presupuesto,
    # planos, croquis, acta de apertura, pólizas de caución, constancias fiscales y
    # una decena de pases de mesa de entradas.
    #
    # Ninguno de estos «arranca» un documento en el sentido de los contratos: un
    # expediente no es una pila de documentos independientes, es UNA actuación. Por
    # eso van con `arranca=False`: identifican la foja sin partir el expediente en
    # pedazos que después habría que volver a pegar.
    Tipo("pliego", "Pliego de condiciones",
         ("PLIEGO DE CONDICIONES", "PLIEGO DE ESPECIFICACIONES",
          "CONDICIONES PARA COTEJO DE PRECIOS"), arranca=False, fojas_tipicas=3),
    Tipo("especificaciones", "Especificaciones técnicas",
         ("ESPECIFICACIONES TECNICAS",), arranca=False, fojas_tipicas=4),
    Tipo("memoria", "Memoria descriptiva",
         ("MEMORIA DESCRIPTIVA",), arranca=False, fojas_tipicas=2),
    Tipo("presupuesto", "Presupuesto",
         ("PRESUPUESTO OFICIAL", "COMPUTO Y PRESUPUESTO",
          "MATERIALES PARA SISTEMAS"), arranca=False, fojas_tipicas=2),
    Tipo("plano", "Plano o croquis",
         ("CROQUIS DE UBICACION", "PLANO DE UBICACION", "PLANO GENERAL"),
         arranca=False, fojas_tipicas=1),
    Tipo("acta_apertura", "Acta de apertura",
         ("ACTA DE APERTURA", "SE PROCEDE A LA APERTURA"),
         arranca=False, fojas_tipicas=2),
    Tipo("poliza", "Póliza de caución",
         ("SEGURO DE CAUCION", "SEGURO CAUCION", "POLIZA DE CAUCION"),
         arranca=False, fojas_tipicas=3),
    Tipo("constancia", "Constancia fiscal",
         ("CONSTANCIA DE INSCRIPCION", "ADMINISTRADORA TRIBUTARIA"),
         arranca=False, fojas_tipicas=1),
    # El pase de mesa de entradas es la cinta transportadora del expediente: dice de
    # qué oficina viene y a cuál va. No es un documento, pero es la única foja que
    # cuenta el trámite, así que no puede quedar como «sin reconocer».
    Tipo("pase", "Pase / providencia",
         ("PASEN LAS ACTUACIONES", "PASE A LA DIRECCION", "PASA A SER FOLIO"),
         arranca=False, fojas_tipicas=1),
)

TIPOS_POR_CLAVE = {t.clave: t for t in TIPOS}
ETIQUETAS = {t.clave: t.etiqueta for t in TIPOS}

# Los documentos que traen precios son piezas propias aunque viajen adentro de un
# expediente: comparar precios es el objetivo central (docs/contrataciones-y-precios.md),
# y un presupuesto pegado como contexto a la foja de al lado no tiene renglones que
# comparar. Un acta de apertura lista las ofertas con sus importes.
TIPOS_CON_PRECIO = frozenset({"presupuesto", "acta_apertura"})

# Qué tipos de foja arrancan una pieza. Hasta acá las piezas salían sólo de los perfiles
# de extracción —factura y contratos—, y `arranca` no lo consultaba nadie: en un legajo
# real, 128 fojas de resoluciones, 48 de remitos y 19 de presupuestos, bien clasificadas,
# no formaban ni una pieza. Una pieza sin extractor para su tipo sigue siendo una pieza:
# se ve, se busca, se anota y se revisa. Los tipos de contexto de un expediente —pliego,
# memoria, planos, pólizas, pases— siguen sin partirlo en pedazos.
TIPOS_PIEZA = frozenset(t.clave for t in TIPOS if t.arranca) | TIPOS_CON_PRECIO
ETIQUETAS["continuacion"] = "Continuación"
ETIQUETAS["desconocida"] = "Sin reconocer"


# ═══════════════════════════════════════════════════════════════════════════
# LAS FOJAS QUE SE APARTAN
# ═══════════════════════════════════════════════════════════════════════════
# No todo lo que entra al escáner es una foja de trabajo, y esto no es un detalle:
# medido sobre el expediente 201.602, de 88 páginas escaneadas **44 son dorsos en
# blanco**. La mitad. Si entran a la cola, la mitad de la cola es nada; si cuentan
# como fojas, todos los números del panel están inflados al doble.
#
# Y hay una segunda clase: la foja que TIENE tinta y aun así no se puede leer.
# Fotocopia de fotocopia de un papel carbónico, un plano escaneado al 30 %, la
# carátula que alguien apoyó de costado. Ahí el OCR no devuelve nada: devuelve PEOR
# que nada, porque devuelve fragmentos que parecen palabras. Decir «no se pudo leer»
# es la única respuesta honesta, y es además la que manda a una persona a mirar el
# papel, que es lo que hay que hacer con esa foja.
#
# Las dos se deciden MIDIENDO, no por frases: una foja en blanco no tiene encabezado
# que reconocer, y una ilegible tiene uno que no dice nada.
FOJA_EN_BLANCO = "en_blanco"
FOJA_SIN_TEXTO = "sin_texto_util"
APARTADAS = frozenset({FOJA_EN_BLANCO, FOJA_SIN_TEXTO})
ETIQUETAS[FOJA_EN_BLANCO] = "Hoja en blanco"
ETIQUETAS[FOJA_SIN_TEXTO] = "No se pudo leer"

# Los dos umbrales salieron de medir el expediente 201.602 entero, no de elegir un
# número redondo. Están acá arriba y con su medición al lado para que el próximo que
# los toque sepa contra qué compararlos.
#
#   PALABRAS: los 44 dorsos en blanco dieron entre 0 y 9 palabras; los 44 frentes,
#   entre 174 y 1.356. No hay nada en el medio, así que el corte en 12 no discute
#   ningún caso real.
PALABRAS_EN_BLANCO = 12
#
#   ÚTILES: la proporción de lo leído que parece una palabra o un número de verdad
#   —cuatro letras seguidas, o una cifra— sobre el total de lo que devolvió el motor.
#   La CONFIANZA sola no sirve y conviene decir por qué: el presupuesto de la obra
#   —una tabla de 31 renglones con todos los importes, la foja más valiosa del
#   expediente— lee con confianza 0,35, más bajo que varios planos. Una tabla
#   apretada siempre lee con poca confianza. La proporción de útiles, en cambio,
#   separa limpio:
#
#       plano escaneado al 30 % ............ 3,4 %
#       fotocopia negra de un carbónico .... 4,1 %
#       carátula apoyada de costado ........ 4,6 %
#       ─────────────────────────────────── corte en 8 %
#       croquis de ubicación (título legible) 11,8 %
#       presupuesto de 31 renglones ........ 19,8 %
#       resolución, memoria, pliego ........ 25 a 41 %
#
#   Las tres de arriba son exactamente las tres que una persona mirando la pantalla
#   también llama «no se lee». Las de abajo tienen todas algo que leer.
UTILES_MINIMOS = 0.08

# Qué cuenta como «útil». Cuatro letras seguidas es una palabra; una cifra con
# separadores es un número. Los fragmentos de dos caracteres que devuelve el motor
# sobre una mancha no son ni una cosa ni la otra, y son justamente lo que hay que no
# contar.
_PALABRA = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{4,}$")
_NUMERO = re.compile(r"^\$?\d[\d.,]{2,}$")


@dataclass(frozen=True)
class Medida:
    """Lo que se puede decir de una foja sin entender lo que dice."""
    palabras: int
    utiles: int

    @property
    def proporcion_util(self) -> float:
        return self.utiles / self.palabras if self.palabras else 0.0


def medir(textos) -> Medida:
    """Cuenta palabras y cuáles de ellas parecen algo. `textos` es lo que leyó el motor."""
    palabras = 0
    utiles = 0
    for t in textos:
        t = (t or "").strip()
        if not t:
            continue
        palabras += 1
        if _PALABRA.match(t) or _NUMERO.match(t):
            utiles += 1
    return Medida(palabras, utiles)


def veredicto(m: Medida | None) -> str | None:
    """
    `en_blanco`, `sin_texto_util`, o `None` si la foja se puede leer.

    Va ANTES que las frases: una hoja en blanco no tiene encabezado que reconocer, y
    una ilegible tiene uno que no dice nada. Clasificarlas por frase las dejaría en
    «sin reconocer», que es un cajón donde ya no se distingue lo que no se pudo leer
    de lo que se leyó y no se entendió.
    """
    if m is None:
        return None
    if m.palabras < PALABRAS_EN_BLANCO:
        return FOJA_EN_BLANCO
    if m.proporcion_util < UTILES_MINIMOS:
        return FOJA_SIN_TEXTO
    return None


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


# Cuánto tiene que parecerse la marca a lo que leyó el motor. No es 1,0 y conviene
# decir por qué, con los casos de verdad al lado: sobre el expediente 201.602 el OCR
# devolvió «ESPEGIFICACIONES TECNICAS» —una C leída como G—, «MATERIALES PARA SISTE
# MAS DE ILUMINACION» —una palabra partida al medio— y «PRESU PUESTO». Con búsqueda
# exacta esas tres fojas quedaban «sin reconocer» teniendo el título impreso en
# catorce puntos arriba de todo.
#
# Que quede claro qué es esto y qué no: acá se está decidiendo A QUÉ SE PARECE una
# foja, no qué dice. Ningún dato sale de esta comparación —los datos se extraen con
# anclaje y doble lectura, como siempre—, la clasificación se muestra siempre y una
# persona la puede cambiar. Aflojar la comparación acá no afloja nada del carril de
# datos.
PARECIDO_MINIMO = 0.90

# Y con un ANCLA exacta, que es lo que evita que la tolerancia se vuelva adivinanza.
# Sin esto, una marca de veinticinco caracteres aceptada al 90 % admite dos letras
# equivocadas, y en cuatrocientos caracteres de ruido de sellos hay muchas ventanas
# donde dos letras alcanzan: medido sobre este mismo expediente, un plano salía
# clasificado «Presupuesto» y una hoja de póliza salía «Resolución». Ahora además
# tienen que aparecer EXACTOS seis caracteres seguidos de la marca. Una letra mal
# leída parte la marca en dos pedazos y el más largo casi siempre pasa los seis;
# el ruido, no.
ANCLA_EXACTA = 6


def _sin_espacios(t: str) -> str:
    return t.replace(" ", "")


def contiene_marca(plano: str, marca: str) -> bool:
    """
    ¿Aparece la marca, aunque el motor la haya leído con alguna letra de más o de menos?

    Se comparan las dos sin espacios —eso solo ya recupera la palabra partida al
    medio— y después se corre la marca por el texto contando cuántos caracteres caen
    en su lugar.
    """
    t = _sin_espacios(plano)
    m = _sin_espacios(marca)
    if not m or len(t) < len(m):
        return False
    if m in t:
        return True
    # El ancla: algún pedazo de la marca tiene que estar TAL CUAL. Si no está, lo que
    # haya se parece de casualidad.
    if len(m) > ANCLA_EXACTA and not any(
            m[i:i + ANCLA_EXACTA] in t for i in range(len(m) - ANCLA_EXACTA + 1)):
        return False
    tope = len(m) * PARECIDO_MINIMO
    for i in range(len(t) - len(m) + 1):
        iguales = 0
        for a, b in zip(m, t[i:i + len(m)]):
            iguales += a == b
        if iguales >= tope:
            return True
    return False


def _puntos(plano: str, tipo: Tipo) -> int:
    """Cuántas de sus marcas aparecen. Más marcas, más seguro el tipo."""
    return sum(1 for m in tipo.marcas if contiene_marca(plano, m))


def clasificar_pagina(texto_plano_normalizado: str,
                      medida: "Medida | None" = None) -> tuple[str, int]:
    """
    Devuelve (clave del tipo, cuántas marcas coincidieron).

    Primero el veredicto de la MEDIDA —en blanco, o con tinta pero sin nada legible—,
    porque esas dos no se reconocen por frases y confundirlas con «sin reconocer»
    pierde la única información que hay sobre ellas.

    Después, el tipo con MÁS marcas coincidentes. El desempate es el orden de la tabla,
    que va de lo más específico a lo más genérico: «CONTRATO DE OBRA» antes que
    «RECIBO», porque un contrato puede mencionar la palabra recibo y no al revés.
    """
    v = veredicto(medida)
    if v:
        return v, 1
    mejor, puntos_mejor = "desconocida", 0
    for t in TIPOS:
        p = _puntos(texto_plano_normalizado, t)
        if p > puntos_mejor:
            mejor, puntos_mejor = t.clave, p
    return mejor, puntos_mejor


def clasificar_documento(paginas, medidas: dict[int, "Medida"] | None = None
                         ) -> dict[int, str]:
    """
    Clasifica todas las fojas de un archivo.

    `paginas` es [(nro, texto plano normalizado), ...] en orden. `medidas` es opcional
    y trae, por foja, cuánto leyó el motor: sin eso no se pueden apartar ni las hojas
    en blanco ni las que no se pudieron leer.

    Una foja sin marcas propias hereda `continuacion` si viene detrás de algo; si está
    al principio de todo y no se reconoce, queda `desconocida` y se ve.
    """
    medidas = medidas or {}
    fuera: dict[int, str] = {}
    ultimo_arranque: str | None = None
    for nro, plano in paginas:
        clave, puntos = clasificar_pagina(plano, medidas.get(nro))
        # Una foja apartada no continúa nada ni arranca nada: es un hueco en la pila.
        # Heredar `continuacion` sobre un dorso en blanco es lo que hacía que un
        # documento se tragara las fojas que tenía atrás.
        if clave in APARTADAS:
            fuera[nro] = clave
            continue
        if puntos == 0:
            fuera[nro] = "continuacion" if ultimo_arranque else "desconocida"
            continue
        fuera[nro] = clave
        # Cualquier foja reconocida deja «algo» atrás, y por eso la siguiente sin
        # marcas propias es su continuación. Antes esto sólo valía para los tipos que
        # ARRANCAN un documento —contrato, factura, decreto—, y en un expediente de
        # obra no arranca ninguno: las fojas de un pliego de cuatro carillas quedaban
        # todas «sin reconocer» teniendo el título en la primera. Medido sobre el
        # expediente 201.602: trece fojas.
        #
        # Que no se confunda con partir el expediente en documentos: eso lo sigue
        # decidiendo `arranca`, en `tramos_por_tipo`. Acá sólo se está diciendo que
        # esta carilla viene atrás de aquella.
        ultimo_arranque = clave
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
