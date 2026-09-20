"""Papelera por archivo: sólo documentos sintéticos, con FK reales activadas."""
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

import fitz

from ufil import db, papelera as pa, actualizacion as ac, versiones as vs, respaldo
from ufil.exclusion import exclusiva, Ocupado


def sembrar(cx, raiz, texto='Documento SINTETICO A', completo=False):
    with fitz.open() as pdf:
        pdf.new_page().insert_text((50, 50), texto)
        contenido = pdf.tobytes()
    sha = hashlib.sha256(contenido).hexdigest()
    ruta = raiz / 'originales' / sha[:2] / (sha + '.pdf')
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)
    cx.execute('INSERT INTO archivo VALUES (?,?,?,?,?,?,?,?)',
               (sha, str(ruta), 'sintetico.pdf', len(contenido), 1, 'application/pdf', 1, db.ahora()))
    p = cx.execute('INSERT INTO pagina(sha256,nro,clasificacion) VALUES (?,1,?)',
                   (sha, 'contrato_obra' if completo else None)).lastrowid
    if completo:
        l = cx.execute("INSERT INTO lectura(pagina_id,ruta,motor,creado_en) VALUES (?,'nativo','sintetico',?)",
                       (p, db.ahora())).lastrowid
        cx.execute("INSERT INTO palabra(lectura_id,orden,texto) VALUES (?,1,'SINTETICO')", (l,))
        d = cx.execute("""INSERT INTO documento(sha256,orden,clave,pagina_desde,pagina_hasta,tipo,perfil)
            VALUES (?,1,?,1,1,'contrato_obra','auto')""", (sha, sha + ':1')).lastrowid
        c = cx.execute("""INSERT INTO campo(documento_id,nombre,valor_literal,pagina_nro,x0,estado,lectura_id)
            VALUES (?,'nombre','PERSONA SINTETICA',1,1,'corregido',?)""", (d, l)).lastrowid
        cx.execute("INSERT INTO normalizacion VALUES (?,'nombre','persona sintetica',NULL)", (c,))
        cx.execute("""INSERT INTO revision_humana(sha256,orden,campo,accion,valor,quien,cuando,ancla_pagina)
            VALUES (?,1,'nombre','corregir','PERSONA SINTETICA','test',?,1)""", (sha, db.ahora()))
        cx.execute("""INSERT INTO auditoria(campo_id,sha256,campo_nombre,accion,quien,cuando)
            VALUES (?,?,'nombre','corregir','test',?)""", (c, sha, db.ahora()))
        cx.execute("INSERT INTO propuesta(campo_id,valor,modelo,creado_en) VALUES (?,'x','sintetico',?)", (c, db.ahora()))
        f = cx.execute("INSERT INTO conflicto(documento_id,campo_nombre) VALUES (?,'nombre')", (d,)).lastrowid
        cx.execute("INSERT INTO conflicto_variante(conflicto_id,ruta,valor) VALUES (?,'ocr','otro')", (f,))
        cx.execute("INSERT INTO foliatura(pagina_id,estado,origen,quien) VALUES (?,'corregida','humano','test')", (p,))
        t = cx.execute("INSERT INTO tabla(sha256,pagina_nro,documento_id,creado_en) VALUES (?,1,?,?)", (sha,d,db.ahora())).lastrowid
        cx.execute("INSERT INTO tabla_celda(tabla_id,fila,columna,texto,lectura_id) VALUES (?,0,0,'dato',?)", (t,l))
        cx.execute("INSERT INTO evento(documento_id,sha256,clase,fecha,origen,campo_id) VALUES (?,?,'hecho','2020-01-01','humano',?)", (d,sha,c))
        cx.execute("INSERT INTO cotejo_numero(sha256,pagina_nro,clase,letras,digitos) VALUES (?,1,'monto','uno','1')", (sha,))
        cx.execute('INSERT INTO pagina_texto(texto,sha256,nro) VALUES (?,?,1)', (texto,sha))
        for etapa in vs.ETAPAS:
            ac.sellar(cx, etapa.clave, str(p) if etapa.alcance == 'pagina' else sha if etapa.alcance == 'archivo' else '')
        render = raiz / 'derivados' / sha[:2] / sha / '1.png'
        render.parent.mkdir(parents=True, exist_ok=True)
        render.write_bytes(b'PNG SINTETICO')
        cx.execute('UPDATE pagina SET render=? WHERE id=?', (str(render),p))
    cx.commit()
    return sha


class PapeleraArchivos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.base = self.raiz / 'ufil.sqlite'
        self.cx = db.abrir(self.base)
        self.addCleanup(lambda: self.cx.close())

    def quitar(self, sha):
        return pa.quitar(self.cx, sha, 'QUITAR ' + sha)

    def reiniciar(self):
        self.cx.close()
        self.cx = db.abrir(self.base)

    def test_recien_subido_quitar_restaurar_y_dos_reinicios(self):
        sha = sembrar(self.cx, self.raiz)
        self.quitar(sha)
        self.reiniciar()
        self.assertEqual(self.cx.execute('SELECT COUNT(*) FROM archivo').fetchone()[0], 0)
        self.assertEqual(pa.listar(self.cx)['archivos'][0]['sha256'], sha)
        self.assertFalse((self.raiz/'originales'/sha[:2]/(sha+'.pdf')).exists())
        pa.restaurar(self.cx, sha)
        self.reiniciar()
        a = self.cx.execute('SELECT * FROM archivo').fetchone()
        self.assertEqual(hashlib.sha256(Path(a['ruta_original']).read_bytes()).hexdigest(), sha)
        self.assertEqual(pa.listar(self.cx), {'archivos': []})

    def test_completo_con_revisiones_y_derivados(self):
        sha = sembrar(self.cx, self.raiz, completo=True)
        antes = pa._instantanea(self.cx, sha)
        self.assertEqual(self.quitar(sha)['revisiones'], 1)
        for tabla in antes['filas']:
            if tabla == 'resultado_etapa':
                continue  # Los cinco sellos globales se invalidan, no se retiran.
            self.assertEqual(self.cx.execute(f'SELECT COUNT(*) FROM "{tabla}"').fetchone()[0], 0, tabla)
        pa.restaurar(self.cx, sha)
        despues = pa._instantanea(self.cx, sha)
        # Los rowid sin PK no constituyen identidad persistente.
        for datos in (antes, despues):
            for rs in datos['filas'].values():
                for r in rs:
                    r.pop('__rid')
        self.assertEqual(antes, despues)
        self.assertEqual(self.cx.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertTrue(Path(self.cx.execute('SELECT render FROM pagina').fetchone()[0]).is_file())

    def test_restaurar_dos_veces_es_conflicto_explicito(self):
        sha = sembrar(self.cx, self.raiz)
        self.quitar(sha)
        pa.restaurar(self.cx, sha)
        with self.assertRaises(pa.ConflictoPapelera):
            pa.restaurar(self.cx, sha)
        self.assertEqual(self.cx.execute('SELECT COUNT(*) FROM archivo').fetchone()[0], 1)

    def test_destruir_exige_papelera_y_confirmacion(self):
        sha = sembrar(self.cx, self.raiz, completo=True)
        with self.assertRaises(pa.ConflictoPapelera):
            pa.destruir(self.cx, sha, 'DESTRUIR ' + sha)
        with self.assertRaises(ValueError):
            self.quitar('invalido')
        self.quitar(sha)
        with self.assertRaises(ValueError):
            pa.destruir(self.cx, sha, 'si')
        pa.destruir(self.cx, sha, 'DESTRUIR ' + sha)
        self.reiniciar()
        self.assertEqual(pa.listar(self.cx)['archivos'], [])
        with self.assertRaises(pa.ConflictoPapelera):
            pa.restaurar(self.cx, sha)

    def test_entidad_compartida_y_relacion_ajena_se_conservan(self):
        a = sembrar(self.cx, self.raiz, completo=True)
        b = sembrar(self.cx, self.raiz, texto='SINTETICO B', completo=True)
        e = self.cx.execute("INSERT INTO entidad(clase,nombre,nombre_norm,creado_en) VALUES ('persona','sintetico','sintetico',?)", (db.ahora(),)).lastrowid
        for d in self.cx.execute('SELECT id,sha256 FROM documento').fetchall():
            self.cx.execute("INSERT INTO mencion(clase,entidad_id,literal,norm,documento_id,sha256,origen) VALUES ('persona',?,'sintetico','sintetico',?,?,'humano')", (e,d['id'],d['sha256']))
        self.cx.execute("INSERT INTO relacion(tipo,desde_entidad,hasta_entidad,fuente,creado_en) VALUES ('vinculo',?,?,'humano',?)", (e,e,db.ahora()))
        self.cx.commit()
        self.quitar(a)
        self.assertEqual(self.cx.execute('SELECT COUNT(*) FROM entidad').fetchone()[0], 1)
        self.assertEqual(self.cx.execute('SELECT COUNT(*) FROM relacion').fetchone()[0], 1)
        self.assertEqual(self.cx.execute('SELECT sha256 FROM mencion').fetchone()[0], b)
        pa.restaurar(self.cx,a)
        self.assertEqual(self.cx.execute('SELECT COUNT(*) FROM mencion').fetchone()[0], 2)

    def test_procesamiento_activo(self):
        sha = sembrar(self.cx, self.raiz)
        ac.sellar(self.cx,'extraccion',sha,estado='corriendo')
        self.cx.commit()
        with self.assertRaises(pa.ConflictoPapelera):
            self.quitar(sha)

    def test_exclusion_otro_hilo(self):
        sha = sembrar(self.cx,self.raiz)
        adquirido, soltar = threading.Event(), threading.Event()
        def tarea():
            with exclusiva(self.base):
                adquirido.set()
                soltar.wait(10)
        hilo = threading.Thread(target=tarea)
        hilo.start()
        try:
            self.assertTrue(adquirido.wait(5))
            with self.assertRaises(Ocupado):
                self.quitar(sha)
        finally:
            soltar.set()
            hilo.join(5)

    def test_colision_id_no_pisa_nuevo_archivo(self):
        a = sembrar(self.cx,self.raiz,completo=True)
        self.quitar(a)
        b = sembrar(self.cx,self.raiz,texto='SINTETICO B',completo=True)
        with self.assertRaises(pa.ConflictoPapelera):
            pa.restaurar(self.cx,a)
        self.assertEqual(self.cx.execute('SELECT sha256 FROM archivo').fetchone()[0], b)
        self.assertEqual(len(pa.listar(self.cx)['archivos']),1)

    def test_fallo_parcial_quitar_rollback(self):
        sha = sembrar(self.cx,self.raiz,completo=True)
        with patch.object(pa,'_invalidar',side_effect=RuntimeError('corte')):
            with self.assertRaises(RuntimeError):
                self.quitar(sha)
        self.reiniciar()
        self.assertEqual(len(pa.listar(self.cx)['archivos']),0)
        self.assertEqual(self.cx.execute('SELECT COUNT(*) FROM revision_humana').fetchone()[0],1)

    def test_fallo_parcial_restaurar_conserva_papelera(self):
        sha = sembrar(self.cx,self.raiz,completo=True)
        self.quitar(sha)
        with patch.object(pa,'_escribir',side_effect=OSError('disco lleno')):
            with self.assertRaises(OSError):
                pa.restaurar(self.cx,sha)
        self.reiniciar()
        self.assertEqual(len(pa.listar(self.cx)['archivos']),1)
        self.assertEqual(self.cx.execute('SELECT COUNT(*) FROM archivo').fetchone()[0],0)
        pa.restaurar(self.cx,sha)

    def test_reinicio_reintenta_limpieza_fisica(self):
        sha = sembrar(self.cx,self.raiz)
        with patch.object(pa,'limpiar_pendientes',side_effect=OSError('ocupado')):
            self.assertTrue(self.quitar(sha)['limpieza_pendiente'])
        self.reiniciar()
        self.assertEqual(self.cx.execute('SELECT COUNT(*) FROM papelera_limpieza').fetchone()[0],0)
        pa.restaurar(self.cx,sha)

    def test_migracion_16_a_actual_con_revision(self):
        sha = sembrar(self.cx,self.raiz,completo=True)
        self.cx.executescript('''DROP TRIGGER archivo_no_reingresar_papelera;
            DROP TABLE papelera_limpieza; DROP TABLE papelera_archivo; PRAGMA user_version=16;''')
        self.reiniciar()
        self.assertEqual(self.cx.execute('PRAGMA user_version').fetchone()[0],db.ESQUEMA_VERSION)
        self.quitar(sha)
        pa.restaurar(self.cx,sha)
        self.assertEqual(self.cx.execute('SELECT COUNT(*) FROM revision_humana').fetchone()[0],1)

    def test_backup_incluye_pdf_y_estado_de_papelera(self):
        sha = sembrar(self.cx,self.raiz,completo=True)
        self.quitar(sha)
        copia = self.raiz/'otra'/'copia.sqlite'
        copia.parent.mkdir()
        respaldo.hacer(self.cx,copia)
        otro = db.abrir(copia)
        try:
            pa.restaurar(otro,sha)
            self.assertTrue(Path(otro.execute('SELECT ruta_original FROM archivo').fetchone()[0]).is_file())
            self.assertTrue(Path(otro.execute('SELECT render FROM pagina').fetchone()[0]).is_file())
        finally:
            otro.close()

    def test_actualizacion_incremental_no_repite_ocr_ni_extraccion(self):
        a = sembrar(self.cx,self.raiz,completo=True)
        b = sembrar(self.cx,self.raiz,texto='SINTETICO B',completo=True)
        self.quitar(a)
        plan = ac.plan(self.cx)
        self.assertEqual(plan['recalcula']['paginas_ocr'],0)
        self.assertEqual(plan['recalcula']['archivos'],0)
        with patch('ufil.capa1_texto.leer_lote',side_effect=AssertionError('OCR inesperado')):
            r = ac.aplicar(self.cx)
        self.assertEqual(r['archivos'],0)
        self.assertEqual(self.cx.execute('SELECT sha256 FROM archivo').fetchone()[0],b)

    def test_reingesta_bloqueada_por_trigger(self):
        sha = sembrar(self.cx,self.raiz)
        fila = tuple(self.cx.execute('SELECT * FROM archivo').fetchone())
        self.quitar(sha)
        with self.assertRaises(sqlite3.IntegrityError):
            self.cx.execute('INSERT INTO archivo VALUES (?,?,?,?,?,?,?,?)',fila)
        self.cx.rollback()


if __name__ == '__main__':
    unittest.main()
