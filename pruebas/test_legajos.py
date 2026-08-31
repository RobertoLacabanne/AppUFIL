"""
LA SÉPTIMA REGLA: ningún cálculo cruza legajos.

Es la única de las siete que no se puede escribir como un `WHERE`. Las otras seis dicen
qué valores pueden entrar en un resultado; esta dice de qué causa pueden salir. Y la
diferencia importa: un filtro que alguien se olvida de poner devuelve de más en
silencio, y el número queda mal en un informe que ya se firmó.

Por eso la separación no es una columna sino un archivo. Estas pruebas verifican que la
separación sea real —que los datos estén de verdad en bases distintas— y no una promesa
de la capa de consultas:

  · un total calculado en un legajo no ve los contratos del otro;
  · una persona identificada en un legajo no aparece en el otro;
  · las imágenes de página y los originales caen adentro de la carpeta de su legajo;
  · dos hilos pueden trabajar en legajos distintos a la vez sin pisarse;
  · un legajo inventado no crea una base: da error.
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ufil import confianza as cf
from ufil import config, db, legajos
from ufil.db import ahora


class DosLegajos(unittest.TestCase):
    """Dos causas distintas, cada una con su contrato y su plata."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._datos = config.DATOS
        config.DATOS = Path(self.tmp.name)
        config.activar_legajo(None)
        self.a = legajos.crear("87.933", "Contratos Legislatura")
        self.b = legajos.crear("91.002", "Otra causa, otra gente")

    def tearDown(self):
        config.activar_legajo(None)
        config.DATOS = self._datos
        self.tmp.cleanup()

    # -- utilidades --
    def _cargar(self, slug, sha, nombre, monto_centavos, cuil):
        """Un contrato con nombre, documento y monto FIRMES en el legajo `slug`."""
        config.activar_legajo(slug)
        cx = db.abrir()
        try:
            cx.execute("""INSERT INTO archivo
                          (sha256,ruta_original,nombre,bytes,paginas,ingerido_en)
                          VALUES (?,?,?,1,1,?)""",
                       (sha, f"/x/{sha}.pdf", f"{sha}.pdf", ahora()))
            cx.execute("INSERT INTO pagina (sha256,nro,ancho_pt,alto_pt) VALUES (?,1,595,842)",
                       (sha,))
            doc = cx.execute(
                """INSERT INTO documento (sha256,orden,pagina_desde,pagina_hasta,tipo,perfil)
                   VALUES (?,1,1,1,'contrato_obra','p')""", (sha,)).lastrowid
            for campo, literal, norm in (
                    ("nombre", nombre, nombre.upper()),
                    ("documento", cuil, f"CUIL:{cuil.replace('-','')}"),
                    ("monto", f"${monto_centavos // 100}", str(monto_centavos))):
                cid = cx.execute(
                    """INSERT INTO campo (documento_id,nombre,valor_literal,pagina_nro,
                                          x0,y0,x1,y1,confianza,estado)
                       VALUES (?,?,?,1,10,10,90,30,0.97,?)""",
                    (doc, campo, literal, cf.AUTOMATICO_ALTA)).lastrowid
                cx.execute("INSERT INTO normalizacion (campo_id,tipo,valor_norm) VALUES (?,?,?)",
                           (cid, campo, norm))
            cx.commit()
        finally:
            cx.close()

    def _total_firme(self, slug):
        from ufil import capa4_analisis as c4
        config.activar_legajo(slug)
        cx = db.abrir()
        try:
            return c4.correr(cx, "10_totales")["filas"][0]
        finally:
            cx.close()

    # -- las pruebas --
    def test_un_total_no_suma_los_contratos_del_otro_legajo(self):
        self._cargar(self.a.slug, "aa", "PEREZ, Ana", 1_000_00, "27-11111111-4")
        self._cargar(self.b.slug, "bb", "GOMEZ, Luis", 9_999_00, "20-22222222-3")

        ta = self._total_firme(self.a.slug)
        tb = self._total_firme(self.b.slug)

        self.assertEqual(ta["total_firme_centavos"], 1_000_00,
                         "el total del legajo 87.933 tiene adentro plata del 91.002")
        self.assertEqual(tb["total_firme_centavos"], 9_999_00)
        self.assertEqual(ta["contratos_con_monto_firme"], 1)
        self.assertEqual(tb["contratos_con_monto_firme"], 1)

    def test_una_persona_de_un_legajo_no_aparece_en_el_otro(self):
        from ufil.capa3_identidad import resolver
        self._cargar(self.a.slug, "aa", "PEREZ, Ana", 1_000_00, "27-11111111-4")
        self._cargar(self.b.slug, "bb", "GOMEZ, Luis", 9_999_00, "20-22222222-3")

        vistos = {}
        for slug in (self.a.slug, self.b.slug):
            config.activar_legajo(slug)
            cx = db.abrir()
            try:
                resolver(cx)
                vistos[slug] = {r["nombre_literal"] for r in
                                cx.execute("SELECT nombre_literal FROM persona_alias")}
            finally:
                cx.close()

        self.assertEqual(vistos[self.a.slug], {"PEREZ, Ana"})
        self.assertEqual(vistos[self.b.slug], {"GOMEZ, Luis"})
        self.assertFalse(vistos[self.a.slug] & vistos[self.b.slug],
                         "hay una persona que figura en los dos legajos")

    def test_son_archivos_distintos_de_verdad(self):
        """
        La garantía no es que las consultas filtren bien: es que no hay dónde mezclar.

        Si algún día alguien vuelve a una columna `legajo_id`, esta prueba se cae, y esa
        es exactamente la conversación que hay que tener antes de hacerlo.
        """
        self._cargar(self.a.slug, "aa", "PEREZ, Ana", 1_000_00, "27-11111111-4")
        self._cargar(self.b.slug, "bb", "GOMEZ, Luis", 9_999_00, "20-22222222-3")

        self.assertNotEqual(self.a.base, self.b.base)
        for base, esperado in ((self.a.base, "PEREZ, Ana"), (self.b.base, "GOMEZ, Luis")):
            cx = sqlite3.connect(f"file:{base}?mode=ro", uri=True)
            try:
                nombres = [r[0] for r in cx.execute(
                    "SELECT valor_literal FROM campo WHERE nombre='nombre'")]
            finally:
                cx.close()
            self.assertEqual(nombres, [esperado],
                             f"{base.name} tiene adentro datos de otro legajo")

    def test_los_derivados_caen_adentro_de_su_legajo(self):
        """Las imágenes de página pesan y son del legajo: no pueden ir a una pila común."""
        config.activar_legajo(self.a.slug)
        self.assertEqual(Path(config.DERIVADOS), self.a.carpeta / "derivados")
        self.assertEqual(Path(config.ORIGINALES), self.a.carpeta / "originales")
        config.activar_legajo(self.b.slug)
        self.assertEqual(Path(config.DERIVADOS), self.b.carpeta / "derivados")
        self.assertNotEqual(Path(config.DERIVADOS), self.a.carpeta / "derivados")

    def test_dos_hilos_en_legajos_distintos_no_se_pisan(self):
        """
        El servidor es multihilo y el procesamiento corre en otro hilo todavía.

        Con un legajo activo global, abrir una causa en una pestaña le cambiaría la
        causa al trabajo que está corriendo en otra. Esto verifica que no pasa.
        """
        config.activar_legajo(self.a.slug)
        visto = {}
        arranco = threading.Event()

        def otro_hilo():
            config.activar_legajo(self.b.slug)
            visto["b"] = Path(config.BASE)
            arranco.set()

        h = threading.Thread(target=otro_hilo); h.start(); arranco.wait(); h.join()

        self.assertEqual(visto["b"], self.b.base)
        self.assertEqual(Path(config.BASE), self.a.base,
                         "otro hilo le cambió el legajo a este")

    def test_un_hilo_reciclado_no_hereda_el_legajo_anterior(self):
        """
        Los hilos del servidor se reusan entre pedidos. Un pedido sin legajo que caiga
        en el hilo que atendió al legajo A tiene que quedarse sin legajo, no con el A.
        """
        config.activar_legajo(self.a.slug)
        config.activar_legajo(None)
        self.assertIsNone(config.legajo_activo())
        self.assertEqual(Path(config.BASE), Path(config.DATOS) / "ufil.sqlite")

    def test_un_legajo_inventado_no_crea_una_base(self):
        """
        Un número mal tipeado tiene que ser un error a la vista. Si la ruta se armara
        sola con lo que vino escrito, quedaría una causa fantasma —vacía, con nombre
        parecido a la de verdad— y nadie se enteraría hasta que faltaran documentos.
        """
        self.assertNotIn("87-9333", legajos.slugs())
        with self.assertRaises(legajos.LegajoInexistente):
            legajos.obtener("87-9333")
        self.assertFalse((Path(config.DATOS) / "legajos" / "87-9333").exists())

    def test_no_se_repite_el_numero_de_legajo(self):
        with self.assertRaises(legajos.LegajoDuplicado):
            legajos.crear("87.933", "La misma causa cargada dos veces")

    def test_la_lista_cuenta_lo_de_cada_uno(self):
        self._cargar(self.a.slug, "aa", "PEREZ, Ana", 1_000_00, "27-11111111-4")
        config.activar_legajo(None)
        por_slug = {f["slug"]: f for f in legajos.listar()}
        self.assertEqual(por_slug[self.a.slug]["documentos"], 1)
        self.assertEqual(por_slug[self.b.slug]["documentos"], 0)
        self.assertEqual(por_slug[self.b.slug]["archivos"], 0)


class PorHTTP(unittest.TestCase):
    """
    Lo mismo pero por la puerta por la que entra de verdad: el servidor.

    Las pruebas de arriba activan el legajo llamando a la función. Acá lo hace un
    navegador, con una cookie, contra un servidor de verdad — que es donde el error
    aparecería: dos pestañas abiertas en dos causas, atendidas por el mismo pool de
    hilos.
    """

    @classmethod
    def setUpClass(cls):
        from http.server import ThreadingHTTPServer
        from ufil import servidor

        cls.tmp = tempfile.TemporaryDirectory()
        cls._datos = config.DATOS
        config.DATOS = Path(cls.tmp.name)
        config.activar_legajo(None)
        cls.a = legajos.crear("87.933", "Contratos Legislatura")
        cls.b = legajos.crear("91.002", "Otra causa")

        for slug, sha, nombre in ((cls.a.slug, "aa", "PEREZ, Ana"),
                                  (cls.b.slug, "bb", "GOMEZ, Luis")):
            config.activar_legajo(slug)
            cx = db.abrir()
            cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,
                                               paginas,ingerido_en)
                          VALUES (?,?,?,1,1,?)""",
                       (sha, f"/x/{sha}.pdf", f"{nombre}.pdf", ahora()))
            cx.execute("INSERT INTO pagina (sha256,nro,ancho_pt,alto_pt) VALUES (?,1,595,842)",
                       (sha,))
            doc = cx.execute("""INSERT INTO documento (sha256,orden,pagina_desde,
                                                       pagina_hasta,tipo,perfil)
                                VALUES (?,1,1,1,'contrato_obra','p')""", (sha,)).lastrowid
            cx.execute("""INSERT INTO campo (documento_id,nombre,valor_literal,pagina_nro,
                                             x0,y0,x1,y1,confianza,estado)
                          VALUES (?,'nombre',?,1,10,10,90,30,0.97,?)""",
                       (doc, nombre, cf.AUTOMATICO_ALTA))
            cx.commit(); cx.close()
        config.activar_legajo(None)

        servidor.RUTA_BASE = None
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), servidor.Manejador)
        cls.puerto = cls.srv.server_address[1]
        cls.hilo = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.hilo.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close(); cls.hilo.join(timeout=5)
        config.activar_legajo(None)
        config.DATOS = cls._datos
        cls.tmp.cleanup()

    def _pedir(self, ruta, legajo=None):
        import json as _json
        import urllib.request
        r = urllib.request.Request(f"http://127.0.0.1:{self.puerto}{ruta}")
        if legajo:
            r.add_header("Cookie", f"ufil_legajo={legajo}")
        with urllib.request.urlopen(r, timeout=10) as resp:
            return _json.loads(resp.read())

    def test_cada_cookie_ve_su_legajo(self):
        pa = self._pedir("/api/contratos", self.a.slug)
        pb = self._pedir("/api/contratos", self.b.slug)
        self.assertEqual([c["nombre_literal"] for c in pa], ["PEREZ, Ana"])
        self.assertEqual([c["nombre_literal"] for c in pb], ["GOMEZ, Luis"])

    def test_pedirlo_muchas_veces_en_paralelo_no_los_mezcla(self):
        """
        El caso que rompe una variable global: dos pestañas pidiendo a la vez, sobre un
        pool de hilos que se reparte los pedidos como quiere.
        """
        errores = []

        def machacar(slug, esperado):
            try:
                for _ in range(12):
                    filas = self._pedir("/api/contratos", slug)
                    nombres = [c["nombre_literal"] for c in filas]
                    if nombres != [esperado]:
                        errores.append(f"{slug} devolvió {nombres}")
            except Exception as e:                       # pragma: no cover
                errores.append(f"{slug}: {type(e).__name__}: {e}")

        hilos = [threading.Thread(target=machacar, args=a) for a in
                 ((self.a.slug, "PEREZ, Ana"), (self.b.slug, "GOMEZ, Luis"),
                  (self.a.slug, "PEREZ, Ana"), (self.b.slug, "GOMEZ, Luis"))]
        for h in hilos: h.start()
        for h in hilos: h.join(timeout=30)
        self.assertEqual(errores, [], "se cruzaron los legajos entre pedidos simultáneos")

    def test_una_cookie_con_un_legajo_inventado_no_abre_nada(self):
        """Y sobre todo: no le muestra el legajo del pedido anterior."""
        self._pedir("/api/contratos", self.a.slug)          # deja el hilo «caliente»
        filas = self._pedir("/api/contratos", "87-9333-inventado")
        self.assertEqual([c["nombre_literal"] for c in filas], [],
                         "una cookie inventada terminó mostrando datos de otro legajo")
        self.assertFalse((Path(config.DATOS) / "legajos" / "87-9333-inventado").exists())

    def test_la_lista_de_legajos_se_contesta_sin_legajo_abierto(self):
        r = self._pedir("/api/legajos")
        self.assertEqual({l["numero"] for l in r["legajos"]}, {"87.933", "91.002"})
        self.assertIsNone(r["activo"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
