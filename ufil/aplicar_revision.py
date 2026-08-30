"""
Aplicación de una decisión humana sobre un campo.

Vive aparte del servidor porque lo usan dos caminos: la interfaz (cuando alguien
decide) y la Capa 2 (cuando se reprocesa el lote y hay que volver a aplicar lo que ya
se decidió antes). Que sea una sola función evita que los dos caminos se separen.
"""
from __future__ import annotations

import sqlite3

from .capa2_campos import PARSERS   # OJO: no volver a importarlo dentro de `aplicar`:
                                   # un import local lo vuelve variable de función y
                                   # rompe las ramas que lo usan antes.
from .db import ahora

ACCIONES = ("verificar", "corregir", "ilegible", "ausente", "ambiguo", "revertir")


def _tipo_de(cx, campo_id: int) -> str:
    r = cx.execute("SELECT tipo FROM normalizacion WHERE campo_id=?", (campo_id,)).fetchone()
    if r:
        return r["tipo"]
    nombre = cx.execute("SELECT nombre FROM campo WHERE id=?", (campo_id,)).fetchone()["nombre"]
    return {"monto": "monto", "documento": "documento",
            "fecha_inicio": "fecha", "fecha_fin": "fecha", "nombre": "nombre"}.get(nombre, "texto")


def _anclaje_de_pagina(cx, campo_id: int):
    """
    Anclaje para un valor cargado a mano sobre un campo que no tenía recuadro.

    La restricción 4 existe para poder ver el dato en la imagen de un clic. Cuando el
    valor lo escribió una persona mirando el folio, el anclaje honesto es el folio
    entero: te lleva a la página que esa persona miró. Se marca `ruta='humano'` para
    que nunca se confunda con una lectura automática.
    """
    c = cx.execute("SELECT documento_id, pagina_nro FROM campo WHERE id=?", (campo_id,)).fetchone()
    nro = c["pagina_nro"] or 1
    p = cx.execute("""SELECT p.ancho_pt, p.alto_pt FROM pagina p
                        JOIN documento d ON d.sha256 = p.sha256
                       WHERE d.id=? AND p.nro=?""", (c["documento_id"], nro)).fetchone()
    if not p:
        return nro, 0.0, 0.0, 595.0, 842.0
    return nro, 0.0, 0.0, float(p["ancho_pt"]), float(p["alto_pt"])


def aplicar(cx: sqlite3.Connection, campo_id: int, accion: str, valor, quien: str,
            *, registrar: bool = True) -> dict:
    if not (quien or "").strip():
        raise ValueError("hace falta indicar quién revisa")
    if accion not in ACCIONES:
        raise ValueError(f"acción desconocida: {accion}")
    c = cx.execute("SELECT * FROM campo WHERE id=?", (campo_id,)).fetchone()
    if not c:
        raise KeyError("campo inexistente")

    # Antes de tocar nada, guardar lo que había leído la máquina (una sola vez: si ya
    # está guardado, es porque esto ya se revisó antes y ese es el estado original).
    if c["valor_auto"] is None and c["motivo_auto"] is None:
        cx.execute("""UPDATE campo SET valor_auto=?, motivo_auto=?, conf_auto=?, ruta_auto=?
                       WHERE id=?""",
                   (c["valor_literal"], c["nulo_motivo"], c["confianza"], c["ruta"], campo_id))
        c = cx.execute("SELECT * FROM campo WHERE id=?", (campo_id,)).fetchone()

    if accion == "revertir":
        # Lo que define si hay algo que deshacer es si ALGUIEN lo tocó, no el estado:
        # un campo puede estar en la cola por dudoso sin que nadie lo haya decidido.
        if not c["revisado_por"]:
            raise ValueError("nadie decidió sobre este campo: no hay nada que deshacer")
        cx.execute("""UPDATE campo SET valor_literal=?, nulo_motivo=?, confianza=?, ruta=?,
                             estado='automatico', revisado_por=NULL, revisado_en=NULL
                       WHERE id=?""",
                   (c["valor_auto"], c["motivo_auto"], c["conf_auto"], c["ruta_auto"], campo_id))
        cx.execute("DELETE FROM normalizacion WHERE campo_id=?", (campo_id,))
        if c["valor_auto"] is not None:
            tipo = _tipo_de(cx, campo_id)
            _, norm, _ = PARSERS.get(tipo, PARSERS["texto"])(c["valor_auto"])
            cx.execute("""INSERT INTO normalizacion (campo_id,tipo,valor_norm,nota)
                          VALUES (?,?,?,'lectura automática restituida')""",
                       (campo_id, tipo, norm))
        # Vuelve a la cola si la lectura automática era dudosa.
        dudoso = (c["motivo_auto"] is not None
                  or (c["conf_auto"] is not None and c["conf_auto"] < 0.85))
        cx.execute("UPDATE campo SET estado=? WHERE id=?",
                   ("a_revisar" if dudoso else "automatico", campo_id))
        d = cx.execute("SELECT sha256, orden FROM documento WHERE id=?",
                       (c["documento_id"],)).fetchone()
        cx.execute("DELETE FROM revision_humana WHERE sha256=? AND orden=? AND campo=?",
                   (d["sha256"], d["orden"], c["nombre"]))
        cx.commit()
        return {"ok": True, "revertido": True}

    if accion == "verificar":
        if c["valor_literal"] is None and c["nulo_motivo"] is None:
            raise ValueError("no hay nada que verificar")
        cx.execute("""UPDATE campo SET estado='verificado', revisado_por=?, revisado_en=?
                       WHERE id=?""", (quien, ahora(), campo_id))

    elif accion == "corregir":
        if valor is None or str(valor).strip() == "":
            raise ValueError("una corrección necesita un valor")
        tipo = _tipo_de(cx, campo_id)
        literal, norm, motivo = PARSERS.get(tipo, PARSERS["texto"])(str(valor))
        if motivo:
            raise ValueError(f"el valor cargado no se puede interpretar como {tipo}: {motivo}")
        nro, x0, y0, x1, y1 = ((c["pagina_nro"], c["x0"], c["y0"], c["x1"], c["y1"])
                               if c["x0"] is not None else _anclaje_de_pagina(cx, campo_id))
        cx.execute("""UPDATE campo SET valor_literal=?, nulo_motivo=NULL, estado='corregido',
                             confianza=1.0, ruta='humano', pagina_nro=?, x0=?, y0=?, x1=?, y1=?,
                             revisado_por=?, revisado_en=? WHERE id=?""",
                   (literal, nro, x0, y0, x1, y1, quien, ahora(), campo_id))
        cx.execute("""INSERT INTO normalizacion (campo_id,tipo,valor_norm,nota)
                      VALUES (?,?,?,'cargado a mano')
                      ON CONFLICT(campo_id) DO UPDATE SET valor_norm=excluded.valor_norm,
                                                          nota='cargado a mano'""",
                   (campo_id, tipo, norm))

    else:                                    # ilegible | ausente | ambiguo, en firme
        cx.execute("""UPDATE campo SET valor_literal=NULL, nulo_motivo=?, estado='verificado',
                             confianza=NULL, ruta='humano', revisado_por=?, revisado_en=?
                       WHERE id=?""", (accion, quien, ahora(), campo_id))
        cx.execute("DELETE FROM normalizacion WHERE campo_id=?", (campo_id,))

    cx.execute("""UPDATE conflicto SET estado='resuelto', resuelto_por=?, resuelto_en=?
                   WHERE documento_id=? AND campo_nombre=? AND estado='abierto'""",
               (quien, ahora(), c["documento_id"], c["nombre"]))

    if registrar and accion != "revertir":
        d = cx.execute("SELECT sha256, orden FROM documento WHERE id=?",
                       (c["documento_id"],)).fetchone()
        cx.execute("""INSERT INTO revision_humana (sha256,orden,campo,accion,valor,quien,cuando)
                      VALUES (?,?,?,?,?,?,?)
                      ON CONFLICT(sha256,orden,campo) DO UPDATE SET accion=excluded.accion,
                          valor=excluded.valor, quien=excluded.quien, cuando=excluded.cuando""",
                   (d["sha256"], d["orden"], c["nombre"], accion,
                    str(valor) if valor is not None else None, quien, ahora()))
    cx.commit()
    return {"ok": True}
