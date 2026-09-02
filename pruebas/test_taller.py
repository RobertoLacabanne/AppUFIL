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
