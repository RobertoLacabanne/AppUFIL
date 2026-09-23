"""Vistas de trabajo: importes nominales, cobertura explícita y fuentes navegables."""
from __future__ import annotations

import json
from decimal import Decimal
from . import paginacion as pg, renglones as rg, contrataciones as ct, confianza as cf


def _montos(cx, proveedor=None):
    """Subtotales de renglones, no totales documentales; no mezcla monedas ni etapas."""
    sql = 'SELECT * FROM renglon WHERE vigente=1 AND documento_id IS NOT NULL'
    args = []
    if proveedor is not None:
        sql += ' AND proveedor_id=?'; args.append(proveedor)
    grupos = {}
    for row in cx.execute(sql, args):
        r = dict(row)
        categoria = 'firme' if r['estado'] in cf.FIRMES and rg.fuente(cx,r,'subtotal') else 'provisional'
        k = (r['etapa'], r['moneda'], categoria)
        g = grupos.setdefault(k, dict(etapa=k[0], moneda=k[1], estado=k[2], valor=None,
                                      renglones=0, con_valor=0, sin_valor=0))
        g['renglones'] += 1
        if r['subtotal'] is None or not r['moneda']:
            g['sin_valor'] += 1
        else:
            g['con_valor'] += 1
            g['valor'] = (g['valor'] or Decimal(0)) + Decimal(r['subtotal'])
    for g in grupos.values():
        g['valor'] = rg.canonico(g['valor'])
        g['completo'] = g['sin_valor'] == 0
        g['alcance'] = 'suma de subtotales de renglones; no total documental'
        g['fuentes_url'] = '/api/resumen/operandos' + ('?proveedor_id='+str(proveedor) if proveedor is not None else '')
    return list(grupos.values())


def operandos(cx, f):
    where, args, aplicados = ['vigente=1','documento_id IS NOT NULL'], [], {}
    for k in ('proveedor_id','etapa','moneda'):
        if f.get(k):
            where.append(k+'=?'); args.append(f[k]); aplicados[k] = f[k]
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
                        precios_sin_fecha=n('SELECT count(*) FROM renglon WHERE vigente=1 AND fecha_precio IS NULL')),
        criterio='Ausente significa que no consta en lo cargado. Los importes mantienen su fecha y moneda.')


def proveedor(cx, eid, f):
    e = cx.execute('SELECT * FROM entidad WHERE id=?',(eid,)).fetchone()
    if e is None:
        raise rg.NoEncontrado('El proveedor no existe.')
    from . import hallazgos
    # Documento vinculado por renglón o mención identificada, nunca por parecido del nombre.
    docs = '''SELECT documento_id FROM renglon WHERE vigente=1 AND proveedor_id=? AND documento_id IS NOT NULL
              UNION SELECT documento_id FROM mencion WHERE entidad_id=? AND documento_id IS NOT NULL'''
    args = [eid,eid]
    contrataciones = pg.consultar(cx,'contrataciones', '''SELECT c.* FROM contratacion c WHERE EXISTS(
        SELECT 1 FROM contratacion_documento cd WHERE cd.contratacion_id=c.id AND cd.estado!='rechazada'
        AND cd.documento_id IN ('''+docs+'))', args, filtros=f)
    def documentos(etapas):
        return pg.consultar(cx, 'documentos', 'SELECT d.* FROM documento d WHERE d.id IN ('+docs+
            ') AND d.tipo IN ('+','.join('?' for _ in etapas)+')',args+list(etapas), filtros=f,
            transformar=lambda d:dict(id=d['id'],tipo=d['tipo'],fuente=ct.fuente_documento(cx,d)))
    precios = pg.consultar(cx,'renglones','SELECT * FROM renglon WHERE vigente=1 AND proveedor_id=?',[eid],
        filtros=f, transformar=lambda r:rg.serializar(cx,r))
    h = pg.consultar(cx,'hallazgos', '''SELECT * FROM hallazgo h WHERE h.ya_no_se_detecta=0 AND EXISTS(
        SELECT 1 FROM hallazgo_fuente hf WHERE hf.hallazgo_id=h.id AND hf.documento_id IN ('''+docs+'))',
        args,filtros=f,transformar=hallazgos.serializar)
    rel = pg.consultar(cx,'relaciones','SELECT * FROM relacion WHERE desde_doc IN ('+docs+') OR hasta_doc IN ('+docs+')',
        args+args,filtros=f)
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
    candidato = """SELECT a.id FROM renglon a WHERE a.vigente=1 AND a.documento_id IS NOT NULL
        AND a.contratacion_id=f.contratacion_id AND a.desc_norm=f.desc_norm
        AND a.etapa=CASE WHEN EXISTS(SELECT 1 FROM renglon z WHERE z.vigente=1
          AND z.contratacion_id=f.contratacion_id AND z.desc_norm=f.desc_norm AND z.etapa='orden_compra')
          THEN 'orden_compra' ELSE 'adjudicacion' END"""
    sql = '''SELECT f.id,f.proveedor_id,f.contratacion_id,
        CASE WHEN (SELECT count(*) FROM ('''+candidato+'''))=1 THEN ('''+candidato+''') END referencia_id
        FROM renglon f WHERE f.vigente=1 AND f.documento_id IS NOT NULL AND f.etapa='factura' '''
    args, applied = [], {}
    for k in ('proveedor_id','contratacion_id'):
        if f.get(k):
            sql += ' AND f.'+k+'=?'; args.append(int(f[k])); applied[k] = args[-1]
    memoria, calculos = precios.LecturaMemoria(cx), {}
    def calcular(rid, aid):
        key = (rid,aid)
        if key in calculos:
            return calculos[key]
        r = rg.fila(memoria,rid)
        a = rg.fila(memoria,aid) if aid is not None else None
        comp = cp.comparabilidad(precios._observacion(memoria,r),precios._observacion(memoria,a)) if a else {'estado':'no_comparable','motivos':[]}
        x,y = r['precio_unitario'], a['precio_unitario'] if a else None
        valida = a and x is not None and y is not None and r['moneda'] and r['moneda']==a['moneda'] and comp['estado'] in ('fuerte','probable')
        dif = Decimal(x)-Decimal(y) if valida else None
        salida = dict(id=rid,contratacion_id=r['contratacion_id'],proveedor=rg.serializar(memoria,r)['proveedor'],
            descripcion={'literal':r['desc_literal'],'normalizada':r['desc_norm']},
            contratado=rg.monto(memoria,a) if a else None,facturado=rg.monto(memoria,r),
            fecha_facturado=r['fecha_precio'],fecha_contratado=a['fecha_precio'] if a else None,
            diferencia_absoluta=precios.dinero(dif),
            diferencia_porcentual=precios.dinero(dif/Decimal(y)*100) if dif is not None and Decimal(y)!=0 else None,
            comparabilidad=comp,estado='requiere_revision',
            ausencia=None if dif is not None else ('no_cargado' if not a else 'pendiente'),
            fuentes=[rg.fuente(memoria,z,'precio') for z in (r,a) if z],
            magnitud=precios.dinero(abs(dif)) if dif is not None else None,
            unidad_comparada='precio_unitario_nominal')
        calculos[key] = salida
        return salida
    cx.create_function('magnitud_cruce',2,lambda rid,aid:calcular(rid,aid)['magnitud'])
    cx.create_collation('decimal_exacto',lambda a,b:(Decimal(a)>Decimal(b))-(Decimal(a)<Decimal(b)))
    sql = 'SELECT *,magnitud_cruce(id,referencia_id) magnitud FROM ('+sql+')'
    # Primero diferencias conocidas, después igualdad y finalmente ausencias, aun en asc.
    direccion = f.get('sentido','desc')
    ordenes = {'diferencia':"(magnitud IS NULL) ASC, magnitud COLLATE decimal_exacto"}
    resultado = pg.consultar(cx,'filas',sql,args,filtros=f,ordenes=ordenes,defecto='diferencia',sentido='desc',
        transformar=lambda r:calcular(r['id'],r['referencia_id']),aplicados=applied)
    resultado['faltantes_total'] = cx.execute('SELECT count(*) FROM ('+sql+') WHERE magnitud IS NULL',args).fetchone()[0]
    resultado['alcance'] = 'Renglones facturados contra referencia única de la misma contratación; precios unitarios nominales.'
    return resultado
