"""
El núcleo documental general: una pieza es una pieza aunque el sistema no sepa leerla.

FASE 3 del pliego. Tres cosas que se sostienen acá:

  * la pieza tiene identidad propia, y resegmentar no la destruye;
  * un documento que ningún extractor reconoce se conserva, se ve y se clasifica a
    mano, pero no entra en ningún total;
  * un conjunto documental conserva el orden de las partes de una entrega, que es lo
    único que no se puede reconstruir después.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ufil import conjuntos, db, piezas
from ufil.aplicar_revision import aplicar
from ufil.capa2_extraccion import segmentar_piezas
from ufil.db import ahora

SHA_A = "a" * 64
SHA_B = "b" * 64


def _archivo(cx, sha, nombre, fojas):
    cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,paginas,ingerido_en)
                  VALUES (?,?,?,1,?,?)""", (sha, f"/x/{nombre}", nombre, fojas, ahora()))
    for n in range(1, fojas + 1):
        cx.execute("INSERT INTO pagina (sha256,nro,ancho_pt,alto_pt) VALUES (?,?,595,842)",
                   (sha, n))
    cx.commit()


def _pieza(cx, sha, orden, desde, hasta, tipo, estado="extraido", campo="monto"):
    doc = cx.execute(
        """INSERT INTO documento (sha256,orden,clave,pagina_desde,pagina_hasta,tipo,
                                  perfil,estado)
           VALUES (?,?,?,?,?,?,'p',?)""",
        (sha, orden, f"{sha}:{desde}", desde, hasta, tipo, estado)).lastrowid
    if campo:
        cx.execute("""INSERT INTO campo (documento_id,nombre,valor_literal,pagina_nro,
                                         x0,y0,x1,y1,confianza,estado)
                      VALUES (?,?,'$ 1.000,00',?,10,10,100,30,0.9,'automatico_alta')""",
                   (doc, campo, desde))
    cx.commit()
    return doc


class LaPiezaTieneIdentidadPropia(unittest.TestCase):
    """
    `orden` ordena, `id` lo asigna la base, `clave` identifica.

    Antes de esto, resegmentar borraba todas las piezas del archivo y las volvía a
    crear. Agregar un tipo documental —que es lo que este sistema tiene que poder hacer
    todo el tiempo— obligaba a reasociar el trabajo de las personas aunque la mayoría
    de las piezas no se hubiera movido un milímetro.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = db.abrir(Path(self.tmp.name) / "t.sqlite")
        _archivo(self.cx, SHA_A, "expediente.pdf", 4)

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def _por_ruta(self):
        """Lo mínimo que `segmentar_piezas` necesita cuando no usa el camino de rótulos."""
        return {"ocr_a": [(n, n, []) for n in range(1, 5)]}

    def test_resegmentar_conserva_la_pieza_que_empieza_en_la_misma_foja(self):
        # La foja 2 es una factura; la 4 también. Dos piezas.
        for n, clase in ((1, "contrato_personal"), (2, "factura"),
                         (3, "contrato_personal"), (4, "factura")):
            self.cx.execute("UPDATE pagina SET clasificacion=? WHERE sha256=? AND nro=?",
                            (clase, SHA_A, n))
        self.cx.commit()
        segmentar_piezas(self.cx, SHA_A, por_ruta=self._por_ruta())
        antes = {f["clave"]: f["id"] for f in self.cx.execute(
            "SELECT clave, id FROM documento WHERE sha256=?", (SHA_A,))}
        self.assertGreaterEqual(len(antes), 2)

        # Una persona revisa un campo de una de las piezas.
        doc = self.cx.execute(
            "SELECT id FROM documento WHERE sha256=? ORDER BY orden", (SHA_A,)).fetchone()["id"]
        self.cx.execute("""INSERT INTO campo (documento_id,nombre,valor_literal,pagina_nro,
                                              x0,y0,x1,y1,confianza,estado)
                           VALUES (?,'monto','$ 1.000,00',1,10,10,100,30,0.9,'automatico_alta')""",
                        (doc,))
        self.cx.commit()
        campo = self.cx.execute("SELECT id FROM campo WHERE documento_id=?", (doc,)).fetchone()["id"]
        aplicar(self.cx, campo, "corregir", "7777", "perez.ana")

        # Se vuelve a segmentar sin que haya cambiado nada.
        segmentar_piezas(self.cx, SHA_A, por_ruta=self._por_ruta())
        despues = {f["clave"]: f["id"] for f in self.cx.execute(
            "SELECT clave, id FROM documento WHERE sha256=?", (SHA_A,))}

        self.assertEqual(antes, despues,
                         "una pieza que sigue empezando en la misma foja es la misma "
                         "pieza: no se puede destruir y volver a crear")
        quedo = self.cx.execute(
            "SELECT valor_literal, revisado_por FROM campo WHERE id=?", (campo,)).fetchone()
        self.assertIsNotNone(quedo, "el campo revisado no se puede perder al resegmentar")
        self.assertEqual(quedo["revisado_por"], "perez.ana")

    def test_una_pieza_que_ya_no_sale_de_la_segmentacion_se_retira(self):
        for n in (1, 2):
            self.cx.execute("UPDATE pagina SET clasificacion='factura' WHERE sha256=? AND nro=?",
                            (SHA_A, n))
        self.cx.commit()
        segmentar_piezas(self.cx, SHA_A, por_ruta=self._por_ruta())
        self.assertEqual(
            self.cx.execute("SELECT COUNT(*) FROM documento WHERE sha256=?",
                            (SHA_A,)).fetchone()[0], 2)

        # La foja 2 deja de ser factura: esa pieza ya no existe.
        self.cx.execute("UPDATE pagina SET clasificacion=NULL WHERE sha256=? AND nro=2",
                        (SHA_A,))
        self.cx.commit()
        segmentar_piezas(self.cx, SHA_A, por_ruta=self._por_ruta())
        claves = [f["clave"] for f in self.cx.execute(
            "SELECT clave FROM documento WHERE sha256=?", (SHA_A,))]
        self.assertEqual(claves, [f"{SHA_A}:1"])

    def test_la_clasificacion_de_una_persona_no_la_pisa_el_sistema(self):
        self.cx.execute("UPDATE pagina SET clasificacion='factura' WHERE sha256=? AND nro=1",
                        (SHA_A,))
        self.cx.commit()
        segmentar_piezas(self.cx, SHA_A, por_ruta=self._por_ruta())
        doc = self.cx.execute("SELECT id FROM documento WHERE sha256=?", (SHA_A,)).fetchone()["id"]
        piezas.clasificar_a_mano(self.cx, doc, "remito", "perez.ana")

        segmentar_piezas(self.cx, SHA_A, por_ruta=self._por_ruta())
        f = self.cx.execute("SELECT tipo, clasificado_por FROM documento WHERE id=?",
                            (doc,)).fetchone()
        self.assertEqual(f["tipo"], "remito",
                         "lo que decidió una persona no lo pisa una corrida del sistema")
        self.assertEqual(f["clasificado_por"], "perez.ana")


class LoQueElSistemaTodaviaNoSabeLeer(unittest.TestCase):
    """
    Un documento que ningún extractor reconoce no es un error ni un descarte.

    Borrarlo convertía «el sistema todavía no sabe leer esto» en «esto no existe», que
    es lo peor que puede hacer un sistema que existe para que no se pierda un papel.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = db.abrir(Path(self.tmp.name) / "t.sqlite")
        _archivo(self.cx, SHA_A, "expediente.pdf", 3)

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_se_ve_pero_no_entra_en_ningun_total(self):
        _pieza(self.cx, SHA_A, 1, 1, 1, "factura", estado="extraido")
        _pieza(self.cx, SHA_A, 2, 2, 2, "factura", estado="sin_perfil", campo=None)

        self.assertEqual(len(piezas.sin_reconocer(self.cx)), 1,
                         "la pieza sin reconocer tiene que poder listarse")
        en_comprobantes = self.cx.execute(
            "SELECT COUNT(*) FROM v_comprobante WHERE sha256=?", (SHA_A,)).fetchone()[0]
        self.assertEqual(en_comprobantes, 1,
                         "de una pieza sin un solo campo leído no se puede sumar nada")
        en_todo = self.cx.execute(
            "SELECT COUNT(*) FROM v_documento_todo WHERE sha256=?", (SHA_A,)).fetchone()[0]
        self.assertEqual(en_todo, 2, "pero en el listado general se ve y se cuenta")
        familia = self.cx.execute(
            """SELECT familia, estado FROM v_documento_todo
                WHERE sha256=? AND estado='sin_perfil'""", (SHA_A,)).fetchone()
        self.assertIsNone(familia["familia"],
                          "no se la acomoda en la familia más parecida")

    def test_clasificarla_a_mano_queda_auditado(self):
        doc = _pieza(self.cx, SHA_A, 1, 1, 1, "factura", estado="sin_perfil", campo=None)
        piezas.clasificar_a_mano(self.cx, doc, "remito", "perez.ana")
        f = self.cx.execute("SELECT tipo, clasificado_por FROM documento WHERE id=?",
                            (doc,)).fetchone()
        self.assertEqual((f["tipo"], f["clasificado_por"]), ("remito", "perez.ana"))
        n = self.cx.execute(
            "SELECT COUNT(*) FROM auditoria WHERE accion='clasificar'").fetchone()[0]
        self.assertEqual(n, 1, "decir qué es un documento es una decisión y se audita")

    def test_no_se_le_puede_poner_un_tipo_inventado(self):
        doc = _pieza(self.cx, SHA_A, 1, 1, 1, "factura", estado="sin_perfil", campo=None)
        with self.assertRaises(piezas.NoSePuede):
            piezas.clasificar_a_mano(self.cx, doc, "cualquier_cosa", "perez.ana")
        with self.assertRaises(piezas.NoSePuede):
            piezas.clasificar_a_mano(self.cx, doc, "remito", "")


class CadaDocumentoEsUnaPiezaAunqueNoHayaExtractor(unittest.TestCase):
    """
    Encontrado en un legajo real: 1.628 fojas producían 54 piezas, todas facturas o
    contratos, porque las piezas salían sólo de los perfiles de extracción. 128 fojas de
    resoluciones, 48 de remitos y 19 de presupuestos —bien clasificadas— no formaban
    ninguna. Para reconstruir una contratación hacen falta justamente ésas.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = db.abrir(Path(self.tmp.name) / "t.sqlite")
        _archivo(self.cx, SHA_A, "expediente.pdf", 8)
        clases = {1: "factura", 2: "remito", 3: "continuacion", 4: "resolucion",
                  5: "presupuesto", 6: "continuacion", 7: "pliego", 8: "en_blanco"}
        for nro, clase in clases.items():
            self.cx.execute("UPDATE pagina SET clasificacion=? WHERE sha256=? AND nro=?",
                            (clase, SHA_A, nro))
        self.cx.commit()

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_remitos_resoluciones_y_presupuestos_son_piezas(self):
        segmentar_piezas(self.cx, SHA_A, por_ruta={"ocr_a": []})
        piezas_ = [(r["pagina_desde"], r["pagina_hasta"], r["tipo"]) for r in self.cx.execute(
            "SELECT pagina_desde, pagina_hasta, tipo FROM documento ORDER BY pagina_desde")]
        # El remito es de una foja (`fojas_tipicas=1`) y no absorbe la «continuación»:
        # en el legajo real, detrás de facturas, remitos y recibos hay 36 fojas así, y
        # mientras no existan los tipos de orden de compra, oferta o adjudicación muchas
        # pueden ser OTRO documento sin reconocer. Pegárselas mezclaría dos documentos.
        self.assertEqual(piezas_, [(1, 1, "factura"), (2, 2, "remito"), (4, 4, "resolucion"),
                                   (5, 6, "presupuesto")])

    def test_el_contexto_del_expediente_no_se_parte_en_pedazos(self):
        segmentar_piezas(self.cx, SHA_A, por_ruta={"ocr_a": []})
        tipos = {r[0] for r in self.cx.execute("SELECT tipo FROM documento")}
        self.assertNotIn("pliego", tipos)
        self.assertNotIn("en_blanco", tipos)


class UnaPiezaQueCambiaDeTipoNoRompeElArchivo(unittest.TestCase):
    """
    Encontrado en un legajo real: al aparecer el tipo «orden de compra», piezas que
    habían salido como facturas —con campos y normalizaciones— pasaron a un tipo sin
    extractor. Sus campos se borraban sin borrar antes lo que colgaba de ellos, y el
    archivo entero fallaba con «FOREIGN KEY constraint failed».
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = db.abrir(Path(self.tmp.name) / "t.sqlite")
        _archivo(self.cx, SHA_A, "expediente.pdf", 1)

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_pasa_a_sin_perfil_sin_romper_nada(self):
        from ufil.capa2_extraccion import extraer_campos
        doc = _pieza(self.cx, SHA_A, 1, 1, 1, "factura")
        campo = self.cx.execute("SELECT id FROM campo WHERE documento_id=?", (doc,)).fetchone()[0]
        self.cx.execute("INSERT INTO normalizacion (campo_id,tipo,valor_norm) VALUES (?,'monto','1000.00')",
                        (campo,))
        self.cx.execute("UPDATE documento SET tipo='orden_compra' WHERE id=?", (doc,))
        self.cx.execute("UPDATE pagina SET clasificacion='orden_compra' WHERE sha256=?", (SHA_A,))
        self.cx.commit()

        extraer_campos(self.cx, SHA_A, "auto", por_ruta={"ocr_a": [(1, None, [])]})

        f = self.cx.execute("SELECT tipo, estado FROM documento WHERE id=?", (doc,)).fetchone()
        self.assertEqual((f["tipo"], f["estado"]), ("orden_compra", "sin_perfil"),
                         "la pieza sigue existiendo, con su tipo, aunque no tenga extractor")
        self.assertEqual(self.cx.execute("SELECT COUNT(*) FROM normalizacion").fetchone()[0], 0)
        self.assertEqual(self.cx.execute("PRAGMA foreign_key_check").fetchall(), [])


class UnaTablaNoImpideBorrarSuPieza(unittest.TestCase):
    """
    Encontrado en el legajo real: dos archivos no se podían resegmentar.

    Una tabla es de la foja, no de la pieza; que esté adentro de una pieza es una
    conclusión que se rehace en cada corrida. Pero `tabla.documento_id` apuntaba a la
    pieza sin soltarse al borrarla, y SQLite abortaba el archivo entero con «FOREIGN KEY
    constraint failed». Como la transacción se deshacía, esos archivos tampoco releían
    sus precios.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = db.abrir(Path(self.tmp.name) / "t.sqlite")
        _archivo(self.cx, SHA_A, "expediente.pdf", 2)

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_resegmentar_suelta_la_tabla_y_no_la_pierde(self):
        from ufil.capa2_extraccion import _borrar_pieza
        doc = _pieza(self.cx, SHA_A, 1, 1, 1, "factura")
        self.cx.execute("""INSERT INTO tabla (sha256,pagina_nro,orden,documento_id,creado_en)
                           VALUES (?,1,1,?,?)""", (SHA_A, doc, db.ahora()))
        self.cx.commit()

        _borrar_pieza(self.cx, doc)

        self.assertEqual(self.cx.execute("SELECT COUNT(*) FROM tabla").fetchone()[0], 1,
                         "la tabla se queda: la próxima detección dirá de qué pieza es")
        self.assertIsNone(self.cx.execute("SELECT documento_id FROM tabla").fetchone()[0])
        self.assertEqual(self.cx.execute("PRAGMA foreign_key_check").fetchall(), [])


class UnaPiezaPuedeSeguirEnOtroArchivo(unittest.TestCase):
    """El límite de un PDF no es el límite de un documento."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = db.abrir(Path(self.tmp.name) / "t.sqlite")
        _archivo(self.cx, SHA_A, "parte-1.pdf", 3)
        _archivo(self.cx, SHA_B, "parte-2.pdf", 3)
        self.doc = _pieza(self.cx, SHA_A, 1, 3, 3, "remito")

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_la_continuidad_la_afirma_una_persona_y_queda_quien_fue(self):
        piezas.continuar_en(self.cx, self.doc, SHA_B, 1, 2, "perez.ana")
        t = piezas.tramos(self.cx, self.doc)
        self.assertEqual(len(t), 2)
        self.assertTrue(t[0]["principal"])
        self.assertEqual((t[1]["sha256"], t[1]["pagina_desde"], t[1]["pagina_hasta"]),
                         (SHA_B, 1, 2))
        self.assertEqual(t[1]["quien"], "perez.ana",
                         "el sistema puede sugerir dónde mirar; afirmarlo lo hace una persona")
        self.assertEqual(
            self.cx.execute("SELECT COUNT(*) FROM auditoria WHERE accion='continuar'"
                            ).fetchone()[0], 1)

    def test_no_se_puede_continuar_en_fojas_que_no_existen(self):
        with self.assertRaises(piezas.NoSePuede):
            piezas.continuar_en(self.cx, self.doc, SHA_B, 1, 99, "perez.ana")
        with self.assertRaises(piezas.NoSePuede):
            piezas.continuar_en(self.cx, self.doc, "c" * 64, 1, 1, "perez.ana")

    def test_separarla_la_saca_y_deja_rastro(self):
        piezas.continuar_en(self.cx, self.doc, SHA_B, 1, 2, "perez.ana")
        tramo = piezas.tramos(self.cx, self.doc)[1]["id"]
        piezas.separar_continuacion(self.cx, tramo, "gomez.luis")
        self.assertEqual(len(piezas.tramos(self.cx, self.doc)), 1)
        self.assertEqual(
            self.cx.execute("SELECT COUNT(*) FROM auditoria WHERE accion='separar'"
                            ).fetchone()[0], 1)


class ElConjuntoConservaElOrden(unittest.TestCase):
    """
    Una entrega son varias partes con un orden, y ese orden es del expediente.

    Hoy vive en el nombre de los archivos, que es el peor lugar posible: se pierde
    apenas alguien renombra uno.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = db.abrir(Path(self.tmp.name) / "t.sqlite")
        _archivo(self.cx, SHA_A, "parte-1.pdf", 2)
        _archivo(self.cx, SHA_B, "parte-2.pdf", 2)

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_las_partes_salen_en_el_orden_en_que_se_pusieron(self):
        c = conjuntos.crear(self.cx, "Oficio 12", organismo="Vialidad")
        conjuntos.agregar(self.cx, c["id"], SHA_A)
        conjuntos.agregar(self.cx, c["id"], SHA_B)
        v = conjuntos.ver(self.cx, c["id"])
        self.assertEqual([p["sha256"] for p in v["partes"]], [SHA_A, SHA_B])

        conjuntos.reordenar(self.cx, c["id"], [SHA_B, SHA_A])
        v = conjuntos.ver(self.cx, c["id"])
        self.assertEqual([p["sha256"] for p in v["partes"]], [SHA_B, SHA_A])

    def test_reordenar_exige_todas_las_partes(self):
        c = conjuntos.crear(self.cx, "Oficio 12")
        conjuntos.agregar(self.cx, c["id"], SHA_A)
        conjuntos.agregar(self.cx, c["id"], SHA_B)
        with self.assertRaises(conjuntos.NoSePuede):
            conjuntos.reordenar(self.cx, c["id"], [SHA_A])

    def test_dice_donde_sigue_sin_afirmar_que_sigue(self):
        c = conjuntos.crear(self.cx, "Oficio 12")
        conjuntos.agregar(self.cx, c["id"], SHA_A)
        conjuntos.agregar(self.cx, c["id"], SHA_B)
        v = conjuntos.vecino(self.cx, SHA_A)
        self.assertEqual(v["sha256"], SHA_B)
        self.assertIsNone(conjuntos.vecino(self.cx, SHA_B),
                          "la última parte no tiene siguiente, y eso no es un error")
        # Saber dónde mirar no crea ninguna continuidad por su cuenta.
        doc = _pieza(self.cx, SHA_A, 1, 2, 2, "remito")
        self.assertEqual(len(piezas.tramos(self.cx, doc)), 1)

    def test_un_archivo_puede_estar_en_dos_entregas(self):
        c1 = conjuntos.crear(self.cx, "Oficio 12")
        c2 = conjuntos.crear(self.cx, "Oficio 30")
        conjuntos.agregar(self.cx, c1["id"], SHA_A)
        conjuntos.agregar(self.cx, c2["id"], SHA_A)
        self.assertEqual(len(conjuntos.de_archivo(self.cx, SHA_A)), 2,
                         "el mismo PDF puede llegar dos veces, y eso es un hecho del "
                         "expediente que hay que poder ver")


if __name__ == "__main__":
    unittest.main()
