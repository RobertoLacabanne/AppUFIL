-- Montos por persona: cantidad de contratos, acumulado y presencia por cámara.
-- El acumulado suma SOLO los contratos con monto firme; `contratos_sin_monto`
-- dice cuántos quedaron afuera de esa suma, para que el total nunca se lea como
-- si fuera completo.
SELECT
  COALESCE(nombre_literal, '(sin nombre)')                         AS contratado,
  documento_literal                                                AS documento,
  persona_id,
  COUNT(*)                                                         AS contratos,
  SUM(CASE WHEN monto_centavos IS NULL THEN 1 ELSE 0 END)          AS contratos_sin_monto,
  SUM(COALESCE(monto_centavos, 0))                                 AS acumulado_centavos,
  MIN(inicio)                                                      AS primer_inicio,
  MAX(fin)                                                         AS ultimo_fin,
  GROUP_CONCAT(DISTINCT camara)                                    AS camaras,
  MIN(confianza_min)                                               AS confianza_min
FROM v_contrato
WHERE persona_id IS NOT NULL
GROUP BY persona_id
ORDER BY acumulado_centavos DESC;
