"""
Las tablas del documento, con la estructura y no sólo el texto.

Una planilla dice lo que dice POR RENGLÓN. Aplanarla a texto corrido pierde justamente
lo que hace falta para comparar lo pactado con lo entregado y con lo facturado.

Lo otro que se prueba acá es la desconfianza: proponer una tabla donde hay un párrafo
con números llena la pantalla de basura y hace que nadie crea en las que sí están.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ufil import db, tablas as tb
from ufil.capa1_texto import Palabra
from ufil.db import ahora

SHA = "a" * 64
COLS = (60.0, 220.0, 330.0, 430.0)      # dónde arrancan las columnas


def _fila(y, textos, cols=COLS):
    """Un renglón de planilla: cada texto arrancando en su columna."""
    return [Palabra(t, cols[i], y, cols[i] + 70, y + 11, 0.9)
            for i, t in enumerate(textos) if t is not None]


def _planilla():
    """Un encabezado y cuatro renglones, alineados como una planilla de verdad."""
    p = _fila(100, ["Articulo", "Descripcion", "Cantidad", "Importe"])
    for i, y in enumerate((120, 140, 160, 180), start=1):
        p += _fila(y, [f"A-{i}", f"Item numero {i}", str(i * 3), f"{i * 1000}"])
    return p


LINEAS = (
    "En la ciudad de Parana a los 3 dias del mes de julio",
    "del ano 2019 entre la Direccion de Vialidad por una",
    "parte y por la otra el contratista se conviene lo que",
    "sigue por la suma de 45000 pesos pagaderos en 4 cuotas",
)


def _parrafo():
    """
    Texto corrido con números adentro. NO es una tabla.

    Los renglones tienen palabras distintas y largos distintos, como la prosa de
    verdad: un párrafo inventado con las mismas palabras en todas las líneas alinea
    perfecto por casualidad y no prueba nada.
    """
    salida = []
    for y, linea in zip((100, 118, 136, 154), LINEAS):
        x = 60.0
        for palabra in linea.split():
            ancho = len(palabra) * 6.0
            salida.append(Palabra(palabra, x, y, x + ancho, y + 11, 0.9))
            x += ancho + 7                     # el espacio de imprenta
    return salida


def _base(tmp: Path, fojas: int = 2):
    """Una base con lecturas DE VERDAD: la celda referencia la lectura de la que salió."""
    cx = db.abrir(tmp / "t.sqlite")
    cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,paginas,ingerido_en)
                  VALUES (?,'/x/e.pdf','e.pdf',1,?,?)""", (SHA, fojas, ahora()))
    for n in range(1, fojas + 1):
        pid = cx.execute(
            "INSERT INTO pagina (sha256,nro,ancho_pt,alto_pt) VALUES (?,?,595,842)",
            (SHA, n)).lastrowid
        cx.execute("""INSERT INTO lectura (pagina_id,ruta,motor,version,confianza,ms,creado_en)
                      VALUES (?,'ocr_a','tesseract','5.4.0',0.9,10,?)""", (pid, ahora()))
    cx.commit()
    return cx


def _lecturas(cx):
    """El id de lectura de cada foja, que es lo que la celda guarda como origen."""
    return {r["nro"]: r["lid"] for r in cx.execute(
        """SELECT p.nro, l.id AS lid FROM pagina p JOIN lectura l ON l.pagina_id = p.id
            WHERE p.sha256=?""", (SHA,))}


class ReconocerUnaTablaYNoUnParrafo(unittest.TestCase):

    def test_una_planilla_se_reconoce_con_sus_filas_y_columnas(self):
        t = tb.detectar_en_pagina(_planilla(), 595, 842)
        self.assertEqual(len(t), 1, "esto es una tabla")
        self.assertEqual(t[0]["columnas"], 4)
        self.assertEqual(t[0]["filas"], 5, "el encabezado y los cuatro renglones")

    def test_un_parrafo_con_numeros_no_es_una_tabla(self):
        self.assertEqual(tb.detectar_en_pagina(_parrafo(), 595, 842), [],
                         "proponer una tabla donde hay prosa hace que nadie crea en "
                         "las tablas que sí están")

    def test_dos_renglones_alineados_no_alcanzan(self):
        p = _fila(100, ["A", "B", "C"]) + _fila(120, ["D", "E", "F"])
        self.assertEqual(tb.detectar_en_pagina(p, 595, 842), [],
                         "dos renglones son dos renglones, no una tabla")

    def test_cada_celda_sabe_donde_esta_en_la_foja(self):
        t = tb.detectar_en_pagina(_planilla(), 595, 842)[0]
        for c in t["celdas"]:
            self.assertIsNotNone(c["caja"], "una cifra que no se puede señalar en la "
                                            "foja no sirve como prueba")
            x0, y0, x1, y1 = c["caja"]
            self.assertLess(x0, x1)
            self.assertLess(y0, y1)

    def test_el_encabezado_se_distingue_de_los_datos(self):
        t = tb.detectar_en_pagina(_planilla(), 595, 842)[0]
        cabeza = [c for c in t["celdas"] if c.get("es_encabezado")]
        self.assertTrue(cabeza, "la primera fila dice qué son las de abajo")
        self.assertTrue(all(c["fila"] == 0 for c in cabeza))


class GuardarlaYLeerlaPorRenglon(unittest.TestCase):

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
        lid = _lecturas(self.cx)
        por_ruta = {"ocr_a": [(n, lid[n], p) for n, p in por_pagina.items()]}
        return tb.detectar_archivo(self.cx, SHA, por_ruta=por_ruta)

    def test_se_guarda_con_sus_celdas_y_se_recupera(self):
        r = self._detectar({1: _planilla(), 2: []})
        self.assertEqual(r["tablas"], 1)
        guardadas = tb.de_archivo(self.cx, SHA)
        self.assertEqual(len(guardadas), 1)
        self.assertEqual(guardadas[0]["columnas"], 4)
        self.assertEqual(len(guardadas[0]["celdas"]), 20)

    def test_los_renglones_traen_los_valores_con_su_encabezado(self):
        self._detectar({1: _planilla(), 2: []})
        t = tb.de_archivo(self.cx, SHA)[0]
        filas = tb.renglones(self.cx, t["id"])
        self.assertEqual(len(filas), 4, "cuatro renglones de datos, sin el encabezado")
        self.assertIn("Cantidad", filas[0]["valores"])
        self.assertEqual(filas[0]["valores"]["Articulo"], "A-1")
        self.assertEqual(filas[3]["valores"]["Importe"], "4000")
        self.assertTrue(all(c["caja"] for c in filas[0]["celdas"]))

    def test_volver_a_detectar_no_duplica(self):
        self._detectar({1: _planilla(), 2: []})
        self._detectar({1: _planilla(), 2: []})
        self.assertEqual(len(tb.de_archivo(self.cx, SHA)), 1)


class UnaPlanillaQueSigueEnLaFojaSiguiente(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = _base(Path(self.tmp.name))
        lid = _lecturas(self.cx)
        por_ruta = {"ocr_a": [(1, lid[1], _planilla()), (2, lid[2], _planilla())]}
        tb.detectar_archivo(self.cx, SHA, por_ruta=por_ruta)
        self.t1, self.t2 = [t["id"] for t in tb.de_archivo(self.cx, SHA)]

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_la_continuidad_se_propone_pero_no_se_da_por_cierta(self):
        t2 = tb.ver(self.cx, self.t2)
        self.assertEqual(t2["continua_de"], self.t1, "se propone")
        self.assertIsNone(t2["union_quien"],
                          "dos planillas distintas del mismo formulario tienen las "
                          "mismas columnas: confirmarlo es de una persona")

    def test_confirmarla_deja_quien_fue(self):
        tb.confirmar_continuidad(self.cx, self.t2, self.t1, "perez.ana")
        self.assertEqual(tb.ver(self.cx, self.t2)["union_quien"], "perez.ana")

    def test_cortarla_la_deja_como_tabla_propia(self):
        tb.confirmar_continuidad(self.cx, self.t2, None, "perez.ana")
        t2 = tb.ver(self.cx, self.t2)
        self.assertIsNone(t2["continua_de"])
        self.assertEqual(t2["union_quien"], "perez.ana")

    def test_leerla_entera_sigue_la_continuacion_y_saltea_el_encabezado_repetido(self):
        tb.confirmar_continuidad(self.cx, self.t2, self.t1, "perez.ana")
        filas = tb.renglones(self.cx, self.t1)
        self.assertEqual(len(filas), 8,
                         "cuatro renglones de cada foja, y el encabezado repetido "
                         "arriba de la continuación no es un renglón de datos")
        self.assertEqual({f["pagina_nro"] for f in filas}, {1, 2})

    def test_una_tabla_no_puede_continuar_de_si_misma(self):
        with self.assertRaises(tb.NoSePuede):
            tb.confirmar_continuidad(self.cx, self.t1, self.t1, "perez.ana")
        with self.assertRaises(tb.NoSePuede):
            tb.confirmar_continuidad(self.cx, self.t1, None, "")


if __name__ == "__main__":
    unittest.main()
