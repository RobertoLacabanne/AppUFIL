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

    # ── Restricción 2: el original es inmutable. Se rehashea una muestra. ──
    muestra = cx.execute("""SELECT sha256, ruta_original FROM archivo
                             ORDER BY RANDOM() LIMIT 12""").fetchall()
    for f in muestra:
        p = Path(f["ruta_original"])
        if not p.exists():
            fallas.append(f"original desaparecido: {p}")
            continue
        if sha256_de(p) != f["sha256"]:
            fallas.append(f"¡EL ORIGINAL CAMBIÓ! {p} ya no coincide con su hash de ingesta")

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
