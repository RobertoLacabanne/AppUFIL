"""
Trae a esta máquina una copia de trabajo del legajo real de una instancia desplegada.

Sólo lee de la instancia: el respaldo sale de `/descargar?que=respaldo` (API de backup de
SQLite, no toca la base) y las fojas de `/pagina`, que sirve los renders ya hechos sin
generar nada. Nunca escribe en la instancia salvo el archivo de respaldo que esa función
deja en la carpeta de respaldos del legajo, que es lo que hace cada vez que alguien
aprieta «Descargar respaldo».

Lo traído va FUERA de cualquier repositorio (por omisión C:\\Users\\rober\\AppUFIL-corpus-real)
y no se versiona nunca:

    produccion-original/respaldo.sqlite   intacto, sólo lectura, con su SHA-256
    derivados/<sha[:2]>/<sha>/pNNNN.png   las fojas, compartidas por las copias
    originales/<sha[:2]>/<sha>.pdf        los originales que se consigan aparte
    <agente>/ufil.sqlite                  una copia de trabajo por agente, con las rutas
                                          de renders y originales apuntando acá

Uso:
    python herramientas/traer_corpus_real.py --url https://<instancia> \\
        [--legajo SLUG] [--clave CLAVE] [--agentes claude codex gemini] [--hilos 3]
    python herramientas/traer_corpus_real.py --solo-rutas   # re-apunta copias existentes
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import http.cookiejar
import json
import shutil
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

DESTINO = Path(r"C:\Users\rober\AppUFIL-corpus-real")


def _cliente(url: str, clave: str | None):
    jarra = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jarra))
    if clave:
        pedido = urllib.request.Request(f"{url}/api/acceso", json.dumps({"clave": clave}).encode(),
                                        {"Content-Type": "application/json"})
        op.open(pedido, timeout=60).read()
    return op


def _bajar(op, url: str, legajo: str, destino: Path, intentos=4) -> int:
    for i in range(intentos):
        try:
            pedido = urllib.request.Request(url, headers={"Cookie": f"ufil_legajo={legajo}"})
            with op.open(pedido, timeout=180) as r:
                datos = r.read()
            temporal = destino.with_suffix(destino.suffix + ".parcial")
            temporal.parent.mkdir(parents=True, exist_ok=True)
            temporal.write_bytes(datos)
            temporal.replace(destino)
            return len(datos)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return -1
            time.sleep(2 * (i + 1))
        except OSError:
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"no se pudo bajar {url}")


def _ro(ruta: Path) -> sqlite3.Connection:
    cx = sqlite3.connect(ruta.resolve().as_uri() + "?mode=ro", uri=True)
    cx.row_factory = sqlite3.Row
    return cx


def traer_respaldo(op, url, legajo, base: Path) -> Path:
    destino = base / "produccion-original" / "respaldo.sqlite"
    if destino.exists():
        print(f"respaldo ya presente: {destino}")
        return destino
    n = _bajar(op, f"{url}/descargar?que=respaldo", legajo, destino)
    cx = _ro(destino)
    ok = cx.execute("PRAGMA integrity_check").fetchone()[0]
    cx.close()
    if ok != "ok":
        raise SystemExit(f"el respaldo no pasa integrity_check: {ok}")
    sha = hashlib.sha256(destino.read_bytes()).hexdigest()
    (destino.parent / "sha256.txt").write_text(f"{sha}  respaldo.sqlite\n")
    destino.chmod(0o444)
    print(f"respaldo: {n / 2**20:.1f} MB, integrity ok, sha256 {sha[:16]}")
    return destino


def traer_fojas(op, url, legajo, respaldo: Path, base: Path, hilos: int):
    cx = _ro(respaldo)
    pedidos = [(r["sha256"], r["nro"]) for r in cx.execute(
        "SELECT sha256, nro FROM pagina WHERE render IS NOT NULL ORDER BY sha256, nro")]
    cx.close()
    faltan = [(s, n) for s, n in pedidos
              if not (base / "derivados" / s[:2] / s / f"p{n:04d}.png").exists()]
    print(f"fojas con render: {len(pedidos)}; ya estaban: {len(pedidos) - len(faltan)}; "
          f"a traer: {len(faltan)} con {hilos} hilos")
    hechas = bytes_ = sin = 0
    t0 = time.monotonic()
    with cf.ThreadPoolExecutor(hilos) as ex:
        futuros = {ex.submit(_bajar, op, f"{url}/pagina?sha={s}&nro={n}", legajo,
                             base / "derivados" / s[:2] / s / f"p{n:04d}.png"): (s, n)
                   for s, n in faltan}
        for f in cf.as_completed(futuros):
            n = f.result()
            hechas += 1
            if n < 0:
                sin += 1
            else:
                bytes_ += n
            if hechas % 100 == 0:
                print(f"  {hechas}/{len(faltan)} · {bytes_ / 2**20:.0f} MB · "
                      f"{time.monotonic() - t0:.0f} s", flush=True)
    print(f"fojas traídas: {hechas - sin}, sin render en el servidor: {sin}, "
          f"{bytes_ / 2**20:.0f} MB")


def preparar_copias(respaldo: Path, base: Path, agentes: list[str], solo_rutas=False):
    for agente in agentes:
        copia = base / agente / "ufil.sqlite"
        if not solo_rutas or not copia.exists():
            copia.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(respaldo, copia)
            copia.chmod(0o644)
        cx = sqlite3.connect(copia)
        renders = originales = 0
        for r in cx.execute("SELECT id, sha256, nro FROM pagina").fetchall():
            png = base / "derivados" / r[1][:2] / r[1] / f"p{r[2]:04d}.png"
            if png.exists():
                cx.execute("UPDATE pagina SET render=? WHERE id=?", (str(png), r[0]))
                renders += 1
        for (sha,) in cx.execute("SELECT sha256 FROM archivo").fetchall():
            pdf = base / "originales" / sha[:2] / f"{sha}.pdf"
            if pdf.exists():
                cx.execute("UPDATE archivo SET ruta_original=? WHERE sha256=?", (str(pdf), sha))
                originales += 1
        cx.commit()
        cx.close()
        print(f"copia {agente}: {renders} fojas y {originales} originales apuntando a {base}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--url", help="dirección de la instancia; obligatoria salvo con --solo-rutas")
    ap.add_argument("--legajo")
    ap.add_argument("--clave")
    ap.add_argument("--destino", type=Path, default=DESTINO)
    ap.add_argument("--agentes", nargs="+", default=["claude", "codex", "gemini"])
    ap.add_argument("--hilos", type=int, default=3)
    ap.add_argument("--solo-rutas", action="store_true")
    a = ap.parse_args(argv)
    respaldo = a.destino / "produccion-original" / "respaldo.sqlite"
    if not a.solo_rutas:
        if not a.url:
            ap.error("falta --url")
        op = _cliente(a.url, a.clave)
        legajo = a.legajo or json.loads(op.open(f"{a.url}/api/legajos", timeout=60).read())[
            "legajos"][0]["slug"]
        respaldo = traer_respaldo(op, a.url, legajo, a.destino)
        traer_fojas(op, a.url, legajo, respaldo, a.destino, a.hilos)
    preparar_copias(respaldo, a.destino, a.agentes, solo_rutas=a.solo_rutas)


if __name__ == "__main__":
    sys.exit(main())
