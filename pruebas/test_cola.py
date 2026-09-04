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


class NingunCampoSePideDosVeces(LaColaNoEscondeTrabajo):
    """
    «A veces aparece lo mismo para corregir más de una vez», dicho por quien la usa.

    La cola se pide por páginas y la página se pide por POSICIÓN (`desde`). La posición
    se corre sola cuando alguien decide un campo: el campo sale de la cola, la lista del
    servidor se acorta, y todo lo que venía atrás sube un lugar. Si la pantalla sigue
    pidiendo desde donde pidió antes, la fila que subió al hueco vuelve a llegar y hay
    que decidirla dos veces; y si descuenta de más, se saltea un campo que nadie va a
    ver nunca —que es peor, porque no se nota—.

    Estas pruebas recorren la cola entera decidiendo campos por el medio, que es lo que
    pasa de verdad, y verifican las dos cosas: ninguno repetido, ninguno perdido.
    """

    def _decidir(self, campo_id):
        aplicar(self.cx, campo_id, "verificar", None, "escribiente")

    def test_la_consulta_nunca_devuelve_dos_veces_el_mismo_campo(self):
        """Antes de paginar: la cola de una sola página no puede traer repetidos."""
        from ufil.servidor import api_cola
        self._muchos(120)
        r = api_cola(self.cx, limite=500)
        ids = [f["campo_id"] for f in r["filas"]]
        self.assertEqual(len(ids), len(set(ids)),
                         "la consulta de la cola devuelve el mismo campo más de una vez")

    def test_paginar_decidiendo_por_el_medio_no_repite_ni_pierde(self):
        """
        Se imita lo que hace la pantalla: pedir una página, decidir algunos campos de
        esa página, y pedir la siguiente desde la posición que corresponde. La cuenta
        que lleva la pantalla es `traidas` —cuántas entregó el servidor— menos una por
        cada campo que salió de la cola.
        """
        from ufil.servidor import api_cola
        self._muchos(120)                                  # 121 con el de setUp
        vistos, decididos, traidas, total = [], set(), 0, 121
        # Se para donde para la pantalla: cuando lo entregado alcanza el total. Si la
        # posición se lleva mal, acá es donde se pierden campos —la cola dice que no
        # queda nada y quedaba—, y por eso el corte tiene que ser el mismo.
        for vuelta in range(40):
            if traidas >= total:
                break
            r = api_cola(self.cx, desde=traidas, limite=20)
            if not r["filas"]:
                break
            total = r["total"]
            traidas += len(r["filas"])
            for f in r["filas"]:
                vistos.append(f["campo_id"])
            # Se deciden dos de cada página, uno del medio y el último.
            for f in (r["filas"][len(r["filas"]) // 2], r["filas"][-1]):
                if f["campo_id"] not in decididos:
                    self._decidir(f["campo_id"])
                    decididos.add(f["campo_id"])
                    traidas -= 1
        self.assertEqual(len(vistos), len(set(vistos)),
                         "un campo llegó dos veces mientras se paginaba y se decidía: "
                         f"repetidos {len(vistos) - len(set(vistos))}")
        # Y no se perdió ninguno. La pantalla dejó de pedir porque cree que ya tiene
        # la cola entera: entonces TODO lo que sigue esperando revisión tiene que
        # haber pasado por ella. Un campo que sigue en la cola y nunca se mostró es
        # trabajo que el sistema esconde —el botón de «traer más» ya no está— y nadie
        # se entera, que es peor que verlo dos veces.
        quedan = {f["campo_id"] for f in api_cola(self.cx, limite=500)["filas"]}
        escondidos = quedan - set(vistos)
        self.assertEqual(
            escondidos, set(),
            f"{len(escondidos)} campos siguen en la cola y nunca se mostraron: la "
            "pantalla dejó de pedir creyendo que ya los tenía")

    def test_la_pantalla_no_agrega_dos_veces_la_misma_fila(self):
        """
        Y aunque el servidor llegara a mandar una repetida —porque otra persona decidió
        algo mientras tanto—, la pantalla no la dibuja dos veces.
        """
        app = (Path(__file__).resolve().parent.parent
               / "ufil/web/app.js").read_text(encoding="utf-8")
        for aguja, queja in (
                ("const yaEstan = new Set(colaEstado.filas.map", "no se comparan los ids"),
                ("!yaEstan.has(String(x.campo_id))", "no se filtran las repetidas"),
                ("colaEstado.traidas += r.filas.length",
                 "la posición se lleva por las filas MOSTRADAS: una página entera de "
                 "repetidas volvería a pedir la misma página para siempre"),
                ("colaEstado.traidas = Math.max(0, (colaEstado.traidas || 0) - 1)",
                 "al sacar un campo de la cola no retrocede la posición: se saltea uno")):
            self.assertIn(aguja, app, queja)


class ElMismoPapelDosVecesSeAvisaMientrasSeRevisa(UnCampoEnLaCola):
    """
    El mismo contrato entrando dos veces desde archivos distintos ya lo detecta la
    consulta 08... mirando sólo los campos FIRMES, o sea después de revisar. Mientras
    se revisa —que es cuando alguien dice «esto ya lo vi»— no lo ve nadie, porque los
    valores que lo delatarían son justamente los que están esperando en la cola.

    Acá se avisa con los valores provisionales, con la misma definición: mismo
    contratado, mismo período y mismo importe. Es una SOSPECHA y así se dice: dos
    contratos con los mismos datos también pueden ser dos contratos reales, y el
    sistema no borra ni fusiona nada.
    """

    def _papel(self, sha, cuil, desde, hasta, monto, estado=None):
        """Un contrato completo, con sus campos y su normalización."""
        estado = estado or cf.PENDIENTE_BAJA
        self.cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,
                                                paginas,ingerido_en)
                           VALUES (?,?,?,1,1,?)""",
                        (sha, f"/x/{sha}.pdf", f"{sha}.pdf", ahora()))
        self.cx.execute("INSERT INTO pagina (sha256,nro,ancho_pt,alto_pt) VALUES (?,1,595,842)",
                        (sha,))
        d = self.cx.execute("""INSERT INTO documento (sha256,orden,pagina_desde,
                                                      pagina_hasta,tipo,perfil)
                               VALUES (?,1,1,1,'contrato_obra','p')""", (sha,)).lastrowid
        for nombre, literal, norm in (("documento", cuil, cuil),
                                      ("fecha_inicio", desde, desde),
                                      ("fecha_fin", hasta, hasta),
                                      ("monto", f"$ {monto}", str(monto))):
            c = self.cx.execute("""INSERT INTO campo (documento_id,nombre,valor_literal,
                                                      pagina_nro,x0,y0,x1,y1,confianza,estado)
                                   VALUES (?,?,?,1,10,10,90,30,0.4,?)""",
                                (d, nombre, literal, estado)).lastrowid
            self.cx.execute("INSERT INTO normalizacion (campo_id,tipo,valor_norm) VALUES (?,?,?)",
                            (c, nombre, norm))
        self.cx.commit()
        return d

    def test_avisa_cuando_los_cuatro_datos_coinciden(self):
        from ufil.servidor import api_cola
        a = self._papel("aa" * 32, "20-11111111-1", "2023-01-01", "2023-06-30", 210000)
        b = self._papel("bb" * 32, "20-11111111-1", "2023-01-01", "2023-06-30", 210000)
        filas = api_cola(self.cx, limite=500)["filas"]
        de_a = [f for f in filas if f["documento_id"] == a]
        self.assertTrue(de_a, "el documento no llegó a la cola")
        for f in de_a:
            aviso = f.get("mismo_papel") or {}
            self.assertEqual([o["documento_id"] for o in aviso.get("otros", [])], [b],
                             "no avisa que el mismo papel está cargado dos veces")
            self.assertTrue(aviso.get("seguro"),
                            "con los cuatro datos leídos y coincidiendo, el aviso no "
                            "tiene por qué andar con vueltas")
        # Y el aviso es recíproco: mirando el otro también tiene que decirlo.
        for f in [f for f in filas if f["documento_id"] == b]:
            self.assertEqual([o["documento_id"] for o in f["mismo_papel"]["otros"]], [a])

    def test_no_marca_a_quien_tiene_varios_contratos(self):
        """
        El campo «documento» de un contrato es el CUIL del contratado, no un número de
        contrato. Agrupar sólo por ahí marcaría como repetido al que tiene cinco
        contratos, que es exactamente lo que esta causa investiga: sería el sistema
        tapando el hallazgo con un cartel de error.
        """
        from ufil.servidor import api_cola
        self._papel("cc" * 32, "20-22222222-2", "2023-01-01", "2023-06-30", 210000)
        self._papel("dd" * 32, "20-22222222-2", "2023-07-01", "2023-12-31", 260000)
        for f in api_cola(self.cx, limite=500)["filas"]:
            self.assertFalse(f.get("mismo_papel"),
                             "marcó como papel repetido a dos contratos distintos de "
                             "la misma persona, que es el hallazgo de la causa")

    def test_con_el_importe_sin_leer_avisa_pero_no_afirma(self):
        """
        Es el caso NORMAL mientras se revisa: el importe es justo lo que está en la
        cola esperando. Requiriendo los cuatro datos, el aviso no aparecía nunca en el
        único momento en que sirve. Con tres, aparece —y dice qué falta comprobar.
        """
        from ufil.servidor import api_cola
        a = self._papel("ee" * 32, "20-33333333-3", "2023-01-01", "2023-06-30", 0)
        b = self._papel("ff" * 32, "20-33333333-3", "2023-01-01", "2023-06-30", 0)
        # Se les borra el importe a los dos, como si nadie lo hubiera podido leer.
        self.cx.execute("""DELETE FROM normalizacion WHERE campo_id IN
                             (SELECT id FROM campo WHERE nombre='monto'
                               AND documento_id IN (?,?))""", (a, b))
        self.cx.commit()
        avisos = [f for f in api_cola(self.cx, limite=500)["filas"]
                  if f["documento_id"] in (a, b) and f.get("mismo_papel")]
        self.assertTrue(avisos, "sin el importe leído dejó de avisar, que es justo "
                                "cuando hace falta: el importe está en la cola")
        for f in avisos:
            self.assertFalse(f["mismo_papel"]["seguro"],
                             "afirma que es el mismo papel sin haber comparado el "
                             "importe, que es lo único que lo distingue de dos "
                             "contratos que se pisan")

    def test_dos_contratos_que_se_pisan_no_son_un_papel_repetido(self):
        """
        Mismo contratado, mismo período, importes DISTINTOS: eso no es un papel
        cargado dos veces, es el hallazgo que esta causa busca. Marcarlo como error
        del sistema sería taparlo.
        """
        from ufil.servidor import api_cola
        a = self._papel("1a" * 32, "20-44444444-4", "2023-01-01", "2023-06-30", 210000)
        b = self._papel("1b" * 32, "20-44444444-4", "2023-01-01", "2023-06-30", 380000)
        for f in api_cola(self.cx, limite=500)["filas"]:
            if f["documento_id"] in (a, b):
                self.assertFalse(f.get("mismo_papel"),
                                 "llamó «papel repetido» a dos contratos que se pisan "
                                 "por importes distintos: eso es el hallazgo, no un error")

    def test_sin_datos_suficientes_no_inventa(self):
        """Con un solo campo leído no hay con qué comparar, y no se dice nada."""
        from ufil.servidor import api_cola
        for f in api_cola(self.cx, limite=500)["filas"]:
            self.assertFalse(f.get("mismo_papel"))

    def test_la_pantalla_lo_dice_como_sospecha_y_no_como_dato(self):
        """
        Va en el carril de interpretación —§5 del pliego—: dos contratos con los mismos
        datos también pueden ser dos contratos reales.
        """
        raiz = Path(__file__).resolve().parent.parent
        app = (raiz / "ufil/web/app.js").read_text(encoding="utf-8")
        css = (raiz / "ufil/web/estilo.css").read_text(encoding="utf-8")
        self.assertIn("puede ser el mismo papel cargado dos veces", app,
                      "el aviso afirma en vez de preguntar, o no está")
        self.assertIn("Si el importe también coincide", app,
                      "sin el importe leído el aviso tiene que decir qué falta "
                      "comprobar, no afirmar")
        import re
        cuerpo = re.search(r"\.mismo-papel\{([^{}]*)\}", css)
        self.assertIsNotNone(cuerpo, "el aviso no tiene tratamiento propio")
        self.assertIn("italic", cuerpo.group(1),
                      "una sospecha con el aspecto de un dato leído es lo que la "
                      "regla de los dos carriles existe para impedir")
