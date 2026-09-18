"""
La cronología: qué pasó y cuándo, que no es el orden en que están las fojas.

Un documento no tiene «una fecha». Tiene la del papel, la de la firma, la del sello de
recepción, la de la notificación, la del hecho que relata y la de su incorporación.
Mezclarlas arma una línea de tiempo que no corresponde a nada.

Y el orden cronológico no es el orden físico: un expediente se arma por incorporación,
así que lo que se agrega último puede relatar lo que pasó primero.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ufil import cronologia as cr, db
from ufil.db import ahora

SHA = "a" * 64


def _base(tmp: Path):
    cx = db.abrir(tmp / "t.sqlite")
    cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,paginas,ingerido_en)
                  VALUES (?,'/x/e.pdf','e.pdf',1,3,?)""", (SHA, ahora()))
    for n in (1, 2, 3):
        cx.execute("INSERT INTO pagina (sha256,nro,ancho_pt,alto_pt) VALUES (?,?,595,842)",
                   (SHA, n))
    cx.commit()
    return cx


def _pieza(cx, orden, desde, tipo="contrato_obra"):
    doc = cx.execute("""INSERT INTO documento (sha256,orden,clave,pagina_desde,pagina_hasta,
                                               tipo,perfil)
                        VALUES (?,?,?,?,?,?,'p')""",
                     (SHA, orden, f"{SHA}:{desde}", desde, desde, tipo)).lastrowid
    cx.commit()
    return doc


def _campo_fecha(cx, doc, nombre, literal, norm, estado="automatico_alta"):
    cid = cx.execute("""INSERT INTO campo (documento_id,nombre,valor_literal,pagina_nro,
                                           x0,y0,x1,y1,confianza,estado)
                        VALUES (?,?,?,1,10,10,100,30,0.9,?)""",
                     (doc, nombre, literal, estado)).lastrowid
    cx.execute("INSERT INTO normalizacion (campo_id,tipo,valor_norm) VALUES (?,'fecha',?)",
               (cid, norm))
    cx.commit()
    return cid


class CadaFechaEsUnaCosaDistinta(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = _base(Path(self.tmp.name))
        self.doc = _pieza(self.cx, 1, 1)

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_una_pieza_puede_tener_varias_fechas_y_no_se_mezclan(self):
        cr.registrar(self.cx, self.doc, "documento", "2019-03-10", origen="campo:x")
        cr.registrar(self.cx, self.doc, "firma", "2019-04-02", origen="campo:x")
        cr.registrar(self.cx, self.doc, "recepcion", "2019-05-20", origen="campo:x")
        fechas = cr.de_documento(self.cx, self.doc)
        self.assertEqual(len(fechas), 3)
        self.assertEqual([f["clase"] for f in fechas],
                         ["documento", "firma", "recepcion"])
        self.assertEqual(fechas[0]["que_es"], "fecha del documento")

    def test_una_fecha_sin_fuente_no_entra(self):
        with self.assertRaises(cr.NoSePuede):
            cr.registrar(self.cx, self.doc, "documento", "2019-03-10", origen="")

    def test_no_se_le_puede_poner_una_clase_inventada(self):
        with self.assertRaises(cr.NoSePuede):
            cr.registrar(self.cx, self.doc, "cualquiera", "2019-03-10", origen="campo:x")

    def test_cargarla_a_mano_queda_auditado(self):
        cr.poner_a_mano(self.cx, self.doc, "hecho", "2019-01-05", "perez.ana",
                        literal="5 de enero de 2019")
        f = cr.de_documento(self.cx, self.doc)[0]
        self.assertEqual((f["clase"], f["origen"], f["quien"]),
                         ("hecho", "humano", "perez.ana"))
        self.assertEqual(
            self.cx.execute("SELECT COUNT(*) FROM auditoria WHERE accion='fechar'"
                            ).fetchone()[0], 1)


class ArmarlaConLoQueYaSeLeyo(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = _base(Path(self.tmp.name))
        self.doc = _pieza(self.cx, 1, 1)

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_toma_las_fechas_extraidas_y_conserva_el_literal(self):
        _campo_fecha(self.cx, self.doc, "fecha_inicio", "10/03/2019", "2019-03-10")
        r = cr.poblar_desde_campos(self.cx)
        self.assertEqual(r["eventos"], 1)
        f = cr.de_documento(self.cx, self.doc)[0]
        self.assertEqual(f["fecha"], "2019-03-10")
        self.assertEqual(f["literal"], "10/03/2019",
                         "el literal del papel viaja con la fecha normalizada")
        self.assertTrue(f["origen"].startswith("campo:"))

    def test_una_fecha_dudosa_no_entra_en_la_linea_de_tiempo(self):
        _campo_fecha(self.cx, self.doc, "fecha_inicio", "10/03/2019", "2019-03-10",
                     estado="pendiente_baja")
        r = cr.poblar_desde_campos(self.cx)
        self.assertEqual(r["eventos"], 0,
                         "en una línea de tiempo una fecha dudosa se lee igual que una "
                         "segura, y eso es justo lo que no puede pasar")

    def test_no_pisa_lo_que_cargo_una_persona(self):
        cr.poner_a_mano(self.cx, self.doc, "documento", "2019-01-01", "perez.ana")
        _campo_fecha(self.cx, self.doc, "fecha_inicio", "10/03/2019", "2019-03-10")
        cr.poblar_desde_campos(self.cx)
        fechas = [f for f in cr.de_documento(self.cx, self.doc) if f["clase"] == "documento"]
        self.assertEqual(len(fechas), 1)
        self.assertEqual(fechas[0]["fecha"], "2019-01-01")
        self.assertEqual(fechas[0]["origen"], "humano")

    def test_volver_a_poblar_no_duplica(self):
        _campo_fecha(self.cx, self.doc, "fecha_inicio", "10/03/2019", "2019-03-10")
        cr.poblar_desde_campos(self.cx)
        cr.poblar_desde_campos(self.cx)
        self.assertEqual(len(cr.de_documento(self.cx, self.doc)), 1)


class LaLineaDeTiempoNoEsElOrdenDeLasFojas(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = _base(Path(self.tmp.name))
        # La pieza que está PRIMERA en el expediente relata un hecho POSTERIOR.
        self.d1 = _pieza(self.cx, 1, 1)
        self.d2 = _pieza(self.cx, 2, 2)
        cr.registrar(self.cx, self.d1, "documento", "2021-06-01", origen="campo:x")
        cr.registrar(self.cx, self.d2, "documento", "2019-02-15", origen="campo:x")

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_sale_ordenada_por_fecha_y_no_por_foja(self):
        l = cr.linea(self.cx)
        self.assertEqual([e["fecha"] for e in l], ["2019-02-15", "2021-06-01"])
        self.assertEqual(l[0]["documento_id"], self.d2,
                         "la pieza que está segunda en el expediente es la primera en "
                         "el tiempo, y la cronología tiene que decir eso")

    def test_se_puede_acotar_por_fecha_y_por_clase(self):
        cr.registrar(self.cx, self.d1, "firma", "2021-07-01", origen="campo:x")
        self.assertEqual(len(cr.linea(self.cx, desde="2021-01-01")), 2)
        self.assertEqual(len(cr.linea(self.cx, clases=("firma",))), 1)
        with self.assertRaises(cr.NoSePuede):
            cr.linea(self.cx, clases=("inventada",))

    def test_cada_hecho_viene_con_su_fuente(self):
        for e in cr.linea(self.cx):
            self.assertTrue(e["origen"], "una cronología sin fuentes es una lista de "
                                         "afirmaciones sin respaldo")
            self.assertTrue(e["archivo"])

    def test_señala_una_fecha_imposible_sin_interpretarla(self):
        cr.registrar(self.cx, self.d1, "firma", "2021-05-01", origen="campo:x")
        d = [x for x in cr.desordenes(self.cx) if x["clase"] == "fecha_imposible"]
        self.assertEqual(len(d), 1)
        self.assertIn("anterior", d[0]["detalle"])

    def test_señala_el_desorden_fisico_como_lo_que_es(self):
        d = [x for x in cr.desordenes(self.cx) if x["clase"] == "fuera_de_orden"]
        self.assertEqual(len(d), 1)
        self.assertIn("incorporación", d[0]["detalle"],
                      "estar fuera de orden es normal en un expediente armado por "
                      "incorporación: se señala, no se denuncia")


if __name__ == "__main__":
    unittest.main()
