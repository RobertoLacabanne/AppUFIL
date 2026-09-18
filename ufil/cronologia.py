"""
La cronología: qué pasó y cuándo, que no es el orden en que están las fojas.

Un documento no tiene «una fecha»
---------------------------------
Tiene varias, y son cosas distintas: la fecha del documento, la de la firma, la del
sello de recepción, la de la notificación, la del hecho que relata y la de su
incorporación al expediente. Un acta que relata un hecho de marzo, firmada en abril y
recibida en mayo, aparecería en el lugar equivocado si se las mezclara.

El orden cronológico no es el orden físico
------------------------------------------
Un expediente se arma por incorporación: lo que se agrega último puede relatar lo que
pasó primero. Ordenar por foja y llamarlo cronología es la forma más rápida de contar
mal una historia. Por eso esta vista existe aparte del orden de las fojas y del orden
de las piezas.

Lo que NO hace
--------------
No interpreta. Pone los hechos en el tiempo con su fuente al lado y deja que quien mire
saque las conclusiones. Que dos cosas pasaron el mismo día es un dato; que una explique
la otra es una lectura, y no la hace el sistema.
"""
from __future__ import annotations

import sqlite3

from .db import ahora

# Las clases de fecha que el pliego distingue. No es una lista cerrada por capricho:
# está acotada porque cada una significa algo distinto en un expediente y ponerle
# cualquier etiqueta a una fecha sería perder justamente la distinción.
CLASES = ("documento", "firma", "recepcion", "notificacion", "hecho", "incorporacion")

ETIQUETAS = {
    "documento": "fecha del documento",
    "firma": "firma",
    "recepcion": "recepción",
    "notificacion": "notificación",
    "hecho": "hecho relatado",
    "incorporacion": "incorporación al expediente",
}

# Qué campo extraído corresponde a qué clase de fecha. Sale de los perfiles, que son
# los que saben qué significa cada campo del formulario; acá sólo se traduce.
DE_CAMPO = {
    "fecha_inicio": "documento",
    "fecha_fin": "hecho",
    "fecha_firma": "firma",
    "fecha_recepcion": "recepcion",
    "fecha_notificacion": "notificacion",
}


class NoSePuede(ValueError):
    """Lo pedido no se puede hacer, y el motivo es para leer."""


def registrar(cx: sqlite3.Connection, documento_id: int, clase: str, fecha: str,
              *, origen: str, literal: str | None = None, campo_id: int | None = None,
              confianza: float | None = None, quien: str | None = None,
              nota: str | None = None) -> dict:
    """
    Anota un hecho en el tiempo. **Siempre con su fuente.**

    `origen` dice de dónde salió: `campo:<nombre>` cuando la trajo la extracción,
    `humano` cuando la cargó una persona. Una fecha sin fuente no entra, que es la misma
    regla que sostiene el resto del sistema: un dato que no se puede rastrear hasta el
    papel no es un dato.
    """
    if clase not in CLASES:
        raise NoSePuede(f"clase de fecha desconocida: {clase}. Las que hay son: "
                        + ", ".join(CLASES))
    if not (fecha or "").strip():
        raise NoSePuede("hace falta la fecha")
    if not (origen or "").strip():
        raise NoSePuede("una fecha sin fuente no se puede anotar")
    d = cx.execute("SELECT sha256, pagina_desde FROM documento WHERE id=?",
                   (documento_id,)).fetchone()
    if not d:
        raise NoSePuede("esa pieza no existe")
    cx.execute("""INSERT INTO evento (documento_id, sha256, pagina_nro, clase, fecha,
                                      literal, campo_id, origen, confianza, nota,
                                      quien, cuando)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                  ON CONFLICT(documento_id, clase, fecha, origen) DO UPDATE SET
                      literal=excluded.literal, campo_id=excluded.campo_id,
                      confianza=excluded.confianza, nota=excluded.nota,
                      quien=excluded.quien, cuando=excluded.cuando""",
               (documento_id, d["sha256"], d["pagina_desde"], clase, fecha, literal,
                campo_id, origen, confianza, nota, quien, ahora()))
    cx.commit()
    return {"ok": True, "documento_id": documento_id, "clase": clase, "fecha": fecha}


def poner_a_mano(cx: sqlite3.Connection, documento_id: int, clase: str, fecha: str,
                 quien: str, *, literal: str | None = None,
                 nota: str | None = None) -> dict:
    """Una persona anota una fecha que el sistema no sacó, y queda auditado."""
    if not (quien or "").strip():
        raise NoSePuede("hace falta indicar quién lo dice")
    r = registrar(cx, documento_id, clase, fecha, origen="humano", literal=literal,
                  confianza=1.0, quien=quien, nota=nota)
    d = cx.execute("SELECT sha256, orden FROM documento WHERE id=?",
                   (documento_id,)).fetchone()
    cx.execute("""INSERT INTO auditoria (campo_id, sha256, orden, campo_nombre, accion,
                                         valor_nuevo, quien, cuando)
                  VALUES (NULL,?,?,?,?,?,?,?)""",
               (d["sha256"], d["orden"], f"(fecha: {ETIQUETAS[clase]})", "fechar",
                fecha, quien, ahora()))
    cx.commit()
    return r


def poblar_desde_campos(cx: sqlite3.Connection) -> dict:
    """
    Arma la cronología con las fechas que ya se extrajeron de los documentos.

    Se apoya en `normalizacion`, que es donde vive la fecha en formato comparable, y
    conserva el literal del papel al lado. Sólo entran campos en estado firme: una fecha
    dudosa en una línea de tiempo se lee igual que una segura, y eso es justo lo que no
    puede pasar.

    No pisa lo que cargó una persona.
    """
    # La lista de estados firmes sale de ufil/confianza.py y no se repite acá: escrita
    # en dos lugares, el día que alguien agregue un estado se separan y lo que se rompe
    # en silencio es qué entra en la línea de tiempo.
    from . import confianza as cf
    firmes = cf.SQL_FIRMES
    puestos, salteados = 0, 0
    for c in cx.execute(f"""
            SELECT c.id, c.documento_id, c.nombre, c.valor_literal, c.confianza,
                   n.valor_norm
              FROM campo c JOIN normalizacion n ON n.campo_id = c.id
             WHERE n.tipo = 'fecha' AND n.valor_norm IS NOT NULL
               AND c.estado IN ({firmes})"""):
        clase = DE_CAMPO.get(c["nombre"])
        if not clase:
            salteados += 1
            continue
        ya = cx.execute("""SELECT 1 FROM evento
                            WHERE documento_id=? AND clase=? AND origen='humano'""",
                        (c["documento_id"], clase)).fetchone()
        if ya:
            continue                   # lo que dijo una persona no lo pisa una corrida
        try:
            registrar(cx, c["documento_id"], clase, c["valor_norm"],
                      origen=f"campo:{c['nombre']}", literal=c["valor_literal"],
                      campo_id=c["id"], confianza=c["confianza"])
            puestos += 1
        except NoSePuede:
            salteados += 1
    return {"eventos": puestos, "salteados": salteados}


def linea(cx: sqlite3.Connection, *, desde: str | None = None, hasta: str | None = None,
          clases: tuple = (), limite: int = 500) -> list[dict]:
    """
    La línea de tiempo, en orden de fecha y NO de foja.

    Cada hecho viene con su fuente: de qué pieza salió, de qué foja, de qué campo, y con
    qué confianza. Sin eso una cronología es una lista de afirmaciones sin respaldo.
    """
    where, args = ["1=1"], []
    if desde:
        where.append("e.fecha >= ?"); args.append(desde)
    if hasta:
        where.append("e.fecha <= ?"); args.append(hasta)
    if clases:
        malas = [c for c in clases if c not in CLASES]
        if malas:
            raise NoSePuede(f"clase de fecha desconocida: {', '.join(malas)}")
        where.append("e.clase IN (" + ",".join("?" * len(clases)) + ")")
        args.extend(clases)
    args.append(limite)
    return [{"fecha": f["fecha"], "clase": f["clase"],
             "que_es": ETIQUETAS.get(f["clase"], f["clase"]),
             "literal": f["literal"], "documento_id": f["documento_id"],
             "tipo": f["tipo"], "archivo": f["nombre"], "pagina_nro": f["pagina_nro"],
             "origen": f["origen"], "confianza": f["confianza"], "nota": f["nota"],
             "quien": f["quien"]}
            for f in cx.execute(f"""
                SELECT e.*, d.tipo, a.nombre FROM evento e
                  LEFT JOIN documento d ON d.id = e.documento_id
                  LEFT JOIN archivo a ON a.sha256 = e.sha256
                 WHERE {' AND '.join(where)}
                 ORDER BY e.fecha, e.clase, e.documento_id
                 LIMIT ?""", args)]


def de_documento(cx: sqlite3.Connection, documento_id: int) -> list[dict]:
    """Todas las fechas de una pieza, con lo que cada una significa."""
    return [{"clase": f["clase"], "que_es": ETIQUETAS.get(f["clase"], f["clase"]),
             "fecha": f["fecha"], "literal": f["literal"], "origen": f["origen"],
             "confianza": f["confianza"], "quien": f["quien"]}
            for f in cx.execute("""SELECT * FROM evento WHERE documento_id=?
                                    ORDER BY fecha, clase""", (documento_id,))]


def desordenes(cx: sqlite3.Connection) -> list[dict]:
    """
    Fechas que no pueden ser, y el orden físico que no coincide con el cronológico.

    Las dos cosas son HECHOS, no errores del sistema, y se señalan sin interpretarlas:

      * un documento firmado antes de la fecha que lleva, o recibido antes de firmarse,
        puede ser un error de tipeo del papel y puede ser otra cosa;
      * una pieza que está antes en el expediente y es posterior en el tiempo es lo
        normal en un expediente armado por incorporación, y también es donde se ve un
        documento agregado después.
    """
    salida = []
    for f in cx.execute("""
            SELECT e1.documento_id, e1.clase AS a, e1.fecha AS fa,
                   e2.clase AS b, e2.fecha AS fb, d.tipo, x.nombre
              FROM evento e1 JOIN evento e2 ON e2.documento_id = e1.documento_id
              LEFT JOIN documento d ON d.id = e1.documento_id
              LEFT JOIN archivo x ON x.sha256 = e1.sha256
             WHERE e1.clase='documento' AND e2.clase IN ('firma','recepcion')
               AND e2.fecha < e1.fecha"""):
        salida.append({
            "clase": "fecha_imposible", "documento_id": f["documento_id"],
            "archivo": f["nombre"], "tipo": f["tipo"],
            "detalle": f"la {ETIQUETAS[f['b']]} ({f['fb']}) es anterior a la "
                       f"{ETIQUETAS['documento']} ({f['fa']})"})

    previa = None
    for f in cx.execute("""
            SELECT e.documento_id, e.fecha, e.pagina_nro, d.orden, x.nombre
              FROM evento e LEFT JOIN documento d ON d.id = e.documento_id
              LEFT JOIN archivo x ON x.sha256 = e.sha256
             WHERE e.clase='documento' AND e.sha256 IS NOT NULL
             ORDER BY x.nombre, d.orden"""):
        if previa and previa["nombre"] == f["nombre"] and f["fecha"] < previa["fecha"]:
            salida.append({
                "clase": "fuera_de_orden", "documento_id": f["documento_id"],
                "archivo": f["nombre"], "tipo": None,
                "detalle": f"está después en el expediente ({f['fecha']}) que la pieza "
                           f"anterior ({previa['fecha']}), que es normal en un "
                           f"expediente armado por incorporación"})
        previa = f
    return salida
