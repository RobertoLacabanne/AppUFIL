"""
Entre Ríos en la pantalla, y el rojo que no puede escaparse.

La provincia entra por dos símbolos verificables, no por decoración inventada:

  · los DOS RÍOS que le dan el nombre —el Paraná y el Uruguay—, dibujados como dos
    líneas en `--rio`, que es el token que en esta paleta ya se llamaba así;
  · la FRANJA de la bandera que diseñó Artigas en 1814, en diagonal de arriba a la
    izquierda a abajo a la derecha, en el rojo del federalismo de la Liga de los
    Pueblos Libres.

Y ahí está el problema que esta prueba existe para vigilar. La paleta tiene UNA regla
que no se negocia: el punzó es el único rojo, y significa error, conflicto o algo que
destruye. Un rojo que además sirve para «importante» o para «lindo» es un rojo que ya
no alarma a nadie, y el día que aparezca una alarma de verdad va a parecer una más.

`--federal` contra `--lapiz` da 1,45:1: como color NO se distinguen, y no hay número
que arregle eso, porque dos rojos son dos rojos. Lo que los separa es el lugar y la
forma —una diagonal de 3,5 px arriba de todo, al lado del nombre del organismo, donde
no hay ningún dato que pudiera estar en conflicto— y esa separación no la sostiene el
buen criterio de nadie a las tres de la mañana: la sostiene esto.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_accesibilidad import (  # noqa: E402
    CLARO, OSCURO, relacion, _resolver, _sin_comentarios)

CSS = (RAIZ / "ufil/web/estilo.css").read_text(encoding="utf-8")
LIMPIO = _sin_comentarios(CSS)
HTML = (RAIZ / "ufil/web/index.html").read_text(encoding="utf-8")
APP = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")

# La única regla del sistema autorizada a usar el rojo de la bandera.
UNICO_LUGAR = ".marca-provincia i"


class ElRojoFederalNoSeEscapa(unittest.TestCase):

    def _reglas_con(self, token: str) -> list[str]:
        """Los selectores de toda regla que menciona `var(--token)`."""
        fuera = []
        for regla in re.finditer(r"([^{}]+)\{([^{}]*)\}", LIMPIO):
            if f"var(--{token})" in regla.group(2):
                fuera.append(regla.group(1).strip())
        return fuera

    def test_vive_en_un_solo_lugar(self):
        usos = self._reglas_con("federal")
        self.assertEqual(
            usos, [UNICO_LUGAR],
            "el rojo de la bandera se usa fuera del bloque de identidad.\n"
            "  No es un color de la paleta: no puede tocar un dato, un sello, un "
            "filete ni un botón.\n"
            f"  Reglas que lo usan: {usos}")

    def test_el_token_existe_en_los_dos_temas(self):
        for nombre, tema in (("claro", CLARO), ("oscuro", OSCURO)):
            self.assertIn("federal", tema,
                          f"falta --federal en el tema {nombre}")

    def test_el_punzo_sigue_siendo_el_rojo_del_error(self):
        """
        Que exista un segundo rojo no puede haber aflojado al primero. El punzó tiene
        que seguir marcando lo que marcaba: alerta, conflicto y destrucción.
        """
        for clase in (".sello.alerta", ".boton.peligro", ".cifra.alerta b"):
            self.assertRegex(
                LIMPIO, re.escape(clase) + r"\s*\{[^{}]*var\(--lapiz\)",
                f"«{clase}» dejó de usar el punzó: el rojo del error se movió")

    def test_la_franja_va_inclinada_como_en_la_bandera(self):
        """
        De arriba a la izquierda a abajo a la derecha. Un rectángulo vertical girado en
        contra de las agujas del reloj —ángulo negativo— deja el extremo de arriba a la
        izquierda, que es la inclinación del pabellón. Con el signo al revés queda la
        diagonal espejada, que es la bandera de otra provincia.
        """
        m = re.search(r"\.marca-provincia i\{([^{}]*)\}", LIMPIO)
        self.assertIsNotNone(m, "se perdió la franja de la marca provincial")
        giro = re.search(r"rotate\((-?[\d.]+)deg\)", m.group(1))
        self.assertIsNotNone(giro, "la franja dejó de estar inclinada")
        self.assertLess(float(giro.group(1)), 0,
                        "la franja quedó espejada: va de arriba a la izquierda a "
                        "abajo a la derecha, como en la bandera de Entre Ríos")


class LosDosRiosVanEnElTokenDelRio(unittest.TestCase):

    def test_las_lineas_son_del_color_del_rio(self):
        m = re.search(r"\.marca-provincia\{([^{}]*)\}", LIMPIO)
        self.assertIsNotNone(m, "se perdió la marca provincial")
        # Cada línea es un degradado plano de `--rio` a `--rio`, así que el token
        # aparece dos veces por línea: se cuentan los degradados, no las menciones.
        lineas = m.group(1).count("linear-gradient(var(--rio),var(--rio))")
        self.assertEqual(lineas, 2,
                         "tienen que ser DOS líneas —el Paraná y el Uruguay— y las dos "
                         f"en --rio; encontré {lineas}")

    def test_no_lleva_informacion_para_el_lector_de_pantalla(self):
        """Es adorno. El nombre de la provincia está escrito abajo, en palabras."""
        self.assertRegex(
            HTML, r'<div class="marca-provincia" aria-hidden="true">',
            "la marca provincial tiene que estar marcada como decorativa")


class ElAnilloDeFocoSeVeEnLaBarra(unittest.TestCase):
    """
    Esto estaba mal y no lo agarraba ninguna prueba.

    El anillo iba en `--sello` para todo. Sobre el papel está perfecto (9,49:1), pero
    sobre la barra lateral —azul macizo— daba **1,28:1** en el tema claro. WCAG 1.4.11
    pide 3:1 para algo que no es texto pero informa, y esto informa lo más básico: en
    qué ítem estás parado. Lo sufría justamente quien navega con teclado.

    La tabla de pares de test_accesibilidad no lo veía porque mide colores de TEXTO
    sobre fondos, y un anillo de foco no es texto.
    """

    MINIMO = 3.0

    def _color_del_anillo(self, selector: str, tema: dict) -> str | None:
        for regla in re.finditer(r"([^{}]+)\{([^{}]*)\}", LIMPIO):
            if regla.group(1).strip() != selector:
                continue
            m = (re.search(r"outline-color:\s*([^;]+)", regla.group(2))
                 or re.search(r"outline:[^;]*?(var\(--[\w-]+\))", regla.group(2)))
            if m:
                return _resolver(m.group(1), tema)
        return None

    def test_sobre_la_barra_lateral_alcanza_3_a_1(self):
        flojos = []
        for nombre, tema in (("claro", CLARO), ("oscuro", OSCURO)):
            anillo = self._color_del_anillo("#lateral :focus-visible", tema)
            self.assertIsNotNone(
                anillo, "la barra lateral se quedó sin anillo de foco propio: vuelve a "
                        "heredar el del papel, que sobre el azul no se ve")
            for fondo in ("barra", "barra-2", "barra-3"):
                r = relacion(anillo, tema[fondo])
                if r < self.MINIMO:
                    flojos.append(f"{nombre}: el anillo ({anillo}) sobre --{fondo} "
                                  f"({tema[fondo]}) da {r:.2f}:1 y pide {self.MINIMO}:1")
        self.assertEqual(flojos, [], "\n" + "\n".join(flojos))

    def test_sobre_el_papel_tambien(self):
        flojos = []
        for nombre, tema in (("claro", CLARO), ("oscuro", OSCURO)):
            anillo = self._color_del_anillo(":focus-visible", tema)
            self.assertIsNotNone(anillo, "se perdió el anillo de foco general")
            for fondo in ("papel", "folio", "fondo", "realce"):
                r = relacion(anillo, tema[fondo])
                if r < self.MINIMO:
                    flojos.append(f"{nombre}: el anillo ({anillo}) sobre --{fondo} "
                                  f"da {r:.2f}:1 y pide {self.MINIMO}:1")
        self.assertEqual(flojos, [], "\n" + "\n".join(flojos))


class LosFiscalesSalenDeUnSoloLugar(unittest.TestCase):
    """
    Los nombres vienen de ufil/identidad.py y del endpoint. Escritos a mano en el HTML
    o en el JavaScript, cambiar de fiscal obliga a buscarlos por todos lados y el que
    queda sin cambiar es el que después aparece impreso en una presentación.
    """

    def test_no_estan_escritos_a_mano_en_la_interfaz(self):
        from ufil import identidad
        for nombre in identidad.BASE["fiscales"]:
            apellido = nombre.split()[-1]
            for archivo, texto in (("index.html", HTML), ("app.js", APP)):
                self.assertNotIn(
                    apellido, texto,
                    f"«{apellido}» está escrito a mano en {archivo}: los nombres "
                    f"salen de ufil/identidad.py")

    def test_la_barra_los_pinta_desde_el_endpoint(self):
        self.assertIn("#m-fiscales", APP,
                      "la barra lateral dejó de pintar quién firma")
        self.assertIn('id="m-fiscales"', HTML,
                      "falta el lugar donde van los fiscales en la barra")

    def test_los_dos_fiscales_de_la_unidad_estan_cargados(self):
        from ufil import identidad
        d = identidad.actual()
        self.assertEqual(len(d["fiscales"]), 2)
        self.assertIn("Badano", " ".join(d["fiscales"]))
        self.assertIn("Ramírez Montrull", " ".join(d["fiscales"]))
        # Y la firma de lo que se exporta los nombra a los dos, con «y» y no con coma.
        self.assertEqual(
            identidad.firma(d),
            "Fiscales: Gonzalo A. Badano y Juan Francisco Ramírez Montrull")
