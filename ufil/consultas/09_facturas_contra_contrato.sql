-- LO FACTURADO CONTRA LO CONTRATADO, persona por persona.
-- Qué se comprometió a pagar el Estado y qué facturó esa persona. Es el cruce que el
-- caso necesita.
--
-- Se unen por el DOCUMENTO y no por el nombre: el CUIL de la factura lleva adentro el
-- DNI del contrato —en 27-28456712-4 los ocho del medio SON el DNI— así que se cruzan
-- solos aunque el nombre esté escrito distinto en cada foja.
--
-- POR QUÉ AGRUPA POR PERSONA Y NO POR CONTRATO. Una factura no dice a qué contrato
-- corresponde. Agrupando por contrato, una persona con dos contratos aparecía dos veces
-- y CADA FILA traía todas sus facturas y todo su facturado: quien sumara la columna
-- obtenía el doble de lo que se facturó. Repartir las facturas entre los contratos por
-- fecha sería adivinar —una factura fuera de todo período no es de ninguno, y una
-- dentro de dos períodos superpuestos no es de una— y este sistema no completa lo que
-- el papel no dice. Así que la unidad es la persona, y el detalle contrato por contrato
-- está en su ficha.
SELECT
  COALESCE(k.contratado, f.emisor, '(sin nombre)')  AS contratado,
  COALESCE(k.persona_id, f.persona_id)              AS persona_id,
  k.documento                                       AS documento,
  k.contratos                                       AS contratos,
  k.desde                                           AS contrato_desde,
  k.hasta                                           AS contrato_hasta,
  -- LO PACTADO: el TOTAL del contrato, no el mensual.
  -- `monto` es el importe MENSUAL (así lo extrae el perfil, a propósito, para poder
  -- comparar contratos de distinto plazo). El total está en su propio campo porque el
  -- contrato lo dice aparte. Poner el mensual acá, al lado de una facturación
  -- acumulada, invita a la conclusión falsa de que se facturó de más: son magnitudes
  -- distintas. Y multiplicar mensual por plazo sería CALCULAR un número que el papel
  -- ya dice o no dice; si el contrato no lo trae legible, esta columna queda corta y la
  -- de al lado dice cuántos contratos le faltan.
  k.total_centavos                                  AS contratado_centavos,
  k.mensual_centavos                                AS mensual_centavos,
  k.contratos_sin_total                             AS contratos_sin_total_firme,
  COALESCE(f.comprobantes, 0)                       AS facturas,
  COALESCE(f.con_importe, 0)                        AS facturas_con_importe,
  COALESCE(f.facturado_centavos, 0)                 AS facturado_legible_centavos,
  -- Las facturas de talonario traen el importe a mano y NO se leen (ver
  -- ufil/manuscrito.py). Se cuentan aparte: mientras esta columna no sea cero, el
  -- facturado está incompleto y no se puede comparar contra lo pactado como si fuera
  -- el total.
  COALESCE(f.a_mano, 0)                             AS facturas_a_mano,
  f.fojas                                           AS fojas_facturas
FROM (
  SELECT persona_id,
         MAX(nombre_literal)                              AS contratado,
         MAX(documento_literal)                           AS documento,
         COUNT(*)                                         AS contratos,
         MIN(inicio)                                      AS desde,
         MAX(fin)                                         AS hasta,
         COALESCE(SUM(monto_total_centavos), 0)           AS total_centavos,
         COALESCE(SUM(monto_centavos), 0)                 AS mensual_centavos,
         SUM(CASE WHEN monto_total_centavos IS NULL THEN 1 ELSE 0 END) AS contratos_sin_total
    FROM v_contrato
   WHERE persona_id IS NOT NULL
   GROUP BY persona_id
) k
LEFT JOIN (
  SELECT persona_id,
         MAX(nombre_literal)                              AS emisor,
         COUNT(*)                                         AS comprobantes,
         SUM(CASE WHEN monto_centavos IS NOT NULL THEN 1 ELSE 0 END) AS con_importe,
         COALESCE(SUM(monto_centavos), 0)                 AS facturado_centavos,
         SUM(CASE WHEN monto_centavos IS NULL THEN 1 ELSE 0 END)     AS a_mano,
         GROUP_CONCAT(archivo || ' f.' || pagina_desde, ' · ')       AS fojas
    FROM v_comprobante
   WHERE persona_id IS NOT NULL
   GROUP BY persona_id
) f ON f.persona_id = k.persona_id
ORDER BY facturas DESC, contratado;
