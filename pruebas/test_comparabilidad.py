"""
Qué se puede comparar con qué, regla por regla (docs/contrataciones-y-precios.md §3–§4).

Cada prueba mira el estado y también el motivo: una comparación que acierta el estado por
la razón equivocada va a fallar con el primer caso real que no se parezca a éste.
"""
from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ufil import comparabilidad as cp
from ufil.comparabilidad import Observacion

HOY = date(2023, 8, 24)


def obs(desc="Bomba de agua centrífuga", **kw) -> Observacion:
    """Un renglón completo: todo conocido. Cada prueba cambia sólo lo que le importa."""
    base = dict(desc_norm=desc, unidad="unidad", moneda="ARS", marca="Rowa", modelo="Tango",
                categoria="bomba", iva="incluido", cantidad=Decimal("1"), fecha=HOY,
                etapa="factura", contratacion=1)
    base.update(kw)
    return Observacion(**base)


def efecto(r: dict, atributo: str) -> str | None:
    return next((m["efecto"] for m in r["motivos"] if m["atributo"] == atributo), None)


class LoQueCoincideEnTodoEsFuerte(unittest.TestCase):

    def test_mismo_producto_con_todo_conocido(self):
        r = cp.comparabilidad(obs(), obs())
        self.assertEqual(r["estado"], cp.FUERTE)
        self.assertEqual(r["similitud"], 1.0)
        for m in r["motivos"]:
            self.assertEqual(m["efecto"], cp.COINCIDE, m)

    def test_la_descripcion_se_compara_sin_tildes_ni_mayusculas(self):
        r = cp.comparabilidad(obs("Tensor móvil de correa Poly-V"),
                              obs("TENSOR MOVIL DE CORREA POLY-V"))
        self.assertEqual(r["estado"], cp.FUERTE)

    def test_marca_y_modelo_ausentes_en_los_dos_no_impiden_fuerte(self):
        r = cp.comparabilidad(obs(marca=None, modelo=None), obs(marca=None, modelo=None))
        self.assertEqual(r["estado"], cp.FUERTE)


class LoQueContradiceBloquea(unittest.TestCase):
    """Un atributo conocido y distinto alcanza: el texto parecido no compensa."""

    def test_cada_atributo_bloqueante(self):
        for atributo, a, b in (("unidad", "unidad", "caja"), ("moneda", "ARS", "USD"),
                               ("marca", "Rowa", "Czerweny"), ("modelo", "Tango", "SFL"),
                               ("categoria", "bomba", "motor")):
            with self.subTest(atributo=atributo):
                r = cp.comparabilidad(obs(**{atributo: a}), obs(**{atributo: b}))
                self.assertEqual(r["estado"], cp.NO_COMPARABLE)
                self.assertEqual(efecto(r, atributo), cp.BLOQUEA)

    def test_numeros_distintos_son_otra_especificacion(self):
        # Como texto se parecen casi del todo; como producto, no.
        r = cp.comparabilidad(obs("Bomba de agua 1 HP"), obs("Bomba de agua 2 HP"))
        self.assertEqual(r["estado"], cp.NO_COMPARABLE)
        self.assertEqual(efecto(r, "especificacion"), cp.BLOQUEA)

    def test_la_coma_decimal_no_cambia_la_especificacion(self):
        r = cp.comparabilidad(obs("Cable unipolar 2,5 mm"), obs("Cable unipolar 2.5 mm"))
        self.assertEqual(efecto(r, "especificacion"), cp.COINCIDE)
        self.assertEqual(r["estado"], cp.FUERTE)

    def test_descripciones_que_no_se_parecen(self):
        r = cp.comparabilidad(obs("Bomba de agua centrífuga"), obs("Resma papel oficio"))
        self.assertEqual(r["estado"], cp.NO_COMPARABLE)
        self.assertEqual(efecto(r, "descripcion"), cp.BLOQUEA)


class LoQueFaltaImpideFuerte(unittest.TestCase):

    def test_marca_de_un_solo_lado_es_probable(self):
        r = cp.comparabilidad(obs(), obs(marca=None))
        self.assertEqual(r["estado"], cp.PROBABLE)
        self.assertEqual(efecto(r, "marca"), cp.FALTA)

    def test_sin_unidad_en_ninguno_no_hay_precio_unitario_seguro(self):
        r = cp.comparabilidad(obs(unidad=None), obs(unidad=None))
        self.assertEqual(r["estado"], cp.PROBABLE)
        self.assertEqual(efecto(r, "unidad"), cp.FALTA)

    def test_iva_desconocido(self):
        r = cp.comparabilidad(obs(), obs(iva=None))
        self.assertEqual(r["estado"], cp.PROBABLE)

    def test_numeros_de_un_solo_lado(self):
        r = cp.comparabilidad(obs("Bomba de agua 1 HP"), obs("Bomba de agua"))
        self.assertEqual(efecto(r, "especificacion"), cp.FALTA)
        self.assertNotEqual(r["estado"], cp.FUERTE)


class LoQuePuedeExplicarLaDiferenciaEsDudoso(unittest.TestCase):

    def test_iva_incluido_contra_discriminado(self):
        r = cp.comparabilidad(obs(iva="incluido"), obs(iva="discriminado"))
        self.assertEqual(r["estado"], cp.DUDOSO)
        self.assertEqual(efecto(r, "iva"), cp.DIFIERE)

    def test_flete_de_un_solo_lado(self):
        r = cp.comparabilidad(obs(condiciones=frozenset({"flete"})), obs())
        self.assertEqual(r["estado"], cp.DUDOSO)
        self.assertEqual(efecto(r, "flete"), cp.DIFIERE)

    def test_parecido_a_medias(self):
        r = cp.comparabilidad(obs("Bomba de agua centrífuga"),
                              obs("Bomba centrífuga para piscina"))
        self.assertEqual(r["estado"], cp.DUDOSO)


class LaDecisionHumanaManda(unittest.TestCase):

    def test_una_persona_dijo_que_es_el_mismo(self):
        r = cp.comparabilidad(obs(), obs(marca=None), decision_humana="mismo", quien="perez.ana")
        self.assertEqual(r["estado"], cp.FUERTE)
        self.assertEqual(r["motivos"][0]["b"], "perez.ana", "se registra quién lo decidió")

    def test_una_persona_dijo_que_no(self):
        r = cp.comparabilidad(obs(), obs(), decision_humana="distinto", quien="perez.ana")
        self.assertEqual(r["estado"], cp.NO_COMPARABLE)


class LaEscalaSeInformaYNoDecide(unittest.TestCase):

    def test_uno_contra_mil(self):
        r = cp.comparabilidad(obs(cantidad=Decimal("1")), obs(cantidad=Decimal("1000")))
        self.assertEqual(efecto(r, "cantidad"), cp.DIFIERE)
        self.assertEqual(r["estado"], cp.FUERTE)


class LosNivelesDeLaReferencia(unittest.TestCase):

    def nivel(self, a, b):
        return cp.nivel(a, b, cp.comparabilidad(a, b)["estado"])

    def test_a_misma_contratacion_fecha_cercana(self):
        self.assertEqual(self.nivel(obs(), obs(etapa="oferta", fecha=HOY - timedelta(30))), "A")

    def test_b_otra_contratacion(self):
        self.assertEqual(self.nivel(obs(), obs(contratacion=2, fecha=HOY - timedelta(200))), "B")

    def test_b_misma_contratacion_pero_fechas_separadas(self):
        self.assertEqual(self.nivel(obs(), obs(fecha=HOY - timedelta(200))), "B")

    def test_c_presupuesto_contemporaneo(self):
        self.assertEqual(self.nivel(obs(), obs(etapa="presupuesto", marca=None,
                                               fecha=HOY - timedelta(20))), "C")

    def test_c_no_es_a_aunque_sea_fuerte(self):
        # Un presupuesto no prueba el precio pactado: nunca es nivel A.
        self.assertEqual(self.nivel(obs(), obs(etapa="presupuesto")), "C")

    def test_d_similar_no_identico(self):
        self.assertEqual(self.nivel(obs(), obs(marca=None, fecha=HOY - timedelta(200))), "D")

    def test_e_dudoso(self):
        self.assertEqual(self.nivel(obs(), obs(iva="discriminado")), "E")

    def test_e_sin_fecha(self):
        self.assertEqual(self.nivel(obs(), obs(fecha=None)), "E",
                         "una fecha que no se conoce no es una fecha cercana")

    def test_e_lejos_en_el_tiempo(self):
        self.assertEqual(self.nivel(obs(), obs(fecha=HOY - timedelta(800))), "E")

    def test_e_referencia_sin_documento(self):
        self.assertEqual(self.nivel(obs(), obs(documentada=False)), "E")

    def test_no_comparable_no_es_referencia(self):
        self.assertIsNone(self.nivel(obs(), obs(unidad="caja")))


class ElNivelDeLaComparacionPrincipal(unittest.TestCase):

    def test_el_mejor_nivel_con_suficientes_referencias(self):
        nivel, adv = cp.elegir_nivel(["A", "A", "B", "C"])
        self.assertEqual(nivel, "A")
        self.assertEqual(adv, [])

    def test_si_hay_que_bajar_de_nivel_se_dice(self):
        nivel, adv = cp.elegir_nivel(["A", "B", "B", "B"])
        self.assertEqual(nivel, "B")
        self.assertTrue(any("nivel A" in a for a in adv), adv)

    def test_una_sola_referencia_se_dice(self):
        nivel, adv = cp.elegir_nivel(["C"])
        self.assertEqual(nivel, "C")
        self.assertTrue(any("una sola" in a for a in adv), adv)

    def test_sin_referencias(self):
        nivel, adv = cp.elegir_nivel([None, None])
        self.assertIsNone(nivel)
        self.assertTrue(adv)


class LaCalidadDeLaComparacion(unittest.TestCase):

    def test_alta(self):
        c = cp.calidad("A", [cp.FUERTE, cp.FUERTE], precios_firmes=True)
        self.assertEqual(c["nivel"], "alta")

    def test_media_por_precio_sin_confirmar(self):
        c = cp.calidad("A", [cp.FUERTE, cp.FUERTE], precios_firmes=False)
        self.assertEqual(c["nivel"], "media")

    def test_media_por_una_sola_referencia(self):
        self.assertEqual(cp.calidad("B", [cp.FUERTE], precios_firmes=True)["nivel"], "media")

    def test_baja_si_algo_es_dudoso(self):
        c = cp.calidad("A", [cp.FUERTE, cp.DUDOSO], precios_firmes=True)
        self.assertEqual(c["nivel"], "baja")

    def test_baja_con_derivados_sin_revisar(self):
        c = cp.calidad("A", [cp.FUERTE, cp.FUERTE], precios_firmes=True,
                       derivados_sin_revisar=True)
        self.assertEqual(c["nivel"], "baja")

    def test_cada_calidad_dice_por_que(self):
        for c in (cp.calidad("A", [cp.FUERTE] * 3, precios_firmes=True),
                  cp.calidad("D", [cp.PROBABLE], precios_firmes=True),
                  cp.calidad("E", [cp.DUDOSO], precios_firmes=False)):
            self.assertTrue(c["motivos"], c)


class LaAplicacionNoConcluye(unittest.TestCase):

    def test_detecta_los_terminos_prohibidos(self):
        for texto in ("Hubo sobreprecio en el renglón 3", "Posible fraude",
                      "Contratación direccionada", "Pago irregular", "Acto ilícito"):
            with self.subTest(texto=texto):
                self.assertTrue(cp.terminos_prohibidos_en(texto))

    def test_posible_sobreprecio_se_admite(self):
        self.assertEqual(cp.terminos_prohibidos_en("Posible sobreprecio"), [])
        self.assertEqual(cp.terminos_prohibidos_en("posibles sobreprecios"), [])

    def test_ningun_texto_del_catalogo_concluye(self):
        cat = cp.catalogo()
        for clave in ("etapas", "comparabilidad", "niveles", "hallazgos", "revision"):
            for e in cat[clave]:
                with self.subTest(catalogo=clave, entrada=e["clave"]):
                    self.assertEqual(cp.terminos_prohibidos_en(e["nombre"] + " " + e["explicacion"]),
                                     [])


class ElCatalogoLoSirveElBackend(unittest.TestCase):

    def test_cada_entrada_tiene_clave_nombre_y_explicacion(self):
        cat = cp.catalogo()
        for clave in ("etapas", "comparabilidad", "niveles", "hallazgos", "revision"):
            self.assertTrue(cat[clave], clave)
            for e in cat[clave]:
                self.assertTrue({"clave", "nombre", "explicacion"} <= set(e), e)

    def test_los_umbrales_viajan_y_se_reflejan_en_las_explicaciones(self):
        cat = cp.catalogo({"dias_cercana": 45})
        self.assertEqual(cat["umbrales"]["dias_cercana"], 45)
        self.assertIn("45 días", next(n for n in cat["niveles"] if n["clave"] == "A")["explicacion"])

    def test_las_etapas_primarias_son_las_que_prueban_precio_pactado_o_pagado(self):
        primarias = {e["clave"] for e in cp.catalogo()["etapas"] if e["primaria"]}
        self.assertIn("factura", primarias)
        self.assertIn("orden_compra", primarias)
        self.assertNotIn("presupuesto", primarias)


if __name__ == "__main__":
    unittest.main()
