# Cómo conviene cargar los escaneos

Respuesta a una pregunta operativa concreta: **¿conviene subir PDF con muchos contratos
adentro, o PDF livianos con pocos?** Está medida, no opinada.

---

## La respuesta corta

> **Un PDF por contrato.** Si no se puede, un PDF por acta o por tanda chica.
>
> Pero **si es más rápido escanear de corrido, hacelo igual**: el sistema separa los
> contratos que vengan juntos y avisa cuáles quedaron repetidos. Sólo que después hay
> que resolverlos a mano.

---

## Lo que NO cambia: velocidad ni exactitud

Doce contratos, veintidós páginas, procesados de las dos maneras:

| | Un PDF por contrato | Todo en un PDF |
|---|---|---|
| Contratos detectados | 12 | 12 |
| Campos leídos con valor | 72 | 72 |
| Campos a revisar | 2 | 2 |
| Lectura OCR | 24,6 s | 27,1 s |
| **Total** | **25,1 s** | **27,6 s** |

Prácticamente idéntico. El costo del OCR es **por página**, no por archivo, así que
partir o juntar no mueve la aguja. Y la segmentación no pierde ni inventa contratos.

**Entonces la decisión no es técnica: es de trabajo.** Y ahí sí hay una diferencia grande.

---

## Lo que sí cambia: volver a escanear

Este es el escenario real. El lunes se escanea una pila. El jueves se rescanea desde la
mitad, por las dudas. Tres contratos quedan en las dos tandas.

| | Un PDF por contrato | Todo en un PDF |
|---|---|---|
| El jueves ingresa | 4 nuevos, **3 reconocidos como ya cargados** | 1 archivo nuevo |
| Vuelve a leer | 4 archivos (8 s) | todo de nuevo (14,7 s) |
| Contratos en la base | **12** ✓ | **15** ✗ |
| Contratos repetidos | **0** | **3** |

Con un PDF por contrato, el sistema reconoce por huella digital los que ya tenía: no los
vuelve a leer y no los cuenta dos veces.

Con todo en un PDF grande, **alcanza una hoja de diferencia** para que sea un archivo
distinto. La huella no lo reconoce, se relee entero, y los tres contratos repetidos
entran otra vez. A partir de ahí los acumulados por persona están inflados y **nadie se
entera**, que es exactamente la clase de error que este sistema existe para evitar.

---

## Qué hace el sistema al respecto

No alcanza con dar el consejo: la gente escanea como puede. Así que:

1. **Separa solo los contratos que vengan juntos.** Detecta dónde arranca cada
   formulario y arma un registro por tramo de páginas, con su rango de fojas. Antes de
   esto, un PDF con cinco contratos producía **un** registro que mezclaba el nombre de
   uno con el monto de otro: un contrato inventado, y sin marca.
2. **Reconoce que una carátula no es un contrato.** Exige el título del formulario *y*
   al menos dos de sus rótulos. Una foja que diga «se agrega copia del contrato de
   locación de servicios» no arranca un contrato fantasma.
3. **Detecta los contratos repetidos** —mismo documento, mismas fechas, mismo monto,
   llegados desde archivos distintos— y los marca. Aparecen en el panel y en la consulta
   `08_contratos_repetidos`.
4. **No los borra ni los suma una sola vez por su cuenta.** Dos contratos con los mismos
   datos también pueden ser dos contratos reales. Los lista para que decida una persona,
   igual que con las fusiones de identidad.

---

## Recomendaciones prácticas

- **Un PDF por contrato** si el escáner lo permite sin costo de tiempo.
- Si no, **un PDF por acta o por tanda chica** (diez, veinte contratos). Achica el daño
  de un rescaneo parcial y hace más liviano volver a procesar si se mejora el perfil de
  extracción.
- **Evitar el PDF único de todo el legajo.** Cualquier corrección obliga a releer todo, y
  cualquier rescaneo parcial duplica.
- El nombre del archivo **no importa**: se guarda igual y el sistema lo indexa por su
  huella digital. Poner el número de contrato en el nombre ayuda a la persona, no al
  programa.
- **Escanear derecho y a 300 DPI** rinde más que cualquier ajuste de software. El límite
  de la lectura lo pone el papel, no el programa.
- Cargar **con el nombre de lote y quién carga**: es lo que después permite decir de
  dónde salió cada cosa.
