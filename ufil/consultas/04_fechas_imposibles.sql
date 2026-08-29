-- Contratos con fechas que no pueden ser. NO se corrige ninguna: se listan para
-- que alguien vaya al folio y mire.
SELECT
  documento_id, archivo, camara,
  COALESCE(nombre_literal,'(sin nombre)') AS contratado,
  inicio, fin,
  CASE
    WHEN fin < inicio THEN 'fin anterior al inicio'
    WHEN CAST(substr(inicio,1,4) AS INTEGER) < 1983 THEN 'año de inicio fuera de rango'
    WHEN CAST(substr(fin,1,4) AS INTEGER) > CAST(strftime('%Y','now') AS INTEGER) + 2
         THEN 'año de fin muy posterior'
    WHEN julianday(fin) - julianday(inicio) > 3650 THEN 'duración mayor a diez años'
  END AS motivo,
  confianza_min
FROM v_contrato
WHERE inicio IS NOT NULL AND fin IS NOT NULL
  AND ( fin < inicio
     OR CAST(substr(inicio,1,4) AS INTEGER) < 1983
     OR CAST(substr(fin,1,4) AS INTEGER) > CAST(strftime('%Y','now') AS INTEGER) + 2
     OR julianday(fin) - julianday(inicio) > 3650 )
ORDER BY documento_id;
