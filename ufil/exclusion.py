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


def tomar_conexiones(ruta, *, compartido):
    """Cada conexión sostiene un lock compartido; reemplazar la base exige exclusivo.

    Se usa LockFileEx en Windows: los locks de lectura de msvcrt no ofrecen
    compartición real en todas las CRT. No bloquea: el llamador recibe 409.
    """
    candado = Path(str(Path(ruta).resolve()) + '.conexiones.lock')
    candado.parent.mkdir(parents=True, exist_ok=True)
    f = candado.open('a+b')
    try:
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            import msvcrt
            class Overlapped(ctypes.Structure):
                _fields_ = [('Internal', ctypes.c_size_t), ('InternalHigh', ctypes.c_size_t),
                            ('Offset', wintypes.DWORD), ('OffsetHigh', wintypes.DWORD),
                            ('hEvent', wintypes.HANDLE)]
            lock = ctypes.WinDLL('kernel32', use_last_error=True).LockFileEx
            lock.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                             wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(Overlapped)]
            lock.restype = wintypes.BOOL
            overlapped = Overlapped()
            if not lock(msvcrt.get_osfhandle(f.fileno()), 1 if compartido else 3,
                        0, 1, 0, ctypes.byref(overlapped)):
                raise Ocupado('Hay conexiones abiertas o una restauración de respaldo en curso.')
        else:
            import fcntl
            fcntl.flock(f.fileno(), (fcntl.LOCK_SH if compartido else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        return f  # Cerrar el handle libera el lock, también al morir el proceso.
    except Exception as e:
        f.close()
        if isinstance(e, OSError):
            raise Ocupado('Hay conexiones abiertas o una restauración de respaldo en curso.') from e
        raise


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
