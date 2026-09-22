"""
Aceptación del incremento 7: una contratación entera, de los PDF a los hallazgos.

Sólo por HTTP, contra la API de docs/contrataciones-y-precios.md §9, y con el resultado
esperado escrito ANTES de que existiera el backend (§11). No mira cómo está hecho: sube
doce PDF sintéticos como los subiría una persona, los procesa, actualiza el análisis y
pregunta. Si un día la implementación cambia entera, esta prueba no debería enterarse.

Se saltea mientras no existan los módulos del backend del incremento.
"""
from __future__ import annotations

import http.client
import importlib.util
import json
import sys
import time
import unittest
from pathlib import Path
from urllib.parse import quote

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from pruebas import test_nucleo_web as soporte
from pruebas.corpus_contratacion import EXPEDIENTE, PROVEEDORES, generar
from ufil import comparabilidad as cp

HAY_BACKEND = all(importlib.util.find_spec(f"ufil.{m}")
                  for m in ("renglones", "contrataciones", "precios", "hallazgos"))


@unittest.skipUnless(HAY_BACKEND, "todavía no está el backend del incremento 7")
class UnaContratacionDePuntaAPunta(unittest.TestCase):
    def setUp(self):
        soporte.NucleoPorHTTP.setUp(self)
        # Los originales se guardan sin permiso de escritura —son el papel— y en Windows
        # eso impide borrar la carpeta temporal al terminar. Se devuelve el permiso antes
        # de que corra la limpieza (las limpiezas corren en orden inverso).
        self.addCleanup(self._devolver_permisos)

    def _devolver_permisos(self):
        for ruta in self.temporal.rglob("*"):
            if ruta.is_file():
                ruta.chmod(0o666)

    restaurar_config = soporte.NucleoPorHTTP.restaurar_config
    restaurar_servidor = soporte.NucleoPorHTTP.restaurar_servidor
    cerrar = soporte.NucleoPorHTTP.cerrar
    pedir = soporte.NucleoPorHTTP.pedir

    # ── cómo lo haría una persona ────────────────────────────────────────────
    def subir(self, ruta: Path):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=30)
        try:
            c.request("POST", f"/api/subir?nombre={quote(ruta.name)}&lote=aceptacion",
                      ruta.read_bytes(), {"Content-Type": "application/pdf",
                                          "Cookie": f"ufil_legajo={self.legajo.slug}"})
            r = c.getresponse()
            return r.status, json.loads(r.read())
        finally:
            c.close()

    def esperar_trabajo(self, limite=180):
        fin = time.monotonic() + limite
        while time.monotonic() < fin:
            estado = self.pedir("/api/trabajo")[1]
            if estado.get("estado") in ("terminado", "error", "detenido"):
                self.assertEqual(estado.get("estado"), "terminado", estado)
                return estado
            time.sleep(0.2)
        self.fail("el trabajo no terminó")

    def procesar_todo(self):
        for ruta in generar(self.temporal / "corpus").values():
            estado, r = self.subir(ruta)
            self.assertEqual(estado, 200, r)
        self.assertEqual(self.pedir("/api/procesar", {}, "POST")[0], 200)
        self.esperar_trabajo()
        self.assertEqual(self.pedir("/api/actualizar", {}, "POST")[0], 200)
        self.esperar_trabajo()

    def todos(self, ruta, clave):
        return self.pedir(f"{ruta}{'&' if '?' in ruta else '?'}limite=500")[1][clave]

    # ── la prueba ────────────────────────────────────────────────────────────
    def test_la_contratacion_se_reconstruye_y_dice_lo_que_hay_que_mirar(self):
        self.procesar_todo()

        # El catálogo lo sirve el backend y es el del núcleo semántico.
        estado, cat = self.pedir("/api/catalogo/contrataciones")
        self.assertEqual(estado, 200, cat)
        self.assertEqual({h["clave"] for h in cat["hallazgos"]},
                         {h["clave"] for h in cp.catalogo()["hallazgos"]})

        # Una contratación, con lo que hay y lo que falta.
        cs = self.todos("/api/contrataciones", "contrataciones")
        self.assertEqual(len(cs), 1, cs)
        self.assertIn(EXPEDIENTE.split("-")[1], cs[0]["expediente"] or "")
        ficha = self.pedir(f"/api/contratacion/{cs[0]['id']}")[1]
        presentes = {e["clave"] for e in ficha["etapas"] if e["presente"]}
        self.assertEqual(presentes, {"pedido", "presupuesto", "oferta", "adjudicacion",
                                     "orden_compra", "remito", "factura", "orden_pago"})
        self.assertIn("pago", {e["clave"] for e in ficha["etapas"] if not e["presente"]},
                      "lo que falta se muestra como faltante")

        # Tres oferentes; B, el adjudicado.
        cuits = {o["cuit"]: o for o in ficha["oferentes"]}
        self.assertEqual(set(cuits), {c for _, c in PROVEEDORES.values()})
        self.assertTrue(cuits[PROVEEDORES["B"][1]]["adjudicado"])
        self.assertEqual(ficha["totales"]["adjudicado"]["valor"], "466000.00")
        self.assertEqual(ficha["totales"]["facturado"]["valor"], "497000.00")

        # Los renglones: el literal intacto y cada precio con su fuente en la foja.
        rs = self.todos("/api/precios", "renglones")
        por_etapa = {}
        for r in rs:
            por_etapa[r["etapa"]] = por_etapa.get(r["etapa"], 0) + 1
            if r["precio_unitario"]["valor"] is not None:
                f = r["precio_unitario"]["fuente"]
                self.assertEqual(f["pagina_nro"], 1)
                self.assertIsNotNone(f["region"], r)
                self.assertTrue(f["celdas"], r)
        for etapa, n in (("presupuesto", 9), ("oferta", 9), ("adjudicacion", 3),
                         ("orden_compra", 3), ("factura", 3)):
            self.assertEqual(por_etapa.get(etapa), n, por_etapa)
        literales = {r["descripcion"]["literal"] for r in rs}
        self.assertIn("Bomba de agua centrifuga 1 HP Rowa Tango", literales,
                      "la descripción original no se reemplaza")

        # «Posible sobreprecio» del renglón 1 de la factura: contra las tres ofertas.
        bomba = next(r for r in rs if r["etapa"] == "factura"
                     and r["precio_unitario"]["valor"] == "180000.00")
        comp = self.pedir(f"/api/renglon/{bomba['id']}/comparacion")[1]
        self.assertEqual(comp["estadisticas"]["nivel"], "A")
        self.assertEqual(comp["estadisticas"]["n"], 3)
        self.assertEqual(comp["estadisticas"]["mediana"], "102500.00")
        self.assertEqual(comp["diferencia"]["absoluta"], "77500.00")
        self.assertEqual(comp["diferencia"]["porcentual"], "75.61")
        niveles = [ref["nivel"] for ref in comp["referencias"]]
        self.assertEqual(niveles.count("A"), 3, "las tres ofertas")
        self.assertEqual(niveles.count("C"), 3, "los tres presupuestos")
        self.assertTrue(comp["excluidas"],
                        "la adjudicación y la orden de la misma compra se muestran excluidas")
        self.assertTrue(comp["calidad"]["motivos"])
        for op in comp["calculo"]["operandos"]:
            self.assertIn("fuente", op)

        # Los hallazgos: exactamente éstos, y ninguno de más.
        hs = self.todos("/api/hallazgos", "hallazgos")
        tipos = {}
        for h in hs:
            tipos[h["tipo"]] = tipos.get(h["tipo"], 0) + 1
            self.assertTrue(h["fuentes"], h)
            self.assertEqual(h["revision"]["estado"], "pendiente")
            self.assertTrue(h["confianza"]["motivos"], h)
            self.assertEqual(cp.terminos_prohibidos_en(h["titulo"] + " " + h["descripcion"]), [])
        self.assertEqual(tipos, {"diferencia_precio": 3, "facturado_vs_adjudicado": 2,
                                 "facturado_vs_entregado": 1, "subtotal_incorrecto": 1})
        sub = next(h for h in hs if h["tipo"] == "subtotal_incorrecto")
        self.assertEqual(sub["calculo"]["resultado"], "84000.00")

        # Una persona lo marca relevante; recalcular no se lo lleva.
        estado, h = self.pedir(f"/api/hallazgo/{sub['id']}/revision",
                               {"estado": "relevante", "nota": "cotejado con la foja"}, "POST")
        self.assertEqual(estado, 200, h)
        self.assertEqual(self.pedir("/api/actualizar", {"forzar": ["renglones"]}, "POST")[0], 200)
        self.esperar_trabajo()
        hs2 = self.todos("/api/hallazgos", "hallazgos")
        self.assertEqual(len(hs2), len(hs), "recalcular no inventa ni pierde hallazgos")
        sub2 = next(h for h in hs2 if h["tipo"] == "subtotal_incorrecto")
        self.assertEqual(sub2["revision"]["estado"], "relevante")
        self.assertEqual(sub2["revision"]["nota"], "cotejado con la foja")


if __name__ == "__main__":
    unittest.main()
