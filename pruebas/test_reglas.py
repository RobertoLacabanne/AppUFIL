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


class VariosContratosEnUnArchivo(unittest.TestCase):
    """
    Un PDF puede traer varios contratos. Antes producía UN registro que mezclaba el
    nombre de un contrato con el monto de otro: un contrato inventado, y sin marca.
    """

    def test_los_tramos_se_arman_bien(self):
        from ufil.capa2_extraccion import segmentar
        # Un solo contrato con carátula y anexo: un tramo que abarca todo.
        self.assertEqual(segmentar([2], [1, 2, 3]), [(1, 3)])
        # Cinco contratos de dos fojas cada uno.
        self.assertEqual(segmentar([1, 3, 5, 7, 9], list(range(1, 11))),
                         [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10)])
        # La carátula previa se le adjunta al PRIMER contrato, no queda suelta.
        self.assertEqual(segmentar([2, 5], [1, 2, 3, 4, 5, 6]), [(1, 4), (5, 6)])
        # Sin formulario reconocido, no hay contratos.
        self.assertEqual(segmentar([], [1, 2]), [])

    def test_una_caratula_no_arranca_un_contrato_fantasma(self):
        """Nombrar el formulario no alcanza: hacen falta sus rótulos."""
        from ufil.capa1_texto import Palabra
        from ufil.capa2_extraccion import cargar_perfil, pagina_es_formulario
        perfil = cargar_perfil("contrato_legislatura")

        def palabras(texto):
            return [Palabra(t, i * 30, 100, i * 30 + 25, 110, 0.9)
                    for i, t in enumerate(texto.split())]

        caratula = palabras("Se agrega copia del CONTRATO DE LOCACION DE SERVICIOS "
                            "suscripto y su documentacion respaldatoria")
        self.assertFalse(pagina_es_formulario(caratula, perfil),
                         "una carátula que MENCIONA el contrato no es el contrato")

        formulario = palabras("CONTRATO DE LOCACION DE SERVICIOS APELLIDO Y NOMBRE CUIL "
                              "CARGO DESDE HASTA RETRIBUCION MENSUAL")
        self.assertTrue(pagina_es_formulario(formulario, perfil))

    def test_un_archivo_puede_tener_varios_documentos(self):
        """La base tiene que permitirlo: antes `sha256` era único."""
        tmp = tempfile.TemporaryDirectory()
        cx = db.abrir(Path(tmp.name) / "t.sqlite")
        cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,ingerido_en)
                      VALUES ('mm','/x/m.pdf','m.pdf',1,?)""", (ahora(),))
        for orden, (d, h) in enumerate([(1, 2), (3, 4), (5, 6)], start=1):
            cx.execute("""INSERT INTO documento (sha256,orden,pagina_desde,pagina_hasta,
                                                 tipo,perfil)
                          VALUES ('mm',?,?,?,'c','p')""", (orden, d, h))
        self.assertEqual(cx.execute("SELECT COUNT(*) FROM documento").fetchone()[0], 3)
        with self.assertRaises(sqlite3.IntegrityError):
            cx.execute("""INSERT INTO documento (sha256,orden,tipo,perfil)
                          VALUES ('mm',1,'c','p')""")   # mismo orden, no
        cx.close(); tmp.cleanup()


class DeshacerUnaRevision(BaseTemporal):
    """Equivocarse revisando es normal. Sin vuelta atrás habría que reprocesar el lote."""

    def _campo(self, nombre="monto", valor="$ 100,00", motivo=None, conf=0.5):
        cid = self.cx.execute("""INSERT INTO campo (documento_id,nombre,valor_literal,
                                     nulo_motivo,pagina_nro,x0,y0,x1,y1,confianza,ruta,estado)
                                 VALUES (?,?,?,?,1,0,0,10,10,?,'ocr_a','a_revisar')""",
                              (self.doc, nombre, valor, motivo, conf)).lastrowid
        if valor:
            self.cx.execute("""INSERT INTO normalizacion (campo_id,tipo,valor_norm)
                               VALUES (?,'monto','10000')""", (cid,))
        self.cx.commit()
        return cid

    def test_deshacer_una_correccion_restituye_lo_que_leyo_la_maquina(self):
        from ufil.aplicar_revision import aplicar
        cid = self._campo(valor="$ 100,00")
        aplicar(self.cx, cid, "corregir", "$ 250,00", "quien.sea")
        c = self.cx.execute("SELECT * FROM campo WHERE id=?", (cid,)).fetchone()
        self.assertEqual(c["valor_literal"], "$ 250,00")
        self.assertEqual(c["estado"], "corregido")
        self.assertEqual(c["valor_auto"], "$ 100,00", "tiene que guardar lo que había")

        aplicar(self.cx, cid, "revertir", None, "quien.sea")
        c = self.cx.execute("SELECT * FROM campo WHERE id=?", (cid,)).fetchone()
        self.assertEqual(c["valor_literal"], "$ 100,00", "tiene que volver lo automático")
        self.assertIsNone(c["revisado_por"])
        self.assertEqual(c["estado"], "a_revisar", "y volver a la cola, porque era dudoso")

    def test_deshacer_un_nulo_marcado_a_mano(self):
        from ufil.aplicar_revision import aplicar
        cid = self._campo(valor="$ 100,00")
        aplicar(self.cx, cid, "ilegible", None, "quien.sea")
        self.assertIsNone(self.cx.execute("SELECT valor_literal FROM campo WHERE id=?",
                                          (cid,)).fetchone()[0])
        aplicar(self.cx, cid, "revertir", None, "quien.sea")
        c = self.cx.execute("SELECT valor_literal, nulo_motivo FROM campo WHERE id=?",
                            (cid,)).fetchone()
        self.assertEqual(c["valor_literal"], "$ 100,00")
        self.assertIsNone(c["nulo_motivo"])

    def test_no_se_puede_deshacer_lo_que_nadie_toco(self):
        from ufil.aplicar_revision import aplicar
        cid = self._campo()
        with self.assertRaises(ValueError):
            aplicar(self.cx, cid, "revertir", None, "quien.sea")

    def test_deshacer_borra_el_registro_para_que_no_vuelva_al_reprocesar(self):
        from ufil.aplicar_revision import aplicar
        cid = self._campo()
        aplicar(self.cx, cid, "corregir", "$ 250,00", "quien.sea")
        self.assertEqual(self.cx.execute("SELECT COUNT(*) FROM revision_humana").fetchone()[0], 1)
        aplicar(self.cx, cid, "revertir", None, "quien.sea")
        self.assertEqual(self.cx.execute("SELECT COUNT(*) FROM revision_humana").fetchone()[0], 0,
                         "si no, al reprocesar el lote volvería a aplicarse")


class ContratosRepetidos(BaseTemporal):
    """El mismo contrato entrando desde archivos distintos infla los acumulados."""

    def _contrato(self, sha, nombre, doc, ini, fin, monto):
        self.cx.execute("""INSERT OR IGNORE INTO archivo
                           (sha256,ruta_original,nombre,bytes,ingerido_en)
                           VALUES (?,?,?,1,?)""", (sha, f"/x/{sha}.pdf", f"{sha}.pdf", ahora()))
        d = self.cx.execute("""INSERT INTO documento (sha256,orden,tipo,perfil)
                               VALUES (?,(SELECT COALESCE(MAX(orden),0)+1 FROM documento
                                          WHERE sha256=?),'c','p')""", (sha, sha)).lastrowid
        for campo, valor, tipo, norm in (
            ("nombre", nombre, "nombre", nombre.upper()),
            ("documento", doc, "documento", f"CUIL:{doc}"),
            ("fecha_inicio", ini, "fecha", ini),
            ("fecha_fin", fin, "fecha", fin),
            ("monto", str(monto), "monto", str(monto)),
        ):
            cid = self.cx.execute("""INSERT INTO campo (documento_id,nombre,valor_literal,
                                         pagina_nro,x0,y0,x1,y1,confianza)
                                     VALUES (?,?,?,1,0,0,1,1,0.95)""",
                                  (d, campo, valor)).lastrowid
            self.cx.execute("""INSERT INTO normalizacion (campo_id,tipo,valor_norm)
                               VALUES (?,?,?)""", (cid, tipo, norm))
        self.cx.commit()

    def test_detecta_el_mismo_contrato_llegado_de_dos_archivos(self):
        from ufil.capa3_identidad import detectar_contratos_repetidos
        self._contrato("aa1", "PEREZ, Juan", "20111111112", "2021-01-01", "2021-12-31", 10000)
        self._contrato("bb2", "PEREZ, Juan", "20111111112", "2021-01-01", "2021-12-31", 10000)
        self.assertEqual(detectar_contratos_repetidos(self.cx), 1)
        n = self.cx.execute("""SELECT COUNT(*) FROM excepcion
                                WHERE clase='contrato_repetido'""").fetchone()[0]
        self.assertEqual(n, 1)

    def test_dos_contratos_distintos_no_son_repetidos(self):
        from ufil.capa3_identidad import detectar_contratos_repetidos
        self._contrato("cc1", "PEREZ, Juan", "20111111112", "2021-01-01", "2021-06-30", 10000)
        self._contrato("cc2", "PEREZ, Juan", "20111111112", "2021-07-01", "2021-12-31", 10000)
        self.assertEqual(detectar_contratos_repetidos(self.cx), 0)


class PaginasTorcidas(unittest.TestCase):
    """Una hoja apoyada de costado en el escáner perdía el contrato entero."""

    def _pagina(self, grados: int) -> Path:
        import fitz
        from PIL import Image
        d = Path(self.tmp.name)
        doc = fitz.open(); pag = doc.new_page(width=595, height=842)
        pag.insert_text((60, 140), "CONTRATO DE LOCACION DE SERVICIOS",
                        fontsize=15, fontname="helv")
        for y, r, v in [(232, "APELLIDO Y NOMBRE", "TROCHE, Ramon E."),
                        (292, "CARGO", "ASESOR TECNICO"),
                        (352, "DESDE", "01/03/2021"),
                        (412, "RETRIBUCION MENSUAL", "$ 145.600,00")]:
            pag.insert_text((60, y), r, fontsize=8, fontname="helv")
            pag.insert_text((60, y + 18), v, fontsize=12, fontname="cour")
        limpio = d / "limpio.pdf"; doc.save(limpio); doc.close()

        with fitz.open(limpio) as f:
            pix = f[0].get_pixmap(matrix=fitz.Matrix(200 / 72, 200 / 72))
            png = d / "p.png"; pix.save(png)
        im = Image.open(png).convert("RGB")
        if grados:
            im = im.rotate(grados, expand=True)
        jpg = d / "p.jpg"; im.save(jpg, "JPEG", quality=85)
        w, h = im.size
        doc = fitz.open()
        pag = doc.new_page(width=w * 72 / 200, height=h * 72 / 200)
        pag.insert_image(fitz.Rect(0, 0, w * 72 / 200, h * 72 / 200), filename=str(jpg))
        destino = d / f"rot{grados}.pdf"; doc.save(destino); doc.close()
        return destino

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        import ufil.config as cfg
        self._der = cfg.DERIVADOS
        cfg.DERIVADOS = Path(self.tmp.name) / "der"

    def tearDown(self):
        import ufil.config as cfg
        cfg.DERIVADOS = self._der
        self.tmp.cleanup()

    def test_una_pagina_derecha_no_se_toca(self):
        from ufil.capa1_texto import leer_ocr, lectura_pobre, render_pagina
        png, esc, _ = render_pagina(self._pagina(0), "x", 1)
        lec = leer_ocr(png, esc, "ocr_a")
        self.assertFalse(lectura_pobre(lec),
                         f"una página derecha no debería dar sospecha (conf {lec.confianza:.2f})")

    def test_una_pagina_de_costado_se_detecta_y_se_endereza(self):
        from ufil.capa1_texto import (enderezar_si_mejora, leer_ocr, lectura_pobre,
                                      render_pagina, tiene_tinta)
        for grados in (90, 180, 270):
            with self.subTest(grados=grados):
                import ufil.config as cfg
                cfg.DERIVADOS = Path(self.tmp.name) / f"der{grados}"
                png, esc, _ = render_pagina(self._pagina(grados), f"r{grados}", 1)
                torcida = leer_ocr(png, esc, "ocr_a")
                self.assertTrue(lectura_pobre(torcida), "tendría que sospechar")
                self.assertTrue(tiene_tinta(png))
                aplicado, derecha = enderezar_si_mejora(png, esc, torcida)
                self.assertEqual(aplicado, grados, "tendría que encontrar el ángulo justo")
                self.assertGreater(derecha.confianza, torcida.confianza)
                texto = " ".join(p.texto for p in derecha.palabras).upper()
                self.assertIn("TROCHE", texto, "después de enderezar tiene que leerse")

    def test_una_pagina_derecha_pero_mal_leida_no_se_gira_al_pedo(self):
        """Si girarla no mejora, se deja como estaba: girar de más también rompe."""
        from ufil.capa1_texto import enderezar_si_mejora, leer_ocr, render_pagina
        png, esc, _ = render_pagina(self._pagina(0), "d0", 1)
        primera = leer_ocr(png, esc, "ocr_a")
        aplicado, final = enderezar_si_mejora(png, esc, primera)
        self.assertEqual(aplicado, 0, "una página derecha no se gira")
        self.assertGreaterEqual(final.confianza, primera.confianza)

    def test_una_hoja_en_blanco_no_se_interroga(self):
        import fitz
        from ufil.capa1_texto import render_pagina, tiene_tinta
        d = Path(self.tmp.name)
        doc = fitz.open(); doc.new_page(width=595, height=842)
        blanco = d / "blanco.pdf"; doc.save(blanco); doc.close()
        png, _, _ = render_pagina(blanco, "b", 1)
        self.assertFalse(tiene_tinta(png), "una hoja en blanco no gasta detección")


class ReanudarDespuesDeUnCorte(unittest.TestCase):
    """
    Un lote grande tarda una hora. Si se corta la luz o alguien cierra la terminal, lo
    leído hasta ahí tiene que quedar guardado y el trabajo tiene que retomar ahí.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        import ufil.config as cfg
        self._der = cfg.DERIVADOS
        cfg.DERIVADOS = Path(self.tmp.name) / "der"
        self.cx = db.abrir(Path(self.tmp.name) / "t.sqlite")

    def tearDown(self):
        import ufil.config as cfg
        cfg.DERIVADOS = self._der
        self.cx.close(); self.tmp.cleanup()

    def _corpus(self, hojas=3):
        import fitz
        corpus = Path(self.tmp.name) / "corpus"; corpus.mkdir()
        doc = fitz.open()
        for i in range(hojas):
            pag = doc.new_page(width=595, height=842)
            pag.insert_text((60, 140), "CONTRATO DE LOCACION DE SERVICIOS",
                            fontsize=15, fontname="helv")
            pag.insert_text((60, 200), f"foja numero {i + 1}", fontsize=12, fontname="cour")
        doc.save(corpus / "x.pdf"); doc.close()
        return corpus

    def test_solo_lee_las_paginas_que_faltan(self):
        from ufil.capa0_ingesta import ingerir
        from ufil.capa1_texto import leer_lote
        ingerir(self.cx, self._corpus(3), lote="t")
        sha = self.cx.execute("SELECT sha256 FROM archivo").fetchone()["sha256"]

        leer_lote(self.cx, [sha])
        antes = self.cx.execute("SELECT COUNT(*) FROM lectura").fetchone()[0]
        self.assertGreater(antes, 0)

        # Se simula el corte: la foja 2 quedó sin guardar.
        pid = self.cx.execute("SELECT id FROM pagina WHERE sha256=? AND nro=2",
                              (sha,)).fetchone()["id"]
        self.cx.execute("""DELETE FROM palabra WHERE lectura_id IN
                           (SELECT id FROM lectura WHERE pagina_id=?)""", (pid,))
        self.cx.execute("DELETE FROM lectura WHERE pagina_id=?", (pid,))
        self.cx.commit()
        parcial = self.cx.execute("SELECT COUNT(*) FROM lectura").fetchone()[0]

        r = leer_lote(self.cx, [sha])
        self.assertEqual(r["paginas"], 1, "sólo tiene que releer la foja que faltaba")
        self.assertEqual(self.cx.execute("SELECT COUNT(*) FROM lectura").fetchone()[0], antes,
                         "y quedar exactamente como antes del corte, sin duplicar")
        self.assertGreater(antes, parcial)

    def test_un_archivo_leido_a_medias_sigue_estando_pendiente(self):
        """Antes lo pendiente se contaba por ARCHIVO: uno a medias quedaba incompleto."""
        from ufil.capa0_ingesta import ingerir
        from ufil.capa1_texto import leer_lote
        ingerir(self.cx, self._corpus(3), lote="t")
        sha = self.cx.execute("SELECT sha256 FROM archivo").fetchone()["sha256"]
        leer_lote(self.cx, [sha])
        pid = self.cx.execute("SELECT id FROM pagina WHERE sha256=? AND nro=3",
                              (sha,)).fetchone()["id"]
        self.cx.execute("""DELETE FROM palabra WHERE lectura_id IN
                           (SELECT id FROM lectura WHERE pagina_id=?)""", (pid,))
        self.cx.execute("DELETE FROM lectura WHERE pagina_id=?", (pid,))
        self.cx.commit()

        pendientes = [f["sha256"] for f in self.cx.execute(
            """SELECT DISTINCT a.sha256 FROM archivo a
                 JOIN pagina p ON p.sha256 = a.sha256
                WHERE NOT EXISTS (SELECT 1 FROM lectura l WHERE l.pagina_id = p.id)""")]
        self.assertEqual(pendientes, [sha],
                         "un archivo con una foja sin leer tiene que seguir pendiente")


class VariantesDeFormulario(unittest.TestCase):
    """El formulario cambia entre cámaras y años: mismos campos, otros rótulos."""

    def test_gana_el_perfil_que_saca_mas_campos_criticos(self):
        from ufil.capa2_extraccion import Hallazgo, puntaje
        def h(**kw):
            return {k: Hallazgo(v, v, None, 1, (0, 0, 1, 1), 0.9, None) if v
                    else Hallazgo(None, None, "ausente", None, None, 0.0, None)
                    for k, v in kw.items()}
        pocos = h(nombre="X", cargo="Y", documento=None, monto=None,
                  fecha_inicio=None, fecha_fin=None)
        muchos = h(nombre="X", cargo=None, documento="20111111112",
                   monto="100", fecha_inicio="2021-01-01", fecha_fin=None)
        self.assertGreater(puntaje(muchos), puntaje(pocos),
                           "gana el que resuelve más campos críticos, no más campos")

    def test_hay_mas_de_un_perfil_y_todos_son_validos(self):
        import json
        from ufil.capa2_extraccion import cargar_perfil, perfiles_disponibles
        nombres = perfiles_disponibles()
        self.assertGreaterEqual(len(nombres), 2, "tiene que haber variantes cargadas")
        for n in nombres:
            p = cargar_perfil(n)
            self.assertEqual(p["nombre"], n, "el nombre interno tiene que coincidir")
            campos = {c["nombre"] for c in p["campos"]}
            self.assertTrue({"nombre", "documento", "fecha_inicio", "fecha_fin", "monto"}
                            <= campos, f"al perfil {n} le faltan campos críticos")


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
