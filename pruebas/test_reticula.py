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
