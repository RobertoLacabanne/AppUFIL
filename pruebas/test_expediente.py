"""
Un expediente administrativo no es una pila de formularios.

El sistema nació leyendo contratos de la Legislatura: un formulario, seis rótulos
impresos, un valor al lado de cada uno. Un expediente de obra pública no se parece en
nada. Lo que hay adentro del expediente 201.602 —iluminación LED sobre la Ruta
Provincial 22, parte 4 de un expediente de más de 850 fojas— es esto, medido:

    88 páginas escaneadas
    44 dorsos en blanco          ← la mitad exacta
     3 fojas con tinta y sin nada legible
    41 fojas de trabajo: pliego, especificaciones, memoria descriptiva, presupuesto,
       planos, croquis, acta de apertura, pólizas de caución, constancias fiscales,
       resoluciones y pases de mesa de entradas.

Ni una sola capa de texto: son 88 fotos. Y no una foto de un original, sino —lo dice
el sello de cada foja— una FOTOCOPIA DE FOTOCOPIA.

Lo que se cuida acá es que el sistema diga la verdad sobre ese material: qué es cada
foja, cuáles no se pueden leer, y dónde el propio papel se contradice.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ufil import clasificacion as cl               # noqa: E402
from ufil.capa2_campos import monto_en_letras      # noqa: E402
from ufil.cotejo_letras import cotejar, discrepancias   # noqa: E402


class LaMitadDelEscaneoSonDorsosEnBlanco(unittest.TestCase):
    """
    44 de 88. Si entran a la cola, la mitad de la cola es nada; si cuentan como fojas,
    todos los números del panel están inflados al doble.

    Se decide MIDIENDO y no por frases, porque una hoja en blanco no tiene encabezado
    que reconocer. Los dorsos del expediente dieron entre 0 y 9 palabras y los frentes
    entre 174 y 1.356: no hay nada en el medio.
    """

    def test_un_dorso_en_blanco_se_aparta(self):
        m = cl.medir(["", " ", "_"])
        self.assertEqual(cl.veredicto(m), cl.FOJA_EN_BLANCO)

    def test_y_una_foja_con_texto_no(self):
        m = cl.medir(["MEMORIA", "DESCRIPTIVA", "ILUMINACION"] * 40)
        self.assertIsNone(cl.veredicto(m),
                          "una foja escrita se está apartando como si fuera un dorso")

    def test_el_umbral_esta_lejos_de_los_dos_casos_reales(self):
        """9 palabras el dorso más sucio, 174 el frente más escaso."""
        self.assertGreater(cl.PALABRAS_EN_BLANCO, 9)
        self.assertLess(cl.PALABRAS_EN_BLANCO, 174)

    def test_una_foja_apartada_no_continua_lo_de_arriba(self):
        """
        Heredar `continuacion` sobre un dorso en blanco es lo que hacía que un
        documento se tragara todas las fojas que tenía atrás.
        """
        clases = cl.clasificar_documento(
            [(1, "MEMORIA DESCRIPTIVA"), (2, ""), (3, "")],
            {2: cl.medir([]), 3: cl.medir(["ALGO"] * 300)})
        self.assertEqual(clases[1], "memoria")
        self.assertEqual(clases[2], cl.FOJA_EN_BLANCO)
        self.assertEqual(clases[3], "continuacion")


class UnaFojaQueNoSePuedeLeerLoDice(unittest.TestCase):
    """
    Tres fojas del expediente tienen tinta y no se leen: un plano escaneado al 30 %,
    una fotocopia negra de un carbónico y una carátula que alguien apoyó de costado.
    Ahí el OCR no devuelve nada: devuelve PEOR que nada, porque devuelve fragmentos que
    parecen palabras.

    La CONFIANZA del motor no sirve para decidirlo, y conviene que quede escrito por
    qué: el presupuesto de la obra —una tabla de 31 renglones con todos los importes,
    la foja más valiosa del expediente— lee con confianza 0,35, más bajo que varios
    planos. Lo que separa es la proporción de lo leído que parece una palabra o un
    número de verdad.
    """

    def test_tinta_sin_nada_legible_se_aparta(self):
        # Lo que devuelve el motor sobre una fotocopia negra: fragmentos de dos letras.
        m = cl.medir(["SS", "1V", "PA", "AS", "GS", "LE", "ES", "SU"] * 30)
        self.assertEqual(cl.veredicto(m), cl.FOJA_SIN_TEXTO)

    def test_pero_una_tabla_apretada_no(self):
        """El presupuesto: 19,8 % de útiles. Lee mal y tiene todos los importes."""
        palabras = ["LUMINARIA", "180", "99.498,75"] + ["|", "ES", "A"] * 6
        m = cl.medir(palabras * 20)
        self.assertGreater(m.proporcion_util, cl.UTILES_MINIMOS)
        self.assertIsNone(cl.veredicto(m),
                          "se aparta el presupuesto, que es la foja con los importes")

    def test_si_una_ruta_vio_tinta_la_foja_no_esta_en_blanco(self):
        """
        Encontrado en un legajo real: una ruta de OCR devolvió 137 fragmentos sin nada
        legible y la otra una sola palabra. Ganaba la ruta de una palabra —tenía más
        útiles— y la foja salía «en blanco», escondida, cuando lo que corresponde es
        «no se pudo leer», que es lo que manda a alguien a mirar el papel.
        """
        import tempfile
        from ufil import db
        from ufil.capa1_texto import Palabra
        from ufil.capa2_extraccion import clasificar_fojas
        from ufil.db import ahora
        with tempfile.TemporaryDirectory() as tmp:
            cx = db.abrir(Path(tmp) / "t.sqlite")
            try:
                sha = "e" * 64
                cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,paginas,ingerido_en)
                              VALUES (?,'/x/a.pdf','a.pdf',1,1,?)""", (sha, ahora()))
                cx.execute("INSERT INTO pagina (sha256,nro) VALUES (?,1)", (sha,))
                cx.commit()
                ruido = [Palabra(t, 10 + i, 10, 14 + i, 14, 0.2)
                         for i, t in enumerate(["~", "|", "-", "..", "'"] * 28)][:137]
                una = [Palabra("Folio", 400, 20, 430, 30, 0.9)]
                r = clasificar_fojas(cx, sha, por_ruta={"ocr_a": [(1, None, ruido)],
                                                        "ocr_b": [(1, None, una)]})
                self.assertEqual(r["clases"][1], cl.FOJA_SIN_TEXTO)
            finally:
                cx.close()

    def test_el_corte_esta_entre_los_dos_casos_medidos(self):
        """4,6 % la peor foja legible-para-nadie; 11,8 % el croquis, que sí se lee."""
        self.assertGreater(cl.UTILES_MINIMOS, 0.046)
        self.assertLess(cl.UTILES_MINIMOS, 0.118)

    def test_las_apartadas_estan_declaradas_en_un_solo_lugar(self):
        """Para que contarlas aparte no dependa de acordarse de dos nombres."""
        self.assertEqual(cl.APARTADAS, {cl.FOJA_EN_BLANCO, cl.FOJA_SIN_TEXTO})
        for c in cl.APARTADAS:
            self.assertIn(c, cl.ETIQUETAS, "una foja apartada sin nombre en pantalla")


class ElTituloSeReconoceAunqueElOcrLoLeaMal(unittest.TestCase):
    """
    Sobre este expediente el motor devolvió «ESPEGIFICACIONES TECNICAS» —una C leída
    como G—, «MATERIALES PARA SISTE MAS» —una palabra partida al medio— y «PRESU
    PUESTO». Con búsqueda exacta esas fojas quedaban «sin reconocer» teniendo el título
    impreso en catorce puntos arriba de todo.
    """

    def test_una_letra_mal_leida_no_esconde_el_titulo(self):
        self.assertTrue(cl.contiene_marca("XX ESPEGIFICACIONES TECNICAS DE MATERIALES",
                                          "ESPECIFICACIONES TECNICAS"))

    def test_una_palabra_partida_al_medio_tampoco(self):
        self.assertTrue(cl.contiene_marca("MEMORIA DESCRIP TIVA DE LA OBRA",
                                          "MEMORIA DESCRIPTIVA"))

    def test_pero_el_ruido_de_los_sellos_no_inventa_un_titulo(self):
        """
        Sin el ancla exacta, una marca larga aceptada al 90 % admite dos letras
        equivocadas, y en cuatrocientos caracteres de ruido hay muchas ventanas donde
        dos letras alcanzan: un plano salía clasificado «Presupuesto».
        """
        ruido = "FIAT LAS 7 KY ASA YA PASA FOLIO ME SER AN A SER 1 E ES WM UN BES SE 14"
        for marca in ("MEMORIA DESCRIPTIVA", "PRESUPUESTO OFICIAL",
                      "PLIEGO DE CONDICIONES", "ACTA DE APERTURA"):
            self.assertFalse(cl.contiene_marca(ruido, marca),
                             f"el ruido de los sellos se lee como «{marca}»")

    def test_el_ancla_es_lo_que_lo_sostiene(self):
        self.assertGreaterEqual(cl.ANCLA_EXACTA, 5,
                                "el ancla se achicó tanto que vuelve a atarse al ruido")


class ElExpedienteTraeSusPropiasFojas(unittest.TestCase):
    """
    Un expediente de obra no trae contratos: trae pliego, especificaciones, memoria,
    presupuesto, planos, acta de apertura, pólizas y constancias. Si el sistema no los
    conoce, las 41 fojas de trabajo quedan todas en «sin reconocer».
    """

    ESPERADOS = ("pliego", "especificaciones", "memoria", "presupuesto", "plano",
                 "acta_apertura", "poliza", "constancia", "pase")

    def test_estan_los_tipos_del_material_administrativo(self):
        for clave in self.ESPERADOS:
            self.assertIn(clave, cl.TIPOS_POR_CLAVE,
                          f"el expediente trae «{clave}» y el sistema no lo conoce")
            self.assertIn(clave, cl.ETIQUETAS, f"«{clave}» sin nombre en pantalla")

    # Lo que acompaña al expediente y no es un documento en sí: si cada una de estas
    # fojas arrancara uno, el expediente quedaría partido en cuarenta documentos de una
    # hoja que después habría que volver a pegar.
    CONTEXTO = ("plano", "poliza", "constancia", "pase")
    # Lo que sí es un documento: dice qué se pidió o a cuánto, y por eso tiene que poder
    # colgar de una contratación y abrirse desde un precio.
    DOCUMENTOS = ("pliego", "especificaciones", "memoria", "presupuesto", "acta_apertura")

    def test_el_contexto_no_parte_el_expediente_en_pedazos(self):
        for clave in self.CONTEXTO:
            self.assertFalse(cl.TIPOS_POR_CLAVE[clave].arranca,
                             f"«{clave}» parte el expediente en pedazos")
            self.assertNotIn(clave, cl.TIPOS_PIEZA)

    def test_lo_que_dice_que_se_pidio_o_a_cuanto_es_una_pieza(self):
        """
        Mientras el pliego y las especificaciones no eran pieza, sus fojas no
        pertenecían a ningún documento: no se podían abrir desde una contratación y sus
        tablas no daban un solo renglón. Y son justamente las que dicen QUÉ se pidió,
        que es lo que permite después afirmar que dos precios son comparables.
        """
        for clave in self.DOCUMENTOS:
            self.assertIn(clave, cl.TIPOS_PIEZA,
                          f"«{clave}» no forma pieza y define qué se compró")

    def test_y_los_de_la_legislatura_siguen_arrancando(self):
        """Un contrato sí es un documento suelto adentro del PDF."""
        for clave in ("contrato_obra", "contrato_locacion", "factura"):
            self.assertTrue(cl.TIPOS_POR_CLAVE[clave].arranca)

    def test_la_leyenda_del_remito_manda_sobre_la_palabra_factura(self):
        """
        Encontrado en un legajo real: 13 fojas con «DOCUMENTO NO VÁLIDO COMO FACTURA»
        —la leyenda que todo remito lleva impresa y ninguna factura— salían «factura»,
        porque la palabra está en la propia leyenda.
        """
        from ufil.capa2_campos import normalizar_cotejo
        for texto in ("DOCUMENTO NO VALIDO COMO FACTURA REMITO N 0001-00004567 PROVEEDOR SINTETICO",
                      "xx Qe DOCUMENTO NO VALIDO COMO FACTUR£-S 20 VIA ORDEN DE COMPRA N 12",
                      "ORDEN DE COMPRA N 4 DOCUMENTO NO VALIDO COMO FACTURA"):
            with self.subTest(texto=texto):
                self.assertEqual(cl.clasificar_pagina(normalizar_cotejo(texto))[0], "remito")
        factura = normalizar_cotejo("ORIGINAL FACTURA B PUNTO DE VENTA 0003 COMP NRO 00001234")
        self.assertEqual(cl.clasificar_pagina(factura)[0], "factura")

    def test_si_una_ruta_leyo_la_leyenda_del_remito_vale(self):
        """
        Encontrado en un legajo real: una ruta de OCR leyó la leyenda entera y la otra,
        con un encabezado más largo, dañada. Ganaba el encabezado más largo y la foja
        salía «orden de compra».
        """
        import tempfile
        from ufil import db
        from ufil.capa1_texto import Palabra
        from ufil.capa2_extraccion import clasificar_fojas
        from ufil.db import ahora

        def palabras(texto):
            return [Palabra(w, 10 + 30 * i, 20, 38 + 30 * i, 30, 0.8) for i, w in enumerate(texto.split())]

        with tempfile.TemporaryDirectory() as tmp:
            cx = db.abrir(Path(tmp) / "t.sqlite")
            try:
                sha = "f" * 64
                cx.execute("""INSERT INTO archivo (sha256,ruta_original,nombre,bytes,paginas,ingerido_en)
                              VALUES (?,'/x/a.pdf','a.pdf',1,1,?)""", (sha, ahora()))
                cx.execute("INSERT INTO pagina (sha256,nro) VALUES (?,1)", (sha,))
                cx.commit()
                larga_danada = ("AN DOCUMENTO N0 VAL1D0 C0M0 FACTUR4 ORDEN DE COMPRA NUMERO 12 "
                                "PROVEEDOR SINTETICO DOMICILIO CALLE FALSA 123 CIUDAD CODIGO POSTAL "
                                "TELEFONO CORREO CANTIDAD DESCRIPCION BULTOS ENTREGADOS")
                corta_buena = "DOCUMENTO NO VALIDO COMO FACTURA REMITO 0001-00004567"
                r = clasificar_fojas(cx, sha, por_ruta={
                    "ocr_a": [(1, None, palabras(larga_danada))],
                    "ocr_b": [(1, None, palabras(corta_buena))]})
                self.assertEqual(r["clases"][1], "remito")
            finally:
                cx.close()

    def test_una_resolucion_se_reconoce_por_su_cuerpo(self):
        """
        El título está arriba a la derecha, que es justo donde se apilan los sellos de
        mesa de entradas: en una fotocopia ahí no se lee nada. VISTO y RESUELVE están
        en el cuerpo y en limpio.
        """
        marcas = cl.TIPOS_POR_CLAVE["resolucion"].marcas
        for m in ("VISTO", "RESUELVE"):
            self.assertIn(m, marcas)


class ElPapelEscribeElNumeroDosVeces(unittest.TestCase):
    """
    «PESOS OCHO MILLONES TRESCIENTOS DOCE MIL CIENTO UNO CON 91/100 ($8.312.101,91)».

    Es una segunda lectura gratis y del propio documento: el §12 pide dos rutas para
    dar un dato por firme, y acá las dos ya están escritas en el papel.
    """

    RESOLUCION = ("Que, se ha estimado un Presupuesto Oficial de PESOS OCHO MILLONES "
                  "TRESCIENTOS DOCE MIL CIENTO UNO CON 91/100 ($8.312.101,91) al mes "
                  "de FEBRERO/23;")
    PRESUPUESTO = ("El presupuesto necesario es de PESOS OCHO MILLONES TRESCIENTOS "
                   "DOCE MIL CIENTO UNO CON NOVENTA Y UN CENTAVOS ($8.312.101,91.-)")

    def test_las_dos_formas_de_escribir_los_centavos(self):
        """
        La resolución 815 escribe «CON 91/100» y el presupuesto de la MISMA obra, «CON
        NOVENTA Y UN CENTAVOS». Es el mismo importe escrito por dos oficinas distintas,
        y sin entender las dos formas el importe en letras no se podía leer nunca en un
        acto administrativo.
        """
        a = monto_en_letras("PESOS OCHO MILLONES TRESCIENTOS DOCE MIL CIENTO UNO "
                            "CON 91/100")
        b = monto_en_letras("PESOS OCHO MILLONES TRESCIENTOS DOCE MIL CIENTO UNO "
                            "CON NOVENTA Y UN CENTAVOS")
        self.assertEqual(a, 831210191, "no lee «CON 91/100»")
        self.assertEqual(b, 831210191, "no lee los centavos escritos con palabras")

    def test_un_importe_que_coincide_se_confirma(self):
        for texto in (self.RESOLUCION, self.PRESUPUESTO):
            c = cotejar(texto)
            self.assertEqual(len(c), 1, f"no encontró el importe en: {texto[:40]}…")
            self.assertTrue(c[0].coinciden, "el importe coincide y dice que no")
            self.assertEqual(c[0].valor_letras, 831210191)

    def test_centavos_que_no_se_entienden_no_inventan_un_importe(self):
        self.assertIsNone(monto_en_letras("PESOS MIL CON CHIRIMBOLOS CENTAVOS"))


class VeintiunoNoEsVeintiocho(unittest.TestCase):
    """
    El hallazgo de verdad de este expediente. La memoria descriptiva dice, dos veces:

        «Se prevé la instalación de 21 (VEINTIOCHO) luminarias del tipo LED»
        «Se instalarán 21 (VEINTIOCHO) columnas con un brazo de 2,50m»

    El presupuesto de la misma obra cotiza 21 luminarias y 21 columnas. Alguien
    escribió veintiocho donde dice veintiuno, en el documento que describe qué se
    compra, y nadie lo vio.
    """

    MEMORIA = ("Se prevé la instalación de 21 (VEINTIOCHO) luminarias del tipo LED, "
               "con 1 (UNO) tableros generales, ver plano adjunto.")

    def test_la_diferencia_aparece(self):
        d = discrepancias(self.MEMORIA)
        self.assertEqual(len(d), 1, "no encuentra «21 (VEINTIOCHO)»")
        self.assertEqual(d[0].letras.upper(), "VEINTIOCHO")
        self.assertEqual(d[0].digitos, "21")

    def test_y_lo_que_coincide_no_molesta(self):
        """«1 (UNO)» está bien escrito y no puede aparecer como hallazgo."""
        unos = [c for c in cotejar(self.MEMORIA) if c.digitos == "1"]
        self.assertEqual(len(unos), 1)
        self.assertTrue(unos[0].coinciden)

    def test_el_sistema_no_elige_cual_tiene_razon(self):
        """
        Un sistema que «corrige» veintiocho por veintiuno estaría inventando un dato en
        un expediente penal. Devuelve las dos, con lo que está escrito en cada una.
        """
        c = discrepancias(self.MEMORIA)[0]
        self.assertEqual(c.letras.upper(), "VEINTIOCHO")
        self.assertEqual(c.digitos, "21")
        self.assertIsNotNone(c.valor_letras)
        self.assertIsNotNone(c.valor_digitos)
        self.assertNotEqual(c.valor_letras, c.valor_digitos)

    def test_un_parentesis_cualquiera_no_es_una_cantidad(self):
        texto = ("columnas con un brazo de 2,50m de 9,00m de altura libre (altura "
                 "total 10m), según plano (ver plano adjunto) y norma IRAM.")
        self.assertEqual(cotejar(texto), [],
                         "lee un paréntesis cualquiera como una cantidad escrita dos "
                         "veces, y eso llena la pantalla de hallazgos que no existen")

    def test_lo_que_no_se_pudo_leer_no_es_una_discrepancia(self):
        """
        Sobre la foja 43 el motor leyó «A OCHO MILLONES…» y «OCHENTA Y TRES MIL ú
        DOSCIENTOS». Ahí no hay desacuerdo entre el papel y el papel: hay una lectura
        que falló, y decir «no coinciden» sería acusar al documento de algo que hizo el
        OCR.
        """
        texto = "PESOS OCHENTA Y TRES MIL ú DOSCIENTOS ($83.200,00)"
        c = cotejar(texto)
        self.assertEqual(len(c), 1)
        self.assertIsNone(c[0].coinciden)
        self.assertEqual(discrepancias(texto), [])


class ElExpedienteSePuedeMirar(unittest.TestCase):
    """
    Antes de esto el expediente entraba al sistema y desaparecía: 88 páginas ingeridas,
    88 leídas, **0 documentos**, ninguna pantalla donde mirarlo. Un expediente de obra
    no produce documentos porque no hay adentro un solo formulario que extraer, y el
    sistema sólo sabía mostrar documentos.
    """

    APP = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")
    SRV = (RAIZ / "ufil/servidor.py").read_text(encoding="utf-8")

    def test_hay_una_pantalla_de_fojas(self):
        for pieza, queja in (
                ("'#/fojas'", "la pantalla no está en la navegación"),
                ("async function vFojas", "no hay pantalla de fojas"),
                ("/api/fojas", "la pantalla no tiene de dónde sacar las fojas")):
            self.assertIn(pieza, self.APP + self.SRV, queja)

    def test_las_apartadas_se_cuentan_y_se_pueden_abrir(self):
        """
        Contarlas y esconderlas no es lo mismo: si el sistema se equivocó apartando una
        foja, poder abrirla es lo único que lo revela.
        """
        self.assertIn("fojas apartadas", self.APP,
                      "las fojas apartadas dejaron de poder mirarse")
        self.assertIn("f.apartada", self.APP)

    def test_una_foja_se_abre_sin_documento_que_la_contenga(self):
        """
        Un expediente no produce documentos, así que pedir su foja 77 «por documento»
        no se puede. Sin esto, la pantalla donde por fin se ve un expediente no podría
        abrir una sola de sus fojas, que es lo único que sirve de un expediente.
        """
        self.assertIn("function abrirFojaSuelta", self.APP)
        self.assertIn('if q.get("sha"):', self.SRV,
                      "la imagen de una foja sólo se puede pedir por documento")

    def test_los_numeros_que_no_coinciden_tienen_su_pantalla(self):
        for pieza in ("'#/numeros'", "async function vNumeros", "/api/numeros"):
            self.assertIn(pieza, self.APP + self.SRV)

    def test_y_van_todos_y_no_solo_los_que_fallan(self):
        """
        Los que coinciden son la prueba de que el importe se leyó bien. Una pantalla con
        sólo las diferencias no deja saber si el sistema miró algo o no miró nada.
        """
        i = self.SRV.index("def api_numeros")
        cuerpo = self.SRV[i:i + 2000]
        self.assertNotIn("WHERE c.coinciden = 0", cuerpo,
                         "la pantalla muestra sólo las diferencias")
        self.assertIn("coinciden IS NOT 0", cuerpo,
                      "las diferencias dejaron de ir primero")

    def test_de_una_hoja_en_blanco_no_sale_ningun_numero(self):
        extraccion = (RAIZ / "ufil/capa2_extraccion.py").read_text(encoding="utf-8")
        self.assertIn("if clases.get(nro) in cl.APARTADAS:", extraccion,
                      "se cotejan números sobre fojas apartadas: de una fotocopia "
                      "ilegible el motor devuelve cualquier cosa, y cualquier cosa "
                      "con un paréntesis pasaría por una cantidad escrita dos veces")
