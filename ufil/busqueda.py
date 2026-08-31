"""
Búsqueda sobre el corpus.

Dos búsquedas distintas, y conviene no confundirlas, porque responden cosas distintas:

  * sobre los CAMPOS EXTRAÍDOS — "traeme a Pérez" — devuelve contratos, con su dato
    normalizado y su anclaje. Es exacta y sirve para trabajar.
  * sobre el TEXTO DE LAS PÁGINAS — "dónde dice maestranza" — devuelve folios, con el
    fragmento donde apareció. Es amplia y sirve para encontrar.

La interfaz las muestra separadas por eso mismo: un resultado de la primera es un
dato; uno de la segunda es un lugar donde mirar.

El índice es SQLite FTS5, que viene con Python. Sin servicio aparte, sin Elasticsearch,
sin nada que se pueda caer un martes a la mañana.
"""
from __future__ import annotations

import re
import sqlite3

MAX = 200


def reindexar(cx: sqlite3.Connection) -> int:
    """
    Rehace el índice de texto. Una fila por página, con la MEJOR lectura disponible.

    Una sola ruta por página a propósito: indexar las dos duplicaría cada resultado y
    el que busca vería el mismo folio dos veces sin entender por qué.
    """
    cx.execute("DELETE FROM pagina_texto")
    filas = cx.execute("""
        SELECT p.sha256, p.nro, l.id AS lid, l.ruta, l.confianza
          FROM pagina p JOIN lectura l ON l.pagina_id = p.id
         ORDER BY p.sha256, p.nro,
                  CASE l.ruta WHEN 'nativo' THEN 0 WHEN 'vlm' THEN 1 ELSE 2 END,
                  l.confianza DESC""").fetchall()
    vistas, n = set(), 0
    for f in filas:
        clave = (f["sha256"], f["nro"])
        if clave in vistas:
            continue
        vistas.add(clave)
        texto = " ".join(r["texto"] for r in cx.execute(
            "SELECT texto FROM palabra WHERE lectura_id=? ORDER BY orden", (f["lid"],)))
        if texto.strip():
            cx.execute("INSERT INTO pagina_texto (texto, sha256, nro) VALUES (?,?,?)",
                       (texto, f["sha256"], f["nro"]))
            n += 1
    cx.commit()
    return n


def preparar(consulta: str) -> str:
    """
    Pasa lo que escribió una persona a sintaxis de FTS5, sin que pueda romperla.

    Todo término se entrecomilla, así un guion o un paréntesis no vuelan la consulta.
    Lo que va entre comillas en la consulta original se respeta como frase exacta.
    Un término suelto admite prefijo (`perez` encuentra `perezosa`); una frase no.
    """
    partes = re.findall(r'"([^"]+)"|(\S+)', consulta.strip())
    tokens = []
    for frase, suelto in partes:
        if frase:
            tokens.append('"' + frase.replace('"', "") + '"')
        elif suelto:
            limpio = re.sub(r'["*()]', " ", suelto).strip()
            if limpio:
                tokens.append('"' + limpio + '"' + ("*" if len(limpio) >= 3 else ""))
    return " AND ".join(tokens)


def en_campos(cx: sqlite3.Connection, consulta: str, limite: int = 60) -> list[dict]:
    """
    Busca sobre los datos extraídos. Devuelve documentos de cualquier familia.

    Va contra `v_documento_todo` y no contra `v_contrato` a propósito: buscar un CUIT
    tiene que encontrar el contrato Y las facturas de esa persona. Una búsqueda que
    calla la mitad del material es peor que ninguna, porque el que busca concluye que
    no hay nada.
    """
    patron = f"%{consulta.strip()}%"
    digitos = re.sub(r"\D", "", consulta)
    filas = cx.execute("""
        SELECT DISTINCT v.documento_id, v.archivo, v.camara, v.persona_id, v.familia,
               v.tipo, v.nombre_literal, v.documento_literal, v.inicio, v.fin,
               v.monto_centavos, c.nombre AS campo, c.valor_literal, c.pagina_nro
          FROM campo c
          JOIN v_documento_todo v ON v.documento_id = c.documento_id
         WHERE c.valor_literal LIKE ? COLLATE NOCASE
            OR (? <> '' AND REPLACE(REPLACE(REPLACE(c.valor_literal,'-',''),'.',''),' ','')
                            LIKE '%' || ? || '%')
         ORDER BY v.documento_id LIMIT ?""",
        (patron, digitos, digitos, limite)).fetchall()
    return [dict(f) for f in filas]


def en_paginas(cx: sqlite3.Connection, consulta: str, limite: int = 60) -> list[dict]:
    """Busca sobre el texto de los folios. Devuelve páginas con el fragmento."""
    expr = preparar(consulta)
    if not expr:
        return []
    try:
        filas = cx.execute("""
            SELECT t.sha256, t.nro,
                   snippet(pagina_texto, 0, '[[', ']]', '…', 14) AS fragmento,
                   a.nombre AS archivo, d.id AS documento_id, d.camara
              FROM pagina_texto t
              JOIN archivo a ON a.sha256 = t.sha256
              LEFT JOIN documento d ON d.sha256 = t.sha256
             WHERE pagina_texto MATCH ?
             ORDER BY rank LIMIT ?""", (expr, limite)).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(f) for f in filas]


def buscar(cx: sqlite3.Connection, consulta: str) -> dict:
    consulta = (consulta or "").strip()
    if len(consulta) < 2:
        return {"consulta": consulta, "campos": [], "paginas": [],
                "aviso": "Escribí al menos dos caracteres."}
    campos = en_campos(cx, consulta)
    paginas = en_paginas(cx, consulta)
    indexado = cx.execute("SELECT COUNT(*) FROM pagina_texto").fetchone()[0]
    return {"consulta": consulta, "campos": campos, "paginas": paginas,
            "paginas_indexadas": indexado,
            "aviso": ("El índice de texto está vacío: correr «Reindexar» "
                      "o procesar un lote.") if not indexado else None}
