"""
VARIAS PERSONAS SOBRE LA MISMA CAUSA.

En la fiscalía esto lo trabaja un equipo, todos contra la misma base. Lo que verifica
que funcione no es que la interfaz lo muestre lindo: es que dos personas escribiendo al
mismo tiempo no se pisen y no pierdan trabajo.

Tres cosas:
  · las escrituras simultáneas no fallan;
  · decidir un campo que otro ya decidió se rechaza, y el mensaje dice QUIÉN lo tomó;
  · cada decisión queda con nombre, y se puede preguntar quién hizo qué.
"""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ufil import config, confianza as cf, db, legajos
from ufil.aplicar_revision import DecisionDesactualizada, aplicar
from ufil.db import ahora
from ufil.servidor import api_actividad


class ElEquipoTrabajaJunto(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._datos = config.DATOS
        config.DATOS = Path(self.tmp.name)
        config.activar_legajo(None)
        self.l = legajos.crear("70.200", "Contratos Legislatura")
        config.activar_legajo(self.l.slug)
        cx = db.abrir()
        cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,paginas,
                                           ingerido_en)
                      VALUES ('a1','/x.pdf','contrato_A_0001.pdf',10,1,?)""", (ahora(),))
        for i in range(60):
            cx.execute("""INSERT INTO documento (sha256,orden,pagina_desde,pagina_hasta,
                                                 tipo,perfil)
                          VALUES ('a1',?,1,1,'contrato_obra',
                                  'contrato_obra_legislatura')""", (i + 1,))
            cx.execute("""INSERT INTO campo (documento_id,nombre,valor_literal,pagina_nro,
                                             x0,y0,x1,y1,confianza,estado)
                          VALUES (?,'monto',?,1,1,1,2,2,0.4,?)""",
                       (i + 1, f"$ {i}", cf.PENDIENTE_BAJA))
        cx.commit()
        cx.close()

    def tearDown(self):
        config.activar_legajo(None)
        config.DATOS = self._datos
        self.tmp.cleanup()

    # ── Que no se pisen ────────────────────────────────────────────────────
    def test_tres_personas_escribiendo_a_la_vez_no_pierden_ninguna_decision(self):
        """
        SQLite serializa a los que escriben. Sin espera configurada, el segundo recibe
        «database is locked» y la decisión se pierde: la persona la dio por tomada y no
        quedó. `db.conectar` abre con 30 s de espera, así que hacen cola.
        """
        fallos: list[str] = []
        slug = self.l.slug

        def persona(nombre: str, desde: int):
            config.activar_legajo(slug)          # cada hilo tiene el suyo
            cx = db.abrir()
            try:
                for i in range(desde, desde + 20):
                    try:
                        aplicar(cx, i + 1, "verificar", None, nombre)
                    except Exception as e:                    # noqa: BLE001
                        fallos.append(f"{nombre} en el campo {i+1}: {type(e).__name__}: {e}")
            finally:
                cx.close()

        hilos = [threading.Thread(target=persona, args=(n, d))
                 for n, d in (("badano.g", 0), ("ramirez.j", 20), ("lacabanne.r", 40))]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()

        self.assertEqual(fallos, [], "\n".join(fallos[:5]))
        config.activar_legajo(slug)
        cx = db.abrir()
        n = cx.execute("SELECT COUNT(*) FROM campo WHERE estado=?",
                       (cf.VERIFICADO,)).fetchone()[0]
        cx.close()
        self.assertEqual(n, 60, "se perdieron decisiones escribiendo en paralelo")

    def test_decidir_lo_que_otro_ya_decidio_se_rechaza_y_dice_quien(self):
        """
        Dos personas abren la cola con el mismo campo a la vista. La primera decide. La
        segunda tiene la pantalla vieja y decide encima.

        Sin este control, la segunda pisa a la primera en silencio y en la auditoría
        queda como si nadie hubiera dudado. Y el mensaje tiene que decir el nombre: «el
        campo cambió» obliga a ir a buscar a quién preguntarle.
        """
        cx = db.abrir()
        try:
            aplicar(cx, 1, "verificar", None, "badano.g")
            with self.assertRaises(DecisionDesactualizada) as e:
                aplicar(cx, 1, "ilegible", None, "ramirez.j",
                        estado_esperado=cf.PENDIENTE_BAJA)
            self.assertIn("badano.g", str(e.exception),
                          "no dice quién tomó el campo, y hay que salir a preguntar")
        finally:
            cx.close()

    def test_sin_nombre_no_se_guarda_ninguna_decision(self):
        """Una decisión sin autor no sirve para firmar nada."""
        cx = db.abrir()
        try:
            for vacio in ("", "   ", None):
                with self.assertRaises(ValueError):
                    aplicar(cx, 2, "verificar", None, vacio)
        finally:
            cx.close()

    # ── Quién hizo qué ─────────────────────────────────────────────────────
    def test_la_actividad_dice_cuanto_llevo_hecho_cada_uno(self):
        cx = db.abrir()
        try:
            for i in range(5):
                aplicar(cx, i + 1, "verificar", None, "badano.g")
            for i in range(5, 8):
                aplicar(cx, i + 1, "ilegible", None, "ramirez.j")

            a = api_actividad(cx)
            self.assertEqual(a["total"], 8)
            por_quien = {q["quien"]: q["decisiones"] for q in a["quienes"]}
            self.assertEqual(por_quien, {"badano.g": 5, "ramirez.j": 3})
            # Ordenado por quién hizo más: es lo que se mira primero.
            self.assertEqual(a["quienes"][0]["quien"], "badano.g")

            # Lo último, de lo más reciente a lo más viejo, con el archivo para ir al folio.
            self.assertEqual(a["ultimas"][0]["quien"], "ramirez.j")
            self.assertEqual(a["ultimas"][0]["archivo"], "contrato_A_0001.pdf")
            self.assertIsNotNone(a["ultimas"][0]["documento_id"],
                                 "sin el documento no se puede ir a mirar el folio")
        finally:
            cx.close()

    def test_lo_ultimo_es_lo_ultimo_aunque_sea_todo_del_mismo_segundo(self):
        """
        Revisando en serio se toman varias decisiones por segundo, y `cuando` guarda
        segundos. Ordenando sólo por fecha, ocho decisiones del mismo segundo salen en
        orden arbitrario y «lo último que se decidió» deja de ser lo último.

        `auditoria.id` es autoincremental: ordena exacto siempre. Esta prueba falla si
        se saca ese desempate.
        """
        cx = db.abrir()
        try:
            for i in range(6):
                aplicar(cx, i + 1, "verificar", None, "badano.g")
            a = api_actividad(cx)
            # `verificar` conserva el literal que ya tenía el campo: los seis campos se
            # cargaron como «$ 0» … «$ 5» en setUp. De la más nueva a la más vieja.
            self.assertEqual([u["valor"] for u in a["ultimas"][:6]],
                             [f"$ {i}" for i in (5, 4, 3, 2, 1, 0)],
                             "«lo último que se decidió» no está en orden")
        finally:
            cx.close()

    def test_el_orden_lo_manda_la_secuencia_real_y_no_el_reloj(self):
        """
        `auditoria.id` es autoincremental: es el orden en que las cosas pasaron de
        verdad. `cuando` es lo que decía el reloj, con resolución de segundos y sujeto
        a que la máquina se ajuste con NTP y salte para atrás.

        Se fabrica la discrepancia: tres decisiones consecutivas, y a la del medio se
        le pone una fecha vieja. Ordenando por reloj, esa se va al fondo y el rastro
        miente sobre en qué orden se decidió. Ordenando por secuencia, no.

        Sin esta prueba el defecto no se ve: con fechas iguales SQLite suele devolver
        las filas en un orden que coincide con el correcto, y la prueba pasa por
        casualidad. Pasó — la primera versión de esto no detectaba la mutación.
        """
        cx = db.abrir()
        try:
            for i in range(3):
                aplicar(cx, i + 1, "verificar", None, "badano.g")
            ids = [r[0] for r in cx.execute("SELECT id FROM auditoria ORDER BY id")]
            self.assertEqual(len(ids), 3)
            cx.execute("UPDATE auditoria SET cuando='2020-01-01T00:00:00+00:00' WHERE id=?",
                       (ids[1],))
            cx.commit()

            devueltos = [u["id"] for u in api_actividad(cx)["ultimas"]]
            self.assertEqual(devueltos, list(reversed(ids)),
                             "el rastro se ordena por el reloj y no por el orden en "
                             "que se decidió")
        finally:
            cx.close()

    def test_deshacer_tambien_queda_con_nombre(self):
        """
        La auditoría es append-only: deshacer no borra la decisión anterior, agrega una
        línea que dice que se revirtió y quién. Si no quedara registrado, alguien podría
        deshacer el trabajo de otro sin dejar rastro.
        """
        cx = db.abrir()
        try:
            aplicar(cx, 1, "verificar", None, "badano.g")
            aplicar(cx, 1, "revertir", None, "ramirez.j")
            a = api_actividad(cx)
            self.assertEqual(a["ultimas"][0]["quien"], "ramirez.j")
            self.assertEqual(a["ultimas"][0]["accion"], "revertir")
        finally:
            cx.close()


if __name__ == "__main__":
    unittest.main()
