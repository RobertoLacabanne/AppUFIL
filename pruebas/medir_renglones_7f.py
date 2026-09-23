"""Corrida completa sobre copia en memoria; fuente SQLite abierta sólo para lectura.

python -m pruebas.medir_renglones_7f BASE SALIDA_JSON
"""
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from ufil import capa2_extraccion as c2, renglones, tablas


def medir(base, salida):
    with closing(sqlite3.connect(Path(base).resolve().as_uri() + '?mode=ro', uri=True)) as fuente:
        with closing(sqlite3.connect(':memory:')) as cx:
            fuente.backup(cx)
            cx.row_factory = sqlite3.Row
            cx.execute('PRAGMA foreign_keys=ON')
            for (sha,) in cx.execute('SELECT sha256 FROM archivo').fetchall():
                rutas = c2.lecturas_por_ruta(cx, sha)
                c2.clasificar_fojas(cx, sha, por_ruta=rutas)
                c2.segmentar_piezas(cx, sha, por_ruta=rutas)
                tablas.detectar_archivo(cx, sha, por_ruta=rutas)
                renglones.extraer_archivo(cx, sha, por_ruta=rutas)
            filas = [{k: r[k] for k in r.keys() if k != 'actualizado_en'}
                     for r in cx.execute('SELECT * FROM renglon WHERE vigente=1 ORDER BY clave')]
            resumen = {'renglones': len(filas),
                       'con_precio_unitario': sum(r['precio_unitario'] is not None for r in filas)}
            Path(salida).write_text(json.dumps({'resumen': resumen, 'filas': filas}, ensure_ascii=False), encoding='utf-8')
            print(json.dumps(resumen))


if __name__ == '__main__':
    medir(*sys.argv[1:])
