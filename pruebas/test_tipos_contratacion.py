import unittest

from ufil import clasificacion as cl
from ufil.capa2_campos import normalizar_cotejo


class TiposDeCompra(unittest.TestCase):
    def test_titulos_y_referencias_no_se_confunden(self):
        for titulo, tipo in [('Solicitud de provisión', 'pedido'), ('OFERTA', 'oferta'),
                             ('Cuadro comparativo', 'cuadro_comparativo'),
                             ('Dictamen de preadjudicación', 'dictamen'),
                             ('Resolución de adjudicación', 'adjudicacion'),
                             ('Orden de compra N 44', 'orden_compra'),
                             ('Orden de pago N 77 Factura B 003', 'orden_pago'),
                             ('Comprobante de transferencia', 'pago'),
                             ('Presupuesto', 'presupuesto'), ('Cotización', 'presupuesto'),
                             ('Remito N 12 Orden de compra N 44', 'remito'),
                             ('Factura B Orden de compra N 44', 'factura')]:
            with self.subTest(titulo=titulo):
                self.assertEqual(cl.clasificar_pagina(normalizar_cotejo(titulo))[0], tipo)
                self.assertIn(tipo, cl.TIPOS_PIEZA)

    def test_cuerpo_de_resolucion_no_inicia_otra_pieza(self):
        clases = cl.clasificar_documento([(1, 'RESOLUCION N 41 VISTO'),
                                         (2, 'RESUELVE ARTICULO 1'),
                                         (3, 'ARTICULO 1 CONTINUACION'),
                                         (4, 'RESOLUCION N 42 VISTO')])
        self.assertEqual(cl.tramos_por_tipo(clases, 'resolucion'), [(1, 3), (4, 4)])

    def test_un_cuerpo_aislado_sigue_siendo_visible(self):
        self.assertEqual(cl.clasificar_documento([(1, 'RESUELVE ARTICULO 1')]),
                         {1: 'resolucion'})

    def test_poco_texto_valido_no_es_foja_vacia(self):
        self.assertIsNone(cl.veredicto(cl.medir(['RECIBO', 'TOTAL', '125,00'])))
        self.assertEqual(cl.veredicto(cl.medir(['_', '.'])), cl.FOJA_EN_BLANCO)
