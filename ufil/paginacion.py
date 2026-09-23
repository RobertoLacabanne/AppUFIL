"""Contrato común: contar en SQL y materializar solamente la página solicitada."""
from __future__ import annotations


def parametros(filtros, ordenes, defecto, sentido='asc'):
    def entero(k, default):
        v = filtros.get(k, default)
        if isinstance(v, bool) or not str(v).isdigit():
            raise ValueError(k + ' debe ser un entero no negativo.')
        return int(v)
    limite, desde = entero('limite', 50), entero('desde', 0)
    if limite < 1:
        raise ValueError('limite debe ser mayor que cero.')
    orden = filtros.get('orden', defecto)
    direccion = filtros.get('sentido', sentido)
    if orden not in ordenes or direccion not in ('asc', 'desc'):
        raise ValueError('Orden inválido. Campos: ' + ', '.join(ordenes) + '; sentido: asc o desc.')
    return dict(desde=desde, limite=min(limite, 500), orden=orden, sentido=direccion)


def booleano(valor):
    if valor in (True, 'true', '1', 1):
        return True
    if valor in (False, 'false', '0', 0):
        return False
    raise ValueError('El filtro booleano debe ser true o false.')


def consultar(cx, clave, sql, args=(), *, filtros=None, ordenes=None, defecto='id',
              sentido='asc', transformar=None, aplicados=None, buscar=(), desempate='1'):
    filtros = filtros or {}
    aplicados = dict(aplicados or {})
    if filtros.get('q') and buscar:
        sql = 'SELECT * FROM ('+sql+') WHERE ('+' OR '.join(c+' LIKE ?' for c in buscar)+')'
        args = list(args) + ['%'+filtros['q']+'%']*len(buscar)
        aplicados['q'] = filtros['q']
    ordenes = ordenes or {'id': 'id'}
    p = parametros(filtros, ordenes, defecto, sentido)
    total = cx.execute('SELECT count(*) FROM (' + sql + ')', args).fetchone()[0]
    # El segundo criterio desempata de forma estable incluso entre nombres iguales.
    orden = ordenes[p['orden']]
    filas = cx.execute('SELECT * FROM (' + sql + ') ORDER BY ' + orden + ' ' + p['sentido'] +
                       ', '+desempate+' ASC LIMIT ? OFFSET ?', list(args) + [p['limite'], p['desde']])
    return {clave: [transformar(dict(r)) if transformar else dict(r) for r in filas],
            'total': total, **p, 'filtros_aplicados': aplicados or {}}
