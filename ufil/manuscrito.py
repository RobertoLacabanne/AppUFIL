"""
Campos escritos a mano.

Por qué este archivo existe, con el número que lo justifica.

Medido sobre las facturas reales de un expediente de la Cámara de Senadores, en el
campo IMPORTE, escrito con birome adentro de un recuadro —o sea, el mejor caso posible
para un motor de OCR: dígitos claros, sobre línea, sin cursiva—:

    valor real         6.000
    Tesseract lee      6.200      con TRES configuraciones distintas, las tres iguales

Y en las otras cuatro muestras devolvió nada, «7» y «5».

Lo grave no es que se equivoque: es CÓMO se equivoca. Las tres rutas de lectura
coincidieron en el número equivocado. Sin discrepancia no se levanta conflicto, la
confianza queda alta, y $6.200 entra a todos los acumulados como dato firme. En un
legajo por pagos, doscientos pesos por factura multiplicados por cientos de facturas es
un número falso adentro de una pericia, y nadie lo mira.

Entonces la regla es dura y no admite matices:

    UN CAMPO DECLARADO MANUSCRITO NUNCA SE LLENA CON OCR.

Se guarda nulo con motivo `manuscrito` y va derecho a la cola de revisión con el
recorte de la imagen al lado. Eso NO es una limitación disfrazada de virtud: leer
«6.000» de una imagen que se ve al costado cuesta dos segundos, y el sistema queda
diciendo la verdad sobre lo que sabe y lo que no.

Cuando haya un modelo de visión disponible, entra por acá: PROPONE un valor al lado
del recorte y una persona lo confirma. Sigue sin llenarse solo.
"""
from __future__ import annotations

MOTIVO = "manuscrito"

# El texto que ve quien revisa. Tiene que explicar por qué está vacío sin sonar a que
# el sistema se rompió: no se rompió, se negó a adivinar.
EXPLICACION = ("Este campo está escrito a mano. El sistema no lo lee: probado sobre "
               "estas mismas facturas, el OCR devuelve un número equivocado y las tres "
               "rutas coinciden en el error, así que no habría forma de detectarlo. "
               "Miralo en el recorte de al lado y cargalo.")


def es_manuscrito(spec: dict) -> bool:
    """¿El perfil declara este campo como escrito a mano?"""
    return bool(spec.get("manuscrito"))
