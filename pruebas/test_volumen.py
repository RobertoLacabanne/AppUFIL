"""
Que el sistema aguante un expediente grande.

El pliego pide pensar en 500, 2.000 y 5.000 fojas. Lo que rompe a esa escala no es el
tiempo sino la memoria: cargar el archivo entero para mirarlo foja por foja hace que el
consumo crezca con el tamaño del PDF, y un expediente de 2.000 fojas pedía medio giga.

Medido antes del arreglo, sobre 400 fojas con dos rutas de lectura: **103 MB**. Después:
**1 MB**. Estas pruebas están para que no vuelva a crecer sin que nadie se entere.
"""
from __future__ import annotations

import sys
import tempfile
import tracemalloc
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ufil import capa2_extraccion as c2, db
from ufil.db import ahora

SHA = "f" * 64
FOJAS, PALABRAS = 120, 300       # suficiente para que la diferencia se vea, rápido de armar


def _archivo_grande(tmp: Path):
    cx = db.abrir(tmp / "t.sqlite")
    cx.execute("PRAGMA synchronous=OFF")
    cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,paginas,ingerido_en)
                  VALUES (?,'/x/g.pdf','grande.pdf',1,?,?)""", (SHA, FOJAS, ahora()))
    for n in range(1, FOJAS + 1):
        pid = cx.execute("INSERT INTO pagina (sha256,nro,ancho_pt,alto_pt) "
                         "VALUES (?,?,595,842)", (SHA, n)).lastrowid
        for ruta in ("ocr_a", "ocr_b"):
            lid = cx.execute(
                """INSERT INTO lectura (pagina_id,ruta,motor,version,confianza,ms,creado_en)
                   VALUES (?,?,'tesseract','5.4.0',0.9,10,?)""",
                (pid, ruta, ahora())).lastrowid
            cx.executemany(
                """INSERT INTO palabra (lectura_id,orden,texto,x0,y0,x1,y1,conf)
                   VALUES (?,?,?,?,?,?,?,0.9)""",
                [(lid, i, f"palabra{i}", 10 + i % 80 * 7, 20 + i // 80 * 12,
                  50 + i % 80 * 7, 32 + i // 80 * 12) for i in range(PALABRAS)])
    cx.commit()
    return cx


def _pico(fn) -> float:
    """El pico de memoria de una llamada, en MB."""
    tracemalloc.start()
    try:
        fn()
        _, pico = tracemalloc.get_traced_memory()
        return pico / 1_048_576
    finally:
        tracemalloc.stop()


class UnExpedienteGrandeNoSeCargaEntero(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.cx = _archivo_grande(Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls.cx.close()
        try:
            cls.tmp.cleanup()
        except PermissionError:
            pass

    def test_leer_foja_por_foja_no_retiene_el_archivo(self):
        """
        El generador entrega una foja por vez. Si retuviera todas, el pico crecería con
        el archivo y volveríamos al problema que esto vino a resolver.
        """
        def recorrer():
            total = 0
            for _nro, rutas in c2.leer_foja_por_foja(self.cx, SHA):
                total += sum(len(pw) for _lid, pw in rutas.values())
            return total
        pico = _pico(recorrer)
        self.assertLess(pico, 8, f"leer de a una foja no puede costar {pico:.0f} MB")

    def test_clasificar_no_hace_crecer_la_memoria_con_el_archivo(self):
        pico = _pico(lambda: c2.clasificar_fojas(self.cx, SHA))
        self.assertLess(pico, 8,
                        f"clasificar {FOJAS} fojas costó {pico:.0f} MB: la memoria "
                        f"volvió a crecer con el tamaño del PDF")

    def test_cotejar_numeros_tampoco(self):
        pico = _pico(lambda: c2.cotejar_numeros(self.cx, SHA))
        self.assertLess(pico, 8, f"cotejar costó {pico:.0f} MB")

    def test_cargar_el_archivo_entero_cuesta_mucho_mas(self):
        """
        No es una prueba de rendimiento: es la que deja escrito POR QUÉ existe la otra
        forma de leer. Si algún día cargar todo dejara de ser caro, esta prueba avisa y
        se puede simplificar el código.
        """
        entero = _pico(lambda: c2.lecturas_por_ruta(self.cx, SHA))
        de_a_una = _pico(lambda: [1 for _ in c2.leer_foja_por_foja(self.cx, SHA)])
        self.assertGreater(entero, de_a_una * 3,
                           f"cargar todo ({entero:.0f} MB) tenía que costar bastante "
                           f"más que de a una ({de_a_una:.0f} MB)")

    def test_las_fojas_sin_una_sola_palabra_siguen_contando(self):
        """
        Una hoja en blanco, un dorso y una fotocopia ilegible son fojas. Al pasar a leer
        de a una se cayeron del recuento, y una foja que desaparece del archivo es lo
        peor que puede hacer un sistema que existe para no perder papeles.
        """
        cx = db.abrir(Path(self.tmp.name) / "vacias.sqlite")
        cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,paginas,ingerido_en)
                      VALUES ('aa','/x/v.pdf','v.pdf',1,3,?)""", (ahora(),))
        for n in (1, 2, 3):
            pid = cx.execute("INSERT INTO pagina (sha256,nro,ancho_pt,alto_pt) "
                             "VALUES ('aa',?,595,842)", (n,)).lastrowid
            cx.execute("""INSERT INTO lectura (pagina_id,ruta,motor,version,confianza,ms,creado_en)
                          VALUES (?,'ocr_a','tesseract','5.4.0',0.9,10,?)""", (pid, ahora()))
        cx.commit()
        try:
            r = c2.clasificar_fojas(cx, "aa")
            self.assertEqual(r["fojas"], 3,
                             "las tres fojas se leyeron y ninguna dio palabras: siguen "
                             "siendo tres fojas")
        finally:
            cx.close()


if __name__ == "__main__":
    unittest.main()
