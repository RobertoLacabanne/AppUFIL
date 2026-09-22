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
    def test_importe_incierto_respeta_cantidad_y_exige_moneda_en_cada_fila(self):
        def celdas(filas):
            return [dict(fila=f, columna=c, texto=t, es_encabezado=0)
                    for f, fila in enumerate(filas) for c, t in enumerate(fila)]
        cs = celdas([('Cable', '$ 100'), ('Cinta', '$ 200'), ('Tubo', '300')])
        roles = rg.columnas(cs)
        self.assertEqual(roles, {'descripcion': 0, 'importe_incierto': 1})
        self.assertNotIn('importe_incierto', rg.valores_fila({c['columna']: c for c in cs if c['fila'] == 2}, roles))
        # Una cantidad y unidad expresas mantienen la extracción anterior.
        cs = celdas([('Cable', '2', 'un', '$ 100,00'), ('Cinta', '3', 'un', '$ 200,00')])
        self.assertEqual(rg.columnas(cs), {'unidad': 2, 'descripcion': 0, 'cantidad': 1})
        # También se excluye la cantidad fundida con la descripción por OCR.
        cs = celdas([('2,00 Cable', '$ 100'), ('3,00 Cinta', '$ 200')])
        roles = rg.columnas(cs)
        for f in (0, 1):
            self.assertNotIn('importe_incierto', rg.valores_fila({c['columna']: c for c in cs if c['fila'] == f}, roles))

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

    def test_notacion_de_la_tabla_y_lo_que_queda_sin_leer(self):
        """
        Parte del legajo real está impresa con coma de miles y punto decimal.

        Medido sobre una copia del legajo real: los 64 renglones de órdenes de compra
        estaban sin precio con motivo «ilegible» teniendo el precio impreso en la celda
        (`5,087.30`), porque el lector sólo aceptaba notación argentina. El número es
        prueba, así que se lee sólo cuando no hay ambigüedad; lo demás queda sin leer.
        """
        celda = lambda t, f=0, c=0: dict(fila=f, columna=c, texto=t, es_encabezado=0, x0=c*100)
        # 1. Con los dos separadores manda el último, en cualquiera de las dos notaciones.
        self.assertEqual(rg.decimal_argentino('5,087.30'), Decimal('5087.30'))
        self.assertEqual(rg.decimal_argentino('5.087,30'), Decimal('5087.30'))
        self.assertEqual(rg.decimal_argentino('1,349,145.00'), Decimal('1349145.00'))
        # 2. Con un separador y dos decimales decide la tabla, no el token.
        self.assertEqual(rg.decimal_argentino('1.905,60'), Decimal('1905.60'))
        self.assertIsNone(rg.decimal_argentino('1905.60'), 'sola, la notación ajena no se supone')
        self.assertEqual(rg.decimal_argentino('1905.60', '.'), Decimal('1905.60'))
        # La notación sale de los tokens inequívocos de la misma tabla.
        self.assertEqual(rg.notacion_tabla([celda('5,087.30'), celda('1905.60', 1)]), '.')
        self.assertEqual(rg.notacion_tabla([celda('5.087,30'), celda('1905,60', 1)]), ',')
        self.assertEqual(rg.notacion_tabla([celda('Tubo'), celda('1905,60', 1)]), ',',
                         'sin evidencia se mantiene la notación argentina')
        # 3. Tres decimales exactos son miles, no fracción, en las dos notaciones.
        self.assertEqual(rg.decimal_argentino('1,349'), Decimal('1349'))
        self.assertEqual(rg.decimal_argentino('1.349'), Decimal('1349'))
        # 4. Una tabla con las dos notaciones no resuelve nada: lo ambiguo no se lee.
        mezclada = [celda('5,087.30'), celda('5.087,30', 1)]
        self.assertIsNone(rg.notacion_tabla(mezclada))
        self.assertIsNone(rg.decimal_argentino('1905.60', rg.notacion_tabla(mezclada)))
        self.assertIsNone(rg.decimal_argentino('1905,60', rg.notacion_tabla(mezclada)))
        self.assertEqual(rg.decimal_argentino('5,087.30', rg.notacion_tabla(mezclada)),
                         Decimal('5087.30'), 'lo inequívoco se sigue leyendo')

    def test_una_tabla_en_notacion_ajena_da_precio_y_conserva_el_literal(self):
        """Como la orden de compra real de la foja 7: cantidad, unitario y total."""
        cs = []
        for fila, valores in enumerate([('80', 'UNIDAD', 'Conductor', '5,087.30', '406,984.00'),
                                        ('200', 'UNIDAD', 'Conductor', '2,451.90', '490,380.00')]):
            for col, t in enumerate(valores):
                cs.append(dict(fila=fila, columna=col, texto=t, es_encabezado=0, x0=col*100))
        filas = rg.filas_por_cuenta(cs)
        self.assertEqual(len(filas), 2)
        notacion = rg.notacion_tabla(cs)
        self.assertEqual(rg.valor_celda(filas[0]['precio'], notacion), Decimal('5087.30'))
        self.assertEqual(filas[0]['precio']['texto'], '5,087.30', 'el literal impreso se conserva')
        self.assertEqual(rg.valor_celda(filas[0]['subtotal'], notacion), Decimal('406984.00'))

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

    def lista_sin_encabezado(self, filas):
        t = self.cx.execute("SELECT t.* FROM tabla t JOIN documento d ON d.id=t.documento_id WHERE d.tipo='presupuesto' LIMIT 1").fetchone()
        self.cx.execute('DELETE FROM tabla_celda WHERE tabla_id=?', (t['id'],))
        for f, textos in enumerate(filas):
            for col, texto in enumerate(textos):
                self.cx.execute('''INSERT INTO tabla_celda(tabla_id,fila,columna,texto,x0,y0,x1,y1,confianza)
                                   VALUES (?,?,?,?,?,?,?,?,1)''',
                                (t['id'], f, col, texto, col*200, 100+f*20, col*200+180, 115+f*20))
        self.cx.commit()
        rg.extraer_archivo(self.cx, t['sha256'], por_ruta={'nativo': []})
        return [dict(r) for r in self.cx.execute('SELECT * FROM renglon WHERE tabla_id=? AND vigente=1 ORDER BY fila', (t['id'],))]

    def test_lista_con_moneda_conserva_importe_sin_inventar_unitario(self):
        filas = [('FUtucelula 10A 220V con ', '$ 36.334,08)'),
                 ('Cinta alsladora TELA x 1', '$ 22.708,80'),
                 ('Cinta aísladora PVC x 20', '$ 30.278,40'),
                 ('Bornera 4 x 25 A con Tor', '$ 14.382,40)')]
        rs = self.lista_sin_encabezado(filas)
        self.assertEqual(len(rs), 4)
        for r, (desc, importe) in zip(rs, filas):
            self.assertEqual(r['desc_literal'], desc)
            self.assertEqual(r['precio_literal'], importe)
            self.assertIsNone(r['precio_unitario'])
            self.assertEqual(r['precio_motivo'], 'rol_incierto')
            self.assertFalse(r['precio_derivado'])
            self.assertIsNone(r['subtotal'])
            fuente = rg.fuente(self.cx, r, 'precio')
            self.assertEqual(fuente['pagina_nro'], r['pagina_nro'])
            celda = self.cx.execute('SELECT * FROM tabla_celda WHERE id=?', (fuente['celdas'][0],)).fetchone()
            self.assertEqual(celda['texto'], importe)
            self.assertEqual(fuente['region']['x0'], celda['x0'])
        comp = precios.comparar(self.cx, self.factura()['id'])
        ids = {r['id'] for r in rs}
        self.assertFalse(ids & {r['renglon']['id'] for r in comp['referencias']})
        self.assertEqual(ids, {r['renglon']['id'] for r in comp['excluidas'] if r['renglon']['id'] in ids})

    def test_lista_ambigua_o_sin_evidencia_no_genera_renglones(self):
        for filas in [
                [('Cable', '$ 10,00', '$ 20,00'), ('Cinta', '$ 15,00', '$ 30,00')],
                [('Cable', '$ 10,00', '20,00'), ('Cinta', '$ 15,00', '30,00')],
                [('Cable', '10,00'), ('Cinta', '15,00')],
                [('Cable', '$ 10,00')],
                [('Cable', '$ 10,00'), ('Cinta', 'sin importe')]]:
            with self.subTest(filas=filas):
                self.assertEqual(self.lista_sin_encabezado(filas), [])

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
        # La factura del corpus no dice «pesos» ni «IVA incluido», pero sí lo dice de
        # las dos formas en que lo dice una factura argentina: el «$» de los importes y
        # la letra B. Ver docs/contrataciones-y-precios.md §2.2.
        self.assertEqual(r['moneda'], 'ARS')
        self.assertEqual(r['iva'], 'incluido')
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
        # Cuando el papel no dice nada —ni «$», ni letra de factura, ni «pesos»— no hay
        # con qué afirmar que es el mismo producto: se borran los atributos del renglón
        # analizado y de sus referencias.
        self.cx.execute("UPDATE renglon SET moneda=NULL, iva=NULL")
        self.cx.commit()
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

