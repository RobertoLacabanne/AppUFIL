"""
La retícula se defiende sola: la escala tipográfica y los estilos incrustados.

Estas dos cosas volvieron una vez y van a volver: no se rompen de golpe, se erosionan.
Alguien agrega una pantalla, necesita un rótulo «un poquito más chico», escribe
`style="font-size:12.5px"` adentro del JavaScript, y nadie lo ve nunca más porque un
estilo incrustado no lo alcanza ninguna prueba de la hoja de estilos.

Así se llegó a **veintiún tamaños distintos** sobre una escala que declara siete, y a
**noventa y ocho** atributos `style` a mano. Y esto es lo que hacía que la aplicación
se viera CASI prolija en vez de prolija: nada se ve mal por separado, pero un rótulo
de 12,5 al lado de uno de 13 y de uno de 11,5 no forma un sistema — forma tres tamaños
que el ojo registra como desalineados sin poder decir por qué.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

CSS = (RAIZ / "ufil/web/estilo.css").read_text(encoding="utf-8")
APP = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")

# Los siete pasos, y ninguno intermedio.
ESCALA = {11, 12, 13, 15, 18, 24, 34}


class LaEscalaTipograficaNoTienePasosIntermedios(unittest.TestCase):

    def test_todo_font_size_cae_en_un_paso_declarado(self):
        intrusos = []
        for n, linea in enumerate(CSS.splitlines(), 1):
            for m in re.finditer(r"font-size:\s*([0-9.]+)px", linea):
                v = float(m.group(1))
                if v not in ESCALA:
                    cerca = min(ESCALA, key=lambda p: abs(p - v))
                    intrusos.append(
                        f"  estilo.css:{n} — {m.group(1)}px no es un paso de la "
                        f"escala; el más cercano es {cerca}px")
        self.assertEqual(
            intrusos, [],
            "\naparecieron tamaños fuera de la escala "
            f"{sorted(ESCALA)}:\n" + "\n".join(intrusos))

    def test_los_pasos_estan_declarados_como_tokens(self):
        """Para poder nombrarlos. Un número suelto no se puede citar en una revisión."""
        faltan = [p for p in sorted(ESCALA) if f"--t-{p}:{p}px" not in CSS]
        self.assertEqual(faltan, [],
                         f"la escala dejó de estar declarada: faltan {faltan}")

    def test_la_prueba_esta_mirando_algo(self):
        """Si la hoja cambia de forma, esto deja de encontrar reglas y pasa siempre."""
        self.assertGreater(len(re.findall(r"font-size:\s*[0-9.]+px", CSS)), 80,
                           "la prueba se quedó sin terreno: ya casi no encuentra "
                           "declaraciones de font-size que mirar")


class ElEstiloNoSeEscribeAdentroDelJavaScript(unittest.TestCase):
    """
    Un `style="…"` en una plantilla es una excepción silenciosa al sistema: no se
    puede auditar, no se puede cambiar de una vez, y no lo alcanza ninguna prueba.

    La única excepción admitida es la GEOMETRÍA QUE SALE DE UN DATO: dónde empieza y
    dónde termina un contrato en la cronología, cuánto se lleva procesado. Eso se
    calcula con el dato en la mano y no puede vivir en la hoja de estilos. Se reconoce
    porque lleva una interpolación adentro; si alguna vez hace falta otra, que sea
    explícita y con el motivo escrito, como todo lo demás acá.
    """

    PERMITIDAS = ("left:", "width:", "top:", "height:")

    def _incrustados(self):
        return [m.group(1) for m in re.finditer(r'style="([^"]*)"', APP)]

    def test_ninguno_trae_tamano_margen_ni_relleno(self):
        malos = [e for e in self._incrustados()
                 if re.search(r"font-size|margin|padding", e)]
        self.assertEqual(
            malos, [],
            "\nvolvieron estilos de tipografía o espaciado adentro de app.js.\n"
            "  Eso vuelve a llenar la hoja de tamaños sueltos y márgenes fuera de la\n"
            "  retícula, y ninguna prueba de estilo.css los alcanza. Promovelos a\n"
            "  clase:\n" + "\n".join(f"    style=\"{e}\"" for e in malos))

    def test_los_que_quedan_son_geometria_calculada(self):
        for e in self._incrustados():
            self.assertIn("${", e,
                          f"«style=\"{e}\"» no sale de un dato: es un estilo fijo "
                          f"escrito a mano y va en estilo.css")
            self.assertTrue(
                any(e.strip().startswith(k) for k in self.PERMITIDAS),
                f"«style=\"{e}\"» calcula algo que no es una posición ni una medida; "
                f"si de verdad hace falta, agregalo a PERMITIDAS con el motivo")

    def test_no_quedaron_dos_atributos_class_en_el_mismo_elemento(self):
        """
        Al promover los estilos a clases, un reemplazo a ciegas deja
        `<div class="aviso" class="sep">`. El navegador se queda con el primero y
        descarta el segundo SIN AVISAR: la clase nueva simplemente no se aplica y la
        pantalla se ve casi bien. Pasó con catorce elementos de una sola vez.
        """
        malos = re.findall(r'<[a-z]+[^<>]*class="[^"]*"[^<>]*class="[^"]*"[^<>]*>',
                           APP, flags=re.S)
        self.assertEqual([m[:70] for m in malos], [],
                         "hay elementos con dos atributos class: el segundo se ignora")

    def test_la_etiqueta_no_quedo_pegada_al_atributo(self):
        """`<divclass="…">` no es un div: es una etiqueta inventada que no aplica nada."""
        self.assertEqual(re.findall(r"<[a-z]+class=", APP), [],
                         "quedó una etiqueta pegada a su atributo class")
