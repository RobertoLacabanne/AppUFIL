"""Línea de comandos. `python3 -m ufil.cli --ayuda` para ver todo."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import config, db, legajos
from . import capa0_ingesta as c0
from . import capa1_texto as c1
from . import capa2_extraccion as c2
from . import capa3_identidad as c3
from . import capa4_analisis as c4
from . import evaluacion as ev
from .castellano import miles, plural


def _cx(a):
    return db.abrir(Path(a.base) if a.base else None)


def _elegir_legajo(a) -> None:
    """
    Deja activo el legajo pedido con `--legajo`, para todo lo que venga después.

    Se valida contra el registro: un número mal tipeado tiene que ser un error a la
    vista y no un legajo nuevo creado en silencio, que es lo que pasaría si dejáramos
    que la ruta se armara sola con lo que vino escrito.
    """
    slug = (getattr(a, "legajo_activo", None) or "").strip()
    disponibles = legajos.slugs()
    if not slug:
        # Sin legajo se trabaja sobre la base suelta, que casi siempre está vacía. Si hay
        # legajos cargados, decirlo evita la peor confusión posible acá: creer que no hay
        # datos cuando lo que falta es decir de qué causa.
        if disponibles and a.cmd not in ("legajos", "diagnostico"):
            n = len(disponibles)
            print(f"  (sin --legajo: se usa la base suelta. "
                  f"Hay {n} legajo{'s' if n != 1 else ''} "
                  f"cargado{'s' if n != 1 else ''}; mirá `ufil legajos`)")
        return
    if slug not in disponibles:
        # También se acepta el número tal cual figura en la carátula: quien escribe el
        # comando conoce «87.933», no el nombre de la carpeta.
        from .legajos import _slug
        if _slug(slug) in disponibles:
            slug = _slug(slug)
        else:
            hay = ", ".join(sorted(disponibles)) or "ninguno todavía"
            raise SystemExit(f"no existe el legajo «{slug}». Hay: {hay}\n"
                             f"Se crea con: ufil legajos crear <numero> <caratula>")
    config.activar_legajo(slug)
    # Y también como omisión del proceso: `servir` levanta hilos nuevos por cada
    # petición, y un valor sólo de este hilo no llegaría hasta ellos.
    config.fijar_legajo_por_omision(slug)


def cmd_legajos(a):
    if a.accion == "crear":
        # Los errores acá salen en castellano y no como excepción de Python: esto lo
        # corre gente de la fiscalía, no quien escribió el programa.
        try:
            l = legajos.crear(a.numero or "", a.caratula or "", fiscal=a.fiscal)
        except legajos.LegajoDuplicado as e:
            print(f"  {e}")
            print("  Si querés trabajar sobre ese, usá: "
                  f"ufil --legajo {legajos._slug(a.numero or '')} <comando>")
            return 1
        except ValueError as e:
            print(f"  Falta un dato: {e}")
            print('  Se usa así: ufil legajos crear "87.933" "Contratos Legislatura"')
            return 1
        print(f"  legajo {l.numero} · {l.caratula}")
        print(f"  carpeta: {l.carpeta}")
        print(f"  para trabajar sobre él: ufil --legajo {l.slug} <comando>")
        return 0
    filas = legajos.listar()
    if not filas:
        print("  todavía no hay ningún legajo.")
        print("  Se crea con: ufil legajos crear \"87.933\" \"Contratos Legislatura\"")
        return 0
    print(f"  {'LEGAJO':<16} {'DOCS':>5} {'PEND':>5}  CARÁTULA")
    for f in filas:
        marca = "  " if f["estado"] == "activo" else "· "
        print(f"{marca}{f['numero']:<16} {f['documentos']:>5} {f['pendientes']:>5}  "
              f"{f['caratula'][:44]}")
    return 0


def cmd_ingerir(a):
    cx = _cx(a)
    # El `--legajo` de la ingesta es un dato de procedencia (de qué legajo salió el
    # secuestro). Si no lo dicen, es el legajo sobre el que se está trabajando.
    r = c0.ingerir(cx, Path(a.carpeta), lote=a.lote,
                   legajo=a.legajo or config.legajo_activo(), acta=a.acta,
                   domicilio=a.domicilio, dispositivo=a.dispositivo,
                   fecha_secuestro=a.fecha_secuestro, operador=a.operador)
    print(f"nuevos {r.nuevos} · duplicados exactos {r.duplicados} · "
          f"fallidos {r.fallidos} · páginas {r.paginas}")
    return 0


def cmd_leer(a):
    cx = _cx(a)
    pend = [f["sha256"] for f in cx.execute(
"""SELECT DISTINCT a.sha256 FROM archivo a
             JOIN pagina p ON p.sha256 = a.sha256
            WHERE NOT EXISTS (SELECT 1 FROM lectura l WHERE l.pagina_id = p.id)
            ORDER BY a.nombre""")]
    if not pend:
        print("  no hay nada sin leer")
        return 0
    t0 = time.perf_counter()

    def avance(hechas, total):
        print(f"\r  páginas {hechas}/{total}", end="", flush=True)

    r = c1.leer_lote(cx, pend, con_vlm=a.vlm, avance=avance)
    seg = time.perf_counter() - t0
    fall = f" · {r['fallidas']} con error" if r["fallidas"] else ""
    print(f"\r  {len(pend)} archivos · {r['paginas']} páginas en {seg:.1f}s "
          f"({seg/max(r['paginas'],1):.2f}s por página, {config.NUCLEOS_OCR} en paralelo){fall}")
    return 0


def cmd_extraer(a):
    cx = _cx(a)
    shas = [f["sha256"] for f in cx.execute("SELECT sha256 FROM archivo ORDER BY nombre")]
    tot = {"documentos": 0, "campos": 0, "conflictos": 0, "a_revisar": 0, "sin_perfil": 0}
    for i, sha in enumerate(shas, 1):
        r = c2.extraer_documento(cx, sha, a.perfil)
        for k in tot:
            tot[k] += r.get(k, 0)
        print(f"\r  extraídos {i}/{len(shas)}", end="", flush=True)
    # Que de un PDF salgan varios contratos es lo NORMAL con material real: un
    # expediente trae la carátula, tres o cuatro contratos, el decreto y las facturas.
    # El mensaje decía «¡contratos de más!», que se leía como un error y no lo era.
    print(f"\r  {plural(len(shas), 'archivo', 'archivos')} -> "
          f"{plural(tot['documentos'], 'documento', 'documentos')} · "
          f"campos {tot['campos']} · conflictos {tot['conflictos']} · "
          f"a revisar {tot['a_revisar']} · sin perfil {tot['sin_perfil']}")
    return 0


def cmd_identidad(a):
    cx = _cx(a)
    print("  " + json.dumps(c3.resolver(cx), ensure_ascii=False))
    print("  " + json.dumps(c3.proponer_fusiones(cx), ensure_ascii=False))
    rep = c3.detectar_contratos_repetidos(cx)
    if rep:
        print(f"  ¡ojo! {plural(rep, 'contrato aparece', 'contratos aparecen')} "
              f"más de una vez: "
              f"ver la consulta 08_contratos_repetidos")
    return 0


def cmd_analizar(a):
    cx = _cx(a)
    if not a.consulta:
        for c in c4.catalogo():
            print(f"  {c['id']:<28} {c['descripcion'][:78]}")
        return 0
    r = c4.correr(cx, a.consulta)
    if a.json:
        print(json.dumps(r["filas"], ensure_ascii=False, indent=2, default=str))
        return 0
    if not r["filas"]:
        print(f"  ({r['id']}: sin filas)")
        return 0
    cols = r["columnas"]
    anchos = [max(len(c), *(len(str(f[c] if f[c] is not None else "")) for f in r["filas"]))
              for c in cols]
    anchos = [min(w, 30) for w in anchos]
    print("  " + "  ".join(c[:w].ljust(w) for c, w in zip(cols, anchos)))
    print("  " + "  ".join("-" * w for w in anchos))
    for f in r["filas"][: a.limite]:
        print("  " + "  ".join(str(f[c] if f[c] is not None else "")[:w].ljust(w)
                               for c, w in zip(cols, anchos)))
    print(f"  ({r['n']} filas · {r['ruta']})")
    return 0


def cmd_evaluar(a):
    cx = _cx(a)
    res = ev.evaluar(cx, Path(a.referencia))
    print(ev.informe_texto(res))
    if a.detalle and res["detalle"]:
        print("\nDETALLE (errores y omisiones)")
        print("-" * 92)
        for d in res["detalle"][: a.detalle]:
            print(f"  {d['archivo']:<24}{d['campo']:<14}{d['clase']:<17}"
                  f"esperado={str(d['esperado'])[:22]:<24}obtenido={str(d['obtenido'])[:22]}")
    if a.salida:
        Path(a.salida).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\ninforme completo en {a.salida}")
    return 0 if res["aprueba"] else 1


def cmd_exportar(a):
    from . import capa7_export as c7
    cx = _cx(a)
    destino = Path(a.destino)
    hechos = c7.exportar(cx, destino, consultas=a.consulta or None,
                         membrete=not a.sin_membrete)
    for h in hechos:
        print(f"  {h}")
    return 0


def cmd_diagnostico(a):
    """Chequeo del entorno. Se corre el primer día, antes de cargar nada."""
    from . import diagnostico
    salidas = diagnostico.correr()
    print(diagnostico.informe_texto(salidas))
    return 0 if diagnostico.resumen(salidas)["puede_trabajar"] else 1


def cmd_manuscrita(a):
    """
    Le pide a un modelo de visión una PROPUESTA para cada campo manuscrito pendiente.

    No llena ningún campo: deja la propuesta al lado del recorte para que una persona
    la confirme en la cola. Ver ufil/lector_manuscrito.py.
    """
    from . import config, lector_manuscrito as lm
    cx = _cx(a)
    if not lm.encendido():
        print("  El lector de manuscrita está apagado.")
        print("  Se enciende con UFIL_VISION=1. Ojo: con eso, el recorte de la foja")
        print("  sale de esta máquina hacia el servicio. Apuntando UFIL_VISION_URL a un")
        print("  modelo local, no sale nada. Ver docs/09-manuscrita.md.")
        return 1

    pendientes = cx.execute("""
        SELECT c.id, c.nombre, c.pagina_nro, c.x0, c.y0, c.x1, c.y1,
               p.render, p.render_escala
          FROM campo c
          JOIN documento d ON d.id = c.documento_id
          JOIN pagina p ON p.sha256 = d.sha256 AND p.nro = c.pagina_nro
         WHERE c.nulo_motivo = 'manuscrito' AND c.x0 IS NOT NULL
           AND p.render IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM propuesta q WHERE q.campo_id = c.id)
         ORDER BY c.id""").fetchall()
    if not pendientes:
        print("  No hay campos manuscritos esperando propuesta.")
        return 0

    print(f"  {plural(len(pendientes), 'campo manuscrito', 'campos manuscritos')}. "
          f"Modelo: {lm.MODELO}")
    leidos = ilegibles = fallados = 0
    for i, f in enumerate(pendientes, 1):
        try:
            png = lm.recorte_a_png(Path(f["render"]),
                                   f["render_escala"] or config.ESCALA_RENDER,
                                   (f["x0"], f["y0"], f["x1"], f["y1"]))
            prop = lm.leer_recorte(png, que_campo=f"el campo «{f['nombre']}»")
            lm.guardar_propuesta(cx, f["id"], prop)
            if prop.ilegible:
                ilegibles += 1
            else:
                leidos += 1
        except lm.VisionNoDisponible as e:
            print(f"\n  {e}")
            return 1
        except Exception as e:                       # noqa: BLE001
            fallados += 1
            cx.execute("""INSERT INTO excepcion (clase, detalle, creado_en)
                          VALUES ('vision_fallo',?,?)""",
                       (f"campo {f['id']}: {type(e).__name__}: {e}", db.ahora()))
            cx.commit()
        print(f"\r  {i}/{len(pendientes)}", end="", flush=True)
    print(f"\r  {plural(len(pendientes), 'campo', 'campos')}: {leidos} con propuesta, "
          f"{ilegibles} que el modelo declaró ilegibles, {fallados} con error.")
    print("  Ninguno se guardó como dato: están en la cola, al lado del recorte,")
    print("  esperando que una persona los confirme.")
    return 0


def cmd_respaldo(a):
    """Copia consistente de la base, sin parar el sistema."""
    from . import respaldo
    cx = _cx(a)
    r = respaldo.resumen(cx)
    # Sin destino explícito, la carpeta de respaldos DEL LEGAJO: dos causas guardando
    # en el mismo lugar terminan con archivos del mismo nombre pisándose.
    carpeta = Path(a.destino) if a.destino else Path(config.RESPALDOS)
    try:
        destino = respaldo.hacer(cx, carpeta)
    except FileExistsError as e:
        # Un respaldo no pisa a otro, pero eso se avisa en castellano y no con una
        # excepción de Python en la cara de quien lo corrió.
        print(f"  No se hizo el respaldo: {e}")
        print("  Elegí otro nombre, o borrá el que está si ya no lo necesitás.")
        return 1
    except OSError as e:
        print(f"  No se pudo escribir el respaldo en {carpeta}: {e}")
        print("  Revisá que la carpeta exista y que haya lugar y permiso para escribir.")
        return 1
    print(respaldo.texto(destino, r))
    return 0


def cmd_verificar(a):
    from . import verificacion
    cx = _cx(a)
    if a.completo:
        r = verificacion.verificar_integridad(cx, completo=True)
        print(f"  integridad: {r['revisados']} originales rehasheados, {r['ok']} intactos")
        fallas = r["fallas"] + [f for f in verificacion.correr(cx) if "ORIGINAL" not in f]
    else:
        fallas = verificacion.correr(cx)
        r = cx.execute("""SELECT COUNT(*) c, MIN(verificado_en) v FROM integridad""").fetchone()
        tot = cx.execute("SELECT COUNT(*) FROM archivo").fetchone()[0]
        print(f"  integridad: {r['c']} de {tot} originales verificados alguna vez"
              f"{'; el más viejo, ' + str(r['v'])[:16].replace('T', ' ') if r['v'] else ''}")
        if r["c"] < tot:
            print(f"  faltan {tot - r['c']}: se van cubriendo solos corriendo `verificar` "
                  f"otra vez, o de una con --completo")
    for f in fallas:
        print(f"  ✗ {f}")
    if not fallas:
        print("  todas las invariantes se cumplen")
    return 1 if fallas else 0


# El legajo donde vive la demostración. Uno solo, siempre el mismo, y nunca uno real.
LEGAJO_DEMO = "demostracion"


def cmd_demo(a):
    """
    Deja la aplicación lista para mostrar, de un solo comando.

    Los contratos inventados van A SU PROPIO LEGAJO, siempre. Nunca a uno de verdad.

    Antes escribían en la base que estuviera activa, y `--limpiar` borraba esa base sin
    preguntar: `ufil --legajo 87.933 demo --limpiar` borraba el legajo 87.933 entero,
    con las revisiones hechas a mano adentro, que es lo único que no se puede volver a
    generar. Ahora la demostración tiene su carpeta y su base, y no hay forma de que
    toque otra: si le pasan un legajo real, se planta.
    """
    import subprocess
    from . import permanencia
    from . import capa5_interpretacion as c5
    from . import busqueda
    from . import capa0_ingesta as c0

    # ── La demostración no se levanta en un servidor de verdad ──────────────
    #
    # `demo` genera contratos inventados y los carga. Está pensada para mostrarle el
    # sistema a alguien en una notebook, y no tiene nada que hacer en una instalación
    # donde se trabaja una causa.
    #
    # Pasó, y varias veces: quedó puesta como comando de arranque de un servicio de
    # nube. Cada despliegue la volvía a cargar, aparecía «DEMOSTRACIÓN» con cincuenta
    # contratos inventados encima del trabajo de verdad, y nadie entendía de dónde
    # salía. Peor: quien ve la app un lunes a la mañana no distingue de un vistazo si
    # esos cincuenta contratos son de la causa o del generador.
    #
    # Así que en un contenedor no arranca la demostración: arranca el servidor, que es
    # lo que corresponde, y lo dice. No se planta con un error, porque un servicio que
    # no levanta deja a la fiscalía sin herramienta; hace lo correcto y avisa.
    if permanencia.en_contenedor() and not getattr(a, "igual_en_la_nube", False):
        print("  Esto corre en un contenedor, así que NO se carga la demostración.")
        print("  Los contratos inventados no tienen nada que hacer en una instalación")
        print("  donde se trabaja una causa: aparecen mezclados con el material real y")
        print("  no hay manera de distinguirlos de un vistazo.")
        print()
        print("  Se levanta el servidor normal. Si de verdad querés la demostración acá,")
        print("  agregá --igual-en-la-nube.")
        print()
        from . import servidor
        servidor.servir(None, a.puerto,
                        "0.0.0.0" if getattr(a, "red", False) else a.host)
        return 0

    activo = config.legajo_activo()
    if activo and activo != LEGAJO_DEMO:
        print(f"  No: «{activo}» es un legajo de trabajo y la demostración carga "
              f"contratos inventados.")
        print(f"  Corré `ufil demo` sin --legajo: va a su propio legajo, aparte.")
        return 1
    if a.base:
        print("  No: `demo` no acepta --base. Los contratos inventados van a su propio")
        print("  legajo, para que no haya forma de mezclarlos con material de una causa.")
        return 1

    if LEGAJO_DEMO not in legajos.slugs():
        legajos.crear("DEMOSTRACIÓN", "Contratos inventados para probar el sistema",
                      fiscal=None, creado_por="demo")
    config.activar_legajo(LEGAJO_DEMO)
    config.fijar_legajo_por_omision(LEGAJO_DEMO)
    base = Path(config.BASE)

    if a.limpiar:
        # Sólo puede borrar la base de la demostración, y sólo si la base es realmente
        # de la demostración. El chequeo es redundante con el de arriba: cuesta dos
        # líneas y lo que hay del otro lado es un borrado sin vuelta atrás.
        if base.exists():
            cx = db.abrir(base)
            marcada = db.ajuste(cx, "demostracion") == "1"
            n = cx.execute("SELECT COUNT(*) FROM archivo").fetchone()[0]
            cx.close()
            if n and not marcada:
                print(f"  No se borra: {base} tiene "
                      f"{plural(n, 'archivo', 'archivos')} y NO está marcada")
                print("  como demostración. Si de verdad querés borrarla, hacelo a mano.")
                return 1
        for suf in ("", "-wal", "-shm"):
            Path(str(base) + suf).unlink(missing_ok=True)
        print("── base de la demostración borrada")

    # El corpus se genera DESPUÉS de los chequeos. Generarlo antes eran cincuenta
    # contratos y veinte segundos de trabajo para después plantarse y no usarlos.
    corpus = Path(a.corpus)
    if not list(corpus.glob("*.pdf")):
        print(f"── generando el corpus sintético en {corpus}")
        subprocess.run([sys.executable, str(config.RAIZ / "herramientas" / "generar_fixtures.py"),
                        "--destino", str(corpus), "--cantidad", str(a.cantidad)], check=True)

    cx = db.abrir(base)
    db.ajuste(cx, "demostracion", "1")
    print(f"── legajo «DEMOSTRACIÓN», marcado como tal, en {base.parent}")

    print("── ingesta")
    r = c0.ingerir(cx, corpus, lote="demostracion", operador="demo",
                   legajo="(corpus de prueba)")
    print(f"   nuevos {r.nuevos} · duplicados {r.duplicados} · páginas {r.paginas}")

    faltan = [f["sha256"] for f in cx.execute(
        """SELECT DISTINCT a.sha256 FROM archivo a
             JOIN pagina p ON p.sha256 = a.sha256
            WHERE NOT EXISTS (SELECT 1 FROM lectura l WHERE l.pagina_id = p.id)
            ORDER BY a.nombre""")]
    if faltan:
        paginas = cx.execute("""SELECT COUNT(*) FROM pagina p
                                 WHERE NOT EXISTS (SELECT 1 FROM lectura l
                                                    WHERE l.pagina_id = p.id)""").fetchone()[0]
        print(f"── lectura de {paginas} páginas en {config.NUCLEOS_OCR} núcleos "
              f"(tarda ~{int(paginas * 0.65)}s)")
        c1.leer_lote(cx, faltan,
                     avance=lambda h, t: print(f"\r   {h}/{t}", end="", flush=True))
        print()

    print("── extracción")
    for sha in [f["sha256"] for f in cx.execute("SELECT sha256 FROM archivo ORDER BY nombre")]:
        c2.extraer_documento(cx, sha, a.perfil)
    print("── identidad, índice y patrones")
    c3.resolver(cx); c3.proponer_fusiones(cx)
    busqueda.reindexar(cx); c5.regenerar(cx)
    cx.close()

    print()
    print("  Listo para mostrar.")
    print(f"  Referencia para medir: {corpus / 'referencia.csv'}")
    print()
    from . import servidor
    # `None` y no `base`: el servidor resuelve la base por el legajo activo, que acá es
    # el de la demostración. Pasarle la ruta a mano lo dejaría clavado ahí aunque
    # alguien cambie de legajo desde la pantalla.
    servidor.servir(None, a.puerto, "0.0.0.0" if getattr(a, "red", False) else a.host)
    return 0


def cmd_servir(a):
    from . import servidor
    # `--red` es la forma legible de decir «escuchá en todas las placas». Existe para
    # que nadie tenga que acordarse de qué significa 0.0.0.0, y para que quede
    # explícito en el comando que se está abriendo el sistema a la red.
    host = "0.0.0.0" if getattr(a, "red", False) else a.host
    servidor.servir(Path(a.base) if a.base else None, a.puerto, host)
    return 0


def cmd_piloto(a):
    """Todo el piloto de punta a punta, como pide la Fase 1."""
    class N: pass
    for paso, fn, args in [
        ("INGESTA", cmd_ingerir, dict(carpeta=a.carpeta, lote=a.lote, legajo=None, acta=None,
                                      domicilio=None, dispositivo=None, fecha_secuestro=None,
                                      operador=None)),
        ("LECTURA", cmd_leer, dict(vlm=a.vlm)),
        ("EXTRACCIÓN", cmd_extraer, dict(perfil=a.perfil)),
        ("IDENTIDAD", cmd_identidad, dict()),
    ]:
        n = N(); n.base = a.base
        for k, v in args.items():
            setattr(n, k, v)
        print(f"\n── {paso} " + "─" * (66 - len(paso)))
        fn(n)
    print("\n── ANÁLISIS " + "─" * 62)
    for cid in ("05_cobertura", "01_superposicion", "04_fechas_imposibles"):
        n = N(); n.base = a.base; n.consulta = cid; n.json = False; n.limite = 8
        print(f"\n  # {cid}")
        cmd_analizar(n)
    if a.referencia:
        print("\n── MEDICIÓN " + "─" * 62)
        n = N(); n.base = a.base; n.referencia = a.referencia; n.detalle = 12; n.salida = a.informe
        return cmd_evaluar(n)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="ufil", description="Análisis documental offline — UFIL Paraná")
    p.add_argument("--base", help="ruta del archivo SQLite (por defecto datos/ufil.sqlite)")
    p.add_argument("--legajo", dest="legajo_activo", metavar="NUMERO",
                   help="sobre qué legajo trabajar. Cada legajo tiene su propia base y "
                        "sus propios derivados: nada se cruza entre uno y otro")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("legajos", help="listar o crear legajos")
    s.add_argument("accion", nargs="?", default="listar", choices=("listar", "crear"))
    s.add_argument("numero", nargs="?"); s.add_argument("caratula", nargs="?")
    s.add_argument("--fiscal")
    s.set_defaults(func=cmd_legajos)

    s = sub.add_parser("ingerir", help="Capa 0: recorre un lote en solo lectura")
    s.add_argument("carpeta"); s.add_argument("--lote", required=True)
    for o in ("legajo", "acta", "domicilio", "dispositivo", "fecha-secuestro", "operador"):
        s.add_argument(f"--{o}", dest=o.replace("-", "_"))
    s.set_defaults(func=cmd_ingerir)

    s = sub.add_parser("leer", help="Capa 1: texto con coordenadas, por todas las rutas")
    s.add_argument("--vlm", action="store_true", help="incluir la ruta del modelo de visión")
    s.set_defaults(func=cmd_leer)

    s = sub.add_parser("extraer", help="Capa 2: campos anclados, con doble lectura")
    s.add_argument("--perfil", default="auto",
                   help="perfil de formulario; «auto» prueba todos y elige el que mejor calce")
    s.set_defaults(func=cmd_extraer)

    s = sub.add_parser("identidad", help="Capa 3: personas por clave fuerte + propuestas")
    s.set_defaults(func=cmd_identidad)

    s = sub.add_parser("analizar", help="Capa 4: corre una consulta .sql versionada")
    s.add_argument("consulta", nargs="?"); s.add_argument("--json", action="store_true")
    s.add_argument("--limite", type=int, default=40)
    s.set_defaults(func=cmd_analizar)

    s = sub.add_parser("evaluar", help="§12: mide contra la transcripción manual")
    s.add_argument("referencia"); s.add_argument("--detalle", type=int, default=0)
    s.add_argument("--salida")
    s.set_defaults(func=cmd_evaluar)

    s = sub.add_parser("exportar", help="Capa 7: .xlsx y .rtf con cita de archivo y foja")
    s.add_argument("destino"); s.add_argument("--consulta", action="append")
    s.add_argument("--sin-membrete", action="store_true",
                   help="sin el encabezado del organismo (borrador interno)")
    s.set_defaults(func=cmd_exportar)

    s = sub.add_parser("manuscrita",
                       help="propone valores para los campos escritos a mano (modelo de visión)")
    s.set_defaults(func=cmd_manuscrita)

    s = sub.add_parser("respaldo", help="copia de la base; lo único que no se regenera")
    s.add_argument("destino", nargs="?",
                   help="carpeta o archivo destino (por omisión, la carpeta de respaldos "
                        "del legajo)")
    s.set_defaults(func=cmd_respaldo)

    s = sub.add_parser("diagnostico", help="¿está todo lo que hace falta para trabajar?")
    s.set_defaults(func=cmd_diagnostico)

    s = sub.add_parser("verificar", help="chequea las invariantes del pliego")
    s.add_argument("--completo", action="store_true",
                   help="rehashea TODOS los originales, no sólo los más postergados")
    s.set_defaults(func=cmd_verificar)

    s = sub.add_parser("servir", help="Capa 6: interfaz web local")
    s.add_argument("--puerto", type=int, default=8713)
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--red", action="store_true",
                   help="dejarlo visible para otros equipos de la red (celulares). "
                        "Genera una clave de acceso y la muestra al arrancar")
    s.set_defaults(func=cmd_servir)

    s = sub.add_parser("demo", help="deja la app cargada y lista para mostrar, y la levanta")
    s.add_argument("--corpus", default="datos/corpus-sintetico")
    s.add_argument("--cantidad", type=int, default=50)
    s.add_argument("--perfil", default="auto",
                   help="perfil de formulario; «auto» prueba todos y elige el que mejor calce")
    s.add_argument("--puerto", type=int, default=8713)
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--red", action="store_true",
                   help="dejarlo visible para otros equipos de la red (celulares)")
    s.add_argument("--limpiar", action="store_true", help="borrar la base y empezar de cero")
    s.add_argument("--igual-en-la-nube", action="store_true",
                   dest="igual_en_la_nube",
                   help="cargar la demostración aunque esto corra en un contenedor. "
                        "No usarlo en una instalación donde se trabaja una causa: los "
                        "contratos inventados quedan mezclados con el material real")
    s.set_defaults(func=cmd_demo)

    s = sub.add_parser("piloto", help="corre todo de punta a punta")
    s.add_argument("carpeta"); s.add_argument("--lote", default="piloto")
    s.add_argument("--perfil", default="auto",
                   help="perfil de formulario; «auto» prueba todos y elige el que mejor calce")
    s.add_argument("--referencia"); s.add_argument("--informe")
    s.add_argument("--vlm", action="store_true")
    s.set_defaults(func=cmd_piloto)

    a = p.parse_args(argv)
    _elegir_legajo(a)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
