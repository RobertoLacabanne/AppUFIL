"""
Capa 5 — Interpretación.

Este es el OTRO carril. Acá el sistema tiene permitido hipotetizar, señalar patrones
y sugerir dónde mirar. Puede equivocarse: para eso cada afirmación arrastra las
fuentes que la sostienen, y la interfaz la muestra con otra tipografía y otro fondo.

Todo lo de este módulo, hoy, sale de REGLAS determinísticas sobre la tabla de datos
(`origen = "regla:<nombre>"`). No hay modelo de lenguaje todavía, y eso es deliberado:
sin saber qué GPU hay, un LLM local sería una promesa. Las reglas de acá ya encuentran
la mayoría de lo que el pliego pide en la sección 7, y cuando entre el modelo va a
sumar resumen y lenguaje natural sobre esta misma estructura, escribiendo en la misma
tabla y con la misma obligación de citar.

Invariante: `insertar` exige fuentes. Sin fuentes no se guarda. `ufil verificar` lo
comprueba después.
"""
from __future__ import annotations

import sqlite3
from statistics import median

from .db import ahora


def insertar(cx, *, alcance: str, alcance_id, clase: str, texto: str, origen: str,
             fuentes: list[dict]) -> int:
    if not fuentes:
        raise ValueError("una interpretación sin fuentes no se guarda (sección 5 del pliego)")
    iid = cx.execute(
        """INSERT INTO interpretacion (alcance, alcance_id, clase, texto, origen, creado_en)
           VALUES (?,?,?,?,?,?)""",
        (alcance, str(alcance_id), clase, texto, origen, ahora())).lastrowid
    for f in fuentes:
        cx.execute(
            """INSERT INTO interpretacion_fuente
               (interpretacion_id, documento_id, campo_id, pagina_nro, nota)
               VALUES (?,?,?,?,?)""",
            (iid, f.get("documento_id"), f.get("campo_id"), f.get("pagina_nro"), f.get("nota")))
    return iid


def _plata(centavos) -> str:
    if centavos is None:
        return "sin monto legible"
    s = f"{centavos/100:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return f"${s}"


def regenerar(cx: sqlite3.Connection) -> dict:
    """Vuelve a generar todas las interpretaciones de regla. Idempotente."""
    cx.execute("DELETE FROM interpretacion_fuente WHERE interpretacion_id IN "
               "(SELECT id FROM interpretacion WHERE origen LIKE 'regla:%')")
    cx.execute("DELETE FROM interpretacion WHERE origen LIKE 'regla:%'")
    cuenta = {"superposicion": 0, "monto_fuera_de_rango": 0, "renovacion_encadenada": 0,
              "altas_agrupadas": 0, "identidad_sin_documento": 0}

    # ── 1. Superposición: el hallazgo se enuncia en palabras, con sus dos folios ──
    for s in cx.execute("""
        SELECT a.documento_id AS da, b.documento_id AS db, a.archivo AS aa, b.archivo AS ab,
               COALESCE(a.nombre_literal,'(sin nombre)') AS quien, a.camara AS ca, b.camara AS cb,
               a.inicio AS ia, a.fin AS fa, b.inicio AS ib, b.fin AS fb,
               CAST(julianday(MIN(a.fin,b.fin)) - julianday(MAX(a.inicio,b.inicio)) + 1 AS INTEGER) AS dias
          FROM v_contrato a JOIN v_contrato b
            ON a.persona_id=b.persona_id AND a.documento_id<b.documento_id
         WHERE a.inicio IS NOT NULL AND a.fin IS NOT NULL
           AND b.inicio IS NOT NULL AND b.fin IS NOT NULL
           AND a.inicio<=b.fin AND b.inicio<=a.fin"""):
        tipo = "dentro de la misma cámara" if s["ca"] == s["cb"] else "entre las dos cámaras"
        insertar(cx, alcance="documento", alcance_id=s["da"], clase="patron",
                 origen="regla:superposicion",
                 texto=(f"{s['quien']} aparece con dos contratos que se pisan {tipo} durante "
                        f"{s['dias']} días: {s['ia']} a {s['fa']} en la cámara {s['ca']}, y "
                        f"{s['ib']} a {s['fb']} en la cámara {s['cb']}. Conviene mirar si las "
                        f"dependencias son compatibles."),
                 fuentes=[{"documento_id": s["da"], "nota": s["aa"]},
                          {"documento_id": s["db"], "nota": s["ab"]}])
        cuenta["superposicion"] += 1

    # ── 2. Monto fuera de rango PARA EL MISMO CARGO (no contra una tabla inventada) ──
    por_cargo: dict[str, list[tuple]] = {}
    for r in cx.execute("""SELECT documento_id, archivo, cargo, monto_centavos,
                                  COALESCE(nombre_literal,'(sin nombre)') AS quien
                             FROM v_contrato
                            WHERE cargo IS NOT NULL AND monto_centavos IS NOT NULL"""):
        por_cargo.setdefault(r["cargo"], []).append(
            (r["documento_id"], r["archivo"], r["monto_centavos"], r["quien"]))
    for cargo, filas in por_cargo.items():
        if len(filas) < 5:
            continue                       # con menos de cinco, "fuera de rango" no dice nada
        montos = [f[2] for f in filas]
        m = median(montos)
        for doc_id, archivo, monto, quien in filas:
            if m and monto > m * 1.6:
                insertar(cx, alcance="documento", alcance_id=doc_id, clase="anomalia",
                         origen="regla:monto_fuera_de_rango",
                         texto=(f"El monto de este contrato ({_plata(monto)}) está muy por "
                                f"encima de lo habitual para el cargo «{cargo}», cuya mediana "
                                f"entre los {len(filas)} contratos legibles del mismo cargo es "
                                f"{_plata(m)}. Puede ser correcto: verificar el monto en el "
                                f"folio antes de sacar conclusiones."),
                         fuentes=[{"documento_id": doc_id, "nota": archivo}])
                cuenta["monto_fuera_de_rango"] += 1

    # ── 3. Renovaciones encadenadas con idéntico cargo ──
    for r in cx.execute("""
        SELECT a.documento_id AS da, b.documento_id AS db, a.archivo AS aa, b.archivo AS ab,
               COALESCE(a.nombre_literal,'(sin nombre)') AS quien, a.cargo AS cargo,
               a.fin AS fa, b.inicio AS ib
          FROM v_contrato a JOIN v_contrato b
            ON a.persona_id=b.persona_id AND a.documento_id<>b.documento_id
         WHERE a.fin IS NOT NULL AND b.inicio IS NOT NULL AND a.cargo IS NOT NULL
           AND a.cargo = b.cargo
           AND julianday(b.inicio) - julianday(a.fin) BETWEEN 0 AND 31"""):
        insertar(cx, alcance="documento", alcance_id=r["da"], clase="patron",
                 origen="regla:renovacion_encadenada",
                 texto=(f"{r['quien']} encadena contratos con idéntico cargo «{r['cargo']}»: "
                        f"uno termina el {r['fa']} y el siguiente arranca el {r['ib']}. Una "
                        f"sucesión de contratos cortos con el mismo objeto puede estar "
                        f"cubriendo una relación permanente."),
                 fuentes=[{"documento_id": r["da"], "nota": r["aa"]},
                          {"documento_id": r["db"], "nota": r["ab"]}])
        cuenta["renovacion_encadenada"] += 1

    # ── 4. Altas agrupadas en la misma fecha ──
    for r in cx.execute("""SELECT inicio, COUNT(*) AS n, GROUP_CONCAT(documento_id) AS docs
                             FROM v_contrato WHERE inicio IS NOT NULL
                            GROUP BY inicio HAVING n >= 4"""):
        docs = [int(x) for x in r["docs"].split(",")]
        insertar(cx, alcance="lote", alcance_id=r["inicio"], clase="patron",
                 origen="regla:altas_agrupadas",
                 texto=(f"{r['n']} contratos empiezan exactamente el mismo día ({r['inicio']}). "
                        f"Un alta grupal puede ser un acto administrativo único; vale la pena "
                        f"buscar la resolución que los agrupa."),
                 fuentes=[{"documento_id": d} for d in docs])
        cuenta["altas_agrupadas"] += 1

    # ── 5. Personas sin documento legible: el límite de la resolución de identidad ──
    n = cx.execute("""SELECT COUNT(*) FROM v_contrato
                       WHERE documento_norm IS NULL OR documento_norm=''""").fetchone()[0]
    if n:
        docs = [f["documento_id"] for f in cx.execute(
            """SELECT documento_id FROM v_contrato
                WHERE documento_norm IS NULL OR documento_norm='' LIMIT 40""")]
        insertar(cx, alcance="lote", alcance_id="identidad", clase="relevancia",
                 origen="regla:identidad_sin_documento",
                 texto=(f"Hay {n} contratos sin documento legible. Esos contratos NO se pueden "
                        f"agrupar con seguridad bajo una persona, así que los acumulados y las "
                        f"superposiciones que los involucren están incompletos. Es el techo "
                        f"actual del análisis y se levanta revisando esos campos a mano."),
                 fuentes=[{"documento_id": d} for d in docs])
        cuenta["identidad_sin_documento"] = n

    cx.commit()
    return cuenta
