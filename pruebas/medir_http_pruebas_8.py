"""Mide las rutas HTTP sobre las bases sintéticas de la suite, incluidas escrituras.

No guarda solicitudes, respuestas ni parámetros: sólo ruta, estado, bytes y tiempo.
"""
import argparse
import functools
import json
import re
import statistics
import time
import unittest
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from ufil import servidor


def correr(salida):
    medidas=defaultdict(list)
    manejador=servidor.Manejador
    originales={k:getattr(manejador,k) for k in ('do_GET','do_POST','_json')}
    def envolver(fn):
        @functools.wraps(fn)
        def medir(self,*args,**kwargs):
            self._inicio_medicion_8=time.perf_counter()
            return fn(self,*args,**kwargs)
        return medir
    def responder(self,obj,codigo=200):
        t=getattr(self,'_inicio_medicion_8',time.perf_counter())
        ruta=re.sub(r'/\d+(?=/|$)','/<id>',urlsplit(self.path).path)
        medidas[(self.command,ruta,codigo)].append((1000*(time.perf_counter()-t),len(json.dumps(obj,ensure_ascii=False,default=str).encode('utf-8'))))
        return originales['_json'](self,obj,codigo)
    try:
        manejador.do_GET=envolver(originales['do_GET'])
        manejador.do_POST=envolver(originales['do_POST'])
        manejador._json=responder
        resultado=unittest.TextTestRunner().run(unittest.defaultTestLoader.discover('pruebas',pattern='test_*.py'))
    finally:
        for k,v in originales.items():setattr(manejador,k,v)
    resumen=[dict(metodo=k[0],ruta=k[1],estado=k[2],peticiones=len(v),
                  ms=round(statistics.median(x[0] for x in v),2),bytes_max=max(x[1] for x in v))
             for k,v in sorted(medidas.items()) if k[1].startswith('/api/')]
    Path(salida).write_text(json.dumps(dict(pruebas=resultado.testsRun,fallos=len(resultado.failures),
        errores=len(resultado.errors),omitidas=len(resultado.skipped),endpoints=resumen),indent=2),encoding='utf-8')
    return resultado.wasSuccessful()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--salida',required=True);a=p.parse_args()
    raise SystemExit(0 if correr(a.salida) else 1)
