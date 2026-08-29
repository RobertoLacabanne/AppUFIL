# Fase 0 — Preguntas abiertas y decisión construir/adoptar

Unidad Fiscal de Investigación y Litigación de Paraná · MPF Entre Ríos
Documento de arranque. Sin código de pipeline.

---

## 1. Lo primero: la pregunta que bloquea todo lo demás

**¿Qué máquina hay?** CPU, RAM, placa de video y VRAM, disco libre.

No es burocracia. De ese dato salen tres arquitecturas distintas y no puedo elegir
entre ellas adivinando:

| Escenario | Hardware | Qué se puede hacer | Qué NO |
|---|---|---|---|
| **A — Sin GPU** | CPU 8+ núcleos, 32 GB RAM | OCR clásico (Tesseract), extracción por reglas + regex, todos los cruces SQL, búsqueda por palabra | Modelo de visión sobre página compleja (se vuelve minutos por página), LLM interpretativo usable |
| **B — GPU media** | 12–16 GB VRAM (RTX 4070 Ti / 4080 / 5070) | Todo lo anterior + VLM de documentos de 3–8B con coordenadas + embeddings + LLM de 8–14B para resumen | Modelos de 30B+ sin cuantización agresiva |
| **C — GPU grande** | 24–48 GB VRAM (RTX 4090 / 5090 / A6000) | Todo, con VLM de 8B en fp16 y LLM de 30B MoE cuantizado corriendo a la vez | — |

Con el escenario A el proyecto sigue siendo útil (el Caso A es 80% cruces SQL, no
inteligencia artificial), pero la mitad de la sección 7 del pliego no entra y hay
que decirlo de entrada en vez de prometerla.

**Si no me contestás nada más, contestame esto.** Con el resto avanzo asumiendo lo
que anoto en el punto 4.

---

## 2. El resto de las preguntas

### Bloquean la Fase 1 (piloto Caso A)

1. **Volumen y formato del corpus de contratos.** Cantidad aproximada de contratos y
   de fojas. ¿PDF escaneado, PDF nativo, papel por digitalizar, mezcla?
2. **Uniformidad.** ¿El formulario de contrato es el mismo entre las dos cámaras y a
   lo largo de los años, o cambia? Un formato estable permite extracción por
   plantilla, que es órdenes de magnitud más barata y más exacta que un modelo.
3. **20 PDFs de muestra reales** que cubran la variedad: la cámara buena y la mala, el
   año viejo y el nuevo, el escaneo torcido, el que tiene la firma encima del monto.
   Sin esto el banco de prueba es teórico.
4. **¿Existe planilla, liquidación o padrón en formato estructurado?** (xlsx, csv,
   una exportación del sistema de sueldos, la nómina que la Legislatura pueda
   entregar en digital.)
   Esta pregunta es la más cara de todas y la pongo aparte abajo.

### Bloquean la Fase 6 (Caso B)

5. **Qué llega efectivamente a la máquina.** ¿Archivos ya extraídos (carpetas, PDFs,
   correo exportado, reportes UFED en PDF/HTML) o imágenes forenses crudas (E01, dd,
   volcados de celular)? **Ninguna de las plataformas candidatas monta imágenes
   forenses.** Si lo que llega es un E01, hace falta un paso previo de extracción con
   herramienta forense, hecho por quien corresponda, y eso no lo resuelve este
   sistema ni debería.
6. **Volumen por operativo**, en GB y en cantidad de piezas. Cambia la recomendación
   de la sección 4 de este documento; abajo digo exactamente en qué umbral.
7. **Cómo se identifica hoy la procedencia.** ¿Hay número de acta de secuestro
   escrito en algún lado que se pueda transcribir al armar la carpeta? La trazabilidad
   pieza → acta → domicilio depende de una convención humana en el momento de la
   ingesta; ningún software la puede reconstruir después.

### No bloquean, pero cambian decisiones

8. Sistema operativo de la máquina, y si se puede instalar Docker y quién tiene
   permisos de administrador.
9. ¿La máquina tiene salida a internet **en algún momento** (una ventana de
   instalación), o hay que llevar absolutamente todo en un disco externo? Cambia el
   diseño del instalador, no si se puede o no.
10. Cuántas personas lo van a usar, y si es una sola máquina o varias.
11. ¿Existe ya escrita la lista de nombres, sociedades y términos de interés del
    legajo, o hay que armarla?
12. ¿Los contratos tienen número de resolución o de expediente administrativo? Sería
    una clave fuerte adicional además de CUIL/DNI.
13. Qué se hace hoy a mano para responder "¿este tipo tuvo contratos superpuestos?" y
    cuánto tarda. Es la línea de base contra la que se mide si esto sirve.

### La pregunta que puede cambiar todo el diseño

**Si existe una planilla de liquidación o un padrón digital de las dos cámaras, la
arquitectura del Caso A se da vuelta.** En ese caso la fuente de verdad de los montos
y los períodos es el archivo estructurado, y el OCR de los contratos pasa a cumplir un
rol distinto y mejor: **verificar** que el papel dice lo mismo que la planilla, y
marcar las discrepancias. Eso es más fácil de construir, mucho más exacto, y además
las discrepancias entre el contrato firmado y la liquidación son, probablemente, más
interesantes para la investigación que los datos en sí.

No lo doy por hecho porque no sé si existe. Pero si existe y no preguntamos, vamos a
construir con OCR algo que ya estaba en una tabla.

---

## 3. Decisión de la sección 9: construir o adoptar

### Recomendación

> **Adoptar para el Caso B. Construir para el Caso A. Y construir, propia y chica, la
> capa de ingesta que alimenta a las dos cosas.**
>
> Plataforma recomendada para el Caso B: **Datashare (ICIJ)**.
> **Aleph queda descartado** por motivos de calendario, no de calidad.

### Por qué Aleph queda afuera

Esto no es opinión, son fechas:

- El mantenimiento del **Aleph clásico terminó el 31 de diciembre de 2025.** Ya
  venció. No hay más parches de seguridad ni correcciones del equipo original.
- OCCRP lo reemplazó por **Aleph Pro**, que es un producto alojado (SaaS). El
  despliegue en la propia máquina existe pero **bajo un nivel "Enterprise" licenciado
  y pago**, con acompañamiento de OCCRP.
- Existe **OpenAleph**, un fork libre y activamente mantenido por el Data and Research
  Center desde 2025. Es una alternativa real y la dejo anotada como plan B.

Instalar hoy Aleph clásico en una máquina de la fiscalía sería montar software sin
mantenimiento sobre material sensible. Aleph Pro es SaaS: choca de frente con la
restricción 1 (offline), y la variante on-premise implica licencia, presupuesto y
compra estatal.

### Por qué Datashare y no construirlo

El Caso B, descripto sin vueltas, es: *meter todo adentro, saber de dónde salió cada
cosa, buscar sobre el conjunto*. La parte difícil de eso no es la búsqueda: es la
**extracción de texto de un corpus heterogéneo**. Correo en PST y MBOX, adjuntos
dentro de adjuntos, ZIPs anidados, .doc de 2003, planillas, imágenes, PDFs rotos.
Apache Tika cubre alrededor de mil quinientos formatos y Datashare lo trae integrado
con OCR y detección de entidades. Reescribir eso es meses de trabajo para llegar
peor.

A favor de Datashare, punto por punto contra los criterios que pediste:

- **Offline real.** Se autohospeda por diseño; el material no sale de la máquina.
  *Con una salvedad que hay que probar, abajo.*
- **Instalación y mantenimiento.** Se distribuye como aplicación de escritorio o como
  `docker-compose`. Un archivo de composición versionado y un instructivo escrito lo
  levanta cualquiera.
- **Licencia.** AGPL-3.0. Software libre, uso interno en un organismo estatal sin
  problema y sin costo.
- **Castellano.** OCR vía Tesseract con paquete `spa`, que es maduro. La detección de
  entidades en español es más floja que en inglés, pero es funcionalidad accesoria acá.
- **El día que el que lo instaló no está.** Este es el argumento más fuerte y el que
  menos se mira. Un Datashare con su `docker-compose.yml` y su instructivo tiene
  documentación pública, comunidad y otros que lo usan. Diez mil líneas nuestras
  tienen un solo lector, y ese lector se puede ir de la unidad.

### Lo que Datashare NO te va a dar, dicho antes y no después

1. **Trazabilidad nativa por acta de secuestro.** Datashare piensa en proyectos y
   documentos, no en actas y domicilios. Se resuelve, pero con trabajo nuestro: un
   proyecto por operativo, una convención rígida de árbol de carpetas
   (`OPERATIVO/ACTA-nnn__DOMICILIO/DISPOSITIVO/...`) y **una tabla de procedencia
   nuestra, indexada por SHA-256**, que es la que responde con autoridad "esta pieza
   salió del acta 14, domicilio tal, la levantó tal operador tal día". Datashare
   busca; la tabla nuestra responde de dónde salió.
2. **Anclaje a coordenadas** (restricción 4). No lo hace. El anclaje página+recuadro
   existe únicamente en el pipeline propio del Caso A. Para el Caso B el anclaje
   llega hasta archivo y página, no hasta el recuadro. Es una limitación aceptable
   para material de secuestro, donde lo que se busca es *dónde mirar*, pero no la voy
   a maquillar.
3. **Verificar antes de confiar:** hay que probar, con la máquina **físicamente
   desconectada**, que Datashare arranca e indexa sin intentar bajar modelos de
   lenguaje o índices en el primer uso. Es el riesgo concreto de la restricción 1 y se
   comprueba en una tarde. Si falla ese test, cambia la recomendación.

### El umbral donde esta recomendación se da vuelta

Si el volumen real por operativo resulta **menor a unas 5.000 piezas y el material
llega mayormente en PDF y ofimática** (nada de correo en PST, nada de volcados de
celular), entonces montar y mantener Datashare —cuatro servicios, un índice más que
cuidar— cuesta más que extender el índice del Caso A con búsqueda de texto completo y
embeddings. En ese escenario: **construir, un solo sistema, y listo.**

Por eso la pregunta 6 no es un trámite.

### Qué implica esto para el tamaño del proyecto

Lo digo como pediste, sin inflar:

- **El Caso B deja de ser desarrollo.** Pasa a ser: instalar, definir la convención de
  carpetas, construir la tabla de procedencia (chica, se comparte con el Caso A),
  escribir el instructivo y hacer una prueba de sala con un operativo real. Semanas,
  no meses. Casi nada de eso es programar.
- **El desarrollo propio se concentra en el Caso A**, que es donde está el problema
  que ninguna plataforma resuelve: leer un formulario, sacar cinco campos con su
  anclaje, normalizar la identidad de la persona y cruzar intervalos. Ahí sí hace
  falta código nuestro, y es acotado.
- **La capa 0 es nuestra y es común a los dos.** Hash, deduplicación, procedencia,
  inmutabilidad del original. Doscientas líneas y es el cimiento de la restricción 2 y
  de toda la trazabilidad. Es el trabajo con mejor relación valor/esfuerzo del
  proyecto entero.

---

## 4. Supuestos con los que avanzo mientras tanto

Para no frenar, arranco asumiendo esto. Cada uno se revisa apenas contestes:

- Escenario de hardware **B** (GPU de 12–16 GB). Si es A, aviso qué se cae.
- Caso A: entre 500 y 5.000 contratos, PDF escaneado, formato mayormente uniforme
  dentro de cada cámara y con variantes entre cámaras y entre años.
- No existe planilla estructurada para cruzar (si existe, mejor, y se rediseña).
- Caso B: el material llega ya extraído a archivos; la extracción forense es previa y
  ajena a este sistema.
- Una sola máquina, dos o tres usuarios, sin conexión.

---

## 5. Stack propuesto

Justificado contra las cuatro restricciones duras. Discutible, y lo marco donde lo es.

| Pieza | Elección | Por qué |
|---|---|---|
| Lenguaje del pipeline | **Python 3.12** | Es donde vive todo el ecosistema de OCR y modelos. Y vos ya lo tocás. |
| Base del piloto | **SQLite** (con WAL) | Archivo único, se copia en un pendrive, no hay servicio que se caiga. El camino a PostgreSQL queda abierto: se usa SQL estándar y sin extensiones raras. Ver decisión discutible 1. |
| Ruta rápida de texto | **OCRmyPDF + Tesseract (`spa`)** | CPU, maduro, offline total. Cubre el escaneo limpio, que va a ser la mayoría. |
| Ruta pesada | **VLM local vía vLLM** (Ollama si el modelo elegido no da coordenadas fiables en vLLM) | Sólo para la página que la ruta rápida no resuelve. Ver banco de prueba abajo. |
| Búsqueda semántica | **bge-m3** o **Qwen3-Embedding-0.6B**, índice FAISS en disco | Los dos andan bien en castellano y corren en CPU si hace falta. bge-m3 además hace denso y disperso a la vez, que en documentos administrativos con jerga fija rinde. |
| Capa interpretativa | **Qwen3-30B-A3B** cuantizado si entra en VRAM; si no, un 8–14B | Mezcla de expertos: activa pocos parámetros por token, así que rinde bastante más de lo que su tamaño sugiere en hardware modesto. |
| Grafo | Tablas de nodos y aristas en la misma base + **Cytoscape.js** para dibujar | No justifica una base de grafos aparte con estos volúmenes. Menos cosas que mantener. |
| Frontend | **Vue 3 o Svelte**, servido por el mismo proceso Python, sin build en la máquina de destino | El bundle se compila acá y se versiona compilado. En la fiscalía no se instala Node. |
| Empaquetado | **Docker Compose**, imágenes exportadas a `.tar` con `docker save` | La instalación no depende de que alguien se acuerde de qué instaló. Y las imágenes viajan en disco externo. |
| Exportación | **openpyxl** para `.xlsx`, RTF generado a mano | RTF es texto plano con marcas: interlineado 1,5, justificado, cuerpo 11, sin dependencias y abre en cualquier lado. |

### Candidatos de VLM y cómo elegirlo

**No fijo el modelo acá.** Tres candidatos actuales de pesos abiertos que devuelven
coordenadas, para pasar por el banco de prueba:

1. **PaddleOCR-VL** (~0,9B, Apache-2.0). Muy chico, pensado específicamente para
   documentos, devuelve JSON con recuadros y maneja tablas. Es el que corre incluso en
   el escenario A. Empezar por acá.
2. **Qwen3-VL 4B / 8B Instruct** (Apache-2.0). Grounding con coordenadas y mucha más
   capacidad de "entender" el formulario, no sólo transcribirlo. El 4B entra en ~3,5 GB
   cuantizado a 4 bits.
3. **dots.ocr** (~3B) o **Surya 2** (~650M) como tercer contendiente según cómo venga
   el manuscrito y el sello encima del texto.

**Banco de prueba (`banco-de-prueba/`):** las mismas 30 páginas del corpus real,
elegidas a mano para que duelan —la torcida, la de sello encima del monto, la de
manuscrito, la de tabla, la de fotocopia de fotocopia—, con la transcripción a mano de
los campos críticos. Cada candidato corre contra las mismas 30 y se compara por
exactitud por campo, tasa de error silencioso y segundos por página. Se elige con
esos tres números, no por reputación.

---

## 6. Cómo se mide si sirve (sección 12)

### Umbrales que propongo

Sobre los 50 contratos con transcripción manual de referencia:

| Campo | Exactitud mínima | Error silencioso máximo |
|---|---|---|
| Documento (CUIL/CUIT/DNI) | 98% | **0** |
| Fecha de inicio | 98% | **0** |
| Fecha de fin | 98% | **0** |
| Monto | 98% | **0** |
| Nombre | 95% | ≤ 1 de 50 |

### Fundamento, que importa más que los números

Los umbrales están puestos **asimétricos a propósito**, y es la decisión de diseño más
importante de todo el proyecto:

- **La omisión es barata.** El sistema dice "no pude leer esta fecha", aparece en la
  cola de revisión, alguien la mira treinta segundos y la carga. Molesta, no daña. Por
  eso banco una tasa de duda alta: **hasta 15 o 20% de campos derivados a revisión
  manual es aceptable** en el piloto.
- **El error silencioso es catastrófico.** Un monto mal leído sin marca entra en el
  acumulado, entra en el informe, y nadie se entera nunca. Un solo caso destruye la
  confianza en el sistema entero y con razón.

Entonces la métrica que gobierna es una sola:

> **Maximizar la cobertura automática, sujeto a error silencioso ≈ 0 en fechas y
> montos.** Nunca al revés.

Y el mecanismo que baja el error silencioso **no es un modelo mejor.** Es la **doble
lectura**: los campos críticos se leen por dos rutas independientes (Tesseract y VLM)
y, si no coinciden carácter por carácter tras normalizar, el campo **no se guarda como
dato: se guarda como conflicto** y va a la cola. Un modelo mejor baja el error de 3% a
1%; la doble lectura convierte ese 1% restante de *error invisible* en *conflicto
visible*, que es la única transformación que importa.

Cuesta el doble de cómputo. Lo banco.

### Si no llega

Si el piloto no alcanza el umbral, lo voy a decir con esas palabras y con la tabla al
lado. Las salidas en ese caso, en orden: (a) subir el umbral de duda y mandar más a
revisión manual, que degrada el sistema a "asistente de carga" pero sigue sirviendo;
(b) mejorar el escaneo de origen, que suele rendir más que cambiar de modelo; (c) si
existe la planilla estructurada, invertir el diseño como decía arriba.
Lo que no vamos a hacer es bajar el umbral para que dé.

---

## 7. Plan de trabajo ajustado

| Fase | Qué | Depende de |
|---|---|---|
| **0** | Este documento. Respuestas y decisión adoptar/construir. | Vos |
| **1** | Piloto vertical Caso A sobre 50 contratos: ingesta con hash, lectura, extracción a tabla con anclaje, la consulta de superposición, y una salida legible. Feo pero de punta a punta. | Hardware + los 20 PDFs de muestra |
| **2** | Medición contra la referencia manual y corrección de lo que falle. | Fase 1 |
| **3** | Resolución de identidad y cruce entre cámaras, con la cola de fusiones asistida por teclado. | Fase 2 aprobada |
| **4** | Búsqueda semántica, grafo, capa interpretativa. | Hardware escenario B o C |
| **5** | Interfaz completa y exportación a xlsx/rtf. | Fase 3 |
| **6** | Caso B: instalar Datashare, convención de procedencia, prueba desconectada, instructivo. | Decisión de la sección 3 confirmada |

Fase 1 empieza apenas tenga el hardware y los PDFs. Nada más.

---

## 8. Decisiones discutibles

Las separo como pediste, para que las discutas sin tener que leer el resto.

1. **SQLite y no PostgreSQL desde el arranque.** Gano portabilidad y cero
   administración; pierdo escritura concurrente y búsqueda de texto avanzada. Con dos o
   tres usuarios sobre una máquina, gana SQLite. Reversible: uso SQL estándar y evito
   lo específico del motor.
2. **Doble lectura obligatoria en los cinco campos críticos.** Duplica el costo de
   cómputo del pipeline. Sostengo que es el único mecanismo que ataca el error
   silencioso de verdad, pero es la decisión más cara y la más discutible.
3. **Un campo sin coordenadas no es un dato.** Si el modelo devuelve un valor pero no
   sabe dónde lo leyó, el valor **no entra en la tabla de datos**: va a la cola. Es
   estricto y va a mandar bastante a revisión al principio. Es la lectura literal de
   la restricción 4 y creo que corresponde.
4. **La normalización no pisa el original.** La tabla de datos guarda el literal leído,
   tal como está en el papel, con sus abreviaturas y sus errores. La forma normalizada
   vive en una tabla aparte que apunta a la primera. Cuesta una unión más en cada
   consulta; a cambio toda normalización es auditable y reversible sin volver a leer
   los documentos.
5. **Adoptar Datashare implica mantener un segundo sistema y un segundo índice.** Es un
   costo real y permanente, no un detalle. Lo asumo porque construirlo cuesta más, pero
   si el volumen del Caso B resulta chico, la cuenta se da vuelta (sección 3).
6. **Fuentes tipográficas versionadas en el repositorio** (unos 3 MB de TTF) en vez de
   instaladas en el sistema operativo. Engorda el repo; a cambio la interfaz se ve
   igual en cualquier máquina y cumple la restricción 1 sin depender de nada externo.
