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


def _tomar(candado, *, compartido, mensaje):
    """Lock del SO sin espera; cerrar el handle lo libera incluso tras una caída."""
    candado = Path(candado)
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
                raise Ocupado(mensaje)
        else:
            import fcntl
            fcntl.flock(f.fileno(), (fcntl.LOCK_SH if compartido else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        return f  # Cerrar el handle libera el lock, también al morir el proceso.
    except Exception as e:
        f.close()
        if isinstance(e, OSError):
            raise Ocupado(mensaje) from e
        raise


def tomar_conexiones(ruta, *, compartido):
    """Conexiones compartidas; reemplazar la base exige acceso exclusivo."""
    return _tomar(str(Path(ruta).resolve()) + '.conexiones.lock',
                  compartido=compartido,
                  mensaje='Hay conexiones abiertas o una restauración de respaldo en curso.')


@contextmanager
def _cerrojo(ruta, nombre, *, compartido, mensaje):
    clave = os.path.normcase(str(Path(ruta).resolve())) + nombre
    activos = getattr(_local, 'activos', {})
    if clave in activos:
        # Un exclusivo satisface una petición compartida, nunca al revés.
        if activos[clave] and not compartido:
            raise Ocupado(mensaje)
        yield
        return
    with _tomar(clave, compartido=compartido, mensaje=mensaje):
        _local.activos = {**activos, clave: compartido}
        try:
            yield
        finally:
            _local.activos = activos


@contextmanager
def exclusiva(ruta):
    """Papelera y restauración: excluye toda carga y todo procesamiento."""
    with _cerrojo(ruta, '.operacion.lock', compartido=False,
                  mensaje='Hay una carga, procesamiento/actualización u operación de '
                          'papelera/restauración en curso en este legajo.'):
        yield


@contextmanager
def _compartida(ruta):
    with _cerrojo(ruta, '.operacion.lock', compartido=True,
                  mensaje='Hay una operación de papelera o restauración de respaldo '
                          'en curso en este legajo.'):
        yield


@contextmanager
def procesamiento(ruta):
    """Una corrida por legajo, compatible con cargas, incluso entre procesos."""
    with _compartida(ruta), _cerrojo(
            ruta, '.proceso.lock', compartido=False,
            mensaje='Hay un procesamiento o actualización en curso en este legajo.'):
        yield


@contextmanager
def carga(ruta):
    """Serializa las cargas (hashes, cotejo y temporales) sin excluir el OCR."""
    with _compartida(ruta), _cerrojo(
            ruta, '.carga.lock', compartido=False,
            mensaje='Hay otra subida o ingesta en curso en este legajo.'):
        yield


def _por_conexion(cerrojo):
    def decorar(fn):
        @wraps(fn)
        def llamada(cx, *args, **kwargs):
            ruta = cx.execute('PRAGMA database_list').fetchone()[2]
            with cerrojo(ruta or config.BASE):
                return fn(cx, *args, **kwargs)
        return llamada
    return decorar


def conexion(fn):
    """Actualización: serializa corridas y fija su planificación inicial.

    `actualizacion.aplicar` confirma su primera transacción después de planificar
    y sellar la ingesta, ANTES del OCR. BEGIN IMMEDIATE impide que sus distintas
    consultas vean una carga a mitad de plan. La carga puede esperar esa sección
    breve con el busy_timeout de la conexión; no espera la corrida completa.
    El avance confirma cada página antes de esperar otra respuesta del OCR.
    """
    @_por_conexion(procesamiento)
    @wraps(fn)
    def llamada(cx, *args, **kwargs):
        propia = not cx.in_transaction
        if propia:
            cx.execute('BEGIN IMMEDIATE')
        avance = kwargs.get('avance')

        def confirmar(hechas, total):
            cx.commit()
            if avance:
                avance(hechas, total)

        kwargs['avance'] = confirmar
        try:
            return fn(cx, *args, **kwargs)
        finally:
            if propia and cx.in_transaction:
                cx.rollback()
    return llamada


conexion_exclusiva = _por_conexion(exclusiva)
conexion_carga = _por_conexion(carga)


def trabajador(fn):
    @wraps(fn)
    def llamada(self, *args, **kwargs):
        config.activar_legajo(self.legajo)
        try:
            with procesamiento(self.ruta_base or config.BASE):
                return fn(self, *args, **kwargs)
        except Ocupado as e:
            with self._lock:
                self.estado.estado = 'error'
                self.estado.mensaje = str(e)
    return llamada
