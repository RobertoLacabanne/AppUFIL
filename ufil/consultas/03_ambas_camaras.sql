-- Contratados presentes en las DOS cámaras, con o sin superposición temporal.
SELECT
  COALESCE(nombre_literal, '(sin nombre)')  AS contratado,
  documento_literal                         AS documento,
  persona_id,
  SUM(CASE WHEN camara='A' THEN 1 ELSE 0 END) AS contratos_camara_a,
  SUM(CASE WHEN camara='B' THEN 1 ELSE 0 END) AS contratos_camara_b,
  SUM(COALESCE(monto_centavos,0))           AS acumulado_centavos,
  MIN(inicio)                               AS desde,
  MAX(fin)                                  AS hasta
FROM v_contrato
WHERE persona_id IS NOT NULL AND camara IS NOT NULL
GROUP BY persona_id
HAVING contratos_camara_a > 0 AND contratos_camara_b > 0
ORDER BY acumulado_centavos DESC;
