"""
CONTRASTE, medido. WCAG 2.1 nivel AA.

Esto lo va a usar gente que trabaja ocho horas frente a la pantalla, en oficinas con
luz de tubo y monitores viejos, y algunas de esas personas no distinguen el rojo del
verde. «Se ve bien» no es una medición: el contraste se calcula.

AA pide:
  · 4,5:1 para texto normal;
  · 3:1 para texto grande (24px, o 18,66px en negrita);
  · 3:1 para el borde de un control —un campo de formulario cuyo límite no se ve es un
    campo que alguien no encuentra— (criterio 1.4.11, «contraste de lo que no es texto»).
    Los filetes decorativos quedan afuera del criterio a propósito: son adorno, no
    información, y subirles el contraste ensucia la página sin que nadie gane nada.

Se miden los pares que EXISTEN en la interfaz, en los dos temas.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

CSS = (RAIZ / "ufil/web/estilo.css").read_text(encoding="utf-8")


def _rgb(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def luminancia(color: str) -> float:
    def canal(v: int) -> float:
        x = v / 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(v) for v in _rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def relacion(a: str, b: str) -> float:
    la, lb = luminancia(a), luminancia(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _bloque(desde: str) -> str:
    """
    El bloque que arranca en `desde`, hasta su llave de cierre.

    Leer hasta el final del archivo se traga el `@media print`, que redefine `--tinta`
    a negro puro y da contrastes de fantasía. Me pasó midiendo esto: el tema oscuro
    daba 1,16:1 en un par que en realidad da 12,76:1.
    """
    i = CSS.index(desde) + len(desde)
    return CSS[i:CSS.index("}", i)]


def paleta(desde: str) -> dict[str, str]:
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6})", _bloque(desde)))


CLARO = paleta(":root{")
OSCURO = paleta(':root[data-tema="oscuro"]{')

# (texto, fondo, mínimo, dónde se ve)
PARES = [
    ("tinta",   "papel",       4.5, "texto normal"),
    ("tinta",   "papel-2",     4.5, "texto sobre bloque gris"),
    ("tinta-2", "papel",       4.5, "prosa secundaria"),
    ("tinta-2", "papel-2",     4.5, "prosa secundaria sobre gris"),
    ("tinta-3", "papel",       3.0, "rótulos y marginalia"),
    ("sello",   "papel",       4.5, "enlaces y sellos"),
    ("sello",   "papel-2",     4.5, "enlaces sobre gris"),
    ("verde",   "papel",       4.5, "sello «al día»"),
    ("ambar",   "papel",       4.5, "sello de atención"),
    ("lapiz",   "papel",       4.5, "sello de alerta"),
    ("lapiz",   "lapiz-suave", 4.5, "aviso de datos de demostración"),
    ("tinta",   "lapiz-suave", 4.5, "texto del aviso de demostración"),
    ("papel",   "lapiz",       4.5, "número sobre el chip rojo de la barra"),
    ("tinta",   "interp",      4.5, "carril de interpretación"),
    ("tinta-2", "interp",      4.5, "prosa del carril de interpretación"),
    ("sello",   "sello-suave", 4.5, "aviso de foja enderezada"),
    # 1.4.11: el límite de un control tiene que verse, y una barra que informa algo
    # también. La cronología dice qué contratos se pisan: es información, no adorno.
    ("borde-control", "papel",   3.0, "borde de campos, selectores y botones"),
    ("borde-control", "papel-2", 3.0, "borde de controles sobre gris"),
    ("marca",         "papel",   3.0, "barra de contrato en la cronología"),
    ("marca-solape",  "papel",   3.0, "barra de superposición en la cronología"),
]


class ElContrasteAlcanzaAA(unittest.TestCase):

    def _revisar(self, tema, nombre):
        flojos = []
        for texto, fondo, minimo, donde in PARES:
            self.assertIn(texto, tema, f"falta --{texto} en el tema {nombre}")
            self.assertIn(fondo, tema, f"falta --{fondo} en el tema {nombre}")
            r = relacion(tema[texto], tema[fondo])
            if r < minimo:
                flojos.append(f"{nombre}: --{texto} sobre --{fondo} da {r:.2f}:1 y "
                              f"pide {minimo}:1 ({donde})")
        self.assertEqual(flojos, [], "\n" + "\n".join(flojos))

    def test_tema_claro(self):
        self._revisar(CLARO, "claro")

    def test_tema_oscuro(self):
        self._revisar(OSCURO, "oscuro")

    def test_los_dos_temas_definen_lo_mismo(self):
        """
        Un token que existe en un tema y no en el otro se resuelve al valor del claro
        y queda ilegible sobre fondo oscuro. Es el defecto que no se ve hasta que
        alguien prende el modo oscuro.
        """
        self.assertEqual(sorted(CLARO), sorted(OSCURO),
                         "los dos temas tienen que definir exactamente los mismos tokens")


class LoQueNoSeDiceSoloConColor(unittest.TestCase):
    """
    Un estado que se distingue SÓLO por el color no existe para quien no distingue ese
    color, ni en una impresión en blanco y negro — y esto se imprime. Cada estado lleva
    además una palabra.
    """

    def test_los_sellos_llevan_texto_ademas_del_color(self):
        js = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")
        # ESTADO mapea cada estado a [etiqueta, tono]: la etiqueta es la palabra.
        estados = re.search(r"const ESTADO = \{(.*?)\n\};", js, re.S)
        self.assertIsNotNone(estados, "no está la tabla de estados")
        from ufil import confianza as cf
        for e in cf.TODOS:
            m = re.search(rf"{e}:\s*\[\s*'([^']+)'", estados.group(1))
            self.assertIsNotNone(m, f"«{e}» no tiene etiqueta en la interfaz")
            self.assertGreater(len(m.group(1)), 2,
                               f"«{e}» se distingue sólo por el color")

    def test_la_tabla_de_salud_no_usa_un_icono_de_color(self):
        """La primera columna de «Estado del sistema» es un sello con palabra."""
        self.assertIn("un sello, no un ícono de color", CSS,
                      "se perdió la razón por la que el estado del sistema usa sellos "
                      "con texto y no puntos de color")

    def test_los_controles_tienen_su_propio_token_de_borde(self):
        """
        Un control se distingue de un filete decorativo. Si los campos volvieran a usar
        `--filete`, su borde daría 1,57:1 y quedaría por debajo del mínimo sin que nada
        falle a la vista.
        """
        for regla in ("input[type=text]{", ".form-legajo input{", ".filtros-cola select{"):
            i = CSS.index(regla)
            cuerpo = CSS[i:CSS.index("}", i)]
            self.assertIn("var(--borde-control)", cuerpo,
                          f"«{regla}» usa un filete decorativo como borde de control")


class SeVeEnUnTelefono(unittest.TestCase):
    """44 px es la medida abajo de la cual se falla el toque."""

    def test_los_controles_tienen_tamano_de_dedo(self):
        movil = CSS[CSS.index("@media (max-width:720px){"):]
        self.assertRegex(movil, r"\.boton,\s*\.tecla,\s*\.chip\{min-height:44px",
                         "los botones dejaron de tener 44 px en un teléfono")
        self.assertRegex(movil, r"input,\s*select,\s*textarea\{min-height:44px",
                         "los campos dejaron de tener 44 px en un teléfono")

    def test_el_tipo_de_los_campos_evita_el_zoom_de_ios(self):
        """Con menos de 16px, iOS hace zoom al tocar un campo y descuadra la pantalla."""
        self.assertIn("font-size:16px", CSS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
