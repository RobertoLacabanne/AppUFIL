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


class LosRadiosSonTresYNoDiez(unittest.TestCase):
    """
    Es el mismo argumento que ya estaba escrito sobre los veintiún tamaños de letra,
    aplicado a otra propiedad, y sin nada que lo cuidara.

    La hoja llegó a tener DIEZ valores distintos —1, 2, 3, 8, 9, 10, 14, 20, 99 px y
    el token— mientras `DESIGN_SYSTEM.md` afirmaba que eran dos. Se veía en el panel:
    el aviso, el chip de campos a revisar y el cuño «AFUERA» tenían tres esquinas
    distintas para tres cosas de la misma familia. Nada se ve mal por separado; el
    conjunto se ve casi prolijo.
    """

    # `0` siempre vale: una esquina viva es una decisión, no un descuido.
    PERMITIDOS = {"0", "var(--radio)", "var(--radio-folio)", "var(--radio-pildora)"}

    def test_ningun_border_radius_trae_un_valor_crudo(self):
        intrusos = []
        for n, linea in enumerate(CSS.splitlines(), 1):
            if "--radio" in linea and ":" in linea.split("--radio")[0][-3:]:
                continue                      # la declaración de los tokens
            for m in re.finditer(r"border-radius:\s*([^;}]+)", linea):
                for pieza in m.group(1).split():
                    if pieza not in self.PERMITIDOS:
                        intrusos.append(
                            f"  estilo.css:{n} — «{pieza}» no es ninguno de los tres "
                            f"radios declarados")
        self.assertEqual(
            intrusos, [],
            "\naparecieron radios fuera de los tres tokens "
            f"{sorted(self.PERMITIDOS - {'0'})}:\n" + "\n".join(intrusos))

    def test_los_tres_estan_declarados(self):
        for token, que in (("--radio:", "un control"),
                           ("--radio-folio:", "una superficie grande"),
                           ("--radio-pildora:", "lo que quiere ser una píldora")):
            self.assertTrue(token in CSS,
                            f"falta el token del radio de {que} ({token})")

    def test_la_prueba_esta_mirando_algo(self):
        self.assertGreater(len(re.findall(r"border-radius:", CSS)), 15,
                           "la prueba se quedó sin radios que mirar")


class TodaClaseQueElJavaScriptPintaExisteEnLaHoja(unittest.TestCase):
    """
    Van TRES colisiones de nombres en este rediseño, y las tres se vieron sólo mirando
    la pantalla:

      · `.marca` era el resaltado de lo buscado adentro de una tabla —punzó, negrita—
        y se usó como nombre del bloque de identidad: el nombre de la unidad salió
        pintado de rojo alarma en la barra lateral.
      · `.lupa` era el panel de 132 px del renglón ampliado de la cola —blanco, con
        borde— y se usó para el ícono del buscador: dibujaba una caja blanca colgando
        del techo.
      · `.cola` es el contenedor entero del listado de revisión —borde, fondo, radio—
        y se usó para el pedazo final del nombre de un documento: el pedazo heredó el
        borde y pasó a medir 96 px de ancho por 39 de alto en vez de 53 por 15.

    **Esta prueba NO las detecta, y conviene decirlo en vez de fingir que sí.** Un
    nombre reutilizado y un nombre reestilizado según el contexto se escriben igual
    —`.componente .clase{…}`— y sólo se distinguen sabiendo qué elemento es cuál. Un
    intento de detectarlas por la forma marcó diez sobreescrituras perfectamente
    legítimas: una prueba con diez falsos positivos es peor que ninguna, porque enseña
    a ignorarla.

    Lo que sí es decidible, y también es un defecto silencioso: que el JavaScript pinte
    una clase que en la hoja no existe. Ahí no hay herencia sorpresa, hay nada — el
    elemento sale sin estilo y la pantalla se ve casi bien.

    Contra las colisiones, lo que hay es el hábito de mirar la pantalla después de
    tocarla, y el comentario que quedó escrito al lado de cada uno de los tres nombres.
    """

    # Clases que las pinta el navegador o vienen de un atributo, no de la hoja.
    DEL_SISTEMA = {"activa", "activo", "abierto", "foco", "clic", "hidden"}

    def _enganches(self):
        """
        Una clase que el JavaScript usa SÓLO para encontrar el elemento después
        —`querySelector('.limpiar-tabla')`— es un enganche, no un estilo, y es un
        patrón legítimo: no tiene por qué existir en la hoja.
        """
        return {m.group(1) for m in
                re.finditer(r"""querySelector(?:All)?\(['"]\.([\w-]+)""", APP)}

    def _clases_del_js(self):
        fuera = set()
        for m in re.finditer(r'class="([^"$]*)"', APP):      # sin interpolación
            for c in m.group(1).split():
                if c and not c.startswith("$"):
                    fuera.add(c)
        return fuera - self.DEL_SISTEMA

    def test_ninguna_clase_pintada_falta_en_la_hoja(self):
        enganches = self._enganches()
        huerfanas = sorted(c for c in self._clases_del_js() - enganches
                           if not re.search(rf"\.{re.escape(c)}(?![\w-])", CSS))
        self.assertEqual(
            huerfanas, [],
            "\nel JavaScript pinta clases que no existen en estilo.css: el elemento "
            "sale sin estilo\n  y la pantalla se ve casi bien.\n  "
            + "\n  ".join(huerfanas))

    def test_la_prueba_encuentra_clases_para_mirar(self):
        self.assertGreater(len(self._clases_del_js()), 40,
                           "la prueba se quedó sin clases que mirar en app.js")


class NadaLeidoDeUnPapelSeParteEnDos(unittest.TestCase):
    """
    Un identificador partido deja de ser el identificador.

    El nombre de archivo ya estaba resuelto; el resto no. Al agregar la columna de
    cronología la tabla se apretó y el CUIT salía cortado en tres pedazos —`27-` /
    `30456789-` / `4`— que es exactamente el número que después se copia a un oficio.
    Una fecha cortada entre el día y el mes deja de ser una fecha.

    Son dos reglas distintas y hacen falta las dos:

      · `white-space:nowrap` en las celdas de dato —mono, número, folio—, porque un
        identificador es UN token y bajarlo de renglón lo destruye;
      · `word-break:normal` con `hyphens:none` en toda celda, que impide partir una
        PALABRA en cualquier lado.

    Faltaba el nombre de la persona. Bajar de renglón entre palabras no rompe ninguna
    palabra, pero rompe el dato igual: en «Superposición temporal» salía «BENÍTEZ,
    Marcelo» en un renglón y «A» en el siguiente, y esa «A» suelta no se lee como la
    inicial de nadie. Antes había una razón para permitirlo —un nombre entero podía no
    entrar en la columna—; ahora, si no entra, la tabla se despliega, así que no hay
    nada que ceder. Es una clase con nombre propio, `nombre`, y no un tercer parche:
    quiere decir «un nombre de persona leído de un papel», y de ahí sale que no se
    parta.
    """

    def test_las_celdas_de_dato_no_bajan_de_renglon(self):
        m = re.search(r"td\.mono, td\.num, td\.fol, td \.mono\{([^{}]*)\}", CSS)
        self.assertIsNotNone(
            m, "se perdió la regla que impide partir un dato en una celda de tabla")
        self.assertIn("white-space:nowrap", m.group(1).replace(" ", ""))

    def test_un_nombre_propio_tampoco_baja_de_renglon(self):
        m = re.search(r"td\.nombre, th\.nombre\{([^{}]*)\}", CSS)
        self.assertIsNotNone(m, "se perdió la regla que impide partir un nombre")
        self.assertIn("white-space:nowrap", m.group(1).replace(" ", ""))

    def test_y_la_clase_esta_puesta_donde_hay_un_nombre(self):
        """Una regla sin nadie que la use es una regla que no hace nada."""
        self.assertGreaterEqual(APP.count("c:'nombre'"), 6,
                                "las columnas de nombre dejaron de decir que lo son")
        self.assertNotIn("{t:'Contratado/a', b:f => f.contratado,", APP,
                         "quedó una columna de contratados sin la clase")

    def test_desplegada_si_puede_bajar_de_renglon(self):
        """
        Sin columna que apretar, un nombre larguísimo en un teléfono angosto tiene que
        poder bajar de renglón antes que salirse de la pantalla. Entre palabras, nunca
        adentro de una: eso lo sigue impidiendo `word-break:normal`.
        """
        plano = CSS.replace(" ", "").replace("\n", "")
        self.assertIn('.tabla-env[data-corte="si"]td.nombre{white-space:normal}', plano)

    def test_la_columna_que_no_se_parte_no_pide_el_ancho_sobrante(self):
        """`cualCrece` le da el sobrante a la que se estaba partiendo. Una que no se
        parte no lo necesita, y llevárselo se lo saca a la que sí."""
        self.assertIn("num|mono|fol|nowrap|nombre", APP,
                      "una columna que ya no se parte sigue pidiendo el ancho que le "
                      "hace falta a otra")

    def test_ninguna_palabra_se_parte_por_la_mitad(self):
        m = re.search(r"table td\{([^{}]*)\}", CSS)
        self.assertIsNotNone(m, "se perdió la regla de corte de palabra en las tablas")
        cuerpo = m.group(1).replace(" ", "")
        for pieza in ("overflow-wrap:normal", "word-break:normal", "hyphens:none"):
            self.assertIn(pieza, cuerpo,
                          f"falta «{pieza}»: una palabra puede volver a partirse en "
                          f"cualquier lado, y con ella un apellido o un CUIT")


class LaBarraDeAvanceSeVeVacia(unittest.TestCase):
    """
    Arriba del contador de la cola hay una barra que dice cuánto se lleva revisado. Al
    0 % no se distinguía de una raya rota: el carril iba en `--realce` con filete
    `--filete-2`, y sobre el folio eso es casi el mismo color. Una barra vacía tiene
    que leerse como una barra que todavía no avanzó, no como un renglón sucio.

    Y medía 64ch —unos 500 px— porque compartía la medida de lectura con la prosa de
    abajo. Una barra de avance no es prosa: se mira de reojo, y cortada a media columna
    parece que le falta un pedazo.
    """

    def _regla(self, selector):
        m = re.search(re.escape(selector) + r"\{([^{}]*)\}", CSS)
        self.assertIsNotNone(m, f"se perdió la regla «{selector}»")
        return m.group(1).replace(" ", "")

    def test_el_carril_se_ve(self):
        cuerpo = self._regla(".riel")
        self.assertIn("background:var(--papel-3)", cuerpo,
                      "el carril vacío volvió a un color que sobre el folio no se ve")
        self.assertIn("border:1pxsolidvar(--filete)", cuerpo,
                      "el filete del carril volvió a ser el más flojo de la casa")

    def test_la_barra_mide_la_columna_y_la_prosa_mide_lo_que_se_lee(self):
        self.assertNotIn("max-width:64ch", self._regla(".avance"),
                         "la barra volvió a cortarse a media columna")
        self.assertIn("max-width:64ch", self._regla(".avance p"),
                      "la prosa perdió su medida de lectura")


class ElLoteNoEsElNombreDeLaCausa(unittest.TestCase):
    """
    El lote es una PROPIEDAD del legajo, no otro identificador. Con la carátula larga
    los dos quedaban pegados en la banda de arriba —«…Contratos Legislatura LOTE
    camara-A-2024»— y el lote se leía como la cola del nombre de la causa.
    """

    def test_hay_un_filete_entre_la_causa_y_el_estado_del_trabajo(self):
        m = re.search(r"\.techo-medio\{([^{}]*)\}", CSS)
        self.assertIsNotNone(m, "se perdió la banda del medio")
        cuerpo = m.group(1).replace(" ", "")
        self.assertIn("border-left:1pxsolidvar(--filete)", cuerpo,
                      "nada separa el nombre de la causa de lo que viene después")
        self.assertIn("padding-left:", cuerpo,
                      "el filete quedó pegado al texto: separa menos que un espacio")
