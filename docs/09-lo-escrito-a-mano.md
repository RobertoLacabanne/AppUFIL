# Lo escrito a mano

En las facturas y recibos que acompañan las rendiciones, **el importe y el concepto van
a mano**. Es la información más valiosa del comprobante y la más difícil de leer.

---

## Lo primero: por qué el OCR no sirve, con el número

Medido sobre las facturas reales del expediente, en el campo IMPORTE. Birome sobre
recuadro, dígitos sueltos, sin cursiva: el **mejor caso posible** para un motor de OCR.

| | |
|---|---|
| Valor real | `6.000` |
| Tesseract lee | **`6.200`** |
| Con cuántas configuraciones | tres, y **las tres dieron lo mismo** |

En las otras cuatro muestras devolvió nada, `7` y `5`.

**Lo grave no es que se equivoque: es cómo.** El sistema detecta errores comparando
rutas de lectura que discrepan. Acá las tres coincidieron en el número equivocado, así
que no se levanta ningún conflicto, la confianza queda alta, y `$6.200` entra a todos
los acumulados como dato firme. Doscientos pesos por factura, multiplicado por cientos
de facturas, es un número falso adentro de una pericia y **no lo detecta nadie**.

Por eso la regla es dura y no admite matices:

> **Un campo declarado manuscrito NUNCA se llena con OCR.**

Queda nulo con motivo `manuscrito` y va a la cola con el recorte de la imagen al lado.
Y hubo que taparle una segunda puerta: la relectura focalizada usa alfabeto restringido
sobre el recorte, que es *exactamente* la configuración que leyó `6.200`.

---

## Lo segundo: qué sí se lee de una factura

Bastante, en realidad. La parte impresa del talonario es perfectamente legible:

| Se lee del impreso | No se lee |
|---|---|
| Quién emitió el comprobante | El importe manuscrito |
| Su CUIT — que es la clave que une la factura con el contrato | El concepto manuscrito |
| El número de comprobante | La fecha, si va a mano |
| La fecha de emisión, si viene impresa | |

Y hay dos clases de factura, que el sistema distingue solo:

- **Electrónica de AFIP** — trae punto de venta, número de comprobante y fecha de
  emisión impresos. **El importe también está impreso y se lee.**
- **De talonario** — el formulario viene impreso y los datos se escriben a mano. El
  importe no se lee.

La distinción no se hace por puntaje —el perfil de la electrónica resuelve más campos y
ganaría siempre, y le sacaría un número inventado a una manuscrita— sino por lo que el
documento dice de sí mismo.

---

## Lo tercero: el lector de manuscrita

Un modelo de visión sí puede leer esa letra. Se enciende a propósito:

```bash
UFIL_VISION=1 python3 -m ufil.cli manuscrita
```

Y funciona bajo tres reglas que no son negociables:

**1. El modelo PROPONE, no decide.** Lo que devuelve va a su propia tabla —`propuesta`,
nunca `campo`— y aparece en la cola al lado del recorte, con otro fondo y diciendo de
qué modelo salió. El campo sigue vacío hasta que **una persona lo confirma**. Un modelo
de visión también se equivoca; la diferencia con el OCR es que acá el error queda a la
vista, contra la imagen, en el momento de decidir. Confirmarlo es una tecla, y queda
registrado como corrección humana con quién y cuándo.

**2. Se le muestra un recorte, no la página.** Se le pregunta por UN campo y se le manda
sólo ese pedazo. Preguntar poco y mostrar poco es lo que hace que la respuesta sea
verificable de un vistazo: quien revisa mira exactamente lo mismo que miró el modelo.

**3. Tiene permitido decir que no sabe, y se le pide que lo haga.** El formato de
respuesta lo obliga a elegir entre un valor y «ilegible». Un «no se lee» es una
respuesta correcta y barata; un número inventado cuesta una pericia.

---

## Y esto sale de la máquina

El sistema nació sin salida a internet (restricción 1 del pliego). Esto la usa, y por lo
tanto **el recorte de una foja del legajo viaja al servicio**. Conviene decirlo sin
adornos:

- Está **apagado por omisión**. Hay que encenderlo a propósito con `UFIL_VISION=1`.
- Queda **registrado** qué se mandó, de qué foja y cuándo, en la tabla `propuesta`.
- **Estado del sistema** lo muestra como aviso mientras esté encendido.
- Se manda **un recorte de un campo**, no la foja entera ni el expediente.
- Apuntando `UFIL_VISION_URL` a un modelo corriendo en la misma máquina, **no sale
  nada**: la restricción 1 sigue en pie y todo lo demás funciona igual.

Es una decisión de quien conduce la investigación, no del programa.

---

## Lo que todavía no está medido

**El lector de manuscrita está escrito pero no probado contra el modelo.** El entorno
donde se desarrolló no tiene credenciales, así que la llamada nunca corrió de verdad.
Lo que sí está probado y con pruebas automáticas: que el recorte sale bien de la foja y
llega como PNG; que la propuesta se guarda en su tabla y **no** toca el campo; que sin
encender nada el sistema se comporta como siempre.

Antes de usarlo sobre un expediente hay que correrlo sobre un puñado de facturas ya
transcritas a mano y ver el porcentaje. Como todo lo demás en este sistema: **el número
primero, la confianza después.**
