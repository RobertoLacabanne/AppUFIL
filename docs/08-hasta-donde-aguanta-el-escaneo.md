# Hasta dónde aguanta el escaneo

Respuesta a la otra pregunta operativa: **¿a cuántos DPI hay que escanear?** Está medida,
no opinada. Y a diferencia de la pregunta de cómo partir los PDF, acá la respuesta no es
«da más o menos lo mismo»: **da muy distinto**.

---

## La respuesta corta

> **300 DPI, en escala de grises.**
>
> A 100 DPI el sistema deja de servir: sobre papel de mala calidad la exactitud cae de
> 83,9 % a **52,5 %**. Uno de cada dos campos no se lee.
>
> Y **no hay que reescanear a más de 300**: de 300 para arriba no se gana nada medible y
> el archivo pesa el doble.

Esto se le puede pedir a quien escanea, por escrito, antes de que empiece. Reescanear
dos mil fojas porque salieron a 100 DPI es una semana perdida que se evita con una
línea en el pedido.

---

## Cómo se midió

`herramientas/barrido_calidad.py` genera **el mismo corpus** —la misma población, los
mismos contratos, el mismo temblor de papel y las mismas motas de fotocopia— escaneado
de distintas maneras, lo procesa entero en bases separadas y mide cada corrida contra la
misma transcripción de referencia. La única variable que cambia entre corridas es el
escaneo, así que la diferencia de exactitud es atribuible a él y a nada más.

```bash
python3 herramientas/barrido_calidad.py --cantidad 90 --dpis 100,300 \
        --render 150,200 --calidad malo
```

---

## El resultado que importa

Noventa contratos, todos con la degradación de papel malo —fotocopia de fotocopia,
hoja torcida, motas, contraste caído—, que es el escenario realista de un expediente
administrativo viejo:

| Escaneo | Exactitud | Errores silenciosos |
|---|---|---|
| **100 DPI** | **52,5 %** | 0 |
| **300 DPI** | **83,9 %** | 0 |

**Treinta y un puntos de diferencia por una perilla del escáner.** Con cuatrocientos
cincuenta campos medidos por corrida, esa distancia está muy lejos de ser casualidad.

### Lo que NO pasa cuando la calidad baja

Las dos corridas dieron **cero errores silenciosos**. Es el dato tranquilizador y hay
que decirlo con todas las letras: **cuando el escaneo es malo, el sistema no inventa,
falla en no leer**. Los campos que no puede sostener quedan nulos con motivo o van a la
cola de revisión. A 52,5 % de exactitud el sistema es inútil —hay que tipear la mitad a
mano—, pero **no es peligroso**: no mete un dato falso en un cruce.

Esa es exactamente la diferencia entre una herramienta que decepciona y una que
perjudica.

---

## Por qué 300 y no más

Un barrido previo, sobre papel de calidad mezclada:

| Escaneo | Exactitud | s/página | MB por contrato |
|---|---|---|---|
| 100 DPI | 92,5 % | 0,67 | 0,07 |
| 150 DPI | 96,6 % | 0,68 | 0,13 |
| 200 DPI | 94,6 % | 0,65 | 0,21 |
| 300 DPI | 95,2 % | 0,79 | 0,40 |
| 400 DPI | 96,6 % | 0,95 | 0,64 |

Entre 150 y 400 las diferencias son de tres o cuatro campos sobre ciento cincuenta:
**están dentro del ruido de la medición y no se pueden presentar como una ventaja de
uno sobre otro.** Lo que sí crece, y mucho, es el archivo: de 150 a 400 DPI el corpus
pesa **cinco veces más** por el mismo resultado.

La recomendación de 300 no sale de que gane la medición —no gana—, sale de otro lado:
es el estándar de digitalización documental, deja margen cómodo sobre el precipicio de
los 100, y **el escaneo es lo único que después no se puede rehacer**. El software se
puede volver a correr con otro criterio cuantas veces haga falta; el papel, no. Ante la
duda, el margen va del lado del original.

---

## Una perilla que sí controlamos: a cuánto rasteriza la app

El DPI del escaneo lo decide quien pasa el papel por la máquina. Pero a cuánto la app
convierte esa imagen en píxeles antes de leerla lo decidimos nosotros
(`config.DPI_RENDER`). Medido sobre originales de 300 DPI:

| La app rasteriza a | Exactitud | s/página |
|---|---|---|
| 150 | 98,6 % | 0,71 |
| 200 (lo que usa hoy) | 95,2 % | 0,78 |
| 300 | 94,6 % | 1,20 |
| 400 | 91,2 % | **6,37** |

Dos conclusiones, con distinto nivel de confianza:

**Firme: rasterizar más alto no sirve, y a 400 hace daño.** Ampliar la imagen por encima
de lo que trae el original no agrega información que no esté en el píxel; sólo agrega
píxeles. A 400 la lectura tarda **ocho veces más**, el campo `documento` se desploma a
71,4 %, y ahí apareció el **único error silencioso de todo el barrido**. La app se queda
en 200.

**Sin confirmar: 150 podría ser mejor que 200.** La diferencia son cinco campos y cae
dentro del ruido. No se cambia un valor por omisión con eso. Queda anotado como algo a
volver a medir cuando haya escaneos reales, que es cuando la respuesta va a valer.

---

## El modo blanco y negro

Muchos escáneres de oficina vienen configurados en «modo texto»: un bit por píxel, con
un umbral fijo. Sobre este corpus sintético **no hizo diferencia** (96,6 %).

**Ese resultado no se puede usar como permiso.** El texto de estos documentos sintéticos
es negro parejo sobre blanco: justo el caso donde un umbral fijo no pierde nada. Un
sello de tinta corrida, un renglón manuscrito flojo o una fotocopia de tercera
generación son exactamente lo contrario, y ahí un umbral fijo **borra para siempre** lo
que caiga del lado equivocado. No hay software que lo recupere después.

Por eso la recomendación es escala de grises igual. La información que no se escaneó
no existe.

---

## Lo que esta medición no dice

Está hecha sobre papel sintético degradado a propósito, no sobre contratos reales de la
Legislatura. Sirve para dimensionar **cuánto pesa la calidad del escaneo** y para saber
que hay un precipicio abajo de los 150 DPI. Los números absolutos —83,9 %, 52,5 %— van a
ser otros con papel de verdad.

Lo que no va a cambiar es la forma de la curva ni la dirección del consejo: **pedir
300 DPI en grises es gratis, y no pedirlo puede costar reescanear todo.**
