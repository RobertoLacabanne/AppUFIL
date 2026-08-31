"""
Capa 1 — Extracción de texto con coordenadas.

Clasificador de ruta por página:
  * capa de texto nativa  -> se lee directo del PDF (exacto, confianza 1,0)
  * escaneo               -> OCR clásico en CPU, en DOS configuraciones distintas
  * página compleja       -> modelo de visión local (ver capa1_vlm.py)

Toda ruta devuelve lo mismo: una lista de `Palabra` con su recuadro en PUNTOS PDF,
origen arriba-izquierda. Esa unidad común es lo que hace posible comparar rutas
entre sí y anclar cualquier dato a su lugar en la imagen (restricción 4).
"""
from __future__ import annotations

import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import fitz
import pytesseract
from PIL import Image

from . import config
from .capa0_ingesta import carpeta_derivados
from .db import ahora


@dataclass
class Palabra:
    texto: str
    x0: float; y0: float; x1: float; y1: float   # puntos PDF
    conf: float                                   # 0..1


@dataclass
class Lectura:
    ruta: str
    motor: str
    version: str
    palabras: list[Palabra]
    confianza: float
    ms: int


# ─────────────────────────────────────────────────────────── render de página ──
def detectar_rotacion(png: Path) -> int:
    """
    Cuántos grados hay que girar la página para dejarla derecha.

    Alguien apoya la hoja de costado en el escáner y esa foja se pierde entera: el motor
    no reconoce una sola palabra y el contrato desaparece sin dejar rastro. Pasa seguido
    y es barato de arreglar.

    Usa el detector de orientación de Tesseract (`osd`). Devuelve 0 si no está seguro:
    girar una página derecha sería peor que no girar la torcida.
    """
    try:
        with Image.open(png) as im:
            datos = pytesseract.image_to_osd(im, output_type=pytesseract.Output.DICT)
    except Exception:
        return 0
    grados = int(datos.get("rotate", 0)) % 360
    confianza = float(datos.get("orientation_conf", 0) or 0)
    if grados in (90, 180, 270) and confianza >= config.CONFIANZA_ORIENTACION:
        return grados
    return 0


def tiene_tinta(png: Path) -> bool:
    """¿La página tiene algo escrito? Una hoja en blanco no se endereza ni se interroga."""
    try:
        with Image.open(png) as im:
            h = im.convert("L").histogram()
    except Exception:
        return True
    total = sum(h)
    return bool(total) and sum(h[:200]) / total > 0.004


def render_pagina(ruta_pdf: Path, sha: str, nro: int) -> tuple[Path, float, int]:
    """
    Renderiza la página a PNG en datos/derivados/. El original NO se toca.

    No endereza acá: la orientación se corrige recién si la lectura sale mal
    (ver `leer_documento`). Preguntarle a Tesseract la orientación de CADA página
    cuesta más de un segundo por página, y las páginas al revés son la excepción:
    sobre el corpus de prueba, pagar eso siempre duplicaba el tiempo total.
    """
    destino = carpeta_derivados(sha) / f"p{nro:04d}.png"
    marca = destino.with_suffix(".rot")
    if destino.exists():
        rot = int(marca.read_text()) if marca.exists() else 0
        return destino, config.ESCALA_RENDER, rot

    with fitz.open(ruta_pdf) as doc:
        pag = doc[nro - 1]
        pix = pag.get_pixmap(matrix=fitz.Matrix(config.ESCALA_RENDER, config.ESCALA_RENDER))
        pix.save(destino)
    marca.write_text("0")
    return destino, config.ESCALA_RENDER, 0


def _girar(png: Path, grados: int) -> None:
    """Gira el derivado. PIL gira en sentido antihorario; acá se piensa en horario."""
    with Image.open(png) as im:
        im.rotate(-grados, expand=True).save(png)


def enderezar_si_mejora(png: Path, escala: float,
                        primera: "Lectura") -> tuple[int, "Lectura"]:
    """
    Endereza la página sólo si al releerla sale MEJOR. Devuelve (grados, lectura buena).

    El detector de orientación de Tesseract acierta el ÁNGULO con mucha seguridad sobre
    una página densa (confianza 25) y con poca sobre una hoja escasa (1,3). Pero en
    ninguno de los dos casos se equivocó diciendo que una página derecha estaba torcida.

    De ahí las dos reglas:

      * si el detector dice que está derecha, se le cree y no se prueba nada;
      * si sugiere un ángulo, la decisión NO la toma él sino el RESULTADO: se gira, se
        relee, y sólo se queda girada si lee mejor. Si su ángulo no mejora se prueban
        los otros dos, y si ninguno sirve la página vuelve a como estaba.

    Así el umbral de confianza del detector deja de ser crítico, y las páginas
    simplemente borrosas no pagan lecturas de más.
    """
    sugerido = detectar_rotacion(png)
    if not sugerido:
        # El detector dice que está derecha. Medido: sobre páginas derechas nunca
        # devolvió un ángulo equivocado, ni densas ni escasas. Entonces se le cree y no
        # se barren los tres ángulos: hacerlo costaba tres lecturas de más en cada
        # página borrosa —un tercio del tiempo total del lote— para no encontrar nada.
        return 0, primera

    orden = [sugerido] + [g for g in (90, 180, 270) if g != sugerido]

    mejor_rot, mejor_lec, acumulado = 0, primera, 0
    for g in orden:
        paso = (g - acumulado) % 360
        if paso:
            _girar(png, paso)
            acumulado = g
        try:
            lec = leer_ocr(png, escala, "ocr_a")
        except Exception:
            continue
        if lec.confianza > mejor_lec.confianza + config.MEJORA_MINIMA_GIRO:
            mejor_rot, mejor_lec = g, lec
            break                      # con una que mejore claramente alcanza

    # Dejar la imagen en el ángulo elegido (o volver al original si ninguno sirvió).
    paso = (mejor_rot - acumulado) % 360
    if paso:
        _girar(png, paso)
    png.with_suffix(".rot").write_text(str(mejor_rot))
    return mejor_rot, mejor_lec


def lectura_pobre(lec: "Lectura") -> bool:
    """
    ¿Esta lectura salió tan mal que vale la pena sospechar de la orientación?

    Lo que separa una página derecha de una de costado es la CONFIANZA, no la cantidad
    de palabras. Medido sobre el corpus de prueba:

        página derecha (formulario, carátula o separador) ... 0,91 a 0,96
        página de costado o al revés ........................ 0,40 a 0,54

    La cantidad de palabras no sirve como señal, y de hecho engaña: una página rotada
    devuelve MÁS palabras que una derecha (306 contra 92), porque el motor parte los
    trazos verticales en fragmentos sueltos. Una carátula corta y derecha da 22 palabras
    con confianza 0,96 y no tiene nada de malo.
    """
    return lec.confianza < config.CONFIANZA_SOSPECHA


# ────────────────────────────────────────────────────────────── ruta: nativa ──
def leer_nativo(ruta_pdf: Path, nro: int) -> Lectura:
    t0 = time.perf_counter()
    palabras: list[Palabra] = []
    with fitz.open(ruta_pdf) as doc:
        for x0, y0, x1, y1, w, *_ in doc[nro - 1].get_text("words"):
            if w.strip():
                palabras.append(Palabra(w, x0, y0, x1, y1, 1.0))
    return Lectura("nativo", "pymupdf", fitz.VersionBind, palabras, 1.0,
                   int((time.perf_counter() - t0) * 1000))


# ───────────────────────────────────────────────────────────────── ruta: OCR ──
_VER_TESS = str(pytesseract.get_tesseract_version()).split()[0]


def leer_ocr(png: Path, escala: float, ruta: str) -> Lectura:
    t0 = time.perf_counter()
    cfg = config.OCR_CONFIG[ruta]
    with Image.open(png) as im:
        datos = pytesseract.image_to_data(
            im, lang=config.OCR_IDIOMA, config=cfg,
            output_type=pytesseract.Output.DICT,
        )
    palabras: list[Palabra] = []
    confs: list[float] = []
    for i, texto in enumerate(datos["text"]):
        texto = (texto or "").strip()
        if not texto:
            continue
        try:
            c = float(datos["conf"][i])
        except (TypeError, ValueError):
            c = -1.0
        if c < 0:
            continue
        conf = c / 100.0
        x, y = datos["left"][i] / escala, datos["top"][i] / escala
        w, h = datos["width"][i] / escala, datos["height"][i] / escala
        palabras.append(Palabra(texto, x, y, x + w, y + h, conf))
        confs.append(conf)
    media = sum(confs) / len(confs) if confs else 0.0
    return Lectura(ruta, "tesseract", _VER_TESS, palabras, media,
                   int((time.perf_counter() - t0) * 1000))


# ─────────────────────────────────────────────────────────────── orquestación ──
def rutas_para(tiene_texto: bool, con_vlm: bool) -> list[str]:
    """
    Qué rutas se corren sobre esta página.

    Siempre al menos dos, para que la comparación exista (doble lectura). Cuando hay
    capa de texto nativa, la segunda lectura es OCR sobre el render: son motores
    genuinamente distintos y la comparación vale mucho.
    """
    rutas = ["nativo", "ocr_a"] if tiene_texto else ["ocr_a", "ocr_b"]
    if con_vlm:
        rutas.append("vlm")
    return rutas


def _leer_pagina(ruta_pdf: Path, sha: str, nro: int, tiene_texto: bool,
                 con_vlm: bool) -> dict:
    """
    Todo el trabajo pesado de UNA página: render, enderezado y lecturas.

    No toca la base. Se lo puede correr en paralelo y después escribir los resultados de
    a uno, que es lo que hace `leer_lote`.
    """
    png, escala, rot = render_pagina(ruta_pdf, sha, nro)
    rutas = rutas_para(tiene_texto, con_vlm)

    # Primera pasada de OCR. Si sale con confianza baja y la hoja tiene tinta, el
    # sospechoso número uno es que esté de costado: se endereza el derivado y se relee.
    # Si salió bien, esta misma lectura se aprovecha y no se repite.
    previas: dict[str, Lectura] = {}
    if not tiene_texto and not rot and "ocr_a" in rutas:
        try:
            primera = leer_ocr(png, escala, "ocr_a")
            if lectura_pobre(primera) and tiene_tinta(png):
                rot, primera = enderezar_si_mejora(png, escala, primera)
            previas["ocr_a"] = primera
        except Exception:
            pass

    # Si se giró, el alto y el ancho se dan vuelta. Las coordenadas de los campos salen
    # de este derivado, así que la página tiene que medir lo que mide ACÁ.
    with Image.open(png) as im:
        ancho_pt, alto_pt = im.width / escala, im.height / escala

    lecturas, fallas = [], []
    for ruta in rutas:
        try:
            if ruta in previas:
                lec = previas[ruta]
            elif ruta == "nativo":
                lec = leer_nativo(ruta_pdf, nro)
            elif ruta == "vlm":
                from .capa1_vlm import leer_vlm
                lec = leer_vlm(png, escala)
            else:
                lec = leer_ocr(png, escala, ruta)
            lecturas.append(lec)
        except Exception as e:
            fallas.append(f"pág {nro} ruta {ruta}: {type(e).__name__}: {e}")

    return {"nro": nro, "png": png, "escala": escala, "rot": rot,
            "ancho_pt": ancho_pt, "alto_pt": alto_pt,
            "lecturas": lecturas, "fallas": fallas}


def _guardar_pagina(cx: sqlite3.Connection, sha: str, pagina_id: int, r: dict) -> int:
    """Escribe en la base lo que produjo `_leer_pagina`. Siempre en un solo hilo."""
    cx.execute("""UPDATE pagina SET render=?, render_escala=?, rotacion=?,
                         ancho_pt=?, alto_pt=? WHERE id=?""",
               (str(r["png"]), r["escala"], r["rot"], r["ancho_pt"], r["alto_pt"], pagina_id))
    for detalle in r["fallas"]:
        cx.execute("INSERT INTO excepcion (sha256, clase, detalle, creado_en) VALUES (?,?,?,?)",
                   (sha, "lectura_fallida", detalle, ahora()))
    hechas = 0
    for lec in r["lecturas"]:
        if cx.execute("SELECT 1 FROM lectura WHERE pagina_id=? AND ruta=?",
                      (pagina_id, lec.ruta)).fetchone():
            continue
        lid = cx.execute(
            """INSERT INTO lectura (pagina_id, ruta, motor, version, confianza, ms, creado_en)
               VALUES (?,?,?,?,?,?,?)""",
            (pagina_id, lec.ruta, lec.motor, lec.version, lec.confianza, lec.ms, ahora())
        ).lastrowid
        cx.executemany(
            """INSERT INTO palabra (lectura_id, orden, texto, x0, y0, x1, y1, conf)
               VALUES (?,?,?,?,?,?,?,?)""",
            [(lid, i, p.texto, p.x0, p.y0, p.x1, p.y1, p.conf)
             for i, p in enumerate(lec.palabras)])
        hechas += 1
    return hechas


def leer_lote(cx: sqlite3.Connection, shas: list[str], *, con_vlm: bool = False,
              avance=None, seguir=None) -> dict:
    """
    Lee varios archivos repartiendo las PÁGINAS entre los núcleos disponibles.

    El OCR es lo que domina el tiempo del sistema y cada página es independiente de las
    demás, así que reparte casi perfecto: medido sobre esta máquina de cuatro núcleos,
    4,1 veces más rápido. Para un lote de cinco mil contratos es la diferencia entre
    seis horas y hora y media.

    Se reparte por PÁGINA y no por archivo porque la mayoría de los contratos tiene una
    o dos: repartiendo por archivo, los núcleos quedarían ociosos esperando al documento
    más largo.

    Tesseract usa varios hilos por su cuenta y eso pelea con el pool. Limitarlo a uno y
    correr varios en paralelo rinde bastante más.

    `seguir` es una función que se consulta entre página y página: si devuelve False, se
    corta. Existe porque un lote grande son horas —cinco mil contratos son hora y media
    en cuatro núcleos— y arrancar sobre el lote equivocado sin poder frenarlo dejaba una
    sola salida: matar el proceso. Cortar acá es seguro: lo leído hasta ese momento está
    confirmado y al reanudar se retoma desde la página que faltaba.
    """
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")
    trabajos = []
    for sha in shas:
        fila = cx.execute("SELECT ruta_original FROM archivo WHERE sha256=?", (sha,)).fetchone()
        if not fila:
            continue
        ruta_pdf = Path(fila["ruta_original"])
        # Sólo las páginas que todavía no se leyeron. Reanudar tiene que retomar donde
        # quedó, no volver a empezar: en un lote grande eso es una hora de trabajo.
        for pag in cx.execute(
            """SELECT id, nro, tiene_texto FROM pagina p
                WHERE p.sha256=? AND NOT EXISTS
                      (SELECT 1 FROM lectura l WHERE l.pagina_id = p.id)
                ORDER BY nro""", (sha,)
        ).fetchall():
            trabajos.append((sha, ruta_pdf, pag["id"], pag["nro"], bool(pag["tiene_texto"])))

    total, hechas, fallidas = len(trabajos), 0, 0
    if not trabajos:
        return {"paginas": 0, "lecturas": 0, "fallidas": 0}

    obreros = max(1, min(config.NUCLEOS_OCR, len(trabajos)))
    lecturas = 0
    with ThreadPoolExecutor(max_workers=obreros) as pool:
        futuros = {
            pool.submit(_leer_pagina, ruta_pdf, sha, nro, con_texto, con_vlm):
                (sha, pagina_id, nro)
            for sha, ruta_pdf, pagina_id, nro, con_texto in trabajos
        }
        cortado = False
        for fut in as_completed(futuros):
            if seguir is not None and not seguir():
                # Se cancela lo que todavía no arrancó. Lo que ya está corriendo
                # termina —matar un Tesseract a mitad de página deja basura— pero no
                # se le manda nada más.
                cortado = True
                for otro in futuros:
                    otro.cancel()
                break
            sha, pagina_id, nro = futuros[fut]
            try:
                lecturas += _guardar_pagina(cx, sha, pagina_id, fut.result())
            except Exception as e:
                fallidas += 1
                cx.execute("""INSERT INTO excepcion (sha256, clase, detalle, creado_en)
                              VALUES (?,?,?,?)""",
                           (sha, "lectura_fallida",
                            f"pág {nro}: {type(e).__name__}: {e}", ahora()))
            hechas += 1
            # Confirmar cada tanto, no al final. Si se corta la luz o alguien cierra la
            # terminal, lo leído hasta ahí queda guardado y al reanudar se retoma desde
            # esa página. Antes, un lote de noventa minutos cortado en el ochenta y cinco
            # perdía las noventa.
            if hechas % config.CONFIRMAR_CADA == 0:
                cx.commit()
            if avance:
                avance(hechas, total)
    cx.commit()
    return {"paginas": total, "lecturas": lecturas, "fallidas": fallidas,
            "hechas": hechas, "cortado": cortado}


def leer_documento(cx: sqlite3.Connection, sha: str, *, con_vlm: bool = False) -> int:
    """Lee todas las páginas de un archivo. Envoltorio de `leer_lote` para un solo archivo."""
    return leer_lote(cx, [sha], con_vlm=con_vlm)["lecturas"]


def _leer_documento_viejo(cx: sqlite3.Connection, sha: str, *, con_vlm: bool = False) -> int:
    """Versión secuencial, conservada para comparar. No se usa."""
    fila = cx.execute("SELECT ruta_original FROM archivo WHERE sha256=?", (sha,)).fetchone()
    if not fila:
        raise KeyError(f"archivo no ingerido: {sha}")
    ruta_pdf = Path(fila["ruta_original"])

    hechas = 0
    for pag in cx.execute(
        "SELECT id, nro, tiene_texto FROM pagina WHERE sha256=? ORDER BY nro", (sha,)
    ).fetchall():
        png, escala, rot = render_pagina(ruta_pdf, sha, pag["nro"])
        rutas = rutas_para(bool(pag["tiene_texto"]), con_vlm)

        # Primera pasada de OCR. Si sale con confianza baja y la hoja tiene tinta, el
        # sospechoso número uno es que esté de costado: se endereza el derivado y se
        # relee. Si salió bien, esta misma lectura se aprovecha y no se repite: hacerla
        # dos veces costaba más que el enderezado que vino a evitar.
        previas: dict[str, Lectura] = {}
        if not pag["tiene_texto"] and not rot and "ocr_a" in rutas:
            try:
                primera = leer_ocr(png, escala, "ocr_a")
                if lectura_pobre(primera) and tiene_tinta(png):
                    rot, primera = enderezar_si_mejora(png, escala, primera)
                previas["ocr_a"] = primera
            except Exception:
                pass

        # Si se giró, el alto y el ancho se dan vuelta. Las coordenadas de los campos
        # salen de este derivado, así que la página tiene que medir lo que mide ACÁ.
        with Image.open(png) as im:
            ancho_pt, alto_pt = im.width / escala, im.height / escala
        cx.execute("""UPDATE pagina SET render=?, render_escala=?, rotacion=?,
                             ancho_pt=?, alto_pt=? WHERE id=?""",
                   (str(png), escala, rot, ancho_pt, alto_pt, pag["id"]))

        for ruta in rutas:
            if cx.execute("SELECT 1 FROM lectura WHERE pagina_id=? AND ruta=?",
                          (pag["id"], ruta)).fetchone():
                continue
            try:
                if ruta in previas:
                    lec = previas[ruta]
                elif ruta == "nativo":
                    lec = leer_nativo(ruta_pdf, pag["nro"])
                elif ruta == "vlm":
                    from .capa1_vlm import leer_vlm
                    lec = leer_vlm(png, escala)
                else:
                    lec = leer_ocr(png, escala, ruta)
            except Exception as e:
                cx.execute(
                    "INSERT INTO excepcion (sha256, clase, detalle, creado_en) VALUES (?,?,?,?)",
                    (sha, "lectura_fallida",
                     f"pág {pag['nro']} ruta {ruta}: {type(e).__name__}: {e}", ahora()),
                )
                continue

            cur = cx.execute(
                """INSERT INTO lectura (pagina_id, ruta, motor, version, confianza, ms, creado_en)
                   VALUES (?,?,?,?,?,?,?)""",
                (pag["id"], lec.ruta, lec.motor, lec.version, lec.confianza, lec.ms, ahora()),
            )
            lid = cur.lastrowid
            cx.executemany(
                """INSERT INTO palabra (lectura_id, orden, texto, x0, y0, x1, y1, conf)
                   VALUES (?,?,?,?,?,?,?,?)""",
                [(lid, i, p.texto, p.x0, p.y0, p.x1, p.y1, p.conf)
                 for i, p in enumerate(lec.palabras)],
            )
            hechas += 1
    cx.commit()
    return hechas


def palabras_de(cx: sqlite3.Connection, lectura_id: int) -> list[Palabra]:
    return [Palabra(r["texto"], r["x0"], r["y0"], r["x1"], r["y1"], r["conf"])
            for r in cx.execute(
                "SELECT texto,x0,y0,x1,y1,conf FROM palabra WHERE lectura_id=? ORDER BY orden",
                (lectura_id,))]
