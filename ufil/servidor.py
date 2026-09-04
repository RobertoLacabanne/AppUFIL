"""
Capa 6 — Servidor local.

Biblioteca estándar de Python y nada más. Ni framework web, ni Node, ni paso de
compilación en la máquina de destino. Son tres razones concretas:

  * la restricción 1 se cumple sola: no hay un solo recurso que no salga de este disco;
  * el día que el que lo instaló no está, alguien puede leer este archivo entero en
    veinte minutos y entender qué hace;
  * dos o tres usuarios sobre una máquina no justifican nada más grande.

Escucha en 127.0.0.1 por defecto: no se expone a la red ni por accidente.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import sqlite3
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import acceso, config, db, legajos
from . import confianza as cf
from . import capa3_identidad as c3
from . import capa4_analisis as c4
from . import capa5_interpretacion as c5
from . import busqueda
from .almacen import ArchivoInvalido, guardar
from .aplicar_revision import DecisionDesactualizada
from .db import ahora
from .trabajo import Procesador

class NoEncontrado(Exception):
    """Lo que se pidió no existe. Se responde 404 y con una explicación, no con una
    excepción de Python en la cara del que está trabajando."""


RUTA_BASE: Path | None = None
PORTERIA: acceso.Porteria = acceso.Porteria(exigir=False)
HOST_ESCUCHA: str = "127.0.0.1"

# Un trabajador POR LEGAJO. Con uno solo, procesar el legajo A dejaría al B esperando
# sin motivo, y peor: el estado de avance que ve la pantalla sería el del otro legajo.
_PROCESADORES: dict[str | None, Procesador] = {}
_BASES_LISTAS: set[str] = set()
_CANDADO = threading.Lock()
_SLUGS_CONOCIDOS: set[str] = set()


# Huella del contenido de un archivo, para la etiqueta de versión. Se guarda en memoria
# contra (fecha, tamaño): mientras el archivo no cambie no se vuelve a leer, y cuando
# cambia se recalcula solo. En desarrollo eso significa que editar el CSS y recargar
# alcanza, sin reiniciar nada.
_HUELLAS: dict[str, tuple[float, int, str]] = {}


def version_interfaz() -> str:
    """
    La versión de lo que se está mostrando: la huella del contenido de la interfaz.

    Existe porque hubo que averiguarlo a mano. Se desplegó una versión nueva, el
    servidor la estaba sirviendo, y desde afuera no había forma de saber si lo que se
    veía en pantalla era esa o una guardada en el navegador. Con este número, la
    pregunta «¿estás viendo lo último?» se contesta mirando, no probando.

    Sale de los archivos de la interfaz y no de un número que alguien tenga que acordarse
    de subir: si cambió la pantalla, cambió el número.
    """
    partes = "".join(huella(config.WEB / n) for n in ("app.js", "estilo.css", "index.html"))
    return hashlib.sha256(partes.encode()).hexdigest()[:8]


def huella(ruta: Path) -> str:
    st = ruta.stat()
    previa = _HUELLAS.get(str(ruta))
    if previa and previa[0] == st.st_mtime and previa[1] == st.st_size:
        return previa[2]
    h = hashlib.sha256(ruta.read_bytes()).hexdigest()[:12]
    _HUELLAS[str(ruta)] = (st.st_mtime, st.st_size, h)
    return h


def _cx() -> sqlite3.Connection:
    """
    Conexión por petición, contra la base del legajo activo en ESTE hilo.

    Sin legajo activo se usa la base suelta con la que arrancó el servidor: las
    instalaciones anteriores a los legajos y las pruebas siguen andando igual.
    """
    # Se resuelve a una ruta concreta y no se deja en None: así el esquema se garantiza
    # también para la base suelta. Antes se confiaba en que `servir()` la hubiera
    # preparado, y bastaba con que alguien borrara el archivo —o con arrancar por otro
    # camino— para que las consultas empezaran a fallar con «no such table».
    ruta = Path(config.BASE) if (config.legajo_activo() or RUTA_BASE is None) else RUTA_BASE
    if str(ruta) not in _BASES_LISTAS:
        # El esquema se aplica una vez por base y por proceso. Un legajo recién creado
        # tiene la carpeta pero no la base: la primera petición que lo abre es la que la
        # crea. Serializado, porque dos pestañas abriendo el mismo legajo nuevo a la vez
        # correrían el `CREATE VIEW` en paralelo.
        with _CANDADO:
            if str(ruta) not in _BASES_LISTAS:
                db.abrir(ruta).close()
                _BASES_LISTAS.add(str(ruta))
    return db.conectar(ruta)


_PERMANENCIA: dict | None = None


def permanencia() -> dict:
    """
    ¿Lo que se guarda sobrevive a un reinicio? Calculado una vez y recordado.

    Va en `/api/legajos` —la pantalla donde se crea un legajo— porque es ahí donde
    alguien está por invertir dos días de revisión, y es el último momento en que la
    advertencia sirve de algo. Se cachea porque la respuesta no cambia mientras el
    proceso vive: el disco se monta al arrancar el contenedor, no en el medio.
    """
    global _PERMANENCIA
    if _PERMANENCIA is None:
        from . import permanencia as pm
        _PERMANENCIA = pm.estado()
    return _PERMANENCIA


def _falta_abrir_legajo() -> str:
    """
    ¿Se está por escribir material sin legajo abierto?

    Sin este control la carga andaba igual: `/api/subir` contestaba 200 y el escaneo
    caía en la base suelta, fuera de todo legajo, mientras el techo de la pantalla
    decía «Ninguno abierto». Después no hay a dónde ir a buscarlo: no figura en ningún
    legajo de la lista y los totales de la causa no lo cuentan.

    La excepción es la instalación anterior a los legajos, que tiene material en la
    base suelta y sigue trabajando ahí. A ésa no se le corta nada: se la reconoce
    porque la base suelta ya tiene documentos.

    Devuelve el motivo, o cadena vacía si se puede escribir.
    """
    if config.legajo_activo():
        return ""
    cx = _cx()
    try:
        if cx.execute("SELECT COUNT(*) FROM documento").fetchone()[0]:
            return ""            # instalación vieja, con material en la base suelta
    finally:
        cx.close()
    return ("No hay ningún legajo abierto. Cada legajo es una base separada: "
            "si esto se cargara ahora quedaría fuera de toda causa. "
            "Abrí o creá el legajo y volvé a intentar.")


def _procesador() -> Procesador:
    """El trabajador del legajo activo. Se crea la primera vez que se lo pide."""
    slug = config.legajo_activo()
    with _CANDADO:
        p = _PROCESADORES.get(slug)
        if p is None:
            base = Path(config.BASE) if slug else RUTA_BASE
            p = _PROCESADORES[slug] = Procesador(base, legajo=slug)
        return p


def _slug_valido(slug: str) -> bool:
    """
    ¿Ese legajo existe de verdad?

    Se chequea SIEMPRE, en cada pedido. La cookie la puede escribir cualquiera, y un
    slug inventado sin este control crearía una base nueva en una carpeta arbitraria.
    El conjunto se guarda en memoria y se relee sólo cuando el slug no está: así un
    legajo recién creado se reconoce enseguida y el caso normal no toca el disco.
    """
    if slug in _SLUGS_CONOCIDOS:
        return True
    with _CANDADO:
        _SLUGS_CONOCIDOS.clear()
        _SLUGS_CONOCIDOS.update(legajos.slugs())
    return slug in _SLUGS_CONOCIDOS


# ─────────────────────────────────────────────────────────────────── consultas ──
def es_demostracion(cx) -> bool:
    """
    ¿Los datos cargados son del corpus sintético de prueba?

    Importa muchísimo: si esto se muestra en una reunión, nadie puede confundir un
    contrato inventado para probar el software con uno de la Legislatura. Cuando da
    verdadero, la interfaz pone un aviso fijo arriba de todo.
    """
    if os.environ.get("UFIL_DEMO", "").strip() in ("1", "si", "true"):
        return True
    if db.ajuste(cx, "demostracion") == "1":
        return True
    n = cx.execute("""SELECT COUNT(*) FROM archivo
                       WHERE ruta_original LIKE '%corpus-sintetico%'""").fetchone()[0]
    return n > 0


def api_cuentas(cx) -> dict:
    """
    Lo poco que la interfaz necesita en CADA cambio de pantalla: qué legajo está
    abierto y cuánto trabajo espera.

    Existe porque para eso se estaba pidiendo `/api/panel` entero, que corre nueve
    consultas de análisis —superposiciones, cruces, cobertura, totales— y en un legajo
    de 1.500 contratos tarda casi un segundo. Eso se pagaba al abrir cualquier pantalla
    y DESPUÉS DE CADA DECISIÓN de la cola: revisar cien campos costaba cien segundos de
    espera repartidos en pedacitos, que es la clase de lentitud que nadie reporta y
    todos sufren.

    Acá hay cinco COUNT sobre índices. Tarda milésimas.
    """
    def uno(sql, *p):
        return cx.execute(sql, p).fetchone()[0]

    abierto = config.legajo_activo()
    try:
        l = legajos.obtener(abierto) if abierto else None
    except legajos.LegajoInexistente:
        l = None
    return {
        "legajo": ({"slug": l.slug, "numero": l.numero, "caratula": l.caratula,
                    "fiscal": l.fiscal} if l else None),
        "hay_legajos": bool(legajos.slugs()),
        "documentos": uno("SELECT COUNT(*) FROM documento"),
        "a_revisar": uno(f"SELECT COUNT(*) FROM campo WHERE estado IN ({cf.SQL_PENDIENTES})"),
        "fusiones": uno("SELECT COUNT(*) FROM fusion_propuesta WHERE estado='pendiente'"),
        "afuera": uno("""SELECT COUNT(*) FROM archivo a
                          WHERE NOT EXISTS (SELECT 1 FROM documento d
                                             WHERE d.sha256 = a.sha256)"""),
        "lote": (cx.execute("SELECT lote FROM procedencia LIMIT 1").fetchone() or [None])[0],
        "demostracion": es_demostracion(cx),
        # La versión que está sirviendo el servidor. La pantalla compara contra la que
        # cargó ella: si no coinciden, es que se actualizó abajo mientras estaba abierta
        # y hay que recargar. Sin esto, quien deja la pestaña abierta sigue usando la
        # versión anterior sin enterarse.
        "version": version_interfaz(),
    }


def api_panel(cx) -> dict:
    def uno(sql, *p):
        return cx.execute(sql, p).fetchone()[0]

    cobertura = c4.correr(cx, "05_cobertura")["filas"]
    # El denominador se dice explícito: firmes sobre el total de campos críticos DE LOS
    # CONTRATOS. «50 % resuelto solo» sin decir sobre qué no significa nada, y mezclar
    # los campos de las facturas acá infla el denominador con documentos que no son de
    # los que habla la frase.
    criticos = [c for c in cobertura
                if c["campo"] in config.CAMPOS_CRITICOS and c["familia"] == "contrato"]
    campos_criticos_total = sum(c["total"] for c in criticos)
    campos_criticos_firmes = sum(c["firmes"] for c in criticos)
    totales = c4.correr(cx, "10_totales")["filas"][0]
    # Qué legajo se está mirando. Va en el panel y no en una llamada aparte porque la
    # interfaz tiene que poder decirlo SIEMPRE, arriba de todo: un número al lado de una
    # carátula equivocada es peor que no mostrar el número.
    abierto = config.legajo_activo()
    try:
        l = legajos.obtener(abierto) if abierto else None
    except legajos.LegajoInexistente:
        l = None
    return {
        "legajo": ({"slug": l.slug, "numero": l.numero, "caratula": l.caratula,
                    "fiscal": l.fiscal} if l else None),
        "hay_legajos": bool(legajos.slugs()),
        # ── Totales, SEPARADOS. Ver ufil/confianza.py y consultas/10_totales.sql ──
        "totales": dict(totales),
        "archivos": uno("SELECT COUNT(*) FROM archivo"),
        "duplicados": uno("SELECT COUNT(*) FROM duplicado"),
        "paginas": uno("SELECT COUNT(*) FROM pagina"),
        # `documentos` es TODO lo que se extrajo: contratos, facturas, decretos y lo que
        # no se pudo clasificar. Los tres de abajo lo desagregan, porque la pantalla
        # decía «N contratos» sobre este número y adentro había facturas.
        "documentos": uno("SELECT COUNT(*) FROM documento"),
        "contratos": uno("SELECT COUNT(*) FROM v_documento_todo WHERE familia='contrato'"),
        "comprobantes": uno("SELECT COUNT(*) FROM v_documento_todo WHERE familia='comprobante'"),
        "actos": uno("SELECT COUNT(*) FROM v_documento_todo WHERE familia='acto'"),
        "sin_familia": uno("SELECT COUNT(*) FROM v_documento_todo WHERE familia IS NULL"),
        "campos": uno("SELECT COUNT(*) FROM campo"),
        "a_revisar": uno(f"SELECT COUNT(*) FROM campo WHERE estado IN ({cf.SQL_PENDIENTES})"),
        "conflictos": uno("SELECT COUNT(*) FROM conflicto WHERE estado='abierto'"),
        "verificados": uno(f"SELECT COUNT(*) FROM campo WHERE estado IN ({cf.SQL_HUMANOS})"),
        # Quiénes ya revisaron algo en esta base. Sirve para no obligar a nadie a
        # escribir su nombre de nuevo cada vez, y sobre todo para que dos personas no
        # queden anotadas como «Perez» y «perez, j» sobre el mismo legajo.
        "quienes": [r[0] for r in cx.execute(
            "SELECT quien, COUNT(*) n FROM revision_humana GROUP BY quien "
            "ORDER BY n DESC LIMIT 12")],
        "fusiones": uno("SELECT COUNT(*) FROM fusion_propuesta WHERE estado='pendiente'"),
        "excepciones": uno("SELECT COUNT(*) FROM excepcion WHERE estado='abierta'"),
        "personas": uno("SELECT COUNT(*) FROM persona"),
        "interpretaciones": uno("SELECT COUNT(*) FROM interpretacion"),
        "cobertura": cobertura,
        "campos_criticos_total": campos_criticos_total,
        "campos_criticos_firmes": campos_criticos_firmes,
        "cobertura_pct": round(100.0 * campos_criticos_firmes / campos_criticos_total, 1)
                         if campos_criticos_total else 0.0,
        "superposiciones": c4.correr(cx, "01_superposicion")["n"],
        "ambas_camaras": c4.correr(cx, "03_ambas_camaras")["n"],
        "fechas_imposibles": c4.correr(cx, "04_fechas_imposibles")["n"],
        "excluidos": c4.correr(cx, "06_excluidos_del_cruce")["n"],
        # Sin lote va `null`, no una raya: el dato faltante se decide en la pantalla,
        # que es la que sabe si conviene dejar el lugar vacío o poner algo. Con la raya
        # acá, la interfaz no puede distinguir «no hay lote» de «el lote se llama —».
        "lote": (cx.execute("SELECT lote FROM procedencia LIMIT 1").fetchone() or [None])[0],
        "demostracion": es_demostracion(cx),
        # Los tres hallazgos más grandes, para que el panel abra con lo que encontró y
        # no con una grilla de números que hay que interpretar.
        "destacados": [dict(r) for r in cx.execute("""
            SELECT a.documento_id AS doc, a.archivo AS archivo_a, b.archivo AS archivo_b,
                   COALESCE(a.nombre_literal,'(sin nombre)') AS contratado,
                   a.persona_id,
                   CASE WHEN a.camara=b.camara THEN 'intracámara' ELSE 'intercámara' END AS cruce,
                   CAST(julianday(MIN(a.fin,b.fin)) - julianday(MAX(a.inicio,b.inicio)) + 1
                        AS INTEGER) AS dias
              FROM v_contrato a JOIN v_contrato b
                ON a.persona_id=b.persona_id AND a.documento_id<b.documento_id
             WHERE a.inicio IS NOT NULL AND a.fin IS NOT NULL
               AND b.inicio IS NOT NULL AND b.fin IS NOT NULL
               AND a.inicio<=b.fin AND b.inicio<=a.fin
             ORDER BY dias DESC LIMIT 3""")],
        # El acumulado firme sale de la consulta de totales, que aplica la doble
        # barrera. Antes salía de una suma sobre la vista y arrastraba montos que en
        # ese momento estaban en la cola esperando revisión.
        "acumulado_centavos": totales["total_firme_centavos"],
        "personas_ambas_camaras": c4.correr(cx, "03_ambas_camaras")["n"],
        "contratos_repetidos": c4.correr(cx, "08_contratos_repetidos")["n"],
        "paginas_enderezadas": uno("SELECT COUNT(*) FROM pagina WHERE rotacion<>0"),
        "perfiles": [dict(r) for r in cx.execute(
            "SELECT perfil, COUNT(*) AS n FROM documento GROUP BY perfil ORDER BY n DESC")],
        "archivos_con_varios": uno("""SELECT COUNT(*) FROM (SELECT sha256 FROM documento
                                       GROUP BY sha256 HAVING COUNT(*) > 1)"""),
        # Archivos que entraron y no dieron ningún contrato. Va en el panel y en la
        # barra: si no se ve sin entrar a buscarlo, nadie lo mira.
        "afuera": uno("""SELECT COUNT(*) FROM archivo a
                          WHERE NOT EXISTS (SELECT 1 FROM documento d
                                             WHERE d.sha256 = a.sha256)""")
                  + uno("""SELECT COUNT(*) FROM (
                             SELECT 1 FROM excepcion
                              WHERE estado='abierta'
                                AND clase IN ('pdf_ilegible','ingesta_ilegible')
                              GROUP BY clase, detalle)"""),
    }


# Qué le decimos a una persona sobre cada clase de excepción. El texto crudo de la
# excepción es un mensaje de Python en inglés con una ruta absoluta adentro: no sirve
# para decidir nada. Acá se traduce a qué pasó y qué se puede hacer.
MOTIVOS = {
    "pdf_ilegible": (
        "El archivo no se pudo abrir",
        "Está vacío, dañado o protegido con contraseña. Conseguí una copia sana, o si "
        "tiene clave, guardalo sin clave antes de subirlo."),
    "ingesta_ilegible": (
        "El archivo no se pudo leer del disco",
        "Puede ser un problema de permisos o un disco con errores. Copialo a otra "
        "carpeta y volvé a subirlo."),
    "perfil_no_aplica": (
        "No se reconoció ningún formulario conocido",
        "El PDF entró bien y se leyó, pero ninguna de sus fojas tiene la forma de los "
        "formularios que el sistema conoce. Puede no ser un contrato, o ser un modelo "
        "de formulario nuevo: en ese caso hay que agregarle un perfil."),
    "lectura_fallida": (
        "La lectura de una foja falló",
        "Se registró la foja pero no se pudo obtener texto. Miralo en el visor: si la "
        "imagen está en blanco o ilegible, el problema está en el escaneo."),
    "pagina_ilegible": (
        "Una foja no se pudo interpretar",
        "La imagen está demasiado deteriorada. Conviene volver a escanear esa hoja."),
}


def api_afuera(cx) -> dict:
    """
    Los archivos que entraron y NO produjeron ningún contrato, con el motivo.

    Es la pantalla que faltaba: sin esto, subir trescientos PDF y que doce no den nada
    es invisible. Y un documento que se pierde en silencio es lo peor que puede hacer
    un sistema que existe para no perder documentos.
    """
    filas = []
    # 1. Los que ni siquiera llegaron a la tabla `archivo`: fallaron al abrirse.
    # Agrupado por detalle: cada vez que se reingiere la misma carpeta, un archivo que
    # no se puede abrir vuelve a anotar su excepción. Sin agrupar, el mismo PDF roto
    # aparecería listado cinco veces y parecería que son cinco problemas distintos.
    for r in cx.execute("""SELECT e.clase, e.detalle, MAX(e.creado_en) AS creado_en,
                                  e.sha256
                             FROM excepcion e
                            WHERE e.estado='abierta'
                              AND e.clase IN ('pdf_ilegible','ingesta_ilegible')
                            GROUP BY e.clase, e.detalle
                            ORDER BY creado_en DESC"""):
        # El detalle viene como "<ruta>: <excepción>". Nos alcanza con el nombre.
        crudo = r["detalle"] or ""
        nombre = crudo.split(": ", 1)[0].rsplit("/", 1)[-1] or "(sin nombre)"
        titulo, que_hacer = MOTIVOS.get(r["clase"], (r["clase"], ""))
        filas.append({"archivo": nombre, "sha256": r["sha256"], "paginas": None,
                      "lote": None, "clase": r["clase"], "titulo": titulo,
                      "que_hacer": que_hacer, "detalle": crudo, "leido": False})

    # 2. Los que se ingirieron bien pero no dieron ningún documento.
    for r in cx.execute("""
        SELECT a.sha256, a.nombre, a.paginas, p.lote,
               (SELECT COUNT(*) FROM lectura l JOIN pagina g ON g.id=l.pagina_id
                 WHERE g.sha256=a.sha256) AS lecturas,
               (SELECT e.clase FROM excepcion e
                 WHERE e.sha256=a.sha256 AND e.estado='abierta' ORDER BY e.id DESC LIMIT 1) AS clase,
               (SELECT e.detalle FROM excepcion e
                 WHERE e.sha256=a.sha256 AND e.estado='abierta' ORDER BY e.id DESC LIMIT 1) AS detalle
          FROM archivo a
          LEFT JOIN procedencia p ON p.sha256 = a.sha256
         WHERE NOT EXISTS (SELECT 1 FROM documento d WHERE d.sha256 = a.sha256)
         ORDER BY a.nombre"""):
        leido = bool(r["lecturas"])
        if not leido:
            titulo = "Todavía no se leyó"
            que_hacer = ("Está cargado pero le falta pasar por la lectura. Andá a "
                         "«Cargar escaneos» y tocá Procesar.")
            clase = "sin_leer"
        else:
            clase = r["clase"] or "perfil_no_aplica"
            titulo, que_hacer = MOTIVOS.get(clase, (clase, ""))
        filas.append({"archivo": r["nombre"], "sha256": r["sha256"],
                      "paginas": r["paginas"], "lote": r["lote"], "clase": clase,
                      "titulo": titulo, "que_hacer": que_hacer,
                      "detalle": r["detalle"], "leido": leido})

    por_clase: dict[str, int] = {}
    for f in filas:
        por_clase[f["clase"]] = por_clase.get(f["clase"], 0) + 1
    # El total tiene que contar también los que no llegaron a la tabla `archivo`: si no,
    # el denominador esconde justamente los que peor les fue.
    total = (cx.execute("SELECT COUNT(*) FROM archivo").fetchone()[0]
             + por_clase.get("pdf_ilegible", 0) + por_clase.get("ingesta_ilegible", 0))
    return {"filas": filas, "total_archivos": total, "afuera": len(filas),
            "por_clase": por_clase,
            "perfiles_conocidos": sorted(p.stem for p in config.PERFILES.glob("*.json"))}


def api_documento(cx, doc_id: int) -> dict:
    d = cx.execute("""SELECT d.*, a.nombre AS archivo, a.ruta_original, a.sha256,
                             p.legajo, p.acta, p.domicilio, p.lote,
                             v.familia AS familia
                        FROM documento d JOIN archivo a ON a.sha256=d.sha256
                        LEFT JOIN procedencia p ON p.sha256=d.sha256
                        LEFT JOIN v_documento_todo v ON v.documento_id = d.id
                       WHERE d.id=?""", (doc_id,)).fetchone()
    if not d:
        raise NoEncontrado("No existe ese documento. Puede que se haya reprocesado el "
                           "lote y los contratos se hayan vuelto a numerar.")
    campos = [dict(r) for r in cx.execute("""
        SELECT c.*, n.valor_norm,
               (SELECT COUNT(*) FROM conflicto k WHERE k.documento_id=c.documento_id
                 AND k.campo_nombre=c.nombre AND k.estado='abierto') AS en_conflicto
          FROM campo c LEFT JOIN normalizacion n ON n.campo_id=c.id
         WHERE c.documento_id=? ORDER BY c.id""", (doc_id,))]
    conflictos = {}
    for k in cx.execute("SELECT * FROM conflicto WHERE documento_id=? AND estado='abierto'", (doc_id,)):
        conflictos[k["campo_nombre"]] = [dict(v) for v in cx.execute(
            "SELECT * FROM conflicto_variante WHERE conflicto_id=? ORDER BY ruta", (k["id"],))]
    # Sólo las páginas de ESTE contrato: un archivo puede traer varios, y mostrar las
    # del vecino haría que el recuadro caiga sobre el folio equivocado.
    paginas = [dict(r) for r in cx.execute(
        """SELECT nro, ancho_pt, alto_pt, render_escala, rotacion FROM pagina
            WHERE sha256=? AND nro BETWEEN ? AND ? ORDER BY nro""",
        (d["sha256"], d["pagina_desde"] or 1, d["pagina_hasta"] or 99999))]
    hermanos = [dict(r) for r in cx.execute(
        """SELECT id, orden, pagina_desde, pagina_hasta, tipo FROM documento
            WHERE sha256=? ORDER BY orden""", (d["sha256"],))]
    interp = [dict(r) for r in cx.execute("""
        SELECT DISTINCT i.* FROM interpretacion i
          JOIN interpretacion_fuente f ON f.interpretacion_id=i.id
         WHERE f.documento_id=? ORDER BY i.id""", (doc_id,))]
    for i in interp:
        i["fuentes"] = [dict(r) for r in cx.execute("""
            SELECT f.documento_id, f.nota, a.nombre AS archivo
              FROM interpretacion_fuente f
              LEFT JOIN documento d2 ON d2.id=f.documento_id
              LEFT JOIN archivo a ON a.sha256=d2.sha256
             WHERE f.interpretacion_id=?""", (i["id"],))]
    return {"documento": dict(d), "campos": campos, "conflictos": conflictos,
            "paginas": paginas, "hermanos": hermanos, "interpretaciones": interp}



def api_persona(cx, persona_id: int) -> dict:
    """
    Todo lo que sabemos de un contratado, en una pantalla.

    Es la vista que un fiscal pide primero: quién es, cuántos contratos tuvo, cuándo,
    por cuánto, y cuáles se pisan. Los datos salen del carril de datos; las hipótesis
    van aparte, abajo, con sus fuentes.
    """
    p = cx.execute("SELECT * FROM persona WHERE id=?", (persona_id,)).fetchone()
    if not p:
        raise NoEncontrado("No existe esa persona. Puede que se haya reprocesado el lote "
                           "y las fichas se hayan vuelto a armar.")

    contratos = [dict(r) for r in cx.execute("""
        SELECT * FROM v_contrato WHERE persona_id=? ORDER BY inicio, documento_id""",
        (persona_id,))]
    # Y sus comprobantes, en su propia lista. La ficha del contratado tiene que mostrar
    # las dos cosas —qué se le pactó y qué facturó— sin sumarlas: son la misma plata
    # vista de los dos lados, y un acumulado que las junte la cuenta dos veces.
    comprobantes = [dict(r) for r in cx.execute("""
        SELECT * FROM v_comprobante WHERE persona_id=? ORDER BY emitida, documento_id""",
        (persona_id,))]
    alias = [dict(r) for r in cx.execute("""
        SELECT nombre_literal, COUNT(*) AS veces FROM persona_alias
         WHERE persona_id=? GROUP BY nombre_literal ORDER BY veces DESC""", (persona_id,))]

    solapes = [dict(r) for r in cx.execute("""
        SELECT a.documento_id AS doc_a, b.documento_id AS doc_b,
               a.archivo AS archivo_a, b.archivo AS archivo_b,
               CASE WHEN a.camara = b.camara THEN 'intracámara' ELSE 'intercámara' END AS cruce,
               MAX(a.inicio, b.inicio) AS desde, MIN(a.fin, b.fin) AS hasta,
               CAST(julianday(MIN(a.fin,b.fin)) - julianday(MAX(a.inicio,b.inicio)) + 1
                    AS INTEGER) AS dias
          FROM v_contrato a JOIN v_contrato b
            ON a.persona_id=b.persona_id AND a.documento_id < b.documento_id
         WHERE a.persona_id=? AND a.inicio IS NOT NULL AND a.fin IS NOT NULL
           AND b.inicio IS NOT NULL AND b.fin IS NOT NULL
           AND a.inicio <= b.fin AND b.inicio <= a.fin
         ORDER BY dias DESC""", (persona_id,))]

    ids = [c["documento_id"] for c in contratos] or [-1]
    marcas = ",".join("?" * len(ids))
    interp = [dict(r) for r in cx.execute(f"""
        SELECT DISTINCT i.* FROM interpretacion i
          JOIN interpretacion_fuente f ON f.interpretacion_id = i.id
         WHERE f.documento_id IN ({marcas}) ORDER BY i.clase, i.id""", ids)]
    for i in interp:
        i["fuentes"] = [dict(r) for r in cx.execute("""
            SELECT f.documento_id, f.nota, a.nombre AS archivo
              FROM interpretacion_fuente f
              LEFT JOIN documento d ON d.id = f.documento_id
              LEFT JOIN archivo a ON a.sha256 = d.sha256
             WHERE f.interpretacion_id=? LIMIT 12""", (i["id"],))]

    con_monto = [c for c in contratos if c["monto_centavos"] is not None]
    facturado = [f for f in comprobantes if f["monto_centavos"] is not None]
    return {
        "persona": dict(p),
        "alias": alias,
        "contratos": contratos,
        "comprobantes": comprobantes,
        "solapes": solapes,
        "interpretaciones": interp,
        "totales": {
            "contratos": len(contratos),
            "sin_monto": len(contratos) - len(con_monto),
            "sin_fechas": sum(1 for c in contratos if not (c["inicio"] and c["fin"])),
            "acumulado_centavos": sum(c["monto_centavos"] for c in con_monto),
            # Lo facturado va aparte y NUNCA se suma con el acumulado de arriba: son la
            # misma plata vista de los dos lados —lo que se pactó y lo que se cobró—, y
            # un número que las junte la cuenta dos veces.
            "comprobantes": len(comprobantes),
            "facturado_centavos": sum(f["monto_centavos"] for f in facturado),
            # Las facturas de talonario traen el importe a mano y no se leen. Si no se
            # dice cuántas son, el facturado parece completo y no lo está.
            "comprobantes_sin_importe": len(comprobantes) - len(facturado),
            "camaras": sorted({c["camara"] for c in contratos if c["camara"]}),
            "desde": min((c["inicio"] for c in contratos if c["inicio"]), default=None),
            "hasta": max((c["fin"] for c in contratos if c["fin"]), default=None),
        },
    }


# Cuántos campos de la cola se mandan por vez. La cola entera de un legajo grande son
# miles de filas: pintarlas todas cuesta segundos y nadie las mira de una sentada.
POR_PAGINA = 200


def api_cola(cx, filtros=None, desde=0, limite=POR_PAGINA) -> dict:
    """
    La cola, con todo lo necesario para revisar SIN salir de la pantalla.

    Trae el anclaje y las medidas de la foja además del valor: la interfaz muestra el
    folio al lado y una lupa sobre el campo, así revisar deja de costar dos navegaciones
    y volver a buscar dónde se había quedado.

    DEVUELVE UNA PÁGINA Y EL TOTAL DE VERDAD, y eso es lo importante. Antes devolvía una
    lista cortada en 400 sin decirlo: en un legajo con 3.892 campos esperando, la
    pantalla mostraba «1 de 400», alguien los revisaba todos y concluía que el legajo
    estaba terminado. Tres mil cuatrocientos noventa y dos campos que nadie iba a ver
    nunca. Un sistema que existe para que no se pierda trabajo no puede esconder
    trabajo.

    Los filtros van en SQL por el mismo motivo: filtrados en la pantalla, filtraban
    sobre las 400 que habían llegado y no sobre la cola.
    """
    filtros = filtros or {}
    # La consulta versionada arma las columnas y el orden; acá se la envuelve para
    # filtrar y paginar sin duplicarla. Se le saca el punto y coma final para poder
    # meterla como subconsulta.
    base = c4._resolver(
        (config.CONSULTAS / "07_cola_revision.sql").read_text(encoding="utf-8")).strip()
    base = base.rstrip(";")

    condiciones, valores = [], []
    for columna, clave in (("familia", "familia"), ("campo", "campo"), ("clase", "clase")):
        valor = (filtros.get(clave) or "").strip()
        if valor:
            condiciones.append(f"q.{columna} = ?")
            valores.append(valor)
    donde = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""

    total = cx.execute(f"SELECT COUNT(*) FROM ({base}) q{donde}", valores).fetchone()[0]
    total_sin_filtro = cx.execute(f"SELECT COUNT(*) FROM ({base}) q").fetchone()[0]

    # El orden se repite afuera: adentro de una subconsulta, SQLite no garantiza
    # conservarlo. Es el mismo criterio de 07_cola_revision.sql —lo que más daño hace
    # si queda mal, primero— y si allá cambia, acá hay que cambiarlo.
    cur = cx.execute(f"""SELECT * FROM ({base}) q{donde}
                          ORDER BY CASE q.campo
                                     WHEN 'monto' THEN 1 WHEN 'fecha_inicio' THEN 2
                                     WHEN 'fecha_fin' THEN 3 WHEN 'documento' THEN 4
                                     WHEN 'nombre' THEN 5 ELSE 9 END,
                                   COALESCE(q.confianza, 0) ASC, q.campo_id
                          LIMIT ? OFFSET ?""", (*valores, max(1, limite), max(0, desde)))
    columnas = [d[0] for d in cur.description]
    filas = [dict(zip(columnas, f)) for f in cur.fetchall()]
    medidas = {}
    for f in filas:
        clave = (f["documento_id"], f["pagina_nro"])
        if clave not in medidas and f["pagina_nro"]:
            r = cx.execute("""SELECT p.ancho_pt, p.alto_pt, p.rotacion
                                FROM pagina p JOIN documento d ON d.sha256 = p.sha256
                               WHERE d.id=? AND p.nro=?""",
                           (f["documento_id"], f["pagina_nro"])).fetchone()
            medidas[clave] = dict(r) if r else None
        f["pagina"] = medidas.get(clave)
    # Para los campos que no se encontraron en ninguna foja no hay recuadro, pero sí
    # sirve ver el folio: se ofrece la primera página del contrato.
    primeras = {}
    for f in filas:
        if f.get("x0") is None:
            d = f["documento_id"]
            if d not in primeras:
                r = cx.execute("""SELECT d.pagina_desde AS nro, p.ancho_pt, p.alto_pt
                                    FROM documento d
                                    JOIN pagina p ON p.sha256 = d.sha256
                                                 AND p.nro = COALESCE(d.pagina_desde, 1)
                                   WHERE d.id=?""", (d,)).fetchone()
                primeras[d] = dict(r) if r else None
            f["pagina_respaldo"] = primeras[d]
    # La propuesta del lector de manuscrita, si la hay. Va como PROPUESTA y no como
    # valor: el campo sigue vacío hasta que alguien la confirma mirando el recorte que
    # está al lado. Ver ufil/lector_manuscrito.py.
    for f in filas:
        if f.get("motivo") != "manuscrito":
            continue
        r = cx.execute("""SELECT q.valor, q.ilegible, q.nota, q.modelo
                            FROM propuesta q JOIN campo c ON c.id = q.campo_id
                           WHERE c.documento_id=? AND c.nombre=?""",
                       (f["documento_id"], f["campo"])).fetchone()
        if r:
            f["propuesta"] = dict(r)

    for f in filas:
        if f["clase"] == "conflicto":
            k = cx.execute("""SELECT id FROM conflicto WHERE documento_id=? AND campo_nombre=?
                               AND estado='abierto'""", (f["documento_id"], f["campo"])).fetchone()
            f["variantes"] = [dict(v) for v in cx.execute(
                "SELECT ruta, valor, confianza FROM conflicto_variante WHERE conflicto_id=? ORDER BY ruta",
                (k["id"],))] if k else []

    # Qué hay para elegir en cada filtro, y cuántos de cada uno. Sale de la cola ENTERA,
    # no de esta página: ofrecer «facturas» porque justo hay una en las doscientas que
    # llegaron, o no ofrecerlas porque no las hay, es un filtro que miente.
    opciones = {}
    for columna in ("familia", "campo", "clase"):
        opciones[columna] = [
            {"valor": r[0], "n": r[1]} for r in cx.execute(
                f"SELECT q.{columna}, COUNT(*) FROM ({base}) q "
                f"GROUP BY q.{columna} ORDER BY COUNT(*) DESC")]

    # ── Cuánto se lleva hecho ──────────────────────────────────────────────
    #
    # «1 de 6» dice dónde está el cursor y no dice nada de la tarea. En una cola de
    # tres mil campos —que es el caso real— alguien revisa cuarenta minutos, ve «1 de
    # 2.847» y no tiene forma de saber si avanzó. Eso es lo que agota y lo que hace
    # que se deje por la mitad.
    #
    # El universo es lo que ALGUNA VEZ necesitó a una persona: lo que sigue esperando
    # más lo que ya se decidió. Un campo revisado sale de la cola y entra en
    # `revision_humana`; si alguien deshace la decisión, la fila se borra y el campo
    # vuelve a la cola. O sea que los dos números se mueven juntos y el total no
    # cambia solo, que es justamente lo que hace falta para que una barra de avance
    # no mienta.
    revisados = cx.execute("SELECT COUNT(*) FROM revision_humana").fetchone()[0]
    # Y de quiénes. Varias personas de la fiscalía trabajan la misma causa: ver el
    # trabajo del equipo acumulado, y no sólo el propio, es parte de por qué esto se
    # comparte.
    revisores = [{"quien": r[0], "n": r[1]} for r in cx.execute(
        "SELECT quien, COUNT(*) FROM revision_humana GROUP BY quien ORDER BY COUNT(*) DESC")]
    return {"filas": filas, "total": total, "total_sin_filtro": total_sin_filtro,
            "revisados": revisados, "revisores": revisores,
            "desde": desde, "limite": limite, "opciones": opciones}


def api_decidir_campo(cx, campo_id: int, accion: str, valor, quien: str,
                      estado_esperado: str | None = None,
                      observacion: str | None = None) -> dict:
    """
    Una decisión humana sobre un campo.

    `estado_esperado` es el bloqueo optimista y lo manda la pantalla: es el estado en
    que estaba el campo cuando se pintó la cola. Si otra persona lo decidió mientras
    tanto, la decisión NO se aplica y se avisa quién y cómo lo dejó. Sin esto, dos
    revisores sobre el mismo legajo se pisan en silencio y gana el último en apretar,
    que no es necesariamente el que tenía razón.
    """
    from .aplicar_revision import aplicar
    return aplicar(cx, campo_id, accion, valor, quien,
                   estado_esperado=estado_esperado, observacion=observacion)


def api_actividad(cx, limite: int = 60) -> dict:
    """
    Quién hizo qué en este legajo, y cuánto lleva hecho cada uno.

    En la fiscalía esto lo trabajan varias personas sobre la misma causa. Sin una
    pantalla que lo muestre, cada una ve un contador que baja y no sabe si bajó porque
    alguien más está revisando o porque se rompió algo. Y a la hora de firmar un
    informe, «lo revisó una persona» no alcanza: hay que poder decir quién.

    Sale de `revision_humana`, que es el registro que ya se escribe con cada decisión.
    No se agrega ninguna tabla ni se duplica nada.
    """
    # Cuántos campos sostiene hoy cada persona. De `revision_humana`, que guarda la
    # decisión vigente: si alguien deshizo lo suyo, deja de contarlo, que es lo
    # correcto — el número dice cuánto hay decidido, no cuántas veces se tocó.
    quienes = [dict(r) for r in cx.execute("""
        SELECT quien,
               COUNT(*)  AS decisiones,
               MIN(cuando) AS primera,
               MAX(cuando) AS ultima
          FROM revision_humana
         GROUP BY quien
         ORDER BY decisiones DESC, quien""")]

    # «Lo último» sale de `auditoria` y no de `revision_humana`, por dos razones que
    # las pruebas encontraron:
    #
    #  · `revision_humana` guarda la decisión VIGENTE de cada campo, y deshacer la
    #    borra. Leyendo de ahí, «fulano deshizo lo que había hecho mengano» no aparece
    #    nunca — justo el movimiento que más importa ver cuando trabajan varios.
    #  · `cuando` tiene resolución de segundos, así que ocho decisiones del mismo
    #    segundo salían en orden arbitrario. `auditoria.id` es autoincremental: ordena
    #    exacto, siempre.
    ultimas = [dict(r) for r in cx.execute("""
        SELECT u.id, u.quien, u.accion, u.campo_nombre AS campo, u.valor_nuevo AS valor,
               u.cuando, u.sha256, u.orden,
               a.nombre AS archivo, d.id AS documento_id
          FROM auditoria u
          JOIN archivo a  ON a.sha256 = u.sha256
          LEFT JOIN documento d ON d.sha256 = u.sha256 AND d.orden = u.orden
         ORDER BY u.id DESC
         LIMIT ?""", (limite,))]

    return {"quienes": quienes, "ultimas": ultimas,
            "total": sum(q["decisiones"] for q in quienes)}


def api_auditoria(cx, campo_id: int) -> list[dict]:
    """
    Todo lo que le pasó a un campo, en orden. Append-only: nada se edita ni se borra.

    Es lo que permite contestar «¿quién puso esto y cuándo?» sin depender de que alguien
    se acuerde. Va por archivo + orden + nombre de campo, y no por `campo_id`, porque
    reprocesar un archivo vuelve a crear las filas de `campo` con ids nuevos: el rastro
    tiene que sobrevivir a eso.

    El `orden` no es opcional: un PDF trae varios contratos, cada uno con su «monto», y
    sin esa columna el historial de uno mostraría también las decisiones de los otros.
    """
    c = cx.execute("""SELECT c.nombre, d.sha256, d.orden FROM campo c
                        JOIN documento d ON d.id = c.documento_id
                       WHERE c.id=?""", (campo_id,)).fetchone()
    if not c:
        raise NoEncontrado("No existe ese campo.")
    return [dict(r) for r in cx.execute(
        """SELECT accion, valor_anterior, valor_nuevo, motivo_anterior, motivo_nuevo,
                  estado_anterior, estado_nuevo, observacion, quien, cuando
             FROM auditoria
            WHERE sha256=? AND orden=? AND campo_nombre=?
            ORDER BY id""", (c["sha256"], c["orden"], c["nombre"]))]


def api_interpretaciones(cx) -> list[dict]:
    salida = []
    for i in cx.execute("SELECT * FROM interpretacion ORDER BY clase, id"):
        d = dict(i)
        d["fuentes"] = [dict(r) for r in cx.execute("""
            SELECT f.documento_id, f.nota, a.nombre AS archivo
              FROM interpretacion_fuente f
              LEFT JOIN documento d2 ON d2.id=f.documento_id
              LEFT JOIN archivo a ON a.sha256=d2.sha256
             WHERE f.interpretacion_id=? LIMIT 12""", (i["id"],))]
        salida.append(d)
    return salida


# ────────────────────────────────────────────────────────────────── handler ──
class Manejador(BaseHTTPRequestHandler):
    server_version = "ufil/0.1"

    def log_message(self, fmt, *args):
        pass                                   # sin ruido en la consola

    # -- utilidades --
    def _json(self, obj, codigo=200):
        cuerpo = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(cuerpo)

    def _archivo(self, ruta: Path, cache=False):
        """
        Sirve un archivo del disco.

        `cache=True` es para lo que NO cambia entre versiones: tipografías, renders de
        página, el escudo.

        La hoja de estilos y el JavaScript van con etiqueta de versión SACADA DEL
        CONTENIDO. Antes salía de la fecha y el tamaño del archivo, y eso puede mentir:
        dos versiones que coinciden en las dos cosas comparten etiqueta, el navegador
        recibe un 304 y se queda con la vieja para siempre. Con el contenido no hay
        forma: misma etiqueta significa mismos bytes.

        Además la página pide esos dos archivos con `?v=` (ver `_index`), así que una
        versión nueva es una URL nueva y no hay caché —del navegador, de un proxy de la
        oficina, de un CDN— que pueda servir la anterior. Es lo que evita el peor caso:
        el JavaScript nuevo corriendo con el CSS viejo.
        """
        if not ruta.exists() or not ruta.is_file():
            return self._json({"error": "no encontrado"}, 404)
        etag = f'"{huella(ruta)}"'
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "max-age=31536000, immutable"
                             if cache else "no-cache")
            self.end_headers()
            return
        datos = ruta.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(ruta.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("ETag", etag)
        # Con `?v=` en la URL, el contenido de esa URL no cambia nunca: se puede guardar
        # un año. Sin `?v=`, se revalida siempre.
        self.send_header("Cache-Control",
                         "max-age=31536000, immutable"
                         if (cache or "v=" in (urlparse(self.path).query or ""))
                         else "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(datos)

    def do_HEAD(self):
        """Igual que GET pero sin cuerpo. Sin esto el servidor contesta 501."""
        return self.do_GET()

    def _index(self):
        """
        La portada, con la versión de cada archivo puesta en su enlace.

        `app.js` y `estilo.css` se piden como `?v=<huella del contenido>`. Una versión
        nueva es una dirección nueva, así que ninguna caché puede servir la anterior —ni
        el navegador, ni un proxy de la oficina, ni el CDN que hay adelante cuando esto
        está publicado—. Es la diferencia entre «actualizamos» y «actualizamos y todos
        lo ven».

        La portada misma va con `no-store`: es cuatro kilobytes y es la que trae los
        números de versión. Si se guardara, seguiría pidiendo los archivos viejos.
        """
        html = (config.WEB / "index.html").read_text(encoding="utf-8")
        for archivo in ("app.js", "estilo.css"):
            html = html.replace(f"/estatico/{archivo}",
                                f"/estatico/{archivo}?v={huella(config.WEB / archivo)}")
        cuerpo = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(cuerpo)

    def _seguro(self, raiz: Path, nombre: str) -> Path | None:
        """Impide salir del directorio permitido (../../etc/passwd y compañía)."""
        destino = (raiz / unquote(nombre)).resolve()
        return destino if raiz.resolve() in destino.parents or destino.parent == raiz.resolve() else None

    # -- portería --
    def _cookie(self, buscada: str) -> str | None:
        for parte in (self.headers.get("Cookie") or "").split(";"):
            nombre, _, valor = parte.strip().partition("=")
            if nombre == buscada:
                return valor
        return None

    def _vale(self) -> str | None:
        """El vale de sesión que trae la cookie, si trae alguno."""
        return self._cookie("ufil_acceso")

    # -- legajo --
    def _activar_legajo(self) -> None:
        """
        Fija el legajo de este pedido, y con él la base y la carpeta de derivados.

        Se llama al principio de CADA pedido, incluso cuando no viene ninguno. Eso no es
        una precaución de más: los hilos del servidor se reciclan entre pedidos, así que
        el hilo que atendió el legajo A sigue teniéndolo activo cuando le toca el
        siguiente pedido. Si ese pedido no trae legajo y no limpiamos, se le contesta
        con datos de A. Ese es exactamente el cruce que todo esto existe para evitar.

        Un legajo que no está en el registro se trata como ninguno, no como el que
        venía: la cookie la escribe el navegador y no es una fuente confiable.

        Y la omisión del proceso —`UFIL_LEGAJO`, o `ufil --legajo X servir`— se valida
        igual que la cookie. No es simetría por prolijidad: si ese valor apunta a un
        legajo que se eliminó, `db.abrir()` le CREA la carpeta y la base vacías al
        pedido siguiente. Aparece de la nada un legajo que no está en el registro, con
        el número de uno que alguien borró a propósito. Pasó: quedó `UFIL_LEGAJO`
        apuntando a la demostración después de eliminarla.
        """
        pedido = (self._cookie("ufil_legajo") or "").strip()
        if pedido and _slug_valido(pedido):
            config.activar_legajo(pedido)
        else:
            # Sin cookie válida se vuelve a la omisión del proceso, NO a lo que este
            # hilo tenía del pedido anterior.
            omision = (config.LEGAJO_POR_OMISION or "").strip()
            config.activar_legajo(omision if omision and _slug_valido(omision) else None)

    def _sin_permiso(self, ruta: str) -> bool:
        """
        ¿Hay que mandar a este pedido a escribir la clave?

        En modo local nunca: la portería no exige nada. En modo red, todo menos la
        pantalla de acceso misma. Ojo con la tentación de dejar pasar «lo estático»:
        el nombre de un archivo del corpus ya es información del legajo.
        """
        if PORTERIA.deja_pasar(self._vale()):
            return False
        # Las tipografías pasan: son archivos de fuente libre, iguales para cualquier
        # instalación, y no dicen nada del legajo. Dejarlas entrar es lo que hace que la
        # pantalla de acceso se vea como el resto del sistema en vez de como una página
        # cualquiera —que en un organismo también es una forma de decir que es el
        # sistema de verdad y no algo que alguien puso en el medio—. El resto no pasa:
        # hasta el nombre de un archivo del corpus es información del legajo.
        return ruta != "/acceso" and not ruta.startswith("/fuentes/")

    def _a_la_puerta(self, error: bool = False):
        cuerpo = acceso.pagina_de_acceso(error)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        # Para que la app, si se le venció la sesión mientras trabajaba, sepa que esto
        # es la puerta y no una respuesta rota, y mande a escribir la clave de nuevo.
        self.send_header("X-UFIL-Acceso", "requerido")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(cuerpo)

    # -- rutas --
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        ruta = u.path
        if self._sin_permiso(ruta):
            return self._a_la_puerta()
        self._activar_legajo()
        try:
            if ruta in ("/", "/index.html"):
                return self._index()
            if ruta.startswith("/estatico/"):
                p = self._seguro(config.WEB, ruta[len("/estatico/"):])
                return self._archivo(p) if p else self._json({"error": "ruta"}, 400)
            if ruta == "/api/identidad":
                # Los nombres de la casa, resueltos: los valores del código, después
                # `identidad.json` de la carpeta de datos, después el entorno. La
                # interfaz no los tiene escritos adentro.
                from . import identidad as ident
                d = ident.actual()
                d["linea_organismo"] = ident.linea_organismo(d)
                d["firma"] = ident.firma(d)
                d["encabezado"] = ident.encabezado_export(d)
                return self._json(d)
            if ruta == "/marca":
                # El escudo oficial del organismo, si lo pusieron. No hay ninguno por
                # omisión: un emblema institucional redibujado no corresponde.
                # Un escudo pensado para fondo claro se pierde sobre el fondo
                # oscuro y viceversa: si dejaron la versión para oscuro, se sirve esa
                # cuando el navegador pide el tema oscuro.
                oscuro = "prefers-color-scheme: dark" in (
                    self.headers.get("Sec-CH-Prefers-Color-Scheme") or "") \
                    or q.get("tema", [""])[0] == "oscuro"
                # El ícono de la pestaña y el del acceso directo del teléfono salen
                # del mismo lugar y por la misma puerta: son la misma marca en otro
                # formato, y tener tres rutas para lo mismo es cómo se termina con
                # una que quedó apuntando a un archivo que ya no está.
                que = q.get("que", [""])[0]
                if que == "icono":
                    nombres = ("icono-32.png", "icono.svg", "icono-512.png")
                elif que == "tactil":
                    nombres = ("icono-tactil.png", "icono-512.png", "icono.svg")
                else:
                    nombres = (("logo-oscuro.svg", "logo-oscuro.png") if oscuro else ()) + \
                              ("logo.svg", "logo.png", "logo.jpg", "logo.webp")
                for nombre in nombres:
                    archivo = config.MARCA / nombre
                    if archivo.exists():
                        return self._archivo(archivo, cache=True)
                return self._json({"error": "sin marca institucional cargada"}, 404)
            if ruta.startswith("/fuentes/"):
                p = self._seguro(config.FUENTES, ruta[len("/fuentes/"):])
                return self._archivo(p, cache=True) if p else self._json({"error": "ruta"}, 400)
            if ruta == "/descargar":
                # Genera el archivo y lo entrega para bajar. En una demostración es la
                # diferencia entre "se puede exportar" y ver el Excel abierto.
                from . import capa7_export as c7
                que = q.get("que", ["xlsx"])[0]
                # La marca del organismo va puesta salvo que pidan lo contrario. Un
                # borrador interno puede salir sin ella; lo que se presenta, no.
                membrete = q.get("membrete", ["si"])[0] != "no"
                cx = _cx()
                try:
                    destino = config.EXPORT
                    if que == "respaldo":
                        # Copia consistente de la base viva, sin parar el sistema. Es la
                        # forma en que esto se va a usar de verdad: bajarla y ponerla en
                        # un pendrive. Nadie va a abrir una terminal para esto.
                        from . import respaldo as rp
                        carpeta = config.RESPALDOS
                        archivo = rp.hacer(cx, carpeta)
                        tipo = "application/vnd.sqlite3"
                        nombre = Path(archivo).name
                    elif que == "rtf":
                        archivo = c7.a_rtf(cx, destino / "informe.rtf",
                                           membrete=membrete)
                        tipo, nombre = "application/rtf", "informe-analisis.rtf"
                    else:
                        archivo = c7.a_xlsx(cx, destino / "analisis.xlsx",
                                            [c["id"] for c in c4.catalogo()],
                                            membrete=membrete)
                        tipo = ("application/vnd.openxmlformats-officedocument."
                                "spreadsheetml.sheet")
                        nombre = "analisis-contratos.xlsx"
                finally:
                    cx.close()
                datos = Path(archivo).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Disposition", f'attachment; filename="{nombre}"')
                self.send_header("Content-Length", str(len(datos)))
                self.end_headers()
                self.wfile.write(datos)
                return
            if ruta == "/pagina":
                cx = _cx()
                r = cx.execute("""SELECT p.render FROM pagina p
                                    JOIN documento d ON d.sha256=p.sha256
                                   WHERE d.id=? AND p.nro=?""",
                               (int(q["doc"][0]), int(q.get("nro", ["1"])[0]))).fetchone()
                cx.close()
                if not r or not r["render"]:
                    return self._json({"error": "sin render"}, 404)
                return self._archivo(Path(r["render"]), cache=True)

            # Los legajos se contestan ANTES de abrir ninguna base de legajo: esta es
            # la pantalla desde la que se elige cuál, así que todavía no hay uno.
            if ruta == "/api/legajos":
                return self._json({
                    "legajos": legajos.listar(),
                    "activo": config.legajo_activo(),
                    "papelera": legajos.papelera(),
                    "permanencia": permanencia(),
                })

            if ruta.startswith("/api/"):
                cx = _cx()
                try:
                    if ruta == "/api/panel":
                        return self._json(api_panel(cx))
                    if ruta == "/api/cuentas":
                        return self._json(api_cuentas(cx))
                    if ruta == "/api/consultas":
                        return self._json([{k: v for k, v in c.items() if k != "sql"}
                                           for c in c4.catalogo()])
                    if ruta == "/api/consulta":
                        return self._json(c4.correr(cx, q["id"][0]))
                    if ruta == "/api/documentos":
                        return self._json(c4.correr(cx, "02_montos_por_persona")["filas"])
                    if ruta == "/api/contratos":
                        cur = cx.execute("SELECT * FROM v_contrato ORDER BY documento_id")
                        cols = [d[0] for d in cur.description]
                        return self._json([dict(zip(cols, f)) for f in cur.fetchall()])
                    if ruta == "/api/comprobantes":
                        # Las facturas de talonario salen con `monto_centavos` en null:
                        # el importe va a mano y no se lee. Es la verdad —hay un
                        # comprobante y no sabemos por cuánto— y la pantalla lo dice
                        # así en vez de mostrar un cero.
                        cur = cx.execute("""SELECT * FROM v_comprobante
                                             ORDER BY emitida, documento_id""")
                        cols = [d[0] for d in cur.description]
                        return self._json([dict(zip(cols, f)) for f in cur.fetchall()])
                    if ruta == "/api/cruce":
                        return self._json(c4.correr(cx, "09_facturas_contra_contrato"))
                    if ruta == "/api/persona":
                        return self._json(api_persona(cx, int(q["id"][0])))
                    if ruta == "/api/buscar":
                        return self._json(busqueda.buscar(cx, q.get("q", [""])[0]))
                    if ruta == "/api/documento":
                        return self._json(api_documento(cx, int(q["id"][0])))
                    if ruta == "/api/cola":
                        return self._json(api_cola(
                            cx,
                            filtros={k: q.get(k, [""])[0]
                                     for k in ("familia", "campo", "clase")},
                            desde=int(q.get("desde", ["0"])[0] or 0),
                            limite=int(q.get("limite", [str(POR_PAGINA)])[0] or POR_PAGINA)))
                    if ruta == "/api/fusiones":
                        return self._json([dict(r) for r in cx.execute("""
                            SELECT f.*, 
                                   (SELECT nombre_literal FROM persona_alias WHERE persona_id=f.persona_a LIMIT 1) AS lit_a,
                                   (SELECT nombre_literal FROM persona_alias WHERE persona_id=f.persona_b LIMIT 1) AS lit_b,
                                   (SELECT clave_fuerte FROM persona WHERE id=f.persona_a) AS doc_a,
                                   (SELECT clave_fuerte FROM persona WHERE id=f.persona_b) AS doc_b
                              FROM fusion_propuesta f WHERE f.estado='pendiente' ORDER BY f.score DESC""")])
                    if ruta == "/api/interpretaciones":
                        return self._json(api_interpretaciones(cx))
                    if ruta == "/api/trabajo":
                        est = _procesador().estado.como_dict()
                        est["sin_leer"] = cx.execute(
                            """SELECT COUNT(DISTINCT a.sha256) FROM archivo a
                                 JOIN pagina p ON p.sha256 = a.sha256
                                WHERE NOT EXISTS (SELECT 1 FROM lectura l
                                                   WHERE l.pagina_id = p.id)"""
                        ).fetchone()[0]
                        est["lotes"] = [dict(r) for r in cx.execute(
                            """SELECT p.lote, COUNT(*) AS archivos,
                                      SUM(a.paginas) AS paginas,
                                      MAX(a.ingerido_en) AS ultimo
                                 FROM procedencia p JOIN archivo a ON a.sha256=p.sha256
                                GROUP BY p.lote ORDER BY ultimo DESC""")]
                        return self._json(est)
                    if ruta == "/api/actividad":
                        return self._json(api_actividad(cx))
                    if ruta == "/api/afuera":
                        return self._json(api_afuera(cx))
                    if ruta == "/api/salud":
                        # Diagnóstico del entorno + invariantes del pliego, en una sola
                        # pantalla. Quien lo va a mirar no abre una terminal.
                        from . import diagnostico, verificacion
                        chequeos = diagnostico.correr(desde_web=True)
                        # Que el sistema esté abierto a la red no es un detalle de
                        # configuración: cambia quién puede leer el legajo. Tiene que
                        # verse en la misma pantalla que todo lo demás, sin buscarlo.
                        chequeos.append(acceso.como_se_entra(HOST_ESCUCHA,
                                                            PORTERIA.exigir))
                        r = diagnostico.resumen(chequeos)
                        integ = cx.execute("""SELECT COUNT(*) c, MIN(verificado_en) v
                                                FROM integridad""").fetchone()
                        total = cx.execute("SELECT COUNT(*) FROM archivo").fetchone()[0]
                        return self._json({
                            **r,
                            "version": version_interfaz(),
                            "esquema": db.ESQUEMA_VERSION,
                            # Sin rehashear: abrir una pantalla no puede leer del
                            # disco doscientos cincuenta PDF. Eso va con el botón.
                            "invariantes": verificacion.correr(cx, con_integridad=False),
                            "integridad": {"verificados": integ["c"], "total": total,
                                           "mas_viejo": integ["v"]},
                        })
                    if ruta == "/api/excepciones":
                        return self._json([dict(r) for r in cx.execute(
                            "SELECT * FROM excepcion WHERE estado='abierta' ORDER BY id DESC LIMIT 200")])
                    return self._json({"error": "ruta desconocida"}, 404)
                finally:
                    cx.close()
            return self._json({"error": "no encontrado"}, 404)
        except NoEncontrado as e:
            return self._json({"error": str(e), "no_encontrado": True}, 404)
        except FileNotFoundError as e:
            return self._json({"error": str(e), "no_encontrado": True}, 404)
        except (KeyError, IndexError):
            return self._json({"error": "Falta un dato en el pedido.",
                               "no_encontrado": True}, 400)
        except ValueError:
            return self._json({"error": "El identificador tiene que ser un número.",
                               "no_encontrado": True}, 400)
        except Exception as e:
            traceback.print_exc()
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_POST(self):
        u = urlparse(self.path)
        largo = int(self.headers.get("Content-Length", 0))

        # La pantalla de acceso: el único POST que se atiende sin haber pasado antes.
        if u.path == "/acceso":
            cuerpo = self.rfile.read(largo).decode("utf-8", "replace") if largo else ""
            intento = parse_qs(cuerpo).get("clave", [""])[0]
            quien = self.client_address[0]
            vale = PORTERIA.abrir(intento, quien)
            if not vale:
                print(f"  acceso rechazado desde {quien}")
                return self._a_la_puerta(error=True)
            print(f"  acceso concedido a {quien}")
            self.send_response(303)
            # HttpOnly para que ningún script pueda leer el vale; SameSite=Strict para
            # que no viaje si a alguien lo mandan acá desde otra página.
            self.send_header("Set-Cookie",
                             f"ufil_acceso={vale}; Path=/; HttpOnly; SameSite=Strict")
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if self._sin_permiso(u.path):
            return self._a_la_puerta()
        self._activar_legajo()

        # La subida manda el PDF crudo en el cuerpo, con los metadatos en la URL. Es a
        # propósito: evita parsear multipart (que salió de la biblioteca estándar) y da
        # progreso archivo por archivo sin esfuerzo.
        if u.path in ("/api/subir", "/api/procesar"):
            falta = _falta_abrir_legajo()
            if falta:
                return self._json({"ok": False, "sin_legajo": True, "error": falta}, 409)

        if u.path == "/api/subir":
            q = parse_qs(u.query)
            datos = self.rfile.read(largo) if largo else b""
            cx = _cx()
            try:
                g = guardar(cx, datos, q.get("nombre", ["sin-nombre.pdf"])[0],
                            lote=(q.get("lote", ["sin-lote"])[0] or "sin-lote").strip(),
                            legajo=(q.get("legajo", [None])[0] or None),
                            acta=(q.get("acta", [None])[0] or None),
                            domicilio=(q.get("domicilio", [None])[0] or None),
                            operador=(q.get("operador", [None])[0] or None))
                return self._json({"ok": True, "sha256": g.sha256, "nombre": g.nombre,
                                   "paginas": g.paginas, "duplicado": g.duplicado})
            except ArchivoInvalido as e:
                return self._json({"ok": False, "error": str(e)}, 400)
            except Exception as e:
                traceback.print_exc()
                return self._json({"ok": False, "error": f"{type(e).__name__}: {e}"}, 500)
            finally:
                cx.close()

        # ── Volver atrás desde una copia de respaldo ──────────────────────
        # Pisa la base de un legajo, así que es de las operaciones destructivas del
        # sistema. El archivo llega crudo en el cuerpo, igual que un PDF de la ingesta.
        if u.path == "/api/respaldo/mirar":
            import tempfile
            from . import respaldo as rp
            crudo = self.rfile.read(largo) if largo else b""
            if not crudo:
                return self._json({"ok": False, "error": "no llegó ningún archivo"}, 400)
            with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as t:
                t.write(crudo)
                temporal = Path(t.name)
            try:
                return self._json({"ok": True, **rp.inspeccionar(temporal)})
            except rp.RespaldoInvalido as e:
                return self._json({"ok": False, "error": str(e)}, 400)
            finally:
                temporal.unlink(missing_ok=True)

        if u.path == "/api/respaldo/restaurar":
            import tempfile
            from . import respaldo as rp
            slug = (parse_qs(u.query).get("slug", [""])[0] or "").strip()
            confirmacion = (parse_qs(u.query).get("confirmacion", [""])[0] or "").strip()
            if not _slug_valido(slug):
                return self._json({"ok": False, "error": "ese legajo no existe"}, 404)
            try:
                l = legajos.obtener(slug)
            except legajos.LegajoInexistente:
                return self._json({"ok": False, "error": "ese legajo no existe"}, 404)
            if confirmacion != l.numero.strip():
                return self._json({"ok": False, "error":
                    f"Para reemplazar la base hay que escribir el número del legajo: "
                    f"{l.numero}"}, 400)
            t = _procesador().estado.como_dict()
            if t.get("estado") == "corriendo":
                return self._json({"ok": False, "error":
                    "Hay un procesamiento en curso. Paralo antes de reemplazar la base."},
                    409)
            crudo = self.rfile.read(largo) if largo else b""
            if not crudo:
                return self._json({"ok": False, "error": "no llegó ningún archivo"}, 400)
            with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
                tf.write(crudo)
                temporal = Path(tf.name)
            try:
                r = rp.restaurar(temporal, legajos.carpeta_de(slug) / "ufil.sqlite")
            except rp.RespaldoInvalido as e:
                return self._json({"ok": False, "error": str(e)}, 400)
            finally:
                temporal.unlink(missing_ok=True)
            legajos.tocar(slug)
            return self._json({"ok": True, **r})

        try:
            cuerpo = json.loads(self.rfile.read(largo) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "cuerpo JSON inválido"}, 400)
        # ── legajos ──
        # Antes de abrir ninguna base: elegir legajo es justamente lo que se hace
        # cuando todavía no hay uno abierto.
        if u.path == "/api/legajos":
            try:
                l = legajos.crear(cuerpo.get("numero", ""),
                                  cuerpo.get("caratula", ""),
                                  fiscal=cuerpo.get("fiscal"),
                                  creado_por=cuerpo.get("quien"))
            except legajos.LegajoDuplicado as e:
                return self._json({"ok": False, "error": str(e)}, 409)
            except ValueError as e:
                return self._json({"ok": False, "error": str(e)}, 400)
            _SLUGS_CONOCIDOS.add(l.slug)
            return self._json({"ok": True, "slug": l.slug, "numero": l.numero,
                               "caratula": l.caratula})
        if u.path == "/api/legajo/abrir":
            slug = (cuerpo.get("slug") or "").strip()
            # Abrir «ninguno» es válido y es cómo se vuelve a la lista de legajos.
            if slug and not _slug_valido(slug):
                return self._json({"ok": False, "error": "ese legajo no existe"}, 404)
            if slug:
                legajos.tocar(slug)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            # Sin Max-Age: la cookie muere al cerrar el navegador. Un legajo abierto
            # no tiene por qué seguir abierto mañana en una máquina compartida.
            self.send_header("Set-Cookie",
                             f"ufil_legajo={slug}; Path=/; HttpOnly; SameSite=Strict"
                             + ("" if slug else "; Max-Age=0"))
            cuerpo_r = json.dumps({"ok": True, "slug": slug or None}).encode("utf-8")
            self.send_header("Content-Length", str(len(cuerpo_r)))
            self.end_headers()
            self.wfile.write(cuerpo_r)
            return
        if u.path == "/api/legajo/archivar":
            slug = (cuerpo.get("slug") or "").strip()
            if not _slug_valido(slug):
                return self._json({"ok": False, "error": "ese legajo no existe"}, 404)
            legajos.archivar(slug, bool(cuerpo.get("archivar", True)))
            return self._json({"ok": True})

        # ── eliminar, y lo que hace falta para que eliminar no dé miedo ──
        # Eliminar no borra: manda la carpeta entera a `datos/eliminados/`, con la
        # base, los derivados y los originales adentro. Lo único que borra de verdad
        # en todo el sistema es `/api/papelera/destruir`, y sólo alcanza a lo que ya
        # está en la papelera.
        if u.path == "/api/legajo/eliminar":
            slug = (cuerpo.get("slug") or "").strip()
            if not _slug_valido(slug):
                return self._json({"ok": False, "error": "ese legajo no existe"}, 404)
            # Un legajo con un procesamiento en curso tiene la base abierta por otro
            # hilo. Moverla en el medio deja el trabajo escribiendo en un archivo que
            # ya no está donde el registro dice.
            t = _procesador().estado.como_dict()
            if t.get("estado") == "corriendo":
                return self._json({"ok": False, "error":
                    "Hay un procesamiento en curso. Paralo antes de eliminar nada."}, 409)
            try:
                evento = legajos.eliminar(slug, cuerpo.get("confirmacion", ""))
            except legajos.NoSePuede as e:
                return self._json({"ok": False, "error": str(e)}, 400)
            _SLUGS_CONOCIDOS.discard(slug)
            # Si era el que estaba abierto, la cookie apunta a una carpeta que ya no
            # está: se cierra acá y no cuando algo falle tres pantallas más adelante.
            cerrar = config.legajo_activo() == slug
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            if cerrar:
                self.send_header("Set-Cookie",
                                 "ufil_legajo=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0")
            r = json.dumps({"ok": True, "cerrado": cerrar, **evento}).encode("utf-8")
            self.send_header("Content-Length", str(len(r)))
            self.end_headers()
            return self.wfile.write(r)

        if u.path == "/api/papelera/restaurar":
            try:
                l = legajos.restaurar((cuerpo.get("marca") or "").strip())
            except legajos.NoSePuede as e:
                return self._json({"ok": False, "error": str(e)}, 400)
            _SLUGS_CONOCIDOS.add(l.slug)
            return self._json({"ok": True, "slug": l.slug, "numero": l.numero})

        if u.path == "/api/papelera/destruir":
            try:
                evento = legajos.destruir((cuerpo.get("marca") or "").strip(),
                                          cuerpo.get("confirmacion", ""))
            except legajos.NoSePuede as e:
                return self._json({"ok": False, "error": str(e)}, 400)
            return self._json({"ok": True, **evento})

        cx = _cx()
        try:
            if u.path == "/api/detener":
                return self._json(_procesador().detener())
            if u.path == "/api/procesar":
                return self._json(_procesador().arrancar(
                    perfil=cuerpo.get("perfil", "auto"),
                    con_vlm=bool(cuerpo.get("vlm"))))
            if u.path == "/api/campo":
                try:
                    return self._json(api_decidir_campo(
                        cx, int(cuerpo["campo_id"]), cuerpo["accion"],
                        cuerpo.get("valor"), cuerpo.get("quien", ""),
                        estado_esperado=cuerpo.get("estado_esperado"),
                        observacion=cuerpo.get("observacion")))
                except DecisionDesactualizada as e:
                    # 409: no es un error de quien apretó, es que el mundo cambió. La
                    # pantalla vuelve a cargar la cola y muestra el mensaje.
                    return self._json({"error": str(e), "desactualizado": True}, 409)
            if u.path == "/api/auditoria":
                return self._json(api_auditoria(cx, int(cuerpo["campo_id"])))
            if u.path == "/api/fusion":
                c3.decidir_fusion(cx, int(cuerpo["id"]), bool(cuerpo["aceptar"]),
                                  cuerpo.get("quien", ""))
                return self._json({"ok": True})
            if u.path == "/api/verificar":
                # Rehashea un lote de originales, empezando por los que hace más tiempo
                # que no se miran. Es lo caro, así que se hace cuando alguien lo pide.
                from . import verificacion
                r = verificacion.verificar_integridad(cx)
                return self._json(r)
            if u.path == "/api/reindexar":
                return self._json({"paginas": busqueda.reindexar(cx)})
            if u.path == "/api/interpretar":
                return self._json(c5.regenerar(cx))
            if u.path == "/api/exportar":
                from . import capa7_export as c7
                destino = config.EXPORT
                return self._json({"archivos": c7.exportar(cx, destino)})
            return self._json({"error": "ruta desconocida"}, 404)
        except NoEncontrado as e:
            return self._json({"error": str(e), "no_encontrado": True}, 404)
        except (ValueError, KeyError) as e:
            return self._json({"error": str(e)}, 400)
        except Exception as e:
            traceback.print_exc()
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)
        finally:
            cx.close()


def armar(puerto: int = 8713, host: str = "127.0.0.1",
          base: Path | None = None) -> ThreadingHTTPServer:
    """
    El servidor listo para atender, sin ponerse a atender.

    Separado de `servir` para que una prueba pueda levantarlo en un puerto libre
    —`armar(0)` y después mirar `server_address[1]`— y llamar a los endpoints de
    verdad. Hacía falta: los endpoints del borrado de legajos pasaban todas las
    pruebas de unidad mientras el manejador tiraba un TypeError en la primera línea,
    porque nada llamaba al manejador.
    """
    global RUTA_BASE, PORTERIA, HOST_ESCUCHA
    RUTA_BASE = base
    if base is not None or not config.legajo_activo():
        db.abrir(base).close()      # el esquema de la base suelta, una vez
    # Las bases de los legajos NO se tocan acá: se abren cuando alguien entra a ese
    # legajo. Con veinte legajos archivados, arrancar no tiene por qué abrir veinte
    # archivos para no usar diecinueve.
    # Escuchar en la red cambia quién puede entrar: de «el que está sentado acá» a
    # «cualquiera en el mismo wifi». Ahí, y sólo ahí, se pide clave. Se decide por la
    # dirección de escucha y no por una opción aparte, así no hay forma de abrirlo a la
    # red y quedarse sin clave por olvido.
    PORTERIA = acceso.Porteria(exigir=acceso.hace_falta_clave(host))
    HOST_ESCUCHA = host
    # Deja la marca que después permite afirmar —con pruebas, no por deducción— si lo
    # que se guarda sobrevive a un reinicio. Ver ufil/permanencia.py.
    from . import permanencia as _pm
    _pm.registrar_arranque()
    return ThreadingHTTPServer((host, puerto), Manejador)


def servir(base: Path | None, puerto: int = 8713, host: str = "127.0.0.1") -> None:
    srv = armar(puerto, host, base)
    print(f"  UFIL · análisis documental")
    print(f"  http://{'127.0.0.1' if host == '0.0.0.0' else host}:{puerto}")
    print(f"  base: {base or config.BASE}")
    if PORTERIA.exigir:
        print(acceso.texto_de_arranque(puerto, PORTERIA.clave))
    print(f"  (Ctrl-C para parar)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  cerrado")
