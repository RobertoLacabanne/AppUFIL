"""Línea de comandos. `python3 -m ufil.cli --ayuda` para ver todo."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import config, db
from . import capa0_ingesta as c0
from . import capa1_texto as c1
from . import capa2_extraccion as c2
from . import capa3_identidad as c3
from . import capa4_analisis as c4
from . import evaluacion as ev


def _cx(a):
    return db.abrir(Path(a.base) if a.base else None)


def cmd_ingerir(a):
    cx = _cx(a)
    r = c0.ingerir(cx, Path(a.carpeta), lote=a.lote, legajo=a.legajo, acta=a.acta,
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
    extra = (f" · ¡{tot['documentos'] - len(shas)} contratos de más!"
             if tot["documentos"] > len(shas) else "")
    print(f"\r  {len(shas)} archivos -> {tot['documentos']} contratos{extra} · "
          f"campos {tot['campos']} · conflictos {tot['conflictos']} · "
          f"a revisar {tot['a_revisar']} · sin perfil {tot['sin_perfil']}")
    return 0


def cmd_identidad(a):
    cx = _cx(a)
    print("  " + json.dumps(c3.resolver(cx), ensure_ascii=False))
    print("  " + json.dumps(c3.proponer_fusiones(cx), ensure_ascii=False))
    rep = c3.detectar_contratos_repetidos(cx)
    if rep:
        print(f"  ¡ojo! {rep} contrato(s) aparecen más de una vez: "
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
    hechos = c7.exportar(cx, destino, consultas=a.consulta or None)
    for h in hechos:
        print(f"  {h}")
    return 0


def cmd_diagnostico(a):
    """Chequeo del entorno. Se corre el primer día, antes de cargar nada."""
    from . import diagnostico
    salidas = diagnostico.correr()
    print(diagnostico.informe_texto(salidas))
    return 0 if diagnostico.resumen(salidas)["puede_trabajar"] else 1


def cmd_respaldo(a):
    """Copia consistente de la base, sin parar el sistema."""
    from . import respaldo
    cx = _cx(a)
    r = respaldo.resumen(cx)
    try:
        destino = respaldo.hacer(cx, Path(a.destino))
    except FileExistsError as e:
        # Un respaldo no pisa a otro, pero eso se avisa en castellano y no con una
        # excepción de Python en la cara de quien lo corrió.
        print(f"  No se hizo el respaldo: {e}")
        print("  Elegí otro nombre, o borrá el que está si ya no lo necesitás.")
        return 1
    except OSError as e:
        print(f"  No se pudo escribir el respaldo en {a.destino}: {e}")
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


def cmd_demo(a):
    """
    Deja la aplicación lista para mostrar, de un solo comando.

    Genera el corpus sintético si falta, lo procesa entero, marca la base como
    DEMOSTRACIÓN —para que la interfaz avise en toda pantalla que ninguno de esos
    contratos es real— y levanta el servidor.
    """
    import subprocess
    from . import capa5_interpretacion as c5
    from . import busqueda
    from . import capa0_ingesta as c0

    corpus = Path(a.corpus)
    if not list(corpus.glob("*.pdf")):
        print(f"── generando el corpus sintético en {corpus}")
        subprocess.run([sys.executable, str(config.RAIZ / "herramientas" / "generar_fixtures.py"),
                        "--destino", str(corpus), "--cantidad", str(a.cantidad)], check=True)

    base = Path(a.base) if a.base else config.BASE
    if a.limpiar:
        for suf in ("", "-wal", "-shm"):
            Path(str(base) + suf).unlink(missing_ok=True)
        print("── base anterior borrada")

    cx = db.abrir(base)
    db.ajuste(cx, "demostracion", "1")
    print("── la base queda marcada como DEMOSTRACIÓN")

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
    servidor.servir(base, a.puerto, "0.0.0.0" if getattr(a, "red", False) else a.host)
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
    sub = p.add_subparsers(dest="cmd", required=True)

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
    s.set_defaults(func=cmd_exportar)

    s = sub.add_parser("respaldo", help="copia de la base; lo único que no se regenera")
    s.add_argument("destino", nargs="?", default="datos/respaldos",
                   help="carpeta o archivo destino (por omisión datos/respaldos/)")
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
    s.set_defaults(func=cmd_demo)

    s = sub.add_parser("piloto", help="corre todo de punta a punta")
    s.add_argument("carpeta"); s.add_argument("--lote", default="piloto")
    s.add_argument("--perfil", default="auto",
                   help="perfil de formulario; «auto» prueba todos y elige el que mejor calce")
    s.add_argument("--referencia"); s.add_argument("--informe")
    s.add_argument("--vlm", action="store_true")
    s.set_defaults(func=cmd_piloto)

    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
