"""Regresiones reales de migración, OCR incremental y respaldo; sólo datos sintéticos."""
import importlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ufil import db, actualizacion as ac, respaldo, versiones as vs
from pruebas.test_papelera_archivos import sembrar


class AuditoriaBackend(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.base = self.raiz/'ufil.sqlite'
        self.cx = db.abrir(self.base)
        self.addCleanup(lambda: self.cx.close())

    def test_releer_ocr_con_celdas_no_rompe_fk(self):
        sha = sembrar(self.cx,self.raiz,completo=True)
        self.assertEqual(ac._borrar_lecturas_de(self.cx,sha),1)
        self.cx.commit()
        self.assertIsNone(self.cx.execute('SELECT lectura_id FROM tabla_celda').fetchone()[0])
        self.assertEqual(self.cx.execute('SELECT texto FROM tabla_celda').fetchone()[0],'dato')
        self.assertEqual(self.cx.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_una_pagina_vieja_no_arrastra_otros_archivos(self):
        a = sembrar(self.cx,self.raiz,completo=True)
        b = sembrar(self.cx,self.raiz,texto='SINTETICO B',completo=True)
        p = str(self.cx.execute('SELECT id FROM pagina WHERE sha256=?',(a,)).fetchone()[0])
        ac.sellar(self.cx,'lectura',p,estado='desactualizado')
        self.cx.commit()
        trabajo = ac.desactualizadas_por_etapa(self.cx)
        for etapa in ac.POR_ARCHIVO:
            self.assertNotIn(b,trabajo.get(etapa,[]),etapa)
        plan = ac.plan(self.cx)
        self.assertEqual(plan['recalcula']['archivos'],1)

    def test_corriendo_tras_reinicio_no_es_vigente(self):
        sha = sembrar(self.cx,self.raiz,completo=True)
        ac.sellar(self.cx,'extraccion',sha,estado='corriendo')
        self.cx.commit()
        self.assertIn(sha,ac.desactualizadas_por_etapa(self.cx).get('extraccion',[]))

    def test_import_backend_no_consulta_tesseract(self):
        from ufil import capa1_texto
        with patch('pytesseract.get_tesseract_version',side_effect=AssertionError('no hay OCR')):
            importlib.reload(capa1_texto)

    def test_migrar_esquema_historico_16_real(self):
        vieja = self.raiz/'v16.sqlite'
        sql = (Path(__file__).parent/'fixtures'/'esquema_v16.sql').read_text(encoding='utf-8-sig')
        for a,b in db.SUSTITUCIONES.items():
            sql=sql.replace(a,b)
        cx=sqlite3.connect(vieja)
        cx.executescript(sql)
        cx.execute("INSERT INTO archivo(sha256,ruta_original,nombre,bytes,ingerido_en) VALUES ('a','/sintetico','sintetico',1,'2020')")
        cx.execute("INSERT INTO documento(sha256,tipo,perfil) VALUES ('a','contrato_obra','auto')")
        cx.execute("INSERT INTO campo(documento_id,nombre,valor_literal,pagina_nro,x0,estado) VALUES (1,'nombre','SINTETICO',1,1,'corregido')")
        cx.execute("INSERT INTO revision_humana(sha256,orden,campo,accion,valor,quien,cuando) VALUES ('a',1,'nombre','corregir','SINTETICO','test','2020')")
        cx.execute('PRAGMA user_version=16')
        cx.commit()
        cx.close()
        cx=db.abrir(vieja)
        try:
            self.assertEqual(cx.execute('PRAGMA user_version').fetchone()[0],db.ESQUEMA_VERSION)
            self.assertEqual(cx.execute('SELECT ancla_pagina FROM revision_humana').fetchone()[0],1)
            self.assertEqual(cx.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertFalse(db.inicializar(cx))
        finally:
            cx.close()

    def test_no_rebaja_version_futura(self):
        self.cx.execute('PRAGMA user_version=999')
        with self.assertRaises(ValueError):
            db.inicializar(self.cx)
        self.assertEqual(self.cx.execute('PRAGMA user_version').fetchone()[0],999)

    def test_respaldo_rechaza_fk_rota(self):
        sembrar(self.cx,self.raiz)
        self.cx.execute('PRAGMA foreign_keys=OFF')
        self.cx.execute("INSERT INTO pagina(sha256,nro) VALUES ('inexistente',1)")
        self.cx.commit()
        with self.assertRaises(respaldo.RespaldoInvalido):
            respaldo.inspeccionar(self.base)

    def test_respaldo_informa_revisiones_en_papelera(self):
        from ufil import papelera
        sha=sembrar(self.cx,self.raiz,completo=True)
        papelera.quitar(self.cx,sha,'QUITAR '+sha)
        resumen=respaldo.resumen(self.cx)
        self.assertEqual(resumen['archivos_papelera'],1)
        self.assertEqual(resumen['revisiones_papelera'],1)

    def test_respaldo_rechaza_destino_con_conexion_abierta(self):
        from ufil.exclusion import Ocupado
        sembrar(self.cx,self.raiz)
        copia=self.raiz/'copia.sqlite'
        respaldo.hacer(self.cx,copia)
        with self.assertRaises(Ocupado):
            respaldo.restaurar(copia,self.base)
        self.assertEqual(self.cx.execute('SELECT COUNT(*) FROM archivo').fetchone()[0],1)

    def test_respaldo_copia_wal_confirmado_del_origen(self):
        sembrar(self.cx,self.raiz)
        # Mantener abierta la conexión deja transacciones confirmadas en WAL.
        self.cx.execute("INSERT INTO ajuste VALUES ('ultima_decision','sintetica')")
        self.cx.commit()
        nueva=self.raiz/'otra'/'ufil.sqlite'
        respaldo.restaurar(self.base,nueva)
        con=db.abrir(nueva)
        try:
            self.assertEqual(con.execute("SELECT valor FROM ajuste WHERE clave='ultima_decision'").fetchone()[0],'sintetica')
        finally:
            con.close()

    def test_fallo_al_publicar_respaldo_conserva_base_y_copia_anterior(self):
        sembrar(self.cx,self.raiz)
        copia=self.raiz/'copia.sqlite'
        respaldo.hacer(self.cx,copia)
        self.cx.execute("INSERT INTO ajuste VALUES ('ultima_decision','sintetica')")
        self.cx.commit()
        self.cx.close()
        with patch('ufil.respaldo.os.replace',side_effect=OSError('fallo publicación')):
            with self.assertRaises(OSError):
                respaldo.restaurar(copia,self.base)
        self.cx=db.abrir(self.base)
        self.assertEqual(self.cx.execute("SELECT valor FROM ajuste WHERE clave='ultima_decision'").fetchone()[0],'sintetica')
        apartadas=list(self.raiz.glob('ufil.reemplazada-*.sqlite'))
        self.assertEqual(len(apartadas),1)
        con=sqlite3.connect(apartadas[0])
        try:
            self.assertEqual(con.execute("SELECT valor FROM ajuste WHERE clave='ultima_decision'").fetchone()[0],'sintetica')
        finally:
            con.close()

    def test_migracion_sql_fallida_es_atomica(self):
        self.cx.execute('PRAGMA user_version=23')
        esquema=db.esquema_sql()
        with patch.object(db,'esquema_sql',return_value=esquema+'\nCREATE TABLE parcial(x); SQL_INVALIDO;'):
            with self.assertRaises(sqlite3.OperationalError):
                db.inicializar(self.cx)
        self.assertEqual(self.cx.execute('PRAGMA user_version').fetchone()[0],23)
        self.assertIsNone(self.cx.execute("SELECT name FROM sqlite_master WHERE name='parcial'").fetchone())
        self.cx.execute('SELECT * FROM v_contrato').fetchall()

    def test_migracion_repara_objetos_faltantes_con_version_actual(self):
        self.cx.execute('DROP TRIGGER archivo_no_reingresar_papelera')
        self.assertTrue(db.inicializar(self.cx))
        self.assertFalse(db.inicializar(self.cx))

    def test_verificar_detecta_fk_rotas(self):
        from ufil import verificacion
        self.cx.execute('PRAGMA foreign_keys=OFF')
        self.cx.execute("INSERT INTO pagina(sha256,nro) VALUES ('inexistente',1)")
        self.cx.commit()
        self.assertTrue(any('referencias foráneas' in e for e in verificacion.correr(self.cx,con_integridad=False)))


if __name__ == '__main__':
    unittest.main()
