"""
Actualizar lo que ya está cargado, sin volver a subirlo y sin repetir lo caro.

Qué resuelve
------------
El acervo crece durante años y el sistema aprende cosas nuevas en el medio. Cuando
aparece un tipo documental, mejora un extractor o cambia una regla, los PDF que ya
están adentro tienen que poder aprovecharlo. Hasta acá la única forma era volver a
correr todo, y «todo» incluye el OCR, que sobre un acervo grande son horas.

Este módulo hace tres cosas:

  1. **Dice qué quedó viejo y qué no**, comparando el sello de cada resultado con el
     vigente (ver ufil/versiones.py). Se puede mirar sin ejecutar nada: es lo que la
     pantalla muestra ANTES de que alguien apriete el botón.
  2. **Invalida en cascada pero sólo hacia adelante.** Si cambia la clasificación se
     rehace lo que se apoya en ella; el OCR no se toca. Si cambia el OCR, ahí sí se
     vuelve a leer, y sólo las fojas que hagan falta.
  3. **Reaplica el trabajo de las personas por anclaje, no por posición**, y cuando no
     puede estar seguro no lo aplica: lo marca para que lo mire alguien.

Lo que este módulo NO puede hacer todavía, y conviene decirlo
-------------------------------------------------------------
Cinco etapas —clasificación, segmentación, cotejo, extracción y normalización— se
contabilizan por separado pero se EJECUTAN juntas: hoy las hace una sola función,
`capa2_extraccion.extraer_documento`, en una sola pasada por archivo. Así que si
cualquiera de las cinco queda vieja, se rehacen las cinco para ese archivo.

No es una limitación grave —las cinco juntas son segundos por archivo, contra horas del
OCR— pero es una diferencia real entre lo que el sistema informa y lo que ejecuta, y
está acá escrita en lugar de disimulada. Separarlas de verdad es trabajo de otro
incremento; la contabilidad ya está lista para cuando se separen.
"""
from __future__ import annotations

import sqlite3

from . import versiones as vs
from .db import ahora
from .exclusion import conexion

# Las etapas que se ejecutan por archivo, cada una por su cuenta. El orden importa:
# es el de dependencia, y es el orden en que se corren.
POR_ARCHIVO = ("clasificacion", "foliatura", "cotejo", "segmentacion",
               "tablas", "extraccion", "normalizacion", "renglones")

# La normalización sigue pegada a la extracción: la escribe `_guardar_contrato` en la
# misma pasada, porque normalizar es interpretar el literal que se acaba de leer y
# separarlo costaría volver a recorrer los campos para nada. Se contabiliza aparte
# —tiene su propia versión— pero se ejecuta con la extracción.
JUNTAS_POR_ARCHIVO = ("extraccion", "normalizacion")
# Las que valen para el legajo entero y no por archivo.
DE_LEGAJO = ("identidad", "indice", "entidades", "cronologia", "interpretacion")


# ────────────────────────────────────────────────────────────── el sello guardado ──
def sellar(cx: sqlite3.Connection, etapa: str, alcance_id: str = "", *,
           estado: str = vs.TERMINADO, origen: str | None = None,
           detalle: str | None = None) -> None:
    """Deja escrito que esta etapa produjo este resultado, con qué versión y config."""
    e = vs.etapa(etapa)
    cx.execute("""INSERT INTO resultado_etapa
                    (etapa, alcance, alcance_id, version, firma, estado, cuando,
                     origen, detalle)
                  VALUES (?,?,?,?,?,?,?,?,?)
                  ON CONFLICT(etapa, alcance, alcance_id) DO UPDATE SET
                     version=excluded.version, firma=excluded.firma,
                     estado=excluded.estado, cuando=excluded.cuando,
                     origen=excluded.origen, detalle=excluded.detalle""",
               (e.clave, e.alcance, str(alcance_id), e.version, e.firma(),
                estado, ahora(), origen, detalle))


def invalidar(cx: sqlite3.Connection, etapa: str) -> tuple[str, ...]:
    """
    Marca una etapa y TODO lo que depende de ella como desactualizado.

    Hacia adelante y nada más: invalidar la interpretación no puede costar un OCR.
    Devuelve las claves que quedaron marcadas, en orden.
    """
    tocadas = vs.cadena(etapa)
    for clave in tocadas:
        cx.execute("UPDATE resultado_etapa SET estado=? WHERE etapa=?",
                   (vs.DESACTUALIZADO, clave))
    cx.commit()
    return tocadas


def _sellos_guardados(cx: sqlite3.Connection, etapa: str) -> dict[str, tuple]:
    return {r["alcance_id"]: (r["version"], r["firma"], r["estado"], r["origen"])
            for r in cx.execute(
                "SELECT alcance_id, version, firma, estado, origen "
                "FROM resultado_etapa WHERE etapa=?", (etapa,))}


# ──────────────────────────────────────────── qué unidades tiene cada etapa hoy ──
def _unidades(cx: sqlite3.Connection, etapa: str) -> list[tuple[str, bool]]:
    """
    Las unidades de trabajo de una etapa y si YA tienen resultado en la base.

    `(alcance_id, hay_salida)`. `hay_salida` es lo que permite distinguir «nunca se
    hizo» de «se hizo antes de que existieran los sellos»: las dos no tienen fila en
    `resultado_etapa`, pero sólo una tiene el resultado guardado.
    """
    if etapa == "ingesta":
        return [(r["sha256"], True) for r in cx.execute("SELECT sha256 FROM archivo")]
    if etapa == "lectura":
        return [(str(r["id"]), bool(r["leida"])) for r in cx.execute(
            """SELECT p.id, EXISTS (SELECT 1 FROM lectura l WHERE l.pagina_id=p.id) AS leida
                 FROM pagina p""")]
    if etapa in ("tablas", "renglones"):
        # Hay salida si ya se buscaron tablas en el archivo. Que no haya ninguna no
        # dice que el archivo no tenga tablas: dice que todavía no se miró.
        return [(r["sha256"], bool(r["hay"])) for r in cx.execute(
            """SELECT a.sha256,
                      EXISTS (SELECT 1 FROM resultado_etapa re
                               WHERE re.etapa=? AND re.alcance_id = a.sha256) AS hay
                 FROM archivo a""", (etapa,))]
    if etapa == "foliatura":
        # Hay salida si alguna foja del archivo tiene foliatura anotada. Que no la
        # tenga NO dice que el papel no esté foliado: dice que todavía no se miró.
        return [(r["sha256"], bool(r["hay"])) for r in cx.execute(
            """SELECT a.sha256,
                      EXISTS (SELECT 1 FROM foliatura f JOIN pagina p ON p.id=f.pagina_id
                               WHERE p.sha256=a.sha256) AS hay
                 FROM archivo a""")]
    if etapa == "clasificacion":
        # La clasificación deja escrito qué es cada foja. Si ninguna foja del archivo
        # lo tiene, no se clasificó nunca.
        return [(r["sha256"], bool(r["hay"])) for r in cx.execute(
            """SELECT a.sha256,
                      EXISTS (SELECT 1 FROM pagina p WHERE p.sha256=a.sha256
                                AND p.clasificacion IS NOT NULL) AS hay
                 FROM archivo a""")]
    if etapa in POR_ARCHIVO:
        # Hay salida si el archivo ya produjo algún documento… o si se lo miró y no
        # produjo ninguno, que también es un resultado y está en `excepcion`. Un
        # archivo sin nada de lo dos no se procesó nunca.
        return [(r["sha256"], bool(r["hay"])) for r in cx.execute(
            """SELECT a.sha256,
                      (EXISTS (SELECT 1 FROM documento d WHERE d.sha256=a.sha256)
                    OR EXISTS (SELECT 1 FROM excepcion x WHERE x.sha256=a.sha256)) AS hay
                 FROM archivo a""")]
    if etapa == "identidad":
        return [("", bool(cx.execute(
            "SELECT EXISTS (SELECT 1 FROM documento_persona)").fetchone()[0]))]
    if etapa == "entidades":
        return [("", bool(cx.execute(
            "SELECT EXISTS (SELECT 1 FROM mencion)").fetchone()[0]))]
    if etapa == "cronologia":
        return [("", bool(cx.execute(
            "SELECT EXISTS (SELECT 1 FROM evento)").fetchone()[0]))]
    if etapa == "indice":
        return [("", bool(cx.execute(
            "SELECT EXISTS (SELECT 1 FROM pagina_texto)").fetchone()[0]))]
    if etapa == "interpretacion":
        return [("", bool(cx.execute(
            "SELECT EXISTS (SELECT 1 FROM interpretacion)").fetchone()[0]))]
    return []


def _estado_unidad(etapa: vs.Etapa, guardado, hay_salida: bool, firma_actual: str) -> str:
    """
    En qué estado está UNA unidad. Los cuatro que ve la pantalla.

      vigente        — la produjo el algoritmo que tengo ahora
      heredada       — ya estaba antes de que existieran los sellos; se la adopta
      desactualizada — la produjo otro algoritmo u otra configuración
      nunca          — todavía no se hizo

    Por qué `heredada` no vale para todas: adoptar significa creerle a un resultado sin
    poder comprobar quién lo produjo. Eso se justifica en dos casos —lo que no se puede
    rehacer y lo que cuesta horas— y en los dos la pantalla lo declara. En una etapa que
    cuesta segundos no hay nada que ahorrar, así que se la recalcula y se sabe con qué
    se hizo. Ver el campo `adopta` en ufil/versiones.py.
    """
    if guardado is None:
        if not hay_salida:
            return "nunca"
        return "heredada" if etapa.adopta else "desactualizada"
    version, firma, estado, _origen = guardado
    if estado in (vs.DESACTUALIZADO, vs.FALLIDO, vs.DETENIDO, vs.PARCIAL,
                  'corriendo', 'pendiente'):
        return "desactualizada"
    if version != etapa.version or firma != firma_actual:
        return "desactualizada"
    return "vigente"


def _motivo(etapa: vs.Etapa, guardado, estado: str, firma_actual: str) -> str | None:
    if estado == "vigente":
        return None
    if estado == "nunca":
        return "todavía no se hizo"
    if estado == "heredada":
        return ("ya estaba en la base antes de que se registrara con qué se hizo; "
                "se adopta lo leído en vez de volver a leerlo")
    if guardado is None:
        return "se hizo antes de que se registrara con qué versión"
    version, firma, _estado, _origen = guardado
    if version != etapa.version:
        return f"cambió el algoritmo (versión {version} → {etapa.version})"
    if firma != firma_actual:
        return "cambió la configuración con la que se hace"
    return "quedó marcada para rehacerse"


# ──────────────────────────────────────────────────────────────────── el plan ──
def plan(cx: sqlite3.Connection, *, forzar: tuple = ()) -> dict:
    """
    Qué quedó desactualizado y qué se va a reutilizar. **No escribe nada.**

    Es lo que se muestra antes de ejecutar, para que nadie apriete un botón sin saber si
    le va a costar dos horas de OCR. `forzar` son claves de etapa que se rehacen aunque
    estén vigentes.
    """
    forzar = tuple(forzar or ())
    for clave in forzar:
        vs.etapa(clave)                      # que reviente acá si no existe

    # Una etapa forzada arrastra a las que dependen de ella: rehacer la lectura sin
    # rehacer la extracción dejaría campos leídos de un texto que ya no está.
    arrastradas: set[str] = set()
    for clave in forzar:
        arrastradas.update(vs.cadena(clave))

    # Las firmas se calculan UNA vez por llamada. Cada una lee y resume archivos del
    # disco —el código fuente de la etapa, los perfiles— y `_estado_unidad` se llama una
    # vez por unidad: calcularla adentro del bucle hacía que mirar un legajo cargado
    # costara miles de lecturas de disco y se fuera de tiempo.
    firmas = {e.clave: e.firma() for e in vs.ETAPAS}
    etapas, archivos_viejos = [], {}
    desactualizadas: set[str] = set()
    # El plan y la ejecución deben aplicar la MISMA propagación por unidad.
    viejas_ejecucion = desactualizadas_por_etapa(cx, forzar=forzar)

    for e in vs.ETAPAS:
        unidades = _unidades(cx, e.clave)
        guardados = _sellos_guardados(cx, e.clave)
        # Si algo de lo que esta etapa necesita se va a rehacer, esta también.
        por_dependencia = any(d in desactualizadas for d in e.depende_de)

        vigentes, viejas, heredadas, nuevas = 0, 0, 0, 0
        for alcance_id, hay_salida in unidades:
            est = _estado_unidad(e, guardados.get(alcance_id), hay_salida, firmas[e.clave])
            if alcance_id in viejas_ejecucion.get(e.clave, ()) and est in ("vigente", "heredada"):
                est = "desactualizada"
            if est == "vigente":
                vigentes += 1
            elif est == "heredada":
                heredadas += 1
                vigentes += 1               # cuenta como aprovechable: no se rehace
            else:
                viejas += 1
                nuevas += 1 if est == "nunca" else 0
                if e.alcance == "archivo":
                    archivos_viejos.setdefault(alcance_id, []).append(e.clave)

        estado = ("vigente" if viejas == 0 and heredadas == 0 else
                  "heredada" if viejas == 0 else
                  "nunca" if nuevas and nuevas == viejas else "desactualizada")
        if viejas:
            desactualizadas.add(e.clave)

        motivo = None
        if viejas or heredadas:
            if e.clave in arrastradas:
                motivo = "se pidió rehacerla"
            elif por_dependencia and viejas:
                motivo = f"cambió algo de lo que depende ({', '.join(e.depende_de)})"
            else:
                # El motivo de la primera unidad que no está vigente: en la práctica
                # todas las de una etapa quedan viejas por lo mismo —cambió el
                # algoritmo o la configuración, que son de la etapa entera—.
                suelta = next(((a, est) for a, h in unidades
                               if (est := _estado_unidad(e, guardados.get(a), h,
                                                         firmas[e.clave])) != "vigente"),
                              None)
                if suelta:
                    motivo = _motivo(e, guardados.get(suelta[0]), suelta[1], firmas[e.clave])

        etapas.append({
            "clave": e.clave, "nombre": e.nombre, "estado": estado, "motivo": motivo,
            "alcance": e.alcance, "explica": e.explica,
            "vigentes": vigentes, "desactualizados": viejas, "total": len(unidades),
            "heredados": heredadas, "cuesta": "caro" if e.caro else "barato",
        })

    # ── qué se reutiliza y qué se recalcula, en las unidades que la gente entiende ──
    #
    # OJO con la cuenta fácil —fojas leídas menos fojas viejas—: miente. La lectura se
    # contabiliza por foja pero se EJECUTA por archivo, así que una sola foja vieja se
    # lleva puesto el archivo entero. Informar a sus vecinas como «reutilizadas» sería
    # decirle a alguien que no va a esperar un OCR que sí va a esperar, que es
    # exactamente lo que esta pantalla existe para que no pase.
    paginas_ocr_viejas, paginas_ocr_ok = _cuenta_de_fojas(
        cx, viejas_ejecucion.get("lectura", []))
    lecturas = cx.execute("SELECT COUNT(*) FROM lectura").fetchone()[0]

    # La lectura se cuenta y se ejecuta por foja; para la tabla de la
    # pantalla hay que saber de qué archivo es cada foja que quedó vieja.
    if paginas_ocr_viejas:
        for r in cx.execute("""SELECT DISTINCT p.sha256 FROM pagina p
                                LEFT JOIN resultado_etapa re
                                       ON re.etapa='lectura'
                                      AND re.alcance_id = CAST(p.id AS TEXT)
                                WHERE re.alcance_id IS NULL
                                   OR re.estado <> ?""", (vs.TERMINADO,)):
            archivos_viejos.setdefault(r["sha256"], []).append("lectura")

    detalle_archivos = []
    for sha, cs in sorted(archivos_viejos.items()):
        fila = cx.execute("SELECT nombre, paginas FROM archivo WHERE sha256=?",
                          (sha,)).fetchone()
        if not fila:
            continue
        detalle_archivos.append({"sha256": sha, "nombre": fila["nombre"],
                                 "paginas": fila["paginas"] or 0,
                                 "desactualizadas": sorted(set(cs))})

    revisiones = _resumen_revisiones(cx, va_a_resegmentar=("segmentacion" in desactualizadas))

    return {
        "vigente": not desactualizadas,
        "etapas": etapas,
        "reutiliza": {"paginas_ocr": paginas_ocr_ok, "lecturas": lecturas},
        "recalcula": {
            "paginas_ocr": paginas_ocr_viejas,
            "archivos": len(detalle_archivos),
            "documentos": cx.execute(
                "SELECT COUNT(*) FROM documento").fetchone()[0] if detalle_archivos else 0,
            "indice": "indice" in desactualizadas,
        },
        "archivos": detalle_archivos,
        "revisiones": revisiones,
    }


def _cuenta_de_fojas(cx: sqlite3.Connection, paginas_viejas: list) -> tuple[int, int]:
    """
    (fojas a releer, fojas que se reutilizan), contando por FOJA.

    Se relee exactamente lo que quedó viejo o nunca se leyó, y se reutiliza toda otra
    foja con lectura, aunque sea del mismo archivo. Es la cuenta que corresponde
    informarle a alguien que va a decidir si espera, y es la misma que ejecuta `aplicar`.
    """
    leidas = """SELECT COUNT(*) FROM pagina p
                 WHERE EXISTS (SELECT 1 FROM lectura l WHERE l.pagina_id = p.id)"""
    if not paginas_viejas:
        return 0, cx.execute(leidas).fetchone()[0]
    marcas = ','.join('?' * len(paginas_viejas))
    reutiliza = cx.execute(
        f"{leidas} AND CAST(p.id AS TEXT) NOT IN ({marcas})", paginas_viejas).fetchone()[0]
    return len(set(paginas_viejas)), reutiliza


def _resumen_revisiones(cx: sqlite3.Connection, *, va_a_resegmentar: bool) -> dict:
    """
    Qué va a pasar con el trabajo de las personas.

    `sin_ancla` son las revisiones viejas que no se pudieron anclar en la migración
    —la pieza ya no está, el campo se llama de otra forma—. Mientras la segmentación no
    cambie se reaplican como siempre. Si va a cambiar, no: se marcan para que las mire
    una persona, porque aplicarlas por posición es lo que pone una corrección en el
    documento equivocado.
    """
    total = cx.execute("SELECT COUNT(*) FROM revision_humana").fetchone()[0]
    marcadas = cx.execute(
        "SELECT COUNT(*) FROM revision_humana WHERE estado='requiere_reasociacion'"
    ).fetchone()[0]
    # Anclada a la foja o, si el campo no tiene valor, a la pieza: ver
    # `capa2_extraccion.reaplicar_revisiones`.
    sin_ancla = cx.execute(
        "SELECT COUNT(*) FROM revision_humana WHERE ancla_pagina IS NULL "
        "AND (ancla_desde IS NULL OR ancla_tipo IS NULL) "
        "AND estado <> 'requiere_reasociacion'").fetchone()[0]
    en_riesgo = sin_ancla if va_a_resegmentar else 0
    return {
        "total": total,
        "preservadas": total - marcadas - en_riesgo,
        "requieren_reasociacion": marcadas + en_riesgo,
        "sin_ancla": sin_ancla,
    }


def desactualizadas_por_etapa(cx: sqlite3.Connection, *, forzar: tuple = ()
                              ) -> dict[str, list[str]]:
    """
    Qué unidades hay que rehacer, por etapa, en orden de dependencia.

    Es la misma cuenta que hace `plan`, pero devolviendo los identificadores en vez de
    los totales: `plan` es para mostrar, esto es para ejecutar. Están separadas a
    propósito —mostrar no puede tener el efecto de nada— y las dos salen de
    `_estado_unidad`, para que no puedan decir cosas distintas.
    """
    arrastradas: set[str] = set()
    for clave in forzar or ():
        arrastradas.update(vs.cadena(vs.etapa(clave).clave))

    firmas = {e.clave: e.firma() for e in vs.ETAPAS}
    viejas: dict[str, list[str]] = {}
    con_cambio: set[str] = set()
    for e in vs.ETAPAS:
        guardados = _sellos_guardados(cx, e.clave)
        # La dependencia se mira POR UNIDAD cuando se puede, y no por etapa entera.
        #
        # Con un solo archivo roto en un lote de cincuenta, mirarlo por etapa marca la
        # etapa como cambiada y arrastra a los otros cuarenta y nueve: al reintentar se
        # rehace todo por culpa de uno. Que es exactamente el desperdicio que este
        # carril existe para evitar.
        #
        # Entre etapas del mismo alcance —las que trabajan por archivo— se compara
        # archivo contra archivo. Cuando los alcances no coinciden (la lectura es por
        # foja, la identidad es de todo el legajo) no hay unidad común que comparar, y
        # ahí sí vale la regla vieja: si cambió algo arriba, esta etapa se rehace entera.
        arrastre_global = any(
            d in con_cambio and vs.POR_CLAVE[d].alcance != e.alcance
            and not (vs.POR_CLAVE[d].alcance == 'pagina' and e.alcance == 'archivo')
            for d in e.depende_de)
        de_arriba = set()
        for d in e.depende_de:
            if d in con_cambio and vs.POR_CLAVE[d].alcance == e.alcance:
                de_arriba.update(viejas.get(d, ()))
            elif d in con_cambio and vs.POR_CLAVE[d].alcance == 'pagina' and e.alcance == 'archivo':
                paginas = set(viejas.get(d, ()))
                de_arriba.update(r['sha256'] for r in cx.execute('SELECT id,sha256 FROM pagina')
                                if str(r['id']) in paginas)
        pendientes = []
        for alcance_id, hay_salida in _unidades(cx, e.clave):
            est = _estado_unidad(e, guardados.get(alcance_id), hay_salida, firmas[e.clave])
            # Lo heredado NO se rehace por su cuenta: adoptarlo es justamente lo que
            # evita releer un acervo entero. Se rehace sólo si alguien lo pide o si
            # cambió algo de lo que depende.
            if (est in ("desactualizada", "nunca") or e.clave in arrastradas
                    or arrastre_global or alcance_id in de_arriba):
                pendientes.append(alcance_id)
        if pendientes:
            viejas[e.clave] = pendientes
            con_cambio.add(e.clave)
    return viejas


def _borrar_lecturas_de(cx: sqlite3.Connection, sha: str,
                        paginas: list[str] | None = None) -> int:
    """
    Saca las lecturas de un archivo —o sólo las de `paginas`— para que se vuelvan a leer.

    Con `paginas`, se tocan sólo esas fojas: las demás conservan su lectura, y
    `c1.leer_lote` lee únicamente las que quedan sin ninguna. Es lo que evita pagar el OCR
    de un archivo entero porque le faltaba una parte.

    No se tocan los documentos ni los campos: `campo.lectura_id` se pone en nulo y la
    extracción, que corre después porque depende de la lectura, los rehace con la
    lectura nueva. Borrar acá las piezas costaría saber cómo estaban repartidas antes,
    que es justamente lo que necesita `reaplicar_revisiones` para no mudar una
    corrección a la pieza equivocada.
    """
    if paginas is None:
        de_paginas, args = "SELECT id FROM pagina WHERE sha256 = ?", (sha,)
    else:
        if not paginas:
            return 0
        de_paginas = (f"SELECT id FROM pagina WHERE sha256 = ? AND CAST(id AS TEXT) IN "
                      f"({','.join('?' * len(paginas))})")
        args = (sha, *paginas)
    dentro = f"SELECT id FROM lectura WHERE pagina_id IN ({de_paginas})"
    cx.execute(f"UPDATE campo SET lectura_id=NULL WHERE lectura_id IN ({dentro})", args)
    cx.execute(f"UPDATE tabla_celda SET lectura_id=NULL WHERE lectura_id IN ({dentro})", args)
    cx.execute(f"DELETE FROM palabra WHERE lectura_id IN ({dentro})", args)
    n = cx.execute(f"DELETE FROM lectura WHERE id IN ({dentro})", args).rowcount
    cx.execute(f"""DELETE FROM resultado_etapa
                    WHERE etapa='lectura' AND alcance_id IN
                          (SELECT CAST(id AS TEXT) FROM ({de_paginas}))""", args)
    return n


@conexion
def aplicar(cx: sqlite3.Connection, *, forzar: tuple = (), perfil: str = "auto",
            con_vlm: bool = False, avance=None, seguir=None, fase=None) -> dict:
    """
    Rehace lo que quedó viejo, y solamente eso.

    `seguir` se consulta entre unidad y unidad: si devuelve False, se corta. Cortar es
    seguro porque cada unidad se sella apenas termina, así que al volver a correr se
    retoma donde iba. Es la misma garantía que ya daba la lectura por página, extendida
    a todas las etapas.

    `fase(nombre, total)` y `avance(hechas, total)` son para la barra de progreso.
    """
    from . import capa1_texto as c1
    from . import capa2_extraccion as c2
    from . import capa3_identidad as c3
    from . import capa5_interpretacion as c5
    from . import busqueda

    def _fase(nombre, total):
        if fase:
            fase(nombre, total)

    def _sigo() -> bool:
        return seguir() if seguir else True

    viejas = desactualizadas_por_etapa(cx, forzar=forzar)
    hecho = {"lectura_paginas": 0, "archivos": 0, "identidad": False, "indice": 0,
             "cronologia": 0, "menciones": 0, "relaciones": 0,
             "interpretacion": 0, "revisiones_reaplicadas": 0,
             "revisiones_a_reasociar": 0, "reutilizado_paginas_ocr": 0,
             "cortado": False, "errores": []}

    # La ingesta no se rehace: los originales son inmutables, así que volver a ingerirlos
    # no puede producir nada distinto. Se sella lo que hay —es lo que convierte una base
    # vieja en una base que sabe qué tiene— pero marcado como HEREDADO, porque eso es lo
    # que pasó: se adoptó lo que estaba, no se comprobó.
    sellados = _sellos_guardados(cx, "ingesta")
    for sha, _ in _unidades(cx, "ingesta"):
        sellar(cx, "ingesta", sha,
               origen=None if sha in sellados else vs.HEREDADO)
    cx.commit()

    # ── 1. Lectura. Lo caro. Sólo las fojas que de verdad quedaron viejas ──────
    paginas_viejas = viejas.get("lectura", [])
    shas_a_releer = [r["sha256"] for r in cx.execute(
        f"""SELECT DISTINCT sha256 FROM pagina
             WHERE CAST(id AS TEXT) IN ({','.join('?' * len(paginas_viejas))})""",
        paginas_viejas)] if paginas_viejas else []

    _, hecho["reutilizado_paginas_ocr"] = _cuenta_de_fojas(cx, paginas_viejas)

    if paginas_viejas:
        shas = shas_a_releer
        _fase("leyendo las fojas que quedaron viejas", len(paginas_viejas))
        # Por foja y no por archivo: un archivo cuyo procesamiento se cortó a la mitad
        # tiene cientos de fojas bien leídas, y releerlas es pagar horas de OCR por nada.
        # Medido en un legajo real: 750 fojas a releer donde faltaban 340.
        por_archivo: dict[str, list[str]] = {}
        for r in cx.execute(
                f"""SELECT sha256, CAST(id AS TEXT) AS id FROM pagina
                     WHERE CAST(id AS TEXT) IN ({','.join('?' * len(paginas_viejas))})""",
                paginas_viejas):
            por_archivo.setdefault(r["sha256"], []).append(r["id"])
        for sha in shas:
            if not _sigo():
                hecho["cortado"] = True
                break
            _borrar_lecturas_de(cx, sha, por_archivo.get(sha, []))
            cx.commit()
        if not hecho["cortado"]:
            try:
                r = c1.leer_lote(cx, shas, con_vlm=con_vlm, avance=avance, seguir=seguir)
                hecho["lectura_paginas"] = r.get("paginas", 0)
                if r.get("cortado"):
                    hecho["cortado"] = True
            except Exception as e:
                hecho["errores"].append({"etapa": "lectura", "detalle": f"{type(e).__name__}: {e}"})
        # Se sella foja por foja: la que se leyó queda vigente aunque el lote se haya
        # cortado en la de al lado. Eso es lo que hace que reanudar no repita.
        for r in cx.execute("""SELECT p.id FROM pagina p
                                WHERE EXISTS (SELECT 1 FROM lectura l
                                               WHERE l.pagina_id = p.id)"""):
            sellar(cx, "lectura", str(r["id"]))
        cx.commit()

    # ── 2. Las etapas por archivo, cada una por su cuenta ──────────────────────
    #
    # Acá está lo que se gana con haberlas separado: si lo único que cambió es la
    # extracción, **sólo corre la extracción**. No se vuelve a clasificar una foja que
    # nadie tocó ni se resegmenta un archivo que no cambió, que además de costar tiempo
    # obligaría a reasociar el trabajo que las personas ya hicieron.
    #
    # Las palabras de todas las lecturas se cargan UNA vez por archivo y se pasan a las
    # etapas que corran: es lo más caro de armar y no tiene sentido pagarlo cuatro veces.
    archivos = sorted({s for clave in POR_ARCHIVO for s in viejas.get(clave, [])})
    if archivos and not hecho["cortado"]:
        _fase("volviendo a mirar los archivos", len(archivos))
        for i, sha in enumerate(archivos, start=1):
            if not _sigo():
                hecho["cortado"] = True
                break
            pendientes = [c for c in POR_ARCHIVO if sha in viejas.get(c, ())]
            try:
                # El archivo entero se carga SOLO si hace falta.
                #
                # La extracción mira tramos de varias fojas y no puede trabajar de a
                # una, así que para ella se carga todo. Las demás etapas trabajan foja
                # por foja y leen solas, sin que la memoria crezca con el tamaño del
                # PDF: medido sobre un expediente de 400 fojas, 103 MB contra 1 MB.
                necesita_todo = ("extraccion" in pendientes
                                 or "normalizacion" in pendientes
                                 or "segmentacion" in pendientes)
                por_ruta = c2.lecturas_por_ruta(cx, sha) if necesita_todo else None
                if "clasificacion" in pendientes:
                    c2.clasificar_fojas(cx, sha, por_ruta=por_ruta)
                    sellar(cx, "clasificacion", sha)
                if "foliatura" in pendientes:
                    from . import foliatura as fol
                    fol.detectar_archivo(cx, sha, por_ruta=por_ruta)
                    sellar(cx, "foliatura", sha)
                if "cotejo" in pendientes:
                    c2.cotejar_numeros(cx, sha, por_ruta=por_ruta)
                    sellar(cx, "cotejo", sha)
                if "segmentacion" in pendientes:
                    seg = c2.segmentar_piezas(cx, sha, perfil, por_ruta=por_ruta)
                    sellar(cx, "segmentacion", sha,
                           detalle="sin perfil que aplique" if seg["sin_perfil"] else None)
                if "tablas" in pendientes:
                    from . import tablas as tb
                    tb.detectar_archivo(cx, sha, por_ruta=por_ruta)
                    sellar(cx, "tablas", sha)
                if "extraccion" in pendientes or "normalizacion" in pendientes:
                    r = c2.extraer_campos(cx, sha, perfil, por_ruta=por_ruta)
                    hecho["revisiones_reaplicadas"] += r.get("revisiones_reaplicadas", 0)
                    hecho["revisiones_a_reasociar"] += r.get("revisiones_a_reasociar", 0)
                    for clave in JUNTAS_POR_ARCHIVO:
                        sellar(cx, clave, sha)
                if "renglones" in pendientes:
                    from . import renglones
                    renglones.extraer_archivo(cx, sha, por_ruta=por_ruta)
                    sellar(cx, "renglones", sha)
                hecho["archivos"] += 1
            except Exception as e:
                detalle = f"{type(e).__name__}: {e}"
                hecho["errores"].append({"etapa": "archivo", "detalle": detalle})
                for clave in pendientes:
                    sellar(cx, clave, sha, estado=vs.FALLIDO, detalle=detalle)
            cx.commit()
            if avance:
                avance(i, len(archivos))

    # ── 3. Las del legajo entero ──────────────────────────────────────────────
    if "identidad" in viejas and not hecho["cortado"]:
        _fase("resolviendo identidades", 1)
        try:
            c3.resolver(cx)
            c3.proponer_fusiones(cx)
            c3.detectar_contratos_repetidos(cx)
            sellar(cx, "identidad")
            hecho["identidad"] = True
        except Exception as e:
            detalle = f"{type(e).__name__}: {e}"
            hecho["errores"].append({"etapa": "identidad", "detalle": detalle})
            sellar(cx, "identidad", estado=vs.FALLIDO, detalle=detalle)
        cx.commit()

    if "cronologia" in viejas and not hecho["cortado"]:
        _fase("armando la cronología", 1)
        try:
            from . import cronologia as cr
            hecho["cronologia"] = cr.poblar_desde_campos(cx)["eventos"]
            sellar(cx, "cronologia")
        except Exception as e:
            detalle = f"{type(e).__name__}: {e}"
            hecho["errores"].append({"etapa": "cronología", "detalle": detalle})
            sellar(cx, "cronologia", estado=vs.FALLIDO, detalle=detalle)
        cx.commit()

    if "indice" in viejas and not hecho["cortado"]:
        _fase("indexando para la búsqueda", 1)
        try:
            hecho["indice"] = busqueda.reindexar(cx)
            sellar(cx, "indice")
        except Exception as e:
            detalle = f"{type(e).__name__}: {e}"
            hecho["errores"].append({"etapa": "índice", "detalle": detalle})
            sellar(cx, "indice", estado=vs.FALLIDO, detalle=detalle)
        cx.commit()

    if "entidades" in viejas and not hecho["cortado"]:
        _fase("reconociendo menciones y relaciones", 1)
        try:
            from . import entidades as en
            from . import relaciones as rel
            hecho["menciones"] = en.poblar_desde_documentos(cx)["menciones"]
            hecho["relaciones"] = rel.proponer_por_comprobante(cx)
            sellar(cx, "entidades")
        except Exception as e:
            detalle = f"{type(e).__name__}: {e}"
            hecho["errores"].append({"etapa": "entidades", "detalle": detalle})
            sellar(cx, "entidades", estado=vs.FALLIDO, detalle=detalle)
        cx.commit()

    if "interpretacion" in viejas and not hecho["cortado"]:
        _fase("buscando patrones", 1)
        try:
            hecho["interpretacion"] = sum(c5.regenerar(cx).values())
            sellar(cx, "interpretacion")
        except Exception as e:
            detalle = f"{type(e).__name__}: {e}"
            hecho["errores"].append({"etapa": "interpretación", "detalle": detalle})
            sellar(cx, "interpretacion", estado=vs.FALLIDO, detalle=detalle)
        cx.commit()

    return hecho


def reasociaciones(cx: sqlite3.Connection) -> list[dict]:
    """
    Las revisiones humanas que quedaron sin pieza segura a la cual aplicarse.

    No se perdieron y no se aplicaron: están esperando que una persona diga a cuál
    corresponden. Es la única respuesta honesta cuando la segmentación cambió y el
    anclaje no alcanza para decidir solo.
    """
    return [{"sha256": r["sha256"], "archivo": r["nombre"] or r["sha256"][:12],
             "campo": r["campo"], "valor": r["valor"], "accion": r["accion"],
             "quien": r["quien"], "cuando": r["cuando"],
             "motivo": r["motivo"] or "la pieza a la que correspondía cambió",
             "ancla_pagina": r["ancla_pagina"], "orden_viejo": r["orden"]}
            for r in cx.execute("""
                SELECT r.*, a.nombre FROM revision_humana r
                  LEFT JOIN archivo a ON a.sha256 = r.sha256
                 WHERE r.estado = 'requiere_reasociacion'
                 ORDER BY a.nombre, r.ancla_pagina, r.campo""")]
