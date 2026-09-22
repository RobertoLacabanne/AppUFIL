"""De PDF nativo ya leído a renglones, decisiones y comparación; todo sintético."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import fitz

from pruebas.corpus_contratacion import generar
from ufil import actualizacion as ac, capa2_extraccion as c2, db, precios, renglones as rg, tablas, versiones as vs


def cargar(cx, carpeta):
    """Simula una base que YA tiene las palabras de la lectura nativa guardadas."""
    for nombre, ruta in generar(carpeta).items():
        crudo = ruta.read_bytes()
        sha = hashlib.sha256(crudo).hexdigest()
        cx.execute('INSERT INTO archivo(sha256,ruta_original,nombre,bytes,paginas,ingerido_en) VALUES (?,?,?,?,1,?)',
                   (sha, str(ruta), ruta.name, len(crudo), db.ahora()))
        pid = cx.execute('INSERT INTO pagina(sha256,nro,ancho_pt,alto_pt) VALUES (?,1,595,842)', (sha,)).lastrowid
        lid = cx.execute("INSERT INTO lectura(pagina_id,ruta,motor,confianza,creado_en) VALUES (?,'nativo','pymupdf',1,?)", (pid, db.ahora())).lastrowid
        with fitz.open(ruta) as pdf:
            for orden, w in enumerate(pdf[0].get_text('words')):
                cx.execute('INSERT INTO palabra(lectura_id,orden,texto,x0,y0,x1,y1,conf) VALUES (?,?,?,?,?,?,?,1)',
                           (lid, orden, w[4], *w[:4]))
    cx.commit()


def derivar(cx):
    for (sha,) in cx.execute('SELECT sha256 FROM archivo').fetchall():
        rutas = c2.lecturas_por_ruta(cx, sha)
        c2.clasificar_fojas(cx, sha, por_ruta=rutas)
        c2.segmentar_piezas(cx, sha, por_ruta=rutas)
        tablas.detectar_archivo(cx, sha, por_ruta=rutas)
        rg.extraer_archivo(cx, sha, por_ruta=rutas)


def vincular(cx):
    # La reconstrucción automática pertenece a 7b; acá se carga una vinculación explícita.
    cid = cx.execute("INSERT INTO contratacion(nombre,creado_en) VALUES ('Compra sintética',?)", (db.ahora(),)).lastrowid
    cx.execute("INSERT INTO contratacion_documento(contratacion_id,documento_id,etapa) SELECT ?,id,tipo FROM documento", (cid,))
    cx.commit()
    return cid


class DecimalesYEstadisticas(unittest.TestCase):
    def test_encabezado_fuera_del_bloque_y_cuenta_inequivoca(self):
        from ufil.capa1_texto import Palabra
        cs = []
        for fila, valores in enumerate([('Tubo', '2', '10,00', '20,00'),
                                       ('Caño', '3', '15,00', '45,00')]):
            for col, t in enumerate(valores):
                cs.append(dict(fila=fila, columna=col, texto=t, es_encabezado=0, x0=col*100))
        palabras = [Palabra('Descripcion', 0, 80, 90, 90, 1),
                    Palabra('Cantidad', 100, 80, 190, 90, 1)]
        roles = rg.columnas(cs, palabras, {'y0': 100})
        self.assertEqual(roles, {'descripcion': 0, 'cantidad': 1, 'precio': 2, 'subtotal': 3})
        # Sin cantidad rotulada, no adivina cuál de los números es cantidad/código.
        self.assertNotIn('precio', rg.columnas(cs))

    def test_argentinos_exactos_y_ausencias(self):
        for literal, esperado in [('165.000,00', '165000.00'), ('0,00', '0.00'),
                                  ('$ 1.234,567', '1234.567'), ('-20,50', '-20.50')]:
            self.assertEqual(rg.decimal_argentino(literal), Decimal(esperado))
        for literal in [None, '', 'NaN', 'inf', '1O0,00', '1.23.45', 'sin precio']:
            self.assertIsNone(rg.decimal_argentino(literal))

    def test_desvio_muestral_cuartiles_y_redondeo(self):
        r = precios.estadisticas([Decimal(x) for x in ('1', '2', '3', '4')], 'B')
        self.assertEqual(r, dict(nivel='B', n=4, minimo='1.00', maximo='4.00', media='2.50',
                                 mediana='2.50', desvio='1.29', rango_intercuartil='1.50'))
        self.assertIsNone(precios.estadisticas([Decimal(0)], 'C')['desvio'])
        self.assertEqual(precios.dinero(Decimal('1.005')), '1.01')
        self.assertEqual(precios.dinero(Decimal('-1.005')), '-1.01')


class RenglonesDelCorpus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.cx = db.abrir(self.raiz / 'ufil.sqlite')
        self.addCleanup(self.cx.close)
        cargar(self.cx, self.raiz / 'originales')
        derivar(self.cx)

    def factura(self):
        return dict(self.cx.execute("SELECT * FROM renglon WHERE etapa='factura' AND fila=1").fetchone())

    def test_cantidades_literales_y_anclajes(self):
        cantidades = dict(self.cx.execute('SELECT etapa,count(*) FROM renglon WHERE vigente=1 GROUP BY etapa'))
        self.assertEqual(cantidades, {'presupuesto': 9, 'oferta': 9, 'adjudicacion': 3,
                                     'orden_compra': 3, 'factura': 3, 'pedido': 3, 'remito': 3})
        r = self.factura()
        self.assertEqual(r['desc_literal'], 'Bomba de agua centrifuga 1 HP Rowa Tango')
        self.assertEqual(r['precio_literal'], '180.000,00')
        self.assertEqual(r['precio_unitario'], '180000.00')
        dato = rg.serializar(self.cx, r)
        self.assertTrue(dato['precio_unitario']['fuente']['celdas'])
        self.assertEqual(dato['fecha']['valor'], '2023-08-24')
        self.assertIsNotNone(dato['fecha']['fuente']['region'])
        # El corpus NO imprime moneda ni tratamiento de IVA en la factura.
        self.assertIsNone(r['moneda'])
        self.assertIsNone(r['iva'])
        self.assertEqual(r['estado'], 'pendiente_baja')

    def test_comparacion_nominal_con_atributos_explicitos(self):
        vincular(self.cx)
        r = self.factura()
        # Variación mínima explícita de la prueba: no altera el corpus de aceptación.
        self.cx.execute("UPDATE renglon SET moneda='ARS',iva='incluido' WHERE id=?", (r['id'],))
        self.cx.commit()
        comp = precios.comparar(self.cx, r['id'])
        self.assertEqual(comp['estadisticas']['nivel'], 'A')
        self.assertEqual(comp['estadisticas']['n'], 3)
        self.assertEqual(comp['estadisticas']['mediana'], '102500.00')
        self.assertEqual(comp['diferencia'], {'absoluta': '77500.00', 'porcentual': '75.61', 'contra': 'mediana'})
        self.assertEqual(sum(r['nivel'] == 'C' for r in comp['referencias']), 3)
        self.assertTrue(any('misma compra' in e['motivo'] for e in comp['excluidas']))
        self.assertTrue(all(o['fuente'] for o in comp['calculo']['operandos']))
        resultado = json.loads(comp['calculo']['resultado'])
        self.assertEqual(resultado['segunda_mejor_oferta']['precio'], '102500.00')

    def test_sin_atributos_no_inventa_fuerte(self):
        vincular(self.cx)
        c = precios.comparar(self.cx, self.factura()['id'])
        self.assertNotEqual(c['estadisticas']['nivel'], 'A')
        self.assertTrue(all(r['comparabilidad']['estado'] != 'fuerte' for r in c['referencias']))

    def test_mediana_cero_y_muestra_unica(self):
        vincular(self.cx)
        r = self.factura()
        self.cx.execute("UPDATE renglon SET vigente=0 WHERE id!=? AND NOT (etapa='oferta' AND fila=1)", (r['id'],))
        self.cx.execute("UPDATE renglon SET precio_unitario='0.00' WHERE etapa='oferta'")
        self.cx.execute("UPDATE renglon SET moneda='ARS',iva='incluido' WHERE id=?", (r['id'],))
        self.cx.commit()
        comp = precios.comparar(self.cx, r['id'])
        self.assertIsNone(comp['diferencia']['porcentual'])
        self.assertTrue(any('cero' in a for a in comp['advertencias']))
        self.cx.execute("UPDATE renglon SET vigente=0 WHERE etapa='oferta' AND id!=(SELECT min(id) FROM renglon WHERE etapa='oferta' AND vigente=1)")
        self.cx.commit()
        comp = precios.comparar(self.cx, r['id'])
        self.assertEqual(comp['estadisticas']['n'], 1)
        self.assertIsNone(comp['estadisticas']['desvio'])
        self.assertTrue(any('sola referencia' in a for a in comp['advertencias']))

    def test_decision_distinto_manda_y_otra_compra_es_independiente(self):
        r = self.factura()
        ref = self.cx.execute("SELECT id FROM renglon WHERE etapa='oferta' AND fila=1 LIMIT 1").fetchone()[0]
        iid = rg.serializar(self.cx, r)['item']['id']
        rg.asignar_item(self.cx, ref, {'decision': 'distinto', 'item_id': iid, 'quien': 'test'})
        comp = precios.comparar(self.cx, r['id'])
        self.assertTrue(any(e['renglon']['id'] == ref and 'decision_humana' in e['motivo'] for e in comp['excluidas']))
        # Sin vinculación a la misma compra, la orden puede ser referencia independiente.
        self.assertTrue(any(e['renglon']['etapa'] == 'orden_compra' for e in comp['referencias']))

    def test_papelera_conserva_asignacion_y_hallazgo_con_fuentes_multiples(self):
        from ufil import papelera
        r = self.factura()
        otro = dict(self.cx.execute("SELECT * FROM renglon WHERE etapa='oferta' LIMIT 1").fetchone())
        decision = rg.asignar_item(self.cx, r['id'], {'decision': 'mismo', 'crear': {'nombre': 'Revisado'}, 'quien': 'test'})
        h = self.cx.execute("""INSERT INTO hallazgo(clave,tipo,titulo,descripcion,revision_estado,quien,nota,version,actualizado_en)
                             VALUES ('estable','diferencia_precio','Diferencia detectada','Prueba','relevante','test','Nota',1,?)""", (db.ahora(),)).lastrowid
        for f in (r, otro):
            self.cx.execute('INSERT INTO hallazgo_fuente(hallazgo_id,sha256,documento_id,renglon_clave,clave) VALUES (?,?,?,?,?)',
                            (h, f['sha256'], f['documento_id'], f['clave'], f['clave']))
        self.cx.commit()
        papelera.quitar(self.cx, r['sha256'], 'QUITAR ' + r['sha256'])
        self.assertEqual(self.cx.execute('SELECT count(*) FROM hallazgo').fetchone()[0], 0)
        self.assertTrue(self.cx.execute('SELECT 1 FROM item WHERE id=?', (decision['item_id'],)).fetchone())
        self.assertTrue(self.cx.execute('SELECT 1 FROM renglon WHERE id=?', (otro['id'],)).fetchone())
        papelera.restaurar(self.cx, r['sha256'])
        self.assertEqual(rg.serializar(self.cx, rg.fila(self.cx, r['id']))['item']['id'], decision['item_id'])
        self.assertEqual(self.cx.execute('SELECT revision_estado,nota FROM hallazgo WHERE id=?', (h,)).fetchone()[:], ('relevante', 'Nota'))
        self.assertEqual(self.cx.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_derivado_con_dos_operandos_y_ausencia_no_es_cero(self):
        r = self.factura()
        self.cx.execute('DELETE FROM tabla_celda WHERE tabla_id=? AND fila=1 AND columna=4', (r['tabla_id'],))
        self.cx.commit()
        rg.extraer_archivo(self.cx, r['sha256'])
        nuevo = rg.fila(self.cx, r['id'])
        self.assertEqual(nuevo['precio_unitario'], '180000.00')
        self.assertTrue(nuevo['precio_derivado'])
        self.assertIsNone(nuevo['precio_literal'])
        self.assertEqual(nuevo['precio_formula'], 'subtotal / cantidad')
        self.assertEqual(len(rg.fuente(self.cx, nuevo, 'precio')['celdas']), 2)
        self.cx.execute('DELETE FROM tabla_celda WHERE tabla_id=? AND fila=1 AND columna=5', (r['tabla_id'],))
        self.cx.commit()
        rg.extraer_archivo(self.cx, r['sha256'])
        self.assertIsNone(rg.fila(self.cx, r['id'])['precio_unitario'])

    def test_decision_sobrevive_tablas_rehechas_y_orden_nuevo(self):
        r = self.factura()
        decision = rg.asignar_item(self.cx, r['id'], {'crear': {'nombre': 'Producto revisado'}, 'decision': 'mismo', 'quien': 'prueba'})
        self.cx.execute('UPDATE documento SET orden=orden+10 WHERE sha256=?', (r['sha256'],))
        self.cx.commit()
        tablas.detectar_archivo(self.cx, r['sha256'])
        rg.extraer_archivo(self.cx, r['sha256'])
        despues = rg.serializar(self.cx, rg.fila(self.cx, r['id']))
        self.assertEqual(despues['item']['id'], decision['item_id'])
        self.assertEqual(despues['item']['comparabilidad'], 'fuerte')
        self.assertEqual(self.cx.execute('SELECT count(*) FROM renglon').fetchone()[0], 33)

    def test_actualizar_material_cargado_no_relee(self):
        self.cx.execute('DELETE FROM renglon_item')
        self.cx.execute('DELETE FROM renglon')
        for e in vs.ETAPAS:
            if e.clave == 'renglones':
                continue
            ids = ([str(r[0]) for r in self.cx.execute('SELECT id FROM pagina')] if e.alcance == 'pagina'
                   else [r[0] for r in self.cx.execute('SELECT sha256 FROM archivo')] if e.alcance == 'archivo' else [''])
            for i in ids:
                ac.sellar(self.cx, e.clave, i)
        self.cx.commit()
        antes = self.cx.execute('SELECT count(*) FROM palabra').fetchone()[0]
        with patch('ufil.capa1_texto.leer_lote', side_effect=AssertionError('No debe releer')):
            resultado = ac.aplicar(self.cx)
        self.assertEqual(resultado['errores'], [])
        self.assertEqual(self.cx.execute('SELECT count(*) FROM renglon WHERE vigente=1').fetchone()[0], 33)
        self.assertEqual(self.cx.execute('SELECT count(*) FROM palabra').fetchone()[0], antes)

    def test_paginacion_filtros_y_niveles_invalidos(self):
        r = precios.listar(self.cx, etapa='factura', limite='2', desde='1')
        self.assertEqual((r['total'], r['limite'], r['desde'], len(r['renglones'])), (3, 2, 1, 2))
        self.assertEqual(precios.listar(self.cx, limite=999)['limite'], 500)
        for kwargs in [dict(limite='no'), dict(desde=-1), dict(dif_min_pct='NaN'), dict(fecha_desde='ayer')]:
            with self.assertRaises(ValueError):
                precios.listar(self.cx, **kwargs)
        with self.assertRaises(ValueError):
            precios.comparar(self.cx, self.factura()['id'], 'Z')


class Migracion26(unittest.TestCase):
    def test_v25_con_datos_y_revisiones_no_pierde_filas(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / 'v25.sqlite'
            cx = sqlite3.connect(ruta)
            # El bloque nuevo es aditivo: el resto es exactamente el esquema previo.
            sql = db.esquema_sql()
            a = sql.index('-- Incremento 7:')
            b = sql.index('-- ─', a)
            cx.executescript(sql[:a] + sql[b:])
            cx.execute('PRAGMA user_version=25')
            cx.execute("INSERT INTO archivo(sha256,ruta_original,nombre,bytes,paginas,ingerido_en) VALUES ('s','/s','s.pdf',1,1,'hoy')")
            cx.execute("INSERT INTO revision_humana(sha256,orden,campo,accion,quien,cuando) VALUES ('s',1,'monto','ausente','persona','hoy')")
            cx.commit()
            antes = cx.execute('SELECT * FROM revision_humana').fetchall()
            cx.close()
            cx = db.abrir(ruta)
            try:
                self.assertEqual(cx.execute('PRAGMA user_version').fetchone()[0], 26)
                self.assertEqual([tuple(r) for r in cx.execute('SELECT * FROM revision_humana')], antes)
                self.assertEqual(cx.execute('SELECT count(*) FROM archivo').fetchone()[0], 1)
                self.assertEqual(cx.execute('PRAGMA foreign_key_check').fetchall(), [])
                for tabla in ('renglon', 'item', 'renglon_item', 'contratacion', 'contratacion_documento', 'hallazgo'):
                    self.assertEqual(cx.execute('SELECT count(*) FROM ' + tabla).fetchone()[0], 0)
            finally:
                cx.close()

