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
import re
import sqlite3
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from . import config
import pytesseract

from .capa1_texto import Palabra, palabras_de
from .capa2_campos import PARSERS, normalizar_cotejo
from . import clasificacion as cl
from .cotejo_letras import cotejar
from .clasificacion import clasificar_documento, tramos_por_tipo
from .manuscrito import MOTIVO as MOTIVO_MANUSCRITO, es_manuscrito
from . import confianza as cf
from .db import ahora

MARGEN_IZQ = 8.0        # puntos que se toleran a la izquierda del rótulo
# Lo que dice `documento.perfil` entre que la segmentación crea la pieza y la
# extracción decide con qué perfil leerla. La columna es NOT NULL y no puede quedar
# vacía, y dejarla en blanco sería peor: una pieza sin perfil no es una pieza sin
# nombre, es una pieza que todavía nadie miró.
SIN_PERFIL = "(sin determinar)"
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


def _recortar_a_la_hoja(region, ancho_pt: float, alto_pt: float):
    """
    Deja la región adentro de la hoja.

    Una zona que se pasa del borde produce un recorte con una franja negra, y en la
    cola de revisión eso se ve como media imagen rota justo cuando la persona necesita
    leer el número.
    """
    x0, y0, x1, y1 = region
    return (max(0.0, x0), max(0.0, y0), min(ancho_pt, x1), min(alto_pt, y1))


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
# ──────────────────────────────────────────── extracción sobre texto corrido ──
# Por qué existe esta segunda estrategia, además de la de rótulo + región.
#
# Los contratos de la Legislatura NO son formularios con casilleros. Son prosa:
#
#   «En la ciudad de Paraná, a los 01 (uno) días del mes de julio del año dos mil
#    dieciseis, entre la Honorable Cámara de Senadores (...) y el/la Sr./a. Beber,
#    Nicolás titular de Documento Nacional de Identidad número 25102152 (...)
#    CUARTA: (...) la suma total de $72000.- (Pesos, Setenta y dos mil) (...)»
#
# No hay rótulo que anclar ni recuadro donde mirar: el dato está adentro de una
# oración. Pero la oración es CONSTANTE entre contratos, porque es un modelo que la
# Cámara reusa. Entonces el ancla deja de ser una coordenada y pasa a ser la frase.
#
# Lo que NO cambia: el anclaje del §4. Cada valor que sale de acá sigue sabiendo de
# qué página y de qué recuadro salió, porque el patrón se busca sobre un texto armado
# con las MISMAS palabras que tienen coordenadas, y el recuadro es la unión de las que
# cayeron adentro de la coincidencia. Sigue sin haber ningún valor sin lugar en la
# imagen.
def _texto_con_indice(palabras: list[Palabra]) -> tuple[str, list[int]]:
    """
    Arma el texto corrido y, para cada carácter, de qué palabra salió.

    Con ese índice, una coincidencia de expresión regular se puede traducir de vuelta
    al conjunto de palabras que la produjeron, y de ahí al recuadro en la imagen.
    """
    partes, indice = [], []
    pos = 0
    for i, w in enumerate(palabras):
        if pos:
            partes.append(" ")
            indice.append(i)
            pos += 1
        partes.append(w.texto)
        indice.extend([i] * len(w.texto))
        pos += len(w.texto)
    return "".join(partes), indice


def _caja_de_palabras(palabras: list[Palabra], desde: int, hasta: int):
    """Recuadro que envuelve a las palabras [desde, hasta] y su confianza mínima."""
    tramo = palabras[desde:hasta + 1]
    if not tramo:
        return None, 0.0
    return ((min(p.x0 for p in tramo), min(p.y0 for p in tramo),
             max(p.x1 for p in tramo), max(p.y1 for p in tramo)),
            min(p.conf for p in tramo))


def _buscar_patron(palabras: list[Palabra], nro: int, lid: int, spec: dict) -> Hallazgo | None:
    """
    Busca el patrón del campo sobre el texto de la página. Devuelve None si no aparece
    —no un valor vacío—: que el patrón no esté en ESTA página no significa que el dato
    falte, puede estar en la siguiente foja del mismo contrato.
    """
    texto, indice = _texto_con_indice(palabras)
    if not texto:
        return None
    for patron in spec["patrones"]:
        m = re.search(patron, texto, re.I | re.S)
        if not m:
            continue
        # El grupo 1 es el valor; si el patrón no tiene grupos, se toma la coincidencia
        # entera. Las posiciones se toman del grupo para que el recuadro señale el dato
        # y no el párrafo que lo contiene.
        ini, fin = (m.span(1) if m.groups() else m.span(0))
        if ini >= len(indice):
            continue
        bruto = m.group(1) if m.groups() else m.group(0)
        literal, norm, motivo = PARSERS[spec["parser"]](bruto)
        caja, conf = _caja_de_palabras(palabras, indice[ini], indice[min(fin, len(indice)) - 1])
        return Hallazgo(literal, norm, motivo, nro, caja, conf, lid, caja)
    return None


def extraer_de_ruta(paginas: list[tuple[int, int, list[Palabra]]], perfil: dict
                    ) -> tuple[dict[str, Hallazgo], str | None, bool]:
    """
    paginas: [(nro, lectura_id, palabras), ...] de una misma ruta.
    Devuelve (hallazgos por campo, cámara detectada, si el perfil aplica).
    """
    plano_total = " ".join(_texto_plano(pw) for _, _, pw in paginas)
    deteccion = perfil.get("deteccion", {})
    det = deteccion.get("alguno_de", [])
    aplica = (not det) or any(normalizar_cotejo(t) in plano_total for t in det)
    # `ninguno_de` es lo que permite distinguir dos variantes del mismo documento sin
    # que la más específica tenga que ganar por puntaje. Una factura electrónica trae
    # el importe IMPRESO y se lee; una de talonario lo trae a mano y no se lee. Si la
    # elección dependiera de cuántos campos resuelve cada perfil, el de la electrónica
    # ganaría siempre —resuelve más— y le sacaría un número inventado a una factura
    # manuscrita. Acá se excluye por lo que el documento dice, no por lo que conviene.
    for marca in deteccion.get("ninguno_de", []):
        if normalizar_cotejo(marca) in plano_total:
            aplica = False
            break

    camara = None
    for regla in perfil.get("camara", []):
        if normalizar_cotejo(regla["si_contiene"]) in plano_total:
            camara = regla["valor"]
            break

    hallazgos: dict[str, Hallazgo] = {}

    # Campos escritos a mano: se ubican, pero NO se leen. Ver ufil/manuscrito.py, que
    # trae la medición: sobre estas mismas facturas el OCR devuelve un número
    # equivocado y las tres rutas coinciden en el error, así que el conflicto nunca se
    # levanta y el valor falso entra como firme. Un campo vacío con motivo cuesta dos
    # segundos de revisión; un monto falso no lo detecta nadie.
    for spec in perfil.get("campos_patron", []) + perfil.get("campos", []):
        if not es_manuscrito(spec):
            continue
        # Sin leerlo, pero SÍ ubicándolo: el campo va a la cola con el recorte de la
        # imagen al lado, y ahí leer «6.000» y tipearlo cuesta dos segundos. Sin
        # coordenadas la cola mostraría un casillero vacío y habría que ir a buscar la
        # foja, que son dos navegaciones por campo y nadie las hace.
        h = Hallazgo(None, None, MOTIVO_MANUSCRITO, None, None, 0.0, None, None)
        for nro, lid, palabras in paginas:
            caja_rot = _buscar_rotulo(palabras, spec.get("rotulo", []))
            if not caja_rot:
                continue
            region = _region(caja_rot, spec)
            ancho = max((w.x1 for w in palabras), default=595.0)
            alto = max((w.y1 for w in palabras), default=842.0)
            region = _recortar_a_la_hoja(region, max(ancho, 595.0), max(alto, 842.0))
            h = Hallazgo(None, None, MOTIVO_MANUSCRITO, nro, region, 0.0, lid, region)
            break
        hallazgos[spec["nombre"]] = h

    # Campos que se buscan por frase, no por casillero. Van primero porque en un
    # documento en prosa son la mayoría; los de rótulo quedan para los formularios.
    for spec in perfil.get("campos_patron", []):
        if es_manuscrito(spec):
            continue
        h = Hallazgo(None, None, "ausente", None, None, 0.0, None, None)
        for nro, lid, palabras in paginas:
            encontrado = _buscar_patron(palabras, nro, lid, spec)
            if encontrado:
                h = encontrado
                break
        hallazgos[spec["nombre"]] = h

    for spec in perfil.get("campos", []):
        if es_manuscrito(spec):
            continue
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
    # `manuscrito` va primero: no es que no se pudo leer, es que no se intenta. La
    # diferencia le importa a quien revisa —«ilegible» invita a mirar si el escaneo
    # está mal; «manuscrito» le dice que mire el recorte y lo tipee— y le importa al
    # que decide si conviene reescanear.
    for preferido in (MOTIVO_MANUSCRITO, "ambiguo", "ilegible", "ausente"):
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
    hallados = sum(1 for spec in perfil.get("campos", [])
                   if _buscar_rotulo(palabras, spec["rotulo"]))
    # Un documento en prosa no tiene rótulos que contar. Lo que se le exige, por la
    # misma razón —que una carátula que menciona un contrato no arranque un contrato
    # fantasma—, es que aparezcan las frases del cuerpo y no sólo el título.
    texto, _ = _texto_con_indice(palabras)
    for spec in perfil.get("campos_patron", []):
        if any(re.search(p, texto, re.I | re.S) for p in spec["patrones"]):
            hallados += 1
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
    for spec in list(perfil.get("campos_patron", [])) + list(perfil.get("campos", [])):
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
        # En un campo manuscrito la relectura focalizada NO corre. Es la misma
        # prohibición del principio, y hay que repetirla acá porque esta es la puerta
        # de atrás: la relectura mira el recorte con alfabeto restringido, que es
        # exactamente la configuración que sobre estas facturas leyó 6.200 donde dice
        # 6.000. Sin este corte, un campo declarado manuscrito terminaba igual con un
        # número inventado adentro, y encima con confianza alta por ser ruta única.
        if es_manuscrito(spec):
            ref = next((h for h in por.values() if h.caja or h.region), None)
            cx.execute("""INSERT INTO campo (documento_id,nombre,nulo_motivo,pagina_nro,
                                             x0,y0,x1,y1,estado)
                          VALUES (?,?,?,?,?,?,?,?,?)""",
                       (doc_id, campo, MOTIVO_MANUSCRITO, ref.pagina if ref else None,
                        *((ref.caja or ref.region) if ref and (ref.caja or ref.region)
                          else (None,) * 4), cf.NO_REVISADO))
            n_campos += 1; n_rev += 1
            continue

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
                          VALUES (?,?,?,?,?,?,?,?,?)""",
                       (doc_id, campo, "conflicto", ref.pagina,
                        *(ref.caja if ref.caja else (None,) * 4), cf.CONFLICTO))
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
                          VALUES (?,?,?,?,?,?,?,?,?)""",
                       (doc_id, campo, motivo, ref.pagina if ref else None,
                        *(ref.caja if ref and ref.caja else (None,) * 4), cf.NO_REVISADO))
            n_campos += 1; n_rev += 1
            continue

        # ── hay valor: coinciden todas las rutas que lo vieron ──
        mejor = max(con_valor.values(), key=lambda h: h.conf)
        unica = len(con_valor) == 1
        conf = mejor.conf * (PENALIZA_UNICA if unica else 1.0)
        if foco_discrepa:
            conf *= PENALIZA_DISCREPANCIA
        # Un campo crítico leído por UNA sola ruta, o cuyo desempate discrepó, queda
        # pendiente aunque su confianza sea alta: una sola opinión no es un cotejo.
        revisar = (conf < config.UMBRAL_CONFIANZA or (unica and critico) or foco_discrepa)
        estado = cf.PENDIENTE_BAJA if revisar else cf.AUTOMATICO_ALTA
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


# ═══════════════════════════════════════════════════════════════════════════
# LAS CUATRO ETAPAS, Y POR QUÉ ESTÁN SEPARADAS
#
# Hasta acá esto era una sola función que hacía todo de una pasada por archivo:
# clasificaba las fojas, cotejaba los números, partía el archivo en piezas y extraía
# los campos. Funcionaba, pero tenía una consecuencia cara: **cualquier cambio en
# cualquiera de las cuatro obligaba a rehacer las cuatro**.
#
# Agregar un extractor —lo más frecuente que va a pasar en este sistema— volvía a
# clasificar fojas que nadie tocó y a resegmentar un archivo que no cambió. Y
# resegmentar no es gratis: destruye las piezas y obliga a reasociar el trabajo que
# las personas ya hicieron, con el riesgo que eso trae (ver `reaplicar_revisiones`).
#
# Ahora son cuatro funciones que se pueden correr solas y que se versionan por
# separado (ver ufil/versiones.py). Lo que se gana en concreto:
#
#   * cambiar la extracción NO vuelve a clasificar ni a resegmentar;
#   * cambiar la segmentación NO vuelve a leer ni a clasificar;
#   * cambiar la clasificación NO vuelve a pasar el OCR.
#
# `extraer_documento` sigue existiendo y hace las cuatro en orden: es lo que usan la
# línea de comandos y el procesamiento de un lote nuevo, donde de todas formas hay que
# hacer todo. Lo que cambió es que ya no es la única forma de hacer una sola.
# ═══════════════════════════════════════════════════════════════════════════


def leer_foja_por_foja(cx: sqlite3.Connection, sha: str):
    """
    Las palabras de un archivo, **de a una foja**. Devuelve `(nro, {ruta: (lid, palabras)})`.

    Por qué existe además de `lecturas_por_ruta`
    --------------------------------------------
    `lecturas_por_ruta` carga el archivo entero en memoria. Medido sobre un expediente
    de 400 fojas con dos rutas de lectura: 360.000 palabras y **103 MB de pico**, o sea
    unos 0,26 MB por foja. Un PDF de 2.000 fojas pediría medio giga, y el pliego pide
    pensar en 5.000.

    Las etapas que trabajan foja por foja —qué es cada foja, la foliatura, el cotejo de
    números, las tablas— no necesitan el archivo entero: necesitan una foja por vez. Con
    esto la memoria deja de crecer con el tamaño del PDF.

    La extracción sí mira tramos de varias fojas, así que sigue usando la otra.
    """
    actual, acumulado = None, {}
    for r in cx.execute(
        """SELECT p.nro, l.id AS lid, l.ruta
             FROM pagina p JOIN lectura l ON l.pagina_id = p.id
            WHERE p.sha256 = ? ORDER BY p.nro, l.ruta""", (sha,)):
        if actual is not None and r["nro"] != actual:
            yield actual, acumulado
            acumulado = {}
        actual = r["nro"]
        acumulado[r["ruta"]] = (r["lid"], palabras_de(cx, r["lid"]))
    if actual is not None:
        yield actual, acumulado


def lecturas_por_ruta(cx: sqlite3.Connection, sha: str) -> dict:
    """
    Las palabras de cada foja, agrupadas por ruta de lectura. **Carga el archivo entero.**

    La usa la extracción, que mira tramos de varias fojas y no puede trabajar de a una.
    Para lo que sí trabaja foja por foja está `leer_foja_por_foja`, que no hace crecer
    la memoria con el tamaño del PDF.
    """
    por_ruta: dict[str, list[tuple[int, int, list[Palabra]]]] = {}
    for r in cx.execute(
        """SELECT p.nro, l.id AS lid, l.ruta
             FROM pagina p JOIN lectura l ON l.pagina_id = p.id
            WHERE p.sha256 = ? ORDER BY p.nro, l.ruta""", (sha,)):
        por_ruta.setdefault(r["ruta"], []).append((r["nro"], r["lid"], palabras_de(cx, r["lid"])))
    if not por_ruta:
        raise RuntimeError(f"sin lecturas para {sha}: correr `leer` antes que `extraer`")
    return por_ruta


def _clases_guardadas(cx: sqlite3.Connection, sha: str) -> dict:
    """Qué es cada foja, según lo que dejó escrito la clasificación."""
    return {r["nro"]: r["clasificacion"]
            for r in cx.execute("""SELECT nro, clasificacion FROM pagina
                                    WHERE sha256=? AND clasificacion IS NOT NULL""", (sha,))}


# ───────────────────────────────────────────────────── ETAPA: clasificación ──
def clasificar_fojas(cx: sqlite3.Connection, sha: str, *, por_ruta=None) -> dict:
    """
    Qué es cada foja de este archivo. Depende de la lectura y de nada más.

    Un expediente real no es una pila prolija de contratos: trae la carátula, dos o
    tres contratos, el decreto que los aprueba, una nota y después quince facturas.
    Clasificar foja por foja es lo que evita que el último contrato se quede con todo
    lo que viene atrás. Se hace sobre el encabezado, que es donde el documento se
    identifica, y con la mejor ruta de lectura disponible para cada foja.

    No mira los perfiles de extracción a propósito: qué ES una foja no depende de si
    sabemos sacarle los campos. Por eso agregar un extractor no vuelve a clasificar.
    """
    encabezados: dict[int, str] = {}
    # Cuánto leyó el motor en cada foja, que es lo que separa un dorso en blanco y una
    # fotocopia ilegible de una foja de trabajo. Se mide sobre la página ENTERA, no
    # sobre el encabezado: una hoja en blanco no tiene encabezado, y de eso se trata.
    # Entre rutas gana la que más cosas legibles encontró, por la misma razón que el
    # encabezado más largo: si alguna pudo leer, la foja se puede leer.
    medidas: dict[int, cl.Medida] = {}

    # De a una foja: lo único que se guarda de cada una es su encabezado normalizado y
    # su medida, que ocupan unos bytes. Antes se retenían todas las palabras del archivo
    # para sacar eso mismo, y la memoria crecía con el tamaño del PDF.
    fuente = (((nro, pw) for pgs in por_ruta.values() for nro, _, pw in pgs)
              if por_ruta else
              ((nro, pw) for nro, rutas in leer_foja_por_foja(cx, sha)
               for _lid, pw in rutas.values()))
    vistas: set = set()
    for nro, pw in fuente:
        # La foja se anota aunque no haya dado una sola palabra. Una hoja en blanco, una
        # fotocopia ilegible y un dorso son fojas: dejarlas afuera acá las borraría del
        # archivo, y distinguirlas es justamente para lo que sirve clasificar.
        vistas.add(nro)
        plano = normalizar_cotejo(" ".join(w.texto for w in pw[:120]))
        if len(plano) > len(encabezados.get(nro, "")):
            encabezados[nro] = plano
        # Se juntan las rutas: lo más que alguna VIO y lo más que alguna LEYÓ. Quedarse
        # con la ruta de más útiles no alcanzaba: en un legajo real, una ruta devolvió
        # 137 fragmentos sin una palabra legible y la otra una sola palabra, y ganaba la
        # de una palabra, así que una foja con algo que no se pudo leer salía «en
        # blanco» en vez de «no se pudo leer», que es lo que manda a alguien a mirarla.
        m = cl.medir(w.texto for w in pw)
        if nro in medidas:
            m = cl.Medida(max(m.palabras, medidas[nro].palabras),
                          max(m.utiles, medidas[nro].utiles))
        medidas[nro] = m
    todas = sorted(vistas)
    if not todas:
        raise RuntimeError(f"sin lecturas para {sha}: correr `leer` antes que `extraer`")

    clases = clasificar_documento([(n, encabezados.get(n, "")) for n in todas], medidas)
    for nro, clase in clases.items():
        cx.execute("UPDATE pagina SET clasificacion=? WHERE sha256=? AND nro=?",
                   (clase, sha, nro))
    cx.commit()
    return {"fojas": len(clases), "clases": clases}


# ────────────────────────────────────────────────────────── ETAPA: cotejo ──
def cotejar_numeros(cx: sqlite3.Connection, sha: str, *, por_ruta=None) -> dict:
    """
    El número que el papel escribe dos veces, en letras y en dígitos.

    Sobre el texto ENTERO de cada foja, no sobre el encabezado: el importe de una
    resolución está en el considerando y la cantidad de luminarias, en el medio de la
    memoria descriptiva.

    Depende de la lectura y de la clasificación —de una hoja en blanco no sale ningún
    número— pero no de los perfiles ni de la segmentación.
    """
    clases = _clases_guardadas(cx, sha)

    # De a una foja, y sin guardar el texto de las que ya se cotejaron: acá lo único que
    # hace falta es el texto de UNA foja por vez.
    def por_foja():
        if por_ruta:
            textos: dict[int, str] = {}
            for pgs in por_ruta.values():
                for nro, _, pw in pgs:
                    t = " ".join(w.texto for w in pw)
                    if len(t) > len(textos.get(nro, "")):
                        textos[nro] = t
            yield from textos.items()
            return
        for nro, rutas in leer_foja_por_foja(cx, sha):
            # Entre rutas gana la que más leyó: si alguna pudo, la foja se puede leer.
            mejor = ""
            for _lid, pw in rutas.values():
                t = " ".join(w.texto for w in pw)
                if len(t) > len(mejor):
                    mejor = t
            yield nro, mejor

    n = 0
    for nro, texto in por_foja():
        if clases.get(nro) in cl.APARTADAS:
            continue            # de una hoja en blanco no sale ningún número
        for c in cotejar(texto):
            cx.execute(
                """INSERT OR IGNORE INTO cotejo_numero
                   (sha256, pagina_nro, clase, letras, digitos,
                    valor_letras, valor_digitos, coinciden, desde)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (sha, nro, c.clase, c.letras, c.digitos,
                 c.valor_letras, c.valor_digitos,
                 None if c.coinciden is None else int(c.coinciden), c.desde))
            n += 1
    cx.commit()
    return {"cotejos": n}


def _tramos_del_archivo(cx, sha: str, perfiles: list, por_ruta) -> tuple:
    """
    En qué piezas se parte este archivo, y qué perfiles declaran cada una.

    Un expediente trae contratos Y facturas en el mismo PDF, así que no se elige un
    tipo: se sacan TODOS. Cada tramo se queda con los perfiles que declaran ese tipo de
    foja. Elegir un solo tipo por archivo era perder los contratos o perder las
    facturas.
    """
    clases = _clases_guardadas(cx, sha)
    tramos: list = []
    perfil_de_tramo: dict = {}
    for pf in perfiles:
        tipo = pf.get("tipo_pagina") or pf.get("tipo")
        for t in tramos_por_tipo(clases, tipo):
            if t not in perfil_de_tramo:
                perfil_de_tramo[t] = []
                tramos.append(t)
            perfil_de_tramo[t].append(pf)
    # Y las piezas de los tipos que no tienen extractor: existen igual (ver
    # `cl.TIPOS_PIEZA`). Sólo se agregan si hay alguna pieza por perfil o algún tipo de
    # pieza en el archivo; un archivo de formularios viejos sigue yendo por rótulos.
    for tipo in sorted(set(clases.values()) & cl.TIPOS_PIEZA):
        for t in tramos_por_tipo(clases, tipo):
            if t not in perfil_de_tramo:
                perfil_de_tramo[t] = []
                tramos.append(t)
    tramos.sort()
    if not tramos:
        # Perfiles viejos de formulario, que no declaran un tipo de foja: se sigue
        # reconociendo por rótulos, como antes.
        todas = sorted({nro for pgs in por_ruta.values() for nro, _, _ in pgs})
        inicios = sorted({nro for pgs in por_ruta.values() for nro, _, pw in pgs
                          if any(pagina_es_formulario(pw, pf) for pf in perfiles)})
        tramos = segmentar(inicios, todas)
    return tramos, perfil_de_tramo


def _borrar_pieza(cx, doc_id: int) -> None:
    """Borra UNA pieza y todo lo que cuelga, en orden de dependencias."""
    sub = "SELECT id FROM campo WHERE documento_id=?"
    cx.execute(f"DELETE FROM persona_alias         WHERE campo_id IN ({sub})", (doc_id,))
    cx.execute(f"DELETE FROM interpretacion_fuente WHERE campo_id IN ({sub})", (doc_id,))
    cx.execute("DELETE FROM interpretacion_fuente  WHERE documento_id=?", (doc_id,))
    cx.execute("DELETE FROM documento_persona      WHERE documento_id=?", (doc_id,))
    cx.execute(f"DELETE FROM normalizacion         WHERE campo_id IN ({sub})", (doc_id,))
    cx.execute("""DELETE FROM conflicto_variante WHERE conflicto_id IN
                  (SELECT id FROM conflicto WHERE documento_id=?)""", (doc_id,))
    cx.execute("DELETE FROM conflicto    WHERE documento_id=?", (doc_id,))
    cx.execute("DELETE FROM campo        WHERE documento_id=?", (doc_id,))
    cx.execute("DELETE FROM pieza_tramo  WHERE documento_id=?", (doc_id,))
    cx.execute("DELETE FROM documento    WHERE id=?", (doc_id,))


def _borrar_piezas(cx, sha: str) -> None:
    """Borra las piezas de un archivo y todo lo que cuelga, en orden de dependencias."""
    for f in cx.execute("SELECT id FROM documento WHERE sha256=?", (sha,)).fetchall():
        doc_id = f["id"]
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


# ──────────────────────────────────────────────────────── ETAPA: segmentación ──
def segmentar_piezas(cx: sqlite3.Connection, sha: str, perfil_nombre: str = "auto",
                     *, por_ruta=None) -> dict:
    """
    Dónde empieza y termina cada pieza documental adentro del archivo.

    Un límite de PDF no es un límite de documento: un archivo puede traer varias piezas
    y una pieza puede ocupar varias fojas. Esto decide los tramos y deja creadas las
    piezas; los campos los llena la extracción, después.

    Cuando el reparto en piezas CAMBIA, las revisiones humanas anteriores al anclaje
    —las que no saben en qué foja estaban— dejan de poder reaplicarse por posición: la
    pieza que ocupa ese lugar ya no es la misma. Se las marca acá para que las mire una
    persona, en lugar de aplicarlas a ciegas sobre otro documento.
    """
    por_ruta = por_ruta or lecturas_por_ruta(cx, sha)
    perfiles = perfiles_a_probar(perfil_nombre)
    tramos, _ = _tramos_del_archivo(cx, sha, perfiles, por_ruta)

    if not tramos:
        cx.execute("INSERT INTO excepcion (sha256, clase, detalle, creado_en) VALUES (?,?,?,?)",
                   (sha, "perfil_no_aplica",
                    "ninguna página se reconoció como formulario conocido; probados: "
                    + ", ".join(pf["nombre"] for pf in perfiles), ahora()))
        cx.commit()
        # Se sale ANTES de borrar las piezas que ya había: un archivo que esta corrida
        # no supo reconocer no puede llevarse puesto lo que otra sí reconoció, ni las
        # revisiones que cuelgan de eso.
        return {"piezas": 0, "sin_perfil": 1, "cambio": False}

    # ── Las piezas se CONSERVAN por identidad, no se destruyen y rehacen ────────
    #
    # `clave` es el archivo y la foja donde la pieza empieza. Una pieza que sigue
    # arrancando en la misma foja es la misma pieza, aunque haya cambiado de largo, de
    # tipo o de posición. Conservarla es lo que hace que resegmentar no se lleve puesto
    # el trabajo de las personas: los campos y las revisiones cuelgan del `id`, y el
    # `id` sobrevive.
    #
    # Antes esto borraba todas las piezas del archivo y las volvía a crear, así que
    # cualquier resegmentación —agregar un tipo documental, por ejemplo— obligaba a
    # reasociar todo aunque la mayoría de las piezas no se hubiera movido.
    existentes = {f["clave"]: f for f in cx.execute(
        """SELECT id, clave, orden, pagina_desde, pagina_hasta, tipo, estado
             FROM documento WHERE sha256=?""", (sha,))}
    clases = _clases_guardadas(cx, sha)
    nuevas_claves = [f"{sha}:{desde}" for desde, _ in tramos]
    cambio = sorted(existentes) != sorted(nuevas_claves)

    # Las que ya no salen de la segmentación se van, con todo lo que cuelga.
    sobran = [f["id"] for k, f in existentes.items() if k not in set(nuevas_claves)]
    for doc_id in sobran:
        _borrar_pieza(cx, doc_id)

    # `orden` se recalcula siempre —es una posición, y las posiciones se corren— pero
    # se aplica en dos pasadas: la clave `(sha256, orden)` es única, así que mover la
    # 3ª al lugar de la 2ª choca con la 2ª mientras todavía está ahí.
    cx.execute("UPDATE documento SET orden = -orden WHERE sha256=?", (sha,))
    for i, (desde, hasta) in enumerate(tramos, start=1):
        clave = f"{sha}:{desde}"
        vieja = existentes.get(clave)
        if vieja is not None:
            # El tipo sólo se recalcula si no lo puso una persona: una clasificación
            # manual no la pisa una corrida del sistema.
            cx.execute("""UPDATE documento
                             SET orden=?, pagina_hasta=?,
                                 tipo = CASE WHEN clasificado_por IS NULL
                                             THEN ? ELSE tipo END
                           WHERE id=?""",
                       (i, hasta, clases.get(desde) or vieja["tipo"], vieja["id"]))
        else:
            # El tipo sale de la clasificación de la foja donde arranca. La extracción
            # lo precisa después con el perfil que gane; hasta entonces la pieza ya
            # existe y se puede ver, que es lo que hace falta para poder trabajarla.
            cx.execute(
                """INSERT INTO documento (sha256, orden, clave, pagina_desde,
                                          pagina_hasta, tipo, perfil, estado)
                   VALUES (?,?,?,?,?,?,?,'segmentado')""",
                (sha, i, clave, desde, hasta,
                 clases.get(desde) or "desconocido", SIN_PERFIL))

    if cambio:
        # Ver el encabezado: sin anclaje no hay forma de saber si la pieza que ocupa
        # ese lugar sigue siendo la que la persona miró.
        # Sin anclaje quiere decir sin foja Y sin pieza: una revisión anclada a su pieza
        # (la de un campo sin valor) la reencuentra `reaplicar_revisiones` por tramo y tipo.
        cx.execute("""UPDATE revision_humana
                         SET estado='requiere_reasociacion', motivo=?
                       WHERE sha256=? AND ancla_pagina IS NULL
                         AND (ancla_desde IS NULL OR ancla_tipo IS NULL)
                         AND estado='vigente'""",
                   ("es una revisión anterior al anclaje y el reparto del archivo en "
                    "piezas cambió, así que su posición ya no la identifica", sha))
    if len(tramos) > 1:
        cx.execute("""INSERT INTO excepcion (sha256, clase, detalle, creado_en)
                      VALUES (?,?,?,?)""",
                   (sha, "varios_contratos_en_un_archivo",
                    f"el archivo trae {len(tramos)} contratos; se separaron en "
                    f"{len(tramos)} registros por tramo de páginas", ahora()))
    cx.commit()
    return {"piezas": len(tramos), "sin_perfil": 0, "cambio": cambio}


# ─────────────────────────────────────────────────────── ETAPA: extracción ──
def extraer_campos(cx: sqlite3.Connection, sha: str, perfil_nombre: str = "auto",
                   *, por_ruta=None) -> dict:
    """
    Los campos de cada pieza ya segmentada. **No vuelve a segmentar.**

    Ésa es la diferencia que hace que agregar un extractor sea barato: trabaja sobre
    las piezas que ya están, con sus tramos, y lo único que rehace son los campos. Las
    piezas conservan su identidad, así que las revisiones humanas se reaplican sobre la
    misma pieza y no hay nada que reasociar.
    """
    piezas_guardadas = cx.execute(
        """SELECT id, orden, pagina_desde, pagina_hasta, tipo FROM documento
            WHERE sha256=? ORDER BY orden""", (sha,)).fetchall()
    total = {"documentos": 0, "campos": 0, "conflictos": 0, "a_revisar": 0,
             "sin_perfil": 0, "revisiones_reaplicadas": 0, "revisiones_a_reasociar": 0}
    if not piezas_guardadas:
        return total

    por_ruta = por_ruta or lecturas_por_ruta(cx, sha)
    perfiles = perfiles_a_probar(perfil_nombre)

    # Render de las páginas, para la relectura focalizada.
    por_pagina = {r["nro"]: (Path(r["render"]), r["render_escala"] or config.ESCALA_RENDER)
                  for r in cx.execute("""SELECT nro, render, render_escala FROM pagina
                                          WHERE sha256=? AND render IS NOT NULL""", (sha,))}

    piezas: list[dict] = []
    for fila in piezas_guardadas:
        doc_id, desde, hasta = fila["id"], fila["pagina_desde"], fila["pagina_hasta"]
        recorte = {ruta: [(n, l, w) for n, l, w in pgs if desde <= n <= hasta]
                   for ruta, pgs in por_ruta.items()}
        recorte = {r: pgs for r, pgs in recorte.items() if pgs}

        # Los perfiles que declaran este tipo de foja. Si ninguno lo declara —perfiles
        # viejos de formulario, que no declaran tipo— se prueban todos, como antes; pero
        # sólo para una pieza cuyo tipo no se conoce. Una resolución o un remito ya
        # sabemos qué son: probarles el extractor de contratos es invitar a que una
        # resolución que cita un contrato en su VISTO salga leída como contrato.
        candidatos = [pf for pf in perfiles
                      if (pf.get("tipo_pagina") or pf.get("tipo")) == fila["tipo"]]
        if not candidatos and fila["tipo"] not in cl.TIPOS_POR_CLAVE:
            candidatos = perfiles

        # Gana el que más campos saca. Con un solo perfil dado a mano, el bucle corre
        # una vez y decide lo mismo.
        mejor_perfil, mejor_res, mejor_cam, mejor_pt = None, None, None, (-1, -1)
        for pf in candidatos:
            resultados, camaras, aplico = {}, [], False
            for ruta, pgs in recorte.items():
                hall, camara, aplica = extraer_de_ruta(pgs, pf)
                resultados[ruta] = hall
                aplico = aplico or aplica
                if camara:
                    camaras.append(camara)
            # Un perfil cuya detección NO da en este tramo no compite, aunque por
            # casualidad resuelva algún campo. Antes el resultado de la detección se
            # descartaba y la elección era sólo por puntaje: eso es dejar que gane el
            # perfil más ambicioso en vez del que corresponde al documento.
            if not aplico:
                continue
            pt = max((puntaje(h) for h in resultados.values()), default=(0, 0))
            if pt > mejor_pt:
                mejor_perfil, mejor_res, mejor_pt = pf, resultados, pt
                mejor_cam = max(set(camaras), key=camaras.count) if camaras else None

        if mejor_perfil is None:
            # Ningún extractor reconoce esta pieza. **No se descarta.**
            #
            # Antes se borraba, y eso convertía «el sistema todavía no sabe leer esto»
            # en «esto no existe». Un documento que el sistema no sabe leer sigue
            # siendo un documento: tiene que poder verse, buscarse, clasificarse a mano
            # y recibir un extractor más adelante sin volver a subir el archivo, que es
            # de lo que se trata todo esto.
            #
            # Queda con `estado='sin_perfil'`, que las vistas de contratos y
            # comprobantes excluyen —no puede sumar en un total algo de lo que no se
            # leyó un solo campo— y `v_documento_todo` muestra con su estado al lado.
            cx.execute("""INSERT INTO excepcion (sha256, clase, detalle, creado_en)
                          VALUES (?,?,?,?)""",
                       (sha, "perfil_no_aplica",
                        f"fojas {desde}-{hasta}: ningún extractor reconoce todavía este "
                        f"documento; queda cargado y se puede clasificar a mano",
                        ahora()))
            cx.execute("DELETE FROM campo WHERE documento_id=?", (doc_id,))
            cx.execute("UPDATE documento SET estado='sin_perfil' WHERE id=?", (doc_id,))
            total["sin_perfil"] += 1
            continue

        perfil = mejor_perfil
        # Los campos de la corrida anterior se van; la PIEZA se queda con su id. Eso es
        # lo que permite que reextraer no obligue a reasociar nada.
        sub = "SELECT id FROM campo WHERE documento_id=?"
        cx.execute(f"DELETE FROM persona_alias         WHERE campo_id IN ({sub})", (doc_id,))
        cx.execute(f"DELETE FROM interpretacion_fuente WHERE campo_id IN ({sub})", (doc_id,))
        cx.execute(f"DELETE FROM normalizacion         WHERE campo_id IN ({sub})", (doc_id,))
        cx.execute("""DELETE FROM conflicto_variante WHERE conflicto_id IN
                      (SELECT id FROM conflicto WHERE documento_id=?)""", (doc_id,))
        cx.execute("DELETE FROM conflicto WHERE documento_id=?", (doc_id,))
        cx.execute("DELETE FROM campo     WHERE documento_id=?", (doc_id,))
        cx.execute("""UPDATE documento SET tipo=?, perfil=?, camara=?, estado='extraido'
                       WHERE id=?""",
                   (perfil["tipo"], perfil["nombre"], mejor_cam, doc_id))

        r = _guardar_contrato(cx, sha, doc_id, perfil, mejor_res, por_pagina)
        piezas.append({"id": doc_id, "orden": fila["orden"], "pagina_desde": desde,
                       "pagina_hasta": hasta, "tipo": perfil["tipo"]})
        total["documentos"] += 1
        for k in ("campos", "conflictos"):
            total[k] += r[k]
        total["a_revisar"] += r["a_revisar"]

    # Recién ACÁ, con todas las piezas del archivo ya resueltas. Mirando una pieza por
    # vez no hay forma de darse cuenta de que dos revisiones caen en la misma o de que
    # una quedó sin dueño: hay que ver el archivo entero para poder decir «esto no se
    # puede decidir solo».
    rev = reaplicar_revisiones(cx, sha, piezas)
    total["revisiones_reaplicadas"] = rev["reaplicadas"]
    total["revisiones_a_reasociar"] = rev["a_reasociar"]
    total["a_revisar"] = max(0, total["a_revisar"] - rev["reaplicadas"])
    cx.commit()
    return total


def extraer_documento(cx: sqlite3.Connection, sha: str,
                      perfil_nombre: str = "auto") -> dict:
    """
    Las cuatro etapas de un archivo, en orden. Es lo que hace falta con material nuevo.

    Sigue existiendo con la misma forma de siempre para que la línea de comandos y el
    procesamiento de un lote no tengan que saber que por dentro ahora son cuatro. Para
    correr una sola —que es lo que hace la actualización incremental— están
    `clasificar_fojas`, `cotejar_numeros`, `segmentar_piezas` y `extraer_campos`.
    """
    por_ruta = lecturas_por_ruta(cx, sha)
    clasificar_fojas(cx, sha, por_ruta=por_ruta)
    cotejar_numeros(cx, sha, por_ruta=por_ruta)
    seg = segmentar_piezas(cx, sha, perfil_nombre, por_ruta=por_ruta)
    if seg["sin_perfil"]:
        return {"documentos": 0, "campos": 0, "conflictos": 0, "a_revisar": 0,
                "sin_perfil": 1, "revisiones_reaplicadas": 0,
                "revisiones_a_reasociar": 0}
    return extraer_campos(cx, sha, perfil_nombre, por_ruta=por_ruta)


def _solapan(a, b) -> float:
    """Cuánto se pisan dos recuadros, de 0 a 1 sobre el más chico. Sin caja, 0."""
    if not a or not b or any(v is None for v in a) or any(v is None for v in b):
        return 0.0
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ancho = min(ax1, bx1) - max(ax0, bx0)
    alto = min(ay1, by1) - max(ay0, by0)
    if ancho <= 0 or alto <= 0:
        return 0.0
    menor = min((ax1 - ax0) * (ay1 - ay0), (bx1 - bx0) * (by1 - by0))
    return (ancho * alto) / menor if menor > 0 else 0.0


def _marcar_para_reasociar(cx, sha: str, orden: int, campo: str, motivo: str) -> None:
    cx.execute("""UPDATE revision_humana SET estado='requiere_reasociacion', motivo=?
                   WHERE sha256=? AND orden=? AND campo=?""", (motivo, sha, orden, campo))


def reaplicar_revisiones(cx: sqlite3.Connection, sha: str, piezas: list) -> dict:
    """
    Vuelve a aplicar lo que las personas ya decidieron sobre las piezas de este archivo.

    Por qué no alcanza con `orden`
    ------------------------------
    `orden` es la posición de la pieza adentro del archivo —1ª, 2ª, 3ª— y se recalcula
    en cada reproceso contando los tramos que salieron de la clasificación. O sea que NO
    identifica a la pieza: identifica a un lugar en una fila que se rearma.

    Cuando el sistema aprende un tipo documental nuevo —que es exactamente lo que este
    incremento existe para permitir— una foja que antes era `continuacion` pasa a ser
    una pieza propia, todas las de atrás se corren un lugar, y la corrección que alguien
    hizo sobre la 2ª pieza se reaplica sobre otra. Con estado `corregido` y confianza
    1,0: entrando como firme en los totales. Está reproducido en
    pruebas/test_actualizacion.py.

    Qué se usa en su lugar
    ----------------------
    La foja y el recuadro donde estaba el campo que la persona miró. Las páginas de un
    PDF no se mueven, así que la foja aguanta la resegmentación; el recuadro desempata
    cuando dos piezas comparten foja.

    Y cuando no alcanza para decidir, **no se aplica**: la revisión queda marcada
    `requiere_reasociacion` y la mira una persona. Perder trabajo humano es malo;
    aplicarlo en silencio al documento equivocado es peor.

    Se hace en dos tiempos —primero se decide todo, después se escribe— y eso no es
    prolijidad. La clave de `revision_humana` incluye el `orden`, así que mover una
    revisión a su pieza nueva choca contra la fila que todavía ocupa ese lugar, que
    puede ser otra revisión que ni siquiera se miró. Escribiendo sobre la marcha, esa
    otra decisión humana se borra en silencio. Decidiendo primero, las colisiones se
    ven antes de tocar nada.

    Las revisiones anteriores al anclaje —las que no saben en qué foja estaban— sólo
    se pueden reaplicar por posición, y eso vale únicamente si el reparto del archivo
    en piezas NO cambió. De eso se encarga `segmentar_piezas`, que es quien sabe si
    cambió: cuando cambia, las marca para que las mire una persona y acá ya no llegan
    como vigentes.

    Una revisión que una persona descartó no se vuelve a aplicar nunca: se saltean
    todos los estados que no sean `vigente` o `requiere_reasociacion`. Las que están
    esperando reasociación sí se vuelven a mirar, porque el reproceso puede haber
    despejado la duda; si sigue sin despejarse, quedan marcadas igual.
    """
    from .aplicar_revision import aplicar
    resultado = {"reaplicadas": 0, "a_reasociar": 0}

    revisiones = cx.execute(
        """SELECT * FROM revision_humana
            WHERE sha256=? AND COALESCE(estado,'vigente')
                  IN ('vigente','requiere_reasociacion')""", (sha,)).fetchall()
    if not revisiones:
        return resultado

    # Los campos que existen ahora, por pieza. Una sola consulta.
    campos: dict[int, dict] = {}
    for c in cx.execute("""SELECT c.id, c.documento_id, c.nombre, c.pagina_nro,
                                  c.x0, c.y0, c.x1, c.y1
                             FROM campo c JOIN documento d ON d.id = c.documento_id
                            WHERE d.sha256=?""", (sha,)):
        campos.setdefault(c["documento_id"], {})[c["nombre"]] = c

    por_orden = {p["orden"]: p for p in piezas}

    # ── Primer tiempo: decidir, sin escribir nada ─────────────────────────────
    decisiones: list = []                 # [fila, pieza|None, campo|None, motivo|None]
    tomados: dict[tuple, int] = {}        # (orden_nuevo, campo) -> índice en decisiones

    for r in revisiones:
        nombre = r["campo"]
        ancla = (r["ancla_x0"], r["ancla_y0"], r["ancla_x1"], r["ancla_y1"])
        pagina = r["ancla_pagina"]
        if pagina is not None and r["ancla_desde"] is not None:
            # Una versión anterior numeraba las fojas de un contrato desde el principio
            # de la pieza y no desde el principio del archivo, y el anclaje heredó ese
            # número. Encontrado en un legajo real: dos correcciones de contratos que
            # empiezan en las fojas 23 y 25 estaban ancladas «en la foja 1». Si la foja
            # del anclaje cae fuera de su propia pieza pero cabe como posición adentro de
            # ella, es esa numeración vieja, y se traduce a la foja del archivo.
            hasta = r["ancla_hasta"] or r["ancla_desde"]
            if not r["ancla_desde"] <= pagina <= hasta \
                    and 1 <= pagina <= hasta - r["ancla_desde"] + 1:
                pagina = r["ancla_desde"] + pagina - 1

        if r["ancla_pagina"] is None and r["ancla_desde"] is not None and r["ancla_tipo"]:
            # Anclada a la pieza y no a una foja: pasa con las revisiones de un campo SIN
            # valor —«no está en el papel», «ilegible»—, que no tienen foja ni recuadro
            # porque no hay nada escrito que señalar. La pieza sí: mismo tramo de fojas y
            # mismo tipo es la misma pieza aunque haya cambiado de lugar en la fila.
            # Encontrado en un legajo real: dos verificaciones de este tipo iban a pasar
            # a «requiere reasociación» en la primera actualización.
            candidatas = [p for p in piezas
                          if p["pagina_desde"] == r["ancla_desde"]
                          and (p["pagina_hasta"] or p["pagina_desde"]) == (
                              r["ancla_hasta"] or r["ancla_desde"])
                          and p["tipo"] == r["ancla_tipo"]]
            if not candidatas:
                decisiones.append([r, None, None,
                                   f"ya no hay una pieza de tipo {r['ancla_tipo']} en las "
                                   f"fojas {r['ancla_desde']}-{r['ancla_hasta']}"])
                continue
        elif r["ancla_pagina"] is None:
            # Revisión anterior al anclaje: sólo se puede aplicar por posición.
            #
            # Que haya llegado hasta acá como vigente significa que la segmentación no
            # cambió el reparto del archivo —`segmentar_piezas` marca las que sí— así
            # que la pieza que ocupa ese lugar sigue siendo la que la persona miró.
            # Si ni siquiera existe esa posición, no se inventa una.
            p = por_orden.get(r["orden"])
            if p is None:
                decisiones.append([r, None, None,
                                   "es una revisión anterior al anclaje y en el archivo "
                                   f"ya no hay una pieza en la posición {r['orden']}"])
                continue
            candidatas = [p]
        else:
            # Las piezas que contienen la foja que la persona miró.
            candidatas = [p for p in piezas
                          if (p["pagina_desde"] or 0) <= pagina
                          <= (p["pagina_hasta"] or p["pagina_desde"] or 0)]

        # De ésas, las que tienen este campo.
        candidatas = [p for p in candidatas if nombre in campos.get(p["id"], {})]

        if not candidatas:
            donde = (f" en la foja {pagina}" if pagina else "")
            decisiones.append([r, None, None,
                               f"ninguna pieza de este archivo tiene hoy el campo "
                               f"«{nombre}»{donde}"])
            continue

        if len(candidatas) > 1:
            # Varias piezas en la misma foja: desempata el recuadro. Si tampoco
            # desempata, no se elige por nosotros.
            def _cuanto(p, _n=nombre, _a=ancla):
                c = campos[p["id"]][_n]
                return _solapan(_a, (c["x0"], c["y0"], c["x1"], c["y1"]))

            candidatas = sorted(candidatas, key=_cuanto, reverse=True)
            if _cuanto(candidatas[0]) <= 0:
                decisiones.append([r, None, None,
                                   f"la foja {pagina} quedó repartida entre "
                                   f"{len(candidatas)} piezas y el recuadro no alcanza "
                                   f"para saber a cuál corresponde"])
                continue

        pieza = candidatas[0]
        clave = (pieza["orden"], nombre)
        if clave in tomados:
            # Dos revisiones distintas apuntan al mismo campo de la misma pieza: la
            # resegmentación fusionó lo que antes eran dos piezas. No se elige ninguna,
            # y la que ya se había anotado tampoco queda aplicada por haber llegado
            # primero.
            choque = ("al resegmentar, esta revisión y otra quedaron apuntando al "
                      "mismo campo de la misma pieza")
            antes = tomados.pop(clave)
            decisiones[antes][1] = None
            decisiones[antes][2] = None
            decisiones[antes][3] = choque
            decisiones.append([r, None, None, choque])
            continue

        tomados[clave] = len(decisiones)
        decisiones.append([r, pieza, campos[pieza["id"]][nombre], None])

    # ── Segundo tiempo: aplicar lo que se pudo decidir ────────────────────────
    for d in decisiones:
        fila, pieza, campo, _motivo = d
        if pieza is None:
            continue
        try:
            aplicar(cx, campo["id"], fila["accion"], fila["valor"], fila["quien"],
                    registrar=False)
        except Exception as e:
            d[1] = d[2] = None
            d[3] = (f"el campo cambió de forma y la decisión ya no se puede "
                    f"aplicar: {e}")

    # ── Y recién ahora se reescriben las filas ────────────────────────────────
    # Se borran todas las de este archivo y se vuelven a insertar con su posición
    # nueva. Es la única forma de mover varias a la vez sin que la clave primaria haga
    # que una pise a otra, y sin que se pierda ninguna en el camino.
    COLUMNAS = """INSERT INTO revision_humana
                    (sha256,orden,campo,accion,valor,quien,cuando,
                     ancla_pagina,ancla_x0,ancla_y0,ancla_x1,ancla_y1,
                     ancla_desde,ancla_hasta,ancla_tipo,estado,motivo)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
    # OJO: se borran SOLAMENTE las que se miraron. Un `DELETE` por `sha256` a secas se
    # llevaría puestas las que quedaron afuera del filtro de arriba —entre ellas las
    # que una persona descartó— y ésas no se vuelven a insertar acá, así que
    # desaparecerían sin que nadie lo pida.
    cx.executemany("DELETE FROM revision_humana WHERE sha256=? AND orden=? AND campo=?",
                   [(sha, f["orden"], f["campo"]) for f, _, _, _ in decisiones])
    for fila, pieza, campo, motivo in decisiones:
        if pieza is None:
            cx.execute(COLUMNAS,
                       (sha, fila["orden"], fila["campo"], fila["accion"], fila["valor"],
                        fila["quien"], fila["cuando"], fila["ancla_pagina"],
                        fila["ancla_x0"], fila["ancla_y0"], fila["ancla_x1"],
                        fila["ancla_y1"], fila["ancla_desde"], fila["ancla_hasta"],
                        fila["ancla_tipo"], "requiere_reasociacion", motivo))
            resultado["a_reasociar"] += 1
        else:
            # Se muda a la pieza que le corresponde ahora, y aprende dónde está: la
            # próxima vez el anclaje va a ser más preciso todavía.
            cx.execute(COLUMNAS,
                       (sha, pieza["orden"], fila["campo"], fila["accion"], fila["valor"],
                        fila["quien"], fila["cuando"], campo["pagina_nro"],
                        campo["x0"], campo["y0"], campo["x1"], campo["y1"],
                        pieza["pagina_desde"], pieza["pagina_hasta"], pieza["tipo"],
                        "vigente", None))
            resultado["reaplicadas"] += 1

    return resultado
