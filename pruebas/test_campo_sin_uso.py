"""
Un campo que un tipo de documento no tiene no va a la cola de revisión.

Del legajo real: trece «fecha de fin» de facturas esperaban que una persona confirmara
que una factura no tiene período. El perfil declara ese campo sólo por la forma del
registro, con un patrón que nunca coincide; guardarlo como nulo lo volvía trabajo.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from ufil import capa2_extraccion as c2  # noqa: E402


class UnCampoSinUsoNoEsTrabajo(unittest.TestCase):

    def test_se_reconoce_el_campo_declarado_por_la_forma(self):
        self.assertTrue(c2.sin_uso({"nombre": "fecha_fin", "patrones": ["(?!x)x"]}))
        self.assertFalse(c2.sin_uso({"nombre": "monto", "patrones": [r"\$\s*([\d.,]+)"]}))
        self.assertFalse(c2.sin_uso({"nombre": "nombre"}))

    def test_las_facturas_declaran_asi_su_fecha_de_fin(self):
        for perfil in ("factura_manual", "factura_electronica"):
            datos = json.loads((RAIZ / f"ufil/perfiles/{perfil}.json").read_text(encoding="utf-8"))
            specs = datos.get("campos_patron", []) + datos.get("campos", [])
            fin = next(s for s in specs if s["nombre"] == "fecha_fin")
            self.assertTrue(c2.sin_uso(fin), perfil)


if __name__ == "__main__":
    unittest.main()
