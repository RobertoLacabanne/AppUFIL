"""Referencias independientes y cuentas nominales reconstruibles con Decimal."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, localcontext

from . import comparabilidad as cp, confianza as cf, renglones as rg

EJECUCION = frozenset({'adjudicacion', 'orden_compra', 'remito', 'factura', 'orden_pago', 'pago'})


def dinero(n):
    return None if n is None else format(n.quantize(Decimal('.01'), rounding=ROUND_HALF_UP), '.2f')


def _cuantil(xs, p):
    """Interpolación lineal inclusiva (posición (n-1)*p); n=1 tiene rango cero."""
    pos = Decimal(len(xs) - 1) * p
    i = int(pos)
    return xs[i] + (xs[min(i + 1, len(xs) - 1)] - xs[i]) * (pos - i)


def estadisticas(valores, nivel):
    xs = sorted(valores)
    if not xs:
        return None
    with localcontext() as ctx:
        ctx.prec = 40
        n = len(xs)
        media = sum(xs) / n
        desvio = (sum((x - media) ** 2 for x in xs) / (n - 1)).sqrt() if n > 1 else None
        return {'nivel': nivel, 'n': n, 'minimo': dinero(xs[0]), 'maximo': dinero(xs[-1]),
                'media': dinero(media), 'mediana': dinero(_cuantil(xs, Decimal('.5'))),
                'desvio': dinero(desvio),
                'rango_intercuartil': dinero(_cuantil(xs, Decimal('.75')) - _cuantil(xs, Decimal('.25')))}


def _observacion(cx, r):
    c = rg.contratacion_de(cx, r)
    return cp.Observacion(desc_norm=r['desc_norm'], unidad=r['unidad_norm'], moneda=r['moneda'],
                          marca=r['marca'], modelo=r['modelo'], categoria=r['categoria'], iva=r['iva'],
                          condiciones=frozenset(json.loads(r['condiciones'])),
                          cantidad=Decimal(r['cantidad']) if r['cantidad'] is not None else None,
                          fecha=date.fromisoformat(r['fecha_precio']) if r['fecha_precio'] else None,
                          etapa=r['etapa'], contratacion=c['id'] if c else None)


def _decision(cx, a, b):
    asignaciones = [cx.execute('SELECT * FROM renglon_item WHERE renglon_clave=?', (r['clave'],)).fetchone()
                    for r in (a, b)]
    x, y = asignaciones
    if x and y and x['item_id'] == y['item_id']:
        for r in (x, y):
            if r['origen'] == 'humano' and r['decision'] == 'distinto':
                return 'distinto', r['quien']
        if all(r['origen'] == 'humano' and r['decision'] == 'mismo' for r in (x, y)):
            return 'mismo', ', '.join(sorted({x['quien'], y['quien']}))
    return None, None


def comparar(cx, rid, niveles=None, *, resumen=False):
    if isinstance(niveles, str):
        niveles = niveles.split(',') if niveles else None
    if niveles is not None and (not niveles or any(n not in cp.ORDEN_NIVELES for n in niveles)):
        raise ValueError('Los niveles válidos son A, B, C, D y E.')
    a = rg.fila(cx, rid)
    oa = _observacion(cx, a)
    refs, excluidas, vistas = [], [], set()
    for row in cx.execute('SELECT * FROM renglon WHERE vigente=1 AND documento_id IS NOT NULL AND id!=? ORDER BY id', (rid,)):
        b = dict(row)
        ob = _observacion(cx, b)
        motivo = None
        if b['documento_id'] == a['documento_id']:
            motivo = 'Otro renglón del mismo documento: no es una referencia independiente.'
        elif oa.contratacion is not None and oa.contratacion == ob.contratacion and b['etapa'] in EJECUCION:
            motivo = 'Etapa de ejecución de la misma contratación: corresponde a la misma compra.'
        elif b['precio_unitario'] is None:
            motivo = 'No tiene precio unitario utilizable.'
        elif b['etapa'] not in cp.ETAPAS_PRIMARIAS | cp.ETAPAS_COTIZACION:
            motivo = 'La etapa documental no permite usarlo como referencia de precio.'
        if motivo and resumen:
            continue
        decision, quien = _decision(cx, a, b)
        comp = cp.comparabilidad(oa, ob, decision_humana=decision, quien=quien)
        nivel = cp.nivel(oa, ob, comp['estado'])
        if motivo is None and nivel is None:
            atributos = ', '.join(m['atributo'] for m in comp['motivos'] if m['efecto'] == 'bloquea')
            motivo = 'No comparable: ' + atributos + '.'
        if motivo is None and niveles is not None and nivel not in niveles:
            motivo = 'Nivel fuera de la selección: ' + nivel + '.'
        # Repetir la misma cotización del mismo proveedor no multiplica la muestra.
        proveedor = b['proveedor_id'] or b['proveedor_cuit'] or ('documento', b['documento_id'])
        huella = (proveedor, ob.contratacion, b['etapa'], b['fecha_precio'], b['desc_norm'],
                  b['unidad_norm'], b['moneda'], b['iva'], b['cantidad'], b['precio_unitario'])
        if motivo is None and huella in vistas:
            motivo = 'Precio repetido de la misma fuente comercial: no agrega una referencia independiente.'
        if motivo:
            if not resumen:
                excluidas.append({'renglon': rg.serializar(cx, b), 'motivo': motivo})
            continue
        vistas.add(huella)
        refs.append((b, {'renglon': None if resumen else rg.serializar(cx, b), 'nivel': nivel,
                         'comparabilidad': {'estado': comp['estado'], 'motivos': comp['motivos']},
                         'dias': abs((oa.fecha - ob.fecha).days) if oa.fecha and ob.fecha else None}))
    elegido, advertencias = cp.elegir_nivel([r['nivel'] for _, r in refs])
    usadas = [(b, r) for b, r in refs if r['nivel'] == elegido]
    valores = [Decimal(b['precio_unitario']) for b, _ in usadas]
    stats = estadisticas(valores, elegido)
    diferencia, calculo = None, None
    if stats:
        # Las diferencias usan la mediana exacta, no su presentación redondeada.
        mediana = _cuantil(sorted(valores), Decimal('.5'))
        precio = Decimal(a['precio_unitario']) if a['precio_unitario'] is not None else None
        if precio is not None:
            dif = precio - mediana
            diferencia = {'absoluta': dinero(dif), 'porcentual': dinero(dif / mediana * 100) if mediana else None,
                          'contra': 'mediana'}
            if not mediana:
                advertencias.append('La mediana es cero: no hay diferencia porcentual.')
        else:
            advertencias.append('El renglón analizado no tiene precio unitario: no hay diferencia.')
        operandos = [{'nombre': 'referencia_' + str(b['id']), 'valor': b['precio_unitario'],
                      'fuente': rg.fuente(cx, b, 'precio')} for b, _ in usadas]
        if precio is not None:
            operandos.insert(0, {'nombre': 'analizado', 'valor': a['precio_unitario'], 'fuente': rg.fuente(cx, a, 'precio')})
        ofertas = sorted(Decimal(b['precio_unitario']) for b, _ in usadas if b['etapa'] == 'oferta')
        segunda = None
        if len(ofertas) >= 2 and precio is not None:
            segunda = {'precio': dinero(ofertas[1]), 'absoluta': dinero(precio - ofertas[1]),
                       'porcentual': dinero((precio - ofertas[1]) / ofertas[1] * 100) if ofertas[1] else None}
        calculo = {
            'formula': 'x = referencias ordenadas; n = len(x); media = sum(x)/n; '
                       'Q(p) = interpolación lineal en (n-1)*p; mediana = Q(0.5); '
                       'desvío = sqrt(sum((x-media)^2)/(n-1)), n>=2; RIC = Q(0.75)-Q(0.25); '
                       'diferencia = analizado-mediana; porcentaje = 100*diferencia/mediana, mediana!=0; '
                       'segunda oferta = ofertas ordenadas[1]; diferencia segunda = analizado-segunda oferta; '
                       'porcentaje segunda = 100*diferencia segunda/segunda oferta, segunda oferta!=0; '
                       'presentación: dos decimales, mitad hacia arriba.',
            'operandos': operandos,
            'resultado': json.dumps({'estadisticas': stats, 'diferencia': diferencia,
                                     'segunda_mejor_oferta': segunda}, ensure_ascii=False)}
    involucrados = [a] + [b for b, _ in usadas]
    calidad = cp.calidad(elegido, [r['comparabilidad']['estado'] for _, r in usadas],
                         precios_firmes=all(r['estado'] in cf.FIRMES and rg.fuente(cx, r, 'precio') for r in involucrados),
                         derivados_sin_revisar=any(r['precio_derivado'] and r['estado'] not in cf.HUMANOS for r in involucrados))
    salida = rg.serializar(cx, a)
    if stats:
        salida['comparacion'] = {'nivel': elegido, 'diferencia_pct': diferencia['porcentual'] if diferencia else None,
                                 'n': stats['n'], 'calidad': calidad['nivel'],
                                 'comparabilidad': min((r['comparabilidad']['estado'] for _, r in usadas),
                                    key=lambda e: {'no_comparable':0,'dudoso':1,'probable':2,'fuerte':3}[e])}
    hallazgo = cx.execute("SELECT id,revision_estado,quien,cuando,nota FROM hallazgo WHERE tipo='diferencia_precio' AND ya_no_se_detecta=0 AND json_extract(datos,'$.renglon_id')=? ORDER BY id LIMIT 1", (rid,)).fetchone()
    revision = ({'id': hallazgo['id'], 'revision': {'estado': hallazgo['revision_estado'],
                 'quien': hallazgo['quien'], 'cuando': hallazgo['cuando'], 'nota': hallazgo['nota']}} if hallazgo else None)
    return {'renglon': salida, 'referencias': [r for _, r in refs], 'excluidas': excluidas,
            'estadisticas': stats, 'diferencia': diferencia, 'calculo': calculo, 'calidad': calidad,
            'advertencias': advertencias, 'hallazgo': revision}


class _CursorMemoria:
    def __init__(self, rows):
        self.rows = rows
    def fetchone(self):
        return self.rows[0] if self.rows else None
    def fetchall(self):
        return list(self.rows)
    def __iter__(self):
        return iter(self.rows)


class LecturaMemoria:
    """Memoización sólo durante una petición; nunca comparte datos entre legajos."""
    def __init__(self, cx):
        self.cx, self.cache = cx, {}
    def execute(self, sql, args=()):
        key = (sql, tuple(args))
        if key not in self.cache:
            self.cache[key] = self.cx.execute(sql, args).fetchall()
        return _CursorMemoria(self.cache[key])


def listar(cx, **filtros):
    from . import paginacion as pg
    filtros = dict(filtros)
    for viejo, nuevo in [('proveedor','proveedor_id'), ('contratacion','contratacion_id'),
                         ('fecha_desde','desde_fecha'), ('fecha_hasta','hasta_fecha')]:
        if viejo in filtros and nuevo not in filtros:
            filtros[nuevo] = filtros[viejo]
    where, args, aplicados = ['r.vigente=1', 'r.documento_id IS NOT NULL'], [], {}
    for k in ('etapa', 'proveedor_id'):
        if filtros.get(k):
            where.append('r.' + k + '=?'); args.append(filtros[k]); aplicados[k] = filtros[k]
    if filtros.get('contratacion_id'):
        # La misma resolución que serializar: vínculo único, luego id persistido.
        where.append("COALESCE((SELECT min(cd.contratacion_id) FROM contratacion_documento cd WHERE cd.documento_id=r.documento_id AND cd.estado!='rechazada' HAVING count(DISTINCT cd.contratacion_id)=1),r.contratacion_id)=?")
        args.append(int(filtros['contratacion_id'])); aplicados['contratacion_id'] = args[-1]
    if filtros.get('q'):
        where.append('r.desc_norm LIKE ?'); args.append('%'+rg.normalizar(filtros['q'])+'%'); aplicados['q'] = filtros['q']
    if filtros.get('item'):
        where.append("EXISTS(SELECT 1 FROM renglon_item ri WHERE ri.renglon_clave=r.clave AND ri.item_id=? AND ri.comparabilidad!='no_comparable')")
        args.append(filtros['item']); aplicados['item'] = filtros['item']
    for k, signo in [('desde_fecha','>='),('hasta_fecha','<=')]:
        if filtros.get(k):
            try:
                fecha = date.fromisoformat(filtros[k]).isoformat()
            except (ValueError, TypeError):
                raise ValueError(k+' debe ser una fecha ISO.') from None
            where.append('r.fecha_precio'+signo+'?'); args.append(fecha); aplicados[k] = fecha
    if 'pendiente' in filtros:
        valor = pg.booleano(filtros['pendiente'])
        where.append(('' if valor else 'NOT ') + "(r.estado IN ("+cf.SQL_PENDIENTES+"))")
        aplicados['pendiente'] = valor
    if 'con_hallazgo' in filtros:
        valor = pg.booleano(filtros['con_hallazgo'])
        where.append(('' if valor else 'NOT ')+"EXISTS(SELECT 1 FROM hallazgo h WHERE h.ya_no_se_detecta=0 AND (json_extract(h.datos,'$.renglon_id')=r.id OR EXISTS(SELECT 1 FROM hallazgo_fuente hf WHERE hf.hallazgo_id=h.id AND hf.renglon_clave=r.clave)))")
        aplicados['con_hallazgo'] = valor
    ordenes = {'id':'id','fecha':'fecha_precio','precio':'CAST(precio_unitario AS REAL)',
               'descripcion':'desc_norm','proveedor':'proveedor_literal','etapa':'etapa'}
    pg.parametros(filtros, ordenes, 'id')
    sql = 'SELECT r.* FROM renglon r WHERE '+' AND '.join(where)
    memoria = LecturaMemoria(cx)
    calculados = {}
    def dato(r):
        if r['id'] not in calculados:
            calculados[r['id']] = comparar(memoria, r['id'], resumen=True)['renglon']
        return calculados[r['id']]
    if 'con_comparacion' in filtros or filtros.get('dif_min_pct') not in (None, ''):
        minimo = None
        if filtros.get('dif_min_pct') not in (None, ''):
            try:
                minimo = Decimal(str(filtros['dif_min_pct']))
                if not minimo.is_finite():
                    raise ValueError()
            except Exception:
                raise ValueError('dif_min_pct debe ser un decimal finito.') from None
            aplicados['dif_min_pct'] = str(minimo)
        con = pg.booleano(filtros['con_comparacion']) if 'con_comparacion' in filtros else None
        if con is not None:
            aplicados['con_comparacion'] = con
        ids = []
        for r in cx.execute(sql, args):
            comp = dato(r)['comparacion']
            pct = (comp or {}).get('diferencia_pct')
            if con is not None and bool(comp) != con:
                continue
            if minimo is not None and (pct is None or Decimal(pct) < minimo):
                continue
            ids.append(r['id'])
        sql += ' AND r.id IN (SELECT value FROM json_each(?))'
        args.append(json.dumps(ids))
    return pg.consultar(cx, 'renglones', sql, args, filtros=filtros, ordenes=ordenes,
                        transformar=dato, aplicados=aplicados)
