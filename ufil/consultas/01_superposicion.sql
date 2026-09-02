-- Superposición temporal de contratos de una misma persona.
-- Es la consulta central del Caso A.
--
-- La condición de solape es la clásica de intervalos:  inicio_A <= fin_B AND inicio_B <= fin_A
--
-- Sólo entran contratos cuyas DOS fechas son dato firme. Un contrato al que le falta
-- una fecha no se estima ni se asume abierto: queda afuera y aparece contado en
-- 05_cobertura.sql. El denominador siempre se puede ver.
SELECT
  a.documento_id                                  AS doc_a,
  b.documento_id                                  AS doc_b,
  a.archivo                                       AS archivo_a,
  b.archivo                                       AS archivo_b,
  COALESCE(a.nombre_literal, '(sin nombre)')      AS contratado,
  a.documento_literal                             AS documento,
  CASE WHEN a.camara = b.camara THEN 'intracámara'
       ELSE 'intercámara' END                     AS cruce,
  a.camara                                        AS camara_a,
  b.camara                                        AS camara_b,
  a.inicio || ' → ' || a.fin                      AS periodo_a,
  b.inicio || ' → ' || b.fin                      AS periodo_b,
  -- Las mismas fechas sin unir, para poder DIBUJAR el solape en vez de obligar a
  -- hacer la resta en la cabeza. Se agregan además de `periodo_a`/`periodo_b` y no
  -- en su lugar: la exportación las escribe ya unidas y no tiene por qué cambiar.
  a.inicio                                        AS inicio_a,
  a.fin                                           AS fin_a,
  b.inicio                                        AS inicio_b,
  b.fin                                           AS fin_b,
  CAST(julianday(MIN(a.fin, b.fin))
     - julianday(MAX(a.inicio, b.inicio)) + 1 AS INTEGER) AS dias_solapados,
  a.monto_centavos                                AS monto_a_centavos,
  b.monto_centavos                                AS monto_b_centavos,
  COALESCE(a.monto_centavos,0) + COALESCE(b.monto_centavos,0) AS suma_centavos,
  MIN(a.confianza_min, b.confianza_min)           AS confianza_min
FROM v_contrato a
JOIN v_contrato b
  ON a.persona_id = b.persona_id
 AND a.documento_id < b.documento_id
WHERE a.inicio IS NOT NULL AND a.fin IS NOT NULL
  AND b.inicio IS NOT NULL AND b.fin IS NOT NULL
  AND a.inicio <= b.fin
  AND b.inicio <= a.fin
ORDER BY dias_solapados DESC, contratado;
