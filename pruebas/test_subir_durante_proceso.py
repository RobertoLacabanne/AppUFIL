"""C8: cargas concurrentes y exclusión real, con PDF sintéticos y eventos."""
from contextlib import contextmanager
import hashlib
import http.client
import json
import queue
import subprocess
import sys
import os
from pathlib import Path
import shutil
import sqlite3
import threading
import unittest
import uuid
from unittest.mock import patch

import fitz

from pruebas import test_nucleo_web as soporte
from ufil import almacen, actualizacion, capa0_ingesta, capa1_texto, config, db, trabajo
from ufil import exclusion, papelera, respaldo


def pdf_sintetico(texto):
    with fitz.open() as pdf:
        pdf.new_page().insert_text((50, 50), 'SINTETICO ' + texto * 8)
        return pdf.tobytes()


def habilitar_limpieza(raiz):
    for ruta in raiz.rglob('*.pdf'):
        ruta.chmod(0o666)


@contextmanager
def tarea_pausada(test, objeto, nombre, tarea):
    """Pausa dentro de una operación real; propaga también errores de su hilo."""
    entro, soltar = threading.Event(), threading.Event()
    errores = []
    original = getattr(objeto, nombre)

    def pausa(*args, **kwargs):
        entro.set()
        if not soltar.wait(20):
            raise AssertionError('No se liberó la operación de prueba')
        return original(*args, **kwargs)

    def correr():
        try:
            tarea()
        except BaseException as e:
            errores.append(e)
            entro.set()

    with patch.object(objeto, nombre, side_effect=pausa):
        hilo = threading.Thread(target=correr)
        hilo.start()
        try:
            test.assertTrue(entro.wait(15))
            test.assertEqual(errores, [])
            yield
        finally:
            soltar.set()
            hilo.join(20)
            test.assertFalse(hilo.is_alive())
            test.assertEqual(errores, [])


def sostener_en_proceso(base, modo):
    """Entrada spawn, también en Windows: los locks no se heredan del padre."""
    try:
        if modo in ('pipeline', 'actualizacion'):
            config.activar_legajo(None)
            config.DERIVADOS = Path(base).parent / 'derivados'
            original = capa1_texto.leer_lote

            def pausa(*args, **kwargs):
                print('listo', flush=True)
                input()
                return original(*args, **kwargs)

            p = trabajo.Procesador(base)
            with patch.object(capa1_texto, 'leer_lote', side_effect=pausa):
                if modo == 'pipeline':
                    p._correr('auto', False)
                else:
                    p._correr_actualizacion((), 'auto', False)
            print(p.estado.estado, flush=True)
        else:
            with getattr(exclusion, modo)(base):
                print('listo', flush=True)
                input()
    except BaseException as e:
        print(repr(e), flush=True)
        raise


@contextmanager
def proceso_pausado(test, base, modo):
    p = subprocess.Popen(
        [sys.executable, '-u', '-c',
         'from pruebas.test_subir_durante_proceso import sostener_en_proceso; '
         'import sys; sostener_en_proceso(sys.argv[1], sys.argv[2])', str(base), modo],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding='utf-8')
    salida = queue.Queue()
    lector = threading.Thread(target=lambda: salida.put(p.stdout.readline()), daemon=True)
    lector.start()
    try:
        test.assertEqual(salida.get(timeout=15).strip(), 'listo')
        yield p
    finally:
        if p.poll() is None:
            p.stdin.write('soltar\n')
            p.stdin.flush()
        try:
            resto, _ = p.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            p.kill()
            resto, _ = p.communicate(timeout=5)
            test.fail('El proceso no terminó: ' + resto)
        lector.join(5)
        if modo in ('pipeline', 'actualizacion'):
            test.assertEqual(p.returncode, 0, resto)
            test.assertIn('terminado', resto)


@contextmanager
def lectura_pausada(test, procesador, actualizar=False):
    entro, soltar = threading.Event(), threading.Event()
    original = capa1_texto.leer_lote

    def leer(*args, **kwargs):
        entro.set()
        if not soltar.wait(20):
            raise AssertionError('No se liberó la lectura de prueba')
        return original(*args, **kwargs)

    with patch.object(capa1_texto, 'leer_lote', side_effect=leer):
        test.assertTrue((procesador.actualizar() if actualizar else procesador.arrancar())['ok'])
        try:
            test.assertTrue(entro.wait(15), procesador.estado.como_dict())
            yield
        finally:
            soltar.set()
            procesador._hilo.join(20)
            test.assertFalse(procesador._hilo.is_alive())


class CargasDuranteProceso(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(__file__).resolve().parents[1] / ('c8-' + uuid.uuid4().hex)
        self.raiz.mkdir()
        self.addCleanup(shutil.rmtree, self.raiz)
        self.addCleanup(habilitar_limpieza, self.raiz)
        self.base = self.raiz / 'ufil.sqlite'
        activo = config.legajo_activo()
        config.activar_legajo(None)
        self.addCleanup(config.activar_legajo, activo)
        entorno = patch.dict(os.environ, {'UFIL_ORIGINALES': str(self.raiz / 'originales')})
        entorno.start()
        self.addCleanup(entorno.stop)
        derivados = patch.object(config, 'DERIVADOS', self.raiz / 'derivados')
        derivados.start()
        self.addCleanup(derivados.stop)
        self.cx = db.abrir(self.base)
        self.addCleanup(self.cx.close)

    def comprobar_carga(self, actualizar=False, ingerir=False):
        viejo = almacen.guardar(self.cx, pdf_sintetico('Inicial '), 'inicial.pdf', lote='a')
        nuevo = pdf_sintetico('Agregado ')
        sha = hashlib.sha256(nuevo).hexdigest()
        p = trabajo.Procesador(self.base)
        with lectura_pausada(self, p, actualizar):
            if ingerir:
                origen = self.raiz / 'entrada'
                origen.mkdir()
                (origen / 'nuevo.pdf').write_bytes(nuevo)
                self.assertEqual(capa0_ingesta.ingerir(self.cx, origen, lote='b').nuevos, 1)
            else:
                g = almacen.guardar(self.cx, nuevo, 'nuevo.pdf', lote='b')
                self.assertEqual(g.sha256, sha)
                self.assertEqual(g.ruta.read_bytes(), nuevo)
            self.assertTrue(p.ocupado())
        self.assertEqual(p.estado.estado, 'terminado', p.estado.como_dict())
        self.assertEqual(p.estado.errores, [])
        self.assertGreater(self.cx.execute('SELECT COUNT(*) FROM lectura l JOIN pagina p '
                                         'ON p.id=l.pagina_id WHERE p.sha256=?', (viejo.sha256,)).fetchone()[0], 0)
        self.assertEqual(self.cx.execute('SELECT COUNT(*) FROM lectura l JOIN pagina p '
                                        'ON p.id=l.pagina_id WHERE p.sha256=?', (sha,)).fetchone()[0], 0)
        self.assertEqual(self.cx.execute('SELECT COUNT(*) FROM documento WHERE sha256=?', (sha,)).fetchone()[0], 0)
        self.assertEqual(self.cx.execute('SELECT COUNT(*) FROM excepcion WHERE sha256=?', (sha,)).fetchone()[0], 0)
        self.assertTrue((p.actualizar() if actualizar else p.arrancar())['ok'])
        p._hilo.join(20)
        self.assertFalse(p._hilo.is_alive())
        self.assertEqual(p.estado.estado, 'terminado', p.estado.como_dict())
        self.assertEqual(p.estado.errores, [])
        self.assertGreater(self.cx.execute('SELECT COUNT(*) FROM lectura l JOIN pagina p '
                                         'ON p.id=l.pagina_id WHERE p.sha256=?', (sha,)).fetchone()[0], 0)
        self.assertEqual(self.cx.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(self.cx.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_guardar_durante_pipeline_y_proxima_corrida(self):
        self.comprobar_carga()

    def test_ingerir_durante_pipeline_y_proxima_corrida(self):
        self.comprobar_carga(ingerir=True)

    def test_guardar_durante_actualizacion_y_proxima_corrida(self):
        self.comprobar_carga(actualizar=True)

    def test_ingerir_durante_actualizacion_y_proxima_corrida(self):
        self.comprobar_carga(actualizar=True, ingerir=True)

    def test_carga_durante_plan_actualizacion_espera_proxima_corrida(self):
        almacen.guardar(self.cx, pdf_sintetico('Primero '), 'a.pdf', lote='a')
        p = trabajo.Procesador(self.base)
        entro, soltar = threading.Event(), threading.Event()
        original = actualizacion._unidades

        def unidades(cx, etapa):
            r = original(cx, etapa)
            if etapa == 'lectura':
                entro.set()
                if not soltar.wait(15):
                    raise AssertionError('No se liberó el plan')
            return r

        intento, termino = threading.Event(), threading.Event()
        resultado, errores = [], []

        def subir():
            cx = db.abrir(self.base)
            try:
                cx.set_trace_callback(lambda sql: intento.set() if sql.startswith('INSERT INTO archivo') else None)
                resultado.append(almacen.guardar(cx, pdf_sintetico('Durante plan '), 'b.pdf', lote='b'))
            except BaseException as e:
                errores.append(e)
            finally:
                termino.set()
                cx.close()

        carga = threading.Thread(target=subir)
        with patch.object(actualizacion, '_unidades', side_effect=unidades):
            p.actualizar()
            try:
                self.assertTrue(entro.wait(10))
                carga.start()
                self.assertTrue(intento.wait(10))
                self.assertFalse(termino.wait(0.1), 'La carga atravesó el plan a medio armar')
            finally:
                soltar.set()
                p._hilo.join(20)
                if carga.ident is not None:
                    carga.join(20)
                self.assertFalse(p._hilo.is_alive())
                self.assertFalse(carga.is_alive())
        self.assertEqual(errores, [])
        nuevo = resultado[0]
        self.assertEqual(p.estado.estado, 'terminado', p.estado.como_dict())
        self.assertEqual(p.estado.errores, [])
        self.assertEqual(self.cx.execute('SELECT COUNT(*) FROM resultado_etapa '
                                        'WHERE alcance_id=?', (nuevo.sha256,)).fetchone()[0], 0)
        self.assertEqual(self.cx.execute('SELECT COUNT(*) FROM documento WHERE sha256=?',
                                        (nuevo.sha256,)).fetchone()[0], 0)
        p.actualizar()
        p._hilo.join(20)
        self.assertFalse(p._hilo.is_alive())
        self.assertEqual(p.estado.estado, 'terminado', p.estado.como_dict())
        self.assertGreater(self.cx.execute('SELECT COUNT(*) FROM lectura l JOIN pagina p '
                                         'ON p.id=l.pagina_id WHERE p.sha256=?',
                                         (nuevo.sha256,)).fetchone()[0], 0)

    def test_carga_entre_paginas_ocr_no_espera_diez_paginas(self):
        for actualizar in (False, True):
            with self.subTest(actualizar=actualizar):
                with fitz.open() as pdf:
                    for nro in (1, 2):
                        pdf.new_page().insert_text((50, 50), f'SINTETICO página {nro} variante {actualizar} ' * 5)
                    almacen.guardar(self.cx, pdf.tobytes(), 'dos.pdf', lote='a')
                p = trabajo.Procesador(self.base)
                primera, soltar = threading.Event(), threading.Event()
                original_pagina = capa1_texto._leer_pagina
                original_lote = capa1_texto.leer_lote

                def pagina(ruta, sha, nro, *args):
                    if nro == 2 and not soltar.wait(15):
                        raise AssertionError('No se liberó la segunda página')
                    return original_pagina(ruta, sha, nro, *args)

                def lote(*args, **kwargs):
                    avance = kwargs['avance']

                    def avisar(hechas, total):
                        avance(hechas, total)
                        primera.set()

                    kwargs['avance'] = avisar
                    return original_lote(*args, **kwargs)

                with patch.object(capa1_texto, '_leer_pagina', side_effect=pagina), \
                        patch.object(capa1_texto, 'leer_lote', side_effect=lote):
                    (p.actualizar if actualizar else p.arrancar)()
                    try:
                        self.assertTrue(primera.wait(10), p.estado.como_dict())
                        self.cx.execute('PRAGMA busy_timeout=200')
                        self.assertFalse(almacen.guardar(self.cx, pdf_sintetico(f'Entre páginas {actualizar} '),
                                                        'entre.pdf', lote='b').duplicado)
                    finally:
                        soltar.set()
                        p._hilo.join(20)
                        self.cx.execute('PRAGMA busy_timeout=30000')
                self.assertFalse(p._hilo.is_alive())
                self.assertEqual(p.estado.estado, 'terminado', p.estado.como_dict())
                self.assertEqual(p.estado.errores, [])


class CargaHTTP(unittest.TestCase):
    def setUp(self):
        soporte.NucleoPorHTTP.setUp(self)
        self.addCleanup(habilitar_limpieza, self.temporal)
    restaurar_config = soporte.NucleoPorHTTP.restaurar_config
    restaurar_servidor = soporte.NucleoPorHTTP.restaurar_servidor
    cerrar = soporte.NucleoPorHTTP.cerrar
    pedir = soporte.NucleoPorHTTP.pedir

    def subir(self, datos):
        c = http.client.HTTPConnection('127.0.0.1', self.srv.server_address[1], timeout=15)
        try:
            c.request('POST', '/api/subir?nombre=sintetico.pdf&lote=c8', datos,
                      {'Content-Type': 'application/pdf', 'Cookie': f'ufil_legajo={self.legajo.slug}'})
            r = c.getresponse()
            return r.status, json.loads(r.read())
        finally:
            c.close()

    def test_subir_con_trabajador_ocupado(self):
        for actualizar in (False, True):
            with self.subTest(actualizar=actualizar):
                self.assertEqual(self.subir(pdf_sintetico(f'Inicial HTTP {actualizar} '))[0], 200)
                p = trabajo.Procesador(self.base, self.legajo.slug)
                with lectura_pausada(self, p, actualizar):
                    estado, r = self.subir(pdf_sintetico(f'Nuevo HTTP {actualizar} '))
                    self.assertEqual(estado, 200, r)
                    self.assertTrue(r['ok'])
                    self.assertFalse(r['duplicado'])
                    self.assertTrue(p.ocupado())
                self.assertEqual(p.estado.estado, 'terminado', p.estado.como_dict())

    def test_http_409_papelera_y_respaldo_en_curso(self):
        cx = db.abrir(self.base)
        copia = self.temporal / 'copia.sqlite'
        respaldo.hacer(cx, copia)
        cx.close()
        with proceso_pausado(self, self.base, 'exclusiva'):
            estado, r = self.subir(pdf_sintetico('Conflicto papelera '))
            self.assertEqual(estado, 409, r)
            self.assertIn('papelera', r['error'])
        with tarea_pausada(self, respaldo, '_copiar_sqlite',
                          lambda: respaldo.restaurar(copia, self.base)):
            estado, r = self.subir(pdf_sintetico('Conflicto respaldo '))
            self.assertEqual(estado, 409, r)
            self.assertIn('restauración de respaldo', r['error'])


class ExclusionesC8(unittest.TestCase):
    setUp = CargasDuranteProceso.setUp

    def guardar(self):
        return almacen.guardar(self.cx, pdf_sintetico('Inicial ' + uuid.uuid4().hex), 'a.pdf', lote='a').sha256

    def operaciones_papelera(self, cx, sha):
        return (lambda: papelera.quitar(cx, sha, 'QUITAR ' + sha),
                lambda: papelera.restaurar(cx, sha),
                lambda: papelera.destruir(cx, sha, 'DESTRUIR ' + sha))

    def cargas_bloqueadas(self):
        with self.assertRaisesRegex(exclusion.Ocupado, 'papelera|restauración'):
            almacen.guardar(self.cx, pdf_sintetico('Nuevo '), 'b.pdf', lote='b')
        with self.assertRaisesRegex(exclusion.Ocupado, 'papelera|restauración'):
            capa0_ingesta.ingerir(self.cx, self.raiz / 'entrada', lote='b')

    def trabajadores_bloqueados(self):
        for actualizar in (False, True):
            p = trabajo.Procesador(self.base)
            self.assertTrue((p.actualizar() if actualizar else p.arrancar())['ok'])
            p._hilo.join(5)
            self.assertFalse(p._hilo.is_alive())
            self.assertEqual(p.estado.estado, 'error')
            self.assertRegex(p.estado.mensaje, 'procesamiento|papelera|restauración')
        with self.assertRaises(exclusion.Ocupado):
            actualizacion.aplicar(self.cx)

    def test_papelera_excluye_cargas_y_trabajadores(self):
        for operacion in ('quitar', 'restaurar', 'destruir'):
            with self.subTest(operacion=operacion):
                sha = self.guardar()
                if operacion != 'quitar':
                    papelera.quitar(self.cx, sha, 'QUITAR ' + sha)

                def tarea():
                    cx = db.abrir(self.base)
                    try:
                        args = (cx, sha) if operacion == 'restaurar' else (
                            cx, sha, operacion.upper() + ' ' + sha)
                        getattr(papelera, operacion)(*args)
                    finally:
                        cx.close()

                with tarea_pausada(self, papelera, '_sha', tarea):
                    self.cargas_bloqueadas()
                    self.trabajadores_bloqueados()
                # Dejar el mismo archivo activo para la siguiente variante.
                if operacion == 'quitar':
                    papelera.restaurar(self.cx, sha)
        self.assertEqual(self.cx.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_cargas_excluyen_papelera_y_respaldo(self):
        sha = self.guardar()
        copia = self.raiz / 'copia.sqlite'
        respaldo.hacer(self.cx, copia)
        for ingerir in (False, True):
            with self.subTest(ingerir=ingerir):
                datos = pdf_sintetico(f'Carga bloqueante {ingerir} ')
                origen = self.raiz / ('entrada-' + str(ingerir))
                origen.mkdir()
                (origen / 'b.pdf').write_bytes(datos)

                def tarea():
                    cx = db.abrir(self.base)
                    try:
                        if ingerir:
                            capa0_ingesta.ingerir(cx, origen, lote='b')
                        else:
                            almacen.guardar(cx, datos, 'b.pdf', lote='b')
                    finally:
                        cx.close()

                modulo = capa0_ingesta if ingerir else almacen
                with tarea_pausada(self, modulo, '_metadatos_pdf', tarea):
                    for operacion in self.operaciones_papelera(self.cx, sha):
                        with self.assertRaises(exclusion.Ocupado):
                            operacion()
                    with self.assertRaises(exclusion.Ocupado):
                        respaldo.restaurar(copia, self.base)
                    # Cotejo y .parcial tampoco pueden competir entre dos cargas.
                    with self.assertRaisesRegex(exclusion.Ocupado, 'subida o ingesta'):
                        almacen.guardar(self.cx, datos, 'b.pdf', lote='b')
                    with self.assertRaisesRegex(exclusion.Ocupado, 'subida o ingesta'):
                        capa0_ingesta.ingerir(self.cx, origen, lote='b')

    def test_trabajadores_excluyen_papelera_y_otras_corridas(self):
        sha = self.guardar()
        for actualizar in (False, True):
            with self.subTest(actualizar=actualizar):
                # Forzar OCR para volver a detener la segunda variante.
                p = trabajo.Procesador(self.base)
                if actualizar:
                    self.guardar()
                with lectura_pausada(self, p, actualizar):
                    for operacion in self.operaciones_papelera(self.cx, sha):
                        with self.assertRaises(exclusion.Ocupado):
                            operacion()
                    self.trabajadores_bloqueados()

    def test_respaldo_impide_abrir_conexion_para_guardar_o_ingerir(self):
        self.guardar()
        copia = self.raiz / 'copia.sqlite'
        respaldo.hacer(self.cx, copia)
        self.cx.close()
        # Incluso un cliente SQLite externo que ya tenga un cx no puede saltar
        # la exclusión de guardar/ingerir mientras se está reemplazando la base.
        externa = sqlite3.connect(self.base)
        externa.row_factory = sqlite3.Row
        try:
            with tarea_pausada(self, respaldo, '_copiar_sqlite',
                              lambda: respaldo.restaurar(copia, self.base)):
                with self.assertRaisesRegex(exclusion.Ocupado, 'restauración de respaldo'):
                    db.abrir(self.base)
                with self.assertRaisesRegex(exclusion.Ocupado, 'restauración de respaldo'):
                    almacen.guardar(externa, pdf_sintetico('Respaldo '), 'b.pdf', lote='b')
                with self.assertRaisesRegex(exclusion.Ocupado, 'restauración de respaldo'):
                    capa0_ingesta.ingerir(externa, self.raiz, lote='b')
                externa.close()
        finally:
            externa.close()
        self.cx = db.abrir(self.base)
        self.addCleanup(self.cx.close)
        self.assertEqual(self.cx.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_corridas_entre_procesos_permiten_carga_y_excluyen_competidores(self):
        sha = self.guardar()
        for modo in ('pipeline', 'actualizacion'):
            with self.subTest(modo=modo):
                if modo == 'actualizacion':
                    self.guardar()
                with proceso_pausado(self, self.base, modo):
                    self.trabajadores_bloqueados()
                    for operacion in self.operaciones_papelera(self.cx, sha):
                        with self.assertRaises(exclusion.Ocupado):
                            operacion()
                    self.assertFalse(almacen.guardar(self.cx, pdf_sintetico(modo),
                                                     'nuevo.pdf', lote='b').duplicado)

    def test_locks_liberados_al_morir_proceso(self):
        for modo in ('procesamiento', 'carga', 'exclusiva'):
            with self.subTest(modo=modo):
                with proceso_pausado(self, self.base, modo) as p:
                    with self.assertRaises(exclusion.Ocupado):
                        with exclusion.exclusiva(self.base):
                            pass
                    p.terminate()
                    p.wait(timeout=5)
                    self.assertIsNotNone(p.poll())
                    # Probar todos los niveles después de terminar sin finally.
                    with exclusion.exclusiva(self.base):
                        pass
                    with exclusion.procesamiento(self.base), exclusion.carga(self.base):
                        pass

    def test_reentrada_por_hilo_sin_promover_compartido_a_exclusivo(self):
        for cerrojo in (exclusion.exclusiva, exclusion.procesamiento, exclusion.carga):
            with self.subTest(cerrojo=cerrojo.__name__):
                with cerrojo(self.base), cerrojo(self.base):
                    pass
        with exclusion.exclusiva(self.base), exclusion.carga(self.base):
            pass
        with exclusion.procesamiento(self.base):
            with self.assertRaises(exclusion.Ocupado):
                with exclusion.exclusiva(self.base):
                    pass
        with exclusion.exclusiva(self.base):
            pass

    def test_fallo_de_adquisicion_no_deja_lock_compartido(self):
        with proceso_pausado(self, self.base, 'procesamiento'):
            with self.assertRaises(exclusion.Ocupado):
                with exclusion.procesamiento(self.base):
                    pass
        with exclusion.exclusiva(self.base):
            pass

    def test_fallo_del_plan_libera_transaccion_y_cerrojos(self):
        with patch.object(actualizacion, 'desactualizadas_por_etapa',
                          side_effect=RuntimeError('fallo sintético del plan')):
            with self.assertRaisesRegex(RuntimeError, 'fallo sintético'):
                actualizacion.aplicar(self.cx)
        self.assertFalse(self.cx.in_transaction)
        sha = self.guardar()
        papelera.quitar(self.cx, sha, 'QUITAR ' + sha)
        papelera.restaurar(self.cx, sha)

    def test_legajos_distintos_son_independientes(self):
        with proceso_pausado(self, self.base, 'exclusiva'):
            with exclusion.procesamiento(self.raiz / 'otra.sqlite'):
                pass


if __name__ == '__main__':
    unittest.main()
