# Un contrato no es una factura

## El defecto, medido

Un legajo con **un contrato de $10.000** y **su factura de $2.500**. El panel decía:

```
total firme: $12.500  ·  2 contratos
```

Ninguna de las dos cosas era cierta. No había dos contratos: había uno y una factura. Y
$12.500 no es una cantidad de plata que exista en ninguna parte.

Peor cuando la factura es el cobro de ese mismo contrato —que es el caso normal—:
sumarlas **cuenta la misma plata dos veces**.

## Por qué pasaba

La vista `v_contrato`, que es de donde salen todos los cruces y todos los acumulados,
no filtraba por tipo de documento. Cualquier fila de `documento` con un monto entraba:
facturas, recibos, decretos, y cualquier tipo que no reconociéramos.

El sistema *sabía* qué era cada foja —`ufil/clasificacion.py` lo decide por frases de
molde desde hace rato, y `documento.tipo` lo guarda—. Lo que faltaba era que ese dato
llegara a las consultas.

## Cómo quedó

### Tres familias, y una cuarta que es no saber

`ufil/clasificacion.py`:

| familia | qué dice | tipos |
|---|---|---|
| `contrato` | lo que se **pactó** pagar | `contrato_obra`, `contrato_personal`, `contrato_locacion` |
| `comprobante` | lo que se **cobró** | `factura`, `recibo`, `remito` |
| `acto` | ni una cosa ni la otra | `decreto`, `resolucion`, `rendicion` |
| `null` | **no lo sabemos** | cualquier otro |

`familia(tipo)` devuelve `None` para lo que no conoce, y eso es lo importante: un tipo
sin familia **no se acomoda en la más probable**. No entra a ningún total, y se cuenta
aparte para que se vea. Un documento que no se suma en ningún lado y tampoco se cuenta
en ningún lado, desapareció — y este sistema existe para no perder documentos.

### Dos carriles en la base

* `v_contrato` — sólo contratos, sólo campos firmes.
* `v_comprobante` — sólo facturas, recibos y remitos, sólo campos firmes.
* `v_documento_todo` — todo, con su `familia` y el estado de cada campo. Es para las
  pantallas que muestran lo provisional como provisional.

Se llama `v_documento_todo` y no `v_contrato_todo` porque adentro hay facturas: el
nombre viejo invitaba justo al error que esto corrige.

### La lista de tipos vive en un solo lugar

El esquema no escribe los tipos: los **pide**.

```sql
WHERE d.tipo IN ({{TIPOS_CONTRATO}})
```

`db.esquema_sql()` los sustituye desde `ufil/clasificacion.py`, y `capa4_analisis` hace
lo mismo con las consultas `.sql`. Sustituir texto adentro de SQL es normalmente una
mala idea; acá lo que se sustituye no es un dato de nadie sino una lista de literales
escrita en el código. Lo que se gana es que la lista exista **una vez**: escrita en dos
archivos, el día que alguien agregue un tipo de contrato nuevo se va a acordar de uno y
no del otro, y lo que se rompe en silencio es un total.

Una marca sin sustituir levanta un error con su nombre, en vez de un error de sintaxis
de SQLite que no dice cuál faltó.

## Lo que hay que mirar dos veces

### El mensual no se compara con lo acumulado

`monto` en un contrato es el importe **mensual** (así lo extrae el perfil, a propósito,
para poder comparar contratos de distinto plazo). Las facturas se **acumulan**. Poner
uno al lado del otro invita a concluir que se facturó de más cuando no se sabe.

El único comparable es `monto_total`, que el contrato dice aparte. Cuando no se pudo
leer, la pantalla lo dice —celda vacía y la cuenta de cuántos contratos faltan— en vez
de mostrar un cero o el mensual en su lugar. **El sistema no multiplica mensual por
plazo para llenarla**: eso sería calcular un número que el papel dice o no dice.

### El cruce va por persona, no por contrato

Una factura no dice a qué contrato corresponde. Con una fila por contrato, una persona
con dos aparecía dos veces y **cada fila traía todas sus facturas**: sumar la columna
daba el doble de lo facturado. Salió mirando la pantalla, no en las pruebas.

Repartir las facturas entre los contratos por fecha sería adivinar: una factura fuera de
todo período no es de ninguno, y una dentro de dos períodos superpuestos no es de una.
Así que la unidad del cruce es la **persona**, y el detalle contrato por contrato está
en su ficha.

### Las facturas de talonario no tienen importe

El importe va escrito a mano y **no se lee con OCR** (ver `docs/09-lo-escrito-a-mano.md`:
Tesseract leyó `6.200` donde el papel decía `6.000`, con las tres configuraciones de
acuerdo — un error silencioso). Salen con el importe vacío, que es la verdad: hay un
comprobante y no sabemos por cuánto.

Mientras la columna «a mano» no sea cero, **el facturado está incompleto** y no se puede
comparar contra lo pactado como si fuera el total. La pantalla lo dice en cada lugar
donde muestra ese número.

### El mismo campo dice cosas distintas

En un contrato, `nombre` es el contratado. En una factura es quien la emitió, y
`fecha_inicio` es la fecha de emisión, no el inicio de nada. La interfaz rotula según la
familia del documento: **Emisor**, **CUIT del emisor**, **Fecha de emisión**,
**Importe**. Rotularlos igual que en un contrato es afirmar algo que el papel no dice.

Por eso también la cobertura va separada por familia: contarlos juntos daba «Contratado
10» en un legajo con 3 contratos, y ese número no era de nadie.

## Encontrado de paso

* **`resolver` se caía entero** con un documento cuyo valor normalizado no tenía la
  forma `DNI:1234`. No costaba ese documento: cortaba la pasada y el legajo quedaba
  **sin ninguna identidad resuelta** —sin personas, sin cruces, sin superposiciones—
  mientras la pantalla mostraba los contratos como si estuviera todo bien.
* **La portada del Excel decía «0 campos pendientes de revisión»** siempre. Filtraba por
  `estado='a_revisar'`, que dejó de existir con los ocho estados de confianza; la
  consulta seguía corriendo sin error y devolvía cero. Una afirmación falsa en un
  documento que se firma.
* En la ficha de la persona, el clic de fila se enganchaba a «la última tabla». Al
  agregar la de comprobantes debajo, cada factura abría el contrato del mismo índice.

## Las pruebas

`pruebas/test_familias.py`, con los números medidos:

* el caso de $12.500 y «2 contratos»;
* que `v_contrato` no traiga facturas y `v_comprobante` no traiga contratos;
* que una factura **no invente una superposición** de contratos (hoy no puede porque no
  tiene fecha de fin, pero eso es una propiedad del perfil, no una regla);
* que dos contratos de la misma persona no dupliquen lo facturado;
* que el mensual no se presente como comparable;
* que un tipo desconocido no entre a ningún total **y se cuente**;
* que la lista de tipos no esté escrita a mano en el esquema.
