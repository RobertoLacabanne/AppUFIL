"""Auditoría GET reproducible. Sólo guarda métricas, nunca contenido del legajo.

python -m pruebas.medir_backend_8 --base ... --salida ... [--puerto 8811]
"""
import argparse
import json
import re
import sqlite3
import statistics
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen


def medir(base, puerto, repeticiones=3):
    cx = sqlite3.connect(Path(base).as_uri() + '?mode=ro', uri=True)
    def primero(tabla, columna='id', donde='1=1'):
        r = cx.execute(f'SELECT {columna} FROM {tabla} WHERE {donde} LIMIT 1').fetchone()
        return r[0] if r else 999999
    sha = primero('archivo', 'sha256')
    did = primero('documento')
    rutas = {r: {} for r in re.findall(r'ruta == ["\'](/api/[^"\']+)',
                                     Path('ufil/servidor.py').read_text(encoding='utf-8'))}
    rutas.update({r: {} for r in ('/api/contrataciones','/api/hallazgos','/api/resumen',
                  '/api/cruce','/api/entidades/sin-resolver','/api/entidades/propuestas',
                  '/api/foliatura/saltos','/api/reasociaciones/candidatas','/api/actividad/personas')})
    for r in ('/api/tablas','/api/foliatura','/api/foliatura/saltos'):
        rutas[r] = {'sha': sha}
    for r in ('/api/documento','/api/pieza/tramos','/api/relaciones/documento'):
        rutas[r] = {'id': did}
    for r in ('/api/tabla','/api/tabla/renglones'):
        rutas[r] = {'id': primero('tabla')}
    for r, t in (('/api/persona','persona'),('/api/entidad','entidad'),
                 ('/api/conjunto','conjunto'),('/api/coleccion','coleccion')):
        rutas[r] = {'id': primero(t)}
    rutas['/api/consulta'] = {'id': '07_cola_revision'}
    rutas['/api/buscar'] = {'q': 'contrato'}
    rutas['/api/pieza/vecino'] = {'sha256': sha}
    rutas['/api/reasociaciones/candidatas'] = {'sha': sha, 'campo': 'monto', 'orden_viejo': 1}
    rutas['/api/contratacion/'+str(primero('contratacion'))] = {}
    rutas['/api/proveedor/'+str(primero('renglon','proveedor_id','proveedor_id IS NOT NULL'))] = {}
    rutas['/api/renglon/'+str(primero('renglon'))+'/comparacion'] = {}
    salida = []
    for ruta, params in sorted(rutas.items()):
        muestras, nbytes, status, obj = [], 0, None, None
        for _ in range(repeticiones):
            inicio = time.perf_counter()
            try:
                with urlopen(f'http://127.0.0.1:{puerto}'+ruta+'?'+urlencode(params), timeout=120) as r:
                    raw, status = r.read(), r.status
            except HTTPError as e:
                raw, status = e.read(), e.code
            muestras.append(1000*(time.perf_counter()-inicio))
            nbytes = len(raw)
            try:
                obj = json.loads(raw)
            except ValueError:
                obj = None
        salida.append(dict(ruta=re.sub(r'/\d+', '/<id>', ruta), estado=status,
                           ms=round(statistics.median(muestras), 2), bytes=nbytes,
                           paginada=isinstance(obj,dict) and 'limite' in obj,
                           total=obj.get('total') if isinstance(obj,dict) else None))
    counts = {t: cx.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in
              ('archivo','pagina','documento','contratacion','renglon','hallazgo','tabla','tabla_celda','persona','palabra')}
    cx.close()
    return dict(repeticiones=repeticiones, cuentas=counts, endpoints=salida)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--base', required=True)
    p.add_argument('--puerto', type=int, default=8811)
    p.add_argument('--salida', required=True)
    a = p.parse_args()
    Path(a.salida).write_text(json.dumps(medir(a.base,a.puerto),indent=2),encoding='utf-8')
