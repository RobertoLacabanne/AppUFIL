"""
Capa 2 — Extracción estructurada con anclaje y doble lectura.

Cómo funciona
-------------
El formulario se describe en un PERFIL declarativo (ufil/perfiles/*.json): por cada
campo, qué rótulo lo precede, dónde buscar el valor respecto de ese rótulo, y con qué
parser interpretarlo. Adaptar el sistema a un formulario distinto es editar un JSON,
no tocar código: eso lo puede hacer el escribiente sin llamar a nadie.

Es determinístico y auditable: no hay modelo generativo en el carril de datos, así que
no hay forma de que aparezca un valor que no esté en la página.

Doble lectura
-------------
Cada campo se extrae por TODAS las rutas de lectura disponibles y después se cotejan:

  * dos o más rutas coinciden      -> es un dato
  * dos o más rutas discrepan      -> es un CONFLICTO; no se guarda ningún valor
  * una sola ruta encontró el valor-> se guarda, con la confianza penalizada y
                                      marcado para revisión si el campo es crítico
  * ninguna ruta lo encontró       -> nulo, con motivo

Esa tercera regla es la que sostiene la promesa del §12: un valor de campo crítico
leído por una sola ruta puede estar mal, pero nunca está mal EN SILENCIO.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from . import config
import pytesseract

from .capa1_texto import Palabra, palabras_de
from .capa2_campos import PARSERS, normalizar_cotejo
from .db import ahora

MARGEN_IZQ = 8.0        # puntos que se toleran a la izquierda del rótulo
PENALIZA_UNICA = 0.6          # confianza cuando una sola ruta vio el valor
PENALIZA_DISCREPANCIA = 0.7   # cuando la relectura focalizada discrepa sin seguridad


def cargar_perfil(nombre: str) -> dict:
    return json.loads((config.PERFILES / f"{nombre}.json").read_text(encoding="utf-8"))


def perfiles_disponibles() -> list[str]:
    return sorted(p.stem for p in config.PERFILES.glob("*.json"))


def perfiles_a_probar(nombre: str) -> list[dict]:
    """
    Qué perfiles se prueban. Con "auto" (lo normal), todos.

    El formulario cambia entre cámaras y entre años: los mismos seis campos con otros
    rótulos impresos. Probar todos y quedarse con el que más campos encuentra evita
    tener que adivinar de antemano qué formato trae cada PDF, y hace que dar de alta un
    formato nuevo sea copiar un JSON.
    """
    if nombre and nombre != "auto":
        return [cargar_perfil(nombre)]
    return [cargar_perfil(n) for n in perfiles_disponibles()]


def puntaje(hallazgos: dict) -> tuple[int, int]:
    """
    Qué tan bien le fue a un perfil en este tramo.

    Primero cuántos campos CRÍTICOS resolvió, después cuántos en total. Un perfil que
    saca el monto y las fechas le gana a uno que saca tres campos accesorios.
    """
    criticos = sum(1 for c in config.CAMPOS_CRITICOS
                   if c in hallazgos and hallazgos[c].norm is not None)
    todos = sum(1 for h in hallazgos.values() if h.norm is not None)
    return (criticos, todos)


@dataclass
class Hallazgo:
    literal: str | None
    norm: str | None
    motivo: str | None
    pagina: int | None
    caja: tuple[float, float, float, float] | None
    conf: float
    lectura_id: int | None
    region: tuple[float, float, float, float] | None = None   # dónde se buscó


# ────────────────────────────────────────────────── geometría sobre palabras ──
def _texto_plano(palabras: list[Palabra]) -> str:
    return normalizar_cotejo(" ".join(p.texto for p in palabras))


SIMILITUD_ROTULO = 0.82   # tolerancia al rótulo mal leído por el OCR


def _buscar_rotulo(palabras: list[Palabra], rotulos: list[str]):
    """
    Busca la secuencia de palabras del rótulo. Devuelve su recuadro, o None.

    El cotejo es tolerante: "APELLlDO Y NOMBRE" con ele minúscula sigue siendo el
    rótulo. Esto NO relaja la restricción 3. El rótulo es texto impreso conocido del
    formulario, que ya sabemos qué dice; lo que se afloja es encontrar dónde está el
    campo, no qué dice el campo. El valor se lee literal y sin tolerancia ninguna.
    """
    normas = [normalizar_cotejo(p.texto) for p in palabras]
    for rot in rotulos:
        objetivo = normalizar_cotejo(rot).split()
        n = len(objetivo)
        objetivo_txt = " ".join(objetivo)
        for i in range(len(palabras) - n + 1):
            ventana = normas[i:i + n]
            if ventana != objetivo:
                if SequenceMatcher(None, " ".join(ventana), objetivo_txt).ratio() < SIMILITUD_ROTULO:
                    continue
            grupo = palabras[i:i + n]
            # Un rótulo está en una sola línea: se descarta el falso positivo que
            # cruza de renglón.
            if max(g.y0 for g in grupo) - min(g.y0 for g in grupo) > 6:
                continue
            return (min(g.x0 for g in grupo), min(g.y0 for g in grupo),
                    max(g.x1 for g in grupo), max(g.y1 for g in grupo))
    return None


def _region(caja_rotulo, spec: dict):
    x0, y0, x1, y1 = caja_rotulo
    if spec.get("region") == "derecha":
        return (x1 + 2, y0 - 4, x1 + 2 + spec["ancho"], y1 + 4)
    return (x0 - MARGEN_IZQ, y1 + 1, x0 - MARGEN_IZQ + spec["ancho"], y1 + spec["alto"])


def _en_renglones(palabras: list[Palabra]) -> list[Palabra]:
    """
    Ordena por renglón y después de izquierda a derecha.

    Agrupar por `round(y/6)` parece equivalente y no lo es: en una página escaneada
    con medio grado de inclinación, dos palabras del mismo renglón caen a los lados
    del corte del bucket y salen invertidas. Eso produjo un error silencioso real en
    la primera corrida ("Héctor ESQUIVEL, D" por "ESQUIVEL, Héctor D."). Acá los
    renglones se arman por solapamiento vertical, que es lo que un renglón es.
    """
    if not palabras:
        return []
    restantes = sorted(palabras, key=lambda p: ((p.y0 + p.y1) / 2, p.x0))
    renglones: list[list[Palabra]] = []
    for p in restantes:
        centro = (p.y0 + p.y1) / 2
        for r in renglones:
            alto = sum(q.y1 - q.y0 for q in r) / len(r)
            centro_r = sum((q.y0 + q.y1) / 2 for q in r) / len(r)
            if abs(centro - centro_r) <= max(alto * 0.6, 3.0):
                r.append(p)
                break
        else:
            renglones.append([p])
    salida: list[Palabra] = []
    for r in sorted(renglones, key=lambda r: min((q.y0 + q.y1) / 2 for q in r)):
        salida.extend(sorted(r, key=lambda q: q.x0))
    return salida


def _palabras_en(region, palabras: list[Palabra]) -> list[Palabra]:
    rx0, ry0, rx1, ry1 = region
    dentro = [p for p in palabras
              if rx0 <= (p.x0 + p.x1) / 2 <= rx1 and ry0 <= (p.y0 + p.y1) / 2 <= ry1]
    return _en_renglones(dentro)


# ──────────────────────────────────────────────────── extracción por ruta ──
def extraer_de_ruta(paginas: list[tuple[int, int, list[Palabra]]], perfil: dict
                    ) -> tuple[dict[str, Hallazgo], str | None, bool]:
    """
    paginas: [(nro, lectura_id, palabras), ...] de una misma ruta.
    Devuelve (hallazgos por campo, cámara detectada, si el perfil aplica).
    """
    plano_total = " ".join(_texto_plano(pw) for _, _, pw in paginas)
    det = perfil.get("deteccion", {}).get("alguno_de", [])
    aplica = (not det) or any(normalizar_cotejo(t) in plano_total for t in det)

    camara = None
    for regla in perfil.get("camara", []):
        if normalizar_cotejo(regla["si_contiene"]) in plano_total:
            camara = regla["valor"]
            break

    hallazgos: dict[str, Hallazgo] = {}
    for spec in perfil["campos"]:
        h = Hallazgo(None, None, "ausente", None, None, 0.0, None, None)
        for nro, lid, palabras in paginas:
            caja_rot = _buscar_rotulo(palabras, spec["rotulo"])
            if not caja_rot:
                continue
            region = _region(caja_rot, spec)
            dentro = _palabras_en(region, palabras)
            bruto = " ".join(p.texto for p in dentro)
            parser = PARSERS[spec["parser"]]
            literal, norm, motivo = parser(bruto)
            if dentro:
                caja = (min(p.x0 for p in dentro), min(p.y0 for p in dentro),
                        max(p.x1 for p in dentro), max(p.y1 for p in dentro))
                conf = min(p.conf for p in dentro)
            else:
                caja, conf = region, 0.0
            h = Hallazgo(literal, norm, motivo, nro, caja, conf, lid, region)
            break
        hallazgos[spec["nombre"]] = h
    return hallazgos, camara, aplica


# ──────────────────────────────────────────────────────── cotejo y guardado ──
# ─────────────────────────────────────────────────── relectura focalizada ──
# Lista de caracteres admisibles por tipo de campo. NO es adivinar el valor: es
# decirle al motor qué alfabeto usa ESE renglón del formulario, y lo sabemos porque lo
# dice el perfil. Un campo de fecha no tiene letras. Restringir el alfabeto es lo que
# le permite a Tesseract distinguir el 7 del 1 en un escaneo mediocre.
#
# El riesgo es real y conviene tenerlo escrito: con el alfabeto restringido, un glifo
# ilegible puede salir como un dígito equivocado pero con confianza alta. Por eso la
# relectura focalizada NO manda. Entra al cotejo como una ruta más, y si discrepa con
# las otras el campo queda en conflicto en lugar de resolverse.
LISTA_CARACTERES = {
    "fecha":     "0123456789/-. ",
    "monto":     "0123456789.,$ ",
    "documento": "0123456789-. ",
}


def relectura_focal(png: Path, escala: float, region_pt, tipo: str) -> Hallazgo | None:
    """Recorta el campo del render, lo agranda, lo binariza y lo relee con atención."""
    from PIL import Image

    from .preproceso import para_campo

    caja_px = tuple(v * escala for v in region_pt)
    cfg = "--oem 1 --psm 7"
    lista = LISTA_CARACTERES.get(tipo)
    if lista:
        cfg += f" -c tessedit_char_whitelist={lista}"
    try:
        with Image.open(png) as im:
            recorte = para_campo(im, caja_px)
        datos = pytesseract.image_to_data(recorte, lang=config.OCR_IDIOMA, config=cfg,
                                          output_type=pytesseract.Output.DICT)
    except Exception:
        return None

    piezas, confs = [], []
    for i, t in enumerate(datos["text"]):
        t = (t or "").strip()
        try:
            c = float(datos["conf"][i])
        except (TypeError, ValueError):
            c = -1.0
        if t and c >= 0:
            piezas.append(t); confs.append(c / 100.0)
    if not piezas:
        return None
    literal, norm, motivo = PARSERS.get(tipo, PARSERS["texto"])(" ".join(piezas))
    return Hallazgo(literal, norm, motivo, None, None,
                    min(confs) if confs else 0.0, None, region_pt)


def _elegir_motivo(motivos: list[str]) -> str:
    for preferido in ("ambiguo", "ilegible", "ausente"):
        if preferido in motivos:
            return preferido
    return "ausente"


# ───────────────────────────────────────────────────────────── segmentación ──
# Un PDF puede traer VARIOS contratos, que es como sale de un escáner de oficina
# cuando se pasa una pila de expedientes de corrido. Sin esto, un archivo con cinco
# contratos producía UN registro que mezclaba el nombre de uno con el monto de otro:
# un contrato inventado, y sin ninguna marca. El peor error posible en este sistema.
MIN_ROTULOS_PARA_SER_FORMULARIO = 2


def pagina_es_formulario(palabras: list[Palabra], perfil: dict) -> bool:
    """
    ¿Esta página es la primera hoja de un contrato?

    Pide dos cosas a la vez: el título del formulario Y al menos dos de sus rótulos.
    Con el título solo no alcanza — una carátula que diga «se agrega copia del contrato
    de locación de servicios» arrancaría un contrato fantasma.
    """
    plano = _texto_plano(palabras)
    marcas = perfil.get("deteccion", {}).get("alguno_de", [])
    if marcas and not any(normalizar_cotejo(t) in plano for t in marcas):
        return False
    hallados = sum(1 for spec in perfil["campos"] if _buscar_rotulo(palabras, spec["rotulo"]))
    return hallados >= MIN_ROTULOS_PARA_SER_FORMULARIO


def segmentar(inicios: list[int], todas: list[int]) -> list[tuple[int, int]]:
    """
    Convierte las páginas donde arranca un contrato en tramos de páginas.

    La carátula que va ANTES del primer contrato se le adjunta a ese primer contrato;
    el anexo que va después de uno se adjunta a ese. Es como está armado el expediente.
    """
    if not inicios:
        return []
    primera, ultima = min(todas), max(todas)
    tramos = []
    for i, arranque in enumerate(inicios):
        desde = primera if i == 0 else arranque
        hasta = (inicios[i + 1] - 1) if i + 1 < len(inicios) else ultima
        tramos.append((desde, hasta))
    return tramos


def _guardar_contrato(cx, sha, doc_id, perfil, resultados, por_pagina) -> dict:
    """Cotejo entre rutas y guardado de los campos de UN contrato."""
    n_campos = n_conf = n_rev = 0
    for spec in perfil["campos"]:
        campo = spec["nombre"]
        critico = campo in config.CAMPOS_CRITICOS
        por = {ruta: res[campo] for ruta, res in resultados.items()}
        con_valor = {r: h for r, h in por.items() if h.norm is not None}

        # ── Tercera lectura: desempate sobre el campo agrandado y binarizado ──
        # Se recorta ajustado AL VALOR que encontraron las rutas de página, no a toda
        # la zona de búsqueda: la zona incluye el filete del formulario, que al
        # binarizar se vuelve una barra negra que el motor lee como caracteres.
        #
        # Y sólo se hace cuando hace falta. Medido sobre el corpus de prueba, correrla
        # de rutina EMPEORA el resultado: cuando las dos rutas de página coinciden con
        # confianza alta ya están bien, y una tercera opinión ruidosa sólo convierte
        # lecturas correctas en conflictos. Donde sí rinde es justo donde hay duda.
        foco_discrepa = False
        conf_pagina = max((h.conf for h in con_valor.values()), default=0.0)
        hay_duda = (not con_valor
                    or len({h.norm for h in con_valor.values()}) > 1
                    or conf_pagina < config.UMBRAL_CONFIANZA)
        # Sólo en campos de alfabeto restringido (fecha, monto, documento). En texto
        # libre la relectura no aporta —medido: pierde contra la lectura de página— y
        # además no hay lista de caracteres que le dé ventaja.
        if critico and hay_duda and spec["parser"] in LISTA_CARACTERES and config.RELECTURA_FOCAL:
            ref = next((h for h in por.values() if h.pagina and (h.caja or h.region)), None)
            if ref and ref.pagina in por_pagina:
                cajas = [h.caja for h in con_valor.values() if h.caja]
                if cajas:
                    recorte = (min(c[0] for c in cajas) - 3, min(c[1] for c in cajas) - 3,
                               max(c[2] for c in cajas) + 3, max(c[3] for c in cajas) + 3)
                else:
                    recorte = ref.region or ref.caja
                png, esc = por_pagina[ref.pagina]
                foc = relectura_focal(png, esc, recorte, spec["parser"])
                if foc and foc.norm is not None:
                    # Llegamos acá sólo porque el campo YA era dudoso, así que iba a la
                    # cola de todos modos. Mostrarle al operador dos candidatas —una de
                    # las cuales suele ser la correcta— le cuesta el mismo clic que
                    # mostrarle una sola lectura dudosa, y le ahorra tipear.
                    foc.pagina, foc.caja = ref.pagina, (ref.caja or ref.region)
                    por["ocr_focal"] = foc
                    con_valor["ocr_focal"] = foc

        valores = {h.norm for h in con_valor.values()}

        # ── discrepancia entre rutas: no se elige, se marca ──
        if len(valores) > 1:
            ref = max(con_valor.values(), key=lambda h: h.conf)
            cx.execute("""INSERT INTO campo (documento_id,nombre,nulo_motivo,pagina_nro,
                                             x0,y0,x1,y1,estado)
                          VALUES (?,?,?,?,?,?,?,?,'a_revisar')""",
                       (doc_id, campo, "conflicto", ref.pagina,
                        *(ref.caja if ref.caja else (None,) * 4)))
            k = cx.execute("INSERT INTO conflicto (documento_id,campo_nombre) VALUES (?,?)",
                           (doc_id, campo)).lastrowid
            for ruta, h in sorted(con_valor.items()):
                cx.execute("""INSERT INTO conflicto_variante
                              (conflicto_id,ruta,valor,confianza,pagina_nro,x0,y0,x1,y1)
                              VALUES (?,?,?,?,?,?,?,?,?)""",
                           (k, ruta, h.literal, h.conf, h.pagina, *(h.caja or (None,) * 4)))
            n_campos += 1; n_conf += 1; n_rev += 1
            continue

        # ── ninguna ruta lo encontró: nulo con motivo ──
        if not con_valor:
            motivo = _elegir_motivo([h.motivo or "ausente" for h in por.values()])
            ref = next((h for h in por.values() if h.caja), None)
            cx.execute("""INSERT INTO campo (documento_id,nombre,nulo_motivo,pagina_nro,
                                             x0,y0,x1,y1,estado)
                          VALUES (?,?,?,?,?,?,?,?,'a_revisar')""",
                       (doc_id, campo, motivo, ref.pagina if ref else None,
                        *(ref.caja if ref and ref.caja else (None,) * 4)))
            n_campos += 1; n_rev += 1
            continue

        # ── hay valor: coinciden todas las rutas que lo vieron ──
        mejor = max(con_valor.values(), key=lambda h: h.conf)
        unica = len(con_valor) == 1
        conf = mejor.conf * (PENALIZA_UNICA if unica else 1.0)
        if foco_discrepa:
            conf *= PENALIZA_DISCREPANCIA
        revisar = (conf < config.UMBRAL_CONFIANZA or (unica and critico) or foco_discrepa)
        estado = "a_revisar" if revisar else "automatico"
        ruta_mejor = next(r for r, h in con_valor.items() if h is mejor)

        cid = cx.execute(
            """INSERT INTO campo (documento_id,nombre,valor_literal,pagina_nro,
                                  x0,y0,x1,y1,ruta,confianza,lectura_id,estado)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (doc_id, campo, mejor.literal, mejor.pagina, *mejor.caja,
             ruta_mejor + ("+unica" if unica else f"+{len(con_valor)}rutas"),
             round(conf, 4), mejor.lectura_id, estado)).lastrowid
        cx.execute("INSERT INTO normalizacion (campo_id,tipo,valor_norm,nota) VALUES (?,?,?,?)",
                   (cid, spec["parser"], mejor.norm,
                    ("lectura única" if unica else f"{len(con_valor)} rutas conformes")
                    + (" · la relectura focalizada discrepa" if foco_discrepa else "")))
        n_campos += 1
        n_rev += int(revisar)
    return {"campos": n_campos, "conflictos": n_conf, "a_revisar": n_rev}


def extraer_documento(cx: sqlite3.Connection, sha: str,
                      perfil_nombre: str = "auto") -> dict:
    """
    Extrae TODOS los contratos que haya en un archivo, con el perfil que mejor le calce.

    Devuelve el agregado del archivo. `documentos` dice cuántos contratos encontró: si
    da más de uno, el PDF traía varios adentro y cada uno quedó como un registro
    separado, con su tramo de páginas.
    """
    perfiles = perfiles_a_probar(perfil_nombre)
    perfil = perfiles[0]

    # Agrupar las lecturas por ruta.
    por_ruta: dict[str, list[tuple[int, int, list[Palabra]]]] = {}
    for r in cx.execute(
        """SELECT p.nro, l.id AS lid, l.ruta
             FROM pagina p JOIN lectura l ON l.pagina_id = p.id
            WHERE p.sha256 = ? ORDER BY p.nro, l.ruta""", (sha,)):
        por_ruta.setdefault(r["ruta"], []).append((r["nro"], r["lid"], palabras_de(cx, r["lid"])))

    if not por_ruta:
        raise RuntimeError(f"sin lecturas para {sha}: correr `leer` antes que `extraer`")

    todas = sorted({nro for pgs in por_ruta.values() for nro, _, _ in pgs})
    # Una página arranca contrato si CUALQUIER ruta la reconoce como formulario. Ser
    # generoso acá es lo correcto: perder un arranque significa perder un contrato
    # entero y mezclarlo con el anterior.
    inicios = sorted({nro for pgs in por_ruta.values() for nro, _, pw in pgs
                      if any(pagina_es_formulario(pw, pf) for pf in perfiles)})
    tramos = segmentar(inicios, todas)

    if not tramos:
        cx.execute("INSERT INTO excepcion (sha256, clase, detalle, creado_en) VALUES (?,?,?,?)",
                   (sha, "perfil_no_aplica",
                    "ninguna página se reconoció como formulario conocido; probados: "
                    + ", ".join(pf["nombre"] for pf in perfiles), ahora()))
        cx.commit()
        return {"documentos": 0, "campos": 0, "conflictos": 0, "a_revisar": 0,
                "sin_perfil": 1, "revisiones_reaplicadas": 0}

    # Render de las páginas, para la relectura focalizada.
    por_pagina = {r["nro"]: (Path(r["render"]), r["render_escala"] or config.ESCALA_RENDER)
                  for r in cx.execute("""SELECT nro, render, render_escala FROM pagina
                                          WHERE sha256=? AND render IS NOT NULL""", (sha,))}

    # Borrar lo anterior de ESTE archivo, en orden de dependencias.
    viejos = [f["id"] for f in cx.execute("SELECT id FROM documento WHERE sha256=?", (sha,))]
    for doc_id in viejos:
        sub = "SELECT id FROM campo WHERE documento_id=?"
        cx.execute(f"DELETE FROM persona_alias         WHERE campo_id IN ({sub})", (doc_id,))
        cx.execute(f"DELETE FROM interpretacion_fuente WHERE campo_id IN ({sub})", (doc_id,))
        cx.execute("DELETE FROM interpretacion_fuente  WHERE documento_id=?", (doc_id,))
        cx.execute("DELETE FROM documento_persona      WHERE documento_id=?", (doc_id,))
        cx.execute(f"DELETE FROM normalizacion         WHERE campo_id IN ({sub})", (doc_id,))
        cx.execute("""DELETE FROM conflicto_variante WHERE conflicto_id IN
                      (SELECT id FROM conflicto WHERE documento_id=?)""", (doc_id,))
        cx.execute("DELETE FROM conflicto WHERE documento_id=?", (doc_id,))
        cx.execute("DELETE FROM campo     WHERE documento_id=?", (doc_id,))
    cx.execute("DELETE FROM documento WHERE sha256=?", (sha,))

    total = {"documentos": 0, "campos": 0, "conflictos": 0, "a_revisar": 0,
             "sin_perfil": 0, "revisiones_reaplicadas": 0}
    for i, (desde, hasta) in enumerate(tramos, start=1):
        recorte = {ruta: [(n, l, w) for n, l, w in pgs if desde <= n <= hasta]
                   for ruta, pgs in por_ruta.items()}
        recorte = {r: pgs for r, pgs in recorte.items() if pgs}

        # Se prueba cada perfil sobre este tramo y gana el que más campos saca. Con un
        # solo perfil dado a mano, el bucle corre una vez y decide lo mismo.
        mejor_perfil, mejor_res, mejor_cam, mejor_pt = None, None, None, (-1, -1)
        for pf in perfiles:
            resultados, camaras = {}, []
            for ruta, pgs in recorte.items():
                hall, camara, _ = extraer_de_ruta(pgs, pf)
                resultados[ruta] = hall
                if camara:
                    camaras.append(camara)
            pt = max((puntaje(h) for h in resultados.values()), default=(0, 0))
            if pt > mejor_pt:
                mejor_perfil, mejor_res, mejor_pt = pf, resultados, pt
                mejor_cam = max(set(camaras), key=camaras.count) if camaras else None
        perfil, resultados, camara = mejor_perfil, mejor_res, mejor_cam

        doc_id = cx.execute(
            """INSERT INTO documento (sha256, orden, pagina_desde, pagina_hasta,
                                      tipo, perfil, camara, estado)
               VALUES (?,?,?,?,?,?,?,'extraido')""",
            (sha, i, desde, hasta, perfil["tipo"], perfil["nombre"], camara)).lastrowid

        r = _guardar_contrato(cx, sha, doc_id, perfil, resultados, por_pagina)
        rehechas = reaplicar_revisiones(cx, doc_id, sha, i)
        total["documentos"] += 1
        for k in ("campos", "conflictos"):
            total[k] += r[k]
        total["a_revisar"] += max(0, r["a_revisar"] - rehechas)
        total["revisiones_reaplicadas"] += rehechas

    if len(tramos) > 1:
        cx.execute("""INSERT INTO excepcion (sha256, clase, detalle, creado_en)
                      VALUES (?,?,?,?)""",
                   (sha, "varios_contratos_en_un_archivo",
                    f"el archivo trae {len(tramos)} contratos; se separaron en "
                    f"{len(tramos)} registros por tramo de páginas", ahora()))
    cx.commit()
    return total


def reaplicar_revisiones(cx: sqlite3.Connection, doc_id: int, sha: str,
                        orden: int = 1) -> int:
    """
    Vuelve a aplicar lo que una persona ya decidió sobre este documento en una corrida
    anterior. Sin esto, mejorar el perfil de extracción y reprocesar el lote le borraría
    al equipo todo el trabajo de revisión, que es exactamente lo que no puede pasar.
    """
    from .aplicar_revision import aplicar
    n = 0
    for r in cx.execute("SELECT * FROM revision_humana WHERE sha256=? AND orden=?",
                        (sha, orden)).fetchall():
        c = cx.execute("SELECT id FROM campo WHERE documento_id=? AND nombre=?",
                       (doc_id, r["campo"])).fetchone()
        if not c:
            continue
        try:
            aplicar(cx, c["id"], r["accion"], r["valor"], r["quien"], registrar=False)
            n += 1
        except Exception:
            pass          # el campo cambió de forma; queda para revisar de nuevo
    return n
