# Navegación final de AppUFIL — decisión de arquitectura de información

Decidido por Claude en la ronda final de rediseño (22/09/2026). Gemini propone el
aspecto; esta es la estructura. Se aplica sobre el resultado integrado, después de
traer el trabajo de Gemini y de Codex.

## El problema que resuelve

La barra lateral tiene hoy **trece secciones de primer nivel**, ordenadas por el orden
histórico en que se fueron implementando: Resumen, Contrataciones, Ítems y precios,
Proveedores, Hallazgos, Documentos, Cronología, Relaciones, Búsqueda, Colecciones,
Informes, Revisión, Sistema. Trece entradas planas no son una jerarquía: son una lista.
Y el orden no le dice nada a quien trabaja, porque responde a cómo se construyó el
sistema y no a lo que la persona vino a hacer.

Además hay cosas mezcladas de naturalezas distintas. «Relaciones» y «Cronología» son
primer nivel, pero «Foliatura» y «Tablas» —que son trabajo de revisión del mismo
calibre— están enterradas dentro de «Documentos». «Consultas» está dentro de
«Hallazgos» cuando es una herramienta de búsqueda. «Cargar escaneos» está dentro de
«Documentos» cuando es administración del legajo.

## La estructura

Cinco grupos, nombrados por la tarea del usuario y no por el módulo técnico. El grupo
es un rótulo, no un destino: no se navega a un grupo.

### INVESTIGACIÓN — «¿qué pasó en esta contratación?»

| entrada | ruta | nota |
|---|---|---|
| Resumen | `#/panel` | qué hay y qué necesita atención |
| Contrataciones | `#/contrataciones` `#/contratacion` | el procedimiento reconstruido |
| Ítems y precios | `#/precios` `#/renglon` | la tabla y el comparador |
| Proveedores | `#/proveedores` `#/proveedor/<id>` `#/personas` `#/entidades` `#/entidad` `#/persona` | empresas proveedoras (listado y ficha), personas, todas las fichas |
| Hallazgos | `#/hallazgos` | diferencias detectadas, con su evidencia |
| Comparaciones | `#/cruce` `#/superposiciones` `#/numeros` `#/interpretacion` | los cruces que hoy cuelgan de Hallazgos |
| Cronología | `#/cronologia` | línea temporal |

«Hallazgos» queda con **una sola cosa adentro**: los hallazgos revisables. Los cruces
(facturado contra contratado, superposiciones, números escritos dos veces,
interpretación) pasan a «Comparaciones», que es lo que son: análisis transversales que
*producen* hallazgos, no hallazgos ellos mismos.

### DOCUMENTACIÓN — «¿dónde está el papel?»

| entrada | ruta |
|---|---|
| Documentos | `#/piezas` (todos, por tipo) `#/contratos` `#/comprobantes` `#/fojas` `#/conjuntos` `#/documento` |
| Búsqueda | `#/buscar` `#/guardadas` `#/consultas` |
| Colecciones | `#/colecciones` `#/coleccion` |

`#/consultas` se muda acá desde «Hallazgos»: es una herramienta de búsqueda.

### REVISIÓN — «¿qué tengo que decidir?»

| entrada | ruta | contador |
|---|---|---|
| Cola de revisión | `#/cola` | `a_revisar` |
| Identidades | `#/identidad` | `fusiones` |
| Relaciones | `#/relaciones` | |
| Foliatura | `#/foliatura` | |
| Tablas | `#/tablas` | |
| Todavía sin reconocer | `#/sin-reconocer` | |
| Quedaron afuera | `#/afuera` | `afuera` |
| Revisiones desplazadas | `#/reasociaciones` | |
| Trabajo del equipo | `#/equipo` | |

Éste es el cambio de fondo. Todo lo que le pide una decisión a una persona vive en un
solo lugar, y el grupo lleva la suma de lo pendiente. Hoy «Foliatura», «Tablas» y
«Todavía sin reconocer» están dentro de «Documentos», donde nadie las busca cuando se
sienta a revisar, y «Relaciones» está sola en primer nivel.

### SALIDA — «¿qué me llevo?»

| entrada | ruta |
|---|---|
| Informes | `#/informes` |

Exportaciones no tiene pantalla propia hoy: vive como acciones dentro de Informes y de
las listas. Si la ronda le hace una, entra acá. **No se crea una entrada vacía para
que el menú parezca completo.**

### ADMINISTRACIÓN — «el legajo y el sistema»

| entrada | ruta |
|---|---|
| Cargar escaneos | `#/ingesta` |
| Legajos | `#/legajos` |
| Actualizar análisis | `#/actualizacion` |
| Papelera | `#/papelera` |
| Estado del sistema | `#/salud` |
| Cómo funciona | `#/como-funciona` |

Todo lo técnico que Fiscalía no necesita en el trabajo cotidiano —pipeline, versiones,
diagnóstico, etapas, métricas— vive detrás de «Estado del sistema», no desparramado.

«Acerca del sistema» se queda en el pie de la barra, donde está: no es una tarea.

## Contrato de datos

`SECCIONES` pasa de un arreglo plano a un arreglo de grupos:

```js
const SECCIONES = [
  {grupo: 'Investigación', entradas: [
    {id: 'panel', rotulo: 'Resumen', hash: '#/panel'},
    ...
  ]},
  ...
];
```

Cada entrada conserva la forma de hoy: `{id, rotulo, hash, items[], tambien[], cuenta}`.
`seccionDe()` y `pintarNav()` recorren un nivel más; nada más cambia.

## Contrato de DOM para el aspecto (Gemini)

El marcado se mantiene compatible con lo que ya existe, con **un** envoltorio nuevo:

```html
<nav class="nav-lateral">
  <div class="nav-grupo">
    <h2 class="nav-grupo-rotulo">Investigación</h2>
    <div class="grupo"> … lo de hoy, sin cambios … </div>
    …
  </div>
  …
</nav>
```

`.grupo`, `.cabeza`, `.activo`, `.apagado`, `.cuenta`, `.txt` y `.ico` **no cambian de
nombre ni de significado**, para que el trabajo de Gemini sobre la barra siga
sirviendo. Lo único que hay que estilar nuevo es `.nav-grupo` y `.nav-grupo-rotulo`,
que es el rótulo del grupo: versalitas, tinta apagada, sin caja, sin borde, y que no
compita con las entradas.

A 1366×768 la barra tiene que seguir entrando sin desplazamiento propio: si no entra,
el rótulo de grupo es lo primero que se comprime.

## Un cambio de texto que no es cosmético

`TITULOS['#/renglon']` dice hoy **«Posible sobreprecio»**, y el `<h1>` de esa pantalla
dice «Análisis de precio». El título viola la regla de producto que no se negocia: la
aplicación **no concluye**. Pasa a decir **«Comparación de precio»**, y la pantalla
presenta la evidencia —precio analizado, referencias, mediana, diferencia absoluta,
diferencia porcentual, calidad de la comparación, por qué son comparables, fuentes—
sin calificar el resultado. La conclusión la escribe Fiscalía.

## Agregado el 23/09/2026

- **Proveedores** abre `#/proveedores`: las empresas del legajo por CUIT, las que más
  documentos tienen primero, y cada una lleva a `#/proveedor/<id>` (qué se le compró, a
  qué precio, cuánto se le ordenó y facturó, qué diferencias hay). «Todas las fichas»
  (`#/entidades`) queda como tercera entrada del grupo.
- **Documentos** abre `#/piezas`: todas las piezas por tipo, con chips y paginación del
  servidor. Contratos y Facturas y recibos siguen como entradas del grupo.
- El enrutador compara sin la consulta cuando una ruta no la contempla: `#/precios?desde=50`
  llega a Ítems y precios.
