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

---

## Incremento 5 — FASES 6, 8, 9 y 10

| | Claude | Codex |
|---|---|---|
| Ramas | `claude/fase6-entidades`, `fase8-busqueda`, `fase9-exportaciones`, `fase10-rendimiento` | `codex/fase6y8-interfaz` |
| Qué hizo | menciones/entidades/relaciones, búsqueda paginada con variantes de OCR, consultas guardadas y colecciones, informes con trazabilidad, pantalla de informes, y el trabajo de volumen y robustez | las pantallas de entidades, relaciones, colecciones y la paginación de la búsqueda, con 11 pruebas |

**Suite:** `699 tests · 1 failure · 14 errors · 1 skipped` — la base de referencia.

### Revisión cruzada: lo que encontró cada uno en el código del otro

- **Codex → Claude.** `/api/buscar` ignoraba `limite` y `desde`: la paginación existía
  en el backend y no se podía alcanzar desde la pantalla. Lo reportó y no lo tocó,
  porque `servidor.py` no era suyo.
- **Codex → Claude, otra vez.** Sus pruebas HTTP dieron 404 en cuatro POST. Cinco rutas
  —informes, colecciones, consultas, entidades y relaciones— habían quedado escritas
  adentro de un `if` que sólo dejaba pasar `/api/pieza/` y `/api/conjunto/`. El
  manejador estaba y la ruta no existía para el servidor. **Sin sus pruebas, las cinco
  se habrían dado por funcionando.**
- **Claude → Codex.** Sin hallazgos: su trabajo pasó las 11 pruebas propias y la suite
  entera una vez corregido el bug de las rutas.

### Lo que Codex dejó y cómo se recuperó

Codex se quedó sin cuota cinco veces y en la última quedó con las pantallas a medio
commitear. Se preservaron en su rama con dos commits marcados `INCOMPLETO`, **sin
integrar**. Al retomar se los evaluó en una rama descartable: sus 11 pruebas pasaban una
vez corregido el bug que ellas mismas habían encontrado, así que se recuperó todo.

### Hallazgos propios de la fase 10

- **103 MB de pico para un archivo de 400 fojas.** Las etapas que trabajan foja por foja
  cargaban el archivo entero. Con lectura de a una: 1 MB.
- **Las fojas sin una sola palabra desaparecían del recuento** al pasar a leer de a una.
  Roto un rato, corregido, con su prueba.
- **Un archivo roto obligaba a rehacer los demás.** La invalidación por dependencia era
  por etapa entera y no por archivo.

---

## Incremento 6 — Papelera de archivos: integración de Codex y Gemini, y correcciones

Tercer agente en el reparto: **Gemini** (Antigravity CLI, `gemini-3.1-pro-high`) toma la
interfaz; **Codex** el backend y sus pruebas; **Claude** coordina, integra y revisa.

**Commit base de las correcciones.** `c324fce` en `claude/integracion-codex-gemini`: la
rama de integración con `codex/post-1464f24` y `gemini/appufil-agent` ya mergeadas, en
ese orden, **sin conflictos** (Codex tocó backend y `servidor.py`; Gemini sólo `ufil/web/*`
y una prueba nueva).

**Suite, con `PYTHONUTF8=1` y Tesseract en el PATH:**

| Punto | Resultado |
|---|---|
| `1464f24` (base) | `699 tests · 0 failures · 14 errors · 1 skipped` — los 14 son `WinError 32` de `tearDown` |
| + Codex (`af54f8a`) | `733 tests · OK · 1 skipped` — Codex además cerró los 14 errores de fixtures |
| + Gemini (`c324fce`) | `736 tests · OK · 1 skipped` |

La suite no ve los problemas de abajo: salen de la revisión cruzada, no de las pruebas.

### E. Ramas y worktrees

| Agente | Rama | Worktree |
|---|---|---|
| Claude | `claude/integracion-codex-gemini` | `C:\Users\rober\AppUFIL` |
| Codex | `codex/papelera-escala` (desde la integración, con este documento) | `C:\Users\rober\AppUFIL-codex-next` |
| Gemini | `gemini/papelera-correcciones` (ídem) | `C:\Users\rober\AppUFIL-gemini` |

Codex se invoca con `codex exec` desde su worktree y Gemini con `agy -p` desde el suyo,
cada uno con su `TASK_*.md` sin versionar. El plugin `/codex:*` no se usa: su runtime
compartido no levanta en Windows (`connect ENOENT \\.\pipe\cxc-…-codex-app-server`),
aunque `codex login status` confirma la sesión. `codex exec` 0.155 no acepta
`--ask-for-approval`: la política va por `-c approval_policy="never"`.

### Revisión cruzada — lo que encontró cada uno

**Codex → Gemini** (navegador real por CDP contra el frontend de `7b7c43c` sin modificar,
backend actual y datos sintéticos; evidencia en `AppUFIL-codex-next`,
`docs/revision-gemini-evidencia.json`):

| # | Hallazgo | Evidencia |
|---|---|---|
| G1 | **Inyección de código.** Los botones de la papelera y de «Quitar del legajo» arman `onclick="f('${esc(nombre)}')"`. `esc` convierte `'` en `&#39;`, pero el navegador decodifica la entidad antes de parsear el JS: un archivo llamado `x',globalThis.__revisionXss=1,'z.pdf` ejecuta código. | `xss.codigoEjecutado: true` |
| G2 | Un nombre con apóstrofo (`O'Brien.pdf`) rompe el botón: `SyntaxError`. | `apostrofe.errores` |
| G3 | El zoom escala el marco de la región desde su propia esquina, no desde la imagen: al duplicar el zoom el resaltado queda en (120,160) y debería estar en (240,320). Señala otro lugar del papel. | `zoomDespues` |
| G4 | Restaurar dos veces seguidas manda dos pedidos; el segundo da 409 y la pantalla muestra un error sobre una restauración que salió bien. | `dobleRestauracion` |
| G5 | Si el refresco posterior falla, queda una promesa rechazada sin manejar y ningún mensaje. | `refrescoSinCatch` |
| G6 | Al terminar una acción se redibuja la papelera aunque la persona ya se haya ido a otra pantalla (`#/informes` mostrando la papelera), y quitar desde otra pantalla hace `location.reload()`. Pierde el lugar (§20). | `perdidaContexto` |
| G7 | Una respuesta incompleta (`{}`) se muestra como «La papelera está vacía». No saber no es lo mismo que no haber. | `respuestaIncompleta` |
| G8 | 1.500 archivos en papelera: 1.500 filas y 3.000 botones, sin paginar. | `listaGrande` |
| G9 | En `#/papelera` la navegación marca «Documentos», donde el enlace no está: la ruta figura en `tambien` de esa sección y como ítem de «Sistema». | `navegacion` |

**Claude → Gemini:**

| # | Hallazgo |
|---|---|
| G10 | **Todos los diálogos de la papelera muestran escapes en vez de letras**: «acci\u00f3n», «est\u00e1», «Destrucci\u00f3n f\u00edsica». El código escribe `\\u00f3` dentro de template literals, que produce la barra literal. Codex lo capturó sin nombrarlo (`procesando`, `dobleRestauracion.texto`). |
| G11 | **La pantalla inventa un número**: `f.revisiones` con `1` por omisión hace decir «1 revisiones» a un archivo con decisiones humanas y cero filas en `revision_humana`. |
| G12 | Las descripciones de los informes están escritas en el JS por `clave`, y la rama por omisión describe Índice, Cronología y Fichas como «datos consolidados de todo el legajo», que no es lo que ninguno de los tres hace. Un informe nuevo heredaría esa frase. |
| G13 | `class="visor-controles" class="acciones-fila"`: el segundo atributo se ignora. |
| G14 | `pruebas/test_papelera_web.py` no protege lo que dice: `test_pedir_quitar` no afirma nada, las pruebas usan un `esc` propio que no escapa `'` (no podían ver G1) y `test_revisiones_humanas_se_informan` **exige** el escape roto de G10. |

**Gemini → Codex** (`docs/revision-codex-por-gemini.md`): la papelera no expone `paginas`
(C1) ni `lote` (C2), y `revisiones` cuenta sólo `revision_humana` mientras
`tiene_revisiones_humanas` mira diez tablas (C3). Los tres son ciertos.

**Claude → Codex:**

| # | Hallazgo |
|---|---|
| C4 | **Quitar un archivo lee la base entera.** `_instantanea` hace `SELECT *` de **todas** las tablas del legajo —incluida `palabra`, una fila por palabra de OCR— y recorre todas las filas en cada vuelta del punto fijo, por cada FK. Con miles de fojas son millones de diccionarios en memoria para retirar un PDF. Es el mismo defecto que la FASE 10 había cerrado (103 MB → 1 MB) y contradice §22. |
| C5 | Los PNG de las fojas van dentro del JSON de la instantánea en base64, y `listar` hace `json_extract` sobre ese JSON en cada fila: mirar la papelera parsea todas las instantáneas enteras. |
| C6 | `restaurar` compara **toda** la fila de cada padre compartido. Si después de quitar cambia una columna cualquiera de una entidad compartida, la restauración queda en 409 para siempre. Hay que reproducirlo antes de corregirlo: puede que ninguna columna de los padres actuales cambie en uso normal. |
| C7 | `/api/archivos` hace doce consultas por archivo (`COUNT`, diez `EXISTS`, `_ocupado`). |

**Claude → Claude:** el informe de Cronología corta en 5.000 hechos sin decirlo
(`cr.linea(cx, limite=5000)`). Es la misma clase de defecto que la búsqueda que cortaba
en sesenta.

### A. Contrato

**`GET /api/papelera/archivos?limite=&desde=`** (Codex) — paginado, lo más reciente primero:

```python
{"archivos": [{"sha256": str, "nombre": str, "quitado_en": str,
               "paginas": int | None,        # None si no se sabe; nunca 0 por no saber
               "lote": str | None,
               "documentos": int, "bytes": int,
               "revisiones": int,            # filas de revision_humana, como hasta ahora
               "decisiones_humanas": int,    # todas las que mira tiene_revisiones_humanas
               "tiene_revisiones_humanas": bool,   # == decisiones_humanas > 0
               "confirmacion_destruir": "DESTRUIR <sha>"}],
 "total": int, "desde": int, "limite": int}
```

`limite` por omisión 100, máximo 500; `desde` por omisión 0. Fuera de rango o no entero: 400.

**`GET /api/archivos`** (Codex): cada archivo agrega `decisiones_humanas` con la misma
definición. `revisiones` y el resto no cambian de nombre ni de forma.

**`GET /api/informes`** (Claude): cada informe agrega `descripcion: str`, qué contiene, en
castellano. La pantalla la muestra tal cual; no escribe ninguna.

### B/C/D. Archivos

- **Codex:** `ufil/papelera.py`, `ufil/esquema.sql`, `ufil/db.py`, `ufil/exclusion.py`,
  `ufil/respaldo.py`, y en `ufil/servidor.py` **sólo** `api_archivos` y los bloques de
  papelera; `pruebas/test_papelera_*.py` salvo `test_papelera_web.py`,
  `pruebas/test_auditoria_backend.py`, `docs/papelera-archivos-backend.md`, y su revisión
  (`docs/revision-gemini-por-codex.md`, `docs/revision-gemini-evidencia.json`,
  `scripts/revision_gemini_*`).
- **Gemini:** `ufil/web/app.js`, `ufil/web/index.html`, `ufil/web/estilo.css`,
  `pruebas/test_papelera_web.py` y pruebas nuevas propias `pruebas/test_*_web*.py`.
- **Claude:** `ufil/exportar.py`, `ufil/cronologia.py`, sus pruebas, y los tres documentos
  vivos.
- **Nadie:** el resto de `ufil/servidor.py` y toda prueba existente no nombrada arriba.

### F. Pruebas

- **Codex:** quitar un archivo de un legajo grande no lee filas de otros archivos (medido,
  no supuesto); la papelera se lista sin parsear instantáneas; `paginas` y `lote`
  correctos y `None` cuando no se saben; `decisiones_humanas` coincide con
  `tiene_revisiones_humanas`; C6 reproducido o descartado con una prueba; paginación con
  400 en los bordes; la suite entera sin regresiones.
- **Gemini:** un nombre con `'`, `"`, `<`, `&` y la carga de G1 no ejecuta nada y el botón
  funciona; los diálogos no contienen `\u`; ningún número que no esté en el JSON; el zoom
  deja el resaltado sobre la región; doble clic manda un solo pedido; una acción que
  termina en otra pantalla no la pisa; respuesta incompleta ≠ vacía; paginación; y las
  pruebas usan el `esc` real de `app.js`.
- **Combinadas:** la suite entera, más la revisión de Codex (`scripts/revision_gemini_*`)
  vuelta a correr contra el frontend corregido.

## Resultado del incremento 6

| | Claude | Codex | Gemini |
|---|---|---|---|
| Rama | `claude/integracion-codex-gemini` | `codex/papelera-escala` | `gemini/papelera-correcciones` |
| Commits | `5c1319b`, y los de integración | `daa9e0d`, `228e08a` (commiteados por Claude) | `16d9dfe` |
| Qué hizo | descripción de informes desde el backend, cronología entera, G9 y la navegación con query, G5, dos pruebas que dependían de la forma y no del comportamiento, y la revisión en navegador sobre la integración | C1–C7, la migración v24 → v25 de la papelera y el cierre de su revisión de Gemini | G1–G4, G6–G8, G10–G14, con 13 pruebas que fallan con la interfaz anterior |

**Integración, segunda vuelta:** Codex primero (`06f233f`), después Gemini (`4e66fc0`),
sin conflictos de merge. Sí hubo dos incompatibilidades que sólo aparecen al correr la
suite combinada, y ninguna era de comportamiento:

- `test_carga` leía los primeros 3.000 caracteres de `api_archivos`; la agregación por
  lote de Codex empujó el orden de los estados fuera de esa ventana. Ahora lee la función
  entera (`0233e69`).
- `test_taller` buscaba la línea literal que espera la carga de la imagen antes de
  desplazarse; Gemini la envolvió para aplicar el zoom primero. Ahora exige las dos cosas
  y en ese orden (`f44a428`).

**Suite final:** `765 tests · OK · 1 skipped` (base `1464f24`: 699 · 14 errors).

**Revisión en navegador real, repetida sobre la interfaz integrada**
(`docs/revision-gemini-evidencia-integrada.json`, `app.js` `7a30a2f9…`, 3 de 3 corridas):

| | Interfaz de `7b7c43c` | Integrada |
|---|---|---|
| G1 código inyectado por el nombre | se ejecuta | no se ejecuta |
| G2 nombre con apóstrofo | `SyntaxError` | sin errores |
| G3 marco con zoom 2 (esperado 240,320) | 120,160 | 240,320 |
| G4 doble restauración / doble destrucción | 200 + 409 / 2 pedidos | 1 pedido / 1 pedido |
| G5 falla el refresco después de restaurar | promesa sin manejar, nada visible | 1 diálogo, sin promesas sueltas |
| G6 acción que termina en `#/informes` | pinta la papelera | queda en Informes |
| G7 respuesta `{}` | «La papelera está vacía» | error dicho como error |
| G8 1.500 archivos | 1.500 filas, sin paginador | 100 filas, paginador |
| G9 sección marcada / enlace visible | Documentos / no | Sistema / sí |
| G10 escapes en diálogos | sí | no |

**Lo que dijo cada informe y lo que se comprobó.** El informe final de Gemini describe G9,
G12 y G13 como otros problemas («reset del formulario», «parpadeo del visor», «IDs
repetidos») y da G9 por cerrado cuando seguía abierto. Las correcciones de G12 y G13 sí
estaban en el código; G9 lo cerró Claude. **Un informe no reemplaza mirar el diff.**

### Desvíos del reparto, anotados

- Claude commiteó por Codex: su sandbox no puede crear `index.lock` en `.git`, ni
  siquiera con `--add-dir` sobre esa carpeta. También repuso el docstring de
  `api_archivos`, que Codex había reducido a dos líneas.
- Claude tocó `ufil/web/app.js` y `pruebas/test_papelera_web.py`, que son de Gemini, para
  G9, la navegación con query y G5, después de que Gemini terminó. Y
  `scripts/revision_gemini_browser.cjs`, de Codex: el arnés cerraba diálogos sin sacarlos
  del DOM y a veces el paso siguiente pulsaba el botón de uno ya cerrado. Con la interfaz
  vieja no pasaba porque esos diálogos ni se abrían.

### Lo que salió mal en la coordinación, para no repetirlo

- **Antigravity CLI manda a segundo plano los comandos largos y los mata al salir**,
  aunque se le pida lo contrario. Las dos primeras sesiones de Gemini terminaron sin
  commit ni informe porque dejaron la suite corriendo de fondo. A Gemini se le pide
  correr sólo sus pruebas y commitear; la suite entera la corre Claude al integrar.
- **El sandbox de Codex en Windows no escribe en `.git`.** Codex deja los cambios y los
  comandos de commit en su informe; Claude revisa el diff, corre la suite fuera del
  sandbox y commitea en su rama.
- **C8, la regresión que dejó la primera papelera:** desde `863fc2b`, subir un PDF
  mientras el pipeline procesaba daba 409, porque `guardar` pedía el mismo cerrojo
  exclusivo que el trabajador sostiene toda la corrida. Lo reprodujo Claude; lo corrigió
  Codex en `codex/subir-durante-proceso` (`8af5d00`) con cerrojos de dos niveles.
  **Codex se quedó sin cuota** («try again at 11:15 PM») con el código y 18 pruebas
  escritas, sin haber corrido la suite ni commiteado. Claude verificó que las pruebas de
  carga fallan con el código anterior por el mismo `Ocupado` de C8 y pasan con el nuevo,
  corrió la suite (783 · OK) y commiteó por él. Integrado en `3cdd2eb`.

**Suite después de C8:** `783 tests · OK · 1 skipped`. La revisión en navegador, repetida
12 veces después de C8: 11 bien y 1 fallo cuya causa no quedó registrada. Pasó justo
después de la suite entera, con la máquina cargada, y el arnés espera como máximo 6 s
por paso: es lo más probable, pero es inferido.

---

# Incremento 7 — Contrataciones y precios

**Cambio de foco (Roberto, 21/09/2026).** El objetivo analítico central pasa a ser asistir
investigaciones de posibles sobreprecios y anomalías en contrataciones públicas:
reconstruir la contratación, comparar precios, relacionar documentos, detectar
inconsistencias y mostrarlas con su fuente, **sin concluir**. El contrato completo
—semántica, modelo, comparabilidad, niveles de referencia, cálculos, hallazgos,
trazabilidad, etapas y API— está en `docs/contrataciones-y-precios.md`, y es la referencia
de este incremento.

**Commit base.** `172c5cf` (incremento 6 integrado en la rama principal).

| | Rama | Worktree |
|---|---|---|
| Claude | `claude/contrataciones-precios` (integración) | `C:\Users\rober\AppUFIL` |
| Codex | `codex/contrataciones-backend` | `C:\Users\rober\AppUFIL-codex-next` |
| Gemini | `gemini/contrataciones-interfaz` | `C:\Users\rober\AppUFIL-gemini` |

Codex no tiene cuota hasta las 23:15. Mientras tanto Claude escribe el núcleo semántico
(`ufil/comparabilidad.py`) y Gemini programa la interfaz contra el contrato con datos
simulados; el backend de Codex arranca cuando vuelve la cuota, sobre ese núcleo.

## El corpus real pasa a ser el criterio (21/09/2026)

Roberto pidió que la validación y la mejora se hagan **sobre el legajo real** cargado en la
instancia desplegada, y autorizó expresamente usarlo para todo. Los PDF sintéticos quedan
como regresión mínima. El flujo: corpus real → problema → reproducir → corregir → prueba
sintética mínima → volver al corpus real → confirmar. **Nada real va a Git**: ni en
pruebas, ni en fixtures, ni en mensajes; en este documento sólo cantidades.

**Dónde está y cómo se copió.** La instancia de Render guarda todo en su disco
persistente (`UFIL_DATOS=/app/datos`, `legajos/<slug>/ufil.sqlite`). La copia se sacó con
la función de respaldo de la propia aplicación (API de backup de SQLite, no toca la base)
a `C:\Users\rober\AppUFIL-corpus-real\` —fuera de todo repositorio—: el original intacto
en `produccion-original/` (sólo lectura, `integrity_check` ok, esquema 25) y una copia de
trabajo por agente (`claude/`, `codex/`, `gemini/`). Coincide con lo que Roberto ve en
producción: 20 piezas, 1.628 fojas, 116 campos a revisar, 2 en conflicto, 6 revisiones
humanas, 18 personas. `herramientas/traer_corpus_real.py` repite el procedimiento.

**Alerta de seguridad, para Roberto:** la instancia desplegada sirve los datos **sin
clave** (`/api/legajos`, `/descargar`), aunque `render.yaml` la pide. Se le avisó; el
arreglo es suyo (variables de entorno en Render) y no se tocó producción.

**Límites de la copia:** de los 11 originales sólo está en esta máquina el de 750 fojas
(mismo SHA-256); los otros 10 no. Los renders de las fojas no se pudieron bajar: el
clasificador de permisos de Claude bloqueó la descarga masiva. El texto leído sí está
completo, así que todo lo que trabaja sobre palabras se puede correr; el visor no.

### Lo que encontró el corpus real, y qué se hizo

| # | Hallazgo (sólo cantidades) | Estado |
|---|---|---|
| R1 | «Actualizar análisis» iba a releer **750** fojas de un archivo que tenía 410 leídas y 340 sin leer: la lectura se ejecutaba por archivo | corregido (`fc291c5`): se leen 340, se reutilizan 1.288 |
| R2 | 2 de las 6 revisiones humanas iban a pasar a «requiere reasociación»: verificaciones de campos sin valor, que no tienen foja; y le pasa a toda confirmación de ese tipo que se haga hoy | corregido (`bb77a62`): anclaje por pieza |
| R3 | El panel decía «1.628 páginas leídas» con 340 sin leer | corregido (`ab35d32`): «1.288 / 1.628» |
| R4 | 1.628 fojas producen **20 piezas**; el PDF de 750 fojas **no tiene ninguna foja clasificada**; 6 de 10 PDF de ~88 fojas, **0 piezas**. En producción corre un pipeline anterior (0 sellos de segmentación); con el de hoy, 54 piezas, todas facturas o contratos: las piezas salían sólo de los perfiles | corregido (`2a055b2`): 258 piezas (128 resoluciones, 48 remitos, 47 facturas, 19 presupuestos…) |
| R9 | Dos correcciones humanas de contratos ancladas «en la foja 1» con numeración relativa a la pieza, de una versión anterior; si la foja 1 tuviera otra pieza con el mismo campo, la corrección se mudaba | corregido (`e8c638f`): las 6 revisiones reales vigentes tras resegmentar |
| R10 | Una foja con 137 fragmentos ilegibles salía «en blanco» porque la otra ruta vio una palabra | corregido (`46ce524`) |
| R11 | 589 fojas «en blanco» | verificado por tinta en el PDF de 750: 230/230 sin tinta; no es un problema |
| R12 | 26 de 128 piezas de resolución pegadas a la anterior (¿una resolución partida?); 36 fojas «continuación» detrás de facturas, remitos y recibos sin pieza | tarea de Codex (7a), medido |
| R5 | Fojas que mencionan orden de compra 81, oferta 72, adjudicación 48, orden de pago 17 — **no hay tipo documental** para ninguna | tarea de Codex (7a) |
| R6 | El detector de tablas encuentra tablas en **41 fojas** de todo el legajo | tarea de Codex (7a) |
| R7 | Los identificadores exactos casi no aparecen en el OCR real: «ORDEN DE COMPRA N°» en 8 fojas de 81, números de factura en 0; el CUIT sí (37 distintos, 10 repetidos) | tarea de Codex (7b) |
| R8 | Nunca corrieron en producción tablas, entidades, menciones, cronología ni relaciones (todas en 0) | se aplican con «Actualizar análisis» |

**Actualización completa sobre la copia de Claude** (con `fc291c5`): 42 minutos, 0 errores;
1.628 fojas leídas (340 de OCR nuevo, 1.288 reutilizadas), 1.628 clasificadas, 61 tablas
con 3.015 celdas, 644 menciones, 36 entidades, 5 hechos de cronología, 0 relaciones.

**Máquina de desarrollo:** a la madrugada del 22/09 quedaban 0,5 GB de RAM libre de 7,7 y el
sistema detuvo el lanzamiento programado de Codex por falta de memoria. No se relanzó sin
pedido de Roberto.

### Backend 7a de Codex, sobre el legajo real (22/09)

Codex dejó hecho —sin cuota para cerrar ni informar— la detección de tablas por bloque, los
tipos de una contratación, el esquema 26, los renglones y la comparación de precios, con
37 pruebas. Claude corrió la suite, lo commiteó por él (`1941561`) y lo probó sobre una
copia del legajo real con todas las fojas leídas:

| # | Hallazgo (cantidades) | Estado |
|---|---|---|
| R13 | 2 archivos fallaban con «FOREIGN KEY constraint failed»: piezas que eran facturas pasaron a órdenes de compra sin extractor y sus campos se borraban sin sus normalizaciones | corregido (`7fa1554`) |
| R14 | 13 fojas con «DOCUMENTO NO VÁLIDO COMO FACTURA» (remitos): 0 bien antes, 7 con 7a | corregido (`4f932d4`): la leyenda manda |
| R15 | Tablas por bloque: de 61 a 859, pero 357 eran ruido (< 15 % legible) | corregido (`88ab54b`): 558, ninguna de ruido, las 82 con importes se conservan |
| R16 | 17 renglones, **ninguno con precio unitario**: las planillas reales salen partidas o con columnas fundidas por las rayas que el OCR lee como «\|» | pendiente, para Codex |
| R17 | Tipos nuevos: 37 órdenes de compra, 13 órdenes de pago, 31 presupuestos; las resoluciones pegadas se reducen con la regla de marcas de cuerpo | comprobado |

**Migración de producción ensayada** sobre una copia intacta del respaldo: esquema 25 → 26,
ninguna fila cambió, `integrity_check` ok, 0 referencias rotas, no migra dos veces.

**Despliegue:** hacer push de la rama principal despliega en Render (la instancia servía
el código de `172c5cf` minutos después de ese push). Las pantallas de contrataciones y
hallazgos, cuyo backend es la 7b, dicen «todavía no disponible» en vez de un error.

## Ronda final de rediseño, segunda sesión (23/09/2026)

**Ramas.** Integración: `claude/prompt-maestro-documental-dwhk59` (local; **no se empuja**:
un push ahí despliega en Render). Copia remota de trabajo: `claude/rediseno-integral`.
Codex: `codex/ronda-final-backend` (worktree `AppUFIL-codex-next`, integrado). Gemini:
`gemini/contrataciones-interfaz` (worktree `AppUFIL-gemini`, ronda 5 en curso).

**Codex.** Retomó su paquete 1 (paginación, agregados, ausencias) y lo terminó como tarea 8
hasta quedarse sin cuota otra vez: **sin cuota hasta el 26/09 21:17**. Claude commiteó e
integró su trabajo y escribió `docs/BACKEND_RONDA_FINAL.md` con sus mediciones.

**El legajo real, recalculado.** La copia `ronda-final` estaba calculada con código viejo.
Recalculada con el código vigente (el anterior a Codex y el integrado dan idéntico): 20
contrataciones con documentos (antes 124, 113 de una sola etapa), 117 precios utilizables
(antes 59), 46 hallazgos. Copia de QA: `AppUFIL-corpus-real\recalculado\`. **Producción
necesita «Actualizar análisis» después del próximo despliegue.**

**Gemini.** Se lanza con `agy.exe -p … --mode accept-edits --sandbox --add-dir <worktree>
--add-dir C:\Users\rober\AppUFIL\.git --add-dir <copia del corpus>`: sin el `.git` del repo
principal el sandbox no ve el worktree; `--dangerously-skip-permissions` lo bloquea el
clasificador de permisos. La ronda 4 se perdió porque su agente principal esperó 30 min a
subagentes en segundo plano y salió sin integrar; en la 5 re-codificó `app.js` entero
(`&oacute;`) y commiteó un archivo que no parseaba. Reparado; relanzado con reglas duras.
Antes de integrar cualquier commit suyo: `python herramientas/qa/revisar_commit_web.py
../AppUFIL-gemini <desde>`.

**QA.** `herramientas/qa/barrer.py` (todas las pantallas, 1920 y 1366, `--completa`,
`--tema`, `--extra`) y `--modo flujo` (el recorrido de una persona, sólo con clics, que
pasa completo en las dos resoluciones). `comparar.py` para antes/después.

**Lo que hizo Claude en la interfaz:** Resumen (qué hacer ahora, plata por etapa), ficha de
contratación, Hallazgos (lista revisable), Comparación de precio (comparación floja apagada,
signo), Facturado contra contratado sobre el contrato nuevo, ficha de proveedor,
`tablaServidor`, nombres de contratación por pieza, enrutador con consulta, enlaces con
color, escala tipográfica y radios de vuelta a los tokens. En el núcleo: una referencia a
cien veces o más del precio deja la comparación en dudosa.

### Cierre de la segunda sesión (23/09/2026, noche)

- **Suite:** 955 pruebas, 0 fallos. **Recorrido de usuario** (`--modo flujo`): completo
  a 1366 y 1920. **Barrido de las 41 pantallas:** ninguna con error ni desborde.
- **Gemini, ronda 5:** integrada (`8de6e53`) y corregida por Claude: CSS triplicado,
  funciones duplicadas, reglas del sistema, Buscar (contrato inventado: toda búsqueda daba
  «sin coincidencias»), Fojas (perdió trabajo/apartadas), Personas y Sin reconocer.
  Gemini fue detenido por el sistema por falta de memoria (1,6 GB libres de 7,7); su
  trabajo sin commitear (una reescritura de Cronología que no parseaba) quedó en un stash.
- **Codex:** sin cuota hasta el 26/09 21:17.
- **Backend corregido al integrar:** la búsqueda devolvía una foja una vez por cada
  documento de su archivo (161 veces en el PDF grande); `/api/archivos` y `/api/consulta`
  paginados habían perdido claves.

**Pendientes reales**
1. **Cola de revisión** sin rediseñar (904 monoespaciados, 270 botones): la versión de los
   subagentes de Gemini estaba rota y no se integró.
2. **Todas las fichas** (`#/entidades`) sigue larga (10.589 px): tres listas apiladas. El
   camino del usuario ya no pasa por ahí (Proveedores abre `#/proveedores`).
3. **Vista de documento:** abre con un bloque que lista los 161 hermanos del PDF.
4. **Ruido en la cola:** 13 «fecha de fin» de facturas (campo sin uso en comprobantes) y 49
   campos de contratos de obra con perfil de contrato de personal.
5. Contratos y Facturas y recibos siguen siendo listas del dominio de contratos de personal.
6. **Producción:** después del despliegue, «Actualizar análisis» (sin OCR nuevo).
