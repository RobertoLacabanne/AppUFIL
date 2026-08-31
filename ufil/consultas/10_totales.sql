-- LOS TOTALES, SEPARADOS. Dos veces separados, por dos motivos distintos.
--
-- 1. Por FIRMEZA. Un solo número que mezcle lo firme con lo dudoso es una afirmación
--    falsa, aunque el promedio dé parecido. Antes de esta separación el panel mostraba
--    $5.847.000 diciendo que sumaba «sólo los montos leídos con seguridad», y adentro
--    había $761.900 de seis montos que en ese momento estaban en la cola.
--
-- 2. Por FAMILIA. Un contrato dice cuánto se PACTÓ pagar; una factura dice cuánto se
--    COBRÓ. Sumarlos no da un total más completo: da un número que no corresponde a
--    nada, y cuando la factura es el cobro de ese mismo contrato cuenta la misma plata
--    dos veces. Medido: con un contrato de $10.000 y su factura de $2.500 el acumulado
--    decía $12.500 y el panel decía «2 contratos».
--
-- Lo firme sale de las vistas `v_contrato` y `v_comprobante`, que ya filtran por
-- estado y por tipo. Lo provisional sale de `v_documento_todo`, que trae todo con el
-- estado de cada campo al lado.
--
-- `todo` va MATERIALIZED a propósito. Sin eso, SQLite volvía a armar `v_documento_todo`
-- —un GROUP BY sobre todos los documentos unidos a todos los campos— una vez por cada
-- subconsulta que la nombra, y son cuatro. Medido en un legajo de 4.547 documentos y
-- 24.235 campos: 397 ms la consulta entera, de los cuales unos 220 eran recorrer cuatro
-- veces lo mismo. Con una sola pasada quedan.
WITH todo AS MATERIALIZED (
  SELECT familia, monto_centavos, monto_estado FROM v_documento_todo
)
SELECT
  -- ── LO CONTRATADO ────────────────────────────────────────────────────────
  (SELECT COALESCE(SUM(monto_centavos), 0) FROM v_contrato)             AS total_firme_centavos,
  (SELECT COUNT(*) FROM v_contrato WHERE monto_centavos IS NOT NULL)    AS contratos_con_monto_firme,
  (SELECT COALESCE(SUM(monto_centavos), 0) FROM todo
    WHERE familia='contrato' AND monto_estado='pendiente_baja')         AS total_provisional_centavos,
  (SELECT COUNT(*) FROM todo
    WHERE familia='contrato' AND monto_estado='pendiente_baja')         AS contratos_con_monto_provisional,

  -- ── LO FACTURADO ─────────────────────────────────────────────────────────
  -- Nunca se suma con lo de arriba. Se muestra al lado, dicho como lo que es.
  (SELECT COALESCE(SUM(monto_centavos), 0) FROM v_comprobante)          AS total_facturado_firme_centavos,
  (SELECT COUNT(*) FROM v_comprobante WHERE monto_centavos IS NOT NULL) AS comprobantes_con_monto_firme,
  -- Las facturas de talonario traen el importe a mano y NO se leen. Que existan y no
  -- se sepa por cuánto es un dato, y tiene que estar a la vista de quien lea el total
  -- facturado: sin esto, ese total parece completo y no lo está.
  (SELECT COUNT(*) FROM todo
    WHERE familia='comprobante' AND monto_centavos IS NULL)             AS comprobantes_sin_importe_legible,
  (SELECT COUNT(*) FROM todo WHERE familia='comprobante')               AS comprobantes,

  -- ── PENDIENTE SIN NÚMERO ─────────────────────────────────────────────────
  -- En conflicto, sin leer, o escrito a mano. No hay monto que sumar; hay trabajo.
  (SELECT COUNT(*) FROM campo c
    WHERE c.nombre='monto' AND c.estado IN ('conflicto','no_revisado'))  AS montos_pendientes_sin_valor,

  -- Contratos sin monto firme, por cualquier motivo. Es el número que dice cuánto le
  -- falta al total firme para estar completo.
  (SELECT COUNT(*) FROM documento d
    WHERE d.tipo IN ({{TIPOS_CONTRATO}})
      AND NOT EXISTS (SELECT 1 FROM campo c
                       WHERE c.documento_id = d.id AND c.nombre='monto'
                         AND c.estado IN ('automatico_alta','verificado','corregido')))
                                                                        AS contratos_sin_monto_firme,

  -- ── DOCUMENTOS QUE NO SON NI UNA COSA NI LA OTRA ─────────────────────────
  -- Tipos que no están en ninguna familia conocida. No entran a ningún total, y por
  -- eso mismo tienen que contarse: un documento que no se suma en ningún lado y
  -- tampoco se cuenta en ningún lado, desapareció.
  (SELECT COUNT(*) FROM todo WHERE familia IS NULL)                     AS documentos_sin_familia,

  -- ── CUÁNTO MIRÓ UNA PERSONA, Y CUÁNDO ────────────────────────────────────
  (SELECT COUNT(*) FROM campo
    WHERE estado IN ('verificado','corregido'))                         AS campos_verificados_por_persona,
  (SELECT COUNT(*) FROM campo
    WHERE estado IN ('pendiente_baja','conflicto','no_revisado'))       AS campos_pendientes_de_revision,
  (SELECT MAX(cuando) FROM auditoria)                                   AS ultima_revision,
  (SELECT MAX(ingerido_en) FROM archivo)                                AS ultima_carga;
