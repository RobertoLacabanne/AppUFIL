"""Conexión y arranque de la base. SQLite en modo WAL, un solo archivo portable."""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config


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


def inicializar(cx: sqlite3.Connection) -> None:
    cx.executescript(config.ESQUEMA.read_text(encoding="utf-8"))
    cx.commit()


def abrir(ruta: Path | None = None) -> sqlite3.Connection:
    cx = conectar(ruta)
    inicializar(cx)
    return cx
