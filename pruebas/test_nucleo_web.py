"""Contrato HTTP y render real del plan, con datos sintéticos variables."""
import http.client
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid
import threading
import unittest
from unittest.mock import patch

from ufil import piezas, conjuntos, config, db, legajos
from ufil.db import ahora

RAIZ = Path(__file__).resolve().parents[1]


class NucleoPorHTTP(unittest.TestCase):
    def setUp(self):
        # mkdir normal conserva los permisos heredados del workspace en Windows.
        self.temporal = RAIZ / ('nucleo-web-' + uuid.uuid4().hex)
        self.temporal.mkdir()
        self.addCleanup(shutil.rmtree, self.temporal)
        self.datos = config.DATOS
        self.activo = config.legajo_activo()
        config.DATOS = self.temporal
        config.activar_legajo(None)
        self.addCleanup(self.restaurar_config)
        self.entorno = patch.dict(os.environ, {'UFIL_ACCESO': 'abierto'})
        self.entorno.start()
        self.addCleanup(self.entorno.stop)
        from ufil import servidor
        self.servidor = servidor
        self.previos = servidor.RUTA_BASE, servidor.PORTERIA, servidor._PROCESADORES.copy()
        self.addCleanup(self.restaurar_servidor)
        self.legajo = legajos.crear('TEST-ACT', 'Material sintético')
        config.activar_legajo(self.legajo.slug)
        self.base = Path(config.BASE)
        db.abrir(self.base).close()
        config.activar_legajo(None)
        self.srv = servidor.armar(0, base=self.temporal / 'suelta.sqlite')
        self.hilo = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.hilo.start()
        self.addCleanup(self.cerrar)

    def restaurar_config(self):
        config.DATOS = self.datos
        config.activar_legajo(self.activo)

    def restaurar_servidor(self):
        s = self.servidor
        s.RUTA_BASE, s.PORTERIA, previos = self.previos
        s._PROCESADORES.clear()
        s._PROCESADORES.update(previos)

    def cerrar(self):
        for p in self.servidor._PROCESADORES.values():
            if p._hilo:
                p._hilo.join(10)
        self.srv.shutdown()
        self.srv.server_close()
        self.hilo.join(5)

    def pedir(self, ruta, cuerpo=None, metodo='GET'):
        c = http.client.HTTPConnection('127.0.0.1', self.srv.server_address[1], timeout=20)
        try:
            c.request(metodo, ruta, None if cuerpo is None else json.dumps(cuerpo),
                      {'Content-Type': 'application/json', 'Cookie': f'ufil_legajo={self.legajo.slug}'})
            r = c.getresponse()
            return r.status, json.loads(r.read())
        finally:
            c.close()


    def sembrar(self):
        cx = db.abrir(self.base)
        try:
            for sha in ('a', 'b', 'c'):
                cx.execute("INSERT INTO archivo (sha256,ruta_original,nombre,bytes,paginas,ingerido_en) VALUES (?,?,?,1,6,?)", (sha, '/'+sha, sha+'.pdf', ahora()))
                for nro in range(1, 7):
                    cx.execute("INSERT INTO pagina (sha256,nro,ancho_pt,alto_pt) VALUES (?,?,100,100)", (sha,nro))
            doc = cx.execute("INSERT INTO documento (sha256,orden,pagina_desde,pagina_hasta,tipo,perfil,estado) VALUES ('a',1,1,2,'desconocido','auto','sin_perfil')").lastrowid
            cx.commit()
            return doc
        finally:
            cx.close()

    def post(self, ruta, datos):
        estado, respuesta = self.pedir(ruta, datos, 'POST')
        self.assertEqual(estado, 200, respuesta)
        return respuesta

    def test_sin_reconocer_vacio(self):
        estado, r = self.pedir('/api/piezas/sin-reconocer')
        self.assertEqual(estado, 200)
        self.assertEqual(r['piezas'], [])
        self.assertEqual(r['tipos'], piezas.tipos_posibles())
        self.assertEqual((r['total'],r['desde'],r['limite']), (0,0,50))

    def test_sin_reconocer_con_material(self):
        doc = self.sembrar()
        estado, r = self.pedir('/api/piezas/sin-reconocer')
        self.assertEqual(estado, 200)
        self.assertEqual(r['piezas'][0]['documento_id'], doc)
        self.assertEqual(r['piezas'][0]['fojas'], 2)
        self.assertEqual(r['piezas'][0]['archivo'], 'a.pdf')
        self.assertEqual(r['tipos'], piezas.tipos_posibles())

    def test_clasificar_cambia_y_audita(self):
        doc = self.sembrar()
        tipo = piezas.tipos_posibles()[0]['clave']
        self.post('/api/pieza/clasificar', dict(documento_id=doc, tipo=tipo, quien='persona.prueba'))
        cx = db.abrir(self.base)
        try:
            p = cx.execute('SELECT * FROM documento WHERE id=?', (doc,)).fetchone()
            self.assertEqual((p['tipo'],p['clasificado_por']), (tipo,'persona.prueba'))
            self.assertTrue(p['clasificado_en'])
            a = cx.execute('SELECT * FROM auditoria').fetchone()
            self.assertEqual((a['accion'], a['valor_nuevo'],a['quien']), ('clasificar',tipo,'persona.prueba'))
        finally:
            cx.close()

    def test_tipo_inventado_no_cambia_nada(self):
        doc = self.sembrar()
        cx = db.abrir(self.base)
        try:
            antes = list(cx.iterdump())
            estado,r = self.pedir('/api/pieza/clasificar', dict(documento_id=doc,tipo='tipo_inventado',quien='persona'), 'POST')
            self.assertEqual(estado,400)
            self.assertIn('tipo desconocido',r['error'])
            self.assertEqual(list(cx.iterdump()), antes)
        finally:
            cx.close()

    def test_continuar_y_separar_en_orden(self):
        doc = self.sembrar()
        for sha,desde,hasta in [('b',2,4),('a',5,6)]:
            r = self.post('/api/pieza/continuar', dict(documento_id=doc,sha256=sha,pagina_desde=desde,pagina_hasta=hasta,quien='persona'))
        estado,t = self.pedir('/api/pieza/tramos?id='+str(doc))
        self.assertEqual((estado,t['tramos']), (200,r['tramos']))
        self.assertEqual([x['sha256'] for x in t['tramos']], ['a','b','a'])
        self.assertEqual([x['quien'] for x in t['tramos']], [None,'persona','persona'])
        self.post('/api/pieza/separar', dict(tramo_id=t['tramos'][1]['id'],quien='otra'))
        self.assertEqual([x['pagina_desde'] for x in self.pedir('/api/pieza/tramos?id='+str(doc))[1]['tramos']], [1,5])
        cx=db.abrir(self.base)
        try:
            self.assertEqual(cx.execute("SELECT quien FROM auditoria WHERE accion='separar'").fetchone()[0], 'otra')
        finally:
            cx.close()

    def conjunto(self):
        self.sembrar()
        c=self.post('/api/conjunto/crear', dict(nombre='Entrega variable', organismo='Oficina', expediente='Referencia', anio=2026, nota='Nota'))
        for sha in ['a','b','c']:
            self.post('/api/conjunto/agregar', dict(conjunto_id=c['id'],sha256=sha))
        return c['id']

    def test_conjuntos_orden_cuentas_vecino_y_quitar(self):
        cid=self.conjunto()
        self.assertEqual(self.pedir('/api/conjuntos')[1]['conjuntos'][0]['archivos'],3)
        self.assertEqual(self.pedir('/api/conjuntos')[1]['conjuntos'][0]['paginas'],18)
        self.post('/api/conjunto/reordenar', dict(conjunto_id=cid,shas=['c','a','b']))
        c=self.pedir('/api/conjunto?id='+str(cid))[1]
        self.assertEqual([p['sha256'] for p in c['partes']],['c','a','b'])
        self.assertEqual([p['orden'] for p in c['partes']],[1,2,3])
        self.assertEqual(sum(p['piezas'] for p in c['partes']),1)
        self.assertEqual(self.pedir('/api/pieza/vecino?sha256=a')[1]['vecino']['sha256'],'b')
        self.assertIsNone(self.pedir('/api/pieza/vecino?sha256=b')[1]['vecino'])
        self.post('/api/conjunto/quitar',dict(conjunto_id=cid,sha256='a'))
        self.assertEqual([p['sha256'] for p in self.pedir('/api/conjunto?id='+str(cid))[1]['partes']],['c','b'])
        self.assertEqual(len(self.pedir('/api/archivos')[1]['archivos']),3)

    def test_reorden_incompleto_o_duplicado_no_escribe(self):
        cid=self.conjunto()
        for shas in [['b','a'],['a','b','c','a'], 'abc', [None]]:
            with self.subTest(shas=shas):
                antes=self.pedir('/api/conjunto?id='+str(cid))
                self.assertEqual(self.pedir('/api/conjunto/reordenar',dict(conjunto_id=cid,shas=shas),'POST')[0],400)
                self.assertEqual(self.pedir('/api/conjunto?id='+str(cid)),antes)

    def test_get_conserva_motivos_del_dominio(self):
        for ruta,motivo in [('/api/conjunto?id=999','ese conjunto no existe'),('/api/pieza/tramos?id=999','no existe la pieza 999')]:
            self.assertEqual(self.pedir(ruta),(400,{'error':motivo}))

    def test_datos_invalidos_son_400(self):
        doc=self.sembrar()
        for datos in [dict(documento_id=doc,tipo=[],quien='p'),dict(documento_id=True,tipo='x',quien='p'),dict(documento_id=doc,tipo='x',quien='')]:
            self.assertEqual(self.pedir('/api/pieza/clasificar',datos,'POST')[0],400)
        self.assertEqual(self.pedir('/api/pieza/continuar',dict(documento_id=doc,sha256='b',pagina_desde=3,pagina_hasta=99,quien='p'),'POST')[0],400)


@unittest.skipUnless(shutil.which('node'), 'El render JavaScript requiere Node')
class PantallasNucleo(unittest.TestCase):
    def test_datos_variables_escape_y_sin_preseleccion(self):
        js=(RAIZ/'ufil/web/app.js').read_text(encoding='utf-8')
        render=js[js.index('function htmlSinReconocer('):js.index('async function vReasociaciones(')]
        script=r"""
const assert=require('node:assert/strict');
const esc=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
"""+render+r"""
assert.ok(htmlSinReconocer([],[]).includes('No hay piezas sin reconocer'));
for (const n of [17,43,89]) {
  const tipos=[{clave:'futuro'+n,nombre:'Tipo futuro '+n,familia:'Familia '+n}];
  const p={documento_id:n,archivo:'<archivo>'+n,pagina_desde:n,pagina_hasta:n+1,fojas:2,tipo:'futuro'+n,clasificado_por:'Persona '+n};
  const h=htmlSinReconocer([p],tipos);
  for(const texto of ['&lt;archivo&gt;'+n,'Tipo futuro '+n,'Familia '+n,'Persona '+n,'No son un error ni un descarte','sin volver a subir nada']) assert.ok(h.includes(texto),texto);
  assert.ok(!h.includes('selected')); assert.ok(!h.includes('<archivo>'));
  const tramos=[{id:null,archivo:'Principal '+n,sha256:'s',pagina_desde:n,pagina_hasta:n+1,principal:true},
    {id:n,archivo:'Continuacion '+n,sha256:'t',pagina_desde:n+2,pagina_hasta:n+3,principal:false,quien:'Autor '+n}];
  const vecino={nombre:'Sugerido '+n,conjunto:'Entrega '+n,orden:n};
  const t=htmlContinuidad(tramos,vecino,[]);
  for(const texto of ['Principal '+n,'Continuacion '+n,'Autor '+n,'Sugerido '+n,'Entrega '+n,'eso no confirma']) assert.ok(t.includes(texto),texto);
  assert.equal((t.match(/data-separar=/g)||[]).length,1);
  assert.ok(!htmlContinuidad(tramos,null,[]).includes('mirar-vecino'));
  const c={nombre:'Conjunto '+n,partes:[{nombre:'Parte B '+n,sha256:'b',paginas:n,piezas:n+1},{nombre:'Parte A '+n,sha256:'a',paginas:n+2,piezas:n+3}]};
  const hcon=htmlConjunto(c,[]);
  assert.ok(hcon.indexOf('Parte B')<hcon.indexOf('Parte A'));
  assert.ok(hcon.includes((2*n+2)+' fojas')); assert.ok(hcon.includes((2*n+4)+' piezas'));
  assert.ok(hcon.includes('data-salto="-1" disabled')); assert.ok(hcon.includes('data-salto="1" disabled'));
}
"""
        r=subprocess.run(['node','-e',script],cwd=RAIZ,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(r.returncode,0,r.stderr)


if __name__ == '__main__':
    unittest.main()
