"""
La foliatura del papel no es el número de página del PDF.

Un escrito que dice «a fojas 47» se refiere a lo que está escrito en la hoja. Si el
sistema contesta con la página 47 del archivo, manda a alguien a mirar otro papel, y en
un legajo penal eso no es un detalle de presentación.

La otra regla que se prueba acá: **no se inventa una foliatura**. Que no se haya
detectado un número no significa que la foja no esté foliada.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ufil import db, foliatura as fol
from ufil.capa1_texto import Palabra
from ufil.db import ahora

SHA = "a" * 64
ANCHO, ALTO = 595.0, 842.0


def _base(tmp: Path, fojas: int = 3):
    cx = db.abrir(tmp / "t.sqlite")
    cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,paginas,ingerido_en)
                  VALUES (?,'/x/e.pdf','e.pdf',1,?,?)""", (SHA, fojas, ahora()))
    for n in range(1, fojas + 1):
        cx.execute("INSERT INTO pagina (sha256,nro,ancho_pt,alto_pt) VALUES (?,?,?,?)",
                   (SHA, n, ANCHO, ALTO))
    cx.commit()
    return cx


def _pal(texto, x0, y0, ancho=22, alto=11):
    return Palabra(texto, x0, y0, x0 + ancho, y0 + alto, 0.9)


def _arriba_derecha(texto):
    """Donde cae el sello foliador en casi todos los expedientes."""
    return _pal(texto, ANCHO - 70, 24)


def _cuerpo(*textos):
    """Texto del documento, en el medio de la hoja."""
    return [_pal(t, 70 + i * 60, ALTO / 2) for i, t in enumerate(textos)]


class LeerLoQueDiceElPapel(unittest.TestCase):

    def test_reconoce_las_formas_que_trae_el_papel(self):
        casos = {
            "47": (47, None, None),
            "f. 47": (47, None, None),
            "fs. 47": (47, None, None),
            "foja 47": (47, None, None),
            "47 bis": (47, "bis", None),
            "47 ter": (47, "ter", None),
            "47 vta.": (47, None, "reverso"),
            "47 v.": (47, None, "reverso"),
        }
        for texto, (numero, sufijo, cara) in casos.items():
            leido = fol.parsear(texto)
            self.assertIsNotNone(leido, f"«{texto}» es una foliatura")
            self.assertEqual((leido["numero"], leido["sufijo"], leido["cara"]),
                             (numero, sufijo, cara), f"al leer «{texto}»")
            self.assertEqual(leido["literal"], texto,
                             "el literal se conserva tal como está escrito")

    def test_no_toma_por_foliatura_cualquier_numero(self):
        for texto in ("", "   ", "página", "2016", "12345", "art. 5 inc. b",
                      "$ 1.000,00", "20-16613186-0"):
            if texto.strip() == "2016":
                continue        # cuatro dígitos sí puede ser una foliatura: decide el lugar
            self.assertIsNone(fol.parsear(texto), f"«{texto}» no es una foliatura")


class DetectarSinInventar(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = _base(Path(self.tmp.name))

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def _detectar(self, por_pagina):
        por_ruta = {"ocr_a": [(nro, nro, palabras) for nro, palabras in por_pagina.items()]}
        return fol.detectar_archivo(self.cx, SHA, por_ruta=por_ruta)

    def test_toma_el_numero_del_margen_y_no_el_del_cuerpo(self):
        r = self._detectar({
            1: [_arriba_derecha("47")] + _cuerpo("Expediente", "1234", "del", "año"),
            2: _cuerpo("nada", "en", "el", "margen"),
            3: [_arriba_derecha("49")],
        })
        self.assertEqual(r["detectadas"], 2)
        self.assertEqual(r["sin_detectar"], 1)
        hojas = {f["pagina_pdf"]: f["foliaturas"] for f in fol.de_archivo(self.cx, SHA)}
        self.assertEqual(hojas[1][0]["numero"], 47)
        self.assertEqual(hojas[3][0]["numero"], 49)
        self.assertEqual(hojas[2], [],
                         "no se detectó nada, y eso NO es «esta foja no está foliada»")

    def test_un_numero_metido_en_una_frase_no_es_foliatura(self):
        # Un número en el margen pero rodeado de palabras: es parte de un encabezado.
        linea = [_pal("Expediente", 60, 26), _pal("1234", 130, 26),
                 _pal("del", 170, 26), _pal("año", 200, 26)]
        r = self._detectar({1: linea, 2: [], 3: []})
        self.assertEqual(r["detectadas"], 0,
                         "un número pegado a otras palabras es parte de una frase")

    def test_lo_que_escribio_una_persona_no_lo_pisa_una_corrida(self):
        self._detectar({1: [_arriba_derecha("47")], 2: [], 3: []})
        pagina_id = self.cx.execute(
            "SELECT id FROM pagina WHERE sha256=? AND nro=1", (SHA,)).fetchone()["id"]
        fol.poner_a_mano(self.cx, pagina_id, "47 bis", "perez.ana")

        self._detectar({1: [_arriba_derecha("47")], 2: [], 3: []})
        f = self.cx.execute("SELECT literal, origen, quien FROM foliatura WHERE pagina_id=?",
                            (pagina_id,)).fetchone()
        self.assertEqual((f["literal"], f["origen"], f["quien"]),
                         ("47 bis", "humano", "perez.ana"))

    def test_decir_que_no_tiene_foliatura_es_una_afirmacion_y_se_guarda(self):
        pagina_id = self.cx.execute(
            "SELECT id FROM pagina WHERE sha256=? AND nro=2", (SHA,)).fetchone()["id"]
        fol.poner_a_mano(self.cx, pagina_id, None, "perez.ana", estado="ausente")
        f = self.cx.execute("SELECT estado, numero, origen FROM foliatura WHERE pagina_id=?",
                            (pagina_id,)).fetchone()
        self.assertEqual(f["estado"], "ausente")
        self.assertIsNone(f["numero"])
        self.assertEqual(
            self.cx.execute("SELECT COUNT(*) FROM auditoria WHERE accion='ausente'"
                            ).fetchone()[0], 1,
            "afirmar algo sobre el papel es una decisión y queda auditada")

    def test_una_foja_puede_tener_dos_foliaturas(self):
        """Un expediente incorporado a otro trae su numeración y recibe la nueva."""
        pagina_id = self.cx.execute(
            "SELECT id FROM pagina WHERE sha256=? AND nro=1", (SHA,)).fetchone()["id"]
        fol.poner_a_mano(self.cx, pagina_id, "47", "perez.ana")
        fol.poner_a_mano(self.cx, pagina_id, "12", "perez.ana", serie="expediente_origen")
        hojas = {f["pagina_pdf"]: f["foliaturas"] for f in fol.de_archivo(self.cx, SHA)}
        self.assertEqual(len(hojas[1]), 2)
        self.assertEqual({s["serie"] for s in hojas[1]},
                         {"principal", "expediente_origen"})


class EncontrarLaFojaQueDiceElEscrito(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = _base(Path(self.tmp.name), fojas=4)
        self.ids = {r["nro"]: r["id"] for r in self.cx.execute(
            "SELECT nro, id FROM pagina WHERE sha256=?", (SHA,))}

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_buscar_por_foja_no_devuelve_la_pagina_del_pdf(self):
        fol.poner_a_mano(self.cx, self.ids[1], "46", "perez.ana")
        fol.poner_a_mano(self.cx, self.ids[2], "47", "perez.ana")
        r = fol.buscar(self.cx, "47")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["pagina_pdf"], 2,
                         "la foja 47 está en la página 2 del PDF, y hay que decir las dos")
        self.assertEqual(r[0]["literal"], "47")

    def test_dos_fojas_con_el_mismo_numero_se_devuelven_las_dos(self):
        fol.poner_a_mano(self.cx, self.ids[1], "47", "perez.ana")
        fol.poner_a_mano(self.cx, self.ids[3], "47", "perez.ana")
        self.assertEqual(len(fol.buscar(self.cx, "47")), 2,
                         "elegir una sola sería esconder que hay dos")

    def test_los_saltos_se_señalan_y_no_se_interpretan(self):
        fol.poner_a_mano(self.cx, self.ids[1], "46", "perez.ana")
        fol.poner_a_mano(self.cx, self.ids[2], "49", "perez.ana")   # faltan dos
        fol.poner_a_mano(self.cx, self.ids[3], "49", "perez.ana")   # repetida
        fol.poner_a_mano(self.cx, self.ids[4], "48", "perez.ana")   # va para atrás
        clases = [s["clase"] for s in fol.saltos(self.cx, SHA)]
        self.assertEqual(clases, ["salto", "repetida", "retrocede"])

    def test_buscar_algo_que_no_es_una_foliatura_no_devuelve_nada(self):
        fol.poner_a_mano(self.cx, self.ids[1], "47", "perez.ana")
        self.assertEqual(fol.buscar(self.cx, "no es un folio"), [])


if __name__ == "__main__":
    unittest.main()
