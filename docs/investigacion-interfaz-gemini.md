# INFORME DE INVESTIGACIÓN: Interfaz y Experiencia AppUFIL

## 1. Visor de Documentos
**Opciones:**
- **PDF.js (Mozilla)**
  - *Licencia:* Apache-2.0
  - *Peso:* ~2.5 MB (core + worker)
  - *Build / Internet:* No requiere build (se usan archivos precompilados minificados). Funciona 100% offline.
  - *Qué resuelve:* Renderiza PDFs en un elemento `<canvas>`. Permite saber las coordenadas exactas del texto, hacer zoom, saltar a fojas y superponer "cajas" resaltadoras para indicar de dónde salió el dato.
- **OpenSeadragon**
  - *Licencia:* New BSD
  - *Peso:* ~150 KB
  - *Build / Internet:* No requiere build. Funciona offline.
  - *Qué resuelve:* Es un visor de imágenes de altísima resolución (Deep Zoom). Excelente alternativa si el backend convierte previamente las fojas PDF a imágenes. Facilita enormemente el zoom fluido.
- **Iframe nativo del navegador (`<iframe src="foja.pdf">`)**
  - *Licencia:* N/A (Nativo)
  - *Peso:* 0 KB
  - *Qué resuelve:* Muestra el PDF rápido sin librerías. *Desventaja:* No permite control programático (no se puede resaltar un texto específico desde afuera, ni sincronizar vistas fácilmente).

**Recomendación:** **PDF.js**.
*Por qué:* Es el estándar absoluto para interactuar con PDFs en la web. Al permitirnos dibujar sobre el canvas y acceder a la metadata, podemos colocar un recuadro amarillo translúcido exactamente sobre el monto o nombre que el OCR leyó, garantizando la **trazabilidad visual**.
*Costo de adopción:* Medio (~2-3 días). Hay que escribir lógica en Vanilla JS para instanciar el visor, cargar el worker, manejar el renderizado asíncrono de cada foja y calcular la escala de las coordenadas para superponer los resaltados al hacer zoom.

## 2. Tablas Grandes (Miles de filas sin trabarse)
**Opciones:**
- **Tabulator**
  - *Licencia:* MIT
  - *Peso:* ~400 KB (JS + CSS)
  - *Build / Internet:* No requiere build. Se incluye con un `<script>`. Funciona offline.
  - *Qué resuelve:* Implementa DOM Virtual. Solo dibuja en el navegador las filas visibles, permitiendo tener decenas de miles de filas sin que la PC colapse. Permite agrupar, filtrar y ordenar.
- **AG Grid (Community Edition)**
  - *Licencia:* MIT
  - *Peso:* ~1.2 MB
  - *Build / Internet:* No requiere build (se puede usar vía script tag). Funciona offline.
  - *Qué resuelve:* Es la tabla más potente de la industria, pero es muy pesada y la API es extremadamente compleja para necesidades básicas.
- **DataTables**
  - *Licencia:* MIT
  - *Peso:* ~100 KB (+ dependencia de jQuery)
  - *Qué resuelve:* Clásico y muy conocido. *Desventaja:* El manejo de miles de filas continuas (extensión Scroller) a veces es torpe, y nos obligaría a incluir jQuery.

**Recomendación:** **Tabulator**.
*Por qué:* Es puro JavaScript (sin jQuery), pesa un tercio que AG Grid, es muy sencillo de instanciar y su rendimiento con DOM virtual en máquinas modestas es excepcional.
*Costo de adopción:* Medio (~1-2 días). Implica cambiar la forma en que generamos las tablas: en lugar de imprimir `<tr>` desde el backend, pasamos un JSON de datos a `new Tabulator()` y configuramos las columnas en JavaScript.

## 3. Navegación y Búsqueda
**Opciones:**
- **HTMX**
  - *Licencia:* BSD-2-Clause
  - *Peso:* ~14 KB
  - *Build / Internet:* No requiere build. Funciona offline.
  - *Qué resuelve:* Navegación ultra rápida. Reemplaza partes de la pantalla pidiendo fragmentos HTML al servidor sin recargar toda la página.
- **Alpine.js**
  - *Licencia:* MIT
  - *Peso:* ~40 KB
  - *Build / Internet:* No requiere build. Funciona offline.
  - *Qué resuelve:* Agrega interactividad directamente en el HTML. Ideal para gestionar pestañas, modales y barras de búsqueda en tiempo real sin escribir JS espagueti.
- **FlexSearch**
  - *Licencia:* Apache-2.0
  - *Peso:* ~5 KB
  - *Qué resuelve:* Búsqueda textual ultra rápida en el cliente sobre datos en memoria.

**Recomendación:** **HTMX + Alpine.js (Combinados)**.
*Por qué:* HTMX nos permite navegar por contrataciones y fojas sin el "parpadeo" de recargar la página blanca, manteniendo abierta la lectura del lado derecho. Alpine.js nos da el control de la UI (abrir/cerrar detalles, menús colapsables) de forma declarativa. Es el stack moderno por excelencia para aplicaciones sin paso de compilación.
*Costo de adopción:* Medio. Hay que adaptar los endpoints del backend para que puedan devolver fragmentos de HTML (`partials`) en lugar de la página entera cuando HTMX lo solicita.

## 4. Comparación Lado a Lado
**Opciones:**
- **Split.js**
  - *Licencia:* MIT
  - *Peso:* ~6 KB
  - *Build / Internet:* No requiere build. Funciona offline.
  - *Qué resuelve:* Crea paneles divisores arrastrables (drag & drop) usando CSS Flexbox/Grid por detrás.
- **CSS Nativo (Flexbox/Grid)**
  - *Licencia:* N/A
  - *Peso:* 0 KB
  - *Qué resuelve:* Paneles fijos (ej: 50% - 50%).

**Recomendación:** **Split.js**.
*Por qué:* En pantallas pequeñas de 1366x768, el espacio es crítico. No podemos fijar un ancho del 50/50. El usuario necesita poder arrastrar la barra divisoria: a veces necesita más espacio para leer una foja pequeña, y otras veces más espacio para ver las columnas de precios en la tabla.
*Costo de adopción:* Muy bajo (horas). Consiste en envolver el visor y la tabla en contenedores `<div>` y ejecutar `Split(['#panel-visor', '#panel-tabla'])`.

## 5. Revisión Humana (Corregir datos con mínimos clics)
**Opciones:**
- **Elemento `<dialog>` Nativo de HTML5**
  - *Licencia:* N/A
  - *Peso:* 0 KB
  - *Qué resuelve:* Modales estándar del navegador. Pueden ser modales que bloqueen el fondo, o paneles flotantes (`<dialog open>`).
- **Floating UI (antes Popper.js)**
  - *Licencia:* MIT
  - *Peso:* ~25 KB
  - *Build / Internet:* No requiere build. Funciona offline.
  - *Qué resuelve:* Posiciona pequeños pop-overs pegados a botones o celdas asegurando que no se corten por los bordes de la pantalla.

**Recomendación:** **`<dialog>` Nativo para edición estructurada, Floating UI para advertencias en contexto**.
*Por qué:* No requerimos librerías pesadas (como SweetAlert). Un simple `<dialog>` nativo puede flotar sobre la tabla para editar un precio. Si la alerta es "¿De dónde salió esto?", Floating UI es perfecto para mostrar una flecha apuntando a la celda exacta sin tapar el PDF.
*Costo de adopción:* Bajo. El `<dialog>` ya está en todos los navegadores modernos.

## 6. Accesibilidad y Claridad (Pantallas de Fiscalía 1366x768)
**Opciones:**
- **Pico.css**
  - *Licencia:* MIT
  - *Peso:* ~10 KB
  - *Build / Internet:* No requiere build. Se incluye en el `<head>`.
  - *Qué resuelve:* Framework CSS semántico. Da estilos limpios, de alto contraste y legibles a las etiquetas HTML por defecto (tablas, botones, inputs) sin tener que ponerles clases manuales.
- **Tailwind CSS (Vía Standalone CLI)**
  - *Licencia:* MIT
  - *Build / Internet:* **Requiere build** (ejecutar un binario localmente que escanea el HTML y compila un CSS final).

**Recomendación:** **Pico.css (o estandarizar CSS Variables si ya hay CSS hecho)**.
*Por qué:* Evitamos agregar el paso de compilación que requiere Tailwind. Pico.css automáticamente mejora los tamaños de letra, el contraste de formularios y la legibilidad para las jornadas largas de los empleados, optimizando el espacio.
*Costo de adopción:* Bajo, pero puede requerir purgar CSS viejo que entre en conflicto con los nuevos estilos por defecto.

---

## Lo que NO conviene adoptar y por qué

1. **React / Vue / Angular / Svelte (SPAs completas)**: 
   - **Por qué no:** Rompe la regla de "sin build". Requieren Node.js, gestores de paquetes (npm), un *bundler* (Webpack/Vite) y cambian el paradigma por completo: habría que reescribir toda la aplicación. No aportan un valor que justifique el gigantesco costo de adopción y mantenimiento para este proyecto.
2. **Bootstrap o Material UI**:
   - **Por qué no:** Material Design usa "paddings" muy amplios, lo cual desperdicia muchísimo espacio vertical y horizontal. En pantallas de 1366x768, necesitamos una alta **densidad de información** (ver muchos renglones de contrataciones a la vez sin tener que hacer scroll constantemente). Además, Bootstrap clásico incluye JS extra que hoy es redundante.
3. **Cargar librerías desde CDNs públicos (unpkg, cdnjs, Google Fonts)**:
   - **Por qué no:** Falla la restricción estricta de seguridad y offline. Si la fiscalía bloquea la red o hay intermitencia externa, la app no cargaría fuentes ni scripts, quedando inutilizable.

---

## 3 Mejoras de Experiencia Rápidas (Sin librerías)

Estas son mejoras que podemos implementar de inmediato usando solo HTML/CSS/JS nativo, modificando lo que ya tenemos sin sumar un solo KB externo:

1. **Tabla con Cabecera y Primera Columna Fijas (`position: sticky`)**
   - **Qué es:** En el CSS de nuestra tabla actual, aplicar `position: sticky; top: 0` al `<thead>` y `position: sticky; left: 0` al primer `<th>` o `<td>` (ej: N° de Ítem).
   - **Impacto:** Al hacer scroll hacia abajo o a la derecha en una lista larga de fojas, el empleado nunca pierde el contexto de qué columna está leyendo ni a qué contratación pertenece la fila.

2. **Navegación por Teclado en Tablas de Revisión**
   - **Qué es:** Un script nativo que escuche las flechas `Arriba / Abajo` (`keydown`) para mover el "foco" entre las filas de la tabla de renglones, y que al apretar `Enter` se active la misma función de clic que muestra la foja en el panel derecho.
   - **Impacto:** Un fiscal revisando 500 renglones no tiene que usar el mouse constantemente. Puede navegar con el teclado y observar el PDF a la derecha actualizándose al instante. Aumenta la velocidad de revisión drásticamente.

3. **Autocentrado de Resaltados (`scrollIntoView`)**
   - **Qué es:** Cuando el usuario hace clic en "Ver origen" de un dato, el JS localiza la caja (el elemento HTML del resaltado) sobre la foja y ejecuta `caja.scrollIntoView({ behavior: 'smooth', block: 'center' })`.
   - **Impacto:** El empleado no tiene que scrollear manualmente la imagen o el PDF para encontrar dónde está el número de 3 píxeles de alto. La pantalla viaja sola hasta el lugar exacto y lo pone en el centro de su visión. Trazabilidad perfecta.
