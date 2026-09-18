"""
Lo que el papel dice y quién es en realidad: son dos cosas.

Y una tercera regla, que es la que más cuesta sostener: **unir de más es peor que no
unir**. Juntar en una ficha lo que dos papeles dicen de personas distintas es, en un
legajo penal, exactamente lo que no puede pasar. Por eso el sistema une sólo por clave
fuerte y todo lo demás lo propone.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ufil import db, entidades as en, relaciones as rel
from ufil.db import ahora

SHA = "a" * 64
# CUIT con dígito verificador válido, construido para la prueba. No es de nadie:
# el prefijo 30 y el cuerpo son arbitrarios y el verificador se calculó a mano.
CUIT_OK = "30-71044766-3"


def _base(tmp: Path):
    cx = db.abrir(tmp / "t.sqlite")
    cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,paginas,ingerido_en)
                  VALUES (?,'/x/e.pdf','e.pdf',1,3,?)""", (SHA, ahora()))
    for n in (1, 2, 3):
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


class ElPapelDiceYLaEntidadEs(unittest.TestCase):

    def test_reconoce_lo_que_tiene_forma_inconfundible(self):
        m = en.detectar_en_texto(
            f"Expte. N 201.602 la firma OBRAS DEL NORTE S.A. CUIT {CUIT_OK} "
            f"presenta la factura 0001-00012345")
        clases = {x["clase"] for x in m}
        self.assertIn("expediente", clases)
        self.assertIn("empresa", clases)
        self.assertIn("comprobante", clases)

    def test_no_toma_por_cuit_cualquier_tira_de_once_numeros(self):
        self.assertFalse(en._cuit_valido("20-16613186-0"),
                         "el dígito verificador es lo que separa un CUIT de un código")
        self.assertTrue(en._cuit_valido(CUIT_OK))
        m = en.detectar_en_texto("el codigo 20-16613186-0 no es un CUIT")
        self.assertEqual([x for x in m if x["clase"] == "empresa"], [])

    def test_el_prefijo_dice_si_es_una_persona_o_una_sociedad(self):
        """
        Un CUIL que empieza en 20 es de una persona; un CUIT que empieza en 30, de una
        sociedad. Meter a una persona en la ficha de una empresa manda a quien consulta
        al lugar equivocado, y apareció de verdad sobre el corpus real.
        """
        self.assertEqual(en.clase_de_cuit("20-60181590-8"), "persona")
        self.assertEqual(en.clase_de_cuit("27-12345678-4"), "persona")
        self.assertEqual(en.clase_de_cuit(CUIT_OK), "empresa")
        clases = {m["clase"]: m["literal"] for m in en.detectar_en_texto(
            f"CUIL 20-60181590-8 y CUIT {CUIT_OK}")}
        self.assertEqual(set(clases), {"persona", "empresa"})

    def test_normalizar_junta_lo_que_es_lo_mismo_y_no_mas(self):
        self.assertEqual(en.normalizar("Dirección de Vialidad"),
                         en.normalizar("DIRECCION DE VIALIDAD"))
        self.assertEqual(en.normalizar("Obras S.A."), en.normalizar("OBRAS SA"))
        self.assertNotEqual(en.normalizar("González, Juan"),
                            en.normalizar("González, Juan C."))


class UnaMencionSiempreSePuedeCitar(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = _base(Path(self.tmp.name))
        self.doc = _pieza(self.cx, 1, 1)

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_la_mencion_guarda_donde_lo_dice(self):
        en.anotar(self.cx, "organismo", "Dirección de Vialidad", origen="texto",
                  documento_id=self.doc, sha256=SHA, pagina_nro=1,
                  caja=(10, 20, 100, 32), confianza=0.8)
        m = self.cx.execute("SELECT * FROM mencion").fetchone()
        self.assertEqual((m["sha256"], m["pagina_nro"]), (SHA, 1))
        self.assertEqual([m["x0"], m["y1"]], [10, 32])
        self.assertIsNone(m["entidad_id"],
                          "sin clave fuerte, a quién se refiere lo decide una persona")

    def test_una_mencion_sin_fuente_no_entra(self):
        with self.assertRaises(en.NoSePuede):
            en.anotar(self.cx, "organismo", "Vialidad", origen="", documento_id=self.doc)
        with self.assertRaises(en.NoSePuede):
            en.anotar(self.cx, "inventada", "X", origen="texto", documento_id=self.doc)

    def test_la_clave_fuerte_une_sola_y_nada_mas_une_solo(self):
        d2 = _pieza(self.cx, 2, 2)
        en.anotar(self.cx, "empresa", "OBRAS DEL NORTE S.A.", origen="texto",
                  documento_id=self.doc, clave_fuerte="30710447669")
        en.anotar(self.cx, "empresa", "Obras del Norte", origen="texto",
                  documento_id=d2, clave_fuerte="30710447669")
        self.assertEqual(self.cx.execute("SELECT COUNT(*) FROM entidad").fetchone()[0], 1,
                         "el mismo CUIT es la misma empresa")
        e = self.cx.execute("SELECT id FROM entidad").fetchone()["id"]
        self.assertEqual(len(en.ver(self.cx, e)["menciones"]), 2,
                         "y la ficha muestra las dos formas en que la nombra el papel")

    def test_lo_parecido_se_propone_no_se_une(self):
        d2 = _pieza(self.cx, 2, 2)
        for doc in (self.doc, d2):
            en.anotar(self.cx, "organismo", "Dirección de Vialidad", origen="texto",
                      documento_id=doc)
        self.assertEqual(self.cx.execute("SELECT COUNT(*) FROM entidad").fetchone()[0], 0,
                         "unir de más es peor que no unir")
        p = en.proponer_fusiones(self.cx)
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["veces"], 2)
        self.assertEqual(len(en.sin_resolver(self.cx)), 2,
                         "y mientras tanto se puede decir cuánto falta resolver")

    def test_confirmarla_la_resuelve_y_sobrevive_al_reproceso(self):
        d2 = _pieza(self.cx, 2, 2)
        for doc in (self.doc, d2):
            en.anotar(self.cx, "organismo", "Dirección de Vialidad", origen="texto",
                      documento_id=doc)
        norm = en.normalizar("Dirección de Vialidad")
        r = en.confirmar_entidad(self.cx, "organismo", norm,
                                 "Dirección de Vialidad", "perez.ana")
        self.assertEqual(r["menciones"], 2)
        self.assertEqual(len(en.sin_resolver(self.cx)), 0)
        self.assertEqual(
            self.cx.execute("SELECT decision FROM entidad_fusion").fetchone()["decision"],
            "aceptada", "la decisión se guarda por identidad, no por id")

    def test_lo_rechazado_no_se_vuelve_a_proponer(self):
        d2 = _pieza(self.cx, 2, 2)
        for doc in (self.doc, d2):
            en.anotar(self.cx, "organismo", "Vialidad", origen="texto", documento_id=doc)
        en.rechazar_fusion(self.cx, "organismo", en.normalizar("Vialidad"), "perez.ana")
        self.assertEqual(en.proponer_fusiones(self.cx), [],
                         "si alguien ya dijo que no son la misma, no se vuelve a preguntar")

    def test_la_misma_persona_no_aparece_dos_veces(self):
        """
        El carril de siempre guarda `DNI:16613186`; el texto de las fojas trae el CUIL
        entero. Son la misma persona, y mostrarla dos veces es inventar dos donde hay
        una. Apareció de verdad sobre el corpus real.
        """
        self.assertEqual(en.documento_del_cuil("20-60181590-8"), "60181590")
        self.cx.execute("INSERT INTO persona (clave_fuerte, creado_en) VALUES ('DNI:60181590',?)",
                        (ahora(),))
        pid = self.cx.execute("SELECT id FROM persona").fetchone()["id"]
        self.cx.execute("""INSERT INTO persona_alias (persona_id, nombre_literal, nombre_norm)
                           VALUES (?, 'Almada, Héctor', 'almada hector')""", (pid,))
        en.anotar(self.cx, "persona", "20-60181590-8", origen="texto",
                  documento_id=self.doc, clave_fuerte="20601815908")
        self.cx.commit()
        personas = [e for e in en.listar(self.cx) if e["clase"] == "persona"]
        self.assertEqual(len(personas), 1,
                         "el CUIL lleva el documento adentro: es la misma persona")
        self.assertEqual(personas[0]["carril"], "persona",
                         "gana el carril de siempre, que sostiene las fichas")

    def test_la_ficha_unificada_incluye_a_las_personas(self):
        self.cx.execute("INSERT INTO persona (clave_fuerte, creado_en) VALUES ('X1',?)",
                        (ahora(),))
        pid = self.cx.execute("SELECT id FROM persona").fetchone()["id"]
        self.cx.execute("""INSERT INTO persona_alias (persona_id, nombre_literal, nombre_norm)
                           VALUES (?, 'Pérez, Ana', 'perez ana')""", (pid,))
        en.anotar(self.cx, "empresa", "OBRAS S.A.", origen="texto",
                  documento_id=self.doc, clave_fuerte="30710447669")
        self.cx.commit()
        clases = {e["clase"] for e in en.listar(self.cx)}
        self.assertEqual(clases, {"persona", "empresa"},
                         "quien consulta no tiene por qué saber que por dentro "
                         "son dos carriles")


class LoQueUnDocumentoDiceDeOtro(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = _base(Path(self.tmp.name))
        self.d1 = _pieza(self.cx, 1, 1, "orden_compra" if False else "factura")
        self.d2 = _pieza(self.cx, 2, 2)

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_una_relacion_sin_fuente_no_entra(self):
        with self.assertRaises(rel.NoSePuede):
            rel.anotar(self.cx, "cita", fuente="", desde_doc=self.d1, hasta_doc=self.d2)
        with self.assertRaises(rel.NoSePuede):
            rel.anotar(self.cx, "inventada", fuente="humano",
                       desde_doc=self.d1, hasta_doc=self.d2)
        with self.assertRaises(rel.NoSePuede):
            rel.anotar(self.cx, "cita", fuente="humano", desde_doc=self.d1,
                       hasta_doc=self.d1)

    def test_nace_propuesta_y_confirmarla_es_una_decision(self):
        rel.anotar(self.cx, "cita", fuente="campo:x", desde_doc=self.d1,
                   hasta_doc=self.d2, confianza=0.6)
        r = rel.pendientes(self.cx)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["que_dice"], "cita")
        with self.assertRaises(rel.NoSePuede):
            rel.decidir(self.cx, r[0]["id"], True, "")
        rel.decidir(self.cx, r[0]["id"], True, "perez.ana")
        self.assertEqual(rel.pendientes(self.cx), [])
        self.assertEqual(rel.de_documento(self.cx, self.d1)[0]["estado"], "confirmada")

    def test_rechazarla_no_la_borra(self):
        rel.anotar(self.cx, "cita", fuente="campo:x", desde_doc=self.d1, hasta_doc=self.d2)
        r = rel.pendientes(self.cx)[0]
        rel.decidir(self.cx, r["id"], False, "perez.ana")
        quedan = rel.de_documento(self.cx, self.d1)
        self.assertEqual(len(quedan), 1)
        self.assertEqual(quedan[0]["estado"], "rechazada",
                         "borrarla haría que el sistema la vuelva a proponer y que "
                         "nadie sepa que ya se había descartado")
        self.assertEqual(
            self.cx.execute("SELECT COUNT(*) FROM auditoria WHERE accion='relacionar'"
                            ).fetchone()[0], 1)

    def test_facturar_no_es_documentar_un_pago(self):
        self.assertIn("factura", rel.TIPOS)
        self.assertIn("documenta_pago", rel.TIPOS)
        self.assertNotEqual(rel.TIPOS["factura"], rel.TIPOS["documenta_pago"],
                            "confundirlos es dar por cobrado lo que sólo está "
                            "facturado")

    def test_el_mismo_comprobante_en_dos_piezas_se_propone(self):
        for doc in (self.d1, self.d2):
            en.anotar(self.cx, "comprobante", "factura 0001-00012345", origen="texto",
                      documento_id=doc)
        n = rel.proponer_por_comprobante(self.cx)
        self.assertEqual(n, 1)
        p = rel.pendientes(self.cx)[0]
        self.assertEqual(p["estado"] if "estado" in p else "propuesta", "propuesta")
        self.assertTrue(p["fuente"].startswith("comprobante:"),
                        "la relación dice de dónde sale")


if __name__ == "__main__":
    unittest.main()
