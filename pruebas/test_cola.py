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


class LaColaNoEscondeTrabajo(UnCampoEnLaCola):
    """
    El defecto medido: en un legajo con **3.892 campos esperando revisión**, la cola
    devolvía 400 y no lo decía. La pantalla mostraba «1 de 400»; alguien los revisaba
    todos y concluía que el legajo estaba terminado. **3.492 campos que nadie iba a ver
    nunca.**

    Un sistema que existe para que no se pierda trabajo no puede esconder trabajo.
    """

    def _muchos(self, n):
        """n campos esperando revisión, repartidos entre contratos y facturas."""
        from ufil.db import ahora
        for i in range(n):
            sha = f"{i:064x}"
            tipo = "contrato_obra" if i % 3 else "factura"
            self.cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,
                                                    paginas,ingerido_en)
                               VALUES (?,?,?,1,1,?)""",
                            (sha, f"/x/{sha}", f"{i:05d}.pdf", ahora()))
            self.cx.execute("""INSERT INTO pagina (sha256,nro,ancho_pt,alto_pt)
                               VALUES (?,1,595,842)""", (sha,))
            d = self.cx.execute(
                """INSERT INTO documento (sha256,orden,pagina_desde,pagina_hasta,tipo,
                                          perfil) VALUES (?,1,1,1,?,'p')""",
                (sha, tipo)).lastrowid
            self.cx.execute(
                """INSERT INTO campo (documento_id,nombre,valor_literal,pagina_nro,
                                      x0,y0,x1,y1,confianza,estado)
                   VALUES (?,'monto','$ 1.000',1,10,10,90,30,0.4,?)""",
                (d, cf.PENDIENTE_BAJA))
        self.cx.commit()

    def test_dice_cuantos_hay_de_verdad_aunque_mande_una_pagina(self):
        from ufil.servidor import api_cola
        self._muchos(950)                       # más el que trae setUp: 951

        r = api_cola(self.cx, limite=200)

        self.assertEqual(len(r["filas"]), 200, "la página tiene que ser una página")
        self.assertEqual(r["total"], 951,
                         "el total tiene que ser el de la cola, no el de la página: "
                         "si dice 200, quien revise 200 va a creer que terminó")
        self.assertEqual(r["total_sin_filtro"], 951)

    def test_se_puede_llegar_hasta_el_final(self):
        """Paginar sirve si se puede seguir. Un tope disfrazado sigue siendo un tope."""
        from ufil.servidor import api_cola
        self._muchos(450)
        vistos, desde = set(), 0
        while True:
            r = api_cola(self.cx, desde=desde, limite=200)
            if not r["filas"]:
                break
            vistos.update(f["campo_id"] for f in r["filas"])
            desde += len(r["filas"])
        self.assertEqual(len(vistos), 451,
                         "no se llega a ver la cola entera paginando")

    def test_el_filtro_filtra_la_cola_entera_y_no_la_pagina(self):
        """
        Filtrado en la pantalla, el filtro corría sobre las 400 filas que habían
        llegado. Con 2.377 comprobantes esperando y un tope de 400, filtrar por
        «facturas» mostraba las que hubiera entre las primeras 400 — un número que no
        significa nada.
        """
        from ufil.servidor import api_cola
        self._muchos(950)

        entero = api_cola(self.cx, limite=200)
        facturas = api_cola(self.cx, filtros={"familia": "comprobante"}, limite=200)

        # Las facturas son una de cada tres, así que hay bastantes más de 200.
        self.assertGreater(facturas["total"], 200)
        self.assertLess(facturas["total"], entero["total"])
        self.assertEqual(facturas["total_sin_filtro"], entero["total"],
                         "el filtro tiene que decir también sobre cuánto filtró")
        self.assertTrue(all(f["familia"] == "comprobante" for f in facturas["filas"]))

    def test_las_opciones_del_filtro_cuentan_la_cola_entera(self):
        """
        Contadas sobre la página, ofrecer «facturas» dependía de que hubiera alguna
        entre las 200 que llegaron. Un filtro que aparece y desaparece según la página
        es un filtro que miente.
        """
        from ufil.servidor import api_cola
        self._muchos(950)
        r = api_cola(self.cx, limite=200)
        por_familia = {o["valor"]: o["n"] for o in r["opciones"]["familia"]}
        self.assertEqual(sum(por_familia.values()), r["total_sin_filtro"])
        self.assertGreater(por_familia["comprobante"], 200)


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


class RevisarNoPuedeCostarUnaEsperaPorCampo(UnCampoEnLaCola):
    """
    La interfaz refresca las cuentas al abrir cualquier pantalla y DESPUÉS DE CADA
    DECISIÓN de la cola. Para eso pedía `/api/panel` entero, que corre nueve consultas
    de análisis —superposiciones, cruces, cobertura, totales—. Medido en un legajo de
    1.500 contratos: 950 ms. Revisar cien campos costaba cien segundos de espera
    repartidos en pedacitos, que es la clase de lentitud que nadie reporta y todos
    sufren.
    """

    def test_las_cuentas_traen_lo_que_la_barra_necesita(self):
        from ufil.servidor import api_cuentas
        c = api_cuentas(self.cx)
        for clave in ("legajo", "hay_legajos", "documentos", "a_revisar", "fusiones",
                      "afuera", "lote", "demostracion"):
            self.assertIn(clave, c, f"la barra usa «{clave}» y las cuentas no lo traen")

    def test_las_cuentas_no_corren_las_consultas_de_analisis(self):
        """
        Si alguna vez vuelven a entrar acá, esto deja de ser barato y nadie se entera
        hasta que el legajo crece. Se cuenta cuántas consultas SQL hace.
        """
        from ufil.servidor import api_cuentas
        consultas = []
        # `set_trace_callback` es la forma que trae SQLite de mirar qué se ejecuta.
        # `Connection.execute` no se puede sustituir: es de sólo lectura.
        self.cx.set_trace_callback(lambda sql: consultas.append(" ".join(sql.split())[:90]))
        try:
            api_cuentas(self.cx)
        finally:
            self.cx.set_trace_callback(None)

        pesadas = [c for c in consultas if "v_contrato" in c or "v_documento_todo" in c
                   or "v_comprobante" in c]
        self.assertEqual(pesadas, [],
                         "las cuentas empezaron a tocar las vistas de análisis: "
                         "vuelven a costar casi un segundo en un legajo grande")
        self.assertLessEqual(len(consultas), 12,
                             f"las cuentas hacen {len(consultas)} consultas; eran cinco")

    def test_la_pantalla_pide_las_cuentas_y_no_el_panel(self):
        js = (Path(__file__).resolve().parent.parent / "ufil/web/app.js").read_text(encoding="utf-8")
        i = js.index("async function refrescarCuentas()")
        cuerpo = js[i:i + 900]
        self.assertIn("'/api/cuentas'", cuerpo)
        self.assertNotIn("'/api/panel'", cuerpo,
                         "volvió a pedir el panel entero en cada cambio de pantalla")

    def test_los_totales_recorren_la_vista_una_sola_vez(self):
        """
        `v_documento_todo` es un GROUP BY sobre todos los documentos unidos a todos los
        campos. Nombrarla cuatro veces sin materializar la arma cuatro veces: medido,
        220 ms de los 397 que tardaba la consulta.
        """
        from ufil import config
        sql = (config.CONSULTAS / "10_totales.sql").read_text(encoding="utf-8")
        self.assertIn("AS MATERIALIZED", sql,
                      "los totales volvieron a recorrer la misma vista una vez por "
                      "subconsulta")
        self.assertLessEqual(sql.count("FROM v_documento_todo"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class ElAvanceDeLaColaNoMiente(unittest.TestCase):
    """
    Cuánto se lleva hecho, y de quién es.

    «1 de 6» dice dónde está el cursor y no dice nada de la tarea. En una cola de tres
    mil campos —el caso real de un lote de la Legislatura— alguien revisa cuarenta
    minutos, ve «1 de 2.847» y no tiene forma de saber si avanzó.

    La barra de avance se apoya en una propiedad que hay que sostener: el universo
    —lo que espera MÁS lo que ya se decidió— no puede moverse solo. Un campo revisado
    sale de la cola y entra en `revision_humana`; si alguien deshace la decisión, la
    fila se borra y el campo vuelve a la cola. Los dos números tienen que moverse
    juntos y en sentidos opuestos, siempre.

    Si esa propiedad se rompe, la barra retrocede o salta sin que nadie haya hecho
    nada, y una barra que hace eso deja de creerse a la semana.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cx = db.abrir(Path(self.tmp.name) / "t.sqlite")
        self.cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,
                                                paginas,ingerido_en)
                           VALUES ('aa','/x/aa.pdf','contrato-12.pdf',1,1,?)""", (ahora(),))
        self.cx.execute("""INSERT INTO pagina (sha256,nro,ancho_pt,alto_pt)
                           VALUES ('aa',1,595,842)""")
        self.doc = self.cx.execute(
            """INSERT INTO documento (sha256,orden,pagina_desde,pagina_hasta,tipo,perfil)
               VALUES ('aa',1,1,1,'contrato_obra','p')""").lastrowid
        self.campos = [self.cx.execute(
            """INSERT INTO campo (documento_id,nombre,valor_literal,pagina_nro,
                                  x0,y0,x1,y1,confianza,estado)
               VALUES (?,?,'$ 4.850.000',1,60,120,300,145,0.42,?)""",
            (self.doc, n, cf.PENDIENTE_BAJA)).lastrowid
            for n in ("monto", "contratado_nombre", "fecha_desde")]
        self.cx.commit()

    def _cola(self):
        from ufil import servidor
        return servidor.api_cola(self.cx)

    def _universo(self, r):
        return r["revisados"] + r["total_sin_filtro"]

    def test_el_universo_no_se_mueve_solo(self):
        antes = self._cola()
        self.assertEqual(antes["revisados"], 0)
        self.assertEqual(self._universo(antes), 3)

        aplicar(self.cx, self.campos[0], "verificar", None, "ana")
        medio = self._cola()
        self.assertEqual(medio["revisados"], 1)
        self.assertEqual(medio["total_sin_filtro"], 2)
        self.assertEqual(self._universo(medio), 3, "el universo saltó al revisar")

        # Deshacer devuelve el campo a la cola. Si el universo cambiara acá, la barra
        # retrocedería sola y quien la mira concluiría que perdió trabajo.
        aplicar(self.cx, self.campos[0], "revertir", None, "ana")
        vuelta = self._cola()
        self.assertEqual(vuelta["revisados"], 0)
        self.assertEqual(vuelta["total_sin_filtro"], 3)
        self.assertEqual(self._universo(vuelta), 3, "el universo cambió al deshacer")

    def test_dice_de_quien_es_cada_revision(self):
        """Varios de la fiscalía sobre la misma causa: el avance es del equipo."""
        aplicar(self.cx, self.campos[0], "verificar", None, "ana")
        aplicar(self.cx, self.campos[1], "verificar", None, "bruno")
        aplicar(self.cx, self.campos[2], "verificar", None, "bruno")
        r = self._cola()
        self.assertEqual(r["revisados"], 3)
        # Ordenado por cantidad: quien más hizo, primero.
        self.assertEqual([(x["quien"], x["n"]) for x in r["revisores"]],
                         [("bruno", 2), ("ana", 1)])

    def test_al_deshacer_baja_la_cuenta_de_quien_lo_habia_hecho(self):
        """
        Deshacer BORRA la fila de `revision_humana` —la auditoría queda igual, que es
        append-only— así que la persona tiene que dejar de figurar. Si no, el reparto
        acumula trabajo que ya no existe y la suma de los revisores deja de dar el
        total.
        """
        aplicar(self.cx, self.campos[0], "verificar", None, "ana")
        aplicar(self.cx, self.campos[1], "verificar", None, "ana")
        aplicar(self.cx, self.campos[0], "revertir", None, "ana")
        r = self._cola()
        self.assertEqual(r["revisados"], 1)
        self.assertEqual([(x["quien"], x["n"]) for x in r["revisores"]], [("ana", 1)])
        self.assertEqual(sum(x["n"] for x in r["revisores"]), r["revisados"],
                         "el reparto por persona no suma el total")
