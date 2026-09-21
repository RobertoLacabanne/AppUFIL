"""Papelera transaccional por archivo. Nunca escribe sobre un corpus externo.

Las FK reales determinan los descendientes; las referencias sin FK se declaran
aparte. Los padres compartidos NO son descendientes y nunca se borran. Restaurar
exige que esos padres sigan siendo los mismos; una colisión no se resuelve con
REPLACE, porque eso podría destruir trabajo realizado después de quitar.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path

from . import db
from .exclusion import conexion


class ConflictoPapelera(ValueError):
    """El estado actual impide una operación segura (HTTP 409)."""


def _sha(sha):
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise ValueError("sha256 debe tener 64 caracteres hexadecimales en minúscula.")


def _q(nombre):
    return '"' + nombre.replace('"', '""') + '"'


def _catalogo(cx):
    # table_list distingue tablas normales de las tablas internas de FTS5.
    tablas = [r['name'] for r in cx.execute('PRAGMA table_list')
              if r['schema'] == 'main' and r['type'] == 'table'
              and not r['name'].startswith(('sqlite_', 'papelera_'))]
    return {t: [dict(f) for f in cx.execute(f'PRAGMA foreign_key_list({_q(t)})')]
            for t in tablas}


def _por_valores(cx, tabla, columna, valores, condicion='1'):
    """Consultas acotadas, incluso por encima del límite de parámetros SQLite."""
    valores = list(set(valores) - {None})
    for inicio in range(0, len(valores), 400):
        lote = valores[inicio:inicio + 400]
        yield from cx.execute(f'SELECT rowid AS __rid,* FROM {_q(tabla)} '
            f'WHERE {_q(columna)} IN ({",".join("?" for _ in lote)}) AND ({condicion})', lote)


def _instantanea(cx, sha):
    catalogo = _catalogo(cx)
    filas = {t: {} for t in catalogo}
    consultados = {}

    def agregar(t, columna, valores, condicion='1'):
        vistos = consultados.setdefault((t, columna, condicion), set())
        nuevos = set(valores) - vistos - {None}
        vistos.update(nuevos)
        for r in _por_valores(cx, t, columna, nuevos, condicion):
            filas[t][r['__rid']] = dict(r)

    for t, fks in catalogo.items():
        columnas = {r['name'] for r in cx.execute(f'PRAGMA table_info({_q(t)})')}
        if 'sha256' in columnas:
            agregar(t, 'sha256', [sha])
        for fk in fks:
            if fk['table'] not in catalogo or fk['seq'] != 0 or fk['to'] is None:
                raise ConflictoPapelera(f'FK compuesta, implícita o no soportada: {t}.')

    agregar('resultado_etapa', 'alcance_id', [sha], "alcance='archivo'")
    for r in cx.execute("SELECT rowid AS __rid,* FROM coleccion_item "
                        "WHERE clase='foja' AND referencia LIKE ?", (sha + ':%',)):
        filas['coleccion_item'][r['__rid']] = dict(r)
    while True:
        antes = sum(map(len, filas.values()))
        for t, fks in catalogo.items():
            for fk in fks:
                agregar(t, fk['from'], [r[fk['to']] for r in filas[fk['table']].values()])
        # Una conclusión afectada sale completa, con TODAS sus fuentes.
        agregar('interpretacion', 'id', [r['interpretacion_id']
                                        for r in filas['interpretacion_fuente'].values()])
        docs = [str(r['id']) for r in filas['documento'].values()]
        paginas = [str(r['id']) for r in filas['pagina'].values()]
        agregar('interpretacion', 'alcance_id', docs, "alcance='documento'")
        agregar('resultado_etapa', 'alcance_id', docs, "alcance='documento'")
        agregar('resultado_etapa', 'alcance_id', paginas, "alcance='pagina'")
        agregar('coleccion_item', 'referencia', docs, "clase='documento'")
        if sum(map(len, filas.values())) == antes:
            break

    for t in ('archivo', 'pagina', 'documento', 'tabla'):
        if any(r['sha256'] != sha for r in filas[t].values()):
            raise ConflictoPapelera(f'{t} de otro archivo depende de éste; separá esa dependencia primero.')
    for t in ('campo', 'tabla_celda'):
        padre, columna = ('documento', 'documento_id') if t == 'campo' else ('tabla', 'tabla_id')
        if any(r[columna] not in filas[padre] for r in filas[t].values()):
            raise ConflictoPapelera(f'{t} de otro archivo depende de esta lectura.')

    padres = {}
    for t, rs in filas.items():
        for fk in catalogo[t]:
            p = fk['table']
            propios = {r[fk['to']] for r in filas[p].values()}
            valores = {r[fk['from']] for r in rs.values()} - propios
            for r in _por_valores(cx, p, fk['to'], valores):
                padres.setdefault(p, {})[r['__rid']] = dict(r)
    return {
        'filas': {t: [rs[i] for i in sorted(rs)] for t, rs in filas.items() if rs},
        'padres': {t: list(rs.values()) for t, rs in padres.items()},
        'fts': [dict(r) for r in cx.execute('SELECT * FROM pagina_texto WHERE sha256=?', (sha,))],
    }


def _iniciar(cx):
    if cx.in_transaction:
        raise ConflictoPapelera('Confirmá la transacción pendiente antes de operar la papelera.')
    cx.execute('BEGIN IMMEDIATE')
    cx.execute('PRAGMA defer_foreign_keys=ON')


def _ocupado(cx, sha):
    return bool(cx.execute("""SELECT 1 FROM resultado_etapa WHERE estado='corriendo'
        AND (alcance='legajo' OR (alcance='archivo' AND alcance_id=?)
        OR (alcance='pagina' AND alcance_id IN
            (SELECT CAST(id AS TEXT) FROM pagina WHERE sha256=?))
        OR (alcance='documento' AND alcance_id IN
            (SELECT CAST(id AS TEXT) FROM documento WHERE sha256=?))) LIMIT 1""",
        (sha, sha, sha)).fetchone())


def listar(cx, *, limite=100, desde=0):
    def entero(valor, nombre, minimo, maximo):
        if isinstance(valor, bool) or not re.fullmatch(r'[0-9]+', str(valor)):
            raise ValueError(f'{nombre} debe ser un número entero entre {minimo} y {maximo}.')
        # Acotar antes de int también evita enteros arbitrariamente largos por HTTP.
        if len(str(valor)) > 19 or not minimo <= int(valor) <= maximo:
            raise ValueError(f'{nombre} debe estar entre {minimo} y {maximo}.')
        return int(valor)
    limite = entero(limite, 'El límite', 1, 500)
    desde = entero(desde, 'El desplazamiento', 0, 9223372036854775807)
    filas = [dict(r) for r in cx.execute("""SELECT sha256,nombre,quitado_en,
        paginas,lote,revisiones,documentos,length(pdf) AS bytes,
        decisiones_humanas,tiene_revisiones_humanas
        FROM papelera_archivo ORDER BY quitado_en DESC,sha256
        LIMIT ? OFFSET ?""", (limite, desde))]
    for r in filas:
        r['tiene_revisiones_humanas'] = bool(r['tiene_revisiones_humanas'])
        r['confirmacion_destruir'] = 'DESTRUIR ' + r['sha256']
    return {'archivos': filas, 'total': cx.execute('SELECT COUNT(*) FROM papelera_archivo').fetchone()[0],
            'desde': desde, 'limite': limite}


# Cada fila calificante cuenta una vez por archivo, aunque cumpla dos condiciones
# o una relación tenga sus dos extremos en el mismo archivo. No son personas ni
# acciones únicas: historial y estado revisado conservan la definición anterior.
_DECISIONES = {
    'revision_humana': (), 'auditoria': (),
    'documento': (('clasificado_por', None),),
    'campo': (('revisado_por', None),),
    'foliatura': (('origen', 'humano'), ('quien', None)),
    'evento': (('origen', 'humano'), ('quien', None)),
    'mencion': (('origen', 'humano'), ('quien', None)),
    'tabla': (('origen', 'humano'), ('union_quien', None)),
    'pieza_tramo': (('quien', None),),
    'relacion': (('fuente', 'humano'), ('quien', None)),
}


def decisiones_por_archivo(cx):
    consultas = []
    for t, condiciones in _DECISIONES.items():
        condicion = ' OR '.join(f't.{_q(c)} IS NOT NULL' if v is None else
                               f"t.{_q(c)}='humano'" for c, v in condiciones) or '1'
        origen, sha = f'{t} t', 't.sha256'
        if t in ('campo', 'foliatura'):
            padre, fk = ('documento', 'documento_id') if t == 'campo' else ('pagina', 'pagina_id')
            origen += f' JOIN {padre} p ON p.id=t.{fk}'
            sha = 'p.sha256'
        elif t == 'relacion':
            origen += ' JOIN documento p ON p.id=t.desde_doc OR p.id=t.hasta_doc'
            sha = 'p.sha256'
        consultas.append(f'SELECT {sha} sha256, COUNT(DISTINCT t.rowid) n FROM {origen} '
                         f'WHERE ({condicion}) GROUP BY {sha}')
    return {r['sha256']: r['n'] for r in cx.execute(
        'SELECT sha256,SUM(n) n FROM (' + ' UNION ALL '.join(consultas) + ') GROUP BY sha256')}


def _decisiones_instantanea(datos, sha):
    filas = datos['filas']
    docs = {r['id'] for r in filas.get('documento', []) if r['sha256'] == sha}
    paginas = {r['id'] for r in filas.get('pagina', []) if r['sha256'] == sha}
    total = 0
    for t, condiciones in _DECISIONES.items():
        for r in filas.get(t, []):
            propio = (r.get('documento_id') in docs if t == 'campo' else
                      r.get('pagina_id') in paginas if t == 'foliatura' else
                      r.get('desde_doc') in docs or r.get('hasta_doc') in docs if t == 'relacion' else
                      r.get('sha256') == sha)
            if propio and (not condiciones or any(r.get(c) is not None if v is None
                                                  else r.get(c) == v for c, v in condiciones)):
                total += 1
    return total


def tiene_revisiones_humanas(cx, sha):
    return decisiones_por_archivo(cx).get(sha, 0) > 0


def _base(cx):
    return Path(cx.execute('PRAGMA database_list').fetchone()['file']).resolve().parent


def _ruta_segura(base, relativa, sha):
    ruta = base / relativa
    permitidas = (base / 'originales' / sha[:2] / f'{sha}.pdf',
                 base / 'derivados' / sha[:2] / sha)
    resuelta = ruta.resolve()
    if not resuelta.is_relative_to(base.resolve()) or not (
            resuelta == permitidas[0] or resuelta.is_relative_to(permitidas[1])):
        raise ConflictoPapelera('Ruta física fuera del almacenamiento de este archivo.')
    if ruta.is_symlink() or any(p.is_symlink() for p in ruta.parents if p != base.parent):
        raise ConflictoPapelera('No se operan enlaces simbólicos en la papelera.')
    return ruta


def _fisicos(cx, a):
    base, sha = _base(cx), a['sha256']
    original = base / 'originales' / sha[:2] / f'{sha}.pdf'
    limpiar = []
    if Path(a['ruta_original']).resolve() == original:
        limpiar.append(original.relative_to(base).as_posix())
    derivados = base / 'derivados' / sha[:2] / sha
    assets = {}
    if derivados.exists():
        for ruta in derivados.rglob('*'):
            relativa = ruta.relative_to(base).as_posix()
            _ruta_segura(base, relativa, sha)
            if ruta.is_file():
                assets[relativa] = ruta.read_bytes()
                if not cx.execute('SELECT 1 FROM pagina WHERE render=? AND sha256<>?',
                                  (str(ruta),sha)).fetchone():
                    limpiar.append(relativa)
    return assets, limpiar


@conexion
def limpiar_pendientes(cx):
    """Reintentable incluso si hubo un apagón después de un unlink y antes del commit."""
    if cx.in_transaction:
        raise ConflictoPapelera('Hay una transacción pendiente.')
    cx.execute('BEGIN IMMEDIATE')
    try:
        for r in cx.execute('SELECT * FROM papelera_limpieza').fetchall():
            a = cx.execute('SELECT pdf FROM papelera_archivo WHERE sha256=?',
                           (r['sha256'],)).fetchone()
            assets = dict(cx.execute('SELECT ruta,contenido FROM papelera_derivado WHERE sha256=?',
                                     (r['sha256'],)))
            for relativa in json.loads(r['rutas']):
                ruta = _ruta_segura(_base(cx), relativa, r['sha256'])
                if ruta.exists():
                    if cx.execute('SELECT 1 FROM archivo WHERE ruta_original=? UNION ALL '
                                  'SELECT 1 FROM pagina WHERE render=?',
                                  (str(ruta),str(ruta))).fetchone():
                        continue  # Otra referencia activa conserva su copia.
                    esperado = assets.get(relativa, a['pdf'])
                    if ruta.read_bytes() != esperado:
                        raise ConflictoPapelera('Cambió un archivo físico pendiente de limpieza; se conserva.')
                    ruta.chmod(0o600)
                    ruta.unlink()
            cx.execute('DELETE FROM papelera_limpieza WHERE sha256=?', (r['sha256'],))
        cx.commit()
    except Exception:
        cx.rollback()
        raise


@conexion
def quitar(cx, sha, confirmacion):
    _sha(sha)
    if confirmacion != f'QUITAR {sha}':
        raise ValueError(f'Confirmación requerida: QUITAR {sha}')
    _iniciar(cx)
    try:
        if _ocupado(cx, sha):
            raise ConflictoPapelera('El archivo está siendo procesado.')
        a = cx.execute('SELECT * FROM archivo WHERE sha256=?', (sha,)).fetchone()
        if not a:
            raise ConflictoPapelera('El archivo no está en el legajo activo.')
        try:
            pdf = Path(a['ruta_original']).read_bytes()
        except OSError as e:
            raise ConflictoPapelera('No se puede leer el original; no se quitó nada.') from e
        if hashlib.sha256(pdf).hexdigest() != sha:
            raise ConflictoPapelera('El original no coincide con su SHA-256; no se quitó nada.')
        datos = _instantanea(cx, sha)
        decisiones = _decisiones_instantanea(datos, sha)
        assets, limpiar = _fisicos(cx, a)
        lote = (cx.execute('SELECT lote FROM procedencia WHERE sha256=?', (sha,)).fetchone() or [None])[0]
        revisiones = len(datos['filas'].get('revision_humana', []))
        cx.execute('''INSERT INTO papelera_archivo
            (sha256,nombre,quitado_en,version,registros,pdf,revisiones,documentos,
             paginas,lote,decisiones_humanas,tiene_revisiones_humanas) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
            (sha, a['nombre'], db.ahora(), db.ESQUEMA_VERSION,
             json.dumps(datos, ensure_ascii=False), pdf, revisiones,
             len(datos['filas'].get('documento', [])), a['paginas'], lote, decisiones, decisiones > 0))
        cx.executemany('INSERT INTO papelera_derivado VALUES (?,?,?)',
                       [(sha, ruta, contenido) for ruta, contenido in assets.items()])
        cx.execute('INSERT INTO papelera_limpieza VALUES (?,?)', (sha, json.dumps(limpiar)))
        # FK diferidas, pero CASCADE/SET NULL siguen inmediatas. Borrar hojas primero
        # evita alterar filas antes de retirarlas; la instantánea ya está completa.
        pendientes = dict(datos['filas'])
        catalogo = _catalogo(cx)
        while pendientes:
            hojas = [t for t in pendientes if not any(
                f['table'] == t for hijo in pendientes if hijo != t for f in catalogo[hijo])]
            if not hojas:
                raise ConflictoPapelera('Dependencias cíclicas no soportadas; no se quitó nada.')
            for t in hojas:
                cx.executemany(f'DELETE FROM {_q(t)} WHERE rowid=?',
                               [(r['__rid'],) for r in pendientes.pop(t)])
        cx.execute('DELETE FROM pagina_texto WHERE sha256=?', (sha,))
        _invalidar(cx)
        if cx.execute('PRAGMA foreign_key_check').fetchone():
            raise ConflictoPapelera('La base tiene referencias inválidas; no se quitó nada.')
        cx.commit()
        pendiente = False
        try:
            limpiar_pendientes(cx)
        except (OSError, ConflictoPapelera):
            pendiente = True
        return {'ok': True, 'sha256': sha, 'estado': 'papelera', 'revisiones': revisiones,
                'limpieza_pendiente': pendiente}
    except Exception:
        cx.rollback()
        raise


def _invalidar(cx):
    # Sólo agregados: los sellos por archivo/página de otros PDF siguen vigentes.
    cx.execute("UPDATE resultado_etapa SET estado='desactualizado' WHERE alcance='legajo'")


@conexion
def restaurar(cx, sha):
    _sha(sha)
    _iniciar(cx)
    try:
        a = cx.execute('SELECT * FROM papelera_archivo WHERE sha256=?', (sha,)).fetchone()
        if not a:
            raise ConflictoPapelera('El archivo no está en papelera (puede estar ya restaurado).')
        if a['version'] != db.ESQUEMA_VERSION:
            raise ConflictoPapelera('La instantánea requiere una migración antes de restaurarla.')
        if hashlib.sha256(a['pdf']).hexdigest() != sha:
            raise ConflictoPapelera('El PDF de papelera no supera el control de integridad.')
        datos = json.loads(a['registros'])
        assets = dict(cx.execute('SELECT ruta,contenido FROM papelera_derivado WHERE sha256=?', (sha,)))
        for t, rs in datos['padres'].items():
            for r in rs:
                actual = cx.execute(f'SELECT rowid AS __rid,* FROM {_q(t)} WHERE rowid=?',
                                    (r['__rid'],)).fetchone()
                # Confirmar el MISMO tipo de una pieza citada sólo cambia quién
                # la clasificó y cuándo. No modifica identidad, fuente ni tipo,
                # y esa decisión posterior debe permanecer al restaurar.
                # El resto se valida conservadoramente, incluyendo toda clave
                # referenciada, ubicación, contenido y asignación a otro padre.
                informativas = {'clasificado_por', 'clasificado_en'} if t == 'documento' else set()
                if actual is None or any(actual[k] != v for k, v in r.items() if k not in informativas):
                    raise ConflictoPapelera(f'Cambió una referencia compartida ({t}); la papelera se conserva.')
        # Primero probar TODAS las inserciones dentro de la transacción. Un ID
        # reutilizado genera un conflicto explícito, nunca un INSERT OR REPLACE.
        cx.execute('DELETE FROM papelera_archivo WHERE sha256=?', (sha,))
        for t, rs in datos['filas'].items():
            for r in rs:
                valores = {k: v for k, v in r.items() if k != '__rid'}
                cx.execute(f'INSERT INTO {_q(t)} ({",".join(map(_q, valores))}) '
                           f'VALUES ({",".join("?" for _ in valores)})', tuple(valores.values()))
        for r in datos['fts']:
            cx.execute('INSERT INTO pagina_texto(texto,sha256,nro) VALUES (?,?,?)',
                       (r['texto'], r['sha256'], r['nro']))
        if cx.execute('PRAGMA foreign_key_check').fetchone():
            raise ConflictoPapelera('No se pueden recuperar todas las referencias; la papelera se conserva.')
        # Materializar antes del COMMIT. Si el proceso cae, sólo puede quedar una
        # copia sin referencia; la instantánea sigue recuperable en SQLite.
        base = _base(cx)
        destino = base / 'originales' / sha[:2] / f'{sha}.pdf'
        _ruta_segura(base, destino.relative_to(base).as_posix(), sha)
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists():
            if hashlib.sha256(destino.read_bytes()).hexdigest() != sha:
                raise ConflictoPapelera('Hay otro contenido en el destino de restauración.')
        else:
            _escribir(destino, a['pdf'])
        for relativa, contenido in assets.items():
            ruta = _ruta_segura(base, relativa, sha)
            if ruta.exists() and ruta.read_bytes() != contenido:
                raise ConflictoPapelera('Un derivado cambió; la papelera se conserva.')
            if not ruta.exists():
                _escribir(ruta, contenido)
        # Renders guardados con ruta absoluta deben seguir funcionando cuando se
        # restaura una copia de respaldo en otra carpeta.
        for p in datos['filas'].get('pagina', []):
            if p.get('render'):
                partes = Path(p['render']).parts
                if 'derivados' in partes:
                    relativa = Path(*partes[partes.index('derivados'):]).as_posix()
                    if relativa in assets:
                        cx.execute('UPDATE pagina SET render=? WHERE id=?',
                                   (str(base / relativa), p['id']))
        cx.execute('UPDATE archivo SET ruta_original=? WHERE sha256=?', (str(destino), sha))
        _invalidar(cx)
        cx.commit()
        return {'ok': True, 'sha256': sha, 'estado': 'activo'}
    except sqlite3.IntegrityError as e:
        cx.rollback()
        raise ConflictoPapelera('Conflicto con datos actuales; la papelera se conserva íntegra.') from e
    except Exception:
        cx.rollback()
        raise


@conexion
def destruir(cx, sha, confirmacion):
    _sha(sha)
    if confirmacion != f'DESTRUIR {sha}':
        raise ValueError(f'Confirmación requerida: DESTRUIR {sha}')
    # Una restauración abortada puede haber publicado copias antes de su rollback.
    # Reconstituir el trabajo de limpieza evita dejarlas atrás al destruir.
    _iniciar(cx)
    try:
        a = cx.execute('SELECT sha256 FROM papelera_archivo WHERE sha256=?', (sha,)).fetchone()
        if not a or cx.execute('SELECT 1 FROM archivo WHERE sha256=?', (sha,)).fetchone():
            raise ConflictoPapelera('Sólo se pueden destruir archivos que ya están en papelera.')
        rutas = [f'originales/{sha[:2]}/{sha}.pdf',
                 *(r[0] for r in cx.execute('SELECT ruta FROM papelera_derivado WHERE sha256=?', (sha,)))]
        cx.execute('INSERT OR REPLACE INTO papelera_limpieza VALUES (?,?)', (sha,json.dumps(rutas)))
        cx.commit()
    except Exception:
        cx.rollback()
        raise
    # No descartar la última copia hasta completar la limpieza física pendiente.
    limpiar_pendientes(cx)
    _iniciar(cx)
    try:
        if cx.execute('SELECT 1 FROM archivo WHERE sha256=?', (sha,)).fetchone():
            raise ConflictoPapelera('Sólo se pueden destruir archivos que ya están en papelera.')
        if not cx.execute('DELETE FROM papelera_archivo WHERE sha256=?', (sha,)).rowcount:
            raise ConflictoPapelera('El archivo no está en papelera.')
        cx.commit()
        return {'ok': True, 'sha256': sha, 'estado': 'destruido'}
    except Exception:
        cx.rollback()
        raise


def _escribir(destino, contenido):
    """Publicación atómica: un corte no deja el destino final truncado."""
    import tempfile
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, temporal = tempfile.mkstemp(prefix='.restaurar-', dir=destino.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(contenido)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporal, destino)
    finally:
        Path(temporal).unlink(missing_ok=True)
