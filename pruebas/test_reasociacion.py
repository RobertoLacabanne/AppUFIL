"""Las decisiones desplazadas sólo se aplican al destino elegido y dejan rastro."""
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

from ufil import config, db, reasociacion as rs
from ufil.db import ahora

RAIZ = Path(__file__).resolve().parents[1]


def sembrar(cx):
    cx.execute("INSERT INTO archivo (sha256,ruta_original,nombre,bytes,paginas,ingerido_en) VALUES ('s','/s.pdf','muestra.pdf',1,8,?)", (ahora(),))
    docs = []
    for orden, desde, hasta, tipo in [(1, 1, 2, 'otro'), (2, 3, 4, 'tipo_previo'), (3, 5, 6, 'otro'), (4, 7, 8, 'tipo_previo')]:
        d = cx.execute("INSERT INTO documento (sha256,orden,pagina_desde,pagina_hasta,tipo,perfil) VALUES ('s',?,?,?,?,'prueba')", (orden, desde, hasta, tipo)).lastrowid
        docs.append(d)
        if orden != 4:
            cx.execute("""INSERT INTO campo (documento_id,nombre,valor_literal,pagina_nro,x0,y0,x1,y1,estado)
                VALUES (?,'referencia',?,?,10,20,100,40,'automatico_alta')""", (d, f'lectura {orden}', desde))
    cx.execute("""INSERT INTO revision_humana (sha256,orden,campo,accion,valor,quien,cuando,
        ancla_pagina,ancla_desde,ancla_hasta,ancla_tipo,estado,motivo)
        VALUES ('s',9,'referencia','corregir','decisión conservada','original',?,5,5,8,
        'tipo_previo','requiere_reasociacion','La segmentación cambió')""", (ahora(),))
    cx.commit()
    return docs


class Resolucion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=RAIZ)
        self.addCleanup(self.tmp.cleanup)
        self.cx = db.abrir(Path(self.tmp.name) / 'base.sqlite')
        self.addCleanup(self.cx.close)
        self.docs = sembrar(self.cx)

    def resolver(self, accion, **kw):
        return rs.resolver(self.cx, 's', 9, 'referencia', accion, 'resolutor', **kw)

    def revision(self):
        return dict(self.cx.execute('SELECT * FROM revision_humana').fetchone())

    def campos(self):
        return [dict(r) for r in self.cx.execute('SELECT * FROM campo ORDER BY id')]

    def test_pendientes_con_candidatas_ordenadas_incluso_sin_campo(self):
        antes = list(self.cx.iterdump())
        r, = rs.pendientes(self.cx)
        self.assertEqual(r['archivo'], 'muestra.pdf')
        self.assertEqual(r['motivo'], 'La segmentación cambió')
        self.assertEqual([c['orden'] for c in r['candidatas']], [3, 2, 4, 1])
        self.assertIn('foja anclada', r['candidatas'][0]['por_que'])
        self.assertFalse(r['candidatas'][2]['tiene_el_campo'])
        self.assertIsNone(r['candidatas'][2]['valor_actual'])
        self.assertEqual(list(self.cx.iterdump()), antes)

    def test_reasociar_aplica_solo_en_destino_y_muda_anclaje(self):
        antes = self.campos()
        origen = self.revision()
        with patch.object(rs.aplicar_revision, 'aplicar', wraps=rs.aplicar_revision.aplicar) as aplicar:
            resultado = self.resolver('reasociar', documento_id=self.docs[1])
        self.assertFalse(aplicar.call_args.kwargs['registrar'])
        self.assertEqual(resultado['estado'], 'vigente')
        despues = self.campos()
        self.assertEqual(despues[0], antes[0])
        self.assertEqual(despues[2], antes[2])
        self.assertEqual(despues[1]['valor_literal'], origen['valor'])
        self.assertEqual(despues[1]['estado'], 'corregido')
        r = self.revision()
        self.assertEqual((r['orden'], r['ancla_pagina'], r['ancla_desde'], r['ancla_hasta'], r['ancla_tipo']), (2, 3, 3, 4, 'tipo_previo'))
        self.assertEqual([r['ancla_' + k] for k in ('x0', 'y0', 'x1', 'y1')], [10, 20, 100, 40])
        self.assertEqual((r['quien'], r['cuando']), (origen['quien'], origen['cuando']))
        self.assertIsNone(r['motivo'])
        self.assertEqual(rs.pendientes(self.cx), [])
        self.assertEqual([r[0] for r in self.cx.execute('SELECT accion FROM auditoria ORDER BY id')], ['corregir', 'reasociar'])
        otra = db.abrir(Path(self.tmp.name) / 'base.sqlite')
        try:
            self.assertEqual(otra.execute('SELECT estado FROM revision_humana').fetchone()[0], 'vigente')
        finally:
            otra.close()

    def test_descartar_conserva_revision_sin_aplicar_y_audita(self):
        campos, r = self.campos(), self.revision()
        self.resolver('descartar')
        self.assertEqual(self.campos(), campos)
        r['estado'] = 'descartada'
        self.assertEqual(self.revision(), r)
        self.assertEqual(rs.pendientes(self.cx), [])
        a = self.cx.execute('SELECT * FROM auditoria').fetchone()
        self.assertEqual((a['accion'], a['estado_nuevo'], a['quien']), ('descartar', 'descartada', 'resolutor'))
        self.assertIsNone(a['campo_id'])

    def test_pendiente_no_cambia_revision_ni_campos_pero_audita(self):
        campos, r = self.campos(), self.revision()
        self.resolver('pendiente')
        self.assertEqual(self.campos(), campos)
        self.assertEqual(self.revision(), r)
        a = self.cx.execute('SELECT * FROM auditoria').fetchone()
        self.assertEqual((a['accion'], a['estado_anterior'], a['estado_nuevo']), ('pendiente', r['estado'], r['estado']))
        self.assertIsNone(a['campo_id'])

    def test_no_se_pisa_otra_revision_en_el_destino(self):
        self.cx.execute("INSERT INTO revision_humana (sha256,orden,campo,accion,quien,cuando) VALUES ('s',2,'referencia','ausente','otra',?)", (ahora(),))
        self.cx.commit()
        antes = list(self.cx.iterdump())
        with self.assertRaisesRegex(ValueError, 'ya tiene una revisión'):
            self.resolver('reasociar', documento_id=self.docs[1])
        self.assertEqual(list(self.cx.iterdump()), antes)

    def test_destinos_invalidos_no_escriben(self):
        self.cx.execute("INSERT INTO archivo (sha256,ruta_original,nombre,bytes,paginas,ingerido_en) VALUES ('ajeno','/ajeno','ajeno',1,1,?)", (ahora(),))
        ajeno = self.cx.execute("INSERT INTO documento (sha256,orden,tipo,perfil) VALUES ('ajeno',1,'otro','prueba')").lastrowid
        self.cx.commit()
        for destino in (None, True, '2', 99999, ajeno, self.docs[3]):
            with self.subTest(destino=destino):
                antes = list(self.cx.iterdump())
                with self.assertRaises(ValueError):
                    self.resolver('reasociar', documento_id=destino)
                self.assertEqual(list(self.cx.iterdump()), antes)

    def test_no_se_resuelve_dos_veces(self):
        self.resolver('descartar')
        with self.assertRaisesRegex(ValueError, 'ya fue resuelta'):
            self.resolver('reasociar', documento_id=self.docs[0])

    def test_error_de_auditoria_revierte_incluso_la_aplicacion(self):
        self.cx.execute("""CREATE TEMP TRIGGER impedir_auditoria BEFORE INSERT ON auditoria
            WHEN NEW.accion='reasociar' BEGIN SELECT RAISE(ABORT,'prueba de rollback'); END""")
        antes = list(self.cx.iterdump())
        with self.assertRaisesRegex(Exception, 'prueba de rollback'):
            self.resolver('reasociar', documento_id=self.docs[1])
        self.assertEqual(list(self.cx.iterdump()), antes)

    def test_error_de_valor_no_deja_cambios_parciales(self):
        self.cx.execute("UPDATE revision_humana SET valor='' ")
        self.cx.commit()
        antes = list(self.cx.iterdump())
        with self.assertRaises(ValueError):
            self.resolver('reasociar', documento_id=self.docs[1])
        self.assertEqual(list(self.cx.iterdump()), antes)

    def test_accion_y_revisor_obligatorios(self):
        for accion, quien in [('borrar', 'persona'), ('pendiente', ''), ('descartar', None)]:
            with self.subTest(accion=accion, quien=quien):
                with self.assertRaises(ValueError):
                    rs.resolver(self.cx, 's', 9, 'referencia', accion, quien)
        self.assertEqual(self.cx.execute('SELECT COUNT(*) FROM auditoria').fetchone()[0], 0)


class ContratoHTTP(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=RAIZ)
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name) / 'base.sqlite'
        cx = db.abrir(self.base)
        try:
            self.docs = sembrar(cx)
        finally:
            cx.close()
        from ufil import servidor
        self.s = servidor
        self.previo = servidor.RUTA_BASE, servidor.PORTERIA, config.legajo_activo()
        self.addCleanup(self.restaurar)
        config.activar_legajo(None)
        p = patch.dict(os.environ, {'UFIL_ACCESO': 'abierto'})
        p.start()
        self.addCleanup(p.stop)
        self.srv = servidor.armar(0, base=self.base)
        self.hilo = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.hilo.start()
        self.addCleanup(self.cerrar)

    def restaurar(self):
        self.s.RUTA_BASE, self.s.PORTERIA, activo = self.previo
        config.activar_legajo(activo)

    def cerrar(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.hilo.join(5)

    def pedir(self, ruta, cuerpo=None):
        c = http.client.HTTPConnection('127.0.0.1', self.srv.server_address[1], timeout=10)
        try:
            c.request('GET' if cuerpo is None else 'POST', ruta,
                      None if cuerpo is None else json.dumps(cuerpo), {'Content-Type': 'application/json'})
            r = c.getresponse()
            return r.status, json.loads(r.read())
        finally:
            c.close()

    def cuerpo(self, accion):
        return dict(sha256='s', orden=9, campo='referencia', accion=accion, quien='http', documento_id=self.docs[1])

    def test_get_y_post_reasociar(self):
        status, r = self.pedir('/api/reasociaciones/pendientes')
        self.assertEqual(status, 200)
        self.assertEqual(len(r['revisiones'][0]['candidatas']), 4)
        status, corto = self.pedir('/api/reasociaciones')
        self.assertEqual(status, 200)
        self.assertNotIn('candidatas', corto['revisiones'][0])
        status, r = self.pedir('/api/reasociacion/resolver', self.cuerpo('reasociar'))
        self.assertEqual((status, r['estado'], r['orden']), (200, 'vigente', 2))
        estado, r = self.pedir('/api/reasociaciones/pendientes')
        self.assertEqual((estado, r['revisiones'], r['total']), (200, [], 0))

    def test_post_pendiente_y_descartar(self):
        for accion, estado in [('pendiente', 'requiere_reasociacion'), ('descartar', 'descartada')]:
            status, r = self.pedir('/api/reasociacion/resolver', self.cuerpo(accion))
            self.assertEqual((status, r['estado']), (200, estado))
        cx = db.abrir(self.base)
        try:
            self.assertEqual([r[0] for r in cx.execute('SELECT accion FROM auditoria ORDER BY id')], ['pendiente', 'descartar'])
        finally:
            cx.close()

    def test_post_invalido_devuelve_400(self):
        for cuerpo in ({}, self.cuerpo('invalida'), dict(self.cuerpo('reasociar'), documento_id=None), dict(self.cuerpo('pendiente'), quien='')):
            status, r = self.pedir('/api/reasociacion/resolver', cuerpo)
            self.assertEqual(status, 400)
            self.assertIn('error', r)


@unittest.skipUnless(shutil.which('node'), 'Requiere Node para ejecutar el render')
class Pantalla(unittest.TestCase):
    def test_render_sin_preseleccion_con_datos_variables_y_escape(self):
        js = (RAIZ / 'ufil/web/app.js').read_text(encoding='utf-8')
        render = js[js.index('function htmlReasociaciones('):js.index('async function vReasociaciones(')]
        script = r"""
const assert = require('node:assert/strict');
const esc = s => String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const vacio = (titulo, texto) => titulo + texto;
const fmtFechaHora = v => v;
const ESTADO = {};
""" + render + r"""
assert.ok(htmlReasociaciones([]).includes('No hay revisiones desplazadas'));
assert.ok(!htmlReasociaciones([]).includes('button'));
for (const n of [17, 29]) {
 const r = {sha256:'s',archivo:'<archivo>'+n,accion:'corregir',campo:'dato_'+n,valor:'<script>',quien:'persona '+n,cuando:'fecha '+n,
 ancla_pagina:n,ancla_tipo:'tipo_'+n,ancla_desde:n,ancla_hasta:n+1,orden:n,motivo:'motivo '+n,
 candidatas:[{documento_id:n,orden:n,tipo:'nuevo_'+n,pagina_desde:n,pagina_hasta:n+1,tiene_el_campo:true,
 valor_actual:'lectura '+n,estado_actual:'estado_'+n,por_que:'razon '+n},
 {documento_id:n+1,orden:n+1,tipo:'sin_campo',pagina_desde:n,pagina_hasta:n,tiene_el_campo:false,por_que:'otra razon'}]};
 const h = htmlReasociaciones([r]);
 for (const texto of ['&lt;archivo&gt;'+n,'persona '+n,'fecha '+n,'motivo '+n,'lectura '+n,'razon '+n,'nuevo '+n,'data-resolver="pendiente"','data-resolver="descartar"']) assert.ok(h.includes(texto),texto);
 assert.ok(!h.includes('<script>'));
 assert.ok(!h.includes('checked'));
 assert.match(h, /data-resolver="reasociar" disabled/);
 assert.ok(h.includes('se puede auditar'));
 r.candidatas=[];
 assert.ok(htmlReasociaciones([r]).includes('No hay piezas candidatas'));
 assert.ok(!htmlReasociaciones([r]).includes('data-resolver="reasociar"'));
}
"""
        r = subprocess.run(['node', '-e', script], cwd=RAIZ, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == '__main__':
    unittest.main()
