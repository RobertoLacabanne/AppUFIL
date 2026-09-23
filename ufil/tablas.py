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
import math

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

# Qué proporción de lo que hay en las celdas tiene que parecer una palabra o un número de
# verdad para que el bloque sea una tabla y no una mancha alineada. Medido en un legajo
# real con la detección por bloque: de 859 «tablas», 357 tenían menos del 15 % de algo
# legible —fragmentos de dos letras sobre sellos y firmas—, 158 más del 40 %. Es la misma
# medida que separa una foja ilegible de una legible (clasificacion.medir).
UTILES_MINIMOS_TABLA = 0.15


def _legible(celdas) -> bool:
    """Si las celdas dicen algo. Las rayas de la planilla que el OCR lee como «|» no cuentan."""
    from .clasificacion import medir
    tokens = [w.strip("|¦[]{}()¡!¿?:;,'\"") for c in celdas for w in (c["texto"] or "").split()]
    m = medir(t for t in tokens if t)
    return m.palabras > 0 and m.proporcion_util >= UTILES_MINIMOS_TABLA


def _estructurada(celdas) -> bool:
    """Exige dos columnas de contenido que se repitan en las mismas filas.

    Los índices asignados por el detector no prueban alineación: se comprueban
    las cajas originales. Rayas y fragmentos OCR no sostienen una columna,
    aunque estén al lado de un párrafo legible. Los números cortos sí cuentan.
    Dos filas permiten validar listas ya guardadas; la detección sigue exigiendo
    una semilla de MIN_FILAS. Sin coordenadas no se descarta evidencia antigua.
    """
    if not celdas:
        return False
    filas = {}
    for c in celdas:
        caja = c.get('caja') if 'caja' in c else (c.get('x0'), c.get('y0'), c.get('x1'), c.get('y1'))
        if not caja or any(v is None for v in caja):
            return True
        filas.setdefault(c['fila'], []).append((c, caja))
    minimo = max(2, math.ceil(len(filas) * PROPORCION_ALINEADA))
    pares = []
    for fila, cs in filas.items():
        utiles = sorted((caja for c, caja in cs
                         if any(ch.isdigit() for ch in c['texto']) or _legible([c])),
                        key=lambda caja: caja[0])
        for i, a in enumerate(utiles):
            for b in utiles[i + 1:]:
                if b[0] - a[2] >= MIN_HUECO:
                    pares.append((fila, a[0], b[0]))
    for _, x, y in pares:
        coinciden = {f for f, a, b in pares
                     if abs(a - x) <= TOLERANCIA_COLUMNA
                     and abs(b - y) <= TOLERANCIA_COLUMNA}
        if len(coinciden) >= minimo:
            return True
    return False


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


def _inicios(r):
    """Sólo los arranques separados por blanco; una palabra interna no es columna."""
    return [p for i, p in enumerate(r)
            if i == 0 or p.x0 - r[i - 1].x1 >= MIN_HUECO]


def _celdas_fila(r, columnas):
    por_columna = {}
    for p in r:
        por_columna.setdefault(_columna_de(p.x0, columnas), []).append(p)
    if len(por_columna) < max(MIN_COLUMNAS, len(columnas) * PROPORCION_ALINEADA):
        return None
    bordes = [(min(p.x0 for p in ps), max(p.x1 for p in ps))
              for _, ps in sorted(por_columna.items())]
    if any(b[0] - a[1] < MIN_HUECO for a, b in zip(bordes, bordes[1:])):
        return None
    # No basta caer dentro de una columna: su arranque debe estar alineado.
    if any(abs(min(p.x0 for p in ps) - columnas[col]) > TOLERANCIA_COLUMNA
           for col, ps in por_columna.items()):
        return None
    return por_columna


def detectar_en_pagina(palabras, ancho: float = 0, alto: float = 0) -> list[dict]:
    """Busca semillas de tres filas consecutivas y extiende cada bloque alineado.

    El denominador es el bloque, no la foja. Encabezados, prosa y totales cortan
    el bloque; dos tablas distintas no se funden por compartir un margen.
    """
    filas = _renglones(palabras)
    candidatos = {}
    for i in range(len(filas) - MIN_FILAS + 1):
        columnas = _columnas_estables([_inicios(r) for r in filas[i:i + MIN_FILAS]])
        if len(columnas) < MIN_COLUMNAS:
            continue
        def cerca(a, b):
            altura = max(p.y1 - p.y0 for p in filas[a] + filas[b])
            return min(p.y0 for p in filas[b]) - max(p.y1 for p in filas[a]) <= altura * 3
        def valida(j):
            return _celdas_fila(filas[j], columnas) is not None
        if not all(valida(j) for j in range(i, i + MIN_FILAS)):
            continue
        if not all(cerca(j, j + 1) for j in range(i, i + MIN_FILAS - 1)):
            continue
        inicio, fin = i, i + MIN_FILAS
        while inicio > 0 and cerca(inicio - 1, inicio) and valida(inicio - 1):
            inicio -= 1
        while fin < len(filas) and cerca(fin - 1, fin) and valida(fin):
            fin += 1
        candidatos[(inicio, fin, tuple(columnas))] = (fin - inicio) * len(columnas)
    usados, tablas = set(), []
    for (inicio, fin, columnas), _ in sorted(candidatos.items(), key=lambda x: -x[1]):
        if usados.intersection(range(inicio, fin)):
            continue
        celdas = []
        for n, r in enumerate(filas[inicio:fin]):
            for col, ps in sorted(_celdas_fila(r, columnas).items()):
                celdas.append({
                    "fila": n, "columna": col, "texto": " ".join(p.texto for p in ps),
                    "caja": (min(p.x0 for p in ps), min(p.y0 for p in ps),
                             max(p.x1 for p in ps), max(p.y1 for p in ps)),
                    "confianza": round(sum(getattr(p, "conf", 1.0) or 0 for p in ps) / len(ps), 2),
                })
        todas = [p for r in filas[inicio:fin] for p in r]
        t = {"filas": fin - inicio, "columnas": len(columnas), "celdas": celdas,
             "caja": (min(p.x0 for p in todas), min(p.y0 for p in todas),
                      max(p.x1 for p in todas), max(p.y1 for p in todas)),
             "confianza": 0.95}
        if not _legible(celdas) or not _estructurada(celdas):
            continue
        usados.update(range(inicio, fin))
        _marcar_encabezado(t)
        tablas.append(t)
    return sorted(tablas, key=lambda t: t["caja"][1])


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
    mejor = {}
    for ruta, pgs in por_ruta.items():
        for nro, lid, palabras in pgs:
            if nro not in medidas:
                continue
            ancho, alto, _ = medidas[nro]
            ts = detectar_en_pagina(palabras, ancho or 0, alto or 0)
            calidad = sum(t["filas"] * t["columnas"] for t in ts)
            if nro not in mejor or calidad > mejor[nro][2]:
                mejor[nro] = (ts, lid, calidad)

    guardadas = 0
    elegidas = [(nro, orden, t, lid) for nro, (ts, lid, _) in sorted(mejor.items())
                for orden, t in enumerate(ts, 1)]
    vigentes = {(nro, orden) for nro, orden, _, _ in elegidas}
    for vieja in cx.execute("SELECT * FROM tabla WHERE sha256=? AND origen!='humano'",
                            (sha,)).fetchall():
        if (vieja["pagina_nro"], vieja["orden"]) not in vigentes:
            cx.execute("UPDATE tabla SET continua_de=NULL WHERE continua_de=?", (vieja["id"],))
            cx.execute("DELETE FROM tabla WHERE id=?", (vieja["id"],))
    for nro, orden, t, lid in elegidas:
        ya = cx.execute("SELECT id, origen FROM tabla WHERE sha256=? AND pagina_nro=? AND orden=?",
                        (sha, nro, orden)).fetchone()
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
                   VALUES (?,?,?,?,?,?,?,?,?,?, 'ocr', ?, ?)""",
                (sha, nro, orden, doc["id"] if doc else None, t["filas"], t["columnas"],
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
    candidatas = [_arma(cx, f) for f in cx.execute(
        """SELECT * FROM tabla WHERE sha256=? ORDER BY pagina_nro, orden""", (sha,))]
    return [t for t in candidatas if t['origen'] == 'humano' or _estructurada(t['celdas'])]


def ver(cx: sqlite3.Connection, tabla_id: int) -> dict:
    f = cx.execute("SELECT * FROM tabla WHERE id=?", (tabla_id,)).fetchone()
    if not f:
        raise NoSePuede("esa tabla no existe")
    return _arma(cx, f)


def _arma(cx, f, *, celdas=None) -> dict:
    if celdas is None:
        celdas = cx.execute('SELECT * FROM tabla_celda WHERE tabla_id=? ORDER BY fila,columna', (f['id'],))
    celdas = [{"fila": c["fila"], "columna": c["columna"], "texto": c["texto"],
               "es_encabezado": bool(c["es_encabezado"]),
               "filas_ocupa": c["filas_ocupa"], "columnas_ocupa": c["columnas_ocupa"],
               "confianza": c["confianza"],
               "caja": None if c["x0"] is None else [c["x0"], c["y0"], c["x1"], c["y1"]]}
              for c in celdas]
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
