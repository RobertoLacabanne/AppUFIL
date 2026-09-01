"""
VOLVER ATRÁS DESDE UNA COPIA.

El respaldo era una calle de una sola mano: se bajaba la copia y no había forma de
devolverla. Eso alcanza para la auditoría —queda el archivo— y no alcanza para lo que
de verdad hace falta el día que el disco aparece vacío, que es tener el legajo de
vuelta.

Restaurar PISA una base, así que es de las operaciones destructivas del sistema y se
prueba como tal: qué acepta, qué rechaza, y qué pasa con lo que estaba antes.
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ufil import config, confianza as cf, db, legajos, respaldo
from ufil.aplicar_revision import aplicar
from ufil.db import ahora


class VolverDesdeUnRespaldo(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self._datos = config.DATOS
        config.DATOS = self.dir / "datos"
        config.activar_legajo(None)
        self.l = legajos.crear("70.300", "Contratos Legislatura")
        config.activar_legajo(self.l.slug)
        cx = db.abrir()
        cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,paginas,
                                           ingerido_en)
                      VALUES ('a1','/x.pdf','contrato.pdf',10,1,?)""", (ahora(),))
        for i in range(4):
            cx.execute("""INSERT INTO documento (sha256,orden,pagina_desde,pagina_hasta,
                                                 tipo,perfil)
                          VALUES ('a1',?,1,1,'contrato_obra',
                                  'contrato_obra_legislatura')""", (i + 1,))
            cx.execute("""INSERT INTO campo (documento_id,nombre,valor_literal,pagina_nro,
                                             x0,y0,x1,y1,confianza,estado)
                          VALUES (?,'monto',?,1,1,1,2,2,0.4,?)""",
                       (i + 1, f"$ {i}", cf.PENDIENTE_BAJA))
        cx.commit()
        # Tres revisiones a mano: es lo único que no se puede volver a generar.
        for i in range(3):
            aplicar(cx, i + 1, "verificar", None, "badano.g")
        cx.close()

    def tearDown(self):
        config.activar_legajo(None)
        config.DATOS = self._datos
        self.tmp.cleanup()

    def _respaldar(self) -> Path:
        cx = db.abrir()
        try:
            return respaldo.hacer(cx, self.dir / "copia.sqlite")
        finally:
            cx.close()

    # ── Qué hay adentro, antes de tocar nada ───────────────────────────────
    def test_dice_que_trae_el_archivo_sin_instalarlo(self):
        """
        Restaurar pisa una base. Quien decide tiene que poder ver ANTES cuántas
        revisiones a mano trae la copia: si trae menos que lo que hay, la restauración
        pierde trabajo de personas.
        """
        r = respaldo.inspeccionar(self._respaldar())
        self.assertEqual(r["documentos"], 4)
        self.assertEqual(r["revisiones"], 3)
        self.assertGreater(r["bytes"], 0)
        self.assertIsNotNone(r["ultima_revision"])

    def test_no_toca_el_archivo_que_inspecciona(self):
        """
        Un archivo que llega de afuera se abre en solo lectura. Abrirlo para escritura
        le aplicaría la migración de esquema al vuelo y lo dejaría modificado antes de
        que nadie haya decidido nada.
        """
        copia = self._respaldar()
        antes = copia.read_bytes()
        respaldo.inspeccionar(copia)
        self.assertEqual(copia.read_bytes(), antes, "la inspección modificó el archivo")

    # ── Qué rechaza ────────────────────────────────────────────────────────
    def test_rechaza_lo_que_no_es_una_base(self):
        malo = self.dir / "cualquiera.pdf"
        malo.write_bytes(b"%PDF-1.4 esto es un contrato, no un respaldo")
        with self.assertRaises(respaldo.RespaldoInvalido) as e:
            respaldo.inspeccionar(malo)
        self.assertIn("no es una base SQLite", str(e.exception))

    def test_rechaza_una_base_de_otro_sistema(self):
        """
        Una base SQLite cualquiera pasaría el control de los primeros bytes. Instalarla
        dejaría el legajo apuntando a un archivo sin ninguna de las tablas, y el
        sistema fallaría recién al abrir la primera pantalla — con la base buena ya
        pisada.
        """
        ajena = self.dir / "ajena.sqlite"
        cx = sqlite3.connect(ajena)
        cx.execute("CREATE TABLE clientes (id INTEGER PRIMARY KEY, nombre TEXT)")
        cx.commit()
        cx.close()
        with self.assertRaises(respaldo.RespaldoInvalido) as e:
            respaldo.inspeccionar(ajena)
        self.assertIn("no de este sistema", str(e.exception))

    # ── Qué pasa con lo que estaba ─────────────────────────────────────────
    def test_restaura_y_aparta_la_base_anterior(self):
        copia = self._respaldar()

        # Después del respaldo se sigue trabajando: una cuarta revisión que la copia
        # no tiene.
        cx = db.abrir()
        aplicar(cx, 4, "verificar", None, "ramirez.j")
        cx.close()

        base = Path(config.BASE)
        r = respaldo.restaurar(copia, base)

        self.assertEqual(r["revisiones"], 3)
        self.assertIsNotNone(r["apartada"], "se borró la base anterior sin apartarla")
        self.assertTrue(Path(r["apartada"]).is_file())

        # La base ahora es la de la copia: tres revisiones, no cuatro.
        cx = db.abrir()
        n = cx.execute("SELECT COUNT(*) FROM revision_humana").fetchone()[0]
        cx.close()
        self.assertEqual(n, 3)

        # Y la que estaba se puede recuperar: tiene las cuatro.
        cx = sqlite3.connect(r["apartada"])
        self.assertEqual(cx.execute("SELECT COUNT(*) FROM revision_humana").fetchone()[0], 4)
        cx.close()

    def test_no_deja_el_diario_de_la_base_vieja(self):
        """
        SQLite escribe en un diario aparte (WAL). Si queda el del archivo anterior, lo
        aplica sobre la base nueva y la corrompe: el legajo restaurado abre roto y sin
        que nadie entienda por qué.
        """
        copia = self._respaldar()
        base = Path(config.BASE)
        wal = base.with_name(base.name + "-wal")
        wal.write_bytes(b"diario viejo")
        respaldo.restaurar(copia, base)
        self.assertFalse(wal.exists(), "quedó el diario de la base anterior")

        cx = db.abrir()          # tiene que abrir sin romperse
        self.assertEqual(cx.execute("SELECT COUNT(*) FROM documento").fetchone()[0], 4)
        cx.close()

    def test_restaurar_donde_no_habia_nada_tambien_anda(self):
        """Es el caso del disco vacío: no hay base que apartar y hay que instalar igual."""
        copia = self._respaldar()
        nueva = self.dir / "otra" / "ufil.sqlite"
        r = respaldo.restaurar(copia, nueva)
        self.assertIsNone(r["apartada"])
        self.assertTrue(nueva.is_file())


class ElEndpointDeRestaurar(unittest.TestCase):
    """
    El módulo puede estar impecable y el botón no hacer nada: ya pasó en este proyecto,
    con el borrado de legajos. Acá se llama al servidor de verdad.
    """

    @classmethod
    def setUpClass(cls):
        import http.client
        import os
        import threading
        cls.tmp = tempfile.TemporaryDirectory()
        cls._datos, cls._acceso = config.DATOS, os.environ.get("UFIL_ACCESO")
        config.DATOS = Path(cls.tmp.name)
        os.environ["UFIL_ACCESO"] = "abierto"
        from ufil import servidor
        cls.srv = servidor.armar(0)
        cls.puerto = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.http = http.client

    @classmethod
    def tearDownClass(cls):
        import os
        cls.srv.shutdown()
        cls.srv.server_close()
        config.DATOS = cls._datos
        if cls._acceso is None:
            os.environ.pop("UFIL_ACCESO", None)
        else:
            os.environ["UFIL_ACCESO"] = cls._acceso
        cls.tmp.cleanup()

    def _post(self, ruta, datos, tipo="application/json"):
        import json as _json
        cuerpo = datos if isinstance(datos, bytes) else _json.dumps(datos).encode()
        c = self.http.HTTPConnection("127.0.0.1", self.puerto, timeout=20)
        c.request("POST", ruta, cuerpo, {"Content-Type": tipo})
        r = c.getresponse()
        salida = _json.loads(r.read() or b"{}")
        c.close()
        return r.status, salida

    _n = 0

    def _base_de_prueba(self) -> bytes:
        """
        Una base válida del sistema, como la que baja «copia de respaldo».

        Cada llamada arma la suya en su propia carpeta. Compartir el archivo entre
        pruebas daba «UNIQUE constraint failed» en la segunda y «database is locked» en
        la tercera, con treinta segundos de espera cada una: la suite pasaba de un
        segundo a más de un minuto y los errores no tenían nada que ver con lo que se
        estaba probando.
        """
        type(self)._n += 1
        d = Path(self.tmp.name) / f"suelta-{type(self)._n}"
        cx = db.abrir(d / "b.sqlite")
        try:
            cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,paginas,
                                               ingerido_en)
                          VALUES (?,'/x.pdf','x.pdf',10,1,?)""",
                       (f"z{type(self)._n}", ahora()))
            cx.commit()
            copia = respaldo.hacer(cx, d / "copia.sqlite")
        finally:
            cx.close()
        return copia.read_bytes()

    def test_mirar_dice_que_trae_sin_instalar_nada(self):
        estado, r = self._post("/api/respaldo/mirar", self._base_de_prueba(),
                               "application/octet-stream")
        self.assertEqual(estado, 200, r)
        self.assertTrue(r["ok"])
        self.assertEqual(r["archivos"], 1)

    def test_mirar_rechaza_un_pdf_con_un_mensaje_que_se_entiende(self):
        estado, r = self._post("/api/respaldo/mirar", b"%PDF-1.4 un contrato",
                               "application/octet-stream")
        self.assertEqual(estado, 400)
        self.assertIn("no es una base SQLite", r["error"])

    def test_restaurar_exige_el_numero_del_legajo(self):
        estado, nuevo = self._post("/api/legajos",
                                   {"numero": "71.001", "caratula": "Para restaurar"})
        self.assertEqual(estado, 200, nuevo)
        slug = nuevo["slug"]
        estado, r = self._post(
            f"/api/respaldo/restaurar?slug={slug}&confirmacion=cualquiera",
            self._base_de_prueba(), "application/octet-stream")
        self.assertEqual(estado, 400, r)
        self.assertIn("71.001", r["error"])

    def test_restaurar_con_el_numero_pisa_la_base_y_aparta_la_anterior(self):
        estado, nuevo = self._post("/api/legajos",
                                   {"numero": "71.002", "caratula": "Para restaurar"})
        slug = nuevo["slug"]
        estado, r = self._post(
            f"/api/respaldo/restaurar?slug={slug}&confirmacion=71.002",
            self._base_de_prueba(), "application/octet-stream")
        self.assertEqual(estado, 200, r)
        self.assertTrue(r["ok"])
        self.assertEqual(r["archivos"], 1)

    def test_restaurar_sobre_un_legajo_que_no_existe_no_crea_nada(self):
        estado, r = self._post(
            "/api/respaldo/restaurar?slug=inventado&confirmacion=inventado",
            self._base_de_prueba(), "application/octet-stream")
        self.assertEqual(estado, 404, r)
        self.assertFalse((Path(self.tmp.name) / "legajos" / "inventado").exists())


if __name__ == "__main__":
    unittest.main()
