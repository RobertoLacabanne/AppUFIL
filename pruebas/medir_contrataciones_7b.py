"""Medición reproducible de 7b. Sólo imprime cantidades, nunca contenido del legajo."""
import argparse
import collections
import json
import re
import sqlite3
from pathlib import Path

from ufil import contrataciones as ct, renglones as rg, tablas


def medir(cx):
    ids = []
    sin_pieza = 0
    for t in cx.execute('SELECT * FROM tabla'):
        cs = cx.execute('SELECT texto FROM tabla_celda WHERE tabla_id=?', (t['id'],)).fetchall()
        if sum(bool(re.search(r'\d[\d.]*,\d{2}', c[0] or '')) for c in cs) >= 2:
            ids.append(t['id'])
            if not cx.execute('SELECT 1 FROM documento WHERE sha256=? AND pagina_desde<=? AND pagina_hasta>=?', (t['sha256'],t['pagina_nro'],t['pagina_nro'])).fetchone():
                sin_pieza += 1
    rs = [dict(r) for r in cx.execute('SELECT * FROM renglon WHERE vigente=1')]
    return dict(tablas=cx.execute('SELECT count(*) FROM tabla').fetchone()[0], tablas_con_importes=len(ids),
        tablas_con_importes_sin_pieza=sin_pieza, renglones=len(rs), con_precio=sum(r['precio_unitario'] is not None for r in rs),
        con_cantidad=sum(r['cantidad'] is not None for r in rs), derivados=sum(r['precio_derivado'] for r in rs),
        tablas_con_importes_y_renglones=len({r['tabla_id'] for r in rs if r['tabla_id'] in ids}),
        tablas_con_importes_y_precio=len({r['tabla_id'] for r in rs if r['tabla_id'] in ids and r['precio_unitario'] is not None}),
        precios_con_fuente=sum(bool(rg.fuente(cx,r,'precio')) for r in rs if r['precio_unitario'] is not None),
        contrataciones=cx.execute("SELECT count(*) FROM contratacion c WHERE EXISTS(SELECT 1 FROM contratacion_documento cd WHERE cd.contratacion_id=c.id AND cd.estado!='rechazada')").fetchone()[0])


def identificadores(cx):
    exactos, tolerantes = collections.defaultdict(lambda: collections.defaultdict(set)), collections.defaultdict(lambda: collections.defaultdict(set))
    for (sha,) in cx.execute('SELECT sha256 FROM archivo').fetchall():
        for nro, ps in ct.paginas_archivo(cx,sha).items():
            texto='\n'.join(' '.join(p.texto for p in linea) for linea in tablas._renglones(ps))
            norm=rg.normalizar(texto)
            for clase, patron in ct._PATRONES.items():
                for m in re.finditer(patron+r'n[°ºo]\s*(\d+(?:[-/]\d+)*)',norm):
                    exactos[clase][m[1]].add((sha,nro))
            for m in re.finditer(r'\b\d{2}-\d{8}-\d\b',texto):
                exactos['cuit'][m[0]].add((sha,nro))
            for linea in texto.splitlines():
                for i in ct.identificadores(linea):
                    tolerantes[i['clase']][i['valor']].add((sha,nro))
    def resumen(datos):
        return {k:dict(fojas=len(set().union(*v.values())), valores=len(v), repetidos_3_fojas=sum(len(s)>=3 for s in v.values())) for k,v in sorted(datos.items())}
    return dict(exactos=resumen(exactos), tolerantes_validados=resumen(tolerantes))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base',type=Path)
    parser.add_argument('--aplicar',action='store_true')
    args=parser.parse_args()
    cx=sqlite3.connect(args.base);cx.row_factory=sqlite3.Row;cx.execute('PRAGMA foreign_keys=ON')
    print(json.dumps({'antes':medir(cx)},ensure_ascii=False),flush=True)
    if args.aplicar:
        for (sha,) in cx.execute('SELECT sha256 FROM archivo').fetchall():
            rg.extraer_archivo(cx,sha)
        print(json.dumps({'reconstruccion':ct.reconstruir(cx)},ensure_ascii=False),flush=True)
        print(json.dumps({'despues':medir(cx)},ensure_ascii=False),flush=True)
    print(json.dumps({'identificadores':identificadores(cx)},ensure_ascii=False),flush=True)
    cx.close()


if __name__=='__main__':main()
