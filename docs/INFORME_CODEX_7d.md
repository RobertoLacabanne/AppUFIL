# 7d — Importes impresos con rol incierto

Se modificaron `ufil/renglones.py` y `pruebas/test_renglones_precios.py`.

Una columna sin rol, con importes marcados con `$` en al menos dos filas con descripción y sin otra columna numérica candidata, permite conservar los renglones. Se exige ausencia de roles cantidad, precio y subtotal. Cada fila rescatada debe tener su propio importe con `$`; las cantidades expresas fundidas por OCR también quedan fuera de esta regla.

El renglón conserva descripción e importe literales completos (incluido el cierre `)` del ejemplo), ancla de precio a la celda original y ancla de fila. Guarda `precio_unitario=NULL`, `precio_motivo='rol_incierto'`, sin derivación ni subtotal supuesto. La tolerancia al cierre se usa sólo para reconocer este caso: no modifica el lector decimal general ni reescribe la celda.

No fue necesario modificar `ufil/precios.py`: su exclusión por precio unitario nulo ya cubre estos renglones y quedó comprobada por regresión. Tampoco fue necesario modificar `ufil/tablas.py`: la estructura de estas tablas ya estaba detectada. Se mantienen las condiciones existentes de selección de piezas documentales; no se amplió la creación de piezas para fojas sin documento.

## Verificación

- La regresión sintética del ejemplo falló antes del cambio: `0 != 4` renglones.
- Con el cambio verifica los cuatro literales, precio nulo, motivo, ausencia de derivación y anclas; además verifica su exclusión de las referencias de comparación.
- Casos negativos: dos columnas monetarias (también si una no tiene `$`), ausencia de moneda, una sola fila y moneda en una sola fila.
- Casos adicionales: umbral de dos filas, importes enteros, exigencia de moneda en cada fila y conservación del comportamiento ante cantidad/unidad y cantidad fundida con descripción.
- Comando final ejecutado en primer plano: `python -m unittest pruebas.test_renglones_precios pruebas.test_contrataciones_hallazgos_7b`.
- Resultado: **52 pruebas, OK** (23,971 s). No se ejecutó la suite completa ni se midió nuevamente el legajo real.

No se ejecutó git ni se hicieron commits. No se modificaron `ufil/comparabilidad.py`, `ufil/hallazgos.py` ni `ufil/web/*`.
