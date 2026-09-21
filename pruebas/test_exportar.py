"""
Lo que sale del sistema tiene que poder verificarse contra el papel.

Una planilla con importes que no se puede volver a atar a una foja no sirve para un
escrito: quien la lee del otro lado va a preguntar de dónde salió cada número, y «del
sistema» no es una respuesta.

Y lo otro: estos informes ordenan y describen. No concluyen.
"""
from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ufil import colecciones as col, cronologia as cr, db, exportar as ex
from ufil.db import ahora

SHA = "a" * 64


def _base(tmp: Path):
    cx = db.abrir(tmp / "t.sqlite")
    cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,paginas,ingerido_en)
                  VALUES (?,'/x/expediente.pdf','expediente.pdf',1,3,?)""", (SHA, ahora()))
    for n in (1, 2, 3):
        cx.execute("INSERT INTO pagina (sha256,nro,ancho_pt,alto_pt) VALUES (?,?,595,842)",
                   (SHA, n))
    cx.commit()
    return cx


def _pieza(cx, orden, desde, tipo="factura", estado="extraido", campo=True):
    doc = cx.execute("""INSERT INTO documento (sha256,orden,clave,pagina_desde,pagina_hasta,
                                               tipo,perfil,estado)
                        VALUES (?,?,?,?,?,?,'p',?)""",
                     (SHA, orden, f"{SHA}:{desde}", desde, desde, tipo, estado)).lastrowid
    if campo:
        cx.execute("""INSERT INTO campo (documento_id,nombre,valor_literal,pagina_nro,
                                         x0,y0,x1,y1,confianza,estado)
                      VALUES (?,'monto','$ 1.000,00',?,10,10,90,30,0.9,'automatico_alta')""",
                   (doc, desde))
    cx.commit()
    return doc


def _leer_csv(ruta: Path):
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f, delimiter=";"))


class TodoLoQueSaleDiceDeDondeSalio(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.cx = _base(self.dir)
        self.d1 = _pieza(self.cx, 1, 1)
        self.d2 = _pieza(self.cx, 2, 2, tipo="contrato_obra")

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_el_indice_trae_archivo_y_fojas_de_cada_pieza(self):
        enc, filas = ex.indice_documental(self.cx)
        self.assertIn("Archivo", enc)
        self.assertIn("Fojas del PDF", enc)
        self.assertEqual(len(filas), 2)
        self.assertTrue(all(f[0] == "expediente.pdf" for f in filas))

    def test_el_indice_incluye_lo_que_el_sistema_no_sabe_leer(self):
        _pieza(self.cx, 3, 3, estado="sin_perfil", campo=False)
        _, filas = ex.indice_documental(self.cx)
        estados = {f[3] for f in filas}
        self.assertIn("sin_perfil", estados,
                      "un índice que deja afuera lo que no se supo leer no corresponde "
                      "a lo que hay en la caja")

    def test_la_foliatura_del_papel_va_al_lado_de_la_pagina_del_pdf(self):
        enc, _ = ex.indice_documental(self.cx)
        self.assertIn("Fojas del PDF", enc)
        self.assertIn("Foliatura del papel", enc)
        self.assertNotEqual(enc.index("Fojas del PDF"),
                            enc.index("Foliatura del papel"))

    def test_sin_foliatura_dice_sin_detectar_y_no_sin_foliar(self):
        _, filas = ex.indice_documental(self.cx)
        self.assertIn("(sin detectar)", {f[5] for f in filas})

    def test_la_seleccion_dice_la_foja_de_cada_dato(self):
        enc, filas = ex.seleccion(self.cx, [self.d1, self.d2])
        self.assertIn("Foja del dato", enc)
        self.assertTrue(filas)
        self.assertTrue(all(f[enc.index("Archivo")] for f in filas))

    def test_un_nulo_sale_con_su_motivo_y_no_como_celda_vacia(self):
        doc = _pieza(self.cx, 3, 3, campo=False)
        self.cx.execute("""INSERT INTO campo (documento_id,nombre,nulo_motivo,estado)
                           VALUES (?,'monto','ilegible','no_revisado')""", (doc,))
        self.cx.commit()
        enc, filas = ex.seleccion(self.cx, [doc])
        valores = [f[enc.index("Valor")] for f in filas]
        self.assertIn("Ø ilegible", valores,
                      "una celda vacía no dice si falta el dato o si no se pudo leer")


class LosArchivosQueSalen(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.cx = _base(self.dir)
        self.d1 = _pieza(self.cx, 1, 1)

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_el_csv_lo_abre_excel_en_castellano(self):
        ruta = ex.generar(self.cx, "indice", self.dir / "i.csv", formato="csv")
        crudo = open(ruta, "rb").read()
        self.assertTrue(crudo.startswith(b"\xef\xbb\xbf"),
                        "sin BOM, Excel rompe los acentos")
        filas = _leer_csv(ruta)
        self.assertEqual(filas[0][0], "Archivo")
        self.assertGreaterEqual(len(filas), 2)

    def test_el_pdf_se_genera_y_se_puede_abrir(self):
        import fitz
        ruta = ex.generar(self.cx, "indice", self.dir / "i.pdf", formato="pdf")
        self.assertTrue(ruta.exists())
        doc = fitz.open(ruta)
        texto = "".join(p.get_text() for p in doc)
        doc.close()
        self.assertIn("expediente.pdf", texto)
        self.assertIn("No saca conclusiones", texto,
                      "el pie tiene que decir qué es esto y qué no es")

    def test_un_formato_o_un_informe_inventado_se_rechazan_con_motivo(self):
        with self.assertRaises(ex.NoSePuede):
            ex.generar(self.cx, "indice", self.dir / "x", formato="docx")
        with self.assertRaises(ex.NoSePuede):
            ex.generar(self.cx, "inventado", self.dir / "x", formato="csv")

    def test_se_puede_preguntar_que_informes_hay(self):
        d = ex.disponibles()
        claves = {x["clave"] for x in d}
        self.assertIn("indice", claves)
        self.assertIn("cronologia", claves)
        self.assertIn("coleccion", claves)
        self.assertTrue(all("csv" in x["formatos"] for x in d))

    def test_cada_informe_dice_que_trae_sin_que_lo_escriba_la_pantalla(self):
        # La pantalla muestra `descripcion` tal cual. Un informe nuevo sin descripción
        # tiene que romper acá, no heredar en la interfaz una frase de otro.
        d = ex.disponibles()
        self.assertEqual({x["clave"] for x in d}, set(ex.DESCRIPCIONES))
        for x in d:
            self.assertTrue(x["descripcion"].strip(), x["clave"])
            for prohibido in ("responsab", "irregular", "sospech", "ilícit", "prueba que"):
                self.assertNotIn(prohibido, x["descripcion"].lower(),
                                 "describen lo que traen, no lo que concluyen")


class ElPunteoConservaElOrdenQueLeDioLaPersona(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.cx = _base(self.dir)
        self.d1 = _pieza(self.cx, 1, 1)
        self.d2 = _pieza(self.cx, 2, 2)
        self.c = col.crear(self.cx, "Para la audiencia", "perez.ana")
        # Se apartan al revés del orden natural, a propósito.
        col.agregar(self.cx, self.c["id"], "documento", str(self.d2), "perez.ana",
                    nota="la que discute el monto")
        col.agregar(self.cx, self.c["id"], "documento", str(self.d1), "perez.ana")

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_sale_en_el_orden_que_le_dio_la_persona(self):
        enc, filas, nombre = ex.punteo_de_coleccion(self.cx, self.c["id"])
        self.assertEqual(nombre, "Para la audiencia")
        self.assertEqual(len(filas), 2)
        self.assertEqual(filas[0][4], "la que discute el monto",
                         "el orden es el que le dio quien armó la colección")

    def test_cada_renglon_dice_archivo_y_fojas(self):
        enc, filas, _ = ex.punteo_de_coleccion(self.cx, self.c["id"])
        self.assertIn("Archivo", enc)
        self.assertIn("Fojas", enc)
        self.assertTrue(all(f[enc.index("Archivo")] == "expediente.pdf" for f in filas))

    def test_el_pdf_del_punteo_dice_que_el_orden_es_de_la_persona(self):
        import fitz
        ruta = ex.generar(self.cx, "coleccion", self.dir / "p.pdf", formato="pdf",
                          coleccion_id=self.c["id"])
        doc = fitz.open(ruta)
        texto = "".join(p.get_text() for p in doc)
        doc.close()
        self.assertIn("Para la audiencia", texto)
        self.assertIn("no uno que el", texto)

    def test_sin_coleccion_no_se_puede(self):
        with self.assertRaises(ex.NoSePuede):
            ex.generar(self.cx, "coleccion", self.dir / "p.csv", formato="csv")


class LaCronologiaYLasFichasSalenConSuFuente(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.cx = _base(self.dir)
        self.d1 = _pieza(self.cx, 1, 1)
        cr.registrar(self.cx, self.d1, "documento", "2019-03-10",
                     origen="campo:fecha_inicio", literal="10/03/2019")

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_la_cronologia_dice_que_clase_de_fecha_es_cada_una(self):
        enc, filas = ex.cronologia(self.cx)
        self.assertIn("Qué es", enc)
        self.assertIn("Como dice el papel", enc)
        self.assertEqual(filas[0][enc.index("Qué es")], "fecha del documento")
        self.assertEqual(filas[0][enc.index("Como dice el papel")], "10/03/2019")
        self.assertTrue(filas[0][enc.index("De dónde sale")].startswith("campo:"))

    def test_la_cronologia_sale_entera_y_no_hasta_un_tope(self):
        # Cortaba en 5.000 sin decirlo: un informe así afirma que no hay más hechos.
        from datetime import date, timedelta
        inicio = date(1990, 1, 1)
        self.cx.executemany(
            """INSERT INTO evento (documento_id, sha256, clase, fecha, origen)
               VALUES (?,?,'documento',?,'campo:fecha')""",
            [(self.d1, SHA, (inicio + timedelta(days=i)).isoformat())
             for i in range(6000)])
        self.cx.commit()
        total = self.cx.execute("SELECT COUNT(*) FROM evento").fetchone()[0]
        enc, filas = ex.cronologia(self.cx)
        self.assertEqual(len(filas), total)
        self.assertEqual(len(cr.linea(self.cx)), 500,
                         "la pantalla sigue paginando; sólo el informe pide todos")

    def test_las_fichas_cuentan_sin_interpretar(self):
        enc, filas = ex.fichas(self.cx)
        self.assertIn("Menciones", enc)
        self.assertIn("Documentos", enc)
        for prohibido in ("Riesgo", "Sospecha", "Irregular", "Responsable"):
            self.assertNotIn(prohibido, enc,
                             "estos informes ordenan y describen; no concluyen")


if __name__ == "__main__":
    unittest.main()
