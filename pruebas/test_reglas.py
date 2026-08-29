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

    def test_la_verificacion_cubre_todo_el_acervo_con_el_uso(self):
        """No es un muestreo al azar: los postergados van primero y la cobertura avanza."""
        from ufil.capa0_ingesta import ingerir
        from ufil.verificacion import verificar_integridad
        import fitz
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            corpus = tmp / "corpus"; corpus.mkdir()
            for i in range(9):
                doc = fitz.open(); pag = doc.new_page()
                pag.insert_text((70, 90), f"documento numero {i}")
                doc.save(corpus / f"d{i}.pdf"); doc.close()
            cx = db.abrir(tmp / "t.sqlite")
            ingerir(cx, corpus, lote="t")

            r1 = verificar_integridad(cx, cuantos=4)
            self.assertEqual((r1["revisados"], r1["ok"], r1["cubiertos"]), (4, 4, 4))
            r2 = verificar_integridad(cx, cuantos=4)
            self.assertEqual(r2["cubiertos"], 8, "la segunda corrida tiene que tomar OTROS cuatro")
            r3 = verificar_integridad(cx, cuantos=4)
            self.assertEqual(r3["cubiertos"], 9, "a la tercera queda cubierto todo el acervo")
            self.assertEqual(r3["sin_verificar_nunca"], 0)
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


class SubidaDeEscaneos(unittest.TestCase):
    """Lo que llega por la interfaz también es un original inmutable."""

    def _pdf(self, texto="contrato de prueba") -> bytes:
        import fitz
        doc = fitz.open(); pag = doc.new_page()
        pag.insert_text((70, 90), texto)
        datos = doc.tobytes(); doc.close()
        return datos

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        import ufil.config as cfg
        self._datos = cfg.DATOS
        cfg.DATOS = Path(self.tmp.name)
        import os
        os.environ["UFIL_ORIGINALES"] = str(Path(self.tmp.name) / "originales")
        self.cx = db.abrir(Path(self.tmp.name) / "t.sqlite")

    def tearDown(self):
        import os
        import ufil.config as cfg
        cfg.DATOS = self._datos
        os.environ.pop("UFIL_ORIGINALES", None)
        self.cx.close(); self.tmp.cleanup()

    def test_lo_que_no_es_pdf_se_rechaza(self):
        from ufil.almacen import ArchivoInvalido, guardar
        for datos, motivo in [(b"", "vacío"), (b"esto no es un pdf", "no es PDF"),
                              (b"\x89PNG\r\n", "una imagen suelta")]:
            with self.assertRaises(ArchivoInvalido, msg=motivo):
                guardar(self.cx, datos, "x.pdf", lote="t")

    def test_el_original_se_guarda_bajo_su_hash_y_sin_permiso_de_escritura(self):
        import hashlib
        import stat
        from ufil.almacen import guardar
        datos = self._pdf()
        g = guardar(self.cx, datos, "contrato.pdf", lote="t", operador="quien.sea")
        self.assertEqual(g.sha256, hashlib.sha256(datos).hexdigest())
        self.assertEqual(g.ruta.stem, g.sha256, "el archivo se nombra por su hash")
        self.assertEqual(g.ruta.read_bytes(), datos, "se guardó byte por byte")
        modo = stat.S_IMODE(g.ruta.stat().st_mode)
        self.assertEqual(modo & 0o222, 0, "no debe quedar con permiso de escritura")

    def test_el_nombre_original_se_conserva_en_la_base(self):
        from ufil.almacen import guardar
        g = guardar(self.cx, self._pdf(), "Contrato Cámara A 2024.pdf", lote="t")
        fila = self.cx.execute("SELECT nombre FROM archivo WHERE sha256=?", (g.sha256,)).fetchone()
        self.assertEqual(fila["nombre"], "Contrato Cámara A 2024.pdf")

    def test_subir_dos_veces_el_mismo_contenido_no_duplica(self):
        from ufil.almacen import guardar
        datos = self._pdf()
        a = guardar(self.cx, datos, "uno.pdf", lote="t")
        b = guardar(self.cx, datos, "otro-nombre.pdf", lote="t")
        self.assertFalse(a.duplicado); self.assertTrue(b.duplicado)
        self.assertEqual(self.cx.execute("SELECT COUNT(*) FROM archivo").fetchone()[0], 1)
        self.assertEqual(self.cx.execute("SELECT COUNT(*) FROM duplicado").fetchone()[0], 1)

    def test_nombres_con_ruta_no_escapan_del_almacen(self):
        from ufil.almacen import guardar
        g = guardar(self.cx, self._pdf(), "../../../etc/passwd.pdf", lote="t")
        self.assertNotIn("..", str(g.ruta))
        self.assertEqual(g.nombre, "passwd.pdf")


class Busqueda(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = db.abrir(Path(self.tmp.name) / "t.sqlite")
        self.cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,ingerido_en)
                           VALUES ('zz','/x/z.pdf','z.pdf',1,?)""", (ahora(),))
        pid = self.cx.execute("""INSERT INTO pagina (sha256,nro,ancho_pt,alto_pt)
                                 VALUES ('zz',1,595,842)""").lastrowid
        lid = self.cx.execute("""INSERT INTO lectura (pagina_id,ruta,motor,creado_en)
                                 VALUES (?,'ocr_a','tesseract',?)""", (pid, ahora())).lastrowid
        for i, w in enumerate("CONTRATO DE LOCACIÓN DE SERVICIOS PERSONAL DE MAESTRANZA".split()):
            self.cx.execute("""INSERT INTO palabra (lectura_id,orden,texto,x0,y0,x1,y1,conf)
                               VALUES (?,?,?,0,0,1,1,0.9)""", (lid, i, w))
        self.cx.commit()

    def tearDown(self):
        self.cx.close(); self.tmp.cleanup()

    def test_encuentra_sin_tildes(self):
        from ufil.busqueda import buscar, reindexar
        reindexar(self.cx)
        self.assertTrue(buscar(self.cx, "locacion")["paginas"],
                        "buscar sin tilde tiene que encontrar la palabra con tilde")

    def test_una_consulta_rota_no_rompe_nada(self):
        from ufil.busqueda import buscar, reindexar
        reindexar(self.cx)
        for q in ['"sin cerrar', "AND OR ((", "* * *", "ñ)(\\"]:
            self.assertIsInstance(buscar(self.cx, q)["paginas"], list, q)

    def test_indexa_una_sola_ruta_por_pagina(self):
        """Con dos lecturas de la misma página, el folio no puede aparecer duplicado."""
        from ufil.busqueda import buscar, reindexar
        pid = self.cx.execute("SELECT id FROM pagina WHERE sha256='zz'").fetchone()["id"]
        lid = self.cx.execute("""INSERT INTO lectura (pagina_id,ruta,motor,creado_en)
                                 VALUES (?,'ocr_b','tesseract',?)""", (pid, ahora())).lastrowid
        self.cx.execute("""INSERT INTO palabra (lectura_id,orden,texto,x0,y0,x1,y1,conf)
                           VALUES (?,0,'MAESTRANZA',0,0,1,1,0.9)""", (lid,))
        self.cx.commit()
        reindexar(self.cx)
        self.assertEqual(len(buscar(self.cx, "maestranza")["paginas"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
