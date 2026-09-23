# Backend de la ronda final de rediseño

Trabajo de Codex (tareas 8 y su paquete original), integrado por Claude el 23/09/2026.
Codex se quedó sin cuota antes de escribir este documento; los números salen de sus
mediciones (`pruebas/medir_backend_8.py`, `pruebas/medir_consultas_backend_8.py`) y de
la validación que hizo Claude sobre el legajo real después de integrar.

## Contrato de listas

Toda lista larga acepta los mismos parámetros y devuelve la misma forma. Lo resuelve
`ufil/paginacion.py`: cuenta el total en SQL y trae sólo la página pedida.

**Parámetros:** `desde` (entero ≥ 0, por defecto 0), `limite` (1–200, por defecto 50),
`orden` (uno de los campos que acepta cada lista), `sentido` (`asc`|`desc`), `q` (texto,
donde la lista lo admite) y los filtros propios de cada una. Un parámetro inválido
contesta 400 con el motivo; nunca se ignora en silencio.

**Respuesta:**

```json
{"<clave>": [ … sólo la página … ],
 "total": 124, "desde": 0, "limite": 50, "orden": "id", "sentido": "asc",
 "filtros_aplicados": {"estado": "propuesta"}}
```

La paginación **agrega** claves, no saca ninguna de las que ya había (`tipos` en
«sin reconocer», `archivos`/`resumen`/`etiquetas` en fojas, `clases` en cronología…).
Las rutas que devolvían un arreglo lo siguen devolviendo cuando se piden sin
parámetros de paginación.

**Consecuencia para el frontend:** una lista pedida sin `desde/limite` trae la primera
página, no todo. Una pantalla que pagina en el cliente sobre esa respuesta muestra sólo
las primeras 50 filas creyendo que son todas. Las pantallas tienen que pedir la página
al servidor (componente `tablaServidor` en `app.js`).

| ruta | clave | filtros | orden |
|---|---|---|---|
| `/api/contrataciones` | `contrataciones` | `estado`, `procedimiento`, `proveedor_id`, `con_hallazgo`, `etapa_faltante`, `q` | `id`, `nombre`, `estado`, `procedimiento`, `expediente` |
| `/api/hallazgos` | `hallazgos` | `tipo`, `estado_revision`, `confianza_min`, `contratacion_id`, `q` | `id`, `tipo`, `confianza` |
| `/api/precios` | `renglones` | `proveedor_id`, `contratacion_id`, `desde_fecha`, `hasta_fecha`, `con_comparacion`, `con_hallazgo`, `pendiente`, `q` | `id`, `fecha`, … |
| `/api/entidades` | `entidades` (+ `clases`, y la primera página de `sin_resolver` y `propuestas` con su `*_paginacion`) | `clase`, `con_contrataciones`, `q` | `id`, `nombre`, `clase`, `documentos`, `menciones` |
| `/api/entidades/sin-resolver` | `sin_resolver` | `q` | `id`, `clase`, `nombre` |
| `/api/entidades/propuestas` | `propuestas` | | `veces`, `clase`, `nombre` |
| `/api/piezas/sin-reconocer` | `piezas` (+ `tipos`) | `q` | `id`, `archivo`, `foja` |
| `/api/fojas` | `fojas` (+ `archivos`, `resumen`, `etiquetas`) | `sha`, `q` | `id`, `archivo`, `foja`, `clase` |
| `/api/foliatura` | `fojas` | `sha` (obligatorio), `q` | `foja`, `id` |
| `/api/cronologia` | `linea` (+ `clases`, `desordenes`) | `clase`, `desde`, `hasta` | `fecha`, … |
| `/api/cola` | `filas` (+ `total_sin_filtro`, `revisados`, `revisores`, `opciones`) | `familia`, `campo`, `clase` | `prioridad`, … (límite por defecto 200) |
| `/api/reasociaciones/pendientes` | `revisiones` | | `cuando`, `archivo`, `foja`, `campo` |

## Agregados nuevos

- **`/api/contrataciones`**: cada fila trae `etapas: {pliego, ofertas, adjudicacion,
  orden_compra, factura, remito, pago}` con la cantidad de documentos por etapa (0 = no
  consta en lo cargado), en una sola consulta agregada.
- **`/api/contratacion/<id>`**: además de `etapas` (las catorce, con sus documentos),
  `estado_etapas` compacto con `presente`, `cantidad`, `documentos` (ids) y `ausencia`.
- **`/api/resumen`**: `prioridades` (hallazgos pendientes, campos por cotejar, piezas sin
  reconocer, con cantidad y acción), `contrataciones`, `hallazgos_por_confianza`,
  `dinero` (suma de subtotales por etapa, moneda y firme/provisional, con cuántos
  renglones tienen valor y cuántos no, el rango de fechas y un enlace a los operandos),
  `destacados`, `incompleto` y `criterio`.
- **`/api/resumen/operandos`**: los renglones que componen cada suma de `dinero`.
- **`/api/proveedor/<id>`**: contrataciones, montos por etapa, ítems, historial de
  precios, facturas, remitos, hallazgos y relaciones, con fuentes.
- **`/api/cruce`**: renglón facturado contra la referencia contratada u ordenada del
  mismo ítem en la misma contratación. `filas` son las diferencias calculables, ordenadas
  por magnitud; `faltantes` lo que no tiene referencia única, con el motivo. Exige
  unidad, moneda, fechas y fuentes antes de calcular una diferencia. Precios nominales.

## Ausencia

Un dato ausente viaja como `null` y, cuando se sabe por qué, con `ausencia`
(`no_consta`, `ilegible`, `no_cargado`, `pendiente`). Ya no se mandan cadenas como
«SIN DATO» ni ceros que parezcan montos (el acumulado de una persona sin contratos con
monto es `null`, no `0`).

## Rendimiento (legajo real, 3 repeticiones)

| medición | antes | después |
|---|---|---|
| `/api/precios`, consultas SQL por pedido | 294 | 9 |
| `/api/precios?limite=100`, tiempo | 4,7 s | 0,34 s |
| `/api/cola`, consultas SQL | 58 | 13 |
| `/api/renglon/<id>/comparacion`, tamaño | 348 KB | 98 KB (referencias y exclusiones paginadas) |
| `/api/entidades`, tamaño | 128 KB | 26 KB |
| endpoints medidos | 61 | ninguno pasa de 200 KB; sólo `/api/actualizacion` pasa de 300 ms (358 ms, es un plan de trabajo, no una lista) |

Esquema 27: sólo índices (renglón por proveedor y fecha, por contratación e ítem;
contratación por estado; hallazgo por revisión, contratación y renglón; fuentes de
hallazgo). La migración no cambia filas.

## Validación sobre el legajo real (Claude, después de integrar)

Sobre dos copias limpias del legajo real, se re-extrajeron los renglones desde las
palabras guardadas (sin OCR nuevo), se reconstruyeron las contrataciones y se
recalcularon los hallazgos: una con el código anterior a esta integración y otra con el
integrado. **Dieron exactamente lo mismo.** O sea: el backend nuevo no cambia ningún
resultado del análisis; lo que cambia es la copia, que estaba calculada con una versión
anterior del código.

| | copia guardada | recalculada con el código vigente |
|---|---:|---:|
| renglones | 154 | 178 |
| con precio unitario | 59 | 117 |
| literal leído y sin valor | 47 | 10 |
| contrataciones con documentos | 124 | 20 |
| … de una sola etapa | 113 | 9 |
| documentos en contrataciones | 253 | 149 |
| hallazgos vigentes | 89 | 46 |
| revisiones humanas | 6 | 6 |

Hallazgos después: 26 renglones sin precio (antes 68), 9 subtotales que no dan su cuenta
(antes 0: no se veían porque no había precios), 7 facturados distintos de lo entregado,
3 documentos no encontrados, 1 importe sin rol.

**Para producción:** la instancia desplegada tiene su análisis calculado con código
anterior. Después de desplegar hay que correr «Actualizar análisis» para que el legajo
muestre estos números; no hace falta OCR nuevo.

La copia recalculada queda en `C:\Users\rober\AppUFIL-corpus-real\recalculado\` y es la
que usa el QA visual desde ahora.

## Pendiente de verdad

- `docs` de Codex sobre cada endpoint con ejemplo de respuesta: no llegó a escribirlos.
- Revisión cruzada de Codex sobre el frontend: sin cuota hasta el 26/09 21:17.
- 10 renglones siguen con literal y sin valor: celdas fusionadas o lecturas ambiguas que
  el lector no puede resolver sin adivinar.
