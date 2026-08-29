# Banco de prueba

Vacío a propósito. Acá van:

1. **`paginas/`** — 30 páginas del corpus real elegidas a mano **para que duelan**: la
   torcida, la del sello encima del monto, la manuscrita, la de tabla, la fotocopia de
   fotocopia, la de la cámara cuyo formulario cambió en 2019.
2. **`referencia.csv`** — la transcripción **hecha a mano** de los campos críticos de
   esas páginas: nombre, documento, fecha de inicio, fecha de fin, monto. Es la verdad
   contra la que se mide todo. Si esta transcripción tiene errores, todas las
   mediciones posteriores mienten.
3. **`resultados/`** — una corrida por candidato de modelo, comparada contra
   `referencia.csv`.

Cada candidato se juzga por tres números y nada más:

- **exactitud por campo**
- **tasa de error silencioso** (devolvió un valor equivocado sin marcarlo como dudoso)
- **segundos por página**

No se elige por reputación del modelo ni por lo que diga un benchmark de internet.

> **Nada de este directorio se versiona en el repositorio.** Son documentos de un
> legajo. Van en el disco de la máquina de la fiscalía y nada más.
