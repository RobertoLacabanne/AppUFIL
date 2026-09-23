"""
Qué se puede comparar con qué, y cuánto vale esa comparación.

Es la semántica de `docs/contrataciones-y-precios.md` (§1, §3, §4 y §6.2) escrita como
funciones puras: no tocan la base ni saben de dónde salió cada renglón. Reciben lo que se
sabe de dos renglones y devuelven un estado **con sus motivos**, porque «comparable
fuerte» sin decir por qué no le sirve a nadie que tenga que verificarlo.

La regla que ordena todo el módulo
----------------------------------
**Dos productos no son comparables porque el texto se parezca.** Una bomba de 1 HP y una
de 2 HP se escriben casi igual y no cuestan lo mismo; un litro y un bidón de veinte
tampoco. Por eso lo que contradice pesa más que lo que coincide: basta un atributo
conocido y distinto para que no haya comparación, y basta uno que falte para que no sea
«fuerte».

Lo que NO hace
--------------
No normaliza descripciones ni unidades (eso es de la extracción de renglones: acá llegan
ya normalizadas), no calcula estadísticos ni lee precios. Y no concluye: los textos que
salen de acá se prueban contra `TERMINOS_PROHIBIDOS`.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import cached_property
from difflib import SequenceMatcher

# ── Estados de comparabilidad (§3) ────────────────────────────────────────────
FUERTE = "fuerte"
PROBABLE = "probable"
DUDOSO = "dudoso"
NO_COMPARABLE = "no_comparable"
ESTADOS = (FUERTE, PROBABLE, DUDOSO, NO_COMPARABLE)

# Cómo afecta cada atributo a la decisión. Van en cada motivo.
COINCIDE, DIFIERE, FALTA, BLOQUEA = "coincide", "difiere", "falta", "bloquea"

# ── Umbrales (§4). Parámetros de trabajo, no verdades: se miden contra el corpus real.
UMBRALES = {
    "dias_cercana": 90,
    "dias_proxima": 365,
    "similitud_minima": 0.40,
    "similitud_probable": 0.70,
    "similitud_fuerte": 0.90,
    "min_referencias": 2,
    "diferencia_senalable_pct": "20.00",
    # Uno contra mil no se compara igual que uno contra uno: el precio por volumen es
    # una explicación posible de la diferencia, así que se informa.
    "escala_cantidad": 100,
    # Dos precios del «mismo» ítem a más de cien veces uno del otro casi nunca son el
    # mismo ítem al mismo precio: lo habitual es un subtotal o un total leído como
    # precio unitario, o una unidad distinta que el papel no dice. No bloquea —un
    # sobreprecio enorme también se vería así—, pero la comparación deja de ser probable.
    "escala_precio": 100,
}

# ── Etapas de una contratación (§2). El orden es el del trámite. `primaria` = el
# documento prueba el precio pactado o pagado, no una intención o una estimación.
ETAPAS = (
    ("pedido", "Pedido o solicitud", False),
    ("presupuesto", "Presupuesto o cotización", False),
    ("pliego", "Pliego", False),
    ("apertura", "Acta de apertura", False),
    ("oferta", "Oferta", True),
    ("cuadro_comparativo", "Cuadro comparativo", False),
    ("dictamen", "Dictamen o preadjudicación", False),
    ("adjudicacion", "Adjudicación", True),
    ("orden_compra", "Orden de compra o contrato", True),
    ("remito", "Remito o entrega", True),
    ("factura", "Factura", True),
    ("orden_pago", "Orden de pago", True),
    ("pago", "Pago o transferencia", True),
    ("otro", "Otro documento relacionado", False),
)
ETAPAS_PRIMARIAS = frozenset(c for c, _, p in ETAPAS if p)
ETAPAS_COTIZACION = frozenset({"presupuesto"})

# ── Niveles de la referencia (§4) ─────────────────────────────────────────────
NIVELES = (
    ("A", "Mismo producto, misma contratación, fecha cercana",
     "Comparable fuerte, de un documento primario de la misma contratación, con fechas a "
     "no más de {dias_cercana} días."),
    ("B", "Mismo producto en otra compra documentada",
     "Comparable fuerte, de un documento primario, con fechas a no más de "
     "{dias_proxima} días."),
    ("C", "Presupuesto o cotización contemporánea",
     "Comparable fuerte o probable, tomado de un presupuesto o cotización con fechas a no "
     "más de {dias_cercana} días."),
    ("D", "Producto similar, no idéntico",
     "Comparable probable: nada lo contradice, pero falta algún atributo para decir que "
     "es el mismo producto."),
    ("E", "Referencia aproximada",
     "Comparable dudoso, fechas lejanas o desconocidas, o una referencia cargada a mano "
     "sin documento."),
)
ORDEN_NIVELES = tuple(n for n, _, _ in NIVELES)

# ── Hallazgos (§6.3): nombres neutros. Dicen qué se detectó, no qué significa. ──
HALLAZGOS = (
    ("diferencia_precio", "Diferencia de precio detectada",
     "El precio unitario supera la mediana de las referencias comparables en más del "
     "umbral de trabajo."),
    ("facturado_vs_adjudicado", "Facturado distinto de lo adjudicado u ordenado",
     "Precio, cantidad, producto, proveedor o total de la factura no coinciden con la "
     "adjudicación o la orden de compra."),
    ("facturado_vs_entregado", "Facturado distinto de lo entregado",
     "Cantidad o producto de la factura no coinciden con el remito asociado."),
    ("subtotal_incorrecto", "Subtotal que no coincide con su cuenta",
     "Cantidad por precio unitario no da el subtotal impreso."),
    ("total_inconsistente", "Total que no coincide con la suma",
     "La suma de los subtotales no da el total impreso."),
    ("precio_ausente", "Renglón sin precio",
     "El renglón no tiene precio unitario y no se lo puede derivar de otros valores."),
    ("precio_sin_rol", "Importe impreso sin poder decir de qué es",
     "La planilla tiene un importe por renglón pero no dice si es el precio de una unidad "
     "o el total del renglón, y no hay cantidad para deducirlo. Hasta que alguien lo "
     "confirme, el importe se muestra pero no se usa como referencia."),
    ("documento_faltante", "Documento no encontrado",
     "Falta una etapa que la secuencia de la contratación permite esperar."),
    ("oferente_unico", "Una sola oferta encontrada",
     "En la contratación se encontró una sola oferta."),
    ("ofertas_identicas", "Ofertas con los mismos precios",
     "Dos ofertas tienen los mismos precios renglón por renglón."),
    ("duplicado_potencial", "Posible duplicado",
     "La misma factura aparece más de una vez, o el mismo remito está asociado a varias "
     "facturas."),
    ("variacion_compras", "Variación entre compras del mismo ítem",
     "El mismo ítem se compró más de una vez con una variación de precio grande."),
    ("secuencia_temporal", "Fechas fuera del orden esperable",
     "Un documento tiene fecha anterior a otro que en el trámite debería precederlo."),
    ("coincidencia_temporal", "Coincidencia temporal detectada",
     "Una anotación tiene fecha próxima a un acto del expediente. No indica relación entre "
     "ambos."),
)

# ── Revisión humana de un hallazgo ───────────────────────────────────────────
REVISION = (
    ("pendiente", "Pendiente de revisión", "Nadie lo miró todavía."),
    ("relevante", "Relevante para la investigación",
     "Una persona lo verificó contra las fuentes y lo considera relevante."),
    ("descartado", "Descartado",
     "Una persona lo revisó y lo descartó; la nota dice por qué."),
)

# ── Vocabulario (§1) ─────────────────────────────────────────────────────────
# Lo que la aplicación no afirma nunca. «Sobreprecio» se admite sólo como «posible
# sobreprecio», que es el nombre de una pantalla y no una conclusión. «Responsable»
# también está prohibido como atribución, pero no se puede distinguir por el texto de
# «responsable de la carga», así que se revisa a mano y no acá.
TERMINOS_PROHIBIDOS = ("fraude", "delito", "direccionamiento", "irregularidad",
                       "irregular", "ilícito", "culpable", "sospechoso", "sobreprecio")
_PROHIBIDOS = re.compile(
    r"\b(fraud\w*|delict\w*|delito\w*|direccionamiento\w*|direccionad\w*|irregular\w*"
    r"|il[ií]cit\w*|culpab\w*|sospech\w*)", re.IGNORECASE)
_SOBREPRECIO = re.compile(r"(?<!posible )(?<!posibles )\bsobreprecios?\b", re.IGNORECASE)


def terminos_prohibidos_en(texto: str) -> list[str]:
    """Los términos prohibidos que aparecen en `texto`, tal como aparecen."""
    texto = texto or ""
    return ([m.group(0) for m in _PROHIBIDOS.finditer(texto)]
            + [m.group(0) for m in _SOBREPRECIO.finditer(texto)])


# ── Lo que se sabe de un renglón ─────────────────────────────────────────────
@dataclass(frozen=True)
class Observacion:
    """
    Lo que se sabe de un renglón de precio para decidir si se lo puede comparar.

    `None` quiere decir «no se sabe», nunca «no tiene». Todo llega normalizado: la
    unidad como «unidad», «litro»; la moneda como «ARS», «USD».
    """
    desc_norm: str
    unidad: str | None = None
    moneda: str | None = None
    marca: str | None = None
    modelo: str | None = None
    categoria: str | None = None
    iva: str | None = None                      # "incluido" | "discriminado" | None
    condiciones: frozenset = frozenset()        # {"flete", "instalacion", "garantia"}
    cantidad: Decimal | None = None
    precio: Decimal | None = None               # precio unitario, si se leyó
    fecha: date | None = None
    etapa: str | None = None
    contratacion: int | None = None
    documentada: bool = True                    # False: referencia cargada a mano sin papel

    @cached_property
    def texto_comparable(self):
        return _plano(self.desc_norm)

    @cached_property
    def tokens(self):
        return tuple(_tokens(self.desc_norm))

    @cached_property
    def numeros(self):
        return frozenset(w for w in self.tokens if any(c.isdigit() for c in w))

    @cached_property
    def atributos_comparables(self):
        return {k:_plano(getattr(self,k)) for k in _BLOQUEANTES}


def _plano(texto) -> str:
    """Sin tildes, en minúscula, con los espacios colapsados. Para comparar atributos."""
    if texto is None:
        return ""
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", t).strip()


# Palabras que no distinguen un producto de otro.
_VACIAS = frozenset("de del la las el los y e o u con sin para por a al en x".split())


def _tokens(texto: str) -> list[str]:
    t = re.sub(r"(\d),(\d)", r"\1.\2", _plano(texto))        # 2,5 mm → 2.5 mm
    return [w for w in re.findall(r"[a-z0-9./]+", t) if w not in _VACIAS and w != "."]


def _numeros(texto: str) -> frozenset:
    """Los números de la descripción: son la especificación (1 HP, 2.5 mm, 1/2")."""
    return frozenset(w for w in _tokens(texto) if any(c.isdigit() for c in w))


def similitud(a: str, b: str) -> float:
    """
    Coeficiente de Dice sobre las palabras, admitiendo errores de tipeo u OCR.

    Dos palabras cuentan como la misma si son iguales o casi iguales (una letra de más o
    de menos). Los números no: «1» y «2» se parecen como texto y son especificaciones
    distintas, así que un número sólo coincide con el mismo número.
    """
    ta, tb = _tokens(a), _tokens(b)
    return _similitud_tokens(ta,tb)


def _similitud_tokens(ta, tb):
    if not ta or not tb:
        return 0.0
    if ta == tb:
        return 1.0
    libres = list(tb)
    iguales = 0
    for w in ta:
        if w in libres:
            libres.remove(w)
            iguales += 1
            continue
        if any(c.isdigit() for c in w):
            continue
        for x in libres:
            # La cota por longitud evita calcular alineamientos que jamás llegan
            # al umbral. No cambia ninguna coincidencia admitida.
            if (2*min(len(w),len(x)) >= .85*(len(w)+len(x))
                    and not any(c.isdigit() for c in x) and SequenceMatcher(None, w, x).ratio() >= 0.85):
                libres.remove(x)
                iguales += 1
                break
    return round(2 * iguales / (len(ta) + len(tb)), 4)


def _motivo(atributo, a, b, efecto) -> dict:
    return {"atributo": atributo, "a": a, "b": b, "efecto": efecto}


# Atributos que, conocidos en los dos lados y distintos, hacen imposible la comparación.
_BLOQUEANTES = ("unidad", "moneda", "marca", "modelo", "categoria")


def comparabilidad(a: Observacion, b: Observacion, *, decision_humana: str | None = None,
                   quien: str | None = None, umbrales: dict | None = None) -> dict:
    """
    Si A (el renglón analizado) se puede comparar con B (una referencia), y por qué.

    `decision_humana` es `"mismo"` o `"distinto"` cuando una persona ya lo dijo: manda
    sobre todo lo demás, y queda en los motivos con su nombre.

    Devuelve `{"estado", "motivos", "similitud"}`.
    """
    u = {**UMBRALES, **(umbrales or {})}
    sim = 1.0 if a.texto_comparable == b.texto_comparable else _similitud_tokens(a.tokens,b.tokens)
    motivos: list[dict] = []

    if decision_humana in ("mismo", "distinto"):
        motivos.append(_motivo("decision_humana", decision_humana, quien,
                               COINCIDE if decision_humana == "mismo" else BLOQUEA))
        return {"estado": FUERTE if decision_humana == "mismo" else NO_COMPARABLE,
                "motivos": motivos, "similitud": sim}

    bloqueado = False
    faltan: list[str] = []

    # La descripción.
    if sim < u["similitud_minima"]:
        motivos.append(_motivo("descripcion", a.desc_norm, b.desc_norm, BLOQUEA))
        bloqueado = True
    else:
        motivos.append(_motivo("descripcion", a.desc_norm, b.desc_norm,
                               COINCIDE if sim >= u["similitud_fuerte"] else DIFIERE))

    # La especificación que traen los números de la descripción.
    na, nb = a.numeros, b.numeros
    if na and nb:
        if na != nb:
            motivos.append(_motivo("especificacion", sorted(na), sorted(nb), BLOQUEA))
            bloqueado = True
        else:
            motivos.append(_motivo("especificacion", sorted(na), sorted(nb), COINCIDE))
    elif na or nb:
        motivos.append(_motivo("especificacion", sorted(na) or None, sorted(nb) or None, FALTA))
        faltan.append("especificacion")

    # Los atributos que bloquean.
    for atributo in _BLOQUEANTES:
        va, vb = getattr(a, atributo), getattr(b, atributo)
        if va is not None and vb is not None:
            if a.atributos_comparables[atributo] != b.atributos_comparables[atributo]:
                motivos.append(_motivo(atributo, va, vb, BLOQUEA))
                bloqueado = True
            else:
                motivos.append(_motivo(atributo, va, vb, COINCIDE))
        elif va is not None or vb is not None:
            motivos.append(_motivo(atributo, va, vb, FALTA))
            faltan.append(atributo)
        elif atributo in ("unidad", "moneda"):
            # Sin unidad ni moneda en ninguno de los dos no hay precio unitario que
            # comparar con seguridad: que falte en los dos también es que falta.
            motivos.append(_motivo(atributo, None, None, FALTA))
            faltan.append(atributo)

    # El IVA: distinto explica diferencias; desconocido impide decir «el mismo precio».
    dudas: list[str] = []
    if a.iva is not None and b.iva is not None:
        if a.iva != b.iva:
            motivos.append(_motivo("iva", a.iva, b.iva, DIFIERE))
            dudas.append("iva")
        else:
            motivos.append(_motivo("iva", a.iva, b.iva, COINCIDE))
    else:
        motivos.append(_motivo("iva", a.iva, b.iva, FALTA))
        faltan.append("iva")

    # Flete, instalación, garantía: si están de un lado solo, pueden explicar la diferencia.
    solo_uno = set(a.condiciones) ^ set(b.condiciones)
    for c in sorted(solo_uno):
        motivos.append(_motivo(c, c in a.condiciones, c in b.condiciones, DIFIERE))
        dudas.append(c)

    # La escala de la compra: no decide, se informa.
    if a.cantidad and b.cantidad and a.cantidad > 0 and b.cantidad > 0:
        razon = max(a.cantidad, b.cantidad) / min(a.cantidad, b.cantidad)
        if razon >= u["escala_cantidad"]:
            motivos.append(_motivo("cantidad", str(a.cantidad), str(b.cantidad), DIFIERE))

    # El orden de magnitud del precio: no decide que no sean comparables, pero una
    # referencia cien veces más cara o más barata no sostiene una comparación firme.
    if a.precio and b.precio and a.precio > 0 and b.precio > 0:
        razon = max(a.precio, b.precio) / min(a.precio, b.precio)
        if razon >= u["escala_precio"]:
            motivos.append(_motivo("orden_de_magnitud", str(a.precio), str(b.precio), DIFIERE))
            dudas.append("orden_de_magnitud")

    if bloqueado:
        estado = NO_COMPARABLE
    elif sim < u["similitud_probable"] or dudas:
        estado = DUDOSO
    elif sim >= u["similitud_fuerte"] and not faltan:
        estado = FUERTE
    else:
        estado = PROBABLE
    return {"estado": estado, "motivos": motivos, "similitud": sim}


def nivel(a: Observacion, b: Observacion, estado: str, *,
          umbrales: dict | None = None) -> str | None:
    """
    Qué calidad tiene B como referencia del precio de A (§4). `None` si no es comparable.

    Sin fecha de alguno de los dos no se puede decir que sean contemporáneos, y eso lo
    deja en E: una fecha que no se conoce no es una fecha cercana.
    """
    if estado == NO_COMPARABLE:
        return None
    u = {**UMBRALES, **(umbrales or {})}
    if not b.documentada:
        return "E"
    dias = abs((a.fecha - b.fecha).days) if a.fecha and b.fecha else None
    primaria = b.etapa in ETAPAS_PRIMARIAS
    misma = a.contratacion is not None and a.contratacion == b.contratacion
    if dias is None:
        return "E"
    if estado == FUERTE and primaria and misma and dias <= u["dias_cercana"]:
        return "A"
    if estado == FUERTE and primaria and dias <= u["dias_proxima"]:
        return "B"
    if estado in (FUERTE, PROBABLE) and b.etapa in ETAPAS_COTIZACION \
            and dias <= u["dias_cercana"]:
        return "C"
    if estado == PROBABLE and dias <= u["dias_proxima"]:
        return "D"
    return "E"


def elegir_nivel(niveles: list[str | None], *, umbrales: dict | None = None
                 ) -> tuple[str | None, list[str]]:
    """
    Con qué nivel se hace la comparación principal, y qué hay que advertir (§4).

    Se usa el mejor nivel que tenga al menos `min_referencias`. Si ninguno llega, el
    mejor que tenga alguna, y se dice que es una sola. Si hubo que bajar de nivel, se dice
    cuál se dejó de lado. Los niveles no se juntan acá: eso sólo por pedido explícito.
    """
    u = {**UMBRALES, **(umbrales or {})}
    cuenta = {n: niveles.count(n) for n in ORDEN_NIVELES}
    advertencias: list[str] = []
    elegido = next((n for n in ORDEN_NIVELES if cuenta[n] >= u["min_referencias"]), None)
    if elegido is None:
        elegido = next((n for n in ORDEN_NIVELES if cuenta[n]), None)
        if elegido is None:
            return None, ["No hay referencias comparables."]
        advertencias.append(f"Hay una sola referencia de nivel {elegido}: la comparación "
                            "depende de un único precio.")
    salteados = [n for n in ORDEN_NIVELES[:ORDEN_NIVELES.index(elegido)] if cuenta[n]]
    for n in salteados:
        advertencias.append(f"El nivel {n} tiene {cuenta[n]} referencia"
                            f"{'s' if cuenta[n] != 1 else ''}, menos de "
                            f"{u['min_referencias']}: se usa el nivel {elegido}.")
    return elegido, advertencias


def calidad(nivel_usado: str | None, estados: list[str], *, precios_firmes: bool,
            derivados_sin_revisar: bool = False, umbrales: dict | None = None) -> dict:
    """
    Cuánto se puede apoyar alguien en la comparación (§6.2): `alta`, `media` o `baja`.

    `estados` son las comparabilidades de las referencias usadas. `precios_firmes` dice
    si todos los precios involucrados —el analizado y las referencias— están en un estado
    firme de `ufil/confianza.py`.
    """
    u = {**UMBRALES, **(umbrales or {})}
    n = len(estados)
    bajas, medias = [], []
    if nivel_usado is None or n == 0:
        return {"nivel": "baja", "motivos": ["No hay referencias comparables."]}
    if nivel_usado == "E":
        bajas.append("Las referencias son aproximadas (nivel E).")
    if DUDOSO in estados:
        bajas.append("Alguna referencia es comparable dudosa.")
    if derivados_sin_revisar:
        bajas.append("Hay precios derivados que nadie revisó.")
    if nivel_usado in ("C", "D"):
        medias.append(f"Las referencias son de nivel {nivel_usado}.")
    if n < u["min_referencias"]:
        medias.append("Hay una sola referencia.")
    if not precios_firmes:
        medias.append("Algún precio está todavía sin confirmar.")
    if any(e != FUERTE for e in estados) and DUDOSO not in estados:
        medias.append("No todas las referencias son comparables fuertes.")
    if bajas:
        return {"nivel": "baja", "motivos": bajas + medias}
    if medias:
        return {"nivel": "media", "motivos": medias}
    return {"nivel": "alta",
            "motivos": [f"{n} referencias de nivel {nivel_usado}, todas comparables fuertes "
                        "y con precios firmes."]}


def catalogo(umbrales: dict | None = None) -> dict:
    """
    Todo lo que la interfaz nombra, para que no lo escriba ella (§9,
    `/api/catalogo/contrataciones`). Cada entrada: `{clave, nombre, explicacion}`.
    """
    u = {**UMBRALES, **(umbrales or {})}
    nombres_estado = {
        FUERTE: ("Comparable fuerte", "Mismo producto: descripción, unidad, moneda, marca, "
                 "modelo e IVA coinciden o faltan en los dos."),
        PROBABLE: ("Comparable probable", "Muy parecido y nada lo contradice, pero falta "
                   "algún atributo de un lado."),
        DUDOSO: ("Comparable dudoso", "Parecido a medias, o con condiciones comerciales "
                 "que pueden explicar la diferencia. No sostiene una conclusión."),
        NO_COMPARABLE: ("No comparable", "Algún atributo conocido lo contradice: unidad, "
                        "moneda, marca, modelo, categoría o especificación."),
    }
    return {
        "etapas": [{"clave": c, "nombre": n, "explicacion": "", "orden": i,
                    "primaria": p} for i, (c, n, p) in enumerate(ETAPAS)],
        "comparabilidad": [{"clave": e, "nombre": nombres_estado[e][0],
                            "explicacion": nombres_estado[e][1]} for e in ESTADOS],
        "niveles": [{"clave": c, "nombre": n, "explicacion": x.format(**u)}
                    for c, n, x in NIVELES],
        "hallazgos": [{"clave": c, "nombre": n, "explicacion": x} for c, n, x in HALLAZGOS],
        "revision": [{"clave": c, "nombre": n, "explicacion": x} for c, n, x in REVISION],
        "umbrales": dict(u),
        "terminos_prohibidos": list(TERMINOS_PROHIBIDOS),
    }
