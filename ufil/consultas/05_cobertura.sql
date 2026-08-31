-- EL DENOMINADOR HONESTO, campo por campo.
-- Sin esta consulta cualquier tablero miente por omisión: muestra lo que encontró y
-- calla lo que no pudo leer. Cada columna dice exactamente qué cuenta, y el porcentaje
-- dice sobre qué. «50 % resuelto solo» sin denominador no significa nada.
SELECT
  -- POR FAMILIA, además de por campo. El campo `nombre` de un contrato es el
  -- contratado; el de una factura es quien la emitió. Contarlos juntos daba «Contratado
  -- 10» en un legajo con 3 contratos, y el número no era de nadie.
  d.familia                                                             AS familia,
  c.nombre                                                              AS campo,
  COUNT(*)                                                              AS total,
  -- FIRME: se puede sumar, cruzar y llevar a un informe.
  SUM(CASE WHEN c.estado='automatico_alta' THEN 1 ELSE 0 END)           AS automaticos_firmes,
  SUM(CASE WHEN c.estado IN ('verificado','corregido') THEN 1 ELSE 0 END) AS verificados_por_persona,
  SUM(CASE WHEN c.estado IN ('automatico_alta','verificado','corregido')
           THEN 1 ELSE 0 END)                                           AS firmes,
  -- PROVISIONAL: hay un valor leído, pero el sistema no lo sostiene todavía.
  SUM(CASE WHEN c.estado='pendiente_baja' THEN 1 ELSE 0 END)            AS pendientes_baja_confianza,
  SUM(CASE WHEN c.estado='conflicto' THEN 1 ELSE 0 END)                 AS conflictos,
  SUM(CASE WHEN c.estado='no_revisado' THEN 1 ELSE 0 END)               AS sin_revisar,
  -- CERRADO SIN VALOR: alguien lo miró y confirmó que no hay nada que leer.
  SUM(CASE WHEN c.estado='ilegible_confirmado' THEN 1 ELSE 0 END)       AS ilegibles_confirmados,
  SUM(CASE WHEN c.estado='ausente_confirmado'  THEN 1 ELSE 0 END)       AS ausentes_confirmados,
  -- El porcentaje, con su denominador dicho: firmes sobre el total de campos de ese
  -- nombre en el legajo.
  ROUND(100.0 * SUM(CASE WHEN c.estado IN ('automatico_alta','verificado','corregido')
                         THEN 1 ELSE 0 END) / COUNT(*), 1)              AS pct_firme_sobre_total
FROM campo c
JOIN v_documento_todo d ON d.documento_id = c.documento_id
GROUP BY d.familia, c.nombre
ORDER BY CASE d.familia WHEN 'contrato' THEN 1 WHEN 'comprobante' THEN 2
                        WHEN 'acto' THEN 3 ELSE 4 END,
         CASE c.nombre
           WHEN 'nombre' THEN 1 WHEN 'documento' THEN 2 WHEN 'fecha_inicio' THEN 3
           WHEN 'fecha_fin' THEN 4 WHEN 'monto' THEN 5 ELSE 9 END;
