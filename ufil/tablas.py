"""
Las tablas del documento: filas, columnas y celdas, cada una con su lugar en la foja.

Por qué no alcanza con el texto
-------------------------------
Una planilla de obra, un remito o una orden de compra dicen lo que dicen POR RENGLÓN:
artículo, descripción, unidad, cantidad, precio, subtotal. Aplanar eso a texto corrido
pierde exactamente lo que hace falta para comparar lo pactado con lo entregado y con lo
facturado, que es la pregunta que trae a alguien a mirar estos papeles.

Cómo se detecta, y por qué así
------------------------------
Sin líneas dibujadas —y en un escaneo las líneas casi nunca sobreviven al OCR— una tabla
se reconoce por una cosa: **las palabras se alinean en columnas a lo largo de varios
renglones**. Un párrafo no hace eso. Dos renglones sueltos tampoco.

Así que se arman los renglones por solapamiento vertical, se buscan los arranques de
palabra que se repiten en la misma coordenada a lo largo de varios renglones, y recién
cuando hay al menos dos columnas estables y varios renglones que las respetan se dice
que ahí hay una tabla. Es conservador a propósito: proponer una tabla donde hay un
párrafo con números llena la pantalla de basura y hace que nadie confíe en las que sí
están.

Lo que NO hace
--------------
No interpreta la tabla. No decide cuál columna es el precio ni suma los subtotales: eso
depende del tipo documental y vive en los extractores. Acá se guarda la estructura y el
anclaje de cada celda, que es lo que después permite que un extractor trabaje sobre
renglones en vez de sobre una sopa de palabras.
"""
from __future__ import annotations

import sqlite3

from .db import ahora

# Cuánto se pueden correr dos arranques de palabra y seguir siendo la misma columna.
# En un escaneo con medio grado de inclinación, la misma columna se mueve unos puntos
# entre el primer renglón y el último.
TOLERANCIA_COLUMNA = 12.0

# Mínimos para decir que algo es una tabla. Por debajo de esto es un párrafo con
# números, y llamarlo tabla es peor que no decir nada.
MIN_FILAS = 3
MIN_COLUMNAS = 2

# Qué proporción de los renglones del bloque tiene que respetar las columnas.
PROPORCION_ALINEADA = 0.6

# El hueco mínimo entre una celda y la siguiente, en puntos.
#
# Es lo que separa una tabla de un párrafo, y hace falta decirlo aparte de la alineación
# porque la alineación sola no alcanza: en un texto justificado las palabras arrancan
# muchas veces en la misma coordenada renglón tras renglón, y eso se ve igual que una
# columna. Lo que NO se parece es el espacio: entre dos palabras de una frase hay un
# espacio de imprenta, y entre dos columnas de una planilla hay un blanco que se ve
# desde lejos.
MIN_HUECO = 18.0


def _renglones(palabras) -> list[list]:
    """
    Agrupa las palabras en renglones por solapamiento vertical.

    Por solapamiento y no por redondeo de la coordenada: en una hoja escaneada con medio
    grado de inclinación, dos palabras del mismo renglón caen a los lados del corte del
    bucket y quedan en renglones distintos. Es el mismo criterio que usa la extracción.
    """
    if not palabras:
        return []
    filas: list[list] = []
    for p in sorted(palabras, key=lambda q: ((q.y0 + q.y1) / 2, q.x0)):
        centro = (p.y0 + p.y1) / 2
        for r in filas:
            alto = sum(q.y1 - q.y0 for q in r) / len(r)
            centro_r = sum((q.y0 + q.y1) / 2 for q in r) / len(r)
            if abs(centro - centro_r) <= max(alto * 0.6, 3.0):
                r.append(p)
                break
        else:
            filas.append([p])
    for r in filas:
        r.sort(key=lambda q: q.x0)
    return sorted(filas, key=lambda r: min((q.y0 + q.y1) / 2 for q in r))


def _columnas_estables(renglones) -> list[float]:
    """
    Las coordenadas donde arrancan columnas, si es que hay columnas.

    Una columna es un arranque de palabra que se repite —dentro de la tolerancia— en
    varios renglones distintos. Se cuentan RENGLONES y no palabras: veinte palabras
    alineadas en un solo renglón no son una columna, son un renglón.
    """
    cuenta: dict[float, set] = {}
    for i, r in enumerate(renglones):
        for p in r:
            for x in cuenta:
                if abs(p.x0 - x) <= TOLERANCIA_COLUMNA:
                    cuenta[x].add(i)
                    break
            else:
                cuenta[p.x0] = {i}
    minimo = max(MIN_FILAS, int(len(renglones) * PROPORCION_ALINEADA))
    return sorted(x for x, filas in cuenta.items() if len(filas) >= minimo)


def _columna_de(x: float, columnas: list[float]) -> int:
    """A qué columna pertenece un arranque. La última que empieza antes que él."""
    idx = 0
    for i, cx0 in enumerate(columnas):
        if x >= cx0 - TOLERANCIA_COLUMNA:
            idx = i
    return idx


def detectar_en_pagina(palabras, ancho: float = 0, alto: float = 0) -> list[dict]:
    """
    Las tablas de una foja. Devuelve una lista; casi siempre vacía o de una.

    Cada tabla trae sus celdas con fila, columna, texto y recuadro. El recuadro es de la
    celda, no de la tabla: es lo que después permite señalar en la foja de dónde salió
    un número.
    """
    renglones = _renglones(palabras)
    if len(renglones) < MIN_FILAS:
        return []
    columnas = _columnas_estables(renglones)
    if len(columnas) < MIN_COLUMNAS:
        return []

    # Sólo entran los renglones que de verdad respetan las columnas. Un título arriba de
    # la planilla, o un total suelto abajo, no son filas de la tabla.
    celdas: list[dict] = []
    fila_nro = 0
    usados = []
    for r in renglones:
        ocupadas = {_columna_de(p.x0, columnas) for p in r}
        if len(ocupadas) < MIN_COLUMNAS:
            continue
        por_columna: dict[int, list] = {}
        for p in r:
            por_columna.setdefault(_columna_de(p.x0, columnas), []).append(p)
        # Entre celda y celda tiene que haber un blanco, no un espacio de imprenta.
        # Ver MIN_HUECO: es lo único que distingue una planilla de un texto justificado.
        bordes = sorted((min(q.x0 for q in ps), max(q.x1 for q in ps))
                        for ps in por_columna.values())
        if any(b[0] - a[1] < MIN_HUECO for a, b in zip(bordes, bordes[1:])):
            continue
        for col, ps in sorted(por_columna.items()):
            celdas.append({
                "fila": fila_nro, "columna": col,
                "texto": " ".join(q.texto for q in ps),
                "caja": (min(q.x0 for q in ps), min(q.y0 for q in ps),
                         max(q.x1 for q in ps), max(q.y1 for q in ps)),
                "confianza": round(sum(getattr(q, "conf", 1.0) or 0 for q in ps) / len(ps), 2),
            })
        usados.append(r)
        fila_nro += 1

    if fila_nro < MIN_FILAS:
        return []

    todas = [p for r in usados for p in r]
    tabla = {
        "filas": fila_nro, "columnas": len(columnas),
        "caja": (min(p.x0 for p in todas), min(p.y0 for p in todas),
                 max(p.x1 for p in todas), max(p.y1 for p in todas)),
        "celdas": celdas,
        # Qué tan segura es: cuántos renglones del bloque respetaron las columnas.
        "confianza": round(min(0.95, 0.45 + 0.5 * (fila_nro / max(len(renglones), 1))), 2),
    }
    # La primera fila es encabezado si no tiene ningún número donde las de abajo sí.
    _marcar_encabezado(tabla)
    return [tabla]


def _marcar_encabezado(tabla: dict) -> None:
    """
    La primera fila es encabezado cuando dice qué son las de abajo, no un dato más.

    La señal que se usa es simple y general: en una planilla, las columnas de cantidades
    traen números en las filas de datos y palabras en el encabezado. Si la primera fila
    no tiene dígitos donde las demás sí, es un encabezado.
    """
    primera = [c for c in tabla["celdas"] if c["fila"] == 0]
    resto = [c for c in tabla["celdas"] if c["fila"] > 0]
    if not primera or not resto:
        return
    con_numero = {c["columna"] for c in resto if any(ch.isdigit() for ch in c["texto"])}
    if not con_numero:
        return
    if not any(any(ch.isdigit() for ch in c["texto"])
               for c in primera if c["columna"] in con_numero):
        for c in primera:
            c["es_encabezado"] = True


def detectar_archivo(cx: sqlite3.Connection, sha: str, *, por_ruta=None) -> dict:
    """
    Busca tablas en cada foja del archivo y las guarda con sus celdas.

    Nunca pisa una tabla que armó o confirmó una persona (`origen='humano'`).
    """
    from .capa2_extraccion import lecturas_por_ruta
    por_ruta = por_ruta or lecturas_por_ruta(cx, sha)

    medidas = {r["nro"]: (r["ancho_pt"], r["alto_pt"], r["id"]) for r in cx.execute(
        "SELECT nro, ancho_pt, alto_pt, id FROM pagina WHERE sha256=?", (sha,))}
    # De cada foja, la ruta de lectura que más filas produjo: si alguna pudo ver la
    # tabla, la tabla está.
    mejor: dict[int, tuple] = {}
    for ruta, pgs in por_ruta.items():
        for nro, lid, palabras in pgs:
            if nro not in medidas:
                continue
            ancho, alto, _ = medidas[nro]
            for t in detectar_en_pagina(palabras, ancho or 0, alto or 0):
                if nro not in mejor or t["filas"] > mejor[nro][0]["filas"]:
                    mejor[nro] = (t, lid)

    guardadas = 0
    for nro, (t, lid) in sorted(mejor.items()):
        ya = cx.execute("""SELECT id, origen FROM tabla
                            WHERE sha256=? AND pagina_nro=? AND orden=1""",
                        (sha, nro)).fetchone()
        if ya and ya["origen"] == "humano":
            continue
        doc = cx.execute("""SELECT id FROM documento
                             WHERE sha256=? AND ? BETWEEN pagina_desde AND pagina_hasta
                             LIMIT 1""", (sha, nro)).fetchone()
        x0, y0, x1, y1 = t["caja"]
        if ya:
            tabla_id = ya["id"]
            cx.execute("DELETE FROM tabla_celda WHERE tabla_id=?", (tabla_id,))
            cx.execute("""UPDATE tabla SET filas=?, columnas=?, documento_id=?,
                                 x0=?, y0=?, x1=?, y1=?, confianza=?, origen='ocr'
                           WHERE id=?""",
                       (t["filas"], t["columnas"], doc["id"] if doc else None,
                        x0, y0, x1, y1, t["confianza"], tabla_id))
        else:
            tabla_id = cx.execute(
                """INSERT INTO tabla (sha256, pagina_nro, orden, documento_id, filas,
                                      columnas, x0, y0, x1, y1, origen, confianza, creado_en)
                   VALUES (?,?,1,?,?,?,?,?,?,?, 'ocr', ?, ?)""",
                (sha, nro, doc["id"] if doc else None, t["filas"], t["columnas"],
                 x0, y0, x1, y1, t["confianza"], ahora())).lastrowid
        for c in t["celdas"]:
            cx.execute("""INSERT INTO tabla_celda (tabla_id, fila, columna, es_encabezado,
                                                   texto, x0, y0, x1, y1, lectura_id,
                                                   confianza)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                       (tabla_id, c["fila"], c["columna"], 1 if c.get("es_encabezado") else 0,
                        c["texto"], *c["caja"], lid, c["confianza"]))
        guardadas += 1
    cx.commit()
    proponer_continuidad(cx, sha)
    return {"fojas": len(medidas), "tablas": guardadas}


def proponer_continuidad(cx: sqlite3.Connection, sha: str) -> int:
    """
    Propone unir una tabla con la de la foja siguiente cuando parecen la misma.

    La señal: misma cantidad de columnas y fojas consecutivas. Es una PROPUESTA —queda
    con `union_quien` en nulo— porque dos planillas distintas del mismo formulario
    también tienen las mismas columnas. Confirmarla es de una persona.
    """
    filas = cx.execute("""SELECT id, pagina_nro, columnas FROM tabla
                           WHERE sha256=? ORDER BY pagina_nro""", (sha,)).fetchall()
    n = 0
    for a, b in zip(filas, filas[1:]):
        if b["pagina_nro"] == a["pagina_nro"] + 1 and b["columnas"] == a["columnas"]:
            cx.execute("UPDATE tabla SET continua_de=? WHERE id=? AND continua_de IS NULL",
                       (a["id"], b["id"]))
            n += 1
    cx.commit()
    return n


class NoSePuede(ValueError):
    """Lo pedido no se puede hacer, y el motivo es para leer."""


def confirmar_continuidad(cx: sqlite3.Connection, tabla_id: int, sigue_de: int | None,
                          quien: str) -> dict:
    """
    Una persona confirma —o corta— que una tabla es la continuación de otra.

    `sigue_de=None` corta la unión: la tabla es propia y no continúa a ninguna.
    """
    if not (quien or "").strip():
        raise NoSePuede("hace falta indicar quién lo dice")
    t = cx.execute("SELECT id, sha256 FROM tabla WHERE id=?", (tabla_id,)).fetchone()
    if not t:
        raise NoSePuede("esa tabla no existe")
    if sigue_de is not None:
        if sigue_de == tabla_id:
            raise NoSePuede("una tabla no puede continuar de sí misma")
        if not cx.execute("SELECT 1 FROM tabla WHERE id=?", (sigue_de,)).fetchone():
            raise NoSePuede("la otra tabla no existe")
    cx.execute("""UPDATE tabla SET continua_de=?, union_quien=?, union_cuando=?
                   WHERE id=?""", (sigue_de, quien, ahora(), tabla_id))
    cx.commit()
    return {"ok": True, "tabla_id": tabla_id, "continua_de": sigue_de}


def de_archivo(cx: sqlite3.Connection, sha: str) -> list[dict]:
    return [_arma(cx, f) for f in cx.execute(
        """SELECT * FROM tabla WHERE sha256=? ORDER BY pagina_nro, orden""", (sha,))]


def ver(cx: sqlite3.Connection, tabla_id: int) -> dict:
    f = cx.execute("SELECT * FROM tabla WHERE id=?", (tabla_id,)).fetchone()
    if not f:
        raise NoSePuede("esa tabla no existe")
    return _arma(cx, f)


def _arma(cx, f) -> dict:
    celdas = [{"fila": c["fila"], "columna": c["columna"], "texto": c["texto"],
               "es_encabezado": bool(c["es_encabezado"]),
               "filas_ocupa": c["filas_ocupa"], "columnas_ocupa": c["columnas_ocupa"],
               "confianza": c["confianza"],
               "caja": None if c["x0"] is None else [c["x0"], c["y0"], c["x1"], c["y1"]]}
              for c in cx.execute("""SELECT * FROM tabla_celda WHERE tabla_id=?
                                      ORDER BY fila, columna""", (f["id"],))]
    return {"id": f["id"], "sha256": f["sha256"], "pagina_nro": f["pagina_nro"],
            "documento_id": f["documento_id"], "filas": f["filas"],
            "columnas": f["columnas"], "origen": f["origen"],
            "confianza": f["confianza"], "continua_de": f["continua_de"],
            "union_quien": f["union_quien"],
            "caja": None if f["x0"] is None else [f["x0"], f["y0"], f["x1"], f["y1"]],
            "celdas": celdas}


def renglones(cx: sqlite3.Connection, tabla_id: int, *, seguir: bool = True) -> list[dict]:
    """
    La tabla leída por renglón, siguiendo sus continuaciones.

    Es la forma en que sirve para trabajar: comparar lo pactado con lo entregado se hace
    renglón contra renglón, y una planilla cortada al pie de la hoja tiene que leerse
    completa. Cada valor viene con la foja y el recuadro de donde salió.
    """
    cadena = [tabla_id]
    if seguir:
        while True:
            sig = cx.execute("SELECT id FROM tabla WHERE continua_de=?",
                             (cadena[-1],)).fetchone()
            if not sig or sig["id"] in cadena:
                break
            cadena.append(sig["id"])

    salida, encabezados = [], None
    for i, tid in enumerate(cadena):
        t = ver(cx, tid)
        cabeza = {c["columna"]: c["texto"] for c in t["celdas"] if c["es_encabezado"]}
        if encabezados is None and cabeza:
            encabezados = cabeza
        for fila in range(t["filas"]):
            celdas = [c for c in t["celdas"] if c["fila"] == fila]
            if not celdas or all(c["es_encabezado"] for c in celdas):
                continue
            # El encabezado repetido arriba de la continuación no es un renglón de datos.
            if i > 0 and cabeza and all(
                    c["texto"] == cabeza.get(c["columna"]) for c in celdas):
                continue
            salida.append({
                "tabla_id": tid, "pagina_nro": t["pagina_nro"], "fila": fila,
                "valores": {(encabezados or {}).get(c["columna"], f"col{c['columna']}"):
                            c["texto"] for c in celdas},
                "celdas": celdas,
            })
    return salida
