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
        """SELECT a.sha256 FROM archivo a
            WHERE (SELECT COUNT(*) FROM pagina p JOIN lectura l ON l.pagina_id=p.id
                    WHERE p.sha256=a.sha256) = 0 ORDER BY a.nombre""")]
    t0 = time.perf_counter()
    for i, sha in enumerate(pend, 1):
        c1.leer_documento(cx, sha, con_vlm=a.vlm)
        print(f"\r  leídos {i}/{len(pend)}", end="", flush=True)
    seg = time.perf_counter() - t0
    print(f"\r  leídos {len(pend)}/{len(pend)} en {seg:.1f}s"
          f"{f' ({seg/len(pend):.2f}s por documento)' if pend else ''}")
    return 0


def cmd_extraer(a):
    cx = _cx(a)
    shas = [f["sha256"] for f in cx.execute("SELECT sha256 FROM archivo ORDER BY nombre")]
    tot = {"campos": 0, "conflictos": 0, "a_revisar": 0, "sin_perfil": 0}
    for i, sha in enumerate(shas, 1):
        r = c2.extraer_documento(cx, sha, a.perfil)
        if r["documento_id"] is None:
            tot["sin_perfil"] += 1
        for k in ("campos", "conflictos", "a_revisar"):
            tot[k] += r[k]
        print(f"\r  extraídos {i}/{len(shas)}", end="", flush=True)
    print(f"\r  extraídos {len(shas)}/{len(shas)} · campos {tot['campos']} · "
          f"conflictos {tot['conflictos']} · a revisar {tot['a_revisar']} · "
          f"sin perfil {tot['sin_perfil']}")
    return 0


def cmd_identidad(a):
    cx = _cx(a)
    print("  " + json.dumps(c3.resolver(cx), ensure_ascii=False))
    print("  " + json.dumps(c3.proponer_fusiones(cx), ensure_ascii=False))
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


def cmd_servir(a):
    from . import servidor
    servidor.servir(Path(a.base) if a.base else None, a.puerto, a.host)
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
    s.add_argument("--perfil", default="contrato_legislatura")
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

    s = sub.add_parser("verificar", help="chequea las invariantes del pliego")
    s.add_argument("--completo", action="store_true",
                   help="rehashea TODOS los originales, no sólo los más postergados")
    s.set_defaults(func=cmd_verificar)

    s = sub.add_parser("servir", help="Capa 6: interfaz web local")
    s.add_argument("--puerto", type=int, default=8713)
    s.add_argument("--host", default="127.0.0.1")
    s.set_defaults(func=cmd_servir)

    s = sub.add_parser("piloto", help="corre todo de punta a punta")
    s.add_argument("carpeta"); s.add_argument("--lote", default="piloto")
    s.add_argument("--perfil", default="contrato_legislatura")
    s.add_argument("--referencia"); s.add_argument("--informe")
    s.add_argument("--vlm", action="store_true")
    s.set_defaults(func=cmd_piloto)

    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
