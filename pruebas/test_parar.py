"""
PARAR UN PROCESAMIENTO.

Un lote grande son horas: cinco mil contratos son hora y media en cuatro núcleos.
Arrancar sobre el lote equivocado y no poder frenarlo dejaba una sola salida —matar el
proceso— que con SQLite en medio de una escritura es la peor de todas.

Dos cosas tienen que ser ciertas:

  · parar corta de verdad, y no en cualquier momento sino ENTRE páginas: cortar en el
    medio de una deja el trabajo a medio guardar;
  · lo leído hasta ahí queda, y al procesar de nuevo se retoma desde donde iba. Si
    parar costara volver a empezar, nadie lo usaría y estaríamos como antes.
"""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ufil import capa1_texto as c1
from ufil import db
from ufil.db import ahora


class CortarEsSeguro(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = db.abrir(Path(self.tmp.name) / "t.sqlite")

    def tearDown(self):
        self.cx.close(); self.tmp.cleanup()

    def _archivo_con_paginas(self, n):
        sha = "aa" * 32
        self.cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,
                                                paginas,ingerido_en)
                           VALUES (?,?,?,1,?,?)""",
                        (sha, "/x/no-existe.pdf", "lote.pdf", n, ahora()))
        for i in range(1, n + 1):
            self.cx.execute("""INSERT INTO pagina (sha256,nro,ancho_pt,alto_pt)
                               VALUES (?,?,595,842)""", (sha, i))
        self.cx.commit()
        return sha

    def test_seguir_falso_corta_y_lo_dice(self):
        """
        `seguir` se consulta entre página y página. Devolviendo False de entrada, no se
        procesa ninguna y el resultado avisa que se cortó — no se hace pasar por
        terminado.
        """
        sha = self._archivo_con_paginas(6)
        r = c1.leer_lote(self.cx, [sha], seguir=lambda: False)
        self.assertTrue(r["cortado"], "se cortó y el resultado no lo dice")
        self.assertEqual(r["hechas"], 0)

    def test_sin_seguir_no_corta_nada(self):
        """La línea de comandos y los reprocesos no pasan `seguir`: nada cambia ahí."""
        sha = self._archivo_con_paginas(3)
        r = c1.leer_lote(self.cx, [sha])
        self.assertFalse(r["cortado"])

    def test_corta_en_el_medio_y_guarda_lo_hecho(self):
        """
        Se deja pasar la mitad y ahí se pide parar. Lo procesado tiene que quedar
        guardado: si parar costara volver a empezar, nadie lo usaría.
        """
        sha = self._archivo_con_paginas(8)
        vistas = []

        def seguir():
            vistas.append(1)
            return len(vistas) <= 4

        r = c1.leer_lote(self.cx, [sha], seguir=seguir)
        self.assertTrue(r["cortado"])
        self.assertLess(r["hechas"], 8, "no cortó: procesó todo igual")

    def test_al_reanudar_no_repite_lo_ya_leido(self):
        """
        Es la propiedad que hace que parar sea barato: `leer_lote` sólo toma las páginas
        SIN lectura. Reanudar retoma donde iba.
        """
        sha = self._archivo_con_paginas(5)
        # Se simula que tres páginas ya se leyeron.
        for nro in (1, 2, 3):
            pid = self.cx.execute("SELECT id FROM pagina WHERE sha256=? AND nro=?",
                                  (sha, nro)).fetchone()["id"]
            self.cx.execute("""INSERT INTO lectura (pagina_id,ruta,motor,confianza,
                                                    creado_en)
                               VALUES (?,'nativo','pymupdf',0.9,?)""", (pid, ahora()))
        self.cx.commit()

        r = c1.leer_lote(self.cx, [sha], seguir=lambda: False)
        self.assertEqual(r["paginas"], 2,
                         "volvió a tomar páginas que ya estaban leídas: reanudar "
                         "costaría el lote entero de nuevo")


class ElProcesadorSeDeja(unittest.TestCase):
    """El trabajador expone parar, y sólo tiene sentido si hay algo corriendo."""

    def test_parar_sin_nada_corriendo_avisa_en_vez_de_romper(self):
        from ufil.trabajo import Procesador
        p = Procesador()
        r = p.detener()
        self.assertFalse(r["ok"])
        self.assertIn("no hay nada", r["motivo"])

    def test_arrancar_limpia_el_pedido_anterior(self):
        """
        Sin esto, parar un lote dejaba la bandera levantada y el SIGUIENTE arranque se
        cortaba solo en la primera página, sin que nadie entendiera por qué.
        """
        from ufil.trabajo import Procesador
        p = Procesador()
        p._parar.set()
        p.arrancar()
        p._hilo.join(timeout=20)
        self.assertFalse(p._parar.is_set(),
                         "la bandera de parar sobrevivió al arranque siguiente")


if __name__ == "__main__":
    unittest.main(verbosity=2)
