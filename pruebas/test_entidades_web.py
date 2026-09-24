"""Interfaz y contrato real, con material sintetico."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path
from pruebas import test_nucleo_web as soporte
from ufil import db, entidades, relaciones

RAIZ = Path(__file__).resolve().parents[1]

class HTTPBase(unittest.TestCase):
    setUp = soporte.NucleoPorHTTP.setUp
    restaurar_config = soporte.NucleoPorHTTP.restaurar_config
    restaurar_servidor = soporte.NucleoPorHTTP.restaurar_servidor
    cerrar = soporte.NucleoPorHTTP.cerrar
    pedir = soporte.NucleoPorHTTP.pedir
    post = soporte.NucleoPorHTTP.post
    sembrar = soporte.NucleoPorHTTP.sembrar


def render(script):
    js = (RAIZ/'ufil/web/app.js').read_text(encoding='utf-8')
    trozo = js[js.index('/* Menciones conservan'):js.index('const rutas = [')]
    esc = "const esc=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('\"','&quot;');"
    r = subprocess.run(['node','-e', "const assert=require('node:assert/strict');" + esc + trozo + script], capture_output=True, text=True, encoding='utf-8', cwd=RAIZ)
    if r.returncode: raise AssertionError(r.stderr)


class EntidadesHTTP(HTTPBase):
    def test_confirmar_y_rechazar_fusion(self):
        doc = self.sembrar()
        cx = db.abrir(self.base)
        try:
            clase = entidades.CLASES[0]
            entidades.anotar(cx, clase, 'Literal inventado', origen='fuente-inventada', documento_id=doc, sha256='a', pagina_nro=2)
        finally: cx.close()
        r = self.post('/api/entidad/confirmar', dict(clase=clase,norm='literal inventado',nombre='Nombre humano',quien='revisor'))
        e = self.pedir('/api/entidad?id='+str(r['entidad_id']))[1]
        self.assertEqual(e['menciones'][0]['origen'],'fuente-inventada')
        self.assertEqual(e['menciones'][0]['pagina_nro'],2)
        self.post('/api/entidad/rechazar',dict(clase=clase,norm='otra',quien='revisor'))
        self.assertEqual(self.pedir('/api/entidad/confirmar',dict(clase=clase,norm='x',nombre='',quien='r'),'POST')[0],400)

    def test_relacion_decisiones_y_anotacion(self):
        doc = self.sembrar()
        cx=db.abrir(self.base)
        try:
            otro=cx.execute("INSERT INTO documento (sha256,orden,pagina_desde,pagina_hasta,tipo,perfil,estado) VALUES ('b',1,1,2,'desconocido','auto','sin_perfil')").lastrowid
            cx.commit()
            tipo=next(iter(relaciones.TIPOS))
            relaciones.anotar(cx,tipo,fuente='fuente inventada',desde_doc=doc,hasta_doc=otro,confianza=.52)
        finally: cx.close()
        r=self.pedir('/api/relaciones')[1]['pendientes'][0]
        for aceptar,estado in [(True,'confirmada'),(False,'rechazada')]:
            self.post('/api/relacion/decidir',dict(id=r['id'],aceptar=aceptar,quien='r'))
            guardada=self.pedir('/api/relaciones/documento?id='+str(doc))[1]['relaciones'][0]
            self.assertEqual(guardada['estado'],estado)
            self.assertEqual(guardada['fuente'],'fuente inventada')
        self.post('/api/relacion/anotar',dict(tipo=tipo,desde_doc=otro,hasta_doc=doc,quien='humana',nota='Respaldo'))
        self.assertEqual(self.pedir('/api/relacion/anotar',dict(tipo='inexistente',desde_doc=doc,hasta_doc=otro,quien='r'),'POST')[0],400)
        self.assertTrue(any(r['hacia']=='llega' for r in self.pedir('/api/relaciones/documento?id='+str(doc))[1]['relaciones']))

@unittest.skipUnless(shutil.which('node'),'Requiere Node')
class EntidadesRender(unittest.TestCase):
    def test_vacios(self):
        render("""assert.ok(htmlRelaciones([]).includes('No hay relaciones')); assert.ok(htmlEntidad({menciones:[]}).includes('No hay menciones'));""")

    def test_catalogos_fuentes_y_propuesta_sin_preseleccion(self):
        render(r"""
global.location = { hash: '#/entidades' };
global.vista = { innerHTML: '' };
global.$ = () => ({});
global.bloque = (a, b, c) => c;
global.ausente = m => m;
global.vacio = (t, m) => m;
global.tablaServidor = (dest, url, clave, cols, opts) => {
  global._cols = global._cols || {}; global._cols[clave] = cols;
  global._opts = global._opts || {}; global._opts[clave] = opts;
};
global.api = async () => global._mockApiResult;
(async () => {
  for (const n of [7,31,83]) {
   const m={clase:'futura'+n,norm:'n',literal:'<literal>'+n,archivo:'archivo'+n,pagina_nro:n,origen:'fuente'+n,confianza:.31};
   const p={clase:'futura'+n,norm:'n',literales:['<literal>'+n],veces:n,motivo:'Motivo'+n};
   global._mockApiResult = { total: 1, clases: [{clave:'futura'+n,que_es:'Clase inventada'+n}], sin_resolver_paginacion: {total:1}, propuestas_paginacion: {total:1} };
   
   global.location.hash = '#/entidades';
   await vEntidades();
   assert.ok(vista.innerHTML.includes('Clase inventada'+n));
   assert.ok(global._opts.entidades.vacio.includes('No hay fichas'));
   
   global.location.hash = '#/entidades?ver=propuestas';
   await vEntidades();
   const rowP = global._cols.propuestas.map(c => c.r(p)).join('');
   for(const x of ['Decidir', '&lt;literal&gt;'+n]) assert.ok(rowP.includes(x), x);
   assert.ok(!rowP.includes('name="nombre" value='));
   
   global.location.hash = '#/entidades?ver=sin-resolver';
   await vEntidades();
   const rowM = global._cols.sin_resolver.map(c => c.r(m)).join('');
   assert.ok(rowM.includes('archivo'+n));
   
   assert.ok(htmlTiposRelacion([{clave:'tipo'+n,que_dice:'Tipo inventado'+n}]).includes('Tipo inventado'+n));
   const r={id:n,tipo:'tipo'+n,que_dice:'afirma'+n,fuente:'fuente'+n,confianza:.62,hacia:'llega'};
   assert.ok(htmlRelaciones([r]).includes('revision-propuesta'));
   assert.ok(htmlRelaciones([{...r,estado:'confirmada',quien:'autor'}]).includes('revision-confirmada'));
   for(const estado of ['propuesta','confirmada','rechazada']) assert.ok(htmlRelaciones([{...r,estado}]).includes('Fuente: fuente'+n));
   assert.ok(htmlEntidad({nombre:'N',menciones:[m,{...m,literal:'Otra forma'}]}).includes('Otra forma'));
  }
})();
""")
