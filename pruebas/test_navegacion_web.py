"""
Cada pantalla marca la sección de la navegación donde está su enlace.

La papelera figuraba en «Sistema» y además en el `tambien` de «Documentos»: al abrirla
se marcaba Documentos, donde el enlace no está, y la persona no veía desde dónde había
llegado. Y con la paginación apareció otra forma de lo mismo: `#/papelera?desde=100` no
coincidía con ninguna sección y la navegación quedaba sin marcar.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


def seccion_de(*hashes):
    """Corre SECCIONES y seccionDe tal como están en app.js, sin copiarlos."""
    js = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")
    trozo = js[js.index("const SECCIONES = ["):js.index("/* Un ícono por sección")]
    guion = trozo + f"\nconsole.log(JSON.stringify({json.dumps(hashes)}.map(h => {{" \
                    "const s = seccionDe(h); return s ? s.id : null; })));"
    r = subprocess.run(["node", "-e", guion], capture_output=True, text=True,
                       encoding="utf-8", cwd=RAIZ)
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def seccion_del_enlace(hash_):
    js = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")
    trozo = js[js.index("const SECCIONES = ["):js.index("/* Un ícono por sección")]
    guion = trozo + f"\nconst s = SECCIONES.find(s => (s.items || []).some(i => i.hash === " \
                    f"{json.dumps(hash_)})); console.log(JSON.stringify(s ? s.id : null));"
    r = subprocess.run(["node", "-e", guion], capture_output=True, text=True,
                       encoding="utf-8", cwd=RAIZ)
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


class LaNavegacionMarcaDondeEstaElEnlace(unittest.TestCase):

    def test_la_papelera_marca_la_seccion_de_su_enlace(self):
        donde = seccion_del_enlace("#/papelera")
        self.assertIsNotNone(donde, "la papelera no tiene enlace en la navegación")
        self.assertEqual(seccion_de("#/papelera"), [donde])

    def test_una_pagina_con_query_marca_la_misma_seccion(self):
        sin, con = seccion_de("#/papelera", "#/papelera?desde=100")
        self.assertEqual(sin, con)
        sin, con = seccion_de("#/cronologia", "#/cronologia?desde=2019-01-01")
        self.assertIsNotNone(sin)
        self.assertEqual(sin, con)

    def test_ninguna_ruta_queda_en_dos_secciones(self):
        # Un enlace en `items` de una sección y en `tambien` de otra es exactamente lo
        # que hacía marcar la sección equivocada.
        js = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")
        trozo = js[js.index("const SECCIONES = ["):js.index("/* Un ícono por sección")]
        guion = trozo + """
          const dueno = {};
          for (const s of SECCIONES)
            for (const h of [...(s.items || []).map(i => i.hash), ...(s.tambien || [])])
              (dueno[h] = dueno[h] || []).push(s.id);
          console.log(JSON.stringify(Object.entries(dueno).filter(([, v]) => v.length > 1)));"""
        r = subprocess.run(["node", "-e", guion], capture_output=True, text=True,
                           encoding="utf-8", cwd=RAIZ)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), [])


if __name__ == "__main__":
    unittest.main()
