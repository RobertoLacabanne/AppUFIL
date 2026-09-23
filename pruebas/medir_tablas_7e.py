"""Medición sin OCR ni escrituras en la base de entrada.

python -m pruebas.medir_tablas_7e RUTA_A_COPIA_SQLITE
"""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
from unittest.mock import patch

from ufil import renglones, tablas


def medir(ruta):
    with closing(sqlite3.connect(Path(ruta).resolve().as_uri() + '?mode=ro', uri=True)) as fuente:
        cx = sqlite3.connect(':memory:')
        fuente.backup(cx)
    cx.row_factory = sqlite3.Row
    try:
        shas = [r[0] for r in cx.execute('SELECT sha256 FROM archivo')]
        # Misma extracción integrada de 7d; se desactiva sólo la nueva compuerta.
        with patch.object(tablas, '_estructurada', return_value=True):
            for sha in shas:
                renglones.extraer_archivo(cx, sha)
        antes = [dict(r) for r in cx.execute('SELECT * FROM renglon WHERE vigente=1 ORDER BY clave')]
        tipos, resumen = {}, {}
        for t in cx.execute('SELECT * FROM tabla'):
            d = cx.execute('''SELECT tipo FROM documento WHERE sha256=?
                              AND ? BETWEEN pagina_desde AND pagina_hasta
                              ORDER BY id LIMIT 1''', (t['sha256'], t['pagina_nro'])).fetchone()
            tipo = d[0] if d else 'sin documento'
            tipos[t['id']] = tipo
            fila = resumen.setdefault(tipo, [0, 0, 0, 0])
            cs = [dict(c) for c in cx.execute('SELECT * FROM tabla_celda WHERE tabla_id=?', (t['id'],))]
            fila[0] += 1
            fila[1] += t['origen'] == 'humano' or tablas._estructurada(cs)
        for sha in shas:
            renglones.extraer_archivo(cx, sha)
        despues = [dict(r) for r in cx.execute('SELECT * FROM renglon WHERE vigente=1 ORDER BY clave')]
        for indice, rs in ((2, antes), (3, despues)):
            for r in rs:
                resumen[tipos[r['tabla_id']]][indice] += 1
        firma = lambda rs: [{k: v for k, v in r.items() if k != 'actualizado_en'} for r in rs]
        iguales = firma(antes) == firma(despues)
        print(json.dumps({'columnas': ['tablas_antes', 'tablas_despues', 'renglones_antes', 'renglones_despues'],
                          'por_tipo': resumen,
                          'total': [sum(f[i] for f in resumen.values()) for i in range(4)],
                          'renglones_identicos_salvo_actualizado_en': iguales}, indent=2))
        if not iguales:
            raise AssertionError('La compuerta cambió los renglones')
    finally:
        cx.close()


if __name__ == '__main__':
    medir(sys.argv[1])
