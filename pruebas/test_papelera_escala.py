"""Escala medida y contrato de papelera; datos exclusivamente sintéticos."""
import sqlite3
import base64
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from pruebas import test_papelera_archivos as soporte
from pruebas.test_papelera_archivos import sembrar
from ufil import conjuntos, entidades, piezas, db, papelera as pa


class PapeleraEscala(unittest.TestCase):
    setUp = soporte.PapeleraArchivos.setUp
    quitar = soporte.PapeleraArchivos.quitar

    def test_quitar_no_materializa_palabras_del_otro_archivo(self):
        a = sembrar(self.cx, self.raiz, completo=True)
        b = sembrar(self.cx, self.raiz, texto='SINTETICO B', completo=True)
        lectura = self.cx.execute('SELECT l.id FROM lectura l JOIN pagina p '
                                  'ON p.id=l.pagina_id WHERE p.sha256=?', (b,)).fetchone()[0]
        medidas = []
        for cantidad in (100, 20000):
            self.cx.executemany('INSERT INTO palabra(lectura_id,orden,texto) VALUES (?,?,?)',
                                ((lectura, n + 2, 'PALABRA SINTETICA') for n in range(cantidad)))
            self.cx.commit()
            leidas = []
            def contar(cursor, fila):
                r = sqlite3.Row(cursor, fila)
                if 'lectura_id' in r.keys() and 'texto' in r.keys() and 'orden' in r.keys():
                    leidas.append(r['lectura_id'])
                return r
            self.cx.row_factory = contar
            try:
                self.quitar(a)
            finally:
                self.cx.row_factory = sqlite3.Row
            medidas.append(len(leidas))
            pa.restaurar(self.cx, a)
        print('C4 palabras materializadas con B=101/20101:', medidas)
        self.assertEqual(medidas[0], medidas[1])
        self.assertNotIn(lectura, leidas)

    def test_c6_operaciones_reales_sobre_entidad_y_conjunto_compartidos(self):
        a = sembrar(self.cx, self.raiz, completo=True)
        b = sembrar(self.cx, self.raiz, texto='SINTETICO B', completo=True)
        cid = conjuntos.crear(self.cx, 'Entrega sintética')['id']
        for sha in (a, b):
            conjuntos.agregar(self.cx, cid, sha)
            did = self.cx.execute('SELECT id FROM documento WHERE sha256=?', (sha,)).fetchone()[0]
            entidades.anotar(self.cx, 'organismo', 'ORGANISMO SINTETICO',
                             origen='humano', documento_id=did, sha256=sha)
        eid = entidades.confirmar_entidad(self.cx, 'organismo',
                    entidades.normalizar('ORGANISMO SINTETICO'), 'Organismo sintético', 'prueba')['entidad_id']
        self.quitar(a)
        antes = dict(self.cx.execute('SELECT * FROM entidad WHERE id=?', (eid,)).fetchone())
        entidades.confirmar_entidad(self.cx, 'organismo',
                    entidades.normalizar('ORGANISMO SINTETICO'), 'Otro nombre propuesto', 'otra persona')
        conjuntos.reordenar(self.cx, cid, [b])
        self.assertEqual(antes, dict(self.cx.execute('SELECT * FROM entidad WHERE id=?', (eid,)).fetchone()))
        pa.restaurar(self.cx, a)
        self.assertEqual(self.cx.execute('SELECT COUNT(*) FROM mencion WHERE entidad_id=?', (eid,)).fetchone()[0], 2)
        self.assertEqual(self.cx.execute('PRAGMA foreign_key_check').fetchall(), [])

    def _referencia_a_pieza_compartida(self):
        a = sembrar(self.cx, self.raiz, completo=True)
        b = sembrar(self.cx, self.raiz, texto='SINTETICO B', completo=True)
        da = self.cx.execute('SELECT id FROM documento WHERE sha256=?', (a,)).fetchone()[0]
        db = self.cx.execute('SELECT id FROM documento WHERE sha256=?', (b,)).fetchone()[0]
        self.cx.execute("INSERT INTO relacion(tipo,desde_doc,hasta_doc,fuente,creado_en) "
                        "VALUES ('vinculo',?,?,'humano','2026')", (da, db))
        self.cx.commit()
        self.quitar(a)
        return a, b, db

    def test_c6_confirmar_mismo_tipo_en_padre_compartido_permite_restaurar(self):
        a, b, documento = self._referencia_a_pieza_compartida()
        piezas.clasificar_a_mano(self.cx, documento, 'contrato_obra', 'persona revisora')
        pa.restaurar(self.cx, a)
        self.assertEqual(self.cx.execute('SELECT clasificado_por FROM documento WHERE id=?',
                                        (documento,)).fetchone()[0], 'persona revisora')
        self.assertEqual(self.cx.execute('SELECT COUNT(*) FROM auditoria WHERE sha256=?', (b,)).fetchone()[0], 2)
        self.assertEqual(self.cx.execute('SELECT hasta_doc FROM relacion').fetchone()[0], documento)

    def test_c6_cambiar_identidad_de_la_pieza_conserva_conflicto(self):
        a, _, documento = self._referencia_a_pieza_compartida()
        self.cx.execute('UPDATE documento SET clave=? WHERE id=?', ('otra pieza', documento))
        self.cx.commit()
        with self.assertRaises(pa.ConflictoPapelera):
            pa.restaurar(self.cx, a)
        self.assertEqual(pa.listar(self.cx)['total'], 1)

    def test_listar_no_lee_ni_parsea_instantaneas(self):
        sha = sembrar(self.cx, self.raiz, completo=True)
        self.quitar(sha)
        def autorizar(accion, tabla, columna, *_):
            if accion == sqlite3.SQLITE_READ and tabla == 'papelera_archivo' and columna == 'registros':
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        self.cx.set_authorizer(autorizar)
        try:
            with patch.object(pa.json, 'loads', side_effect=AssertionError('No parsear JSON')):
                r = pa.listar(self.cx)
        finally:
            self.cx.set_authorizer(None)
        self.assertEqual(r['total'], 1)
        self.assertEqual(r['archivos'][0]['paginas'], 1)
        self.assertEqual(r['archivos'][0]['decisiones_humanas'], 4)
        registro = self.cx.execute('SELECT registros FROM papelera_archivo').fetchone()[0]
        self.assertNotIn('assets', json.loads(registro))
        self.assertEqual(self.cx.execute('SELECT contenido,typeof(contenido) FROM papelera_derivado').fetchone()[:],
                         (b'PNG SINTETICO', 'blob'))

    def test_paginas_y_lote_nulos_y_conocidos(self):
        for paginas, lote in ((None, None), (1, 'Entrega sintética')):
            with self.subTest(paginas=paginas):
                sha = sembrar(self.cx, self.raiz)
                self.cx.execute('UPDATE archivo SET paginas=? WHERE sha256=?', (paginas, sha))
                if lote:
                    self.cx.execute('INSERT INTO procedencia(sha256,lote) VALUES (?,?)', (sha, lote))
                self.cx.commit()
                self.quitar(sha)
                fila = next(r for r in pa.listar(self.cx)['archivos'] if r['sha256'] == sha)
                self.assertEqual((fila['paginas'], fila['lote']), (paginas, lote))

    def test_api_archivos_cantidad_de_sentencias_constante(self):
        from ufil.servidor import api_archivos
        cantidades = []
        for n in (1, 30):
            for i in range(n):
                sembrar(self.cx, self.raiz, texto=f'SINTETICO {n}-{i}', completo=True)
            sentencias = []
            self.cx.set_trace_callback(sentencias.append)
            try:
                datos = api_archivos(self.cx)
            finally:
                self.cx.set_trace_callback(None)
            cantidades.append(len(sentencias))
            for f in datos['archivos']:
                self.assertEqual(f['decisiones_humanas'], 4)
                self.assertTrue(f['tiene_revisiones_humanas'])
        print('C7 sentencias con 1/31 archivos:', cantidades)
        self.assertEqual(cantidades[0], cantidades[1])

    def test_decisiones_misma_definicion_y_relaciones_sin_duplicar(self):
        from ufil.servidor import api_archivos
        a = sembrar(self.cx, self.raiz, completo=True)
        b = sembrar(self.cx, self.raiz, texto='SINTETICO B', completo=True)
        da = self.cx.execute('SELECT id FROM documento WHERE sha256=?', (a,)).fetchone()[0]
        otro = self.cx.execute('SELECT id FROM documento WHERE sha256=?', (b,)).fetchone()[0]
        self.cx.execute("UPDATE documento SET clasificado_por='test' WHERE id=?", (da,))
        self.cx.execute("UPDATE campo SET revisado_por='test' WHERE documento_id=?", (da,))
        self.cx.execute("UPDATE tabla SET origen='humano',union_quien='test' WHERE sha256=?", (a,))
        self.cx.execute("INSERT INTO mencion(clase,literal,norm,sha256,origen,quien) VALUES ('organismo','X','x',?,'humano','test')", (a,))
        self.cx.execute("INSERT INTO pieza_tramo(documento_id,sha256,pagina_desde,pagina_hasta,quien) VALUES (?,?,1,1,'test')", (da, a))
        for destino in (da, otro):
            self.cx.execute("INSERT INTO relacion(tipo,desde_doc,hasta_doc,fuente,quien,creado_en) VALUES ('vinculo',?,?,'humano','test','2026')", (da, destino))
        self.cx.commit()
        activos = {f['sha256']: f for f in api_archivos(self.cx)['archivos']}
        self.assertEqual(activos[a]['decisiones_humanas'], 11)
        self.assertEqual(activos[b]['decisiones_humanas'], 5)
        self.assertEqual(activos[a]['revisiones'], 1)
        self.assertTrue(pa.tiene_revisiones_humanas(self.cx, a))
        self.quitar(a)
        f = pa.listar(self.cx)['archivos'][0]
        self.assertEqual(f['decisiones_humanas'], 11)
        self.assertEqual(f['tiene_revisiones_humanas'], f['decisiones_humanas'] > 0)

    def _papelera_historica_24(self):
        sha = sembrar(self.cx, self.raiz, completo=True)
        self.cx.execute("INSERT INTO procedencia(sha256,lote) VALUES (?,'Lote sintético')", (sha,))
        self.cx.commit()
        self.quitar(sha)
        a = dict(self.cx.execute('SELECT * FROM papelera_archivo').fetchone())
        datos = json.loads(a['registros'])
        datos['assets'] = {r['ruta']: base64.b64encode(r['contenido']).decode('ascii')
                           for r in self.cx.execute('SELECT * FROM papelera_derivado')}
        datos['tiene_revisiones_humanas'] = True
        self.cx.executescript('''DROP TABLE papelera_derivado;
            DROP TABLE papelera_limpieza;
            DROP TRIGGER archivo_no_reingresar_papelera;
            DROP TABLE papelera_archivo;
            CREATE TABLE papelera_archivo (
              sha256 TEXT PRIMARY KEY, nombre TEXT NOT NULL, quitado_en TEXT NOT NULL,
              version INTEGER NOT NULL, registros TEXT NOT NULL, pdf BLOB NOT NULL,
              revisiones INTEGER NOT NULL, documentos INTEGER NOT NULL);
            CREATE TABLE papelera_limpieza (
              sha256 TEXT PRIMARY KEY REFERENCES papelera_archivo(sha256) ON DELETE CASCADE,
              rutas TEXT NOT NULL);
            PRAGMA user_version=24;''')
        self.cx.execute('INSERT INTO papelera_archivo VALUES (?,?,?,?,?,?,?,?)',
                        (sha, a['nombre'], a['quitado_en'], 24, json.dumps(datos), a['pdf'], 1, 1))
        self.cx.commit()
        return sha, datos

    def test_migracion_v24_con_papelera_restaurable(self):
        sha, antes = self._papelera_historica_24()
        self.assertTrue(db.inicializar(self.cx))
        self.assertFalse(db.inicializar(self.cx))
        self.assertEqual(self.cx.execute('PRAGMA user_version').fetchone()[0], 25)
        fila = pa.listar(self.cx)['archivos'][0]
        self.assertEqual((fila['paginas'], fila['lote'], fila['decisiones_humanas']), (1, 'Lote sintético', 4))
        self.assertNotIn('assets', json.loads(self.cx.execute('SELECT registros FROM papelera_archivo').fetchone()[0]))
        pa.restaurar(self.cx, sha)
        despues = pa._instantanea(self.cx, sha)
        for datos in (antes, despues):
            for filas in datos['filas'].values():
                for r in filas:
                    r.pop('__rid')
        self.assertEqual(antes['filas'], despues['filas'])
        self.assertEqual(antes['fts'], despues['fts'])
        render = self.cx.execute('SELECT render FROM pagina').fetchone()[0]
        self.assertEqual(Path(render).read_bytes(), b'PNG SINTETICO')
        self.assertEqual(self.cx.execute('SELECT COUNT(*) FROM papelera_derivado').fetchone()[0], 0)
        self.assertEqual(self.cx.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_migracion_fallida_no_sube_version_ni_pierde_instantanea(self):
        sha, _ = self._papelera_historica_24()
        antes = self.cx.execute('SELECT registros FROM papelera_archivo').fetchone()[0]
        with patch('base64.b64decode', side_effect=ValueError('fallo sintético')):
            with self.assertRaises(ValueError):
                db.inicializar(self.cx)
        self.assertEqual(self.cx.execute('PRAGMA user_version').fetchone()[0], 24)
        self.assertEqual(self.cx.execute('SELECT registros FROM papelera_archivo').fetchone()[0], antes)
        db.inicializar(self.cx)
        pa.restaurar(self.cx, sha)

    def test_interpretacion_completa_y_referencias_sin_fk(self):
        a = sembrar(self.cx, self.raiz, completo=True)
        b = sembrar(self.cx, self.raiz, texto='SINTETICO B', completo=True)
        docs = [r[0] for r in self.cx.execute('SELECT id FROM documento ORDER BY id')]
        iid = self.cx.execute("INSERT INTO interpretacion(alcance,clase,texto,origen,creado_en) VALUES ('lote','resumen','SINTETICO','regla:test','2026')").lastrowid
        self.cx.executemany('INSERT INTO interpretacion_fuente(interpretacion_id,documento_id) VALUES (?,?)',
                            [(iid, d) for d in docs])
        cid = self.cx.execute("INSERT INTO coleccion(nombre,quien,creado_en) VALUES ('Sintética','test','2026')").lastrowid
        self.cx.execute("INSERT INTO coleccion_item(coleccion_id,clase,referencia,quien,cuando) VALUES (?,'foja',?,'test','2026')", (cid, a + ':1'))
        self.cx.commit()
        self.quitar(a)
        self.assertEqual(self.cx.execute('SELECT COUNT(*) FROM interpretacion_fuente').fetchone()[0], 0)
        self.assertEqual(self.cx.execute('SELECT COUNT(*) FROM interpretacion').fetchone()[0], 0)
        self.assertEqual(self.cx.execute('SELECT COUNT(*) FROM coleccion_item').fetchone()[0], 0)
        self.assertEqual(self.cx.execute('SELECT sha256 FROM documento').fetchone()[0], b)
        pa.restaurar(self.cx, a)
        self.assertEqual(self.cx.execute('SELECT COUNT(*) FROM interpretacion_fuente').fetchone()[0], 2)

    def test_campo_ajeno_que_usa_lectura_impide_quitar(self):
        a = sembrar(self.cx, self.raiz, completo=True)
        b = sembrar(self.cx, self.raiz, texto='SINTETICO B', completo=True)
        lectura = self.cx.execute('SELECT l.id FROM lectura l JOIN pagina p ON p.id=l.pagina_id WHERE p.sha256=?', (a,)).fetchone()[0]
        self.cx.execute('UPDATE campo SET lectura_id=? WHERE documento_id IN (SELECT id FROM documento WHERE sha256=?)', (lectura, b))
        self.cx.commit()
        with self.assertRaises(pa.ConflictoPapelera):
            self.quitar(a)
        self.assertEqual(self.cx.execute('SELECT COUNT(*) FROM archivo').fetchone()[0], 2)


if __name__ == '__main__':
    unittest.main()
