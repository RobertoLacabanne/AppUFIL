"""
Capa 7 — Exportación.

Tablas a .xlsx y cuerpo a .rtf con interlineado 1,5, justificado y cuerpo 11.

Cada afirmación exportada arrastra su archivo y su foja. Un informe que dice
"contrató en las dos cámaras" sin decir en qué papel lo leyó no sirve para
trabajar: obliga a rehacer la búsqueda a mano.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from . import capa4_analisis as c4

TINTA = "FF1B1D21"; SELLO = "FF23477A"; FILETE = "FFCFCBC2"; PAPEL2 = "FFF1EFEA"


def _hoja(wb: Workbook, res: dict) -> None:
    ws = wb.create_sheet(res["id"][:31])
    cols = res["columnas"]
    ws.append(cols)
    for c in range(1, len(cols) + 1):
        celda = ws.cell(row=1, column=c)
        celda.font = Font(bold=True, size=9, color="FFFFFFFF")
        celda.fill = PatternFill("solid", fgColor=SELLO)
        celda.alignment = Alignment(vertical="center", wrap_text=True)
    for fila in res["filas"]:
        ws.append([fila[c] for c in cols])

    fino = Side(style="thin", color=FILETE)
    for f in ws.iter_rows(min_row=2):
        for celda in f:
            celda.font = Font(size=10)
            celda.border = Border(bottom=fino)
            if isinstance(celda.value, (int, float)):
                celda.alignment = Alignment(horizontal="right")
                if "centavos" in str(ws.cell(row=1, column=celda.column).value):
                    celda.number_format = '#,##0.00'
                    celda.value = celda.value / 100.0
    for i, c in enumerate(cols, start=1):
        ancho = max(len(str(c)), *(len(str(f[c])) for f in res["filas"])) if res["filas"] else len(c)
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = min(max(ancho + 2, 10), 42)
    ws.freeze_panes = "A2"


def a_xlsx(cx: sqlite3.Connection, destino: Path, consultas: list[str]) -> Path:
    wb = Workbook(); wb.remove(wb.active)
    portada = wb.create_sheet("procedencia", 0)
    portada.append(["Sistema de análisis documental — UFIL Paraná"])
    portada["A1"].font = Font(bold=True, size=13)
    portada.append([])
    portada.append(["Generado", date.today().isoformat()])
    portada.append(["Archivos ingeridos",
                    cx.execute("SELECT COUNT(*) FROM archivo").fetchone()[0]])
    portada.append(["Documentos extraídos",
                    cx.execute("SELECT COUNT(*) FROM documento").fetchone()[0]])
    portada.append(["Campos pendientes de revisión",
                    cx.execute("SELECT COUNT(*) FROM campo WHERE estado='a_revisar'").fetchone()[0]])
    portada.append([])
    portada.append(["Advertencia:"])
    portada.append(["Los valores de estas planillas se leyeron automáticamente de los "
                    "documentos. Los campos"])
    portada.append(["pendientes de revisión NO están verificados por una persona. "
                    "Antes de incorporar cualquier"])
    portada.append(["dato a un legajo, verificarlo contra el original citado."])
    portada.column_dimensions["A"].width = 34
    portada.column_dimensions["B"].width = 22

    for cid in consultas:
        _hoja(wb, c4.correr(cx, cid))
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino


# ─────────────────────────────────────────────────────────────────────── RTF ──
def _rtf(s: str) -> str:
    out = []
    for ch in str(s):
        if ch == "\\": out.append(r"\\")
        elif ch == "{": out.append(r"\{")
        elif ch == "}": out.append(r"\}")
        elif ord(ch) < 128: out.append(ch)
        else: out.append(r"\u%d?" % ord(ch))
    return "".join(out)


def a_rtf(cx: sqlite3.Connection, destino: Path) -> Path:
    """Cuerpo justificado, interlineado 1,5, cuerpo 11. Cada afirmación con su cita."""
    sup = c4.correr(cx, "01_superposicion")["filas"]
    amb = c4.correr(cx, "03_ambas_camaras")["filas"]
    cob = c4.correr(cx, "05_cobertura")["filas"]
    exc = c4.correr(cx, "06_excluidos_del_cruce")["filas"]

    P = r"\pard\qj\sl360\slmult1\fi567\sa120\fs22 "
    T = r"\pard\qc\sl360\slmult1\sa200\b\fs26 "
    H = r"\pard\ql\sl360\slmult1\sa120\sb200\b\fs24 "

    p = [r"{\rtf1\ansi\ansicpg1252\deff0",
         r"{\fonttbl{\f0\froman\fcharset0 Times New Roman;}}",
         r"\margl1701\margr1134\margt1134\margb1134",
         T + _rtf("INFORME DE ANÁLISIS DOCUMENTAL") + r"\b0\par",
         P + _rtf(f"Generado el {date.today().strftime('%d/%m/%Y')} sobre "
                  f"{cx.execute('SELECT COUNT(*) FROM documento').fetchone()[0]} documentos "
                  f"procesados automáticamente. Cada afirmación de este informe cita el "
                  f"archivo y la foja de donde se leyó el dato, para poder verificarla "
                  f"contra el original.") + r"\par"]

    p.append(H + _rtf("1. Alcance y cobertura de la lectura") + r"\b0\par")
    for c in cob:
        p.append(P + _rtf(
            f"Campo «{c['campo']}»: {c['resueltos_solos']} de {c['total']} resueltos sin "
            f"intervención ({c['pct_sin_intervencion']}%); {c['con_valor_a_revisar']} con valor "
            f"pendiente de revisión; {c['conflictos']} en conflicto entre rutas de lectura; "
            f"{c['ilegibles']} ilegibles y {c['ausentes']} ausentes en el formulario.") + r"\par")
    p.append(P + r"\i " + _rtf(
        f"Quedaron fuera del cruce de superposición {len(exc)} contratos por faltarles algún "
        f"dato firme. Se detallan en la planilla adjunta: el total de hallazgos no debe leerse "
        f"como si el universo estuviera completo.") + r"\i0\par")

    p.append(H + _rtf("2. Superposición temporal de contratos") + r"\b0\par")
    if not sup:
        p.append(P + _rtf("No se detectaron superposiciones entre los contratos legibles.") + r"\par")
    for s in sup[:60]:
        p.append(P + _rtf(
            f"{s['contratado']} (documento {s['documento'] or 'no legible'}) registra "
            f"contratos superpuestos por {s['dias_solapados']} días, de tipo {s['cruce']}: "
            f"el período {s['periodo_a']} en la cámara {s['camara_a']} y el período "
            f"{s['periodo_b']} en la cámara {s['camara_b']} "
            f"(cf. {s['archivo_a']} y {s['archivo_b']}).") + r"\par")

    p.append(H + _rtf("3. Contratados presentes en ambas cámaras") + r"\b0\par")
    if not amb:
        p.append(P + _rtf("No se detectaron contratados en ambas cámaras.") + r"\par")
    for a in amb[:60]:
        p.append(P + _rtf(
            f"{a['contratado']} (documento {a['documento'] or 'no legible'}) registra "
            f"{a['contratos_camara_a']} contrato/s en la cámara A y {a['contratos_camara_b']} "
            f"en la cámara B, entre {a['desde']} y {a['hasta']}, por un acumulado de "
            f"${a['acumulado_centavos']/100:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
            + ".") + r"\par")

    p.append(H + _rtf("Advertencia") + r"\b0\par")
    p.append(P + _rtf(
        "Este informe es una herramienta de trabajo interna. Los datos fueron leídos "
        "automáticamente y los campos pendientes de revisión no están verificados por una "
        "persona. Nada de lo que aquí se afirma debe incorporarse a un legajo sin cotejarlo "
        "antes contra la documentación original citada.") + r"\par")
    p.append("}")

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(p), encoding="cp1252", errors="replace")
    return destino


def exportar(cx: sqlite3.Connection, destino: Path, consultas: list[str] | None = None) -> list[str]:
    destino = Path(destino); destino.mkdir(parents=True, exist_ok=True)
    consultas = consultas or [c["id"] for c in c4.catalogo()]
    hechos = [str(a_xlsx(cx, destino / "analisis.xlsx", consultas)),
              str(a_rtf(cx, destino / "informe.rtf"))]
    return hechos
