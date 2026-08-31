"""
QUE LO QUE SE ACTUALIZA, SE VEA.

Pasó de verdad: se desplegó una versión nueva, el servidor la estaba sirviendo, y quien
entró siguió viendo la de antes. Perseguir eso cuesta una tarde y termina en «probá
recargar con Ctrl+Shift+R», que no es una solución: es pedirle a cada persona que
arregle a mano un problema del sistema.

Dos reglas, y las dos son verificables:

  · La etiqueta de versión sale del CONTENIDO. Salía de la fecha y el tamaño, y eso
    puede mentir: dos versiones que coinciden en las dos cosas comparten etiqueta, el
    navegador recibe un 304 y se queda con la vieja para siempre.

  · La portada pide `app.js` y `estilo.css` con `?v=<huella>`. Una versión nueva es una
    dirección nueva, y ninguna caché —navegador, proxy de la oficina, CDN— puede servir
    la anterior. Sin esto, el peor caso no es ver la interfaz vieja: es el JavaScript
    nuevo corriendo con la hoja de estilos vieja.
"""
from __future__ import annotations

import re
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ufil import config, db, servidor


class LaVersionViajaEnLaDireccion(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls._datos = config.DATOS
        config.DATOS = Path(cls.tmp.name)
        config.activar_legajo(None)
        db.abrir(Path(cls.tmp.name) / "ufil.sqlite").close()
        servidor.RUTA_BASE = None
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), servidor.Manejador)
        cls.puerto = cls.srv.server_address[1]
        cls.hilo = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.hilo.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close(); cls.hilo.join(timeout=5)
        config.DATOS = cls._datos
        cls.tmp.cleanup()

    def _pedir(self, ruta, cabeceras=None):
        r = urllib.request.Request(f"http://127.0.0.1:{self.puerto}{ruta}",
                                   headers=cabeceras or {})
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, dict(resp.headers), resp.read()

    def _portada(self):
        return self._pedir("/")[2].decode("utf-8")

    def test_la_portada_pide_los_archivos_con_version(self):
        html = self._portada()
        for archivo in ("app.js", "estilo.css"):
            self.assertRegex(html, rf"/estatico/{re.escape(archivo)}\?v=[0-9a-f]{{6,}}",
                             f"«{archivo}» se pide sin versión: una caché vieja puede "
                             f"seguir sirviéndolo después de actualizar")

    def test_la_portada_no_se_guarda(self):
        """Es la que trae los números de versión. Guardada, sigue pidiendo los viejos."""
        _, cab, _ = self._pedir("/")
        self.assertEqual(cab.get("Cache-Control"), "no-store")

    def test_el_archivo_versionado_se_puede_guardar_para_siempre(self):
        v = re.search(r"app\.js\?v=([0-9a-f]+)", self._portada()).group(1)
        _, cab, _ = self._pedir(f"/estatico/app.js?v={v}")
        self.assertIn("immutable", cab.get("Cache-Control", ""),
                      "la URL versionada no cambia nunca: se puede guardar un año")

    def test_sin_version_se_revalida_siempre(self):
        _, cab, _ = self._pedir("/estatico/app.js")
        self.assertEqual(cab.get("Cache-Control"), "no-cache")

    def test_la_etiqueta_sale_del_contenido_y_no_de_la_fecha(self):
        """
        Se toca la fecha del archivo sin cambiar un byte: la etiqueta NO puede moverse.
        Con la etiqueta vieja —fecha + tamaño— cualquier `touch` invalidaba la caché de
        todo el mundo sin motivo, y peor: dos versiones distintas del mismo tamaño y con
        la misma fecha compartían etiqueta.
        """
        ruta = config.WEB / "app.js"
        antes = servidor.huella(ruta)
        st = ruta.stat()
        import os
        os.utime(ruta, (st.st_atime + 10, st.st_mtime + 10))
        try:
            self.assertEqual(servidor.huella(ruta), antes,
                             "la huella cambió sin que cambiara el contenido")
        finally:
            os.utime(ruta, (st.st_atime, st.st_mtime))

    def test_al_cambiar_el_contenido_cambia_la_version(self):
        ruta = config.WEB / "app.js"
        original = ruta.read_bytes()
        antes = re.search(r"app\.js\?v=([0-9a-f]+)", self._portada()).group(1)
        try:
            ruta.write_bytes(original + b"\n/* un cambio */\n")
            despues = re.search(r"app\.js\?v=([0-9a-f]+)", self._portada()).group(1)
            self.assertNotEqual(antes, despues,
                                "se cambió el archivo y la dirección quedó igual: "
                                "el navegador va a seguir con la versión anterior")
        finally:
            ruta.write_bytes(original)

    def test_el_mismo_contenido_devuelve_304(self):
        v = re.search(r"app\.js\?v=([0-9a-f]+)", self._portada()).group(1)
        _, cab, _ = self._pedir(f"/estatico/app.js?v={v}")
        etag = cab["ETag"]
        try:
            self._pedir(f"/estatico/app.js?v={v}", {"If-None-Match": etag})
            self.fail("tendría que haber contestado 304")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 304)


if __name__ == "__main__":
    unittest.main(verbosity=2)
