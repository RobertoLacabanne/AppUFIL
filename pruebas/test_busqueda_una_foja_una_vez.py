"""
Una foja aparece una vez en la búsqueda, unida al documento que la contiene.

Del legajo real: la búsqueda unía cada foja con TODOS los documentos de su archivo.
En un PDF con 161 piezas, una foja volvía 161 veces —la primera página de sesenta
resultados era la misma foja repetida— y cada copia apuntaba a un documento distinto.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from ufil import busqueda, db  # noqa: E402


class UnaFojaUnaVez(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = db.abrir(Path(self.tmp.name) / "ufil.sqlite")
        self.cx.execute("INSERT INTO archivo(sha256, nombre, ruta_original, bytes, ingerido_en) "
                        "VALUES ('a', 'Expte.pdf', 'x', 1, '2026-01-01')")
        for orden, (desde, hasta) in enumerate([(1, 2), (3, 3), (4, 6)], 1):
            self.cx.execute("INSERT INTO documento(sha256, orden, tipo, perfil, pagina_desde, "
                            "pagina_hasta) VALUES ('a', ?, 'remito', '', ?, ?)",
                            (orden, desde, hasta))
        self.cx.execute("INSERT INTO pagina_texto(texto, sha256, nro) "
                        "VALUES ('cable conductor de cobre', 'a', 3)")
        self.cx.commit()

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_la_foja_vuelve_una_vez_con_su_documento(self):
        r = busqueda.en_paginas(self.cx, "conductor")
        self.assertEqual(len(r["items"]), 1)
        doc = self.cx.execute("SELECT id FROM documento WHERE pagina_desde=3").fetchone()[0]
        self.assertEqual(r["items"][0]["documento_id"], doc)


if __name__ == "__main__":
    unittest.main()
