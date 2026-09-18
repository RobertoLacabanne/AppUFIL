# Evolución documental de AppUFIL

Arquitectura, decisiones, estado y pendientes del carril que permite que AppUFIL crezca:
que un documento cargado hace un año pueda recibir una capacidad incorporada hoy, sin
volver a subirlo y sin repetir lo que cuesta horas.

---

# 1. El problema, dicho con precisión

AppUFIL va a recibir documentación durante años. Cada tanto va a aprender algo que antes
no sabía: un tipo documental nuevo, un extractor mejor, otra forma de leer una tabla.
Cuando eso pasa, los PDF que ya están adentro tienen que poder aprovecharlo.

Hasta el commit `2f875ae`, no podían. La razón es una sola línea de criterio repetida en
todo el pipeline: **se usaba la existencia de una fila como señal de que el trabajo
estaba hecho.**

## Los centinelas de existencia que había

| Dónde | Qué preguntaba | Qué pasaba |
|---|---|---|
| `ufil/trabajo.py:126` | `NOT EXISTS (SELECT 1 FROM lectura WHERE pagina_id = p.id)` | Una página con cualquier lectura, de cualquier versión de Tesseract y con cualquier configuración, se consideraba leída para siempre. Mejorar el OCR no releía nada. |
| `ufil/capa1_texto.py:353` | lo mismo, al armar el lote | Idem. |
| `ufil/capa0_ingesta.py:118` | `SELECT sha256 FROM archivo WHERE sha256=?` | Correcto: el original es inmutable. Es el único caso donde la existencia sí alcanza. |

Y al revés, en la extracción no había centinela ninguno: `ufil/trabajo.py:146` corría
`extraer_documento` sobre **todos** los archivos en cada procesamiento, borrando y
rehaciendo todo. O sea que el sistema tenía las dos formas del mismo defecto: repetía
siempre lo que podía haber reutilizado, y nunca rehacía lo que sí había que rehacer.

## Qué resultados tenían versión, antes

Uno solo, y a medias: `lectura.version` guarda la versión del motor
(`ufil/capa1_texto.py:194`, `_VER_TESS`), pero **nunca se la leía para decidir nada**.
Era un dato de auditoría, no un criterio.

Sin ninguna versión ni firma de configuración: `palabra`, `pagina.clasificacion`,
`pagina.huella`, `documento` (o sea la segmentación), `campo`, `normalizacion`,
`persona` / `documento_persona`, `cotejo_numero`, `interpretacion` y el índice
`pagina_texto`.

---

# 2. El defecto grave: una corrección que se muda de documento

Es lo peor que encontró el relevamiento, y no estaba a la vista.

`revision_humana` tiene clave primaria `(sha256, orden, campo)`. `orden` es la posición
de la pieza adentro del archivo —1ª, 2ª, 3ª— y **se recalcula en cada reproceso**
contando los tramos que salieron de la clasificación (`ufil/capa2_extraccion.py`,
`enumerate(tramos, start=1)`). O sea que `orden` no identifica a la pieza: identifica a
un lugar en una fila que se rearma sola.

El día que el sistema aprende un tipo documental nuevo —que es **exactamente** lo que
este incremento viene a habilitar— una foja que antes era `continuacion` pasa a ser una
pieza propia, todas las de atrás se corren un lugar, y `reaplicar_revisiones` toma la
corrección que una persona hizo sobre la 2ª pieza y la aplica sobre la que ahora ocupa
ese lugar.

No es una hipótesis. Está reproducido en
`pruebas/test_actualizacion.py::UnaCorreccionNoSeMudaDeDocumento`. Con el código
anterior:

```
orden 1 contrato_obra  foja 1  monto=None
orden 2 recibo         foja 2  monto=$5.000,00  estado=corregido  por=perez.ana   <-- no es suyo
orden 3 factura        foja 3  monto=$ 1.000,00 estado=automatico_alta            <-- perdió la suya
```

Lo que lo vuelve grave es lo que pasa después: el valor entra con `estado='corregido'`,
`confianza=1.0` y `ruta='humano'`, así que **pasa los tres filtros de firmeza de
`v_contrato`** y se suma a los totales como dato verificado por una persona. Un error
que el sistema presenta con la máxima autoridad que tiene.

---

# 3. Lo que se construyó

## `ufil/versiones.py` — qué produjo cada cosa

Un registro de las etapas que **hoy existen en el código** (no las quince que enumera el
pliego: registrar etapas vacías sería decir que el sistema versiona algo que no hace).
Cada etapa lleva:

- `version` — un entero que sube una persona cuando cambia el algoritmo a propósito;
- `firma()` — una huella de la configuración que de verdad altera el resultado;
- `depende_de` — de qué etapas se alimenta;
- `caro` — si rehacerla cuesta horas;
- `adopta` — si, cuando no tiene sello, se adopta lo que ya está en vez de rehacerlo.

Las dos primeras juntas son el **sello**. Un resultado con otro sello está viejo.

### La decisión que más importa: cómo se calcula cada firma

Hay dos maneras de saber que un algoritmo cambió, y se pagan distinto:

- **Por configuración declarada** (idioma del OCR, DPI, versión del motor). Es precisa:
  no se dispara porque alguien tocó un comentario.
- **Por huella del código fuente del módulo.** Atrapa cualquier cambio real, incluido el
  que nadie se acordó de declarar, pero también se dispara con un comentario.

**La lectura usa la primera. Todas las demás, la segunda.** El motivo es asimétrico y
vale escribirlo: sobre un acervo grande, releer por un cambio que no cambia nada cuesta
horas de máquina y es exactamente lo que este trabajo existe para evitar. En una etapa
que cuesta segundos el riesgo que importa es el opuesto —que una mejora quede sin
aplicarse y nadie se entere— así que ahí conviene equivocarse por rehacer de más.

## `ufil/actualizacion.py` — qué quedó viejo, y rehacerlo

- `plan(cx, forzar=())` — **no escribe nada**. Es lo que se muestra antes de ejecutar.
- `desactualizadas_por_etapa(cx, forzar=())` — lo mismo pero con identificadores, para
  ejecutar. Están separadas a propósito: mostrar no puede tener el efecto de nada.
- `invalidar(cx, etapa)` — marca la etapa y **sólo** lo que depende de ella.
- `aplicar(cx, ...)` — rehace lo viejo, sellando unidad por unidad para que cortar y
  reanudar no repita.
- `reasociaciones(cx)` — las revisiones que necesitan que una persona decida.

## El anclaje de las revisiones humanas

`revision_humana` guarda ahora **dónde estaba lo que la persona miró**: foja, recuadro
del campo, tramo de la pieza y tipo, en el momento de revisar
(`ufil/aplicar_revision.py`). Las páginas de un PDF no se mueven, así que la foja
aguanta la resegmentación y el recuadro desempata cuando dos piezas comparten foja.

`reaplicar_revisiones` (`ufil/capa2_extraccion.py`) pasó de correr pieza por pieza, a
medida que se creaban, a correr **una vez por archivo con todas las piezas ya creadas**.
El cambio no es de forma: mirando una pieza por vez no hay manera de darse cuenta de que
dos revisiones caen en la misma, o de que una quedó sin dueño. Hay que ver el archivo
entero para poder decir «esto no se puede decidir solo».

Y cuando no se puede decidir, **no se aplica**: queda `estado='requiere_reasociacion'`
con su motivo en castellano. Perder trabajo humano es malo; aplicarlo en silencio al
documento equivocado es peor.

## Compatibilidad hacia atrás

Una base que ya venía trabajándose no pierde nada:

1. Las columnas nuevas se agregan por `ALTER TABLE` (`COLUMNAS_AGREGADAS` en
   `ufil/db.py`), nunca recreando la tabla: un `DROP` ahí borraría las revisiones, que
   es lo único que no se puede volver a generar.
2. `_anclar_revisiones_viejas` (`ufil/db.py`) les aprende el anclaje a las revisiones
   que se hicieron antes de que existiera. **Se hace en la migración y no más tarde a
   propósito**: en ese momento la base todavía no se resegmentó, así que la pieza que
   ocupa el `orden` N sigue siendo la que la persona miró. Es la última oportunidad de
   saberlo sin adivinar.
3. El OCR ya hecho se **adopta** en vez de releerse, y se lo muestra como `heredado`:
   se adoptó lo que había, que no es lo mismo que haber comprobado que coincide. La
   pantalla tiene que decir cuál de las dos cosas es.
4. Una revisión vieja que no se pudo anclar se sigue aplicando por posición **sólo si la
   pieza que ocupa esa posición quedó igual** (mismo tramo, mismo tipo). Si cambió, se
   marca para reasociar.

---

# 4. Lo que se comprobó, con números

Sobre corpus sintético generado con `herramientas/generar_fixtures.py` (6 contratos,
10 fojas, 200 DPI), con Tesseract 5.4.0 y OCR real:

| | |
|---|---|
| Lectura inicial (OCR de las 10 fojas) | **16,6 s** |
| Actualización incremental posterior | **1,3 s**, 0 fojas releídas, 10 reutilizadas |
| Aparece un extractor nuevo | **1,4 s**, 0 fojas releídas, 6 archivos re-analizados |
| Revisión humana | conservada: `$123.456,78 · corregido · perez.ana` |

Con el extractor nuevo, lo que quedó **vigente y no se tocó**: la lectura (lo caro), la
clasificación de fojas —un perfil no cambia qué es cada foja— y el índice de búsqueda,
que se apoya en la lectura y no en la extracción. Eso es la invalidación selectiva
funcionando: no es que se rehaga menos, es que se rehace lo que corresponde.

---

# 5. Lo que NO hace todavía, y hay que decirlo

**Cinco etapas se contabilizan por separado pero se ejecutan juntas.** Clasificación,
segmentación, cotejo, extracción y normalización las hace hoy una sola función
—`capa2_extraccion.extraer_documento`— en una sola pasada por archivo. Si cualquiera de
las cinco queda vieja, se rehacen las cinco para ese archivo. No es grave (las cinco
juntas son segundos, contra horas del OCR) pero es una diferencia real entre lo que el
sistema informa y lo que ejecuta. La contabilidad ya está lista para cuando se separen.

**El alcance de la lectura es la foja, pero se ejecuta por archivo.** Invalidar una sola
foja hace que se relea ese archivo.

**Faltan etapas que el pliego §8 enumera y el código todavía no tiene**: layout,
foliatura, tablas, relaciones y cronología. No están registradas porque registrarlas
vacías sería decir que se versionan. Agregarlas cuando existan es una línea en
`ETAPAS`.

**No se probó sobre los PDF reales de Vialidad ni sobre la instalación con los nueve
archivos ya cargados**: no son accesibles desde este entorno de desarrollo. Lo medido es
corpus sintético. Queda como prueba pendiente.

---

# 6. Próximos pasos, en orden

1. **Separar de verdad las cinco etapas fusionadas**, empezando por clasificación y
   segmentación, que son las que más cambian cuando aparece un tipo documental nuevo.
2. **Resolver las reasociaciones desde la interfaz**: hoy se pueden listar, pero no hay
   todavía una pantalla donde una persona diga a qué pieza corresponde cada una.
3. **Probar sobre el acervo real** e informar los tiempos con volumen de verdad
   (500, 2.000, 5.000 fojas).
4. **Registrar las etapas que faltan** a medida que se implementen.
