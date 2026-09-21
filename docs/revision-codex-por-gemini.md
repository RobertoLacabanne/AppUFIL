# Revisión Independiente del Backend de Papelera (Codex)

Realizada por: Gemini (Rol: Ingeniero Principal Frontend / UX / QA Visual)
Fecha: 2026-09-19
Referencia de revisión: `origin/codex/post-1464f24`

## Veredicto General

El backend diseñado por Codex es de un nivel técnico **excepcional**. 
El manejo de exclusión concurrente entre procesos nativos (usando locks del SO, `LockFileEx` en Windows y `fcntl.flock` en POSIX), el modelo de *snapshotting* de bases de datos relacionales sin corromper la integridad transaccional (recolectando cuidadosamente `EXISTS` en un árbol hacia adelante y chequeando `PRAGMA foreign_key_check`), y la seguridad de la idempotencia en las operaciones de restauración/destrucción, son completamente sólidos.

Incluso patrones propensos a generar **fallas en cascada**, como un error en la rutina `limpiar_pendientes`, están totalmente contenidos. La estructura de limpieza asíncrona apoyada en claves foráneas (`ON DELETE CASCADE` en `papelera_limpieza`) garantiza de forma nativa que si un usuario "restaura" un archivo atascado en el limbo de borrado, la solicitud de borrado físico desaparece automáticamente junto con el registro en SQLite. Es una arquitectura inquebrantable.

## Hallazgos

A continuación, detallo los hallazgos desde el punto de vista de integración e interfaz de usuario (UX). **No se ha detectado ningún fallo crítico de pérdida de datos ni brechas de seguridad (path traversal mitigado exitosamente mediante `_ruta_segura`).**

### 1. Campo insuficiente para consistencia UX (Páginas)
* **Clasificación**: BAJO
* **Archivo**: `ufil/papelera.py`
* **Endpoint**: `GET /api/papelera/archivos`
* **Reproducción**: El payload de la API devuelve `documentos`, `bytes`, y `revisiones`, pero omite intencionalmente la cantidad de `paginas` físicas del PDF original.
* **Impacto**: La pantalla principal ("Ingesta") ancla su experiencia de usuario fuertemente en el tamaño de los documentos ("Megabytes" y "Páginas"). Al mover un documento a la papelera, el usuario pierde esta referencia vital de magnitud de su archivo físico, obligando a la UI a mostrar la cantidad de "Documentos inferidos" como aproximación pobre.
* **Corrección sugerida**: Modificar `def listar(cx):` para incluir `json_extract(registros,'$.paginas') AS paginas` en la sentencia SQL, puesto que ese valor fue resguardado correctamente en el snapshot JSON.

### 2. Campo insuficiente para UX y Auditoría (Lote)
* **Clasificación**: MEDIO
* **Archivo**: `ufil/papelera.py`
* **Endpoint**: `GET /api/papelera/archivos`
* **Reproducción**: El sistema no devuelve el `lote` al cual pertenecía el archivo eliminado.
* **Impacto**: En las fiscalías, los archivos se ingestan masivamente por "Lote" (ej: el lote de allanamientos del martes). Si se quitan decenas de archivos por un error de ingesta en un lote, la papelera se llena de filas sin agrupación visible. Resulta imposible para el operario humano identificar de un vistazo a qué lote correspondían los archivos caídos.
* **Corrección sugerida**: Dado que `_instantanea` guarda la fila original del archivo, se recomienda extraer el campo de lote en la consulta: `json_extract(registros,'$.filas.archivo[0].lote') AS lote` y exponerlo al frontend para poder construir columnas de filtrado útiles.

### 3. Divergencia en métrica de Revisiones Humanas
* **Clasificación**: BAJO
* **Archivo**: `ufil/servidor.py` (`api_archivos`)
* **Endpoint**: `GET /api/archivos`
* **Reproducción**: La propiedad `revisiones` suma exclusivamente un `COUNT(*)` sobre la tabla `revision_humana`. Sin embargo, `tiene_revisiones_humanas` realiza una verificación exhaustiva (`EXISTS`) contra unas 10 tablas distintas (relaciones, foliaturas, decisiones, campos manuales, etc).
* **Impacto**: Podría darse la circunstancia de que un usuario acepte 50 fusiones o cree 20 relaciones (lo cual activa `tiene_revisiones_humanas=True`), pero el contador devuelto de `revisiones` exprese "0". El frontend actual ha sido parcheado para forzar un visual de "1 revisión humana" como mínimo si se detecta que existe actividad, mitigando el impacto ante el usuario final, pero la semántica del dato recibido es parcial.
* **Corrección sugerida**: De considerarse un valor nominal valioso, se sugiere expandir el `COUNT` para incluir las otras tablas auditadas. Si resultare muy costoso (por degradación de *performance* de SQL al usar múltiples agregaciones), documentar formalmente que este número es sólo un proxy referencial de la capa base de anotación.

## Conclusión

El contrato es respetable, íntegro y ha sido implementado y validado en la rama frontend `gemini/appufil-agent` con exactitud. El backend es promovible sin mayores fricciones funcionales.
