"""
Respaldo de la base.

Qué se pierde si se rompe el disco, y por qué esto importa más de lo que parece.

Los PDF originales no son el problema: están en su carpeta, y si hiciera falta se
vuelven a ingerir. Los derivados —las imágenes de página, el texto leído— tampoco: se
regeneran corriendo el proceso de nuevo, que cuesta tiempo de máquina y nada más.

Lo que NO se regenera es el trabajo de las personas: cada campo que alguien miró contra
el folio y corrigió, cada fusión de identidad que alguien confirmó, con quién la hizo y
cuándo. Eso son semanas de trabajo de la unidad y vive en un solo archivo. Sin respaldo,
un disco roto las borra.

El respaldo se hace con `VACUUM INTO`, que es la forma que tiene SQLite de copiar una
base VIVA de manera consistente: no hay que parar el sistema ni pedirle a nadie que
deje de trabajar, y la copia nunca queda a mitad de una escritura. Copiar el archivo a
mano mientras el sistema anda, en cambio, puede dar una base rota, porque el diario de
escrituras (WAL) va aparte.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from . import config
from .castellano import miles, plural


def nombre_sugerido(ahora: datetime | None = None) -> str:
    """Con segundos: dos respaldos seguidos no pueden chocarse de nombre."""
    a = ahora or datetime.now()
    return f"ufil-respaldo-{a.strftime('%Y%m%d-%H%M%S')}.sqlite"


def resumen(cx: sqlite3.Connection) -> dict:
    """Qué hay adentro, en las unidades que le importan a quien decide si respaldar."""
    def uno(sql):
        try:
            return cx.execute(sql).fetchone()[0]
        except sqlite3.OperationalError as e:
            # Sólo se tolera que la tabla no exista todavía —una base recién creada—.
            # Una columna mal escrita tiene que reventar y no volverse un cero
            # silencioso: este resumen es lo que alguien lee para decidir si el
            # respaldo vale la pena, y un cero de mentira dice justo lo contrario.
            if "no such table" in str(e):
                return 0
            raise
    return {
        "archivos": uno("SELECT COUNT(*) FROM archivo"),
        "documentos": uno("SELECT COUNT(*) FROM documento"),
        # Lo irreemplazable: decisiones de personas.
        "revisiones": uno("SELECT COUNT(*) FROM revision_humana"),
        "fusiones": uno("SELECT COUNT(*) FROM fusion_decidida"),
        "quienes": uno("SELECT COUNT(DISTINCT quien) FROM revision_humana"),
    }


def hacer(cx: sqlite3.Connection, destino: Path) -> Path:
    """
    Copia consistente de la base a `destino`. No hace falta parar el sistema.

    `VACUUM INTO` falla si el archivo destino ya existe, que es la conducta que
    queremos: un respaldo no pisa a otro respaldo por accidente.
    """
    destino = Path(destino)
    # Sin extensión .sqlite se entiende como carpeta, exista o no todavía. Si sólo se
    # mirara `is_dir()`, la primera corrida con la carpeta sin crear dejaría un archivo
    # llamado «respaldos» y la segunda fallaría por nombre ocupado.
    if destino.is_dir() or destino.suffix.lower() != ".sqlite":
        destino = destino / nombre_sugerido()
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        raise FileExistsError(f"ya existe {destino}; un respaldo no pisa a otro")
    cx.execute("VACUUM INTO ?", (str(destino),))
    return destino


def texto(destino: Path, r: dict) -> str:
    peso = destino.stat().st_size / 1_000_000
    L = [f"  respaldo en {destino}  ({peso:.1f} MB)", ""]
    L.append(f"  adentro van {r['archivos']} archivos y {r['documentos']} contratos, y "
             f"sobre todo:")
    L.append(f"    · {r['revisiones']} campos revisados a mano")
    L.append(f"    · {r['fusiones']} decisiones de identidad confirmadas")
    if r["quienes"]:
        L.append(f"    · trabajo de {plural(r['quienes'], 'persona', 'personas')}")
    L.append("")
    L.append("  Eso es lo único que no se puede volver a generar. Los PDF originales")
    L.append("  siguen en su carpeta y las imágenes de página se rehacen procesando")
    L.append("  de nuevo. Guardá este archivo en otro disco.")
    L.append("")
    L.append("  Para restaurar: parar el sistema y copiar este archivo sobre")
    L.append(f"  {config.BASE} (borrando antes los .sqlite-wal y .sqlite-shm si están).")
    return "\n".join(L)


# ── Volver atrás ───────────────────────────────────────────────────────────
#
# El respaldo era una calle de una sola mano: se podía bajar la copia y no había forma
# de devolverla. Sirve para la auditoría —queda el archivo— y no sirve para lo que hace
# falta cuando el disco se vacía, que es tener el legajo de vuelta.
#
# Restaurar PISA una base. Es de las tres operaciones destructivas del sistema, junto
# con vaciar la papelera y borrar un legajo, y se trata como tal:
#
#   1. se mira qué hay adentro del archivo ANTES de tocar nada, y se muestra;
#   2. se rechaza cualquier cosa que no sea una base de este sistema;
#   3. la base que estaba NO se borra: se aparta con fecha, para que una restauración
#      equivocada tenga vuelta atrás igual que todo lo demás.

class RespaldoInvalido(ValueError):
    """El archivo no es una copia de este sistema. El mensaje se muestra tal cual."""


def inspeccionar(ruta: Path) -> dict:
    """
    Qué hay adentro de un archivo de respaldo, sin instalarlo.

    Se abre en SOLO LECTURA. Un archivo que llega de afuera no se toca hasta saber qué
    es: abrirlo para escritura le aplicaría la migración de esquema al vuelo y lo
    dejaría modificado antes de que nadie haya decidido nada.
    """
    ruta = Path(ruta)
    if not ruta.is_file():
        raise RespaldoInvalido("No se pudo leer el archivo.")
    # Los controles van del más específico al más general, y cada uno dice lo suyo. Al
    # revés, un PDF de cuarenta bytes se rechazaba con «el archivo está vacío», que es
    # falso y manda a la persona a buscar el problema donde no está.
    with ruta.open("rb") as f:
        cabecera = f.read(16)
    if cabecera != b"SQLite format 3\x00":
        raise RespaldoInvalido(
            "Eso no es una copia de respaldo: no es una base SQLite. La copia se baja "
            "desde el panel, con «Descargar una copia de respaldo».")
    if ruta.stat().st_size < 512:
        raise RespaldoInvalido(
            "El archivo empieza como una base pero está truncado: se cortó la descarga "
            "o la copia quedó a medias.")

    cx = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    cx.row_factory = sqlite3.Row
    try:
        tablas = {r[0] for r in cx.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        faltan = {"archivo", "documento", "campo", "revision_humana"} - tablas
        if faltan:
            raise RespaldoInvalido(
                "Es una base SQLite, pero no de este sistema: le faltan las tablas "
                + ", ".join(sorted(faltan)) + ".")

        def uno(sql, por_omision=0):
            try:
                r = cx.execute(sql).fetchone()
                return (r[0] if r else por_omision) or por_omision
            except sqlite3.Error:
                return por_omision

        return {
            "version_esquema": uno("PRAGMA user_version"),
            "archivos": uno("SELECT COUNT(*) FROM archivo"),
            "documentos": uno("SELECT COUNT(*) FROM documento"),
            "campos": uno("SELECT COUNT(*) FROM campo"),
            # Lo único que no se puede volver a generar. Es el número que hay que mirar
            # antes de pisar nada: si el archivo tiene menos que la base actual, se
            # está por perder trabajo de personas.
            "revisiones": uno("SELECT COUNT(*) FROM revision_humana"),
            "ultima_revision": uno("SELECT MAX(cuando) FROM revision_humana", None),
            "bytes": ruta.stat().st_size,
        }
    finally:
        cx.close()


def restaurar(origen: Path, destino: Path) -> dict:
    """
    Instala el respaldo `origen` como base `destino`.

    Lo que estaba se aparta con fecha —no se borra— y se devuelve dónde quedó. Una
    restauración equivocada sobre el legajo que no era es exactamente el accidente que
    esta función podría causar, así que tiene la misma vuelta atrás que todo lo demás.
    """
    origen, destino = Path(origen), Path(destino)
    datos = inspeccionar(origen)

    destino.parent.mkdir(parents=True, exist_ok=True)
    apartada = None
    if destino.exists():
        sello = datetime.now().strftime("%Y%m%d-%H%M%S")
        apartada = destino.with_name(f"{destino.stem}.reemplazada-{sello}{destino.suffix}")
        destino.replace(apartada)
    # Los archivos laterales del WAL pertenecen a la base que se acaba de apartar: si
    # quedaran, SQLite los aplicaría sobre la base nueva y la corrompería.
    for lateral in ("-wal", "-shm"):
        suelto = destino.with_name(destino.name + lateral)
        if suelto.exists():
            suelto.unlink()

    # Se copia en vez de mover: el archivo de origen puede ser el que la persona
    # subió a una carpeta temporal, y moverlo dejaría la carpeta sin él si algo falla
    # después.
    destino.write_bytes(origen.read_bytes())
    return {**datos, "apartada": str(apartada) if apartada else None}
