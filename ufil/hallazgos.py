"""Diferencias verificables, con cálculo, fuentes y revisión que sobrevive al recálculo."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal

from . import clasificacion, comparabilidad as cp, confianza as cf, contrataciones as ct, precios, renglones as rg, versiones
from .db import ahora

CATALOGO = {k: (n, e) for k, n, e in cp.HALLAZGOS}


def serializar(row):
    r = dict(row)
    return {**{k: r[k] for k in ('id', 'tipo', 'titulo', 'descripcion', 'contratacion_id')},
            **{k: json.loads(r[k]) if r[k] else None for k in ('datos', 'calculo', 'fuentes', 'confianza')},
            'revision': dict(estado=r['revision_estado'], quien=r['quien'], cuando=r['cuando'], nota=r['nota']),
            'ya_no_se_detecta': bool(r['ya_no_se_detecta'])}


def obtener(cx, hid):
    r = cx.execute('SELECT * FROM hallazgo WHERE id=?', (hid,)).fetchone()
    if r is None:
        raise rg.NoEncontrado('El hallazgo no existe.')
    return serializar(r)


def listar(cx, **filtros):
    limite, desde = ct.paginar(filtros)
    donde, args = ["(ya_no_se_detecta=0 OR revision_estado!='pendiente' OR cuando IS NOT NULL OR quien IS NOT NULL OR nota IS NOT NULL)"], []
    for k, col, validos in [('tipo', 'tipo', CATALOGO), ('estado', 'revision_estado', {r[0] for r in cp.REVISION})]:
        if filtros.get(k):
            if filtros[k] not in validos:
                raise ValueError(k + ' desconocido.')
            donde.append(col + '=?')
            args.append(filtros[k])
    if filtros.get('contratacion'):
        try:
            cid = int(filtros['contratacion'])
        except (TypeError, ValueError):
            raise ValueError('contratacion debe ser un entero.') from None
        donde.append('contratacion_id=?')
        args.append(cid)
    sql = ' FROM hallazgo WHERE ' + ' AND '.join(donde)
    total = cx.execute('SELECT count(*)' + sql, args).fetchone()[0]
    rows = cx.execute('SELECT *' + sql + ' ORDER BY id LIMIT ? OFFSET ?', args + [limite, desde])
    return dict(hallazgos=[serializar(r) for r in rows], total=total, limite=limite, desde=desde)


def revisar(cx, hid, cuerpo):
    if not isinstance(cuerpo, dict) or cuerpo.get('estado') not in {r[0] for r in cp.REVISION}:
        raise ValueError('Indicá un estado de revisión válido.')
    for k in ('nota', 'quien'):
        if cuerpo.get(k) is not None and not isinstance(cuerpo[k], str):
            raise ValueError(k + ' debe ser texto.')
    obtener(cx, hid)
    with cx:
        cx.execute('UPDATE hallazgo SET revision_estado=?,nota=?,quien=?,cuando=? WHERE id=?',
                   (cuerpo['estado'], cuerpo.get('nota'), cuerpo.get('quien'), ahora(), hid))
    return obtener(cx, hid)


def _calculo(formula, operandos, resultado):
    return dict(formula=formula, operandos=operandos, resultado=resultado)


def _op(cx, r, campo):
    rol = {'precio_unitario': 'precio', 'subtotal': 'subtotal', 'cantidad': 'cantidad', 'proveedor_cuit': 'proveedor'}.get(campo, 'fila')
    return dict(nombre=campo, valor=r[campo], fuente=rg.fuente(cx, r, rol))


def recalcular(cx):
    docs = ct.documentos(cx)
    por_doc = {d['id']: d for d in docs}
    rows = [dict(r) for r in cx.execute('SELECT * FROM renglon WHERE vigente=1 AND documento_id IS NOT NULL')]
    rdoc = defaultdict(list)
    for r in rows:
        rdoc[r['documento_id']].append(r)
    propuestas = {}

    def agregar(tipo, cid, anclas, fuentes, datos=None, calculo=None, calidad=None):
        fuentes = [f for f in fuentes if f]
        if not fuentes:
            return
        clave = hashlib.sha256(json.dumps([tipo, sorted(anclas)], ensure_ascii=False).encode()).hexdigest()
        propuestas[clave] = dict(tipo=tipo, contratacion_id=cid, titulo=CATALOGO[tipo][0], descripcion=CATALOGO[tipo][1],
            datos=datos or {}, calculo=calculo, fuentes=fuentes,
            confianza=calidad or {'nivel': 'baja', 'motivos': ['Lecturas y agrupación propuestas; requiere cotejo con las fuentes.']})

    def dk(d):
        return d['clave'] or f"{d['sha256']}:{d['pagina_desde']}"

    def precio_calidad(rs):
        comparaciones = [cp.comparabilidad(precios._observacion(cx, rs[0]), precios._observacion(cx, r))['estado'] for r in rs[1:]]
        nivel = 'D' if 'probable' in comparaciones else 'E' if any(c in ('dudoso', 'no_comparable') for c in comparaciones) else 'A'
        return cp.calidad(nivel, comparaciones or ['fuerte'],
            precios_firmes=all(r['estado'] in cf.FIRMES for r in rs),
            derivados_sin_revisar=any(r['precio_derivado'] and r['estado'] not in cf.HUMANOS for r in rs))

    for r in rows:
        cid = r['contratacion_id']
        if r['etapa'] in ('adjudicacion', 'orden_compra', 'factura') and r['precio_unitario'] is not None:
            comp = precios.comparar(cx, r['id'])
            pct = (comp['diferencia'] or {}).get('porcentual')
            if pct is not None and Decimal(pct) > Decimal(cp.UMBRALES['diferencia_senalable_pct']):
                claves = [r['clave']] + [rg.fila(cx, ref['renglon']['id'])['clave'] for ref in comp['referencias']
                                        if ref['nivel'] == comp['estadisticas']['nivel']]
                agregar('diferencia_precio', cid, claves, [op['fuente'] for op in comp['calculo']['operandos']],
                        dict(renglon_id=r['id'], diferencia=comp['diferencia'], estadisticas=comp['estadisticas']), comp['calculo'], comp['calidad'])
        if all(r[k] is not None for k in ('cantidad', 'precio_unitario', 'subtotal')):
            esperado = Decimal(r['cantidad']) * Decimal(r['precio_unitario'])
            if precios.dinero(esperado) != precios.dinero(Decimal(r['subtotal'])):
                ops = [_op(cx, r, k) for k in ('cantidad', 'precio_unitario', 'subtotal')]
                agregar('subtotal_incorrecto', cid, [r['clave']], [o['fuente'] for o in ops],
                        dict(renglon_id=r['id'], impreso=r['subtotal']),
                        _calculo('cantidad * precio_unitario', ops, precios.dinero(esperado)), precio_calidad([r]))
        if r['etapa'] in clasificacion.TIPOS_CON_PRECIO and r['precio_unitario'] is None:
            agregar('precio_ausente', cid, [r['clave']], [rg.fuente(cx, r)],
                    dict(renglon_id=r['id'], motivo=r['precio_motivo']))

    for d in docs:
        rs = rdoc[d['id']]
        if d['total'] and rs and all(r['subtotal'] is not None for r in rs) and d['contexto'].get('iva') != 'discriminado':
            suma = sum(Decimal(r['subtotal']) for r in rs)
            if precios.dinero(suma) != precios.dinero(Decimal(d['total']['valor'])):
                ops = [_op(cx, r, 'subtotal') for r in rs] + [dict(nombre='total_impreso', valor=d['total']['valor'], fuente=d['total']['fuente'])]
                agregar('total_inconsistente', rs[0]['contratacion_id'], [dk(d)], [o['fuente'] for o in ops],
                        dict(total_impreso=d['total']['valor']), _calculo('sum(subtotales)', ops, precios.dinero(suma)), precio_calidad(rs))

    grupos = defaultdict(list)
    for l in cx.execute("SELECT * FROM contratacion_documento WHERE estado!='rechazada'"):
        if l['documento_id'] in por_doc:
            grupos[l['contratacion_id']].append(por_doc[l['documento_id']])
    for cid, ds in grupos.items():
        etapas = defaultdict(list)
        for d in ds:
            etapas[d['etapa']].append(d)
        for presente, requeridas in [('adjudicacion', ('factura',)), ('factura', ('adjudicacion', 'orden_compra')), ('pago', ('factura',))]:
            if etapas[presente] and not any(etapas[e] for e in requeridas):
                fuentes = [d['fuente'] for d in etapas[presente]]
                agregar('documento_faltante', cid, [dk(d) for d in etapas[presente]] + [','.join(requeridas)], fuentes,
                        dict(etapa_presente=presente, etapas_no_encontradas=requeridas))
        ofertas = etapas['oferta']
        if len(ofertas) == 1:
            agregar('oferente_unico', cid, [dk(ofertas[0])], [ofertas[0]['fuente']], dict(ofertas=1))
        for i, a in enumerate(ofertas):
            for b in ofertas[i+1:]:
                ra, rb = rdoc[a['id']], rdoc[b['id']]
                def firma(rs):
                    return sorted((r['desc_norm'], r['unidad_norm'] or '', r['moneda'] or '', r['precio_unitario']) for r in rs)
                if ra and len(ra) == len(rb) and all(r['precio_unitario'] is not None for r in ra+rb) and firma(ra) == firma(rb):
                    agregar('ofertas_identicas', cid, [dk(a), dk(b)], [rg.fuente(cx, r, 'precio') for r in ra+rb],
                            dict(renglones=len(ra)), _calculo('precios_a == precios_b por producto y unidad',
                            [_op(cx, r, 'precio_unitario') for r in ra+rb], 'iguales'), precio_calidad(ra+rb))

        def asociado(f, candidatos):
            refs = {k for k in f['claves'] if k[0] in ('orden_compra', 'remito')}
            exactos = [d for d in candidatos if refs & d['claves']]
            if len(exactos) == 1:
                return exactos[0]
            return candidatos[0] if not exactos and len(candidatos) == 1 else None

        for f in etapas['factura']:
            for tipo, candidatos in [('facturado_vs_adjudicado', etapas['orden_compra'] or etapas['adjudicacion']),
                                     ('facturado_vs_entregado', etapas['remito'])]:
                a = asociado(f, candidatos)
                if not a:
                    continue
                for r in rdoc[f['id']]:
                    iguales = [s for s in rdoc[a['id']] if s['desc_norm'] == r['desc_norm']
                               and (not s['unidad_norm'] or not r['unidad_norm'] or s['unidad_norm'] == r['unidad_norm'])]
                    s = iguales[0] if len(iguales) == 1 else None
                    if s is None:
                        # El producto ausente se informa sólo si la otra planilla fue leída.
                        if rdoc[a['id']] and not iguales:
                            agregar(tipo, cid, [r['clave'], dk(a), 'producto'], [rg.fuente(cx, r), a['fuente']], dict(atributo='producto', descripcion=r['desc_literal']))
                        continue
                    campos = ('cantidad',) if tipo == 'facturado_vs_entregado' else ('precio_unitario', 'cantidad', 'proveedor_cuit')
                    for campo in campos:
                        x, y = r[campo], s[campo]
                        if x is None or y is None or x == y:
                            continue
                        if campo != 'proveedor_cuit' and Decimal(x) == Decimal(y):
                            continue
                        ops = [_op(cx, r, campo), _op(cx, s, campo)]
                        resultado = precios.dinero(Decimal(x)-Decimal(y)) if campo != 'proveedor_cuit' else 'distintos'
                        agregar(tipo, cid, [r['clave'], s['clave'], campo], [o['fuente'] for o in ops],
                                dict(atributo=campo, facturado=x, referencia=y),
                                _calculo('facturado - referencia' if campo != 'proveedor_cuit' else 'facturado != referencia', ops, resultado),
                                precio_calidad([r, s]) if campo == 'precio_unitario' else None)
                if tipo == 'facturado_vs_adjudicado' and f['total'] and a['total'] and f['total']['valor'] != a['total']['valor']:
                    ops = [dict(nombre=n, valor=d['total']['valor'], fuente=d['total']['fuente']) for n, d in [('facturado', f), ('ordenado', a)]]
                    agregar(tipo, cid, [dk(f), dk(a), 'total'], [o['fuente'] for o in ops], dict(atributo='total'),
                            _calculo('facturado - ordenado', ops, precios.dinero(Decimal(ops[0]['valor']) - Decimal(ops[1]['valor']))))
                if f['fecha'] and a['fecha'] and f['fecha']['valor'] < a['fecha']['valor'] and tipo == 'facturado_vs_adjudicado':
                    agregar('secuencia_temporal', cid, [dk(f), dk(a)], [f['fecha']['fuente'], a['fecha']['fuente']],
                            dict(anterior=f['fecha'], posterior=a['fecha']))
        for p in etapas['pago']:
            f = asociado(p, etapas['factura'])
            if f and p['fecha'] and f['fecha'] and p['fecha']['valor'] < f['fecha']['valor']:
                agregar('secuencia_temporal', cid, [dk(p), dk(f)], [p['fecha']['fuente'], f['fecha']['fuente']], dict(pago=p['fecha'], factura=f['fecha']))
        for i, a in enumerate(etapas['factura']):
            for b in etapas['factura'][i+1:]:
                comunes = {k for k in a['claves'] & b['claves'] if k[0] in ('factura', 'remito')}
                mismo_prov = a['contexto'].get('proveedor_cuit') and a['contexto'].get('proveedor_cuit') == b['contexto'].get('proveedor_cuit')
                if comunes and mismo_prov:
                    agregar('duplicado_potencial', cid, [dk(a), dk(b)], [a['fuente'], b['fuente']], dict(coincidencias=sorted(comunes)))

    # Compras distintas: una observación por producto y compra, factura antes que orden.
    compras = {}
    for r in sorted(rows, key=lambda r: {'factura': 0, 'orden_compra': 1, 'adjudicacion': 2}.get(r['etapa'], 3)):
        if r['contratacion_id'] and r['etapa'] in ('factura', 'orden_compra', 'adjudicacion') and r['precio_unitario']:
            compras.setdefault((r['contratacion_id'], r['desc_norm'], r['unidad_norm']), r)
    elegidas = list(compras.values())
    for i, a in enumerate(elegidas):
        for b in elegidas[i+1:]:
            if a['contratacion_id'] == b['contratacion_id']:
                continue
            oa, ob = precios._observacion(cx, a), precios._observacion(cx, b)
            comp = cp.comparabilidad(oa, ob)
            if comp['estado'] != 'fuerte':
                continue
            x, y = Decimal(a['precio_unitario']), Decimal(b['precio_unitario'])
            menor = min(x, y)
            if menor <= 0 or (max(x, y)-menor)/menor*100 <= Decimal(cp.UMBRALES['diferencia_senalable_pct']):
                continue
            ops = [_op(cx, a, 'precio_unitario'), _op(cx, b, 'precio_unitario')]
            nivel = cp.nivel(oa, ob, comp['estado'])
            calidad = cp.calidad(nivel, [comp['estado']], precios_firmes=all(r['estado'] in cf.FIRMES for r in (a,b)),
                                 derivados_sin_revisar=any(r['precio_derivado'] and r['estado'] not in cf.HUMANOS for r in (a,b)))
            agregar('variacion_compras', a['contratacion_id'], [a['clave'], b['clave']], [o['fuente'] for o in ops],
                    dict(contrataciones=[a['contratacion_id'], b['contratacion_id']]),
                    _calculo('100 * (max(precios)-min(precios))/min(precios)', ops, precios.dinero((max(x,y)-menor)/menor*100)), calidad)

    # La proximidad de una anotación de agenda no establece una relación causal.
    for agenda in (d for d in docs if d.get('es_agenda') and d['fecha']):
        for cid, ds in grupos.items():
            for acto in ds:
                if acto['id'] == agenda['id'] or acto['etapa'] not in ('adjudicacion', 'orden_compra', 'factura', 'pago') or not acto['fecha']:
                    continue
                dias = abs((date.fromisoformat(agenda['fecha']['valor'])-date.fromisoformat(acto['fecha']['valor'])).days)
                if dias <= 1:
                    ops = [dict(nombre=n, valor=d['fecha']['valor'], fuente=d['fecha']['fuente']) for n,d in [('agenda',agenda),('acto',acto)]]
                    agregar('coincidencia_temporal', cid, [dk(agenda),dk(acto)], [o['fuente'] for o in ops],
                            dict(dias=dias, ventana_dias=1), _calculo('abs(fecha_agenda-fecha_acto), en días', ops, str(dias)))

    with cx:
        cx.execute('UPDATE hallazgo SET ya_no_se_detecta=1')
        for clave, h in propuestas.items():
            columnas = ['clave'] + list(h) + ['version', 'actualizado_en', 'ya_no_se_detecta']
            valores = [clave] + [json.dumps(v, ensure_ascii=False) if k in ('datos','calculo','fuentes','confianza') and v is not None else v for k,v in h.items()] + [versiones.etapa('hallazgos').version, ahora(), 0]
            cx.execute(f"INSERT INTO hallazgo({','.join(columnas)}) VALUES ({','.join('?' for _ in columnas)}) ON CONFLICT(clave) DO UPDATE SET " + ','.join(k+'=excluded.'+k for k in columnas if k != 'clave'), valores)
            hid = cx.execute('SELECT id FROM hallazgo WHERE clave=?', (clave,)).fetchone()[0]
            cx.execute('DELETE FROM hallazgo_fuente WHERE hallazgo_id=?', (hid,))
            for f in h['fuentes']:
                d = por_doc.get(f['documento_id'])
                fk = (dk(d) if d else f['sha256']) + ':' + str(f['pagina_nro']) + ':' + json.dumps(f['region'], sort_keys=True)
                cx.execute('INSERT OR IGNORE INTO hallazgo_fuente(hallazgo_id,sha256,documento_id,clave) VALUES (?,?,?,?)', (hid, f['sha256'], f['documento_id'], fk))
    return {'hallazgos': len(propuestas)}
