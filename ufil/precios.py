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


def comparar(cx, rid, niveles=None):
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
            excluidas.append({'renglon': rg.serializar(cx, b), 'motivo': motivo})
            continue
        vistas.add(huella)
        refs.append((b, {'renglon': rg.serializar(cx, b), 'nivel': nivel,
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
                                 'n': stats['n'], 'calidad': calidad['nivel']}
    hallazgo = cx.execute("SELECT id,revision_estado,quien,cuando,nota FROM hallazgo WHERE tipo='diferencia_precio' AND ya_no_se_detecta=0 AND json_extract(datos,'$.renglon_id')=? ORDER BY id LIMIT 1", (rid,)).fetchone()
    revision = ({'id': hallazgo['id'], 'revision': {'estado': hallazgo['revision_estado'],
                 'quien': hallazgo['quien'], 'cuando': hallazgo['cuando'], 'nota': hallazgo['nota']}} if hallazgo else None)
    return {'renglon': salida, 'referencias': [r for _, r in refs], 'excluidas': excluidas,
            'estadisticas': stats, 'diferencia': diferencia, 'calculo': calculo, 'calidad': calidad,
            'advertencias': advertencias, 'hallazgo': revision}


def listar(cx, **filtros):
    def entero(clave, defecto, minimo, maximo=None):
        valor = filtros.get(clave, defecto)
        if isinstance(valor, bool):
            raise ValueError(clave + ' debe ser un entero.')
        try:
            n = int(valor)
        except (ValueError, TypeError):
            raise ValueError(clave + ' debe ser un entero.') from None
        if n < minimo:
            raise ValueError(clave + ' fuera de rango.')
        return min(n, maximo) if maximo else n
    limite, desde = entero('limite', 100, 1, 500), entero('desde', 0, 0)
    donde, args = ['r.vigente=1', 'r.documento_id IS NOT NULL'], []
    for k, col in (('etapa', 'etapa'), ('proveedor', 'proveedor_id')):
        if filtros.get(k):
            donde.append('r.' + col + '=?')
            args.append(filtros[k])
    if filtros.get('q'):
        donde.append('r.desc_norm LIKE ?')
        args.append('%' + rg.normalizar(filtros['q']) + '%')
    if filtros.get('item'):
        donde.append('EXISTS(SELECT 1 FROM renglon_item ri WHERE ri.renglon_clave=r.clave AND ri.item_id=? AND ri.comparabilidad!=\'no_comparable\')')
        args.append(filtros['item'])
    for k, signo in (('fecha_desde', '>='), ('fecha_hasta', '<=')):
        if filtros.get(k):
            try:
                fecha = date.fromisoformat(filtros[k]).isoformat()
            except (TypeError, ValueError):
                raise ValueError(k + ' debe ser una fecha ISO (AAAA-MM-DD).') from None
            donde.append('r.fecha_precio' + signo + '?')
            args.append(fecha)
    minimo = None
    if filtros.get('dif_min_pct') not in (None, ''):
        try:
            minimo = Decimal(str(filtros['dif_min_pct']))
            if not minimo.is_finite():
                raise ValueError()
        except Exception:
            raise ValueError('dif_min_pct debe ser un decimal finito.') from None
    rows = [dict(r) for r in cx.execute('SELECT r.* FROM renglon r WHERE ' + ' AND '.join(donde) + ' ORDER BY r.id', args)]
    if filtros.get('contratacion'):
        cid = entero('contratacion', None, 1)
        rows = [r for r in rows if (rg.contratacion_de(cx, r) or {}).get('id') == cid]
    salida = []
    for r in rows:
        if minimo is not None:
            dato = comparar(cx, r['id'])['renglon']
            pct = (dato['comparacion'] or {}).get('diferencia_pct')
            if pct is None or Decimal(pct) < minimo:
                continue
            salida.append(dato)
        else:
            salida.append(r)
    total = len(salida)
    pagina = salida[desde:desde + limite]
    if minimo is None:
        pagina = [comparar(cx, r['id'])['renglon'] for r in pagina]
    return {'renglones': pagina, 'total': total, 'desde': desde, 'limite': limite}
