# Nueva app: punteo de evidencia para remisiones a juicio y abreviados

## Objetivo

Construir una aplicación separada de AppUFIL que reutilice únicamente los componentes útiles del proyecto actual para transformar un legajo escaneado en un punteo de evidencia revisable por una persona.

La aplicación no decide qué prueba debe ofrecerse. Detecta, ordena y presenta cada pieza potencial de evidencia para revisión humana. La selección final siempre la realiza el usuario.

## Flujo principal

1. Crear un caso e indicar si se trata de una remisión a juicio o un abreviado.
2. Cargar el legajo escaneado en PDF.
3. Procesar OCR y conservar trazabilidad por archivo, página/foja y coordenadas.
4. Detectar piezas documentales y testimoniales relevantes.
5. Generar un checklist de evidencia.
6. Mostrar cada ítem junto a la foja o recorte que lo fundamenta.
7. Permitir al usuario elegir incluir, excluir o dejar pendiente cada ítem.
8. En remisiones a juicio, asociar a cada pieza el testigo/persona que la introduce al debate cuando corresponda.
9. Permitir editar descripción, tipo de prueba, foja y testigo sin perder el valor originalmente detectado.
10. Generar al final un punteo textual únicamente con los ítems elegidos.

## Estructura de cada ítem

Cada elemento del checklist debe guardar, como mínimo:

- estado: incluir / excluir / pendiente;
- tipo: documental / testimonial / informe / pericia / acta / soporte digital / otra;
- descripción breve;
- detalle suficiente para identificar la pieza;
- archivo de origen;
- foja o rango de fojas;
- página física del PDF;
- coordenadas del fragmento de origen cuando sea posible;
- testigo o persona que introduce la prueba, para remisiones a juicio;
- observaciones del usuario;
- confianza de detección automática;
- texto original detectado;
- historial de correcciones manuales.

## Modos de trabajo

### Remisión a juicio

El formulario debe priorizar:

- pieza de evidencia;
- descripción;
- foja;
- quién la introduce al debate;
- selección final.

Salida esperada: punteo ordenado de prueba ofrecida, usando exclusivamente los ítems marcados como incluidos.

### Abreviado

El mismo motor de ingestión y revisión, pero sin exigir testigo introductor cuando jurídicamente no corresponda.

La salida debe adaptarse al formato de evidencia utilizado en el acuerdo/abreviado, sin inventar información ni conclusiones.

## Principios heredados de AppUFIL

Se reutilizan conceptualmente y, cuando convenga, a nivel de código:

- ingesta de PDF;
- OCR;
- identificación por archivo y página;
- coordenadas y recortes;
- visor simultáneo documento + decisión;
- documentos fuente inmutables;
- derivados separados;
- procesamiento en segundo plano;
- barra de progreso;
- funcionamiento responsive;
- exportación;
- datos sintéticos para pruebas;
- trazabilidad de toda corrección humana.

## Qué NO reutilizar de AppUFIL

No copiar lógica específica de:

- contratos;
- facturas;
- identificación de contratados;
- análisis de montos;
- cruces determinísticos propios de contrataciones;
- perfiles de formularios de contratos;
- reglas de sumatoria económica.

La nueva aplicación debe tener un dominio propio: `evidencia`, no `contratos`.

## Pantalla principal de revisión

Diseño sugerido de dos paneles:

### Izquierda

Visor del legajo:

- foja actual;
- miniaturas;
- zoom;
- búsqueda;
- resaltado del fragmento vinculado al ítem seleccionado.

### Derecha

Tarjeta del ítem de evidencia:

- checkbox/estado;
- tipo de prueba;
- descripción editable;
- foja editable;
- testigo introductor editable cuando corresponda;
- observaciones;
- botones anterior/siguiente;
- indicador de confianza;
- acceso al texto OCR original.

Nunca permitir una decisión sin que la foja correspondiente esté visible.

## Vista checklist

Tabla o lista filtrable con columnas:

- incluir;
- número;
- tipo;
- descripción;
- foja;
- testigo;
- estado;
- advertencias.

Filtros:

- incluidos;
- excluidos;
- pendientes;
- sin testigo;
- sin foja;
- baja confianza;
- duplicados posibles.

## Generador final

El generador debe usar solamente los registros marcados `incluir`.

Debe respetar el orden elegido por el usuario y nunca agregar prueba que no esté seleccionada.

Ejemplo de formato conceptual para remisión:

`Acta de procedimiento de fecha ..., obrante a fs. XX/XX, que será introducida al debate por ...`

El texto debe generarse a partir de campos estructurados y no desde una conversación libre del modelo.

## Control humano

La aplicación puede sugerir:

- que dos ítems parecen duplicados;
- que falta un testigo;
- que la foja parece incorrecta;
- que una pieza contiene varias evidencias distintas.

Pero nunca debe resolver estas situaciones de forma silenciosa.

## Arquitectura recomendada

Mantener una arquitectura offline/local similar a AppUFIL:

- Python;
- SQLite;
- OCR local;
- interfaz web local;
- sin servicios externos en runtime;
- originales montados o tratados como solo lectura.

Separar módulos de dominio desde el inicio:

- `ingesta`;
- `ocr`;
- `segmentacion`;
- `evidencia`;
- `revision`;
- `personas`;
- `generacion`;
- `exportacion`.

## Modelo mínimo de datos

### caso

- id
- numero_legajo
- caratula
- tipo_proceso: remision / abreviado
- fecha_creacion

### documento

- id
- caso_id
- archivo
- sha256
- paginas

### evidencia

- id
- caso_id
- documento_id
- tipo
- descripcion_detectada
- descripcion_final
- pagina_pdf
- foja_desde
- foja_hasta
- bbox
- texto_origen
- confianza
- estado_revision
- incluir
- orden_salida

### persona

- id
- caso_id
- nombre
- rol

### evidencia_persona

- evidencia_id
- persona_id
- funcion: introductor / autor / interviniente / mencionado

### revision

- id
- evidencia_id
- campo
- valor_anterior
- valor_nuevo
- fecha
- usuario

## Primera versión útil

La primera versión no necesita resolver automáticamente toda la clasificación jurídica.

Debe hacer muy bien cinco cosas:

1. cargar un legajo escaneado;
2. mostrarlo foja por foja;
3. proponer ítems de evidencia con descripción y foja;
4. permitir incluir/excluir, editar y asignar testigo;
5. generar el punteo final exactamente según lo seleccionado.

Ese MVP es suficiente para probar el flujo con un legajo real antes de agregar automatizaciones más complejas.
