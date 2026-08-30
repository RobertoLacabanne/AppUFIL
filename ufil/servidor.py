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

import json
import mimetypes
import os
import sqlite3
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import acceso, config, db
from . import capa3_identidad as c3
from . import capa4_analisis as c4
from . import capa5_interpretacion as c5
from . import busqueda
from .almacen import ArchivoInvalido, guardar
from .db import ahora
from .trabajo import Procesador

class NoEncontrado(Exception):
    """Lo que se pidió no existe. Se responde 404 y con una explicación, no con una
    excepción de Python en la cara del que está trabajando."""


RUTA_BASE: Path | None = None
PROCESADOR: Procesador | None = None
PORTERIA: acceso.Porteria = acceso.Porteria(exigir=False)


def _cx() -> sqlite3.Connection:
    """Conexión por petición. El esquema ya se aplicó al arrancar, no se toca acá."""
    return db.conectar(RUTA_BASE)


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


def api_panel(cx) -> dict:
    def uno(sql, *p):
        return cx.execute(sql, p).fetchone()[0]

    cobertura = c4.correr(cx, "05_cobertura")["filas"]
    criticos = [c for c in cobertura if c["campo"] in config.CAMPOS_CRITICOS]
    tot = sum(c["total"] for c in criticos) or 1
    solos = sum(c["resueltos_solos"] for c in criticos)
    return {
        "archivos": uno("SELECT COUNT(*) FROM archivo"),
        "duplicados": uno("SELECT COUNT(*) FROM duplicado"),
        "paginas": uno("SELECT COUNT(*) FROM pagina"),
        "documentos": uno("SELECT COUNT(*) FROM documento"),
        "campos": uno("SELECT COUNT(*) FROM campo"),
        "a_revisar": uno("SELECT COUNT(*) FROM campo WHERE estado='a_revisar'"),
        "conflictos": uno("SELECT COUNT(*) FROM conflicto WHERE estado='abierto'"),
        "verificados": uno("SELECT COUNT(*) FROM campo WHERE estado IN ('verificado','corregido')"),
        "fusiones": uno("SELECT COUNT(*) FROM fusion_propuesta WHERE estado='pendiente'"),
        "excepciones": uno("SELECT COUNT(*) FROM excepcion WHERE estado='abierta'"),
        "personas": uno("SELECT COUNT(*) FROM persona"),
        "interpretaciones": uno("SELECT COUNT(*) FROM interpretacion"),
        "cobertura": cobertura,
        "cobertura_pct": round(100.0 * solos / tot, 1),
        "superposiciones": c4.correr(cx, "01_superposicion")["n"],
        "ambas_camaras": c4.correr(cx, "03_ambas_camaras")["n"],
        "fechas_imposibles": c4.correr(cx, "04_fechas_imposibles")["n"],
        "excluidos": c4.correr(cx, "06_excluidos_del_cruce")["n"],
        "lote": (cx.execute("SELECT lote FROM procedencia LIMIT 1").fetchone() or ["—"])[0],
        "demostracion": es_demostracion(cx),
        "marca": any((config.MARCA / n).exists()
                     for n in ("logo.svg", "logo.png", "logo.jpg", "logo.webp")),
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
        "acumulado_centavos": uno("""SELECT COALESCE(SUM(monto_centavos),0) FROM v_contrato"""),
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
                  + uno("""SELECT COUNT(*) FROM excepcion
                            WHERE estado='abierta'
                              AND clase IN ('pdf_ilegible','ingesta_ilegible')"""),
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
    for r in cx.execute("""SELECT e.clase, e.detalle, e.creado_en, e.sha256
                             FROM excepcion e
                            WHERE e.estado='abierta'
                              AND e.clase IN ('pdf_ilegible','ingesta_ilegible')
                            ORDER BY e.id DESC"""):
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
                             p.legajo, p.acta, p.domicilio, p.lote
                        FROM documento d JOIN archivo a ON a.sha256=d.sha256
                        LEFT JOIN procedencia p ON p.sha256=d.sha256
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
        """SELECT id, orden, pagina_desde, pagina_hasta FROM documento
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
    return {
        "persona": dict(p),
        "alias": alias,
        "contratos": contratos,
        "solapes": solapes,
        "interpretaciones": interp,
        "totales": {
            "contratos": len(contratos),
            "sin_monto": len(contratos) - len(con_monto),
            "sin_fechas": sum(1 for c in contratos if not (c["inicio"] and c["fin"])),
            "acumulado_centavos": sum(c["monto_centavos"] for c in con_monto),
            "camaras": sorted({c["camara"] for c in contratos if c["camara"]}),
            "desde": min((c["inicio"] for c in contratos if c["inicio"]), default=None),
            "hasta": max((c["fin"] for c in contratos if c["fin"]), default=None),
        },
    }


def api_cola(cx, limite=400) -> list[dict]:
    """
    La cola, con todo lo necesario para revisar SIN salir de la pantalla.

    Trae el anclaje y las medidas de la foja además del valor: la interfaz muestra el
    folio al lado y una lupa sobre el campo, así revisar deja de costar dos navegaciones
    y volver a buscar dónde se había quedado.
    """
    filas = c4.correr(cx, "07_cola_revision")["filas"][:limite]
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
    for f in filas:
        if f["clase"] == "conflicto":
            k = cx.execute("""SELECT id FROM conflicto WHERE documento_id=? AND campo_nombre=?
                               AND estado='abierto'""", (f["documento_id"], f["campo"])).fetchone()
            f["variantes"] = [dict(v) for v in cx.execute(
                "SELECT ruta, valor, confianza FROM conflicto_variante WHERE conflicto_id=? ORDER BY ruta",
                (k["id"],))] if k else []
    return filas


def api_decidir_campo(cx, campo_id: int, accion: str, valor, quien: str) -> dict:
    from .aplicar_revision import aplicar
    return aplicar(cx, campo_id, accion, valor, quien)


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
        página, el escudo. La hoja de estilos y el JavaScript nunca llevan caché larga:
        con un día de vencimiento, después de actualizar la app la gente seguía viendo
        la interfaz vieja —o peor, el JavaScript nuevo con el CSS viejo— y la única
        salida era enseñarle a cada uno a recargar sin caché. Van con etiqueta de
        versión: el navegador pregunta, y en una máquina local preguntar no cuesta nada.
        """
        if not ruta.exists() or not ruta.is_file():
            return self._json({"error": "no encontrado"}, 404)
        st = ruta.stat()
        etag = f'"{int(st.st_mtime)}-{st.st_size}"'
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.end_headers()
            return
        datos = ruta.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(ruta.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", "max-age=86400" if cache else "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(datos)

    def do_HEAD(self):
        """Igual que GET pero sin cuerpo. Sin esto el servidor contesta 501."""
        return self.do_GET()

    def _seguro(self, raiz: Path, nombre: str) -> Path | None:
        """Impide salir del directorio permitido (../../etc/passwd y compañía)."""
        destino = (raiz / unquote(nombre)).resolve()
        return destino if raiz.resolve() in destino.parents or destino.parent == raiz.resolve() else None

    # -- portería --
    def _vale(self) -> str | None:
        """El vale de sesión que trae la cookie, si trae alguno."""
        for parte in (self.headers.get("Cookie") or "").split(";"):
            nombre, _, valor = parte.strip().partition("=")
            if nombre == "ufil_acceso":
                return valor
        return None

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
        try:
            if ruta in ("/", "/index.html"):
                return self._archivo(config.WEB / "index.html")
            if ruta.startswith("/estatico/"):
                p = self._seguro(config.WEB, ruta[len("/estatico/"):])
                return self._archivo(p) if p else self._json({"error": "ruta"}, 400)
            if ruta == "/marca":
                # El escudo oficial del organismo, si lo pusieron. No hay ninguno por
                # omisión: un emblema institucional redibujado no corresponde.
                for nombre in ("logo.svg", "logo.png", "logo.jpg", "logo.webp"):
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
                cx = _cx()
                try:
                    destino = config.DATOS / "export"
                    if que == "rtf":
                        archivo = c7.a_rtf(cx, destino / "informe.rtf")
                        tipo, nombre = "application/rtf", "informe-analisis.rtf"
                    else:
                        archivo = c7.a_xlsx(cx, destino / "analisis.xlsx",
                                            [c["id"] for c in c4.catalogo()])
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

            if ruta.startswith("/api/"):
                cx = _cx()
                try:
                    if ruta == "/api/panel":
                        return self._json(api_panel(cx))
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
                    if ruta == "/api/persona":
                        return self._json(api_persona(cx, int(q["id"][0])))
                    if ruta == "/api/buscar":
                        return self._json(busqueda.buscar(cx, q.get("q", [""])[0]))
                    if ruta == "/api/documento":
                        return self._json(api_documento(cx, int(q["id"][0])))
                    if ruta == "/api/cola":
                        return self._json(api_cola(cx))
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
                        est = PROCESADOR.estado.como_dict() if PROCESADOR else {"estado": "inactivo"}
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
                    if ruta == "/api/afuera":
                        return self._json(api_afuera(cx))
                    if ruta == "/api/salud":
                        # Diagnóstico del entorno + invariantes del pliego, en una sola
                        # pantalla. Quien lo va a mirar no abre una terminal.
                        from . import diagnostico, verificacion
                        chequeos = diagnostico.correr(desde_web=True)
                        r = diagnostico.resumen(chequeos)
                        integ = cx.execute("""SELECT COUNT(*) c, MIN(verificado_en) v
                                                FROM integridad""").fetchone()
                        total = cx.execute("SELECT COUNT(*) FROM archivo").fetchone()[0]
                        return self._json({
                            **r,
                            "invariantes": verificacion.correr(cx),
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

        # La subida manda el PDF crudo en el cuerpo, con los metadatos en la URL. Es a
        # propósito: evita parsear multipart (que salió de la biblioteca estándar) y da
        # progreso archivo por archivo sin esfuerzo.
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

        try:
            cuerpo = json.loads(self.rfile.read(largo) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "cuerpo JSON inválido"}, 400)
        cx = _cx()
        try:
            if u.path == "/api/procesar":
                if PROCESADOR is None:
                    return self._json({"error": "procesador no disponible"}, 500)
                return self._json(PROCESADOR.arrancar(
                    perfil=cuerpo.get("perfil", "auto"),
                    con_vlm=bool(cuerpo.get("vlm"))))
            if u.path == "/api/campo":
                return self._json(api_decidir_campo(
                    cx, int(cuerpo["campo_id"]), cuerpo["accion"],
                    cuerpo.get("valor"), cuerpo.get("quien", "")))
            if u.path == "/api/fusion":
                c3.decidir_fusion(cx, int(cuerpo["id"]), bool(cuerpo["aceptar"]),
                                  cuerpo.get("quien", ""))
                return self._json({"ok": True})
            if u.path == "/api/reindexar":
                return self._json({"paginas": busqueda.reindexar(cx)})
            if u.path == "/api/interpretar":
                return self._json(c5.regenerar(cx))
            if u.path == "/api/exportar":
                from . import capa7_export as c7
                destino = config.DATOS / "export"
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


def servir(base: Path | None, puerto: int = 8713, host: str = "127.0.0.1") -> None:
    global RUTA_BASE, PROCESADOR, PORTERIA
    RUTA_BASE = base
    db.abrir(base).close()          # el esquema se aplica UNA vez, acá
    PROCESADOR = Procesador(base)
    # Escuchar en la red cambia quién puede entrar: de «el que está sentado acá» a
    # «cualquiera en el mismo wifi». Ahí, y sólo ahí, se pide clave. Se decide por la
    # dirección de escucha y no por una opción aparte, así no hay forma de abrirlo a la
    # red y quedarse sin clave por olvido.
    PORTERIA = acceso.Porteria(exigir=not acceso.es_local(host))
    srv = ThreadingHTTPServer((host, puerto), Manejador)
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
