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
from unittest.mock import patch
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
        d1 = _pieza(self.cx, 1, 1, 1, "contrato_obra", con_campo=None)
        d2 = _pieza(self.cx, 2, 2, 2, "recibo", pagina=2)
        d3 = _pieza(self.cx, 3, 3, 3, "factura", pagina=3)
        piezas = [{"id": d1, "orden": 1, "pagina_desde": 1, "pagina_hasta": 1, "tipo": "contrato_obra"},
                  {"id": d2, "orden": 2, "pagina_desde": 2, "pagina_hasta": 2, "tipo": "recibo"},
                  {"id": d3, "orden": 3, "pagina_desde": 3, "pagina_hasta": 3, "tipo": "factura"}]
        reaplicar_revisiones(self.cx, SHA, piezas)

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

    def test_confirmar_que_un_campo_falta_sobrevive_al_reparto_nuevo(self):
        """
        Encontrado en un legajo real: dos verificaciones de campos sin valor iban a pasar
        a «requiere reasociación» en la primera actualización. Un campo que no está en el
        papel no tiene foja ni recuadro, así que su revisión no tenía anclaje de foja; sí
        tiene el de su pieza —tramo de fojas y tipo—, y con eso alcanza.
        """
        doc = _pieza(self.cx, 1, 3, 3, "factura", con_campo=None)
        campo = self.cx.execute(
            """INSERT INTO campo (documento_id,nombre,nulo_motivo,estado)
               VALUES (?,'monto','ausente','no_revisado')""", (doc,)).lastrowid
        self.cx.commit()
        aplicar(self.cx, campo, "ausente", None, "perez.ana")
        self.assertEqual(ac.plan(self.cx)["revisiones"]["sin_ancla"], 0,
                         "anclada a su pieza no es una revisión sin anclaje")

        # Aparece una pieza nueva adelante: la factura pasa del 1º al 2º lugar.
        _borrar_piezas(self.cx)
        d1 = _pieza(self.cx, 1, 1, 2, "contrato_obra", con_campo=None)
        d2 = _pieza(self.cx, 2, 3, 3, "factura", con_campo=None)
        for d in (d1, d2):
            self.cx.execute("""INSERT INTO campo (documento_id,nombre,nulo_motivo,estado)
                               VALUES (?,'monto','ausente','no_revisado')""", (d,))
        self.cx.commit()
        piezas = [{"id": d1, "orden": 1, "pagina_desde": 1, "pagina_hasta": 2, "tipo": "contrato_obra"},
                  {"id": d2, "orden": 2, "pagina_desde": 3, "pagina_hasta": 3, "tipo": "factura"}]
        r = reaplicar_revisiones(self.cx, SHA, piezas)

        self.assertEqual(r["reaplicadas"], 1, r)
        estados = dict(self.cx.execute("SELECT documento_id, estado FROM campo").fetchall())
        self.assertEqual(estados[d2], "ausente_confirmado", "la confirmación sigue a su pieza")
        self.assertEqual(estados[d1], "no_revisado", "y no se muda a la que ocupó su lugar")

    def test_un_anclaje_numerado_desde_la_pieza_no_se_muda_a_la_foja_1_del_archivo(self):
        """
        Encontrado en un legajo real: una versión anterior numeraba las fojas de un
        contrato desde el principio de la pieza, y dos correcciones quedaron ancladas «en
        la foja 1» siendo de contratos que empiezan en las fojas 23 y 25. Ahí se perdían
        (en la foja 1 no había ese campo). Si la hubiera, la corrección se mudaba de pieza.
        """
        contrato = _pieza(self.cx, 1, 2, 3, "contrato_obra", pagina=2)
        campo = self.cx.execute("SELECT id FROM campo WHERE documento_id=?",
                                (contrato,)).fetchone()["id"]
        aplicar(self.cx, campo, "corregir", "5000", "perez.ana")
        # El anclaje como lo dejaba la versión anterior: foja 1 de la pieza.
        self.cx.execute("UPDATE revision_humana SET ancla_pagina=1")
        self.cx.commit()

        # Aparece una factura en la foja 1 del archivo, con su propio monto.
        _borrar_piezas(self.cx)
        d1 = _pieza(self.cx, 1, 1, 1, "factura", pagina=1)
        d2 = _pieza(self.cx, 2, 2, 3, "contrato_obra", pagina=2)
        piezas = [{"id": d1, "orden": 1, "pagina_desde": 1, "pagina_hasta": 1, "tipo": "factura"},
                  {"id": d2, "orden": 2, "pagina_desde": 2, "pagina_hasta": 3, "tipo": "contrato_obra"}]
        r = reaplicar_revisiones(self.cx, SHA, piezas)

        self.assertEqual(r["reaplicadas"], 1, r)
        de = {row["documento_id"]: row for row in self.cx.execute(
            "SELECT documento_id, revisado_por, valor_literal FROM campo")}
        self.assertIsNone(de[d1]["revisado_por"], "la corrección del contrato no va a la factura")
        self.assertEqual(de[d2]["revisado_por"], "perez.ana")
        self.assertEqual(self.cx.execute("SELECT ancla_pagina FROM revision_humana").fetchone()[0],
                         2, "y el anclaje queda escrito con la foja del archivo")

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
        r = reaplicar_revisiones(self.cx, SHA, piezas)

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

    def test_dos_revisiones_que_se_corren_de_lugar_no_se_pisan(self):
        """
        Cuando aparece una pieza nueva adelante, TODAS las de atrás se corren un lugar.

        La clave de `revision_humana` incluye el `orden`, así que al mudar la primera
        revisión a su lugar nuevo, ese lugar ya está ocupado por la segunda —que todavía
        no se miró—. Escribiendo sobre la marcha, esa segunda decisión humana se borra
        sin que nadie se entere. Las dos tienen que sobrevivir y cada una quedar en la
        pieza que le corresponde.
        """
        _pieza(self.cx, 1, 2, 2, "factura", pagina=2)
        _pieza(self.cx, 2, 3, 3, "factura", pagina=3)
        for orden, valor in ((1, "1000"), (2, "2000")):
            campo = self.cx.execute(
                """SELECT c.id FROM campo c JOIN documento d ON d.id=c.documento_id
                    WHERE d.orden=?""", (orden,)).fetchone()["id"]
            aplicar(self.cx, campo, "corregir", valor, f"revisor{orden}")
        self.assertEqual(self.cx.execute("SELECT COUNT(*) FROM revision_humana").fetchone()[0], 2)

        # Aparece una pieza en la foja 1: las dos de atrás se corren un lugar.
        _borrar_piezas(self.cx)
        d1 = _pieza(self.cx, 1, 1, 1, "contrato_obra", pagina=1)
        d2 = _pieza(self.cx, 2, 2, 2, "factura", pagina=2)
        d3 = _pieza(self.cx, 3, 3, 3, "factura", pagina=3)
        piezas = [{"id": d1, "orden": 1, "pagina_desde": 1, "pagina_hasta": 1, "tipo": "contrato_obra"},
                  {"id": d2, "orden": 2, "pagina_desde": 2, "pagina_hasta": 2, "tipo": "factura"},
                  {"id": d3, "orden": 3, "pagina_desde": 3, "pagina_hasta": 3, "tipo": "factura"}]
        r = reaplicar_revisiones(self.cx, SHA, piezas)

        self.assertEqual(r["reaplicadas"], 2, "las dos revisiones tienen que aplicarse")
        self.assertEqual(
            self.cx.execute("SELECT COUNT(*) FROM revision_humana").fetchone()[0], 2,
            "ninguna de las dos se puede perder al correrse de lugar")
        foja2 = self.cx.execute(
            """SELECT c.valor_literal, c.revisado_por FROM campo c
                 JOIN documento d ON d.id=c.documento_id WHERE d.pagina_desde=2""").fetchone()
        foja3 = self.cx.execute(
            """SELECT c.valor_literal, c.revisado_por FROM campo c
                 JOIN documento d ON d.id=c.documento_id WHERE d.pagina_desde=3""").fetchone()
        self.assertEqual(foja2["revisado_por"], "revisor1")
        self.assertIn("1.000", foja2["valor_literal"])
        self.assertEqual(foja3["revisado_por"], "revisor2")
        self.assertIn("2.000", foja3["valor_literal"])

    def test_una_revision_vieja_sin_anclaje_no_se_aplica_a_ciegas(self):
        """
        Una revisión anterior al anclaje sólo se puede reaplicar por posición, y eso
        vale únicamente mientras el reparto del archivo en piezas no cambie.

        Quien sabe si cambió es la segmentación, así que es ella la que las marca. Acá
        se comprueba el otro extremo: si la posición ni siquiera existe, la revisión no
        se le encaja a la pieza que haya quedado.
        """
        _pieza(self.cx, 2, 2, 2, "factura", pagina=2)
        campo = self.cx.execute("SELECT id FROM campo").fetchone()["id"]
        aplicar(self.cx, campo, "corregir", "5000", "perez.ana")
        self.cx.execute("UPDATE revision_humana SET ancla_pagina=NULL, ancla_x0=NULL")
        self.cx.commit()

        _borrar_piezas(self.cx)
        d1 = _pieza(self.cx, 1, 1, 1, "factura", pagina=1)   # ya no hay una 2ª pieza
        piezas = [{"id": d1, "orden": 1, "pagina_desde": 1, "pagina_hasta": 1,
                   "tipo": "factura"}]
        r = reaplicar_revisiones(self.cx, SHA, piezas)

        self.assertEqual(r["a_reasociar"], 1)
        self.assertEqual(r["reaplicadas"], 0)
        quedo = self.cx.execute(
            "SELECT revisado_por FROM campo WHERE documento_id=?", (d1,)).fetchone()
        self.assertIsNone(quedo["revisado_por"],
                          "no se le puede encajar a la única pieza que quedó")

    def test_una_revision_que_se_descarto_no_vuelve_sola(self):
        """
        Si una persona decidió que una revisión desplazada no corresponde, reprocesar
        no puede resucitarla. Y la fila tiene que seguir existiendo: descartar no es
        borrar, es una decisión que queda registrada.
        """
        d1 = _pieza(self.cx, 1, 1, 1, "factura", pagina=1)
        campo = self.cx.execute("SELECT id FROM campo").fetchone()["id"]
        aplicar(self.cx, campo, "corregir", "5000", "perez.ana")
        self.cx.execute("UPDATE revision_humana SET estado='descartada'")
        self.cx.execute("UPDATE campo SET valor_literal='$ 1.000,00', estado='automatico_alta', "
                        "revisado_por=NULL WHERE id=?", (campo,))
        self.cx.commit()

        piezas = [{"id": d1, "orden": 1, "pagina_desde": 1, "pagina_hasta": 1,
                   "tipo": "factura"}]
        r = reaplicar_revisiones(self.cx, SHA, piezas)

        self.assertEqual(r["reaplicadas"], 0, "una decisión descartada no se reaplica")
        self.assertEqual(
            self.cx.execute("SELECT COUNT(*) FROM revision_humana").fetchone()[0], 1,
            "y la fila no se puede perder: descartar no es borrar")
        self.assertIsNone(
            self.cx.execute("SELECT revisado_por FROM campo WHERE id=?",
                            (campo,)).fetchone()["revisado_por"])


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

    def _aplicar_contando_fojas_leidas(self) -> set:
        """Corre la actualización con un OCR simulado y devuelve qué fojas leyó."""
        leidas = set()

        def leer_lote(cx, shas, **_):
            for r in cx.execute("""SELECT id FROM pagina p WHERE NOT EXISTS
                                     (SELECT 1 FROM lectura l WHERE l.pagina_id=p.id)""").fetchall():
                cx.execute("""INSERT INTO lectura (pagina_id,ruta,motor,version,confianza,ms,creado_en)
                              VALUES (?,'ocr_a','tesseract','5.4.0',0.9,10,?)""", (r["id"], ahora()))
                leidas.add(r["id"])
            cx.commit()
            return {"paginas": len(leidas)}

        from ufil import capa1_texto
        with patch.object(capa1_texto, "leer_lote", side_effect=leer_lote):
            ac.aplicar(self.cx)
        return leidas

    def test_una_foja_vieja_se_relee_sola(self):
        """
        Antes una sola foja vieja se llevaba puesto el archivo entero. El plan lo decía
        con honestidad, pero en un legajo real eso era releer cientos de fojas bien
        leídas. Ahora se relee la foja vieja y nada más, y el plan dice exactamente eso:
        no puede prometer reutilizar lo que va a releer, ni al revés.
        """
        _leer_todo(self.cx)
        for p in self.cx.execute("SELECT id FROM pagina").fetchall():
            ac.sellar(self.cx, "lectura", str(p["id"]))
        una = self.cx.execute("SELECT id FROM pagina ORDER BY nro LIMIT 1").fetchone()["id"]
        self.cx.execute("UPDATE resultado_etapa SET firma='otra' "
                        "WHERE etapa='lectura' AND alcance_id=?", (str(una),))
        self.cx.commit()
        otras = {r[0] for r in self.cx.execute(
            "SELECT id FROM lectura WHERE pagina_id<>?", (una,))}

        p = ac.plan(self.cx)
        self.assertEqual(p["recalcula"]["paginas_ocr"], 1)
        self.assertEqual(p["reutiliza"]["paginas_ocr"], 2)

        self.assertEqual(self._aplicar_contando_fojas_leidas(), {una})
        self.assertTrue(otras <= {r[0] for r in self.cx.execute("SELECT id FROM lectura")},
                        "las lecturas de las otras dos fojas siguen siendo las mismas")

    def test_un_archivo_leido_a_medias_lee_sólo_lo_que_falta(self):
        # Medido en un legajo real: un archivo con 410 fojas leídas y 340 sin leer iba a
        # releer las 750. La forma mínima del caso: tres fojas, dos leídas.
        pids = [r[0] for r in self.cx.execute("SELECT id FROM pagina ORDER BY nro")]
        for pid in pids[:2]:
            self.cx.execute("""INSERT INTO lectura (pagina_id,ruta,motor,version,confianza,ms,creado_en)
                               VALUES (?,'ocr_a','tesseract','5.4.0',0.9,10,?)""", (pid, ahora()))
        self.cx.commit()
        antes = {r[0] for r in self.cx.execute("SELECT id FROM lectura")}

        p = ac.plan(self.cx)
        self.assertEqual(p["recalcula"]["paginas_ocr"], 1)
        self.assertEqual(p["reutiliza"]["paginas_ocr"], 2)

        self.assertEqual(self._aplicar_contando_fojas_leidas(), {pids[2]})
        self.assertTrue(antes <= {r[0] for r in self.cx.execute("SELECT id FROM lectura")})

    def test_cambiar_una_etapa_de_arriba_no_toca_el_ocr(self):
        """
        Agregar un extractor tiene que alcanzar a los documentos viejos SIN releerlos.
        """
        _leer_todo(self.cx)
        for e in vs.ETAPAS:
            ac.sellar(self.cx, e.clave, "")
        # La lista sale de `POR_ARCHIVO`, no escrita a mano: agregar una etapa nueva al
        # pipeline no puede hacer fallar una prueba que no habla de ella.
        for s in ("ingesta",) + ac.POR_ARCHIVO:
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
        # Del índice cuelga el reconocimiento de menciones, que lee el texto ya
        # indexado. Lo que importa es que rehacer el índice NO arrastre nada caro:
        # invalidarlo no puede terminar costando un OCR.
        self.assertNotIn("lectura", vs.dependientes("indice"),
                         "rehacer el índice no puede costar un OCR")
        self.assertTrue(all(not vs.POR_CLAVE[c].caro for c in vs.dependientes("indice")),
                        "de una etapa barata no puede colgar una cara")
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


class LasEtapasCorrenPorSeparado(unittest.TestCase):
    """
    FASE 1: clasificación, cotejo, segmentación y extracción son cuatro cosas, no una.

    Antes eran una sola pasada por archivo, y eso hacía que cualquier cambio en
    cualquiera de las cuatro obligara a rehacer las cuatro. Agregar un extractor
    —lo más frecuente que va a pasar acá— volvía a clasificar fojas que nadie tocó y a
    resegmentar archivos que no cambiaron, y resegmentar obliga a reasociar el trabajo
    de las personas.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = _base(Path(self.tmp.name))
        _leer_todo(self.cx)
        # Todo sellado y al día: el punto de partida de los dos escenarios.
        ac.aplicar(self.cx)

    def tearDown(self):
        self.cx.close()
        try:
            self.tmp.cleanup()
        except PermissionError:
            pass

    def _viejas(self, forzar=()):
        return ac.desactualizadas_por_etapa(self.cx, forzar=forzar)

    def test_cambiar_la_extraccion_no_vuelve_a_clasificar_ni_a_segmentar(self):
        self.cx.execute("UPDATE resultado_etapa SET firma='otra' WHERE etapa='extraccion'")
        self.cx.commit()
        viejas = self._viejas()
        self.assertIn("extraccion", viejas)
        self.assertNotIn("clasificacion", viejas,
                         "clasificar una foja no depende de si sabemos extraerle campos")
        self.assertNotIn("segmentacion", viejas,
                         "resegmentar por un extractor nuevo obligaría a reasociar el "
                         "trabajo de las personas sin ningún motivo")
        self.assertNotIn("lectura", viejas, "y el OCR mucho menos")
        self.assertNotIn("cotejo", viejas)

    def test_cambiar_la_segmentacion_no_vuelve_a_leer_ni_a_clasificar(self):
        self.cx.execute("UPDATE resultado_etapa SET firma='otra' WHERE etapa='segmentacion'")
        self.cx.commit()
        viejas = self._viejas()
        self.assertIn("segmentacion", viejas)
        self.assertIn("extraccion", viejas, "los campos cuelgan de la pieza: se rehacen")
        self.assertNotIn("lectura", viejas)
        self.assertNotIn("clasificacion", viejas,
                         "la clasificación está ANTES de la segmentación, no después")

    def test_cambiar_la_clasificacion_arrastra_hacia_adelante_y_no_el_ocr(self):
        self.cx.execute("UPDATE resultado_etapa SET firma='otra' WHERE etapa='clasificacion'")
        self.cx.commit()
        viejas = self._viejas()
        for clave in ("clasificacion", "segmentacion", "cotejo", "extraccion"):
            self.assertIn(clave, viejas, f"{clave} se apoya en la clasificación")
        self.assertNotIn("lectura", viejas, "clasificar de nuevo no puede costar un OCR")

    def test_extraer_no_resegmenta(self):
        """
        `extraer_campos` trabaja sobre las piezas que YA están: no recalcula tramos.

        Se comprueba con una pieza cuyo tramo la segmentación nunca habría producido
        —la clasificación de estas fojas no la sostiene—. Si la extracción resegmentara,
        la pieza no sería la que se le dio. Que conserve su `id` cuando la reconoce un
        perfil está comprobado sobre corpus real, no acá: con fojas sintéticas ningún
        perfil reconoce nada y la pieza se retira, que es lo que corresponde.
        """
        from ufil import capa2_extraccion as c2
        _pieza(self.cx, 7, 1, 3, "factura", pagina=1)     # tramo inventado, orden 7
        antes = self.cx.execute(
            """SELECT orden, pagina_desde, pagina_hasta FROM documento
                WHERE sha256=?""", (SHA,)).fetchall()
        self.assertEqual([tuple(f) for f in antes], [(7, 1, 3)])
        c2.extraer_campos(self.cx, SHA)
        # Ningún extractor la reconoce, así que queda `sin_perfil` —un documento que
        # todavía no sabemos leer sigue siendo un documento— pero en ningún momento
        # aparecieron los tramos que la segmentación habría calculado.
        despues = self.cx.execute(
            """SELECT orden, pagina_desde, pagina_hasta, estado FROM documento
                WHERE sha256=?""", (SHA,)).fetchall()
        self.assertEqual([tuple(f) for f in despues], [(7, 1, 3, "sin_perfil")],
                         "la extracción no puede inventar tramos ni borrar la pieza")


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
