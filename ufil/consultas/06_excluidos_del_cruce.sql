-- Contratos que NO pudieron entrar en la consulta de superposición, y por qué.
-- Es la contracara de 01: lo que el tablero no está mirando.
SELECT
  documento_id, archivo, camara,
  COALESCE(nombre_literal,'(sin nombre)') AS contratado,
  documento_literal                       AS documento,
  inicio, fin,
  TRIM(
    CASE WHEN inicio IS NULL     THEN 'sin fecha de inicio; '   ELSE '' END ||
    CASE WHEN fin    IS NULL     THEN 'sin fecha de fin; '      ELSE '' END ||
    CASE WHEN persona_id IS NULL THEN 'sin persona asignada; '  ELSE '' END ||
    CASE WHEN monto_centavos IS NULL THEN 'sin monto; '         ELSE '' END
  ) AS falta
FROM v_contrato
WHERE inicio IS NULL OR fin IS NULL OR persona_id IS NULL OR monto_centavos IS NULL
ORDER BY documento_id;
