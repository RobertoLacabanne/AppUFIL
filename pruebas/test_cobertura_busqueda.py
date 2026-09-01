"""
La búsqueda no puede afirmar una ausencia que no verificó.

Éste era el único lugar del sistema que lo hacía. «Sin coincidencias» se leía como
«esta palabra no está en el legajo», cuando lo único cierto era «no está en las fojas
que el sistema pudo leer». Dos fojas se caían del índice sin dejar rastro:

  · la que se procesó y cuya lectura quedó vacía —`reindexar` no inserta la fila si el
    texto está en blanco—;
  · la que nunca se procesó, que ni siquiera entra en la consulta que arma el índice.

En una herramienta que se usa para decidir si algo se imputa o se archiva, eso no es
un detalle de presentación. Y contradice al resto del sistema, que está construido
sobre lo contrario: `Ø motivo` en lugar de celda vacía, el nulo que se escribe con su
causa, la interfaz que no resuelve un conflicto sola.

Lo que se mide acá es que los números digan la verdad en los tres casos, y que la
pantalla nunca vuelva a decir «sin coincidencias» a secas.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ufil import busqueda, db  # noqa: E402
from ufil.db import ahora  # noqa: E402

APP = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")


class LaBusquedaDiceSobreCuantoBusco(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cx = db.abrir(Path(self.tmp.name) / "t.sqlite")
        self.cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,
                                                paginas,ingerido_en)
                           VALUES ('aa','/x/aa.pdf','contrato-1.pdf',1,3,?)""", (ahora(),))

    def _pagina(self, nro: int) -> int:
        return self.cx.execute(
            "INSERT INTO pagina (sha256,nro,ancho_pt,alto_pt) VALUES ('aa',?,595,842)",
            (nro,)).lastrowid

    def _lectura(self, pagina_id: int, palabras: list[str]) -> None:
        lid = self.cx.execute(
            """INSERT INTO lectura (pagina_id,ruta,motor,confianza,creado_en)
               VALUES (?,'ocr_a','tesseract',0.9,?)""", (pagina_id, ahora())).lastrowid
        for i, w in enumerate(palabras):
            self.cx.execute(
                """INSERT INTO palabra (lectura_id,orden,texto,x0,y0,x1,y1,conf)
                   VALUES (?,?,?,10,10,50,20,0.9)""", (lid, i, w))

    def _tres_casos(self):
        """Una foja legible, una procesada sin texto, y una que nunca se procesó."""
        self._lectura(self._pagina(1), ["GONZALEZ", "MARIA", "LAURA"])
        self._lectura(self._pagina(2), [])          # se procesó y no dio nada
        self._pagina(3)                             # nunca se procesó
        self.cx.commit()
        busqueda.reindexar(self.cx)

    def test_las_tres_fojas_se_cuentan_y_se_distinguen(self):
        self._tres_casos()
        c = busqueda.cobertura(self.cx)
        self.assertEqual(c["fojas"], 3, "no cuenta todas las fojas cargadas")
        self.assertEqual(c["indexadas"], 1, "sobre esto es lo único que se buscó")
        self.assertEqual(c["fuera"], 2, "dos fojas no entraron a la búsqueda")
        # Dos motivos distintos y dos remedios distintos: la que nunca se procesó se
        # arregla corriendo el proceso; la otra hay que mirarla contra el papel.
        self.assertEqual(c["sin_procesar"], 1)
        self.assertEqual(c["sin_texto"], 1)

    def test_la_suma_cierra_siempre(self):
        """Si los dos motivos no suman lo que quedó afuera, alguno miente."""
        self._tres_casos()
        c = busqueda.cobertura(self.cx)
        self.assertEqual(c["sin_procesar"] + c["sin_texto"], c["fuera"])
        self.assertEqual(c["indexadas"] + c["fuera"], c["fojas"])

    def test_buscar_devuelve_la_cobertura_haya_o_no_resultados(self):
        self._tres_casos()
        con = busqueda.buscar(self.cx, "gonzalez")
        self.assertTrue(con["paginas"], "debería encontrar la foja legible")
        self.assertIn("cobertura", con, "con resultados tampoco se dice el denominador")
        sin = busqueda.buscar(self.cx, "portillo")
        self.assertFalse(sin["paginas"])
        self.assertEqual(sin["cobertura"]["fuera"], 2,
                         "el caso vacío es justo donde más falta hace")

    def test_sin_nada_cargado_no_inventa(self):
        c = busqueda.cobertura(self.cx)
        self.assertEqual((c["fojas"], c["indexadas"], c["fuera"]), (0, 0, 0))

    def test_cuando_se_pudo_leer_todo_no_queda_nada_afuera(self):
        self._lectura(self._pagina(1), ["ACTA"])
        self.cx.commit()
        busqueda.reindexar(self.cx)
        c = busqueda.cobertura(self.cx)
        self.assertEqual(c["fuera"], 0)
        self.assertEqual(c["indexadas"], c["fojas"])

    def test_el_indice_atrasado_no_se_declara_ilegible(self):
        """
        Si se procesó un lote y nadie reindexó, esas fojas NO se miraron —así que
        decir que quedaron fuera de esta búsqueda es cierto—, pero llamarlas
        ilegibles sería inventar. El número nunca puede afirmar más de lo que sabe.
        """
        self._lectura(self._pagina(1), ["ACTA"])
        self.cx.commit()                      # sin reindexar a propósito
        c = busqueda.cobertura(self.cx)
        self.assertEqual(c["indexadas"], 0)
        self.assertEqual(c["fuera"], 1)
        self.assertEqual(c["sin_procesar"], 0, "tiene lectura: procesada está")
        self.assertEqual(c["sin_texto"], 1)


class LaPantallaNuncaDiceSinCoincidenciasASecas(unittest.TestCase):
    """
    `assertIn` contra un archivo de tres mil líneas imprime el archivo entero cuando
    falla, y ahí el mensaje ya no se puede leer. Se busca a mano y se afirma un
    booleano, que falla con la frase y nada más.
    """

    def _hay(self, aguja, queja):
        self.assertTrue(aguja in APP, queja + f"\n  (falta en app.js: {aguja!r})")

    def test_el_caso_vacio_muestra_la_cobertura(self):
        self._hay("if (nada) return cob ||",
                  "el caso vacío volvió a contestar sin decir dónde buscó")

    def test_la_cobertura_va_tambien_cuando_hay_resultados(self):
        """
        Mostrarla sólo cuando no hay resultados es el mismo error con otra ropa:
        cuatro coincidencias sobre 241 fojas leídas de 260 no es lo mismo que cuatro
        sobre 260.
        """
        self._hay("return `${cob}",
                  "la cobertura dejó de mostrarse cuando hay resultados")

    def test_no_llama_ilegible_a_lo_que_no_se_proceso(self):
        import re
        i = APP.index("function coberturaHTML")
        cuerpo = APP[i:APP.index("\nfunction resultadosHTML")]
        # Sin los comentarios: el motivo por el que NO se usa esa palabra está escrito
        # ahí adentro, y buscarla en crudo se encuentra a sí misma.
        cuerpo = re.sub(r"//[^\n]*", "", cuerpo)
        self.assertNotIn("ilegible", cuerpo.lower(),
                         "«ilegible» afirma que se intentó leer y no se pudo; de la "
                         "foja que nunca se procesó eso no se sabe")
        self.assertIn("todavía no se", cuerpo,
                      "se perdió la distinción entre no procesada y sin texto")
        # Y que concuerde en número: «1 que se procesaron» se nota.
        for singular, plural_ in (("procesó", "procesaron"),):
            self.assertIn(f"'{singular}' : '{plural_}'", cuerpo,
                          f"la frase no concuerda en número: falta el par "
                          f"{singular}/{plural_}")
