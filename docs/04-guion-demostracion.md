# Guión de demostración

Para mostrar el sistema en una reunión, en unos diez minutos. Está escrito para leer de
reojo mientras se muestra.

---

## Antes de entrar

Un solo comando deja todo cargado y levanta el servidor:

```bash
python3 -m ufil.cli demo --limpiar
```

Tarda unos dos minutos la primera vez (tiene que leer los 50 contratos con OCR). Después
abrir **http://127.0.0.1:8713**

Antes de empezar, chequear que ninguna pantalla esté rota:

```bash
python3 herramientas/humo.py
```

**La base queda marcada como DEMOSTRACIÓN**, así que arriba de cada pantalla aparece un
aviso en rojo diciendo que ninguno de esos contratos es real. Es a propósito y **no hay
que sacarlo**: es lo que evita que alguien salga de la reunión creyendo que vio datos de
la Legislatura.

> Si en cambio se va a mostrar con documentos reales, no usar `demo`: cargar el lote
> desde la pantalla *Cargar escaneos* y el aviso no aparece.

---

## El guión

### 1. Panel — «qué encontró» (1 minuto)

Abre en una frase en castellano, no en una grilla de números:

> «Sobre 50 contratos leídos: 14 personas figuran en las dos cámaras y 17 pares de
> contratos se pisan en el tiempo.»

**Lo que conviene decir:** el sistema no reemplaza a nadie, ordena. Eso que se lee en una
frase hoy sale de mirar contrato por contrato.

**Y señalar esto**, que es lo que distingue esta herramienta de una planilla:

> «Quedan 39 campos esperando revisión y 3 contratos afuera del cruce. El sistema te dice
> lo que **no** pudo leer. Un tablero que sólo muestra lo que encontró miente por
> omisión.»

### 2. Ficha de una persona (2 minutos)

Clic en la primera superposición del panel. Se abre la ficha del contratado.

- La **cronología** muestra los dos contratos pisándose. En rojo, justamente, el solape.
- El **acumulado** dice al lado «es un piso, no un total», porque suma sólo los montos
  que se leyeron con seguridad.
- Abajo, en otro fondo y en bastardilla, la **interpretación**: la hipótesis del sistema,
  con los dos documentos que la sostienen colgados.

**Lo que conviene decir:** hay dos carriles, y nunca se mezclan. Lo que está en
monoespaciada se leyó de un papel. Lo que está en bastardilla es una conjetura del
sistema y puede estar mal.

### 3. El visor — el momento que convence (2 minutos)

Clic en cualquiera de los dos contratos. Después, clic en la **ficha de anclaje** al lado
de un dato (el rectangulito azul).

El recuadro salta al lugar exacto del folio de donde se leyó ese valor.

**Lo que conviene decir:**

> «Todo dato numérico o de fecha sabe de qué archivo, qué página y qué parte de la imagen
> salió. Verificar un monto son dos segundos, no media hora de buscar el papel.»

Y mostrar el caso del contrato A-0001, que es el mejor argumento del sistema:

> «Acá el sistema leyó 21 donde el papel dice 27. **Se equivocó.** Pero fijate que el dato
> está rayado: no se equivocó callado. Está marcado y está en la cola.»

### 4. La cola de revisión (2 minutos)

- Se opera **con el teclado**, sin mouse.
- Mostrar una fila de **conflicto**: dos lecturas distintas del mismo monto. El sistema
  **no elige**: muestra las dos y espera.
- Señalar que ninguna acción dice «aceptar todo».

**Lo que conviene decir:**

> «Preferimos que dude mucho antes que se equivoque en silencio. Una omisión se corrige en
> treinta segundos. Un monto mal leído sin marcar entra en todos los cruces y no lo ve
> nadie.»

### 5. Buscar (1 minuto)

Buscar `maestranza`. Dos secciones separadas:

- en los **datos extraídos** devuelve contratos;
- en el **texto de los folios** devuelve lugares donde mirar.

Probar `locacion` sin tilde para mostrar que igual encuentra.

### 6. Llevárselo (1 minuto)

Volver al panel, abajo de todo: **Descargar la planilla** y **Descargar el informe**.

La planilla abre con una portada que aclara qué campos no están verificados. El informe
en RTF cita archivo y foja en cada afirmación.

### 7. Cómo funciona (1 minuto, si preguntan)

La pestaña **Cómo funciona** contesta lo que siempre se pregunta: de dónde salen los
datos, qué pasa si se equivoca, y qué NO hace. Está escrita sin jerga.

---

## Las preguntas que van a hacer

**«¿Esto se conecta a internet? ¿Los documentos salen de acá?»**
No. No hay una sola llamada de red en el programa; ni las tipografías, que se sirven desde
el disco. El servidor escucha únicamente en esta máquina. Todo se descarga una vez en la
instalación y después la máquina puede estar desconectada.

**«¿Puede modificar los originales?»**
No. Se guardan en modo solo lectura, el programa corre sin privilegios de administrador y
se re-verifican solos con su huella digital: si alguno cambiara, el sistema avisa.

**«¿Y si inventa un dato?»**
En el carril de datos no interviene ningún modelo generativo: la extracción es
determinística. La base de datos directamente **rechaza** guardar un campo que tenga valor
y motivo de ausencia a la vez, o ninguno de los dos, y **rechaza** un valor que no diga de
qué parte de la imagen salió.

**«¿Qué tan seguro es lo que lee?»**
Medido contra una transcripción hecha a mano: entre 84 % y 100 % según el campo. **Todavía
no llega a los umbrales que nos pusimos**, y por eso hay una cola de revisión. Lo que sí
llega, y con margen, es lo que importa: **cero errores silenciosos**, cero casos en que el
sistema devolvió un valor equivocado sin marcarlo.

**«¿Sirve para el legajo?»**
No directamente, y no pretende. Es una herramienta de trabajo interna para entender rápido
y decidir dónde mirar. Lo que se incorpora al legajo se hace después, a mano, sobre la
documentación original.

**«¿Cuánto tarda con 5.000 contratos?»**
Alrededor de dos horas y media, en una computadora común sin placa de video.

**«¿Qué hace falta para ponerlo en producción?»**
Dos cosas: **veinte contratos reales de muestra** para medir contra el papel de verdad —
todo lo que se ve acá está medido sobre documentos generados para la prueba — y saber
**qué máquina** hay disponible. Y una tercera que puede cambiarlo todo para mejor: si
existe una planilla de liquidación o un padrón digital de las cámaras, la exactitud deja
de depender del OCR.

---

## Lo que NO conviene prometer

- Que lee bien todos los contratos. No los lee, y la cola de revisión está justamente para
  eso.
- Que reemplaza la lectura del expediente. Ordena y señala; no concluye.
- Que los números que se ven en la demostración son los que va a dar con los contratos
  reales. Son sobre documentos de prueba, y con papel real van a ser peores.

Prometer de menos y mostrar de más. Al revés se paga caro.
