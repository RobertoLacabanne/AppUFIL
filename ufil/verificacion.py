"""
Verificación de invariantes. Es el chequeo de que las restricciones del pliego se
siguen cumpliendo después de cada corrida, no sólo el día que se escribió el código.

`ufil verificar` devuelve código de salida 1 si algo falla, así que se puede colgar
de una tarea programada y enterarse solo.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from . import config
from .capa0_ingesta import sha256_de
from .db import ahora


# Cuántos originales se rehashean por corrida. Se empieza siempre por los que hace más
# tiempo que no se miran, así la cobertura avanza sola hasta dar la vuelta completa.
POR_CORRIDA = 250


def verificar_integridad(cx: sqlite3.Connection, *, cuantos: int = POR_CORRIDA,
                         completo: bool = False) -> dict:
    """
    Rehashea originales y compara contra el hash de ingesta.

    NO es un muestreo al azar. Se ordenan por antigüedad de verificación —los que nunca
    se miraron primero— y se toma un lote. Corriéndolo seguido, el acervo entero queda
    cubierto y se sabe con números cuánto y desde cuándo.
    """
    total = cx.execute("SELECT COUNT(*) FROM archivo").fetchone()[0]
    sql = """SELECT a.sha256, a.ruta_original, a.nombre, i.verificado_en
               FROM archivo a LEFT JOIN integridad i ON i.sha256 = a.sha256
              ORDER BY (i.verificado_en IS NOT NULL), i.verificado_en, a.nombre"""
    filas = cx.execute(sql).fetchall()
    if not completo:
        filas = filas[:cuantos]

    fallas, ok = [], 0
    for f in filas:
        p = Path(f["ruta_original"])
        if not p.exists():
            detalle = f"original desaparecido: {f['nombre']} ({p})"
            fallas.append(detalle)
            estado = 0
        elif sha256_de(p) != f["sha256"]:
            detalle = (f"¡EL ORIGINAL CAMBIÓ! {f['nombre']} ya no coincide con su hash "
                       f"de ingesta ({p})")
            fallas.append(detalle)
            estado = 0
        else:
            detalle, estado, ok = None, 1, ok + 1
        cx.execute("""INSERT INTO integridad (sha256, verificado_en, ok, detalle)
                      VALUES (?,?,?,?)
                      ON CONFLICT(sha256) DO UPDATE SET verificado_en=excluded.verificado_en,
                          ok=excluded.ok, detalle=excluded.detalle""",
                   (f["sha256"], ahora(), estado, detalle))
    cx.commit()

    cubiertos = cx.execute("SELECT COUNT(*) FROM integridad").fetchone()[0]
    mas_viejo = cx.execute("SELECT MIN(verificado_en) FROM integridad").fetchone()[0]
    return {"revisados": len(filas), "ok": ok, "fallas": fallas, "total": total,
            "cubiertos": cubiertos, "mas_viejo": mas_viejo,
            "sin_verificar_nunca": total - cubiertos}


def correr(cx: sqlite3.Connection) -> list[str]:
    fallas: list[str] = []

    # ── Restricción 3: o valor, o motivo. Nunca las dos, nunca ninguna ──
    n = cx.execute("""SELECT COUNT(*) FROM campo
                       WHERE (valor_literal IS NULL) = (nulo_motivo IS NULL)""").fetchone()[0]
    if n:
        fallas.append(f"{n} campos violan «o valor, o motivo» (restricción 3)")

    # ── Restricción 4: todo valor tiene anclaje ──
    n = cx.execute("""SELECT COUNT(*) FROM campo
                       WHERE valor_literal IS NOT NULL
                         AND (pagina_nro IS NULL OR x0 IS NULL OR y0 IS NULL)""").fetchone()[0]
    if n:
        fallas.append(f"{n} campos con valor pero sin anclaje a página y recuadro (restricción 4)")

    # ── Sección 5: ninguna interpretación sin fuente que la sostenga ──
    n = cx.execute("""SELECT COUNT(*) FROM interpretacion i
                       WHERE NOT EXISTS (SELECT 1 FROM interpretacion_fuente f
                                          WHERE f.interpretacion_id = i.id)""").fetchone()[0]
    if n:
        fallas.append(f"{n} interpretaciones sin ninguna fuente documental (sección 5)")

    # ── El sistema nunca resuelve un conflicto solo ──
    n = cx.execute("""SELECT COUNT(*) FROM conflicto k
                       JOIN campo c ON c.documento_id=k.documento_id AND c.nombre=k.campo_nombre
                      WHERE k.estado='abierto' AND c.valor_literal IS NOT NULL""").fetchone()[0]
    if n:
        fallas.append(f"{n} campos tienen valor pese a tener un conflicto abierto")

    # ── Las fusiones de identidad no se aplican solas ──
    n = cx.execute("""SELECT COUNT(*) FROM fusion_propuesta
                       WHERE estado='aceptada' AND (decidido_por IS NULL OR decidido_por='')""").fetchone()[0]
    if n:
        fallas.append(f"{n} fusiones aplicadas sin constancia de quién las confirmó")

    # ── Restricción 2: el original es inmutable ──
    fallas.extend(verificar_integridad(cx)["fallas"])

    # ── Los derivados nunca viven adentro del corpus ──
    for f in cx.execute("SELECT DISTINCT ruta_original FROM archivo LIMIT 50"):
        origen = Path(f["ruta_original"]).parent.resolve()
        if config.DERIVADOS.resolve() == origen or config.DERIVADOS.resolve() in origen.parents:
            fallas.append(f"los derivados están adentro del corpus: {origen}")
            break

    # ── Restricción 1: si hay VLM configurado, tiene que ser la misma máquina ──
    url = os.environ.get("UFIL_VLM_URL", "")
    if url and not any(h in url for h in ("127.0.0.1", "localhost", "::1", "0.0.0.0")):
        fallas.append(f"UFIL_VLM_URL apunta fuera de la máquina: {url} (restricción 1)")

    return fallas
