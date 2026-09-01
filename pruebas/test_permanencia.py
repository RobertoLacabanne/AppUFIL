"""
QUE EL TRABAJO NO SE PIERDA.

Es la única falla de todo el sistema que no se ve venir. Un servicio de nube sin disco
montado anda perfecto: guarda los PDF, arma las bases, muestra los totales bien, deja
revisar campo por campo durante dos días. Y en el próximo despliegue la carpeta vuelve
a estar vacía. Nadie se entera hasta que abre la aplicación y el legajo no está.

Lo que se pierde no es simétrico. Los PDF se pueden volver a subir y las imágenes de
página se rehacen procesando de nuevo. **Las revisiones hechas a mano no**: son horas
de alguien mirando un folio y decidiendo, y no hay de dónde sacarlas otra vez.

Por eso el sistema tiene que SABER si sus datos sobreviven a un reinicio, y decirlo
antes de que alguien cargue una causa. Estas pruebas verifican que lo sepa.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ufil import config, diagnostico


class ElSistemaSabeSiSusDatosSobreviven(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._datos = config.DATOS
        self._render = os.environ.get("RENDER")
        config.DATOS = Path(self.tmp.name) / "datos"

    def tearDown(self):
        config.DATOS = self._datos
        if self._render is None:
            os.environ.pop("RENDER", None)
        else:
            os.environ["RENDER"] = self._render
        self.tmp.cleanup()

    def test_en_un_contenedor_sin_disco_propio_es_una_falla(self):
        """
        No un aviso: una falla. «Aviso» es lo que se lee y se sigue de largo, y acá
        seguir de largo cuesta el trabajo de dos días.
        """
        os.environ["RENDER"] = "true"
        r = diagnostico._persistencia()
        self.assertEqual(r["estado"], "falla", r)
        self.assertIn("SE BORRA", r["detalle"])
        self.assertTrue(r["arreglo"], "una falla sin arreglo deja a la persona igual")
        self.assertIn("disco", r["arreglo"].lower())

    def test_dice_qué_es_lo_que_no_se_puede_recuperar(self):
        """
        «Se pierden los datos» no alcanza para entender el tamaño. Los PDF se vuelven a
        subir; las revisiones hechas a mano no existen en ningún otro lado.
        """
        os.environ["RENDER"] = "true"
        r = diagnostico._persistencia()
        self.assertIn("revisiones hechas a mano", r["detalle"])

    def test_en_una_maquina_de_escritorio_no_alarma(self):
        """El disco de una notebook ES persistente. Alarmar ahí enseña a ignorar."""
        os.environ.pop("RENDER", None)
        r = diagnostico._persistencia()
        self.assertEqual(r["estado"], "ok", r)

    def test_con_un_disco_montado_lo_reconoce(self):
        """
        Un punto de montaje que contiene la carpeta de datos significa que hay un
        volumen atrás. Se busca el más específico: en un contenedor TODO está debajo de
        «/», así que quedarse con el primero que aparezca daría siempre «hay disco».
        """
        montaje = self._algun_montaje_de_verdad()
        if montaje is None:
            self.skipTest("no hay ningún punto de montaje además de / en esta máquina")
        os.environ["RENDER"] = "true"
        config.DATOS = Path(montaje) / "ufil-prueba"
        r = diagnostico._persistencia()
        self.assertEqual(r["estado"], "ok", r)
        self.assertIn(montaje, r["detalle"])

    @staticmethod
    def _algun_montaje_de_verdad():
        """
        Un punto de montaje donde de verdad se pueda crear una carpeta.

        `os.access(..., W_OK)` no alcanza: `/proc` lo pasa y después no deja crear
        nada. La única comprobación que no miente es intentarlo.
        """
        try:
            with open("/proc/self/mounts", encoding="utf-8") as f:
                candidatos = [l.split()[1] for l in f if len(l.split()) > 1]
        except OSError:
            return None
        for m in candidatos:
            if m == "/":
                continue
            try:
                d = Path(m) / "ufil-prueba"
                d.mkdir(parents=True, exist_ok=True)
                d.rmdir()
                return m
            except OSError:
                continue
        return None

    def test_el_chequeo_esta_en_la_pantalla_de_estado(self):
        """
        Que exista la función no sirve si no la corre nadie. Y va ANTES del espacio
        libre: de nada sirve saber que entran diez mil páginas si se borran en el
        próximo despliegue.
        """
        nombres = [c["nombre"] for c in diagnostico.correr(desde_web=True)]
        self.assertIn("Permanencia de los datos", nombres)
        self.assertLess(nombres.index("Permanencia de los datos"),
                        nombres.index("Espacio en disco"),
                        "el espacio libre se muestra antes que si los datos sobreviven")

    def test_una_falla_de_permanencia_impide_decir_que_todo_esta_bien(self):
        os.environ["RENDER"] = "true"
        r = diagnostico.resumen(diagnostico.correr(desde_web=True))
        self.assertFalse(r["puede_trabajar"],
                         "el sistema se declara listo mientras los datos se borran")


class AbrirLaAppSinLegajoNoEsUnError(unittest.TestCase):
    """
    La cookie que recuerda qué legajo está abierto muere con el navegador, a propósito:
    en una máquina compartida una causa no puede quedar abierta hasta mañana. Así que
    entrar sin legajo es lo NORMAL, no una falla.

    Contestarlo con un cartel en el medio de una pantalla vacía se lee como que el
    sistema se rompió —o peor, como que los legajos se perdieron, cuando están todos a
    un clic—. Al abrir se va derecho a donde se elige uno.
    """

    JS = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")

    def test_la_primera_pantalla_manda_a_elegir_legajo(self):
        i = self.JS.index("async function rutear()")
        cuerpo = self.JS[i:i + 2500]
        self.assertIn("PRIMERA_PANTALLA", cuerpo,
                      "el ruteo dejó de distinguir la primera pantalla de las demás")
        self.assertIn("location.hash = '#/legajos'", cuerpo,
                      "abrir sin legajo ya no lleva a elegir uno")

    def test_adentro_de_la_sesion_sigue_explicando(self):
        """
        Ir a Contratos con la app ya abierta es otra cosa: pediste algo puntual y falta
        un paso. Ahí sí corresponde el cartel, con el botón para darlo.
        """
        self.assertIn("vistaSinLegajo", self.JS)
        i = self.JS.index("function vistaSinLegajo")
        self.assertIn("Elegir o crear un legajo", self.JS[i:i + 900],
                      "el cartel dejó de ofrecer cómo salir de ahí")

    def test_la_pantalla_de_legajos_avisa_si_el_disco_no_guarda(self):
        i = self.JS.index("async function vLegajos()")
        cuerpo = self.JS[i:i + 3000]
        self.assertIn("permanencia", cuerpo,
                      "la pantalla donde se crea un legajo no mira si los datos "
                      "sobreviven")


if __name__ == "__main__":
    unittest.main()
