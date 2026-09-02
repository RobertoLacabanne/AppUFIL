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
        self.assertIn("justify-self:center", c,
                      "el lienzo se estira y el recuadro deja de coincidir con la foja")
        self.assertIn("width:auto", c)

    def test_las_tres_fajas_quietas_estan_declaradas(self):
        c = cuerpo(".taller")
        self.assertIn("grid-template-rows:auto auto auto minmax(0,1fr) auto", c,
                      "el taller dejó de ser cabeza + filtros + aviso + paneles + pie")

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

    Medido después del cambio: 226 px.
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

    def test_el_recorte_de_la_foja_va_despues_de_la_lista(self):
        """
        En el escritorio va al costado y se mira de reojo. En el teléfono el orden
        natural es ver qué hay que decidir y DESPUÉS mirar el papel; iba con
        `order:-1`, o sea primero, empujando la lista una pantalla para abajo.
        """
        cuerpo = self._regla(".taller-cuerpo .folio-lado", self._movil())
        self.assertIn("order:1", cuerpo,
                      "el recorte de la foja volvió a ponerse arriba de la lista")
        self.assertIn("position:static", cuerpo,
                      "sigue pegado arriba: ocupa pantalla antes de la primera fila")

    def test_los_filtros_van_plegados(self):
        """Tres selectores de 44 px que en el caso normal —sin filtro— no dicen nada."""
        _hay(self, '<details class="taller-filtros"', APP,
             "los filtros dejaron de poder plegarse")
        _hay(self, "hayFiltro || !esTelefono()", APP,
             "los filtros dejaron de abrirse solos cuando hay uno puesto: un filtro "
             "activo escondido es peor que tres selectores de más")
        self.assertIn("display:flex", self._regla(".taller-filtros > summary", self._movil()),
                      "el resumen plegable no se ve en el teléfono")

    def test_la_prosa_explicativa_no_va_en_el_telefono(self):
        """Dice cómo funciona la pantalla y se lee una vez; cuesta dos renglones cada
        vez que se entra."""
        self.assertIn("display:none", self._regla(".taller-sub", self._movil()))


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
