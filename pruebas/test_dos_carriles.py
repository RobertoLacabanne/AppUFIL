"""
Que el dato y la conjetura NO se vean iguales.

Es la regla fundacional del sistema: lo que el sistema leyó de un papel y lo que el
sistema supone son dos cosas distintas, y tienen que distinguirse de un vistazo, sin
leer la etiqueta. De esa distinción depende qué se puede sumar y llevar a un informe.

Esta prueba existe por un accidente concreto. Se agregó una baldosa de fondo a las
cifras del panel —`.cifra{background:var(--realce)}`, para que siete ceros sueltos
dejaran de parecer una pantalla rota— y esa baldosa llegó también al total FIRME, que
hasta entonces iba sin fondo. Como `--realce` y `--interp` son los dos un azul apenas,
el total firme y el provisional quedaron con el mismo fondo, uno al lado del otro. No
falló ninguna prueba: el contraste del texto seguía perfecto, la separación entre
carriles no la miraba nadie. Se vio en una captura de pantalla, de casualidad.

En el tema oscuro era peor: `--folio` #141E2B contra `--interp` #131E2A daban
**1,003:1**, o sea el mismo color.

Lo que se mide acá es la separación entre los dos fondos, en los dos temas. No es un
criterio de WCAG —AA no dice nada sobre distinguir dos superficies— así que el piso lo
fijamos nosotros en 1,10:1, que es aproximadamente lo que el tema claro venía teniendo
y se ve. Por debajo de eso son el mismo color con otro nombre.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Se reusan el lector de paleta y el medidor de contraste: son los mismos, y dos
# copias de la misma cuenta se despegan la primera vez que una se corrige.
from test_accesibilidad import (  # noqa: E402
    CLARO, OSCURO, CSS, relacion, _resolver, _sin_comentarios)

SEPARACION_MINIMA = 1.10
LIMPIO = _sin_comentarios(CSS)


def fondo_de(selector: str, tema: dict) -> str | None:
    """El fondo que declara una regla, resuelto a #rrggbb."""
    for regla in re.finditer(r"([^{}]+)\{([^{}]*)\}", LIMPIO):
        if regla.group(1).strip() != selector:
            continue
        m = re.search(r"(?<![-\w])background(?:-color)?:\s*([^;]+)", regla.group(2))
        if m:
            return _resolver(m.group(1).split()[0], tema)
    return None


# (carril del dato, carril de la conjetura, dónde se ve)
CARRILES = [
    (".cifra.firme", ".cifra.provisional",
     "los dos totales del panel, uno al lado del otro"),
    (".carril--dato", ".carril--interp",
     "los dos carriles de la pantalla de interpretación"),
]


class ElDatoYLaConjeturaNoSeVenIgual(unittest.TestCase):

    def _revisar(self, tema, nombre):
        problemas = []
        for dato, conjetura, donde in CARRILES:
            a, b = fondo_de(dato, tema), fondo_de(conjetura, tema)
            self.assertIsNotNone(a, f"«{dato}» dejó de declarar un fondo medible")
            self.assertIsNotNone(b, f"«{conjetura}» dejó de declarar un fondo medible")
            r = relacion(a, b)
            if r < SEPARACION_MINIMA:
                problemas.append(
                    f"{nombre}: «{dato}» ({a}) y «{conjetura}» ({b}) se separan "
                    f"{r:.3f}:1 y hace falta {SEPARACION_MINIMA}:1 — {donde}")
        self.assertEqual(problemas, [], "\n" + "\n".join(problemas))

    def test_tema_claro(self):
        self._revisar(CLARO, "claro")

    def test_tema_oscuro(self):
        self._revisar(OSCURO, "oscuro")


class ElColorNoEsLoUnicoQueLosSepara(unittest.TestCase):
    """
    Quien no distingue el azul del papel tiene que poder separarlos igual. Los dos
    carriles llevan además un filete al costado, y los filetes tienen que ser de
    colores distintos: si los dos fueran del mismo, el filete no agrega nada.

    El costado no es siempre el mismo: el carril del dato va a la izquierda de la
    pantalla y lleva su filete a la DERECHA, contra el carril de al lado. Por eso se
    mira cualquiera de los dos costados y no `border-left` a secas.
    """

    def _filete(self, selector: str, tema: dict) -> str | None:
        for regla in re.finditer(r"([^{}]+)\{([^{}]*)\}", LIMPIO):
            if regla.group(1).strip() != selector:
                continue
            m = re.search(r"border-(?:left|right):\s*[\d.]+px\s+\w+\s+([^;]+)",
                          regla.group(2))
            if m:
                return _resolver(m.group(1), tema)
        return None

    def test_cada_carril_lleva_su_propio_filete(self):
        for nombre, tema in (("claro", CLARO), ("oscuro", OSCURO)):
            for dato, conjetura, donde in CARRILES:
                a, b = self._filete(dato, tema), self._filete(conjetura, tema)
                self.assertIsNotNone(a, f"«{dato}» se quedó sin filete al costado")
                self.assertIsNotNone(b, f"«{conjetura}» se quedó sin filete al costado")
                self.assertNotEqual(
                    a, b, f"{nombre}: «{dato}» y «{conjetura}» llevan el mismo filete "
                          f"{a}, así que el color es lo único que los separa — {donde}")


class LaPruebaEstaMirandoAlgo(unittest.TestCase):
    """
    Todo esto busca selectores por su texto exacto. Si a alguno le cambian el nombre,
    `fondo_de` devuelve None y la prueba de arriba revienta con un mensaje claro —pero
    sólo si los selectores siguen existiendo en el archivo—. Que se note.
    """

    def test_los_selectores_existen(self):
        for dato, conjetura, _ in CARRILES:
            for sel in (dato, conjetura):
                self.assertIn(sel + "{", LIMPIO.replace(" {", "{"),
                              f"«{sel}» ya no está en el CSS: la prueba se quedó sin "
                              f"terreno y hay que apuntarla al selector nuevo")
