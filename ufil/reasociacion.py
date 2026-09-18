"""Resolución explícita de revisiones cuyo anclaje dejó de ser seguro."""
from . import aplicar_revision
from .db import ahora


def _revision(cx, sha256, orden, campo):
    r = cx.execute("SELECT * FROM revision_humana WHERE sha256=? AND orden=? AND campo=?",
                   (sha256, orden, campo)).fetchone()
    if not r:
        raise KeyError("revisión inexistente")
    return dict(r)


def candidatas(cx, sha256, orden, campo) -> list[dict]:
    """Ordena indicios; ninguna pieza queda elegida automáticamente."""
    r = _revision(cx, sha256, orden, campo)
    piezas = []
    for fila in cx.execute("""SELECT d.id AS documento_id, d.orden, d.tipo,
            d.pagina_desde, d.pagina_hasta, c.id AS campo_id,
            c.valor_literal AS valor_actual, c.estado AS estado_actual
        FROM documento d LEFT JOIN campo c ON c.documento_id=d.id AND c.nombre=?
        WHERE d.sha256=? ORDER BY d.orden""", (campo, sha256)):
        p = dict(fila)
        contiene = (r['ancla_pagina'] is not None and p['pagina_desde'] is not None
                    and p['pagina_hasta'] is not None
                    and p['pagina_desde'] <= r['ancla_pagina'] <= p['pagina_hasta'])
        mismo = r['ancla_tipo'] is not None and p['tipo'] == r['ancla_tipo']
        p['tiene_el_campo'] = p.pop('campo_id') is not None
        razones = []
        if contiene:
            razones.append('Contiene la foja anclada')
        if mismo:
            razones.append('Mismo tipo de pieza que al revisar')
        p['por_que'] = '; '.join(razones) or 'Otra pieza del mismo archivo'
        piezas.append(((not contiene, not mismo, p['orden']), p))
    return [p for _, p in sorted(piezas, key=lambda par: par[0])]


def pendientes(cx) -> list[dict]:
    """Conserva una entrada por decisión, con todas las piezas actuales."""
    filas = cx.execute("""SELECT r.*, a.nombre AS archivo FROM revision_humana r
        LEFT JOIN archivo a ON a.sha256=r.sha256
        WHERE r.estado='requiere_reasociacion' ORDER BY r.cuando, r.sha256, r.orden, r.campo""").fetchall()
    return [dict(r, candidatas=candidatas(cx, r['sha256'], r['orden'], r['campo']))
            for r in filas]


class _SinCommit:
    """aplicar confirma por sí sola; la resolución debe confirmarse entera."""
    def __init__(self, cx):
        self.cx = cx

    def execute(self, *args):
        return self.cx.execute(*args)

    def commit(self):
        pass


def resolver(cx, sha256, orden, campo, accion, quien, *, documento_id=None) -> dict:
    """Guarda la resolución y su rastro juntos, sin pisar decisiones ajenas."""
    if accion not in ('reasociar', 'descartar', 'pendiente'):
        raise ValueError('acción de reasociación desconocida')
    if not isinstance(quien, str) or not quien.strip():
        raise ValueError('hace falta indicar quién resuelve')
    if not isinstance(sha256, str) or not isinstance(campo, str) or type(orden) is not int:
        raise ValueError('hace falta identificar el archivo, el orden y el campo')
    if accion == 'reasociar' and type(documento_id) is not int:
        raise ValueError('elegí una pieza para reasociar')
    propia = not cx.in_transaction
    if propia:
        cx.execute('BEGIN IMMEDIATE')
    cx.execute('SAVEPOINT resolver_revision')
    try:
        r = _revision(cx, sha256, orden, campo)
        if r['estado'] != 'requiere_reasociacion':
            raise ValueError('esta revisión ya fue resuelta; volvé a cargar la lista')
        estado = r['estado']
        nuevo_orden, campo_id = orden, None
        if accion == 'reasociar':
            if r['accion'] not in ('verificar', 'corregir', 'ilegible', 'ausente', 'ambiguo'):
                raise ValueError('la revisión conservada no tiene una decisión aplicable')
            d = cx.execute('SELECT * FROM documento WHERE id=? AND sha256=?',
                           (documento_id, sha256)).fetchone()
            if not d:
                raise ValueError('la pieza elegida no pertenece al archivo de la revisión')
            nuevo_orden = d['orden']
            if nuevo_orden != orden and cx.execute(
                    'SELECT 1 FROM revision_humana WHERE sha256=? AND orden=? AND campo=?',
                    (sha256, nuevo_orden, campo)).fetchone():
                raise ValueError('la pieza destino ya tiene una revisión para ese campo; no se puede pisar')
            c = cx.execute('SELECT * FROM campo WHERE documento_id=? AND nombre=?',
                           (documento_id, campo)).fetchone()
            if not c:
                raise ValueError('la pieza todavía no tiene ese campo; dejá la revisión pendiente hasta que se extraiga')
            campo_id = c['id']
            if c['revisado_por']:
                raise ValueError('el campo destino ya tiene una decisión humana; no se puede pisar')
            aplicar_revision.aplicar(_SinCommit(cx), campo_id, r['accion'], r['valor'],
                                     quien.strip(), registrar=False,
                                     observacion=f'Reasociación de la revisión del orden {orden}, hecha por {r["quien"]} el {r["cuando"]}')
            c = cx.execute('SELECT * FROM campo WHERE id=?', (campo_id,)).fetchone()
            estado = 'vigente'
            cx.execute("""UPDATE revision_humana SET orden=?, ancla_pagina=?,
                ancla_x0=?, ancla_y0=?, ancla_x1=?, ancla_y1=?,
                ancla_desde=?, ancla_hasta=?, ancla_tipo=?, estado='vigente', motivo=NULL
                WHERE sha256=? AND orden=? AND campo=?""",
                (nuevo_orden, c['pagina_nro'], c['x0'], c['y0'], c['x1'], c['y1'],
                 d['pagina_desde'], d['pagina_hasta'], d['tipo'], sha256, orden, campo))
        elif accion == 'descartar':
            estado = 'descartada'
            cx.execute("UPDATE revision_humana SET estado=? WHERE sha256=? AND orden=? AND campo=?",
                       (estado, sha256, orden, campo))
        cx.execute("""INSERT INTO auditoria (campo_id,sha256,orden,campo_nombre,accion,
            valor_anterior,valor_nuevo,motivo_anterior,motivo_nuevo,estado_anterior,
            estado_nuevo,observacion,quien,cuando) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (campo_id, sha256, orden, campo, accion, r['valor'], r['valor'], r['motivo'],
             None if estado == 'vigente' else r['motivo'], r['estado'], estado,
             f'Revisión de {r["quien"]} del {r["cuando"]}. Orden de origen: {orden}. Orden de destino: {nuevo_orden}.',
             quien.strip(), ahora()))
        cx.execute('RELEASE resolver_revision')
        if propia:
            cx.commit()
        return {'ok': True, 'estado': estado, 'orden': nuevo_orden, 'documento_id': documento_id if accion == 'reasociar' else None}
    except Exception:
        cx.execute('ROLLBACK TO resolver_revision')
        cx.execute('RELEASE resolver_revision')
        if propia:
            cx.rollback()
        raise
