"""
El conjunto documental: una entrega, no un archivo.

Una oficina que contesta un oficio no manda un PDF: manda nueve, y el noveno sigue
donde terminó el octavo. Ese orden es información del expediente y hoy vive solamente
en el nombre de los archivos, que es el peor lugar posible: se pierde apenas alguien
renombra uno, y con él se pierde la única pista de que una pieza sigue en la parte
siguiente.

Acá el conjunto es una cosa propia, con su orden, y un archivo puede pertenecer a más
de uno: el mismo PDF puede llegar dos veces en dos entregas distintas, y eso también es
un hecho del expediente que hay que poder ver.
"""
from __future__ import annotations

import sqlite3

from .db import ahora


class NoSePuede(ValueError):
    """Lo pedido no se puede hacer, y el motivo es para leer."""


def crear(cx: sqlite3.Connection, nombre: str, *, organismo: str | None = None,
          expediente: str | None = None, anio: int | None = None,
          nota: str | None = None) -> dict:
    nombre = (nombre or "").strip()
    if not nombre:
        raise NoSePuede("el conjunto necesita un nombre para poder encontrarlo después")
    cid = cx.execute(
        """INSERT INTO conjunto (nombre, organismo, expediente, anio, nota, creado_en)
           VALUES (?,?,?,?,?,?)""",
        (nombre, organismo or None, expediente or None, anio, nota or None,
         ahora())).lastrowid
    cx.commit()
    return {"id": cid, "nombre": nombre}


def agregar(cx: sqlite3.Connection, conjunto_id: int, sha256: str,
            orden: int | None = None) -> dict:
    """
    Suma un archivo al conjunto, en su posición.

    Sin `orden` va al final, que es lo que corresponde cuando alguien carga las partes
    en el orden en que llegaron.
    """
    if not cx.execute("SELECT 1 FROM conjunto WHERE id=?", (conjunto_id,)).fetchone():
        raise NoSePuede("ese conjunto no existe")
    if not cx.execute("SELECT 1 FROM archivo WHERE sha256=?", (sha256,)).fetchone():
        raise NoSePuede("ese archivo no está cargado")
    if orden is None:
        orden = (cx.execute("SELECT COALESCE(MAX(orden),0) FROM conjunto_archivo "
                            "WHERE conjunto_id=?", (conjunto_id,)).fetchone()[0] or 0) + 1
    cx.execute("""INSERT INTO conjunto_archivo (conjunto_id, sha256, orden)
                  VALUES (?,?,?)
                  ON CONFLICT(conjunto_id, sha256) DO UPDATE SET orden=excluded.orden""",
               (conjunto_id, sha256, orden))
    cx.commit()
    return {"ok": True, "conjunto_id": conjunto_id, "sha256": sha256, "orden": orden}


def quitar(cx: sqlite3.Connection, conjunto_id: int, sha256: str) -> dict:
    """Saca un archivo del conjunto. El archivo NO se toca: sigue cargado."""
    cx.execute("DELETE FROM conjunto_archivo WHERE conjunto_id=? AND sha256=?",
               (conjunto_id, sha256))
    cx.commit()
    return {"ok": True}


def reordenar(cx: sqlite3.Connection, conjunto_id: int, shas: list) -> dict:
    """
    Fija el orden de las partes de una vez, con la lista completa.

    De a uno no se puede: mover la parte 5 al lugar 2 cambia la posición de tres
    archivos más, y hacerlo con llamadas sueltas deja el conjunto en estados
    intermedios donde dos partes comparten posición.
    """
    tengo = {r["sha256"] for r in cx.execute(
        "SELECT sha256 FROM conjunto_archivo WHERE conjunto_id=?", (conjunto_id,))}
    if set(shas) != tengo:
        raise NoSePuede("hay que mandar todas las partes del conjunto, y sólo ésas")
    for i, sha in enumerate(shas, start=1):
        cx.execute("UPDATE conjunto_archivo SET orden=? WHERE conjunto_id=? AND sha256=?",
                   (i, conjunto_id, sha))
    cx.commit()
    return {"ok": True, "partes": len(shas)}


def listar(cx: sqlite3.Connection) -> list[dict]:
    return [{"id": f["id"], "nombre": f["nombre"], "organismo": f["organismo"],
             "expediente": f["expediente"], "anio": f["anio"], "nota": f["nota"],
             "archivos": f["archivos"], "paginas": f["paginas"] or 0}
            for f in cx.execute("""
                SELECT c.*,
                       (SELECT COUNT(*) FROM conjunto_archivo x WHERE x.conjunto_id=c.id)
                         AS archivos,
                       (SELECT SUM(a.paginas) FROM conjunto_archivo x
                          JOIN archivo a ON a.sha256 = x.sha256
                         WHERE x.conjunto_id=c.id) AS paginas
                  FROM conjunto c ORDER BY c.nombre""")]


def ver(cx: sqlite3.Connection, conjunto_id: int) -> dict:
    """El conjunto con sus partes EN ORDEN, que es lo único que no se puede reconstruir."""
    c = cx.execute("SELECT * FROM conjunto WHERE id=?", (conjunto_id,)).fetchone()
    if not c:
        raise NoSePuede("ese conjunto no existe")
    partes = [{"sha256": f["sha256"], "nombre": f["nombre"], "orden": f["orden"],
               "paginas": f["paginas"] or 0,
               "piezas": f["piezas"]}
              for f in cx.execute("""
                  SELECT x.sha256, x.orden, a.nombre, a.paginas,
                         (SELECT COUNT(*) FROM documento d WHERE d.sha256 = x.sha256)
                           AS piezas
                    FROM conjunto_archivo x JOIN archivo a ON a.sha256 = x.sha256
                   WHERE x.conjunto_id=? ORDER BY x.orden""", (conjunto_id,))]
    return {"id": c["id"], "nombre": c["nombre"], "organismo": c["organismo"],
            "expediente": c["expediente"], "anio": c["anio"], "nota": c["nota"],
            "partes": partes}


def de_archivo(cx: sqlite3.Connection, sha256: str) -> list[dict]:
    """A qué conjuntos pertenece un archivo, y en qué posición de cada uno."""
    return [{"id": f["id"], "nombre": f["nombre"], "orden": f["orden"]}
            for f in cx.execute("""SELECT c.id, c.nombre, x.orden
                                     FROM conjunto_archivo x
                                     JOIN conjunto c ON c.id = x.conjunto_id
                                    WHERE x.sha256=? ORDER BY c.nombre""", (sha256,))]


def vecino(cx: sqlite3.Connection, sha256: str, salto: int = 1) -> dict | None:
    """
    La parte siguiente (o anterior) del conjunto al que pertenece este archivo.

    Es lo que hace falta para preguntarse si una pieza que termina en la última foja de
    una parte sigue en la primera de la que viene. El sistema no lo afirma solo —eso lo
    dice una persona, ver ufil/piezas.py— pero sí puede decir dónde mirar.
    """
    for c in de_archivo(cx, sha256):
        f = cx.execute("""SELECT x.sha256, a.nombre, x.orden FROM conjunto_archivo x
                            JOIN archivo a ON a.sha256 = x.sha256
                           WHERE x.conjunto_id=? AND x.orden=?""",
                       (c["id"], c["orden"] + salto)).fetchone()
        if f:
            return {"conjunto": c["nombre"], "sha256": f["sha256"],
                    "nombre": f["nombre"], "orden": f["orden"]}
    return None
