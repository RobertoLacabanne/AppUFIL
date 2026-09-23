"""Contratos aditivos, paginación SQL y agregados sobre evidencia sintética."""
import json
import sqlite3
import unittest
from decimal import Decimal

from ufil import agregados_api as ag, contrataciones as ct, db, hallazgos, listas_api as listas
from ufil import paginacion as pg, precios, renglones as rg, servidor


class BackendFinal(unittest.TestCase):
    def setUp(self):
        self.cx = sqlite3.connect(':memory:')
        self.cx.row_factory = sqlite3.Row
        self.cx.executescript(db.esquema_sql())
        self.addCleanup(self.cx.close)
        self.cx.execute("INSERT INTO archivo(sha256,ruta_original,nombre,bytes,paginas,ingerido_en) VALUES ('s','s','Ejemplo.pdf',1,12,'2026-01-01')")
        for n in range(1,13):
            self.cx.execute("INSERT INTO pagina(sha256,nro,ancho_pt,alto_pt) VALUES ('s',?,595,842)",(n,))
        self.cx.execute("INSERT INTO entidad(id,clase,nombre,nombre_norm,clave_fuerte,creado_en) VALUES (1,'proveedor','Proveedor inventado','proveedor inventado','prueba','2026-01-01')")
        self.cid = self.cx.execute("INSERT INTO contratacion(nombre,procedimiento,estado,creado_en) VALUES ('Compra de prueba','licitacion','propuesta','2026-01-01')").lastrowid

    def documento(self, etapa, *, estado='extraido'):
        n = self.cx.execute('SELECT count(*)+1 FROM documento').fetchone()[0]
        did = self.cx.execute("INSERT INTO documento(sha256,orden,clave,pagina_desde,pagina_hasta,tipo,perfil,estado) VALUES ('s',?,?,?,?,?,'sin_perfil',?)",
                              (n,'s:'+str(n),n,n,etapa,estado)).lastrowid
        self.cx.execute('INSERT INTO contratacion_documento(contratacion_id,documento_id,etapa) VALUES (?,?,?)',(self.cid,did,etapa))
        return did

    def renglon(self, etapa, precio='10.00', moneda='ARS', desc='Cable', proveedor=1, fecha='2026-01-01'):
        did = self.documento(etapa)
        ancla = dict(pagina_nro=did,region=dict(x0=10,y0=10,x1=20,y1=20),celdas=[],campo_id=None)
        r = dict(clave='r'+str(did),sha256='s',pieza_clave='s:'+str(did),documento_id=did,
                 fila=1,pagina_nro=did,desc_literal=desc,desc_norm=rg.normalizar(desc),
                 unidad_literal='u',unidad_norm='unidad',cantidad='1.00',cantidad_literal='1',
                 precio_literal=precio,precio_unitario=precio,subtotal_literal=precio,subtotal=precio,
                 moneda=moneda,iva='incluido',fecha_precio=fecha,fecha_literal=fecha,
                 proveedor_id=proveedor,proveedor_literal='Proveedor inventado',
                 etapa=etapa,anclajes=json.dumps({k:ancla for k in ('precio','subtotal','fila','fecha')}),
                 metodo='sintetico',version=1,actualizado_en='2026-01-01')
        return self.cx.execute('INSERT INTO renglon('+','.join(r)+') VALUES ('+','.join('?' for _ in r)+')',list(r.values())).lastrowid

    def test_etapas_listado_una_agregacion_y_ficha_aditiva(self):
        self.documento('pliego'); self.documento('oferta'); rechazado=self.documento('oferta')
        self.cx.execute("UPDATE contratacion_documento SET estado='rechazada' WHERE documento_id=?",(rechazado,))
        sql=[]; self.cx.set_trace_callback(sql.append)
        r=ct.listar(self.cx)
        self.cx.set_trace_callback(None)
        # Cuenta, página, etapas agregadas y hallazgos agregados: cuatro consultas fijas,
        # cualquiera sea el largo de la página. Si crece con las filas, volvió el N+1.
        self.assertEqual(len(sql),4)
        self.assertEqual(r['contrataciones'][0]['etapas'],dict(pliego=1,ofertas=1,adjudicacion=0,orden_compra=0,factura=0,remito=0,pago=0))
        self.assertEqual(ct.listar(self.cx,etapa_faltante='ofertas')['total'],0)
        self.assertEqual(ct.listar(self.cx,etapa_faltante='pago')['total'],1)
        ficha=ct.ficha(self.cx,self.cid)
        self.assertEqual(len(ficha['estado_etapas']),7)
        pago=next(e for e in ficha['estado_etapas'] if e['clave']=='pago')
        self.assertEqual((pago['presente'],pago['cantidad'],pago['documentos'],pago['ausencia']),(False,0,[],'no_consta'))
        self.assertTrue(all('documento_ids' in e and 'documentos' in e for e in ficha['etapas']))

    def test_listas_buscan_antes_de_paginar_y_conservan_claves(self):
        for _ in range(3): self.documento('desconocido',estado='sin_perfil')
        for ruta, f, clave in [('/api/piezas/sin-reconocer',{'q':'Ejemplo'},'piezas'),
                               ('/api/fojas',{'q':'Ejemplo'},'fojas')]:
            a=listas.resolver(self.cx,ruta,dict(f,limite=1,desde=1))
            self.assertEqual(len(a[clave]),1)
            self.assertGreater(a['total'],1)
            self.assertEqual(a['filtros_aplicados']['q'],'Ejemplo')
            self.assertEqual(listas.resolver(self.cx,ruta,dict(f,desde=999))['total'],a['total'])
        fojas=listas.resolver(self.cx,'/api/fojas',{})
        self.assertTrue({'archivos','resumen','etiquetas','fojas'}<=fojas.keys())
        self.assertIn('tipos',listas.resolver(self.cx,'/api/piezas/sin-reconocer',{}))
        self.assertTrue({'clases','sin_resolver','propuestas'}<=listas.resolver(self.cx,'/api/entidades',{}).keys())

    def test_foliatura_pagina_acotada_sin_consulta_por_foja(self):
        for n in range(1,13):
            self.cx.execute("INSERT INTO foliatura(pagina_id,serie,literal,numero,estado,origen,cuando) VALUES (?,'principal',?,?,'leida','ocr','hoy')",(n,str(n+20),n+20))
        cantidades=[]
        for limite in (1,10):
            sql=[];self.cx.set_trace_callback(sql.append)
            r=listas.resolver(self.cx,'/api/foliatura',dict(sha='s',limite=limite))
            self.cx.set_trace_callback(None);cantidades.append(len(sql))
            self.assertEqual(r['total'],12)
            self.assertEqual(len(r['fojas']),limite)
            self.assertIn('caja',r['fojas'][0]['foliaturas'][0])
            self.assertIn('saltos',r)
        self.assertEqual(cantidades[0],cantidades[1])
        self.assertEqual(listas.resolver(self.cx,'/api/foliatura',dict(sha='s',q='25'))['total'],1)

    def test_cruce_ordena_diferencias_y_separa_ausencias(self):
        self.renglon('orden_compra','10.00')
        menor=self.renglon('factura','11.00'); mayor=self.renglon('factura','15.00')
        igual=self.renglon('factura','10.00'); otro=self.renglon('factura','20.00',moneda='USD')
        r=ag.cruce(self.cx,{})
        self.assertEqual([x['id'] for x in r['filas']],[mayor,menor,igual])
        self.assertEqual(r['filas'][0]['diferencia_absoluta'],'5.00')
        self.assertEqual(r['filas'][0]['diferencia_porcentual'],'50.00')
        self.assertEqual((r['total'],r['faltantes_total'],r['total_general']),(3,1,4))
        self.assertEqual(r['faltantes']['filas'][0]['id'],otro)
        self.assertIsNone(r['faltantes']['filas'][0]['diferencia_absoluta'])
        self.assertTrue(all(x['fuentes'] and x['fecha_contratado'] for x in r['filas']))
        self.assertEqual(ag.cruce(self.cx,{'limite':1,'desde':1})['filas'][0]['id'],menor)
        self.assertEqual([x['id'] for x in ag.cruce(self.cx,{'sentido':'asc'})['filas']],[menor,mayor,igual])

    def test_cruce_no_elige_entre_referencias_ambiguas_o_sin_fecha(self):
        self.renglon('orden_compra'); self.renglon('orden_compra')
        self.renglon('factura','12.00')
        self.assertEqual(ag.cruce(self.cx,{})['total'],0)
        self.cx.execute('UPDATE renglon SET vigente=0 WHERE id=2')
        self.cx.execute('UPDATE renglon SET fecha_precio=NULL WHERE id=3')
        self.assertEqual(ag.cruce(self.cx,{})['total'],0)

    def test_resumen_y_proveedor_separan_monedas_etapas_y_ausencias(self):
        self.renglon('adjudicacion','10.00'); self.renglon('factura','12.00')
        self.renglon('factura','3.00',moneda='USD'); self.renglon('factura',None)
        r=ag.resumen(self.cx)
        ars=next(m for m in r['dinero'] if m['etapa']=='factura' and m['moneda']=='ARS')
        self.assertEqual((ars['valor'],ars['con_valor'],ars['sin_valor'],ars['completo']),('12.00',1,1,False))
        self.assertEqual(len(r['prioridades']),3)
        p=ag.proveedor(self.cx,1,{'limite':1})
        self.assertEqual((len(p['historial_precios']['renglones']),p['historial_precios']['total']),(1,4))
        self.assertEqual(p['facturas']['total'],3)
        self.assertEqual(p['contrataciones']['total'],1)
        self.assertTrue(p['facturas']['documentos'][0]['fuente'])
        self.assertEqual(len(p['monto_facturado']),2)
        self.assertEqual(ag.operandos(self.cx,{'etapa':'factura','moneda':'USD'})['total'],1)

    def test_precio_cero_no_es_ausencia_y_literal_no_convertido_es_pendiente(self):
        rid=self.renglon('factura','0.00')
        self.assertIsNone(rg.serializar(self.cx,rg.fila(self.cx,rid))['precio_unitario']['ausencia'])
        self.cx.execute("UPDATE renglon SET precio_literal='7,890.12',precio_unitario=NULL WHERE id=?",(rid,))
        m=rg.serializar(self.cx,rg.fila(self.cx,rid))['precio_unitario']
        self.assertEqual((m['valor'],m['literal'],m['ausencia']),(None,'7,890.12','pendiente'))
        self.assertEqual(rg.decimal_argentino(m['literal']),Decimal('7890.12'))
        self.assertEqual(rg.importes('7.890'),[])

    def test_filtros_precio_antes_del_conteo_y_validacion(self):
        self.renglon('factura','10.00',fecha='2026-01-01')
        self.renglon('factura','20.00',fecha='2026-02-01',desc='Tubo')
        r=precios.listar(self.cx,q='tubo',desde_fecha='2026-02-01',proveedor_id=1,limite=1)
        self.assertEqual(r['total'],1)
        self.assertEqual(r['renglones'][0]['precio_unitario']['valor'],'20.00')
        self.assertEqual(precios.listar(self.cx,con_comparacion=False)['total'],2)
        self.assertEqual(precios.listar(self.cx,con_comparacion=True)['total'],0)
        for f in ({'orden':'id; DROP TABLE renglon'}, {'sentido':'otro'}, {'limite':0}, {'desde':-1}):
            with self.assertRaises(ValueError): precios.listar(self.cx,**f)

    def test_cola_busqueda_y_orden_conservan_la_revision(self):
        did=self.documento('contrato')
        for n in ('nombre','monto'):
            self.cx.execute("INSERT INTO campo(documento_id,nombre,valor_literal,estado,pagina_nro,x0) VALUES (?,?,'dato','pendiente_baja',1,0)",(did,n))
        r=servidor.api_cola(self.cx,{'q':'dato','orden':'campo','sentido':'desc'},limite=1)
        self.assertEqual((r['total'],len(r['filas']),r['filas'][0]['campo']),(2,1,'nombre'))
        self.assertEqual(r['filtros_aplicados'],{'q':'dato'})
        self.assertIn('opciones',r)

    def test_resumen_de_comparacion_conserva_el_calculo_completo(self):
        rid=self.renglon('factura','15.00',desc='Cable 2 mm')
        self.renglon('oferta','10.00',desc='Cable 2 mm')
        self.renglon('oferta','9.00',desc='Cable 3 mm')
        self.renglon('oferta','8.00',desc='Cable 2 mm',moneda='USD')
        completo=precios.comparar(self.cx,rid)
        breve=precios.comparar(self.cx,rid,resumen=True)
        for k in ('renglon','estadisticas','diferencia','calculo','calidad','advertencias'):
            self.assertEqual(completo[k],breve[k],k)
        pagina=precios.comparar(self.cx,rid,paginacion={'limite':1})
        self.assertEqual(pagina['excluidas_paginacion']['total'],2)
        self.assertEqual(len(pagina['excluidas']),1)
        self.assertEqual(pagina['estadisticas'],completo['estadisticas'])

    def test_consultas_de_precios_no_crecen_por_cada_fila(self):
        self.renglon('factura');self.renglon('oferta');self.renglon('oferta')
        cantidades=[]
        for limite in (1,3):
            sql=[];self.cx.set_trace_callback(sql.append)
            precios.listar(self.cx,limite=limite)
            self.cx.set_trace_callback(None);cantidades.append(len(sql))
        self.assertEqual(cantidades,[9,9])


if __name__ == '__main__':
    unittest.main()
