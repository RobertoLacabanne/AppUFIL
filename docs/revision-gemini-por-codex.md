# Revisión de la interfaz de Gemini por Codex

Frontend de `7b7c43c`, sin modificar, servido desde `.revision-gemini/ufil/web`
contra el backend real y un legajo sintético. Se usó Edge headless por CDP, sin
dependencias de automatización externas. Se ejercitaron botones, confirmaciones,
400/409, doble clic, navegación y geometría del visor. Las fallas de red y carreras
se indujeron sustituyendo `api` en el navegador; el zoom usó una imagen SVG sintética.

La [evidencia original](revision-gemini-evidencia.json) se conserva sin alterar.
Sus observaciones corresponden a esa interfaz, no a las correcciones posteriores.

| Hallazgo | Observación y clave de evidencia |
|---|---|
| G1 | El nombre `x',globalThis.__revisionXss=1,'z.pdf` ejecuta código al pulsar Quitar. `xss.codigoEjecutado=true`; `xss.handler` muestra la entidad HTML ya decodificada dentro de JavaScript. |
| G2 | `O'Brien.pdf` rompe el botón con `SyntaxError`. `apostrofe.errores`; no abre diálogo. |
| G3 | Con zoom 2, el marco queda en (120,160), cuando corresponde (240,320). `zoomAntes`, `zoomDespues`. |
| G4 | Dos restauraciones consecutivas mandan dos POST: 200 y 409. `dobleRestauracion`. También se logró duplicar Destruir editando la confirmación durante el pedido: `dobleDestruccion.peticiones=2`. |
| G5 | El GET posterior a restaurar falla y queda una promesa rechazada sin mensaje visible. `refrescoSinCatch.promesas`, `dialogos=0`. |
| G6 | La acción termina después de navegar a Informes y repinta Papelera bajo `#/informes`. `perdidaContexto`. La recarga desde otras pantallas se identificó además al leer `pedirQuitarArchivo`; no tiene medición separada en el JSON. |
| G7 | Una respuesta `{}` se interpreta como vacía. `respuestaIncompleta=true`. |
| G8 | La respuesta sintética de 1.500 archivos dibuja 1.500 filas y 3.000 botones, sin paginador. `listaGrande`. |
| G9 | Papelera marca la sección Documentos y su enlace no está visible en esa navegación. `navegacion.seccion`, `enlaceVisible=false`. |

La evidencia también contiene los escapes literales señalados después como G10
(`procesando`, `dobleRestauracion.texto`). `contrato={}` en la evidencia antigua no
demuestra el contrato HTTP: éste se verifica con las pruebas de producto.

## Cómo repetir

```powershell
$env:PYTHONUTF8 = '1'
$env:REVISION_WEB = 'C:\Users\rober\AppUFIL-gemini\ufil\web'
$env:REVISION_EVIDENCIA = 'docs/revision-gemini-evidencia-corregida.json'
python -m unittest scripts.revision_gemini_runner -v
```

Sin `REVISION_WEB` se usa `.revision-gemini/ufil/web`; sin `REVISION_EVIDENCIA` se
actualiza el archivo de evidencia original. `REVISION_EDGE` permite elegir el
ejecutable Chromium. Cada ejecución satisfactoria registra ruta, huella de `app.js`,
fecha y versión del backend para identificar lo observado.

El arnés ahora registra resultados en lugar de exigir que existan los defectos.
Acepta botones con `data-sha` o el `onclick` anterior, espera al menos una restauración
y observa cuántas hubo; el simulador de 1.500 archivos respeta la paginación solicitada.
Los fallos del propio arnés (servidor, navegador/CDP, selectores o tiempos de espera)
siguen dando salida distinta de cero. Está fuera del discovery de `pruebas/`.

## Estado al cerrar este incremento

- **Comprobado:** evidencia histórica preservada; `node --check` y compilación Python
  del arnés pasan. Se intentó ejecutar contra la interfaz original y contra el
  directorio corregido. Edge cerró CDP en `Network.enable`, antes de cargar la
  aplicación; en otro intento no publicó el puerto. Chrome tampoco publicó CDP.
- **Inferido:** el arnés adaptado admite las correcciones de los hallazgos sin
  convertirlas en fallos; falta confirmarlo en una ejecución completa de navegador.
- **Pendiente:** repetir la revisión visual completa en un entorno que permita
  iniciar Chromium/CDP y sobre la integración final. No se generó evidencia nueva
  ni se dio por aprobada la interfaz corregida.
