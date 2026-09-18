"""
La foliatura que tiene el papel, que no es el número de página del PDF.

Por qué importa la diferencia
-----------------------------
En un expediente conviven cuatro numeraciones y no son la misma:

  1. la página del PDF — la posición en el archivo;
  2. la posición global — en qué lugar del conjunto documental cae;
  3. **la foliatura visible** — el número escrito o sellado en el papel;
  4. la numeración interna de una pieza — «hoja 2 de 5».

Un escrito que dice «a fojas 47» se refiere a la tercera. Si el sistema contesta con la
primera, manda a alguien a mirar otro papel, y eso en un legajo penal no es un detalle
de presentación.

La regla que ordena todo este módulo
------------------------------------
**No se inventa una foliatura.** Que no se haya detectado un número NO significa que la
foja no esté foliada: significa que no se detectó. Decir «esta foja no tiene foliatura»
es una afirmación sobre el papel, y la hace una persona.

Por eso la detección es deliberadamente desconfiada: prefiere no proponer nada antes que
proponer el número equivocado. Un número suelto en un margen puede ser una foliatura, y
también puede ser el año de un formulario, el número de un artículo o la numeración de
un renglón. Cuando no está razonablemente aislado, no se toma.
"""
from __future__ import annotations

import re
import sqlite3

from .db import ahora

# Cuánto de la hoja, arriba y abajo, se considera margen. La foliatura vive ahí: en el
# medio de la hoja hay texto del documento, y cualquier número que aparezca entre
# renglones es del documento y no del expediente.
MARGEN = 0.13

# Qué tan sola tiene que estar la palabra para que se la tome por foliatura. Un número
# pegado a otras palabras es parte de una frase. Medido en puntos PDF.
AISLAMIENTO = 45.0

# La forma de una foliatura. Admite el rótulo delante y los sufijos que el papel trae.
_FOLIO = re.compile(
    r"""^(?:f{1,2}s?\.?|folios?|fojas?)?\s*      # f. · fs. · folio · foja (opcional)
         (\d{1,4})                                # el número
         \s*(bis|ter|quater)?                     # 12 bis
         \s*\.?\s*(vta\.?|vto\.?|v\.?|r\.?)?$     # vuelta / reverso
     """,
    re.IGNORECASE | re.VERBOSE)

_SUFIJOS = {"bis": "bis", "ter": "ter", "quater": "quater"}
_REVERSO = {"vta", "vta.", "vto", "vto.", "v", "v."}


def parsear(texto: str) -> dict | None:
    """
    Interpreta un literal de foliatura. Devuelve None si no lo parece.

    El literal se conserva TAL CUAL está escrito. Lo que se separa es la lectura que
    hacemos de él, que es otra cosa y puede estar equivocada.
    """
    crudo = (texto or "").strip()
    if not crudo:
        return None
    m = _FOLIO.match(crudo.replace("°", "").replace("º", ""))
    if not m:
        return None
    numero, sufijo, cara = m.group(1), m.group(2), m.group(3)
    return {
        "literal": crudo,
        "numero": int(numero),
        "sufijo": _SUFIJOS.get((sufijo or "").lower()),
        "cara": ("reverso" if (cara or "").lower() in _REVERSO else None),
    }


def _candidatas(palabras, ancho: float, alto: float) -> list[dict]:
    """
    Las palabras de los márgenes que podrían ser una foliatura, mejor primero.

    Se puntúa por dónde está y por qué tan sola: arriba a la derecha es el lugar
    habitual del sello foliador, abajo al centro el de la numeración impresa.
    """
    if not (ancho and alto):
        return []
    arriba, abajo = alto * MARGEN, alto * (1 - MARGEN)
    salida = []
    for p in palabras:
        centro_y = (p.y0 + p.y1) / 2
        if arriba < centro_y < abajo:
            continue                                  # está en el cuerpo de la hoja
        leido = parsear(p.texto)
        if not leido:
            continue
        # ¿Está sola en su renglón?
        #
        # Lo que separa una foliatura de un número cualquiera del margen es que la
        # foliatura está SOLA: el sello foliador no escribe una frase. Un encabezado
        # como «Expediente 1234 del año» tiene un número en el margen y no es una
        # foliatura. Se cuentan las palabras del renglón entero, no las pegadas: medir
        # distancia deja pasar justamente las frases espaciadas.
        #
        # Se toleran hasta dos acompañantes porque el rótulo suele venir suelto del
        # OCR: «f.» «47», o «fs.» «47» «vta.».
        en_el_renglon = sum(1 for q in palabras
                            if q is not p
                            and abs(((q.y0 + q.y1) / 2) - centro_y) < 6)
        if en_el_renglon > 2:
            continue                                  # es parte de una frase
        vecinas = sum(1 for q in palabras
                      if q is not p
                      and abs(((q.y0 + q.y1) / 2) - centro_y) < 6
                      and (q.x0 - p.x1 < AISLAMIENTO and p.x0 - q.x1 < AISLAMIENTO))
        centro_x = (p.x0 + p.x1) / 2
        derecha = centro_x > ancho * 0.66
        centrada = ancho * 0.33 <= centro_x <= ancho * 0.66
        arriba_de_todo = centro_y <= arriba
        puntos = 0.5
        if arriba_de_todo and derecha:
            puntos = 0.92                             # el sello foliador, casi siempre
        elif not arriba_de_todo and derecha:
            puntos = 0.80
        elif not arriba_de_todo and centrada:
            puntos = 0.72                             # numeración impresa al pie
        elif arriba_de_todo and centrada:
            puntos = 0.60
        puntos -= 0.08 * vecinas
        salida.append({**leido, "confianza": round(max(0.3, puntos), 2),
                       "caja": (p.x0, p.y0, p.x1, p.y1)})
    salida.sort(key=lambda c: c["confianza"], reverse=True)
    return salida


def detectar_archivo(cx: sqlite3.Connection, sha: str, *, por_ruta=None,
                     serie: str = "principal") -> dict:
    """
    Propone la foliatura visible de cada foja de un archivo, leyendo los márgenes.

    Lo que propone es una LECTURA, con su confianza y su recuadro para poder ir a
    mirarla. Nunca pisa una foliatura que puso una persona.
    """
    from .capa2_extraccion import lecturas_por_ruta
    por_ruta = por_ruta or lecturas_por_ruta(cx, sha)

    medidas = {r["nro"]: (r["id"], r["ancho_pt"], r["alto_pt"])
               for r in cx.execute("""SELECT id, nro, ancho_pt, alto_pt FROM pagina
                                       WHERE sha256=?""", (sha,))}
    # La mejor candidata de cada foja, entre todas las rutas de lectura.
    mejor: dict[int, dict] = {}
    for pgs in por_ruta.values():
        for nro, _, palabras in pgs:
            if nro not in medidas:
                continue
            _, ancho, alto = medidas[nro]
            for c in _candidatas(palabras, ancho or 0, alto or 0)[:1]:
                if nro not in mejor or c["confianza"] > mejor[nro]["confianza"]:
                    mejor[nro] = c

    puestas = 0
    for nro, c in mejor.items():
        pagina_id = medidas[nro][0]
        ya = cx.execute("""SELECT origen FROM foliatura
                            WHERE pagina_id=? AND serie=?""", (pagina_id, serie)).fetchone()
        if ya and ya["origen"] == "humano":
            continue                    # lo que puso una persona no lo pisa una corrida
        x0, y0, x1, y1 = c["caja"]
        cx.execute("""INSERT INTO foliatura (pagina_id, serie, literal, numero, sufijo,
                                             cara, estado, origen, confianza,
                                             x0, y0, x1, y1, cuando)
                      VALUES (?,?,?,?,?,?,'leida','ocr',?,?,?,?,?,?)
                      ON CONFLICT(pagina_id, serie) DO UPDATE SET
                          literal=excluded.literal, numero=excluded.numero,
                          sufijo=excluded.sufijo, cara=excluded.cara,
                          estado='leida', origen='ocr', confianza=excluded.confianza,
                          x0=excluded.x0, y0=excluded.y0, x1=excluded.x1,
                          y1=excluded.y1, cuando=excluded.cuando""",
                   (pagina_id, serie, c["literal"], c["numero"], c["sufijo"], c["cara"],
                    c["confianza"], x0, y0, x1, y1, ahora()))
        puestas += 1
    cx.commit()
    # Las fojas sin candidata NO se marcan como «sin foliar»: no se detectó, que es
    # otra cosa. Ver el encabezado del módulo.
    return {"fojas": len(medidas), "detectadas": puestas,
            "sin_detectar": len(medidas) - puestas}


class NoSePuede(ValueError):
    """Lo pedido no se puede hacer, y el motivo es para leer."""


def poner_a_mano(cx: sqlite3.Connection, pagina_id: int, literal: str | None, quien: str,
                 *, serie: str = "principal", estado: str = "corregida") -> dict:
    """
    Una persona escribe la foliatura de una foja, o dice que no tiene.

    `estado='ausente'` es la forma de afirmar que el papel NO está foliado, que es
    distinto de que no se haya detectado nada. `estado='ilegible'` es que está y no se
    puede leer. Las dos son información sobre el expediente y por eso se guardan.
    """
    if not (quien or "").strip():
        raise NoSePuede("hace falta indicar quién lo dice")
    if estado not in ("corregida", "ausente", "ilegible"):
        raise NoSePuede(f"estado desconocido: {estado}")
    if not cx.execute("SELECT 1 FROM pagina WHERE id=?", (pagina_id,)).fetchone():
        raise NoSePuede("esa foja no existe")

    leido = {"literal": None, "numero": None, "sufijo": None, "cara": None}
    if estado == "corregida":
        if not (literal or "").strip():
            raise NoSePuede("hace falta escribir la foliatura, o decir que no tiene")
        leido = parsear(literal) or {"literal": literal.strip(), "numero": None,
                                     "sufijo": None, "cara": None}
    cx.execute("""INSERT INTO foliatura (pagina_id, serie, literal, numero, sufijo, cara,
                                         estado, origen, confianza, quien, cuando)
                  VALUES (?,?,?,?,?,?,?,'humano',1.0,?,?)
                  ON CONFLICT(pagina_id, serie) DO UPDATE SET
                      literal=excluded.literal, numero=excluded.numero,
                      sufijo=excluded.sufijo, cara=excluded.cara,
                      estado=excluded.estado, origen='humano', confianza=1.0,
                      quien=excluded.quien, cuando=excluded.cuando""",
               (pagina_id, serie, leido["literal"], leido["numero"], leido["sufijo"],
                leido["cara"], estado, quien, ahora()))
    p = cx.execute("SELECT sha256, nro FROM pagina WHERE id=?", (pagina_id,)).fetchone()
    cx.execute("""INSERT INTO auditoria (campo_id, sha256, orden, campo_nombre, accion,
                                         valor_nuevo, quien, cuando)
                  VALUES (NULL,?,?,?,?,?,?,?)""",
               (p["sha256"], p["nro"], f"(foliatura {serie})", estado,
                leido["literal"], quien, ahora()))
    cx.commit()
    return {"ok": True, "pagina_id": pagina_id, "serie": serie, "estado": estado,
            **leido}


def de_archivo(cx: sqlite3.Connection, sha: str) -> list[dict]:
    """
    La foliatura de cada foja de un archivo, con la página del PDF al lado.

    Las dos juntas y nombradas distinto a propósito: es la única forma de que quien
    mire la pantalla no las confunda.
    """
    filas = {}
    for r in cx.execute("""SELECT p.id, p.nro FROM pagina p WHERE p.sha256=?
                            ORDER BY p.nro""", (sha,)):
        filas[r["id"]] = {"pagina_id": r["id"], "pagina_pdf": r["nro"], "foliaturas": []}
    for f in cx.execute("""SELECT f.* FROM foliatura f
                             JOIN pagina p ON p.id = f.pagina_id
                            WHERE p.sha256=? ORDER BY p.nro, f.serie""", (sha,)):
        if f["pagina_id"] in filas:
            filas[f["pagina_id"]]["foliaturas"].append(
                {"serie": f["serie"], "literal": f["literal"], "numero": f["numero"],
                 "sufijo": f["sufijo"], "cara": f["cara"], "estado": f["estado"],
                 "origen": f["origen"], "confianza": f["confianza"],
                 "quien": f["quien"],
                 "caja": None if f["x0"] is None else [f["x0"], f["y0"], f["x1"], f["y1"]]})
    return list(filas.values())


def buscar(cx: sqlite3.Connection, texto: str) -> list[dict]:
    """
    Dónde está la foja que el papel numera así.

    Es lo que contesta «andá a fojas 47». Devuelve TODAS las que coinciden: en un legajo
    con expedientes incorporados puede haber más de una foja 47, y elegir una sola sería
    esconder el problema en lugar de mostrarlo.
    """
    leido = parsear(texto)
    if not leido:
        return []
    filas = cx.execute("""
        SELECT f.*, p.sha256, p.nro, a.nombre
          FROM foliatura f JOIN pagina p ON p.id = f.pagina_id
          JOIN archivo a ON a.sha256 = p.sha256
         WHERE f.numero = ? AND COALESCE(f.sufijo,'') = COALESCE(?, '')
         ORDER BY a.nombre, p.nro""", (leido["numero"], leido["sufijo"])).fetchall()
    return [{"sha256": f["sha256"], "archivo": f["nombre"], "pagina_pdf": f["nro"],
             "literal": f["literal"], "serie": f["serie"], "estado": f["estado"],
             "origen": f["origen"], "confianza": f["confianza"]} for f in filas]


def saltos(cx: sqlite3.Connection, sha: str) -> list[dict]:
    """
    Dónde la foliatura se corta, se repite o va para atrás.

    No es un error del sistema: es un hecho del expediente, y de los que importan. Una
    foja que falta entre la 46 y la 48 puede ser una foja sacada; dos fojas 47 pueden
    ser un expediente incorporado con su propia numeración. El sistema los señala, no
    los interpreta.
    """
    vistas = [(f["nro"], f["numero"], f["literal"]) for f in cx.execute("""
        SELECT p.nro, f.numero, f.literal FROM foliatura f
          JOIN pagina p ON p.id = f.pagina_id
         WHERE p.sha256=? AND f.serie='principal' AND f.numero IS NOT NULL
         ORDER BY p.nro""", (sha,))]
    salida = []
    for (nro_a, num_a, lit_a), (nro_b, num_b, lit_b) in zip(vistas, vistas[1:]):
        if num_b == num_a:
            salida.append({"clase": "repetida", "pagina_pdf": nro_b, "literal": lit_b,
                           "detalle": f"la foliatura {lit_b} aparece dos veces seguidas"})
        elif num_b < num_a:
            salida.append({"clase": "retrocede", "pagina_pdf": nro_b, "literal": lit_b,
                           "detalle": f"después de {lit_a} viene {lit_b}"})
        elif num_b > num_a + 1:
            salida.append({"clase": "salto", "pagina_pdf": nro_b, "literal": lit_b,
                           "detalle": f"entre {lit_a} y {lit_b} faltan "
                                      f"{num_b - num_a - 1} fojas"})
    return salida
