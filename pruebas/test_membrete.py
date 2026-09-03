"""
El membrete de la hoja impresa, y el cuño de demostración.

Dos cosas que sólo importan cuando el sistema deja de estar en la pantalla:

  · Una hoja que sale de acá termina agregada a un legajo. Tiene que decir de dónde
    salió sin depender de que alguien se acuerde de escribirlo: el organismo, la
    unidad, qué legajo y cuándo se emitió.
  · Y si esa hoja trae contratos inventados, tiene que decirlo de una manera que no se
    pueda perder. El aviso era una franja horizontal que cruzaba TODAS las pantallas,
    siempre; a los dos días se aprende a no verla, que es lo peor que le puede pasar a
    un aviso de seguridad. Ahora es un cuño girado, fijo abajo a la derecha, con el
    doble filete que el sistema ya usa.

Un cuño de seguridad tiene tres condiciones y las tres se verifican acá: no se puede
cerrar, no se puede tapar, y en impresión sale sí o sí.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

CSS = (RAIZ / "ufil/web/estilo.css").read_text(encoding="utf-8")
HTML = (RAIZ / "ufil/web/index.html").read_text(encoding="utf-8")
APP = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")


def _bloque_impresion() -> str:
    """El `@media print` grande, con las llaves balanceadas."""
    marca = "@media print{"
    i, mejor = 0, ""
    while (i := CSS.find(marca, i)) != -1:
        j, hondo = i + len(marca), 1
        while j < len(CSS) and hondo:
            hondo += (CSS[j] == "{") - (CSS[j] == "}")
            j += 1
        trozo = CSS[i + len(marca):j - 1]
        if len(trozo) > len(mejor):
            mejor = trozo
        i = j
    return mejor


class LaHojaImpresaDiceDeDondeSalio(unittest.TestCase):

    def test_el_membrete_existe_y_solo_en_papel(self):
        self.assertIn('id="membrete"', HTML, "se perdió el membrete de impresión")
        self.assertRegex(
            CSS, r"#membrete\{display:none\}",
            "el membrete se ve en pantalla: la identidad ya está en la barra lateral "
            "y repetirla arriba de cada folio es decir dos veces lo mismo")
        self.assertIn("#membrete{display:flex", _bloque_impresion(),
                      "el membrete dejó de aparecer al imprimir")

    def test_dice_las_cuatro_cosas(self):
        for id_, que in (("membrete-organismo", "el organismo"),
                         ("membrete-unidad", "la unidad"),
                         ("membrete-legajo", "qué legajo"),
                         ("membrete-fecha", "cuándo se emitió")):
            self.assertIn(f'id="{id_}"', HTML,
                          f"el membrete dejó de decir {que}")

    def test_el_nombre_sale_de_identidad_y_no_escrito_a_mano(self):
        self.assertIn("$('#membrete-organismo')", APP,
                      "el membrete dejó de tomar el nombre del endpoint de identidad: "
                      "cambiar de unidad dejaría hojas impresas con el nombre viejo")

    def test_la_hora_se_sella_al_imprimir_y_no_al_cargar(self):
        """
        Una pestaña abierta desde la mañana imprimiría la hora de la mañana, y esa
        hoja se agrega a un legajo.
        """
        self.assertIn("addEventListener('beforeprint'", APP,
                      "la fecha de emisión volvió a fijarse al cargar la página")


class ElCunoDeDemostracionNoSePuedePerder(unittest.TestCase):

    def _regla(self, donde=CSS):
        m = re.search(r"#aviso-demo\{([^{}]*)\}", donde)
        self.assertIsNotNone(m, "se perdió el cuño de demostración")
        return m.group(1).replace(" ", "")

    def test_es_un_cuno_y_no_una_franja(self):
        cuerpo = self._regla()
        self.assertIn("position:fixed", cuerpo,
                      "volvió a ser una franja en el flujo, que se come un renglón de "
                      "todas las pantallas para siempre")
        self.assertRegex(cuerpo, r"transform:rotate\(-?\d",
                         "el cuño dejó de estar girado y se lee como un cartel más")

    def test_no_estorba_el_trabajo_pero_no_se_puede_cerrar(self):
        cuerpo = self._regla()
        self.assertIn("pointer-events:none", cuerpo,
                      "el cuño intercepta clics: puesto encima del trabajo, tapa lo "
                      "que hay debajo")
        # No se puede cerrar porque no hay con qué: ningún botón en el marcado.
        i = HTML.index('id="aviso-demo"')
        self.assertNotIn("<button", HTML[i:HTML.index("</div>", i)],
                         "le pusieron un botón de cerrar a un aviso de seguridad")

    def test_en_papel_sale_si_o_si(self):
        impresion = _bloque_impresion()
        self.assertIn("#aviso-demo{position:static", impresion.replace(" ", ""),
                      "el cuño no está resuelto para el papel: una hoja con contratos "
                      "inventados podría salir sin decirlo")
        self.assertNotRegex(
            impresion, r"#aviso-demo\{[^{}]*display:none",
            "el cuño se apaga al imprimir, que es justo cuando más hace falta")

    def test_el_texto_largo_no_esta_adentro_del_cuno(self):
        """Un cuño es breve o no es un cuño: el párrafo entero lo volvía un cartel."""
        i = HTML.index('id="aviso-demo"')
        marcado = HTML[i:HTML.index("</div>", i)]
        self.assertIn("title=", marcado,
                      "la explicación completa dejó de estar al alcance")
        cuerpo = re.sub(r"<[^>]*>", " ", marcado.split(">", 1)[1])
        self.assertLess(len(" ".join(cuerpo.split())), 90,
                        "el cuño volvió a llevar el párrafo entero adentro")
