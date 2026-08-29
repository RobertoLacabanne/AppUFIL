# Fase 1 — Piloto vertical del Caso A

Estado: **corriendo de punta a punta.** Ingesta → lectura → extracción anclada →
identidad → cruces SQL → interfaz → exportación.

Lo que sigue está medido, no estimado. Los comandos para reproducirlo están abajo.

---

## 1. El veredicto primero

> **El piloto NO alcanza los umbrales de exactitud que propuse en la Fase 0.**
> **Sí alcanza —y con margen— el umbral que importa: cero errores silenciosos.**

| Campo | Exactitud | Umbral | | Errores silenciosos | Umbral | |
|---|---|---|---|---|---|---|
| nombre | 84,0 % | 95 % | ✗ | 0 | ≤1 | ✓ |
| documento | 93,8 % | 98 % | ✗ | 0 | 0 | ✓ |
| fecha de inicio | 100 % | 98 % | ✓ | 0 | 0 | ✓ |
| fecha de fin | 98,0 % | 98 % | ✗ *(48/49)* | 0 | 0 | ✓ |
| monto | 96,0 % | 98 % | ✗ | 0 | 0 | ✓ |

**De los 12 errores y omisiones, los 12 están marcados.** Ninguno entró en un cruce
haciéndose pasar por dato firme. Los errores son confusiones de carácter que un OCR
hace y son visibles al lado del folio: `Rosa I.` leído `Rosa Il`, `27-` leído `21-`.

Corregir esos 12 a mano en la cola es trabajo de unos pocos minutos. Después de
hacerlo, monto llega a 100 %. **Ese es exactamente el modo de operación buscado:** el
sistema hace el 85 % solo, marca lo que no puede sostener, y una persona cierra la
diferencia mirando el folio al lado del dato.

### Advertencia sobre estos números, que es importante

**Están medidos sobre un corpus SINTÉTICO de 50 contratos generados para probar el
software**, no sobre los contratos de la Legislatura. Un escaneo real es peor:
fotocopia de fotocopia, sello de tinta corrida sobre el número, papel amarillo,
manuscrito, grapas, el formulario que cambió en 2019.

Lo que estos números prueban es que **el software funciona y que el arnés de medición
mide bien**. Los números del §12 del pliego salen recién cuando tengamos los 50
contratos reales con su transcripción a mano. Espero que sean peores. Cuánto peores,
es justamente lo que hay que medir.

---

## 2. Cobertura: cuánto hizo solo

| Campo | Resueltos sin intervención | A revisar | Conflictos | Ausentes |
|---|---|---|---|---|
| nombre | 78 % | 8 | 3 | 0 |
| documento | 80 % | 7 | 0 | 3 |
| fecha de inicio | 100 % | 0 | 0 | 0 |
| fecha de fin | 90 % | 3 | 0 | 1 |
| monto | 82 % | 7 | 0 | 1 |

Cobertura media de campos críticos: **86 %**. Quedan 39 campos en la cola de revisión
sobre 250. Eso está dentro del 15-20 % que la Fase 0 daba por aceptable, y es
deliberado: **preferimos una cola larga a un error invisible.**

---

## 3. Hallazgos que produjo el piloto

Sobre los 50 contratos sintéticos, sin ninguna intervención humana:

- **17 pares de contratos superpuestos**, discriminados entre intracámara e intercámara.
- **14 personas con contratos en las dos cámaras.**
- **1 contrato con fecha imposible** (fin anterior al inicio).
- **2 contratos excluidos del cruce** por faltarles un dato firme — contados y listados
  aparte, para que el total de hallazgos no se lea como si el universo estuviera completo.
- **2 propuestas de fusión de identidad**, ninguna aplicada sola.

Encontró los cinco casos que el generador de corpus había plantado a propósito:
superposición entre cámaras, superposición dentro de una cámara, misma persona con el
nombre escrito distinto pero mismo CUIL, nombres parecidos sin documento (que **no** se
fusionaron solos), y la fecha imposible.

---

## 4. Rendimiento, en CPU sin GPU

| | |
|---|---|
| Lectura (OCR, dos rutas por página) | **1,67 s por página** |
| Pipeline completo, 50 documentos | **92 s** |
| Proyección a 5.000 contratos de una página | **≈ 2 h 20 min** |

Corre entero en CPU. **No hace falta GPU para el Caso A.** La GPU suma en la ruta del
modelo de visión (páginas complejas, manuscrito, sellos encima del texto) y en la capa
interpretativa en lenguaje natural, no en esto.

---

## 5. Dos cosas que aprendí corriéndolo, y que cambian el diseño

### El cotejo entre dos configuraciones de Tesseract es más débil de lo que parece

En la primera corrida, **las dos rutas de OCR coincidieron en un valor equivocado**:
las dos leyeron `21-27219539-2` donde el papel dice `27-`. El cotejo no lo detectó, y
tiene sentido: las dos rutas comparten el motor de reconocimiento. Lo que difiere entre
ellas es cómo segmentan la página, no cómo interpretan un glifo.

Lo salvó el **umbral de confianza** (0,75 < 0,85 → a la cola).

Conclusión concreta: hoy el error silencioso lo está frenando la confianza, no la doble
lectura. Esto **refuerza** el argumento de la Fase 0 para el modelo de visión: hace
falta una segunda lectura con un motor de reconocimiento *genuinamente distinto*. No es
un lujo, es la pieza que falta del mecanismo.

### El primer error silencioso que apareció fue un bug mío, no del OCR

El sistema devolvió `Héctor ESQUIVEL, D` donde el papel dice `ESQUIVEL, Héctor D.`. No
fue el OCR: fue mi código agrupando palabras en renglones con `round(y/6)`, que en una
página con medio grado de inclinación parte el renglón en dos y da vuelta el orden.

Está corregido (los renglones ahora se arman por solapamiento vertical) y hay una
prueba que lo cubre. Lo dejo escrito porque es la moraleja: **el error silencioso no
viene sólo del modelo. Viene, y bastante, del código que lo rodea.**

---

## 6. Cómo reproducirlo

```bash
# 1. Generar el corpus sintético con su verdad conocida
python3 herramientas/generar_fixtures.py --cantidad 50

# 2. Correr el piloto entero y medirlo
python3 -m ufil.cli piloto datos/corpus-sintetico --lote piloto-01 \
        --referencia datos/corpus-sintetico/referencia.csv

# 3. Comprobar que las restricciones del pliego se siguen cumpliendo
python3 -m ufil.cli verificar
python3 -m unittest discover -s pruebas

# 4. Mirarlo
python3 -m ufil.cli servir      # http://127.0.0.1:8713
```

---

## 7. Cómo quedaron las restricciones duras

| Restricción | Cómo se cumple | Cómo se comprueba |
|---|---|---|
| **1. Offline total** | Cero llamadas de red en el código. Fuentes servidas desde disco. El servidor escucha sólo en 127.0.0.1. Sin Node ni compilación en la máquina de destino. | `ufil verificar` falla si `UFIL_VLM_URL` apunta fuera de la máquina |
| **2. Original inmutable** | La ingesta abre en `"rb"` y nada más. Los derivados van a `datos/derivados/`, indexados por el hash del original. En Docker el corpus se monta `:ro`. | `ufil verificar` rehashea una muestra en cada corrida; hay una prueba que altera un original y comprueba que salte |
| **3. Nada se inventa** | El carril de datos no tiene ningún modelo generativo. Los parsers devuelven `ambiguo` antes que suponer. La base tiene un `CHECK`: o valor, o motivo. | 7 pruebas en `NadaSeInventa` |
| **4. Todo anclado** | `CHECK (valor_literal IS NULL OR (pagina_nro IS NOT NULL AND x0 IS NOT NULL))`. Un valor sin coordenadas **no entra en la base.** | prueba `test_no_puede_haber_valor_sin_anclaje` |
| **5. Dos carriles** | Separación estructural: `campo` contra `interpretacion`. Una interpretación sin fuentes lanza excepción. En la interfaz, mono contra serif bastardilla sobre otro fondo. | `ufil verificar` + 2 pruebas |

---

## 8. Lo que todavía no está

Dicho para que no se lea como terminado:

- **Ruta del modelo de visión: no implementada.** `ufil/capa1_vlm.py` define el
  contrato y explica cómo enchufarla, pero no simula nada: llamarla sin configurar
  levanta una excepción explícita. Falta saber qué GPU hay y correr el banco de prueba.
- **Capa interpretativa en lenguaje natural: no está.** Lo que hay son reglas
  determinísticas que ya cubren buena parte de la sección 7 del pliego. El resumen y las
  preguntas en lenguaje natural necesitan un LLM local, y eso necesita hardware.
- **Búsqueda semántica y grafo de vínculos: no están** (Fase 4).
- **El procesamiento se dispara por línea de comandos**, no desde la interfaz.
- **Caso B: no empezado**, según lo decidido en la Fase 0 (adoptar Datashare).

---

## 9. Decisiones discutibles de esta fase

1. **Cambié de opinión sobre el frontend.** La Fase 0 proponía Vue o Svelte compilado.
   Lo hice con JavaScript sin dependencias ni compilación, servido por la biblioteca
   estándar de Python. Motivo: en la fiscalía no hay que instalar Node, no hay paso de
   build, y el día que el que lo instaló no está, `app.js` se lee entero en media hora.
   Se paga en comodidad de desarrollo. Con dos o tres usuarios sobre una máquina, creo
   que conviene. Es reversible.

2. **Extracción por perfil declarativo, no por modelo.** Los formularios se describen en
   `ufil/perfiles/*.json`. Es determinístico, auditable y adaptable sin tocar código —
   pero **depende de que el formulario sea razonablemente uniforme.** Si los contratos
   de la Legislatura varían mucho entre cámaras y años, va a hacer falta un perfil por
   variante, o la ruta del modelo de visión. Es la apuesta más grande de esta fase y
   depende de una respuesta que todavía no tengo (pregunta 2 de la Fase 0).

3. **Tolerancia al rótulo mal leído.** El cotejo del rótulo acepta hasta 18 % de
   diferencia: `APELLlDO Y NOMBRE` con ele minúscula sigue siendo el rótulo. Esto NO
   relaja la restricción 3 —el rótulo es texto impreso conocido, que ya sabemos qué
   dice; lo que se afloja es *encontrar dónde está el campo*, no *qué dice el campo*—
   pero es un aflojamiento y corresponde señalarlo.

4. **Un valor cargado a mano se ancla al folio entero.** Cuando una persona escribe un
   valor sobre un campo que no tenía recuadro, el anclaje es la página completa, con
   `ruta='humano'`. Es un anclaje degenerado; la alternativa era relajar la restricción
   4 para valores humanos, que me pareció peor.

5. **Reprocesar el lote conserva el trabajo humano.** Correcciones de campo y fusiones
   confirmadas viven en `revision_humana` y `fusion_decidida`, indexadas por el hash del
   archivo, y se vuelven a aplicar solas. Cuesta dos tablas más; sin eso, mejorar el
   perfil de extracción borraría semanas de revisión, que es inaceptable.
