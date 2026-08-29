-- EL DENOMINADOR HONESTO.
-- Cuántos campos críticos quedaron resueltos solos, cuántos esperando revisión y
-- cuántos en conflicto. Sin esta consulta, cualquier tablero miente por omisión:
-- muestra lo que encontró y calla lo que no pudo leer.
SELECT
  c.nombre                                                              AS campo,
  COUNT(*)                                                              AS total,
  SUM(CASE WHEN c.valor_literal IS NOT NULL AND c.estado='automatico'
           THEN 1 ELSE 0 END)                                           AS resueltos_solos,
  SUM(CASE WHEN c.valor_literal IS NOT NULL AND c.estado='a_revisar'
           THEN 1 ELSE 0 END)                                           AS con_valor_a_revisar,
  SUM(CASE WHEN c.estado IN ('verificado','corregido') THEN 1 ELSE 0 END) AS verificados_a_mano,
  SUM(CASE WHEN c.nulo_motivo='conflicto' THEN 1 ELSE 0 END)            AS conflictos,
  SUM(CASE WHEN c.nulo_motivo='ilegible'  THEN 1 ELSE 0 END)            AS ilegibles,
  SUM(CASE WHEN c.nulo_motivo='ausente'   THEN 1 ELSE 0 END)            AS ausentes,
  SUM(CASE WHEN c.nulo_motivo='ambiguo'   THEN 1 ELSE 0 END)            AS ambiguos,
  ROUND(100.0 * SUM(CASE WHEN c.valor_literal IS NOT NULL AND c.estado='automatico'
                         THEN 1 ELSE 0 END) / COUNT(*), 1)              AS pct_sin_intervencion
FROM campo c
GROUP BY c.nombre
ORDER BY CASE c.nombre
           WHEN 'nombre' THEN 1 WHEN 'documento' THEN 2 WHEN 'fecha_inicio' THEN 3
           WHEN 'fecha_fin' THEN 4 WHEN 'monto' THEN 5 ELSE 9 END;
