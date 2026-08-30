# Lo que el papel trae, y qué hace el sistema con eso

Cada vez que hice el corpus de prueba más parecido al papel real, aparecieron errores
graves que no se veían antes. Este documento es el registro de esa serie: qué casos se
probaron, qué se rompía, y cómo quedó.

La conclusión general vale más que cada caso: **el corpus de prueba es la parte más
importante del sistema de calidad.** Un pipeline que anda perfecto sobre documentos
prolijos de una página no dice nada sobre uno que anda sobre expedientes.

---

## 1. Varios contratos en un mismo PDF

**Cómo llega:** alguien pasa una pila de expedientes de corrido por el escáner.

**Qué pasaba:** un PDF con cinco contratos producía **un** registro que mezclaba el
nombre de un contrato con el monto y las fechas de otro. Un contrato inventado, sin
ninguna marca, entrando en los acumulados.

**Cómo quedó:** el documento dejó de ser el archivo y pasó a ser un **tramo de páginas**
dentro del archivo. El sistema detecta dónde arranca cada formulario y arma un registro
por tramo, con su rango de fojas. Verificado: de ese PDF salen los cinco, con los
nombres y montos correctos.

---

## 2. Carátulas y anexos

**Cómo llega:** el contrato casi nunca es la primera hoja. Adelante va la carátula del
expediente administrativo, atrás el anexo de constancias.

**Qué pasaba:** el visor mostraba siempre la foja 1. Con un expediente de tres fojas, el
recuadro de anclaje de un dato de la foja 2 se dibujaba **sobre la carátula**: le
mostraba al fiscal el lugar equivocado, que es la forma más rápida de perder su
confianza.

**Cómo quedó:** el visor navega entre fojas, usa las dimensiones de la que está
mostrando, abre en la que tiene los datos —no en la carátula— y sólo expone las páginas
de ese contrato.

Y para que una carátula no arranque un contrato fantasma, una página cuenta como
comienzo de formulario sólo si tiene el título **y** al menos dos de sus rótulos. Una
hoja que diga «se agrega copia del contrato de locación de servicios» no alcanza.

---

## 3. Hojas al revés o de costado

**Cómo llega:** alguien apoya la hoja girada en el escáner. Pasa todo el tiempo.

**Qué pasaba:** **pérdida total.** Tres archivos rotados 90°, 180° y 270° dieron cero
contratos. El motor no reconocía una sola palabra y el contrato desaparecía sin dejar
rastro.

**Cómo quedó:** si una página con tinta se lee con confianza baja, se sospecha de la
orientación, se gira la copia de trabajo y **se decide por el resultado**: sólo queda
girada si al releerla lee mejor. Si ningún ángulo mejora, vuelve a como estaba. El
original nunca se toca, y el visor avisa qué foja llegó girada.

Los números que llevaron a ese diseño:

| | confianza de lectura |
|---|---|
| página derecha (formulario, carátula o separador) | 0,91 – 0,96 |
| página de costado o al revés | 0,40 – 0,54 |

La cantidad de palabras **no sirve** como señal, y de hecho engaña: una página rotada
devuelve *más* palabras que una derecha (306 contra 92), porque el motor parte los
trazos verticales en fragmentos sueltos.

Y sobre el detector de orientación de Tesseract, medido:

| | confianza del detector |
|---|---|
| página densa | 25 – 28 (siempre acierta el ángulo) |
| página escasa | 0,87 – 1,57 (a veces no la detecta) |

Nunca se equivocó diciendo que una página derecha estaba torcida. Por eso: si dice que
está derecha, se le cree y no se prueba nada —así una página simplemente borrosa no paga
lecturas de más—; si sugiere un ángulo, se verifica releyendo.

**Costo:** cero en el caso normal. Sobre el corpus de 87 páginas la lectura tarda lo
mismo que antes de tener esta función.

---

## 4. El formulario cambia entre cámaras y entre años

**Cómo llega:** los mismos seis campos con otros rótulos impresos: donde una cámara pone
«APELLIDO Y NOMBRE», la otra pone «AGENTE CONTRATADO»; donde una pone «DESDE», la otra
«VIGENCIA DESDE EL».

**Qué pasaba:** con un solo perfil, de seis campos se leían dos.

**Cómo quedó:** hay varios perfiles y el sistema **prueba todos y se queda con el que
más campos críticos resuelve**, tramo por tramo. Dar de alta un formato nuevo es copiar
un JSON y cambiar los rótulos: no hay que tocar código ni saber programar.

---

## 5. Capa de texto basura embebida por el escáner

**Cómo llega:** muchos escáneres de oficina hacen su propio OCR y lo pegan adentro del
PDF. Cuando ese OCR es malo, el texto embebido es ilegible.

**Qué pasa:** el sistema lo lee igual y bien. La ruta nativa no encuentra los rótulos en
la basura, la ruta de OCR sí, y el campo queda con lectura única —marcado para revisión—
en lugar de tomar el texto embebido como bueno.

---

## 6. Hojas en blanco y separadores

**Cómo llega:** el escáner mete hojas en blanco, o el expediente trae separadores.

**Qué pasa:** se ignoran. Una hoja sin tinta ni siquiera se interroga por orientación, y
ninguna de las dos arranca un contrato.

---

---

## 7. Revisar sin salir de la pantalla

**Cómo se trabaja:** el escribiente pasa el día en la cola de revisión. Con 42 campos
repartidos en 25 documentos, cada uno costaba dos navegaciones —ir al folio y volver— y
además se perdía el lugar en la lista. Ochenta y cuatro saltos de pantalla para revisar
un lote chico.

**Cómo quedó:** la cola es una vista partida. La lista a la izquierda, y a la derecha la
foja de la fila que tiene el foco, con una **lupa sobre el campo**: el renglón ampliado,
que es lo único que hace falta mirar para decidir. `J` y `K` mueven el foco y la imagen
sigue sola. Después de decidir, el foco queda donde estaba en vez de volver al principio.

Para los campos que el sistema no encontró en ninguna foja no hay recuadro, pero igual
se muestra el folio: es lo que hay que mirar para cargarlo a mano. En la práctica, ahí
se ve por qué falló —casi siempre un sello encima del campo.

Y se puede **deshacer**. Un campo revisado guarda lo que había leído la máquina, así que
una decisión equivocada vuelve atrás con un botón. Sin eso, arreglar un clic obligaba a
reprocesar el lote entero.

---

## Lo que sigue faltando

Todo esto está medido sobre papel que generé yo. **Veinte contratos reales van a traer
casos que no se me ocurrieron**, y la serie de arriba es la prueba de que eso pasa cada
vez. Los candidatos que ya sospecho:

- fechas escritas en letras («quince de marzo de dos mil veintiuno»);
- montos en letras además de en números;
- sellos y firmas encima de los campos (el corpus lo simula, pero de manera prolija);
- fotocopias de fotocopias, que es otro nivel de degradación;
- correcciones a mano sobre el formulario impreso.
