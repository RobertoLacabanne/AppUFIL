"""Listas HTTP con paginación SQL; los servicios de exportación conservan su alcance."""
from __future__ import annotations

import json
import re
from . import paginacion as pg


def entidades(cx, f):
    from . import entidades as en
    clase = f.get('clase')
    if clase and clase not in en.CLASES:
        raise ValueError('clase desconocida.')
    cx.create_function('dni_entidad', 1, en.documento_del_cuil, deterministic=True)
    cx.create_function('digitos', 1, lambda v: re.sub(r'\D', '', v or ''), deterministic=True)
    sql = """SELECT e.id,e.clase,e.nombre,e.clave_fuerte,e.quien,'entidad' carril,
             (SELECT count(*) FROM mencion m WHERE m.entidad_id=e.id) menciones,
             (SELECT count(DISTINCT documento_id) FROM mencion m WHERE m.entidad_id=e.id) documentos,
             EXISTS(SELECT 1 FROM renglon r JOIN contratacion_documento cd ON cd.documento_id=r.documento_id
                    WHERE r.proveedor_id=e.id AND r.vigente=1 AND cd.estado!='rechazada') con_contrataciones
             FROM entidad e WHERE e.clase!='persona' OR NOT EXISTS(
               SELECT 1 FROM persona p WHERE p.clave_fuerte=e.clave_fuerte
               OR (digitos(p.clave_fuerte)!='' AND digitos(p.clave_fuerte)=dni_entidad(e.clave_fuerte)))
             UNION ALL
             SELECT p.id,'persona',(SELECT nombre_literal FROM persona_alias a WHERE a.persona_id=p.id ORDER BY a.id LIMIT 1),
             p.clave_fuerte,NULL,'persona',
             (SELECT count(*) FROM documento_persona dp WHERE dp.persona_id=p.id),
             (SELECT count(*) FROM documento_persona dp WHERE dp.persona_id=p.id),
             EXISTS(SELECT 1 FROM documento_persona dp JOIN contratacion_documento cd ON cd.documento_id=dp.documento_id
                    WHERE dp.persona_id=p.id AND cd.estado!='rechazada') FROM persona p"""
    where, args, applied = ['1=1'], [], {}
    if clase:
        where.append('clase=?'); args.append(clase); applied['clase'] = clase
    if f.get('q'):
        where.append('(nombre LIKE ? OR clave_fuerte LIKE ?)'); args.extend(['%'+f['q']+'%']*2); applied['q'] = f['q']
    if 'con_contrataciones' in f:
        v = pg.booleano(f['con_contrataciones']); where.append('con_contrataciones=?'); args.append(v); applied['con_contrataciones'] = v
    r = pg.consultar(cx, 'entidades', 'SELECT * FROM ('+sql+') WHERE '+' AND '.join(where), args,
                     filtros=f, ordenes={k:k for k in ('id','nombre','clase','documentos','menciones')}, defecto='nombre', aplicados=applied)
    r['clases'] = [{'clave':c,'que_es':en.ETIQUETAS[c]} for c in en.CLASES]
    r['listas_auxiliares'] = {'sin_resolver':'/api/entidades/sin-resolver', 'propuestas':'/api/entidades/propuestas'}
    return r


def resolver(cx, ruta, f):
    """None indica que el despachador habitual debe continuar."""
    from . import clasificacion as cl, piezas
    if ruta == '/api/entidades':
        return entidades(cx, f)
    if ruta == '/api/entidades/sin-resolver':
        return pg.consultar(cx, 'sin_resolver', '''SELECT m.id,m.clase,m.literal,m.norm,a.nombre archivo,
            m.pagina_nro,m.documento_id,m.origen,m.confianza FROM mencion m LEFT JOIN archivo a ON a.sha256=m.sha256
            WHERE m.entidad_id IS NULL''', filtros=f, ordenes={'id':'id','clase':'clase','nombre':'norm'})
    if ruta == '/api/entidades/propuestas':
        return pg.consultar(cx, 'propuestas', '''SELECT min(m.id) id,m.clase,m.norm,count(*) veces,min(m.literal) a,max(m.literal) b
            FROM mencion m WHERE m.entidad_id IS NULL AND NOT EXISTS(SELECT 1 FROM entidad_fusion ef
            WHERE ef.clase=m.clase AND ef.ident_a=m.norm AND ef.ident_b=m.norm AND ef.decision='rechazada')
            GROUP BY m.clase,m.norm HAVING count(*)>1''', filtros=f,
            ordenes={'veces':'veces','clase':'clase','nombre':'norm'}, defecto='veces', sentido='desc',
            transformar=lambda r:dict(r, literales=sorted({r.pop('a'),r.pop('b')})))
    if ruta == '/api/piezas/sin-reconocer':
        r = pg.consultar(cx, 'piezas', '''SELECT d.id documento_id,d.sha256,a.nombre archivo,d.orden,d.clave,
            d.pagina_desde,d.pagina_hasta,d.pagina_hasta-d.pagina_desde+1 fojas,d.tipo,d.clasificado_por
            FROM documento d JOIN archivo a ON a.sha256=d.sha256 WHERE d.estado='sin_perfil' ''', filtros=f,
            ordenes={'id':'documento_id','archivo':'archivo','foja':'pagina_desde'}, defecto='archivo')
        r['tipos'] = piezas.tipos_posibles()
        return r
    if ruta == '/api/fojas':
        where, args = (' WHERE p.sha256=?', [f['sha']]) if f.get('sha') else ('', [])
        return pg.consultar(cx, 'fojas', '''SELECT p.id,p.sha256,a.nombre archivo,p.nro,p.clasificacion clase
            FROM pagina p JOIN archivo a ON a.sha256=p.sha256'''+where, args, filtros=f,
            ordenes={'id':'id','archivo':'archivo','foja':'nro','clase':'clase'}, defecto='id',
            transformar=lambda r:dict(r, etiqueta=cl.ETIQUETAS.get(r['clase'],'Sin clasificar'), apartada=r['clase'] in cl.APARTADAS),
            aplicados={'sha':f['sha']} if f.get('sha') else {})
    if ruta == '/api/foliatura':
        sha = f['sha']
        def foja(r):
            r['foliaturas'] = [dict(x) for x in cx.execute('SELECT * FROM foliatura WHERE pagina_id=? ORDER BY serie,id',(r['pagina_id'],))]
            return r
        return pg.consultar(cx, 'fojas', 'SELECT id pagina_id,nro pagina_pdf FROM pagina WHERE sha256=?', [sha],
            filtros=f, ordenes={'foja':'pagina_pdf','id':'pagina_id'}, defecto='foja', transformar=foja, aplicados={'sha':sha})
    if ruta == '/api/foliatura/saltos':
        return pg.consultar(cx,'saltos', '''WITH secuencia AS (
            SELECT p.id,p.nro pagina_pdf,f.literal,f.numero,lag(f.numero) OVER(ORDER BY p.nro) anterior,
            lag(f.literal) OVER(ORDER BY p.nro) literal_anterior FROM foliatura f JOIN pagina p ON p.id=f.pagina_id
            WHERE p.sha256=? AND f.serie='principal' AND f.numero IS NOT NULL)
            SELECT *,CASE WHEN numero=anterior THEN 'repetida' WHEN numero<anterior THEN 'retrocede' ELSE 'salto' END clase
            FROM secuencia WHERE numero!=anterior+1''',[f['sha']],filtros=f,
            ordenes={'foja':'pagina_pdf','id':'id'},defecto='foja',aplicados={'sha':f['sha']})
    if ruta == '/api/tablas':
        # La clasificación geométrica no es SQL: una UDF valida celdas del candidato,
        # sin materializar todas las tablas ni ejecutar una consulta por candidata.
        from . import tablas as tb
        def estructurada(raw):
            return tb._estructurada(json.loads(raw or '[]'))
        cx.create_function('tabla_estructurada', 1, estructurada)
        sql = '''SELECT t.* FROM tabla t WHERE t.sha256=? AND (t.origen='humano' OR tabla_estructurada(
            (SELECT json_group_array(json_object('fila',c.fila,'texto',c.texto,'x0',c.x0,'y0',c.y0,'x1',c.x1,'y1',c.y1))
             FROM tabla_celda c WHERE c.tabla_id=t.id)))'''
        return pg.consultar(cx, 'tablas', sql, [f['sha']], filtros=f,
            ordenes={'id':'id','foja':'pagina_nro','filas':'filas'}, defecto='foja',
            transformar=lambda r:tb._arma(cx,r), aplicados={'sha':f['sha']})
    if ruta in ('/api/reasociaciones', '/api/reasociaciones/pendientes'):
        # Las candidatas se consultan aparte, también paginadas.
        return pg.consultar(cx, 'revisiones', '''SELECT r.sha256,r.orden,r.campo,r.valor,r.accion,r.quien,r.cuando,
            r.motivo,r.ancla_pagina,r.ancla_tipo,a.nombre archivo,r.orden orden_viejo
            FROM revision_humana r LEFT JOIN archivo a ON a.sha256=r.sha256 WHERE r.estado='requiere_reasociacion' ''',
            filtros=f, ordenes={'cuando':'cuando','archivo':'archivo','foja':'ancla_pagina','campo':'campo'}, defecto='cuando')
    if ruta == '/api/reasociaciones/candidatas':
        return pg.consultar(cx, 'candidatas', '''SELECT d.id documento_id,d.orden,d.tipo,d.pagina_desde,d.pagina_hasta,
            c.id campo_id,c.valor_literal valor_actual,c.estado estado_actual FROM documento d
            LEFT JOIN campo c ON c.documento_id=d.id AND c.nombre=? WHERE d.sha256=?''', [f['campo'],f['sha']],
            filtros=f, ordenes={'id':'documento_id','orden':'orden','foja':'pagina_desde'}, defecto='orden',
            aplicados={'sha':f['sha'],'campo':f['campo']})
    if ruta in ('/api/contratos', '/api/comprobantes'):
        clave, vista = ('contratos','v_contrato') if ruta.endswith('contratos') else ('comprobantes','v_comprobante')
        return pg.consultar(cx, clave, 'SELECT * FROM '+vista, filtros=f,
                            ordenes={'id':'documento_id','archivo':'archivo'}, defecto='id')
    if ruta == '/api/documentos':
        return pg.consultar(cx, 'personas', '''SELECT persona_id,MAX(nombre_literal) contratado,MAX(documento_literal) documento,
            count(*) contratos,sum(monto_centavos IS NULL) contratos_sin_monto,sum(monto_centavos) acumulado_centavos,
            min(inicio) primer_inicio,max(fin) ultimo_fin,group_concat(DISTINCT camara) camaras,min(confianza_min) confianza_min
            FROM v_contrato WHERE persona_id IS NOT NULL GROUP BY persona_id''', filtros=f,
            ordenes={'id':'persona_id','nombre':'contratado','monto':'acumulado_centavos'}, defecto='monto', sentido='desc')
    if ruta == '/api/cronologia':
        from . import cronologia as cr
        where,args,aplicados = ['1=1'],[],{}
        for k, col, op in [('desde_fecha','fecha','>='),('hasta_fecha','fecha','<='),('clase','clase','=')]:
            if f.get(k):
                where.append('e.'+col+op+'?');args.append(f[k]);aplicados[k]=f[k]
        r = pg.consultar(cx,'linea', '''SELECT e.*,d.tipo,a.nombre archivo FROM evento e
            LEFT JOIN documento d ON d.id=e.documento_id LEFT JOIN archivo a ON a.sha256=e.sha256
            WHERE '''+' AND '.join(where),args,filtros=f,ordenes={'id':'id','fecha':'fecha','clase':'clase'},defecto='fecha',
            transformar=lambda r:dict(r,que_es=cr.ETIQUETAS.get(r['clase'],r['clase'])),aplicados=aplicados)
        r['clases']=[{'clave':c,'que_es':cr.ETIQUETAS[c]} for c in cr.CLASES]
        return r
    if ruta in ('/api/relaciones','/api/relaciones/documento'):
        from . import relaciones as rl
        where,args = ("r.estado='propuesta'",[]) if ruta=='/api/relaciones' else ('(r.desde_doc=? OR r.hasta_doc=?)',[int(f['id'])]*2)
        r = pg.consultar(cx,'pendientes' if ruta=='/api/relaciones' else 'relaciones', '''SELECT r.*,a.nombre archivo_desde,b.nombre archivo_hasta
            FROM relacion r LEFT JOIN documento da ON da.id=r.desde_doc LEFT JOIN archivo a ON a.sha256=da.sha256
            LEFT JOIN documento db ON db.id=r.hasta_doc LEFT JOIN archivo b ON b.sha256=db.sha256 WHERE '''+where,
            args,filtros=f,ordenes={'id':'id','tipo':'tipo','confianza':'confianza'},
            transformar=lambda r:dict(r,que_dice=rl.TIPOS.get(r['tipo'],r['tipo'])))
        r['tipos']=rl.tipos_posibles()
        return r
    if ruta == '/api/actividad':
        return pg.consultar(cx,'ultimas', '''SELECT u.id,u.quien,u.accion,u.campo_nombre campo,u.valor_nuevo valor,
            u.cuando,u.sha256,u.orden,a.nombre archivo,d.id documento_id FROM auditoria u
            JOIN archivo a ON a.sha256=u.sha256 LEFT JOIN documento d ON d.sha256=u.sha256 AND d.orden=u.orden''',
            filtros=f,ordenes={'id':'id','cuando':'cuando','quien':'quien'},sentido='desc')
    if ruta == '/api/actividad/personas':
        return pg.consultar(cx,'quienes', '''SELECT quien,count(*) decisiones,min(cuando) primera,max(cuando) ultima
            FROM revision_humana GROUP BY quien''',filtros=f,ordenes={'quien':'quien','decisiones':'decisiones'},defecto='decisiones',sentido='desc')
    if ruta == '/api/consulta':
        from . import capa4_analisis as c4
        consulta = next((c for c in c4.catalogo() if c['id']==f.get('id')),None)
        if consulta is None:
            raise ValueError('Consulta desconocida.')
        sql=consulta['sql'].strip().rstrip(';')
        columnas=[d[0] for d in cx.execute('SELECT * FROM ('+sql+') LIMIT 0').description]
        r=pg.consultar(cx,'filas',sql,filtros=f,ordenes={k:'"'+k+'"' for k in columnas},defecto=columnas[0],aplicados={'id':f['id']})
        r.update(id=f['id'],columnas=columnas,n=r['total'])
        return r
    simples = {
        '/api/excepciones': ('excepciones', "SELECT * FROM excepcion WHERE estado='abierta'", 'id'),
        '/api/consultas-guardadas': ('consultas','SELECT * FROM consulta_guardada','id'),
        '/api/conjuntos': ('conjuntos','SELECT * FROM conjunto','id'),
        '/api/colecciones': ('colecciones','SELECT c.*,(SELECT count(*) FROM coleccion_item i WHERE i.coleccion_id=c.id) items FROM coleccion c','id'),
        '/api/interpretaciones': ('interpretaciones','SELECT * FROM interpretacion','id'),
        '/api/numeros': ('numeros', '''SELECT c.*,a.nombre archivo FROM cotejo_numero c JOIN archivo a ON a.sha256=c.sha256''','id'),
        '/api/fusiones': ('fusiones', '''SELECT f.*,
            (SELECT nombre_literal FROM persona_alias WHERE persona_id=f.persona_a LIMIT 1) lit_a,
            (SELECT nombre_literal FROM persona_alias WHERE persona_id=f.persona_b LIMIT 1) lit_b,
            (SELECT clave_fuerte FROM persona WHERE id=f.persona_a) doc_a,
            (SELECT clave_fuerte FROM persona WHERE id=f.persona_b) doc_b
            FROM fusion_propuesta f WHERE f.estado='pendiente' ''','id'),
    }
    if ruta in simples:
        clave, sql, orden = simples[ruta]
        def transformar(r):
            if ruta=='/api/consultas-guardadas':
                r['filtros']=json.loads(r['filtros'] or '{}')
            if ruta=='/api/interpretaciones':
                r['fuentes']=[dict(x) for x in cx.execute('''SELECT f.documento_id,f.nota,a.nombre archivo FROM interpretacion_fuente f
                    LEFT JOIN documento d ON d.id=f.documento_id LEFT JOIN archivo a ON a.sha256=d.sha256 WHERE f.interpretacion_id=?''',(r['id'],))]
            return r
        return pg.consultar(cx, clave, sql, filtros=f, ordenes={orden:orden}, defecto=orden,transformar=transformar)
    return None
