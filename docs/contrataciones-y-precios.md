# Contrataciones y precios — arquitectura y contrato

Desde el 21/09/2026 el objetivo analítico central de AppUFIL es asistir investigaciones de
posibles sobreprecios y otras anomalías en licitaciones, compras y contrataciones
públicas. La aplicación sigue aceptando cualquier documentación, pero tiene que saber
para qué la lee:

**reconstruir una contratación → comparar precios → relacionar documentos → detectar
inconsistencias → mostrarlas con su fuente → permitir que Fiscalía las verifique.**

La pregunta que tiene que contestar bien: *con miles de fojas de una contratación,
¿encuentro rápido qué se compró, a quién, cuánto, a qué precio, qué otras ofertas hubo,
cuánto se facturó y se pagó, cómo se compara con otras referencias, y de qué documento,
foja y región salió cada dato?*

Este documento es el contrato entre Claude (semántica e integración), Codex (backend) y
Gemini (interfaz). Se escribe antes de programar; si algo no se puede cumplir, se dice
acá, no en el código.

---

## 1. La aplicación no concluye

AppUFIL no dice «hubo sobreprecio», «fraude», «direccionamiento», «delito» ni
«irregularidad». Identifica y ordena diferencias, relaciones, secuencias, coincidencias,
divergencias, valores atípicos, faltantes e inconsistencias, y lleva a la persona al papel
que respalda cada dato.

**Vocabulario.** La interfaz y la API hablan de *diferencia detectada*, *comparación*,
*posible anomalía*, *requiere revisión*, *coincidencia temporal*. «Posible sobreprecio» se
admite como nombre de pantalla porque dice «posible». Quedan prohibidos como afirmación
del sistema: *fraude*, *delito*, *direccionamiento*, *irregular/irregularidad*,
*ilícito*, *culpable*, *sospechoso*, *responsable* (en sentido de atribución), y
*sobreprecio* sin *posible*. `ufil/comparabilidad.py` expone la lista
(`TERMINOS_PROHIBIDOS`) y cada catálogo de textos que sale del backend se prueba contra
ella.

Los informes describen. Las conclusiones las escribe Fiscalía.

---

## 2. El modelo

```
EXPEDIENTE ─ PROCEDIMIENTO (contratación) ─ OBJETO
                 │
     etapas: pedido → presupuesto → pliego → apertura → oferta → cuadro comparativo
             → dictamen → adjudicación → orden de compra → remito → factura
             → orden de pago → pago
                 │
     renglones de precio (uno por fila con precio, en cualquier etapa)
                 │
     ítem canónico  ← asignación renglón→ítem con su comparabilidad
                 │
     comparaciones (derivadas)  →  hallazgos (con revisión humana)
```

No todos los casos tienen todas las etapas. **La aplicación muestra qué existe y qué
falta**: una etapa sin documentos es un dato, no un error.

### 2.1 Contratación

Un procedimiento de compra o contratación. Campos: `expediente` (literal y, cuando se
resuelve, la entidad de clase `expediente`), `organismo`, `procedimiento` (licitación
pública, licitación privada, concurso de precios, contratación directa, desconocido…),
`objeto`, `origen` (`sistema` | `humano`), `quien`. Se reconstruye agrupando documentos
por número de expediente, referencias cruzadas (número de orden, de comprobante), CUIT del
proveedor y conjunto documental; **la agrupación que propone el sistema es una propuesta**
hasta que una persona la confirma, como las relaciones.

`contratacion_documento` vincula cada pieza con su etapa (`etapa`, `origen`, `estado`
propuesta|confirmada|rechazada, `confianza`). **El catálogo de etapas es extensible y lo
sirve el backend**: la interfaz no escribe la lista.

### 2.2 Renglón de precio

Una fila con precio, tal como está en un documento concreto. Es la unidad sobre la que se
compara. Guarda **las dos descripciones**:

| campo | qué es |
|---|---|
| `desc_literal` | tal como está en el papel, sin tocar. **Nunca se reemplaza.** |
| `desc_norm` | normalizada para comparar («Tensor móvil de correa Poly-V») |
| `categoria`, `marca`, `modelo`, `especificaciones` | lo que se pudo identificar; `NULL` = no se sabe |
| `unidad_literal`, `unidad_norm` | «u.», «unid» → `unidad`; «lt» → `litro` |
| `cantidad` | literal y valor |
| `precio_unitario`, `subtotal` | literal y valor decimal exacto |
| `moneda` | `ARS`, `USD`… o `NULL` si el papel no lo dice |
| `iva` | `incluido` \| `discriminado` \| `NULL` (no se sabe) |
| `condiciones` | flete, instalación, garantía, plazo, cuando el papel las dice |
| `fecha_precio` | fecha y de dónde sale (campo, evento o la del documento) |
| `proveedor` | entidad (clave fuerte: CUIT) y la mención literal |
| `documento_id`, `etapa`, `contratacion_id` | dónde vive |
| anclaje | `tabla_id`, `fila`, y las celdas (`tabla_celda.id`) de cada valor |
| `metodo`, `version`, `confianza`, `estado` | como un campo (`ufil/confianza.py`) |

**Nunca se reemplaza ausencia por cero.** Un precio que no está es `NULL` con motivo. Un
precio unitario que falta pero se puede derivar de subtotal y cantidad se guarda como
**derivado**, con la fórmula y las dos celdas de las que sale.

Importes: decimal exacto (`Decimal` en Python, texto canónico `"180000.00"` en la base y
en la API). Nunca `float`.

### 2.3 Ítem canónico y asignación

`item` es «qué es esto» independientemente de quién lo vendió: nombre normalizado,
categoría, marca, modelo, especificación clave, unidad. `renglon_item` asigna un renglón
a un ítem con su **estado de comparabilidad** (§3) y sus motivos. El sistema propone; una
persona confirma o rechaza, y su decisión se conserva al reprocesar, anclada al renglón
por su celda y su pieza, igual que las revisiones de campos.

### 2.4 Hallazgo

Ver §6. Es lo único que el sistema «señala», y siempre con qué, datos, fuentes, cálculo,
confianza y estado de revisión.

---

## 3. Qué se puede comparar

Regla crítica: **dos productos no son comparables porque el texto se parezca.** La
comparabilidad de un renglón A (el analizado) con un renglón B (la referencia) es una de:

| estado | significa |
|---|---|
| `fuerte` | mismo producto: descripción normalizada equivalente, misma unidad, misma moneda, marca y modelo coinciden (o faltan en los dos y la especificación coincide), mismo tratamiento del IVA |
| `probable` | muy parecido, sin nada que lo contradiga, pero falta un atributo de un lado (marca, modelo, unidad, IVA o moneda sin informar) |
| `dudoso` | parecido a medias, o condiciones comerciales distintas o desconocidas que pueden explicar la diferencia (flete, instalación, garantía, IVA distinto) |
| `no_comparable` | algo lo contradice: unidad distinta, moneda distinta, marca distinta, modelo distinto, categoría distinta, o descripción demasiado distinta |

Reglas, en orden:

1. **Decisión humana manda.** Si una persona confirmó que A y B son el mismo ítem, es
   `fuerte` (se registra quién). Si dijo que no, es `no_comparable`.
2. **Bloqueantes → `no_comparable`**: unidad normalizada conocida en los dos lados y
   distinta; moneda conocida y distinta; marca conocida y distinta; modelo conocido y
   distinto; categoría conocida y distinta; similitud de descripción menor que
   `SIMILITUD_MINIMA`; y **números distintos en la descripción** («bomba 1 HP» contra
   «bomba 2 HP», «cable 2,5 mm» contra «cable 4 mm»): los números son la especificación,
   y como texto se parecen demasiado para confiar en la similitud. Si sólo uno de los dos
   trae números, la especificación *falta* y no puede ser `fuerte`.
3. **`fuerte`** exige: descripción normalizada igual o similitud ≥ `SIMILITUD_FUERTE`,
   unidad y moneda conocidas e iguales, marca y modelo iguales o ausentes en los dos,
   IVA conocido e igual, y ninguna condición comercial conocida de un solo lado.
4. **`dudoso`**: similitud entre `SIMILITUD_MINIMA` y `SIMILITUD_PROBABLE`; o IVA
   conocido y distinto; o flete, instalación o garantía presentes de un lado y no del
   otro.
5. **`probable`**: el resto — parecido y nada lo contradice, pero falta algo.

Cada resultado trae `motivos`: una lista `{atributo, a, b, efecto}` con `efecto` en
`coincide | difiere | falta | bloquea`. **La pantalla muestra los motivos**: «comparable
fuerte» sin decir por qué no sirve para verificar.

**Una comparación dudosa nunca se presenta como conclusión firme** ni alimenta un
hallazgo de confianza alta.

La cantidad no decide la comparabilidad —se comparan precios unitarios— pero una
diferencia de escala grande (1 unidad contra 1.000) se informa como motivo, porque el
precio por volumen es una explicación posible.

## 4. Niveles de la referencia

La calidad de una referencia no es la misma siempre. Para A analizado y B referencia:

| nivel | cuándo |
|---|---|
| **A** | comparabilidad `fuerte`, **misma contratación**, documento primario (oferta, adjudicación, orden de compra, factura, remito, orden de pago), fechas a ≤ `DIAS_CERCANA` |
| **B** | `fuerte`, documento primario, fechas a ≤ `DIAS_PROXIMA` — típicamente **otra contratación pública**; también la misma contratación con fechas más separadas que A |
| **C** | `fuerte` o `probable`, B es un **presupuesto o cotización**, fechas a ≤ `DIAS_CERCANA` |
| **D** | `probable` (similar, no idéntico), fechas a ≤ `DIAS_PROXIMA` |
| **E** | el resto de lo comparable: `dudoso`, fechas más lejanas, fecha desconocida, o una referencia cargada a mano sin documento |

`no_comparable` no es referencia de ningún nivel: se lista aparte, con el motivo, para que
se vea que se descartó y por qué.

**Qué cuenta como referencia.** Una referencia tiene que ser *independiente* del precio
analizado. Para un renglón de la contratación K, **no** son referencias los renglones de
las etapas de ejecución de la misma K (adjudicación, orden de compra, remito, factura,
orden de pago, pago): son la misma compra, y se comparan entre sí por
`facturado_vs_adjudicado` y `facturado_vs_entregado`, no como mercado. **Sí** lo son las
ofertas de K —de cualquier oferente, incluido el adjudicado: que alguien ofrezca 104.000
y se le adjudique a 165.000 es exactamente lo que hay que ver—, los presupuestos de K, y
los renglones de cualquier etapa primaria de otras contrataciones.

**Qué renglones se analizan.** Los precios comprometidos o cobrados: los de adjudicación,
orden de compra y factura. Un hallazgo `diferencia_precio` por renglón analizado; la
interfaz los agrupa por ítem.

**Los niveles no se mezclan sin advertencia.** Los estadísticos se calculan por nivel; la
comparación principal usa el mejor nivel disponible con al menos `MIN_REFERENCIAS`
referencias, y si hay que bajar de nivel o juntar niveles, el resultado lo dice en
`advertencias`.

### Umbrales (valores iniciales; los sirve el backend)

| umbral | valor | para qué |
|---|---|---|
| `DIAS_CERCANA` | 90 | «fecha cercana» |
| `DIAS_PROXIMA` | 365 | «fecha próxima» |
| `SIMILITUD_MINIMA` | 0,40 | por debajo, no comparable |
| `SIMILITUD_PROBABLE` | 0,70 | por debajo, dudoso |
| `SIMILITUD_FUERTE` | 0,90 | desde acá puede ser fuerte |
| `MIN_REFERENCIAS` | 2 | para usar la mediana de un nivel sin advertencia |
| `DIFERENCIA_SEÑALABLE_PCT` | 20,00 | para proponer un hallazgo de diferencia de precio |

Son parámetros de trabajo, no verdades: se van a medir contra el corpus real y se ajustan
acá.

## 5. El precio depende de la fecha

Toda comparación conserva **la fecha de cada precio** y de dónde sale. Se informa la
**variación nominal**. No hay ajuste por inflación: si algún día se agrega, es un módulo
explícito con una fuente definida y la pantalla muestra **nominal y ajustado por
separado**, nunca sólo el ajustado.

## 6. Cálculos y hallazgos

### 6.1 Estadísticos

Sobre los precios unitarios de las referencias de un nivel: `n`, mínimo, máximo, media,
mediana, desvío estándar (muestral, n−1; `NULL` con n < 2) y rango intercuartil. Contra el
analizado: diferencia absoluta y porcentual respecto de la mediana, y contra la segunda
mejor oferta cuando es una matriz de ofertas. Porcentaje con dos decimales, redondeo
mitad hacia arriba. Mediana cero o sin referencias: **no hay porcentaje**, y se dice.

Cada resultado trae su **cálculo**: fórmula y operandos, y cada operando su fuente. Un
estadístico que no se puede reconstruir desde las fuentes no se muestra.

### 6.2 Calidad de la comparación

`alta` | `media` | `baja`, con motivos:

- **alta**: nivel A o B, n ≥ `MIN_REFERENCIAS`, todas las referencias `fuerte`, y los
  precios involucrados en estado firme (`ufil/confianza.py`).
- **media**: nivel C o D, o n = 1, o algún precio provisorio.
- **baja**: nivel E, o algún `dudoso`, o precios derivados sin revisar.

### 6.3 Hallazgos

Catálogo inicial (extensible; lo sirve el backend con nombre y explicación neutros):

| tipo | qué detecta |
|---|---|
| `diferencia_precio` | precio unitario por encima de la mediana de referencias en más de `DIFERENCIA_SEÑALABLE_PCT` |
| `facturado_vs_adjudicado` | precio, cantidad, producto, proveedor o total facturado distinto de la orden de compra, o de la adjudicación si no hay orden |
| `facturado_vs_entregado` | cantidad o producto de la factura distinto del remito asociado |
| `subtotal_incorrecto` | cantidad × precio unitario ≠ subtotal (con la cuenta) |
| `total_inconsistente` | suma de subtotales ≠ total impreso |
| `precio_ausente` | renglón sin precio unitario ni forma de derivarlo |
| `documento_faltante` | etapa esperable sin documento (adjudicación sin factura encontrada, factura sin acto de adjudicación encontrado, pago sin factura encontrada) |
| `oferente_unico` | contratación con una sola oferta encontrada |
| `ofertas_identicas` | dos ofertas con los mismos precios renglón por renglón |
| `duplicado_potencial` | misma factura repetida; mismo remito asociado a varias facturas |
| `variacion_compras` | mismo ítem comprado varias veces con una variación grande |
| `secuencia_temporal` | fechas fuera de orden (factura antes de la orden, pago antes de la factura) |
| `coincidencia_temporal` | anotación de agenda con fecha próxima a un acto del expediente — **sin afirmar relación** |

Cada hallazgo:

```python
{"id": int, "tipo": str, "titulo": str,          # neutro: «Diferencia de precio detectada»
 "descripcion": str,                             # qué se detectó, en castellano
 "datos": {...},                                 # los valores involucrados
 "calculo": {"formula": str, "operandos": [{"nombre", "valor", "fuente"}], "resultado": str} | None,
 "fuentes": [Fuente, ...],                       # todo documento involucrado
 "confianza": {"nivel": "alta|media|baja", "motivos": [str]},
 "revision": {"estado": "pendiente|relevante|descartado", "quien", "cuando", "nota"}}
```

**La revisión humana de un hallazgo sobrevive al recálculo**: el hallazgo se identifica
por su tipo y las claves estables de sus fuentes, no por su `id`. Si el recálculo lo hace
desaparecer y tenía revisión, se conserva marcado como `ya_no_se_detecta` en vez de
borrarse.

## 7. Trazabilidad

Todo número de la API viaja con su **fuente**, en una sola forma:

```python
Fuente = {"documento_id": int | None, "sha256": str, "archivo": str,
          "pagina_nro": int, "pagina": {"ancho_pt": float, "alto_pt": float},
          "region": {"x0", "y0", "x1", "y1"} | None,     # en puntos PDF
          "tipo_documento": str | None, "etiqueta": str,  # «Factura 0003-00001234»
          "celdas": [int] | None, "campo_id": int | None}

Monto = {"literal": str | None, "valor": "180000.00" | None, "moneda": str | None,
         "derivado": bool, "formula": str | None,
         "fuente": Fuente | None, "estado": str}          # estado de ufil/confianza.py
```

La interfaz abre la foja con `/pagina?sha=…&nro=…` y dibuja el recuadro en porcentaje de
`pagina.ancho_pt` / `pagina.alto_pt`, como el visor de hoy. **Un dato sin fuente no se
presenta como firme.**

## 8. El pipeline: capacidades nuevas sobre material viejo

Tres etapas nuevas, versionadas en `ufil/versiones.py` como las demás, para que **lo ya
cargado reciba estas capacidades con «Actualizar análisis», sin volver a subir nada**:

| etapa | alcance | depende de |
|---|---|---|
| `renglones` | archivo | `tablas`, `extraccion`, `clasificacion` |
| `contrataciones` | legajo | `renglones`, `entidades`, `cronologia` |
| `hallazgos` | legajo | `contrataciones` |

Cambiar un umbral de §4 cambia la firma de `hallazgos` y desactualiza sólo esa etapa.

## 9. API — incremento 7

Todas las listas paginan con `limite` (por omisión 100, máximo 500) y `desde`, y
devuelven `total`. Los catálogos salen del backend.

| Método | Ruta | Devuelve |
|---|---|---|
| GET | `/api/catalogo/contrataciones` | `{etapas, comparabilidad, niveles, hallazgos, revision, umbrales, terminos_prohibidos}` — cada entrada `{clave, nombre, explicacion}` |
| GET | `/api/precios?q=&item=&proveedor=&contratacion=&etapa=&fecha_desde=&fecha_hasta=&dif_min_pct=` | `{renglones: [Renglon], total, desde, limite}` — la tabla maestra |
| GET | `/api/renglon/<id>/comparacion?niveles=A,B,C` | la pantalla «Posible sobreprecio» (abajo) |
| POST | `/api/renglon/<id>/item` | `{decision: "mismo"\|"distinto", item_id?, crear?: {nombre}}` → la asignación, con quién |
| GET | `/api/contrataciones` | `{contrataciones: [Resumen], total, desde, limite}` |
| GET | `/api/contratacion/<id>` | la ficha (abajo) |
| GET | `/api/hallazgos?tipo=&estado=&contratacion=` | `{hallazgos: [Hallazgo], total, desde, limite}` |
| POST | `/api/hallazgo/<id>/revision` | `{estado, nota}` → el hallazgo actualizado |

```python
Renglon = {"id", "fecha": {"valor", "literal", "fuente"} | None,
           "contratacion": {"id", "nombre"} | None, "expediente": str | None,
           "etapa": str | None,
           "proveedor": {"entidad_id", "nombre", "cuit"} | None,
           "descripcion": {"literal", "normalizada"},
           "item": {"id", "nombre", "comparabilidad"} | None,
           "marca", "modelo",
           "cantidad": {"literal", "valor"} | None,
           "unidad": {"literal", "normalizada"} | None,
           "precio_unitario": Monto, "subtotal": Monto | None,
           "fuente": Fuente, "estado": str,
           "comparacion": {"nivel", "diferencia_pct", "n", "calidad"} | None}

# GET /api/renglon/<id>/comparacion
{"renglon": Renglon,
 "referencias": [{"renglon": Renglon, "nivel": "A".."E",
                  "comparabilidad": {"estado", "motivos": [...]}, "dias": int | None}],
 "excluidas": [{"renglon": Renglon, "motivo": str}],      # no comparables, a la vista
 "estadisticas": {"nivel": "A"|..., "n", "minimo", "maximo", "media", "mediana",
                  "desvio", "rango_intercuartil"} | None,  # importes como texto decimal
 "diferencia": {"absoluta", "porcentual", "contra": "mediana"} | None,
 "calculo": {"formula", "operandos", "resultado"} | None,
 "calidad": {"nivel": "alta|media|baja", "motivos": [str]},
 "advertencias": [str],
 "hallazgo": {"id", "revision"} | None}

# GET /api/contratacion/<id>
{"contratacion": {"id", "nombre", "expediente", "organismo", "procedimiento", "objeto",
                  "origen", "estado"},
 "etapas": [{"clave", "nombre", "presente": bool,
             "documentos": [{"documento_id", "tipo", "fecha", "etiqueta", "fuente"}]}],
 "oferentes": [{"entidad_id", "nombre", "cuit", "adjudicado": bool}],
 "matriz": {"columnas": [{"clave", "titulo", "entidad_id" | None}],   # ofertas, adjudicado, facturado
            "filas": [{"item": {...} | None, "descripcion": {...},
                       "valores": {"<clave de columna>": Monto | None},
                       "menor": "<clave>" | None}]},
 "totales": {"adjudicado": Monto | None, "facturado": Monto | None, "pagado": Monto | None},
 "cronologia": [{"fecha", "etapa", "etiqueta", "fuente"}],
 "hallazgos": [Hallazgo]}
```

Proveedores y personas ya tienen fichas (`/api/entidad/<id>`); sumarles contrataciones,
productos y montos es el incremento 8.

## 10. Reparto del incremento 7

| | Claude | Codex | Gemini |
|---|---|---|---|
| Rama | `claude/contrataciones-precios` (integración) | `codex/contrataciones-backend` | `gemini/contrataciones-interfaz` |
| Worktree | `C:\Users\rober\AppUFIL` | `C:\Users\rober\AppUFIL-codex-next` | `C:\Users\rober\AppUFIL-gemini` |
| Hace | este contrato; `ufil/comparabilidad.py` (§3, §4, §6.2, vocabulario, catálogos) | esquema 26, las tres etapas, extracción de renglones desde las tablas, normalización de ítems, estadísticos (§6.1), reconstrucción de contrataciones, hallazgos, endpoints de §9 | menú por preguntas de investigación, comparador, «posible sobreprecio», ficha de contratación, hallazgos con revisión, abrir dos fuentes lado a lado |

Archivos:

- **Claude:** `ufil/comparabilidad.py`, `pruebas/test_comparabilidad.py`, este documento y
  los documentos vivos.
- **Codex:** `ufil/esquema.sql`, `ufil/db.py`, `ufil/versiones.py`,
  `ufil/actualizacion.py` (sólo para registrar las etapas), módulos nuevos
  (`ufil/renglones.py`, `ufil/contrataciones.py`, `ufil/precios.py`, `ufil/hallazgos.py`),
  en `ufil/servidor.py` sólo el bloque de las rutas nuevas, y sus pruebas nuevas.
  **Usa `ufil/comparabilidad.py` y no reimplementa sus reglas**: si necesita otra regla, la
  pide acá.
- **Gemini:** `ufil/web/*` y sus pruebas nuevas `pruebas/test_*_web*.py`. Programa contra
  §9 con datos simulados: el backend llega después.
- **Nadie:** el resto.

Pruebas mínimas de cada uno: las reglas de §3 y §4, caso por caso, con los motivos
(Claude); un corpus sintético de una contratación completa —pedido, tres presupuestos,
tres ofertas, adjudicación, orden, remito, factura con un precio distinto del adjudicado,
orden de pago— que atraviesa las tres etapas y produce los hallazgos esperados y ninguno
de más, más la reaplicación sobre una base ya cargada sin volver a subir nada (Codex); que
ningún número de las pantallas nuevas salga de otro lado que el JSON, que toda cifra
tenga un enlace a su fuente, y que ningún texto use un término de
`terminos_prohibidos` (Gemini).

## 11. Corpus de aceptación y resultado esperado

`pruebas/corpus_contratacion.py` genera una contratación entera, inventada —organismo,
expediente, proveedores, CUIT y precios—, en doce PDF con texto nativo. Cada documento
tiene encabezado, datos del proveedor, una planilla de renglones y, si corresponde, el
total, como el papel de verdad. `pruebas/test_aceptacion_contratacion.py` la sube por
HTTP, la procesa, actualiza el análisis y verifica, sólo contra la API de §9:

| qué | esperado |
|---|---|
| contrataciones | 1, con el expediente del corpus |
| etapas presentes | pedido, presupuesto, oferta, adjudicación, orden de compra, remito, factura, orden de pago |
| etapas faltantes | entre ellas `pago`: hay orden de pago, no constancia |
| oferentes | los tres; B adjudicado |
| totales | adjudicado `466000.00`; facturado `497000.00` |
| renglones con precio | presupuestos 9, ofertas 9, adjudicación 3, orden 3, factura 3 |
| comparación del renglón 1 de la factura (180.000) | nivel A, n = 3 (las ofertas), mediana `102500.00`, diferencia `77500.00` / `75.61` %; los tres presupuestos como nivel C; la adjudicación y la orden de la misma compra, excluidas con su motivo |
| hallazgos | **exactamente** `diferencia_precio` 3 (renglón 1 de adjudicación, orden y factura), `facturado_vs_adjudicado` 2 (precio del renglón 1 y total), `facturado_vs_entregado` 1 (renglón 3: facturadas 10, remitidas 8), `subtotal_incorrecto` 1 (renglón 2: 4 × 21.000 = `84000.00`, impreso 85.000) |
| revisión | un hallazgo marcado `relevante` sigue `relevante`, con su nota, después de recalcular |

Los renglones 2 y 3 adjudicados quedan a +2,44 % y +1,96 % de la mediana de las ofertas:
**por debajo del umbral, no son hallazgo.** `precio_ausente` sólo aplica a etapas que
llevan precio: un pedido o un remito sin precio no son un faltante.

### Lo que el corpus encontró antes de que hubiera backend

**El detector de tablas no ve una planilla dentro de una foja con otras cosas.**
`ufil/tablas.py` exige que una columna aparezca en el 60 % de los renglones de **toda la
foja**. En una factura o una orden de compra —encabezado, datos del proveedor, planilla de
pocos renglones, total— la planilla no llega a esa proporción, y no se detecta: sobre los
doce PDF del corpus, ninguna planilla salió completa (lo mejor fueron cinco de cuatro
filas por dos columnas, que eran el margen izquierdo). **Sin tablas no hay renglones, y
sin renglones no hay nada que comparar**: arreglarlo es la primera tarea del backend. Las
columnas se tienen que buscar por **bloque de renglones consecutivos**, no por foja,
conservando la desconfianza que hoy impide tomar un párrafo con números por planilla (las
pruebas de `pruebas/test_tablas.py` siguen valiendo).

Riesgo aparte, anotado y no resuelto en este incremento: el blanco mínimo entre columnas
(`MIN_HUECO`, 18 pt) deja afuera encabezados largos y pegados, que son comunes.

### Ajuste al reparto de §10

Codex toma también `ufil/tablas.py` (la detección por bloque, con sus pruebas) y
`ufil/clasificacion.py` (los tipos que faltan para una contratación: pedido o solicitud,
presupuesto, oferta, cuadro comparativo, dictamen o preadjudicación, adjudicación, orden
de compra, orden de pago, constancia de pago o transferencia). Cambiar la clasificación
cambia su firma y desactualiza esa etapa en el material ya cargado, que es lo que se
quiere.
