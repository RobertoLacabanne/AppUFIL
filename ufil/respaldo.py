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
        L.append(f"    · trabajo de {r['quienes']} persona(s)")
    L.append("")
    L.append("  Eso es lo único que no se puede volver a generar. Los PDF originales")
    L.append("  siguen en su carpeta y las imágenes de página se rehacen procesando")
    L.append("  de nuevo. Guardá este archivo en otro disco.")
    L.append("")
    L.append("  Para restaurar: parar el sistema y copiar este archivo sobre")
    L.append(f"  {config.BASE} (borrando antes los .sqlite-wal y .sqlite-shm si están).")
    return "\n".join(L)
