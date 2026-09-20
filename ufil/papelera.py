"""Papelera transaccional por archivo. Nunca escribe sobre un corpus externo.

Las FK reales determinan los descendientes; las referencias sin FK se declaran
aparte. Los padres compartidos NO son descendientes y nunca se borran. Restaurar
exige que esos padres sigan siendo los mismos; una colisión no se resuelve con
REPLACE, porque eso podría destruir trabajo realizado después de quitar.
"""
from __future__ import annotations

import hashlib
import base64
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


def _instantanea(cx, sha):
    catalogo = _catalogo(cx)
    filas = {t: {r['__rid']: dict(r) for r in cx.execute(
        f'SELECT rowid AS __rid, * FROM {_q(t)}')} for t in catalogo}
    seleccion = {t: set() for t in catalogo}
    for t, rs in filas.items():
        seleccion[t].update(i for i, r in rs.items() if r.get('sha256') == sha)

    while True:
        antes = sum(map(len, seleccion.values()))
        for t, fks in catalogo.items():
            for fk in fks:
                padre = fk['table']
                if padre not in seleccion:
                    raise ConflictoPapelera(f'FK no soportada: {t} → {padre}.')
                if fk['seq'] != 0 or fk['to'] is None:
                    raise ConflictoPapelera(f'FK compuesta o implícita no soportada: {t}.')
                valores = {filas[padre][i][fk['to']] for i in seleccion[padre]}
                seleccion[t].update(i for i, r in filas[t].items()
                                    if r[fk['from']] is not None and r[fk['from']] in valores)
        # Una conclusión que perdió parte de su sustento debe salir completa,
        # incluyendo sus otras fuentes, para no publicar una conclusión engañosa.
        seleccion['interpretacion'].update(
            filas['interpretacion_fuente'][i]['interpretacion_id']
            for i in seleccion['interpretacion_fuente'])
        docs = {filas['documento'][i]['id'] for i in seleccion['documento']}
        paginas = {filas['pagina'][i]['id'] for i in seleccion['pagina']}
        seleccion['interpretacion'].update(i for i, r in filas['interpretacion'].items()
            if r['alcance'] == 'documento' and r['alcance_id'] in {str(d) for d in docs})
        seleccion['resultado_etapa'].update(i for i, r in filas['resultado_etapa'].items()
            if (r['alcance'] == 'archivo' and r['alcance_id'] == sha)
            or (r['alcance'] == 'pagina' and r['alcance_id'] in {str(p) for p in paginas})
            or (r['alcance'] == 'documento' and r['alcance_id'] in {str(d) for d in docs}))
        seleccion['coleccion_item'].update(i for i, r in filas['coleccion_item'].items()
            if (r['clase'] == 'documento' and r['referencia'] in {str(d) for d in docs})
            or (r['clase'] == 'foja' and r['referencia'].startswith(sha + ':')))
        if sum(map(len, seleccion.values())) == antes:
            break

    # Nunca retirar contenido propio de otro archivo por una referencia cruzada.
    # Los vínculos (relación, tramo, evento) sí salen y quedan recuperables.
    for t in ('archivo', 'pagina', 'documento', 'tabla'):
        if any(filas[t][i]['sha256'] != sha for i in seleccion[t]):
            raise ConflictoPapelera(f'{t} de otro archivo depende de éste; separá esa dependencia primero.')
    for t in ('campo', 'tabla_celda'):
        padre, columna = ('documento', 'documento_id') if t == 'campo' else ('tabla', 'tabla_id')
        if any(filas[t][i][columna] not in seleccion[padre] for i in seleccion[t]):
            raise ConflictoPapelera(f'{t} de otro archivo depende de esta lectura.')

    padres = {}
    for t, ids in seleccion.items():
        for fk in catalogo[t]:
            p = fk['table']
            valores = {filas[t][i][fk['from']] for i in ids}
            for i, r in filas[p].items():
                if i not in seleccion[p] and r[fk['to']] in valores:
                    padres.setdefault(p, {})[i] = r
    return {
        'filas': {t: [filas[t][i] for i in sorted(ids)] for t, ids in seleccion.items() if ids},
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


def listar(cx):
    filas = [dict(r) for r in cx.execute('''SELECT sha256,nombre,quitado_en,
        revisiones,documentos,length(pdf) AS bytes,
        json_extract(registros,'$.tiene_revisiones_humanas') AS tiene_revisiones_humanas
        FROM papelera_archivo ORDER BY quitado_en,sha256''')]
    for r in filas:
        r['tiene_revisiones_humanas'] = bool(r['tiene_revisiones_humanas'])
        r['confirmacion_destruir'] = 'DESTRUIR ' + r['sha256']
    return {'archivos': filas}


def tiene_revisiones_humanas(cx, sha):
    return bool(cx.execute('''SELECT
        EXISTS(SELECT 1 FROM revision_humana WHERE sha256=:sha) OR
        EXISTS(SELECT 1 FROM auditoria WHERE sha256=:sha) OR
        EXISTS(SELECT 1 FROM documento WHERE sha256=:sha AND clasificado_por IS NOT NULL) OR
        EXISTS(SELECT 1 FROM campo c JOIN documento d ON d.id=c.documento_id
               WHERE d.sha256=:sha AND c.revisado_por IS NOT NULL) OR
        EXISTS(SELECT 1 FROM foliatura f JOIN pagina p ON p.id=f.pagina_id
               WHERE p.sha256=:sha AND (f.origen='humano' OR f.quien IS NOT NULL)) OR
        EXISTS(SELECT 1 FROM evento WHERE sha256=:sha AND (origen='humano' OR quien IS NOT NULL)) OR
        EXISTS(SELECT 1 FROM mencion WHERE sha256=:sha AND (origen='humano' OR quien IS NOT NULL)) OR
        EXISTS(SELECT 1 FROM tabla WHERE sha256=:sha AND (origen='humano' OR union_quien IS NOT NULL)) OR
        EXISTS(SELECT 1 FROM pieza_tramo WHERE sha256=:sha AND quien IS NOT NULL) OR
        EXISTS(SELECT 1 FROM relacion WHERE (fuente='humano' OR quien IS NOT NULL)
               AND (desde_doc IN (SELECT id FROM documento WHERE sha256=:sha)
                 OR hasta_doc IN (SELECT id FROM documento WHERE sha256=:sha)))''', {'sha':sha}).fetchone()[0])


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
                assets[relativa] = base64.b64encode(ruta.read_bytes()).decode('ascii')
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
            a = cx.execute('SELECT pdf,registros FROM papelera_archivo WHERE sha256=?',
                           (r['sha256'],)).fetchone()
            datos = json.loads(a['registros'])
            for relativa in json.loads(r['rutas']):
                ruta = _ruta_segura(_base(cx), relativa, r['sha256'])
                if ruta.exists():
                    if cx.execute('SELECT 1 FROM archivo WHERE ruta_original=? UNION ALL '
                                  'SELECT 1 FROM pagina WHERE render=?',
                                  (str(ruta),str(ruta))).fetchone():
                        continue  # Otra referencia activa conserva su copia.
                    esperado = (base64.b64decode(datos['assets'][relativa])
                                if relativa in datos.get('assets', {}) else a['pdf'])
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
        datos['tiene_revisiones_humanas'] = tiene_revisiones_humanas(cx, sha)
        datos['assets'], limpiar = _fisicos(cx, a)
        revisiones = len(datos['filas'].get('revision_humana', []))
        cx.execute('INSERT INTO papelera_archivo VALUES (?,?,?,?,?,?,?,?)',
            (sha, a['nombre'], db.ahora(), db.ESQUEMA_VERSION,
             json.dumps(datos, ensure_ascii=False), pdf, revisiones,
             len(datos['filas'].get('documento', []))))
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
        for t, rs in datos['padres'].items():
            for r in rs:
                actual = cx.execute(f'SELECT rowid AS __rid,* FROM {_q(t)} WHERE rowid=?',
                                    (r['__rid'],)).fetchone()
                if actual is None or dict(actual) != r:
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
        for relativa, contenido in datos.get('assets', {}).items():
            ruta = _ruta_segura(base, relativa, sha)
            contenido = base64.b64decode(contenido, validate=True)
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
                    if relativa in datos.get('assets', {}):
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
        a = cx.execute('SELECT registros FROM papelera_archivo WHERE sha256=?', (sha,)).fetchone()
        if not a or cx.execute('SELECT 1 FROM archivo WHERE sha256=?', (sha,)).fetchone():
            raise ConflictoPapelera('Sólo se pueden destruir archivos que ya están en papelera.')
        datos = json.loads(a['registros'])
        rutas = [f'originales/{sha[:2]}/{sha}.pdf', *datos.get('assets', {})]
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
