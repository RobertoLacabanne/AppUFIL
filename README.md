# Sistema de análisis documental offline — UFIL Paraná

Unidad Fiscal de Investigación y Litigación de Paraná · Ministerio Público Fiscal de
Entre Ríos.

Herramienta interna de trabajo. Sirve para que el equipo entienda rápido un volumen de
información que hoy no puede abarcar y decida mejor dónde mirar. **No es un sistema de
gestión del legajo y no produce piezas procesales.** Lo que se incorpora formalmente al
legajo se hace después, a mano, sobre la documentación original.

---

## Estado

**Corre de punta a punta, y se opera desde la interfaz.** Se arrastran los PDF
escaneados a la pantalla de carga, se procesa en segundo plano con barra de progreso, y
a partir de ahí se trabaja: buscar en todo el corpus, ficha por contratado con
cronología, cola de revisión por teclado, cruces y exportación a `.xlsx` y `.rtf`.

Medido sobre 50 contratos sintéticos: **86 % de campos críticos resueltos sin
intervención y cero errores silenciosos**, pero **por debajo de los umbrales de
exactitud** propuestos en la Fase 0. El detalle honesto, con lo que falta, está en
[`docs/02-fase-1.md`](docs/02-fase-1.md).

---

## Arrancar

```bash
./scripts/descargar-fuentes.sh    # una vez, con internet
python3 -m ufil.cli servir        # http://127.0.0.1:8713
```

**Para mostrarlo**, un solo comando deja todo cargado, marca la base como demostración
—aparece un aviso en toda pantalla de que los contratos no son reales— y levanta el
servidor:

```bash
python3 -m ufil.cli demo --limpiar
python3 herramientas/humo.py      # chequea que ninguna pantalla esté rota
```

El guión para la reunión está en [`docs/04-guion-demostracion.md`](docs/04-guion-demostracion.md).

Y desde ahí: **Cargar escaneos** → arrastrar los PDF → **Procesar**. Nada más.

Para probarlo sin documentos reales, hay un generador de corpus sintético con verdad
conocida:

```bash
python3 herramientas/generar_fixtures.py --cantidad 50
python3 -m ufil.cli piloto datos/corpus-sintetico --lote piloto-01 \
        --referencia datos/corpus-sintetico/referencia.csv
```

Instalación en la máquina de la fiscalía, paso por paso: [`INSTALAR.md`](INSTALAR.md).

---

## Las cuatro restricciones que gobiernan todo

1. **Offline total.** Ninguna llamada de red en tiempo de ejecución. Nada por CDN,
   fuentes tipográficas incluidas. Sin Node ni paso de compilación en la máquina de
   destino. El servidor escucha sólo en `127.0.0.1`.
2. **El original es inmutable.** Solo lectura sobre el material fuente. Los derivados
   van aparte, con el SHA-256 del original del que salieron. En Docker el corpus se
   monta `:ro`, así que lo hace cumplir el kernel y no la buena voluntad del código.
3. **Nada se inventa en un campo de datos.** Si un valor no está legible o no está en
   el documento, se guarda nulo con motivo (`ilegible`, `ausente`, `ambiguo`). Lo hace
   cumplir un `CHECK` de la base: o hay valor, o hay motivo. Nunca los dos, nunca ninguno.
4. **Todo dato numérico o de fecha está anclado a su origen:** archivo, página y
   coordenadas del recuadro. **Un valor sin coordenadas no entra en la base**, por otro
   `CHECK`.

`python3 -m ufil.cli verificar` comprueba las cuatro después de cada corrida, y devuelve
error si alguna falla.

## Cómo conviene cargar los escaneos

**Un PDF por contrato.** Medido: separar o juntar no cambia ni la velocidad ni la
exactitud, pero cuando se rescanea parte de una pila, con archivos sueltos el sistema
reconoce por huella digital los que ya tenía (12 contratos, 0 repetidos) y con todo en un
PDF grande alcanza una hoja de diferencia para que entre de nuevo (15 contratos, 3
repetidos inflando los acumulados).

Si igual conviene escanear de corrido, hacelo: **el sistema separa los contratos que
vengan juntos** —detecta dónde arranca cada formulario y arma un registro por tramo de
fojas— y **marca los repetidos** para que los resuelva una persona. El detalle está en
[`docs/05-como-conviene-cargar.md`](docs/05-como-conviene-cargar.md).

## La regla de los dos carriles

- **Carril de datos** (tabla `campo`): lo que se leyó de un documento, con anclaje y
  confianza. Sin ningún modelo generativo de por medio. En la interfaz: **monoespaciada**.
- **Carril de interpretación** (tabla `interpretacion`): resúmenes, patrones, anomalías.
  Puede equivocarse. **No se puede guardar sin al menos una fuente documental**, y la
  aplicación lo rechaza. En la interfaz: **serif en bastardilla, sobre otro fondo**.

La separación es estructural, no una convención de nombres: no hay forma de mezclarlos
por accidente.

---

## Las capas

| | | |
|---|---|---|
| 0 | `capa0_ingesta.py` | Recorrido en solo lectura, SHA-256, duplicados exactos, procedencia |
| 1 | `capa1_texto.py` · `capa1_vlm.py` | Texto con coordenadas. Endereza las fojas que llegaron giradas, ruta nativa, dos rutas de OCR, y el contrato del modelo de visión (**sin implementar**, a propósito) |
| 2 | `capa2_extraccion.py` · `capa2_campos.py` | Separa los contratos que vengan juntos en un mismo PDF, elige el perfil de formulario que mejor calce, y extrae cada uno con anclaje y cotejo entre rutas |
| 3 | `capa3_identidad.py` | Clave fuerte automática; fusiones por similitud **sólo propuestas** |
| 4 | `consultas/*.sql` · `capa4_analisis.py` | Cruces determinísticos, cada uno un archivo versionado |
| 5 | `capa5_interpretacion.py` | El otro carril. Hoy, reglas; mañana, un LLM local |
| 6 | `servidor.py` · `web/` · `almacen.py` · `trabajo.py` · `busqueda.py` | Carga de escaneos, procesamiento en segundo plano, búsqueda e interfaz local — sin dependencias ni build |
| 7 | `capa7_export.py` | `.xlsx` y `.rtf` con cita de archivo y foja |

---

## Documentos

| | |
|---|---|
| [`docs/00-fase-0.md`](docs/00-fase-0.md) | Preguntas abiertas, decisión construir/adoptar, stack y umbrales de calidad |
| [`docs/01-identidad-visual.md`](docs/01-identidad-visual.md) | El sistema visual: por qué la tipografía es la etiqueta de procedencia |
| [`docs/02-fase-1.md`](docs/02-fase-1.md) | **Qué se construyó, qué mide y qué falta.** Con los números. |
| [`docs/03-carga-y-trabajo.md`](docs/03-carga-y-trabajo.md) | Carga desde la interfaz, búsqueda, ficha del contratado, y un experimento de lectura que salió mal. |
| [`docs/04-guion-demostracion.md`](docs/04-guion-demostracion.md) | Cómo mostrarlo en una reunión, con las preguntas que van a hacer y qué contestar. |
| [`docs/05-como-conviene-cargar.md`](docs/05-como-conviene-cargar.md) | **¿Un PDF por contrato o todo junto?** La respuesta, medida. |
| [`docs/06-lo-que-el-papel-trae.md`](docs/06-lo-que-el-papel-trae.md) | Hojas al revés, carátulas, formularios distintos: qué se rompía y cómo quedó. |
| [`docs/identidad/guia-visual.html`](docs/identidad/guia-visual.html) | La guía visual, se abre con doble clic |
| [`INSTALAR.md`](INSTALAR.md) | Instalación en dos etapas y operación diaria |

---

## Lo que decide qué sigue

Falta **una sola respuesta** para destrabar la Fase 2: **qué máquina hay** (CPU, RAM,
placa de video con VRAM, disco). El Caso A ya corre entero en CPU; la GPU decide si
entran el modelo de visión y la capa interpretativa en lenguaje natural.

Y falta lo más valioso: **20 contratos reales de muestra** que cubran la variedad —la
cámara buena y la mala, el año viejo y el nuevo, el escaneo torcido, el que tiene la
firma encima del monto—. Sin eso, los números de calidad son sobre papel sintético.

## Decisión de la sección 9, en corto

Caso B (secuestros masivos): **adoptar Datashare (ICIJ, AGPL-3.0)**, no construir.
Aleph queda descartado — el mantenimiento del Aleph clásico venció el 31/12/2025 y su
sucesor, Aleph Pro, es un producto alojado con despliegue propio bajo licencia paga.
Caso A (contratos): **construir**, que es lo que está en este repositorio.
Fundamento completo en [`docs/00-fase-0.md`](docs/00-fase-0.md).
