# Un legajo por causa, y por qué están en archivos separados

## El problema

Una fiscalía no trabaja una causa por vez. En la misma máquina van a convivir los
contratos de la Legislatura, una compulsa de proveedores y lo que venga el mes que
viene. Y hay una regla que no se puede romper nunca:

> **Un número de un legajo no puede aparecer en el informe de otro.**

Un total que suma contratos de dos causas distintas es un dato falso presentado como
verdadero. No es un error de visualización: es un error que puede terminar firmado.

## La decisión

La forma habitual de resolver esto es una columna `legajo_id` en cada tabla y un
`WHERE legajo_id = ?` en cada consulta. **No lo hicimos así.**

El motivo es que ese diseño depende de que nadie se olvide el filtro nunca —ni hoy,
ni en la consulta que alguien agregue el año que viene—, y una consulta sin filtro
**no falla**: devuelve de más, en silencio, y el número queda mal.

Cada legajo tiene **su propia base de datos, en su propia carpeta**:

```
datos/
  legajos.sqlite                  el registro: qué legajos existen
  legajos/
    87-933/
      ufil.sqlite                 la base de ESE legajo
      derivados/                  sus imágenes de página
      originales/                 los PDF tal como se subieron
      respaldos/
      export/
    91-002/
      ...
```

Cruzar dos legajos no es difícil: **es imposible**. Los datos no están en el mismo
archivo. La garantía la da el sistema de archivos, no la memoria de quien escriba el
próximo `SELECT`.

Lo que se gana además:

* el respaldo y la restauración son por legajo, que es como se trabaja;
* un legajo archivado se mueve de carpeta y deja de pesar;
* una base corrupta afecta a una causa, no a todas;
* los derivados —las imágenes de página, que es lo que ocupa— también quedan separados.

Lo que se pierde, y hay que decirlo: **no se pueden cruzar dos legajos entre sí**. Eso
es a propósito. Si algún día hace falta, se hace con una exportación explícita de los
dos, no con una consulta que los toque a la vez sin que nadie lo haya decidido.

## Cómo se usa

### Desde la pantalla

Se entra y lo primero que aparece es la lista de legajos, con número, carátula, fiscal
responsable, cuántos documentos tiene y cuánto falta revisar. Se hace clic en uno y se
trabaja ahí.

Arriba de todo queda **una cinta con el número y la carátula del legajo abierto**, en
todas las pantallas y sin necesidad de bajar. Es lo único que no se puede confundir: el
error de leer un total creyendo que es de otra causa no se ve mirando el número, se ve
cuando ya está en el informe.

Para cambiar: **«Cambiar de legajo»**, a la derecha de esa cinta. La página se recarga
entera a propósito, para que no quede ni un dato de la causa anterior en pantalla.

### Desde la terminal

```bash
ufil legajos                                        # los que hay
ufil legajos crear "87.933" "Contratos Legislatura" --fiscal "Dr. Rodríguez"

ufil --legajo 87.933 ingerir /ruta/escaneos --lote "Secuestro 12/24"
ufil --legajo 87.933 leer
ufil --legajo 87.933 analizar 10_totales
ufil --legajo 87.933 respaldo
```

`--legajo` acepta el número tal como figura en la carátula (`87.933`) o el nombre de la
carpeta (`87-933`). Un número que no existe **es un error a la vista**, con la lista de
los que sí:

```
no existe el legajo «87.9333». Hay: 87-933, 88-410, 91-002
Se crea con: ufil legajos crear <numero> <caratula>
```

No se crea solo. Si la ruta se armara con lo que vino escrito, un número mal tipeado
dejaría una causa fantasma —vacía, con nombre parecido a la de verdad— y nadie se
enteraría hasta que faltaran documentos.

Sin `--legajo` se trabaja sobre una base suelta (`datos/ufil.sqlite`), que es como
funcionaban las instalaciones anteriores a los legajos. Si hay legajos cargados, el
comando lo avisa antes de correr.

Para dejar el servidor clavado en una causa —una máquina dedicada a un solo legajo—:

```bash
ufil --legajo 87.933 servir
```

## Cómo está hecho, para el que venga después

El legajo activo vive **por hilo** (`ufil/config.py`), no en una variable global. El
servidor atiende pedidos en varios hilos y el procesamiento corre en otro: con un valor
compartido, abrir una causa en una pestaña le cambiaría la causa al trabajo que está
corriendo en otra.

`config.BASE`, `config.DERIVADOS`, `config.ORIGINALES`, `config.RESPALDOS` y
`config.EXPORT` **se resuelven al vuelo** según el hilo, mediante el `__getattr__` del
módulo. Por eso ningún llamador tuvo que cambiar: el código que hacía `db.abrir()` sigue
haciendo `db.abrir()`, y abre la base que corresponde.

Tres lugares tienen que declarar el legajo explícitamente, porque son hilos que nacen
sin heredar nada:

1. **cada pedido HTTP** (`Manejador._activar_legajo`), que lo lee de la cookie
   `ufil_legajo` y **lo valida contra el registro**. Se llama en *todos* los pedidos,
   incluso los que no traen legajo: los hilos del servidor se reciclan, y el que atendió
   la causa A la seguiría teniendo activa en el pedido siguiente;
2. **el hilo del procesamiento** (`trabajo.Procesador._correr`), en su primera línea;
3. **la línea de comandos** (`cli._elegir_legajo`), que además fija la omisión del
   proceso para que `servir` la herede en los hilos que cree después.

La regla está cubierta por `pruebas/test_legajos.py`, que la verifica de las dos formas:
llamando a las funciones, y por HTTP contra un servidor de verdad con cuatro hilos
pidiendo en paralelo sobre dos legajos.

## La demostración vive en su propio legajo

`ufil demo` carga cincuenta contratos inventados para poder mostrar el sistema andando.
Esos contratos **van siempre al legajo `DEMOSTRACIÓN`**, nunca a uno de trabajo, y ese
legajo aparece marcado como **«datos de prueba»** en la lista, antes de que nadie entre.

Antes escribían en la base que estuviera activa, y `--limpiar` borraba esa base sin
preguntar: `ufil --legajo 87.933 demo --limpiar` borraba el legajo 87.933 entero, con
las revisiones hechas a mano adentro —lo único del sistema que no se puede volver a
generar a partir de los originales—. Hoy hay tres cerrojos:

1. si hay un legajo de trabajo activo, `demo` se planta y no hace nada;
2. `demo` no acepta `--base`;
3. `--limpiar` sólo borra una base que esté marcada como demostración; si tiene
   archivos y no está marcada, se niega.

Están cubiertos por `pruebas/test_legajos.py::LaDemostracionNoTocaUnaCausa`.

## Qué muestra una instalación recién puesta

Nada, que es lo correcto: no viene con datos de ejemplo. Lo primero que aparece es la
pantalla de legajos con el formulario de alta, porque lo primero que hay que hacer es
abrir la causa. El sello de arriba a la derecha dice **«Sin datos»** y no «al día»: al
día es afirmar terminado un trabajo que no empezó.
