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
    """Corre GRUPOS, SECCIONES y seccionDe tal como están en app.js, sin copiarlos."""
    js = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")
    trozo = js[js.index("const GRUPOS = ["):js.index("/* Un ícono por sección")]
    guion = trozo + f"\nconsole.log(JSON.stringify({json.dumps(hashes)}.map(h => {{" \
                    "const s = seccionDe(h); return s ? s.id : null; })));"
    r = subprocess.run(["node", "-e", guion], capture_output=True, text=True,
                       encoding="utf-8", cwd=RAIZ)
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def seccion_del_enlace(hash_):
    js = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")
    trozo = js[js.index("const GRUPOS = ["):js.index("/* Un ícono por sección")]
    # Una entrada tiene su propio `hash` y, si agrupa pantallas, sus `items`.
    guion = trozo + f"\nconst h = {json.dumps(hash_)};" \
                    "const s = SECCIONES.find(s => s.hash === h || " \
                    "(s.items || []).some(i => i.hash === h));" \
                    "console.log(JSON.stringify(s ? s.id : null));"
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
        trozo = js[js.index("const GRUPOS = ["):js.index("/* Un ícono por sección")]
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


class LasFilasSeRecorrenConElTeclado(unittest.TestCase):
    """
    Un fiscal que revisa quinientos renglones no puede depender del mouse: con las
    flechas mueve el foco y con Enter abre la foja al lado. Para eso cada fila que se
    puede clicar tiene que poder recibir el foco, y las que no, no: una tabla de sólo
    lectura llena de paradas de tabulación es peor que ninguna.
    """

    def ejecutar(self, guion):
        import shutil
        node = shutil.which("node")
        if not node:
            self.skipTest("sin node: la parte que se ejecuta no se puede correr acá")
        js = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")
        i = js.index("function claseCol(")
        j = js.index("// `lista` marca")
        # `esc` sólo hace falta para que el código corra; lo que se comprueba acá es
        # cuáles filas pueden recibir el foco, no el escapado.
        preludio = "const esc = s => String(s ?? '');\n"
        fuente = preludio + js[i:j] + "\nreturn tr;\n}\n"
        r = subprocess.run([node, "-e", fuente + guion], capture_output=True, text=True,
                           encoding="utf-8", timeout=30)
        self.assertEqual(r.returncode, 0, "el código de la tabla no corre:\n" + r.stderr[-800:])
        return r.stdout

    def test_solo_las_filas_que_se_pueden_abrir_reciben_el_foco(self):
        cols = '[{t:"Foja",k:"f"},{t:"Tipo",k:"t"}]'
        filas = '[{f:1,t:"Factura"},{f:2,t:"Remito"}]'
        con = self.ejecutar(f'console.log(tabla({cols}, {filas}, {{alClic: () => {{}}}}));')
        sin = self.ejecutar(f'console.log(tabla({cols}, {filas}));')
        self.assertEqual(con.count('tabindex="0"'), 2,
                         "cada fila que se puede abrir tiene que poder recibir el foco")
        self.assertNotIn("tabindex", sin,
                         "una tabla que no se clica no puede llenar de paradas el tabulador")
        self.assertIn('data-i="0"', con, "la fila sigue sabiendo cuál es")


class ElRecuadroSeCentraSolo(unittest.TestCase):
    """
    El dato que se va a verificar puede ser un número de tres píxeles en una hoja
    entera. Centrarlo es la diferencia entre comprobarlo y buscarlo a mano.
    """

    def test_se_centra_en_las_dos_direcciones(self):
        js = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")
        i = js.index("const alCampo = ()")
        fuente = js[i:i + 600]
        self.assertIn("scrollIntoView", fuente)
        # Con zoom, un campo del borde derecho queda fuera de la vista aunque esté
        # centrado de arriba abajo: tiene que centrarse en las dos direcciones.
        self.assertIn("inline: 'center'", fuente, "falta el centrado horizontal")
        self.assertIn("block: 'center'", fuente, "falta el centrado vertical")


class LaFilaEnfocadaSeVeYSeAnuncia(unittest.TestCase):
    def test_el_foco_tiene_estilo_propio_y_estado_accesible(self):
        css = (RAIZ / "ufil/web/estilo.css").read_text(encoding="utf-8")
        js = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")
        self.assertIn("tr.clic:focus", css.replace(" ", ""),
                      "sin estilo de foco no se ve en qué fila se está")
        self.assertIn("aria-selected", js,
                      "un lector de pantalla tiene que poder anunciar la fila activa")


class LaInterfazTieneQuePoderCargarse(unittest.TestCase):
    """
    La prueba más barata y la que más falta hacía.

    El 22/09/2026 la aplicación estuvo rota en producción sin que ninguna prueba se
    enterara: `app.js` tenía ocho líneas huérfanas —el final duplicado de una función,
    escombro de una edición— y el navegador no ejecutaba NADA del archivo. La pantalla
    quedaba en blanco. Todas las demás pruebas de interfaz seguían en verde porque
    extraen un pedazo del archivo y lo corren suelto, así que el pedazo roto nunca se
    miraba. Un archivo que no parsea no es una pantalla con un defecto: es ninguna
    pantalla.
    """

    def test_el_javascript_de_la_aplicacion_parsea(self):
        import shutil
        node = shutil.which("node")
        if not node:
            self.skipTest("sin node: no se puede comprobar que el archivo parsee")
        ruta = RAIZ / "ufil/web/app.js"
        r = subprocess.run([node, "--check", str(ruta)], capture_output=True, text=True,
                           encoding="utf-8", timeout=60)
        self.assertEqual(r.returncode, 0,
                         "app.js no parsea, así que el navegador no ejecuta nada:\n"
                         + (r.stderr or "")[:1200])


if __name__ == "__main__":
    unittest.main()
