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


class ElAnchoNoCambiaAlCambiarDePantalla(unittest.TestCase):
    """
    Esto era lo que se veía como «se rompe, como que se hace un zoom».

    La página entera scrollea con la barra del navegador. El panel es largo y la barra
    aparece; «Trabajo del equipo» entra en una pantalla y la barra se va. En 1366×768,
    medido: la columna de contenido pasaba de 1119 px a 1134 y volvía a 1119 en cada
    salto de pantalla. Quince píxeles, pero se los lleva TODO —la caja de búsqueda de
    arriba, el ancho de la hoja, el reparto de columnas de cada tabla—, así que ir de
    una pantalla a otra hacía correr el contenido de costado y reacomodarse.

    Reservar el lugar de la barra siempre lo deja en 1119 en las diez pantallas,
    incluso con la foja abierta o la cola adentro, que apagan el scroll de la página.
    """

    def test_el_lugar_de_la_barra_esta_siempre_reservado(self):
        self.assertIn("scrollbar-gutter:stable", cuerpo(self, "html"),
                      "sin esto el ancho de la hoja cambia según la pantalla tenga "
                      "barra de scroll o no")

    def test_y_es_una_regla_de_base_y_no_de_una_pantalla_sola(self):
        """
        Adentro de un `@media` arregla una pantalla y deja saltando a las demás, que
        es exactamente el problema.
        """
        antes = LIMPIO[:LIMPIO.index("html{scrollbar-gutter:stable}")]
        self.assertEqual(antes.count("{") - antes.count("}"), 0,
                         "la reserva quedó adentro de un @media: arregla una pantalla "
                         "y deja saltando a las demás")

    def test_la_franja_que_sobra_se_pinta_del_papel_que_tiene_al_lado(self):
        """
        La cola es la única pantalla que pinta de lado a lado, y de las que no
        scrollean: ahí los 15 px reservados quedan a la vista. El lienzo de la ventana
        lo pinta el `body`, así que del mismo papel la franja no se ve.
        """
        self.assertIn("body.taller-abierto{background-color:var(--folio)}",
                      LIMPIO.replace(" ", ""),
                      "la franja reservada vuelve a verse como una costura contra el "
                      "papel del taller")

    def test_con_la_foja_abierta_la_franja_acompaña_al_visor(self):
        plano = LIMPIO.replace(" ", "")
        self.assertIn("body.con-visor{background-color:var(--fondo)}", plano)
        # A igual peso gana la última: escrita antes de la del taller no haría nada
        # justo en el caso que importa, que es abrir la foja desde la cola.
        self.assertGreater(plano.index("body.con-visor{background-color"),
                           plano.index("body.taller-abierto{background-color"),
                           "la regla del visor está antes que la del taller: con la "
                           "foja abierta desde la cola no tiene efecto")

    def test_se_pinta_el_color_y_no_el_atajo(self):
        """
        Con el atajo `background` se va la textura de papel del fondo, que está en una
        regla aparte y en `background-image`.
        """
        plano = LIMPIO.replace(" ", "")
        for regla in ("body.taller-abierto{background:", "body.con-visor{background:"):
            self.assertNotIn(regla, plano,
                             "con el atajo se pierde la textura del papel: va "
                             "`background-color`")


class UnaTablaCortadaLoDice(unittest.TestCase):
    """
    Nueve columnas de contratos piden 957 px y en 1366×768 la hoja les da 875. La
    tabla se corta: «Conf.» queda entera afuera y de «Monto» se ve `$74.200,0`.

    Correrla de costado siempre se pudo —`overflow-x:auto`—, pero la barra que lo
    dice está al pie de cincuenta y un renglones. Y el problema no es la incomodidad:
    un importe cortado a la mitad no se ve cortado. Se lee como un número entero que
    no es el que dice el papel, que es justo lo que el sistema no puede hacer.

    La sombra aparece sola del lado donde hay más tabla y se va sola cuando no la hay.
    Medido en 1366: sin correr, sombra a la derecha y nada a la izquierda; corrida
    hasta el final, al revés; en el medio, las dos; y en una tabla que entra —«Trabajo
    del equipo»— ninguna.
    """

    def cuatro_capas(self):
        return cuerpo(self, ".tabla-env")

    def test_las_tapas_viajan_con_el_contenido(self):
        """
        Ancladas al contenido (`local`), las tapas del color del folio llegan al borde
        justo cuando se acabó la tabla, y ahí tapan la sombra. Sin esto la sombra
        queda prendida siempre y deja de significar «hay más».
        """
        capas = self.cuatro_capas()
        self.assertEqual(capas.count("no-repeatlocal"), 2,
                         "faltan las dos tapas ancladas al contenido: la sombra se "
                         "queda prendida aunque no haya más tabla")
        self.assertEqual(capas.count("var(--folio)"), 2,
                         "las tapas tienen que ser del color del folio, que es lo que "
                         "hay abajo de la tabla")

    def test_las_sombras_se_quedan_quietas_contra_el_marco(self):
        capas = self.cuatro_capas()
        self.assertEqual(capas.count("no-repeatscroll"), 2,
                         "las sombras se anclaron al contenido: se van de viaje con "
                         "la tabla en vez de quedarse en el borde")
        self.assertEqual(capas.count("var(--corte)"), 2,
                         "quedó una sola sombra: el lado que se corta cuando uno ya "
                         "corrió la tabla no avisa nada")

    def test_hay_una_de_cada_lado(self):
        capas = self.cuatro_capas()
        for lado in ("toright", "toleft"):
            self.assertEqual(capas.count(lado), 2, f"falta una capa hacia {lado}")

    def test_el_color_del_corte_existe_en_los_dos_temas(self):
        """Sobre el folio oscuro una sombra clara no se ve, y al revés tampoco."""
        self.assertIn("--corte:", CSS)
        i = CSS.index('[data-tema="oscuro"]')
        self.assertIn("--corte:", CSS[i:],
                      "el oscuro se quedó con la sombra del tema claro")

    def test_en_papel_no_hay_nada_que_correr(self):
        """La tabla impresa entra entera: dos manchas de tinta en los bordes serían
        una señal de algo que en papel no puede pasar."""
        m = re.search(r"\.tabla-env\{(break-inside[^{}]*)\}", LIMPIO)
        self.assertIsNotNone(m, "se perdió la regla de impresión de la tabla")
        self.assertIn("background:none", m.group(1).replace(" ", ""),
                      "las sombras de «sigue más allá» se imprimen")
