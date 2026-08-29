# Carga de escaneos y trabajo sobre lo extraído

Lo que se agregó después de la Fase 1, a partir de que quedó claro que **los contratos
se van a ir subiendo como PDF escaneados** y que el trabajo arranca sobre lo extraído.

---

## 1. Cargar desde la interfaz

Ya no hace falta la línea de comandos para procesar un lote.

- **Arrastrar y soltar PDF** en la pantalla *Cargar escaneos*, con lote, legajo y quién
  carga.
- Cada archivo sube por separado y se ve archivo por archivo qué pasó: cuántas páginas
  tiene, si ya estaba, o por qué se rechazó.
- **Procesar** dispara el pipeline en segundo plano con barra de progreso, etapa actual
  y estimación de lo que falta. Se puede cerrar la pestaña; el trabajo sigue.
- Se procesa **sólo lo que falta**: subir un lote nuevo la semana que viene no reprocesa
  lo de esta semana.

### El archivo subido es el original, y no se toca más

Cuando un PDF llega por el navegador hay que guardarlo en algún lado, y ese archivo pasa
a ser *el* original. Entonces:

- se guarda bajo **su propio SHA-256**, no bajo el nombre que traía (dos personas suben
  `contrato.pdf` el mismo día y no se pisan);
- el nombre original se conserva **en la base**, no en el sistema de archivos;
- se le sacan los permisos de escritura (**modo 0444**);
- el contenedor corre como **usuario sin privilegios**, porque el 0444 no frena a root;
- si el contenido ya estaba, no se vuelve a escribir: se registra como copia exacta.

Se rechaza lo que no es un PDF, lo vacío, y lo que pesa más de 200 MB. Un nombre como
`../../etc/passwd.pdf` se queda en `passwd.pdf` y nunca sale del almacén — hay una
prueba que lo verifica.

---

## 2. La verificación de integridad ahora sirve de verdad

**Esto era una debilidad seria y la encontré probando.** `verificar` rehasheaba *doce
archivos al azar*. Rompí un original a propósito y no lo detectó en tres corridas. Sobre
5.000 contratos, mirar doce por vez es no mirar.

Ahora la verificación es **incremental y ordenada**: cada corrida rehashea los 250
originales que hace más tiempo que no se revisan, registra el resultado, y reporta
cuántos del total llevan verificación y desde cuándo. Corriéndola seguido, el acervo
entero queda cubierto y se sabe con números cuánto. `--completo` los rehashea todos.

Con el cambio, el original alterado se detecta en la primera corrida.

---

## 3. Buscar

Dos búsquedas separadas a propósito, porque responden cosas distintas:

- **En los datos extraídos** — «traeme a Pérez» — devuelve **contratos**, con el dato
  leído y su anclaje. Exacta; sirve para trabajar.
- **En el texto de los folios** — «dónde dice maestranza» — devuelve **páginas**, con el
  fragmento donde apareció. Amplia; sirve para encontrar.

Índice SQLite FTS5, que viene con Python: sin servicio aparte, sin Elasticsearch, sin
nada que se pueda caer un martes. Ignora tildes (`locacion` encuentra `locación`), acepta
frases entre comillas, y una consulta mal escrita no rompe nada.

---

## 4. La ficha del contratado

La pantalla que un fiscal pide primero: quién es, cuántos contratos, cuándo, por cuánto,
y cuáles se pisan.

- **Cronología de tramos**: un renglón por contrato sobre un eje temporal común. Un solo
  tono para los contratos y el rojo de estado **sólo para la superposición**, que es lo
  que el gráfico existe para mostrar. La cámara va como texto en el rótulo: la identidad
  nunca depende del color solo. Los tonos están validados para daltonismo y contraste en
  los dos modos.
- **Acumulado**, con la advertencia al lado: suma sólo los contratos con monto firme, así
  que **es un piso, no un total**.
- Los contratos **sin documento legible aparecen sueltos**, uno por contrato. Sin clave
  fuerte el sistema no los junta solo, y la ficha lo dice con todas las letras.

---

## 5. Un experimento que salió mal, y qué quedó de él

Como los escaneos son ahora *la* entrada, probé mejorar la lectura con una **relectura
focalizada**: recortar el recuadro del campo, agrandarlo tres veces, binarizarlo con
Otsu y releerlo con la lista de caracteres del tipo de campo (un campo de fecha no tiene
letras).

Suena bien. **Medido, pierde.** Sobre los 250 campos críticos del corpus de prueba:

| Estrategia de recorte | Exactitud |
|---|---|
| Lectura de página (la que ya había) | **94,7 %** |
| Recorte ajustado al valor | 84,6 % |
| Recorte holgado | 69,6 % |
| Zona de búsqueda entera | 62,3 % |

Agrandar y binarizar no agrega información que no esté en el píxel, y encima el recorte
pierde el contexto que el motor usa para segmentar. Como tercera opinión de rutina
**empeoraba todo**: los conflictos saltaron de 6 a 38 y el monto cayó de 96 % a 62 %.

Lo que sí quedó: la relectura corre **sólo como desempate**, y sólo en campos ya dudosos
y de alfabeto restringido (fecha, monto, documento). Ahí no cuesta exactitud y aporta
algo medible:

> **El 100 % de los campos que quedan en conflicto trae la lectura correcta entre las
> candidatas.** Se resuelven eligiendo, no tipeando.

Para medir eso hubo que agregar una métrica que la exactitud sola no capta: cuando el
sistema se rinde y manda un campo a la cola, ¿le está ofreciendo al que revisa la
respuesta correcta, o lo está mandando a tipear? Para el operador es la diferencia entre
una tecla y quince.

Sobre escaneos reales de 300 DPI la relectura puede rendir distinto — hay que volver a
medirlo. Queda detrás de `RELECTURA_FOCAL` en la configuración, para poder apagarla.

---

## 6. Un bug de concurrencia que hubiera aparecido el primer día

El esquema de la base se reejecutaba en **cada petición HTTP**. Con el trabajador de
fondo procesando y alguien mirando el panel, dos conexiones recreaban la vista
`v_contrato` al mismo tiempo y una fallaba con *view already exists*. Apareció apenas
la interfaz empezó a hacer dos cosas a la vez.

Ahora el esquema se aplica **una sola vez al arrancar**, con candado de proceso y número
de versión. Probado con 8 hilos abriendo la base en paralelo: sin errores.

---

## 7. Estado de la medición

Los números de calidad **no cambiaron** con todo esto, y era lo esperable: nada de lo de
arriba toca cómo se lee un contrato.

| Campo | Exactitud | Umbral | Errores silenciosos |
|---|---|---|---|
| nombre | 84,0 % | 95 % | 0 |
| documento | 93,8 % | 98 % | 0 |
| fecha de inicio | 100 % | 98 % | 0 |
| fecha de fin | 98,0 % | 98 % | 0 |
| monto | 96,0 % | 98 % | 0 |

Sigue **sin alcanzar los umbrales de exactitud** y sigue en **cero errores silenciosos**.
Y sigue medido sobre corpus sintético: el número que importa sale con los contratos
reales.

---

## 8. Lo que sigue haciendo falta

1. **Contratos reales de muestra.** Es lo único que destraba subir la exactitud, porque
   sin ellos no sé contra qué estoy optimizando. Veinte que cubran la variedad.
2. **El hardware**, para la ruta del modelo de visión y la capa interpretativa.
3. Lista de nombres y términos de interés del legajo, para priorizar por relevancia.
