-- LOS TOTALES, SEPARADOS. Un solo número que mezcle lo firme con lo dudoso es una
-- afirmación falsa, aunque el promedio dé parecido.
--
-- Antes de esta separación el panel mostraba $5.847.000 diciendo que sumaba «sólo los
-- montos leídos con seguridad», y adentro había $761.900 de seis montos que en ese
-- momento estaban en la cola esperando que alguien los mirara.
SELECT
  -- FIRME: montos en estado automático de alta confianza, verificado o corregido.
  -- Es el único número que puede ir a un informe.
  (SELECT COALESCE(SUM(CAST(n.valor_norm AS INTEGER)), 0)
     FROM campo c JOIN normalizacion n ON n.campo_id = c.id
    WHERE c.nombre='monto'
      AND c.estado IN ('automatico_alta','verificado','corregido')
      AND NOT EXISTS (SELECT 1 FROM conflicto k
                       WHERE k.documento_id=c.documento_id AND k.campo_nombre=c.nombre
                         AND k.estado='abierto'))                       AS total_firme_centavos,
  (SELECT COUNT(*) FROM campo c
    WHERE c.nombre='monto'
      AND c.estado IN ('automatico_alta','verificado','corregido')
      AND NOT EXISTS (SELECT 1 FROM conflicto k
                       WHERE k.documento_id=c.documento_id AND k.campo_nombre=c.nombre
                         AND k.estado='abierto'))                       AS contratos_con_monto_firme,

  -- PROVISIONAL: hay un número leído, pero el sistema no lo sostiene. Se muestra
  -- aparte y dicho como lo que es.
  (SELECT COALESCE(SUM(CAST(n.valor_norm AS INTEGER)), 0)
     FROM campo c JOIN normalizacion n ON n.campo_id = c.id
    WHERE c.nombre='monto' AND c.estado='pendiente_baja')               AS total_provisional_centavos,
  (SELECT COUNT(*) FROM campo c
    WHERE c.nombre='monto' AND c.estado='pendiente_baja')               AS contratos_con_monto_provisional,

  -- PENDIENTE SIN NÚMERO: en conflicto, sin leer, o escrito a mano. No hay monto que
  -- sumar; hay trabajo que hacer.
  (SELECT COUNT(*) FROM campo c
    WHERE c.nombre='monto' AND c.estado IN ('conflicto','no_revisado'))  AS montos_pendientes_sin_valor,

  -- Contratos que NO tienen un monto firme, por cualquier motivo. Es el número que
  -- dice cuánto le falta al total firme para estar completo.
  (SELECT COUNT(*) FROM documento d
    WHERE d.tipo LIKE 'contrato%'
      AND NOT EXISTS (SELECT 1 FROM campo c
                       WHERE c.documento_id = d.id AND c.nombre='monto'
                         AND c.estado IN ('automatico_alta','verificado','corregido')))
                                                                        AS contratos_sin_monto_firme,

  -- Cuánto de esto lo miró una persona.
  (SELECT COUNT(*) FROM campo
    WHERE estado IN ('verificado','corregido'))                         AS campos_verificados_por_persona,
  (SELECT COUNT(*) FROM campo
    WHERE estado IN ('pendiente_baja','conflicto','no_revisado'))       AS campos_pendientes_de_revision,

  -- Cuándo se actualizó por última vez lo que se está mostrando.
  (SELECT MAX(cuando) FROM auditoria)                                   AS ultima_revision,
  (SELECT MAX(ingerido_en) FROM archivo)                                AS ultima_carga;
