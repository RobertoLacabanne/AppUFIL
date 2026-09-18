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
| Codex | `codex/actualizacion-incremental` | `C:\Users\rober\AppUFIL\_codex` |
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
ufil/cli.py
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


---

## Desvío del reparto, anotado

**Claude tocó `ufil/servidor.py`**, que en este incremento es de Codex. Fue una línea, y
conviene decir por qué y qué se tocó, para que Codex no se encuentre con una sorpresa al
integrar.

El esquema nuevo hace que una base recién creada ocupe una página de 16 KB más
(245.760 → 262.144 bytes). Eso destapó un defecto que ya estaba:
`/api/respaldo/restaurar` contestaba `400` o `404` **sin haber leído el archivo subido**.
Mientras la copia entraba en el buffer del socket el mensaje de error llegaba igual;
pasado ese tamaño, el cliente recibe una conexión cortada en lugar del error. O sea que
quien se equivocaba al escribir el número del legajo veía «se cortó la conexión» en vez
de la frase que le dice qué tiene que escribir.

La corrección es mover la lectura del cuerpo ANTES de las validaciones. No toca ninguna
de las rutas que tiene que construir Codex ni el despachador; está adentro del bloque
`if u.path == "/api/respaldo/restaurar"`.

Lo cubre `pruebas/test_respaldo_vuelta.py::test_restaurar_exige_el_numero_del_legajo`,
que sin la corrección falla con `ConnectionResetError [WinError 10054]`. No hizo falta
agregar una prueba: la que ya estaba pasó a ser la de regresión.

## Por qué el worktree de Codex está ADENTRO del repositorio

El primer intento lo puso al lado, en `AppUFIL-codex`, que es donde corresponde. No
funciona: el entorno de Codex sólo puede escribir bajo la carpeta del proyecto, así que
un worktree hermano le queda fuera del área autorizada y no puede tocar un archivo.

Queda entonces en `_codex/`, adentro, y anotado en `.gitignore`. Sigue siendo un worktree
de verdad —otra rama, otro directorio de trabajo— así que los dos agentes pueden
programar a la vez sin pisarse, que es lo único que se le pedía.

---

## Resultado del incremento 1

| | Claude | Codex |
|---|---|---|
| Rama | `claude/actualizacion-incremental` | `codex/actualizacion-incremental` |
| Commits | 11 | 1 (`876b515`) |
| Qué hizo | esquema y migración, versionado de etapas, invalidación selectiva, actualización incremental, anclaje y reasociación de revisiones humanas, integración del pipeline, línea de comandos, 12 pruebas | los tres endpoints, la pantalla «Actualizar análisis», estilos y 7 pruebas del contrato HTTP |

**Integración:** merge de las dos ramas en `claude/prompt-maestro-documental-dwhk59`,
**sin conflictos** — el reparto de archivos aguantó.

**Pruebas combinadas después de integrar:** `549 tests · 1 failure · 14 errors · 1 skipped`,
que es la base de referencia más 19 pruebas nuevas y ninguna regresión.

**Hallazgos de la revisión cruzada:**

- *De Claude sobre Codex:* pedir una etapa inexistente devolvía el mensaje entre
  comillas. No era de la pantalla: `str()` de un `KeyError` devuelve el `repr` de su
  argumento, así que las comillas viajaban desde `ufil/versiones.py`. Corregido en
  `82e7211`, y ahora además dice cuáles son las etapas válidas.
- *De Codex sobre Claude:* ninguno. Consumió el contrato sin pedir cambios.

**Lo que salió mal en la coordinación, para no repetirlo:** se lanzaron dos tareas de
Codex apuntando al mismo worktree y las dos escribieron sobre los mismos archivos, así
que quedaron los tres endpoints duplicados. Lo detectó el propio Codex al ver cambios
que no había escrito. Se consolidó en una sola pasada suya. **Una tarea por worktree a
la vez**, y verificar que la anterior terminó antes de lanzar la siguiente.

---

## Incremento 2 — FASE 1 y FASE 2, en paralelo

| | Claude | Codex |
|---|---|---|
| Rama | `claude/fase1-desacoplar-pipeline` | `codex/fase2-reasociacion` |
| Qué hizo | partió `extraer_documento` en cuatro etapas (clasificación, cotejo, segmentación, extracción), cada una ejecutable y versionable sola; movió a la segmentación la decisión de si el reparto en piezas cambió; 5 pruebas nuevas | `ufil/reasociacion.py`, dos endpoints y la pantalla para resolver revisiones desplazadas; 14 pruebas |

**Integración:** merge de las dos en `claude/prompt-maestro-documental-dwhk59`, sin conflictos.
**Suite combinada:** `568 tests · 1 failure · 14 errors · 1 skipped` — la base de referencia, sin regresiones.

**Revisión cruzada:**

- *De Codex sobre Claude:* encontró que `reaplicar_revisiones` volvía a aplicar una
  revisión que una persona había descartado. No lo tocó porque era de otro. **Ya estaba
  cerrado** en la FASE 1 por el filtro de estados, y se comprobó contra la rama
  integrada: `reaplicadas: 0`, el campo intacto y la fila descartada en su lugar.
- *De Claude sobre Codex:* sin hallazgos. Consumió el contrato sin pedir cambios.

**Comprobado sobre corpus real** (6 contratos, 10 fojas, OCR de verdad): reextraer
conserva la identidad de la pieza y la clasificación, y la corrección humana sobrevive
(`$999.888,77 · corregido · perez.ana`, 1 reaplicada, 0 a reasociar). El pipeline
completo da lo mismo que antes del corte: 6 documentos, 36 campos, 1 conflicto.

---

## Incremento 3 — FASE 3 (núcleo documental) y FASE 4 (foliatura)

| | Claude | Codex |
|---|---|---|
| Ramas | `claude/fase3-nucleo-documental`, `claude/fase4-foliatura` | `codex/fase3-interfaz` |
| Qué hizo | identidad estable de pieza (`clave`), piezas sin reconocer como ciudadanas de primera clase, conjunto documental, continuidad entre PDF, foliatura visible con detección conservadora; 24 pruebas | endpoints y pantallas de piezas sin reconocer, tramos y conjuntos; 10 pruebas |

**Integración:** tres ramas en `claude/prompt-maestro-documental-dwhk59`, sin conflictos.
**Suite combinada:** `602 tests · 1 failure · 14 errors · 1 skipped` — la base de referencia.

**Revisión cruzada (de Claude sobre Codex):** los cinco endpoints contestan sobre corpus
real; un tipo documental inventado da 400 con el mensaje correcto; el catálogo de tipos
sale del backend (19) y no del JavaScript; las partes del conjunto salen en orden. Sin
hallazgos.

**Codex agotó su cuota** a los 5 m 57 s, con los endpoints, las pantallas y las diez
pruebas ya escritas pero sin poder commitear ni informar. Claude verificó el trabajo
(las diez pruebas pasan), lo commiteó en su rama y siguió con la FASE 4. Se retoma a
Codex en el próximo incremento.

---

## Incremento 4 — FASE 5 (tablas), FASE 7 (cronología) y las pantallas

| | Claude | Codex |
|---|---|---|
| Ramas | `claude/fase5-tablas`, `claude/fase7-cronologia` | — |
| Qué hizo | `ufil/tablas.py` y `ufil/cronologia.py` con sus etapas versionadas, cinco endpoints de lectura, las tres pantallas que faltaban y 29 pruebas | nada: agotó su cuota tres veces |

**Codex quedó sin cuota** (falla en 5 s, reintento a las 19:51). Según la regla de
continuidad, Claude siguió solo y tomó las pantallas, que en el reparto son de Codex.
Queda anotado acá para que no aparezca como sorpresa.

**Suite:** `631 tests · 1 failure · 14 errors · 1 skipped` — la base de referencia.

**Migración verificada de punta a punta.** Se construyó una base con el código del commit
base (`user_version=16`, 6 archivos, 10 fojas, 20 lecturas, 36 campos, 1 revisión humana),
se la abrió con el código de ahora y se la actualizó:

- migró a `user_version=21` **sin perder una sola fila**;
- la revisión aprendió su anclaje (`ancla_pagina=1`, `ancla_tipo=contrato_personal`);
- las piezas aprendieron su identidad estable;
- el OCR se adoptó como heredado: **10 fojas reutilizadas, 0 releídas**;
- y recibió las capacidades nuevas —10 hechos de cronología, 3 tablas, 1 foliatura—
  **sin volver a subir un archivo**, en 1,3 s, con la corrección humana intacta
  (`$555.444,33 · corregido · perez.ana`).

Es exactamente lo que pide el §7 del pliego, comprobado y no inferido.
