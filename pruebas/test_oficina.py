"""
La pantalla de la oficina: 1366×768.

Los anchos de referencia del sistema eran 1440, 1180, 1024 y 390, y ninguno es la
pantalla que hay en las oficinas de la unidad. Todo lo que esta prueba cuida apareció
recién ahí, con un legajo de verdad:

  · los tres filtros de la cola apilados en una columna de 179 px —la quinta parte del
    alto útil— para decir tres veces «todos»;
  · la prosa que explica la pantalla, cobrando dos renglones todos los días;
  · una columna de números con el rótulo pegado a la izquierda y el número a la
    derecha, a cuatrocientos píxeles, sin nada que los conecte;
  · un ítem del menú cortado al ras del borde, con media letra visible.

Lo que hay acá no reemplaza mirar la pantalla: son las reglas que la sostienen para
que no vuelvan a caerse solas.
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
HTML = (RAIZ / "ufil/web/index.html").read_text(encoding="utf-8")
LIMPIO = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), CSS, flags=re.S)


def cuerpo(caso, selector):
    m = re.search(re.escape(selector) + r"\{([^{}]*)\}", LIMPIO)
    caso.assertIsNotNone(m, f"se perdió la regla «{selector}»")
    return m.group(1).replace(" ", "").replace("\n", "")


class UnaColumnaDeNumerosSeAlineaConSuRotulo(unittest.TestCase):
    """
    En «Trabajo del equipo», el rótulo CAMPOS REVISADOS quedaba a la izquierda y su
    valor —un `1`— a la derecha, a unos cuatrocientos píxeles. El ojo no los conecta:
    parece que el 1 pertenece a otra cosa.
    """

    def test_el_rotulo_se_alinea_como_su_dato(self):
        self.assertIn("text-align:right", cuerpo(self, "thead th.num"),
                      "el rótulo de una columna de números volvió a la izquierda")

    def test_el_encabezado_lleva_la_clase_de_su_columna(self):
        """Sin eso no hay con qué alinearlo: el `<th>` no sabe qué columna es."""
        self.assertIn("claseCol(cols, c, i, filas)", APP,
                      "el encabezado dejó de llevar la clase de su columna")
        self.assertNotIn("`<th>${esc(c.t)}</th>`", APP,
                         "volvió el encabezado sin clase")

    def test_el_ancho_que_sobra_se_lo_lleva_una_sola_columna(self):
        """
        Cuatro valores cortos estirados sobre 900 px se leen peor que los mismos
        cuatro juntos a la izquierda.
        """
        self.assertIn("width:100%", cuerpo(self, "th.crece, td.crece"))
        self.assertIn("function claseCol", APP)

    def test_no_crece_una_columna_de_numeros(self):
        """Estirar una columna de números vuelve a alejar el número de su rótulo."""
        i = APP.index("function cualCrece")
        self.assertIn("num", APP[i:i + 700],
                      "la columna que crece se elige sin mirar si es de números")

    def test_crece_la_columna_de_texto_mas_largo(self):
        """
        La primera versión le daba el sobrante a la última columna que no fuera de
        números. En la tabla de contratos esa era «Fin» —una fecha de nueve
        caracteres— que se quedaba con doscientos píxeles mientras «Contratado/a» se
        apretaba y los apellidos caían en dos renglones. El sobrante tiene que ir
        donde hace falta.
        """
        i = APP.index("function cualCrece")
        cuerpo = APP[i:APP.index("function tabla(", i)]
        self.assertIn("Math.max(max", cuerpo,
                      "la columna que crece se elige por posición y no por contenido")
        self.assertIn("sinEtiquetas", cuerpo,
                      "mide el HTML y no el texto: una celda con un sello o un enlace "
                      "adentro parecería la más larga por las etiquetas")
        # Y las que nunca se parten no compiten: el ancho de más no les cambia nada y
        # se lo sacan a la que sí se estaba partiendo.
        self.assertIn("const noSeParte", cuerpo,
                      "una columna de fechas o de nombres de archivo se lleva el "
                      "sobrante mientras los apellidos caen en dos renglones")
        self.assertIn("if (cual < 0) cual = ultimaSuelta;", cuerpo,
                      "si todas son de las que no se parten, nadie absorbe y la tabla "
                      "vuelve a estirarse entera")


class LosFiltrosNoSeLlevanLaQuintaParteDeLaPantalla(unittest.TestCase):

    def test_van_plegados_salvo_que_haya_uno_puesto(self):
        self.assertIn("${hayFiltro ? ' open' : ''}", APP,
                      "los filtros volvieron a abrirse solos")

    def test_los_controles_van_adentro_de_una_fila(self):
        """
        Un `<details>` con `display:flex` NO acomoda su contenido: el navegador mete
        todo lo que sigue al `<summary>` en una caja de bloque anónima. Medido: los
        tres selectores apilados, 179 px de alto en una pantalla de 768.
        """
        self.assertIn("display:flex", cuerpo(self, ".filtros-fila"))
        self.assertIn('class="filtros-fila"', APP)
        self.assertIn("display:block", cuerpo(self, ".taller-filtros"),
                      "el <details> volvió a ser el que acomoda: no puede")


class LaProsaSeLeeUnaVez(unittest.TestCase):

    def test_se_recuerda_por_sesion(self):
        self.assertIn("function explicarUnaVez", APP)
        self.assertIn("sessionStorage", APP[APP.index("function explicarUnaVez"):][:600],
                      "se recuerda para siempre: al día siguiente hay que poder "
                      "volver a leer cómo funciona la pantalla")

    def test_sin_sessionStorage_se_explica_igual(self):
        """En una ventana privada no hay dónde recordar, y la pantalla tiene que
        seguir explicándose."""
        i = APP.index("function explicarUnaVez")
        self.assertIn("catch (e) { return true; }", APP[i:i + 600],
                      "sin sessionStorage la explicación desaparecería para siempre")


class LaBarraLateralNoCortaUnItem(unittest.TestCase):

    def test_el_desplazamiento_se_detiene_en_el_borde_de_un_item(self):
        c = cuerpo(self, ".nav-lateral")
        self.assertIn("scroll-snap-type:yproximity", c,
                      "un ítem del menú vuelve a poder quedar partido al ras del borde")
        self.assertIn("scroll-snap-align:start",
                      cuerpo(self, ".nav-lateral .grupo, .nav-lateral > a"))

    def test_en_una_pantalla_baja_la_identidad_cede_lugar(self):
        self.assertIn("@media (max-height:820px)", CSS,
                      "en 768 px de alto el membrete le sigue comiendo el lugar a la "
                      "navegación")
        i = CSS.index("@media (max-height:820px)")
        self.assertIn(".identidad-fiscales{display:none}", CSS[i:i + 400].replace(" ", ""),
                      "los fiscales son un membrete, no una herramienta: en una "
                      "pantalla baja se van, y siguen en «Acerca del sistema»")
        # Y DESPUÉS de la regla base, que declara `display:flex`: a igual
        # especificidad gana la última, y escrita antes no hace nada. Se vio en la
        # captura: los fiscales seguían ahí en 768 px de alto.
        self.assertGreater(i, CSS.index(".identidad-fiscales{margin"),
                           "la regla de pantalla baja está antes de la que pisa: no "
                           "tiene efecto")


class ElTechoNoSeLeeComoUnaTerminal(unittest.TestCase):

    def test_la_caratula_lleva_comillas_latinas(self):
        self.assertIn("function comillasLatinas", APP)
        self.assertIn("comillasLatinas(l.caratula)", APP,
                      "la carátula se muestra con las comillas rectas que se tipearon")

    def test_pero_no_se_toca_lo_que_hay_en_la_base(self):
        """Es tipografía, no una corrección del dato: en la base queda como la
        escribieron."""
        i = APP.index("function comillasLatinas")
        self.assertIn("SÓLO para mostrar", APP[max(0, i - 700):i],
                      "falta decir que no se toca el dato, y el próximo que lo lea "
                      "va a creer que puede normalizar la carátula en la base")

    def test_el_lote_no_va_en_monoespaciada(self):
        """No es un dato leído de un papel: es una etiqueta que puso una persona."""
        self.assertNotIn('id="f-lote" class="mono"', HTML,
                         "el lote volvió a la monoespaciada de los datos leídos")
        self.assertIn('<span id="f-lote">', HTML)
