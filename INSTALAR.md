# Instalación y operación

Escrito para que lo pueda seguir alguien que no participó del desarrollo. Si algo de
acá no se entiende, es un error del instructivo, no del lector.

---

## Idea general

El sistema se instala en **dos etapas**, y esto no es un capricho: la restricción 1 dice
que la máquina de la fiscalía no sale a internet.

1. **Etapa con internet**, en cualquier computadora: se descarga todo y se arma un
   paquete.
2. **Etapa sin internet**, en la máquina de la fiscalía: se copia el paquete y se
   levanta. A partir de ahí el sistema **nunca más** toca la red.

---

## Etapa 1 — En una máquina con internet

```bash
git clone <el repositorio>
cd AppUFIL

# 1. Las fuentes tipográficas de la interfaz (una sola vez; ya vienen versionadas).
./scripts/descargar-fuentes.sh

# 2. La imagen del contenedor, con Tesseract y el paquete de castellano adentro.
docker compose build

# 3. Exportarla a un archivo para que viaje en un disco externo.
docker save ufil-analisis:0.1 | gzip > ufil-analisis-0.1.tar.gz
```

Copiar al disco externo: `ufil-analisis-0.1.tar.gz` y el repositorio entero.

### Si no se puede usar Docker

```bash
pip download -r requisitos.txt -d ruedas/
```
y llevar también la carpeta `ruedas/`, más los paquetes `tesseract-ocr` y
`tesseract-ocr-spa` del sistema operativo que corresponda.

---

## Etapa 2 — En la máquina de la fiscalía, sin internet

```bash
gunzip -c ufil-analisis-0.1.tar.gz | docker load
cd AppUFIL
mkdir -p corpus datos
```

**Poner los PDF adentro de `corpus/`.** Se pueden copiar o, mejor, montar el directorio
donde ya están. El sistema los abre en solo lectura y no los modifica nunca.

```bash
docker compose up -d
```

Abrir **http://127.0.0.1:8713**

### Sin Docker

```bash
pip install --no-index --find-links ruedas/ -r requisitos.txt
python3 -m ufil.cli servir
```

---

## Procesar un lote

**Lo normal es hacerlo desde la interfaz**, sin tocar la terminal:

1. **Cargar escaneos** → poner el nombre del lote y quién carga.
2. Arrastrar los PDF (o elegirlos). Se ve archivo por archivo qué pasó con cada uno.
3. **Procesar**. Barra de progreso, etapa actual y cuánto falta. Se puede cerrar la
   pestaña: el trabajo sigue.
4. **Panel** para ver el estado, **Cola de revisión** para resolver lo dudoso.

Sólo se procesa lo que falta, así que subir un lote nuevo la semana que viene no
reprocesa lo de esta semana.

### Por línea de comandos, si hace falta

```bash
# Con Docker, adelante de cada comando: docker compose exec ufil
python3 -m ufil.cli ingerir /corpus --lote "contratos-2024" \
        --legajo "N° ..." --operador "apellido.nombre"
python3 -m ufil.cli leer          # OCR: alrededor de 1,7 s por página en CPU
python3 -m ufil.cli extraer
python3 -m ufil.cli identidad
```

### Todo junto

```bash
python3 -m ufil.cli piloto /corpus --lote "contratos-2024"
```

---

## Comprobaciones que conviene hacer

```bash
# Las restricciones del pliego siguen valiendo (incluye rehashear originales)
python3 -m ufil.cli verificar

# Las reglas duras siguen probadas
python3 -m unittest discover -s pruebas

# Calidad contra una transcripción manual
python3 -m ufil.cli evaluar banco-de-prueba/referencia.csv --detalle 20
```

`verificar` devuelve error si algo falla, así que se puede colgar de una tarea
programada y enterarse solo. Conviene correrlo seguido: cada corrida rehashea los 250
originales que hace más tiempo que no se revisan, y reporta cuántos del total llevan
verificación y desde cuándo.

---

## Exportar

```bash
python3 -m ufil.cli exportar datos/export
```

Deja `analisis.xlsx` (una hoja por consulta, más una portada con las advertencias) y
`informe.rtf` (interlineado 1,5, justificado, cuerpo 11, con cita de archivo en cada
afirmación).

---

## Adaptar el sistema a otro formulario

**No hay que tocar código.** Los formularios se describen en
`ufil/perfiles/*.json`: por cada campo, qué rótulo lo precede, dónde buscar el valor y
con qué parser interpretarlo. Se copia `contrato_legislatura.json`, se le cambian los
rótulos y se corre `extraer --perfil <nombre>`.

## Agregar una consulta

Tampoco hay que tocar código. Se copia un archivo de `ufil/consultas/`, se lo edita y
aparece solo en la interfaz, en la pestaña **Consultas**.

---

## Preguntas frecuentes

**¿Puede el sistema modificar los documentos originales?**
No, y hay tres barreras superpuestas. La ingesta abre en modo lectura; los PDF que se
suben por la interfaz se guardan en modo `0444` y el contenedor corre como usuario sin
privilegios, así que un intento de sobrescribir falla; y el corpus montado se monta
`:ro`, que lo hace cumplir el kernel.

Con una salvedad que conviene saber: **el modo `0444` no frena a root.** Si alguien
entra con permisos de administrador puede sobrescribir cualquier cosa. Por eso el
sistema no se apoya sólo en los permisos: `ufil verificar` rehashea los originales y
avisa si alguno cambió, **empezando siempre por los que hace más tiempo que no se
miran**, así con el uso normal el acervo entero queda cubierto. `ufil verificar
--completo` los rehashea todos de una.

**¿Sale a internet?**
No. No hay ninguna llamada de red en el código, las fuentes tipográficas se sirven
desde el disco y el servidor escucha sólo en 127.0.0.1. Si algún día se conecta un
modelo de visión, tiene que ser en la misma máquina: `ufil verificar` falla si
`UFIL_VLM_URL` apunta afuera.

**¿Puede inventar un dato?**
En el carril de datos, no: no interviene ningún modelo generativo. La extracción es
determinística sobre las palabras leídas y sus coordenadas. Lo que no se puede leer se
guarda como nulo con motivo, y la base tiene una restricción que lo hace cumplir.

**¿Y si me equivoco revisando?**
Cada decisión queda registrada con quién y cuándo, y se puede volver a cambiar. Además
el literal leído nunca se pisa: la normalización vive en una tabla aparte.

**Si reproceso el lote, ¿pierdo la revisión que ya hice?**
No. Las correcciones de campo y las fusiones de identidad confirmadas se guardan en
`revision_humana` y `fusion_decidida`, indexadas por el hash del archivo, y se vuelven
a aplicar solas después de reprocesar.

**¿Dónde están los archivos derivados?**
En `datos/derivados/<primeros 2 del hash>/<hash completo>/`. Cada derivado está
indexado por el hash del original del que salió. El corpus queda intacto.
