"""Filas documentales con sus literales, decimales y fuentes; nunca precios inventados."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

from . import clasificacion as cl, confianza as cf, tablas, versiones
from .db import ahora


def normalizar(texto):
    t = unicodedata.normalize('NFKD', texto or '')
    return ' '.join(''.join(c for c in t if not unicodedata.combining(c)).lower().split())


def decimal_argentino(literal):
    """No acepta basura OCR, separadores incoherentes ni valores no finitos."""
    if literal is None:
        return None
    t = re.sub(r'^(?:ARS|USD|EUR|\$)\s*', '', str(literal).strip(), flags=re.I)
    t = re.sub(r'\s*(?:ARS|USD|EUR)$', '', t, flags=re.I).strip()
    if not re.fullmatch(r'[+-]?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?', t):
        return None
    try:
        return Decimal(t.replace('.', '').replace(',', '.'))
    except InvalidOperation:
        return None


def canonico(valor):
    if valor is None:
        return None
    # Dos decimales como mínimo, sin redondear un precio unitario impreso más preciso.
    return format(valor, '.2f') if valor.as_tuple().exponent >= -2 else format(valor, 'f')


_UNIDADES = {
    'u': 'unidad', 'un': 'unidad', 'unid': 'unidad', 'unidad': 'unidad', 'unidades': 'unidad',
    'lt': 'litro', 'lts': 'litro', 'l': 'litro', 'litro': 'litro', 'litros': 'litro',
    'kg': 'kilogramo', 'kgs': 'kilogramo', 'kilo': 'kilogramo', 'kilogramo': 'kilogramo',
    'm': 'metro', 'mts': 'metro', 'metro': 'metro', 'metros': 'metro',
    'm2': 'metro cuadrado', 'm3': 'metro cubico', 'hs': 'hora', 'hora': 'hora',
}


def unidad(texto):
    t = normalizar(texto).strip('.')
    return _UNIDADES.get(t, t or None)


def atributos(descripcion):
    """Sólo etiquetas expresas: un nombre comercial suelto no se presume marca."""
    salida = {}
    for atributo in ('marca', 'modelo', 'categoria', 'especificaciones'):
        m = re.search(r'\b' + atributo + r'\s*:\s*(.+?)(?=\s+(?:marca|modelo|categoria|especificaciones)\s*:|[;\n]|$)',
                      descripcion, re.I)
        salida[atributo] = normalizar(m[1]) if m else None
    return salida


def _rol(t):
    t = normalizar(t).replace('.', '')
    if re.search(r'sub\s*total|importe|total', t):
        return 'subtotal'
    if re.search(r'(?:precio|p|valor)\s*(?:unitario|unit|u)\b', t):
        return 'precio'
    if re.search(r'cantidad|\bcant\b', t):
        return 'cantidad'
    if re.search(r'unidad|\bunid\b|\bum\b', t):
        return 'unidad'
    if re.search(r'descrip|detalle|concepto|designacion|articulo|producto', t):
        return 'descripcion'
    return None


def columnas(celdas, palabras=None, tabla=None):
    """Encabezado primero; contenido sólo para descripción y unidad inequívocas.

    Dos columnas de números sin rótulo no permiten decidir cuál es el precio.
    No se toma el subtotal por unitario para completar artificialmente una fila.
    """
    roles = {}
    for c in celdas:
        if c['es_encabezado']:
            rol = _rol(c['texto'])
            if rol and rol not in roles:
                roles[rol] = c['columna']
    datos = [c for c in celdas if not c['es_encabezado']]
    por_col = {}
    for c in datos:
        por_col.setdefault(c['columna'], []).append(c['texto'] or '')
    libres = {k: ts for k, ts in por_col.items() if k not in roles.values()}
    if 'unidad' not in roles:
        candidatas = [k for k, ts in libres.items()
                      if ts and all(normalizar(t).strip('.') in _UNIDADES for t in ts)]
        if len(candidatas) == 1:
            roles['unidad'] = candidatas[0]
    if 'descripcion' not in roles:
        candidatas = [k for k, ts in libres.items() if k not in roles.values()
                      and ts and all(re.search(r'[a-zA-Záéíóúñ]{3}', t) for t in ts)]
        if len(candidatas) == 1:
            roles['descripcion'] = candidatas[0]
    # Un encabezado largo puede no respetar los blancos del cuerpo. Se lo lee
    # arriba del bloque, proyectado sobre las columnas YA detectadas, sin inventar
    # una fila ni alterar las celdas originales.
    if palabras and tabla:
        xs = {col: min(c['x0'] for c in datos if c['columna'] == col) for col in por_col}
        for ps in reversed(tablas._renglones([p for p in palabras
                                             if tabla['y0'] - 45 <= p.y0 < tabla['y0'] - 2])):
            por = {}
            for p in ps:
                col = min(xs, key=lambda col: abs(xs[col] - p.x0))
                por.setdefault(col, []).append(p.texto)
            halladas = {_rol(' '.join(ts)): col for col, ts in por.items() if _rol(' '.join(ts))}
            if len(halladas) >= 2 and any(k in halladas for k in ('descripcion', 'cantidad')):
                roles.update(halladas)
                break
    # La cuenta de varias filas puede desambiguar columnas monetarias sin título.
    # Exige cantidad conocida: un código numérico no se presume una cantidad.
    if 'cantidad' in roles and 'precio' not in roles and 'subtotal' not in roles:
        monetarias = [col for col, ts in por_col.items() if col not in roles.values()
                      and sum(decimal_argentino(t) is not None and bool(re.search(r',\d{2}\b', t))
                              for t in ts) >= 2]
        pares = []
        por_fila = {}
        for c in datos:
            por_fila.setdefault(c['fila'], {})[c['columna']] = decimal_argentino(c['texto'])
        for pu in monetarias:
            for sub in monetarias:
                if pu == sub:
                    continue
                filas = [(f.get(roles['cantidad']), f.get(pu), f.get(sub)) for f in por_fila.values()]
                completas = [(q, p, s) for q, p, s in filas if None not in (q, p, s)]
                if (len(completas) >= 2 and any(q != 1 for q, _, _ in completas)
                        and all(q > 0 and q * p == s for q, p, s in completas)):
                    pares.append((pu, sub))
        if len(pares) == 1:
            roles['precio'], roles['subtotal'] = pares[0]
    return roles


def _ancla(celdas, pagina):
    return {'pagina_nro': pagina, 'celdas': [c['id'] for c in celdas], 'campo_id': None,
            'region': dict(zip(('x0', 'y0', 'x1', 'y1'),
                              (min(c['x0'] for c in celdas), min(c['y0'] for c in celdas),
                               max(c['x1'] for c in celdas), max(c['y1'] for c in celdas))))}


def _ancla_palabras(ps, pagina):
    return {'pagina_nro': pagina, 'celdas': None, 'campo_id': None,
            'region': {'x0': min(p.x0 for p in ps), 'y0': min(p.y0 for p in ps),
                       'x1': max(p.x1 for p in ps), 'y1': max(p.y1 for p in ps)}}


def _contexto(cx, doc, paginas):
    """Datos explícitos de la pieza, con región de cada evidencia."""
    salida = {'anclajes': {}, 'condiciones': []}
    lineas = []
    for nro in range(doc['pagina_desde'], doc['pagina_hasta'] + 1):
        for ps in tablas._renglones(paginas.get(nro, [])):
            lineas.append((' '.join(p.texto for p in ps), ps, nro))
    proveedores, monedas, tratamientos = [], set(), set()
    for texto, ps, nro in lineas:
        norm = normalizar(texto)
        ancla = _ancla_palabras(ps, nro)
        if 'fecha_precio' not in salida and re.search(r'\bfecha\b', norm):
            m = re.search(r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b', texto)
            if m:
                try:
                    salida.update(fecha_precio=date(int(m[3]), int(m[2]), int(m[1])).isoformat(),
                                  fecha_literal=m[0])
                    salida['anclajes']['fecha'] = ancla
                except ValueError:
                    pass
        m = re.search(r'\b(?:expediente|expte\.?)\s*[:N°º.]*\s*(\S+)', texto, re.I)
        if m and 'expediente' not in salida:
            salida['expediente'] = m[1]
            salida['anclajes']['expediente'] = ancla
        moneda = ('USD' if re.search(r'\busd\b|dolares|u\$s', norm) else
                  'EUR' if re.search(r'\beur\b|euros', norm) else
                  'ARS' if re.search(r'\bars\b|\bpesos\b', norm) else None)
        if moneda:
            monedas.add(moneda)
            salida['moneda'] = moneda
            salida['anclajes']['moneda'] = ancla
        if re.search(r'iva\s+incluido', norm):
            tratamientos.add('incluido')
            salida['iva'] = 'incluido'
            salida['anclajes']['iva'] = ancla
        elif re.search(r'iva\s+discriminado', norm):
            tratamientos.add('discriminado')
            salida['iva'] = 'discriminado'
            salida['anclajes']['iva'] = ancla
        for condicion in ('flete', 'instalacion', 'garantia'):
            if re.search(r'\b' + condicion + r'\b', norm):
                salida['condiciones'].append(condicion)
                salida['anclajes'][condicion] = ancla
        m = re.search(r'\bCU[IÍ]T\s*[:N°º.]*\s*(\d{2}[- .]?\d{8}[- .]?\d)\b', texto, re.I)
        if m:
            nombre = re.sub(r'^(?:proveedor|oferente|beneficiario|adjudicase a)\s*:?\s*',
                            '', texto[:m.start()].strip(), flags=re.I)
            proveedores.append((m[1], nombre, ancla))
    for k, vistos in (('moneda', monedas), ('iva', tratamientos)):
        if len(vistos) > 1:
            salida.pop(k, None)
            salida['anclajes'].pop(k, None)
    # Dos CUIT pueden ser comprador y vendedor: sin una atribución unívoca no se elige.
    if len({re.sub(r'\D', '', p[0]) for p in proveedores}) == 1:
        cuit, nombre, ancla = proveedores[0]
        salida.update(proveedor_cuit=cuit, proveedor_literal=nombre or cuit)
        salida['anclajes']['proveedor'] = ancla
        from . import entidades as en
        reconocidos = [m for m in en.detectar_en_texto(cuit) if m.get('clave_fuerte')]
        if reconocidos:
            m = reconocidos[0]
            cx.execute("""INSERT INTO entidad(clase,clave_fuerte,nombre,nombre_norm,creado_en)
                          VALUES (?,?,?,?,?) ON CONFLICT(clase,clave_fuerte) DO NOTHING""",
                       (m['clase'], m['clave_fuerte'], nombre or cuit,
                        en.normalizar(nombre or cuit), ahora()))
            salida['proveedor_id'] = cx.execute(
                'SELECT id FROM entidad WHERE clase=? AND clave_fuerte=?',
                (m['clase'], m['clave_fuerte'])).fetchone()[0]
    # Campos revisados de la pieza tienen prioridad y conservan su propia fuente.
    for c in cx.execute('SELECT * FROM campo WHERE documento_id=?', (doc['id'],)):
        if c['nombre'] in ('fecha', 'fecha_emision', 'fecha_documento') and c['valor_literal']:
            m = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', c['valor_literal'])
            if m and c['x0'] is not None:
                try:
                    salida['fecha_precio'] = date(int(m[3]), int(m[2]), int(m[1])).isoformat()
                    salida['fecha_literal'] = c['valor_literal']
                    salida['anclajes']['fecha'] = {
                        'pagina_nro': c['pagina_nro'], 'campo_id': c['id'], 'celdas': None,
                        'region': {k: c[k] for k in ('x0', 'y0', 'x1', 'y1')}}
                except ValueError:
                    pass
    if 'fecha_precio' not in salida:
        eventos = cx.execute("SELECT * FROM evento WHERE documento_id=? AND clase='documento'", (doc['id'],)).fetchall()
        if len({e['fecha'] for e in eventos}) == 1:
            e = eventos[0]
            try:
                fecha = date.fromisoformat(e['fecha']).isoformat()
            except ValueError:
                fecha = None
            if fecha and e['pagina_nro'] is not None:
                salida.update(fecha_precio=fecha, fecha_literal=e['literal'])
                salida['anclajes']['fecha'] = {'pagina_nro': e['pagina_nro'], 'campo_id': e['campo_id'],
                                              'region': None, 'celdas': None, 'evento_id': e['id']}
    salida['condiciones'] = sorted(set(salida['condiciones']))
    return salida


def extraer_archivo(cx, sha, *, por_ruta=None):
    from .capa2_extraccion import lecturas_por_ruta
    por_ruta = por_ruta or lecturas_por_ruta(cx, sha)
    paginas = {}
    for ruta, pgs in por_ruta.items():
        for nro, _, ps in pgs:
            if nro not in paginas or len(ps) > len(paginas[nro]):
                paginas[nro] = ps
    docs = {d['id']: dict(d) for d in cx.execute('SELECT * FROM documento WHERE sha256=?', (sha,))}
    contextos, cantidad = {}, 0
    with cx:
        cx.execute('UPDATE renglon SET vigente=0 WHERE sha256=?', (sha,))
        for t in cx.execute('SELECT * FROM tabla WHERE sha256=? ORDER BY pagina_nro,orden', (sha,)).fetchall():
            doc = docs.get(t['documento_id'])
            if not doc:
                doc = next((d for d in docs.values() if d['pagina_desde'] <= t['pagina_nro'] <= d['pagina_hasta']), None)
            if not doc or doc['tipo'] not in cl.TIPOS_CON_PRECIO | {'pedido', 'remito'}:
                continue
            if doc['id'] not in contextos:
                contextos[doc['id']] = _contexto(cx, doc, paginas)
            contexto = contextos[doc['id']]
            celdas = [dict(c) for c in cx.execute('SELECT * FROM tabla_celda WHERE tabla_id=? ORDER BY fila,columna', (t['id'],))]
            roles = columnas(celdas, paginas.get(t['pagina_nro']), t)
            if 'descripcion' not in roles:
                continue
            for fila in sorted({c['fila'] for c in celdas if not c['es_encabezado']}):
                cs = {c['columna']: c for c in celdas if c['fila'] == fila and not c['es_encabezado']}
                valores = {rol: cs[col] for rol, col in roles.items() if col in cs}
                desc = valores.get('descripcion')
                if not desc or not desc['texto'] or re.match(r'^(?:sub\s*total|total)\b', normalizar(desc['texto'])):
                    continue
                if not any(k in valores for k in ('precio', 'subtotal', 'cantidad')):
                    continue
                anclas = dict(contexto['anclajes'])
                for rol, celda in valores.items():
                    anclas[rol] = _ancla([celda], t['pagina_nro'])
                anclas['fila'] = _ancla(list(cs.values()), t['pagina_nro'])
                def literal(k):
                    return valores[k]['texto'] if k in valores else None
                cant, precio, sub = (decimal_argentino(literal(k)) for k in ('cantidad', 'precio', 'subtotal'))
                derivado, formula = False, None
                motivo = None if precio is not None else ('ilegible' if literal('precio') else 'ausente')
                if precio is None and literal('precio') is None and sub is not None and cant is not None and cant > 0:
                    precio, derivado, formula, motivo = sub / cant, True, 'subtotal / cantidad', None
                    anclas['precio'] = _ancla([valores['subtotal'], valores['cantidad']], t['pagina_nro'])
                pieza = doc['clave'] or f"{sha}:{doc['pagina_desde']}"
                region = ':'.join(f"{desc[k]:.1f}" for k in ('x0', 'y0', 'x1', 'y1'))
                clave = f"{pieza}:{t['pagina_nro']}:{region}"
                confianza = min(c['confianza'] or 0 for c in valores.values())
                # Una sola ruta elegida no equivale a doble lectura concordante.
                estado = cf.PENDIENTE_BAJA if precio is not None else cf.NO_REVISADO
                r = {k: v for k, v in contexto.items() if k not in ('anclajes', 'condiciones')}
                r.update(atributos(desc['texto']))
                r.update(clave=clave, sha256=sha, pieza_clave=pieza, documento_id=doc['id'],
                         tabla_id=t['id'], fila=fila, pagina_nro=t['pagina_nro'], desc_celda_id=desc['id'],
                         desc_literal=desc['texto'], desc_norm=normalizar(desc['texto']),
                         unidad_literal=literal('unidad'), unidad_norm=unidad(literal('unidad')),
                         cantidad_literal=literal('cantidad'), cantidad=canonico(cant),
                         precio_literal=literal('precio'), precio_unitario=canonico(precio), precio_motivo=motivo,
                         precio_derivado=int(derivado), precio_formula=formula,
                         subtotal_literal=literal('subtotal'), subtotal=canonico(sub),
                         etapa='apertura' if doc['tipo'] == 'acta_apertura' else doc['tipo'],
                         condiciones=json.dumps(contexto['condiciones']),
                         anclajes=json.dumps(anclas, ensure_ascii=False), metodo='tabla_encabezado_contenido',
                         version=versiones.etapa('renglones').version, confianza=confianza,
                         estado=estado, vigente=1, actualizado_en=ahora())
                # Ausencias nuevas no pueden dejar datos obsoletos de una corrida anterior.
                for k in ('moneda', 'iva', 'fecha_precio', 'fecha_literal', 'proveedor_id',
                          'proveedor_literal', 'proveedor_cuit', 'expediente'):
                    r.setdefault(k, None)
                ks = list(r)
                cx.execute(f"INSERT INTO renglon ({','.join(ks)}) VALUES ({','.join('?' for _ in ks)}) "
                           f"ON CONFLICT(clave) DO UPDATE SET {','.join(k+'=excluded.'+k for k in ks if k!='clave')}",
                           [r[k] for k in ks])
                item_clave = hashlib.sha256(json.dumps([r['desc_norm'], r['unidad_norm']], ensure_ascii=False).encode()).hexdigest()
                cx.execute('INSERT INTO item(clave,nombre,unidad,creado_en) VALUES (?,?,?,?) ON CONFLICT(clave) DO NOTHING',
                           (item_clave, r['desc_norm'], r['unidad_norm'], ahora()))
                iid = cx.execute('SELECT id FROM item WHERE clave=?', (item_clave,)).fetchone()[0]
                cx.execute("""INSERT INTO renglon_item(sha256,renglon_clave,item_id,comparabilidad,origen)
                              VALUES (?,?,?,'probable','sistema') ON CONFLICT(renglon_clave) DO UPDATE
                              SET item_id=excluded.item_id,comparabilidad=excluded.comparabilidad
                              WHERE renglon_item.origen='sistema'""", (sha, clave, iid))
                cantidad += 1
    return {'renglones': cantidad}


class NoEncontrado(ValueError):
    pass


def fila(cx, rid):
    r = cx.execute('SELECT * FROM renglon WHERE id=? AND vigente=1 AND documento_id IS NOT NULL', (rid,)).fetchone()
    if not r:
        raise NoEncontrado('Ese renglón no existe o necesita actualizar el análisis.')
    return dict(r)


def fuente(cx, r, rol='fila'):
    ancla = json.loads(r['anclajes']).get(rol)
    if not ancla:
        return None
    p = cx.execute('SELECT ancho_pt,alto_pt FROM pagina WHERE sha256=? AND nro=?',
                   (r['sha256'], ancla['pagina_nro'])).fetchone()
    a = cx.execute('SELECT nombre FROM archivo WHERE sha256=?', (r['sha256'],)).fetchone()
    return {'documento_id': r['documento_id'], 'sha256': r['sha256'], 'archivo': a[0],
            'pagina_nro': ancla['pagina_nro'], 'pagina': dict(p), 'region': ancla['region'],
            'tipo_documento': r['etapa'], 'etiqueta': cl.ETIQUETAS.get(r['etapa'], r['etapa']),
            'celdas': ancla['celdas'], 'campo_id': ancla['campo_id']}


def monto(cx, r, subtotal=False):
    return {'literal': r['subtotal_literal'] if subtotal else r['precio_literal'],
            'valor': r['subtotal'] if subtotal else r['precio_unitario'], 'moneda': r['moneda'],
            'derivado': False if subtotal else bool(r['precio_derivado']),
            'formula': None if subtotal else r['precio_formula'],
            'fuente': fuente(cx, r, 'subtotal' if subtotal else 'precio'), 'estado': r['estado']}


def contratacion_de(cx, r):
    vinculadas = cx.execute("""SELECT DISTINCT c.id,c.nombre FROM contratacion_documento cd
                               JOIN contratacion c ON c.id=cd.contratacion_id
                               WHERE cd.documento_id=? AND cd.estado!='rechazada'""", (r['documento_id'],)).fetchall()
    if len(vinculadas) == 1:
        return dict(vinculadas[0])
    if r['contratacion_id']:
        c = cx.execute('SELECT id,nombre FROM contratacion WHERE id=?', (r['contratacion_id'],)).fetchone()
        return dict(c) if c else None
    return None


def serializar(cx, r):
    item = cx.execute('SELECT i.id,i.nombre,ri.comparabilidad FROM renglon_item ri JOIN item i ON i.id=ri.item_id WHERE ri.renglon_clave=?', (r['clave'],)).fetchone()
    prov = None
    if r['proveedor_literal'] or r['proveedor_id']:
        prov = {'entidad_id': r['proveedor_id'], 'nombre': r['proveedor_literal'], 'cuit': r['proveedor_cuit']}
    return {'id': r['id'], 'fecha': {'valor': r['fecha_precio'], 'literal': r['fecha_literal'],
                                    'fuente': fuente(cx, r, 'fecha')} if r['fecha_precio'] else None,
            'contratacion': contratacion_de(cx, r), 'expediente': r['expediente'], 'etapa': r['etapa'],
            'proveedor': prov, 'descripcion': {'literal': r['desc_literal'], 'normalizada': r['desc_norm']},
            'item': dict(item) if item else None, 'marca': r['marca'], 'modelo': r['modelo'],
            'cantidad': {'literal': r['cantidad_literal'], 'valor': r['cantidad']} if r['cantidad_literal'] is not None else None,
            'unidad': {'literal': r['unidad_literal'], 'normalizada': r['unidad_norm']} if r['unidad_literal'] is not None else None,
            'precio_unitario': monto(cx, r), 'subtotal': monto(cx, r, True) if r['subtotal_literal'] is not None else None,
            'fuente': fuente(cx, r), 'estado': r['estado'], 'comparacion': None}


def asignar_item(cx, rid, cuerpo):
    if not isinstance(cuerpo, dict):
        raise ValueError('Se necesita un objeto JSON.')
    decision, quien = cuerpo.get('decision'), cuerpo.get('quien')
    if decision not in ('mismo', 'distinto') or not isinstance(quien, str) or not quien.strip():
        raise ValueError('Indicá la decisión (mismo o distinto) y quién la toma.')
    r = fila(cx, rid)
    iid, crear = cuerpo.get('item_id'), cuerpo.get('crear')
    if (iid is None) == (crear is None):
        raise ValueError('Indicá item_id o crear, uno solo.')
    with cx:
        if crear is not None:
            if decision != 'mismo' or not isinstance(crear, dict) or not isinstance(crear.get('nombre'), str) or not crear['nombre'].strip():
                raise ValueError('Para crear un ítem, indicá su nombre y la decisión mismo.')
            iid = cx.execute("INSERT INTO item(nombre,origen,quien,creado_en) VALUES (?,'humano',?,?)",
                             (crear['nombre'].strip(), quien.strip(), ahora())).lastrowid
        elif isinstance(iid, bool) or not isinstance(iid, int) or not cx.execute('SELECT 1 FROM item WHERE id=?', (iid,)).fetchone():
            raise ValueError('Ese ítem no existe.')
        estado = 'fuerte' if decision == 'mismo' else 'no_comparable'
        motivos = json.dumps([{'atributo': 'decision_humana', 'a': decision, 'b': quien.strip(),
                               'efecto': 'coincide' if decision == 'mismo' else 'bloquea'}])
        cx.execute("""INSERT INTO renglon_item(sha256,renglon_clave,item_id,comparabilidad,motivos,decision,origen,quien,cuando)
                      VALUES (?,?,?,?,?,?,'humano',?,?) ON CONFLICT(renglon_clave) DO UPDATE SET
                      item_id=excluded.item_id,comparabilidad=excluded.comparabilidad,motivos=excluded.motivos,
                      decision=excluded.decision,origen='humano',quien=excluded.quien,cuando=excluded.cuando""",
                   (r['sha256'], r['clave'], iid, estado, motivos, decision, quien.strip(), ahora()))
    return {'renglon_id': rid, 'item_id': iid, 'decision': decision, 'comparabilidad': estado,
            'quien': quien.strip()}

