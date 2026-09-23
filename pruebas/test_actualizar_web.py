"""Contrato HTTP y render real del plan, con datos sintéticos variables."""
import http.client
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from ufil import actualizacion as ac, config, db, legajos
from ufil.db import ahora

RAIZ = Path(__file__).resolve().parents[1]


class ActualizarPorHTTP(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=RAIZ)
        self.addCleanup(self.tmp.cleanup)
        self.datos = config.DATOS
        self.activo = config.legajo_activo()
        config.DATOS = Path(self.tmp.name)
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
        self.srv = servidor.armar(0, base=Path(self.tmp.name) / 'suelta.sqlite')
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
            cx.execute("INSERT INTO archivo (sha256,ruta_original,nombre,bytes,paginas,ingerido_en) VALUES ('s','/s.pdf','muestra.pdf',1,1,?)", (ahora(),))
            p = cx.execute("INSERT INTO pagina (sha256,nro,ancho_pt,alto_pt) VALUES ('s',1,100,100)").lastrowid
            cx.execute("INSERT INTO lectura (pagina_id,ruta,motor,version,confianza,ms,creado_en) VALUES (?,'ocr_a','sintetico','1',0.9,1,?)", (p, ahora()))
            cx.commit()
        finally:
            cx.close()

    def test_base_vacia_devuelve_el_plan_sin_material(self):
        estado, r = self.pedir('/api/actualizacion')
        self.assertEqual(estado, 200)
        cx = db.abrir(self.base)
        try:
            self.assertEqual(r, ac.plan(cx))
        finally:
            cx.close()
        self.assertEqual(r['archivos'], [])
        self.assertEqual(r['reutiliza']['paginas_ocr'], 0)
        self.assertEqual(r['recalcula']['archivos'], 0)
        self.assertTrue(all(e['total'] == 0 for e in r['etapas'] if e['alcance'] != 'legajo'))

    def test_informa_herencia_recalculo_y_motivo_sin_escribir(self):
        self.sembrar()
        cx = db.abrir(self.base)
        try:
            antes = list(cx.iterdump())
            esperado = ac.plan(cx)
            estado, r = self.pedir('/api/actualizacion')
            self.assertEqual((estado, r), (200, esperado))
            self.assertEqual(list(cx.iterdump()), antes)
        finally:
            cx.close()
        self.assertEqual(r['reutiliza']['paginas_ocr'], 1)
        self.assertEqual(r['recalcula']['paginas_ocr'], 0)
        self.assertTrue(any(e['desactualizados'] and e['motivo'] for e in r['etapas']))
        self.assertTrue(any(e['estado'] == 'heredada' for e in r['etapas']))

    def test_arranca_un_hilo_y_publica_su_progreso(self):
        entro, liberar = threading.Event(), threading.Event()
        def aplicar(cx, **opciones):
            opciones['avance'](2, 7)
            entro.set()
            if not liberar.wait(10):
                raise RuntimeError('No se liberó la prueba')
            return {'errores': []}
        with patch.object(ac, 'aplicar', side_effect=aplicar) as trabajo:
            try:
                self.assertEqual(self.pedir('/api/actualizar', {'forzar': ['lectura']}, 'POST'), (200, {'ok': True}))
                self.assertTrue(entro.wait(5))
                estado, r = self.pedir('/api/trabajo')
                self.assertEqual((estado, r['estado'], r['hecho'], r['total']), (200, 'corriendo', 2, 7))
                self.assertEqual(trabajo.call_args.kwargs['forzar'], ('lectura',))
                self.assertFalse(self.pedir('/api/actualizar', {}, 'POST')[1]['ok'])
            finally:
                liberar.set()
                self.servidor._PROCESADORES[self.legajo.slug]._hilo.join(5)
        self.assertEqual(self.pedir('/api/trabajo')[1]['estado'], 'terminado')

    def test_actualiza_base_vacia_sin_simular_el_motor(self):
        self.assertEqual(self.pedir('/api/actualizar', metodo='POST'), (200, {'ok': True}))
        self.servidor._PROCESADORES[self.legajo.slug]._hilo.join(10)
        self.assertEqual(self.pedir('/api/trabajo')[1]['estado'], 'terminado')

    def test_rechaza_forzar_invalido(self):
        for valor in ('lectura', ['no_existe'], [42]):
            with self.subTest(valor=valor):
                self.assertEqual(self.pedir('/api/actualizar', {'forzar': valor}, 'POST')[0], 400)

    def test_reasociaciones_son_trabajo_conservado(self):
        self.sembrar()
        cx = db.abrir(self.base)
        try:
            cx.execute("""INSERT INTO revision_humana
                (sha256,orden,campo,accion,valor,quien,cuando,estado,motivo)
                VALUES ('s',1,'campo_prueba','corregir','dato humano','persona',?,
                'requiere_reasociacion','No hay anclaje seguro')""", (ahora(),))
            cx.commit()
            esperado = ac.reasociaciones(cx)
        finally:
            cx.close()
        estado, r = self.pedir('/api/reasociaciones')
        self.assertEqual((estado, r['revisiones']), (200, esperado))
        self.assertEqual((r['total'],r['desde'],r['limite']), (1,0,50))
        self.assertEqual(esperado[0]['valor'], 'dato humano')


@unittest.skipUnless(shutil.which('node'), 'El render JavaScript requiere Node')
class PantallaDesdeJSON(unittest.TestCase):
    def test_render_dinamico_vigente_heredado_y_escape(self):
        # Ejecuta la misma función usada por la pantalla, no una traducción en Python.
        js = (RAIZ / 'ufil/web/app.js').read_text(encoding='utf-8')
        render = js[js.index('function htmlActualizacion('):js.index('async function vActualizacion(')]
        script = r"""
const assert = require('node:assert/strict');
const fmtNum = new Intl.NumberFormat('es-AR');
const esc = s => String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
""" + render + r"""
for (const n of [13, 27, 91]) {
  const p = {vigente:false, etapas:[{clave:'futura',nombre:'Etapa futura '+n,
    estado:'heredada',motivo:'Motivo variable '+n,alcance:'pagina',vigentes:n,
    desactualizados:n+1,total:n+2,heredados:n,cuesta:'caro'}],
    reutiliza:{paginas_ocr:n,lecturas:n+3},recalcula:{paginas_ocr:n+4,archivos:n+5,documentos:n+6,indice:true},
    revisiones:{total:n+7,preservadas:n+8,requieren_reasociacion:n+9},
    archivos:[{nombre:'<archivo>'+n,paginas:n+10,desactualizadas:['futura']}]};
  const html = htmlActualizacion(p,[{archivo:'Revision '+n,campo:'Campo '+n,valor:'<script>',quien:'Persona '+n,cuando:'Fecha '+n,motivo:'Anclaje '+n}]);
  for (let k=0;k<=10;k++) assert.ok(html.includes(String(n+k)));
  for (const texto of ['Etapa futura '+n,'Motivo variable '+n,'&lt;archivo&gt;'+n,'Revision '+n,'Anclaje '+n,'heredados aprovechables','Se reutiliza','Se recalcula','b-actualizar']) assert.ok(html.includes(texto),texto);
  assert.ok(!html.includes('<script>'));
  p.vigente=true;
  assert.ok(!htmlActualizacion(p,[]).includes('b-actualizar'));
  p.vigente=false; p.etapas[0].total=0;
  assert.ok(htmlActualizacion(p,[]).includes('No hay material'));
  assert.ok(!htmlActualizacion(p,[]).includes('b-actualizar'));
}
"""
        r = subprocess.run(['node', '-e', script], cwd=RAIZ, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == '__main__':
    unittest.main()
