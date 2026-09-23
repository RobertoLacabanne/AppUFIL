"""
El panel no puede decir que se leyó lo que no se leyó.

Encontrado en un legajo real: decía «1.628 páginas leídas» contando todas las fojas,
cuando 340 no se habían leído nunca. Quien mira el panel concluye que el legajo está
entero leído, busca, no encuentra, y cree que no está: es la confusión entre «no hay» y
«todavía no se miró» que el sistema existe para evitar.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from ufil import db
from ufil.db import ahora

SHA = "d" * 64


class ElPanelDiceCuantoSeLeyo(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = db.abrir(Path(self.tmp.name) / "t.sqlite")
        self.cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,paginas,ingerido_en)
                           VALUES (?,'/x/a.pdf','a.pdf',1,3,?)""", (SHA, ahora()))
        for n in (1, 2, 3):
            pid = self.cx.execute("INSERT INTO pagina (sha256,nro) VALUES (?,?)", (SHA, n)).lastrowid
            if n < 3:
                self.cx.execute("""INSERT INTO lectura (pagina_id,ruta,motor,version,confianza,ms,creado_en)
                                   VALUES (?,'ocr_a','tesseract','5',0.9,1,?)""", (pid, ahora()))
        self.cx.commit()

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_la_api_separa_fojas_de_fojas_leidas(self):
        from ufil import servidor
        p = servidor.api_panel(self.cx)
        self.assertEqual(p["paginas"], 3)
        self.assertEqual(p["paginas_leidas"], 2)

    def test_la_pantalla_muestra_las_leidas_y_no_el_total(self):
        app = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")
        i = app.index("cifra('Fojas leídas'")
        self.assertIn("p.paginas_leidas", app[i:i + 120],
                      "el rótulo «Fojas leídas» tiene que ir con las fojas que tienen lectura")


if __name__ == "__main__":
    unittest.main()
