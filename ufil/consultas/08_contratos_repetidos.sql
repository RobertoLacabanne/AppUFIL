-- Contratos que aparecen MÁS DE UNA VEZ en la base.
--
-- No es lo mismo que un archivo duplicado: dos PDF idénticos se detectan por su huella
-- digital y no entran dos veces. Esto es lo otro, y es más peligroso: el MISMO contrato
-- entrando desde archivos DISTINTOS. Pasa cuando se vuelve a escanear una parte de una
-- pila y las dos tandas se suben como PDF grandes con varios contratos adentro: los
-- archivos son distintos —una página de diferencia alcanza—, así que la huella no los
-- reconoce, y el mismo contrato termina sumando dos veces en los acumulados.
--
-- El sistema NO los borra ni los suma una sola vez por su cuenta: dos contratos con los
-- mismos datos también pueden ser dos contratos reales. Los lista para que decida una
-- persona.
SELECT
  documento_literal                          AS documento,
  COALESCE(nombre_literal,'(sin nombre)')    AS contratado,
  inicio, fin,
  monto_centavos,
  COUNT(*)                                   AS veces,
  GROUP_CONCAT(DISTINCT archivo)             AS archivos,
  GROUP_CONCAT(documento_id)                 AS documentos,
  CASE WHEN COUNT(DISTINCT sha256) > 1
       THEN 'entró desde archivos distintos'
       ELSE 'repetido dentro del mismo archivo' END AS origen
FROM v_contrato
WHERE documento_literal IS NOT NULL
  AND inicio IS NOT NULL AND fin IS NOT NULL
GROUP BY documento_norm, inicio, fin, monto_centavos
HAVING COUNT(*) > 1
ORDER BY veces DESC, contratado;
