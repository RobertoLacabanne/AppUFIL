"""
Legajos: cada uno con su propia base, en su propia carpeta.

Por qué así y no con una columna `legajo_id`
--------------------------------------------
El requisito es que la información de dos legajos NUNCA se mezcle por error. Con una
columna y un `WHERE legajo_id = ?` en cada consulta, eso depende de que nadie se olvide
el filtro nunca — ni hoy, ni en la consulta que alguien agregue el año que viene. Y una
consulta sin filtro no falla: devuelve de más, en silencio, y el número queda mal en un
informe que ya se firmó.

Con una base por legajo, cruzarlos no es difícil: es imposible. Los datos no están en el
mismo archivo. La garantía la da el sistema de archivos, no la memoria de quien escribe
el próximo SELECT.

Lo que se gana además:
  · El respaldo y la restauración son por legajo, que es como se trabaja.
  · Un legajo que se archiva se mueve de carpeta y deja de pesar.
  · Una base corrupta afecta a un legajo, no a todos.
  · Los derivados —imágenes de página, que es lo que ocupa— también quedan separados.

Lo que se pierde, y hay que decirlo: no se pueden cruzar dos legajos entre sí. Eso es a
propósito. Si algún día hace falta, se hace con una exportación explícita de los dos, no
con una consulta que los toque a los dos a la vez sin que nadie lo haya decidido.

Estructura en disco
-------------------
    datos/
      legajos.sqlite                 el registro: qué legajos existen
      legajos/
        <slug>/
          ufil.sqlite                la base de ESE legajo
          derivados/                 sus imágenes de página
          originales/                los PDF que se subieron por la interfaz
          respaldos/
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from . import config
from .db import ahora

REGISTRO_ESQUEMA = """
CREATE TABLE IF NOT EXISTS legajo (
  slug        TEXT PRIMARY KEY,      -- identificador en disco, derivado del número
  numero      TEXT NOT NULL,         -- el número de legajo tal como lo usa la fiscalía
  caratula    TEXT NOT NULL,
  fiscal      TEXT,
  estado      TEXT NOT NULL DEFAULT 'activo',   -- activo | archivado
  creado_en   TEXT NOT NULL,
  creado_por  TEXT,
  ultima_actividad TEXT
);
CREATE INDEX IF NOT EXISTS ix_legajo_estado ON legajo(estado, ultima_actividad DESC);
"""

ESTADOS = ("activo", "archivado")


class LegajoInexistente(KeyError):
    """Se pidió un legajo que no está en el registro."""


class LegajoDuplicado(ValueError):
    """Ya existe un legajo con ese número."""


@dataclass(frozen=True)
class Legajo:
    slug: str
    numero: str
    caratula: str
    fiscal: str | None
    estado: str

    @property
    def carpeta(self) -> Path:
        return carpeta_de(self.slug)

    @property
    def base(self) -> Path:
        return self.carpeta / "ufil.sqlite"

    @property
    def derivados(self) -> Path:
        return self.carpeta / "derivados"

    @property
    def originales(self) -> Path:
        return self.carpeta / "originales"


def _slug(numero: str) -> str:
    """
    Un nombre de carpeta seguro derivado del número de legajo.

    Se saca de un dato que la fiscalía ya usa —«Legajo N° 87.933»— y no de un
    identificador inventado, para que mirando el disco se entienda qué hay adentro.
    """
    limpio = unicodedata.normalize("NFD", numero)
    limpio = "".join(c for c in limpio if unicodedata.category(c) != "Mn")
    limpio = re.sub(r"[^A-Za-z0-9]+", "-", limpio).strip("-").lower()
    return limpio or "sin-numero"


def carpeta_registro() -> Path:
    return Path(config.DATOS)


def ruta_registro() -> Path:
    return carpeta_registro() / "legajos.sqlite"


def carpeta_de(slug: str) -> Path:
    return carpeta_registro() / "legajos" / slug


def abrir_registro() -> sqlite3.Connection:
    ruta = ruta_registro()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(ruta, timeout=30.0)
    cx.row_factory = sqlite3.Row
    cx.execute("PRAGMA journal_mode=WAL")
    cx.executescript(REGISTRO_ESQUEMA)
    cx.commit()
    return cx


def crear(numero: str, caratula: str, *, fiscal: str | None = None,
          creado_por: str | None = None) -> Legajo:
    numero = (numero or "").strip()
    caratula = (caratula or "").strip()
    if not numero:
        raise ValueError("el legajo necesita un número")
    if not caratula:
        raise ValueError("el legajo necesita una carátula")
    slug = _slug(numero)
    cx = abrir_registro()
    try:
        if cx.execute("SELECT 1 FROM legajo WHERE slug=?", (slug,)).fetchone():
            raise LegajoDuplicado(f"ya existe un legajo con el número «{numero}»")
        cx.execute("""INSERT INTO legajo (slug,numero,caratula,fiscal,creado_en,
                                          creado_por,ultima_actividad)
                      VALUES (?,?,?,?,?,?,?)""",
                   (slug, numero, caratula, (fiscal or "").strip() or None,
                    ahora(), creado_por, ahora()))
        cx.commit()
    finally:
        cx.close()
    # Las carpetas se crean acá y no al abrir: si algo falla, no queda una carpeta
    # huérfana sin registro.
    for sub in ("", "derivados", "originales", "respaldos"):
        (carpeta_de(slug) / sub).mkdir(parents=True, exist_ok=True)
    return Legajo(slug, numero, caratula, fiscal, "activo")


def obtener(slug: str) -> Legajo:
    cx = abrir_registro()
    try:
        r = cx.execute("SELECT * FROM legajo WHERE slug=?", (slug,)).fetchone()
    finally:
        cx.close()
    if not r:
        raise LegajoInexistente(f"no existe el legajo «{slug}»")
    return Legajo(r["slug"], r["numero"], r["caratula"], r["fiscal"], r["estado"])


def slugs() -> set[str]:
    """
    Sólo los identificadores, sin abrir ninguna base de legajo.

    Existe aparte de `listar` porque el servidor valida el legajo de CADA pedido contra
    el registro, y `listar` abre una base por legajo para contar documentos: eso está
    bien para pintar una pantalla y está mal para hacerlo cientos de veces por minuto.
    """
    cx = abrir_registro()
    try:
        return {r["slug"] for r in cx.execute("SELECT slug FROM legajo")}
    finally:
        cx.close()


def listar(estado: str | None = None) -> list[dict]:
    """
    Los legajos, con lo que hace falta para elegir uno: cuántos documentos tiene y
    cuánto trabajo pendiente. Esos números salen de la base de CADA legajo, así que
    esta es la única función que abre varias bases — y sólo para contar, nunca para
    mezclar datos.
    """
    cx = abrir_registro()
    try:
        sql = "SELECT * FROM legajo"
        p = ()
        if estado:
            sql += " WHERE estado=?"
            p = (estado,)
        sql += " ORDER BY (estado='archivado'), ultima_actividad DESC, numero"
        filas = [dict(r) for r in cx.execute(sql, p)]
    finally:
        cx.close()

    for f in filas:
        f.update(_resumen(carpeta_de(f["slug"]) / "ufil.sqlite"))
    return filas


def _resumen(base: Path) -> dict:
    """Cuántos documentos y cuánto pendiente. Si la base no existe todavía, ceros."""
    vacio = {"documentos": 0, "archivos": 0, "pendientes": 0, "existe": False,
             "demostracion": False}
    if not base.exists():
        return vacio
    try:
        cx = sqlite3.connect(f"file:{base}?mode=ro", uri=True, timeout=5.0)
    except sqlite3.OperationalError:
        return vacio
    try:
        def uno(sql, sin_filas=0):
            """
            El primer valor de la consulta, o `sin_filas` si no hay ninguna.

            OJO con el caso de cero filas: un COUNT siempre devuelve una fila, pero un
            `SELECT valor ... WHERE clave=?` no, y `fetchone()` da None. Sin este
            chequeo, un ajuste que no está reventaba la lista ENTERA de legajos —no el
            legajo, la lista— y la pantalla desde la que se elige causa quedaba en
            «Algo falló».
            """
            try:
                f = cx.execute(sql).fetchone()
            except sqlite3.OperationalError:
                return sin_filas               # la tabla todavía no existe
            return sin_filas if f is None else f[0]
        return {
            "documentos": uno("SELECT COUNT(*) FROM documento"),
            "archivos": uno("SELECT COUNT(*) FROM archivo"),
            "pendientes": uno("SELECT COUNT(*) FROM campo WHERE estado IN "
                              "('pendiente_baja','conflicto','no_revisado')"),
            # Si el legajo tiene contratos inventados, la lista tiene que decirlo ANTES
            # de que alguien entre. Adentro ya hay un cartel; acá también, porque la
            # confusión que importa evitar —tomar por real algo que no lo es— empieza
            # en la pantalla donde se elige.
            "demostracion": uno("SELECT valor FROM ajuste WHERE clave='demostracion'",
                                None) == "1",
            "existe": True,
        }
    finally:
        cx.close()


def tocar(slug: str) -> None:
    """Marca actividad en el legajo. Sirve para ordenar la lista por lo más reciente."""
    cx = abrir_registro()
    try:
        cx.execute("UPDATE legajo SET ultima_actividad=? WHERE slug=?", (ahora(), slug))
        cx.commit()
    finally:
        cx.close()


def archivar(slug: str, archivado: bool = True) -> None:
    cx = abrir_registro()
    try:
        cx.execute("UPDATE legajo SET estado=? WHERE slug=?",
                   ("archivado" if archivado else "activo", slug))
        cx.commit()
    finally:
        cx.close()


# ── Eliminar un legajo ─────────────────────────────────────────────────────
#
# Un legajo son meses de trabajo de lectura y revisión a mano, y adentro están los
# PDF que alguien subió por la interfaz —que en una máquina de nube pueden ser la
# única copia que existe de ese lote—. Un botón que borre eso de verdad, de una, es
# un botón que tarde o temprano alguien va a tocar sin querer.
#
# Así que borrar tiene dos tiempos:
#
#   1. `eliminar` MUEVE la carpeta entera a `datos/eliminados/`. Nada se destruye:
#      la base, los derivados, los originales y los respaldos siguen ahí, completos,
#      y se pueden traer de vuelta. Es lo que hace el botón de la interfaz.
#   2. `destruir` borra de verdad, y sólo desde la papelera, con el número escrito a
#      mano otra vez. Es la única función de todo el sistema que borra algo.
#
# Y en los dos casos hay que escribir el número del legajo tal cual. No una casilla
# que se tilda: el número, que obliga a mirar cuál es el que se está por borrar. Es la
# diferencia entre confirmar y leer.

CARPETA_PAPELERA = "eliminados"
BITACORA = "eliminados.jsonl"


class NoSePuede(Exception):
    """Falta una condición para borrar. El mensaje es para mostrarlo tal cual."""


def carpeta_papelera() -> Path:
    return carpeta_registro() / CARPETA_PAPELERA


def _pesa(carpeta: Path) -> int:
    """Bytes que ocupa una carpeta. Un archivo que desaparece a mitad del recorrido
    no puede hacer fallar el cálculo: se está informando un tamaño, no auditando."""
    total = 0
    for p in carpeta.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            pass
    return total


def _anotar(evento: dict) -> None:
    """
    Una línea por cada cosa que se borró, en un archivo aparte del registro.

    Va afuera de la base a propósito: es el rastro de que un legajo existió, y tiene
    que sobrevivir a que la base del registro se pierda o se rehaga. Si no se puede
    escribir, la eliminación sigue: perder la anotación es malo, dejar el legajo a
    medio borrar es peor.
    """
    try:
        destino = carpeta_papelera()
        destino.mkdir(parents=True, exist_ok=True)
        with (destino / BITACORA).open("a", encoding="utf-8") as f:
            f.write(json.dumps(evento, ensure_ascii=False) + "\n")
    except OSError:
        pass


def eliminar(slug: str, confirmacion: str) -> dict:
    """
    Saca el legajo del registro y le manda la carpeta a la papelera.

    No borra nada: mueve. Devuelve con qué nombre quedó guardado, que es lo que hace
    falta para traerlo de vuelta.
    """
    l = obtener(slug)                       # levanta LegajoInexistente si no existe
    if (confirmacion or "").strip() != l.numero.strip():
        raise NoSePuede(f"Para eliminarlo hay que escribir el número del legajo tal "
                        f"como figura: {l.numero}")

    carpeta = carpeta_de(slug)
    # `20260831-164257`: fecha y hora, sin los dos puntos ni el huso, que en un nombre
    # de carpeta y en una URL molestan. La interfaz la vuelve a leer para mostrarla como
    # 31/08/2026 16:42.
    sello = re.sub(r"[^0-9]", "", ahora())[:14]
    marca = f"{slug}--{sello[:8]}-{sello[8:14]}"
    destino = carpeta_papelera() / marca
    destino.parent.mkdir(parents=True, exist_ok=True)

    pesa = _pesa(carpeta) if carpeta.exists() else 0
    resumen = _resumen(carpeta / "ufil.sqlite")

    if carpeta.exists():
        # `shutil.move` entre carpetas del mismo disco es un renombre: instantáneo, y
        # sin la ventana en la que existen dos copias a medio hacer. Entre discos
        # distintos copia y borra, que tarda pero termina igual de completo.
        shutil.move(str(carpeta), str(destino))

    cx = abrir_registro()
    try:
        cx.execute("DELETE FROM legajo WHERE slug=?", (slug,))
        cx.commit()
    finally:
        cx.close()

    evento = {"que": "eliminado", "cuando": ahora(), "slug": slug, "numero": l.numero,
              "caratula": l.caratula, "fiscal": l.fiscal, "marca": marca,
              "bytes": pesa, "documentos": resumen.get("documentos", 0),
              "archivos": resumen.get("archivos", 0)}
    _anotar(evento)
    return evento


def papelera() -> list[dict]:
    """Lo que está en la papelera, de lo más nuevo a lo más viejo."""
    raiz = carpeta_papelera()
    if not raiz.is_dir():
        return []
    fuera = []
    for c in raiz.iterdir():
        if not c.is_dir():
            continue
        # El nombre guarda el slug y la fecha: `94-220--20260831-141203`.
        slug, _, cuando = c.name.partition("--")
        datos = _resumen(c / "ufil.sqlite")
        fuera.append({"marca": c.name, "slug": slug, "eliminado_en": cuando,
                      "bytes": _pesa(c), "documentos": datos.get("documentos", 0),
                      "numero": _numero_guardado(c) or slug})
    fuera.sort(key=lambda d: d["eliminado_en"], reverse=True)
    return fuera


def _en_la_papelera(marca: str) -> Path:
    """
    La carpeta que nombra `marca`, siempre que sea hija directa de la papelera.

    `marca` viene escrita en un pedido HTTP. Sin esta comprobación, un `marca` de
    «../legajos/94-220» hace que el botón de vaciar la papelera le pase el `rmtree`
    a un legajo en uso.

    La comprobación es en positivo —resolver el camino de verdad y exigir que el
    padre sea la papelera— y no una lista de cosas prohibidas. Una lista de
    prohibiciones hay que acertarla entera: la primera versión de esto miraba «/» y
    «\\» y «.», y una prueba escrita para verificarla pasaba igual con las tres
    sacadas, porque lo que estaba frenando el ataque era otra comprobación de más
    abajo. Resolver y comparar no se puede rodear.
    """
    raiz = carpeta_papelera()
    try:
        real = (raiz / marca).resolve(strict=True)
        if real.parent != raiz.resolve() or not real.is_dir():
            raise NoSePuede("Eso no está en la papelera")
    except (OSError, RuntimeError, ValueError):
        raise NoSePuede("Eso no está en la papelera")
    return real


def _numero_guardado(carpeta: Path) -> str | None:
    """
    El número del legajo, leído de la bitácora.

    El slug de la carpeta perdió los puntos («94-220» por «94.220») y ese es
    justamente el número que la persona tiene que escribir para borrar en serio. Que
    el sistema le pida escribir algo distinto de lo que ve en pantalla es la clase de
    detalle que hace que alguien se dé por vencido y busque el atajo.
    """
    try:
        with (carpeta.parent / BITACORA).open(encoding="utf-8") as f:
            for linea in f:
                d = json.loads(linea)
                if d.get("marca") == carpeta.name:
                    return d.get("numero")
    except (OSError, ValueError):
        pass
    return None


def restaurar(marca: str) -> Legajo:
    """Trae un legajo de vuelta de la papelera y lo vuelve a poner en el registro."""
    origen = _en_la_papelera(marca)
    slug = origen.name.partition("--")[0]
    destino = carpeta_de(slug)
    if destino.exists():
        raise NoSePuede(f"Ya hay un legajo usando esa carpeta ({slug}). Renombralo o "
                        f"eliminalo antes de restaurar éste.")

    guardado = {}
    try:
        with (origen.parent / BITACORA).open(encoding="utf-8") as f:
            for linea in f:
                d = json.loads(linea)
                if d.get("marca") == origen.name:
                    guardado = d
    except (OSError, ValueError):
        pass

    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(origen), str(destino))

    cx = abrir_registro()
    try:
        cx.execute("""INSERT INTO legajo (slug,numero,caratula,fiscal,estado,creado_en,
                                          ultima_actividad)
                      VALUES (?,?,?,?, 'activo', ?, ?)""",
                   (slug, guardado.get("numero") or slug,
                    guardado.get("caratula") or "(carátula perdida al eliminar)",
                    guardado.get("fiscal"), ahora(), ahora()))
        cx.commit()
    finally:
        cx.close()
    _anotar({"que": "restaurado", "cuando": ahora(), "marca": origen.name, "slug": slug})
    return obtener(slug)


def destruir(marca: str, confirmacion: str) -> dict:
    """
    Borra de verdad, y sin vuelta atrás. Es la única función del sistema que destruye
    algo, y por eso está sola, exige el número escrito a mano y sólo alcanza lo que ya
    está en la papelera: no hay manera de llegar desde acá a un legajo en uso.
    """
    carpeta = _en_la_papelera(marca)
    numero = _numero_guardado(carpeta) or carpeta.name.partition("--")[0]
    if (confirmacion or "").strip() != numero.strip():
        raise NoSePuede(f"Para borrarlo definitivamente hay que escribir su número: "
                        f"{numero}")

    pesa = _pesa(carpeta)
    shutil.rmtree(carpeta)
    evento = {"que": "destruido", "cuando": ahora(), "marca": carpeta.name,
              "numero": numero, "bytes": pesa}
    _anotar(evento)
    return evento
