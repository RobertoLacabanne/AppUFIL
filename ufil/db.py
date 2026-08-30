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
ESQUEMA_VERSION = 7

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
    if not forzar and cx.execute("PRAGMA user_version").fetchone()[0] == ESQUEMA_VERSION:
        return False
    with _candado:
        if not forzar and cx.execute("PRAGMA user_version").fetchone()[0] == ESQUEMA_VERSION:
            return False
        cx.executescript(config.ESQUEMA.read_text(encoding="utf-8"))
        cx.execute(f"PRAGMA user_version={ESQUEMA_VERSION}")
        cx.commit()
    return True


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
