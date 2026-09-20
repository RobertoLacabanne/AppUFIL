# Papelera de archivos — contrato y persistencia

Rama `codex/post-1464f24`, base `1464f24`. Esquema 24.
Todo el material de prueba se genera sintéticamente. No se modifica la interfaz.

## Contrato para Gemini

| Método y ruta | Cuerpo / respuesta |
| --- | --- |
| `GET /api/archivos` | Mantiene la respuesta anterior. Cada archivo agrega `revisiones`, `tiene_revisiones_humanas`, `procesando`, `confirmacion_quitar`. `documentos` ya contiene la cantidad de piezas. |
| `POST /api/archivo/quitar` | `{"sha256":"<hash>","confirmacion":"QUITAR <hash>"}` |
| `POST /api/archivo/restaurar` | `{"sha256":"<hash>"}` |
| `GET /api/papelera/archivos` | `{"archivos":[{"sha256":"…","nombre":"…","quitado_en":"…","revisiones":1,"documentos":2,"bytes":123}]}` |
| `POST /api/archivo/destruir` | `{"sha256":"<hash>","confirmacion":"DESTRUIR <hash>"}` |

El hash debe ser SHA-256 hexadecimal de 64 caracteres en minúscula. Las confirmaciones
son literales, con espacio y hash completo. Respuesta de mutación: `ok`, `sha256`,
`estado` (`papelera`, `activo`, `destruido`). Quitar también informa `revisiones` y
`limpieza_pendiente`. Entrada inválida: 400. Conflicto de estado, procesamiento,
referencias modificadas o segunda restauración: 409. Ante conflicto no se descarta
la instantánea ni se sobrescriben registros activos.

El procesamiento existente planifica por legajo: mientras corre se bloquean las
operaciones de papelera de ese legajo. El estado por archivo también consulta
`resultado_etapa`. No se cambia ningún nombre del contrato solicitado.

## Qué se conserva

`papelera_archivo` conserva PDF original como BLOB, versión del esquema, metadatos y
una instantánea JSON con filas, padres compartidos y derivados físicos. Una única
transacción `BEGIN IMMEDIATE` guarda esta instantánea y retira los registros activos.
Las FK siguen habilitadas y diferidas durante la transacción; se verifica
`foreign_key_check` antes de confirmar.

Se inspecciona `PRAGMA table_list` y `foreign_key_list` de la base real. Se recorre
la dependencia desde `archivo`, sin ascender hacia padres compartidos. Las tablas
internas de FTS5 no se copian: se guardan sus filas lógicas. También se tratan
explícitamente las referencias sin FK:

- `revision_humana`, `auditoria`, `excepcion`, `mencion` por hash;
- `resultado_etapa` por alcance archivo, página y documento;
- `coleccion_item` por documento o `sha:foja`;
- `interpretacion` por alcance y fuentes: una conclusión afectada sale completa;
- `pagina_texto` por hash.

Los descendientes incluyen páginas, lecturas, palabras, clasificación, documentos,
campos, propuestas, conflictos y variantes, normalización, tablas/celdas,
foliatura, menciones, eventos, relaciones, tramos, conjuntos y alias vinculados.
Entidades, personas, decisiones de fusión y contenedores compartidos permanecen.
Una dependencia que exigiría retirar páginas, piezas, tablas o campos propios de
otro archivo se rechaza explícitamente: debe separarse antes esa dependencia.

Restaurar reinserta registros sin `REPLACE`, valida padres compartidos y verifica
FK. Si un ID fue reutilizado o un padre cambió, responde 409 y conserva la papelera.
Se eligió este comportamiento conservador en lugar de adivinar una reasociación.
Dos restauraciones no duplican datos: la segunda recibe 409 explícito.

## Disco, reinicios y respaldos

Después del commit de quitar, `papelera_limpieza` permite reintentar la limpieza de
copias administradas y derivados. El arranque reintenta trabajos pendientes. La
instantánea contiene el PDF y los derivados antes de que se eliminen esas copias.
Sólo se eliminan rutas confinadas a `originales/<prefijo>/<sha>.pdf` y
`derivados/<prefijo>/<sha>/` junto a la base. Se rechazan enlaces simbólicos.
Los originales de un corpus externo, ingestado en modo lectura, nunca se modifican.

La restauración publica el PDF con temporal, fsync y reemplazo atómico antes del
commit. Una interrupción puede dejar una copia física sin referencia; nunca un
registro activo que dependa de un PDF a medio escribir. Los renders se reubican al
restaurar en otra carpeta. El respaldo SQLite incluye la papelera completa.
Destruir sólo descarta una instantánea que ya estaba en papelera, con confirmación
explícita y después de completar su limpieza física pendiente. No es un borrado
forense del dispositivo ni altera copias de respaldo anteriores.

La exclusión entre procesos usa cerrojos del sistema operativo por ruta de base:
se liberan al morir el proceso. Ingesta, subida, pipeline, actualización y papelera
participan. El endpoint comparte además el candado de arranque del trabajador para
evitar la carrera entre consultar `ocupado` e iniciar la operación.

## Actualización y límites

Se retiran/restauran los sellos de las unidades afectadas y se invalidan sólo los
sellos globales. Los otros archivos conservan OCR y extracción. Los agregados del
legajo pueden regenerarse en la siguiente actualización sin releer el acervo.

La instantánea requiere memoria proporcional a la base examinada y a los derivados
del archivo: no es un formato de archivo en streaming. No se promete restauración
automática frente a cambios de esquema futuros: una versión distinta exige una
migración explícita de instantáneas. Los conflictos conservan todo para su revisión.

## Validación del bloque inicial

17 pruebas específicas pasan en `pruebas.test_papelera_archivos` y
`pruebas.test_papelera_http`: archivo nuevo y procesado, revisiones, quitar/restaurar,
segunda restauración, destruir y sus validaciones, entidad compartida, procesamiento,
dos reinicios, migración, actualización incremental, fallos parciales, bloqueo,
limpieza reintentable, reingesta y respaldo portable. Las pruebas HTTP usan el
servidor real y comprueban las cinco rutas, 400 y 409.

Se corrigió además la consulta a Tesseract durante el import del backend: ahora sólo
se consulta al ejecutar OCR, permitiendo administrar datos sin ese ejecutable.

Suite amplia del bloque inicial: **716 pruebas, 14 errores de limpieza de temporales
preexistentes en Windows, 1 omitida**. No hay fallos de aserción con Tesseract en PATH
y `PYTHONUTF8=1`. Los 14 errores son conexiones que los fixtures de
`test_cobertura_busqueda` y `test_cola` no cierran antes de borrar sus temporales;
coinciden con el antecedente documentado en `docs/relevo-claude-codex.md`.
