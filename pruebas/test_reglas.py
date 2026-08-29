"""
Pruebas de las reglas que NO se pueden romper.

No prueban que el OCR lea bien —eso se mide con `ufil evaluar` contra la transcripción
manual—. Prueban que las restricciones del pliego sigan siendo verdad dentro de seis
meses, cuando alguien toque el código sin acordarse de por qué estaba así.

    python3 -m unittest discover -s pruebas -v
"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ufil import db
from ufil.capa2_campos import parse_documento, parse_fecha, parse_monto
from ufil.capa5_interpretacion import insertar
from ufil.db import ahora


class BaseTemporal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = db.abrir(Path(self.tmp.name) / "t.sqlite")
        self.cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,ingerido_en)
                           VALUES ('aa','/x/a.pdf','a.pdf',1,?)""", (ahora(),))
        self.cx.execute("INSERT INTO documento (sha256,tipo,perfil) VALUES ('aa','c','p')")
        self.doc = self.cx.execute("SELECT id FROM documento").fetchone()["id"]

    def tearDown(self):
        self.cx.close(); self.tmp.cleanup()


class NadaSeInventa(unittest.TestCase):
    """Restricción 3: ante la duda, nulo con motivo. Nunca una suposición."""

    def test_monto_con_separador_ambiguo_no_se_adivina(self):
        for crudo in ("74.20", "74,2", "1.234.5"):
            _, norm, motivo = parse_monto(crudo)
            self.assertIsNone(norm, f"{crudo} no debería resolverse")
            self.assertEqual(motivo, "ambiguo")

    def test_monto_claro_si_se_lee(self):
        self.assertEqual(parse_monto("$ 74.200,00")[1], "7420000")
        self.assertEqual(parse_monto("$ 96.750")[1], "9675000")

    def test_fecha_de_dos_digitos_no_elige_siglo(self):
        _, norm, motivo = parse_fecha("24/12/20")
        self.assertIsNone(norm); self.assertEqual(motivo, "ambiguo")

    def test_fecha_inexistente_no_se_corrige(self):
        _, norm, motivo = parse_fecha("31/02/2020")
        self.assertIsNone(norm); self.assertEqual(motivo, "ambiguo")

    def test_ocr_con_letra_en_la_fecha_no_se_sustituye(self):
        # "2O/12/2021" con O mayúscula. Tentador cambiarla por cero. No se hace.
        _, norm, motivo = parse_fecha("2O/12/2021")
        self.assertIsNone(norm); self.assertEqual(motivo, "ambiguo")

    def test_documento_incompleto_no_se_rellena(self):
        for crudo in ("2712345678", "271234567890"):
            _, norm, motivo = parse_documento(crudo)
            self.assertIsNone(norm); self.assertEqual(motivo, "ambiguo")

    def test_documento_valido_se_normaliza(self):
        self.assertEqual(parse_documento("27-27219539-2")[1], "CUIL:27272195392")
        self.assertEqual(parse_documento("12.345.678")[1], "DNI:12345678")


class CarrilDeDatos(BaseTemporal):
    """Restricciones 3 y 4, garantizadas por la base misma y no por buena voluntad."""

    def test_no_puede_haber_valor_sin_anclaje(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.cx.execute("""INSERT INTO campo (documento_id,nombre,valor_literal)
                               VALUES (?,'monto','$ 100,00')""", (self.doc,))

    def test_no_puede_haber_valor_y_motivo_a_la_vez(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.cx.execute("""INSERT INTO campo (documento_id,nombre,valor_literal,nulo_motivo,
                                                  pagina_nro,x0,y0,x1,y1)
                               VALUES (?,'monto','$ 100,00','ilegible',1,0,0,1,1)""", (self.doc,))

    def test_no_puede_haber_campo_sin_valor_ni_motivo(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.cx.execute("INSERT INTO campo (documento_id,nombre) VALUES (?,'monto')",
                            (self.doc,))

    def test_valor_con_anclaje_entra(self):
        self.cx.execute("""INSERT INTO campo (documento_id,nombre,valor_literal,
                                              pagina_nro,x0,y0,x1,y1)
                           VALUES (?,'monto','$ 100,00',1,10,20,30,40)""", (self.doc,))
        self.assertEqual(self.cx.execute("SELECT COUNT(*) FROM campo").fetchone()[0], 1)


class CarrilDeInterpretacion(BaseTemporal):
    """Sección 5: ninguna conjetura sin los documentos que la sostienen."""

    def test_interpretacion_sin_fuentes_se_rechaza(self):
        with self.assertRaises(ValueError):
            insertar(self.cx, alcance="documento", alcance_id=self.doc, clase="patron",
                     texto="algo", origen="regla:x", fuentes=[])

    def test_interpretacion_con_fuente_entra(self):
        iid = insertar(self.cx, alcance="documento", alcance_id=self.doc, clase="patron",
                       texto="algo", origen="regla:x",
                       fuentes=[{"documento_id": self.doc, "nota": "a.pdf"}])
        n = self.cx.execute("SELECT COUNT(*) FROM interpretacion_fuente WHERE interpretacion_id=?",
                            (iid,)).fetchone()[0]
        self.assertEqual(n, 1)


class VistaDeContratos(BaseTemporal):
    """Un campo con conflicto abierto NO puede llegar a las consultas de análisis."""

    def _campo(self, nombre, valor, tipo, norm):
        cid = self.cx.execute("""INSERT INTO campo (documento_id,nombre,valor_literal,
                                     pagina_nro,x0,y0,x1,y1,confianza)
                                 VALUES (?,?,?,1,0,0,1,1,0.99)""",
                              (self.doc, nombre, valor)).lastrowid
        self.cx.execute("INSERT INTO normalizacion (campo_id,tipo,valor_norm) VALUES (?,?,?)",
                        (cid, tipo, norm))
        return cid

    def test_campo_en_conflicto_sale_nulo_de_la_vista(self):
        self._campo("fecha_inicio", "01/03/2021", "fecha", "2021-03-01")
        self._campo("monto", "$ 100,00", "monto", "10000")
        self.assertEqual(self.cx.execute("SELECT monto_centavos FROM v_contrato").fetchone()[0],
                         10000)
        self.cx.execute("INSERT INTO conflicto (documento_id,campo_nombre) VALUES (?,'monto')",
                        (self.doc,))
        self.assertIsNone(self.cx.execute("SELECT monto_centavos FROM v_contrato").fetchone()[0],
                          "un campo en conflicto no puede entrar en el análisis")


class Identidad(BaseTemporal):
    """El nombre nunca es clave. Las fusiones no se aplican solas."""

    def _doc_con(self, sha, nombre, documento):
        self.cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,ingerido_en)
                           VALUES (?,?,?,1,?)""", (sha, f"/x/{sha}.pdf", f"{sha}.pdf", ahora()))
        d = self.cx.execute("INSERT INTO documento (sha256,tipo,perfil) VALUES (?,'c','p')",
                            (sha,)).lastrowid
        for campo, valor, tipo, norm in (
            ("nombre", nombre, "nombre", nombre.upper().replace(",", "")),
            ("documento", documento, "documento", f"CUIL:{documento}" if documento else None),
        ):
            if valor is None:
                continue
            cid = self.cx.execute("""INSERT INTO campo (documento_id,nombre,valor_literal,
                                         pagina_nro,x0,y0,x1,y1,confianza)
                                     VALUES (?,?,?,1,0,0,1,1,0.99)""",
                                  (d, campo, valor)).lastrowid
            self.cx.execute("INSERT INTO normalizacion (campo_id,tipo,valor_norm) VALUES (?,?,?)",
                            (cid, tipo, norm))
        return d

    def test_mismo_documento_es_la_misma_persona(self):
        from ufil.capa3_identidad import resolver
        self._doc_con("b1", "CORREA, Silvia N.", "27111111112")
        self._doc_con("b2", "CORREA, Silvia Noemí", "27111111112")
        resolver(self.cx)
        n = self.cx.execute("""SELECT COUNT(DISTINCT persona_id) FROM documento_persona dp
                                 JOIN documento d ON d.id=dp.documento_id
                                WHERE d.sha256 IN ('b1','b2')""").fetchone()[0]
        self.assertEqual(n, 1, "el mismo CUIL tiene que unirlos solo")

    def test_nombres_parecidos_sin_documento_NO_se_fusionan_solos(self):
        from ufil.capa3_identidad import proponer_fusiones, resolver
        self._doc_con("c1", "CORREA, Silvia N.", None)
        self._doc_con("c2", "CORREA, Silvia Noemí", None)
        resolver(self.cx)
        proponer_fusiones(self.cx)
        n = self.cx.execute("""SELECT COUNT(DISTINCT persona_id) FROM documento_persona dp
                                 JOIN documento d ON d.id=dp.documento_id
                                WHERE d.sha256 IN ('c1','c2')""").fetchone()[0]
        self.assertEqual(n, 2, "sin documento NO se pueden unir solos")
        p = self.cx.execute("SELECT COUNT(*) FROM fusion_propuesta WHERE estado='pendiente'").fetchone()[0]
        self.assertGreaterEqual(p, 1, "pero sí se tiene que proponer la fusión")

    def test_fusion_sin_constancia_de_quien_se_rechaza(self):
        from ufil.capa3_identidad import decidir_fusion, proponer_fusiones, resolver
        self._doc_con("d1", "CORREA, Silvia N.", None)
        self._doc_con("d2", "CORREA, Silvia Noemí", None)
        resolver(self.cx); proponer_fusiones(self.cx)
        pid = self.cx.execute("SELECT id FROM fusion_propuesta LIMIT 1").fetchone()["id"]
        with self.assertRaises(ValueError):
            decidir_fusion(self.cx, pid, True, "")


class OriginalInmutable(unittest.TestCase):
    """Restricción 2: el material fuente no se toca, y si cambia, nos enteramos."""

    def test_la_ingesta_no_modifica_el_original(self):
        from ufil.capa0_ingesta import ingerir, sha256_de
        import fitz
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            corpus = tmp / "corpus"; corpus.mkdir()
            doc = fitz.open(); doc.new_page(); doc.save(corpus / "x.pdf"); doc.close()
            antes = sha256_de(corpus / "x.pdf")
            mtime_antes = (corpus / "x.pdf").stat().st_mtime

            cx = db.abrir(tmp / "t.sqlite")
            ingerir(cx, corpus, lote="t")
            self.assertEqual(sha256_de(corpus / "x.pdf"), antes, "el original cambió")
            self.assertEqual((corpus / "x.pdf").stat().st_mtime, mtime_antes)
            self.assertEqual([p.name for p in corpus.iterdir()], ["x.pdf"],
                             "no se escribió nada adentro del corpus")
            cx.close()

    def test_verificar_detecta_un_original_alterado(self):
        from ufil.capa0_ingesta import ingerir
        from ufil.verificacion import correr
        import fitz
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            corpus = tmp / "corpus"; corpus.mkdir()
            doc = fitz.open(); doc.new_page(); doc.save(corpus / "x.pdf"); doc.close()
            cx = db.abrir(tmp / "t.sqlite")
            ingerir(cx, corpus, lote="t")
            self.assertEqual(correr(cx), [])
            (corpus / "x.pdf").write_bytes(b"%PDF-1.4 otra cosa")
            fallas = correr(cx)
            self.assertTrue(any("EL ORIGINAL CAMBIÓ" in f for f in fallas), fallas)
            cx.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
