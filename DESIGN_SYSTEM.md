# Sistema visual

Cómo se ve y por qué. Está escrito para que alguien que no participó del desarrollo
pueda agregar una pantalla sin desarmar el conjunto.

Esto no es un producto de consumo: es una herramienta que va a usar gente de una
fiscalía ocho horas por día, en oficinas con luz de tubo y monitores viejos, para
producir documentos que se firman y entran a un legajo. Todas las decisiones de abajo
salen de ahí.

---

## 1. La regla que manda: la tipografía es la etiqueta de procedencia

Este sistema mezcla tres cosas que **nunca** se pueden confundir entre sí:

| Familia | Qué dice | Dónde |
|---|---|---|
| **Monoespaciada** — IBM Plex Mono | **Un dato leído de un papel**, con su anclaje: archivo, foja, recuadro | valores extraídos, documentos, montos, fechas, sha256 |
| **Serif** — Source Serif 4 | **Texto del documento**, o una interpretación (en bastardilla) | prosa explicativa, carril de interpretación |
| **Sans** — Archivo | **La aplicación hablando** | rótulos, botones, navegación, encabezados |

Si un dato leído de un escaneo aparece en sans, la pantalla está mintiendo sobre de
dónde salió. Es el error más caro que se puede cometer en este sistema, y por eso la
familia tipográfica —y no un ícono ni un color— es la que lo dice.

Las tres se sirven **desde disco** (`assets/fuentes/`). Ninguna llamada de red: el
sistema tiene que andar en una máquina desconectada, y una tipografía que llega de un
CDN también le cuenta a alguien que este equipo está mirando este legajo.

---

## 2. Color

### La paleta

Papel y tinta, no blanco y negro. El fondo es un blanco cálido de papel de expediente
y la tinta es un negro azulado, no `#000`.

| Token | Claro | Oscuro |
|---|---|---|
| `--papel` | `#FCFBF9` | `#16181B` |
| `--papel-2` | `#F1EFEA` | `#1E2126` |
| `--papel-3` | `#E7E4DD` | `#272B31` |
| `--tinta` | `#1B1D21` | `#E6E3DC` |
| `--tinta-2` | `#5A5D64` | `#9B9A95` |
| `--tinta-3` | `#84868C` | `#75767A` |
| `--filete` | `#CFCBC2` | `#33373D` |
| `--filete-2` | `#E3E0D9` | `#25292E` |
| `--borde-control` | `#8C8A80` | `#6D6B64` |
| `--sello` | `#23477A` | `#7EA3D6` |
| `--sello-suave` | `#DCE4F0` | `#1C2836` |
| `--interp` | `#E9EDF3` | `#1B2028` |
| `--interp-filete` | `#7F97B8` | `#4A5E7A` |
| `--verde` | `#2C5946` | `#79B79B` |
| `--ambar` | `#8A6714` | `#D0A63F` |
| `--lapiz` | `#96301F` | `#E08472` |
| `--lapiz-suave` | `#F4E2DE` | `#31201D` |
| `--marca` | `#31629E` | `#5A8CCF` |
| `--marca-solape` | `#A8402A` | `#CC6A52` |

### Qué significa cada color

* **`--sello` (azul)** — el sistema afirmando algo: enlaces, sellos, la pestaña activa.
* **`--verde`** — firme. Se puede sumar, cruzar y llevar a un informe.
* **`--ambar`** — atención: se puede trabajar igual, pero conviene mirarlo.
* **`--lapiz` (rojo)** — alerta o trabajo pendiente. Es el lápiz rojo del corrector.
* **`--interp`** — el carril de interpretación. Fondo propio, para que una hipótesis
  nunca se lea como un dato.
* **`--marca` / `--marca-solape`** — la cronología. Un solo tono para los contratos; el
  rojo marca **únicamente** la superposición, que es lo que el gráfico existe para
  mostrar. La cámara va como texto en el rótulo: la identidad no depende del color.

**Todos los colores viven en los dos bloques de paleta.** `--marca` y `--marca-solape`
estaban en un `:root` suelto doscientas líneas más abajo, y por eso ninguna prueba de
contraste los miraba. Un color fuera de la paleta es un color que nadie mide.

### `--filete` no es `--borde-control`

Son dos cosas distintas y se confunden fácil:

* `--filete` es una **raya que separa**: el borde de una tabla, la línea entre bloques.
  Es adorno estructural. WCAG lo excluye del criterio de contraste a propósito, y
  subirle el contraste ensucia la página sin que nadie gane nada.
* `--borde-control` es el **límite de algo que se toca**: un campo, un selector, un
  botón. Un campo cuyo borde no se ve es un campo que alguien no encuentra.

Usar `--filete` en el borde de un `input` da **1,57:1** y queda por debajo del mínimo
sin que nada falle a la vista. `pruebas/test_accesibilidad.py` lo verifica.

---

## 3. Accesibilidad — WCAG 2.1 AA, medido

No se estima a ojo. `pruebas/test_accesibilidad.py` calcula la relación de luminancia
de cada par que existe de verdad en la interfaz, **en los dos temas**, y falla si alguno
baja del mínimo.

| Par | Dónde | Claro | Oscuro | Pide |
|---|---|---|---|---|
| `--tinta` sobre `--papel` | texto normal | 16.32:1 | 13.88:1 | 4.5:1 |
| `--tinta` sobre `--papel-2` | texto sobre bloque gris | 14.69:1 | 12.60:1 | 4.5:1 |
| `--tinta-2` sobre `--papel` | prosa secundaria | 6.38:1 | 6.31:1 | 4.5:1 |
| `--tinta-2` sobre `--papel-2` | prosa secundaria sobre gris | 5.74:1 | 5.73:1 | 4.5:1 |
| `--tinta-3` sobre `--papel` | rótulos y marginalia | 3.52:1 | 3.92:1 | 3.0:1 |
| `--sello` sobre `--papel` | enlaces y sellos | 9.01:1 | 6.86:1 | 4.5:1 |
| `--sello` sobre `--papel-2` | enlaces sobre gris | 8.11:1 | 6.22:1 | 4.5:1 |
| `--verde` sobre `--papel` | sello «al día» | 7.74:1 | 7.67:1 | 4.5:1 |
| `--ambar` sobre `--papel` | sello de atención | 5.04:1 | 7.80:1 | 4.5:1 |
| `--lapiz` sobre `--papel` | sello de alerta | 7.41:1 | 6.53:1 | 4.5:1 |
| `--lapiz` sobre `--lapiz-suave` | aviso de datos de demostración | 6.13:1 | 5.69:1 | 4.5:1 |
| `--tinta` sobre `--lapiz-suave` | texto del aviso de demostración | 13.49:1 | 12.09:1 | 4.5:1 |
| `--papel` sobre `--lapiz` | número sobre el chip rojo de la barra | 7.41:1 | 6.53:1 | 4.5:1 |
| `--tinta` sobre `--interp` | carril de interpretación | 14.36:1 | 12.76:1 | 4.5:1 |
| `--tinta-2` sobre `--interp` | prosa del carril de interpretación | 5.61:1 | 5.80:1 | 4.5:1 |
| `--sello` sobre `--sello-suave` | aviso de foja enderezada | 7.28:1 | 5.76:1 | 4.5:1 |
| `--borde-control` sobre `--papel` | borde de campos y botones | 3.35:1 | 3.34:1 | 3.0:1 |
| `--borde-control` sobre `--papel-2` | borde de controles sobre gris | 3.01:1 | 3.03:1 | 3.0:1 |
| `--marca` sobre `--papel` | barra de contrato en la cronología | 6.02:1 | 5.16:1 | 3.0:1 |
| `--marca-solape` sobre `--papel` | barra de superposición | 5.92:1 | 4.87:1 | 3.0:1 |

### Nada se dice sólo con color

Un estado que se distingue únicamente por el color no existe para quien no distingue ese
color, ni en una impresión en blanco y negro — **y esto se imprime**. Cada estado lleva
además una palabra:

```
[ AL DÍA ]        verde   + la palabra
[ 2 A REVISAR ]   rojo    + el número y la palabra
[ CONFLICTO ]     rojo    + la palabra
```

La primera columna de «Estado del sistema» es un sello con texto, no un punto de color,
por el mismo motivo.

### Foco visible

`:focus-visible{outline:2px solid var(--sello); outline-offset:2px}` — sin excepciones.
Toda la aplicación se puede recorrer con teclado; la cola además tiene `J`/`K` y una
tecla por acción, y esos atajos **se ocultan en pantallas chicas** porque decir «apretá
J» donde no hay teclado es peor que no decir nada.

### Teléfono

* Botones y campos: `min-height:44px`, que es la medida abajo de la cual se falla el toque.
* Campos a `font-size:16px`: con menos, iOS hace zoom al tocarlos y descuadra la pantalla.
* La cinta de legajo se queda pegada arriba; el encabezado y las pestañas se van con el
  scroll. En una pantalla de 844 px de alto se comían 200 entre las dos.

---

## 4. La retícula

Una **canaleta de 112 px** a la izquierda, con el folio y el rótulo del bloque. Es la
marginalia de un expediente: dice dónde estás sin ocupar el lugar del contenido.

```
┌──────────┬────────────────────────────────────────────┐
│ f. 0002  │  Estado del lote                           │
│ LOTE     │  ────────────────────────────────────────  │
│          │  contenido                                 │
└──────────┴────────────────────────────────────────────┘
```

En pantallas de menos de 720 px la canaleta desaparece y el rótulo pasa arriba.

### Las tiras de arriba, y cómo se apilan

Hay hasta tres pegadas al borde superior: el **aviso de datos de demostración**, la
**cinta de legajo** y el **techo** (encabezado + pestañas).

Sus posiciones **las mide el navegador** y las escribe en `--h-demo`, `--h-cinta` y
`--h-techo` (ver `medirTecho` en `app.js`). No están escritas a mano, y hay un motivo:
antes eran seis números repartidos por la hoja (`0`, `37`, `59`, `96`, `150`, `190`) y
**eran mentira** — el encabezado mide 71 px y el CSS decía 59, así que la barra de
pestañas se le montaba encima 12 px. Peor: el alto real depende de si las pestañas
entran en uno o dos renglones, que depende del ancho de la ventana. Ningún número
escrito a mano puede acertar eso.

---

## 5. Navegación

**Dos niveles.** Seis secciones arriba y, debajo, lo que hay adentro de la que está
abierta. La estructura vive en `SECCIONES`, en `app.js`; la barra se arma sola.

```
Panel │ Cargar escaneos │ Documentos │ Hallazgos │ Revisión (6) │ Sistema
──────────────────────────────────────────────────────────────────────────
Contratos │ Facturas y recibos │ Personas │ Buscar
```

**Dos barras y no un menú desplegable, a propósito.** Un desplegable esconde: hay que
saber qué hay adentro para ir a buscarlo, no anda con el dedo igual que con el mouse, y
el que no lo encuentra concluye que el sistema no lo tiene.

Las **cuentas de trabajo pendiente suben a la sección**: si «Revisión» esconde 88 campos
esperando, la barra lo dice sin que haya que entrar.

Medido: una fila por barra en 1440, 1366 y 1024 (antes eran dieciséis enlaces planos que
se partían en dos renglones), y tres renglones en un teléfono en vez de cinco.

---

## 6. Componentes

### Sello — `.sello`
Estado, en versalitas con doble filete. Variantes: `.ok` (verde), `.alerta` (rojo),
`.atencion` (ámbar), y la de base (azul).

### Cifra — `.cifra`
Un número grande con su rótulo abajo. En grilla auto-ajustable de mínimo 132 px.
Variantes: `.firme` (filete verde), `.provisional` (fondo gris), `.facturado` (filete
azul), `.alerta`.

**El filete de `.facturado` es distinto del de `.firme` y no es decoración:** son dos
platas que no se suman, y si los dos bloques se ven iguales el ojo los lee como partes
de un mismo total.

### Valor nulo — `.nulo`
`Ø motivo`. Nunca una celda vacía y nunca un cero: `Ø a mano`, `Ø sin leer`, `Ø ilegible`.
**Cero significa «es cero» y vacío significa «no lo sabemos».** No son lo mismo y no se
muestran igual.

### Barra de confianza — `.barra-conf`
Cinco muescas. Verde ≥ 0,85, ámbar ≥ 0,5, rojo abajo. Va **además** del estado escrito,
nunca en lugar de él.

### Tabla — `tabla(cols, filas, opts)`
Siempre adentro de `.tabla-env`, que tiene `overflow-x:auto`: **el cuerpo de la página
nunca se desplaza de costado**, la tabla sí.

`opts.lista` marca qué muestra la tabla. Hace falta cuando una pantalla tiene más de
una: enganchar el clic por «la última tabla» funcionaba hasta que se agregó otra debajo,
y entonces cada fila abría el documento equivocado.

### Tabla grande — `tablaBuscable(destino, cols, filas, opts)`
Para las tablas que **crecen con el legajo**: contratos, facturas, personas, el cruce.
Trae buscador, orden por columna y render por tandas de 150.

Medido en un legajo de 1.500 contratos y 3.047 facturas: la de facturas pintaba 3.047
filas, 51.085 nodos y **106.400 px de alto**. Cien metros de página, sin forma de
encontrar a nadie salvo desplazarse leyendo. Con el componente: 2.681 nodos y 5.835 px.

Tres reglas:

* el filtro corre sobre **todas** las filas, no sobre las pintadas — si no, un apellido
  aparece o no según hasta dónde bajaste;
* ignora tildes y mayúsculas: quien busca «peres» tiene que encontrar a Pérez, porque el
  nombre puede venir de un OCR y nadie sabe cómo quedó escrito;
* al ordenar, **lo que falta va al final**. Un contrato sin monto legible no puede
  colarse arriba como si valiera cero: no vale cero, no se sabe cuánto vale.

Las tablas que no crecen —superposiciones, fusiones— usan `tabla()` a secas: un buscador
arriba de cuatro filas es ruido.

### Estado vacío — `vacio(titulo, texto, accion)`
Nunca una grilla de ceros: qué es esto, y qué hacer ahora.

---

## 7. Cómo se escriben los números y las palabras

Vive en `ufil/castellano.py` y en las funciones de formato de `app.js`.

* **Plural que concuerda.** `plural(1, 'archivo', 'archivos')` → «1 archivo». Nunca
  `1 archivo(s)`: un organismo que le manda a un juez un documento que dice «1
  contrato(s)» está diciendo, sin querer, que nadie lo leyó antes de mandarlo.
* **Fechas dd/mm/aaaa.** La base guarda ISO porque ordena bien; eso es una decisión de
  almacenamiento y no tiene por qué asomarse a una pantalla.
* **Importes con coma decimal y punto de miles:** `$4.850.000,00`.
* **Nombres de campo en castellano**, y **según el documento**: `monto` es «Monto
  mensual» en un contrato e «Importe» en una factura; `fecha_inicio` es «Fecha de
  emisión» en un comprobante. Rotularlos igual afirma algo que el papel no dice.
* **Cámaras por su nombre**, no `A` y `B`.

`pruebas/test_castellano.py` verifica todo esto, incluido que no vuelva a aparecer un
`(s)`.

---

## 8. Impresión

Se imprime, y se imprime en blanco y negro. `@media print` quita la navegación y los
botones, vuelve todo estático, y **deja la cinta de legajo**: en un papel suelto, saber
de qué causa es lo primero que hace falta.

---

## 9. Al agregar una pantalla

1. Envolvela en `bloque(folio, rotulo, html)`.
2. Elegí la familia tipográfica por **procedencia del dato**, no por estética.
3. Si hay un valor que puede faltar, mostralo como `Ø motivo`, nunca vacío ni en cero.
4. Si mostrás plata, decí si es **firme** o **provisional**, y si es **contratada** o
   **facturada**. Nunca sumes las dos.
5. Sumala a `SECCIONES` en `app.js` — no escribas el enlace a mano en el HTML.
6. Corré `python -m unittest discover -s pruebas`: hay pruebas de contraste, de
   castellano y de que la interfaz no muestre nombres técnicos.
7. Miralas en 1440, 1366, 1024 y 390. El cuerpo de la página no puede desplazarse de
   costado en ninguno.
