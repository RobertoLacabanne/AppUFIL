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
cronología, cola de revisión con el folio al lado, cruces y exportación a `.xlsx` y
`.rtf`. **Anda igual en un celular**, en la red de la fiscalía y con clave de acceso.

Medido sobre 50 contratos sintéticos: **86 % de campos críticos resueltos sin
intervención y cero errores silenciosos**, pero **por debajo de los umbrales de
exactitud** propuestos en la Fase 0. El detalle honesto, con lo que falta, está en
[`docs/02-fase-1.md`](docs/02-fase-1.md).

Para operarlo todos los días, cuatro pantallas que no son de análisis y hacen falta
igual:

| | |
|---|---|
| **Quedaron afuera** | Cada PDF que entró y no produjo ningún contrato, agrupado por motivo y con qué hacer. Un documento que se pierde en silencio es lo peor que puede hacer un sistema que existe para no perder documentos. |
| **Estado del sistema** | Si esta máquina tiene todo lo que hace falta, si las reglas del pliego se siguen cumpliendo, y si los originales cambiaron. |
| **Respaldo** | Un botón. Lo único que no se regenera es el trabajo de las personas: cada campo revisado, cada identidad confirmada, con quién y cuándo. |
| **Cargar escaneos** | Con el consejo medido de cómo conviene pedir el escaneo, que es la decisión que más pesa en el resultado. |

---

## Arrancar

**Para instalarlo en una máquina nueva**, sin saber nada del proyecto:
[`EMPEZAR.md`](EMPEZAR.md). Son tres pasos y el instalador chequea todo solo.

```bash
./scripts/instalar.sh             # una sola vez
./scripts/arrancar.sh             # todos los días
```

Por dentro, o para adaptarlo:

```bash
./scripts/descargar-fuentes.sh    # una vez, con internet
python3 -m ufil.cli diagnostico   # ¿está todo lo que hace falta en esta máquina?
python3 -m ufil.cli servir        # http://127.0.0.1:8713
```

`diagnostico` es lo primero que conviene correr en una máquina nueva: chequea Tesseract,
el idioma castellano, el detector de orientación, la búsqueda de texto, permisos, disco
y aislamiento de red, y si algo falta dice qué instalar. Lo mismo está en la interfaz,
en **Estado del sistema**, para quien no abre la terminal.

**Desde un celular**, en la misma red:

```bash
python3 -m ufil.cli servir --red   # muestra la dirección y una clave de acceso
```

Cómo funciona y qué protege, en
[`docs/07-desde-el-celular.md`](docs/07-desde-el-celular.md).

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

## Cuánto tarda

El OCR reparte casi perfecto entre núcleos, así que se leen varias páginas a la vez.
Medido en una máquina de cuatro núcleos: **0,63 s por página** (contra 1,43 s
secuencial). Para 5.000 contratos de una o dos fojas, alrededor de **hora y media**.
Se ajusta con `UFIL_NUCLEOS` si hace falta dejarle CPU a otra cosa.

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
| 6 | `servidor.py` · `web/` · `almacen.py` · `trabajo.py` · `busqueda.py` | Carga de escaneos, procesamiento en paralelo con progreso, búsqueda, cola de revisión con el folio al lado, e interfaz local — sin dependencias ni build |
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
| [`docs/07-desde-el-celular.md`](docs/07-desde-el-celular.md) | Entrar desde un teléfono: cómo se hace, qué protege la clave y qué no. |
| [`docs/08-hasta-donde-aguanta-el-escaneo.md`](docs/08-hasta-donde-aguanta-el-escaneo.md) | **¿A cuántos DPI hay que escanear?** El punto de quiebre, medido. |
| [`docs/identidad/guia-visual.html`](docs/identidad/guia-visual.html) | La guía visual, se abre con doble clic |
| [`EMPEZAR.md`](EMPEZAR.md) | **Cómo hacerlo andar en una máquina nueva.** Tres pasos, para alguien que no participó del desarrollo. |
| [`INSTALAR.md`](INSTALAR.md) | Instalación en dos etapas (sin internet), operación diaria y respaldo |
| [`docs/09-lo-escrito-a-mano.md`](docs/09-lo-escrito-a-mano.md) | Por qué el OCR no lee la manuscrita, con el número, y qué hace el sistema en cambio. |

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
