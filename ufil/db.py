"""Conexión y arranque de la base. SQLite en modo WAL, un solo archivo portable."""
from __future__ import annotations
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import config

# Se sube cuando cambia `esquema.sql`. Sirve para no reejecutar el script en cada
# conexión: con el servidor multihilo y el trabajador de fondo, dos conexiones que
# corrían el esquema a la vez chocaban al recrear la vista `v_contrato`.
ESQUEMA_VERSION = 13

_candado = threading.Lock()


def ahora() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def conectar(ruta: Path | None = None) -> sqlite3.Connection:
    ruta = Path(ruta or config.BASE)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(ruta, timeout=30.0)
    cx.row_factory = sqlite3.Row
    cx.execute("PRAGMA journal_mode=WAL")
    cx.execute("PRAGMA foreign_keys=ON")
    cx.execute("PRAGMA synchronous=NORMAL")
    return cx


def inicializar(cx: sqlite3.Connection, *, forzar: bool = False) -> bool:
    """
    Aplica el esquema si hace falta. Devuelve True si lo aplicó.

    Serializado con un candado de proceso: el `DROP VIEW` seguido del `CREATE VIEW` no
    es atómico, y dos hilos ejecutándolo a la vez terminan en «view already exists».
    """
    # Las columnas que faltan se chequean SIEMPRE, aunque la versión ya esté al día.
    # Si no, una base que quedó a mitad de camino —el número subió pero el ALTER no
    # llegó a correr— se queda rota para siempre y sin forma de arreglarse sola. Son
    # seis consultas de catálogo: no cuesta nada y se hace una vez por arranque.
    with _candado:
        if _agregar_columnas_faltantes(cx):
            cx.commit()
        _migrar_estados(cx)
    if not forzar and cx.execute("PRAGMA user_version").fetchone()[0] == ESQUEMA_VERSION:
        return False
    with _candado:
        if not forzar and cx.execute("PRAGMA user_version").fetchone()[0] == ESQUEMA_VERSION:
            return False
        cx.executescript(config.ESQUEMA.read_text(encoding="utf-8"))
        _agregar_columnas_faltantes(cx)
        cx.execute(f"PRAGMA user_version={ESQUEMA_VERSION}")
        cx.commit()
    return True


# Columnas que se sumaron a tablas que ya existían. `CREATE TABLE IF NOT EXISTS` no las
# agrega a una base ya creada, así que hay que pedirlas una por una. Es la forma
# barata de migrar sin perder lo que hay adentro: un `DROP TABLE` acá borraría las
# revisiones hechas a mano, que es exactamente lo que no se puede volver a generar.
COLUMNAS_AGREGADAS = (
    ("pagina", "rotacion", "INTEGER DEFAULT 0"),
    ("pagina", "clasificacion", "TEXT"),
    ("campo", "valor_auto", "TEXT"),
    ("campo", "motivo_auto", "TEXT"),
    ("campo", "conf_auto", "REAL"),
    ("campo", "ruta_auto", "TEXT"),
)


# Los estados de `campo` cambiaron por los ocho de ufil/confianza.py. Una base que ya
# tenía datos hay que traducirla, no dejarla con los viejos: media base con
# 'automatico' y media con 'automatico_alta' es peor que cualquiera de las dos, porque
# las consultas filtran por una lista y la mitad de las filas se cae en silencio.
TRADUCCION_ESTADOS = (
    # (viejo, condición extra, nuevo)
    ("automatico", "nulo_motivo IS NULL AND confianza >= 0.85", "automatico_alta"),
    ("automatico", "nulo_motivo IS NULL", "pendiente_baja"),
    ("automatico", "nulo_motivo = 'conflicto'", "conflicto"),
    ("automatico", "1=1", "no_revisado"),
    ("a_revisar",  "nulo_motivo = 'conflicto'", "conflicto"),
    ("a_revisar",  "valor_literal IS NOT NULL", "pendiente_baja"),
    ("a_revisar",  "1=1", "no_revisado"),
)


def _migrar_estados(cx: sqlite3.Connection) -> int:
    """Traduce los estados viejos de `campo` a los ocho de ufil/confianza.py."""
    try:
        quedan = cx.execute(
            "SELECT COUNT(*) FROM campo WHERE estado IN ('automatico','a_revisar')"
        ).fetchone()[0]
    except sqlite3.OperationalError:
        return 0                      # la tabla todavía no existe
    if not quedan:
        return 0
    for viejo, cond, nuevo in TRADUCCION_ESTADOS:
        cx.execute(f"UPDATE campo SET estado=? WHERE estado=? AND {cond}", (nuevo, viejo))
    cx.commit()
    return quedan


def _agregar_columnas_faltantes(cx: sqlite3.Connection) -> list[str]:
    agregadas = []
    for tabla, columna, tipo in COLUMNAS_AGREGADAS:
        # OJO: sobre una tabla que no existe, `PRAGMA table_info` NO da error, devuelve
        # cero filas. Sin este chequeo, en una base recién creada —donde todavía no
        # corrió el esquema— el conjunto sale vacío, parece que falta la columna y el
        # ALTER revienta con «no such table».
        existentes = {r[1] for r in cx.execute(f"PRAGMA table_info({tabla})")}
        if not existentes:
            continue
        if columna not in existentes:
            cx.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}")
            agregadas.append(f"{tabla}.{columna}")
    return agregadas


def ajuste(cx: sqlite3.Connection, clave: str, valor=None):
    """Lee o escribe un ajuste. Sin `valor`, lee."""
    if valor is None:
        r = cx.execute("SELECT valor FROM ajuste WHERE clave=?", (clave,)).fetchone()
        return r["valor"] if r else None
    cx.execute("""INSERT INTO ajuste (clave, valor) VALUES (?,?)
                  ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor""",
               (clave, str(valor)))
    cx.commit()
    return str(valor)


def abrir(ruta: Path | None = None) -> sqlite3.Connection:
    """Conexión con el esquema garantizado. Para la línea de comandos y el arranque."""
    cx = conectar(ruta)
    inicializar(cx)
    return cx
