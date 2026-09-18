"""
Búsqueda exhaustiva, consultas guardadas y colecciones.

Tres cosas que se sostienen acá:

  * una búsqueda que corta en sesenta y no lo dice está afirmando «no hay más», que es
    una afirmación que nadie verificó;
  * una colección NO es el resultado de una consulta: si un escrito cita «las nueve
    piezas de la colección X», esas nueve no pueden pasar a ser once porque alguien
    cargó un PDF nuevo;
  * el OCR confunde el uno con la ele, y quien busca «BENITEZ» y no encuentra nada tiene
    derecho a que el sistema le diga que pudo haberse leído «BEN1TEZ».
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ufil import busqueda, colecciones as col, db
from ufil.db import ahora

SHA = "a" * 64


def _base(tmp: Path, fojas: int = 3):
    cx = db.abrir(tmp / "t.sqlite")
    cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,paginas,ingerido_en)
                  VALUES (?,'/x/e.pdf','e.pdf',1,?,?)""", (SHA, fojas, ahora()))
    for n in range(1, fojas + 1):
        cx.execute("INSERT INTO pagina (sha256,nro,ancho_pt,alto_pt) VALUES (?,?,595,842)",
                   (SHA, n))
    cx.commit()
    return cx


def _pieza(cx, orden, desde, tipo="factura"):
    doc = cx.execute("""INSERT INTO documento (sha256,orden,clave,pagina_desde,pagina_hasta,
                                               tipo,perfil)
                        VALUES (?,?,?,?,?,?,'p')""",
                     (SHA, orden, f"{SHA}:{desde}", desde, desde, tipo)).lastrowid
    cx.commit()
    return doc


class LaBusquedaDiceCuantosHay(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = _base(Path(self.tmp.name))
        # Doce piezas con el mismo apellido: más de una página de resultados.
        for i in range(1, 13):
            d = _pieza(self.cx, i, 1)
            self.cx.execute("""INSERT INTO campo (documento_id,nombre,valor_literal,
                                                  pagina_nro,x0,y0,x1,y1,confianza,estado)
                               VALUES (?,'nombre','BENÍTEZ, Marcelo',1,10,10,90,30,
                                       0.9,'automatico_alta')""", (d,))
        self.cx.commit()

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_devuelve_el_total_y_no_solo_la_pagina(self):
        r = busqueda.buscar(self.cx, "BENITEZ", limite=5)
        self.assertEqual(len(r["campos"]), 5, "trae la página pedida")
        self.assertEqual(r["campos_total"], 12, "y dice cuántos hay de verdad")
        self.assertTrue(r["hay_mas"],
                        "cortar en cinco y callarlo es afirmar «no hay más»")

    def test_la_pagina_siguiente_trae_lo_que_falta_y_no_repite(self):
        a = busqueda.buscar(self.cx, "BENITEZ", limite=5, desde=0)["campos"]
        b = busqueda.buscar(self.cx, "BENITEZ", limite=5, desde=5)["campos"]
        c = busqueda.buscar(self.cx, "BENITEZ", limite=5, desde=10)["campos"]
        ids = [x["documento_id"] for x in a + b + c]
        self.assertEqual(len(ids), 12)
        self.assertEqual(len(set(ids)), 12, "ninguna pieza puede salir dos veces")
        self.assertFalse(busqueda.buscar(self.cx, "BENITEZ", limite=5,
                                         desde=10)["hay_mas"])

    def test_la_cobertura_va_siempre(self):
        r = busqueda.buscar(self.cx, "BENITEZ")
        self.assertIn("cobertura", r)
        vacio = busqueda.buscar(self.cx, "no-existe-esto")
        self.assertEqual(vacio["campos_total"], 0)
        self.assertIn("cobertura", vacio,
                      "«sin resultados» y «no se buscó en todo» no son lo mismo")


class LoQueElOcrPudoHaberLeidoMal(unittest.TestCase):

    def test_ofrece_variantes_de_lo_que_se_confunde(self):
        v = busqueda.variantes_de("BENITEZ")
        self.assertIn("ben1tez", v, "el uno y la ele se confunden en cualquier escaneo")
        self.assertTrue(all(x != "benitez" for x in v))

    def test_no_ofrece_variantes_de_algo_demasiado_corto(self):
        self.assertEqual(busqueda.variantes_de("ab"), [],
                         "sobre dos letras todo es una variante de todo")

    def test_devuelve_pocas_y_no_una_lista_inutil(self):
        self.assertLessEqual(len(busqueda.variantes_de("1011010")), 6)


class UnaColeccionNoEsUnaConsulta(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = _base(Path(self.tmp.name))
        self.d1 = _pieza(self.cx, 1, 1)
        self.d2 = _pieza(self.cx, 2, 2)

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_lo_apartado_no_cambia_porque_entren_datos_nuevos(self):
        c = col.crear(self.cx, "Para el escrito", "perez.ana")
        col.agregar(self.cx, c["id"], "documento", str(self.d1), "perez.ana")
        self.assertEqual(len(col.ver(self.cx, c["id"])["items"]), 1)
        # Entra material nuevo que cumple el mismo criterio.
        _pieza(self.cx, 3, 3)
        self.assertEqual(len(col.ver(self.cx, c["id"])["items"]), 1,
                         "si un escrito cita las piezas de una colección, esas piezas "
                         "no pueden cambiar solas")

    def test_los_items_se_describen_y_no_son_solo_ids(self):
        c = col.crear(self.cx, "Para la audiencia", "perez.ana")
        col.agregar(self.cx, c["id"], "documento", str(self.d1), "perez.ana",
                    nota="la que discute el monto")
        it = col.ver(self.cx, c["id"])["items"][0]
        self.assertEqual(it["archivo"], "e.pdf")
        self.assertEqual(it["que_es"], "factura")
        self.assertEqual(it["nota"], "la que discute el monto")

    def test_no_se_puede_apartar_algo_que_no_existe(self):
        c = col.crear(self.cx, "X", "perez.ana")
        with self.assertRaises(col.NoSePuede):
            col.agregar(self.cx, c["id"], "documento", "99999", "perez.ana")
        with self.assertRaises(col.NoSePuede):
            col.agregar(self.cx, c["id"], "foja", "no-es-una-foja", "perez.ana")
        with self.assertRaises(col.NoSePuede):
            col.agregar(self.cx, c["id"], "inventada", "1", "perez.ana")

    def test_apartar_dos_veces_lo_mismo_no_lo_duplica(self):
        c = col.crear(self.cx, "X", "perez.ana")
        col.agregar(self.cx, c["id"], "documento", str(self.d1), "perez.ana")
        col.agregar(self.cx, c["id"], "documento", str(self.d1), "perez.ana")
        self.assertEqual(len(col.ver(self.cx, c["id"])["items"]), 1)

    def test_dice_en_que_colecciones_esta_una_pieza(self):
        for nombre in ("Una", "Otra"):
            c = col.crear(self.cx, nombre, "perez.ana")
            col.agregar(self.cx, c["id"], "documento", str(self.d1), "perez.ana")
        self.assertEqual(len(col.de_documento(self.cx, self.d1)), 2)
        self.assertEqual(len(col.de_documento(self.cx, self.d2)), 0)

    def test_una_foja_tambien_se_puede_apartar(self):
        c = col.crear(self.cx, "Fojas sueltas", "perez.ana")
        col.agregar(self.cx, c["id"], "foja", f"{SHA}:2", "perez.ana")
        it = col.ver(self.cx, c["id"])["items"][0]
        self.assertEqual((it["que_es"], it["fojas"]), ("foja", "2"))


class LaConsultaQueSeVuelveAEscribirVeinteVeces(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = _base(Path(self.tmp.name))

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_se_guarda_con_sus_filtros_y_se_recupera_igual(self):
        col.guardar_consulta(self.cx, "Comprobantes del proveedor", "BENITEZ",
                             "perez.ana", filtros={"familia": "comprobante",
                                                   "desde": "2019-03-01"})
        g = col.consultas(self.cx)[0]
        self.assertEqual(g["consulta"], "BENITEZ")
        self.assertEqual(g["filtros"]["familia"], "comprobante",
                         "sin los filtros, dos personas comparando resultados no "
                         "están mirando lo mismo")

    def test_usarla_deja_rastro_de_que_sirve(self):
        col.guardar_consulta(self.cx, "X", "algo", "perez.ana")
        cid = col.consultas(self.cx)[0]["id"]
        col.usar_consulta(self.cx, cid)
        col.usar_consulta(self.cx, cid)
        self.assertEqual(col.consultas(self.cx)[0]["veces"], 2)

    def test_no_se_guarda_una_consulta_sin_nombre_ni_vacia(self):
        with self.assertRaises(col.NoSePuede):
            col.guardar_consulta(self.cx, "", "algo", "perez.ana")
        with self.assertRaises(col.NoSePuede):
            col.guardar_consulta(self.cx, "X", "", "perez.ana")
        with self.assertRaises(col.NoSePuede):
            col.guardar_consulta(self.cx, "X", "algo", "")

    def test_guardar_con_el_mismo_nombre_la_reemplaza_y_no_duplica(self):
        col.guardar_consulta(self.cx, "X", "uno", "perez.ana")
        col.guardar_consulta(self.cx, "X", "dos", "perez.ana")
        self.assertEqual(len(col.consultas(self.cx)), 1)
        self.assertEqual(col.consultas(self.cx)[0]["consulta"], "dos")


if __name__ == "__main__":
    unittest.main()
