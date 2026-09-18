"""
Sacar el trabajo del sistema: índice documental, cronología, fichas y punteos.

La regla que ordena todo este módulo
------------------------------------
**Todo lo que sale lleva de dónde salió.** Archivo, foja y —cuando corresponde— el
recuadro. Una planilla con importes que no se puede volver a atar al papel no sirve
para un escrito: quien la lee del otro lado va a preguntar de dónde salió cada número,
y «del sistema» no es una respuesta.

La otra regla
-------------
Estos informes **ordenan y describen**. No concluyen. No dicen quién es responsable, ni
si algo es irregular, ni si alguien mintió. Que dos fechas no cierren es un dato y va;
que eso pruebe algo es una lectura y la hace quien firma el escrito, no el programa.

Sobre los formatos
------------------
`.csv` para lo que se va a seguir trabajando en una planilla, y `.pdf` para lo que se
lee o se adjunta. El `.xlsx` y el `.rtf` de siempre siguen donde estaban, en
ufil/capa7_export.py.

**No hay `.docx`.** Producirlo necesitaría una dependencia más, y esta instalación es
offline con ruedas fijas: agregarla obliga a bajar un paquete en otra máquina y
llevarlo. El `.rtf` que ya existe se abre y se edita en Word, que es la necesidad real.
Si hace falta `.docx` de verdad, es una decisión de instalación y no un olvido.
"""
from __future__ import annotations

import csv
import sqlite3
from datetime import date
from pathlib import Path

import fitz

from . import colecciones as col
from . import cronologia as cr
from . import entidades as en
from . import foliatura as fol


def _escribir_csv(destino: Path, encabezados: list, filas: list) -> Path:
    """
    Un CSV que Excel en castellano abre bien.

    Punto y coma como separador y BOM adelante: sin eso, Excel en una máquina con
    configuración regional argentina mete todo en una sola columna y rompe los acentos.
    Es un detalle de diez minutos que decide si alguien puede usar el archivo o no.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(encabezados)
        w.writerows(filas)
    return destino


# El pie que lleva todo lo que sale. Dice qué es esto y qué no es.
PIE = ("Este listado ordena y describe lo que el sistema leyó de los originales. "
       "No saca conclusiones sobre responsabilidad, intención ni licitud. "
       "Cada fila indica el archivo y la foja de donde sale, para poder verificarla "
       "contra el original.")


def _escribir_pdf(destino: Path, titulo: str, encabezados: list, filas: list,
                  *, nota: str | None = None) -> Path:
    """
    Un PDF de lectura, con la tabla y su pie. Sin dependencias nuevas: lo arma PyMuPDF.

    No pretende ser una pieza de diseño: pretende poder adjuntarse y leerse, y que cada
    fila diga de qué foja salió.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    ancho, alto = fitz.paper_size("a4")
    margen, y = 40, 60
    pagina = doc.new_page(width=ancho, height=alto)

    def linea(texto, tam=8, negrita=False, salto=12):
        nonlocal y, pagina
        if y > alto - 60:
            pagina = doc.new_page(width=ancho, height=alto)
            y = 60
        pagina.insert_text((margen, y), texto, fontsize=tam,
                           fontname="helv" if not negrita else "hebo")
        y += salto

    linea(titulo, tam=14, negrita=True, salto=22)
    linea(f"Generado el {date.today().strftime('%d/%m/%Y')} · {len(filas)} filas",
          tam=8, salto=18)
    if nota:
        linea(nota, tam=8, salto=16)

    anchos = [max(60, min(150, int((ancho - 2 * margen) / max(len(encabezados), 1))))
              for _ in encabezados]
    linea(" | ".join(str(h)[:22].ljust(18) for h in encabezados), tam=7, negrita=True)
    for fila in filas:
        linea(" | ".join(str(c or "")[:22].ljust(18) for c in fila), tam=7, salto=10)

    y = alto - 40
    pagina.insert_textbox(fitz.Rect(margen, alto - 52, ancho - margen, alto - 20),
                          PIE, fontsize=6.5, fontname="helv")
    doc.save(destino)
    doc.close()
    return destino


# ── Índice documental ────────────────────────────────────────────────────────
def indice_documental(cx: sqlite3.Connection) -> tuple[list, list]:
    """
    Qué hay, dónde está y qué es cada pieza. Es el índice que se adjunta a un escrito.

    Incluye las piezas que el sistema **todavía no sabe leer**: dejarlas afuera daría
    un índice que no corresponde a lo que hay en la caja, que es peor que no tener
    índice. Se las muestra con su estado.

    Y lleva la foliatura del papel al lado de la página del PDF, que son dos cosas.
    """
    encabezados = ["Archivo", "Pieza", "Tipo", "Estado", "Fojas del PDF",
                   "Foliatura del papel", "Campos leídos", "Clasificada por"]
    filas = []
    for d in cx.execute("""
            SELECT d.id, d.orden, d.tipo, d.estado, d.pagina_desde, d.pagina_hasta,
                   d.clasificado_por, a.nombre, d.sha256,
                   (SELECT COUNT(*) FROM campo c WHERE c.documento_id = d.id
                     AND c.valor_literal IS NOT NULL) AS campos
              FROM documento d JOIN archivo a ON a.sha256 = d.sha256
             ORDER BY a.nombre, d.orden"""):
        folios = [f["literal"] for f in cx.execute("""
            SELECT f.literal FROM foliatura f JOIN pagina p ON p.id = f.pagina_id
             WHERE p.sha256=? AND p.nro BETWEEN ? AND ? AND f.literal IS NOT NULL
             ORDER BY p.nro""", (d["sha256"], d["pagina_desde"], d["pagina_hasta"]))]
        filas.append([
            d["nombre"], d["orden"], d["tipo"], d["estado"],
            f"{d['pagina_desde']}-{d['pagina_hasta']}",
            ", ".join(folios) if folios else "(sin detectar)",
            d["campos"], d["clasificado_por"] or ""])
    return encabezados, filas


# ── Cronología ───────────────────────────────────────────────────────────────
def cronologia(cx: sqlite3.Connection) -> tuple[list, list]:
    """La línea de tiempo, con qué clase de fecha es cada una y de dónde sale."""
    encabezados = ["Fecha", "Qué es", "Como dice el papel", "Archivo", "Foja",
                   "Tipo de pieza", "De dónde sale"]
    filas = [[e["fecha"], e["que_es"], e["literal"] or "", e["archivo"] or "",
              e["pagina_nro"] or "", e["tipo"] or "", e["origen"]]
             for e in cr.linea(cx, limite=5000)]
    return encabezados, filas


# ── Fichas ───────────────────────────────────────────────────────────────────
def fichas(cx: sqlite3.Connection) -> tuple[list, list]:
    """
    Las fichas: personas, empresas, organismos, obras, expedientes y comprobantes.

    Con cuántas menciones y en cuántos documentos aparece cada una. No con lo que eso
    significa: que alguien aparezca en once piezas es un dato, no un indicio.
    """
    encabezados = ["Clase", "Nombre", "Clave fuerte", "Menciones", "Documentos",
                   "Confirmada por"]
    filas = [[e["clase"], e["nombre"], e["clave_fuerte"] or "", e["menciones"],
              e["documentos"], e["quien"] or ""]
             for e in en.listar(cx)]
    return encabezados, filas


# ── Selección documental y punteo ────────────────────────────────────────────
def punteo_de_coleccion(cx: sqlite3.Connection, coleccion_id: int) -> tuple[list, list]:
    """
    El punteo de una colección: lo que alguien apartó, en su orden, con su anclaje.

    Es lo que se lleva a una audiencia. Por eso el orden es el que la persona le dio y
    no uno que el sistema decida, y por eso cada renglón dice archivo y foja: un punteo
    que no se puede verificar contra el papel no sirve para ofrecer prueba.
    """
    c = col.ver(cx, coleccion_id)
    encabezados = ["#", "Qué es", "Archivo", "Fojas", "Nota", "Apartado por"]
    filas = [[i, it.get("que_es", ""), it.get("archivo") or it.get("nombre") or "",
              it.get("fojas", ""), it.get("nota") or "", it.get("quien") or ""]
             for i, it in enumerate(c["items"], start=1)]
    return encabezados, filas, c["nombre"]


def seleccion(cx: sqlite3.Connection, documento_ids: list) -> tuple[list, list]:
    """Una selección suelta de piezas, con todo lo que se leyó de cada una."""
    if not documento_ids:
        return ["Archivo", "Pieza", "Tipo", "Fojas", "Campo", "Valor", "Estado"], []
    marcas = ",".join("?" * len(documento_ids))
    encabezados = ["Archivo", "Pieza", "Tipo", "Fojas", "Campo", "Valor", "Estado",
                   "Foja del dato"]
    filas = [[f["nombre"], f["orden"], f["tipo"],
              f"{f['pagina_desde']}-{f['pagina_hasta']}", f["campo"],
              f["valor_literal"] or f"Ø {f['nulo_motivo']}", f["estado"],
              f["pagina_nro"] or ""]
             for f in cx.execute(f"""
                 SELECT a.nombre, d.orden, d.tipo, d.pagina_desde, d.pagina_hasta,
                        c.nombre AS campo, c.valor_literal, c.nulo_motivo, c.estado,
                        c.pagina_nro
                   FROM documento d JOIN archivo a ON a.sha256 = d.sha256
                   LEFT JOIN campo c ON c.documento_id = d.id
                  WHERE d.id IN ({marcas})
                  ORDER BY a.nombre, d.orden, c.nombre""", documento_ids)]
    return encabezados, filas


# ── La puerta de entrada ─────────────────────────────────────────────────────
INFORMES = {
    "indice": ("Índice documental", indice_documental),
    "cronologia": ("Cronología", cronologia),
    "fichas": ("Fichas", fichas),
}


class NoSePuede(ValueError):
    """Lo pedido no se puede hacer, y el motivo es para leer."""


def disponibles() -> list[dict]:
    """Qué se puede exportar y en qué formatos. Para ofrecerlo sin escribirlo a mano."""
    return [{"clave": k, "nombre": n, "formatos": ["csv", "pdf"]}
            for k, (n, _) in INFORMES.items()] + [
        {"clave": "coleccion", "nombre": "Punteo de una colección",
         "formatos": ["csv", "pdf"], "necesita": "coleccion_id"},
        {"clave": "seleccion", "nombre": "Selección de piezas",
         "formatos": ["csv", "pdf"], "necesita": "documento_ids"}]


def generar(cx: sqlite3.Connection, clave: str, destino: Path, *, formato: str = "csv",
            coleccion_id: int | None = None, documento_ids: list | None = None) -> Path:
    """Arma el informe pedido y devuelve el archivo."""
    if formato not in ("csv", "pdf"):
        raise NoSePuede(f"formato desconocido: {formato}. Se puede csv o pdf. "
                        f"El .xlsx y el .rtf salen por «exportar».")
    nota = None
    if clave == "coleccion":
        if coleccion_id is None:
            raise NoSePuede("hace falta decir qué colección")
        encabezados, filas, nombre = punteo_de_coleccion(cx, coleccion_id)
        titulo = f"Punteo — {nombre}"
        nota = ("El orden es el que le dio quien armó la colección, no uno que el "
                "sistema haya decidido.")
    elif clave == "seleccion":
        encabezados, filas = seleccion(cx, documento_ids or [])
        titulo = "Selección de piezas"
    elif clave in INFORMES:
        titulo, fn = INFORMES[clave]
        encabezados, filas = fn(cx)
    else:
        raise NoSePuede(f"informe desconocido: {clave}. Los que hay son: "
                        + ", ".join(list(INFORMES) + ["coleccion", "seleccion"]))

    destino = Path(destino)
    if destino.is_dir() or not destino.suffix:
        destino = Path(destino) / f"{clave}.{formato}"
    if formato == "csv":
        return _escribir_csv(destino, encabezados, filas)
    return _escribir_pdf(destino, titulo, encabezados, filas, nota=nota)
