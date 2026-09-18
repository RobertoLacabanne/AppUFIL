"""
La pieza documental: lo que el sistema todavía no sabe leer, y lo que sigue en otro PDF.

Dos cosas que el núcleo documental necesita y que no se resuelven solas:

**Un documento que el sistema no sabe leer sigue siendo un documento.** Cuando ningún
extractor reconoce una pieza, queda con `estado='sin_perfil'`: se ve, se cuenta, se
busca y se puede clasificar a mano. No se descarta y no se fuerza a ser contrato o
factura sólo porque es lo más parecido. Y el día que aparezca un extractor nuevo, se le
aplica sin volver a subir el archivo.

**El límite de un PDF no es el límite de un documento.** Un remito de cuatro fojas puede
quedar partido entre dos archivos porque así salió del escáner. Eso no lo puede adivinar
el sistema con seguridad, así que lo dice una persona y queda registrado quién lo dijo.
"""
from __future__ import annotations

import sqlite3

from . import clasificacion as cl
from .db import ahora


class NoSePuede(ValueError):
    """Lo pedido no se puede hacer, y el motivo es para leer."""


def _pieza(cx: sqlite3.Connection, documento_id: int):
    f = cx.execute("""SELECT id, sha256, orden, clave, pagina_desde, pagina_hasta,
                             tipo, perfil, estado, clasificado_por
                        FROM documento WHERE id=?""", (documento_id,)).fetchone()
    if not f:
        raise NoSePuede(f"no existe la pieza {documento_id}")
    return f


def sin_reconocer(cx: sqlite3.Connection, limite: int = 200) -> list[dict]:
    """
    Las piezas que ningún extractor reconoce todavía.

    No son un error ni un descarte: son documentos cargados que el sistema no sabe
    leer. Se listan para que una persona pueda mirarlos, decir qué son, y para que se
    sepa qué le falta aprender al sistema.
    """
    return [{"documento_id": f["id"], "sha256": f["sha256"], "archivo": f["nombre"],
             "orden": f["orden"], "clave": f["clave"],
             "pagina_desde": f["pagina_desde"], "pagina_hasta": f["pagina_hasta"],
             "fojas": (f["pagina_hasta"] or f["pagina_desde"] or 0)
                      - (f["pagina_desde"] or 0) + 1,
             "tipo": f["tipo"], "clasificado_por": f["clasificado_por"]}
            for f in cx.execute("""
                SELECT d.*, a.nombre FROM documento d
                  JOIN archivo a ON a.sha256 = d.sha256
                 WHERE d.estado = 'sin_perfil'
                 ORDER BY a.nombre, d.orden LIMIT ?""", (limite,))]


def tipos_posibles() -> list[dict]:
    """
    El catálogo documental, para ofrecerlo. **No es una lista cerrada.**

    Sale de ufil/clasificacion.py, que es donde se decide qué tipos conoce el sistema,
    para que agregar uno sea tocar un solo lugar y no dos.
    """
    return [{"clave": t.clave, "nombre": getattr(t, "nombre", t.clave),
             "familia": cl.familia(t.clave)} for t in cl.TIPOS]


def clasificar_a_mano(cx: sqlite3.Connection, documento_id: int, tipo: str,
                      quien: str) -> dict:
    """
    Una persona dice qué es esta pieza.

    Queda registrado quién lo dijo y cuándo, y a partir de ahí **el sistema no le vuelve
    a cambiar el tipo**: una resegmentación posterior respeta la clasificación humana
    (ver `segmentar_piezas`). Es la misma regla que sostiene todo lo demás acá: lo que
    decidió una persona no lo pisa una corrida.
    """
    if not (quien or "").strip():
        raise NoSePuede("hace falta indicar quién clasifica")
    tipo = (tipo or "").strip()
    if not tipo:
        raise NoSePuede("hace falta decir qué es la pieza")
    conocidos = {t["clave"] for t in tipos_posibles()}
    if tipo not in conocidos and tipo != "desconocido":
        raise NoSePuede(f"tipo desconocido: {tipo}. Los que hay son: "
                        + ", ".join(sorted(conocidos)))
    p = _pieza(cx, documento_id)
    cx.execute("""UPDATE documento SET tipo=?, clasificado_por=?, clasificado_en=?
                   WHERE id=?""", (tipo, quien, ahora(), documento_id))
    cx.execute("""INSERT INTO auditoria (campo_id, sha256, orden, campo_nombre, accion,
                                         valor_anterior, valor_nuevo, quien, cuando)
                  VALUES (NULL,?,?,?,?,?,?,?,?)""",
               (p["sha256"], p["orden"], "(tipo de la pieza)", "clasificar",
                p["tipo"], tipo, quien, ahora()))
    cx.commit()
    return {"ok": True, "documento_id": documento_id, "tipo": tipo, "quien": quien}


def continuar_en(cx: sqlite3.Connection, documento_id: int, sha256: str,
                 pagina_desde: int, pagina_hasta: int, quien: str) -> dict:
    """
    Dice que esta pieza SIGUE en otro tramo, de este archivo o de otro.

    Lo dice una persona. El sistema puede sospecharlo —dos partes de un escaneo, un
    remito cortado al final del PDF— pero no puede afirmarlo: dos documentos parecidos
    pegados uno atrás del otro se ven igual que uno partido al medio. Afirmarlo solo
    sería inventar una pieza que nadie vio.
    """
    if not (quien or "").strip():
        raise NoSePuede("hace falta indicar quién lo dice")
    p = _pieza(cx, documento_id)
    if not cx.execute("SELECT 1 FROM archivo WHERE sha256=?", (sha256,)).fetchone():
        raise NoSePuede("ese archivo no está cargado")
    if pagina_desde is None or pagina_hasta is None or pagina_hasta < pagina_desde:
        raise NoSePuede("el tramo tiene que ir de una foja a otra posterior o igual")
    hay = cx.execute("""SELECT COUNT(*) FROM pagina
                         WHERE sha256=? AND nro BETWEEN ? AND ?""",
                     (sha256, pagina_desde, pagina_hasta)).fetchone()[0]
    if hay != (pagina_hasta - pagina_desde + 1):
        raise NoSePuede("ese archivo no tiene todas esas fojas")
    if sha256 == p["sha256"] and not (
            pagina_hasta < (p["pagina_desde"] or 0) or pagina_desde > (p["pagina_hasta"] or 0)):
        raise NoSePuede("ese tramo ya es parte de la pieza")

    orden = (cx.execute("SELECT COALESCE(MAX(orden),0) FROM pieza_tramo WHERE documento_id=?",
                        (documento_id,)).fetchone()[0] or 0) + 1
    cx.execute("""INSERT OR REPLACE INTO pieza_tramo
                    (documento_id, sha256, pagina_desde, pagina_hasta, orden, quien, cuando)
                  VALUES (?,?,?,?,?,?,?)""",
               (documento_id, sha256, pagina_desde, pagina_hasta, orden, quien, ahora()))
    cx.execute("""INSERT INTO auditoria (campo_id, sha256, orden, campo_nombre, accion,
                                         valor_nuevo, quien, cuando)
                  VALUES (NULL,?,?,?,?,?,?,?)""",
               (p["sha256"], p["orden"], "(continuación de la pieza)", "continuar",
                f"{sha256[:12]}… fojas {pagina_desde}-{pagina_hasta}", quien, ahora()))
    cx.commit()
    return {"ok": True, "documento_id": documento_id, "tramos": tramos(cx, documento_id)}


def separar_continuacion(cx: sqlite3.Connection, tramo_id: int, quien: str) -> dict:
    """Deshace una continuación. Queda el rastro de que se hizo y de quién la deshizo."""
    f = cx.execute("SELECT * FROM pieza_tramo WHERE id=?", (tramo_id,)).fetchone()
    if not f:
        raise NoSePuede("esa continuación no existe")
    p = _pieza(cx, f["documento_id"])
    cx.execute("DELETE FROM pieza_tramo WHERE id=?", (tramo_id,))
    cx.execute("""INSERT INTO auditoria (campo_id, sha256, orden, campo_nombre, accion,
                                         valor_anterior, quien, cuando)
                  VALUES (NULL,?,?,?,?,?,?,?)""",
               (p["sha256"], p["orden"], "(continuación de la pieza)", "separar",
                f"{f['sha256'][:12]}… fojas {f['pagina_desde']}-{f['pagina_hasta']}",
                quien, ahora()))
    cx.commit()
    return {"ok": True}


def tramos(cx: sqlite3.Connection, documento_id: int) -> list[dict]:
    """
    Todos los tramos de una pieza, en orden de lectura. El primero es el de la pieza
    misma; los demás son las continuaciones que alguien marcó.
    """
    p = _pieza(cx, documento_id)
    salida = [{"id": None, "sha256": p["sha256"],
               "archivo": cx.execute("SELECT nombre FROM archivo WHERE sha256=?",
                                     (p["sha256"],)).fetchone()["nombre"],
               "pagina_desde": p["pagina_desde"], "pagina_hasta": p["pagina_hasta"],
               "principal": True, "quien": None}]
    for f in cx.execute("""SELECT t.*, a.nombre FROM pieza_tramo t
                             JOIN archivo a ON a.sha256 = t.sha256
                            WHERE t.documento_id=? ORDER BY t.orden""", (documento_id,)):
        salida.append({"id": f["id"], "sha256": f["sha256"], "archivo": f["nombre"],
                       "pagina_desde": f["pagina_desde"], "pagina_hasta": f["pagina_hasta"],
                       "principal": False, "quien": f["quien"]})
    return salida
