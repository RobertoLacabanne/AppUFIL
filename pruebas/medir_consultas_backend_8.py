"""Cuenta consultas y verifica planes sin guardar parámetros ni contenido real."""
import argparse
import json
import sqlite3
import statistics
import time
from pathlib import Path

from ufil import agregados_api, busqueda, contrataciones, listas_api, precios, servidor


def medir(base):
    c=sqlite3.connect(Path(base).as_uri()+'?mode=ro',uri=True)
    c.row_factory=sqlite3.Row
    sha=c.execute('SELECT sha256 FROM archivo LIMIT 1').fetchone()[0]
    prov=c.execute('SELECT proveedor_id FROM renglon WHERE proveedor_id IS NOT NULL LIMIT 1').fetchone()[0]
    resultado={'consultas':{},'planes':{}}
    for nombre,fn in [
        ('contrataciones',lambda:contrataciones.listar(c)),
        ('tablas',lambda:listas_api.resolver(c,'/api/tablas',{'sha':sha})),
        ('foliatura',lambda:listas_api.resolver(c,'/api/foliatura',{'sha':sha})),
        ('entidades',lambda:listas_api.resolver(c,'/api/entidades',{})),
        ('precios',lambda:precios.listar(c)),('cola',lambda:servidor.api_cola(c)),
        ('cruce',lambda:agregados_api.cruce(c,{})),('resumen',lambda:agregados_api.resumen(c)),
        ('proveedor',lambda:agregados_api.proveedor(c,prov,{}))]:
        consultas=[];c.set_trace_callback(consultas.append)
        t=time.perf_counter();fn();ms=1000*(time.perf_counter()-t)
        c.set_trace_callback(None)
        resultado['consultas'][nombre]=dict(consultas=len(consultas),ms=round(ms,2))
    lid=c.execute('SELECT id FROM lectura LIMIT 1').fetchone()[0]
    queries={
        'palabras_por_lectura':('SELECT texto FROM palabra WHERE lectura_id=? ORDER BY orden',(lid,)),
        'texto_fts':('SELECT rowid FROM pagina_texto WHERE pagina_texto MATCH ? LIMIT 50',('"contrato"*',)),
        'precios_proveedor':('SELECT id FROM renglon WHERE proveedor_id=? AND vigente=1 AND fecha_precio>=? ORDER BY fecha_precio,id LIMIT 50',(prov,'2020-01-01')),
        'celdas_tabla':('SELECT * FROM tabla_celda WHERE tabla_id=? ORDER BY fila,columna',(1,)),
        'hallazgos_revision':("SELECT id FROM hallazgo WHERE revision_estado='pendiente' AND ya_no_se_detecta=0 ORDER BY id LIMIT 50",()),
    }
    for nombre,(sql,args) in queries.items():
        resultado['planes'][nombre]=[r[3] for r in c.execute('EXPLAIN QUERY PLAN '+sql,args)]
    # Comparación de índices en una copia EN MEMORIA, con los mismos datos.
    copia=sqlite3.connect(':memory:');c.backup(copia)
    indices=('ix_renglon_proveedor_fecha','ix_renglon_compra_item','ix_contratacion_documento_doc',
             'ix_contratacion_estado_procedimiento','ix_hallazgo_revision','ix_hallazgo_contratacion',
             'ix_hallazgo_renglon','ix_hallazgo_fuente_renglon','ix_hallazgo_fuente_doc')
    ddl=[r[0] for r in copia.execute('SELECT sql FROM sqlite_master WHERE name IN ('+','.join('?' for _ in indices)+')',indices)]
    for i in indices:copia.execute('DROP INDEX IF EXISTS '+i)
    resultado['indices_misma_copia']={}
    for estado in ('sin_indices_27','con_indices_27'):
        if estado=='con_indices_27':
            for sql in ddl:copia.execute(sql)
        medidas={}
        for nombre in ('precios_proveedor','hallazgos_revision'):
            sql,args=queries[nombre]
            muestras=[]
            for _ in range(101):
                t=time.perf_counter();copia.execute(sql,args).fetchall();muestras.append(1000*(time.perf_counter()-t))
            medidas[nombre]=dict(ms=round(statistics.median(muestras),4),plan=[r[3] for r in copia.execute('EXPLAIN QUERY PLAN '+sql,args)])
        resultado['indices_misma_copia'][estado]=medidas
    copia.close();c.close()
    return resultado


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--salida',required=True)
    a=p.parse_args();Path(a.salida).write_text(json.dumps(medir(a.base),indent=2),encoding='utf-8')
