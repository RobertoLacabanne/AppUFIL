"""
Cargar el mismo papel dos veces.

El sistema reconocía el mismo ARCHIVO: se guarda bajo su SHA-256 y un byte igual al
anterior se anota como copia. Eso alcanzaba mientras el material llegara una sola vez y
de una sola mano.

No alcanza, y está medido. Abrir el expediente 201.602 y volver a exportarlo —lo que
hace cualquier programa al guardarlo, y lo que hace un portal al rearmar la descarga—
produce el mismo documento con otro SHA-256: mismas 88 páginas, mismos 22.776.043
bytes, otra huella. Cargado de nuevo, el sistema dijo «nuevos 1» y el legajo quedó con
2 archivos y 176 fojas. El expediente entero duplicado, sin un solo aviso.

En un expediente eso no es una molestia: son los mismos importes contados dos veces, la
misma decisión pedida dos veces en la cola, y dos «documentos» que se pisan en el tiempo
porque son el mismo papel. El sistema encontraría una superposición que no existe.

Lo que se cuida acá es que reconozca la foja y no el archivo, y —sobre todo— que al
hacerlo no se lleve puesta ninguna foja legítima.
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import fitz

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ufil import huella as hu      # noqa: E402
from ufil import db                # noqa: E402


def _pdf(paginas: list[str], destino: Path) -> Path:
    """Un PDF de prueba: una frase por página. Sin frase, la página queda en blanco."""
    doc = fitz.open()
    for texto in paginas:
        pg = doc.new_page(width=595, height=842)
        if texto:
            # Bastante tinta como para que la foja tenga huella: una línea suelta a 24
            # dpi es casi nada, y casi nada es una hoja en blanco.
            for i in range(28):
                pg.insert_text((50, 80 + i * 24), texto * 3, fontsize=15)
    doc.save(destino)
    doc.close()
    return destino


class LaHuellaEsDeLaFojaYNoDelArchivo(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_el_mismo_dibujo_da_la_misma_huella(self):
        a = hu.del_archivo(_pdf(["alfa", "beta"], self.tmp / "a.pdf"))
        b = hu.del_archivo(_pdf(["alfa", "beta"], self.tmp / "b.pdf"))
        self.assertEqual(a, b, "dos archivos con las mismas fojas dan huellas distintas")

    def test_y_una_foja_distinta_da_otra(self):
        a = hu.del_archivo(_pdf(["alfa"], self.tmp / "a.pdf"))
        b = hu.del_archivo(_pdf(["gama"], self.tmp / "b.pdf"))
        self.assertNotEqual(a, b)

    def test_reexportar_el_pdf_no_cambia_la_huella(self):
        """
        Es el caso que lo motivó todo: el mismo documento con otro SHA-256.
        """
        uno = _pdf(["alfa", "beta", "gama"], self.tmp / "uno.pdf")
        d = fitz.open(uno)
        d.save(self.tmp / "dos.pdf")
        d.close()
        self.assertNotEqual((self.tmp / "uno.pdf").read_bytes(),
                            (self.tmp / "dos.pdf").read_bytes(),
                            "el reexportado salió igual byte a byte y la prueba no "
                            "está probando nada")
        self.assertEqual(hu.del_archivo(uno), hu.del_archivo(self.tmp / "dos.pdf"))

    def test_una_hoja_en_blanco_no_tiene_huella(self):
        """
        Dos hojas en blanco se parecen entre sí más que ninguna otra cosa. Contarlas
        como coincidencia diría «este expediente ya estaba» por cuarenta y cuatro
        dorsos vacíos.
        """
        h = hu.del_archivo(_pdf(["alfa", ""], self.tmp / "a.pdf"))
        self.assertTrue(h[0])
        self.assertEqual(h[1], "", "un dorso en blanco está diciendo que es una foja")

    def test_el_umbral_de_tinta_esta_entre_los_dos_casos_medidos(self):
        """Dorsos del expediente: 0,00076 a 0,0046. Frentes: 0,047 a 0,71."""
        self.assertGreater(hu.TINTA_MINIMA, 0.0046)
        self.assertLess(hu.TINTA_MINIMA, 0.047)


class ElMismoPapelNoEntraDosVeces(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cx = sqlite3.connect(self.tmp / "b.sqlite")
        self.cx.row_factory = sqlite3.Row
        db.inicializar(self.cx)

    def _cargar(self, nombre: str, huellas: list[str], paginas: int | None = None):
        """Deja un archivo en la base con esas huellas, sin pasar por la ingesta."""
        n = paginas if paginas is not None else len(huellas)
        self.cx.execute("""INSERT INTO archivo (sha256, ruta_original, nombre, bytes,
                                                mtime, mime, paginas, ingerido_en)
                           VALUES (?,?,?,0,0,'application/pdf',?,'2026-01-01')""",
                        (nombre, f"/tmp/{nombre}", nombre, n))
        for i, h in enumerate(huellas, start=1):
            self.cx.execute("""INSERT INTO pagina (sha256, nro, ancho_pt, alto_pt,
                                                   tiene_texto, huella)
                               VALUES (?,?,595,842,0,?)""", (nombre, i, h or None))
        self.cx.commit()

    def test_una_copia_entera_se_reconoce(self):
        self._cargar("viejo", ["a", "b", "c"])
        c = hu.cotejar(self.cx, ["a", "b", "c"])
        self.assertEqual(hu.veredicto(c), "repetido")
        self.assertEqual(c["mismo_que"], "viejo")

    def test_con_dorsos_en_blanco_tambien(self):
        """
        La mitad del expediente son dorsos sin huella. Si las fojas que no se pueden
        comparar impidieran declarar la copia, el caso real —44 de 88— no se detectaría
        nunca.
        """
        self._cargar("viejo", ["a", "", "b", ""])
        c = hu.cotejar(self.cx, ["a", "", "b", ""])
        self.assertEqual(hu.veredicto(c), "repetido")

    def test_pero_una_foja_nueva_lo_impide(self):
        """
        Éste es el que importa. Un archivo con cuatro fojas del empalme y cuatro nuevas
        NO es una copia: tirarlo es hacer desaparecer prueba, que es lo peor que puede
        hacer este sistema. Y pasaba: la primera versión miraba sólo las fojas
        comparables, así que cuatro fojas nuevas casi vacías no contaban y el archivo
        se declaraba copia entera.
        """
        self._cargar("viejo", ["a", "b", "c", "d"])
        c = hu.cotejar(self.cx, ["a", "b", "nueva", ""])
        self.assertEqual(hu.veredicto(c), "parcial",
                         "un archivo con fojas nuevas se está tirando como copia")
        self.assertIsNone(c["mismo_que"])
        self.assertEqual(c["nuevas"], 1)

    def test_y_tampoco_si_tiene_otra_cantidad_de_fojas(self):
        """Un pedazo de un archivo no es ese archivo."""
        self._cargar("viejo", ["a", "b", "c", "d"])
        c = hu.cotejar(self.cx, ["a", "b"])
        self.assertEqual(hu.veredicto(c), "parcial")

    def test_el_solapamiento_dice_cuánto_y_con_qué(self):
        """
        Dos partes de un expediente comparten la foja del empalme, y eso es correcto en
        el papel. El sistema avisa y NO decide: quien carga sabe cuál de las dos cosas
        es.
        """
        self._cargar("parte4", ["a", "b", "c"])
        c = hu.cotejar(self.cx, ["c", "nueva1", "nueva2"])
        self.assertEqual(hu.veredicto(c), "parcial")
        self.assertEqual(c["repetidas"], 1)
        self.assertEqual(c["nuevas"], 2)
        self.assertEqual(c["archivos"][0]["archivo"], "parte4")
        self.assertIn((1, "parte4", 3), c["donde"],
                      "no dice en qué foja del otro archivo estaba")

    def test_un_archivo_nuevo_no_molesta(self):
        self._cargar("viejo", ["a", "b"])
        c = hu.cotejar(self.cx, ["x", "y"])
        self.assertEqual(hu.veredicto(c), "nuevo")
        self.assertEqual(c["repetidas"], 0)

    def test_no_se_compara_contra_si_mismo(self):
        """Al recalcular la huella de un archivo ya cargado, no es copia de sí mismo."""
        self._cargar("viejo", ["a", "b"])
        c = hu.cotejar(self.cx, ["a", "b"], sha_propio="viejo")
        self.assertEqual(hu.veredicto(c), "nuevo")


class QueFaltaProcesar(unittest.TestCase):
    """
    Antes el único dato era «N documentos sin leer», y contaba archivos SIN NINGUNA
    lectura. Un archivo leído a medias —porque el procesamiento se cortó, o porque la
    máquina se apagó— no aparecía ni como pendiente ni como terminado. Y «leído pero sin
    extraer» no existía como estado: un archivo podía estar leído entero y no haber
    producido una sola foja clasificada sin que nada lo dijera.
    """

    SRV = (RAIZ / "ufil/servidor.py").read_text(encoding="utf-8")
    APP = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")

    def test_hay_estado_por_archivo(self):
        self.assertIn("def api_archivos", self.SRV)
        for estado in ("sin_leer", "a_medio_leer", "sin_extraer", "listo"):
            self.assertIn(f'"{estado}"', self.SRV, f"falta el estado «{estado}»")
            self.assertIn(estado, self.APP, f"«{estado}» no se muestra en la pantalla")

    def test_lo_que_falta_manda_sobre_lo_que_ya_se_hizo(self):
        """Ochenta fojas leídas y ocho sin leer es «a medio leer», no «leído»."""
        i = self.SRV.index("def api_archivos")
        cuerpo = self.SRV[i:i + 3000]
        self.assertLess(cuerpo.index('"a_medio_leer"'), cuerpo.index('"listo"'),
                        "el estado se decide por lo que ya se hizo y no por lo que falta")

    def test_el_boton_dice_cuanto_falta_y_no_cuantos_archivos(self):
        self.assertIn("fojas sin leer", self.APP,
                      "el botón volvió a contar archivos: un archivo leído a medias no "
                      "se cuenta y su trabajo pendiente desaparece")
        self.assertIn("ar.falta_leer", self.APP)

    def test_a_medio_leer_se_ve_como_una_falla_y_no_como_algo_por_hacer(self):
        """
        Sin leer es trabajo pendiente; a medio leer es que algo se cortó. §2: el punzó
        se gasta si se usa para lo que simplemente falta hacer.
        """
        i = self.APP.index("const ESTADO_CARGA")
        cuerpo = self.APP[i:i + 600]
        self.assertIn("a_medio_leer: sello('alerta'", cuerpo)
        self.assertIn("sin_leer: sello('atencion'", cuerpo)


class NoSeSubeLoQueYaEsta(unittest.TestCase):
    """
    Un PDF de un expediente pesa veintidós megabytes. Subirlo entero para que el
    servidor conteste «ya estaba» es tiempo de quien está cargando, y una carpeta de
    trescientos escaneos vuelta a arrastrar es la tarde entera.
    """

    SRV = (RAIZ / "ufil/servidor.py").read_text(encoding="utf-8")
    APP = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")

    def test_se_pregunta_antes_de_subir(self):
        self.assertIn("def api_ya_esta", self.SRV)
        self.assertIn("/api/yaestan", self.APP)
        self.assertIn("crypto.subtle.digest('SHA-256'", self.APP,
                      "el navegador dejó de calcular la huella y vuelve a subir todo")

    def test_si_el_navegador_no_puede_se_sube_igual(self):
        """
        `crypto.subtle` no existe sin HTTPS y sin localhost. Que falte esto no puede
        impedir cargar: es una optimización, no un control.
        """
        self.assertIn("if (crypto.subtle)", self.APP,
                      "se da por sentado que el navegador puede calcular el hash")

    def test_cada_final_se_dice_distinto(self):
        for pieza, queja in (
                ("ya estaba — no se subió", "no se distingue lo que ni se subió"),
                ("es el mismo papel que", "el mismo papel con otro nombre no se dice"),
                ("fojas ya estaban", "el solapamiento parcial no se dice")):
            self.assertIn(pieza, self.APP, queja)

    def test_el_mismo_papel_se_puede_auditar_despues(self):
        """
        Un archivo que entró y no dejó rastro tiene que poder explicarse después: va a
        «Quedaron afuera», que es la pantalla que existe para eso.
        """
        self.assertIn("'mismo_papel'", self.SRV,
                      "el archivo rechazado por ser el mismo papel no aparece en "
                      "«Quedaron afuera» y desaparece sin explicación")
