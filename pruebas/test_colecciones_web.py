"""Colecciones manuales y consultas que vuelven a correr."""
import shutil
import unittest
from pruebas.test_entidades_web import HTTPBase, render
from ufil import db

class ColeccionesHTTP(HTTPBase):
    def test_consulta_guardar_listar_borrar(self):
        self.post('/api/consulta/guardar',dict(nombre='Busqueda',consulta='palabra',filtros={'clase':'inventada'},quien='r'))
        c=self.pedir('/api/consultas-guardadas')[1]['consultas'][0]
        self.assertEqual(c['filtros'],{'clase':'inventada'})
        self.post('/api/consulta/borrar',dict(id=c['id']))
        self.assertEqual(self.pedir('/api/consultas-guardadas')[1]['consultas'],[])
        self.assertEqual(self.pedir('/api/consulta/guardar',dict(nombre='',consulta='x',quien='r'),'POST')[0],400)

    def test_coleccion_crear_agregar_quitar_y_no_cambia_sola(self):
        doc=self.sembrar()
        c=self.post('/api/coleccion/crear',dict(nombre='Seleccion',quien='r',nota='Para revisar'))
        datos=dict(coleccion_id=c['id'],clase='documento',referencia=str(doc),quien='r',nota='Elegido')
        self.post('/api/coleccion/agregar',datos)
        self.post('/api/coleccion/agregar',datos)
        self.assertEqual(len(self.pedir('/api/coleccion?id='+str(c['id']))[1]['items']),1)
        self.assertEqual(self.pedir('/api/coleccion/agregar',{**datos,'clase':'inventada'},'POST')[0],400)
        self.post('/api/coleccion/quitar',{k:datos[k] for k in ['coleccion_id','clase','referencia']})
        self.assertEqual(self.pedir('/api/coleccion?id='+str(c['id']))[1]['items'],[])
        self.assertEqual(self.pedir('/api/documento?id='+str(doc))[0],200)

    def test_busqueda_expone_totales(self):
        self.sembrar()
        r=self.pedir('/api/buscar?q=palabra&limite=1&desde=0')[1]
        for clave in ['campos_total','paginas_total','hay_mas','variantes']: self.assertIn(clave,r)

    def test_http_respeta_paginacion(self):
        self.sembrar()
        r=self.pedir('/api/buscar?q=palabra&limite=1&desde=2')[1]
        self.assertEqual((r['limite'],r['desde']),(1,2))

@unittest.skipUnless(shutil.which('node'),'Requiere Node')
class ColeccionesRender(unittest.TestCase):
    def test_vacias_y_distincion(self):
        render("""assert.ok(htmlGuardadas({consultas:[]}).includes('No hay consultas')); assert.ok(htmlColecciones({colecciones:[]}).includes('No hay colecciones')); assert.ok(htmlColeccion({items:[]}).includes('no tiene elementos')); assert.ok(htmlColecciones({colecciones:[]}).includes('no cambia sola')); assert.ok(htmlGuardadas({consultas:[]}).includes('resultados cambian'));""")

    def test_datos_variables_y_escape(self):
        render("""for(const n of [9,27,81]) { const c={id:n,nombre:'<Nombre>'+n,quien:'Autor'+n,items:[{clase:'inventada'+n,referencia:'ref'+n,archivo:'archivo'+n,fojas:n,nota:'Nota'+n,quien:'Autor'+n}]}; const h=htmlColeccion(c); for(const x of ['&lt;Nombre&gt;'+n,'inventada'+n,'archivo'+n,'Nota'+n]) assert.ok(h.includes(x)); assert.ok(htmlGuardadas({consultas:[{...c,consulta:'texto'+n,filtros:{futuro:n}}]}).includes('texto'+n)); }""")

    def test_total_variantes_y_paginas_sin_duplicados(self):
        render("""const r={consulta:'BENITEZ',campos:[],paginas:[{sha256:'a',nro:1}],campos_total:0,paginas_total:731,desde:0,limite:1}; assert.ok(htmlResumenBusqueda(r).includes('Total: 731')); assert.ok(htmlResumenBusqueda(r).includes('Mostradas: 1')); const poco={...r,paginas_total:1,variantes:['BEN1TEZ']}; assert.ok(htmlResumenBusqueda(poco).includes('BEN1TEZ')); assert.ok(htmlResumenBusqueda(poco).includes('OCR')); const s=acumularBusqueda(r,{...r,desde:1,paginas:[{sha256:'a',nro:1},{sha256:'a',nro:2}]}); assert.equal(s.paginas.length,2); assert.throws(()=>acumularBusqueda(r,r),/repiti/);""")
