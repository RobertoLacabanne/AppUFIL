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


# Los acentos, a un lado y al otro de la comparación.
#
# `COLLATE NOCASE` de SQLite es ASCII: «BENÍTEZ» y «benitez» le resultan distintos por
# la Í, y ni siquiera `lower()` la baja. Medido sobre el legajo de prueba: buscando el
# apellido sin acento —que es como lo escribe cualquiera— la búsqueda sobre campos
# devolvía CERO y la del texto de las fojas devolvía cuatro. Dos respuestas distintas
# a la misma pregunta en la misma pantalla, y la que decía cero es la que se lee como
# «no está en el legajo».
#
# Se resuelve en SQL y no con una función de Python: la comparación corre adentro de
# la consulta, sobre todos los valores, y una llamada a Python por fila cuesta más que
# los reemplazos. Están las dos capitalizaciones porque `lower()` tampoco baja una Í.
_ACENTOS = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n",
            "Á": "a", "É": "e", "Í": "i", "Ó": "o", "Ú": "u", "Ü": "u", "Ñ": "n"}


def _plano_sql(columna: str) -> str:
    expr = columna
    for de, a in _ACENTOS.items():
        expr = f"REPLACE({expr},'{de}','{a}')"
    return f"lower({expr})"


def plano(texto: str) -> str:
    """Lo mismo del lado de Python, para que los dos lados comparen igual."""
    for de, a in _ACENTOS.items():
        texto = texto.replace(de, a)
    return texto.lower()


def en_campos(cx: sqlite3.Connection, consulta: str, limite: int = 60) -> list[dict]:
    """
    Busca sobre los datos extraídos. Devuelve documentos de cualquier familia.

    Va contra `v_documento_todo` y no contra `v_contrato` a propósito: buscar un CUIT
    tiene que encontrar el contrato Y las facturas de esa persona. Una búsqueda que
    calla la mitad del material es peor que ninguna, porque el que busca concluye que
    no hay nada.
    """
    patron = f"%{plano(consulta.strip())}%"
    digitos = re.sub(r"\D", "", consulta)
    filas = cx.execute(f"""
        SELECT DISTINCT v.documento_id, v.archivo, v.camara, v.persona_id, v.familia,
               v.tipo, v.nombre_literal, v.documento_literal, v.inicio, v.fin,
               v.monto_centavos, c.nombre AS campo, c.valor_literal, c.pagina_nro
          FROM campo c
          JOIN v_documento_todo v ON v.documento_id = c.documento_id
         WHERE {_plano_sql("c.valor_literal")} LIKE ?
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


def cobertura(cx: sqlite3.Connection) -> dict:
    """
    Sobre cuántas fojas se buscó, y cuántas quedaron afuera.

    Esto existe porque la búsqueda era el ÚNICO lugar del sistema que afirmaba una
    ausencia sin haberla verificado.

    Dos fojas no entran al índice y las dos desaparecían sin dejar rastro:
    la que se procesó y cuya lectura quedó vacía —`reindexar` no inserta la fila si el
    texto está en blanco— y la que nunca se procesó, que ni siquiera aparece en la
    consulta que arma el índice. Para quien mira la pantalla, «esta palabra no está en
    el legajo» y «esta palabra puede estar en una de las diecinueve fojas que el
    sistema no pudo leer» se veían exactamente igual.

    En una herramienta que se usa para decidir si algo se imputa o se archiva, eso es
    de otra categoría que un tamaño de letra mal elegido. Y contradice al resto del
    sistema, que está construido sobre lo contrario: `Ø motivo` en lugar de celda
    vacía, el nulo que se escribe con su causa, la interfaz que no resuelve un
    conflicto sola.

    Se calcula al momento de buscar y no se guarda. Un contador guardado se queda
    viejo —basta con procesar un lote y no reindexar— y un número viejo acá vuelve a
    ser una afirmación que nadie verificó.

    La palabra que se usa afuera es «quedaron fuera de esta búsqueda», nunca
    «ilegibles». Es lo único que se puede sostener siempre: si el índice está
    atrasado, esas fojas igual no se miraron. El número nunca afirma más de lo que
    sabe.
    """
    def uno(sql):
        try:
            return cx.execute(sql).fetchone()[0] or 0
        except sqlite3.OperationalError:
            return 0

    fojas = uno("SELECT COUNT(*) FROM pagina")
    indexadas = uno("SELECT COUNT(*) FROM pagina_texto")
    # Nunca se procesaron: no tienen ni una lectura. Se arregla corriendo el proceso.
    sin_procesar = uno("""SELECT COUNT(*) FROM pagina p
                           WHERE NOT EXISTS (SELECT 1 FROM lectura l
                                              WHERE l.pagina_id = p.id)""")
    fuera = max(0, fojas - indexadas)
    return {
        "fojas": fojas,
        "indexadas": indexadas,
        "fuera": fuera,
        "sin_procesar": min(sin_procesar, fuera),
        # Se procesaron y no dieron texto utilizable. Ésas están en «Quedaron afuera»
        # y hay que mirarlas contra el papel.
        "sin_texto": max(0, fuera - min(sin_procesar, fuera)),
    }


def buscar(cx: sqlite3.Connection, consulta: str) -> dict:
    consulta = (consulta or "").strip()
    cob = cobertura(cx)
    if len(consulta) < 2:
        return {"consulta": consulta, "campos": [], "paginas": [],
                "cobertura": cob, "paginas_indexadas": cob["indexadas"],
                "aviso": "Escribí al menos dos caracteres."}
    campos = en_campos(cx, consulta)
    paginas = en_paginas(cx, consulta)
    return {"consulta": consulta, "campos": campos, "paginas": paginas,
            # La cobertura va SIEMPRE, haya resultados o no. Mostrarla sólo cuando no
            # hay es el mismo error con otra ropa: cuatro coincidencias sobre 241 fojas
            # leídas de 260 tampoco es lo mismo que cuatro sobre 260.
            "cobertura": cob,
            "paginas_indexadas": cob["indexadas"],
            "aviso": ("El índice de texto está vacío: correr «Reindexar» "
                      "o procesar un lote.") if not cob["indexadas"] else None}
