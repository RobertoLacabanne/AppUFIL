-- Lo facturado contra lo contratado, persona por persona.
-- Une el contrato con las facturas y recibos de la MISMA persona: el CUIT de la
-- factura lleva adentro el DNI del contrato, así que se cruzan solos.
-- Es el cruce que el caso necesita: qué se comprometió a pagar y qué se facturó.
SELECT
  COALESCE(k.nombre_literal, f.nombre_literal, '(sin nombre)') AS contratado,
  k.documento_literal            AS documento,
  k.persona_id,
  k.camara,
  k.inicio                       AS contrato_desde,
  k.fin                          AS contrato_hasta,
  k.monto_centavos               AS mensual_contratado_centavos,
  k.monto_total_centavos         AS total_contratado_centavos,
  COUNT(f.documento_id)          AS facturas,
  SUM(CASE WHEN f.monto_centavos IS NOT NULL THEN 1 ELSE 0 END) AS facturas_con_importe,
  SUM(COALESCE(f.monto_centavos, 0)) AS facturado_legible_centavos,
  -- Las facturas de talonario traen el importe a mano y NO se leen. Se cuentan
  -- aparte para que nadie tome el acumulado por el total facturado.
  -- OJO con el LEFT JOIN: un contrato SIN facturas trae una fila con todo en NULL, y
  -- contarla como «factura sin importe» diría que hay una factura manuscrita donde no
  -- hay ninguna factura. Se cuenta contra el id del documento, no contra el monto.
  SUM(CASE WHEN f.documento_id IS NOT NULL AND f.monto_centavos IS NULL
           THEN 1 ELSE 0 END)      AS facturas_a_mano,
  GROUP_CONCAT(f.archivo || ' f.' || f.pagina_desde, ' · ') AS fojas_facturas
FROM v_contrato k
LEFT JOIN v_contrato f
       ON f.persona_id = k.persona_id
      AND f.tipo IN ('factura', 'recibo')
WHERE k.tipo LIKE 'contrato%'
  AND k.persona_id IS NOT NULL
GROUP BY k.documento_id
ORDER BY facturas DESC, contratado
