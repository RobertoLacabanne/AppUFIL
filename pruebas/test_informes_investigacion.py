"""
Los informes que se lleva la investigación: hallazgos, precios y contrataciones.

Existían el índice, la cronología y las fichas, pero no lo central del producto: la
lista de diferencias detectadas con su cuenta, su revisión y sus fojas, los precios
leídos y las contrataciones con sus documentos. Sin ellos, el paso «generar el
informe» del flujo terminaba en un índice de piezas.
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from ufil import db, exportar as ex  # noqa: E402
from ufil import comparabilidad as cp  # noqa: E402


class LosInformesDeLaInvestigacion(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = db.abrir(Path(self.tmp.name) / "ufil.sqlite")

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_estan_ofrecidos(self):
        claves = {i["clave"] for i in ex.disponibles()}
        self.assertTrue({"hallazgos", "precios", "contrataciones"} <= claves)

    def test_salen_vacios_sin_romperse_en_los_dos_formatos(self):
        for clave in ("hallazgos", "precios", "contrataciones"):
            for formato in ("csv", "pdf"):
                f = ex.generar(self.cx, clave, Path(self.tmp.name), formato=formato)
                self.assertTrue(f.exists() and f.stat().st_size > 0, (clave, formato))

    def test_cada_fila_dice_de_donde_sale_y_nada_concluye(self):
        for clave in ("hallazgos", "precios", "contrataciones"):
            encabezados, _ = ex.INFORMES[clave][1](self.cx)
            self.assertTrue(any("Archivo" in e or "Fuentes" in e for e in encabezados), clave)
            titulo = ex.INFORMES[clave][0] + " " + ex.DESCRIPCIONES[clave]
            self.assertEqual(cp.terminos_prohibidos_en(titulo), [], clave)

    def test_el_detalle_dice_cual_es(self):
        self.assertIn("155745.00", ex._detalle_hallazgo(
            "subtotal_incorrecto", {"impreso": "155745.00"},
            {"operandos": [{"nombre": "cantidad", "valor": "76"},
                           {"nombre": "precio_unitario", "valor": "2076.60"}],
             "resultado": "157821.60"}))
        self.assertIn("ni orden compra", ex._detalle_hallazgo(
            "documento_faltante", {"etapa_presente": "factura",
                                   "etapas_no_encontradas": ["adjudicacion", "orden_compra"]}, None))


if __name__ == "__main__":
    unittest.main()
