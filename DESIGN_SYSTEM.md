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

Cuatro familias, y cada una tiene un oficio del que no se sale.

| | Token | Claro | Oscuro |
|---|---|---|---|
| **azul tribunal** | `--tribunal` | `#1C3557` | `#7FA9D6` |
| **azul de texto** | `--tribunal-txt` | `#2A5480` | `#7FA9D6` |
| **río** | `--rio` | `#4E88B5` | `#6B9FCB` |
| **dorado justicia** | `--oro` | `#D7B46A` | `#E5C57C` |
| **punzó** | `--lapiz` | `#A81F26` | `#F08B8B` |
| verde de «firme» | `--verde` | `#2C6A4B` | `#74BC97` |
| ámbar de atención | `--ambar` | `#8A6714` | `#E5C57C` |
| papel | `--papel` | `#FCFBF8` | `#0B1119` |
| fondo secundario | `--papel-2` | `#F2F0E9` | `#111A25` |
| superficie elevada | `--papel-3` | `#E8E5DB` | `#18232F` |
| tinta | `--tinta` | `#0F172A` | `#F2F5F8` |
| texto secundario | `--tinta-2` | `#545F70` | `#AEB9C6` |
| marginalia | `--tinta-3` | `#6E7A8A` | `#8A96A5` |
| filete decorativo | `--filete` | `#DCD9CF` | `#2C3B4D` |
| borde de control | `--borde-control` | `#737E8C` | `#5C6D80` |
| barra lateral | `--barra` | `#1C3557` | `#111A25` |
| ítem abierto | `--barra-2` | `#142944` | `#1B2836` |
| bajo el puntero | `--barra-3` | `#26456B` | `#24354A` |
| texto de la barra | `--barra-txt` | `#F2F6FA` | `#F2F5F8` |
| rótulos de la barra | `--barra-txt-2` | `#B6C7DC` | `#AEB9C6` |
| enlaces y sellos | `--sello` | `#24466E` | `#7FA9D6` |
| carril de interpretación | `--interp` | `#EBF1F7` | `#131E2A` |
| su borde | `--interp-filete` | `#4A79A8` | `#5A82AC` |
| cronología | `--marca` | `#2A5480` | `#6B9FCB` |
| superposición | `--marca-solape` | `#A81F26` | `#F08B8B` |

### Qué puede decir cada color

* **Azul tribunal** — quién sos y dónde estás parado: la barra lateral, la marca, los
  enlaces, el botón que hace la acción principal. Es cromo: no informa nada sobre un
  dato.
* **Río** — información y avance: barras de progreso, el carril de interpretación, los
  trazos de la cronología. Da **3,68:1** sobre el papel: alcanza para un trazo o un
  borde (WCAG 1.4.11 pide 3:1) y **no alcanza para texto corriente**. Donde el río
  tiene que hablar, habla `--tribunal-txt` (7,58:1).
* **Dorado justicia** — detalle institucional, y nada más. Da **1,91:1** sobre el
  papel: ahí es adorno y no puede llevar información. Sobre el azul de la barra da
  6,26:1 y ahí sí marca el ítem activo. `ElDoradoNoLlevaInformacion` verifica que
  `color:var(--oro)` no aparezca fuera de la barra lateral.
* **Verde** — **firme**, y solamente firme. Ver abajo por qué esto merece un apartado.
* **Ámbar** — atención: hay trabajo por hacer, se puede trabajar igual.
* **Punzó** — error, conflicto y destrucción. Sólo eso. En los botones vive únicamente
  en `.boton.peligro` y `.mini.peligro`, que son los que borran algo.
* **`--marca` / `--marca-solape`** — la cronología. Un solo tono para los contratos; el
  punzó marca **únicamente** la superposición, que es lo que el gráfico existe para
  mostrar. La cámara va como texto en el rótulo: la identidad no depende del color.

### Por qué el cromo no puede ser verde

Este sistema tuvo una paleta verde, tomada de los círculos del escudo del organismo.
Se cambió, y el motivo vale escribirlo porque es un error fácil de repetir.

La distinción más importante del sistema es **firme contra provisional**: es la que
decide qué se puede sumar, cruzar y llevar a un informe. En la paleta verde, el token
del cromo (`--verde-oper`: botón principal, enlaces, sello «trabajando») y el token del
estado firme (`--verde`) eran **el mismo hex, `#2F7463`**. El color que decía «el
sistema afirma que este dato es firme» era el mismo que decía «esto es un botón».

Un color que significa dos cosas no significa ninguna. Con el azul de cromo, el verde
queda reservado para un solo significado en toda la pantalla, y ese significado es el
que más caro sale confundir.

El azul tampoco es ajeno a la casa: sale del celeste del escudo, igual que el verde
salía de los círculos.

### Movimiento

Un solo tiempo para todo: `--paso: 140ms` con `--curva: cubic-bezier(.2,.6,.3,1)`. Se
mueve lo que ayuda a entender qué pasó —de dónde salió el cajón de la barra lateral, que
la fila que acabás de decidir se fue— y nada más. La única cosa que se mueve sola es la
rueda del sello «trabajando», porque decir «esperá» con algo quieto no se distingue de
decirlo con algo colgado.

`prefers-reduced-motion: reduce` lo apaga **todo**, sin excepciones: hay gente a la que
el movimiento le da náuseas o le dispara una migraña.

### El oscuro es una paleta pensada, no la clara dada vuelta

Los azules suben de luminosidad para no apagarse contra el fondo, y el fondo tira a
azul muy oscuro —no a gris— para que siga siendo la misma casa. Se declara **dos
veces**: una para `prefers-color-scheme: dark` y otra para `[data-tema="oscuro"]`, que
es la elección explícita. Son idénticas a propósito, y por eso mismo se separan solas:
se toca una, se olvida la otra, y el que eligió el oscuro a mano ve una pantalla
distinta que el que lo tiene por preferencia del sistema.
`ElOscuroEsUnaPaletaYNoDosSueltas` verifica que no se separen.

El botón dice **«Activar modo oscuro»** / **«Activar modo claro»**: qué va a pasar si lo
tocás. Decía «Tema», que no es ni una pregunta ni una respuesta.

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
| `--tinta` sobre `--papel` | texto normal | 17.25:1 | 17.31:1 | 4.5:1 |
| `--tinta` sobre `--papel-2` | texto sobre bloque gris | 15.66:1 | 16.02:1 | 4.5:1 |
| `--tinta-2` sobre `--papel` | prosa secundaria | 6.25:1 | 9.52:1 | 4.5:1 |
| `--tinta-2` sobre `--papel-2` | prosa secundaria sobre gris | 5.67:1 | 8.81:1 | 4.5:1 |
| `--tinta-3` sobre `--papel` | rótulos y marginalia | 4.22:1 | 6.30:1 | 3.0:1 |
| `--sello` sobre `--papel` | enlaces y sellos | 9.33:1 | 7.71:1 | 4.5:1 |
| `--sello` sobre `--papel-2` | enlaces sobre gris | 8.46:1 | 7.13:1 | 4.5:1 |
| `--verde` sobre `--papel` | sello «al día» | 6.21:1 | 8.46:1 | 4.5:1 |
| `--ambar` sobre `--papel` | sello de atención | 5.03:1 | 11.38:1 | 4.5:1 |
| `--lapiz` sobre `--papel` | sello de alerta | 7.02:1 | 7.91:1 | 4.5:1 |
| `--lapiz` sobre `--lapiz-suave` | aviso de datos de demostración | 6.17:1 | 6.94:1 | 4.5:1 |
| `--tinta` sobre `--lapiz-suave` | texto del aviso de demostración | 15.15:1 | 15.20:1 | 4.5:1 |
| `--papel` sobre `--lapiz` | número sobre el chip rojo de la barra | 7.02:1 | 7.91:1 | 4.5:1 |
| `--tinta` sobre `--interp` | carril de interpretación | 15.69:1 | 15.39:1 | 4.5:1 |
| `--tinta-2` sobre `--interp` | prosa del carril de interpretación | 5.68:1 | 8.47:1 | 4.5:1 |
| `--sello` sobre `--sello-suave` | aviso de foja enderezada | 8.27:1 | 6.69:1 | 4.5:1 |
| `--borde-control` sobre `--papel` | borde de campos, selectores y botones | 3.99:1 | 3.57:1 | 3.0:1 |
| `--borde-control` sobre `--papel-2` | borde de controles sobre gris | 3.62:1 | 3.30:1 | 3.0:1 |
| `--marca` sobre `--papel` | barra de contrato en la cronología | 7.58:1 | 6.72:1 | 3.0:1 |
| `--marca-solape` sobre `--papel` | barra de superposición en la cronología | 7.02:1 | 7.91:1 | 3.0:1 |
| `--barra-txt` sobre `--barra` | ítems de la barra lateral | 11.40:1 | 16.02:1 | 4.5:1 |
| `--barra-txt-2` sobre `--barra` | rótulos de grupo en la barra lateral | 7.19:1 | 8.81:1 | 4.5:1 |
| `--barra-txt` sobre `--barra-2` | el ítem abierto de la barra lateral | 13.52:1 | 13.68:1 | 4.5:1 |
| `--barra-txt-2` sobre `--barra-2` | prosa del ítem abierto | 8.52:1 | 7.52:1 | 4.5:1 |
| `--barra-txt` sobre `--barra-3` | el ítem bajo el puntero | 9.01:1 | 11.40:1 | 4.5:1 |
| `--oro` sobre `--barra` | la marca del ítem activo, sobre el azul | 6.26:1 | 10.52:1 | 3.0:1 |
| `--barra-filete` sobre `--barra` | separadores de la barra: adorno, no información | 1.41:1 | 1.54:1 | 1.2:1 |
| `--tribunal-txt` sobre `--papel` | botón principal en texto, y sellos de firme | 7.58:1 | 7.71:1 | 4.5:1 |
| `--tribunal-txt` sobre `--papel-2` | botón principal sobre gris | 6.88:1 | 7.13:1 | 4.5:1 |
| `--papel` sobre `--tribunal-txt` | texto del botón principal | 7.58:1 | 7.71:1 | 4.5:1 |
| `--rio` sobre `--papel` | trazos de avance y borde del carril de interpretación | 3.68:1 | 6.72:1 | 3.0:1 |
| `--rio` sobre `--papel-2` | trazos de avance sobre gris | 3.34:1 | 6.21:1 | 3.0:1 |
| `--interp-filete` sobre `--interp` | el borde que marca el carril de interpretación | 4.02:1 | 4.19:1 | 3.0:1 |
| `--tribunal-txt` sobre `--interp` | el rótulo de clase dentro del carril | 6.89:1 | 6.86:1 | 4.5:1 |
| `--ambar` sobre `--ambar-suave` | aviso de atención | 4.60:1 | 10.16:1 | 4.5:1 |
| `--tinta` sobre `--ambar-suave` | texto del aviso de atención | 15.76:1 | 15.46:1 | 4.5:1 |

### Nada se dice sólo con color

Un estado que se distingue únicamente por el color no existe para quien no distingue ese
color, ni en una impresión en blanco y negro — **y esto se imprime**. Cada estado lleva
además una palabra:

```
[ ✓ AL DÍA ]      verde   + ícono y palabra
[ ⚠ 2 A REVISAR ] ámbar   + ícono, número y palabra
[ ⊗ CONFLICTO ]   punzó   + ícono y palabra
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

### La escala tipográfica

Siete pasos y **ninguno intermedio**. Están declarados como tokens (`--t-11` … `--t-34`)
y `pruebas/test_reticula.py` falla si aparece un `font-size` en px que no sea uno de
ellos.

| paso | dónde |
|---|---|
| **11** | rótulos en versalitas, foliatura, marginalia, cuños |
| **12** | encabezado de tabla, sellos, pies, la barra lateral |
| **13** | cuerpo de la aplicación, notas al pie de un bloque |
| **15** | prosa, valores de campo, campos de formulario |
| **18** | `h3`, el número de legajo, campos en el teléfono (≥16 evita el zoom de iOS) |
| **24** | `h2`, el título de una sección |
| **34** | la cifra grande de una baldosa del panel |

Esto se había perdido: el CSS llegó a tener **veintiún** tamaños distintos, catorce de
ellos medios puntos (9,5 · 10,5 · 11,5 · 12,5 · 13,5 · 14,5 · 15,5 · 16,5). Nada se ve
mal por separado; pero un rótulo de 12,5 al lado de uno de 13 y de uno de 11,5 no forma
un sistema, forma tres tamaños que el ojo registra como desalineados sin poder decir por
qué. **Es la diferencia entre una interfaz cuidada y una casi cuidada.**

La fuente de casi todas esas desviaciones eran los **98 atributos `style="…"`** escritos
a mano en `app.js`. Un estilo incrustado no se puede auditar, no se puede cambiar de una
vez, y no lo alcanza ninguna prueba de esta hoja: cada uno es una excepción silenciosa.
Quedan tres, y son las únicas que corresponden — `left` y `width` calculados a partir de
un dato, que es geometría que sale de la base y no puede vivir en el CSS.

### Dos planos: la mesa y el folio

**Decidido: hay superficies, hay radio y hay sombra.** Se deja escrito porque
`docs/01-identidad-visual.md` —que es histórico— pide lo contrario («cero tarjetas,
cero sombras, radio 0») y las dos estéticas son defendibles. Tener las dos a la vez es
lo que no lo es.

Gana ésta, y el motivo es medible. Con un solo plano —el mismo papel de fondo detrás
del texto y bloques separados por un filete de 1 px— una pantalla con dos cosas
cargadas no tiene ningún borde que diga dónde termina lo que el sistema tiene para
decir, y **se lee como un error**. Pasó de verdad: el índice de legajos recién
instalado y la cola sin nada se veían como pantallas rotas, y así lo reportó quien
las usa.

| | |
|---|---|
| `--fondo` | la mesa. En claro, un crema apagado; en oscuro, el fondo de siempre |
| `--folio` | la hoja apoyada encima. En claro sube a casi blanco; en oscuro **sube** de luminosidad |
| `--realce` | un azul apenas, para lo que la vista agarra sin leer: encabezado de tabla, fila bajo el puntero, baldosa de una cifra. Es fondo y nunca texto |

En el tema oscuro la relación se da vuelta a propósito: la altura la da la superficie
—que se aclara— y no la sombra, porque sobre un fondo casi negro una sombra negra no
se ve. Es el mismo criterio de Carbon y es el correcto.

**El radio es 5 px en un control y 14 px en un folio.** No son dos sistemas: es la
misma proporción. 14 px en una hoja de 950 px se ve igual de contenido que 5 px en un
botón de 90; un radio fijo para todo se ve enorme en lo chico o inexistente en lo
grande.

**Las sombras van en tres capas, no en una.** Una sola sombra difusa es una mancha
gris que el ojo lee como suciedad y no como altura; apiladas, cada una duplicando el
desenfoque y bajando la opacidad a la mitad, dan la caída progresiva de una sombra
real. Tres alcanzan: de ahí para arriba la diferencia no se ve y sólo cuesta pintado.
Y no son negras sino tiradas al marrón — una sombra negra sobre papel cálido ensucia;
teñida hacia el tono del fondo, oscurece.

Lo que **no** cambia y sigue valiendo del documento histórico: nada de esto puede
llevar información. Una sombra no dice que algo esté firme, un radio no dice que algo
esté en conflicto. Eso lo dicen el color, el ícono y la palabra, los tres juntos.

### El armazón

La pantalla se parte en dos y no cambia nunca: a la izquierda **dónde estás parado**
(la barra lateral, azul tribunal macizo), a la derecha **en qué estás trabajando**.
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
`.boton` al contorno en azul; `.boton.lleno` para la acción principal de una
pantalla —en una hoja con ocho botones al contorno, el que hay que apretar tiene que
distinguirse sin leerlos todos—; `.boton.gris` para lo secundario; `.boton.peligro` y
`.mini.peligro` en punzó, **sólo** para lo que destruye algo.

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
