"""
Ninguna tabla muestra un dato cortado.

`overflow-x:auto` dejaba correr la tabla de costado, y eso alcanzaba mientras lo que
quedaba afuera fuera una columna que se recupera mirando la fila. No era el caso.
Medido en 1366×768, en «Superposición temporal»: la tabla pedía 976 px y la hoja le
daba 875, así que «Conf.» desaparecía entera y de «Suma» se veía `$164.` y `$329.`.

**Un importe cortado no se ve cortado.** `$164.` es un número perfectamente plausible
y el que lo lee no tiene cómo saber que le falta la mitad. Todo el sistema está armado
para no decir un dato que no está en el papel, y acá lo estaba diciendo mal por una
cuestión de ancho de pantalla.

Lo que se cuida acá es la DECISIÓN —medir, ensanchar la hoja, y recién ahí desplegar—,
corriendo la función de verdad con anchos de verdad. Lo que no se puede cuidar desde
una prueba de Python es el dibujo: eso se mira en el navegador, y las medidas están en
el mensaje del commit.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

APP = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")
CSS = (RAIZ / "ufil/web/estilo.css").read_text(encoding="utf-8")
LIMPIO = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), CSS, flags=re.S)


def _fuente_vigilar() -> str:
    i = APP.index("const _tablasVigiladas")
    j = APP.index("function interpHTML(")
    return APP[i:j]


# El banco de pruebas: una hoja con tablas adentro, con anchos que se comportan como
# los de verdad. Una tabla pide `pide` px; el envoltorio mide lo que le da la hoja, y
# la hoja da 138 px más cuando se le saca la canaleta. Desplegada ya no desborda.
BANCO = r"""
class Hoja {
  constructor(base, canaleta) { this.base = base; this.canaleta = canaleta;
    this._clases = new Set();
    this.classList = {add: c => this._clases.add(c), contains: c => this._clases.has(c)}; }
  get ancho() { return this.base + (this._clases.has('ancho') ? this.canaleta : 0); }
}
class Env {
  constructor(hoja, pide) { this.hoja = hoja; this.pide = pide; this.dataset = {}; }
  get clientWidth() { return this.hoja.ancho; }
  get scrollWidth() { return this.dataset.corte === 'si'
    ? this.clientWidth : Math.max(this.pide, this.clientWidth); }
  closest(sel) { return sel === '.bloque' ? this.hoja : null; }
}
const observadores = [];
globalThis.ResizeObserver = class { constructor(fn){ this.fn = fn; }
  observe(el){ observadores.push(() => this.fn()); } };
globalThis.ENVS = [];
globalThis.document = { querySelectorAll: () => globalThis.ENVS };
globalThis.Hoja = Hoja; globalThis.Env = Env; globalThis.observadores = observadores;
"""


class LaTablaSeMideYNoSeAdivina(unittest.TestCase):

    def correr(self, guion: str) -> dict:
        node = shutil.which("node")
        if not node:
            self.skipTest("sin node: la parte que se ejecuta no se puede correr acá")
        # `closest('.tabla-legajos')` devuelve null en el banco: acá no hay índice de
        # legajos, que es el único que queda afuera de la medición.
        entero = BANCO + _fuente_vigilar() + guion
        r = subprocess.run([node, "-e", entero], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, "vigilarCortes no corre:\n" + r.stderr[-900:])
        return json.loads(r.stdout)

    def test_una_tabla_que_entra_se_deja_en_paz(self):
        """Si no se cuidara esto, todas las tablas del sistema quedarían desplegadas."""
        s = self.correr("""
          const h = new Hoja(875, 138); ENVS = [new Env(h, 800)];
          vigilarCortes();
          console.log(JSON.stringify({corte: ENVS[0].dataset.corte || 'no',
            ancho: h.classList.contains('ancho')}));""")
        self.assertEqual(s["corte"], "no", "despliega una tabla que entra")
        self.assertFalse(s["ancho"], "le saca la canaleta a una hoja que no lo necesita")

    def test_primero_se_le_da_la_hoja_entera(self):
        """
        Superposiciones en la pantalla de la oficina: pide 976 y tiene 875. La canaleta
        —«f. 0005 / CRUCE»— son 138 px que la tabla no está usando. Devolvérselos
        alcanza, y la tabla sigue siendo una tabla, que se lee mucho mejor que una
        lista de renglones.
        """
        s = self.correr("""
          const h = new Hoja(875, 138); ENVS = [new Env(h, 976)];
          vigilarCortes();
          console.log(JSON.stringify({corte: ENVS[0].dataset.corte || 'no',
            ancho: h.classList.contains('ancho'), queda: ENVS[0].clientWidth}));""")
        self.assertTrue(s["ancho"], "no le devolvió la canaleta y desplegó de más")
        self.assertEqual(s["corte"], "no",
                         "despliega una tabla que entraba con la hoja entera")
        self.assertGreaterEqual(s["queda"], 976, "la tabla sigue sin entrar")

    def test_y_si_ni_asi_entra_la_fila_se_despliega(self):
        """A 1024 le faltan 249 px: no hay canaleta que alcance."""
        s = self.correr("""
          const h = new Hoja(727, 0); ENVS = [new Env(h, 976)];
          vigilarCortes();
          console.log(JSON.stringify({corte: ENVS[0].dataset.corte || 'no',
            desborda: ENVS[0].scrollWidth - ENVS[0].clientWidth}));""")
        self.assertEqual(s["corte"], "si", "deja la tabla cortada mostrando medio importe")
        self.assertEqual(s["desborda"], 0, "desplegada y todavía se sale del borde")

    def test_dos_tablas_en_la_misma_hoja(self):
        """
        Esta es la que se rompió de verdad, en el panel. La primera tabla entra y no
        toca nada; la segunda no entra, le saca la canaleta a la hoja —que ya podría
        habérsela sacado la primera— y TIENE QUE VOLVER A MEDIR EN EL ACTO. La versión
        que esperaba el aviso del `ResizeObserver` se quedaba esperando para siempre
        cuando la clase ya estaba puesta: no cambia el tamaño, no hay aviso.
        """
        s = self.correr("""
          const h = new Hoja(875, 138);
          ENVS = [new Env(h, 800), new Env(h, 1328)];
          vigilarCortes();
          console.log(JSON.stringify({
            primera: ENVS[0].dataset.corte || 'no', segunda: ENVS[1].dataset.corte || 'no',
            desborda: ENVS[1].scrollWidth - ENVS[1].clientWidth}));""")
        self.assertEqual(s["primera"], "no", "desplegó la tabla que entraba")
        self.assertEqual(s["segunda"], "si",
                         "la segunda tabla de la hoja se quedó cortada: es el defecto "
                         "del panel, donde el importe seguía saliendo a medias")
        self.assertEqual(s["desborda"], 0)

    def test_al_agrandar_la_ventana_la_tabla_vuelve_a_ser_tabla(self):
        """
        Desplegada no se puede medir cuánto pediría: se compara contra el ancho que se
        anotó cuando todavía era una tabla. Sin eso queda desplegada para siempre.
        """
        s = self.correr("""
          const h = new Hoja(727, 0); ENVS = [new Env(h, 976)];
          vigilarCortes();
          const antes = ENVS[0].dataset.corte || 'no';
          h.base = 1200; observadores.forEach(f => f());
          console.log(JSON.stringify({antes, despues: ENVS[0].dataset.corte || 'no'}));""")
        self.assertEqual(s["antes"], "si")
        self.assertEqual(s["despues"], "no",
                         "la tabla se quedó desplegada aunque ya entra: en una pantalla "
                         "grande se lee peor que como tabla")

    def test_se_vuelve_a_mirar_cuando_cambia_el_tamaño(self):
        """No es un punto de corte: se remide, y por eso hace falta el observador."""
        self.assertIn("new ResizeObserver(mirar).observe(env)", APP,
                      "dejó de remedirse al cambiar el tamaño de la ventana")
        i = APP.index("function vigilarCortes")
        j = APP.index("function interpHTML(")
        self.assertNotIn("matchMedia", APP[i:j],
                         "la decisión volvió a salir de un punto de corte de pantalla, "
                         "que no sabe cuántas columnas tiene la tabla")


class CadaValorDesplegadoDiceDeQueColumnaEs(unittest.TestCase):

    def test_la_celda_lleva_el_rotulo_de_su_columna(self):
        """Sin el encabezado arriba, `$164.900,00` suelto no dice si es el monto de
        este contrato o la suma de los dos."""
        self.assertEqual(APP.count('data-rotulo="${esc(c.t)}"'), 2,
                         "alguna de las dos tablas dejó de poner el rótulo en la celda")
        self.assertIn('content:attr(data-rotulo)', LIMPIO.replace(" ", ""),
                      "el rótulo está en el HTML y no se muestra")

    def test_es_el_mismo_texto_que_el_encabezado(self):
        """Dos rótulos separados se desincronizan: uno se corrige y el otro no."""
        self.assertIn("esc(c.t)}</th>", APP)

    def test_la_columna_de_numeros_deja_de_alinearse_a_la_derecha(self):
        """
        Alineado a la derecha sólo tiene sentido contra una columna. Suelto en un
        renglón, el importe se separa de su rótulo: es el mismo defecto que ya se
        arregló en «Trabajo del equipo».
        """
        plano = LIMPIO.replace(" ", "").replace("\n", "")
        self.assertIn('.tabla-env[data-corte="si"]td.num{text-align:left}', plano)

    def test_el_ancho_sobrante_no_se_come_el_renglon(self):
        plano = LIMPIO.replace(" ", "").replace("\n", "")
        self.assertIn('.tabla-env[data-corte="si"]th.crece,'
                      '.tabla-env[data-corte="si"]td.crece{width:auto}', plano)

    def test_se_puede_seguir_ordenando(self):
        """
        En las tablas grandes el encabezado no es un rótulo: es el control con el que
        se ordena. Esconderlo al desplegar sacaba el orden justo en las pantallas
        chicas, que es donde una lista de cincuenta filas más falta hace.
        """
        self.assertIn('<div class="tabla-env" data-ordenable="si">', APP,
                      "la tabla grande dejó de decir que se puede ordenar")
        plano = LIMPIO.replace(" ", "").replace("\n", "")
        self.assertIn('.tabla-env[data-corte="si"][data-ordenable]thead{display:block}',
                      plano, "al desplegarse se pierde poder ordenar")
        self.assertIn('content:"Ordenarpor"', plano,
                      "la tira de columnas queda sin decir para qué está")

    def test_una_celda_vacia_no_deja_un_rotulo_suelto(self):
        plano = LIMPIO.replace(" ", "").replace("\n", "")
        self.assertIn('.tabla-env[data-corte="si"]td:empty{display:none}', plano)


class NoEsUnPuntoDeCorteDePantalla(unittest.TestCase):
    """
    La misma pantalla con seis columnas entra y con nueve no. Un `@media` no sabe
    cuántas columnas hay, así que la regla que despliega no puede vivir adentro de uno.
    """

    def test_la_regla_que_despliega_es_de_base(self):
        i = LIMPIO.index('.tabla-env[data-corte="si"] > table')
        antes = LIMPIO[:i]
        self.assertEqual(antes.count("{") - antes.count("}"), 0,
                         "la regla que despliega quedó adentro de un @media")

    def test_la_hoja_ancha_tampoco_depende_del_ancho_de_pantalla(self):
        i = LIMPIO.index(".bloque.ancho{")
        antes = LIMPIO[:i]
        self.assertEqual(antes.count("{") - antes.count("}"), 0,
                         "«darle la hoja entera a la tabla» volvió a ser un @media")
