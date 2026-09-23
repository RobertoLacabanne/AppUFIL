"""Vistas de trabajo: importes nominales, cobertura explícita y fuentes navegables."""
from __future__ import annotations

import json
from decimal import Decimal
from urllib.parse import urlencode
from . import paginacion as pg, renglones as rg, contrataciones as ct, confianza as cf


def _montos(cx, proveedor=None):
    """Subtotales de renglones, no totales documentales; no mezcla monedas ni etapas."""
    sql = '''SELECT r.*,EXISTS(SELECT 1 FROM pagina p WHERE p.sha256=r.sha256
             AND p.nro=json_extract(r.anclajes,'$.subtotal.pagina_nro')) fuente_subtotal
             FROM renglon r WHERE vigente=1 AND documento_id IS NOT NULL'''
    args = []
    if proveedor is not None:
        sql += ' AND proveedor_id=?'; args.append(proveedor)
    grupos = {}
    for row in cx.execute(sql, args):
        r = dict(row)
        categoria = 'firme' if r['estado'] in cf.FIRMES and r['fuente_subtotal'] else 'provisional'
        k = (r['etapa'], r['moneda'], categoria)
        g = grupos.setdefault(k, dict(etapa=k[0], moneda=k[1], estado=k[2], valor=None,
                                      renglones=0, con_valor=0, sin_valor=0,
                                      fecha_desde=None,fecha_hasta=None,sin_fecha=0))
        g['renglones'] += 1
        if r['fecha_precio']:
            g['fecha_desde'] = min(g['fecha_desde'] or r['fecha_precio'],r['fecha_precio'])
            g['fecha_hasta'] = max(g['fecha_hasta'] or r['fecha_precio'],r['fecha_precio'])
        else:
            g['sin_fecha'] += 1
        if r['subtotal'] is None or not r['moneda']:
            g['sin_valor'] += 1
        else:
            g['con_valor'] += 1
            g['valor'] = (g['valor'] or Decimal(0)) + Decimal(r['subtotal'])
    for g in grupos.values():
        g['valor'] = rg.canonico(g['valor'])
        g['ausencia'] = None if g['valor'] is not None else 'no_consta'
        g['completo'] = g['sin_valor'] == 0
        g['alcance'] = 'suma de subtotales de renglones; no total documental'
        parametros = dict(etapa=g['etapa'] or 'null',moneda=g['moneda'] or 'null',estado=g['estado'])
        if proveedor is not None:
            parametros['proveedor_id'] = proveedor
        g['fuentes_url'] = '/api/resumen/operandos?' + urlencode(parametros)
    return list(grupos.values())


def operandos(cx, f):
    where, args, aplicados = ['vigente=1','documento_id IS NOT NULL'], [], {}
    for k in ('proveedor_id','etapa','moneda'):
        if k in f:
            where.append("coalesce("+k+",'')=?")
            args.append('' if f[k]=='null' and k in ('etapa','moneda') else f[k]); aplicados[k] = f[k]
    if f.get('estado'):
        if f['estado'] not in ('firme','provisional'):
            raise ValueError('estado debe ser firme o provisional.')
        where.append(('' if f['estado']=='firme' else 'NOT ')+
                     "(estado IN ("+cf.SQL_FIRMES+") AND EXISTS(SELECT 1 FROM pagina p WHERE p.sha256=renglon.sha256 AND p.nro=json_extract(renglon.anclajes,'$.subtotal.pagina_nro')))")
        aplicados['estado'] = f['estado']
    return pg.consultar(cx, 'operandos', 'SELECT * FROM renglon WHERE '+' AND '.join(where), args,
                        filtros=f, transformar=lambda r:dict(renglon_id=r['id'], etapa=r['etapa'],
                        fecha=r['fecha_precio'], descripcion={'literal':r['desc_literal'],'normalizada':r['desc_norm']},
                        monto=rg.monto(cx,r,True)), aplicados=aplicados)


def resumen(cx):
    from . import hallazgos
    def n(sql):
        return cx.execute(sql).fetchone()[0]
    pendientes = n("SELECT count(*) FROM hallazgo WHERE ya_no_se_detecta=0 AND revision_estado='pendiente'")
    sin_clasificar = n("SELECT count(*) FROM documento WHERE estado='sin_perfil'")
    campos = n('SELECT count(*) FROM campo WHERE estado IN ('+cf.SQL_PENDIENTES+')')
    return dict(
        prioridades=[dict(clave='hallazgos',cantidad=pendientes,accion='Revisar diferencias y fuentes',url='/api/hallazgos?estado_revision=pendiente&orden=confianza&sentido=desc'),
                     dict(clave='campos',cantidad=campos,accion='Cotejar lecturas pendientes',url='/api/cola'),
                     dict(clave='piezas',cantidad=sin_clasificar,accion='Identificar piezas cargadas',url='/api/piezas/sin-reconocer')],
        contrataciones=n("SELECT count(*) FROM contratacion c WHERE EXISTS(SELECT 1 FROM contratacion_documento cd WHERE cd.contratacion_id=c.id AND cd.estado!='rechazada')"),
        hallazgos_por_confianza=[dict(r) for r in cx.execute("SELECT json_extract(confianza,'$.nivel') nivel,count(*) cantidad FROM hallazgo WHERE ya_no_se_detecta=0 GROUP BY nivel")],
        dinero=_montos(cx),
        destacados=hallazgos.listar(cx,estado_revision='pendiente',orden='confianza',sentido='desc',limite=5),
        incompleto=dict(piezas_sin_reconocer=sin_clasificar,campos_pendientes=campos,
                        precios_sin_fecha=n('SELECT count(*) FROM renglon WHERE vigente=1 AND fecha_precio IS NULL'),
                        contrataciones_sin_etapas=[dict(r) for r in cx.execute('''WITH etapas(clave,documental) AS (
                            VALUES ('pliego','pliego'),('ofertas','oferta'),('adjudicacion','adjudicacion'),
                            ('orden_compra','orden_compra'),('factura','factura'),('remito','remito'),('pago','pago'))
                            SELECT e.clave,count(*) cantidad FROM etapas e CROSS JOIN contratacion c
                            WHERE EXISTS(SELECT 1 FROM contratacion_documento d WHERE d.contratacion_id=c.id AND d.estado!='rechazada')
                            AND NOT EXISTS(SELECT 1 FROM contratacion_documento d WHERE d.contratacion_id=c.id AND d.estado!='rechazada' AND d.etapa=e.documental)
                            GROUP BY e.clave''')]),
        criterio='Ausente significa que no consta en lo cargado. Los importes mantienen su fecha y moneda.')


def proveedor(cx, eid, f):
    e = cx.execute('SELECT * FROM entidad WHERE id=?',(eid,)).fetchone()
    if e is None:
        raise rg.NoEncontrado('El proveedor no existe.')
    from . import hallazgos, precios as pr
    memoria = pr.LecturaMemoria(cx)
    # Documento vinculado por renglón o mención identificada, nunca por parecido del nombre.
    docs = '''SELECT documento_id FROM renglon WHERE vigente=1 AND proveedor_id=? AND documento_id IS NOT NULL
              UNION SELECT documento_id FROM mencion WHERE entidad_id=? AND documento_id IS NOT NULL'''
    args = [eid,eid]
    contrataciones = pg.consultar(cx,'contrataciones', '''SELECT c.* FROM contratacion c WHERE EXISTS(
        SELECT 1 FROM contratacion_documento cd WHERE cd.contratacion_id=c.id AND cd.estado!='rechazada'
        AND cd.documento_id IN ('''+docs+'))', args, filtros=f)
    def documentos(etapas):
        r = pg.consultar(cx, 'documentos', 'SELECT d.* FROM documento d WHERE d.id IN ('+docs+
            ') AND d.tipo IN ('+','.join('?' for _ in etapas)+')',args+list(etapas), filtros=f)
        memoria.preparar_fuentes({(d['sha256'],d['pagina_desde']) for d in r['documentos']})
        r['documentos'] = [dict(id=d['id'],tipo=d['tipo'],fuente=ct.fuente_documento(memoria,d)) for d in r['documentos']]
        return r
    precios = pg.consultar(cx,'renglones','SELECT * FROM renglon WHERE vigente=1 AND documento_id IS NOT NULL AND proveedor_id=?',[eid],
        filtros=f)
    memoria.preparar_renglones(precios['renglones'])
    precios['renglones'] = [rg.serializar(memoria,r) for r in precios['renglones']]
    h = pg.consultar(cx,'hallazgos', '''SELECT * FROM hallazgo h WHERE h.ya_no_se_detecta=0 AND EXISTS(
        SELECT 1 FROM hallazgo_fuente hf WHERE hf.hallazgo_id=h.id AND hf.documento_id IN ('''+docs+'))',
        args,filtros=f,transformar=hallazgos.serializar)
    rel = pg.consultar(cx,'relaciones','SELECT * FROM relacion WHERE desde_doc IN ('+docs+') OR hasta_doc IN ('+docs+')',
        args+args,filtros=f)
    for c in contrataciones['contrataciones']:
        c['fuentes_url'] = '/api/contratacion/'+str(c['id'])
    for r in rel['relaciones']:
        r['fuentes_url'] = ['/api/documento?id='+str(d) for d in (r['desde_doc'],r['hasta_doc']) if d is not None]
    montos = _montos(cx,eid)
    return dict(proveedor=dict(e),contrataciones=contrataciones,
                monto_adjudicado=[m for m in montos if m['etapa']=='adjudicacion'],
                monto_ordenado=[m for m in montos if m['etapa']=='orden_compra'],
                monto_facturado=[m for m in montos if m['etapa']=='factura'],
                cantidad_items=cx.execute('''SELECT count(DISTINCT ri.item_id) FROM renglon r JOIN renglon_item ri
                   ON ri.renglon_clave=r.clave WHERE r.vigente=1 AND r.proveedor_id=?''',(eid,)).fetchone()[0],
                historial_precios=precios,facturas=documentos(('factura',)),remitos=documentos(('remito',)),
                hallazgos=h,relaciones=rel,
                cobertura='Sólo datos con proveedor identificado; no se atribuyen importes por proximidad o nombre parecido.')


def cruce(cx, f):
    from . import precios, comparabilidad as cp
    # Una factura necesita una referencia única: preferir orden frente a adjudicación
    # evita contar dos etapas de la misma compra como dos compromisos.
    candidato = """SELECT a.id FROM vigentes a WHERE
        a.compra_id=f.compra_id AND a.desc_norm=f.desc_norm
        AND a.etapa=CASE WHEN EXISTS(SELECT 1 FROM vigentes z WHERE
          z.compra_id=f.compra_id AND z.desc_norm=f.desc_norm AND z.etapa='orden_compra')
          THEN 'orden_compra' ELSE 'adjudicacion' END"""
    sql = '''WITH vigentes AS (SELECT r.*,COALESCE(
        (SELECT min(cd.contratacion_id) FROM contratacion_documento cd WHERE cd.documento_id=r.documento_id
         AND cd.estado!='rechazada' HAVING count(DISTINCT cd.contratacion_id)=1),r.contratacion_id) compra_id
        FROM renglon r WHERE r.vigente=1 AND r.documento_id IS NOT NULL)
        SELECT f.id,f.proveedor_id,f.compra_id contratacion_id,
        CASE WHEN (SELECT count(*) FROM ('''+candidato+'''))=1 THEN ('''+candidato+''') END referencia_id
        FROM vigentes f WHERE f.etapa='factura' '''
    args, applied = [], {}
    for k in ('proveedor_id','contratacion_id'):
        if f.get(k):
            sql += ' AND f.'+('compra_id' if k=='contratacion_id' else k)+'=?'; args.append(int(f[k])); applied[k] = args[-1]
    if f.get('q'):
        sql += ' AND f.desc_norm LIKE ?'; args.append('%'+rg.normalizar(f['q'])+'%'); applied['q'] = f['q']
    memoria, calculos = precios.LecturaMemoria(cx), {}
    memoria.preparar_comparaciones()
    def calcular(rid, aid):
        key = (rid,aid)
        if key in calculos:
            return calculos[key]
        r = rg.fila(memoria,rid)
        a = rg.fila(memoria,aid) if aid is not None else None
        decision, quien = precios._decision(memoria,r,a) if a else (None,None)
        comp = cp.comparabilidad(precios._observacion(memoria,r),precios._observacion(memoria,a),
                                decision_humana=decision,quien=quien) if a else {'estado':'no_comparable','motivos':[]}
        x,y = r['precio_unitario'], a['precio_unitario'] if a else None
        fuentes = [rg.fuente(memoria,z,'precio') for z in (r,a) if z]
        valido_proveedor = a and not (
            (r['proveedor_id'] and a['proveedor_id'] and r['proveedor_id']!=a['proveedor_id']) or
            (r['proveedor_cuit'] and a['proveedor_cuit'] and r['proveedor_cuit']!=a['proveedor_cuit']))
        valida = (a and x is not None and y is not None and r['moneda'] and r['moneda']==a['moneda']
                  and r['unidad_norm'] and r['unidad_norm']==a['unidad_norm'] and valido_proveedor
                  and r['fecha_precio'] and a['fecha_precio'] and all(fuentes)
                  and comp['estado'] in ('fuerte','probable'))
        dif = Decimal(x)-Decimal(y) if valida else None
        compra = rg.contratacion_de(memoria,r)
        salida = dict(id=rid,contratacion_id=compra['id'] if compra else None,proveedor=rg.serializar(memoria,r)['proveedor'],
            descripcion={'literal':r['desc_literal'],'normalizada':r['desc_norm']},
            contratado=rg.monto(memoria,a) if a else None,facturado=rg.monto(memoria,r),
            fecha_facturado=r['fecha_precio'],fecha_contratado=a['fecha_precio'] if a else None,
            diferencia_absoluta=precios.dinero(dif),
            diferencia_porcentual=precios.dinero(dif/Decimal(y)*100) if dif is not None and Decimal(y)!=0 else None,
            comparabilidad=comp,estado='requiere_revision' if dif != 0 else 'sin_diferencia',
            ausencia=None if dif is not None else ('no_cargado' if not a else 'pendiente'),
            motivo=None if dif is not None else ('No consta una referencia única de la misma contratación.' if not a else
                'Revisar comparabilidad, proveedor, unidad, moneda, fechas y fuentes antes de calcular.'),
            fuentes=fuentes,
            magnitud=rg.canonico(abs(dif)) if dif is not None else None,
            unidad_comparada='precio_unitario_nominal')
        calculos[key] = salida
        return salida
    cx.create_function('magnitud_cruce',2,lambda rid,aid:calcular(rid,aid)['magnitud'])
    cx.create_collation('decimal_exacto',lambda a,b:(Decimal(a)>Decimal(b))-(Decimal(a)<Decimal(b)))
    sql = 'SELECT *,magnitud_cruce(id,referencia_id) magnitud FROM ('+sql+')'
    # Primero diferencias conocidas, después igualdad y finalmente ausencias, aun en asc.
    ordenes = {'diferencia':"(CAST(magnitud AS NUMERIC)=0) ASC, magnitud COLLATE decimal_exacto"}
    resultado = pg.consultar(cx,'filas','SELECT * FROM ('+sql+') WHERE magnitud IS NOT NULL',args,
        filtros=f,ordenes=ordenes,defecto='diferencia',sentido='desc',
        transformar=lambda r:calcular(r['id'],r['referencia_id']),aplicados=applied)
    resultado['faltantes'] = pg.consultar(cx,'filas','SELECT * FROM ('+sql+') WHERE magnitud IS NULL',args,
        filtros={'desde':f.get('faltantes_desde',0),'limite':f.get('limite',50)},
        transformar=lambda r:calcular(r['id'],r['referencia_id']),aplicados=applied)
    resultado['faltantes_total'] = resultado['faltantes']['total']
    resultado['total_general'] = resultado['total']+resultado['faltantes_total']
    resultado['alcance'] = 'Renglones facturados contra referencia única de la misma contratación; precios unitarios nominales.'
    return resultado
