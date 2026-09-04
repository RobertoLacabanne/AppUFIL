"""
Entre Ríos en la pantalla, y el rojo que no puede escaparse.

Antes la provincia entraba por dos símbolos dibujados a mano —dos líneas por el Paraná
y el Uruguay, y la franja de Artigas cruzándolas en diagonal—. Llegó el isotipo oficial
del organismo y esa marca de la casa se fue: eran tres maneras apiladas de decir de
quién es esto, y a 13 px de alto la diagonal roja se leía como un tachado.

Lo que NO se fue es la regla que aquella marca obligó a escribir, y que ahora hay que
sostener contra un archivo en vez de contra dos reglas de CSS.

**Acá el color significa estado.** El verde quiere decir «dato firme». El punzó quiere
decir «las dos lecturas no coinciden». El isotipo trae adentro un celeste, un verde y
un rojo institucionales; si alguno se convierte en color de interfaz, en la misma
pantalla van a convivir dos verdes —o dos rojos— que quieren decir cosas distintas, y
el operador va a tener que aprender cuál es cuál a las tres de la mañana.

Entonces los colores de la marca viven adentro del isotipo, que es un archivo, y no
entran a la hoja de estilos. Esta prueba los lee del archivo instalado —no de una
lista escrita acá, que envejece el día que cambie el logotipo— y verifica que ninguno
aparezca en `estilo.css`. Lo único que sí se alinea es el marino, porque no lleva
estado: es cromo.
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

ISOTIPO = RAIZ / "assets/marca/logo.svg"


class ElSegundoRojoNoVolvio(unittest.TestCase):
    """
    `--federal` era el rojo de la franja de Artigas, y existía para una sola regla.
    Con el isotipo oficial esa regla se borró y el token quedó sin uso, así que se
    fue con ella. Que no vuelva: contra el punzó da 1,45:1 —dos rojos son dos rojos,
    y no hay número que arregle eso— y lo único que los separaba era el lugar.
    """

    def test_el_token_no_esta_en_la_hoja(self):
        usos = [n for n, linea in enumerate(LIMPIO.splitlines(), 1)
                if "--federal" in linea]
        self.assertEqual(
            usos, [],
            f"volvió --federal a estilo.css (líneas {usos}).\n"
            "  El rojo de la bandera vive adentro del isotipo, que es un archivo.\n"
            "  Un segundo rojo en la hoja vuelve a poner al operador a distinguir\n"
            "  cuál de los dos quiere decir «conflicto».")

    def test_el_punzo_sigue_siendo_el_rojo_del_error(self):
        """
        Que exista un segundo rojo no puede haber aflojado al primero. El punzó tiene
        que seguir marcando lo que marcaba: alerta, conflicto y destrucción.
        """
        for clase in (".sello.alerta", ".boton.peligro", ".cifra.alerta b"):
            self.assertRegex(
                LIMPIO, re.escape(clase) + r"\s*\{[^{}]*var\(--lapiz\)",
                f"«{clase}» dejó de usar el punzó: el rojo del error se movió")


class LaPaletaInstitucionalNoSeVuelvePaletaDeInterfaz(unittest.TestCase):
    """
    Llegó el logotipo oficial del MPF Entre Ríos y con él la tentación de repintar la
    aplicación con sus colores. No se puede, y el motivo es de fondo, no de gusto.

    **Acá el color significa estado.** El verde quiere decir «dato firme». El punzó
    quiere decir «las dos lecturas no coinciden». Si el verde institucional #1C8F80
    entra como color de interfaz, en la misma pantalla conviven dos verdes que quieren
    decir cosas distintas y el operador tiene que aprender cuál es cuál. Lo mismo con
    el rojo #EA3F3F al lado del punzó #A81F26. Una aplicación institucional se ve
    institucional porque lleva bien la marca, no porque se pinte con sus colores.

    Y además ninguno de los tres podría ser texto: medidos sobre el papel #FFFDF8 dan
    3,01:1 el celeste, 3,90:1 el verde y 3,91:1 el rojo, contra los 4,5 que pide AA.
    El único que entra es el MARINO #011E3F, y entra porque no lleva estado: es cromo.

    Es la misma regla que ya cuida al dorado y al rojo de la bandera, aplicada al
    logotipo. Los colores viven adentro del isotipo —un archivo— y no en la hoja.
    """

    def _colores_de_la_marca(self) -> set[str]:
        """
        Los colores se leen DEL ARCHIVO instalado, no de una lista escrita acá.

        Escritos a mano, la lista queda vieja el día que cambie el logotipo —y una
        prueba que vigila colores que ya no existen no vigila nada—. El blanco queda
        afuera: es el ojo del isotipo, y prohibir el blanco en una hoja de estilos no
        tiene sentido.
        """
        svg = ISOTIPO.read_text(encoding="utf-8")
        return {c.upper() for c in re.findall(r"#[0-9a-fA-F]{6}", svg)} - {"#FFFFFF"}

    def test_la_marca_trae_los_colores_que_hay_que_vigilar(self):
        """Si el archivo dejara de traer colores, la prueba de abajo pasaría sola."""
        self.assertGreaterEqual(
            len(self._colores_de_la_marca()), 3,
            "el isotipo tiene que traer sus colores adentro; si no, la prueba que "
            "los mantiene fuera de la hoja de estilos no está probando nada")

    def test_ninguno_aparece_en_la_hoja_de_estilos(self):
        # Sin los comentarios: el motivo por el que estos tres NO entran está escrito
        # en la hoja, con los tres hex adentro, y buscarlos en crudo los encuentra ahí.
        # Se reemplaza cada comentario por saltos de línea para no correr la numeración.
        limpio = re.sub(r"/\*.*?\*/",
                        lambda m: "\n" * m.group(0).count("\n"), CSS, flags=re.S)
        intrusos = []
        for n, linea in enumerate(limpio.splitlines(), 1):
            for color in self._colores_de_la_marca():
                if color.lower() in linea.lower():
                    intrusos.append(f"  estilo.css:{n} — {color}, que es de la marca")
        self.assertEqual(
            intrusos, [],
            "\nun color de la paleta institucional se volvió color de interfaz.\n"
            "  Acá el color significa estado: dos verdes o dos rojos en la misma "
            "pantalla\n  obligan a aprender cuál es cuál.\n" + "\n".join(intrusos))

    def test_el_marino_si_entro_y_es_el_cromo(self):
        """Lo único que se alinea, porque no lleva estado."""
        for token in ("--tribunal:#011E3F", "--barra:#011E3F"):
            self.assertTrue(token in CSS.replace(" ", ""),
                            f"el cromo dejó de estar alineado con el marino oficial "
                            f"({token})")

    def test_alinearlo_mejoro_el_contraste_y_no_lo_empeoro(self):
        """
        El cambio tenía que ser gratis. Si alguna vez deja de serlo, esta prueba lo
        dice en vez de dejarlo pasar por venir «del manual».
        """
        for texto, minimo, que in (("barra-txt", 12.0, "el texto de la barra"),
                                   ("barra-txt-2", 7.5, "los rótulos de grupo"),
                                   ("oro", 6.5, "el anillo de foco")):
            r = relacion(CLARO[texto], CLARO["barra"])
            self.assertGreaterEqual(
                r, minimo,
                f"{que} sobre la barra da {r:.2f}:1 y con el azul viejo daba más: "
                f"alinear con la marca no puede costar contraste")


class ElIsotipoOficialEsElQueManda(unittest.TestCase):
    """
    Reemplazó al ícono genérico de documento y a la marca provincial dibujada a mano.
    Lo que esta clase cuida son las cuatro maneras de arruinarlo:

      · usar el logotipo entero, con el nombre adentro, sobre la barra marina —donde
        el wordmark, que también es marino, desaparece—;
      · recolorearlo para que se vea, que es intervenir una marca institucional;
      · aplastarlo dándole ancho y alto a la vez;
      · achicarlo abajo del tamaño donde los anillos concéntricos se funden.

    Y la quinta, que es la que ya pasó una vez: que se apilen tres maneras de decir
    de quién es esto y ninguna lo diga bien.
    """

    def test_el_archivo_esta_y_es_vectorial(self):
        self.assertTrue(ISOTIPO.is_file(),
                        "falta assets/marca/logo.svg; ver el LEEME de esa carpeta")
        self.assertIn("<svg", ISOTIPO.read_text(encoding="utf-8")[:400])

    def test_es_el_isotipo_y_no_el_logotipo_con_el_texto(self):
        """
        El logotipo completo lleva el nombre en marino y sobre la barra marina no se
        ve. Si alguna vez alguien copia `logotipo.svg` encima de `logo.svg`, esto lo
        agarra: el isotipo no tiene ni una letra adentro.
        """
        svg = ISOTIPO.read_text(encoding="utf-8")
        for marca, que in (("<text", "un bloque de texto"),
                           ("font-family", "una tipografía"),
                           ("<tspan", "un renglón de texto")):
            self.assertNotIn(marca, svg,
                             f"el archivo de la barra trae {que}: es el logotipo "
                             f"completo, no el isotipo. El nombre va al lado, "
                             f"compuesto en la tipografía de la aplicación.")

    def test_el_alto_alcanza_para_que_se_lean_los_anillos(self):
        """
        Medido sobre el marino: a 28 px los anillos concéntricos se funden en una
        mancha, a 36 es marginal, a 48 se lee entero. El piso es 40.
        """
        m = re.search(r"\.isotipo\{([^{}]*)\}", LIMPIO)
        self.assertIsNotNone(m, "se perdió la regla del isotipo")
        alto = re.search(r"height:(\d+)px", m.group(1))
        self.assertIsNotNone(alto, "el isotipo tiene que tener un alto declarado")
        self.assertGreaterEqual(
            int(alto.group(1)), 40,
            "abajo de 40 px los anillos del isotipo se funden en una mancha. "
            "Si no entra en el ancho de la barra, la salida no es achicarlo.")

    def test_no_se_deforma(self):
        """
        Alto fijo y ancho automático. Con los dos puestos, cualquier cambio del
        archivo lo estira, y estirar una marca institucional no se hace.
        """
        m = re.search(r"\.isotipo\{([^{}]*)\}", LIMPIO)
        cuerpo = m.group(1)
        self.assertIn("width:auto", cuerpo.replace(" ", ""),
                      "sin `width:auto` el flex de al lado le come el ancho y lo aplasta")
        self.assertIn("flex:none", cuerpo.replace(" ", ""),
                      "sin `flex:none` el isotipo se encoge cuando el nombre no entra")

    def test_la_marca_dibujada_a_mano_se_fue_entera(self):
        """
        No alcanza con sacarla del HTML: el CSS huérfano y el comentario que la
        explicaba envejecen peor que el código, porque el próximo que los lea los va
        a tomar por especificación.
        """
        for nombre, texto in (("estilo.css", CSS), ("index.html", HTML),
                              ("app.js", APP)):
            self.assertNotIn("marca-provincia", texto,
                             f"quedó rastro de la marca provincial en {nombre}")

    def test_el_monograma_sigue_de_respaldo(self):
        """
        El isotipo es material del organismo y no todas las instalaciones lo van a
        tener. Sin archivo, la barra tiene que seguir teniendo cara: manda el
        monograma, que está dibujado adentro del HTML y no depende de nada.
        """
        self.assertIn('id="monograma"', HTML)
        for evento in ("'load'", "'error'"):
            self.assertIn(f"addEventListener({evento}", APP,
                          f"nadie escucha {evento} sobre el isotipo")
        # Y una decisión inmediata además de los eventos: app.js se carga al final del
        # cuerpo, así que la imagen puede haber terminado antes de que nadie escuche.
        # Sólo con los eventos, el isotipo no aparecía nunca en una máquina rápida.
        self.assertIn("naturalWidth", APP,
                      "sin mirar la imagen ya cargada, el `load` puede haber pasado "
                      "antes de que app.js llegue a escucharlo")


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


class LaMarcaSaleDelServidorPorUnaSolaPuerta(unittest.TestCase):
    """
    El isotipo, el ícono de la pestaña y el del acceso directo del teléfono son la
    misma marca en tres formatos, y salen todos por `/marca`. Tres rutas distintas
    para lo mismo es cómo se termina con una apuntando a un archivo que ya no está.

    Y las tres tienen que contestar 404 —no 500, no una página en blanco— cuando la
    marca no está puesta: hay instalaciones que no la van a tener, y ahí manda el
    monograma.
    """

    @classmethod
    def setUpClass(cls):
        import tempfile
        import threading
        from http.server import ThreadingHTTPServer
        from ufil import config, db, servidor
        cls.tmp = tempfile.TemporaryDirectory()
        cls._datos, cls._marca = config.DATOS, config.MARCA
        config.DATOS = Path(cls.tmp.name)
        config.activar_legajo(None)
        db.abrir(Path(cls.tmp.name) / "ufil.sqlite").close()
        servidor.RUTA_BASE = None
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), servidor.Manejador)
        cls.puerto = cls.srv.server_address[1]
        cls.hilo = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.hilo.start()

    @classmethod
    def tearDownClass(cls):
        from ufil import config
        cls.srv.shutdown(); cls.srv.server_close(); cls.hilo.join(timeout=5)
        config.DATOS, config.MARCA = cls._datos, cls._marca
        cls.tmp.cleanup()

    def _pedir(self, ruta):
        import urllib.error
        import urllib.request
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{self.puerto}{ruta}", timeout=10) as r:
                return r.status, r.headers.get("Content-Type", ""), r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Content-Type", ""), e.read()

    def test_las_tres_puertas_entregan_el_archivo(self):
        from ufil import config
        config.MARCA = RAIZ / "assets/marca"
        try:
            for ruta, esperado in (("/marca", b"<?xml"),
                                   ("/marca?que=icono", b"\x89PNG"),
                                   ("/marca?que=tactil", b"\x89PNG")):
                estado, tipo, cuerpo = self._pedir(ruta)
                self.assertEqual(estado, 200, f"«{ruta}» no entregó la marca")
                self.assertTrue(cuerpo.startswith(esperado),
                                f"«{ruta}» entregó otra cosa: {cuerpo[:16]!r}")
                self.assertNotIn("json", tipo,
                                 f"«{ruta}» contestó un JSON en vez de una imagen")
        finally:
            config.MARCA = self._marca

    def test_sin_marca_puesta_contesta_404_y_no_se_cae(self):
        import tempfile
        from ufil import config
        config.MARCA = Path(tempfile.mkdtemp())
        try:
            for ruta in ("/marca", "/marca?que=icono", "/marca?que=tactil"):
                estado, _, _ = self._pedir(ruta)
                self.assertEqual(estado, 404,
                                 f"«{ruta}» sin archivo tiene que contestar 404: la "
                                 f"pantalla se entera así de que manda el monograma")
        finally:
            config.MARCA = self._marca

    def test_la_pantalla_pide_por_esas_mismas_puertas(self):
        """Una ruta que nadie pide y una pantalla que pide una ruta que no existe."""
        self.assertIn('src="/marca"', HTML, "la barra dejó de pedir el isotipo")
        self.assertIn('href="/marca?que=tactil"', HTML)
        self.assertIn("'/marca?que=icono'", APP)
