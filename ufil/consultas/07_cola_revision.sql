-- La cola de trabajo: todo lo que el sistema no resolvió, ordenado por lo que más
-- daño hace si queda mal (campos críticos primero, y dentro de eso lo más dudoso).
SELECT
  c.id            AS campo_id,
  d.id            AS documento_id,
  a.nombre        AS archivo,
  c.nombre        AS campo,
  c.valor_literal AS valor,
  c.nulo_motivo   AS motivo,
  c.confianza,
  c.pagina_nro,
  c.x0, c.y0, c.x1, c.y1,
  c.ruta,
  CASE WHEN k.id IS NOT NULL THEN 'conflicto'
       WHEN c.nulo_motivo IS NOT NULL THEN 'nulo'
       ELSE 'baja confianza' END AS clase
FROM campo c
JOIN documento d ON d.id = c.documento_id
JOIN archivo a   ON a.sha256 = d.sha256
LEFT JOIN conflicto k ON k.documento_id = c.documento_id
                     AND k.campo_nombre = c.nombre AND k.estado='abierto'
WHERE c.estado = 'a_revisar'
ORDER BY
  CASE c.nombre WHEN 'monto' THEN 1 WHEN 'fecha_inicio' THEN 2 WHEN 'fecha_fin' THEN 3
                WHEN 'documento' THEN 4 WHEN 'nombre' THEN 5 ELSE 9 END,
  COALESCE(c.confianza, 0) ASC;
