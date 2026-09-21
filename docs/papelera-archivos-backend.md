# Papelera de archivos — contrato y persistencia

Incremento 6: rama `codex/papelera-escala`, base `fefba22`. Esquema 25.
Todo el material de prueba se genera sintéticamente. No se modifica la interfaz.

## Contrato para Gemini

| Método y ruta | Cuerpo / respuesta |
| --- | --- |
| `GET /api/archivos` | Mantiene la respuesta anterior. Cada archivo agrega `revisiones`, `decisiones_humanas`, `tiene_revisiones_humanas`, `procesando`, `confirmacion_quitar`. `documentos` ya contiene la cantidad de piezas. |
| `POST /api/archivo/quitar` | `{"sha256":"<hash>","confirmacion":"QUITAR <hash>"}` |
| `POST /api/archivo/restaurar` | `{"sha256":"<hash>"}` |
| `GET /api/papelera/archivos?limite=&desde=` | `{"archivos":[…],"total":int,"desde":int,"limite":int}`. Cada archivo incluye `sha256`, `nombre`, `quitado_en`, `paginas`, `lote`, `revisiones`, `decisiones_humanas`, `documentos`, `bytes`, `tiene_revisiones_humanas`, `confirmacion_destruir`. |
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
una instantánea JSON con filas y padres compartidos. Los derivados físicos viven
en `papelera_derivado(sha256,ruta,contenido BLOB)`, con `ON DELETE CASCADE`. Una única
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
FK. Si un ID fue reutilizado o cambió la identidad o el contenido de un padre, responde
409 y conserva la papelera. En `documento` se toleran cambios de `clasificado_por`
y `clasificado_en`: confirmar el mismo tipo no rompe la referencia. No se
sobrescribe esa decisión posterior. Las demás columnas se comparan conservadoramente.
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

Antes de eliminar una copia física se compara su contenido con la instantánea y
se comprueba que no siga referenciada por registros activos. Un contenido distinto
queda conservado y bloquea la destrucción. Se incluyen también copias publicadas
por una restauración abortada antes del commit.

La exclusión entre procesos usa cerrojos del sistema operativo por ruta de base:
se liberan al morir el proceso. Ingesta, subida, pipeline, actualización y papelera
participan. El endpoint comparte además el candado de arranque del trabajador para
evitar la carrera entre consultar `ocupado` e iniciar la operación.

## Actualización y límites

Se retiran/restauran los sellos de las unidades afectadas y se invalidan sólo los
sellos globales. Los otros archivos conservan OCR y extracción. Los agregados del
legajo pueden regenerarse en la siguiente actualización sin releer el acervo.

La instantánea requiere memoria proporcional a las filas seleccionadas y a los
derivados del archivo: no es un formato de archivo en streaming. Si una conclusión
cita otro archivo, se lee sólo el padre referenciado. No se cargan sus descendientes. No se promete restauración
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

## Auditoría posterior y regresiones

- **Integridad referencial:** `verificacion.correr` ahora informa FK rotas;
  `respaldo.inspeccionar` verifica `quick_check` y `foreign_key_check` antes de admitir
  una copia. Se preservan las relaciones que no dependen del archivo retirado.
- **Migraciones:** se probó el SQL histórico real de versión 16, extraído del commit
  `2f875ae` y guardado como fixture `pruebas/fixtures/esquema_v16.sql`. Migra a 24,
  conserva y ancla la revisión humana, y una segunda inicialización no reejecuta el
  esquema. El script de tablas/vistas y el aumento de versión son transaccionales.
  Los ajustes anteriores de columnas/anclajes conservan su estrategia reintentable.
  Una versión futura se rechaza, y los objetos faltantes de papelera se reparan
  aunque `user_version` indique 24.
- **Fallo parcial de respaldo:** se prepara una copia SQLite temporal, se migra y
  valida, se sincroniza y recién entonces se publica con `os.replace`. Antes se
  conserva una copia consistente de la base anterior, incluyendo su WAL. Los
  nombres llevan UUID para no pisar dos respaldos hechos en el mismo segundo.
  Una falla de publicación conserva tanto la base activa como la copia anterior.
- **Concurrencia:** cada conexión abierta por `db.conectar` sostiene un lock
  compartido entre procesos; reemplazar la base exige lock exclusivo. En Windows
  se usa `LockFileEx`, en POSIX `flock`. Los lectores HTTP y los trabajadores
  participan. Los cerrojos no se trasladan ni se borran mientras están en uso.
  Clientes SQLite externos que eludan la API de conexión deben cerrarse antes de
  reemplazar una base; se comprueba además que el checkpoint no esté ocupado.
- **HTTP de respaldo:** se protege la base destino indicada por `slug`, no sólo
  el trabajador del legajo de la cookie. Los conflictos de conexión devuelven 409;
  el JSON con codificación inválida devuelve 400. La copia preparada ya está
  migrada, por lo que el caché de inicialización del servidor no entrega un esquema
  antiguo después de restaurar.
- **Invalidación incremental:** el cambio de una página se propaga únicamente a
  su archivo. El plan y la ejecución usan la misma selección de unidades. Una
  etapa `corriendo` o `pendiente` no se considera un resultado terminado al
  recuperar el trabajo. Releer OCR desvincula también `tabla_celda.lectura_id`,
  conservando las celdas en lugar de fallar por FK.
- **Revisiones:** el indicador incluye clasificación manual, foliatura, menciones,
  eventos, uniones de tablas, tramos y relaciones, además de campos e historial.
  Los resúmenes de respaldo cuentan por separado archivos y revisiones en papelera.
- **Fixtures de backend en Windows:** se corrigieron los tres fixtures que dejaban
  conexiones abiertas antes de limpiar temporales. Sus 14 errores desaparecen sin
  cambiar aserciones ni archivos de interfaz.

Pruebas específicas de auditoría: `pruebas/test_auditoria_backend.py`. No se usaron
causas reales, credenciales ni despliegues. No se modificaron `ufil/web/*` ni el
prompt maestro.

Validación final del bloque de auditoría: **733 pruebas, 0 fallos, 0 errores,
1 omitida**, en 55,616 s. Comando usado en PowerShell:

```powershell
$env:PATH = 'C:\Program Files\Tesseract-OCR;' + $env:PATH
$env:PYTHONUTF8 = '1'
python -m unittest discover -s pruebas -p 'test_*.py' -q
```

La omisión corresponde a una prueba opcional del repositorio. Se mantienen algunos
`ResourceWarning` de otros fixtures existentes; no son fallos de las aserciones.


## Incremento 6: escala y contrato

La selección se siembra con `WHERE sha256=?`. Cada FK se sigue mediante `WHERE fk
IN (…)`, en grupos de hasta 400 parámetros; se recuerdan los valores ya consultados.
El punto fijo recorre sólo filas seleccionadas. Los padres se buscan por las claves
referenciadas, sin cargar sus tablas completas. Se mantienen las referencias sin FK,
la salida completa de interpretaciones y el rechazo de páginas/piezas/tablas/campos
ajenos. `foreign_key_check` sigue siendo global: esta garantía de integridad puede
recorrer la base en SQLite. La medición demuestra materialización constante en Python
ante palabras ajenas; no promete tiempo total constante de todas las verificaciones.

El listado usa las columnas `paginas`, `lote`, `decisiones_humanas` y
`tiene_revisiones_humanas`; no lee `registros` ni la tabla de derivados. Orden:
`quitado_en DESC, sha256` (desempate estable). Límite 100 por omisión, entre 1 y 500;
desplazamiento 0 por omisión, entre 0 y el máximo entero de SQLite. Valores vacíos,
no enteros o fuera de rango reciben 400 en castellano. `paginas` y `lote` conservan
NULL cuando no se conocen; el número de páginas sale del archivo, no de su OCR.

`decisiones_humanas` cuenta las filas de las diez fuentes que antes usaba el indicador:
revisión humana, auditoría, documento clasificado por una persona, campo revisado,
foliatura/evento/mención de origen humano o con autor, tabla humana o unida por una
persona, tramo con autor y relación humana o con autor vinculada a documentos del
archivo. Una fila cuenta una vez aunque cumpla dos condiciones; una relación cuenta
una vez por archivo aunque tenga ambos extremos en él. Historial y estado revisado
son fuentes distintas: no es una cuenta de personas ni de acciones únicas. La misma
definición genera el agregado SQL y el contador de instantáneas/migración.
`tiene_revisiones_humanas` equivale exactamente a `decisiones_humanas > 0`.
`revisiones` sigue contando sólo `revision_humana`.

`api_archivos` calcula por lotes las decisiones, revisiones, procesamiento, fojas,
lecturas y piezas. Ya no emite consultas dentro del bucle de archivos. Si hay etapas
corriendo sobre páginas/documentos, se agregan dos consultas constantes para resolver
sus hashes; no dependen de la cantidad de archivos.

### Migración 24 → 25

Se agregan las columnas, se completa cada resumen una sola vez desde las filas
históricas, se decodifican los derivados a BLOB y se retiran del JSON. La instantánea
24 recibe versión 25 porque sus filas activas mantienen exactamente el mismo esquema;
no se admite cualquier versión por equivalencia supuesta. Columnas, contenido,
versiones y esquema se confirman en una transacción. Un fallo de conversión deja la
instantánea y la versión anteriores intactas y permite reintentar. El respaldo
SQLite transporta también la nueva tabla de derivados.

### C6 reproducido

Dos archivos están unidos por una relación que cita la pieza de B. Se quita A y
`piezas.clasificar_a_mano` confirma el mismo tipo en B con otra persona: el código
anterior rechaza restaurar A al cambiar autor/fecha. La prueba se ejecutó antes de
corregirlo y falló con `ConflictoPapelera`. Ahora restaura sin pisar la clasificación
ni la auditoría nuevas. Cambiar la clave de la pieza sigue produciendo conflicto.
También se probaron `entidades.confirmar_entidad` y `conjuntos.reordenar` sobre padres
compartidos: esas operaciones no modifican la fila padre y restaurar ya funcionaba.

### Regresiones y mediciones ejecutadas

`pruebas/test_papelera_escala.py` cubre:

- C4: quitar A, con B de 101 y 20.101 palabras, materializaba 102 y 20.102 palabras
  antes del cambio; ahora materializa 1 y 1. Cuenta filas mediante `row_factory`.
- C7: `set_trace_callback` mide 4 sentencias con 1 y con 31 archivos.
- C5: un autorizador SQLite prohíbe leer `registros` y un mock prohíbe parsear JSON;
  listar sigue funcionando. Verifica BLOB separado.
- Metadatos conocidos y NULL; las diez fuentes humanas, relaciones sin duplicación y
  coincidencia entre activo y papelera.
- Base con DDL de papelera 24 y assets base64 → migración → restauración de todas las
  filas, FTS y PNG; fallo de migración y reintento sin pérdida.
- C6 mediante operaciones reales y conflicto por cambio de identidad.
- Interpretación con fuentes en A y B, colección sin FK y protección de un campo ajeno.

`pruebas/test_papelera_http.py` agrega paginación, orden, valores por omisión, página
vacía y 400 en los bordes. La aserción del listado vacío en la prueba anterior se
actualizó al nuevo sobre; no se alteraron pruebas de Gemini.


Además del fixture de regresión, se ejecutó una migración con `db.py`, `papelera.py`
y `esquema.sql` reales de `fefba22`, cargados desde `git show`: el código antiguo creó
la base 24 y quitó un archivo completo. El código nuevo abrió esa base, migró a 25 y
restauró el archivo, su revisión y el PNG, sin FK rotas.

Suite de cierre: **749 pruebas en 48,224 s, OK, 1 omitida** (13 nuevas respecto de
736). Quedan `ResourceWarning` de fixtures ajenos, sin fallos ni errores.

En este sandbox de Windows, Python 3.13 crea los directorios de `TemporaryDirectory`
con modo 0700 y luego no puede acceder a ellos (`PermissionError`, incluso bajo el
workspace). El comando literal falló por ese motivo antes de ejecutar aserciones.
La suite completa se ejecutó conservando permisos heredados al crear directorios,
sólo dentro del proceso de prueba, sin modificar producto ni fixtures ajenos:

```powershell
$env:PATH = 'C:\Program Files\Tesseract-OCR;' + $env:PATH
$env:PYTHONUTF8 = '1'
python -c "import os,unittest; mkdir=os.mkdir; os.mkdir=lambda path,mode=0o777,**kw: mkdir(path,0o777,**kw); unittest.main(module=None,argv=['unittest','discover','-s','pruebas','-p','test_*.py','-q'])"
```

No se tocaron los archivos de frontend. La revisión visual corregida queda pendiente
por fallo de inicio/CDP de Chromium, detallado en `revision-gemini-por-codex.md`.

### Entrega bloqueada por permisos de Git

El intento de `git add` con rutas explícitas y posterior `git commit` falló al crear
`C:/Users/rober/AppUFIL/.git/worktrees/AppUFIL-codex-next/index.lock`:
`Permission denied`. No existe un lock abandonado; la ACL del directorio contiene
denegaciones de escritura. No se alteraron permisos ni se intentó eludirlas.
La rama sigue en `fefba22`; no se crearon commits ni se hizo push.

Los cambios quedan listos para estos dos commits, desde un entorno con escritura
habilitada en los metadatos de Git:

```powershell
git add ufil/papelera.py ufil/esquema.sql ufil/db.py ufil/servidor.py pruebas/test_papelera_archivos.py pruebas/test_papelera_http.py pruebas/test_papelera_escala.py docs/papelera-archivos-backend.md
git commit -m "Acotar la papelera por archivo y migrar sus resúmenes y derivados sin perder restauración"
git add docs/revision-gemini-por-codex.md docs/revision-gemini-evidencia.json scripts/revision_gemini_runner.py scripts/revision_gemini_browser.cjs
git commit -m "Documentar la revisión de Gemini y registrar observaciones al repetirla"
```

`.revision-gemini/` y `TASK_CODEX.md` permanecen ajenos a esos comandos.
`.tmp-pruebas/` contiene registros locales de las ejecuciones y no se versiona.
