"""Regresiones sintéticas del incremento 7b, sin material del legajo real."""
import json
import sqlite3
import unittest
import uuid
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from pruebas.test_renglones_precios import cargar, derivar
from ufil import db, renglones as rg, contrataciones as ct, hallazgos as ha, precios, versiones as vs


class OCRPlanillas(unittest.TestCase):
    def celdas(self, filas, encabezado=False):
        return [dict(id=1+f*10+c, fila=f, columna=c, texto=t, es_encabezado=int(encabezado and f==0),
                     x0=c*100, x1=c*100+90, y0=f*20, y1=f*20+15, confianza=.8)
                for f, fila in enumerate(filas) for c,t in enumerate(fila)]

    def test_barras_y_simbolos_pegados(self):
        self.assertEqual(str(rg.decimal_argentino('$1.638,65|')), '1638.65')
        self.assertEqual(rg.importes('$1.638,65| S32% $'), ['$1.638,65'])
        self.assertEqual(rg.importes('10,00 %'), [])
        self.assertEqual(rg.importes('$163865|'), [])
        self.assertEqual(rg.importes('1O0,00'), [])

    def test_encabezados_danados(self):
        for texto, esperado in [('Precio unarto','precio'), ('precio unramo','precio'),
                                ('MPorTE TOTAL','subtotal'), ('CANT.','cantidad')]:
            self.assertEqual(rg._rol(texto), esperado)

    def test_dos_importes_en_una_celda_conservan_fuente(self):
        cs=self.celdas([['Arandela', '$12,00| $24,00']])
        nuevos=rg.celdas_ocr(cs)
        self.assertEqual([c['texto'] for c in nuevos], ['Arandela','$12,00','$24,00'])
        self.assertEqual(nuevos[1]['id'], nuevos[2]['id'])
        self.assertEqual(nuevos[1]['x0'], nuevos[2]['x0'])

    def test_sin_encabezado_unidad_y_cuenta(self):
        cs=self.celdas([['2','un','Tubo','10,00','20,00'],['3','un','Caño','15,00','45,00']])
        self.assertEqual(rg.columnas(cs),dict(unidad=1,descripcion=2,cantidad=0,precio=3,subtotal=4))
        self.assertEqual(len(rg.filas_por_cuenta(cs)),2)

    def test_cantidad_fundida_con_descripcion_y_porcentaje(self):
        cs=self.celdas([['2.00 Tuerca','$10,00 0,00 %','$20,00'],['3.00 Perno','$12,00 0,00 %','$36,00']])
        filas=rg.filas_por_cuenta(cs)
        self.assertEqual(len(filas),2)
        self.assertEqual(filas[0]['descripcion']['texto'],'2.00 Tuerca')
        self.assertEqual(filas[0]['cantidad']['texto'],'2.00')
        self.assertEqual(str(rg.valor_celda(filas[0]['cantidad'])),'2.00')
        self.assertEqual(filas[0]['precio']['texto'],'$10,00')

    def test_no_adivina_columna_de_importes_sola_ni_codigo(self):
        for filas in [[['Tubo','12,00'],['Caño','13,00']],
                      [['2','Tubo','10,00','20,00'],['3','Caño','15,00','45,00']],
                      [['1','un','Tubo','10,00','10,00'],['1','un','Caño','15,00','15,00']]]:
            self.assertFalse(rg.filas_por_cuenta(self.celdas(filas)))


class ReconstruccionYHallazgos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=sqlite3.connect(':memory:'); cls.base.row_factory=sqlite3.Row
        cls.base.executescript(db.esquema_sql())
        carpeta=Path(__file__).resolve().parents[1]/'.tmp-pruebas'/('7b-sintetico-'+uuid.uuid4().hex)
        carpeta.mkdir(parents=True)
        cargar(cls.base,carpeta)
        derivar(cls.base)
        ct.reconstruir(cls.base)
        cls.base.commit()

    @classmethod
    def tearDownClass(cls):
        cls.base.close()

    def setUp(self):
        self.cx=sqlite3.connect(':memory:');self.cx.row_factory=sqlite3.Row
        self.base.backup(self.cx)
        self.cx.execute('PRAGMA foreign_keys=ON')
        self.addCleanup(self.cx.close)

    def hallazgos(self):
        ha.recalcular(self.cx)
        return ha.listar(self.cx,limite=500)['hallazgos']

    def test_corpus_exactamente_siete_con_fuentes_y_revision(self):
        hs=self.hallazgos()
        self.assertEqual(Counter(h['tipo'] for h in hs),dict(diferencia_precio=3,facturado_vs_adjudicado=2,
            facturado_vs_entregado=1,subtotal_incorrecto=1))
        for h in hs:
            self.assertTrue(h['fuentes']);self.assertTrue(h['confianza']['motivos'])
            self.assertFalse(ct.cp.terminos_prohibidos_en(h['titulo']+' '+h['descripcion']))
            if h['calculo']:
                self.assertTrue(all(o['fuente'] for o in h['calculo']['operandos']))
        h=next(h for h in hs if h['tipo']=='subtotal_incorrecto')
        ha.revisar(self.cx,h['id'],dict(estado='relevante',nota='Verificado',quien='Prueba'))
        for (sha,) in self.cx.execute('select sha256 from archivo').fetchall():rg.extraer_archivo(self.cx,sha)
        ct.reconstruir(self.cx)
        self.hallazgos()
        self.assertEqual(ha.obtener(self.cx,h['id'])['revision']['nota'],'Verificado')

    def test_revisado_que_desaparece_se_conserva(self):
        h=next(h for h in self.hallazgos() if h['tipo']=='subtotal_incorrecto')
        ha.revisar(self.cx,h['id'],dict(estado='descartado',nota='Corrección de lectura'))
        self.cx.execute("UPDATE renglon SET subtotal='84000.00' WHERE etapa='factura' AND fila=2")
        self.hallazgos()
        nuevo=ha.obtener(self.cx,h['id'])
        self.assertTrue(nuevo['ya_no_se_detecta'])
        self.assertEqual(nuevo['revision']['estado'],'descartado')

    def test_ficha_propuesta_etapas_totales_matriz_cronologia(self):
        cs=ct.listar(self.cx)['contrataciones'];self.assertEqual(len(cs),1)
        f=ct.ficha(self.cx,cs[0]['id'])
        self.assertEqual(f['contratacion']['estado'],'propuesta')
        self.assertEqual(len(f['oferentes']),3)
        self.assertEqual(f['totales']['adjudicado']['valor'],'466000.00')
        self.assertEqual(f['totales']['facturado']['valor'],'497000.00')
        self.assertIsNone(f['totales']['pagado'])
        self.assertEqual(len(f['matriz']['filas']),3)
        self.assertEqual(len(f['cronologia']),12)
        self.assertTrue(all(e['fuente'] for e in f['cronologia']))

    def test_decision_humana_se_conserva(self):
        self.cx.execute("UPDATE contratacion_documento SET origen='humano',estado='rechazada',quien='Prueba' WHERE documento_id=(SELECT id FROM documento WHERE tipo='factura')")
        ct.reconstruir(self.cx)
        self.assertEqual(self.cx.execute("SELECT count(*) FROM contratacion_documento WHERE estado='rechazada' AND quien='Prueba'").fetchone()[0],1)
        self.assertIsNone(self.cx.execute("SELECT contratacion_id FROM renglon WHERE etapa='factura'").fetchone()[0])

    def test_total_inconsistente(self):
        self.cx.execute("UPDATE renglon SET subtotal='85001.00' WHERE etapa='factura' AND fila=2")
        h=next(h for h in self.hallazgos() if h['tipo']=='total_inconsistente')
        self.assertEqual(h['calculo']['resultado'],'497001.00')

    def test_precio_ausente_solo_etapas_con_precio(self):
        self.cx.execute("UPDATE renglon SET precio_unitario=NULL,precio_motivo='ilegible' WHERE etapa='factura' AND fila=1")
        hs=[h for h in self.hallazgos() if h['tipo']=='precio_ausente']
        self.assertEqual(len(hs),1)

    def test_oferente_unico(self):
        self.cx.execute("DELETE FROM contratacion_documento WHERE etapa='oferta' AND documento_id!=(SELECT min(documento_id) FROM contratacion_documento WHERE etapa='oferta')")
        self.assertEqual(sum(h['tipo']=='oferente_unico' for h in self.hallazgos()),1)

    def test_ofertas_identicas(self):
        self.cx.execute("UPDATE renglon SET precio_unitario=CASE fila WHEN 1 THEN '100.00' WHEN 2 THEN '200.00' ELSE '300.00' END WHERE etapa='oferta'")
        self.assertEqual(sum(h['tipo']=='ofertas_identicas' for h in self.hallazgos()),3)

    def test_documento_faltante(self):
        self.cx.execute("DELETE FROM contratacion_documento WHERE etapa='factura'")
        self.assertTrue(any(h['tipo']=='documento_faltante' for h in self.hallazgos()))

    def test_secuencia_temporal(self):
        docs=ct.documentos(self.cx)
        for d in docs:
            if d['etapa']=='factura':d['fecha']['valor']='2023-01-01'
        with patch.object(ct,'documentos',return_value=docs):
            self.assertEqual(sum(h['tipo']=='secuencia_temporal' for h in self.hallazgos()),1)

    def test_duplicado_potencial(self):
        docs=ct.documentos(self.cx)
        factura=next(d for d in docs if d['etapa']=='factura')
        otro=next(d for d in docs if d['etapa']=='orden_pago')
        otro['etapa']='factura';otro['claves']=set(factura['claves'])
        with patch.object(ct,'documentos',return_value=docs):
            self.assertTrue(any(h['tipo']=='duplicado_potencial' for h in self.hallazgos()))

    def test_paginacion_revision_y_validaciones(self):
        self.hallazgos()
        pagina=ha.listar(self.cx,limite=2,desde=1)
        self.assertEqual((pagina['total'],len(pagina['hallazgos'])),(7,2))
        for kw in [dict(limite=0),dict(desde=-1),dict(tipo='inventado'),dict(estado='confirmado')]:
            with self.assertRaises(ValueError):ha.listar(self.cx,**kw)
        with self.assertRaises(rg.NoEncontrado):ha.revisar(self.cx,99999,dict(estado='relevante'))
        with self.assertRaises(ValueError):ha.revisar(self.cx,1,dict(estado='inventado'))

    def test_sello_solo_hallazgos_cambia_con_umbral(self):
        a,b=vs.etapa('contrataciones').sello(),vs.etapa('hallazgos').sello()
        with patch.dict(ct.cp.UMBRALES,diferencia_senalable_pct='25.00'):
            self.assertEqual(vs.etapa('contrataciones').sello(),a)
            self.assertNotEqual(vs.etapa('hallazgos').sello(),b)

    def test_variacion_compras_independientes(self):
        cid=self.cx.execute("INSERT INTO contratacion(clave,nombre,creado_en) VALUES ('otra','Otra compra',?)",(db.ahora(),)).lastrowid
        doc=self.cx.execute("SELECT id FROM documento WHERE tipo='factura'").fetchone()[0]
        self.cx.execute('UPDATE contratacion_documento SET contratacion_id=? WHERE documento_id=?',(cid,doc))
        self.cx.execute("UPDATE renglon SET contratacion_id=?,moneda='ARS',iva='incluido' WHERE documento_id=?",(cid,doc))
        self.cx.execute("UPDATE renglon SET precio_unitario='220000.00' WHERE etapa='factura' AND fila=1")
        self.assertEqual(sum(h['tipo']=='variacion_compras' for h in self.hallazgos()),1)

    def test_coincidencia_agenda_no_afirma_relacion(self):
        docs=ct.documentos(self.cx)
        agenda=next(d for d in docs if d['etapa']=='pedido')
        factura=next(d for d in docs if d['etapa']=='factura')
        agenda['es_agenda']=True;agenda['fecha']['valor']=factura['fecha']['valor']
        with patch.object(ct,'documentos',return_value=docs):
            hs=[h for h in self.hallazgos() if h['tipo']=='coincidencia_temporal']
        self.assertEqual(len(hs),1)
        self.assertIn('No indica relación',hs[0]['descripcion'])

    def test_varias_senales_sin_fusion_por_cuit_solo(self):
        # Dos pares: dentro de cada par hay una orden de compra repetida que los une; entre
        # pares sólo está el CUIT compartido, que por sí solo no alcanza para fusionar.
        docs=ct.documentos(self.cx)[:4]
        for i,d in enumerate(docs):
            d['claves']={('cuit','30712345670'),('orden_compra',f'{111*(1+i//2)}/2023')}
            d['conjuntos']=set()
        with patch.object(ct,'documentos',return_value=docs):ct.reconstruir(self.cx)
        self.assertEqual(ct.listar(self.cx)['total'],2)
        for d in docs:d['conjuntos']={1}
        with patch.object(ct,'documentos',return_value=docs):ct.reconstruir(self.cx)
        self.assertEqual(ct.listar(self.cx)['total'],1)
        self.assertTrue(all(r[0]=='propuesta' for r in self.cx.execute('SELECT estado FROM contratacion_documento')))

    def test_expedientes_distintos_no_se_unen_por_orden(self):
        # Dos piezas por expediente: el sistema no propone contrataciones de una sola pieza,
        # así que para ver si dos expedientes se unen o no hay que darle algo que unir.
        docs=ct.documentos(self.cx)[:4]
        for i,d in enumerate(docs):
            d['claves']={('expediente',str(100+i//2)),('orden_compra','333/2023')}
        with patch.object(ct,'documentos',return_value=docs):ct.reconstruir(self.cx)
        self.assertEqual(ct.listar(self.cx)['total'],2)

    def test_ficha_no_escribe_entidades(self):
        cid=ct.listar(self.cx)['contrataciones'][0]['id']
        cambios=self.cx.total_changes
        ct.ficha(self.cx,cid)
        self.assertEqual(self.cx.total_changes,cambios)

    def test_resegmentar_conserva_agrupacion_confirmada(self):
        self.cx.execute("UPDATE contratacion_documento SET origen='humano',estado='confirmada',quien='Prueba'")
        self.cx.commit()
        derivar(self.cx)
        ct.reconstruir(self.cx)
        self.assertEqual(self.cx.execute("SELECT count(*) FROM contratacion_documento WHERE estado='confirmada' AND quien='Prueba'").fetchone()[0],12)

    def test_decision_persistente_reaplica_por_clave_y_expone_ancla_perdida(self):
        l=self.cx.execute('SELECT * FROM contratacion_documento LIMIT 1').fetchone()
        ct.decidir_vinculo(self.cx,l['contratacion_id'],l['documento_id'],'confirmada','Persona')
        self.cx.execute('DELETE FROM contratacion_documento WHERE id=?',(l['id'],))
        ct.reconstruir(self.cx)
        self.assertEqual(self.cx.execute('SELECT estado FROM contratacion_documento WHERE documento_id=?',(l['documento_id'],)).fetchone()[0],'confirmada')
        self.cx.execute("UPDATE documento SET clave='pieza_cambiada' WHERE id=?",(l['documento_id'],))
        f=ct.ficha(self.cx,l['contratacion_id'])
        self.assertEqual(len(f['decisiones_sin_pieza']),1)

    def test_planilla_sin_pieza_se_ancla_sin_inventar_etapa(self):
        sha=self.cx.execute('SELECT sha256 FROM archivo LIMIT 1').fetchone()[0]
        self.cx.execute('INSERT INTO pagina(sha256,nro,ancho_pt,alto_pt) VALUES (?,2,600,800)',(sha,))
        tid=self.cx.execute('INSERT INTO tabla(sha256,pagina_nro,orden,filas,columnas,x0,y0,x1,y1,creado_en) VALUES (?,2,1,2,5,0,0,500,40,?)',(sha,db.ahora())).lastrowid
        cs=OCRPlanillas().celdas([['2','un','Tornillo','10,00','20,00'],['3','un','Arandela','12,00','36,00']])
        for c in cs:
            self.cx.execute('INSERT INTO tabla_celda(tabla_id,fila,columna,texto,x0,y0,x1,y1,confianza) VALUES (?,?,?,?,?,?,?,?,?)',
                            (tid,c['fila'],c['columna'],c['texto'],c['x0'],c['y0'],c['x1'],c['y1'],.8))
        self.cx.commit()
        rg.extraer_archivo(self.cx,sha)
        rs=[dict(r) for r in self.cx.execute('SELECT * FROM renglon WHERE tabla_id=? AND vigente=1',(tid,))]
        self.assertEqual(len(rs),2)
        self.assertEqual({r['etapa'] for r in rs},{'otro'})
        self.assertTrue(all(rg.fuente(self.cx,r,'precio')['celdas'] for r in rs))
        rg.extraer_archivo(self.cx,sha)
        self.assertEqual(self.cx.execute('SELECT count(*) FROM renglon WHERE tabla_id=? AND vigente=1',(tid,)).fetchone()[0],2)


class Identificadores(unittest.TestCase):
    def test_ocr_numero_y_digitos_separados(self):
        ids=ct.identificadores('Expte. N º 1 2 3 4 / 2 0 2 3; Orden de compra Nro.: 0 1 2 / 2 0 2 3')
        self.assertIn(('expediente','1234/2023'),{(i['clase'],i['valor']) for i in ids})
        self.assertIn(('orden_compra','12/2023'),{(i['clase'],i['valor']) for i in ids})

    def test_ceros_y_prefijo_no_rompen_referencia(self):
        a=ct.identificadores('Expediente EXP-007731/2023')
        b=ct.identificadores('Expte. 7731/2023')
        self.assertEqual(a[0]['valor'],b[0]['valor'])

    def test_cuit_valida_verificador(self):
        bueno=next('3071234567'+str(i) for i in range(10) if ct.entidades._cuit_valido('3071234567'+str(i)))
        ids=ct.identificadores('CUIT '+ ' '.join(bueno)+'; CUIT 00-00000000-1')
        self.assertEqual([i['valor'] for i in ids if i['clase']=='cuit'],[bueno])


from pruebas import test_nucleo_web as soporte


class Rutas7b(unittest.TestCase):
    setUp=soporte.NucleoPorHTTP.setUp
    restaurar_config=soporte.NucleoPorHTTP.restaurar_config
    restaurar_servidor=soporte.NucleoPorHTTP.restaurar_servidor
    cerrar=soporte.NucleoPorHTTP.cerrar
    pedir=soporte.NucleoPorHTTP.pedir

    def test_listas_ficha_revision_y_errores_http(self):
        cx=db.abrir(self.base)
        try:
            cargar(cx,self.temporal/'sinteticos')
            derivar(cx);ct.reconstruir(cx);ha.recalcular(cx)
        finally:cx.close()
        estado,lista=self.pedir('/api/contrataciones?limite=1')
        self.assertEqual(estado,200);self.assertEqual(lista['total'],1)
        cid=lista['contrataciones'][0]['id']
        self.assertEqual(self.pedir('/api/contratacion/'+str(cid))[0],200)
        self.assertEqual(self.pedir('/api/contratacion/999999')[0],404)
        estado,lista=self.pedir('/api/hallazgos?tipo=subtotal_incorrecto&limite=1')
        self.assertEqual(estado,200);self.assertEqual(lista['total'],1)
        hid=lista['hallazgos'][0]['id']
        estado,h=self.pedir('/api/hallazgo/'+str(hid)+'/revision',dict(estado='relevante',nota='Cotejado'),'POST')
        self.assertEqual(estado,200);self.assertEqual(h['revision']['nota'],'Cotejado')
        self.assertEqual(self.pedir('/api/hallazgo/999999/revision',dict(estado='relevante'),'POST')[0],404)
        self.assertEqual(self.pedir('/api/hallazgo/'+str(hid)+'/revision',dict(estado='invalido'),'POST')[0],400)
        self.assertEqual(self.pedir('/api/hallazgos?desde=-1')[0],400)
        self.assertEqual(self.pedir('/api/contrataciones?limite=x')[0],400)
