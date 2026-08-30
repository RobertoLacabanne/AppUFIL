"""
Procesamiento en segundo plano, con progreso.

Leer un lote de escaneos lleva minutos: no puede colgar el navegador ni obligar a
nadie a abrir una terminal. Un solo hilo trabajador, una cola, y un estado que la
interfaz consulta cada dos segundos.

Un solo hilo a propósito: Tesseract ya usa varios núcleos, SQLite escribe mejor de a
uno, y un trabajador único hace que el progreso sea comprensible en lugar de ser una
suma de barras que avanzan a saltos.
"""
from __future__ import annotations

import threading
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import config, db
from . import capa1_texto as c1
from . import capa2_extraccion as c2
from . import capa3_identidad as c3
from . import busqueda
from . import capa5_interpretacion as c5


@dataclass
class Estado:
    estado: str = "inactivo"          # inactivo | corriendo | terminado | error
    etapa: str = ""
    hecho: int = 0
    total: int = 0
    mensaje: str = ""
    errores: list = field(default_factory=list)
    inicio: float | None = None
    fin: float | None = None
    resumen: dict = field(default_factory=dict)

    def como_dict(self) -> dict:
        d = asdict(self)
        d["segundos"] = round((self.fin or time.time()) - self.inicio, 1) if self.inicio else 0
        if self.hecho and self.total and self.estado == "corriendo":
            paso = (time.time() - self.inicio) / self.hecho
            d["faltan_segundos"] = round(paso * (self.total - self.hecho))
        else:
            d["faltan_segundos"] = None
        return d


class Procesador:
    """Un trabajador. `arrancar` no hace nada si ya hay algo corriendo."""

    def __init__(self, ruta_base: Path | None = None):
        self.ruta_base = ruta_base
        self.estado = Estado()
        self._lock = threading.Lock()
        self._hilo: threading.Thread | None = None

    def ocupado(self) -> bool:
        return bool(self._hilo and self._hilo.is_alive())

    def arrancar(self, perfil: str = "auto", con_vlm: bool = False) -> dict:
        with self._lock:
            if self.ocupado():
                return {"ok": False, "motivo": "ya hay un procesamiento en curso"}
            self.estado = Estado(estado="corriendo", etapa="preparando",
                                 inicio=time.time(), mensaje="")
            self._hilo = threading.Thread(target=self._correr, args=(perfil, con_vlm),
                                          daemon=True)
            self._hilo.start()
        return {"ok": True}

    # ── el trabajo propiamente dicho ──
    def _correr(self, perfil: str, con_vlm: bool) -> None:
        cx = db.abrir(self.ruta_base)
        try:
            pendientes = [r["sha256"] for r in cx.execute(
"""SELECT DISTINCT a.sha256 FROM archivo a
             JOIN pagina p ON p.sha256 = a.sha256
            WHERE NOT EXISTS (SELECT 1 FROM lectura l WHERE l.pagina_id = p.id)
            ORDER BY a.nombre""")]
            # El progreso va por PÁGINA, que es la unidad real de trabajo: un lote de
            # cincuenta archivos donde uno tiene treinta fojas avanzaba a los saltos.
            paginas = cx.execute("""SELECT COUNT(*) FROM pagina p
                                     WHERE NOT EXISTS (SELECT 1 FROM lectura l
                                                        WHERE l.pagina_id = p.id)"""
                                 ).fetchone()[0] if pendientes else 0
            self._fase("leyendo los escaneos", paginas)

            def avance(hechas, total):
                with self._lock:
                    self.estado.hecho = hechas
                    self.estado.total = total

            if pendientes:
                try:
                    c1.leer_lote(cx, pendientes, con_vlm=con_vlm, avance=avance)
                except Exception as e:
                    self._error(cx, pendientes[0], "lectura", e)

            shas = [r["sha256"] for r in cx.execute(
                "SELECT sha256 FROM archivo ORDER BY ingerido_en, nombre")]
            self._fase("extrayendo los campos", len(shas))
            totales = {"documentos": 0, "campos": 0, "conflictos": 0,
                       "a_revisar": 0, "sin_perfil": 0}
            for sha in shas:
                try:
                    r = c2.extraer_documento(cx, sha, perfil)
                    for k in totales:
                        totales[k] += r.get(k, 0)
                except Exception as e:
                    self._error(cx, sha, "extracción", e)
                self._avance(cx)

            self._fase("resolviendo identidades", 2)
            ident = c3.resolver(cx); self._avance(cx)
            fus = c3.proponer_fusiones(cx)
            repetidos = c3.detectar_contratos_repetidos(cx); self._avance(cx)

            self._fase("indexando para la búsqueda", 1)
            paginas_idx = busqueda.reindexar(cx); self._avance(cx)

            self._fase("buscando patrones", 1)
            interp = c5.regenerar(cx); self._avance(cx)

            with self._lock:
                self.estado.estado = "terminado"
                self.estado.etapa = "listo"
                self.estado.fin = time.time()
                self.estado.resumen = {**totales, **ident, **fus,
                                       "contratos_repetidos": repetidos,
                                       "paginas_indexadas": paginas_idx,
                                       "interpretaciones": sum(interp.values())}
                extra = (f" (¡{totales['documentos'] - len(shas)} más que archivos: "
                         f"había PDF con varios contratos adentro!)"
                         if totales["documentos"] > len(shas) else "")
                self.estado.mensaje = (
                    f"{len(shas)} archivos · {totales['documentos']} contratos{extra} · "
                    f"{totales['a_revisar']} a revisar · {fus['propuestas']} fusiones propuestas")
        except Exception as e:
            traceback.print_exc()
            with self._lock:
                self.estado.estado = "error"
                self.estado.fin = time.time()
                self.estado.mensaje = f"{type(e).__name__}: {e}"
        finally:
            cx.close()

    def _fase(self, etapa: str, total: int) -> None:
        with self._lock:
            self.estado.etapa = etapa
            self.estado.hecho = 0
            self.estado.total = total
            self.estado.inicio = self.estado.inicio or time.time()

    def _avance(self, cx=None) -> None:
        with self._lock:
            self.estado.hecho += 1

    def _error(self, cx, sha: str, etapa: str, e: Exception) -> None:
        nombre = (cx.execute("SELECT nombre FROM archivo WHERE sha256=?", (sha,)).fetchone()
                  or {"nombre": sha[:12]})["nombre"]
        detalle = f"{nombre}: {type(e).__name__}: {e}"
        with self._lock:
            self.estado.errores.append({"etapa": etapa, "detalle": detalle})
        cx.execute("""INSERT INTO excepcion (sha256, clase, detalle, creado_en)
                      VALUES (?,?,?,?)""", (sha, f"falla_{etapa}", detalle, db.ahora()))
        cx.commit()
