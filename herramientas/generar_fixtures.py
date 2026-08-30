#!/usr/bin/env python3
"""
Genera un corpus SINTÉTICO de contratos "escaneados" con su verdad conocida.

Para qué sirve: probar que el software funciona de punta a punta y que el arnés de
medición mide bien, ANTES de tener los documentos reales.

Para qué NO sirve: decir qué tan bien va a leer los contratos de la Legislatura. Un
escaneo real es peor que esto —fotocopias de fotocopias, sellos de tinta corrida,
papel amarillo, grapas, manuscrito—. Los números del §12 del pliego se miden con los
50 contratos reales y su transcripción a mano. Esto es el banco de pruebas del
software, no del corpus.

Las personas son inventadas y los CUIL están construidos para que NO sean válidos
(el dígito verificador es deliberadamente incorrecto), justamente para que no puedan
confundirse con datos de una persona real.
"""
from __future__ import annotations

import argparse
import csv
import random
from datetime import date, timedelta
from pathlib import Path

import fitz
from PIL import Image, ImageFilter

APELLIDOS = ["ALMADA", "BENÍTEZ", "CORREA", "DUARTE", "ESQUIVEL", "FRANCO", "GAUNA",
             "HEREÑÚ", "IRIGOYEN", "JAUREGUI", "LEDESMA", "MONZÓN", "NÚÑEZ", "OJEDA",
             "PAIVA", "QUIROGA", "RAMÍREZ", "SOSA", "TROCHE", "URQUIZA"]
NOMBRES = ["Rosa I.", "Julio C.", "Silvia N.", "Marcelo A.", "Ana P.", "Héctor D.",
           "Lucía M.", "Ramón E.", "Gabriela S.", "Osvaldo F.", "Noelia B.", "Ariel G."]
CARGOS = ["ASESOR TÉCNICO", "AUXILIAR ADMINISTRATIVO", "ASISTENTE DE BLOQUE",
          "PERSONAL DE MAESTRANZA", "ASESOR LETRADO", "OPERADOR INFORMÁTICO"]


def cuil_invalido(rng: random.Random, prefijo: str) -> str:
    """CUIL con formato correcto y dígito verificador ROTO a propósito."""
    cuerpo = "".join(str(rng.randint(0, 9)) for _ in range(8))
    return f"{prefijo}-{cuerpo}-{rng.choice('0123456789')}"


def dibujar(pdf: Path, d: dict) -> None:
    doc = fitz.open()
    pag = doc.new_page(width=595, height=842)          # A4 en puntos

    def txt(x, y, s, size=11, font="times-roman", color=(0.08, 0.09, 0.10)):
        pag.insert_text((x, y), s, fontsize=size, fontname=font, color=color)

    def rotulo(x, y, s):
        txt(x, y, s, size=7.5, font="helv", color=(0.42, 0.43, 0.45))

    def linea(x0, y, x1):
        pag.draw_line(fitz.Point(x0, y), fitz.Point(x1, y),
                      color=(0.72, 0.71, 0.68), width=0.7)

    txt(60, 78, "HONORABLE LEGISLATURA DE LA PROVINCIA", size=9, font="helv",
        color=(0.35, 0.36, 0.38))
    txt(60, 96, d["camara_texto"], size=10, font="helv", color=(0.35, 0.36, 0.38))
    pag.draw_line(fitz.Point(60, 106), fitz.Point(535, 106),
                  color=(0.55, 0.55, 0.55), width=1.1)
    txt(60, 140, "CONTRATO DE LOCACIÓN DE SERVICIOS", size=15, font="helv")
    txt(430, 140, f"N° {d['nro_contrato']}", size=11, font="cour")

    txt(60, 178, "Entre la Cámara referida, por una parte, y la persona que se identifica", size=10)
    txt(60, 194, "seguidamente, por la otra, se conviene el presente contrato:", size=10)

    rotulo(60, 232, "APELLIDO Y NOMBRE")
    txt(60, 250, d["nombre"], size=12, font="cour");           linea(60, 256, 330)
    rotulo(360, 232, "CUIL")
    txt(360, 250, d["documento"] or "", size=11, font="cour"); linea(360, 256, 535)

    rotulo(60, 292, "CARGO / FUNCIÓN")
    txt(60, 310, d["cargo"], size=11, font="cour");            linea(60, 316, 400)

    rotulo(60, 352, "DESDE")
    txt(60, 370, d["inicio_txt"], size=12, font="cour");       linea(60, 376, 195)
    rotulo(230, 352, "HASTA")
    txt(230, 370, d["fin_txt"] or "", size=12, font="cour");   linea(230, 376, 365)

    rotulo(60, 412, "RETRIBUCIÓN MENSUAL")
    txt(60, 432, d["monto_txt"], size=13, font="cour");        linea(60, 440, 260)

    txt(60, 486, "El contratado prestará servicios en las dependencias que la Cámara", size=10)
    txt(60, 502, "determine, sin relación de dependencia y por el plazo estipulado.", size=10)
    txt(60, 518, "La retribución se abonará por mes vencido conforme la normativa vigente.", size=10)

    pag.draw_line(fitz.Point(330, 700), fitz.Point(520, 700),
                  color=(0.72, 0.71, 0.68), width=0.7)
    txt(330, 714, "FIRMA DEL CONTRATADO", size=7.5, font="helv", color=(0.42, 0.43, 0.45))

    # Sello de mesa de entradas encima del campo indicado: caso difícil real.
    if d.get("sello_sobre"):
        caja = {"monto": (52, 408, 268, 452), "fin": (222, 348, 372, 392)}[d["sello_sobre"]]
        r = fitz.Rect(*caja)
        pag.draw_rect(r, color=(0.32, 0.25, 0.45), width=1.6)
        pag.insert_textbox(r, "\nMESA DE ENTRADAS", fontsize=9, fontname="helv",
                           color=(0.32, 0.25, 0.45), align=1)

    doc.save(pdf); doc.close()


def hoja_suelta(pdf: Path, titulo: str, lineas: list[str]) -> None:
    """
    Una foja de relleno: carátula de expediente o anexo.

    Existe para que el corpus de prueba tenga documentos de VARIAS páginas, que es como
    van a llegar los contratos reales. Con una sola página, media docena de errores del
    visor y del anclaje quedan escondidos.
    """
    doc = fitz.open()
    pag = doc.new_page(width=595, height=842)
    pag.insert_text((60, 96), titulo, fontsize=13, fontname="helv", color=(0.2, 0.21, 0.23))
    pag.draw_line(fitz.Point(60, 110), fitz.Point(535, 110), color=(0.55, 0.55, 0.55), width=1)
    y = 150
    for l in lineas:
        pag.insert_text((60, y), l, fontsize=10, fontname="times-roman",
                        color=(0.15, 0.16, 0.18))
        y += 22
    doc.save(pdf); doc.close()


def a_escaneo(pdf_limpio: Path, destino: Path, semilla: int, calidad: str,
              extras: list[Path] | None = None, dpi: int = 200,
              binario: bool = False) -> None:
    """
    Rasteriza y degrada para simular un escaneo. El PDF final es solo imagen.

    `extras` son fojas adicionales: una tupla (antes, después) del contrato. Se
    rasterizan igual, así el documento entero queda como un escaneo de varias hojas.

    `dpi` y `binario` son las dos perillas que de verdad tiene un escáner de oficina:
    la resolución y el "modo texto" en blanco y negro puro. Se pueden barrer para medir
    hasta dónde aguanta el sistema (ver herramientas/barrido_calidad.py).

    La degradación usa un generador propio sembrado por documento, no el `rng` global:
    así el mismo contrato sale con el mismo temblor y las mismas motas a cualquier DPI,
    y la comparación entre resoluciones no arrastra otra variable.
    """
    paginas_fuente = list(extras[0]) + [pdf_limpio] + list(extras[1]) if extras else [pdf_limpio]

    doc = fitz.open()
    for i, fuente in enumerate(paginas_fuente):
        with fitz.open(fuente) as f:
            pix = f[0].get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72))
            png = destino.with_suffix(f".tmp{i}.png")
            pix.save(png)
        _degradar_y_pegar(doc, png, destino, random.Random(semilla * 100 + i),
                          calidad, i, binario)
        png.unlink(missing_ok=True)
    doc.save(destino, deflate=True); doc.close()


def _degradar_y_pegar(doc, png: Path, destino: Path, rng: random.Random,
                      calidad: str, i: int, binario: bool = False) -> None:
    im = Image.open(png).convert("L")
    # El desenfoque y las motas se expresan en milímetros de papel, no en píxeles, así
    # que escalan con la resolución. Si no, a 300 DPI el mismo desenfoque taparía la
    # mitad de letra que a 100 y estaríamos midiendo dos degradaciones distintas.
    escala = im.width / (595 / 72 * 200)               # 1,0 = la referencia de 200 DPI
    if calidad == "malo":
        im = im.rotate(rng.uniform(-1.4, 1.4), resample=Image.BICUBIC,
                       fillcolor=248, expand=False)
        im = im.filter(ImageFilter.GaussianBlur(0.7 * escala))
        px = im.load()
        for _ in range(int(im.width * im.height * 0.004)):        # motas de fotocopia
            px[rng.randrange(im.width), rng.randrange(im.height)] = rng.randrange(0, 90)
        im = im.point(lambda v: max(0, min(255, int((v - 128) * 1.18 + 128) - 14)))
    elif calidad == "regular":
        im = im.rotate(rng.uniform(-0.5, 0.5), resample=Image.BICUBIC,
                       fillcolor=250, expand=False)
        im = im.filter(ImageFilter.GaussianBlur(0.35 * escala))

    if binario:
        # "Modo texto" de un escáner de oficina: un umbral fijo y todo a un bit. Lo que
        # queda por debajo del umbral se pierde para siempre, no hay software que lo
        # recupere. Es el ajuste por defecto de muchas máquinas, por eso vale medirlo.
        im = im.point(lambda v: 255 if v > 150 else 0).convert("1").convert("L")

    jpg = destino.with_suffix(f".tmp{i}.jpg")
    im.convert("RGB").save(jpg, "JPEG", quality={"bueno": 88, "regular": 74, "malo": 58}[calidad])
    pag = doc.new_page(width=595, height=842)
    pag.insert_image(fitz.Rect(0, 0, 595, 842), filename=str(jpg))
    jpg.unlink(missing_ok=True)


def construir_poblacion(rng: random.Random, n: int) -> list[dict]:
    """Arma la población con casos que el análisis TIENE que encontrar."""
    personas = []
    for i in range(20):
        ap, no = APELLIDOS[i], rng.choice(NOMBRES)
        personas.append({
            "nombre": f"{ap}, {no}",
            "documento": cuil_invalido(rng, rng.choice(["20", "23", "27"])),
        })

    filas: list[dict] = []
    base = date(2019, 1, 1)

    def contrato(p, camara, ini, fin, **extra):
        monto = rng.choice([74200, 88300, 96750, 118400, 164900, 182400, 210000])
        d = {
            "persona": p, "camara": camara,
            "camara_texto": "CÁMARA DE DIPUTADOS" if camara == "A" else "CÁMARA DE SENADORES",
            "nombre": p["nombre"], "documento": p["documento"],
            "cargo": rng.choice(CARGOS),
            "inicio": ini, "fin": fin,
            "monto_centavos": monto * 100,
            "nro_contrato": f"{camara}-{len(filas)+1:04d}",
            "calidad": rng.choices(["bueno", "regular", "malo"], weights=[5, 3, 2])[0],
        }
        d.update(extra)
        filas.append(d)
        return d

    # 1. Superposición ENTRE cámaras: el hallazgo central del Caso A.
    for p in personas[:4]:
        ini = base + timedelta(days=rng.randrange(0, 900))
        contrato(p, "A", ini, ini + timedelta(days=365))
        contrato(p, "B", ini + timedelta(days=rng.randrange(60, 240)),
                 ini + timedelta(days=rng.randrange(400, 600)))

    # 2. Superposición DENTRO de una misma cámara.
    for p in personas[4:7]:
        ini = base + timedelta(days=rng.randrange(0, 900))
        contrato(p, "A", ini, ini + timedelta(days=180))
        contrato(p, "A", ini + timedelta(days=rng.randrange(30, 150)),
                 ini + timedelta(days=330))

    # 3. Misma persona con el nombre escrito distinto pero el MISMO CUIL:
    #    la clave fuerte los une sola, sin intervención humana.
    p = personas[7]
    ini = base + timedelta(days=400)
    contrato(p, "A", ini, ini + timedelta(days=200))
    contrato({"nombre": p["nombre"].replace(",", " ,"), "documento": p["documento"]},
             "B", ini + timedelta(days=100), ini + timedelta(days=300))

    # 4. Nombres parecidos SIN documento: NUNCA se fusionan solos. Van a la cola.
    p = personas[8]
    apellido = p["nombre"].split(",")[0]
    contrato({"nombre": f"{apellido}, Silvia N.", "documento": None}, "B",
             base + timedelta(days=200), base + timedelta(days=500))
    contrato({"nombre": f"{apellido}, Silvia Noemí", "documento": None}, "B",
             base + timedelta(days=600), base + timedelta(days=800))

    # 5. Fecha imposible: el fin antes del inicio.
    p = personas[9]
    contrato(p, "A", date(2022, 6, 1), date(2021, 12, 31))

    # 6. Sello de mesa de entradas tapando un campo crítico.
    contrato(personas[10], "A", date(2020, 3, 1), date(2020, 12, 31),
             sello_sobre="monto", calidad="malo")
    contrato(personas[11], "B", date(2021, 4, 1), date(2021, 11, 30),
             sello_sobre="fin", calidad="malo")

    # 7. Contrato sin fecha de fin en el formulario: ausente, no ilegible.
    contrato(personas[12], "A", date(2023, 2, 1), None)

    # Relleno hasta n, sin superposiciones buscadas.
    while len(filas) < n:
        p = rng.choice(personas)
        ini = base + timedelta(days=rng.randrange(0, 1600))
        contrato(p, rng.choice(["A", "B"]), ini, ini + timedelta(days=rng.choice([90, 180, 365])))
    return filas[:n]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--destino", default="datos/corpus-sintetico")
    ap.add_argument("--cantidad", type=int, default=50)
    ap.add_argument("--semilla", type=int, default=1974)
    ap.add_argument("--dpi", type=int, default=200,
                    help="resolución del escaneo simulado (la perilla del escáner)")
    ap.add_argument("--binario", action="store_true",
                    help='simula el "modo texto" en blanco y negro puro de un escáner')
    ap.add_argument("--calidad", choices=["bueno", "regular", "malo"], default=None,
                    help="fija la calidad de TODOS los documentos, en vez de mezclarlas")
    a = ap.parse_args()

    rng = random.Random(a.semilla)
    dest = Path(a.destino); dest.mkdir(parents=True, exist_ok=True)
    tmp = dest / "_limpio.pdf"

    filas = construir_poblacion(rng, a.cantidad)
    if a.calidad:
        for d in filas:
            d["calidad"] = a.calidad
    caratula = dest / "_caratula.pdf"
    anexo = dest / "_anexo.pdf"
    hoja_suelta(caratula, "EXPEDIENTE ADMINISTRATIVO",
                ["Actuaciones remitidas por la Dirección de Personal.",
                 "Se agrega copia del contrato suscripto y su documentación respaldatoria.",
                 "Fojas útiles: tres."])
    hoja_suelta(anexo, "ANEXO — CONSTANCIAS",
                ["Se acompaña constancia de inscripción y declaración jurada.",
                 "No se registran observaciones de la Dirección de Asuntos Jurídicos."])

    referencia = []
    for i, d in enumerate(filas, start=1):
        d["inicio_txt"] = d["inicio"].strftime("%d/%m/%Y")
        d["fin_txt"] = d["fin"].strftime("%d/%m/%Y") if d["fin"] else ""
        d["monto_txt"] = f"$ {d['monto_centavos']//100:,}".replace(",", ".") + ",00"
        nombre_archivo = f"contrato_{d['camara']}_{i:04d}.pdf"
        dibujar(tmp, d)
        # Un tercio de los documentos viene con carátula y anexo, o sea que el
        # formulario NO está en la primera foja. Es como llegan los expedientes reales.
        if i % 3 == 0:
            extras = ([caratula], [anexo]); d["fojas"] = 3
        elif i % 7 == 0:
            extras = ([caratula], []); d["fojas"] = 2
        else:
            extras = None; d["fojas"] = 1
        a_escaneo(tmp, dest / nombre_archivo, a.semilla + i, d["calidad"], extras,
                  dpi=a.dpi, binario=a.binario)
        referencia.append({
            "archivo": nombre_archivo,
            "camara": d["camara"],
            "nombre": d["nombre"],
            "documento": d["documento"] or "",
            "fecha_inicio": d["inicio"].isoformat(),
            "fecha_fin": d["fin"].isoformat() if d["fin"] else "",
            "monto_centavos": d["monto_centavos"],
            "calidad_simulada": d["calidad"],
            "dpi_simulado": a.dpi,
            "binario": int(a.binario),
            "fojas": d["fojas"],
        })
    tmp.unlink(missing_ok=True)
    caratula.unlink(missing_ok=True); anexo.unlink(missing_ok=True)

    ref = dest / "referencia.csv"
    with open(ref, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(referencia[0].keys()))
        w.writeheader(); w.writerows(referencia)

    modo = "blanco y negro" if a.binario else "escala de grises"
    print(f"{len(referencia)} contratos sintéticos en {dest} ({a.dpi} DPI, {modo})")
    print(f"verdad conocida en {ref}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
