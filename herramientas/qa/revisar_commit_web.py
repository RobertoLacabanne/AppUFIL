"""
Control rápido de un commit que toca la interfaz, antes de integrarlo.

    python herramientas/qa/revisar_commit_web.py <repo> <desde> [<hasta>]

Para cada commit entre `desde` y `hasta` (por defecto HEAD) dice si `app.js` parsea,
si aparecieron entidades HTML de acentos (`&oacute;` y compañía: señal de que alguien
reescribió el archivo entero y lo re-codificó) y cuántas líneas cambió en `app.js` y
`estilo.css`. Un commit que dice «integrar una vista» y cambia setecientas líneas no
integró una vista.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

ENTIDADES = re.compile(r"&(?:[aeiou]acute|ntilde|uuml|middot|rarr|laquo|raquo);", re.I)


def git(repo, *args) -> str:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                          encoding="utf-8").stdout


def main() -> int:
    repo, desde = sys.argv[1], sys.argv[2]
    hasta = sys.argv[3] if len(sys.argv) > 3 else "HEAD"
    commits = git(repo, "rev-list", "--reverse", f"{desde}..{hasta}").split()
    malo = 0
    for c in commits:
        titulo = git(repo, "log", "-1", "--format=%s", c).strip()
        js = git(repo, "show", f"{c}:ufil/web/app.js")
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write(js)
        parsea = subprocess.run(["node", "--check", f.name], capture_output=True).returncode == 0
        Path(f.name).unlink()
        entidades = len(ENTIDADES.findall(js))
        stat = git(repo, "diff", "--numstat", f"{c}~1", c, "--", "ufil/web/app.js", "ufil/web/estilo.css")
        lineas = sum(int(a) + int(b) for a, b, _ in (l.split("\t") for l in stat.splitlines()) if a.isdigit())
        problemas = []
        if not parsea:
            problemas.append("app.js NO PARSEA")
        if entidades:
            problemas.append(f"{entidades} entidades HTML de acentos")
        if lineas > 600:
            problemas.append(f"{lineas} líneas cambiadas: ¿reescribió el archivo?")
        malo += bool(problemas)
        print(f"{c[:7]} {'MAL' if problemas else 'ok '} {lineas:5d} líneas  {titulo[:60]}"
              + ("  <- " + "; ".join(problemas) if problemas else ""))
    return 1 if malo else 0


if __name__ == "__main__":
    sys.exit(main())
