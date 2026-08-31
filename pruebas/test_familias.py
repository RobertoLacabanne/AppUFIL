"""
UN CONTRATO NO ES UNA FACTURA.

Los dos traen un nombre, un CUIT y un monto, y los dos salen del mismo PDF. Pero dicen
cosas distintas: el contrato dice cuánto se PACTÓ pagar, la factura dice cuánto se
COBRÓ. Sumarlos no da un total más completo — da un número que no corresponde a nada—,
y cuando la factura es el cobro de ese mismo contrato, cuenta la misma plata dos veces.

El defecto medido, con un contrato de $10.000 y su factura de $2.500:

    total firme: $12.500 · «2 contratos»

Ninguna de las dos cosas era cierta. La vista `v_contrato` no filtraba por tipo, así
que cualquier documento con un monto entraba al acumulado de lo contratado.

Lo que estas pruebas custodian:

  · lo contratado y lo facturado se cuentan por separado y nunca se suman;
  · una factura no puede inventar una superposición de contratos;
  · un tipo de documento que el sistema no conoce NO se acomoda en la familia más
    probable: queda afuera de todos los totales y se cuenta aparte, a la vista;
  · la lista de tipos vive en un solo lugar.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ufil import capa4_analisis as c4
from ufil import clasificacion as cl
from ufil import confianza as cf
from ufil import db
from ufil.db import ahora


class BaseMixta(unittest.TestCase):
    """Un legajo como los de verdad: contratos y facturas en la misma pila."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = db.abrir(Path(self.tmp.name) / "t.sqlite")

    def tearDown(self):
        self.cx.close(); self.tmp.cleanup()

    def _doc(self, sha, tipo, *, nombre=None, ident=None, monto=None,
             inicio=None, fin=None, estado=cf.AUTOMATICO_ALTA):
        self.cx.execute("""INSERT OR IGNORE INTO archivo
                           (sha256,ruta_original,nombre,bytes,paginas,ingerido_en)
                           VALUES (?,?,?,1,1,?)""",
                        (sha, f"/x/{sha}.pdf", f"{sha}.pdf", ahora()))
        self.cx.execute("""INSERT OR IGNORE INTO pagina (sha256,nro,ancho_pt,alto_pt)
                           VALUES (?,1,595,842)""", (sha,))
        d = self.cx.execute(
            """INSERT INTO documento (sha256,orden,pagina_desde,pagina_hasta,tipo,perfil)
               VALUES (?,1,1,1,?,'p')""", (sha, tipo)).lastrowid
        campos = [("nombre", nombre, nombre.upper() if nombre else None),
                  ("documento", ident, ident),
                  ("monto", f"${monto // 100}" if monto else None, str(monto) if monto else None),
                  ("fecha_inicio", inicio, inicio), ("fecha_fin", fin, fin)]
        for c, lit, norm in campos:
            if lit is None:
                continue
            cid = self.cx.execute(
                """INSERT INTO campo (documento_id,nombre,valor_literal,pagina_nro,
                                      x0,y0,x1,y1,confianza,estado)
                   VALUES (?,?,?,1,10,10,90,30,0.96,?)""", (d, c, lit, estado)).lastrowid
            self.cx.execute("""INSERT INTO normalizacion (campo_id,tipo,valor_norm)
                               VALUES (?,?,?)""", (cid, c, norm))
        self.cx.commit()
        return d

    def _totales(self):
        return c4.correr(self.cx, "10_totales")["filas"][0]


class LoContratadoNoSeSumaConLoFacturado(BaseMixta):

    def test_el_caso_medido(self):
        """Un contrato de $10.000 y su factura de $2.500. El total decía $12.500."""
        self._doc("aa", "contrato_obra", nombre="PEREZ, Ana", monto=1_000_000)
        self._doc("bb", "factura", nombre="PEREZ, Ana", monto=250_000)
        t = self._totales()

        self.assertEqual(t["total_firme_centavos"], 1_000_000,
                         "el total de lo contratado tiene adentro una factura")
        self.assertEqual(t["contratos_con_monto_firme"], 1,
                         "una factura se está contando como contrato")
        self.assertEqual(t["total_facturado_firme_centavos"], 250_000)
        self.assertEqual(t["comprobantes_con_monto_firme"], 1)

    def test_la_vista_de_contratos_no_trae_facturas(self):
        self._doc("aa", "contrato_obra", nombre="PEREZ, Ana", monto=1_000_000)
        self._doc("bb", "factura", nombre="PEREZ, Ana", monto=250_000)
        self._doc("cc", "recibo", nombre="PEREZ, Ana", monto=250_000)

        tipos = [r["tipo"] for r in self.cx.execute("SELECT tipo FROM v_contrato")]
        self.assertEqual(tipos, ["contrato_obra"])
        self.assertEqual(
            sorted(r["tipo"] for r in self.cx.execute("SELECT tipo FROM v_comprobante")),
            ["factura", "recibo"])

    def test_el_cruce_encuentra_las_facturas_del_contrato(self):
        """
        Lo que el caso necesita: cuánto se pactó y cuánto se cobró contra eso.

        El CUIL de la factura lleva adentro el DNI del contrato, así que se unen sin
        depender del nombre, que se escribe de mil maneras.
        """
        from ufil.capa3_identidad import resolver
        self._doc("c1", "contrato_obra", nombre="PEREZ, Ana", ident="DNI:28456712",
                  monto=1_000_000, inicio="2023-03-01", fin="2023-05-31")
        for i, f in enumerate(("2023-03-31", "2023-04-30", "2023-05-31"), 1):
            self._doc(f"f{i}", "factura", nombre="PEREZ ROMERO, Ana Laura",
                      ident="CUIL:27284567124", monto=1_000_000, inicio=f)
        # Una de talonario: el importe va a mano y no se lee.
        self._doc("f9", "factura", nombre="PEREZ ROMERO, Ana Laura",
                  ident="CUIL:27284567124", inicio="2023-06-30")
        resolver(self.cx)

        filas = c4.correr(self.cx, "09_facturas_contra_contrato")["filas"]
        self.assertEqual(len(filas), 1, "el cruce tiene que dar una fila por persona")
        f = filas[0]
        self.assertEqual(f["mensual_centavos"], 1_000_000)
        self.assertEqual(f["facturas"], 4)
        self.assertEqual(f["facturas_con_importe"], 3)
        self.assertEqual(f["facturas_a_mano"], 1,
                         "la factura de talonario tiene que contarse aparte: existe y "
                         "no se sabe por cuánto")
        self.assertEqual(f["facturado_legible_centavos"], 3_000_000)

    def test_dos_contratos_de_la_misma_persona_no_duplican_lo_facturado(self):
        """
        Salió en la pantalla, no en las pruebas: Ana tenía dos contratos y el cruce
        mostraba DOS filas, cada una con sus cinco facturas y sus $19.400.000 enteros.
        Quien sumara la columna concluía que se facturó el doble.

        La causa es que una factura no dice a qué contrato corresponde. Repartirlas por
        fecha sería adivinar —una fuera de todo período no es de ninguno, una dentro de
        dos períodos superpuestos no es de una—, así que la unidad del cruce es la
        persona.
        """
        from ufil.capa3_identidad import resolver
        self._doc("c1", "contrato_obra", nombre="PEREZ, Ana", ident="DNI:28456712",
                  monto=485_000_000, inicio="2023-03-01", fin="2023-08-31")
        self._doc("c2", "contrato_obra", nombre="PEREZ, Ana", ident="DNI:28456712",
                  monto=180_000_000, inicio="2023-06-01", fin="2023-11-30")
        for i, f in enumerate(("2023-03-31", "2023-04-30", "2023-05-31"), 1):
            self._doc(f"f{i}", "factura", nombre="PEREZ ROMERO, Ana Laura",
                      ident="CUIL:27284567124", monto=485_000_000, inicio=f)
        resolver(self.cx)

        filas = c4.correr(self.cx, "09_facturas_contra_contrato")["filas"]
        self.assertEqual(len(filas), 1,
                         "una persona con dos contratos sale dos veces y sus facturas "
                         "se cuentan dos veces")
        f = filas[0]
        self.assertEqual(f["contratos"], 2)
        self.assertEqual(f["mensual_centavos"], 665_000_000)
        self.assertEqual(f["facturas"], 3)
        self.assertEqual(f["facturado_legible_centavos"], 1_455_000_000)
        # Y lo que importa de verdad: la columna se puede sumar.
        self.assertEqual(sum(x["facturado_legible_centavos"] for x in filas), 1_455_000_000)

    def test_el_mensual_del_contrato_no_se_compara_con_la_facturacion(self):
        """
        `monto` es el importe MENSUAL del contrato; las facturas se acumulan. Ponerlos
        uno al lado del otro como si fueran comparables invita a la conclusión de que se
        facturó de más cuando no se sabe: son magnitudes distintas.

        El único comparable es `monto_total`, que el contrato dice aparte. Cuando no se
        pudo leer, se dice —no se rellena multiplicando mensual por plazo, que sería
        calcular un número que el papel dice o no dice—.
        """
        from ufil.capa3_identidad import resolver
        self._doc("c1", "contrato_obra", nombre="PEREZ, Ana", ident="DNI:28456712",
                  monto=485_000_000, inicio="2023-03-01", fin="2023-08-31")
        self._doc("f1", "factura", nombre="PEREZ, Ana", ident="CUIL:27284567124",
                  monto=485_000_000, inicio="2023-03-31")
        resolver(self.cx)

        f = c4.correr(self.cx, "09_facturas_contra_contrato")["filas"][0]
        self.assertEqual(f["mensual_centavos"], 485_000_000)
        self.assertEqual(f["contratado_centavos"], 0,
                         "sin monto total legible no hay total contratado que informar")
        self.assertEqual(f["contratos_sin_total_firme"], 1,
                         "tiene que decir cuántos contratos no traen el total")

    def test_cuando_el_total_esta_en_el_papel_se_usa_ese(self):
        from ufil.capa3_identidad import resolver
        doc = self._doc("c1", "contrato_obra", nombre="PEREZ, Ana", ident="DNI:28456712",
                        monto=485_000_000, inicio="2023-03-01", fin="2023-08-31")
        cid = self.cx.execute(
            """INSERT INTO campo (documento_id,nombre,valor_literal,pagina_nro,
                                  x0,y0,x1,y1,confianza,estado)
               VALUES (?,'monto_total','$ 29.100.000',1,10,10,90,30,0.96,?)""",
            (doc, cf.AUTOMATICO_ALTA)).lastrowid
        self.cx.execute("""INSERT INTO normalizacion (campo_id,tipo,valor_norm)
                           VALUES (?,'monto_total','2910000000')""", (cid,))
        self.cx.commit()
        resolver(self.cx)

        f = c4.correr(self.cx, "09_facturas_contra_contrato")["filas"][0]
        self.assertEqual(f["contratado_centavos"], 2_910_000_000)
        self.assertEqual(f["contratos_sin_total_firme"], 0)

    def test_una_factura_no_inventa_una_superposicion(self):
        """
        El error más caro posible: una superposición que no existe.

        Es una afirmación sobre una persona. Hoy no pasa porque las facturas no traen
        fecha de fin, pero eso es una propiedad del perfil y no una regla: si mañana
        alguien le da una fecha de fin a la factura, sin el filtro por tipo aparecen
        superposiciones falsas entre un contrato y el comprobante que lo cobra.
        """
        self._doc("c1", "contrato_obra", nombre="PEREZ, Ana", ident="DNI:28456712",
                  monto=1_000_000, inicio="2023-03-01", fin="2023-05-31")
        self._doc("f1", "factura", nombre="PEREZ, Ana", ident="DNI:28456712",
                  monto=1_000_000, inicio="2023-03-15", fin="2023-04-15")
        from ufil.capa3_identidad import resolver
        resolver(self.cx)

        self.assertEqual(c4.correr(self.cx, "01_superposicion")["n"], 0,
                         "una factura se cruzó con el contrato que la origina y salió "
                         "como superposición de contratos")


class LoQueNoSeSabeQueEsSeVe(BaseMixta):

    def test_un_tipo_desconocido_no_entra_a_ningun_total(self):
        self._doc("aa", "contrato_obra", nombre="PEREZ, Ana", monto=1_000_000)
        self._doc("zz", "vaya_a_saber_que_es", nombre="(?)", monto=999_999)
        t = self._totales()

        self.assertEqual(t["total_firme_centavos"], 1_000_000)
        self.assertEqual(t["total_facturado_firme_centavos"], 0)

    def test_pero_se_cuenta_para_que_no_desaparezca(self):
        """
        Un documento que no se suma en ningún lado y tampoco se cuenta en ningún lado,
        desapareció. Y este sistema existe para no perder documentos.
        """
        self._doc("aa", "contrato_obra", nombre="PEREZ, Ana", monto=1_000_000)
        self._doc("zz", "vaya_a_saber_que_es", nombre="(?)", monto=999_999)
        self.assertEqual(self._totales()["documentos_sin_familia"], 1)

    def test_familia_devuelve_none_en_vez_de_adivinar(self):
        self.assertIsNone(cl.familia("vaya_a_saber_que_es"))
        self.assertIsNone(cl.familia(None))
        self.assertEqual(cl.familia("contrato_obra"), cl.FAMILIA_CONTRATO)
        self.assertEqual(cl.familia("factura"), cl.FAMILIA_COMPROBANTE)
        self.assertEqual(cl.familia("decreto"), cl.FAMILIA_ACTO)

    def test_un_acto_administrativo_no_es_plata(self):
        """Un decreto que aprueba contratos no es plata contratada ni plata cobrada."""
        self._doc("dd", "decreto", nombre="(decreto 1234)", monto=500_000)
        t = self._totales()
        self.assertEqual(t["total_firme_centavos"], 0)
        self.assertEqual(t["total_facturado_firme_centavos"], 0)


class UnDatoRaroNoTiraAbajoTodoElLegajo(BaseMixta):
    """
    `resolver` recorre TODOS los documentos del legajo en una pasada. Una excepción a
    la mitad no cuesta ese documento: cuesta todos los que venían después, y el legajo
    queda sin ninguna identidad resuelta —sin personas, sin cruces, sin superposiciones—
    mientras la pantalla muestra los contratos como si estuviera todo bien.

    Pasó con un documento cuyo valor normalizado no tenía la forma «DNI:1234».
    """

    def test_un_documento_sin_forma_de_clave_no_corta_la_resolucion(self):
        from ufil.capa3_identidad import resolver
        self._doc("aa", "contrato_obra", nombre="PEREZ, Ana", ident="DNI:28456712")
        self._doc("bb", "decreto", nombre="(Decreto 1234/23)", ident="sin-forma-de-clave")
        self._doc("cc", "contrato_obra", nombre="GOMEZ, Luis", ident="DNI:31114567")

        r = resolver(self.cx)

        self.assertEqual(
            self.cx.execute("SELECT COUNT(*) FROM documento_persona").fetchone()[0], 3,
            "un valor con forma inesperada dejó documentos sin resolver")
        self.assertEqual(r["sin_clave"], 1,
                         "el documento raro tiene que quedar aislado y visible, no "
                         "colgado de la clave de otro")


class LaListaDeTiposViveEnUnSoloLugar(BaseMixta):
    """
    Si la lista de tipos estuviera escrita en el esquema Y en Python, el día que alguien
    agregue un tipo de contrato nuevo se va a acordar de uno y no del otro, y lo que se
    rompe en silencio es un total. Por eso el esquema la pide por nombre.
    """

    def test_el_esquema_no_tiene_la_lista_escrita_a_mano(self):
        from ufil import config
        crudo = config.ESQUEMA.read_text(encoding="utf-8")
        self.assertIn("{{TIPOS_CONTRATO}}", crudo,
                      "el esquema tiene que pedir los tipos, no escribirlos")
        for tipo in cl.TIPOS_CONTRATO:
            self.assertNotIn(f"'{tipo}'", crudo,
                             f"«{tipo}» está escrito a mano en el esquema: se va a "
                             f"separar de ufil/clasificacion.py")

    def test_no_queda_ninguna_marca_sin_sustituir(self):
        self.assertNotIn("{{", db.esquema_sql())

    def test_una_marca_desconocida_se_avisa_con_nombre(self):
        from unittest import mock
        with mock.patch.object(type(db.config.ESQUEMA), "read_text",
                               return_value="SELECT {{TIPOS_INVENTADOS}};"):
            with self.assertRaises(RuntimeError) as e:
                db.esquema_sql()
        self.assertIn("TIPOS_INVENTADOS", str(e.exception))

    def test_las_consultas_tambien_resuelven_las_marcas(self):
        sql = c4.correr(self.cx, "10_totales")["sql"]
        self.assertNotIn("{{", sql,
                         "la pantalla de consultas muestra una plantilla en vez del "
                         "SQL que se corrió")
        self.assertIn("'contrato_obra'", sql)


if __name__ == "__main__":
    unittest.main(verbosity=2)
