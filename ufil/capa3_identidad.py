"""
Capa 3 — Normalización e identidad.

Es donde el sistema más fácil se equivoca, así que es donde más conservador es.

Dos reglas, no negociables:

1. CUIT/CUIL/DNI es clave fuerte. Dos contratos con el mismo documento son la misma
   persona, y eso se resuelve solo. El nombre, jamás: "CORREA, Silvia N." y
   "CORREA, Silvia Noemí" pueden ser la misma persona o dos hermanas.

2. Todo lo que no tenga clave fuerte queda como persona SEPARADA, una por contrato.
   El sistema propone fusiones con un puntaje y un motivo, pero no aplica ninguna:
   una fusión errónea inventa un contratado con el doble de contratos, y eso contamina
   todos los cruces río abajo sin dejar rastro.

Aplicar una fusión es un acto humano y queda registrado con quién y cuándo.
"""
from __future__ import annotations

import sqlite3
from difflib import SequenceMatcher

from . import confianza as cf
from .capa2_campos import normalizar_cotejo, clave_de_persona
from .db import ahora

UMBRAL_PROPUESTA = 0.86


def _valor(cx, doc_id: int, campo: str, *, solo_firme: bool = True):
    """
    El valor de un campo, y por omisión SÓLO si está firme.

    Es la corrección de un defecto que se veía en la pantalla de personas: entraban
    como personas consolidadas nombres de OCR con confianza 0,31 —«SOSA, Rosa lI»,
    «LEDESMA, Héctor-D»— porque acá alcanzaba con que hubiera un valor. Una persona
    consolidada es una afirmación sobre alguien: no puede salir de un valor que el
    propio sistema tiene marcado como dudoso y sin revisar.

    `solo_firme=False` sirve para mostrar lo provisional donde corresponda mostrarlo,
    nunca para consolidar.
    """
    filtro = f"AND c.estado IN ({cf.SQL_FIRMES})" if solo_firme else ""
    r = cx.execute(
        f"""SELECT c.valor_literal, n.valor_norm
             FROM campo c LEFT JOIN normalizacion n ON n.campo_id=c.id
            WHERE c.documento_id=? AND c.nombre=? AND c.valor_literal IS NOT NULL
                  {filtro}""",
        (doc_id, campo)).fetchone()
    return (r["valor_literal"], r["valor_norm"]) if r else (None, None)


def resolver(cx: sqlite3.Connection) -> dict:
    """
    Asigna persona a cada documento. Solo une por clave fuerte.

    Es idempotente: se puede volver a correr todo el pipeline sin duplicar personas.
    Las decisiones humanas de fusión NO se pierden — viven en `fusion_decidida`,
    indexadas por nombre normalizado, y se vuelven a aplicar al final.
    """
    cx.execute("DELETE FROM persona_alias")
    cx.execute("DELETE FROM documento_persona")
    cx.execute("DELETE FROM fusion_propuesta")
    cx.execute("DELETE FROM persona")
    creadas = unidas = sueltas = 0
    for d in cx.execute("SELECT id FROM documento ORDER BY id").fetchall():
        doc_id = d["id"]
        nombre_lit, nombre_norm = _valor(cx, doc_id, "nombre")
        _, doc_norm = _valor(cx, doc_id, "documento")

        # Un documento normalizado tiene la forma «DNI:28456712» o «CUIL:27284567124».
        # Si no la tiene, no es una clave y se trata como si no hubiera documento: la
        # persona queda aislada y visible. Antes esto era un `split` a secas, y un solo
        # valor con forma inesperada cortaba el `resolver` a la mitad con un ValueError
        # —dejando al legajo entero SIN identidades resueltas, no sólo a ese documento—.
        # Que un dato raro cueste una persona aislada es aceptable; que cueste todas las
        # personas del legajo, no.
        if doc_norm and ":" in doc_norm:               # ── clave fuerte ──
            tipo, numero = doc_norm.split(":", 1)
            # El contrato identifica al contratado por DNI y la factura por CUIT. Un
            # CUIL de persona lleva el DNI adentro por construcción —en 27-27200341-1
            # los ocho del medio SON el DNI—, así que las dos claves se colapsan a la
            # misma. Sin esto, la misma persona entraba dos veces y el pago nunca se
            # cruzaba con el contrato que lo justifica, que es el cruce que hace falta.
            clave = clave_de_persona(doc_norm) or doc_norm
            fila = cx.execute("SELECT id FROM persona WHERE clave_fuerte=?", (clave,)).fetchone()
            if fila:
                pid = fila["id"]; unidas += 1
            else:
                pid = cx.execute(
                    """INSERT INTO persona (clave_fuerte, doc_tipo, doc_numero, creado_en)
                       VALUES (?,?,?,?)""", (clave, tipo, numero, ahora())).lastrowid
                creadas += 1
            via = "clave_fuerte"
        else:                                          # ── sin clave: aislada ──
            pid = cx.execute("INSERT INTO persona (clave_fuerte, creado_en) VALUES (NULL,?)",
                             (ahora(),)).lastrowid
            creadas += 1; sueltas += 1
            via = "sin_clave"

        cx.execute("""INSERT INTO documento_persona (documento_id, persona_id, via)
                      VALUES (?,?,?)
                      ON CONFLICT(documento_id) DO UPDATE SET persona_id=excluded.persona_id,
                                                              via=excluded.via""",
                   (doc_id, pid, via))
        if nombre_lit:
            campo_id = cx.execute(
                "SELECT id FROM campo WHERE documento_id=? AND nombre='nombre'", (doc_id,)
            ).fetchone()["id"]
            cx.execute("""INSERT INTO persona_alias (persona_id, nombre_literal, nombre_norm, campo_id)
                          VALUES (?,?,?,?)""",
                       (pid, nombre_lit, nombre_norm or normalizar_cotejo(nombre_lit), campo_id))
    cx.commit()
    rehechas = _reaplicar_decisiones(cx)
    return {"personas_creadas": creadas, "unidas_por_clave": unidas,
            "sin_clave": sueltas, "fusiones_humanas_reaplicadas": rehechas}


def identificador(cx, persona_id: int) -> str:
    """
    Identificador estable de una persona, que sobrevive a reprocesar el lote.

    Con clave fuerte, la clave misma. Sin clave fuerte, el SHA-256 de un documento
    suyo: como a cada documento sin documento legible le corresponde exactamente una
    persona, el hash la identifica sin ambigüedad. El nombre normalizado NO sirve —
    en los casos que importan, dos personas distintas comparten nombre.
    """
    r = cx.execute("SELECT clave_fuerte FROM persona WHERE id=?", (persona_id,)).fetchone()
    if r and r["clave_fuerte"]:
        return "clave:" + r["clave_fuerte"]
    d = cx.execute("""SELECT d.sha256, d.orden FROM documento_persona dp
                        JOIN documento d ON d.id = dp.documento_id
                       WHERE dp.persona_id=? ORDER BY d.id LIMIT 1""", (persona_id,)).fetchone()
    # Con el orden incluido: un mismo archivo puede traer varios contratos, y cada uno
    # es una persona distinta cuando no hay documento legible.
    return f"doc:{d['sha256']}#{d['orden']}" if d else f"persona:{persona_id}"


def _persona_por_ident(cx, ident: str):
    if ident.startswith("clave:"):
        r = cx.execute("SELECT id FROM persona WHERE clave_fuerte=?", (ident[6:],)).fetchone()
        return r["id"] if r else None
    if ident.startswith("doc:"):
        resto = ident[4:]
        sha, _, orden = resto.partition("#")
        r = cx.execute("""SELECT dp.persona_id FROM documento_persona dp
                            JOIN documento d ON d.id = dp.documento_id
                           WHERE d.sha256=? AND d.orden=?""",
                       (sha, int(orden or 1))).fetchone()
        return r["persona_id"] if r else None
    return None


def _reaplicar_decisiones(cx) -> int:
    """Vuelve a aplicar las fusiones que una persona ya confirmó en corridas previas."""
    n = 0
    for d in cx.execute("SELECT * FROM fusion_decidida WHERE decision='aceptada'").fetchall():
        a, b = _persona_por_ident(cx, d["ident_a"]), _persona_por_ident(cx, d["ident_b"])
        if a and b and a != b:
            _fusionar(cx, a, b); n += 1
    cx.commit()
    return n


def _fusionar(cx, destino: int, origen: int) -> None:
    """Mueve todo de `origen` a `destino`. Si una tiene clave fuerte, esa manda."""
    cf_d = cx.execute("SELECT clave_fuerte FROM persona WHERE id=?", (destino,)).fetchone()
    cf_o = cx.execute("SELECT clave_fuerte FROM persona WHERE id=?", (origen,)).fetchone()
    if cf_d and cf_o and not cf_d["clave_fuerte"] and cf_o["clave_fuerte"]:
        destino, origen = origen, destino
    cx.execute("""UPDATE documento_persona SET persona_id=?, via='fusion_confirmada'
                   WHERE persona_id=?""", (destino, origen))
    cx.execute("UPDATE persona_alias SET persona_id=? WHERE persona_id=?", (destino, origen))


def _parecido(a: str, b: str) -> tuple[float, str] | None:
    if a == b:
        return 1.0, "nombre normalizado idéntico"
    ta, tb = a.split(), b.split()
    if ta and tb and ta[0] == tb[0]:
        # "SILVIA N" contra "SILVIA NOEMI": el nombre abreviado se expande.
        corto, largo = (ta, tb) if len(" ".join(ta)) < len(" ".join(tb)) else (tb, ta)
        if len(corto) == len(largo) and all(
            c == l or (len(c) <= 2 and l.startswith(c[0])) for c, l in zip(corto, largo)
        ):
            return 0.93, "mismo apellido, nombre abreviado contra desarrollado"
    r = SequenceMatcher(None, a, b).ratio()
    return (r, f"similitud de nombre {r:.2f}") if r >= UMBRAL_PROPUESTA else None


def proponer_fusiones(cx: sqlite3.Connection) -> dict:
    """Propone. No aplica nada. Devuelve cuántas propuestas y cuántas homonimias."""
    filas = cx.execute("""
        SELECT p.id, p.clave_fuerte,
               (SELECT nombre_norm FROM persona_alias WHERE persona_id=p.id LIMIT 1) AS nn,
               (SELECT nombre_literal FROM persona_alias WHERE persona_id=p.id LIMIT 1) AS nl
          FROM persona p ORDER BY p.id""").fetchall()
    gente = [f for f in filas if f["nn"]]

    propuestas = homonimias = 0
    for i, a in enumerate(gente):
        for b in gente[i + 1:]:
            if a["clave_fuerte"] and b["clave_fuerte"]:
                if a["clave_fuerte"] != b["clave_fuerte"] and a["nn"] == b["nn"]:
                    # Mismo nombre, documentos distintos. No es fusión: es un dato
                    # que alguien tiene que mirar.
                    cx.execute("""INSERT INTO excepcion (clase, detalle, creado_en)
                                  VALUES ('homonimia_documentos_distintos',?,?)""",
                               (f"{a['nl']} ({a['clave_fuerte']}) vs {b['nl']} ({b['clave_fuerte']})",
                                ahora()))
                    homonimias += 1
                continue                       # nunca se fusionan dos claves fuertes
            r = _parecido(a["nn"], b["nn"])
            if not r:
                continue
            score, motivo = r
            if a["clave_fuerte"] or b["clave_fuerte"]:
                motivo += " · una de las dos tiene documento y la otra no"
            ia, ib = identificador(cx, a["id"]), identificador(cx, b["id"])
            if ia == ib:
                continue                   # ya son la misma persona
            ya = cx.execute("""SELECT 1 FROM fusion_decidida
                                WHERE (ident_a=? AND ident_b=?) OR (ident_a=? AND ident_b=?)""",
                            (ia, ib, ib, ia)).fetchone()
            if ya:
                continue                   # ya lo decidió una persona; no se re-pregunta
            cx.execute("""INSERT OR IGNORE INTO fusion_propuesta
                          (persona_a, persona_b, nombre_a, nombre_b, ident_a, ident_b,
                           score, motivo) VALUES (?,?,?,?,?,?,?,?)""",
                       (a["id"], b["id"], a["nn"], b["nn"], ia, ib, score, motivo))
            propuestas += 1
    cx.commit()
    return {"propuestas": propuestas, "homonimias": homonimias}


def detectar_contratos_repetidos(cx: sqlite3.Connection) -> int:
    """
    Marca los contratos que aparecen más de una vez.

    Un archivo repetido se detecta por su huella digital y no entra dos veces. Esto es
    lo otro: el mismo contrato llegando desde archivos DISTINTOS, que es lo que pasa
    cuando se rescanea parte de una pila y se sube todo junto en un PDF grande. Los
    archivos difieren en una página, la huella no los reconoce, y el contrato suma dos
    veces en los acumulados sin que nadie lo note.
    """
    cx.execute("DELETE FROM excepcion WHERE clase='contrato_repetido'")
    n = 0
    for r in cx.execute("""
        SELECT COALESCE(nombre_literal,'(sin nombre)') AS quien, documento_literal AS doc,
               inicio, fin, COUNT(*) AS veces,
               GROUP_CONCAT(DISTINCT archivo) AS archivos
          FROM v_contrato
         WHERE documento_literal IS NOT NULL AND inicio IS NOT NULL AND fin IS NOT NULL
         GROUP BY documento_norm, inicio, fin, monto_centavos
        HAVING COUNT(*) > 1""").fetchall():
        cx.execute("""INSERT INTO excepcion (clase, detalle, creado_en) VALUES (?,?,?)""",
                   ("contrato_repetido",
                    f"{r['quien']} ({r['doc']}) {r['inicio']}→{r['fin']} aparece "
                    f"{r['veces']} veces, en: {r['archivos']}", ahora()))
        n += 1
    cx.commit()
    return n


def decidir_fusion(cx: sqlite3.Connection, propuesta_id: int, aceptar: bool, quien: str) -> None:
    """Registra la decisión humana sobre una propuesta y, si es aceptada, la aplica."""
    if not quien or not quien.strip():
        raise ValueError("una fusión no se aplica sin constancia de quién la confirmó")
    f = cx.execute("SELECT * FROM fusion_propuesta WHERE id=?", (propuesta_id,)).fetchone()
    if not f or f["estado"] != "pendiente":
        raise ValueError("propuesta inexistente o ya decidida")
    decision = "aceptada" if aceptar else "rechazada"
    ia = f["ident_a"] or identificador(cx, f["persona_a"])
    ib = f["ident_b"] or identificador(cx, f["persona_b"])
    cx.execute("""INSERT OR REPLACE INTO fusion_decidida
                  (ident_a, ident_b, nombre_a, nombre_b, decision, quien, cuando)
                  VALUES (?,?,?,?,?,?,?)""",
               (ia, ib, f["nombre_a"], f["nombre_b"], decision, quien, ahora()))
    if aceptar:
        _fusionar(cx, f["persona_a"], f["persona_b"])
    cx.execute("""UPDATE fusion_propuesta SET estado=?, decidido_por=?, decidido_en=?
                   WHERE id=?""", (decision, quien, ahora(), propuesta_id))
    cx.commit()
