"""Filas documentales con sus literales, decimales y fuentes; nunca precios inventados."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from difflib import SequenceMatcher
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
    t = str(literal).strip().strip('|[]_ ').strip()
    t = re.sub(r'^(?:ARS|USD|EUR|\$)\s*', '', t, flags=re.I)
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
    t = t.strip('|[]_ ')
    if re.search(r'precio\s+un\w+|p\s+unit', t):
        return 'precio'
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
    for palabra, rol in [('importe', 'subtotal'), ('cantidad', 'cantidad'),
                         ('descripcion', 'descripcion'), ('unitario', 'precio')]:
        if any(SequenceMatcher(None, palabra, token).ratio() >= .78 for token in t.split()):
            return rol
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
                      and ts and sum(bool(re.search(r'[a-zA-Záéíóúñ]{3}', t)) for t in ts) >= max(1, len(ts)*.6)]
        if len(candidatas) == 1:
            roles['descripcion'] = candidatas[0]
    # Un encabezado largo puede no respetar los blancos del cuerpo. Se lo lee
    # arriba del bloque, proyectado sobre las columnas YA detectadas, sin inventar
    # una fila ni alterar las celdas originales.
    if palabras and tabla:
        xs = {col: min(c['x0'] for c in datos if c['columna'] == col) for col in por_col}
        for ps in reversed(tablas._renglones([p for p in palabras
                                             if 0 <= p.y0 < tabla['y0'] - 2])):
            por = {}
            for p in ps:
                col = min(xs, key=lambda col: abs(xs[col] - p.x0))
                por.setdefault(col, []).append(p.texto)
            halladas = {_rol(' '.join(ts)): col for col, ts in por.items() if _rol(' '.join(ts))}
            if len(halladas) >= 2 and any(k in halladas for k in ('descripcion', 'cantidad')):
                roles.update(halladas)
                break
    # Cantidades sin título requieren también una columna de unidades explícitas.
    # Un código numérico solo sigue sin ser una cantidad.
    if 'cantidad' not in roles and 'unidad' in roles:
        candidatas = [col for col, ts in por_col.items() if col not in roles.values()
                      and ts and all(decimal_argentino(t) is not None and ',' not in t for t in ts)]
        if len(candidatas) == 1:
            roles['cantidad'] = candidatas[0]
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


_IMPORTE = re.compile(r'(?<![\w.,])(?:\$\s*)?[+-]?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}(?![\d.,]|\s*%)')


def importes(texto):
    """Tokens completos; ni porcentajes ni reparación de dígitos OCR."""
    return [m.group() for m in _IMPORTE.finditer(texto or '')]


def celdas_ocr(celdas):
    """Desdobla columnas fundidas conservando id y región de la celda original.

    Sólo separadores explícitos o dos importes completos permiten desdoblar.
    Un número sin coma decimal no se convierte en dinero.
    """
    salida = []
    for c in celdas:
        texto = c['texto'] or ''
        partes = [p.strip() for p in re.split(r'[|]', texto) if p.strip()]
        # Las barras dentro de la descripción no definen columnas por sí solas.
        if len(partes) > 1 and sum(decimal_argentino(p) is not None for p in partes) >= 2:
            for i, p in enumerate(partes):
                salida.append(dict(c, columna=c['columna'] * 100 + i, texto=p))
        else:
            nums = importes(texto)
            if len(nums) == 2 and not re.search(r'[A-RT-Za-rt-z]{3}', texto):
                for i, p in enumerate(nums):
                    salida.append(dict(c, columna=c['columna'] * 100 + i, texto=p))
            else:
                salida.append(dict(c, columna=c['columna'] * 100))
    return salida


def valores_fila(cs, roles):
    valores = {rol: cs[col] for rol, col in roles.items() if col in cs}
    # Cantidad y descripción pueden compartir celda, incluso el encabezado.
    for c in cs.values():
        if c['columna'] == roles.get('cantidad') and re.search(r'[A-Za-z]{3}', c['texto'] or ''):
            m = re.match(r'\s*(\d+(?:[,.]\d{2})?)\s+(.+)', c['texto'])
            if m:
                valores['cantidad'] = dict(c, texto=m[1], numero=Decimal(m[1].replace(',', '.')))
                valores['descripcion'] = c  # el literal original se conserva entero
    for rol in ('precio', 'subtotal'):
        if rol in valores and decimal_argentino(valores[rol]['texto']) is None:
            nums = importes(valores[rol]['texto'])
            if len(nums) == 1:
                valores[rol] = dict(valores[rol], texto=nums[0])
    return valores


def valor_celda(celda):
    if celda is None:
        return None
    return celda.get('numero', decimal_argentino(celda['texto']))


def filas_por_cuenta(celdas):
    """Dos filas concordantes prueban la estructura de una planilla sin título.

    La cantidad tiene una unidad expresa o está unida a una descripción como
    decimal con dos posiciones. No se ensayan códigos sueltos como cantidades.
    Se exige una única cuenta y al menos una cantidad distinta de uno.
    """
    candidatas = {}
    for fila in {c['fila'] for c in celdas if not c['es_encabezado']}:
        cs = [c for c in celdas if c['fila'] == fila and not c['es_encabezado']]
        descs = [c for c in cs if re.search(r'[A-Za-zÁ-ÿ]{3}', c['texto'] or '')]
        if not descs:
            continue
        desc = max(descs, key=lambda c: sum(ch.isalpha() for ch in c['texto']))
        cantidades = []
        for c in cs:
            # Cantidad decimal al principio de una descripción (facturas).
            m = re.match(r'\s*(\d+[.,]\d{2})\s+[A-Za-zÁ-ÿ]', c['texto'] or '')
            if m:
                cantidades.append(dict(c, texto=m[1], numero=Decimal(m[1].replace(',', '.'))))
            # Cantidad contigua a una unidad, en columna fundida por OCR.
            for m in re.finditer(r'(?:^|[|\s])(\d+)\s*[| ]+\s*(?:un\.?|unid\.?|unidad|m\.?|kg|lt)\b', normalizar(c['texto'])):
                cantidades.append(dict(c, texto=m[1]))
        if any(normalizar(c['texto']).strip('. ') in _UNIDADES for c in cs):
            cantidades += [c for c in cs if re.fullmatch(r'\d+', (c['texto'] or '').strip())]
        montos = [dict(c, texto=t) for c in cs for t in importes(c['texto'])]
        opciones = []
        for q in cantidades:
            cantidad = valor_celda(q)
            for i, p in enumerate(montos):
                for s in montos[i+1:]:
                    if cantidad and cantidad * decimal_argentino(p['texto']) == decimal_argentino(s['texto']):
                        opciones.append({'descripcion': desc, 'cantidad': q, 'precio': p, 'subtotal': s})
        if len(opciones) == 1:
            candidatas[fila] = opciones[0]
    if len(candidatas) >= 2 and any(valor_celda(v['cantidad']) != 1 for v in candidatas.values()):
        return candidatas
    return {}


def _ancla_palabras(ps, pagina):
    return {'pagina_nro': pagina, 'celdas': None, 'campo_id': None,
            'region': {'x0': min(p.x0 for p in ps), 'y0': min(p.y0 for p in ps),
                       'x1': max(p.x1 for p in ps), 'y1': max(p.y1 for p in ps)}}


def _contexto(cx, doc, paginas, *, crear_entidades=True):
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
                  'ARS' if re.search(r'\bars\b|\bpesos\b', norm) else
                  # En un comprobante argentino «$» a secas es pesos; el dólar se escribe
                  # U$S o USD y ya se descartó arriba. Sin esto, una factura que no dice
                  # «pesos» queda sin moneda, y un renglón sin moneda nunca llega a
                  # comparable fuerte (docs/contrataciones-y-precios.md §3).
                  'ARS' if '$' in texto else None)
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
        elif re.search(r'\bfactura\s*"?\s*([abc])\b', norm):
            # La letra de la factura lo dice sin ambigüedad: la A discrimina el IVA y la
            # B y la C lo llevan incluido en el precio. Es de la normativa, no del legajo,
            # y muchas veces es lo único que una factura dice sobre su tratamiento.
            letra = re.search(r'\bfactura\s*"?\s*([abc])\b', norm)[1]
            tratamiento = 'discriminado' if letra == 'a' else 'incluido'
            tratamientos.add(tratamiento)
            salida['iva'] = tratamiento
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
            if crear_entidades:
                cx.execute("""INSERT INTO entidad(clase,clave_fuerte,nombre,nombre_norm,creado_en)
                              VALUES (?,?,?,?,?) ON CONFLICT(clase,clave_fuerte) DO NOTHING""",
                           (m['clase'], m['clave_fuerte'], nombre or cuit,
                            en.normalizar(nombre or cuit), ahora()))
            entidad = cx.execute(
                'SELECT id FROM entidad WHERE clase=? AND clave_fuerte=?',
                (m['clase'], m['clave_fuerte'])).fetchone()
            if entidad:
                salida['proveedor_id'] = entidad[0]
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
            originales = [dict(c) for c in cx.execute('SELECT * FROM tabla_celda WHERE tabla_id=? ORDER BY fila,columna', (t['id'],))]
            cuentas = filas_por_cuenta(originales)
            doc = docs.get(t['documento_id'])
            if not doc:
                doc = next((d for d in docs.values() if d['pagina_desde'] <= t['pagina_nro'] <= d['pagina_hasta']), None)
            if not doc and cuentas:
                # Una planilla comprobable también es una pieza fuente aunque la
                # segmentación no haya reconocido su tipo. No se inventa su etapa.
                clave = f"{sha}:{t['pagina_nro']}"
                orden = cx.execute('SELECT coalesce(max(orden),0)+1 FROM documento WHERE sha256=?', (sha,)).fetchone()[0]
                cx.execute("""INSERT OR IGNORE INTO documento(sha256,orden,clave,pagina_desde,pagina_hasta,tipo,perfil,estado)
                              VALUES (?,?,?,?,?,'desconocido','sin_perfil','segmentado')""",
                           (sha, orden, clave, t['pagina_nro'], t['pagina_nro']))
                doc = dict(cx.execute('SELECT * FROM documento WHERE clave=?', (clave,)).fetchone())
                docs[doc['id']] = doc
                cx.execute('UPDATE tabla SET documento_id=? WHERE id=?', (doc['id'], t['id']))
            if not doc or (doc['tipo'] not in cl.TIPOS_CON_PRECIO | {'pedido', 'remito'} and not cuentas):
                continue
            if doc['id'] not in contextos:
                contextos[doc['id']] = _contexto(cx, doc, paginas)
            contexto = contextos[doc['id']]
            celdas = celdas_ocr(originales)
            roles = columnas(celdas, paginas.get(t['pagina_nro']), t)
            if 'descripcion' not in roles and 'cantidad' not in roles and not cuentas:
                continue
            for fila in sorted({c['fila'] for c in celdas if not c['es_encabezado']}):
                cs = {c['columna']: c for c in celdas if c['fila'] == fila and not c['es_encabezado']}
                valores = valores_fila(cs, roles)
                if fila in cuentas and not {'precio', 'subtotal'} <= valores.keys():
                    valores.update(cuentas[fila])
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
                cant, precio, sub = (valor_celda(valores.get(k)) for k in ('cantidad', 'precio', 'subtotal'))
                if cant is None and precio is None and sub is None:
                    continue
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
                         etapa=('apertura' if doc['tipo'] == 'acta_apertura' else
                                doc['tipo'] if doc['tipo'] in cl.TIPOS_CON_PRECIO | {'pedido', 'remito'} else 'otro'),
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

