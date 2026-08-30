"""
Capa 1b — Lectura de campos escritos a mano, con un modelo de visión.

Qué problema resuelve y por qué no lo resuelve el OCR
-----------------------------------------------------
Medido sobre las facturas reales del expediente, en el campo IMPORTE —birome sobre
recuadro, el mejor caso posible para un motor de OCR—:

    valor real       6.000
    Tesseract lee    6.200      con tres configuraciones distintas, las tres iguales

Las tres rutas coincidieron en el número equivocado, así que no se levanta conflicto y
el valor falso entra como firme. Por eso `ufil/manuscrito.py` le prohíbe a Tesseract
tocar estos campos, y por eso hace falta otra cosa.

Las tres reglas que gobiernan este archivo
------------------------------------------
1. EL MODELO PROPONE, NO DECIDE. Lo que devuelve se guarda como PROPUESTA, en su propia
   tabla, y aparece en la cola de revisión al lado del recorte. El campo sigue nulo con
   motivo `manuscrito` hasta que una persona lo confirma. Un modelo de visión también
   se equivoca; la diferencia con el OCR es que acá el error queda a la vista, contra
   la imagen, en el momento de decidir.

2. SE LE MUESTRA UN RECORTE, NO LA PÁGINA. Se le pregunta por UN campo y se le manda
   sólo ese pedazo de imagen. Preguntar poco y mostrar poco es lo que hace que la
   respuesta sea verificable de un vistazo: quien revisa mira el mismo recorte que miró
   el modelo.

3. TIENE PERMITIDO DECIR QUE NO SABE, y se le pide explícitamente que lo haga. Un
   «no se lee» es una respuesta correcta y barata; un número inventado cuesta una
   pericia. El esquema de salida obliga a elegir entre un valor y `ilegible`.

Sobre la restricción 1 del pliego
---------------------------------
El sistema nació sin salida a internet. Esto la usa, y por lo tanto CONTENIDO DEL
LEGAJO SALE DE LA MÁQUINA: el recorte de la foja viaja al servicio. Es una decisión de
quien conduce la investigación, no del programa, así que:

  · está apagado por omisión y hay que encenderlo a propósito (UFIL_VISION=1);
  · queda registrado qué se mandó, cuándo y de qué foja, en la tabla `propuesta`;
  · «Estado del sistema» lo muestra como aviso mientras esté encendido;
  · apuntando UFIL_VISION_URL a un modelo local, no sale nada de la máquina.
"""
from __future__ import annotations

import base64
import io
import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .db import ahora

# Encendido explícito. Sin esto, el sistema se comporta como siempre: los campos
# manuscritos van a la cola sin propuesta y una persona los tipea.
def encendido() -> bool:
    return os.environ.get("UFIL_VISION", "").strip() in ("1", "si", "true")


MODELO = os.environ.get("UFIL_VISION_MODELO", "claude-opus-5")
# Apuntar a un servidor local (vLLM, Ollama con API compatible) hace que no salga nada
# de la máquina y la restricción 1 siga en pie.
URL_LOCAL = os.environ.get("UFIL_VISION_URL", "").strip()

# Cuánto se agranda el recorte antes de mandarlo. La letra a mano en un escaneo de 200
# DPI queda chica; agrandarla no agrega información pero sí ayuda al modelo, igual que
# ayuda a una persona acercar el papel.
ESCALA_ENVIO = 3.0
LADO_MAXIMO = 1400          # px; más que esto es mandar píxeles de más y pagar de más


class VisionNoDisponible(RuntimeError):
    """No hay lector de manuscrita configurado. No es un error: es el estado normal."""


@dataclass(frozen=True)
class Propuesta:
    valor: str | None          # lo que se leyó, tal cual, o None
    ilegible: bool             # el modelo dijo que no se lee
    nota: str                  # por qué, en una línea
    modelo: str


INSTRUCCION = """Sos un asistente de transcripción para una fiscalía. Se te muestra el
RECORTE de un campo de un documento escaneado. Tenés que transcribir EXACTAMENTE lo que
está escrito ahí, sin interpretarlo ni completarlo.

Reglas:
- Transcribí sólo lo que ves. No completes, no redondees, no corrijas.
- Si el campo trae un importe, transcribí los dígitos y los separadores tal cual están
  escritos, incluido el punto o la coma.
- Si no se lee con seguridad, o si dudás entre dos lecturas posibles, respondé
  ilegible=true. Es la respuesta correcta y esperada cuando el papel no da: acá una
  duda tuya vale más que un número parecido.
- No expliques. No agregues texto fuera del formato pedido."""

ESQUEMA = {
    "type": "object",
    "properties": {
        "valor": {"type": ["string", "null"],
                  "description": "Lo escrito, transcripto tal cual. null si es ilegible."},
        "ilegible": {"type": "boolean",
                     "description": "true si no se lee con seguridad o hay más de una lectura posible."},
        "nota": {"type": "string",
                 "description": "Una línea: qué se ve, o por qué no se lee."},
    },
    "required": ["valor", "ilegible", "nota"],
    "additionalProperties": False,
}


def recorte_a_png(png_pagina: Path, escala: float, caja_pt, margen_pt: float = 6.0) -> bytes:
    """
    Saca el recorte del campo desde el render de la página y lo devuelve en PNG.

    El margen extra es a propósito: la letra a mano se sale del casillero, y un recorte
    justo corta el número. Mejor que sobre papel a que falte un dígito.
    """
    from PIL import Image

    with Image.open(png_pagina) as im:
        x0, y0, x1, y1 = caja_pt
        caja_px = [max(0, int((x0 - margen_pt) * escala)),
                   max(0, int((y0 - margen_pt) * escala)),
                   min(im.width, int((x1 + margen_pt) * escala)),
                   min(im.height, int((y1 + margen_pt) * escala))]
        if caja_px[2] <= caja_px[0] or caja_px[3] <= caja_px[1]:
            raise ValueError("recuadro vacío")
        trozo = im.crop(caja_px).convert("L")
        ancho = min(int(trozo.width * ESCALA_ENVIO), LADO_MAXIMO)
        alto = max(1, int(trozo.height * ancho / trozo.width))
        trozo = trozo.resize((ancho, alto), Image.LANCZOS)
        buf = io.BytesIO()
        trozo.save(buf, "PNG", optimize=True)
        return buf.getvalue()


def _cliente():
    try:
        import anthropic
    except ImportError as e:                     # noqa: PERF203
        raise VisionNoDisponible(
            "falta el paquete `anthropic`. Se instala en la etapa con internet: "
            "pip install anthropic") from e
    if URL_LOCAL:
        # Modelo corriendo en la misma máquina: no sale nada a la red.
        return anthropic.Anthropic(base_url=URL_LOCAL)
    return anthropic.Anthropic()


def leer_recorte(png: bytes, que_campo: str = "un importe") -> Propuesta:
    """
    Le muestra el recorte al modelo y devuelve su PROPUESTA. Nunca un dato.

    Levanta VisionNoDisponible si no está encendido o no hay credencial: el llamador
    sigue de largo y el campo queda como estaba, en la cola para tipear a mano.
    """
    if not encendido():
        raise VisionNoDisponible("el lector de manuscrita está apagado (UFIL_VISION)")

    cliente = _cliente()
    r = cliente.messages.create(
        model=MODELO,
        max_tokens=1024,
        system=INSTRUCCION,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                             "data": base64.standard_b64encode(png).decode()}},
                {"type": "text",
                 "text": f"Este recorte es {que_campo} de un documento de la Legislatura. "
                         f"Transcribí lo que dice, o marcalo ilegible."},
            ],
        }],
        output_config={"format": {"type": "json_schema", "schema": ESQUEMA}},
    )
    texto = next(b.text for b in r.content if b.type == "text")
    d = json.loads(texto)
    return Propuesta(valor=(d.get("valor") or None), ilegible=bool(d.get("ilegible")),
                     nota=str(d.get("nota", ""))[:300], modelo=MODELO)


def guardar_propuesta(cx: sqlite3.Connection, campo_id: int, p: Propuesta) -> None:
    """
    La propuesta va a SU tabla, nunca a `campo`.

    Es la línea que sostiene todo: el carril de datos sigue sin un valor que no haya
    confirmado una persona, y la propuesta existe para ahorrarle tipeo, no para
    reemplazar su decisión.
    """
    cx.execute("""INSERT INTO propuesta (campo_id, valor, ilegible, nota, modelo, creado_en)
                  VALUES (?,?,?,?,?,?)
                  ON CONFLICT(campo_id) DO UPDATE SET
                      valor=excluded.valor, ilegible=excluded.ilegible,
                      nota=excluded.nota, modelo=excluded.modelo,
                      creado_en=excluded.creado_en""",
               (campo_id, p.valor, 1 if p.ilegible else 0, p.nota, p.modelo, ahora()))
    cx.commit()
