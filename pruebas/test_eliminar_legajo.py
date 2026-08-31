"""
BORRAR UN LEGAJO SIN PERDER NADA.

Un legajo son meses de lectura y de revisión a mano, y adentro están los PDF que
alguien subió por la interfaz —que en una instalación de nube pueden ser la única
copia que quedó de ese lote—. Un borrado de un clic es un borrado que tarde o
temprano ocurre por accidente, y no hay «deshacer» que lo arregle.

Por eso son dos tiempos, y estas pruebas verifican los dos:

  1. Eliminar MUEVE la carpeta a la papelera. No se pierde un solo byte, y se puede
     traer de vuelta con todo adentro.
  2. Destruir borra de verdad, y sólo desde la papelera, con el número escrito otra
     vez a mano.

Y en los dos casos: sin el número exacto no pasa nada, y el legajo sigue entero.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ufil import config, db, legajos
from ufil.db import ahora


class Papelera(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._datos = config.DATOS
        config.DATOS = Path(self.tmp.name)
        config.activar_legajo(None)
        self.l = legajos.crear("94.220", "Contratos Legislatura 2021-2023",
                               fiscal="Dra. Fulana")
        config.activar_legajo(self.l.slug)
        cx = db.abrir()
        cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,paginas,
                                           ingerido_en)
                      VALUES ('a1','/x/a1.pdf','a1.pdf',10,1,?)""", (ahora(),))
        cx.execute("""INSERT INTO documento (sha256,orden,pagina_desde,pagina_hasta,
                                            tipo,perfil)
                      VALUES ('a1',1,1,1,'contrato_obra','contrato_obra_legislatura')""")
        cx.commit()
        cx.close()
        # Un original en disco: es lo que no se puede perder.
        orig = legajos.carpeta_de(self.l.slug) / "originales"
        orig.mkdir(parents=True, exist_ok=True)
        (orig / "secuestro.pdf").write_bytes(b"%PDF-1.4 esto es el original")
        config.activar_legajo(None)

    def tearDown(self):
        config.activar_legajo(None)
        config.DATOS = self._datos
        self.tmp.cleanup()

    # ── Sin el número exacto no se borra nada ──────────────────────────────
    def test_sin_el_numero_escrito_no_pasa_nada(self):
        for intento in ("", "  ", "si", "94220", "94.221", "borrar"):
            with self.assertRaises(legajos.NoSePuede, msg=f"aceptó «{intento}»"):
                legajos.eliminar(self.l.slug, intento)
        self.assertIn(self.l.slug, legajos.slugs())
        self.assertTrue(legajos.carpeta_de(self.l.slug).is_dir())

    def test_el_mensaje_dice_qué_hay_que_escribir(self):
        """Un «no se pudo» sin decir qué falta obliga a adivinar, y adivinando se
        borra el legajo de al lado."""
        with self.assertRaises(legajos.NoSePuede) as e:
            legajos.eliminar(self.l.slug, "")
        self.assertIn("94.220", str(e.exception))

    # ── Eliminar mueve, no borra ───────────────────────────────────────────
    def test_eliminar_saca_del_registro_pero_guarda_todo(self):
        evento = legajos.eliminar(self.l.slug, "94.220")

        self.assertNotIn(self.l.slug, legajos.slugs())
        self.assertFalse(legajos.carpeta_de(self.l.slug).exists())

        guardado = legajos.carpeta_papelera() / evento["marca"]
        self.assertTrue((guardado / "ufil.sqlite").is_file(), "se perdió la base")
        self.assertEqual((guardado / "originales" / "secuestro.pdf").read_bytes(),
                         b"%PDF-1.4 esto es el original",
                         "se perdió el original, que es lo único irrecuperable")

    def test_la_papelera_dice_qué_hay_y_cuánto_pesa(self):
        legajos.eliminar(self.l.slug, "94.220")
        p = legajos.papelera()
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["numero"], "94.220",
                         "tiene que mostrar el número, no el slug con guiones")
        self.assertEqual(p[0]["documentos"], 1)
        self.assertGreater(p[0]["bytes"], 0, "sin el tamaño nadie sabe qué va a liberar")

    def test_lo_eliminado_queda_anotado(self):
        legajos.eliminar(self.l.slug, "94.220")
        lineas = (legajos.carpeta_papelera() / legajos.BITACORA).read_text(encoding="utf-8")
        self.assertIn("94.220", lineas)
        self.assertIn("Contratos Legislatura 2021-2023", lineas)

    # ── Traerlo de vuelta ──────────────────────────────────────────────────
    def test_restaurar_lo_devuelve_entero(self):
        evento = legajos.eliminar(self.l.slug, "94.220")
        vuelto = legajos.restaurar(evento["marca"])

        self.assertEqual(vuelto.numero, "94.220")
        self.assertEqual(vuelto.caratula, "Contratos Legislatura 2021-2023")
        self.assertIn(vuelto.slug, legajos.slugs())
        self.assertEqual(
            (legajos.carpeta_de(vuelto.slug) / "originales" / "secuestro.pdf").read_bytes(),
            b"%PDF-1.4 esto es el original")
        config.activar_legajo(vuelto.slug)
        cx = db.abrir()
        self.assertEqual(cx.execute("SELECT COUNT(*) FROM documento").fetchone()[0], 1)
        cx.close()
        self.assertEqual(legajos.papelera(), [])

    def test_no_restaura_encima_de_un_legajo_que_existe(self):
        """
        Restaurar sobre una carpeta ocupada mezclaría dos causas en el mismo archivo,
        que es exactamente lo que todo el diseño de legajos existe para impedir.
        """
        evento = legajos.eliminar(self.l.slug, "94.220")
        legajos.crear("94.220", "Otra cosa, mismo número")
        with self.assertRaises(legajos.NoSePuede):
            legajos.restaurar(evento["marca"])
        self.assertTrue((legajos.carpeta_papelera() / evento["marca"]).is_dir(),
                        "el fallido no puede dejar la papelera a medio vaciar")

    # ── Destruir de verdad ─────────────────────────────────────────────────
    def test_destruir_pide_el_numero_otra_vez(self):
        evento = legajos.eliminar(self.l.slug, "94.220")
        with self.assertRaises(legajos.NoSePuede):
            legajos.destruir(evento["marca"], "sí")
        self.assertTrue((legajos.carpeta_papelera() / evento["marca"]).is_dir())

        legajos.destruir(evento["marca"], "94.220")
        self.assertFalse((legajos.carpeta_papelera() / evento["marca"]).exists())
        self.assertEqual(legajos.papelera(), [])

    def test_destruir_no_llega_a_nada_de_afuera_de_la_papelera(self):
        """
        La marca viene escrita en un pedido HTTP.

        El caso que importa no es el obvio: es éste. Se elimina el legajo, se vuelve
        a crear uno con el mismo número —cosa perfectamente normal: alguien se
        equivocó de carátula y lo rehace—, y entonces `../legajos/94-220` apunta a un
        legajo VIVO. Como esa carpeta no tiene bitácora al lado, el número que el
        sistema exige confirmar termina siendo el texto del ataque, que el atacante
        obviamente conoce. Sin la comprobación del camino, ahí se le pasa el `rmtree`
        a una causa en uso.

        Esta prueba está escrita para fallar si esa comprobación se saca. La versión
        anterior no fallaba: la salvaba de casualidad el control del número.
        """
        legajos.eliminar(self.l.slug, "94.220")
        vivo = legajos.crear("94.220", "La causa rehecha")
        camino = "../legajos/" + vivo.slug

        with self.assertRaises(legajos.NoSePuede):
            legajos.destruir(camino, camino)       # la confirmación «acierta»
        self.assertTrue(legajos.carpeta_de(vivo.slug).is_dir(),
                        "se borró un legajo en uso desde la papelera")

        for veneno in (camino, "..", "/etc", ".", "a/../..", "..\\legajos", ".oculto"):
            with self.assertRaises(legajos.NoSePuede, msg=f"aceptó «{veneno}»"):
                legajos.destruir(veneno, veneno)
            with self.assertRaises(legajos.NoSePuede, msg=f"aceptó «{veneno}»"):
                legajos.restaurar(veneno)
        self.assertTrue(legajos.carpeta_de(vivo.slug).is_dir())

    def test_eliminar_un_legajo_no_toca_al_de_al_lado(self):
        otro = legajos.crear("87.933", "La otra causa")
        legajos.eliminar(self.l.slug, "94.220")
        self.assertIn(otro.slug, legajos.slugs())
        self.assertTrue(legajos.carpeta_de(otro.slug).is_dir())


if __name__ == "__main__":
    unittest.main()


class LosEndpointsDelBorrado(unittest.TestCase):
    """
    Las pruebas de arriba verifican `ufil/legajos.py` y pasaban todas mientras el
    endpoint que lo llama tiraba un TypeError en la primera línea: preguntaba
    `_procesador().estado()` cuando `estado` es un atributo, no un método. Se supo
    apretando el botón, no corriendo las pruebas.

    Así que acá se llama a los manejadores del servidor, con un servidor de verdad
    levantado sobre una carpeta temporal. Es más lento y es lo único que prueba que el
    botón hace algo.
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
        cls.srv = servidor.armar(0)          # puerto libre que elige el sistema
        cls.puerto = cls.srv.server_address[1]
        cls.hilo = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.hilo.start()
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

    def _post(self, ruta, datos):
        import json
        c = self.http.HTTPConnection("127.0.0.1", self.puerto, timeout=15)
        c.request("POST", ruta, json.dumps(datos),
                  {"Content-Type": "application/json"})
        r = c.getresponse()
        cuerpo = json.loads(r.read() or b"{}")
        c.close()
        return r.status, cuerpo

    def _get(self, ruta):
        import json
        c = self.http.HTTPConnection("127.0.0.1", self.puerto, timeout=15)
        c.request("GET", ruta)
        r = c.getresponse()
        cuerpo = json.loads(r.read() or b"{}")
        c.close()
        return r.status, cuerpo

    def test_el_camino_entero_desde_el_boton(self):
        estado, nuevo = self._post("/api/legajos",
                                   {"numero": "99.111", "caratula": "Prueba del borrado"})
        self.assertEqual(estado, 200, nuevo)
        slug = nuevo["slug"]

        # Sin el número escrito, no pasa nada y el legajo sigue en la lista.
        estado, r = self._post("/api/legajo/eliminar", {"slug": slug, "confirmacion": ""})
        self.assertEqual(estado, 400, r)
        self.assertIn("99.111", r["error"])
        self.assertIn("99.111", [l["numero"] for l in self._get("/api/legajos")[1]["legajos"]])

        # Con el número, va a la papelera.
        estado, r = self._post("/api/legajo/eliminar",
                               {"slug": slug, "confirmacion": "99.111"})
        self.assertEqual(estado, 200, r)
        _, lista = self._get("/api/legajos")
        self.assertNotIn("99.111", [l["numero"] for l in lista["legajos"]])
        self.assertEqual([p["numero"] for p in lista["papelera"]], ["99.111"])
        marca = lista["papelera"][0]["marca"]

        # Y vuelve entero.
        estado, r = self._post("/api/papelera/restaurar", {"marca": marca})
        self.assertEqual(estado, 200, r)
        _, lista = self._get("/api/legajos")
        self.assertIn("99.111", [l["numero"] for l in lista["legajos"]])
        self.assertEqual(lista["papelera"], [])

    def test_un_legajo_que_no_existe_no_borra_nada(self):
        estado, r = self._post("/api/legajo/eliminar",
                               {"slug": "inventado", "confirmacion": "inventado"})
        self.assertEqual(estado, 404, r)

    def test_la_identidad_sale_del_modulo_y_no_de_la_interfaz(self):
        estado, d = self._get("/api/identidad")
        self.assertEqual(estado, 200)
        self.assertEqual(d["unidad"], "UFIL Paraná")
        self.assertIn("Entre Ríos", d["linea_organismo"])
        self.assertTrue(d["fiscales"], "la pantalla se quedó sin fiscales")
        self.assertIn(d["fiscales"][0], d["firma"])
