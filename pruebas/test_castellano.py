"""
CÓMO ESTÁ ESCRITO LO QUE SALE A LA PANTALLA Y AL PAPEL.

«1 archivo(s)». Ese paréntesis estaba en la interfaz, en la terminal, en el informe .rtf
y en la portada de la planilla. Un organismo que le manda a un juez un documento que
dice «1 contrato(s)» está diciendo, sin querer, que nadie lo leyó antes de mandarlo.

Y no era sólo el paréntesis: el panel decía «1 pares de contratos se pisan» y
«1 contratos quedaron afuera del cruce».

Estas pruebas no juzgan estilo. Buscan una forma concreta, verificable y equivocada.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ufil.castellano import concordar, miles, pesos, plural


class ElPluralConcuerda(unittest.TestCase):

    def test_uno_va_en_singular(self):
        self.assertEqual(plural(1, "archivo", "archivos"), "1 archivo")

    def test_muchos_van_en_plural(self):
        self.assertEqual(plural(3, "archivo", "archivos"), "3 archivos")

    def test_cero_va_en_plural(self):
        """«0 archivos», que es como se dice; «0 archivo» no lo escribe nadie."""
        self.assertEqual(plural(0, "archivo", "archivos"), "0 archivos")

    def test_se_pasan_las_dos_formas_enteras(self):
        """En castellano el plural no siempre es agregar una «s»."""
        self.assertEqual(plural(2, "mes", "meses"), "2 meses")
        self.assertEqual(plural(2, "lápiz", "lápices"), "2 lápices")

    def test_los_miles_van_con_punto(self):
        """La coma acá es el separador decimal: «1,234» se lee uno coma doscientos."""
        self.assertEqual(miles(1234567), "1.234.567")

    def test_los_pesos_llevan_coma_decimal(self):
        self.assertEqual(pesos(485_000_000), "$4.850.000,00")
        self.assertEqual(pesos(1050), "$10,50")

    def test_un_importe_que_no_existe_no_se_inventa_como_cero(self):
        """`None` es «no lo sabemos» y $0,00 es «es cero». No son lo mismo."""
        self.assertEqual(pesos(None), "—")
        self.assertEqual(pesos(0), "$0,00")


class NadieEscribeParentesisEse(unittest.TestCase):
    """
    Que no vuelva. Barre el código que produce texto para una persona.

    Se mira el fuente y no la salida porque la salida depende de los datos: un `(s)` en
    una rama que sólo se ve con cierto legajo cargado pasaría desapercibido hasta que
    aparezca en el peor momento, que es cuando alguien imprime el informe.
    """

    ARCHIVOS = [
        "ufil/cli.py", "ufil/servidor.py", "ufil/capa7_export.py", "ufil/diagnostico.py",
        "ufil/evaluacion.py", "ufil/respaldo.py", "ufil/acceso.py", "ufil/legajos.py",
        "ufil/web/app.js",
    ]
    # `(s)` aparece legítimamente en código: `querySelector(s)`, `str(s)`, una firma.
    # Lo que se busca es el paréntesis pegado a una palabra adentro de un texto.
    PATRON = re.compile(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}\(s\)")
    # `querySelector(s)` es una llamada, no un texto. Se reconoce porque lo que precede
    # al paréntesis es una función y no una palabra suelta adentro de una frase.
    LLAMADA = re.compile(r"[\w.$]\w*\(s(?:[,)])")

    def test_ninguno(self):
        malos = []
        for rel in self.ARCHIVOS:
            ruta = RAIZ / rel
            if not ruta.exists():
                continue
            for i, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
                # El módulo que explica el problema puede nombrarlo.
                if "castellano" in linea or self.LLAMADA.search(linea):
                    continue
                if self.PATRON.search(linea):
                    malos.append(f"{rel}:{i}: {linea.strip()[:90]}")
        self.assertEqual(malos, [], "quedó un «(s)» en texto que ve una persona:\n"
                                    + "\n".join(malos))


class ElInformeQueSeFirma(unittest.TestCase):
    """
    El .rtf es lo que sale del sistema y va a un legajo. Lo que diga mal, queda escrito.

    El defecto: para dar vuelta el separador decimal, el código hacía
    `f"...${n:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")` — sobre la
    FRASE ENTERA, no sobre el número. El informe salía diciendo «PEREZ ROMERO. Ana
    Laura» y «en la cámara B. entre 2023…». Apellidos mal escritos en un documento que
    se firma.
    """

    def setUp(self):
        import sqlite3
        import tempfile
        from ufil import confianza as cf, db
        from ufil.capa3_identidad import resolver
        from ufil.db import ahora
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = db.abrir(Path(self.tmp.name) / "t.sqlite")
        for sha, camara, ini, fin in (("aa", "A", "2023-03-01", "2023-08-31"),
                                      ("bb", "B", "2023-06-01", "2023-11-30")):
            self.cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,
                                                    paginas,ingerido_en)
                               VALUES (?,?,?,1,1,?)""",
                            (sha, f"/x/{sha}", f"{sha}.pdf", ahora()))
            self.cx.execute("""INSERT INTO pagina (sha256,nro,ancho_pt,alto_pt)
                               VALUES (?,1,595,842)""", (sha,))
            d = self.cx.execute(
                """INSERT INTO documento (sha256,orden,pagina_desde,pagina_hasta,tipo,
                                          perfil,camara)
                   VALUES (?,1,1,1,'contrato_obra','p',?)""", (sha, camara)).lastrowid
            for c, lit, norm in (("nombre", "PEREZ ROMERO, Ana Laura", "PEREZ ROMERO ANA LAURA"),
                                 ("documento", "28.456.712", "DNI:28456712"),
                                 ("fecha_inicio", ini, ini), ("fecha_fin", fin, fin),
                                 ("monto", "$ 4.850.000", "485000000")):
                cid = self.cx.execute(
                    """INSERT INTO campo (documento_id,nombre,valor_literal,pagina_nro,
                                          x0,y0,x1,y1,confianza,estado)
                       VALUES (?,?,?,1,10,10,90,30,0.96,?)""",
                    (d, c, lit, cf.AUTOMATICO_ALTA)).lastrowid
                self.cx.execute("""INSERT INTO normalizacion (campo_id,tipo,valor_norm)
                                   VALUES (?,?,?)""", (cid, c, norm))
        self.cx.commit()
        resolver(self.cx)

    def tearDown(self):
        self.cx.close(); self.tmp.cleanup()

    def _texto(self):
        import re
        import tempfile
        from ufil import capa7_export as c7
        ruta = c7.a_rtf(self.cx, Path(tempfile.mkdtemp()) / "i.rtf")
        crudo = ruta.read_text(encoding="cp1252")
        return re.sub(r"\\u(\d+)\?", lambda m: chr(int(m.group(1))), crudo)

    def test_el_apellido_conserva_su_coma(self):
        t = self._texto()
        self.assertIn("PEREZ ROMERO, Ana Laura", t,
                      "el apellido salió con punto: el reemplazo del separador decimal "
                      "se está aplicando a la frase y no al número")
        self.assertNotIn("PEREZ ROMERO. Ana Laura", t)

    def test_el_importe_lleva_coma_decimal_y_punto_de_miles(self):
        self.assertIn("$9.700.000,00", self._texto())

    def test_las_camaras_se_nombran(self):
        t = self._texto()
        self.assertIn("cámara de Diputados", t)
        self.assertIn("Senadores", t)
        self.assertNotIn("cámara A", t)

    def test_las_fechas_van_como_se_escriben_aca(self):
        t = self._texto()
        self.assertIn("01/03/2023", t)
        self.assertNotIn("2023-03-01", t)

    def test_la_cobertura_dice_de_que_documento_habla(self):
        self.assertIn("Contrato · campo", self._texto())


class LaInterfazNoMuestraNombresTecnicos(unittest.TestCase):
    """
    Quien revisa lee «Fecha de inicio», no `fecha_inicio`. Los nombres de campo de la
    base no se muestran crudos en ninguna pantalla.
    """

    def test_hay_rotulo_para_cada_campo_critico(self):
        js = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")
        from ufil import config
        for campo in config.CAMPOS_CRITICOS:
            self.assertRegex(js, rf"\b{campo}:\s*'",
                             f"«{campo}» no tiene rótulo legible en NOMBRE_CAMPO")

    def test_las_fechas_se_muestran_como_se_escriben_aca(self):
        """dd/mm/aaaa. La base guarda ISO porque ordena bien; la pantalla no."""
        js = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")
        self.assertIn("${m[3]}/${m[2]}/${m[1]}", js,
                      "fmtFecha dejó de dar vuelta la fecha")
        # Y ninguna columna de fecha sale cruda por `k:`, que muestra el ISO tal cual.
        for clave in ("inicio", "fin", "desde", "hasta", "emitida",
                      "primer_inicio", "ultimo_fin"):
            self.assertNotRegex(
                js, rf"k:\s*'{clave}'",
                f"la columna «{clave}» sale sin pasar por fmtFecha: muestra 2023-03-01")


class LasTablasGrandesSePuedenRecorrer(unittest.TestCase):
    """
    Medido con un legajo del tamaño de una causa de verdad —1.500 contratos y 3.047
    facturas—: la pantalla de facturas pintaba 3.047 filas, 51.085 nodos y 106.400 px
    de alto. Cien metros de página, sin forma de encontrar a nadie salvo desplazarse
    leyendo.

    Las cuatro tablas que crecen con el legajo van con buscador, orden por columna y
    render por tandas. Las que no crecen —superposiciones, fusiones— quedan como están:
    un buscador arriba de cuatro filas es ruido.
    """

    GRANDES = ["tabla-contratos", "tabla-comprobantes", "tabla-personas", "tabla-cruce"]

    def setUp(self):
        self.js = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")

    def test_las_cuatro_tablas_grandes_usan_el_buscador(self):
        for destino in self.GRANDES:
            self.assertIn(f"tablaBuscable($('#{destino}')", self.js,
                          f"«{destino}» volvió a pintar todas las filas de una")

    def test_ninguna_pinta_mas_de_una_tanda_de_entrada(self):
        m = re.search(r"const POR_TANDA = (\d+);", self.js)
        self.assertIsNotNone(m, "se perdió el tamaño de la tanda")
        self.assertLessEqual(int(m.group(1)), 300,
                             "la tanda es tan grande que volvemos al problema")

    def test_el_buscador_ignora_tildes_y_mayusculas(self):
        """
        Quien busca «peres» tiene que encontrar a Pérez: el nombre puede venir de un OCR
        y nadie sabe cómo quedó escrito.
        """
        self.assertIn("normalize('NFD')", self.js)
        self.assertIn(".toLowerCase()", self.js)

    def test_el_buscador_filtra_sobre_todas_las_filas(self):
        """
        Filtrar sobre las pintadas sería el mismo problema con otra cara: buscar un
        apellido y que aparezca o no según hasta dónde bajaste.
        """
        i = self.js.index("function tablaBuscable")
        cuerpo = self.js[i:i + 4000]
        self.assertIn("v = filas;", cuerpo,
                      "el filtro dejó de partir del total de filas")
        # y el corte por tanda va DESPUÉS de filtrar y ordenar
        self.assertLess(cuerpo.index("v = filas;"), cuerpo.index("slice(0, estado.mostradas)"))

    def test_lo_que_falta_se_ordena_al_final(self):
        """
        Ordenando por monto, los contratos sin monto legible no pueden colarse arriba
        como si valieran cero: no valen cero, no se sabe cuánto valen.
        """
        i = self.js.index("function tablaBuscable")
        cuerpo = self.js[i:i + 4000]
        self.assertIn("if (x == null) return 1;", cuerpo)


if __name__ == "__main__":
    unittest.main(verbosity=2)
