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

### La paleta institucional

Los colores son los del Ministerio Público Fiscal de Entre Ríos. No decoran: nombran.
Cuatro familias, y cada una tiene un oficio del que no se sale.

| | Token | Claro | Oscuro |
|---|---|---|---|
| **verde institucional** | `--verde-inst` | `#23594C` | `#72B5A2` |
| **verde operativo** | `--verde-oper` | `#2F7463` | `#72B5A2` |
| **turquesa Paraná** | `--turquesa` | `#4D927F` | `#5FA894` |
| **dorado justicia** | `--oro` | `#D7B46A` | `#E5C57C` |
| **rojo** | `--lapiz` | `#B71C1C` | `#F08B8B` |
| papel cálido | `--papel` | `#FCFBF8` | `#0B1213` |
| fondo secundario | `--papel-2` | `#F2F0E9` | `#111C1B` |
| superficie elevada | `--papel-3` | `#E8E5DB` | `#172522` |
| azul tinta | `--tinta` | `#0F172A` | `#F2F5F2` |
| texto secundario | `--tinta-2` | `#5D6B66` | `#AEBBB7` |
| marginalia | `--tinta-3` | `#78857F` | `#8A9A95` |
| filete decorativo | `--filete` | `#DCD9CF` | `#2C413C` |
| borde de control | `--borde-control` | `#70827C` | `#5A7A74` |
| barra lateral | `--barra` | `#23594C` | `#111C1B` |
| ítem abierto | `--barra-2` | `#1B4A3E` | `#1B2E2A` |
| ítem bajo el puntero | `--barra-3` | `#2F7463` | `#24413B` |
| texto de la barra | `--barra-txt` | `#F4F8F6` | `#F2F5F2` |
| rótulos de la barra | `--barra-txt-2` | `#B9D2C8` | `#AEBBB7` |
| enlaces y sellos | `--sello` | `#23594C` | `#72B5A2` |
| carril de interpretación | `--interp` | `#EDF3F0` | `#14201F` |
| su borde | `--interp-filete` | `#43836F` | `#5A857A` |
| atención | `--ambar` | `#8A6714` | `#E5C57C` |
| cronología | `--marca` | `#2F7463` | `#5FA894` |
| superposición | `--marca-solape` | `#B71C1C` | `#F08B8B` |

### Qué puede decir cada color

* **Verde institucional** — quién sos y dónde estás parado: la barra lateral, la marca,
  los enlaces, el botón que hace la acción principal.
* **Turquesa Paraná** — información y avance: barras de progreso, el carril de
  interpretación, los trazos de la cronología. Da **3,54:1** sobre el papel: alcanza
  para un trazo o un borde (WCAG 1.4.11 pide 3:1) y **no alcanza para texto corriente**.
  Donde el turquesa tiene que hablar, habla el verde operativo (5,34:1).
* **Dorado justicia** — detalle institucional, y nada más. Da **1,91:1** sobre el papel:
  sobre el papel es adorno y no puede llevar información. Sobre el verde de la barra da
  4,08:1 y ahí sí marca el ítem activo. Hay una prueba
  (`ElDoradoNoLlevaInformacion`) que verifica que `color:var(--oro)` no aparezca fuera
  de la barra lateral.
* **Rojo** — error, conflicto y destrucción. Sólo eso. Un rojo que también sirve para
  «importante» es un rojo que ya no alarma a nadie. En los botones vive únicamente en
  `.boton.peligro` y `.mini.peligro`, que son los que borran algo.
* **`--interp`** — el carril de interpretación. Fondo propio, para que una hipótesis
  nunca se lea como un dato.
* **`--marca` / `--marca-solape`** — la cronología. Un solo tono para los contratos; el
  rojo marca **únicamente** la superposición, que es lo que el gráfico existe para
  mostrar. La cámara va como texto en el rótulo: la identidad no depende del color.

**Todos los colores viven en los tres bloques de paleta.** `--marca` y `--marca-solape`
estuvieron en un `:root` suelto doscientas líneas más abajo, y por eso ninguna prueba de
contraste los miraba. Un color fuera de la paleta es un color que nadie mide.

### El oscuro es una paleta pensada, no la clara dada vuelta

Los verdes suben de luminosidad para no apagarse contra el fondo, y el fondo tira a
verde muy oscuro —no a gris— para que siga siendo la misma casa. Se declara **dos
veces**: una para `prefers-color-scheme: dark` y otra para `[data-tema="oscuro"]`, que
es la elección explícita. Son idénticas a propósito, y por eso mismo se separan solas:
se toca una, se olvida la otra, y el que eligió el oscuro a mano ve una pantalla
distinta que el que lo tiene por preferencia del sistema.
`ElOscuroEsUnaPaletaYNoDosSueltas` verifica que no se separen.

El botón dice **«Activar modo oscuro»** / **«Activar modo claro»**: qué va a pasar si lo
tocás. Decía «Tema», que no es ni una pregunta ni una respuesta.

### Movimiento

Un solo tiempo para todo: `--paso: 140ms` con `--curva: cubic-bezier(.2,.6,.3,1)`. Se
mueve lo que ayuda a entender qué pasó —de dónde salió el cajón de la barra lateral, que
la fila que acabás de decidir se fue— y nada más. La única cosa que se mueve sola es la
rueda del sello «trabajando», porque decir «esperá» con algo quieto no se distingue de
decirlo con algo colgado.

`prefers-reduced-motion: reduce` lo apaga **todo**, sin excepciones: hay gente a la que
el movimiento le da náuseas o le dispara una migraña.

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
* La barra lateral se guarda y se abre con el botón de la izquierda del techo. 232 px
  fijos son un cuarto de la pantalla gastado en decir dónde estás.
* La barra de arriba se queda pegada: es un renglón, y es lo único que dice sobre qué
  causa se está mirando.

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

### El armazón

La pantalla se parte en dos y no cambia nunca: a la izquierda **dónde estás parado**
(la barra lateral, verde institucional macizo), a la derecha **en qué estás trabajando**.
Arriba de la derecha, una barra de un renglón con el legajo abierto, el lote, qué está
haciendo el sistema y la búsqueda.

Antes eran tres tiras apiladas contra el borde superior —aviso, cinta de legajo,
encabezado con dos filas de pestañas— y cada una tenía que empezar donde terminaba la
anterior. En 1024 px de ancho las pestañas caían en dos renglones, el techo se comía
190 px de alto y de una pantalla de 768 px quedaba menos de la mitad para el expediente.
Y el alto dependía del ancho de la ventana, así que ningún número escrito a mano
acertaba: seis números repartidos por la hoja (`0`, `37`, `59`, `96`, `150`, `190`) y
**eran mentira** — el encabezado medía 71 px y el CSS decía 59, así que la barra de
pestañas se le montaba encima 12 px.

Con la barra al costado el alto de arriba es uno solo y ya no depende del ancho. Se
sigue midiendo con `medirTecho` —el aviso de datos de demostración aparece y
desaparece— pero ahora hay **una sola cosa que medir**.

---

## 5. Navegación

**Tres niveles, en la barra lateral.** La marca arriba (organismo → unidad → área →
herramienta), las seis secciones en el medio, y adentro de la que está abierta sus
ítems. La estructura vive en `SECCIONES`, en `app.js`; la barra se arma sola.

```
┌─ UFIL Paraná ───────────────┐
│  Área Anticorrupción        │
│  ─────────────────────────  │  ← filete dorado
│  Ministerio Público Fiscal  │
│  de la Provincia de …       │
├─────────────────────────────┤
│  ⌂ Panel                    │
│  ↑ Cargar escaneos          │
│  ▤ Documentos               │
│  ⌕ Hallazgos                │
│ ▌⋮ Revisión            (49) │  ← abierta: fondo, negrita y filete dorado
│    · Cola de revisión  (42) │
│    · Identidad          (7) │
│    · Quedaron afuera        │
│  ✳ Sistema                  │
├─────────────────────────────┤
│  ☾ Activar modo oscuro      │
│    Acerca del sistema       │
└─────────────────────────────┘
```

**Al costado y no arriba, a propósito.** Las pantallas son anchas y bajas: 1366×768 y
1024×768 son las que hay en las oficinas. Cada renglón que se gasta arriba es un
renglón menos de expediente; a lo ancho, en cambio, sobra.

**Nada de menús desplegables.** Un desplegable esconde: hay que saber qué hay adentro
para ir a buscarlo, no anda con el dedo igual que con el mouse, y el que no lo encuentra
concluye que el sistema no lo tiene.

La sección abierta se marca **de tres maneras a la vez** —fondo, negrita y un filete
dorado al costado— porque una sola de las tres se le escapa a alguien.

Las **cuentas de trabajo pendiente suben a la sección**: si «Revisión» esconde 49 cosas
esperando, la barra lo dice sin que haya que entrar.

En pantallas de menos de 900 px la barra es un **cajón**: se abre con el botón de la
izquierda del techo, se cierra con Escape, tocando el velo, o sola cuando elegís a dónde
ir. Verificado en 390×844.

---

## 6. Componentes

### Sello de estado — `.estado`, `sello(tono, texto)`
**Ícono + palabra + color, siempre los tres, en todas las pantallas.** Tonos: `ok`,
`atencion`, `alerta`, `neutro`, `trabajando`.

El color es el **tercer** refuerzo y nunca el único. Una fila que informa su estado sólo
con color no le informa nada a quien no distingue el rojo del verde —entre el 5 y el 8 %
de los varones— ni a nadie cuando esto sale impreso en blanco y negro, que es como llega
a una audiencia.

Los íconos son cinco trazos sin relleno, del tamaño de la letra: al lado de una
tipografía nítida, un ícono relleno pesa más que la palabra y se lleva la lectura.

`pintarSello(el, tono, texto)` pinta adentro de un nodo que ya existe, sin reemplazarlo:
el sello del techo se repinta en cada refresco y cambiarlo por otro le haría perder el
id, los escuchadores y el lugar en el orden de tabulación.

### Cuño — `.sello`
El sello viejo, cuadrado y con doble filete. Sigue existiendo donde hace falta un cuño y
no un estado: la portada de un informe, el rótulo de un bloque impreso.

### Diálogo de confirmación — `.dialogo`
`<dialog>` del navegador y no un `div` propio: trae solo el foco atrapado adentro,
Escape para cerrar, y el resto de la página marcado como inerte para quien navega con
lector de pantalla. Escribir eso a mano sale mal casi siempre.

**Para confirmar algo destructivo hay que escribir el número del legajo**, y el botón
está apagado hasta que coincide. Una casilla que se tilda se tilda mirando el cartel; el
número obliga a mirar *cuál* es el legajo que se está por sacar. Y un botón prendido que
después rechaza es un botón que enseña a apretar sin leer.

### Botones
`.boton` al contorno en verde operativo; `.boton.lleno` para la acción principal de una
pantalla —en una hoja con ocho botones al contorno, el que hay que apretar tiene que
distinguirse sin leerlos todos—; `.boton.gris` para lo secundario; `.boton.peligro` y
`.mini.peligro` en rojo, **sólo** para lo que destruye algo.

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

### Taller — `.taller` (la cola de revisión)
La cola no es una página: es un **puesto de trabajo**. Ocupa el alto entero de la
ventana y se parte en cuatro fajas —encabezado con el «1 de N», filtros, los dos paneles,
pie—, donde las tres que no son los paneles quedan quietas.

```
┌──────────────────────────────────────────────┬──────────────┐
│ Cola de revisión                    1 de 42  │              │  ← queda quieta
├──────────────────────────────────────────────┴──────────────┤
│ DOCUMENTO ▾   CAMPO ▾   MOTIVO ▾                            │  ← queda quieta
├──────────────────────────────────────┬──────────────────────┤
│ contrato_A_0020  Monto mensual   C X │   ┌──────────────┐   │
│ contrato_A_0029  Monto mensual  1 2 N│   │  el renglón  │   │
│ contrato_A_0031  Monto mensual  1 2 N│   └──────────────┘   │  ← la foja entra
│              ↕ lo único que se mueve │   la foja entera     │     entera
├──────────────────────────────────────┴──────────────────────┤
│ J/K para moverse. Ninguna acción es «aceptar todo».         │  ← queda quieta
└─────────────────────────────────────────────────────────────┘
```

**Una sola barra de desplazamiento.** Antes la página tenía la suya y la lista tenía otra
adentro, a un centímetro de distancia, y cuál de las dos movía la rueda del mouse
dependía de dónde hubiera quedado el puntero. Encima el «1 de 42» y los filtros se iban
para arriba a las tres filas, justo cuando más falta hacen: revisando el campo treinta,
saber que vas por el treinta es la mitad del sentido de la tarea.

El alto **no se mide con JavaScript**: `#cuerpo` toma el alto de la ventana, el techo y
el aviso ocupan lo suyo, y `main` se queda con el resto por ser el único que crece. El
navegador ya sabe restar.

Medido con la cola de 42 campos abierta:

| | la página | adentro |
|---|---|---|
| 1440×900 claro y oscuro | no se desplaza | `#cola` (3483 > 593) |
| 1366×768 claro | no se desplaza | `#cola` (3492 > 461) |
| 1024×768 claro y oscuro | no se desplaza | `#cola` (5583 > 451) |
| 390×844 claro | se desplaza | nada |

En el teléfono la que corre es la página, que es lo correcto: los dos paneles no entran
uno al lado del otro y forzar el alto de la ventana dejaría dos cajitas de 200 px donde
no se puede trabajar. `pruebas/test_taller.py` verifica las reglas de las que sale eso.

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

## 9. La identidad institucional

La jerarquía se respeta en todas las pantallas, de arriba abajo:

```
Ministerio Público Fiscal de la Provincia de Entre Ríos   ← el organismo
  UFIL Paraná                                             ← la unidad
    Área Anticorrupción                                   ← el área
      Análisis documental                                 ← esta herramienta
```

Los **fiscales** van en segundo plano —pantalla de acceso, «Acerca del sistema»,
encabezado de lo que se exporta— y nunca compitiendo con el dato de la pantalla.

**Ningún nombre está escrito en un componente.** Todos salen de `ufil/identidad.py`, que
se puede pisar de tres maneras, de la más general a la más particular:

1. los valores del módulo, que son los que corresponden hoy;
2. un `identidad.json` en la carpeta de datos;
3. variables de entorno `UFIL_UNIDAD`, `UFIL_AREA`, `UFIL_FISCALES`… —así se cambia en
   un despliegue sin tocar el código. Varios fiscales se separan con **punto y coma**:
   los nombres llevan coma adentro («Pérez, Juan») y la coma no sirve de separador.

Estaban repartidos en once archivos: el encabezado HTML, la portada del Excel, la
pantalla de acceso, el título de la pestaña, el pie de los informes. Cambiar de fiscal
significaba buscarlos todos, y el que quedaba sin cambiar era el que después aparecía
impreso en una presentación.

### El monograma, y el escudo oficial

El monograma es una **foja con su lomo y un filete dorado**: SVG en línea, 2 kB, nítido
en cualquier tamaño, cambia de color con el tema. Nada de mazos, balanzas, columnas
grecorromanas ni escudos inventados.

El **archivo oficial** del organismo se deja caer en `assets/marca/logo.svg` (o `.png`) y
la barra lateral lo muestra sola. No viaja en el repositorio: es material institucional
del organismo, no del proyecto, y un emblema oficial redibujado de memoria queda mal y
no corresponde usarlo así. Ver `assets/marca/LEEME.md`.

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
