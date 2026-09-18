"""
Lo que el papel dice, y quién es en realidad. Son dos cosas.

La distinción
-------------
Una **mención** es lo que un documento dice: «VIALIDAD PROVINCIAL», «Vialidad»,
«D.P.V.». Una **entidad** es el organismo del que se habla. Tres menciones, una entidad
—o quizá dos, si una resulta ser otra repartición—.

Guardar sólo la entidad pierde cómo lo dice cada papel, que es lo que después hay que
poder citar. Guardar sólo la mención obliga a reconstruir a mano quién es quién en cada
consulta. Por eso están las dos, y la mención siempre apunta a su documento, su foja y
su recuadro.

Una mención sin entidad asignada **no es un error**: es una mención que todavía nadie
resolvió, y el sistema tiene que poder decir cuántas hay.

Por qué las fusiones se proponen y no se hacen
----------------------------------------------
Dos menciones parecidas pueden ser la misma entidad y pueden ser dos. «Dirección de
Vialidad» y «Dirección de Vialidad de Entre Ríos» probablemente sean una; «González,
Juan» y «González, Juan C.» probablemente sean dos, o no. Unir de más es peor que no
unir: junta en una ficha lo que dos papeles dicen de personas distintas, y eso en un
legajo penal es exactamente lo que no puede pasar.

Así que el sistema une **sólo por clave fuerte** —un CUIT es un CUIT— y todo lo demás lo
propone para que lo decida alguien. Lo que una persona decidió queda guardado por
identidad, no por id, así que sobrevive a que se vuelva a procesar todo.

Sobre las personas
------------------
Las personas siguen viviendo en la tabla `persona`, que ya existía y que sostiene las
fichas, los acumulados y los cruces. No se las movió: migrar ese carril para ganar
uniformidad habría puesto en riesgo lo que ya funciona. Lo que se hace acá es ofrecer
una vista unificada —`listar`— que las incluye, para que quien consulte no tenga que
saber que por dentro son dos tablas. Es una deuda declarada, no un descuido.
"""
from __future__ import annotations

import re
import sqlite3
import unicodedata

from .db import ahora

# Las clases de entidad que el pliego pide. No es una lista cerrada por capricho: cada
# una se busca distinto y se muestra distinto, y agregar una es agregar cómo se la
# reconoce, no sólo una etiqueta.
CLASES = ("persona", "empresa", "organismo", "obra", "bien", "expediente", "comprobante")

ETIQUETAS = {
    "persona": "persona", "empresa": "empresa", "organismo": "organismo",
    "obra": "obra", "bien": "bien", "expediente": "expediente",
    "comprobante": "comprobante",
}


class NoSePuede(ValueError):
    """Lo pedido no se puede hacer, y el motivo es para leer."""


def normalizar(texto: str) -> str:
    """
    Para comparar: sin tildes, sin mayúsculas, sin puntuación ni espacios de más.

    No reemplaza al literal, que se guarda aparte. Esto existe sólo para decidir si dos
    menciones dicen lo mismo, y para eso «S.A.» y «SA» tienen que colapsar.
    """
    t = unicodedata.normalize("NFD", (texto or "").strip().lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    # El punto de una abreviatura se borra en lugar de convertirse en espacio: si no,
    # «S.A.» queda «s a» y «SA» queda «sa», que es justo la diferencia que esto existe
    # para borrar. Los demás signos sí separan.
    t = t.replace(".", "")
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# ── Cómo se reconoce cada clase en el texto ──────────────────────────────────
# Son patrones GENERALES, de la forma que tienen estos identificadores en Argentina, no
# de los documentos que tenemos a mano. Un CUIT es un CUIT en cualquier expediente.
_CUIT = re.compile(r"\b(\d{2})[-\s.]?(\d{8})[-\s.]?(\d)\b")
_EXPEDIENTE = re.compile(
    r"\b(?:expte\.?|expediente)\s*(?:n[°ºo]?\.?\s*)?([\d.\-/]{3,20})", re.IGNORECASE)
_COMPROBANTE = re.compile(
    r"\b(?:factura|remito|recibo|orden\s+de\s+(?:compra|pago))\s*"
    r"(?:n[°ºo]\.?\s*)?([\dA-Z]{1,4}[-\s]?\d{4,12})", re.IGNORECASE)
# Una empresa se reconoce por su forma societaria, que es lo único general que hay.
_SOCIEDAD = re.compile(
    r"\b([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ&.\s]{2,60}?)\s+"
    r"(S\.?\s?A\.?|S\.?R\.?L\.?|S\.?A\.?S\.?|S\.?\s?H\.?|U\.?T\.?E\.?)\b")


# El prefijo dice si es una persona o una sociedad, y confundirlos manda a alguien a
# la ficha equivocada. 20/23/24/27 son personas físicas; 30/33/34, personas jurídicas.
# Es la regla de la CUIT/CUIL argentina, no algo del corpus que tenemos.
_PREFIJO_PERSONA = {"20", "23", "24", "27"}
_PREFIJO_EMPRESA = {"30", "33", "34"}


def clase_de_cuit(cuit: str) -> str:
    """Si ese CUIT es de una persona o de una sociedad. Lo dice el prefijo."""
    d = re.sub(r"\D", "", cuit or "")
    if d[:2] in _PREFIJO_PERSONA:
        return "persona"
    if d[:2] in _PREFIJO_EMPRESA:
        return "empresa"
    return "empresa"


def _cuit_valido(cuit: str) -> bool:
    """
    El dígito verificador. Sirve para no tomar por CUIT cualquier tira de once números.

    Un número de expediente largo o un código de barras tienen la misma forma; el
    verificador es lo que los separa sin tener que saber de qué documento salieron.
    """
    d = re.sub(r"\D", "", cuit)
    if len(d) != 11:
        return False
    pesos = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    suma = sum(int(x) * p for x, p in zip(d[:10], pesos))
    resto = 11 - (suma % 11)
    ver = 0 if resto == 11 else (9 if resto == 10 else resto)
    return ver == int(d[10])


def detectar_en_texto(texto: str) -> list[dict]:
    """
    Las menciones que se pueden reconocer en un texto por su forma.

    Deliberadamente pocas y muy marcadas. Lo que se reconoce acá se reconoce porque
    tiene una forma que no se confunde —un CUIT con verificador válido, un «Expte. N°»—
    y no porque se parezca a algo que vimos antes. Adivinar nombres de obras o de
    organismos a partir del texto corrido produce ruido, y el ruido en una ficha de un
    legajo penal cuesta más de lo que ahorra.
    """
    salida, vistos = [], set()

    for m in _CUIT.finditer(texto or ""):
        crudo = m.group(0)
        if not _cuit_valido(crudo):
            continue
        clave = re.sub(r"\D", "", crudo)
        clase = clase_de_cuit(crudo)
        if (clase, clave) in vistos:
            continue
        vistos.add((clase, clave))
        salida.append({"clase": clase, "literal": crudo, "norm": clave,
                       "clave_fuerte": clave, "confianza": 0.9, "desde": m.start()})

    for m in _EXPEDIENTE.finditer(texto or ""):
        clave = normalizar(m.group(1))
        if not clave or ("expediente", clave) in vistos:
            continue
        vistos.add(("expediente", clave))
        salida.append({"clase": "expediente", "literal": m.group(0).strip(),
                       "norm": clave, "clave_fuerte": clave, "confianza": 0.75,
                       "desde": m.start()})

    for m in _COMPROBANTE.finditer(texto or ""):
        clave = normalizar(m.group(1))
        if not clave or ("comprobante", clave) in vistos:
            continue
        vistos.add(("comprobante", clave))
        salida.append({"clase": "comprobante", "literal": m.group(0).strip(),
                       "norm": clave, "clave_fuerte": clave, "confianza": 0.7,
                       "desde": m.start()})

    for m in _SOCIEDAD.finditer(texto or ""):
        literal = re.sub(r"\s+", " ", m.group(0)).strip()
        clave = normalizar(literal)
        if len(clave) < 5 or ("empresa", clave) in vistos:
            continue
        vistos.add(("empresa", clave))
        salida.append({"clase": "empresa", "literal": literal, "norm": clave,
                       "clave_fuerte": None, "confianza": 0.6, "desde": m.start()})

    return salida


def anotar(cx: sqlite3.Connection, clase: str, literal: str, *, origen: str,
           documento_id: int | None = None, campo_id: int | None = None,
           sha256: str | None = None, pagina_nro: int | None = None,
           caja=None, confianza: float | None = None, clave_fuerte: str | None = None,
           quien: str | None = None) -> dict:
    """
    Anota que un documento menciona algo. **No decide a quién se refiere.**

    Resolver la mención a una entidad es otra cosa y pasa después: por clave fuerte se
    hace solo, y sin clave fuerte lo decide una persona.
    """
    if clase not in CLASES:
        raise NoSePuede(f"clase desconocida: {clase}. Las que hay son: "
                        + ", ".join(CLASES))
    literal = (literal or "").strip()
    if not literal:
        raise NoSePuede("una mención necesita el texto que dice el papel")
    if not (origen or "").strip():
        raise NoSePuede("una mención sin fuente no se puede anotar")
    norm = normalizar(literal)
    x0, y0, x1, y1 = (caja or (None, None, None, None))
    cx.execute("""INSERT INTO mencion (clase, literal, norm, documento_id, campo_id,
                                       sha256, pagina_nro, x0, y0, x1, y1, origen,
                                       confianza, quien, cuando)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                  ON CONFLICT(documento_id, clase, norm, origen) DO UPDATE SET
                      literal=excluded.literal, campo_id=excluded.campo_id,
                      confianza=excluded.confianza""",
               (clase, literal, norm, documento_id, campo_id, sha256, pagina_nro,
                x0, y0, x1, y1, origen, confianza, quien, ahora()))
    mid = cx.execute("""SELECT id FROM mencion WHERE documento_id IS ? AND clase=?
                         AND norm=? AND origen=?""",
                     (documento_id, clase, norm, origen)).fetchone()["id"]
    if clave_fuerte:
        _resolver_por_clave(cx, mid, clase, literal, clave_fuerte)
    cx.commit()
    return {"mencion_id": mid, "clase": clase, "literal": literal}


def _resolver_por_clave(cx, mencion_id: int, clase: str, nombre: str,
                        clave: str) -> int:
    """
    Une la mención a su entidad por CLAVE FUERTE, que es lo único que se une solo.

    Un CUIT es un CUIT: dos documentos que traen el mismo no están hablando de dos
    empresas. Todo lo demás —parecido de nombre, cercanía, coincidencia parcial— se
    propone y lo decide alguien.
    """
    f = cx.execute("SELECT id FROM entidad WHERE clase=? AND clave_fuerte=?",
                   (clase, clave)).fetchone()
    if f:
        eid = f["id"]
    else:
        eid = cx.execute("""INSERT INTO entidad (clase, clave_fuerte, nombre, nombre_norm,
                                                 creado_en)
                            VALUES (?,?,?,?,?)""",
                         (clase, clave, nombre, normalizar(nombre), ahora())).lastrowid
    cx.execute("UPDATE mencion SET entidad_id=? WHERE id=?", (eid, mencion_id))
    return eid


def poblar_desde_documentos(cx: sqlite3.Connection) -> dict:
    """
    Recorre lo que ya está leído y anota las menciones que se puedan reconocer.

    Se apoya en los campos extraídos —que ya tienen anclaje— y en el texto de las fojas
    para lo que tiene forma inconfundible. No pisa lo que anotó una persona.
    """
    puestas = 0

    # Del texto de cada foja, atado a la pieza que la contiene.
    for f in cx.execute("""SELECT t.sha256, t.nro, t.texto,
                                  (SELECT d.id FROM documento d
                                    WHERE d.sha256 = t.sha256
                                      AND t.nro BETWEEN d.pagina_desde AND d.pagina_hasta
                                    LIMIT 1) AS documento_id
                             FROM pagina_texto t""").fetchall():
        for m in detectar_en_texto(f["texto"]):
            try:
                anotar(cx, m["clase"], m["literal"], origen="texto",
                       documento_id=f["documento_id"], sha256=f["sha256"],
                       pagina_nro=f["nro"], confianza=m["confianza"],
                       clave_fuerte=m["clave_fuerte"])
                puestas += 1
            except NoSePuede:
                pass

    sin_resolver = cx.execute(
        "SELECT COUNT(*) FROM mencion WHERE entidad_id IS NULL").fetchone()[0]
    cx.commit()
    return {"menciones": puestas, "sin_resolver": sin_resolver}


def proponer_fusiones(cx: sqlite3.Connection) -> list[dict]:
    """
    Qué menciones sin entidad PODRÍAN ser la misma cosa. Propuestas, nunca decisiones.

    El criterio es el nombre normalizado: si dos menciones dicen lo mismo una vez
    sacadas tildes y puntuación, casi seguro son la misma. «Casi seguro» no es seguro,
    así que se propone.

    Lo que una persona ya rechazó no se vuelve a proponer.
    """
    rechazadas = {(r["clase"], r["ident_a"], r["ident_b"]) for r in cx.execute(
        "SELECT clase, ident_a, ident_b FROM entidad_fusion WHERE decision='rechazada'")}
    salida = []
    for f in cx.execute("""
            SELECT clase, norm, COUNT(*) AS veces, MIN(literal) AS a, MAX(literal) AS b
              FROM mencion WHERE entidad_id IS NULL
             GROUP BY clase, norm HAVING COUNT(*) > 1 ORDER BY veces DESC LIMIT 200"""):
        if (f["clase"], f["norm"], f["norm"]) in rechazadas:
            continue
        salida.append({"clase": f["clase"], "norm": f["norm"], "veces": f["veces"],
                       "literales": sorted({f["a"], f["b"]}),
                       "motivo": "dicen lo mismo una vez sacadas tildes y puntuación"})
    return salida


def confirmar_entidad(cx: sqlite3.Connection, clase: str, norm: str, nombre: str,
                      quien: str) -> dict:
    """
    Una persona dice que todas las menciones que dicen esto son la misma entidad.

    Queda registrado por identidad —la clase y el nombre normalizado— así que sobrevive
    a que se vuelva a procesar todo el legajo.
    """
    if clase not in CLASES:
        raise NoSePuede(f"clase desconocida: {clase}")
    if not (quien or "").strip():
        raise NoSePuede("hace falta indicar quién lo dice")
    nombre = (nombre or "").strip()
    if not nombre:
        raise NoSePuede("la entidad necesita un nombre")
    f = cx.execute("""SELECT id FROM entidad WHERE clase=? AND clave_fuerte IS NULL
                       AND nombre_norm=?""", (clase, norm)).fetchone()
    eid = f["id"] if f else cx.execute(
        """INSERT INTO entidad (clase, clave_fuerte, nombre, nombre_norm, creado_en, quien)
           VALUES (?,NULL,?,?,?,?)""",
        (clase, nombre, norm, ahora(), quien)).lastrowid
    n = cx.execute("""UPDATE mencion SET entidad_id=? WHERE clase=? AND norm=?
                       AND entidad_id IS NULL""", (eid, clase, norm)).rowcount
    cx.execute("""INSERT INTO entidad_fusion (clase, ident_a, ident_b, decision, quien, cuando)
                  VALUES (?,?,?,'aceptada',?,?)
                  ON CONFLICT(clase, ident_a, ident_b) DO UPDATE SET
                      decision='aceptada', quien=excluded.quien, cuando=excluded.cuando""",
               (clase, norm, norm, quien, ahora()))
    cx.commit()
    return {"ok": True, "entidad_id": eid, "menciones": n}


def rechazar_fusion(cx: sqlite3.Connection, clase: str, norm: str, quien: str) -> dict:
    """Una persona dice que NO son la misma. No se vuelve a proponer."""
    if not (quien or "").strip():
        raise NoSePuede("hace falta indicar quién lo dice")
    cx.execute("""INSERT INTO entidad_fusion (clase, ident_a, ident_b, decision, quien, cuando)
                  VALUES (?,?,?,'rechazada',?,?)
                  ON CONFLICT(clase, ident_a, ident_b) DO UPDATE SET
                      decision='rechazada', quien=excluded.quien, cuando=excluded.cuando""",
               (clase, norm, norm, quien, ahora()))
    cx.commit()
    return {"ok": True}


def listar(cx: sqlite3.Connection, clase: str | None = None) -> list[dict]:
    """
    Las fichas, de todas las clases. **Incluye las personas**, que viven en otra tabla.

    Quien consulta no tiene por qué saber que por dentro son dos carriles. Ver el
    encabezado del módulo: es una deuda declarada.
    """
    if clase and clase not in CLASES:
        raise NoSePuede(f"clase desconocida: {clase}")
    salida = []
    if not clase or clase != "persona":
        for f in cx.execute("""
                SELECT e.*, (SELECT COUNT(*) FROM mencion m WHERE m.entidad_id = e.id)
                              AS menciones,
                            (SELECT COUNT(DISTINCT m.documento_id) FROM mencion m
                              WHERE m.entidad_id = e.id) AS documentos
                  FROM entidad e {} ORDER BY e.clase, e.nombre_norm
                """.format("WHERE e.clase=?" if clase else ""),
                (clase,) if clase else ()):
            salida.append({"id": f["id"], "clase": f["clase"], "nombre": f["nombre"],
                           "clave_fuerte": f["clave_fuerte"], "menciones": f["menciones"],
                           "documentos": f["documentos"], "quien": f["quien"],
                           "carril": "entidad"})
    if not clase or clase == "persona":
        # Una persona puede estar en los dos carriles: en `persona`, que es el de
        # siempre, y en `entidad` si su CUIL apareció en el texto. Mostrarla dos veces
        # sería inventar dos personas donde hay una, así que gana el carril de siempre,
        # que es el que sostiene las fichas y los acumulados.
        conocidas = _claves_persona(cx)
        salida = [e for e in salida
                  if not (e["clase"] == "persona" and e["carril"] == "entidad"
                          and (e["clave_fuerte"] in conocidas
                               or documento_del_cuil(e["clave_fuerte"] or "") in conocidas))]
        for f in cx.execute("""
                SELECT p.id, p.clave_fuerte,
                       (SELECT a.nombre_literal FROM persona_alias a
                         WHERE a.persona_id = p.id LIMIT 1) AS nombre,
                       (SELECT COUNT(*) FROM documento_persona d
                         WHERE d.persona_id = p.id) AS documentos
                  FROM persona p ORDER BY nombre"""):
            salida.append({"id": f["id"], "clase": "persona",
                           "nombre": f["nombre"] or "(sin nombre)",
                           "clave_fuerte": f["clave_fuerte"],
                           "menciones": f["documentos"], "documentos": f["documentos"],
                           "quien": None, "carril": "persona"})
    return salida


def documento_del_cuil(cuil: str) -> str:
    """
    El número de documento que lleva adentro un CUIL. Son los ocho del medio.

    Sirve para reconocer que `20-60181590-8` y `DNI:60181590` son la misma persona: el
    carril de personas guarda el documento y el texto de las fojas trae el CUIL. Sin
    esto, la misma persona aparece dos veces en la lista de fichas.
    """
    d = re.sub(r"\D", "", cuil or "")
    return d[2:10] if len(d) == 11 else d


def _claves_persona(cx) -> set:
    """
    Las claves fuertes del carril de personas, en todas las formas comparables.

    El carril de siempre guarda `DNI:16613186`; las menciones traen el CUIL entero. Se
    devuelven las dos para que la comparación no dependa de cuál de los dos formatos
    llegó primero.
    """
    salida = set()
    for r in cx.execute("SELECT clave_fuerte FROM persona WHERE clave_fuerte IS NOT NULL"):
        crudo = r["clave_fuerte"]
        salida.add(crudo)
        solo = re.sub(r"\D", "", crudo)
        if solo:
            salida.add(solo)
    return salida


def ver(cx: sqlite3.Connection, entidad_id: int) -> dict:
    """La ficha de una entidad, con TODAS sus menciones y dónde está cada una."""
    e = cx.execute("SELECT * FROM entidad WHERE id=?", (entidad_id,)).fetchone()
    if not e:
        raise NoSePuede("esa entidad no existe")
    menciones = [{"id": m["id"], "literal": m["literal"], "documento_id": m["documento_id"],
                  "archivo": m["nombre"], "pagina_nro": m["pagina_nro"],
                  "origen": m["origen"], "confianza": m["confianza"],
                  "caja": None if m["x0"] is None else [m["x0"], m["y0"], m["x1"], m["y1"]]}
                 for m in cx.execute("""SELECT m.*, a.nombre FROM mencion m
                                          LEFT JOIN archivo a ON a.sha256 = m.sha256
                                         WHERE m.entidad_id=?
                                         ORDER BY a.nombre, m.pagina_nro""", (entidad_id,))]
    return {"id": e["id"], "clase": e["clase"], "nombre": e["nombre"],
            "clave_fuerte": e["clave_fuerte"], "quien": e["quien"],
            "menciones": menciones}


def sin_resolver(cx: sqlite3.Connection, limite: int = 200) -> list[dict]:
    """
    Las menciones que todavía no se sabe a quién se refieren.

    No son un error: son trabajo pendiente, y el sistema tiene que poder decir cuánto
    hay en vez de esconderlo.
    """
    return [{"id": m["id"], "clase": m["clase"], "literal": m["literal"],
             "norm": m["norm"], "archivo": m["nombre"], "pagina_nro": m["pagina_nro"],
             "documento_id": m["documento_id"], "origen": m["origen"],
             "confianza": m["confianza"]}
            for m in cx.execute("""SELECT m.*, a.nombre FROM mencion m
                                     LEFT JOIN archivo a ON a.sha256 = m.sha256
                                    WHERE m.entidad_id IS NULL
                                    ORDER BY m.clase, m.norm LIMIT ?""", (limite,))]
