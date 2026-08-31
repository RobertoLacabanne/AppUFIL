# Informe de entrega

Qué se hizo, qué se encontró, qué falta decidir. Escrito para que se pueda auditar sin
leer el código.

---

## 1. Lo que se encontró, en orden de gravedad

Los defectos de abajo estaban **en producción**. Ninguno se veía como una falla: el
sistema andaba, mostraba números y nadie tenía motivo para desconfiar. Esa es
exactamente la razón por la que importan.

### 1.1 El total sumaba plata que el sistema no sostenía

El panel mostraba **$5.847.000** y decía que sumaba «sólo los montos leídos con
seguridad». Adentro había **$761.900** de montos que en ese mismo momento estaban en la
cola esperando que alguien los mirara.

Y en la tabla de personas figuraba **`e DUARTE) Sidvia Nit PA AA A a a`** como una
persona consolidada del legajo, con confianza 0,31.

**Cómo quedó:** ocho estados de confianza explícitos (`ufil/confianza.py`), y la
separación **hecha cumplir en la base**, no en la pantalla: la vista `v_contrato` sólo
deja pasar campos firmes, con doble barrera (el estado *y* que no haya conflicto
abierto). Una regla que sólo vive en la interfaz se saltea sola la próxima vez que
alguien escriba un `SELECT`.

El total pasó a **$5.085.100 firme + $761.900 provisional**, dicho por separado.

### 1.2 Una factura se contaba como contrato

Con un contrato de $10.000 y su factura de $2.500, el panel decía **«total firme
$12.500 · 2 contratos»**. Ninguna de las dos cosas era cierta. Cuando la factura es el
cobro de ese mismo contrato —el caso normal— sumarlas cuenta **la misma plata dos
veces**.

**Cómo quedó:** tres familias de documento (lo pactado, lo cobrado, los actos
administrativos) y una cuarta que es *no saber*. Un tipo desconocido no se acomoda en la
más probable: no entra a ningún total y **se cuenta aparte para que se vea**. Ver
[`docs/11-contrato-o-factura.md`](docs/11-contrato-o-factura.md).

### 1.3 La imagen de Docker viajaba con la puerta abierta

El `Dockerfile` traía `UFIL_ACCESO=abierto` horneado. Esa variable significa «quién
llega a este puerto ya está restringido afuera de este proceso», y es cierto en
`docker-compose.yml`, que publica en `127.0.0.1`. **En un servicio de nube es falso**:
ahí el puerto sale a internet.

Cualquier despliegue de esa imagen —Render, Fly, una VM, un `docker run -p 0.0.0.0:...`—
dejaba el legajo **abierto para cualquiera que supiera la dirección, sin ninguna
puerta**.

**Cómo quedó:** la variable salió de la imagen y está en `docker-compose.yml`, tres
líneas debajo de la publicación que la justifica. Por omisión la imagen pide clave.
`render.yaml` fija `UFIL_ACCESO=clave` explícito. Hay pruebas que fallan si vuelve.

### 1.4 La planilla que se firma decía «0 campos pendientes de revisión». Siempre.

La portada del `.xlsx` filtraba por `estado='a_revisar'`, un estado que dejó de existir
cuando entraron los ocho de confianza. La consulta seguía corriendo **sin error** y
devolvía cero. Una afirmación falsa en un documento que se incorpora a un legajo.

### 1.5 El informe .rtf escribía mal los apellidos

Para dar vuelta el separador decimal, el código hacía
`f"...${n:,.2f}".replace(",", "@").replace(".", ",")...` — **sobre la frase entera**, no
sobre el número. El informe salía diciendo:

> PEREZ ROMERO**.** Ana Laura (documento 28**,**456**,**712)

Apellidos y números de documento corrompidos en el documento que se firma.

### 1.6 `resolver` se caía entero y dejaba el legajo sin identidades

Un documento cuyo valor normalizado no tenía la forma `DNI:1234` cortaba la pasada de
identidad con un `ValueError`. No costaba ese documento: costaba **todos los que venían
después**. El legajo quedaba sin personas, sin cruces y sin superposiciones, mientras la
pantalla mostraba los contratos como si estuviera todo bien.

### 1.7 Otros, encontrados mirando la pantalla

* Una persona con **dos contratos** aparecía dos veces en el cruce, y **cada fila traía
  todas sus facturas**: sumar la columna daba el doble de lo facturado.
* El cruce comparaba el **monto mensual** del contrato contra la **facturación
  acumulada**. Son magnitudes distintas; ponerlas juntas invita a concluir que se
  facturó de más cuando no se sabe.
* La cobertura contaba los campos de contratos, facturas y decretos juntos: decía
  **«Contratado 10»** en un legajo con 3 contratos.
* En la ficha de la persona, el clic de fila se enganchaba a «la última tabla»; al
  agregar la de comprobantes debajo, cada factura abría **el contrato del mismo índice**.
* Los offsets de las barras pegadas arriba eran seis números escritos a mano y **estaban
  mal**: el encabezado mide 71 px y el CSS decía 59.
* «AL DÍA» sobre una base vacía; «lote —»; «1 archivo(s)»; «1 pares de contratos se
  pisan»; fechas en ISO; cámaras como «A» y «B».
* El borde de los campos de formulario daba **1,57:1** de contraste, por debajo del
  mínimo de WCAG AA.
* `--marca` y `--marca-solape` —las barras de la cronología— vivían en un `:root` suelto
  y **ninguna prueba de contraste las miraba**.

---

## 2. Decisiones que conviene discutir

### 2.1 Una base de datos por legajo, no una columna `legajo_id`

Lo habitual sería una columna y un `WHERE legajo_id = ?` en cada consulta. **No se hizo
así.** Ese diseño depende de que nadie se olvide el filtro nunca —ni hoy, ni en la
consulta que alguien agregue el año que viene— y una consulta sin filtro **no falla**:
devuelve de más, en silencio, y el número queda mal en un informe que ya se firmó.

Con una base por legajo, cruzarlos no es difícil: es **imposible**. La garantía la da el
sistema de archivos.

**Lo que se pierde, y hay que decirlo:** no se pueden cruzar dos legajos entre sí. Es a
propósito. Si algún día hace falta, se hace con una exportación explícita de los dos.

### 2.2 El sistema no completa lo que el papel no dice

Tres lugares donde sería fácil «mejorar» el número y **no se hace**:

* El total contratado sale de `monto_total`, que el contrato dice aparte. Si no se pudo
  leer, la celda queda vacía. **No se multiplica mensual × plazo** para llenarla: eso
  sería calcular un número que el papel dice o no dice.
* Las facturas **no se reparten entre los contratos por fecha**. Una factura fuera de
  todo período no es de ninguno; una dentro de dos períodos superpuestos no es de una.
  Por eso el cruce va por persona.
* El importe manuscrito de una factura de talonario **no se lee con OCR**. Medido:
  Tesseract leyó `6.200` donde el papel decía `6.000`, con las tres configuraciones de
  acuerdo entre sí — un error silencioso, que es la peor clase.

### 2.3 La demostración vive en su propio legajo

`demo --limpiar` borraba la base activa sin preguntar. Con legajos, eso significaba que
`ufil --legajo 87.933 demo --limpiar` borraba el legajo 87.933 entero. Hoy hay tres
cerrojos y el legajo de demostración sale marcado **«datos de prueba»** en la lista,
antes de que nadie entre.

---

## 3. Qué cambió, en archivos

`34 archivos · +4.223 −323`, en seis entregas.

**Nuevos**

| Archivo | Qué es |
|---|---|
| `ufil/legajos.py` | El registro de legajos y sus carpetas |
| `ufil/castellano.py` | Plural, concordancia, miles, pesos, fechas, cámaras |
| `DESIGN_SYSTEM.md` | El sistema visual, con los contrastes medidos |
| `render.yaml` | El despliegue en la nube, con disco y con clave |
| `docs/10-un-legajo-por-causa.md` | Por qué una base por legajo |
| `docs/11-contrato-o-factura.md` | Por qué las platas no se suman |
| `pruebas/test_legajos.py` · `test_familias.py` · `test_castellano.py` · `test_cola.py` · `test_accesibilidad.py` | 63 pruebas nuevas |

**Los que más cambiaron:** `ufil/servidor.py`, `ufil/web/app.js`, `ufil/web/estilo.css`,
`ufil/esquema.sql`, `ufil/capa7_export.py`, `ufil/cli.py`, `ufil/config.py`.

---

## 4. Migración de la base

`ESQUEMA_VERSION` pasó de **13 a 14**. La migración es automática y **no destructiva**:
corre sola al abrir una base vieja.

| Qué | Cómo |
|---|---|
| Estados de `campo` | `automatico` y `a_revisar` se traducen a los ocho de `confianza.py` |
| Columnas nuevas | `ALTER TABLE` una por una (`COLUMNAS_AGREGADAS` en `db.py`) |
| `v_contrato` | Se recrea filtrada por tipo de documento |
| `v_contrato_todo` | Se renombra a `v_documento_todo` y gana la columna `familia` |
| `v_comprobante` | Nueva |

**Un `DROP TABLE` acá borraría las revisiones hechas a mano**, que es lo único que no se
puede volver a generar a partir de los originales. Por eso se migra con `ALTER` y no se
recrea nada que tenga datos.

> **Antes de actualizar una instalación con trabajo hecho: `ufil respaldo`.** Tarda
> segundos y es la única red.

---

## 5. Variables de entorno

| Variable | Para qué | Por omisión |
|---|---|---|
| `UFIL_DATOS` | Dónde vive todo | `datos/` |
| `UFIL_LEGAJO` | Legajo con el que arranca el proceso | ninguno |
| `UFIL_BASE` | Base suelta, sin legajos (instalaciones viejas y pruebas) | — |
| `UFIL_ACCESO` | `auto` \| `clave` \| `abierto` | `auto` (según la dirección de escucha) |
| `UFIL_CLAVE` | Clave fija, mínimo 12 caracteres | se genera al azar en cada arranque |
| `UFIL_NUCLEOS` | Páginas leídas en paralelo | los núcleos de la máquina |
| `UFIL_DPI_RENDER` | DPI de las imágenes de trabajo | 200 |
| `UFIL_OCR_IDIOMA` | Idioma de Tesseract | `spa` |
| `UFIL_DEMO` | Fuerza el cartel de datos de prueba | — |
| `UFIL_UNIDAD` | «UFIL Paraná» | del módulo `ufil/identidad.py` |
| `UFIL_AREA` | «Área Anticorrupción» | ídem |
| `UFIL_FISCALES` | Fiscales, separados por **punto y coma** | ídem |
| `UFIL_ORGANISMO`, `UFIL_JURISDICCION`, `UFIL_SISTEMA` | El resto de la marca | ídem |
| `PORT` | Lo inyecta el servicio de nube; el contenedor lo respeta | `8713` |

**`UFIL_ACCESO=abierto` significa «quién llega a este puerto ya está restringido afuera
de este proceso».** Ponerla donde eso no es cierto deja el legajo abierto de par en par.

Las de identidad también se pueden poner en un `identidad.json` en la carpeta de datos.
El orden es: los valores del módulo, después el JSON, después el entorno. Un solo lugar
cambia el encabezado de la pantalla de acceso, el de «Acerca del sistema» y la portada
de todo lo que se exporta.

### Eliminar un legajo

Se hace desde **Sistema → Legajos**, con el botón «Eliminar» de cada renglón, y hay que
**escribir el número del legajo** para confirmar.

**Eliminar no borra:** mueve la carpeta entera —la base, las imágenes de página, los PDF
que se subieron y los respaldos— a `datos/eliminados/<slug>--<fecha>/`, y queda anotado
en `datos/eliminados/eliminados.jsonl`. Desde la papelera se restaura con todo adentro.

Lo único que borra de verdad en todo el sistema es **«Borrar del disco»**, desde la
papelera, y pide el número otra vez. Es la operación que libera espacio: la papelera
sigue ocupando disco, y la pantalla dice cuánto.

Un legajo con un procesamiento en curso no se puede eliminar: la base está abierta por
otro hilo y moverla en el medio deja el trabajo escribiendo en un archivo que ya no está
donde el registro dice. El sistema lo dice y pide pararlo primero.

---

## 6. Instalación

* **Una máquina de la fiscalía:** [`EMPEZAR.md`](EMPEZAR.md). Tres pasos; después es
  doble clic en `scripts/arrancar.bat`.
* **Sin internet, en dos etapas:** [`INSTALAR.md`](INSTALAR.md).
* **Docker:** `docker compose up -d` → `http://127.0.0.1:8713`. El corpus se monta en
  **solo lectura**: la restricción de no tocar el original la hace cumplir el kernel, no
  la buena voluntad del código.
* **Render:** `render.yaml`, con Blueprints. Trae el disco persistente y la clave.

### Respaldo y restauración

```bash
ufil --legajo 87.933 respaldo          # va a la carpeta de respaldos DE ESE legajo
```

Copia consistente con el sistema andando, sin pedirle a nadie que deje de trabajar. Se
restaura parando el sistema y copiando el archivo sobre `ufil.sqlite` (borrando antes
los `.sqlite-wal` y `.sqlite-shm` si están).

Los PDF originales están en su carpeta y las imágenes de página se rehacen procesando de
nuevo. **Lo que no se regenera es el trabajo de las personas**, y eso vive en un solo
archivo.

---

## 7. Cómo se verificó

### Pruebas: 164, en verde

| Archivo | Qué custodia |
|---|---|
| `test_reglas.py` | Las invariantes del pliego |
| `test_confianza.py` | Un valor dudoso no alimenta un total firme |
| `test_legajos.py` | Ningún cálculo cruza legajos — por función y **por HTTP con cuatro hilos en paralelo** |
| `test_familias.py` | Un contrato no es una factura |
| `test_cola.py` | Dos revisores no se pisan; deshacer no borra |
| `test_castellano.py` | Concordancia, y que el informe no corrompa apellidos |
| `test_accesibilidad.py` | Contraste WCAG AA en los dos temas; la puerta de la nube |

**Verificadas contra versiones rotas a propósito.** Tres veces se rompió el código
adrede para confirmar que la prueba lo agarra: el legajo global en vez de por hilo (4
pruebas fallan), el `replace` sobre la frase entera (falla), el borde de control con
`--filete` (falla). Una prueba que no falla cuando el defecto está no custodia nada.

### Revisión visual

**18 pantallas × 4 anchos** (1440×900, 1366×768, 1024×768, 390×844), con un navegador de
verdad por CDP: sin desborde horizontal, sin errores de JavaScript, sin `undefined` ni
`NaN` en pantalla. **72 combinaciones, todas limpias.**

Contraste: los 20 pares que existen en la interfaz, en los dos temas, calculados — no
estimados. Todos los enlaces pasan 4,5:1 en claro y en oscuro.

---

## 8. Riesgos que quedan, y son institucionales

Estos **no son defectos del software**. Son decisiones que le corresponden a la fiscalía
y que el sistema no puede tomar por nadie.

### 8.1 El material en un servidor de un tercero

`appufil.onrender.com` es cómodo para mostrar el sistema, y **es un servidor de una
empresa extranjera**. Subir ahí material de una causa penal es una decisión que no la
toma quien despliega: la toma quien responde por el legajo.

Para mostrárselo al fiscal alcanza con el legajo de demostración, que viene marcado.
Para trabajar en serio, la instalación va en una máquina de la fiscalía.

### 8.2 Nada de lo que sale de acá está verificado por una persona salvo lo que diga que sí

El sistema separa lo firme de lo provisional y lo dice en cada pantalla y en cada
exportación. **Eso no reemplaza el cotejo contra el original.** La planilla lo dice en la
portada y el informe en la advertencia final, pero conviene que esté dicho también acá:
un dato «firme» significa *el sistema lo leyó con confianza alta*, no *alguien lo miró*.

La columna «verificados por una persona» es la que dice eso último, y hoy en la mayoría
de los legajos vale cero.

### 8.3 No hay usuarios ni sesiones

Cada decisión registra **quién** la tomó, pero ese «quién» es lo que la persona escribió
en su navegador. No hay contraseña por usuario ni forma de probar que quien dijo llamarse
`perez.ana` sea ella. Para trazabilidad interna alcanza; **para una discusión sobre quién
firmó qué, no**.

Se sacó del alcance a pedido. Si el legajo va a ser objeto de una discusión sobre
autoría, esto hay que resolverlo antes.

### 8.4 La clave es una sola, para todos

En modo red hay **una clave por arranque**, no una por persona. Quien la tiene, entra.
No se puede revocar el acceso de una persona sin cambiársela a todas.

### 8.5 El OCR se equivoca, y a veces sin avisar

Está medido y documentado en [`docs/08`](docs/08-hasta-donde-aguanta-el-escaneo.md) y
[`docs/09`](docs/09-lo-escrito-a-mano.md). El hallazgo que más importa: el modo
«blanco y negro» del escáner da **mejor exactitud aparente** (95,8% contra 83,9%) y
produjo **el único error silencioso de toda la medición**, porque binarizar destruye el
desacuerdo entre rutas de lectura que es como el sistema se entera de que no sabe.

**Recomendación:** escanear en escala de grises, no en modo texto.

### 8.6 Lo que el sistema todavía no sabe hacer

* No lee manuscrita, y no va a leerla. Propone y una persona confirma.
* No reconoce formularios que no tengan un perfil escrito. Los que no reconoce
  **aparecen en «Quedaron afuera»** con el motivo, no desaparecen.
* No cruza legajos entre sí, a propósito.
* No sabe si dos personas con el mismo nombre y sin documento legible son la misma. No
  las fusiona sola: **propone y espera confirmación**.
