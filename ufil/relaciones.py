"""
Lo que un documento dice de otro.

«Esta factura corresponde a aquella orden de compra». «Este decreto aprueba aquel
contrato». Son afirmaciones sobre el expediente, y una afirmación sin fuente no vale
nada: por eso `fuente` es obligatoria y dice de dónde salió.

Por qué tienen estado
---------------------
El sistema puede PROPONER que dos documentos hablan del mismo comprobante porque el
número coincide. De ahí a afirmar que uno documenta el pago del otro hay una distancia
que la recorre una persona. Una relación propuesta y una confirmada se ven distinto y
cuentan distinto, y mezclarlas convierte una sospecha en un hecho sin que nadie lo haya
decidido.

Lo que este módulo NO hace
--------------------------
No concluye. Que una factura cite una orden de compra es un dato; que eso pruebe que lo
facturado corresponde a lo contratado es una lectura, y la hace quien mira. El sistema
ordena y muestra con qué respaldo.
"""
from __future__ import annotations

import sqlite3

from .db import ahora

# Los tipos de relación del pliego. Cada uno dice algo distinto y por eso están
# separados: «factura» no es «documenta pago», y confundirlos es dar por cobrado lo que
# sólo está facturado.
TIPOS = {
    "incorpora": "incorpora",
    "remite_a": "remite a",
    "responde_a": "responde a",
    "aprueba": "aprueba",
    "modifica": "modifica",
    "cita": "cita",
    "notifica": "notifica",
    "factura": "factura",
    "documenta_entrega": "documenta entrega",
    "ordena_pagar": "ordena pagar",
    "documenta_pago": "documenta pago",
    "anula": "anula",
    "referencia": "hace referencia a",
    "copia_de": "es copia de",
    "version_de": "es versión de",
}

PROPUESTA, CONFIRMADA, RECHAZADA = "propuesta", "confirmada", "rechazada"


class NoSePuede(ValueError):
    """Lo pedido no se puede hacer, y el motivo es para leer."""


def anotar(cx: sqlite3.Connection, tipo: str, *, fuente: str,
           desde_doc: int | None = None, hasta_doc: int | None = None,
           desde_entidad: int | None = None, hasta_entidad: int | None = None,
           campo_id: int | None = None, confianza: float | None = None,
           estado: str = PROPUESTA, quien: str | None = None,
           nota: str | None = None) -> dict:
    """
    Anota una relación. Nace **propuesta** salvo que una persona la afirme.

    `fuente` es obligatoria: dice de dónde sale la afirmación (`campo:<nombre>`,
    `comprobante:<nro>`, `humano`). Una relación sin fuente no se puede revisar, y una
    relación que no se puede revisar no debería existir en un legajo.
    """
    if tipo not in TIPOS:
        raise NoSePuede(f"tipo de relación desconocido: {tipo}. Los que hay son: "
                        + ", ".join(TIPOS))
    if estado not in (PROPUESTA, CONFIRMADA, RECHAZADA):
        raise NoSePuede(f"estado desconocido: {estado}")
    if not (fuente or "").strip():
        raise NoSePuede("una relación sin fuente no se puede anotar")
    if desde_doc is None and desde_entidad is None:
        raise NoSePuede("la relación tiene que salir de un documento o de una entidad")
    if hasta_doc is None and hasta_entidad is None:
        raise NoSePuede("la relación tiene que llegar a un documento o a una entidad")
    if desde_doc is not None and desde_doc == hasta_doc:
        raise NoSePuede("un documento no se relaciona consigo mismo")
    if estado == CONFIRMADA and not (quien or "").strip():
        raise NoSePuede("confirmar una relación es una decisión: hace falta quién")

    cx.execute("""INSERT INTO relacion (tipo, desde_doc, hasta_doc, desde_entidad,
                                        hasta_entidad, fuente, campo_id, estado,
                                        confianza, nota, quien, cuando, creado_en)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                  ON CONFLICT(tipo, desde_doc, hasta_doc, desde_entidad, hasta_entidad,
                              fuente)
                  DO UPDATE SET confianza=excluded.confianza, nota=excluded.nota""",
               (tipo, desde_doc, hasta_doc, desde_entidad, hasta_entidad, fuente,
                campo_id, estado, confianza, nota, quien, ahora(), ahora()))
    cx.commit()
    return {"ok": True, "tipo": tipo, "estado": estado}


def decidir(cx: sqlite3.Connection, relacion_id: int, aceptar: bool, quien: str) -> dict:
    """
    Una persona confirma o rechaza una relación propuesta. **Nunca se borra.**

    Rechazar deja constancia de que alguien la miró y dijo que no. Borrarla haría que el
    sistema la vuelva a proponer en la próxima corrida, y que nadie sepa que ya se había
    descartado.
    """
    if not (quien or "").strip():
        raise NoSePuede("hace falta indicar quién decide")
    r = cx.execute("SELECT * FROM relacion WHERE id=?", (relacion_id,)).fetchone()
    if not r:
        raise NoSePuede("esa relación no existe")
    estado = CONFIRMADA if aceptar else RECHAZADA
    cx.execute("UPDATE relacion SET estado=?, quien=?, cuando=? WHERE id=?",
               (estado, quien, ahora(), relacion_id))
    cx.execute("""INSERT INTO auditoria (campo_id, sha256, orden, campo_nombre, accion,
                                         valor_anterior, valor_nuevo, quien, cuando)
                  VALUES (NULL,?,?,?,?,?,?,?,?)""",
               ((cx.execute("SELECT sha256 FROM documento WHERE id=?",
                            (r["desde_doc"],)).fetchone() or {"sha256": ""})["sha256"]
                if r["desde_doc"] else "", 0,
                f"(relación: {TIPOS.get(r['tipo'], r['tipo'])})", "relacionar",
                r["estado"], estado, quien, ahora()))
    cx.commit()
    return {"ok": True, "id": relacion_id, "estado": estado}


def proponer_por_comprobante(cx: sqlite3.Connection) -> int:
    """
    Propone relaciones entre documentos que nombran el mismo comprobante.

    Es la relación que más se usa al mirar un expediente de compras: qué factura
    corresponde a qué orden. Se propone por coincidencia del número, que es una señal
    fuerte pero no una prueba —dos organismos numeran sus órdenes desde uno— así que
    queda `propuesta` y con su fuente puesta.
    """
    n = 0
    filas = cx.execute("""
        SELECT m.norm, m.documento_id, d.tipo
          FROM mencion m JOIN documento d ON d.id = m.documento_id
         WHERE m.clase='comprobante' AND m.documento_id IS NOT NULL
         ORDER BY m.norm""").fetchall()
    por_numero: dict[str, list] = {}
    for f in filas:
        por_numero.setdefault(f["norm"], []).append(f)
    for numero, docs in por_numero.items():
        unicos = {d["documento_id"]: d for d in docs}
        if len(unicos) < 2:
            continue
        ids = sorted(unicos)
        for a, b in zip(ids, ids[1:]):
            try:
                anotar(cx, "referencia", fuente=f"comprobante:{numero}",
                       desde_doc=a, hasta_doc=b, confianza=0.6,
                       nota=f"las dos piezas nombran el comprobante {numero}")
                n += 1
            except NoSePuede:
                pass
    return n


def de_documento(cx: sqlite3.Connection, documento_id: int) -> list[dict]:
    """Las relaciones de una pieza, en las dos direcciones, con su estado y su fuente."""
    filas = cx.execute("""
        SELECT r.*, da.nombre AS archivo_desde, db.nombre AS archivo_hasta
          FROM relacion r
          LEFT JOIN documento d1 ON d1.id = r.desde_doc
          LEFT JOIN archivo da ON da.sha256 = d1.sha256
          LEFT JOIN documento d2 ON d2.id = r.hasta_doc
          LEFT JOIN archivo db ON db.sha256 = d2.sha256
         WHERE r.desde_doc=? OR r.hasta_doc=?
         ORDER BY r.estado, r.tipo""", (documento_id, documento_id)).fetchall()
    return [{"id": f["id"], "tipo": f["tipo"], "que_dice": TIPOS.get(f["tipo"], f["tipo"]),
             "desde_doc": f["desde_doc"], "hasta_doc": f["hasta_doc"],
             "archivo_desde": f["archivo_desde"], "archivo_hasta": f["archivo_hasta"],
             "hacia": "sale" if f["desde_doc"] == documento_id else "llega",
             "fuente": f["fuente"], "estado": f["estado"], "confianza": f["confianza"],
             "nota": f["nota"], "quien": f["quien"]} for f in filas]


def pendientes(cx: sqlite3.Connection, limite: int = 200) -> list[dict]:
    """Las relaciones que el sistema propuso y nadie miró todavía."""
    return [{"id": f["id"], "tipo": f["tipo"],
             "que_dice": TIPOS.get(f["tipo"], f["tipo"]),
             "desde_doc": f["desde_doc"], "hasta_doc": f["hasta_doc"],
             "archivo_desde": f["archivo_desde"], "archivo_hasta": f["archivo_hasta"],
             "fuente": f["fuente"], "confianza": f["confianza"], "nota": f["nota"]}
            for f in cx.execute("""
                SELECT r.*, da.nombre AS archivo_desde, db.nombre AS archivo_hasta
                  FROM relacion r
                  LEFT JOIN documento d1 ON d1.id = r.desde_doc
                  LEFT JOIN archivo da ON da.sha256 = d1.sha256
                  LEFT JOIN documento d2 ON d2.id = r.hasta_doc
                  LEFT JOIN archivo db ON db.sha256 = d2.sha256
                 WHERE r.estado='propuesta' ORDER BY r.confianza DESC LIMIT ?""",
                (limite,))]


def tipos_posibles() -> list[dict]:
    """El catálogo de relaciones, para ofrecerlo sin escribirlo a mano en la pantalla."""
    return [{"clave": k, "que_dice": v} for k, v in TIPOS.items()]
