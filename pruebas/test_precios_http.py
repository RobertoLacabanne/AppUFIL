"""Contrato HTTP de 7a y compatibilidad de las claves que consume la interfaz."""
from contextlib import closing
import json
import os
import stat
import unittest
from pathlib import Path

from pruebas import test_nucleo_web as soporte
from pruebas.test_renglones_precios import cargar, derivar, vincular
from ufil import comparabilidad as cp, db


class PreciosHTTP(unittest.TestCase):
    def setUp(self):
        soporte.NucleoPorHTTP.setUp(self)
        # La ingesta marca los originales sólo lectura. Son PDFs sintéticos que
        # esta prueba creó; liberar ese atributo permite el cleanup en Windows.
        self.addCleanup(self.liberar_originales)

    def liberar_originales(self):
        raiz = self.temporal.resolve()
        for ruta in self.temporal.rglob('*.pdf'):
            if ruta.resolve().is_relative_to(raiz):
                os.chmod(ruta, stat.S_IWRITE | stat.S_IREAD)
    restaurar_config = soporte.NucleoPorHTTP.restaurar_config
    restaurar_servidor = soporte.NucleoPorHTTP.restaurar_servidor
    cerrar = soporte.NucleoPorHTTP.cerrar
    pedir = soporte.NucleoPorHTTP.pedir

    def cargar(self):
        with closing(db.abrir(self.base)) as cx:
            try:
                cargar(cx, self.temporal / 'corpus')
                derivar(cx)
                vincular(cx)
                rid = cx.execute("SELECT id FROM renglon WHERE etapa='factura' AND fila=1").fetchone()[0]
                cx.execute("UPDATE renglon SET moneda='ARS',iva='incluido' WHERE id=?", (rid,))
                cx.commit()
                return rid
            finally:
                cx.close()

    def forma(self, ejemplo, real, ruta=''):
        # Los fixtures omitieron campos obligatorios de Fuente y Monto de §7.
        # Se exige igualdad de claves en lo demás y presencia/tipo de cada clave
        # del fixture; sólo se admiten esas extensiones documentadas por el contrato.
        if ejemplo is None or real is None:
            return  # Campos nullable en §9.
        if isinstance(ejemplo, dict):
            self.assertIsInstance(real, dict, ruta)
            extras = (set(real) - set(ejemplo))
            permitidas = ({'literal', 'derivado', 'formula', 'ausencia'} if ruta.endswith('precio_unitario') else
                          {'ausencia'} if ruta.endswith('subtotal') else
                          {'comparabilidad'} if ruta.endswith('comparacion') else
                          {'tipo_documento', 'celdas', 'campo_id'} if ruta.endswith('fuente') else
                          {'orden', 'sentido', 'filtros_aplicados', 'referencias_paginacion', 'excluidas_paginacion'} if ruta == '' else set())
            self.assertTrue(extras <= permitidas, (ruta, extras))
            self.assertTrue(set(ejemplo) <= set(real), ruta)
            for k, v in ejemplo.items():
                self.forma(v, real[k], ruta + '.' + k)
        elif isinstance(ejemplo, list):
            self.assertIsInstance(real, list, ruta)
            if ejemplo and real:
                self.forma(ejemplo[0], real[0], ruta + '[]')
        elif isinstance(ejemplo, (int, float)) and not isinstance(ejemplo, bool):
            self.assertIsInstance(real, (int, float), ruta)
        else:
            self.assertIsInstance(real, type(ejemplo), ruta)

    def test_api_y_fixtures_de_la_interfaz(self):
        rid = self.cargar()
        fixtures = Path(__file__).parent / 'fixtures' / 'contrataciones'
        estado, catalogo = self.pedir('/api/catalogo/contrataciones')
        self.assertEqual((estado, catalogo), (200, cp.catalogo()))
        for nombre, ruta in [('precios', '/api/precios?etapa=factura'),
                             ('renglon_1', f'/api/renglon/{rid}/comparacion')]:
            estado, real = self.pedir(ruta)
            self.assertEqual(estado, 200, real)
            self.forma(json.loads((fixtures / (nombre + '.json')).read_text(encoding='utf-8')), real)
        estado, decision = self.pedir(f'/api/renglon/{rid}/item',
                                     {'decision': 'mismo', 'crear': {'nombre': 'Revisado'}, 'quien': 'test'}, 'POST')
        self.assertEqual(estado, 200, decision)
        self.assertEqual(decision['quien'], 'test')
        with closing(db.abrir(self.base)) as cx:
            try:
                derivar(cx)
            finally:
                cx.close()
        estado, real = self.pedir(f'/api/renglon/{rid}/comparacion')
        self.assertEqual(real['renglon']['item']['id'], decision['item_id'])

    def test_errores_de_cliente_tienen_estado_y_motivo(self):
        rid = self.cargar()
        self.assertEqual(self.pedir('/api/renglon/999999/comparacion')[0], 404)
        for ruta in ['/api/precios?limite=no', '/api/precios?desde=-1', f'/api/renglon/{rid}/comparacion?niveles=Z']:
            estado, r = self.pedir(ruta)
            self.assertEqual(estado, 400, r)
            self.assertTrue(r['error'])
        self.assertEqual(self.pedir(f'/api/renglon/{rid}/item', {'decision': 'mismo'}, 'POST')[0], 400)

    def test_subir_procesar_y_actualizar_con_el_pipeline_real(self):
        from pruebas.test_aceptacion_contratacion import UnaContratacionDePuntaAPunta as flujo
        from pruebas.corpus_contratacion import generar
        for ruta in generar(self.temporal / 'entrada').values():
            self.assertEqual(flujo.subir(self, ruta)[0], 200)
        self.assertEqual(self.pedir('/api/procesar', {}, 'POST')[0], 200)
        flujo.esperar_trabajo(self)
        estado, r = self.pedir('/api/precios?limite=500')
        self.assertEqual(estado, 200, r)
        self.assertEqual(r['total'], 33)
        self.assertEqual(self.pedir('/api/actualizar', {}, 'POST')[0], 200)
        flujo.esperar_trabajo(self)
        self.assertEqual(self.pedir('/api/precios?etapa=factura')[1]['total'], 3)
