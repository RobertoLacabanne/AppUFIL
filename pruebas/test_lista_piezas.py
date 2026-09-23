"""La lista de todos los documentos: paginada, filtrable por tipo, con la cuenta de cada tipo."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from ufil import db, listas_api as la  # noqa: E402


class LaListaDeDocumentos(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = db.abrir(Path(self.tmp.name) / "ufil.sqlite")
        self.cx.execute("INSERT INTO archivo(sha256, nombre, ruta_original, bytes, ingerido_en) "
                        "VALUES ('a', 'Expte 1.pdf', 'x', 1, '2026-01-01')")
        for i, tipo in enumerate(["orden_compra", "orden_compra", "remito"]):
            self.cx.execute("INSERT INTO documento(sha256, orden, clave, tipo, perfil, pagina_desde, "
                            "pagina_hasta, estado) VALUES ('a', ?, ?, ?, '', ?, ?, 'sin_perfil')",
                            (i, f"k{i}", tipo, i + 1, i + 1))

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_cuenta_filtra_y_pagina(self):
        r = la.resolver(self.cx, "/api/piezas", {"limite": "1"})
        self.assertEqual(r["total"], 3)
        self.assertEqual(len(r["piezas"]), 1)
        self.assertEqual({t["tipo"]: t["cantidad"] for t in r["tipos"]},
                         {"orden_compra": 2, "remito": 1})
        r = la.resolver(self.cx, "/api/piezas", {"tipo": "remito"})
        self.assertEqual(r["total"], 1)
        self.assertEqual(r["filtros_aplicados"], {"tipo": "remito"})


if __name__ == "__main__":
    unittest.main()
