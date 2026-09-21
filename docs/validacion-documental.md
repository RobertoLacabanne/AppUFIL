# Validación documental

Corpus, métricas, pruebas y limitaciones del carril de actualización incremental. Lo que
se midió, con qué se midió, y lo que todavía no se midió.

La regla de este documento es una sola: **nunca decir que algo se probó si no se
ejecutó.** Lo comprobado, lo inferido y lo pendiente van separados y con ese nombre.

---

# 1. Corpus usado

## Sintético — es lo que se usó

`herramientas/generar_fixtures.py`, 6 contratos, 10 fojas, 200 DPI, escala de grises,
semilla 7. Personas inventadas y CUIL con dígito verificador deliberadamente incorrecto,
para que no puedan confundirse con datos de una persona real. Los PDF llevan
`UFIL-CORPUS-SINTETICO-DE-PRUEBA` en los metadatos, que el sistema detecta al ingerir
para marcar la base entera como demostración.

Sirve para probar que el mecanismo funciona de punta a punta. **No sirve** para decir qué
tan bien lee documentación real: un escaneo de verdad es peor —fotocopia de fotocopia,
sello de tinta corrida, papel amarillo, grapas, manuscrito—.

## Real — NO se usó, y no se puede afirmar nada sobre él

Los PDF de Vialidad y Legislatura, y la instalación con los nueve archivos ya cargados,
**no son accesibles desde este entorno de desarrollo**. No se ejecutó una sola corrida
sobre ellos. Todo lo que dice este documento vale para corpus sintético.

Queda como la prueba pendiente más importante: el mecanismo de adopción de OCR heredado
(§4 de `docs/evolucion-documental.md`) está pensado exactamente para esa base, y es ahí
donde tiene que demostrarse que no obliga a releer nada.

---

# 2. Lo COMPROBADO — se ejecutó y estos son los números

Máquina: Windows 11, Python 3.13, Tesseract 5.4.0 con `spa`, PyMuPDF 1.24.14.

## 2.1 El pipeline corre de punta a punta

```
ingerir  ->  6 nuevos · 0 duplicados · 0 mismo papel · 0 fallidos · 10 páginas
leer     ->  6 archivos · 10 páginas en 16,6 s (1,66 s por página, 12 en paralelo)
extraer  ->  6 archivos -> 6 documentos · 36 campos · 1 conflicto · 7 a revisar
identidad->  4 personas creadas · 2 unidas por clave fuerte · 1 sin clave
```

## 2.2 La actualización reutiliza lo caro

| Escenario | Tiempo | Fojas releídas | Fojas reutilizadas |
|---|---|---|---|
| Lectura inicial | 16,6 s | 10 | — |
| Actualizar una base sin sellos | **1,3 s** | **0** | 10 |
| Aparece un extractor nuevo | **1,4 s** | **0** | 10 |

## 2.3 La invalidación es selectiva

Al aparecer un extractor nuevo (un `.json` más en `ufil/perfiles/`), el plan informó:

```
ingesta         vigente         6/6
lectura         heredada       10/10
clasificacion   vigente         6/6
segmentacion    desactualizada  0/6   <- se rehace
cotejo          vigente         6/6
extraccion      desactualizada  0/6   <- se rehace
normalizacion   desactualizada  0/6   <- se rehace
identidad       desactualizada  0/1   <- se rehace
indice          vigente         1/1
interpretacion  desactualizada  0/1   <- se rehace
```

Lo que importa de ese cuadro es lo que **no** se rehace: la lectura, la clasificación de
fojas (un perfil de extracción no cambia qué es cada foja) y el índice de búsqueda, que
se apoya en la lectura y no en la extracción.

## 2.4 El trabajo de las personas sobrevive

Una corrección hecha sobre un importe (`$123.456,78`, `perez.ana`) se conservó con su
estado `corregido` a través de dos actualizaciones completas, incluida una que rehízo la
segmentación.

## 2.5 La aplicación real levanta y responde

Se levantó `ufil.servidor` sobre la base del corpus sintético, con el esquema nuevo
aplicado. `/`, `/api/panel`, `/api/documentos` y `/api/salud` contestaron 200 con datos.

## 2.6 Dos defectos más, encontrados y cerrados durante el incremento

- **Una revisión que se corre de lugar borraba a la de al lado.** La clave de
  `revision_humana` incluye el `orden`; al mudar una revisión a su posición nueva, esa
  posición podía estar ocupada por otra revisión todavía sin mirar, que se borraba en
  silencio. Se reescribió la reasociación en dos tiempos: primero se decide todo,
  después se escribe. Cubierto por
  `test_dos_revisiones_que_se_corren_de_lugar_no_se_pisan`.
- **`/api/respaldo/restaurar` contestaba sin leer el archivo subido.** Latente desde
  antes: lo destapó que el esquema nuevo agregue una página de 16 KB a una base recién
  creada (245.760 → 262.144 bytes), lo que empujó el archivo de la prueba por encima
  del tamaño del buffer del socket. Pasado ese umbral, quien se equivocaba al escribir
  el número del legajo recibía una conexión cortada en lugar del mensaje que le dice
  qué escribir. Cubierto por la prueba que ya existía,
  `test_respaldo_vuelta.py::test_restaurar_exige_el_numero_del_legajo`, que sin la
  corrección falla con `ConnectionResetError [WinError 10054]`.

## 2.7 El defecto de resegmentación está reproducido y cerrado

`pruebas/test_actualizacion.py::UnaCorreccionNoSeMudaDeDocumento`. Con el código anterior
al arreglo, una corrección hecha sobre la factura de la foja 3 terminaba aplicada al
recibo de la foja 2, con `estado=corregido` y `confianza=1.0`. La prueba falla sin el
arreglo y pasa con él.

---

# 3. Pruebas automáticas

## Suite completa

```
python -m unittest discover -s pruebas -p "test_*.py" -q
```

Tesseract tiene que estar en el PATH (`C:\Program Files\Tesseract-OCR`). Sin él, el
import de `ufil/capa1_texto.py` falla y se caen 63 pruebas que no tienen nada que ver.

| | Antes del incremento | Después |
|---|---|---|
| Tests | 530 | **542** |
| Failures | 1 | 1 |
| Errors | 14 | 14 |
| Skipped | 1 | 1 |

Las 12 nuevas son `pruebas/test_actualizacion.py` y pasan todas.

## Las fallas que ya estaban, y por qué no son del incremento

- **1 failure**, `test_taller.py::test_la_caja_se_juzga_de_verdad_y_no_por_su_nombre`:
  la prueba lee `ufil/web/app.js` sin declarar `encoding="utf-8"` y en Windows lo
  decodifica en cp1252, así que el `×` de un mensaje llega roto a la comparación. Es de
  entorno, no de la aplicación: el mensaje en el `.js` está bien escrito.
- **14 errors**, todos `PermissionError [WinError 32]` al borrar el directorio temporal
  con una conexión SQLite todavía abierta. Ocurren en el `tearDown`, no en una
  aserción, y son propios de Windows.

Ninguna de las dos se tocó: arreglar pruebas ajenas en el mismo incremento vuelve
imposible saber qué rompió qué. Quedan anotadas acá para que se arreglen aparte.

## Qué cubren las pruebas nuevas

| Prueba | Qué sostiene |
|---|---|
| `la_correccion_queda_en_la_pieza_que_la_persona_miro` | El defecto del §2. Regresión. |
| `si_no_se_puede_saber_a_cual_corresponde_no_se_aplica_a_ninguna` | No se le encaja una revisión al documento que quedó sólo porque quedó. |
| `una_revision_vieja_sin_anclaje_no_se_aplica_a_ciegas` | Compatibilidad: las filas viejas no se aplican por posición si la pieza cambió. |
| `el_ocr_ya_hecho_se_reutiliza_en_una_base_sin_sellos` | No releer un acervo entero por haber agregado versionado. |
| `cambiar_una_etapa_de_arriba_no_toca_el_ocr` | Invalidación selectiva. |
| `la_cascada_va_solo_hacia_adelante` | Invalidar la interpretación no puede costar un OCR. |
| `invalidar_marca_la_etapa_y_las_que_dependen` | Idem, sobre la base. |
| `migrar_no_pierde_revisiones_y_las_ancla` | Compatibilidad hacia atrás. |
| `dos_revisiones_que_se_corren_de_lugar_no_se_pisan` | Al mudarse de posición, una revisión no puede borrar a la de al lado. |
| `no_promete_reutilizar_fojas_que_va_a_releer` | La cuenta de fojas reutilizadas no puede ser optimista. |
| `cortarla_no_pierde_lo_hecho_ni_repite` | Reanudable. |
| `forzar_una_etapa_la_rehace_y_arrastra_a_las_de_abajo` | Forzado explícito. |

---

# 4. Lo INFERIDO — razonado, no medido

- **Que el mecanismo escala a miles de fojas.** El plan hace una consulta por etapa y la
  actualización trabaja por archivo, así que debería crecer de forma lineal. No se midió
  con 500, 2.000 ni 5.000 fojas. Es una expectativa, no un resultado.
- **Que la huella por código fuente no produce falsos positivos molestos.** Se dispara
  con un comentario, y eso es a propósito en etapas baratas, pero no se midió cuántas
  veces pasaría en un ciclo de desarrollo real.
- **Que adoptar el OCR heredado es seguro sobre la base existente.** Es correcto por
  construcción —no se toca nada— pero sobre esa base concreta no se ejecutó.

---

# 5. Lo PENDIENTE

1. Correr todo sobre el acervo real y sobre la instalación con los nueve archivos ya
   cargados. Es la prueba que le da sentido a la adopción de OCR heredado.
2. Medir con volumen (500 / 2.000 / 5.000 fojas) y publicar los tiempos.
3. Medir exactitud de campos críticos contra `banco-de-prueba/referencia.csv`, que hoy
   está vacío a propósito y hace falta llenar a mano. Sin eso, el objetivo de ≥ 99 % del
   pliego §23 no se puede afirmar ni negar.
4. Arreglar, en un incremento aparte, el `encoding` de `test_taller.py` y el cierre de
   conexiones en los `tearDown` de Windows.

---

# 6. Fases 1 a 7 — lo medido

Mismo entorno: Windows 11, Python 3.13, Tesseract 5.4.0 con `spa`, PyMuPDF 1.24.14.
Mismo corpus sintético: 6 contratos, 10 fojas, 200 DPI.

## Suite

| | Commit base | Ahora |
|---|---|---|
| Tests | 530 | **628** |
| Failures | 1 | 1 |
| Errors | 14 | 14 |
| Skipped | 1 | 1 |

98 pruebas nuevas, ninguna regresión. El `failure` y los 14 `errors` son los mismos de
siempre: el `encoding` de `test_taller.py` y los `PermissionError` de `tearDown` en
Windows. Ninguno se tocó.

## COMPROBADO ejecutando

- **El pipeline sigue dando lo mismo después de partirlo en cuatro**: 6 archivos →
  6 documentos · 36 campos · 1 conflicto · 7 a revisar · 0 sin perfil, idéntico a antes
  de la FASE 1.
- **Reextraer conserva la identidad de la pieza y la clasificación**, y la corrección
  humana sobrevive (`$999.888,77 · corregido · perez.ana`, 1 reaplicada, 0 a reasociar).
- **Resegmentar conserva las piezas**: misma identidad, 6 campos conservados, 1 revisión
  vigente.
- **Foliatura**: 1 candidata detectada en 10 fojas (confianza 0,72). Las otras 9 quedaron
  **sin detectar y sin marcar como «sin foliar»**, que es la conducta correcta.
- **Tablas**: 3 tablas de fechas reconocidas en 10 fojas (3×2, confianza 0,53–0,54), y
  **ningún contrato en prosa tomado por planilla**.
- **Cronología**: 10 hechos ordenados por fecha, cada uno con su literal, su foja y su
  origen (`campo:fecha_inicio`, `campo:fecha_fin`).
- **Los endpoints contestan** sobre corpus real: `/api/tablas`, `/api/tabla`,
  `/api/tabla/renglones`, `/api/cronologia`, `/api/foliatura`, más los cinco de la
  FASE 3 y los tres de la actualización incremental.

## INFERIDO, no medido

- Que la detección de tablas y de foliatura se porte bien sobre escaneos reales. El
  corpus sintético es limpio; un expediente de verdad trae fotocopias de fotocopias,
  sellos encima del número y papel amarillo. **Los umbrales van a tener que medirse de
  nuevo contra material real.**
- Que la candidata de foliatura detectada (confianza 0,72) sea efectivamente una
  foliatura: el corpus sintético no tiene una transcripción de referencia contra la cual
  compararla.

## PENDIENTE

1. Pantallas para tablas, cronología y foliatura. El backend, la persistencia, la línea
   de comandos, las pruebas y los endpoints están; **la interfaz no**, así que las
   FASES 4, 5 y 7 no están terminadas según el criterio del pliego §32.
2. Medir sobre el acervo real y contra `banco-de-prueba/referencia.csv`, que sigue vacío.
3. Volumen: 500 / 2.000 / 5.000 fojas.
4. FASE 6 (entidades más allá de personas), 8 (colecciones y consultas guardadas),
   9 (exportaciones nuevas) y 10 (rendimiento) no se empezaron.

---

# 7. Incremento 6 — papelera de archivos, lo medido

Windows 11, Python 3.13, Tesseract con `spa` en el PATH, `PYTHONUTF8=1`. Corpus
sintético generado por las pruebas; **no se usó el acervo real**.

## Suite

| | `1464f24` (base) | + Codex | + Gemini | Integrada final |
|---|---|---|---|---|
| Tests | 699 | 733 | 736 | **765** |
| Failures | 0 | 0 | 0 | 0 |
| Errors | 14 | 0 | 0 | 0 |
| Skipped | 1 | 1 | 1 | 1 |

Los 14 `errors` de siempre (`PermissionError` al borrar temporales con conexiones
abiertas) los cerró Codex en los tres fixtures que no cerraban su conexión. El `failure`
de `test_taller.py` por `cp1252` no aparece con `PYTHONUTF8=1`.

## COMPROBADO ejecutando

- **Quitar es proporcional al archivo.** Con un archivo A y otro B de 101 y de 20.101
  palabras de OCR, quitar A materializa **1 fila de `palabra` en los dos casos**, la suya
  (`test_papelera_escala`, visto al correr la suite). Codex informó 102 y 20.102 con el
  código anterior; eso no lo volvió a medir Claude.
- **`/api/archivos` no crece con los archivos**: 4 sentencias con 1 archivo y con 31.
- **Una papelera v24 migra a v25 y se restaura** con su revisión humana, sus PNG y la
  integridad referencial (`test_migracion_v24_con_papelera_restaurable`); una migración
  que falla no sube la versión ni pierde la instantánea.
- **C6 reproducido antes de corregirlo**: confirmar el mismo tipo de una pieza compartida
  bloqueaba restaurar; ahora restaura y conserva esa decisión. Cambiar la identidad de la
  pieza sigue dando conflicto.
- **Subir durante un procesamiento da 409** (C8): con el cerrojo del trabajador tomado,
  `almacen.guardar` levanta `Ocupado`. Reproducido por Claude; en corrección.
- **Revisión de la interfaz en navegador real** (Edge headless por CDP, backend real):
  G1–G10 y G13 pasan de defecto a correcto sobre la interfaz integrada, en 3 corridas de
  3. Evidencia en `docs/revision-gemini-evidencia-integrada.json`, contra la original en
  `docs/revision-gemini-evidencia.json`.
- **Las pruebas nuevas prueban**: de las 14 de `test_papelera_web.py` (13 de Gemini y la
  de G5 de Claude), 11 fallan con el `app.js` de `fefba22`; las otras 3 cubren conductas
  que ya estaban bien (entre ellas, redibujar después de restaurar en la página 2: el
  código viejo redibujaba siempre). Las 3 de navegación fallan con el `app.js` que dejó
  Gemini. Las del informe de cronología y de descripciones fallan con el `exportar.py`
  anterior (`5000 != 6001`).

## INFERIDO, no medido

- Que el tiempo de quitar también sea proporcional al archivo. Se midieron filas
  materializadas, no tiempo. Las columnas grandes que recorre (`palabra.lectura_id`,
  `lectura.pagina_id`, `pagina.sha256`) tienen índice; las que no lo tienen son de tablas
  chicas.
- Que la papelera se porte igual sobre el acervo real y con miles de fojas.

## PENDIENTE

1. C8 (subir durante el procesamiento).
2. Papelera sobre el acervo real y a 2.000 / 5.000 fojas.
3. La revisión en navegador corre fuera del discovery (`scripts/revision_gemini_runner.py`):
   hay que acordarse de correrla cuando se toque la papelera o el visor.
