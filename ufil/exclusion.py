"""Exclusión entre procesos para operaciones largas sobre un mismo legajo.

El sistema operativo libera el cerrojo al morir el proceso; no quedan leases
caducados. Reentrante por hilo para el pipeline que llama a etapas protegidas.
"""
from contextlib import contextmanager
from functools import wraps
import os
from pathlib import Path
import threading

from . import config


class Ocupado(ValueError):
    pass


_local = threading.local()


@contextmanager
def exclusiva(ruta):
    ruta = str(Path(ruta).resolve())
    activos = getattr(_local, 'activos', set())
    if ruta in activos:
        yield
        return
    candado = Path(ruta + '.operacion.lock')
    candado.parent.mkdir(parents=True, exist_ok=True)
    with candado.open('a+b') as f:
        if f.tell() == 0:
            f.write(b'0')
            f.flush()
        f.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            raise Ocupado('Hay un procesamiento u otra operación en curso en este legajo.') from e
        _local.activos = activos | {ruta}
        try:
            yield
        finally:
            _local.activos = activos
            f.seek(0)
            if os.name == 'nt':
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def conexion(fn):
    @wraps(fn)
    def llamada(cx, *args, **kwargs):
        ruta = cx.execute('PRAGMA database_list').fetchone()[2]
        with exclusiva(ruta or config.BASE):
            return fn(cx, *args, **kwargs)
    return llamada


def trabajador(fn):
    @wraps(fn)
    def llamada(self, *args, **kwargs):
        config.activar_legajo(self.legajo)
        try:
            with exclusiva(self.ruta_base or config.BASE):
                return fn(self, *args, **kwargs)
        except Ocupado as e:
            with self._lock:
                self.estado.estado = 'error'
                self.estado.mensaje = str(e)
    return llamada
