"""
LA COLA DE REVISIÓN: dos personas, un campo, y el rastro de lo que pasó.

La cola es donde el sistema y las personas se encuentran. Todo lo que el sistema no
pudo sostener solo termina acá, y lo que se decide acá es lo único del legajo que no se
puede volver a generar a partir de los originales.

Dos cosas que tienen que ser ciertas:

  · Dos revisores sobre el mismo legajo NO se pisan en silencio. Sin bloqueo optimista
    gana el último en apretar, que no es necesariamente el que tenía razón, y el primero
    nunca se entera de que su decisión se perdió.

  · Deshacer NO borra. La auditoría es append-only: revertir agrega una línea que dice
    que se revirtió, quién y cuándo. Un rastro que se puede editar no es un rastro.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ufil import capa4_analisis as c4
from ufil import confianza as cf
from ufil import db
from ufil.aplicar_revision import DecisionDesactualizada, aplicar
from ufil.db import ahora


class UnCampoEnLaCola(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cx = db.abrir(Path(self.tmp.name) / "t.sqlite")
        self.cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,
                                                paginas,ingerido_en)
                           VALUES ('aa','/x/aa.pdf','contrato-12.pdf',1,1,?)""", (ahora(),))
        self.cx.execute("""INSERT INTO pagina (sha256,nro,ancho_pt,alto_pt)
                           VALUES ('aa',1,595,842)""")
        self.doc = self.cx.execute(
            """INSERT INTO documento (sha256,orden,pagina_desde,pagina_hasta,tipo,perfil)
               VALUES ('aa',1,1,1,'contrato_obra','p')""").lastrowid
        self.campo = self.cx.execute(
            """INSERT INTO campo (documento_id,nombre,valor_literal,pagina_nro,
                                  x0,y0,x1,y1,confianza,estado)
               VALUES (?,'monto','$ 4.850.000',1,60,120,300,145,0.42,?)""",
            (self.doc, cf.PENDIENTE_BAJA)).lastrowid
        self.cx.execute("""INSERT INTO normalizacion (campo_id,tipo,valor_norm)
                           VALUES (?,'monto','485000000')""", (self.campo,))
        self.cx.commit()

    def tearDown(self):
        self.cx.close(); self.tmp.cleanup()

    def _estado(self):
        return self.cx.execute("SELECT estado, valor_literal FROM campo WHERE id=?",
                               (self.campo,)).fetchone()

    def _rastro(self):
        return [dict(r) for r in self.cx.execute(
            "SELECT * FROM auditoria ORDER BY id")]


class DosRevisoresNoSePisan(UnCampoEnLaCola):

    def test_el_segundo_se_entera(self):
        """
        Los dos abrieron la cola y vieron el campo «pendiente». Ana decide primero.
        Cuando Luis aprieta, su decisión NO se aplica: se le avisa qué pasó.
        """
        visto = self._estado()["estado"]

        aplicar(self.cx, self.campo, "verificar", None, "perez.ana",
                estado_esperado=visto)

        with self.assertRaises(DecisionDesactualizada) as e:
            aplicar(self.cx, self.campo, "corregir", "$ 9.999.999", "gomez.luis",
                    estado_esperado=visto)

        self.assertEqual(self._estado()["valor_literal"], "$ 4.850.000",
                         "la segunda decisión pisó a la primera")
        # Y el aviso tiene que servir para entender qué pasó, no sólo para frenar.
        mensaje = str(e.exception)
        self.assertIn("perez.ana", mensaje, "no dice quién lo decidió")
        self.assertIn("Verificado", mensaje, "no dice cómo quedó")

    def test_sin_estado_esperado_no_se_chequea_nada(self):
        """
        La línea de comandos y los reprocesos llaman sin `estado_esperado`. Ahí no hay
        nadie mirando una pantalla vieja, así que no hay nada que chequear.
        """
        aplicar(self.cx, self.campo, "verificar", None, "perez.ana")
        aplicar(self.cx, self.campo, "corregir", "$ 5.000.000", "gomez.luis")
        self.assertEqual(self._estado()["valor_literal"], "$ 5.000.000")

    def test_el_que_llega_al_dia_si_puede_decidir(self):
        """Enterarse no es quedar bloqueado: con el estado actual, la decisión entra."""
        aplicar(self.cx, self.campo, "verificar", None, "perez.ana",
                estado_esperado=cf.PENDIENTE_BAJA)
        aplicar(self.cx, self.campo, "corregir", "$ 9.999.999", "gomez.luis",
                estado_esperado=cf.VERIFICADO)
        self.assertEqual(self._estado()["valor_literal"], "$ 9.999.999")


class DeshacerNoBorra(UnCampoEnLaCola):

    def test_revertir_agrega_una_linea_en_vez_de_sacar_la_anterior(self):
        aplicar(self.cx, self.campo, "corregir", "$ 5.000.000", "perez.ana")
        aplicar(self.cx, self.campo, "revertir", None, "perez.ana",
                observacion="deshecho desde la cola")

        r = self._rastro()
        self.assertEqual([x["accion"] for x in r], ["corregir", "revertir"],
                         "deshacer borró la decisión anterior en vez de anotarse")
        self.assertEqual(r[0]["valor_nuevo"], "$ 5.000.000",
                         "la decisión original tiene que seguir legible en el rastro")
        self.assertEqual(r[1]["observacion"], "deshecho desde la cola")

    def test_el_campo_vuelve_a_la_cola(self):
        antes = c4.correr(self.cx, "07_cola_revision")["n"]
        aplicar(self.cx, self.campo, "verificar", None, "perez.ana")
        self.assertEqual(c4.correr(self.cx, "07_cola_revision")["n"], antes - 1)
        aplicar(self.cx, self.campo, "revertir", None, "perez.ana")
        self.assertEqual(c4.correr(self.cx, "07_cola_revision")["n"], antes,
                         "deshacer no devolvió el campo a la cola")

    def test_el_valor_original_del_ocr_sobrevive_a_todo(self):
        """
        Corregir a mano no puede tapar lo que había leído el sistema: si mañana hay que
        explicar de dónde salió un número, hace falta lo que decía el papel según el
        OCR y lo que puso la persona.
        """
        aplicar(self.cx, self.campo, "corregir", "$ 5.000.000", "perez.ana")
        c = self.cx.execute("SELECT valor_auto, valor_literal FROM campo WHERE id=?",
                            (self.campo,)).fetchone()
        self.assertEqual(c["valor_auto"], "$ 4.850.000",
                         "se perdió lo que había leído el sistema")
        self.assertEqual(c["valor_literal"], "$ 5.000.000")


class ElRastroSeSeparaPorDocumento(UnCampoEnLaCola):
    """
    Un PDF puede traer varios contratos, cada uno con su «monto». El rastro va por
    archivo + orden + campo: sin el orden, el historial de un contrato mostraría también
    las decisiones tomadas sobre el de al lado.
    """

    def test_dos_documentos_del_mismo_archivo_no_mezclan_su_rastro(self):
        from ufil.servidor import api_auditoria
        otro = self.cx.execute(
            """INSERT INTO documento (sha256,orden,pagina_desde,pagina_hasta,tipo,perfil)
               VALUES ('aa',2,2,2,'contrato_obra','p')""").lastrowid
        campo2 = self.cx.execute(
            """INSERT INTO campo (documento_id,nombre,valor_literal,pagina_nro,
                                  x0,y0,x1,y1,confianza,estado)
               VALUES (?,'monto','$ 1.000.000',2,60,120,300,145,0.44,?)""",
            (otro, cf.PENDIENTE_BAJA)).lastrowid
        self.cx.commit()

        aplicar(self.cx, self.campo, "corregir", "$ 5.000.000", "perez.ana")
        aplicar(self.cx, campo2, "corregir", "$ 2.000.000", "gomez.luis")

        uno = api_auditoria(self.cx, self.campo)
        dos = api_auditoria(self.cx, campo2)
        self.assertEqual([x["valor_nuevo"] for x in uno], ["$ 5.000.000"])
        self.assertEqual([x["valor_nuevo"] for x in dos], ["$ 2.000.000"])


class LaColaSePuedeFiltrar(UnCampoEnLaCola):
    """Revisar montos de contratos y montos de facturas son dos tareas distintas."""

    def test_cada_fila_dice_de_qué_familia_es(self):
        self.cx.execute("""INSERT INTO documento (sha256,orden,pagina_desde,pagina_hasta,
                                                  tipo,perfil)
                           VALUES ('aa',2,1,1,'factura','factura_electronica')""")
        doc2 = self.cx.execute("SELECT id FROM documento WHERE orden=2").fetchone()["id"]
        self.cx.execute(
            """INSERT INTO campo (documento_id,nombre,valor_literal,pagina_nro,
                                  x0,y0,x1,y1,confianza,estado)
               VALUES (?,'monto','$ 1.000',1,10,10,90,30,0.4,?)""", (doc2, cf.PENDIENTE_BAJA))
        self.cx.commit()

        por_familia = {}
        for f in c4.correr(self.cx, "07_cola_revision")["filas"]:
            por_familia.setdefault(f["familia"], []).append(f["campo"])
        self.assertEqual(sorted(por_familia), ["comprobante", "contrato"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
