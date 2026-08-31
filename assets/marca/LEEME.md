# Marca institucional

Acá va el **archivo oficial** del escudo del Ministerio Público Fiscal de Entre Ríos.
No hay ninguno puesto a propósito: un emblema oficial redibujado de memoria queda mal y
no corresponde usarlo así.

## Cómo ponerlo

Copiar el archivo con uno de estos nombres exactos:

```
assets/marca/logo.svg     ← preferido: escala sin perder nitidez
assets/marca/logo.png     ← alternativa, idealmente 400 px de alto o más
```

La interfaz lo detecta sola y lo muestra en la barra lateral, debajo del monograma. Si
no hay archivo, manda el monograma —una foja con su lomo y un filete dorado, dibujado en
SVG— y todo funciona igual.

## Por qué no sirve una captura de pantalla

Se probó con una: el archivo que circula por WhatsApp es un PNG con **fondo blanco**, no
transparente. Sobre el papel cálido de la interfaz se le ve el recuadro, y sobre el fondo
oscuro aparece un rectángulo blanco en el medio de la barra. Y aunque el fondo fuera
transparente, las palabras «Ministerio Público» y «de la Provincia de Entre Ríos» están
en negro: sobre el fondo oscuro desaparecen.

Un solo mapa de bits no puede servir para los dos temas. Con el archivo vectorial sí, y
si además hay una versión para fondo oscuro, se pone como `logo-oscuro.svg`.

## De dónde sacarlo

Del área de comunicación del organismo, o del sitio institucional. Conviene pedir la
versión vectorial (`.svg` o `.eps`): la que circula en internet suele ser una captura
chica y se ve borrosa al ampliarla.

## Por qué no viaja en el repositorio

Es material institucional del organismo, no del proyecto. Se agrega en la instalación,
igual que las tipografías.
