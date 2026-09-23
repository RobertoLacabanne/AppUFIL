"""Reconstrucción propuesta de compras, con anclas documentales y decisiones humanas."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from decimal import Decimal

from . import comparabilidad as cp, entidades, renglones as rg, tablas
from .db import ahora


ETAPA = {'acta_apertura': 'apertura', 'contrato_obra': 'orden_compra', 'recibo': 'pago'}
_PATRONES = {
    'expediente': r'\b(?:expediente|expte\.?|exp\.)\s*',
    'orden_compra': r'\borden\s+de\s+compra\s*',
    'orden_pago': r'\borden\s+de\s+pago\s*',
    'remito': r'\bremito\s*',
    'factura': r'\bfactura\s*(?:[abc]\b)?\s*',
    'licitacion': r'\blicitacion\s+(?:publica|privada)\s*',
    'resolucion': r'\bresolucion\s*',
}
_PREFIJO = r'(?:n(?:umero|ro|um)?\.?\s*[°ºoa:ª"*#·\-]*\s*|[°º:#]+\s*)?'
_NUMERO = r'(?:exp\s*[-:]\s*)?\d(?:[ \t]*\d){0,15}(?:\s*[-/]\s*\d(?:[ \t]*\d){0,7}){0,2}'


def _numero(valor):
    valor = re.sub(r'^exp\s*[-:]\s*', '', valor, flags=re.I)
    valor = re.sub(r'\s+', '', valor)
    return re.sub(r'\d+', lambda m: str(int(m[0])), valor)


def identificadores(texto):
    """No corrige letras por dígitos. CUIT inválido sólo puede ser mención literal."""
    norm = rg.normalizar(texto)
    salida = []
    for clase, patron in _PATRONES.items():
        for m in re.finditer(patron + _PREFIJO + '(' + _NUMERO + r')(?!\d)', norm):
            valor = _numero(m[1])
            if len(re.sub(r'\D', '', valor)) >= (3 if clase == 'expediente' else 1):
                salida.append({'clase': clase, 'valor': valor, 'literal': m[0]})
    for m in re.finditer(r'\bc\s*u\s*i\s*t\s*[:°ºn.]*\s*((?:\d[ .-]*){10}\d)(?!\d)', norm):
        valor = re.sub(r'\D', '', m[1])
        if entidades._cuit_valido(valor):
            salida.append({'clase': 'cuit', 'valor': valor, 'literal': m[0]})
    return salida


def paginas_archivo(cx, sha, rangos=None):
    from .capa2_extraccion import lecturas_por_ruta, palabras_de
    paginas = {}
    if rangos is not None:
        for r in cx.execute('''SELECT p.nro,l.id FROM pagina p JOIN lectura l ON l.pagina_id=p.id
                               WHERE p.sha256=? AND EXISTS(SELECT 1 FROM json_each(?) j
                               WHERE p.nro BETWEEN json_extract(j.value,'$[0]') AND json_extract(j.value,'$[1]'))
                               ORDER BY p.nro,l.ruta''', (sha, json.dumps(rangos))):
            ps = palabras_de(cx, r['id'])
            if r['nro'] not in paginas or len(ps) > len(paginas[r['nro']]):
                paginas[r['nro']] = ps
        return paginas
    for pgs in lecturas_por_ruta(cx, sha).values():
        for nro, _, ps in pgs:
            if nro not in paginas or len(ps) > len(paginas[nro]):
                paginas[nro] = ps
    return paginas


def fuente_documento(cx, doc, ancla=None):
    ancla = ancla or {'pagina_nro': doc['pagina_desde'], 'region': None, 'campo_id': None, 'celdas': None}
    return rg.fuente(cx, dict(documento_id=doc['id'], sha256=doc['sha256'],
                             etapa=doc['tipo'], anclajes=json.dumps({'fila': ancla})))


def documentos(cx, ids=None):
    salida, ultimo_sha, paginas = [], None, {}
    filtro = (' WHERE id IN (' + ','.join('?' for _ in ids) + ')') if ids is not None else ''
    seleccion = list(cx.execute('SELECT * FROM documento' + filtro + ' ORDER BY sha256,pagina_desde,id', list(ids) if ids is not None else []))
    for row in seleccion:
        d = dict(row)
        if d['sha256'] != ultimo_sha:
            paginas = paginas_archivo(cx, d['sha256'], [(r['pagina_desde'], r['pagina_hasta']) for r in seleccion
                                                       if r['sha256'] == d['sha256']] if ids is not None else None)
            ultimo_sha = d['sha256']
        d['etapa'] = ETAPA.get(d['tipo'], d['tipo'] if d['tipo'] in {e[0] for e in cp.ETAPAS} else 'otro')
        d['contexto'] = rg._contexto(cx, d, paginas, crear_entidades=False)
        d['identificadores'], d['totales'], d['atributos'], d['es_agenda'] = [], [], {}, False
        for nro in range(d['pagina_desde'], d['pagina_hasta'] + 1):
            for ps in tablas._renglones(paginas.get(nro, [])):
                texto = ' '.join(p.texto for p in ps)
                ancla = rg._ancla_palabras(ps, nro)
                if re.fullmatch(r'(?:anotacion(?:es)? de )?agenda', rg.normalizar(texto).strip(': ')):
                    d['es_agenda'] = True
                for campo in ('organismo', 'objeto'):
                    m = re.match(r'\s*' + campo + r'\s*:\s*(.+)', texto, re.I)
                    if m:
                        d['atributos'][campo] = dict(valor=m[1], fuente=fuente_documento(cx, d, ancla))
                m = re.search(r'licitacion (?:publica|privada)|concurso de precios|contratacion directa', rg.normalizar(texto))
                if m:
                    d['atributos']['procedimiento'] = dict(valor=m[0], fuente=fuente_documento(cx, d, ancla))
                for ident in identificadores(texto):
                    d['identificadores'].append(dict(ident, fuente=fuente_documento(cx, d, ancla)))
                m = re.search(r'punto de venta\s*:\s*(\d{4,5})\s+comp\.?\s*n(?:ro|[°ºo])?\.?\s*:\s*(\d{8})', rg.normalizar(texto))
                if m and d['etapa'] == 'factura':
                    d['identificadores'].append(dict(clase='factura', valor=_numero(m[1]+'-'+m[2]),
                                                    literal=m[0], fuente=fuente_documento(cx,d,ancla)))
                if re.match(r'^\s*(?:importe\s+)?total\s*[:$]', rg.normalizar(texto)):
                    nums = rg.importes(texto)
                    if len(nums) == 1:
                        d['totales'].append({'literal': nums[0], 'valor': rg.canonico(rg.decimal_argentino(nums[0])),
                            'moneda': d['contexto'].get('moneda'), 'derivado': False, 'formula': None,
                            'fuente': fuente_documento(cx, d, ancla), 'estado': 'pendiente_baja'})
        d['total'] = d['totales'][0] if len(d['totales']) == 1 else None
        d['fuente'] = fuente_documento(cx, d)
        d['fecha'] = ({'valor': d['contexto']['fecha_precio'], 'literal': d['contexto'].get('fecha_literal'),
                       'fuente': fuente_documento(cx, d, d['contexto']['anclajes']['fecha'])}
                      if d['contexto'].get('fecha_precio') else None)
        d['claves'] = {(i['clase'], i['valor']) for i in d['identificadores']}
        d['conjuntos'] = {r[0] for r in cx.execute('SELECT conjunto_id FROM conjunto_archivo WHERE sha256=?', (d['sha256'],))}
        salida.append(d)
    return salida


def reconstruir(cx):
    docs = documentos(cx)
    frecuencia = Counter(k for d in docs for k in d['claves'])
    padre = {d['id']: d['id'] for d in docs}
    expedientes = {d['id']: {v for k, v in d['claves'] if k == 'expediente'} for d in docs}
    confianza = {d['id']: .3 for d in docs}
    def raiz(i):
        while padre[i] != i:
            i = padre[i]
        return i
    for pos, a in enumerate(docs):
        for b in docs[pos + 1:]:
            comunes = a['claves'] & b['claves']
            anclas = {k for k in comunes if k[0] not in ('cuit', 'resolucion') and frecuencia[k] >= 2}
            cuit = any(k[0] == 'cuit' for k in comunes)
            cerca = a['sha256'] == b['sha256'] and abs(a['pagina_hasta'] - b['pagina_desde']) <= 3
            conjunto = bool(a['conjuntos'] & b['conjuntos'])
            if not anclas and not (cuit and (conjunto or cerca)):
                continue
            x, y = raiz(a['id']), raiz(b['id'])
            if x == y:
                continue
            if expedientes[x] and expedientes[y] and expedientes[x] != expedientes[y]:
                continue
            padre[y] = x
            expedientes[x] |= expedientes[y]
            score = .9 if any(k[0] == 'expediente' for k in anclas) else .8 if anclas and cuit else .65 if anclas else .45
            confianza[a['id']] = max(confianza[a['id']], score)
            confianza[b['id']] = max(confianza[b['id']], score)
    grupos = defaultdict(list)
    for d in docs:
        if d['etapa'] != 'otro' or d['claves']:
            grupos[raiz(d['id'])].append(d)
    with cx:
        conservar_decisiones(cx)
        _reaplicar_decisiones(cx)
        # Las decisiones humanas son un límite a la propuesta automática.
        humanos = {r[0] for r in cx.execute("SELECT documento_id FROM contratacion_documento WHERE origen='humano' OR estado!='propuesta'")}
        cx.execute("DELETE FROM contratacion_documento WHERE origen='sistema' AND estado='propuesta'")
        cx.execute('UPDATE renglon SET contratacion_id=NULL')
        propuestas = 0
        for grupo in grupos.values():
            # Una contratación que propone el sistema tiene que unir al menos dos piezas:
            # una pieza sola no es una reconstrucción, es una pieza, y se la sigue viendo
            # en Documentos. Medido en un legajo real: de 124 contrataciones propuestas,
            # 104 eran de una sola pieza y sólo 6 tenían tres etapas o más. Una persona
            # puede agrupar a mano lo que el sistema no se anima a proponer.
            if len(grupo) < 2:
                continue
            propuestas += 1
            exps = sorted({v for d in grupo for k, v in d['claves'] if k == 'expediente'})
            exp = exps[0] if len(exps) == 1 else None
            clave = 'exp:' + exp if exp else 'pieza:' + min(d['clave'] or f"{d['sha256']}:{d['pagina_desde']}" for d in grupo)
            cx.execute("""INSERT INTO contratacion(clave,nombre,expediente,procedimiento,creado_en)
                          VALUES (?,?,?,'desconocido',?) ON CONFLICT(clave) DO UPDATE SET
                          expediente=excluded.expediente WHERE contratacion.origen='sistema' AND contratacion.estado='propuesta'""",
                       (clave, 'Contratación ' + (exp or 'por verificar'), exp, ahora()))
            cid = cx.execute('SELECT id FROM contratacion WHERE clave=?', (clave,)).fetchone()[0]
            entidades_exp = [r['id'] for r in cx.execute("SELECT id,clave_fuerte FROM entidad WHERE clase='expediente' AND clave_fuerte IS NOT NULL")
                             if exp and _numero(r['clave_fuerte']) == exp]
            cx.execute("UPDATE contratacion SET expediente_entidad_id=? WHERE id=? AND origen='sistema' AND estado='propuesta'",
                       (entidades_exp[0] if len(entidades_exp) == 1 else None, cid))
            for campo in ('organismo', 'objeto', 'procedimiento'):
                valores = {d['atributos'][campo]['valor'] for d in grupo if campo in d['atributos']}
                valor = next(iter(valores)) if len(valores) == 1 else ('desconocido' if campo == 'procedimiento' else None)
                cx.execute(f"UPDATE contratacion SET {campo}=? WHERE id=? AND origen='sistema' AND estado='propuesta'", (valor, cid))
            for d in grupo:
                if d['id'] not in humanos:
                    cx.execute('INSERT OR IGNORE INTO contratacion_documento(contratacion_id,documento_id,etapa,confianza) VALUES (?,?,?,?)',
                               (cid, d['id'], d['etapa'], confianza[d['id']]))
        cx.execute("""UPDATE renglon SET contratacion_id=(SELECT min(contratacion_id) FROM contratacion_documento
                      WHERE documento_id=renglon.documento_id AND estado!='rechazada' HAVING count(DISTINCT contratacion_id)=1)""")
    return {'contrataciones': propuestas, 'identificadores': sum(len(d['identificadores']) for d in docs),
            'anclas_repetidas': sum(n >= 2 for n in frecuencia.values())}


def paginar(filtros):
    if any(isinstance(filtros.get(k), bool) for k in ('limite', 'desde')):
        raise ValueError('limite y desde deben ser enteros.')
    try:
        limite, desde = int(filtros.get('limite', 100)), int(filtros.get('desde', 0))
    except (TypeError, ValueError):
        raise ValueError('limite y desde deben ser enteros.') from None
    if limite < 1 or desde < 0:
        raise ValueError('Paginación fuera de rango.')
    return min(limite, 500), desde


def decidir_vinculo(cx, cid, documento_id, estado, quien):
    """Decisión explícita sobre una propuesta existente; no cambia otras piezas."""
    if estado not in ('confirmada', 'rechazada') or not isinstance(quien, str) or not quien.strip():
        raise ValueError('Indicá confirmada o rechazada y quién toma la decisión.')
    if not cx.execute('SELECT 1 FROM contratacion_documento WHERE contratacion_id=? AND documento_id=?',
                      (cid, documento_id)).fetchone():
        raise rg.NoEncontrado('El vínculo documental no existe.')
    with cx:
        cx.execute("UPDATE contratacion_documento SET estado=?,origen='humano',quien=?,cuando=? WHERE contratacion_id=? AND documento_id=?",
                   (estado, quien.strip(), ahora(), cid, documento_id))
        conservar_decisiones(cx)
        cx.execute("UPDATE renglon SET contratacion_id=(SELECT min(contratacion_id) FROM contratacion_documento WHERE documento_id=? AND estado!='rechazada' HAVING count(DISTINCT contratacion_id)=1) WHERE documento_id=?",
                   (documento_id, documento_id))
        from .actualizacion import invalidar
        invalidar(cx, 'hallazgos')
    return [dict(r) for r in cx.execute('SELECT * FROM contratacion_documento WHERE contratacion_id=? AND documento_id=?', (cid, documento_id))]


def _decisiones(cx):
    ultimas = {}
    for row in cx.execute("SELECT valor_nuevo FROM auditoria WHERE campo_nombre='contratacion_documento' AND accion='decision_contratacion' ORDER BY id"):
        d = json.loads(row[0])
        ultimas[(d['pieza_clave'], d['contratacion_id'], d['etapa'])] = d
    return ultimas


def conservar_decisiones(cx):
    """El diario de auditoría ya sobrevive a piezas que cambian de identidad."""
    previas = _decisiones(cx)
    for r in cx.execute("""SELECT cd.*,d.clave AS pieza_clave,d.sha256,d.orden FROM contratacion_documento cd
                           JOIN documento d ON d.id=cd.documento_id WHERE cd.origen='humano' OR cd.estado!='propuesta'"""):
        d = {k: r[k] for k in ('pieza_clave','contratacion_id','etapa','estado','quien','cuando','confianza')}
        if not d['pieza_clave'] or previas.get((d['pieza_clave'],d['contratacion_id'],d['etapa'])) == d:
            continue
        cx.execute("""INSERT INTO auditoria(sha256,orden,campo_nombre,accion,valor_nuevo,quien,cuando)
                      VALUES (?,?,'contratacion_documento','decision_contratacion',?,?,?)""",
                   (r['sha256'],r['orden'],json.dumps(d,ensure_ascii=False),r['quien'] or '',r['cuando'] or ahora()))


def _reaplicar_decisiones(cx):
    for d in _decisiones(cx).values():
        doc = cx.execute('SELECT id FROM documento WHERE clave=?', (d['pieza_clave'],)).fetchone()
        if not doc or not cx.execute('SELECT 1 FROM contratacion WHERE id=?', (d['contratacion_id'],)).fetchone():
            continue
        cx.execute("""INSERT INTO contratacion_documento(contratacion_id,documento_id,etapa,origen,estado,quien,cuando,confianza)
                      VALUES (?,?,?,'humano',?,?,?,?) ON CONFLICT(contratacion_id,documento_id,etapa) DO UPDATE SET
                      origen='humano',estado=excluded.estado,quien=excluded.quien,cuando=excluded.cuando,confianza=excluded.confianza""",
                   (d['contratacion_id'],doc[0],d['etapa'],d['estado'],d['quien'],d['cuando'],d['confianza']))


def listar(cx, **filtros):
    from . import paginacion as pg
    where = ["EXISTS(SELECT 1 FROM contratacion_documento cd WHERE cd.contratacion_id=c.id AND cd.estado!='rechazada')"]
    args, aplicados = [], {}
    for k in ('estado', 'procedimiento'):
        if filtros.get(k):
            where.append('c.'+k+'=?'); args.append(filtros[k]); aplicados[k] = filtros[k]
    if filtros.get('q'):
        where.append("(c.nombre LIKE ? OR c.objeto LIKE ? OR c.expediente LIKE ?)")
        args.extend(['%'+filtros['q']+'%']*3); aplicados['q'] = filtros['q']
    if filtros.get('proveedor_id'):
        where.append("EXISTS(SELECT 1 FROM renglon r JOIN contratacion_documento cd ON cd.documento_id=r.documento_id WHERE cd.contratacion_id=c.id AND cd.estado!='rechazada' AND r.vigente=1 AND r.proveedor_id=?)")
        args.append(int(filtros['proveedor_id'])); aplicados['proveedor_id'] = args[-1]
    if 'con_hallazgo' in filtros:
        v = pg.booleano(filtros['con_hallazgo'])
        where.append(('' if v else 'NOT ')+"EXISTS(SELECT 1 FROM hallazgo h WHERE h.contratacion_id=c.id AND h.ya_no_se_detecta=0)")
        aplicados['con_hallazgo'] = v
    if filtros.get('etapa_faltante'):
        etapa = filtros['etapa_faltante']
        if etapa not in {e[0] for e in cp.ETAPAS} | {'ofertas'}:
            raise ValueError('etapa_faltante desconocida.')
        where.append("NOT EXISTS(SELECT 1 FROM contratacion_documento cd WHERE cd.contratacion_id=c.id AND cd.estado!='rechazada' AND cd.etapa=?)")
        args.append('oferta' if etapa == 'ofertas' else etapa); aplicados['etapa_faltante'] = etapa
    resultado = pg.consultar(cx, 'contrataciones', 'SELECT c.* FROM contratacion c WHERE '+' AND '.join(where), args,
                        filtros=filtros, ordenes={k:k for k in ('id','nombre','estado','procedimiento','expediente')}, aplicados=aplicados)
    claves = ('pliego','ofertas','adjudicacion','orden_compra','factura','remito','pago')
    filas = {c['id']: c for c in resultado['contrataciones']}
    for c in filas.values():
        c['etapas'] = dict.fromkeys(claves, 0)
    if filas:
        for r in cx.execute('''SELECT contratacion_id,etapa,count(DISTINCT documento_id) cantidad
                FROM contratacion_documento WHERE estado!='rechazada'
                AND contratacion_id IN (SELECT value FROM json_each(?))
                GROUP BY contratacion_id,etapa''', (json.dumps(list(filas)),)):
            clave = 'ofertas' if r['etapa'] == 'oferta' else r['etapa']
            if clave in claves:
                filas[r['contratacion_id']]['etapas'][clave] = r['cantidad']
    return resultado


def totalizar(montos):
    if not montos or any(m is None for m in montos):
        return None
    if len(montos) == 1:
        return montos[0]
    if len({m['moneda'] for m in montos}) != 1:
        return None
    return dict(literal=None, valor=rg.canonico(sum(Decimal(m['valor']) for m in montos)),
                moneda=montos[0]['moneda'], derivado=True, formula='suma de totales documentales',
                fuente=montos[0]['fuente'], fuentes=[m['fuente'] for m in montos],
                operandos=[{'valor': m['valor'], 'fuente': m['fuente']} for m in montos], estado='pendiente_baja')


def ficha(cx, cid, *, docs=None, incluir_hallazgos=True):
    c = cx.execute('SELECT * FROM contratacion WHERE id=?', (cid,)).fetchone()
    if c is None:
        raise rg.NoEncontrado('La contratación no existe.')
    links = {r['documento_id']: dict(r) for r in cx.execute("SELECT * FROM contratacion_documento WHERE contratacion_id=? AND estado!='rechazada'", (cid,))}
    docs = [d for d in (docs if docs is not None else documentos(cx, ids=links)) if d['id'] in links]
    etapas, cronologia = [], []
    for clave, nombre, _ in cp.ETAPAS:
        piezas = []
        for d in docs:
            if links[d['id']]['etapa'] != clave:
                continue
            piezas.append(dict(documento_id=d['id'], tipo=d['tipo'], fecha=d['fecha'], etiqueta=nombre,
                               fuente=d['fuente'], estado=links[d['id']]['estado'], confianza=links[d['id']]['confianza'],
                               identificadores=d['identificadores']))
            if d['fecha']:
                cronologia.append(dict(fecha=d['fecha']['valor'], etapa=clave, etiqueta=nombre, fuente=d['fecha']['fuente']))
        etapas.append(dict(clave=clave, nombre=nombre, rotulo=nombre, presente=bool(piezas), cantidad=len(piezas),
                           ausencia=None if piezas else 'no_consta', documento_ids=[p['documento_id'] for p in piezas], documentos=piezas))
    oferentes = {}
    for d in docs:
        ctx = d['contexto']
        if d['etapa'] not in ('oferta', 'adjudicacion', 'orden_compra') or not ctx.get('proveedor_literal'):
            continue
        k = ctx.get('proveedor_cuit') or ctx['proveedor_literal']
        p = oferentes.setdefault(k, dict(entidad_id=ctx.get('proveedor_id'), nombre=ctx['proveedor_literal'],
                                         cuit=ctx.get('proveedor_cuit'), adjudicado=False))
        p['adjudicado'] |= d['etapa'] in ('adjudicacion', 'orden_compra')
    totales = {}
    for nombre, candidatos in [('adjudicado', ('orden_compra', 'adjudicacion')), ('facturado', ('factura',)), ('pagado', ('pago',))]:
        etapa = next((e for e in candidatos if any(d['etapa'] == e for d in docs)), None)
        totales[nombre] = totalizar([d['total'] for d in docs if etapa and d['etapa'] == etapa])
    columnas, filas = {}, {}
    for r in cx.execute('SELECT * FROM renglon WHERE vigente=1 AND contratacion_id=? ORDER BY id', (cid,)):
        r = dict(r)
        if r['etapa'] not in ('oferta', 'adjudicacion', 'orden_compra', 'factura'):
            continue
        col = str(r['documento_id'])
        columnas[col] = dict(clave=col, titulo=r['etapa'] + ': ' + (r['proveedor_literal'] or 'sin atribuir'), entidad_id=r['proveedor_id'])
        dato = rg.serializar(cx, r)
        k = (r['desc_norm'], r['unidad_norm'])
        f = filas.setdefault(k, dict(item=dato['item'], descripcion=dato['descripcion'], valores={}, menor=None))
        # No colapsar dos renglones del mismo producto y documento.
        if col in f['valores']:
            f = filas.setdefault(k + (r['clave'],), dict(item=dato['item'], descripcion=dato['descripcion'], valores={}, menor=None))
        f['valores'][col] = dato['precio_unitario']
    for f in filas.values():
        conocidos = [(k, m) for k, m in f['valores'].items() if m['valor'] is not None]
        if conocidos and len({m['moneda'] for _, m in conocidos}) == 1 and conocidos[0][1]['moneda']:
            f['menor'] = min(conocidos, key=lambda par: Decimal(par[1]['valor']))[0]
    from . import hallazgos
    estado_etapas = [dict(clave='ofertas' if e['clave']=='oferta' else e['clave'], rotulo=e['rotulo'],
                         presente=e['presente'], cantidad=e['cantidad'], documentos=e['documento_ids'], ausencia=e['ausencia'])
                     for e in etapas if e['clave'] in ('pliego','oferta','adjudicacion','orden_compra','factura','remito','pago')]
    return dict(contratacion=dict(c), etapas=etapas, estado_etapas=estado_etapas, oferentes=list(oferentes.values()),
                matriz=dict(columnas=list(columnas.values()), filas=list(filas.values())), totales=totales,
                cronologia=sorted(cronologia, key=lambda e: e['fecha']),
                decisiones_sin_pieza=[d for d in _decisiones(cx).values() if d['contratacion_id'] == cid and
                                     not cx.execute('SELECT 1 FROM documento WHERE clave=?', (d['pieza_clave'],)).fetchone()],
                hallazgos=hallazgos.listar(cx, contratacion=cid, limite=500)['hallazgos'] if incluir_hallazgos else [])
