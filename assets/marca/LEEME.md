# Marca institucional

Los archivos del **Ministerio Público Fiscal de la Provincia de Entre Ríos** que usa la
aplicación. Vinieron del paquete `MPF-logo-app` que preparó la unidad.

## Qué usa cada cosa

| archivo | dónde sale |
|---|---|
| `logo.svg` | el **isotipo** —la bandera con la banda federal y los anillos del río—, arriba de la barra lateral y en el encabezado de las hojas impresas. Es el que sirve `/marca`. |
| `logo.png` | el mismo isotipo rasterizado, para la portada del `.xlsx` que se exporta (una planilla no puede llevar un `.svg` adentro). |
| `logotipo.svg` | el **logotipo completo**, con el nombre del organismo al lado. Para fondo claro. Hoy no lo usa ninguna pantalla; está guardado para cuando haga falta un papel con la marca entera. |
| `logotipo-oscuro.svg` | el mismo, con el texto en blanco, para fondo oscuro. |
| `icono.svg`, `icono-32.png`, `icono-512.png` | el ícono cuadrado: la pestaña del navegador (`/marca?que=icono`). |
| `icono-tactil.png` | el acceso directo cuando alguien se guarda la aplicación en la pantalla de un teléfono (`/marca?que=tactil`). |

## Las dos reglas que no se negocian

**1. En la barra va el isotipo, nunca el logotipo con el texto.** El nombre del
organismo, en el logotipo, está en marino: sobre la barra marina desaparece.
Recolorearlo a blanco sería intervenir la marca, y eso no se le hace a un logotipo
institucional. El isotipo solo, con el nombre al lado compuesto en la tipografía de la
aplicación, es la solución correcta y la que cualquier manual permite.

**2. Los colores del isotipo no son la paleta de la aplicación.** El celeste, el verde
y el rojo viven adentro del archivo y no entran a `estilo.css`. Acá el color significa
estado —el verde quiere decir «dato firme», el punzó quiere decir «las dos lecturas no
coinciden»— y un segundo verde en la misma pantalla obliga al operador a aprender cuál
es cuál. Lo único que se alinea con la marca es el marino del cromo, porque no lleva
estado. Lo sostiene `pruebas/test_entre_rios.py`, que lee los colores **de este
archivo** y verifica que ninguno aparezca en la hoja de estilos.

## Si no están los archivos

No pasa nada. La barra manda el monograma —una foja con su lomo y un filete dorado,
dibujada en SVG adentro del HTML—, la pestaña se queda con el mismo monograma embebido,
y todo lo demás funciona igual. Se elige solo: si `/marca` responde, entra el isotipo.

## Por qué ahora sí viaja en el repositorio

Antes estaba en `.gitignore`, con el argumento de que es material del organismo y no
del proyecto. El argumento era razonable y el resultado era malo: la aplicación se
despliega empujando este repositorio, así que lo que no está acá no existe en el
servidor donde la usa el equipo. Las tipografías viajan por la misma razón. Este
repositorio es de la unidad.

## Qué falta pedir

El paquete que hay acá es un **rediseño** del identificador, no el archivo del manual
institucional. Sirve y se ve bien, pero antes de que algo con esta marca salga de la
unidad —un escrito, una presentación— conviene que comunicación del organismo valide la
adaptación, o que manden el vectorial oficial para reemplazar estos archivos. El
reemplazo es copiar encima con los mismos nombres: nada del código los tiene escritos
adentro.
