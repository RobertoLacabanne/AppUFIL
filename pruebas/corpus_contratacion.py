"""
Una contratación completa, inventada, para probar de punta a punta el incremento 7.

Todo es sintético: el organismo, el expediente, los proveedores, sus CUIT y los precios.
No sale de ningún corpus real y no se parece a ninguno a propósito. Lo que sí es real es
la forma: cada documento es un PDF con texto nativo, encabezado, datos del proveedor y una
planilla de renglones alineada en columnas, que es lo que el detector de tablas tiene que
encontrar sin ayuda.

El guion (ver `docs/contrataciones-y-precios.md` §11, «resultado esperado»):

    12/07 pedido            3 renglones
    18/07 presupuestos      de los tres proveedores
    25/07 ofertas           de los tres proveedores
    02/08 adjudicación      al proveedor B, el renglón 1 a 165.000 —su oferta fue 104.000—
    10/08 orden de compra   a B, igual que la adjudicación
    23/08 remito            de B: el renglón 3 entrega 8, no 10
    24/08 factura           de B: el renglón 1 a 180.000; el subtotal del 2 mal sumado
    04/09 orden de pago     por el total de la factura
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import fitz

EXPEDIENTE = "EXP-7731/2023"
ORGANISMO = "Direccion Provincial de Talleres Sinteticos"

PROVEEDORES = {
    "A": ("Repuestos Albatros SRL", "30-71234567-8"),
    "B": ("Bombas del Litoral Sintetico SA", "30-79876543-2"),
    "C": ("Casa Cormoran SRL", "30-70011223-4"),
}

# (descripción, unidad) — la descripción ya trae marca, modelo y especificación.
ITEMS = (
    ("Bomba de agua centrifuga 1 HP Rowa Tango", "unidad"),
    ("Tensor movil de correa Poly-V", "unidad"),
    ("Aceite hidraulico ISO 68", "litro"),
)
CANTIDADES = (2, 4, 10)

PRESUPUESTOS = {"A": (98000, 19800, 4950), "B": (101000, 20900, 5150),
                "C": (99500, 20400, 5050)}
OFERTAS = {"A": (100000, 20000, 5000), "B": (104000, 21000, 5200),
           "C": (102500, 20500, 5100)}
ADJUDICADO = (165000, 21000, 5200)          # a B
FACTURADO = (180000, 21000, 5200)           # renglón 1 distinto de lo adjudicado
REMITIDO = (2, 4, 8)                        # el renglón 3 entrega 8 de 10
SUBTOTAL_MAL = {1: 85000}                   # 4 × 21.000 = 84.000, impreso 85.000

# Con aire entre columnas: el detector exige 18 pt de blanco entre una celda y la
# siguiente (ufil/tablas.py, MIN_HUECO). Los encabezados largos y pegados de muchas
# facturas reales no llegan; eso queda anotado como riesgo aparte.
#
# Lo que este corpus SÍ prueba del detector, a propósito: cada planilla vive en una foja
# con encabezado, datos del proveedor y total, como en el papel de verdad. Al escribirlo,
# el detector no encontraba ninguna, porque pide que las columnas aparezcan en el 60 % de
# los renglones de TODA la foja (docs/contrataciones-y-precios.md §11).
COLUMNAS = (40, 95, 320, 370, 430, 510)
ENCABEZADO = ("Rengl.", "Descripcion", "Cant.", "Unidad", "P. unitario", "Subtotal")


def importe(n) -> str:
    """Como se escribe en Argentina: 165.000,00."""
    entero, dec = f"{Decimal(n):.2f}".split(".")
    return f"{int(entero):,}".replace(",", ".") + "," + dec


def _pdf(destino: Path, titulo: str, lineas: list[str], renglones=None, total=None) -> Path:
    doc = fitz.open()
    p = doc.new_page(width=595, height=842)
    y = 60
    p.insert_text((50, y), titulo, fontsize=14)
    y += 26
    for linea in lineas:
        p.insert_text((50, y), linea, fontsize=10)
        y += 16
    if renglones:
        y += 14
        for x, t in zip(COLUMNAS, ENCABEZADO):
            p.insert_text((x, y), t, fontsize=8)
        for fila in renglones:
            y += 18
            for x, t in zip(COLUMNAS, fila):
                p.insert_text((x, y), str(t), fontsize=8)
    if total is not None:
        y += 30
        p.insert_text((380, y), f"Total $ {importe(total)}", fontsize=10)
    destino.parent.mkdir(parents=True, exist_ok=True)
    doc.save(destino)
    doc.close()
    return destino


def _filas(precios, cantidades=CANTIDADES, subtotales=None):
    subtotales = subtotales or {}
    filas, total = [], Decimal(0)
    for i, ((desc, unidad), cant, precio) in enumerate(zip(ITEMS, cantidades, precios)):
        sub = subtotales.get(i, cant * precio)
        total += sub
        filas.append((i + 1, desc, cant, unidad, importe(precio), importe(sub)))
    return filas, total


def generar(carpeta: Path) -> dict[str, Path]:
    """Escribe los doce PDF de la contratación y devuelve {nombre: ruta}."""
    carpeta = Path(carpeta)
    cab = [f"Expediente {EXPEDIENTE}", ORGANISMO]
    salida = {}

    filas = [(i + 1, desc, cant, unidad)
             for i, ((desc, unidad), cant) in enumerate(zip(ITEMS, CANTIDADES))]
    salida["pedido"] = _pdf(carpeta / "01-pedido.pdf", "SOLICITUD DE PROVISION",
                            cab + ["Fecha: 12/07/2023", "Se solicita la provision de:"], filas)

    for k, precios in PRESUPUESTOS.items():
        nombre, cuit = PROVEEDORES[k]
        filas, total = _filas(precios)
        salida[f"presupuesto_{k}"] = _pdf(
            carpeta / f"02-presupuesto-{k}.pdf", "PRESUPUESTO",
            cab + [f"Proveedor: {nombre}  CUIT {cuit}", "Fecha: 18/07/2023",
                   "Importes en pesos, IVA incluido"], filas, total)

    for k, precios in OFERTAS.items():
        nombre, cuit = PROVEEDORES[k]
        filas, total = _filas(precios)
        salida[f"oferta_{k}"] = _pdf(
            carpeta / f"03-oferta-{k}.pdf", "OFERTA",
            cab + [f"Oferente: {nombre}  CUIT {cuit}", "Fecha: 25/07/2023",
                   "Importes en pesos, IVA incluido"], filas, total)

    nombre_b, cuit_b = PROVEEDORES["B"]
    filas, total = _filas(ADJUDICADO)
    salida["adjudicacion"] = _pdf(
        carpeta / "04-adjudicacion.pdf", "RESOLUCION DE ADJUDICACION",
        cab + ["Fecha: 02/08/2023", f"ADJUDICASE a {nombre_b}  CUIT {cuit_b}",
               "Importes en pesos, IVA incluido"], filas, total)

    filas, total = _filas(ADJUDICADO)
    salida["orden_compra"] = _pdf(
        carpeta / "05-orden-de-compra.pdf", "ORDEN DE COMPRA N 0418/2023",
        cab + ["Fecha: 10/08/2023", f"Proveedor: {nombre_b}  CUIT {cuit_b}",
               "Importes en pesos, IVA incluido"], filas, total)

    filas, _ = _filas(ADJUDICADO, cantidades=REMITIDO)
    filas = [f[:4] for f in filas]
    salida["remito"] = _pdf(
        carpeta / "06-remito.pdf", "REMITO N 0002-00005521",
        cab + ["Fecha: 23/08/2023", f"Proveedor: {nombre_b}  CUIT {cuit_b}",
               "Orden de compra N 0418/2023"], filas)

    filas, total = _filas(FACTURADO, subtotales=SUBTOTAL_MAL)
    salida["factura"] = _pdf(
        carpeta / "07-factura.pdf", "FACTURA B",
        [f"{nombre_b}  CUIT {cuit_b}", "Punto de Venta: 0003  Comp. Nro: 00001234",
         "Fecha de Emision: 24/08/2023", f"Expediente {EXPEDIENTE}",
         "Orden de compra N 0418/2023  Remito N 0002-00005521"], filas, total)

    salida["orden_pago"] = _pdf(
        carpeta / "08-orden-de-pago.pdf", "ORDEN DE PAGO N 0977/2023",
        cab + ["Fecha: 04/09/2023", f"Beneficiario: {nombre_b}  CUIT {cuit_b}",
               "Factura B 0003-00001234"], total=total)
    return salida
