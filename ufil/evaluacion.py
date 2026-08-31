"""
Medición de calidad (§12 del pliego).

Compara la salida del sistema contra una transcripción hecha a mano y reporta, por
campo: aciertos, errores y omisiones. Y aparte —porque es la única categoría
peligrosa— los ERRORES SILENCIOSOS.

Definición operativa, que es lo que importa:

  acierto            el valor coincide con la referencia
  error marcado      el valor NO coincide, pero el sistema lo dejó marcado para
                     revisión (baja confianza, conflicto o lectura única en campo
                     crítico). Cuesta tiempo, no daña.
  ERROR SILENCIOSO   el valor NO coincide y el sistema lo dio por bueno. Entra en
                     todos los cruces y no lo ve nadie. Es el único que puede hundir
                     la confianza en el sistema entero.
  omisión            el sistema no devolvió valor y la referencia tenía uno.
  nulo correcto      ni el sistema ni la referencia tenían valor.

Y una métrica más, que la exactitud sola no captura: RESCATABLE. De los campos que
quedaron en la cola por conflicto entre rutas, en cuántos alguna de las lecturas
ofrecidas era la correcta. Mide si la cola se resuelve ELIGIENDO o hay que TIPEAR, que
para el que revisa es la diferencia entre una tecla y quince.
"""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from . import config
from .capa2_campos import normalizar_cotejo
from .castellano import miles, plural

# Umbrales propuestos en docs/00-fase-0.md §6. Asimétricos a propósito.
UMBRAL_EXACTITUD = {"nombre": 0.95, "documento": 0.98,
                    "fecha_inicio": 0.98, "fecha_fin": 0.98, "monto": 0.98}
UMBRAL_SILENCIOSOS = {"nombre": 1, "documento": 0, "fecha_inicio": 0, "fecha_fin": 0, "monto": 0}

COLUMNAS_REF = {"nombre": "nombre", "documento": "documento",
                "fecha_inicio": "fecha_inicio", "fecha_fin": "fecha_fin",
                "monto": "monto_centavos"}


def _solo_valor(campo: str, literal: str | None) -> str | None:
    """Normaliza una variante de conflicto igual que el pipeline, para poder compararla."""
    if literal is None:
        return None
    from .capa2_campos import PARSERS
    tipo = {"monto": "monto", "documento": "documento", "nombre": "nombre",
            "fecha_inicio": "fecha", "fecha_fin": "fecha"}.get(campo, "texto")
    _, norm, _ = PARSERS[tipo](literal)
    if campo == "documento" and norm:
        norm = norm.split(":", 1)[1]
    return norm


def _canon(campo: str, valor: str | None) -> str:
    if valor is None or str(valor).strip() == "":
        return ""
    v = str(valor).strip()
    if campo == "nombre":
        return normalizar_cotejo(v)
    if campo == "documento":
        return "".join(c for c in v if c.isdigit())
    if campo == "monto":
        return str(int(v))
    return v


def evaluar(cx: sqlite3.Connection, referencia_csv: Path) -> dict:
    with open(referencia_csv, encoding="utf-8") as f:
        ref = {r["archivo"]: r for r in csv.DictReader(f)}

    campos = list(config.CAMPOS_CRITICOS)
    tabla = {c: {"acierto": 0, "error_marcado": 0, "error_silencioso": 0,
                 "omision": 0, "nulo_correcto": 0, "sin_referencia": 0,
                 "en_conflicto": 0, "rescatable": 0} for c in campos}

    # Variantes ofrecidas en cada conflicto abierto, por (documento, campo).
    variantes: dict[tuple[int, str], list[str]] = {}
    for v in cx.execute("""SELECT k.documento_id, k.campo_nombre, v.valor
                             FROM conflicto k JOIN conflicto_variante v ON v.conflicto_id = k.id
                            WHERE k.estado = 'abierto'"""):
        variantes.setdefault((v["documento_id"], v["campo_nombre"]), []).append(v["valor"])
    detalle: list[dict] = []

    # La transcripción de referencia tiene una fila por ARCHIVO. Si un archivo produjo
    # varios contratos —un PDF con una pila adentro—, no hay forma de saber cuál fila le
    # corresponde a cuál contrato, así que esos quedan fuera de la medición y se
    # informan aparte. Medir contra la referencia equivocada sería peor que no medir.
    multiples = {r["nombre"] for r in cx.execute("""
        SELECT a.nombre FROM documento d JOIN archivo a ON a.sha256 = d.sha256
         GROUP BY d.sha256 HAVING COUNT(*) > 1""")}

    filas = cx.execute("""
        SELECT a.nombre AS archivo, c.nombre AS campo, c.valor_literal, c.nulo_motivo,
               c.estado, c.confianza, n.valor_norm, d.id AS documento_id
          FROM campo c
          JOIN documento d ON d.id = c.documento_id
          JOIN archivo  a ON a.sha256 = d.sha256
          LEFT JOIN normalizacion n ON n.campo_id = c.id
         WHERE c.nombre IN (%s)""" % ",".join("?" * len(campos)), campos).fetchall()

    for f in filas:
        campo, archivo = f["campo"], f["archivo"]
        r = None if archivo in multiples else ref.get(archivo)
        if not r:
            tabla[campo]["sin_referencia"] += 1
            continue

        esperado = _canon(campo, r[COLUMNAS_REF[campo]])
        norm = f["valor_norm"]
        if campo == "documento" and norm:
            norm = norm.split(":", 1)[1]
        obtenido = _canon(campo, norm) if norm else ""
        marcado = f["estado"] in ("a_revisar",) or f["nulo_motivo"] is not None

        if not obtenido:
            clase = "omision" if esperado else "nulo_correcto"
        elif obtenido == esperado:
            clase = "acierto"
        else:
            clase = "error_marcado" if marcado else "error_silencioso"

        tabla[campo][clase] += 1

        if f["nulo_motivo"] == "conflicto":
            tabla[campo]["en_conflicto"] += 1
            ofrecidas = variantes.get((f["documento_id"], campo), [])
            if esperado and any(_canon(campo, _solo_valor(campo, v)) == esperado
                                for v in ofrecidas):
                tabla[campo]["rescatable"] += 1

        if clase in ("error_silencioso", "error_marcado", "omision"):
            detalle.append({
                "archivo": archivo, "documento_id": f["documento_id"], "campo": campo,
                "clase": clase, "esperado": r[COLUMNAS_REF[campo]],
                "obtenido": f["valor_literal"], "motivo": f["nulo_motivo"],
                "confianza": f["confianza"], "estado": f["estado"],
            })

    resumen = {}
    aprueba = True
    for campo, t in tabla.items():
        con_ref = t["acierto"] + t["error_marcado"] + t["error_silencioso"] + t["omision"]
        exactitud = t["acierto"] / con_ref if con_ref else 0.0
        ok_exac = exactitud >= UMBRAL_EXACTITUD[campo]
        ok_sil = t["error_silencioso"] <= UMBRAL_SILENCIOSOS[campo]
        aprueba &= ok_exac and ok_sil
        resumen[campo] = {
            **t, "con_referencia": con_ref, "exactitud": round(exactitud, 4),
            "rescate": (round(t["rescatable"] / t["en_conflicto"], 3)
                        if t["en_conflicto"] else None),
            "umbral_exactitud": UMBRAL_EXACTITUD[campo],
            "umbral_silenciosos": UMBRAL_SILENCIOSOS[campo],
            "cumple_exactitud": ok_exac, "cumple_silenciosos": ok_sil,
        }
    return {"por_campo": resumen, "detalle": detalle, "aprueba": aprueba,
            "documentos": len(ref), "archivos_con_varios_contratos": sorted(multiples)}


def informe_texto(res: dict) -> str:
    L = []
    L.append("MEDICIÓN DE CALIDAD — campos críticos")
    L.append("=" * 92)
    L.append(f"{'campo':<14}{'acier':>6}{'err.mar':>8}{'ERR.SIL':>9}{'omis':>6}"
             f"{'nulo ok':>9}{'exactitud':>11}{'umbral':>9}   veredicto")
    L.append("-" * 92)
    for campo, t in res["por_campo"].items():
        v = "cumple" if (t["cumple_exactitud"] and t["cumple_silenciosos"]) else "NO CUMPLE"
        L.append(f"{campo:<14}{t['acierto']:>6}{t['error_marcado']:>8}"
                 f"{t['error_silencioso']:>9}{t['omision']:>6}{t['nulo_correcto']:>9}"
                 f"{t['exactitud']*100:>10.1f}%{t['umbral_exactitud']*100:>8.0f}%   {v}")
    L.append("-" * 92)
    sil = sum(t["error_silencioso"] for t in res["por_campo"].values())
    L.append(f"errores silenciosos en total: {sil}")
    conf = sum(t["en_conflicto"] for t in res["por_campo"].values())
    resc = sum(t["rescatable"] for t in res["por_campo"].values())
    if conf:
        L.append(f"campos en conflicto: {conf} · de esos, con la lectura correcta entre las "
                 f"ofrecidas: {resc} ({100*resc/conf:.0f}%) — se resuelven eligiendo, sin tipear")
    if res.get("archivos_con_varios_contratos"):
        n = len(res["archivos_con_varios_contratos"])
        L.append(f"fuera de la medición: {plural(n, 'archivo trae', 'archivos traen')} "
                 f"varios contratos adentro y la "
                 f"referencia tiene una sola fila por archivo")
    L.append("")
    L.append("VEREDICTO: " + ("cumple los umbrales propuestos"
                              if res["aprueba"] else "NO alcanza los umbrales propuestos"))
    return "\n".join(L)
