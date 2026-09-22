"""Regresiones de forma: planillas entre encabezados y prosa, sin datos reales."""
import tempfile
import unittest
from pathlib import Path

import fitz

from ufil import tablas as tb
from ufil.capa1_texto import Palabra
from pruebas.corpus_contratacion import generar
from pruebas.test_tablas import _planilla, _parrafo


class TablasPorBloque(unittest.TestCase):
    def test_todas_las_planillas_del_corpus(self):
        with tempfile.TemporaryDirectory() as tmp:
            for nombre, ruta in generar(Path(tmp)).items():
                with self.subTest(nombre=nombre), fitz.open(ruta) as pdf:
                    palabras = [Palabra(w[4], *w[:4], 1.0) for w in pdf[0].get_text('words')]
                    tablas = tb.detectar_en_pagina(palabras)
                    if nombre == 'orden_pago':
                        self.assertEqual(tablas, [])
                        continue
                    self.assertEqual(len(tablas), 1)
                    self.assertEqual(tablas[0]['columnas'],
                                     4 if nombre in ('pedido', 'remito') else 6)
                    self.assertEqual(tablas[0]['filas'], 4)

    def test_dos_bloques_separados_no_se_funden(self):
        palabras = _planilla()
        palabras += [Palabra(p.texto, p.x0, p.y0 + 150, p.x1, p.y1 + 150, p.conf)
                     for p in _parrafo()]
        palabras += [Palabra(p.texto, p.x0, p.y0 + 300, p.x1, p.y1 + 300, p.conf)
                     for p in _planilla()]
        ts = tb.detectar_en_pagina(palabras)
        self.assertEqual([(t['filas'], t['columnas']) for t in ts], [(5, 4), (5, 4)])

    def test_pocas_filas_en_mucha_prosa(self):
        palabras = _parrafo() + [Palabra(p.texto, p.x0, p.y0 + 150, p.x1,
                                         p.y1 + 150, p.conf) for p in _planilla()]
        self.assertEqual([(t['filas'], t['columnas']) for t in tb.detectar_en_pagina(palabras)],
                         [(5, 4)])
