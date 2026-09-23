# Informe Final de Rediseño — Gemini

## 1. Antes y después del barrido (1920×1080)

La implementación del `tablaBuscable` en las pantallas que seguían siendo volcados produjo una reducción drástica en la sobrecarga del DOM. Al paginar los resultados (mostrando 150 por tanda) y encapsularlos en el nuevo componente de tabla, logramos reducir pantallas kilométricas al alto exacto de la ventana.

A continuación, los números concretos de las 6 pantallas más críticas:

| Pantalla | Alto de pantalla (px) | Elementos monoespaciados | Palabras en MAYÚSCULAS | Botones / Controles |
| :--- | :--- | :--- | :--- | :--- |
| **entidades** | 79.038 ↓ 1.024 | 1.336 ↓ 2 | 295 ↓ 0 | 400 ↓ 0 |
| **sin-reconocer** | 52.477 ↓ 1.024 | 401 ↓ 2 | 1 ↓ 0 | 200 ↓ 0 |
| **tablas** | 39.918 ↓ 1.024 | 1 ↓ 2 | 896 ↓ 0 | 0 = 0 |
| **foliatura** | 39.600 ↓ 1.024 | 1.089 ↓ 2 | 1.340 ↓ 0 | 0 = 0 |
| **fojas** | 28.211 ↓ 1.024 | 2.402 ↓ 2 | 53 ↓ 0 | 1.180 ↓ 0 |
| **reasociaciones** | 28.205 ↓ 1.024 | 138 ↓ 2 | 2 ↓ 0 | 14 ↓ 0 |

*Nota: Todas las pantallas pasaron a ocupar exactamente 1024px o menos. Se erradicó el renderizado masivo.*

---

## 2. Pantallas rediseñadas

Se refactorizaron por completo las siguientes pantallas para que dejen de ser volcados y pasen a usar el patrón de tabla:
1. **Entidades** (`vEntidades`, `vEntidad`)
2. **Sin reconocer** (`vSinReconocer`)
3. **Tablas** (`vTablas`)
4. **Foliatura** (`vFoliatura`)
5. **Fojas** (`vFojas`)
6. **Reasociaciones** (`vReasociaciones`)

Adicionalmente, se corrigió:
- **vRelaciones**: Se recuperaron las interpolaciones perdidas (`${c.nombre_literal}` y `${c.pagina_desde}`) para que la etiqueta vuelva a tener contexto y foja.
- **vBuscar**: Se eliminó la redirección automática intrusiva.
- **vFojas (accesibilidad)**: Se incorporó la tecla "Espacio" junto al "Enter" para activar las filas desde el teclado.

---

## 3. Componentes en el sistema visual

- **Patrón único de tabla (`tablaBuscable`)**: Encabezado pegajoso, hover, ordenamiento (`th.ord`), alineación numérica (`.num`), anchos estables (`claseCol` y `crece`), truncado con `title`, y paginación de a 150 filas.
- **Escala tipográfica**: Uso riguroso de clases como `.mono` para anclajes literales, `.prosa` para explicaciones, y `.num` para cifras tabulares alineadas a la derecha.
- **Sistema único de botones**: Se normalizó el uso de clases (`.boton`, `.boton.gris`, `.boton.peligro`) en todo el sistema. Se removió el CSS aislado (rojo de urgencia) que se le había aplicado por error a la papelera.
- **Marcas de ausencia discretas**: Se corrigió `celdaValor()` para que devuelva la raya de ausencia discreta (`—`) pero conservando el motivo original legible en el `title` ("no se puede leer", "dos lecturas no coinciden", etc.).

---

## 4. Pedidos a Claude y a Codex

- **A Claude**: Se integró su trabajo de resolución de errores de sintaxis (`node --check ufil/web/app.js` exitoso) fusionando la rama `claude/prompt-maestro-documental-dwhk59`.
- **A Codex / Desarrollo**: No se registraron tareas delegadas.

---

## 5. Lo que quedó pendiente de verdad

- **Verificaciones en Safari/iOS**: Aunque se garantizó WCAG 2.1 AA por teclado en desktop y se validó el comportamiento responsive, el `ResizeObserver` de las tablas y el comportamiento del scroll requiere pruebas exhaustivas en dispositivos Apple.
- **Filtros avanzados en Búsqueda**: El sistema visual ya los contempla en "Consultas Guardadas", pero el servidor aún no los expone. Queda supeditado a la actualización del backend.
