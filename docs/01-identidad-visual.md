# Identidad visual — "Retícula de expediente"

> **DOCUMENTO HISTÓRICO. No es la especificación vigente.**
>
> Es el estado del sistema visual de una etapa anterior del proyecto y quedó escrito
> en presente y en tono de pliego, que es lo que lo vuelve peligroso: cualquiera —o
> cualquier agente— que lo lea va a concluir que el código se desvió de la
> especificación y va a «arreglarlo» hacia atrás.
>
> **La especificación vigente es [`DESIGN_SYSTEM.md`](../DESIGN_SYSTEM.md).**
>
> Lo que este documento dice y el código ya NO hace:
>
> | Acá dice | El código hace | Por qué |
> |---|---|---|
> | `--sello:#23477A`, punzó `#96301F`, tinta `#1B1D21` | `#24466E`, `#A81F26`, `#0F172A` | ajuste de contraste medido, DESIGN_SYSTEM.md §3 |
> | «radio 0» | `--radio:5px` | ver §4, decidido y escrito |
> | «cero sombras» | sombras en tres capas | los folios se apoyan sobre la mesa; ver §4 |
> | «cero tarjetas» | cada bloque es un folio | una pantalla sin superficies se lee como una pantalla rota |
> | «no hay animación de entrada» | 24 transiciones, todas de 140 ms | se apagan enteras con `prefers-reduced-motion` |
>
> Lo que SIGUE siendo verdad y se mudó a `DESIGN_SYSTEM.md`: la tabla de las tres
> voces tipográficas, la retícula con la canaleta de foliatura, los estados que nunca
> se dicen sólo con color, y la ficha de anclaje.

Escrito en una etapa anterior. La demostración de aquel momento está en
`docs/identidad/guia-visual.html`.

---

## La idea, en una línea

**La tipografía te dice de dónde viene lo que estás leyendo.** No es una decoración:
es la regla de la sección 5 del pliego —dato contra interpretación— resuelta en el
único lugar donde un fiscal la va a leer sin que se la expliquen, que es la forma de
las letras.

| Voz | Familia | Qué significa cuando la ves |
|---|---|---|
| **Mono** | IBM Plex Mono | Esto se leyó de un documento. Tiene anclaje. No se estimó. |
| **Serif** | Source Serif 4 | Esto es texto: o la transcripción del documento, o una interpretación del sistema (en bastardilla). |
| **Sans** | Archivo | Esto es la aplicación hablando: rótulos, botones, encabezados de tabla. |

Una cifra en mono es un dato. La misma cifra en bastardilla serif es una conjetura. No
hace falta leer el rótulo.

Archivo, además, es una grotesca diseñada por Omnibus-Type, fundición argentina.
Eligiéndola la herramienta suena local sin tener que ponerle una escarapela.

---

## Referencias, traducidas a decisiones

Del expediente se toma la **estructura**, no la textura. Nada de papel manchado ni
sellos rotados: eso es disfraz.

| Del expediente | En la interfaz |
|---|---|
| Margen izquierdo ancho, el que se cose | Canaleta funcional fija a la izquierda de cada bloque: foliatura, estado, confianza. No es decoración: es la marginalia que se consulta de reojo. |
| Foliatura | Todo registro lleva su `f. 0142` en mono, chico, en la canaleta. Es la dirección física del dato. |
| Sello | Rectángulo de doble filete, versalitas, interletrado abierto. Sin rotación, sin textura. Marca estado de lote y de verificación. |
| Cuerpo y marginalia | Cuerpo justificado de ~68 caracteres para transcripciones; la nota al costado, nunca intercalada. |
| Filetes del formulario | Reglas de 1 píxel separan registros. **Cero tarjetas, cero sombras, radio 0.** |

Prohibiciones del pliego, cumplidas: no hay violeta ni degradados, no hay tarjetas
redondeadas flotando, no hay íconos decorativos, no hay animación de entrada.

---

## Paleta

Neutros cálidos —papel, no gris de dashboard— con un solo acento y tres colores
semánticos que **no** son el acento.

| Rol | Token | Claro | Oscuro |
|---|---|---|---|
| Tinta | `--tinta` | `#1B1D21` | `#E6E3DC` |
| Tinta secundaria | `--tinta-2` | `#5A5D64` | `#9B9A95` |
| Papel | `--papel` | `#FCFBF9` | `#16181B` |
| Papel hundido | `--papel-2` | `#F1EFEA` | `#1E2126` |
| Filete | `--filete` | `#CFCBC2` | `#33373D` |
| **Acento — azul tampón** | `--sello` | `#23477A` | `#7EA3D6` |
| Fondo de interpretación | `--interp` | `#E9EDF3` | `#1B2028` |

Semánticos, deliberadamente separados del acento:

| Estado | Token | Claro | Oscuro |
|---|---|---|---|
| Verificado por humano | `--verde` | `#2C5946` | `#79B79B` |
| Confianza baja | `--ambar` | `#8A6714` | `#D0A63F` |
| **Conflicto entre rutas** | `--lapiz` | `#96301F` | `#E08472` |

El rojo óxido es el lápiz del corrector sobre el expediente. Es el único color que
grita, y grita una sola cosa: *las dos lecturas no coinciden, no confíes todavía*.

---

## Los tres estados que la interfaz tiene que comunicar sin texto

### 1. Confianza
Barra de cinco segmentos en la canaleta, más el número en mono. Por debajo de 0,85 la
celda se cubre con una trama diagonal fina. La trama se ve de lejos; el número está
para cuando te acercás.

### 2. Nulo con motivo
Una celda vacía es ambigua: no se sabe si el sistema no leyó o si el documento no
decía. Entonces el nulo **se escribe**: `∅ ILEGIBLE`, `∅ AUSENTE`, `∅ AMBIGUO`, en
versalitas sobre papel hundido. La ausencia también es un dato.

### 3. Conflicto entre rutas
Filete izquierdo de 3 px en rojo óxido, las dos lecturas mostradas una arriba de la
otra con su ruta rotulada, y ningún valor elegido. **La interfaz nunca resuelve un
conflicto sola**; lo muestra y espera.

---

## El anclaje

Todo dato numérico o de fecha lleva su ficha de anclaje pegada:

```
27-XX XXX XXX-4   [ A-0142 · f. 7 · ▣ ]
```

La ficha es un botón. Un clic y aparece el folio con el recuadro resaltado. Ese clic
es el que convierte media hora de buscar el papel en dos segundos, y es la razón de
ser de la restricción 4 del pliego.

---

## Retícula

- Canaleta de marginalia: **112 px** fijos.
- Cuerpo de lectura: **68 caracteres** máximo.
- Escala tipográfica: 11 / 12 / 13 / 15 / 18 / 24 / 34 px. Sin pasos intermedios.
- Espaciado en múltiplos de **4 px**, con `gap` de flex o grid, nunca márgenes sueltos.
- Cifras siempre con `font-variant-numeric: tabular-nums`, para que las columnas de
  montos se lean como columna y no como lista.
- Radio de borde: **0**. Excepción única: 2 px en las fichas de anclaje, para que se
  lean como botón.

---

## Fuentes

Las tres son de licencia libre (OFL) y **se sirven desde el disco**, nunca por CDN
(restricción 1). Se bajan una sola vez en la etapa de instalación:

```
./scripts/descargar-fuentes.sh
```

Quedan en `assets/fuentes/` y versionadas en el repositorio. La hoja de estilos declara
además una pila de reserva, así que si las fuentes faltan la interfaz se degrada fea
pero legible, nunca rota.
