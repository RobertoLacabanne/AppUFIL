"""
LA COLA DE REVISIÓN SE DESPLAZA EN UN SOLO LUGAR.

Es la pantalla donde alguien se sienta ocho horas. Antes tenía dos barras de
desplazamiento a un centímetro una de la otra —la de la página y la de la lista— y
cuál de las dos movía la rueda del mouse dependía de dónde hubiera quedado el
puntero. Encima el «1 de 42» y los filtros se iban para arriba a las tres filas,
justo cuando más falta hacen.

Medido en el navegador después del arreglo, con la cola de 42 campos abierta:

    1440×900  claro y oscuro  la página no se desplaza · se desplaza #cola (3483>593)
    1366×768  claro           la página no se desplaza · se desplaza #cola (3492>461)
    1024×768  claro y oscuro  la página no se desplaza · se desplaza #cola (5583>451)
     390×844  claro           se desplaza la página · nada adentro

En el teléfono la que corre es la página, que es lo correcto: los dos paneles no
entran uno al lado del otro y forzar el alto de la ventana dejaría dos cajitas de
200 px donde no se puede trabajar.

Esta prueba no abre un navegador —las pruebas tienen que correr sin uno—, así que
verifica las reglas de las que sale ese comportamiento. Si alguna se cae, la pantalla
vuelve a tener dos barras y esto lo dice antes de que lo diga el usuario.
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
JS = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")
HTML = (RAIZ / "ufil/web/index.html").read_text(encoding="utf-8")


def _sin_medias(css: str) -> str:
    """
    El CSS sin los bloques `@media`.

    Las reglas de base y las de pantalla angosta dicen lo contrario a propósito —una
    apaga el desplazamiento de la página y la otra lo devuelve—, así que buscar «la
    primera que aparezca» encuentra cualquiera de las dos según el orden del archivo.
    Y una prueba que encuentra cualquiera de las dos no verifica ninguna.
    """
    fuera, hondo, i = [], 0, 0
    while i < len(css):
        if css.startswith("@media", i):
            j, nivel = css.index("{", i) + 1, 1
            while nivel and j < len(css):
                nivel += (css[j] == "{") - (css[j] == "}")
                j += 1
            i = j
            continue
        fuera.append(css[i])
        i += 1
    return "".join(fuera)


BASE = _sin_medias(CSS)


def cuerpo(selector: str, css: str = BASE) -> str:
    """El cuerpo de la regla de base que empieza exactamente con ese selector."""
    m = re.search(r"(?:^|[};/])\s*" + re.escape(selector) + r"\s*\{([^{}]*)\}",
                  css, re.M)
    if not m:
        raise AssertionError(f"no existe la regla de base «{selector}»")
    return m.group(1)


class UnaSolaBarraDeDesplazamiento(unittest.TestCase):

    def test_la_pagina_no_se_desplaza_con_la_cola_abierta(self):
        c = cuerpo("body.taller-abierto #cuerpo")
        self.assertIn("overflow:hidden", c,
                      "la página volvió a desplazarse detrás de la cola")
        self.assertRegex(c, r"height:100vh|height:100dvh")

    def test_la_lista_es_lo_unico_que_se_desplaza(self):
        self.assertIn("overflow-y:auto", cuerpo(".taller-cuerpo .cola"))
        self.assertIn("overflow:hidden", cuerpo(".taller-cuerpo .folio-lado"),
                      "el panel del folio volvió a tener barra propia")

    def test_la_foja_entra_entera_en_su_panel(self):
        """
        Si la imagen del folio no se escala al alto disponible, el panel de la derecha
        se hace largo y aparece la segunda barra que todo esto vino a sacar.
        """
        c = cuerpo(".taller-cuerpo .lienzo img")
        self.assertIn("height:100%", c)
        self.assertIn("width:auto", c)

    def test_el_lienzo_mide_lo_que_mide_la_foja(self):
        """
        El recuadro que marca el campo se posiciona en PORCENTAJES de `.lienzo` (ver
        `encuadrar` en app.js). Si `.lienzo` es más ancho que la imagen —porque se la
        centró adentro de una caja estirada— el recuadro apunta a un renglón que no es
        el del campo. Señalar mal es peor que no señalar: quien mira el recuadro decide
        sobre el renglón equivocado y firma el error.
        """
        c = cuerpo(".taller-cuerpo .lienzo")
        # `align-self:center` en una columna flex hace lo mismo que hacía
        # `justify-self:center` en la grilla: achica la caja hasta la imagen en vez de
        # estirarla. El panel pasó a ser columna porque el alto que sobra tiene que
        # llevárselo el que esté a la vista —la lupa o la hoja—, y una grilla de filas
        # fijas no sabe cuál de los dos es.
        self.assertIn("align-self:center", c,
                      "el lienzo se estira y el recuadro deja de coincidir con la foja")
        self.assertIn("width:auto", c)

    def test_las_tres_fajas_quietas_estan_declaradas(self):
        """
        Y el alto que sobra se lo llevan LOS PANELES, dicho en el propio elemento.
        Estaba dicho por posición —«la cuarta fila»— y la cuarta fila era la de los
        paneles sólo si estaban los cinco hijos: con el aviso de «otros revisaron»
        oculto, que es lo normal, el `1fr` se lo llevaba el pie y la barra de deshacer
        terminaba abajo del borde de la pantalla.
        """
        c = cuerpo(".taller")
        self.assertIn("flex-direction:column", c,
                      "el taller volvió a repartir el alto por posición")
        self.assertIn("flex:1 1 auto", cuerpo(".taller > .taller-cuerpo"),
                      "los paneles dejaron de llevarse el alto que sobra")
        self.assertIn("flex:none", cuerpo(".taller > *"),
                      "sin esto, la cabeza y el pie se estiran y se comen los paneles")

    def test_al_salir_de_la_cola_se_devuelve_el_desplazamiento(self):
        """
        `taller-abierto` apaga el desplazamiento de la página entera. Si se prende y
        no se apaga, TODO el resto del sistema queda con el pie cortado y sin manera
        de bajar — y el defecto no se ve en la cola, se ve tres pantallas después.
        """
        self.assertIn("document.body.classList.add('taller-abierto')", JS)
        self.assertIn("document.body.classList.remove('taller-abierto')", JS)
        # Y el que apaga tiene que estar en el ruteo, que corre en CADA navegación.
        i = JS.index("async function rutear()")
        self.assertIn("classList.remove('taller-abierto')", JS[i:i + 1200],
                      "apagar el taller no está en el ruteo: se apaga sólo a veces")

    def test_en_pantalla_angosta_vuelve_el_desplazamiento_normal(self):
        # Hay más de un `@media (max-width:1000px)`: se busca el que habla del
        # taller, no el primero que aparezca.
        i = CSS.index("body.taller-abierto #cuerpo{height:auto")
        bloque = CSS[CSS.rindex("@media", 0, i):CSS.index("\n}", i)]
        self.assertIn("max-width:1000px", bloque)
        self.assertIn("height:auto", bloque)
        self.assertIn("overflow:visible", bloque)


if __name__ == "__main__":
    unittest.main()


class ElNombreDelDocumentoNoSeParte(unittest.TestCase):
    """
    La celda de la izquierda dice de qué papel salió el campo que se está por decidir.

    Tenía `overflow-wrap:anywhere`, puesto a propósito para que un nombre largo no se
    cortara por la izquierda. El efecto real era peor: a 1440 px `contrato_A_0013` se
    leía «contrato_A_001» y en el renglón de abajo, solo, un «3». Con quince renglones
    así en pantalla, decidir sobre el documento equivocado es cuestión de tiempo, y es
    lo más caro que puede pasar en esta pantalla.

    Se elide por el MEDIO y se conserva el final: los nombres de un lote comparten
    prefijo, así que lo que distingue un documento de otro son los últimos caracteres.
    Cortando por la izquierda se pierde justamente lo que identifica.
    """

    def _hay(self, aguja, donde, queja):
        self.assertTrue(aguja in donde, queja + f"\n  (falta: {aguja!r})")

    def test_la_celda_no_parte_palabras(self):
        """
        Se miran TODAS las reglas con ese selector, no la primera. Hay tres —una por
        cada corte de pantalla— y `re.search` devolvía la de la media query de 1024,
        así que la prueba habría dado por buena la regla principal con el defecto
        adentro. Lo encontré rompiéndola a propósito: falló señalando la regla que no
        era.
        """
        reglas = re.findall(r"\.taller-cuerpo \.fila \.marginalia\{([^{}]*)\}", CSS)
        self.assertGreaterEqual(len(reglas), 2,
                                "se perdieron las reglas de la celda del nombre")
        for i, cuerpo in enumerate(reglas):
            for prohibido in ("overflow-wrap:anywhere", "word-break:break-all",
                              "word-break:break-word"):
                self.assertNotIn(
                    prohibido.replace(" ", ""), cuerpo.replace(" ", ""),
                    f"«{prohibido}» en la regla {i + 1} de {len(reglas)} vuelve a "
                    f"partir el identificador del documento por cualquier lado; el "
                    f"último dígito cae solo al renglón de abajo")

    def test_se_elide_por_el_medio_conservando_el_final(self):
        self._hay("function nombreArchivo", APP,
                  "se perdió la elisión por el medio del nombre del documento")
        self._hay("n.slice(-COLA_NOMBRE)", APP,
                  "el final del nombre —lo único que distingue un documento de otro— "
                  "dejó de conservarse entero")
        m = re.search(r"\.nombre-doc \.doc-ini\{([^{}]*)\}", CSS)
        self.assertIsNotNone(m, "se perdió la pieza que se encoge del nombre")
        self.assertIn("text-overflow:ellipsis", m.group(1).replace(" ", ""),
                      "la parte de adelante dejó de mostrar los puntos suspensivos: "
                      "el nombre se corta sin avisar que se cortó")
        f = re.search(r"\.nombre-doc \.doc-fin\{([^{}]*)\}", CSS)
        self.assertIsNotNone(f, "se perdió la pieza que NO se encoge")
        self.assertIn("flex:0 0 auto", f.group(1).replace("  ", " "),
                      "el final del nombre puede encogerse otra vez")

    def test_el_nombre_completo_queda_al_alcance(self):
        """Elidido en pantalla, entero en el `title`: nada se pierde del todo."""
        i = APP.index("function nombreArchivo")
        cuerpo = APP[i:APP.index("\nfunction filaCola")]
        self.assertIn('title="${esc(n)}"', cuerpo,
                      "el nombre completo dejó de estar disponible al pasar el puntero")


def _hay(caso, aguja, donde, queja):
    """
    `assertIn` contra un archivo de tres mil líneas imprime el archivo entero cuando
    falla, y ahí el mensaje ya no se puede leer.
    """
    caso.assertTrue(aguja in donde, queja + f"\n  (falta: {aguja!r})")


class EnUnTelefonoSeEmpiezaATrabajarEnSeguida(unittest.TestCase):
    """
    Contado en un teléfono de 390×844: antes de la primera fila que hay que decidir
    había el techo, el título, dos renglones de prosa, la barra de avance, tres
    selectores a ancho completo y el recorte de la foja con su botón. La primera fila
    arrancaba cerca de los **1.300 px**: tres pantallas de desplazamiento cada vez que
    se entra, sólo para empezar.

    El primer arreglo bajó eso a 226 px mandando el recorte DESPUÉS de la lista, y fue
    peor: se llegaba en seguida a una decisión que no se podía tomar, porque el papel
    quedaba abajo de setenta y ocho tarjetas. Empezar rápido a decidir a ciegas no es
    una mejora.

    Ahora la unidad de trabajo es otra —un campo por pantalla, ver `ElTelefonoEsUnCampo
    PorPantalla`— y lo que esta clase cuida es lo que sigue valiendo de aquel arreglo:
    la prosa y los filtros no le comen la pantalla a la ficha.
    """

    def _movil(self):
        """
        TODO el CSS de teléfono, con las llaves balanceadas.

        Cortar desde el primer `@media (max-width:720px){` hasta el final del archivo
        —que es lo que hacía— se lleva puestas también las reglas de escritorio que
        vienen después, y entonces `re.search` encuentra la de escritorio y da por
        buena una regla de teléfono que no existe. Lo encontré porque tres pruebas
        fallaron señalando el cuerpo equivocado.
        """
        trozos, i = [], 0
        marca = "@media (max-width:720px){"
        while (i := CSS.find(marca, i)) != -1:
            j, hondo = i + len(marca), 1
            while j < len(CSS) and hondo:
                hondo += (CSS[j] == "{") - (CSS[j] == "}")
                j += 1
            trozos.append(CSS[i + len(marca):j - 1])
            i = j
        self.assertTrue(trozos, "no hay ningún bloque de teléfono en la hoja")
        return "\n".join(trozos)

    def _regla(self, selector, donde):
        cuerpos = re.findall(re.escape(selector) + r"\{([^{}]*)\}", donde)
        self.assertTrue(cuerpos, f"se perdió la regla «{selector}» del teléfono")
        return " ".join(cuerpos).replace(" ", "")

    def test_los_filtros_van_plegados(self):
        """Tres selectores de 44 px que en el caso normal —sin filtro— no dicen nada."""
        _hay(self, '<details class="taller-filtros"', APP,
             "los filtros dejaron de poder plegarse")
        _hay(self, "${hayFiltro ? ' open' : ''}", APP,
             "los filtros dejaron de abrirse solos cuando hay uno puesto: un filtro "
             "activo escondido es peor que tres selectores de más")
        # Y plegados EN TODAS las pantallas, no sólo en el teléfono: medido en
        # 1366×768, abiertos se llevaban 179 px para decir tres veces «todos».
        self.assertIn("display:flex", self._regla(".taller-filtros > summary", CSS),
                      "el resumen plegable no se ve")
        self.assertNotIn("!esTelefono()", APP.split("details class=\"taller-filtros")[1][:400],
                         "los filtros vuelven a abrirse solos en el escritorio")

    def test_los_controles_del_filtro_van_en_fila_y_no_apilados(self):
        """
        Un `<details>` con `display:flex` NO acomoda su contenido: el navegador mete
        todo lo que sigue al `<summary>` en una caja de bloque anónima. Medido en
        1366×768 cuando esto se volvió plegable por el teléfono: los tres selectores
        apilados, 179 px de alto, la quinta parte de la pantalla.
        """
        _hay(self, 'class="filtros-fila"', APP,
             "los controles volvieron a colgar sueltos del <details>")
        self.assertIn("display:flex", self._regla(".filtros-fila", CSS),
                      "la fila de filtros dejó de ser una fila")
        # Y el rótulo al lado del selector, no arriba: arriba son tres renglones más.
        import re
        cuerpo = re.search(r"\.taller-filtros label\{([^{}]*)\}",
                           re.sub(r"/\*.*?\*/", "", CSS, flags=re.S))
        self.assertIsNotNone(cuerpo)
        self.assertIn("display:flex", cuerpo.group(1).replace(" ", ""),
                      "el rótulo del filtro volvió arriba del selector")

    def test_la_prosa_explicativa_no_va_en_el_telefono(self):
        """Dice cómo funciona la pantalla y se lee una vez; cuesta dos renglones cada
        vez que se entra."""
        self.assertIn("display:none", self._regla(".taller-sub", self._movil()))


class ElTelefonoEsUnCampoPorPantalla(unittest.TestCase):
    """
    La regla que esta clase existe para sostener está escrita en el README y es la
    quinta de la casa: **no se decide sin ver**. Un control de decisión no puede
    existir en pantalla si el recorte del campo no está a la vista al mismo tiempo.

    Lo que pasó, y por lo que hace falta una prueba: por debajo de 720 px el panel del
    recorte se mandó DESPUÉS de la lista. En un teléfono quedaban setenta y ocho
    tarjetas de decisión, cada una con sus botones, y el papel abajo de las setenta y
    ocho. Se podía decidir sin ver, que es lo único que este sistema no puede
    permitir. Y la propia pantalla prometía en su subtítulo «el folio está a la vista:
    no hace falta salir de acá».

    El error no era de implementación: un panel único no puede servir a una lista de
    setenta y ocho filas en una pantalla donde no entran los dos a la vez. Por eso en
    el teléfono la cola deja de ser una lista y pasa a ser una ficha.
    """

    def _movil(self):
        return EnUnTelefonoSeEmpiezaATrabajarEnSeguida._movil(self)

    def _regla(self, selector, donde):
        return EnUnTelefonoSeEmpiezaATrabajarEnSeguida._regla(self, selector, donde)

    def test_el_recorte_va_antes_que_la_decision(self):
        """
        Si vuelve a `order:1`, el papel vuelve a quedar abajo de la lista entera.
        """
        cuerpo = self._regla(".taller-cuerpo .folio-lado", self._movil())
        self.assertIn("order:-1", cuerpo,
                      "el recorte de la foja quedó DESPUÉS de la lista: en un teléfono "
                      "eso es decidir sin ver el papel")
        # Y pegado arriba: un campo con cinco opciones no entra entero abajo del
        # recorte, y bajar para llegar al último botón es volver a decidir sin ver.
        self.assertIn("position:sticky", cuerpo,
                      "el recorte se despega al bajar: con un conflicto de cinco "
                      "opciones, el último botón queda sin papel a la vista")

    def test_se_dibuja_un_campo_y_no_setenta_y_ocho(self):
        movil = self._movil()
        _hay(self, ".modo-ficha .taller-cuerpo .cola .fila:not(.foco)", movil,
             "la ficha volvió a dibujar la lista entera: con setenta y ocho tarjetas "
             "el recorte no puede estar al lado de su decisión")
        self.assertIn("display:none",
                      self._regla(".modo-ficha .taller-cuerpo .cola .fila:not(.foco)",
                                  movil))

    def test_el_recorte_es_el_elemento_mas_grande(self):
        """
        Es la razón por la que existe la pantalla. Estaba clavado en 132 px, que para
        un importe manuscrito no alcanza.
        """
        cuerpo = self._regla(".lupa", self._movil())
        alto = re.search(r"min-height:(\d+)vh", cuerpo)
        self.assertIsNotNone(alto, "el recorte dejó de medirse contra la pantalla")
        self.assertGreaterEqual(int(alto.group(1)), 30,
                                "el recorte se achicó: abajo de 30 vh un manuscrito no "
                                "se lee y la decisión se toma a ciegas")
        self.assertIn("pinch-zoom", cuerpo,
                      "sin pellizco para acercar, un manuscrito chico no se lee de una")

    def test_la_lista_sigue_existiendo_para_saltar_a_un_campo(self):
        """
        La ficha no puede ser una cárcel: filtrar y saltar a un campo puntual siguen
        haciendo falta. Lo que cambia es que dejan de ser la pantalla de entrada.
        """
        _hay(self, 'id="ficha-lista"', APP, "no hay manera de ver la lista completa")
        _hay(self, "ponerModoCola(", APP, "el botón de la lista no cambia el modo")
        _hay(self, "'ficha' ? 'lista' : 'ficha'", APP,
             "el botón de la lista no alterna entre los dos modos")
        _hay(self, "modoCola === 'lista' && esTelefono()", APP,
             "tocar una fila de la lista tiene que volver a la ficha de ese campo: "
             "adentro de la lista no se puede ver el papel")
        # Y adentro de la lista no hay con qué decidir: no se ve el papel.
        self.assertIn("display:none",
                      self._regla(".modo-lista .taller-cuerpo .fila .acc", self._movil()),
                      "la lista dejó los botones de decidir puestos, y ahí no hay "
                      "recorte a la vista: es decidir a ciegas otra vez")

    def test_se_avanza_sin_recorrer(self):
        movil = self._movil()
        for id_ in ('ficha-antes', 'ficha-despues', 'ficha-donde'):
            _hay(self, f'id="{id_}"', APP, f"falta «{id_}» para avanzar en el teléfono")
        _hay(self, "moverFicha(-1)", APP, "no se puede volver al campo anterior")
        _hay(self, "moverFicha(+1)", APP, "no se puede pasar al campo siguiente")
        # En la zona del pulgar: pegada abajo y con controles de 44 px.
        pie = self._regla(".taller-pie", movil)
        # Fija y no `sticky`: `sticky` con `bottom` no despega si el elemento es lo
        # último de su contenedor, que es justo el caso. Medido: quedaba en 756→885
        # sobre una pantalla de 844, o sea abajo del borde.
        self.assertIn("position:fixed", pie,
                      "la barra de avanzar tiene que estar SIEMPRE a la vista")
        self.assertIn("bottom:0", pie)
        self.assertIn("padding-bottom:72px", self._regla(".taller-cuerpo", movil),
                      "sin hueco abajo, la barra fija tapa la última decisión")
        self.assertIn("min-height:44px", self._regla(".ficha-mover", movil))

    def test_los_dos_caminos_no_se_ven_iguales(self):
        """
        Uno escribe un dato en el legajo y el otro cierra el campo sin valor. Y la
        diferencia no puede ser sólo el color: es la regla de la casa.
        """
        movil = self._movil()
        produce = self._regla(".taller-cuerpo .acc .tecla.opcion, "
                              ".taller-cuerpo .acc .tecla.principal", movil)
        descarta = self._regla(".taller-cuerpo .acc .tecla.secundaria", movil)
        self.assertIn("border-color:var(--verde)", produce)
        self.assertIn("border-style:dashed", descarta,
                      "los dos caminos se distinguen sólo por el color: hace falta una "
                      "diferencia que se vea en blanco y negro")

    def test_la_ficha_no_se_mete_en_el_escritorio(self):
        """
        `modoCola` arranca en «ficha» siempre, pero la ficha sólo existe abajo de
        720 px. Preguntando sólo por el modo, el escritorio se quedaba sin
        `scrollIntoView`: bajar con J y K dejaba de mover la lista y el foco se iba
        abajo del borde sin que nada se moviera.
        """
        _hay(self, "modoCola === 'ficha' && esTelefono()", APP,
             "la ficha tiene que preguntar TAMBIÉN por el ancho: en el escritorio "
             "hay lista y panel al costado, y el modo no significa nada")
        _hay(self, "if (!enFicha()) filas[colaEstado.foco].scrollIntoView", APP,
             "el escritorio perdió el desplazamiento al foco")

    def test_la_procedencia_va_primero_y_en_mono(self):
        _hay(self, 'id="ficha-procedencia"', APP,
             "la ficha no dice de dónde sale lo que se está por decidir")
        _hay(self, 'class="ficha-procedencia mono"', APP,
             "la procedencia va en mono: es un dato leído del documento")


class LaFojaSeAbreParaLeerla(unittest.TestCase):
    """
    La lámina del costado —tanto en la cola como en la pantalla del documento— entra
    entera y por eso no se lee: a 340 px no se distingue un importe. Es un mapa, no el
    documento. El visor la abre al tamaño del escaneo, que es la única manera de
    leerla, y por eso también es la única manera honesta de habilitar una decisión
    cuando el recorte no sirve.
    """

    def test_se_abre_desde_las_dos_pantallas(self):
        _hay(self, 'id="abrir-foja"', APP, "la cola no puede abrir la foja")
        _hay(self, 'id="abrir-foja-doc"', APP,
             "la pantalla del documento no puede abrir la foja, y es donde más se "
             "mira: la lámina de ahí tampoco se lee")
        _hay(self, "$('#lienzo').onclick = abrirLaFoja", APP,
             "tocar la lámina tiene que abrirla: quien quiere leerla la toca antes "
             "de buscar un botón")

    def test_se_engancha_una_sola_vez_y_no_adentro_de_una_vista(self):
        """
        Enganchado adentro de `vCola`, el botón de cerrar no hacía nada en la
        pantalla del documento: quedaba sólo `Esc`, que es un atajo y no una salida.
        """
        _hay(self, "function engancharVisor", APP,
             "el visor volvió a engancharse adentro de una vista")
        self.assertNotIn("$('#visor-cerrar').onclick", APP.split("async function vCola")[1][:6000],
                         "el visor se volvió a enganchar adentro de la cola")

    def test_abre_mirando_el_campo(self):
        """
        Una foja de 1.653 px en una ventana de 1.366 entra a medias. Abierta en el
        origen, el campo que se venía a leer queda abajo del borde; y con el velo que
        oscurece lo que no es el recuadro, la pantalla entera se veía gris sin que el
        recuadro estuviera a la vista.
        """
        _hay(self, "const alCampo = ()", APP, "el visor abre en la esquina de arriba")
        _hay(self, "caja.scrollTop +=", APP,
             "el visor no se desplaza al recuadro")
        _hay(self, "if (img.complete && img.naturalWidth) alCampo();", APP,
             "sin esperar a que cargue la imagen no hay a dónde desplazarse")

    def test_cambiar_de_pantalla_lo_cierra(self):
        """
        El visor vive AFUERA de `#vista` —tiene que taparlo todo—, así que un cambio
        de ruta repintaba lo de abajo y la foja quedaba flotando encima de otra
        pantalla, tapándola entera y con el desplazamiento del cuerpo trabado.
        """
        _hay(self, "addEventListener('hashchange', () => { cerrarVisor(); rutear(); })", APP,
             "navegar con la foja abierta deja la foja tapando la pantalla nueva")

    def test_lo_de_abajo_queda_apagado_mientras_esta_abierta(self):
        """
        Tabulando desde el botón de cerrar se llegaba a los botones de decidir que
        estaban TAPADOS por la foja: se podía decidir un campo sin ver lo que se
        estaba decidiendo, con la foja de otro encima. Con `inert` no se toca, no se
        tabula y un lector de pantalla no lo lee.
        """
        _hay(self, "cuerpo.inert = true", APP, "lo de abajo sigue alcanzable con Tab")
        _hay(self, "cuerpo.inert = false", APP,
             "al cerrar no se vuelve a encender: la pantalla queda muerta")
        # Y para eso el visor no puede ser hijo de lo que se apaga.
        i = HTML.index('<div id="visor"')
        j = HTML.index('<div id="cuerpo">')
        k = HTML.index('</div>', HTML.index('<main id="vista"'))
        self.assertTrue(i > k or i < j,
                        "el visor está adentro de #cuerpo: al apagarlo se apaga a sí "
                        "mismo y no se puede ni cerrar")

    def test_al_cerrar_el_foco_vuelve_a_donde_estaba(self):
        """Quien navega con teclado no tiene que salir a buscar dónde quedó."""
        _hay(self, "volverElFoco = document.activeElement", APP,
             "no se recuerda desde dónde se abrió")
        _hay(self, "volverElFoco.focus()", APP, "el foco se pierde al cerrar la foja")
        _hay(self, "document.contains(volverElFoco)", APP,
             "si la pantalla se repintó, ese elemento ya no existe y enfocarlo "
             "tiraría un error")

    def test_mientras_esta_abierto_ninguna_tecla_decide(self):
        i = APP.index("document.addEventListener('keydown'")
        cabeza = APP[i:i + 400]
        self.assertIn("if (!$('#visor')?.hidden)", cabeza,
                      "con la foja abierta a pantalla completa, las teclas de la cola "
                      "siguen decidiendo campos que no se están mirando")


class NoSeDecideSinVer(unittest.TestCase):
    """
    La quinta restricción de la casa, del lado de quien decide. Un «es correcto»
    apretado sin mirar el papel es una afirmación sin fundamento con la firma de una
    persona encima.

    Se juzga sobre lo que el navegador REALMENTE cargó, no sobre lo que la base dice
    que hay: una imagen que no llegó deja la pantalla igual de ciega que un campo sin
    anclaje.
    """

    def test_la_regla_esta_escrita_donde_van_las_reglas(self):
        readme = (RAIZ / "README.md").read_text(encoding="utf-8")
        self.assertIn("No se decide sin ver", readme,
                      "la regla tiene que estar en el README, con las otras cuatro: "
                      "una regla que sólo vive en el CSS se pierde en el próximo "
                      "cambio de layout")

    def test_sin_recorte_los_controles_se_apagan(self):
        _hay(self, "function pintarSinVer", APP,
             "se perdió la regla: sin recorte, los controles se apagan")
        _hay(self, "b.disabled = !!motivo", APP,
             "los controles de decisión tienen que apagarse cuando no hay qué mirar")
        _hay(self, "aviso-sin-ver", APP,
             "apagarlos sin decir por qué deja a la persona sin saber qué hacer")

    def test_se_mira_la_imagen_y_no_la_base(self):
        _hay(self, "mira.complete", APP,
             "hay que esperar a que la imagen termine de cargar")
        _hay(self, "mira.naturalWidth", APP,
             "hay que mirar si la imagen CARGÓ: una que no llegó deja la pantalla "
             "igual de ciega que un campo sin anclaje")
        _hay(self, "mira.onerror = juzgar", APP,
             "una imagen que falla tiene que apagar los controles, no dejarlos vivos")

    def test_la_regla_tambien_vale_para_las_teclas(self):
        """
        El botón sale `disabled`, pero una tecla no pasa por el botón. La regla se
        cumple en `decidir`, que es por donde pasan todos los caminos.
        """
        cuerpo = APP[APP.index("async function decidir("):]
        cuerpo = cuerpo[:cuerpo.index("\n}\n")]
        self.assertIn("if (!hayQueMirar) return;", cuerpo,
                      "«decidir» decide sin comprobar que haya papel a la vista")

    def test_un_recuadro_que_existe_pero_no_sirve_tambien_apaga(self):
        """
        El agujero que quedaba, y el que apareció con documentos de verdad: el
        guardián comprobaba que el recorte EXISTIERA, no que SIRVIERA. Una caja
        degenerada —x1 y x0 casi iguales, que es lo que devuelve el reconocimiento
        cuando no delimitó un manuscrito— tiene `x0` distinto de `null`, así que
        pasaba el control, los botones se encendían y alguien decidía mirando dos
        letras sueltas contra el borde de la lupa.

        Los tres casos que ahora caen en «sin recorte» están escritos en `cajaUtil`,
        y cada uno con su número: si alguna vez rechaza una caja que estaba bien,
        quien lo vea puede decir exactamente cuál era.
        """
        _hay(self, "function cajaUtil", APP,
             "volvió a alcanzar con que el recuadro exista")
        for constante, que in (
                ("CAJA_MINIMA", "la caja degenerada, de dos puntos de lado"),
                ("CAJA_MAXIMA_HOJA", "la caja del tamaño de media hoja"),
                ("CAJA_MAS_ALTA_QUE_ANCHA", "la caja con forma imposible")):
            _hay(self, constante, APP, f"dejó de mirarse {que}")
        # Y la caja fuera del papel, que es como se nota que las coordenadas y el
        # ancho de la hoja no están en la misma unidad para ese escaneo.
        _hay(self, "cae afuera de la hoja", APP,
             "una caja fuera del papel corre el encuadre entero y no se detecta")
        # Los tres caminos terminan en el mismo lugar: sin recorte.
        _hay(self, "const roto = cajaUtil(f, pag);", APP,
             "el encuadre dejó de preguntar si la caja sirve")
        _hay(self, "if (roto) {", APP, "se calcula si la caja sirve y no se usa")

    def test_la_caja_se_juzga_de_verdad_y_no_por_su_nombre(self):
        """
        Esto CORRE la función con cajas de prueba, en vez de buscar palabras en el
        archivo. Buscar palabras no alcanzó: renombrando la constante y dejando el uso
        como estaba —que es lo que pasa cuando alguien refactoriza a medias— el texto
        seguía ahí y la función se rompía al ejecutarse.

        Los casos son los tres que aparecieron con documentos reales, más uno bueno
        para que la prueba no pase por prohibirlo todo.
        """
        import json
        import shutil
        import subprocess
        node = shutil.which("node")
        if not node:
            self.skipTest("sin node: la parte que se ejecuta no se puede correr acá")
        i = APP.index("const CAJA_MINIMA")
        j = APP.index("/* Cuando no hay recorte")
        fuente = APP[i:j]
        pag = {"ancho_pt": 595, "alto_pt": 842}
        casos = {
            "buena":      {"x0": 60, "y0": 120, "x1": 300, "y1": 145},
            "degenerada": {"x0": 60, "y0": 120, "x1": 62,  "y1": 124},
            "enorme":     {"x0": 10, "y0": 10,  "x1": 580, "y1": 700},
            "torre":      {"x0": 60, "y0": 100, "x1": 80,  "y1": 400},
            "afuera":     {"x0": 60, "y0": 120, "x1": 900, "y1": 145},
        }
        guion = fuente + "\nconst casos = " + json.dumps(casos) + ";\n" + \
            "const pag = " + json.dumps(pag) + ";\n" + \
            "const out = {}; for (const k in casos) out[k] = cajaUtil(casos[k], pag);\n" + \
            "console.log(JSON.stringify(out));"
        r = subprocess.run([node, "-e", guion], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, "cajaUtil no corre:\n" + r.stderr[-600:])
        salida = json.loads(r.stdout)
        self.assertEqual(salida["buena"], "",
                         "rechaza una caja normal: así no se puede revisar nada")
        for malo in ("degenerada", "enorme", "torre", "afuera"):
            self.assertTrue(salida[malo],
                            f"la caja «{malo}» pasa el control y no se puede mirar")
            # Y el motivo trae los números, para poder discutirlo si alguna vez se
            # equivoca.
            self.assertRegex(salida[malo], r"\d+×\d+ pt",
                             f"el motivo de «{malo}» no dice cuánto medía la caja")

    def test_el_campo_esta_marcado_adentro_del_recorte(self):
        """
        La lupa muestra el renglón Y lo que lo rodea, y eso hace falta: es lo que
        permite saber que se está mirando el renglón correcto. Pero sin nada que lo
        marque hay que adivinar cuál de los renglones a la vista es el campo, y
        adivinar mal es decidir sobre el renglón equivocado y firmarlo.
        """
        _hay(self, 'id="lupa-marco"', APP, "el campo no está marcado adentro de la lupa")
        _hay(self, "if (marco) {\n    marco.hidden = false;", APP,
             "el recuadro se calcula y nunca se muestra")
        _hay(self, "marco.style.left = ((r.width - caja.w * escala) / 2)", APP,
             "el recuadro se calcula por otro lado que el encuadre: si no sale de la "
             "misma cuenta que centró la imagen, señala un renglón que no es")
        # Y se apaga cuando no hay recorte: un recuadro sobre una caja vacía señala
        # un lugar que no existe.
        i = APP.index("lupa.classList.add('sin-anclaje')")
        self.assertIn("marco.hidden = true", APP[i:i + 300],
                      "sin recorte, el recuadro queda dibujado sobre la nada")

    def test_el_aumento_tiene_piso_y_no_solo_techo(self):
        """
        Sin piso, una caja grande hacía que la escala se desplomara y entrara la
        página entera del tamaño de una estampilla. Mostrar el renglón más chico que
        el propio escaneo es dar por bueno que no se lea: si con el piso no entra, la
        lupa recorta y se ve el principio.
        """
        _hay(self, "Math.max(Math.min(cabe,", APP,
             "el aumento volvió a tener sólo techo")
        _hay(self, "const natural = 200 / 72;", APP,
             "el piso tiene que ser el tamaño del escaneo, no un número inventado")

    def test_una_estampilla_no_cuenta_como_haber_visto(self):
        """
        Sin recorte útil queda la hoja entera en un panel de 340 px, donde no se lee
        un importe. Darla por buena era el agujero más grande que quedaba: había que
        abrirla de verdad.
        """
        _hay(self, "const fojasMiradas = new Set();", APP,
             "no se recuerda qué fojas se abrieron de verdad")
        _hay(self, "sinRecorteUtil && !fojasMiradas.has(String(f.campo_id))", APP,
             "la miniatura de la hoja volvió a contar como haber visto el campo")
        _hay(self, "function abrirFoja", APP, "no hay manera de abrir la foja entera")
        _hay(self, "fojasMiradas.add(String(f.campo_id))", APP,
             "abrir la foja no habilita la decisión: quedaría trabada para siempre")
        # Y el visor muestra la hoja al tamaño del escaneo, no encogida.
        self.assertIn("max-width:none", CSS[CSS.index("#visor-img"):CSS.index("#visor-img") + 120],
                      "el visor encoge la hoja, que es justo lo que impide leerla")

    def test_el_visor_abre_tambien_los_campos_sin_foja_propia(self):
        """
        La trampa que casi se va con esto puesto: los campos SIN anclaje son los que
        necesitan que se abra la hoja, y son justamente los que no tienen
        `pagina_nro`. Con el visor mirando sólo ese campo, el botón no hacía nada, los
        controles quedaban apagados y la decisión trabada para siempre. Se vio
        abriéndolo en el navegador, no leyendo el código.
        """
        _hay(self, "function fojaDe", APP,
             "el visor volvió a depender de que el campo tenga foja propia")
        _hay(self, "f.pagina_respaldo && f.pagina_respaldo.nro", APP,
             "sin la foja de respaldo, los campos sin anclaje no se pueden abrir")
        _hay(self, "abrir.disabled = !fojaDe(f)", APP,
             "un botón que no hace nada es peor que un botón apagado")

    def test_el_aviso_se_ve_sin_color(self):
        cuerpo = re.findall(r"\.aviso-sin-ver\{([^{}]*)\}", CSS)
        self.assertTrue(cuerpo, "se perdió el estilo del aviso")
        self.assertIn("border-left", cuerpo[0].replace(" ", ""),
                      "el aviso se dice sólo con color")


class UnSoloContadorYNoDos(unittest.TestCase):
    """
    Convivían «0 de 62 campos revisados» arriba a la izquierda y «1 de 62» arriba a la
    derecha, separados por todo el ancho de la pantalla. Uno es avance y el otro es
    posición, pero se leen igual, y en el teléfono quedaban pegados uno al otro, donde
    además se veía que el 0 y el 1 no coinciden.
    """

    def test_el_contador_de_la_derecha_ya_no_existe(self):
        self.assertFalse('id="posicion"' in APP,
                         "volvió el segundo contador arriba a la derecha")
        self.assertFalse(".taller-cabeza .posicion" in CSS,
                         "quedó CSS de un contador que ya no se pinta")

    def test_el_que_queda_dice_las_dos_cosas(self):
        i = APP.index("function tripasAvance")
        cuerpo = APP[i:APP.index("\n/* Vuelve a pintar el avance")]
        _hay(self, "Campo <strong>", cuerpo, "el renglón dejó de decir dónde estás")
        _hay(self, "campos revisados", cuerpo, "el renglón dejó de decir cuánto llevás")

    def test_la_posicion_se_repinta_al_moverse(self):
        """Un contador que sólo se actualiza al recargar es peor que no tenerlo."""
        _hay(self, "colaEstado.foco, colaEstado.total", APP,
             "el renglón dejó de recibir la posición al repintarse")
