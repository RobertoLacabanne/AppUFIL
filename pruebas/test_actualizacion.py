"""
Que una capacidad nueva alcance al material viejo, sin volver a subirlo y sin repetir
lo caro. Y que el trabajo de las personas no termine aplicado al documento equivocado.

Es lo que el sistema tiene que poder hacer para crecer durante años: cuando aprende a
reconocer algo que antes no reconocía, los PDF que ya están adentro tienen que poder
aprovecharlo. Ver PROMPT_MAESTRO_APPUFIL.md §§7-11 y docs/evolucion-documental.md.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ufil import actualizacion as ac
from ufil import db
from ufil import versiones as vs
from ufil.aplicar_revision import aplicar
from ufil.capa2_extraccion import reaplicar_revisiones
from ufil.db import ahora

SHA = "a" * 64


def _base(tmp: Path):
    cx = db.abrir(tmp / "t.sqlite")
    cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,paginas,ingerido_en)
                  VALUES (?,'/x/expediente.pdf','expediente.pdf',1,3,?)""", (SHA, ahora()))
    for n in (1, 2, 3):
        cx.execute("INSERT INTO pagina (sha256,nro,ancho_pt,alto_pt) VALUES (?,?,595,842)",
                   (SHA, n))
    cx.commit()
    return cx


def _leer_todo(cx):
    """Simula que el OCR ya pasó por todas las fojas."""
    for p in cx.execute("SELECT id FROM pagina WHERE sha256=?", (SHA,)).fetchall():
        cx.execute("""INSERT INTO lectura (pagina_id,ruta,motor,version,confianza,ms,creado_en)
                      VALUES (?,'ocr_a','tesseract','5.4.0',0.9,10,?)""", (p["id"], ahora()))
    cx.commit()


def _pieza(cx, orden, desde, hasta, tipo, con_campo="monto", valor="$ 1.000,00", pagina=None):
    doc = cx.execute("""INSERT INTO documento (sha256,orden,pagina_desde,pagina_hasta,tipo,perfil)
                        VALUES (?,?,?,?,?,'p')""", (SHA, orden, desde, hasta, tipo)).lastrowid
    if con_campo:
        cx.execute("""INSERT INTO campo (documento_id,nombre,valor_literal,pagina_nro,
                                         x0,y0,x1,y1,confianza,estado)
                      VALUES (?,?,?,?,10,10,100,30,0.9,'automatico_alta')""",
                   (doc, con_campo, valor, pagina if pagina is not None else desde))
    cx.commit()
    return doc


def _borrar_piezas(cx):
    """El mismo orden de borrado que usa `capa2_extraccion.extraer_documento`."""
    for f in cx.execute("SELECT id FROM documento WHERE sha256=?", (SHA,)).fetchall():
        d = f["id"]
        sub = "SELECT id FROM campo WHERE documento_id=?"
        cx.execute(f"DELETE FROM persona_alias         WHERE campo_id IN ({sub})", (d,))
        cx.execute(f"DELETE FROM interpretacion_fuente WHERE campo_id IN ({sub})", (d,))
        cx.execute("DELETE FROM interpretacion_fuente  WHERE documento_id=?", (d,))
        cx.execute("DELETE FROM documento_persona      WHERE documento_id=?", (d,))
        cx.execute(f"DELETE FROM normalizacion         WHERE campo_id IN ({sub})", (d,))
        cx.execute("""DELETE FROM conflicto_variante WHERE conflicto_id IN
                      (SELECT id FROM conflicto WHERE documento_id=?)""", (d,))
        cx.execute("DELETE FROM conflicto WHERE documento_id=?", (d,))
        cx.execute("DELETE FROM campo     WHERE documento_id=?", (d,))
    cx.execute("DELETE FROM documento WHERE sha256=?", (SHA,))
    cx.commit()


class UnaCorreccionNoSeMudaDeDocumento(unittest.TestCase):
    """
    El defecto que motiva todo este incremento.

    `orden` es la posición de la pieza adentro del archivo y se recalcula contando los
    tramos en cada reproceso: no identifica a la pieza, identifica a un lugar en una
    fila que se rearma. El día que el sistema aprende un tipo documental nuevo, las
    piezas de atrás se corren un lugar.

    Antes de este arreglo, la corrección que una persona hacía sobre la 2ª pieza se
    reaplicaba sobre la que pasara a ocupar ese lugar, con estado `corregido` y
    confianza 1,0. O sea: entrando como firme en los totales, en silencio.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = _base(Path(self.tmp.name))

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass                      # Windows: la base todavía está tomada

    def test_la_correccion_queda_en_la_pieza_que_la_persona_miro(self):
        # Antes: contrato (fojas 1-2) y factura (foja 3).
        _pieza(self.cx, 1, 1, 2, "contrato_obra", con_campo=None)
        _pieza(self.cx, 2, 3, 3, "factura", pagina=3)
        campo = self.cx.execute(
            """SELECT c.id FROM campo c JOIN documento d ON d.id=c.documento_id
                WHERE d.orden=2""").fetchone()["id"]
        # Una persona corrige el importe DE LA FACTURA, mirando la foja 3.
        aplicar(self.cx, campo, "corregir", "5000", "perez.ana")

        # Llega una capacidad nueva: la foja 2 deja de ser continuación y pasa a ser una
        # pieza propia. La factura se corre de la 2ª posición a la 3ª.
        _borrar_piezas(self.cx)
        viejo = {1: (1, 2, "contrato_obra"), 2: (3, 3, "factura")}
        d1 = _pieza(self.cx, 1, 1, 1, "contrato_obra", con_campo=None)
        d2 = _pieza(self.cx, 2, 2, 2, "recibo", pagina=2)
        d3 = _pieza(self.cx, 3, 3, 3, "factura", pagina=3)
        piezas = [{"id": d1, "orden": 1, "pagina_desde": 1, "pagina_hasta": 1, "tipo": "contrato_obra"},
                  {"id": d2, "orden": 2, "pagina_desde": 2, "pagina_hasta": 2, "tipo": "recibo"},
                  {"id": d3, "orden": 3, "pagina_desde": 3, "pagina_hasta": 3, "tipo": "factura"}]
        reaplicar_revisiones(self.cx, SHA, piezas, viejo)

        recibo = self.cx.execute(
            """SELECT c.valor_literal, c.estado, c.revisado_por FROM campo c
                 JOIN documento d ON d.id=c.documento_id WHERE d.orden=2""").fetchone()
        factura = self.cx.execute(
            """SELECT c.valor_literal, c.estado, c.revisado_por FROM campo c
                 JOIN documento d ON d.id=c.documento_id WHERE d.orden=3""").fetchone()

        self.assertIsNone(
            recibo["revisado_por"],
            "la corrección que se hizo sobre la factura terminó aplicada al recibo: es "
            "el error que este arreglo existe para que no pase")
        self.assertEqual(
            factura["revisado_por"], "perez.ana",
            "la corrección tiene que seguir en la factura, que es la foja que la "
            "persona miró, aunque haya cambiado de posición")
        self.assertIn("5.000", factura["valor_literal"],
                      "y tiene que ser el valor que cargó la persona, no el leído")
        self.assertEqual(factura["estado"], "corregido")

    def test_si_no_se_puede_saber_a_cual_corresponde_no_se_aplica_a_ninguna(self):
        """
        Perder trabajo humano es malo; aplicarlo al documento equivocado es peor.

        Cuando la pieza que la persona revisó ya no existe, la revisión NO se aplica a
        la más parecida: queda marcada para que alguien diga a cuál corresponde.
        """
        _pieza(self.cx, 1, 3, 3, "factura", pagina=3)
        campo = self.cx.execute("SELECT id FROM campo").fetchone()["id"]
        aplicar(self.cx, campo, "corregir", "5000", "perez.ana")

        # La foja 3 deja de reconocerse y desaparece como pieza.
        _borrar_piezas(self.cx)
        d1 = _pieza(self.cx, 1, 1, 1, "contrato_obra", pagina=1)
        piezas = [{"id": d1, "orden": 1, "pagina_desde": 1, "pagina_hasta": 1,
                   "tipo": "contrato_obra"}]
        r = reaplicar_revisiones(self.cx, SHA, piezas, {1: (3, 3, "factura")})

        self.assertEqual(r["reaplicadas"], 0)
        self.assertEqual(r["a_reasociar"], 1)
        quedo = self.cx.execute(
            """SELECT c.revisado_por FROM campo c JOIN documento d ON d.id=c.documento_id
                WHERE d.orden=1""").fetchone()
        self.assertIsNone(quedo["revisado_por"],
                          "no se le puede encajar la corrección al único documento que "
                          "quedó sólo porque es el único que quedó")
        pendiente = ac.reasociaciones(self.cx)
        self.assertEqual(len(pendiente), 1, "la revisión tiene que seguir existiendo")
        self.assertEqual(pendiente[0]["quien"], "perez.ana")
        self.assertTrue(pendiente[0]["motivo"], "tiene que decir por qué quedó pendiente")

    def test_una_revision_vieja_sin_anclaje_no_se_aplica_a_ciegas(self):
        """
        Las revisiones hechas antes de que existiera el anclaje se pueden reaplicar por
        posición, pero SÓLO si la pieza que ocupa esa posición es la misma que antes.
        """
        _pieza(self.cx, 1, 1, 1, "contrato_obra", pagina=1)
        campo = self.cx.execute("SELECT id FROM campo").fetchone()["id"]
        aplicar(self.cx, campo, "corregir", "5000", "perez.ana")
        # Se le saca el anclaje: así quedaron las filas de una base anterior.
        self.cx.execute("UPDATE revision_humana SET ancla_pagina=NULL, ancla_x0=NULL")
        self.cx.commit()

        _borrar_piezas(self.cx)
        d1 = _pieza(self.cx, 1, 1, 1, "factura", pagina=1)     # otro tipo en el mismo lugar
        piezas = [{"id": d1, "orden": 1, "pagina_desde": 1, "pagina_hasta": 1,
                   "tipo": "factura"}]
        r = reaplicar_revisiones(self.cx, SHA, piezas, {1: (1, 1, "contrato_obra")})

        self.assertEqual(r["a_reasociar"], 1)
        self.assertEqual(r["reaplicadas"], 0)


class LoQueQuedoViejoYLoQueNo(unittest.TestCase):
    """
    Invalidación selectiva: si cambia una etapa se rehace esa y las que dependen de
    ella, y nada más. Es lo que permite agregar un extractor sin pagar otra vez el OCR.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = _base(Path(self.tmp.name))

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def _estado(self, plan, clave):
        return next(e for e in plan["etapas"] if e["clave"] == clave)

    def test_el_ocr_ya_hecho_se_reutiliza_en_una_base_sin_sellos(self):
        _leer_todo(self.cx)
        p = ac.plan(self.cx)
        lectura = self._estado(p, "lectura")
        self.assertEqual(lectura["estado"], "heredada")
        self.assertEqual(lectura["desactualizados"], 0,
                         "no se puede releer un acervo entero sólo porque antes no se "
                         "anotaba con qué versión se había leído")
        self.assertEqual(p["reutiliza"]["paginas_ocr"], 3)
        self.assertEqual(p["recalcula"]["paginas_ocr"], 0)

    def test_cambiar_una_etapa_de_arriba_no_toca_el_ocr(self):
        """
        Agregar un extractor tiene que alcanzar a los documentos viejos SIN releerlos.
        """
        _leer_todo(self.cx)
        for e in vs.ETAPAS:
            ac.sellar(self.cx, e.clave, "")
        for s in ("ingesta", "clasificacion", "segmentacion", "cotejo", "extraccion",
                  "normalizacion"):
            ac.sellar(self.cx, s, SHA)
        for p in self.cx.execute("SELECT id FROM pagina").fetchall():
            ac.sellar(self.cx, "lectura", str(p["id"]))
        self.cx.commit()
        self.assertTrue(ac.plan(self.cx)["vigente"], "recién sellado, no debería faltar nada")

        # Cambia la extracción: otro perfil, otro umbral, lo que sea.
        self.cx.execute("UPDATE resultado_etapa SET firma='otra' WHERE etapa='extraccion'")
        self.cx.commit()

        p = ac.plan(self.cx)
        self.assertEqual(self._estado(p, "lectura")["desactualizados"], 0,
                         "cambiar la extracción no puede costar un OCR")
        self.assertEqual(self._estado(p, "indice")["estado"], "vigente",
                         "el índice se apoya en la lectura, no en la extracción")
        self.assertGreater(self._estado(p, "extraccion")["desactualizados"], 0)
        for clave in ("normalizacion", "identidad", "interpretacion"):
            self.assertGreater(self._estado(p, clave)["desactualizados"], 0,
                               f"{clave} depende de la extracción y tiene que rehacerse")

    def test_la_cascada_va_solo_hacia_adelante(self):
        self.assertEqual(vs.dependientes("indice"), (),
                         "nada se apoya en el índice: invalidarlo no puede arrastrar nada")
        self.assertNotIn("lectura", vs.dependientes("extraccion"))
        self.assertIn("clasificacion", vs.dependientes("lectura"))
        self.assertIn("interpretacion", vs.dependientes("lectura"))

    def test_invalidar_marca_la_etapa_y_las_que_dependen(self):
        _leer_todo(self.cx)
        for e in vs.ETAPAS:
            ac.sellar(self.cx, e.clave, SHA if e.alcance == "archivo" else "")
        for p in self.cx.execute("SELECT id FROM pagina").fetchall():
            ac.sellar(self.cx, "lectura", str(p["id"]))
        self.cx.commit()

        tocadas = ac.invalidar(self.cx, "clasificacion")
        self.assertIn("clasificacion", tocadas)
        self.assertIn("extraccion", tocadas)
        self.assertNotIn("lectura", tocadas, "el OCR está antes, no puede quedar viejo")
        self.assertNotIn("ingesta", tocadas)


class UnaBaseVieja(unittest.TestCase):
    """
    Una base que ya venía trabajándose tiene que seguir funcionando y no perder nada:
    ni una foja leída, ni una revisión hecha por una persona.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta = Path(self.tmp.name) / "vieja.sqlite"

    def tearDown(self):
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_migrar_no_pierde_revisiones_y_las_ancla(self):
        cx = _base(Path(self.tmp.name))
        _leer_todo(cx)
        _pieza(cx, 1, 1, 1, "contrato_obra", pagina=1)
        campo = cx.execute("SELECT id FROM campo").fetchone()["id"]
        aplicar(cx, campo, "corregir", "5000", "perez.ana")
        # Se simula el estado anterior: la fila existe, sin anclaje.
        cx.execute("""UPDATE revision_humana SET ancla_pagina=NULL, ancla_x0=NULL,
                         ancla_y0=NULL, ancla_x1=NULL, ancla_y1=NULL,
                         ancla_desde=NULL, ancla_hasta=NULL, ancla_tipo=NULL""")
        cx.execute("PRAGMA user_version=16")
        cx.commit()
        cx.close()

        # Se vuelve a abrir: es lo que pasa al actualizar el programa.
        cx = db.abrir(Path(self.tmp.name) / "t.sqlite")
        r = cx.execute("SELECT * FROM revision_humana").fetchone()
        self.assertIsNotNone(r, "la revisión no se puede perder al migrar")
        self.assertEqual(r["quien"], "perez.ana")
        self.assertEqual(r["ancla_pagina"], 1,
                         "la migración tiene que aprender dónde estaba el campo, que es "
                         "la última vez que se puede saber sin adivinar")
        self.assertEqual(r["ancla_tipo"], "contrato_obra")
        self.assertEqual(cx.execute("SELECT COUNT(*) FROM lectura").fetchone()[0], 3,
                         "las fojas ya leídas no se tocan")
        cx.close()


class LaActualizacionSeRetoma(unittest.TestCase):
    """
    Un acervo grande son horas: la actualización se corta y se reanuda. Lo que ya se
    hizo queda sellado y no se repite.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = _base(Path(self.tmp.name))
        _leer_todo(self.cx)

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def test_cortarla_no_pierde_lo_hecho_ni_repite(self):
        cortar = {"ahora": False}
        ac.aplicar(self.cx, seguir=lambda: not cortar["ahora"])
        p = ac.plan(self.cx)
        self.assertTrue(p["vigente"],
                        f"después de actualizar no debería quedar nada viejo: "
                        f"{[e['clave'] for e in p['etapas'] if e['desactualizados']]}")

        # Volver a correrla no puede volver a hacer nada.
        r = ac.aplicar(self.cx)
        self.assertEqual(r["archivos"], 0, "no hay nada que rehacer, no se rehace nada")
        self.assertEqual(r["lectura_paginas"], 0, "y el OCR mucho menos")
        self.assertEqual(r["reutilizado_paginas_ocr"], 3)

    def test_forzar_una_etapa_la_rehace_y_arrastra_a_las_de_abajo(self):
        ac.aplicar(self.cx)
        self.assertTrue(ac.plan(self.cx)["vigente"])
        p = ac.plan(self.cx, forzar=("clasificacion",))
        self.assertFalse(p["vigente"])
        lectura = next(e for e in p["etapas"] if e["clave"] == "lectura")
        self.assertEqual(lectura["desactualizados"], 0,
                         "forzar la clasificación no puede arrastrar el OCR")


if __name__ == "__main__":
    unittest.main()
