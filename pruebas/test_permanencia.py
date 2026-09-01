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
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ufil import config, diagnostico, permanencia


class LaPermanenciaSeMideNoSeDeduce(unittest.TestCase):
    """
    La primera versión de este chequeo miraba `/proc/self/mounts` y **mentía**.

    El Dockerfile declara `VOLUME ["/app/datos"]`. El motor de contenedores crea ahí un
    volumen anónimo, que aparece en los montajes como cualquier otro… y se destruye
    junto con el contenedor, o sea en cada despliegue. El chequeo contestaba «está en
    un disco propio: sobrevive a los reinicios» sobre almacenamiento que no sobrevivía
    a ninguno, y esa respuesta tranquilizadora es peor que no tener chequeo: sin él
    alguien desconfía y baja un respaldo.

    Ahora se mide. Se deja una marca en la carpeta de datos y se cuentan los arranques
    que sobrevivió. O el archivo sigue ahí después de reiniciar, o no sigue.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._datos = config.DATOS
        self._render = os.environ.get("RENDER")
        config.DATOS = Path(self.tmp.name) / "datos"
        os.environ["RENDER"] = "true"          # se comporta como en la nube

    def tearDown(self):
        config.DATOS = self._datos
        if self._render is None:
            os.environ.pop("RENDER", None)
        else:
            os.environ["RENDER"] = self._render
        self.tmp.cleanup()

    # ── El caso que le costó el legajo a alguien ───────────────────────────
    def test_un_montaje_propio_NO_alcanza_para_decir_que_sobrevive(self):
        """
        LA prueba de esta historia. Se simula exactamente el escenario del volumen
        anónimo: la carpeta de datos está bajo un punto de montaje propio, y aun así
        se borra en cada arranque.

        El sistema NO puede decir «ok» acá. Si lo dice, alguien carga una causa encima.
        """
        montaje = self._montaje_de_verdad()
        if montaje is None:
            self.skipTest("no hay ningún punto de montaje además de / en esta máquina")
        config.DATOS = Path(montaje) / "ufil-volumen-anonimo"
        # Esta carpeta vive FUERA del directorio temporal —tiene que estar sobre un
        # montaje de verdad— así que la limpieza no la hace `tearDown`. Sin este borrado
        # inicial, la marca de la corrida anterior queda ahí y la primera vuelta arranca
        # con la cuenta heredada: la prueba pasa o falla según el orden. Pasó.
        shutil.rmtree(config.DATOS, ignore_errors=True)
        self.addCleanup(shutil.rmtree, config.DATOS, True)

        # Tres despliegues seguidos: cada uno arranca y cada uno se lleva la carpeta,
        # que es justo lo que hace un volumen anónimo.
        for _ in range(3):
            permanencia.registrar_arranque()
            r = permanencia.estado()
            self.assertNotEqual(
                r["estado"], "ok",
                "declara que los datos sobreviven sobre almacenamiento que se borra "
                "en cada arranque: es exactamente el defecto que costó un legajo")
            self.assertEqual(r["arranques"], 1)
            shutil.rmtree(config.DATOS, ignore_errors=True)   # el despliegue se la lleva

    # ── Lo que sí puede afirmar ────────────────────────────────────────────
    def test_el_primer_arranque_no_afirma_nada_todavia(self):
        permanencia.registrar_arranque()
        r = permanencia.estado()
        self.assertEqual(r["estado"], "aviso", r)
        self.assertIn("todavía no se puede afirmar", r["detalle"])
        self.assertIn("reiniciá el servicio", r["arreglo"],
                      "no dice cómo salir de la duda en dos minutos")

    def test_al_sobrevivir_un_reinicio_lo_afirma_con_el_numero(self):
        permanencia.registrar_arranque()
        permanencia.registrar_arranque()
        r = permanencia.estado()
        self.assertEqual(r["estado"], "ok", r)
        self.assertIn("comprobado", r["detalle"])
        self.assertIn("2 arranques", r["detalle"])

    def test_la_cuenta_sigue_subiendo(self):
        for _ in range(5):
            permanencia.registrar_arranque()
        self.assertEqual(permanencia.estado()["arranques"], 5)

    def test_en_una_maquina_de_escritorio_no_alarma(self):
        """El disco de una notebook ES persistente. Alarmar ahí enseña a ignorar."""
        os.environ.pop("RENDER", None)
        permanencia.registrar_arranque()
        self.assertEqual(permanencia.estado()["estado"], "ok")

    def test_si_no_puede_dejar_la_marca_es_una_falla(self):
        """Sin marca no hay medición, y sin medición no se puede afirmar nada."""
        config.DATOS.mkdir(parents=True, exist_ok=True)
        r = permanencia.estado()          # sin registrar_arranque(): no hay archivo
        self.assertEqual(r["estado"], "falla", r)

    # ── Que esté puesto donde se mira ──────────────────────────────────────
    def test_el_chequeo_esta_en_la_pantalla_de_estado_y_antes_que_el_espacio(self):
        permanencia.registrar_arranque()
        nombres = [c["nombre"] for c in diagnostico.correr(desde_web=True)]
        self.assertIn("Permanencia de los datos", nombres)
        self.assertLess(nombres.index("Permanencia de los datos"),
                        nombres.index("Espacio en disco"),
                        "el espacio libre se muestra antes que si los datos sobreviven")

    def test_lo_que_anda_mal_se_muestra_arriba(self):
        """
        Diecisiete renglones con el mismo recuadro al costado y la única diferencia en
        la palabra de adentro. Quien abre «Estado del sistema» ve diecisiete verdes y
        no encuentra el único que no lo es —y el que importa, si lo que se guarda
        sobrevive a un reinicio, es el número doce—.

        El orden lo hace la pantalla, así que se mira ahí. Y se mira que el orden
        DENTRO de cada grupo no se toque: `sort` de JavaScript es estable y hay que
        seguir usándolo así, porque una lista que se reacomoda entera cada vez que algo
        cambia de estado obliga a releerla entera.
        """
        js = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")
        css = (RAIZ / "ufil/web/estilo.css").read_text(encoding="utf-8")
        # `assertIn` sobre un archivo de tres mil líneas imprime el archivo entero
        # cuando falla, y entonces el mensaje no se puede leer. Se busca a mano y se
        # afirma un booleano, que falla con la frase y nada más.
        def hay(aguja, donde, queja):
            self.assertTrue(aguja in donde, queja + f"\n  (falta: {aguja!r})")

        hay("const PESO = {falla: 0, aviso: 1, ok: 2};", js,
            "se perdió el orden por gravedad de la lista de chequeos")
        hay("const ordenados = [...s.chequeos].sort(", js,
            "el orden tiene que hacerse sobre una COPIA: ordenar la lista del "
            "servidor en el lugar deja el arreglo pegado al objeto que se vuelve a "
            "pintar")
        hay("ordenados.map(c =>", js,
            "la tabla se sigue pintando desde la lista sin ordenar")
        # La fila que no está en verde se marca también por fuera del sello: el color
        # solo no alcanza para quien no distingue el rojo del verde.
        hay("tr.chequeo-mal td{", css,
            "la fila con problema no se distingue del resto")

    def test_el_servidor_registra_el_arranque(self):
        """
        La medición depende de que alguien deje la marca. Si el servidor deja de
        llamarla, el contador se queda en cero para siempre y el chequeo pasa a decir
        «falla» sobre una instalación sana.
        """
        fuente = (RAIZ / "ufil/servidor.py").read_text(encoding="utf-8")
        i = fuente.index("def armar(")
        self.assertIn("registrar_arranque()", fuente[i:i + 2000],
                      "el servidor ya no deja la marca al arrancar")

    @staticmethod
    def _montaje_de_verdad():
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
