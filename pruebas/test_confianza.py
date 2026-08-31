"""
Pruebas de regresión del MODELO DE CONFIANZA.

Cada una fija un defecto que estaba en producción y que se veía en la pantalla:

  · Entraban a la tabla de personas nombres de OCR como «SOSA, Rosa lI» con confianza
    0,31, o «DUARTE) Sidvia Nit PA AA A a a», como si fueran personas consolidadas.
  · El acumulado mostraba $5.847.000 y adentro había $761.900 de montos que en ese
    mismo momento estaban en la cola esperando revisión.
  · Y el panel decía que sumaba «sólo los montos leídos con seguridad».

La regla que estas pruebas custodian es una sola: un valor pendiente o en conflicto no
alimenta resultados firmes. Vive en la base y en las consultas, no en la interfaz,
porque una regla que sólo está en la pantalla se saltea sola la próxima vez que alguien
escriba un SELECT.
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ufil import confianza as cf
from ufil import db
from ufil.aplicar_revision import aplicar
from ufil.db import ahora


class BaseConDatos(unittest.TestCase):
    """Un legajo mínimo con contratos, para poder afirmar cosas sobre los totales."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = db.abrir(Path(self.tmp.name) / "t.sqlite")

    def tearDown(self):
        self.cx.close(); self.tmp.cleanup()

    def _contrato(self, sha="aa", orden=1, nombre_archivo=None):
        nombre_archivo = nombre_archivo or f"{sha}.pdf"
        self.cx.execute("""INSERT OR IGNORE INTO archivo
                           (sha256,ruta_original,nombre,bytes,paginas,ingerido_en)
                           VALUES (?,?,?,1,1,?)""",
                        (sha, f"/x/{nombre_archivo}", nombre_archivo, ahora()))
        self.cx.execute("""INSERT OR IGNORE INTO pagina (sha256,nro,ancho_pt,alto_pt)
                           VALUES (?,1,595,842)""", (sha,))
        return self.cx.execute(
            """INSERT INTO documento (sha256,orden,pagina_desde,pagina_hasta,tipo,perfil)
               VALUES (?,?,1,1,'contrato_obra','p')""", (sha, orden)).lastrowid

    def _campo(self, doc, nombre, literal, estado, *, norm=None, conf=0.95,
               motivo=None):
        cid = self.cx.execute(
            """INSERT INTO campo (documento_id,nombre,valor_literal,nulo_motivo,
                                  pagina_nro,x0,y0,x1,y1,confianza,estado)
               VALUES (?,?,?,?,1,10,10,90,30,?,?)""",
            (doc, nombre, literal, motivo, conf, estado)).lastrowid
        if norm is not None:
            self.cx.execute("""INSERT INTO normalizacion (campo_id,tipo,valor_norm)
                               VALUES (?,?,?)""", (cid, nombre, norm))
        return cid

    def _totales(self):
        from ufil import capa4_analisis as c4
        return c4.correr(self.cx, "10_totales")["filas"][0]


class UnNombreRotoNoEsUnaPersona(BaseConDatos):
    """
    1. El nombre defectuoso de OCR no aparece como persona firme.

    El caso real: en la pantalla de personas figuraba
    «e DUARTE) Sidvia Nit PA AA A a a» como una persona consolidada del legajo. Salía
    de un campo con confianza 0,31 que estaba, al mismo tiempo, en la cola de revisión.
    """

    def test_un_nombre_pendiente_no_consolida_persona(self):
        from ufil.capa3_identidad import resolver
        doc = self._contrato()
        self._campo(doc, "nombre", "e DUARTE) Sidvia Nit PA AA A a a",
                    cf.PENDIENTE_BAJA, norm="DUARTE SIDVIA NIT PA AA A A A", conf=0.31)
        self._campo(doc, "documento", "27-12345678-4", cf.PENDIENTE_BAJA,
                    norm="CUIL:27123456784", conf=0.30)
        self.cx.commit()
        resolver(self.cx)

        alias = self.cx.execute(
            "SELECT nombre_literal FROM persona_alias").fetchall()
        self.assertEqual(
            [a["nombre_literal"] for a in alias], [],
            "un nombre que el propio sistema tiene marcado como dudoso no puede "
            "figurar como persona consolidada del legajo")

    def test_al_corregirlo_a_mano_sí_consolida(self):
        """Y cuando una persona lo arregla, entra: la regla no es «nunca», es «no todavía»."""
        from ufil.capa3_identidad import resolver
        doc = self._contrato()
        cid = self._campo(doc, "nombre", "e DUARTE) Sidvia Nit",
                          cf.PENDIENTE_BAJA, norm="DUARTE SIDVIA NIT", conf=0.31)
        self._campo(doc, "documento", "27-12345678-4", cf.AUTOMATICO_ALTA,
                    norm="CUIL:27123456784")
        self.cx.commit()
        aplicar(self.cx, cid, "corregir", "DUARTE, Silvia Noemí", "perez.ana")
        resolver(self.cx)

        alias = [a["nombre_literal"] for a in self.cx.execute(
            "SELECT nombre_literal FROM persona_alias")]
        self.assertIn("DUARTE, Silvia Noemí", alias)


class UnMontoDudosoNoMueveElTotalFirme(BaseConDatos):
    """
    2 y 3. Un monto de baja confianza no modifica el total firme; al verificarlo, sí.
    """

    def setUp(self):
        super().setUp()
        self.doc_firme = self._contrato("aa", 1)
        self._campo(self.doc_firme, "monto", "$ 12.000", cf.AUTOMATICO_ALTA,
                    norm="1200000")
        self.doc_dudoso = self._contrato("bb", 1)
        self.campo_dudoso = self._campo(self.doc_dudoso, "monto", "$ 5.000",
                                        cf.PENDIENTE_BAJA, norm="500000", conf=0.42)
        self.cx.commit()

    def test_el_dudoso_queda_fuera_del_total_firme(self):
        t = self._totales()
        self.assertEqual(t["total_firme_centavos"], 1200000,
                         "el total firme sólo puede tener el monto firme")
        self.assertEqual(t["total_provisional_centavos"], 500000,
                         "y el dudoso tiene que verse, aparte y dicho como provisional")
        self.assertEqual(t["contratos_con_monto_firme"], 1)
        self.assertEqual(t["contratos_con_monto_provisional"], 1)

    def test_al_verificarlo_entra_en_todas_las_vistas(self):
        aplicar(self.cx, self.campo_dudoso, "verificar", None, "perez.ana")
        t = self._totales()
        self.assertEqual(t["total_firme_centavos"], 1700000,
                         "verificado por una persona, el monto entra al total firme")
        self.assertEqual(t["total_provisional_centavos"], 0)
        self.assertEqual(t["campos_verificados_por_persona"], 1)
        # Y también en la vista de contratos, que es de donde salen los cruces.
        n = self.cx.execute(
            "SELECT COUNT(*) FROM v_contrato WHERE monto_centavos IS NOT NULL"
        ).fetchone()[0]
        self.assertEqual(n, 2, "y aparece en la vista firme de contratos")

    def test_deshacer_lo_saca_de_nuevo(self):
        aplicar(self.cx, self.campo_dudoso, "verificar", None, "perez.ana")
        aplicar(self.cx, self.campo_dudoso, "revertir", None, "perez.ana")
        t = self._totales()
        self.assertEqual(t["total_firme_centavos"], 1200000,
                         "deshacer tiene que devolver el total a como estaba")


class UnConflictoNoSeResuelveSolo(BaseConDatos):
    """4. Un conflicto no se resuelve automáticamente. Lo decide una persona."""

    def test_el_conflicto_no_aporta_valor_a_ninguna_vista(self):
        doc = self._contrato()
        self._campo(doc, "monto", None, cf.CONFLICTO, motivo="conflicto", conf=None)
        k = self.cx.execute("""INSERT INTO conflicto (documento_id,campo_nombre)
                               VALUES (?,'monto')""", (doc,)).lastrowid
        for ruta, v in (("ocr_a", "$ 74.200"), ("ocr_b", "$ 14.200")):
            self.cx.execute("""INSERT INTO conflicto_variante (conflicto_id,ruta,valor)
                               VALUES (?,?,?)""", (k, ruta, v))
        self.cx.commit()

        self.assertEqual(self._totales()["total_firme_centavos"], 0)
        fila = self.cx.execute("SELECT monto_centavos FROM v_contrato").fetchone()
        self.assertIsNone(fila["monto_centavos"],
                          "de un conflicto no sale ningún valor: no se elige, se marca")
        # Sigue abierto: nada lo cerró solo.
        abierto = self.cx.execute(
            "SELECT COUNT(*) FROM conflicto WHERE estado='abierto'").fetchone()[0]
        self.assertEqual(abierto, 1)

    def test_las_dos_lecturas_originales_se_conservan(self):
        """Una corrección humana conserva el OCR original y todos sus candidatos."""
        doc = self._contrato()
        cid = self._campo(doc, "monto", None, cf.CONFLICTO, motivo="conflicto", conf=None)
        k = self.cx.execute("""INSERT INTO conflicto (documento_id,campo_nombre)
                               VALUES (?,'monto')""", (doc,)).lastrowid
        for ruta, v in (("ocr_a", "$ 74.200"), ("ocr_b", "$ 14.200")):
            self.cx.execute("""INSERT INTO conflicto_variante (conflicto_id,ruta,valor)
                               VALUES (?,?,?)""", (k, ruta, v))
        self.cx.commit()
        aplicar(self.cx, cid, "corregir", "74200", "perez.ana")

        variantes = [v["valor"] for v in self.cx.execute(
            "SELECT valor FROM conflicto_variante WHERE conflicto_id=?", (k,))]
        self.assertEqual(sorted(variantes), ["$ 14.200", "$ 74.200"],
                         "los candidatos que vio la máquina no se borran al corregir")
        c = self.cx.execute("SELECT motivo_auto, estado FROM campo WHERE id=?",
                            (cid,)).fetchone()
        self.assertEqual(c["motivo_auto"], "conflicto",
                         "y queda registrado que la máquina no había podido decidir")
        self.assertEqual(c["estado"], cf.CORREGIDO)


class DosPersonasNoSeFusionanPorParecido(BaseConDatos):
    """5. Nombres parecidos nunca se fusionan sin confirmación humana."""

    def test_mismo_apellido_distinto_documento_son_dos_personas(self):
        from ufil.capa3_identidad import resolver, proponer_fusiones
        for i, (sha, nom, doc) in enumerate([
                ("aa", "SOSA, Silvia N.",     "27-30111222-3"),
                ("bb", "SOSA, Silvia Noemí",  "27-40222333-4")], start=1):
            d = self._contrato(sha, 1)
            self._campo(d, "nombre", nom, cf.AUTOMATICO_ALTA,
                        norm=nom.upper().replace(",", "").replace(".", ""))
            self._campo(d, "documento", doc, cf.AUTOMATICO_ALTA,
                        norm="CUIL:" + doc.replace("-", ""))
        self.cx.commit()
        resolver(self.cx)

        n = self.cx.execute("SELECT COUNT(*) FROM persona").fetchone()[0]
        self.assertEqual(n, 2, "dos documentos distintos son dos personas, se parezcan "
                               "los nombres lo que se parezcan")

    def test_una_propuesta_de_fusion_no_se_aplica_sola(self):
        from ufil.capa3_identidad import resolver
        for sha, nom in (("aa", "SOSA, Silvia N."), ("bb", "SOSA, Silvia Noemi")):
            d = self._contrato(sha, 1)
            self._campo(d, "nombre", nom, cf.AUTOMATICO_ALTA,
                        norm="SOSA SILVIA N" if "N." in nom else "SOSA SILVIA NOEMI")
        self.cx.commit()
        resolver(self.cx)

        # Puede haber una propuesta; lo que no puede haber es una fusión hecha.
        aplicadas = self.cx.execute(
            "SELECT COUNT(*) FROM fusion_propuesta WHERE estado='aceptada'").fetchone()[0]
        self.assertEqual(aplicadas, 0, "una propuesta es una pregunta, no una decisión")
        self.assertEqual(self.cx.execute("SELECT COUNT(*) FROM persona").fetchone()[0], 2)


class LosTotalesCoincidenConSusRegistros(BaseConDatos):
    """6. Los totales coinciden exactamente con los registros que los componen."""

    def test_el_total_firme_es_la_suma_de_sus_filas(self):
        montos = [("aa", "1200000", cf.AUTOMATICO_ALTA),
                  ("bb", "500000",  cf.PENDIENTE_BAJA),
                  ("cc", "742000",  cf.VERIFICADO),
                  ("dd", "96750",   cf.CORREGIDO),
                  ("ee", None,      cf.CONFLICTO)]
        for sha, norm, estado in montos:
            d = self._contrato(sha, 1)
            self._campo(d, "monto", None if norm is None else f"${norm}", estado,
                        norm=norm, motivo=None if norm else "conflicto",
                        conf=None if norm is None else 0.9)
        self.cx.commit()

        t = self._totales()
        suma_a_mano = sum(int(n) for _, n, e in montos if n and e in cf.FIRMES)
        self.assertEqual(t["total_firme_centavos"], suma_a_mano)

        # Y la suma de la vista firme tiene que dar exactamente lo mismo: si estas dos
        # se separan, hay un camino por el que un valor entra sin pasar por la regla.
        de_la_vista = self.cx.execute(
            "SELECT COALESCE(SUM(monto_centavos),0) FROM v_contrato").fetchone()[0]
        self.assertEqual(de_la_vista, t["total_firme_centavos"])

    def test_firme_mas_provisional_es_todo_lo_leido(self):
        """Ningún monto leído se pierde entre las dos categorías."""
        for sha, norm, estado in (("aa", "1000", cf.AUTOMATICO_ALTA),
                                  ("bb", "2000", cf.PENDIENTE_BAJA),
                                  ("cc", "3000", cf.VERIFICADO)):
            d = self._contrato(sha, 1)
            self._campo(d, "monto", f"${norm}", estado, norm=norm)
        self.cx.commit()
        t = self._totales()
        self.assertEqual(t["total_firme_centavos"] + t["total_provisional_centavos"],
                         1000 + 2000 + 3000)


class LosEstadosSonInequivocos(unittest.TestCase):
    """El modelo mismo: ocho estados, sin superposiciones ni huecos."""

    def test_cada_estado_cae_en_una_sola_categoria(self):
        cats = (cf.FIRMES, cf.PROVISIONALES, cf.CERRADOS_SIN_VALOR)
        for e in cf.TODOS:
            n = sum(1 for c in cats if e in c)
            self.assertLessEqual(n, 1, f"«{e}» está en más de una categoría")

    def test_no_hay_estados_sin_etiqueta_ni_explicacion(self):
        for e in cf.TODOS:
            self.assertIn(e, cf.ETIQUETAS, f"«{e}» no tiene etiqueta para mostrar")
            self.assertIn(e, cf.EXPLICACIONES, f"«{e}» no tiene explicación")

    def test_ningun_estado_cerrado_por_una_persona_es_firme(self):
        """
        `ilegible_confirmado` y `ausente_confirmado` son decisiones humanas firmes,
        pero sobre la AUSENCIA de un valor: no aportan nada que sumar.
        """
        for e in cf.CERRADOS_SIN_VALOR:
            self.assertNotIn(e, cf.FIRMES)

    def test_la_clasificacion_no_pisa_una_decision_humana(self):
        for humano in cf.HUMANOS:
            self.assertEqual(
                cf.clasificar("cualquier cosa", None, 0.01, 0.85, humano), humano,
                "un reproceso no puede deshacer lo que decidió una persona")


if __name__ == "__main__":
    unittest.main(verbosity=2)
