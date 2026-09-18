# Relevo Claude ↔ Codex

Quién hace qué, sobre qué archivos, contra qué contrato y con qué pruebas. Una entrada
por incremento. Se escribe ANTES de empezar a programar, no después: es lo que permite
que dos agentes toquen el mismo repositorio sin pisarse.

---

# Incremento 1 — Actualización incremental del material ya cargado

**Problema que resuelve.** Hoy, cuando AppUFIL incorpora una capacidad nueva, no hay
forma de aplicarla al material ya cargado sin volver a leerlo entero, y no hay forma de
saber qué quedó viejo. Peor: al reprocesar, una revisión hecha por una persona puede
terminar aplicada a otra pieza. Ver `docs/evolucion-documental.md` para el diagnóstico.

**Commit base.** `2f875ae6863c33e64c1c64896b63ca524a863461`

## E. Ramas y worktrees

| Agente | Rama | Worktree |
|---|---|---|
| Claude | `claude/actualizacion-incremental` | `C:\Users\rober\AppUFIL` |
| Codex | `codex/actualizacion-incremental` | `C:\Users\rober\AppUFIL-codex` |
| Integración | `claude/prompt-maestro-documental-dwhk59` | — |

Cada uno commitea en la suya. La integración es un merge de las dos, con las pruebas
combinadas corriendo después.

## B. Archivos que edita Claude — Codex NO los toca

```
ufil/esquema.sql
ufil/db.py
ufil/versiones.py          (nuevo)
ufil/actualizacion.py      (nuevo)
ufil/capa1_texto.py
ufil/capa2_extraccion.py
ufil/aplicar_revision.py
ufil/trabajo.py
pruebas/test_actualizacion.py   (nuevo)
docs/evolucion-documental.md
docs/relevo-claude-codex.md
```

## C. Archivos que edita Codex — Claude NO los toca

```
ufil/servidor.py
ufil/web/app.js
ufil/web/index.html
ufil/web/estilo.css
pruebas/test_actualizar_web.py  (nuevo)
```

## D. Archivos compartidos — nadie los edita en este incremento

`ufil/config.py`, `ufil/clasificacion.py`, `ufil/confianza.py`, `ufil/busqueda.py`,
`ufil/capa3_identidad.py`, `ufil/legajos.py`, y toda prueba existente en `pruebas/`.

Si alguno de los dos necesita tocar uno de estos, lo pide en este documento y espera.
La razón es concreta: `ufil/servidor.py` es un solo despachador de 1.740 líneas y
`ufil/esquema.sql` una sola tabla de verdades; dos escritores simultáneos ahí garantizan
conflicto.

---

## A. Contrato entre los componentes

Claude expone funciones de Python puras sobre una conexión. Codex las consume desde
`servidor.py` y las muestra. **Codex no consulta las tablas nuevas directamente**: si
necesita un dato que no está en el contrato, lo pide acá.

### `ufil.actualizacion.plan(cx, *, forzar=()) -> dict`

Qué quedó desactualizado y qué se va a reutilizar. **No escribe nada**: es lo que se
muestra ANTES de ejecutar. `forzar` es una tupla de claves de etapa que se recalculan
aunque estén vigentes.

```python
{
  "vigente": bool,                 # True si no hay nada que hacer
  "etapas": [                      # en orden de dependencia
    {
      "clave": "lectura",
      "nombre": "Lectura de las fojas (OCR)",
      "estado": "vigente",         # vigente | desactualizada | nunca | heredada
      "motivo": str | None,        # por qué quedó vieja, en castellano
      "alcance": "pagina",         # archivo | pagina | documento | legajo
      "vigentes": 412,
      "desactualizados": 0,
      "total": 412,
      "cuesta": "caro"             # caro | barato — para que la pantalla lo diga
    }, ...
  ],
  "reutiliza": {"paginas_ocr": 412, "lecturas": 824},
  "recalcula": {"paginas_ocr": 0, "archivos": 9, "documentos": 37, "indice": True},
  "archivos": [                    # uno por archivo, para la tabla de la pantalla
    {"sha256": str, "nombre": str, "paginas": int,
     "desactualizadas": ["clasificacion", "extraccion"]}
  ],
  "revisiones": {
    "total": 44,
    "preservadas": 43,             # se reaplican solas, con anclaje seguro
    "requieren_reasociacion": 1    # NO se aplican: necesitan que una persona mire
  }
}
```

### `ufil.actualizacion.reasociaciones(cx) -> list[dict]`

Las revisiones humanas que quedaron sin pieza segura a la cual aplicarse. Se muestran
para que una persona decida; **nunca se aplican solas**.

```python
[{"sha256": str, "archivo": str, "campo": str, "valor": str | None,
  "quien": str, "cuando": str, "motivo": str,
  "ancla_pagina": int | None, "orden_viejo": int}]
```

### `ufil.trabajo.Procesador.actualizar(forzar=()) -> dict`

Arranca la actualización incremental en el hilo de fondo. Misma forma de respuesta que
`arrancar()`: `{"ok": True}` o `{"ok": False, "motivo": str}`. El progreso se lee con
`Procesador.estado.como_dict()`, que ya es lo que consume `/api/trabajo` hoy — **no
cambia de forma**, así que la barra de progreso existente sigue andando sin tocarla.

### Endpoints que tiene que construir Codex

| Método | Ruta | Cuerpo | Devuelve |
|---|---|---|---|
| GET | `/api/actualizacion` | — | `plan(cx)` tal cual |
| GET | `/api/reasociaciones` | — | `{"revisiones": reasociaciones(cx)}` |
| POST | `/api/actualizar` | `{"forzar": ["lectura", ...]}` opcional | `Procesador.actualizar(...)` tal cual |

Las tres van adentro del bloque que ya existe en `servidor.py` (`if ruta == "/api/..."`
para GET, `if u.path == "/api/..."` para POST), con el mismo manejo de errores que las
demás. `/api/actualizar` va después de `cx = _cx()`, junto a `/api/procesar`.

### Lo que tiene que construir Codex en la interfaz

Una acción **«Actualizar análisis»** que, **antes de ejecutar**, muestre lo que devuelve
`/api/actualizacion`: qué etapas están vigentes, cuáles quedaron viejas y por qué, qué se
reutiliza (sobre todo el OCR, que es lo caro), y cuántas revisiones humanas se preservan
y cuántas necesitan que alguien las mire. Recién después, el botón que la ejecuta.

Reglas que no son cosméticas:

- **Si no hay nada que hacer, decirlo** y no ofrecer un botón que no hace nada.
- **«Se reutiliza» tiene que ser tan visible como «se recalcula».** Lo que esta pantalla
  existe para responder es «¿me va a hacer esperar dos horas de OCR de nuevo?».
- Una etapa `heredada` se muestra como vigente pero **se dice que es heredada**: se
  adoptó lo que ya estaba en la base sin volver a leerlo. No es lo mismo que haber
  comprobado que coincide, y la pantalla no puede sugerir que sí.
- Las revisiones que **requieren reasociación** no son un error ni una pérdida: son
  trabajo humano que se conservó y que no se aplicó solo porque no era seguro a cuál
  pieza corresponde. El texto tiene que decir eso.
- Nada de cantidades, nombres de archivo ni tipos documentales escritos a mano en el
  JS: todo sale del JSON.

## F. Pruebas que tiene que pasar cada implementación

**Claude** (`pruebas/test_actualizacion.py`):
1. Una revisión humana hecha sobre una pieza NO puede terminar aplicada a otra después
   de resegmentar. (Regresión del defecto que motiva el incremento.)
2. Cambiar la versión/configuración de una etapa desactualiza esa etapa y las que
   dependen de ella, y **sólo** ésas.
3. Cambiar una etapa posterior no desactualiza el OCR: las lecturas se reutilizan.
4. Una base vieja, sin sellos, se migra sin perder revisiones ni lecturas.
5. La actualización es reanudable: cortarla a la mitad y volver a correrla no repite lo
   ya hecho ni pierde lo que faltaba.

**Codex** (`pruebas/test_actualizar_web.py`):
1. `GET /api/actualizacion` sobre una base vacía no revienta y dice que no hay nada.
2. `GET /api/actualizacion` informa las etapas desactualizadas y lo que se reutiliza.
3. `POST /api/actualizar` arranca el trabajo y `GET /api/trabajo` lo refleja.
4. `GET /api/reasociaciones` devuelve las revisiones que necesitan una persona.
5. La pantalla no inventa: todo número que muestra sale del JSON.

**Combinadas, después de integrar:** la suite entera
(`python -m unittest discover -s pruebas -p "test_*.py"`).

### Base de referencia de la suite (medida en el commit base, antes de tocar nada)

`Ran 530 tests · 1 failure · 14 errors · 1 skipped`

Ninguno de esos es del incremento y ninguno se puede empeorar:

- El `failure` es de entorno: `pruebas/test_taller.py` lee `ufil/web/app.js` sin declarar
  `encoding="utf-8"` y en Windows lo decodifica en cp1252, así que el `×` de un mensaje
  llega roto a la comparación.
- Los 14 `errors` son todos `PermissionError [WinError 32]` al borrar el directorio
  temporal en Windows con una conexión SQLite todavía abierta. Son de `tearDown`, no de
  aserción.

Correr con Tesseract en el PATH (`C:\Program Files\Tesseract-OCR`); sin él, el import de
`ufil/capa1_texto.py` falla y se caen 63 pruebas que no tienen nada que ver.
