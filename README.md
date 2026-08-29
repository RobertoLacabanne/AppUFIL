# Sistema de análisis documental offline — UFIL Paraná

Unidad Fiscal de Investigación y Litigación de Paraná · Ministerio Público Fiscal de
Entre Ríos.

Herramienta interna de trabajo. Sirve para que el equipo entienda rápido un volumen de
información que hoy no puede abarcar y decida mejor dónde mirar. **No es un sistema de
gestión del legajo y no produce piezas procesales.** Lo que se incorpora formalmente al
legajo se hace después, a mano, sobre la documentación original.

## Estado

**Fase 0.** Todavía no hay pipeline. Lo que hay es la decisión de arquitectura, las
preguntas que faltan responder y el sistema visual.

| | |
|---|---|
| [`docs/00-fase-0.md`](docs/00-fase-0.md) | Preguntas abiertas, decisión construir/adoptar, stack propuesto y umbrales de calidad. **Empezá por acá.** |
| [`docs/01-identidad-visual.md`](docs/01-identidad-visual.md) | Especificación del sistema visual. |
| [`docs/identidad/guia-visual.html`](docs/identidad/guia-visual.html) | La guía corriendo, con maquetas de las pantallas. Se abre con doble clic, no necesita servidor. |
| [`scripts/descargar-fuentes.sh`](scripts/descargar-fuentes.sh) | Descarga las fuentes. Se corre una sola vez, en instalación, con conexión. |
| `banco-de-prueba/` | Vacío por ahora. Va la muestra de páginas difíciles con la transcripción manual de referencia. |

## Las cuatro restricciones que gobiernan todo

1. **Offline total.** Ninguna llamada de red en tiempo de ejecución. Nada por CDN,
   fuentes tipográficas incluidas. Todo se descarga en la instalación y queda en disco.
2. **El original es inmutable.** Solo lectura sobre el material fuente. Nunca se
   reescribe, renombra, mueve ni recomprime. Los derivados van aparte, con el SHA-256
   del original del que salieron.
3. **Nada se inventa en un campo de datos.** Si un valor no está legible o no está en
   el documento, se guarda nulo con motivo (`ilegible`, `ausente`, `ambiguo`).
4. **Todo dato numérico o de fecha está anclado a su origen:** archivo, página y
   coordenadas del recuadro.

## La regla de los dos carriles

El sistema interpreta, resume e hipotetiza —es la mitad de su valor—, pero eso viaja
por un carril distinto del dato duro y se distingue de una ojeada.

- **Carril de datos:** lo que se leyó de un documento. Con anclaje y confianza. Nunca se
  completa, nunca se estima, nunca se redondea. En la interfaz: monoespaciada.
- **Carril de interpretación:** resúmenes, hipótesis, patrones, relevancia sugerida.
  Puede equivocarse; se presenta como lo que es y cada afirmación linkea a los
  documentos que la sostienen. En la interfaz: serif en bastardilla, sobre otro fondo.

## Decisión de la sección 9, en corto

Para el **Caso B (secuestros masivos): adoptar Datashare (ICIJ)**, no construir. Aleph
queda descartado: el mantenimiento del Aleph clásico venció el 31/12/2025 y su
sucesor, Aleph Pro, es un producto alojado con despliegue propio bajo licencia paga.

Para el **Caso A (contratos): construir**, que es donde está el problema que ninguna
plataforma resuelve.

**La capa de ingesta es propia y común a los dos.** El fundamento completo, con las
limitaciones y el umbral donde esta decisión se da vuelta, está en
[`docs/00-fase-0.md`](docs/00-fase-0.md).
