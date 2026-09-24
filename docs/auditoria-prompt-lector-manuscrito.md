# Auditoría del prompt del lector de manuscrita

Revisión del único punto del sistema que le habla a un modelo de Claude:
`ufil/lector_manuscrito.py` (`INSTRUCCION`, `ESQUEMA` y la llamada en `leer_recorte`).
Se buscaron instrucciones escritas para modelos anteriores que hoy sobran o estorban, y
parámetros de la llamada que no encajan con el modelo que se usa.

## Supuestos

- **Alcance.** Todo lo que llega al modelo como texto o como parámetro: la instrucción de
  sistema, el turno de usuario armado en `leer_recorte`, el esquema de salida y la
  configuración de la llamada. En el repositorio no hay otra llamada a la API de Claude.
  Las menciones a Gemini y Codex (`scripts/revision_gemini_runner.py`,
  `herramientas/traer_corpus_real.py`, `docs/revision-*.md`) son de otras herramientas de
  desarrollo, no le mandan prompts a un modelo desde la aplicación, y quedaron afuera.
- **Modelo de destino.** `claude-opus-5`, que es el valor por omisión de
  `UFIL_VISION_MODELO` en el código.
- **Procedencia.** El archivo entró en un solo commit (`88fcda3`), así que `git blame`
  no dice qué falla de qué modelo motivó cada línea. La única falla documentada es la de
  Tesseract (leyó 6.200 donde decía 6.000), y esa sostiene las reglas de transcripción
  literal.
- **Sin medición contra el modelo.** Como dice `docs/09-lo-escrito-a-mano.md`, la llamada
  nunca corrió de verdad porque no hay credenciales. Los cambios propuestos se probaron
  con un cliente simulado y con las pruebas existentes, no con el modelo.

## Resumen

Hay tres hallazgos de confianza alta, dos de confianza media y cuatro marcados para
decidir. Por grupo: 1b (andamiaje reemplazado por una función de la API) 1; grupo 4
(configuración de la llamada) 4; señalados sin cambio propuesto 4.

Lo que más pesa no es el texto del prompt sino la llamada. Con `claude-opus-5` el modelo
razona por omisión, y ese razonamiento comparte el `max_tokens=1024` con la respuesta: el
JSON puede cortarse a mitad y el campo termina como `vision_fallo` sin explicación. A eso
se suma que el código no mira `stop_reason` antes de leer la respuesta, así que una
negativa del modelo o un corte por tope aparecen como un `StopIteration` vacío o un
`JSONDecodeError`. El prompt en sí está bien escrito: da contexto, da razones y deja
decir «no sé». La única línea que sobra es «No expliques. No agregues texto fuera del
formato pedido.», que además choca con el campo `nota`.

## Hallazgos

| # | Ubicación | Evidencia | Patrón | Por qué ya no corresponde | Confianza | Acción |
|---|---|---|---|---|---|---|
| 1 | `ufil/lector_manuscrito.py:166` | `max_tokens=1024,` | Grupo 4: `max_tokens` dimensionado para otro modelo | En `claude-opus-5` el razonamiento viene encendido cuando no se pasa `thinking`, y `max_tokens` topea razonamiento más respuesta. 1024 alcanzaba para el JSON sin razonar; con razonamiento, la respuesta puede cortarse antes de cerrar el JSON. | Alta | Reescribir: `max_tokens=16000` (hunk 1) |
| 2 | `ufil/lector_manuscrito.py:180` | `texto = next(b.text for b in r.content if b.type == "text")` | Grupo 4: respuesta leída sin mirar `stop_reason` | `claude-opus-5` puede negarse con HTTP 200 y `stop_reason: "refusal"`, y un corte por tope llega como `max_tokens`. Hoy los dos terminan en un error opaco (`StopIteration` sin mensaje o `JSONDecodeError`) dentro de la tabla `excepcion`. | Alta | Agregar: chequeo de `stop_reason` con un mensaje claro (hunk 2) |
| 3 | `ufil/lector_manuscrito.py:97` | `- No expliques. No agregues texto fuera del formato pedido.` | 1b: instrucción para forzar el formato que la salida estructurada ya garantiza | `output_config.format` con `json_schema` ya impide texto fuera del esquema. La línea sobra y además contradice a `nota`, que le pide al modelo explicar en una línea qué ve o por qué no se lee. | Alta | Quitar (hunk 3) |
| 4 | `ufil/lector_manuscrito.py:183` | `modelo=MODELO)` | Grupo 4: trazabilidad del modelo que contestó | Se guarda el modelo **pedido**, no el que **contestó**. Con un servidor local, o con el respaldo del hallazgo 5, pueden ser distintos, y la cola le muestra a quien revisa «de qué modelo salió». `r.model` trae el que efectivamente respondió. | Media | Reescribir: `modelo=r.model` (hunk 4) |
| 5 | `ufil/lector_manuscrito.py:164` | `cliente.messages.create(` sin `fallbacks` | Grupo 4: lista de migración de `claude-opus-5` | Para `claude-opus-5` se recomienda `fallbacks: "default"`: si el clasificador de seguridad se niega, el mismo pedido se reintenta en otro modelo de Anthropic dentro de la misma llamada. Para dígitos manuscritos una negativa es improbable pero no imposible. | Media | Agregar, sólo cuando no hay `UFIL_VISION_URL` (hunk 5, ver la nota) |
| 6 | `ufil/lector_manuscrito.py:164-179` | la llamada no fija `output_config.effort` | Grupo 4: esfuerzo | Sin `effort` corre en `high`. En `claude-opus-5`, `low` y `medium` rinden muy bien y son la palanca principal de costo y demora. Pero acá lo central es que el modelo dude a tiempo y responda `ilegible`, y bajar el esfuerzo podría afectar justo eso. | Baja | Señalar: medir `low`/`medium`/`high` sobre recortes reales antes de tocarlo |
| 7 | `ufil/lector_manuscrito.py:131-134` | `.convert("L")` y `ESCALA_ENVIO = 3.0`, `LADO_MAXIMO = 1400` | 1d: preparación de imagen pensada para visión más débil | El modelo lee hasta 2576 px de lado. Agrandar ×3 no agrega información y cobra más tokens visuales. Pasar a escala de grises borra el color de la tinta, que es justamente lo que distingue la birome del recuadro impreso. | Baja | Señalar: comparar color y sin agrandar contra lo actual sobre los mismos recortes |
| 8 | `ufil/lector_manuscrito.py:174` | `f"Este recorte es {que_campo} de un documento de la Legislatura. "` | Contexto (se conserva si es verdadero) | El contexto está bien si todos los legajos procesados son de la Legislatura. Si el sistema procesa documentos de otros organismos, el modelo recibe un dato falso. | Baja | Señalar: confirmar, o pasar el organismo como parámetro |
| 9 | `ufil/cli.py:408-409`, `docs/09-lo-escrito-a-mano.md:98` | «Apuntando UFIL_VISION_URL a un modelo local, no sale nada» / «todo lo demás funciona igual» | Fuera del alcance del prompt | Con `UFIL_VISION_URL`, el modelo sigue siendo `claude-opus-5` salvo que se cambie `UFIL_VISION_MODELO`, y no está verificado que un servidor local compatible acepte `output_config` con `json_schema`. Además, el aviso de la CLI remite a `docs/09-manuscrita.md`, que no existe (el archivo es `docs/09-lo-escrito-a-mano.md`). | Baja | Señalar |

### Lo que se revisó y se queda

La línea de rol («Sos un asistente de transcripción para una fiscalía») se queda porque
enfoca la tarea y va acompañada del contexto real. «Transcribí EXACTAMENTE… sin
interpretarlo ni completarlo» y «No completes, no redondees, no corrijas» dicen casi lo
mismo, pero cubren una falla demostrada (el 6.000 leído como 6.200), en un lugar donde un
número parecido cuesta una pericia. Es redundancia que funciona, así que queda. La regla
de `ilegible` lleva su razón al lado, y es la que sostiene la regla 3 del archivo. La
regla sobre los separadores del importe es un dato del dominio que el modelo no tiene. Las
descripciones del esquema son contrato, no sobran.

## Cambios propuestos

Cada hunk corresponde a un hallazgo, así que pueden tomarse por separado. Los hunks 1 a 4
se aplicaron a una copia y se verificaron. Con un cliente simulado, una respuesta normal
arma la `Propuesta` con el modelo que contestó, y `refusal` y `max_tokens` levantan
`RuntimeError` con su mensaje, que `cmd_manuscrita` registra como `vision_fallo`. Las
pruebas de `LoEscritoAManoNoSeAdivina` en `pruebas/test_reglas.py` pasan igual que antes.
Ninguna prueba ni documento cita el texto de la línea que se quita.

**Hunk 1 — tope de tokens (hallazgo 1)**

```diff
@@ -163,7 +162,9 @@
     cliente = _cliente()
     r = cliente.messages.create(
         model=MODELO,
-        max_tokens=1024,
+        # El modelo por omisión razona antes de contestar, y ese razonamiento comparte
+        # este tope con la respuesta. Con 1024 se puede cortar antes de cerrar el JSON.
+        max_tokens=16000,
         system=INSTRUCCION,
         messages=[{
             "role": "user",
```

**Hunk 2 — mirar `stop_reason` antes de leer (hallazgo 2)**

```diff
@@ -177,10 +178,16 @@
         }],
         output_config={"format": {"type": "json_schema", "schema": ESQUEMA}},
     )
+    # Una negativa del modelo o un corte por tope no traen un JSON válido. Se levanta
+    # como error: el llamador lo registra y el campo queda en la cola para tipearlo.
+    if r.stop_reason == "refusal":
+        raise RuntimeError("el modelo se negó a leer el recorte")
+    if r.stop_reason == "max_tokens":
+        raise RuntimeError("la respuesta se cortó por el tope de tokens")
     texto = next(b.text for b in r.content if b.type == "text")
     d = json.loads(texto)
```

**Hunk 3 — quitar la línea que choca con la salida estructurada (hallazgo 3)**

```diff
@@ -93,8 +93,7 @@
   escritos, incluido el punto o la coma.
 - Si no se lee con seguridad, o si dudás entre dos lecturas posibles, respondé
   ilegible=true. Es la respuesta correcta y esperada cuando el papel no da: acá una
-  duda tuya vale más que un número parecido.
-- No expliques. No agregues texto fuera del formato pedido."""
+  duda tuya vale más que un número parecido."""
```

**Hunk 4 — guardar el modelo que contestó (hallazgo 4)**

```diff
     return Propuesta(valor=(d.get("valor") or None), ilegible=bool(d.get("ilegible")),
-                     nota=str(d.get("nota", ""))[:300], modelo=MODELO)
+                     nota=str(d.get("nota", ""))[:300], modelo=r.model)
```

**Hunk 5 — respaldo ante una negativa (hallazgo 5)**

No está verificado: el paquete `anthropic` no está instalado en este entorno. Va por la
vía beta y con el parámetro en `extra_body`, porque los tipos del SDK pueden no traerlo
todavía. Se aplica sólo al servicio de Anthropic: un servidor local no conoce ni la
cabecera ni el parámetro.

```diff
     cliente = _cliente()
-    r = cliente.messages.create(
+    # Si el modelo se niega, el servicio reintenta en otro modelo de Anthropic dentro de
+    # la misma llamada. Un servidor local no lo conoce, así que ahí no se pide.
+    respaldo = {} if URL_LOCAL else {
+        "betas": ["server-side-fallback-2026-07-01"],
+        "extra_body": {"fallbacks": "default"},
+    }
+    crear = cliente.messages.create if URL_LOCAL else cliente.beta.messages.create
+    r = crear(
         model=MODELO,
         ...
         output_config={"format": {"type": "json_schema", "schema": ESQUEMA}},
+        **respaldo,
     )
```

Nota sobre el hunk 5: con el respaldo encendido, un recorte que el primer modelo declinó
lo lee otro modelo de Anthropic. El recorte no sale hacia ningún destino nuevo, pero es
otra decisión de quien conduce la investigación, igual que encender `UFIL_VISION`. Si se
toma, conviene tomarlo junto con el hunk 4, así la cola muestra qué modelo contestó de
verdad.

## Cómo verificarlo cuando haya credenciales

Ningún cambio de esta lista reemplaza una medición. Con credenciales, conviene correr
`UFIL_VISION=1 python3 -m ufil.cli manuscrita` sobre un puñado de recortes con valor
conocido: la factura de 6.000, algunos claros y algunos que una persona considere
ilegibles. Hay que registrar cuántos vuelven con propuesta, cuántos como `ilegible` y
cuántos como `vision_fallo`, y repetir cambiando de a una cosa: el esfuerzo (hallazgo 6)
y la preparación de la imagen (hallazgo 7). Lo que importa no es cuántos lee, sino que
ninguno vuelva con un número parecido en vez de `ilegible`.
