"""
Capa 4 — Análisis determinístico.

Corre las consultas de ufil/consultas/*.sql. Son archivos versionados, no cadenas
embebidas en el código: cuando el fiscal pida una variante ("lo mismo pero sólo 2021")
se copia el archivo, se edita y queda el rastro de las dos versiones.

Acá no hay modelo de lenguaje. Todo lo que sale de esta capa es SQL sobre las tablas
normalizadas, y se puede reproducir a mano.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from . import config


def _resolver(sql: str) -> str:
    """
    Reemplaza las marcas de tipos de documento, igual que en el esquema.

    Una consulta que quiera separar contratos de comprobantes escribe
    `d.tipo IN ({{TIPOS_CONTRATO}})` en vez de la lista a mano, y así la lista sigue
    viviendo en un solo lugar (ufil/clasificacion.py). Se importa acá adentro y no
    arriba para no atar esta capa a la de clasificación cuando la consulta no la usa.
    """
    if "{{" not in sql:
        return sql
    from .db import SUSTITUCIONES
    for marca, valor in SUSTITUCIONES.items():
        sql = sql.replace(marca, valor)
    return sql


def catalogo() -> list[dict]:
    salida = []
    for p in sorted(config.CONSULTAS.glob("*.sql")):
        texto = p.read_text(encoding="utf-8")
        desc = [l[3:].strip() for l in texto.splitlines() if l.startswith("--")]
        salida.append({
            "id": p.stem,
            "titulo": p.stem.split("_", 1)[1].replace("_", " ").capitalize(),
            "descripcion": " ".join(desc[:3]),
            # Con los tipos ya puestos: la pantalla de consultas muestra el SQL que se
            # corrió de verdad, no una plantilla que nadie puede pegar en una terminal.
            "sql": _resolver(texto),
            "ruta": str(p.relative_to(config.RAIZ)),
        })
    return salida


def correr(cx: sqlite3.Connection, id_consulta: str) -> dict:
    ruta = config.CONSULTAS / f"{id_consulta}.sql"
    if not ruta.exists():
        raise FileNotFoundError(f"No existe la consulta «{id_consulta}».")
    sql = _resolver(ruta.read_text(encoding="utf-8"))
    cur = cx.execute(sql)
    columnas = [d[0] for d in cur.description]
    filas = [dict(zip(columnas, f)) for f in cur.fetchall()]
    return {"id": id_consulta, "columnas": columnas, "filas": filas,
            "n": len(filas), "sql": sql, "ruta": str(ruta.relative_to(config.RAIZ))}
