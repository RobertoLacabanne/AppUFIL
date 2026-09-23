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
    return dict(desde=desde, limite=min(limite, 200), orden=orden, sentido=direccion)


def booleano(valor):
    if valor in (True, 'true', '1', 1):
        return True
    if valor in (False, 'false', '0', 0):
        return False
    raise ValueError('El filtro booleano debe ser true o false.')


def consultar(cx, clave, sql, args=(), *, filtros=None, ordenes=None, defecto='id',
              sentido='asc', transformar=None, aplicados=None):
    filtros = filtros or {}
    ordenes = ordenes or {'id': 'id'}
    p = parametros(filtros, ordenes, defecto, sentido)
    total = cx.execute('SELECT count(*) FROM (' + sql + ')', args).fetchone()[0]
    # El segundo criterio desempata de forma estable incluso entre nombres iguales.
    orden = ordenes[p['orden']]
    filas = cx.execute('SELECT * FROM (' + sql + ') ORDER BY ' + orden + ' ' + p['sentido'] +
                       ', 1 ASC LIMIT ? OFFSET ?', list(args) + [p['limite'], p['desde']])
    return {clave: [transformar(dict(r)) if transformar else dict(r) for r in filas],
            'total': total, **p, 'filtros_aplicados': aplicados or {}}


_AUSENTES = {'', 'sin nombre', '(sin nombre)', 'sin dato', 'no consta', 'ø', '—'}
_LITERALES = {'literal', 'texto', 'descripcion', 'desc_literal', 'valor_literal', 'nombre_literal'}


def ausencias(dato):
    """Conserva literales y ceros; acompaña nulos con motivos sin inventar evidencia."""
    if isinstance(dato, list):
        return [ausencias(v) for v in dato]
    if not isinstance(dato, dict):
        return dato
    salida, motivos = {}, dict(dato.get('ausencias') or {})
    for k, v in dato.items():
        if k == 'ausencias':
            continue
        if k not in _LITERALES and isinstance(v, str) and v.strip().casefold() in _AUSENTES:
            v = None
        salida[k] = ausencias(v)
        if v is None and k not in ('ausencia',):
            motivos.setdefault(k, 'no_consta')
    if 'valor' in salida:
        salida['ausencia'] = (dato.get('ausencia') or 'no_consta') if salida['valor'] is None else None
    if motivos:
        salida['ausencias'] = motivos
    return salida
