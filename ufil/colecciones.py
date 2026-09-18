"""
Lo que alguien quiere volver a mirar: consultas guardadas y colecciones.

Dos cosas que hoy se pierden al cerrar el navegador y que cuestan caro rehacer.

Una **consulta guardada** es una búsqueda con sus filtros y con nombre. En un legajo que
se trabaja durante meses, «los comprobantes de este proveedor entre marzo y julio» se
vuelve a escribir veinte veces y cada vez con una variante distinta, así que dos
personas que comparan resultados no están mirando lo mismo.

Una **colección** es un conjunto de piezas elegidas a mano: lo que alguien apartó para
un escrito, para una audiencia, para revisar mañana. **No es el resultado de una
consulta.** Esa diferencia es la que importa: una consulta se vuelve a correr y cambia
cuando cambian los datos; una colección tiene que quedar igual hasta que la persona que
la armó la cambie. Si un escrito cita «las nueve piezas de la colección X», esas nueve
no pueden pasar a ser once porque alguien cargó un PDF nuevo.
"""
from __future__ import annotations

import json
import sqlite3

from .db import ahora

CLASES = ("documento", "foja", "entidad")


class NoSePuede(ValueError):
    """Lo pedido no se puede hacer, y el motivo es para leer."""


# ── Consultas guardadas ──────────────────────────────────────────────────────
def guardar_consulta(cx: sqlite3.Connection, nombre: str, consulta: str, quien: str,
                     *, filtros: dict | None = None) -> dict:
    nombre = (nombre or "").strip()
    consulta = (consulta or "").strip()
    if not nombre:
        raise NoSePuede("la consulta necesita un nombre para poder encontrarla después")
    if not consulta:
        raise NoSePuede("no se puede guardar una consulta vacía")
    if not (quien or "").strip():
        raise NoSePuede("hace falta indicar quién la guarda")
    cx.execute("""INSERT INTO consulta_guardada (nombre, consulta, filtros, quien, creado_en)
                  VALUES (?,?,?,?,?)
                  ON CONFLICT(nombre) DO UPDATE SET consulta=excluded.consulta,
                      filtros=excluded.filtros, quien=excluded.quien""",
               (nombre, consulta, json.dumps(filtros or {}, ensure_ascii=False),
                quien, ahora()))
    cx.commit()
    return {"ok": True, "nombre": nombre}


def consultas(cx: sqlite3.Connection) -> list[dict]:
    return [{"id": f["id"], "nombre": f["nombre"], "consulta": f["consulta"],
             "filtros": json.loads(f["filtros"] or "{}"), "quien": f["quien"],
             "creado_en": f["creado_en"], "usada_en": f["usada_en"], "veces": f["veces"]}
            for f in cx.execute("SELECT * FROM consulta_guardada ORDER BY nombre")]


def usar_consulta(cx: sqlite3.Connection, consulta_id: int) -> dict:
    """
    Devuelve la consulta y anota que se usó.

    Saber cuáles se usan y cuáles no es lo que después permite limpiar la lista sin
    borrar la que alguien necesita una vez por mes.
    """
    f = cx.execute("SELECT * FROM consulta_guardada WHERE id=?", (consulta_id,)).fetchone()
    if not f:
        raise NoSePuede("esa consulta no existe")
    cx.execute("UPDATE consulta_guardada SET usada_en=?, veces=veces+1 WHERE id=?",
               (ahora(), consulta_id))
    cx.commit()
    return {"id": f["id"], "nombre": f["nombre"], "consulta": f["consulta"],
            "filtros": json.loads(f["filtros"] or "{}")}


def borrar_consulta(cx: sqlite3.Connection, consulta_id: int) -> dict:
    cx.execute("DELETE FROM consulta_guardada WHERE id=?", (consulta_id,))
    cx.commit()
    return {"ok": True}


# ── Colecciones ──────────────────────────────────────────────────────────────
def crear(cx: sqlite3.Connection, nombre: str, quien: str,
          nota: str | None = None) -> dict:
    nombre = (nombre or "").strip()
    if not nombre:
        raise NoSePuede("la colección necesita un nombre")
    if not (quien or "").strip():
        raise NoSePuede("hace falta indicar quién la crea")
    if cx.execute("SELECT 1 FROM coleccion WHERE nombre=?", (nombre,)).fetchone():
        raise NoSePuede(f"ya hay una colección que se llama «{nombre}»")
    cid = cx.execute("""INSERT INTO coleccion (nombre, nota, quien, creado_en)
                        VALUES (?,?,?,?)""", (nombre, nota, quien, ahora())).lastrowid
    cx.commit()
    return {"id": cid, "nombre": nombre}


def agregar(cx: sqlite3.Connection, coleccion_id: int, clase: str, referencia: str,
            quien: str, *, nota: str | None = None) -> dict:
    """Aparta algo en la colección. Lo mismo dos veces no la duplica."""
    if clase not in CLASES:
        raise NoSePuede(f"clase desconocida: {clase}. Las que hay son: " + ", ".join(CLASES))
    if not (quien or "").strip():
        raise NoSePuede("hace falta indicar quién lo aparta")
    if not cx.execute("SELECT 1 FROM coleccion WHERE id=?", (coleccion_id,)).fetchone():
        raise NoSePuede("esa colección no existe")
    referencia = str(referencia).strip()
    if not referencia:
        raise NoSePuede("hace falta decir qué se aparta")
    _existe(cx, clase, referencia)
    orden = (cx.execute("SELECT COALESCE(MAX(orden),0) FROM coleccion_item "
                        "WHERE coleccion_id=?", (coleccion_id,)).fetchone()[0] or 0) + 1
    cx.execute("""INSERT INTO coleccion_item (coleccion_id, clase, referencia, nota,
                                              orden, quien, cuando)
                  VALUES (?,?,?,?,?,?,?)
                  ON CONFLICT(coleccion_id, clase, referencia) DO UPDATE SET
                      nota=excluded.nota""",
               (coleccion_id, clase, referencia, nota, orden, quien, ahora()))
    cx.commit()
    return {"ok": True, "coleccion_id": coleccion_id, "clase": clase,
            "referencia": referencia}


def _existe(cx, clase: str, referencia: str) -> None:
    """
    Que lo que se aparta exista de verdad.

    Una colección con referencias colgadas es peor que no tenerla: quien la abre para
    escribir un punteo se encuentra con huecos y no sabe si es un error del sistema o si
    la pieza se borró por algo.
    """
    if clase == "documento":
        if not cx.execute("SELECT 1 FROM documento WHERE id=?", (referencia,)).fetchone():
            raise NoSePuede("esa pieza no existe")
    elif clase == "entidad":
        if not cx.execute("SELECT 1 FROM entidad WHERE id=?", (referencia,)).fetchone():
            raise NoSePuede("esa entidad no existe")
    elif clase == "foja":
        sha, _, nro = str(referencia).partition(":")
        if not nro.isdigit() or not cx.execute(
                "SELECT 1 FROM pagina WHERE sha256=? AND nro=?", (sha, int(nro))).fetchone():
            raise NoSePuede("esa foja no existe; se escribe «<sha256>:<nro>»")


def quitar(cx: sqlite3.Connection, coleccion_id: int, clase: str,
           referencia: str) -> dict:
    cx.execute("""DELETE FROM coleccion_item WHERE coleccion_id=? AND clase=?
                   AND referencia=?""", (coleccion_id, clase, str(referencia)))
    cx.commit()
    return {"ok": True}


def listar(cx: sqlite3.Connection) -> list[dict]:
    return [{"id": f["id"], "nombre": f["nombre"], "nota": f["nota"],
             "quien": f["quien"], "creado_en": f["creado_en"], "items": f["items"]}
            for f in cx.execute("""
                SELECT c.*, (SELECT COUNT(*) FROM coleccion_item i
                              WHERE i.coleccion_id = c.id) AS items
                  FROM coleccion c ORDER BY c.nombre""")]


def ver(cx: sqlite3.Connection, coleccion_id: int) -> dict:
    """
    La colección con lo que tiene adentro, ya resuelto a algo que se puede mostrar.

    Cada ítem trae de dónde sale: archivo y fojas de la pieza, o el nombre de la
    entidad. Una colección que sólo guarda ids obliga a quien la abre a ir a buscar qué
    era cada cosa.
    """
    c = cx.execute("SELECT * FROM coleccion WHERE id=?", (coleccion_id,)).fetchone()
    if not c:
        raise NoSePuede("esa colección no existe")
    items = []
    for f in cx.execute("""SELECT * FROM coleccion_item WHERE coleccion_id=?
                            ORDER BY orden""", (coleccion_id,)):
        items.append({**_describir(cx, f["clase"], f["referencia"]),
                      "clase": f["clase"], "referencia": f["referencia"],
                      "nota": f["nota"], "quien": f["quien"], "orden": f["orden"]})
    return {"id": c["id"], "nombre": c["nombre"], "nota": c["nota"],
            "quien": c["quien"], "items": items}


def _describir(cx, clase: str, referencia: str) -> dict:
    if clase == "documento":
        f = cx.execute("""SELECT d.tipo, d.pagina_desde, d.pagina_hasta, a.nombre
                            FROM documento d JOIN archivo a ON a.sha256 = d.sha256
                           WHERE d.id=?""", (referencia,)).fetchone()
        if f:
            return {"que_es": f["tipo"], "archivo": f["nombre"],
                    "fojas": f"{f['pagina_desde']}-{f['pagina_hasta']}"}
    elif clase == "entidad":
        f = cx.execute("SELECT clase, nombre FROM entidad WHERE id=?",
                       (referencia,)).fetchone()
        if f:
            return {"que_es": f["clase"], "archivo": None, "nombre": f["nombre"]}
    elif clase == "foja":
        sha, _, nro = str(referencia).partition(":")
        f = cx.execute("SELECT nombre FROM archivo WHERE sha256=?", (sha,)).fetchone()
        if f:
            return {"que_es": "foja", "archivo": f["nombre"], "fojas": nro}
    # Si no se pudo describir, se dice. No se inventa un rótulo.
    return {"que_es": "(ya no está)", "archivo": None}


def de_documento(cx: sqlite3.Connection, documento_id: int) -> list[dict]:
    """En qué colecciones está apartada esta pieza."""
    return [{"id": f["id"], "nombre": f["nombre"]}
            for f in cx.execute("""SELECT c.id, c.nombre FROM coleccion_item i
                                     JOIN coleccion c ON c.id = i.coleccion_id
                                    WHERE i.clase='documento' AND i.referencia=?
                                    ORDER BY c.nombre""", (str(documento_id),))]
