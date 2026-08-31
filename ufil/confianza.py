"""
Qué se puede afirmar y qué no.

Este archivo define la línea más importante del sistema: la que separa un dato que se
puede sumar, cruzar y llevar a un informe, de uno que todavía no.

El problema que resuelve, con el caso que lo hizo evidente
---------------------------------------------------------
Antes de esto, cualquier campo con un valor y sin conflicto abierto entraba a las
vistas. Medido sobre el corpus:

  · Entraban a la tabla de personas nombres como «SOSA, Rosa lI» con confianza 0,31,
    que es basura de OCR, y quedaban como una persona consolidada más.
  · El acumulado mostraba $5.847.000, y adentro había $761.900 de seis montos que en
    ese mismo momento estaban en la cola esperando que alguien los mirara.
  · Y el panel decía que sumaba «sólo los montos que se leyeron con seguridad».

Las tres cosas son la misma: **un valor dudoso presentado como firme**. Es exactamente
lo que este sistema existe para que no pase, y estaba pasando.

La regla
--------
Un campo alimenta resultados FIRMES —personas consolidadas, acumulados,
superposiciones, interpretaciones, totales— solamente si su estado es firme. Todo lo
demás existe, se ve, se cuenta y se puede trabajar, pero en su propia sección, dicha
como lo que es: provisional.

La regla no vive en la interfaz. Vive en la base y en las consultas, porque una regla
que sólo está en la pantalla se saltea sola la próxima vez que alguien escriba un
SELECT.
"""
from __future__ import annotations

# ── Los ocho estados. No hay un noveno, y ninguno es ambiguo ─────────────────
#
# Los tres primeros los pone la máquina; los cuatro siguientes, una persona; el último
# es el estado de algo que todavía nadie miró y que el sistema tampoco pudo resolver.
AUTOMATICO_ALTA     = "automatico_alta"       # la máquina lo leyó y está segura
PENDIENTE_BAJA      = "pendiente_baja"        # la máquina lo leyó y NO está segura
CONFLICTO           = "conflicto"             # las rutas de lectura discrepan
VERIFICADO          = "verificado"            # una persona lo miró y lo dio por bueno
CORREGIDO           = "corregido"             # una persona lo corrigió
ILEGIBLE_CONFIRMADO = "ilegible_confirmado"   # una persona confirmó que no se lee
AUSENTE_CONFIRMADO  = "ausente_confirmado"    # una persona confirmó que no está
NO_REVISADO         = "no_revisado"           # nulo sin valor y sin decisión humana

TODOS = (AUTOMATICO_ALTA, PENDIENTE_BAJA, CONFLICTO, VERIFICADO, CORREGIDO,
         ILEGIBLE_CONFIRMADO, AUSENTE_CONFIRMADO, NO_REVISADO)

# ── Firme: puede sumarse, cruzarse y llevarse a un informe ───────────────────
#
# Sólo tres. Uno lo decidió la máquina con alta confianza y los otros dos los decidió
# una persona. `ilegible_confirmado` y `ausente_confirmado` NO están: son decisiones
# humanas firmes, sí, pero sobre la AUSENCIA de un valor — no aportan un dato que sumar.
FIRMES = frozenset({AUTOMATICO_ALTA, VERIFICADO, CORREGIDO})

# ── Provisional: existe, se ve, se trabaja, pero no se afirma ────────────────
PROVISIONALES = frozenset({PENDIENTE_BAJA, CONFLICTO})

# ── Cerrado sin valor: alguien lo miró y dijo que no hay nada que leer ───────
CERRADOS_SIN_VALOR = frozenset({ILEGIBLE_CONFIRMADO, AUSENTE_CONFIRMADO})

# Lo que espera trabajo humano: es lo que se cuenta como «pendiente de revisión».
PENDIENTES_DE_REVISION = frozenset({PENDIENTE_BAJA, CONFLICTO, NO_REVISADO})

# Puesto por una persona. Sirve para contar «verificados por una persona» y para que
# un reproceso no pise una decisión humana.
HUMANOS = frozenset({VERIFICADO, CORREGIDO, ILEGIBLE_CONFIRMADO, AUSENTE_CONFIRMADO})

ETIQUETAS = {
    AUTOMATICO_ALTA:     "Automático",
    PENDIENTE_BAJA:      "Pendiente",
    CONFLICTO:           "Conflicto",
    VERIFICADO:          "Verificado",
    CORREGIDO:           "Corregido",
    ILEGIBLE_CONFIRMADO: "Ilegible confirmado",
    AUSENTE_CONFIRMADO:  "Ausente confirmado",
    NO_REVISADO:         "Sin revisar",
}

# Qué significa cada uno, para mostrarlo donde haga falta explicarlo.
EXPLICACIONES = {
    AUTOMATICO_ALTA:     "Lo leyó el sistema y las lecturas coincidieron con confianza alta.",
    PENDIENTE_BAJA:      "Lo leyó el sistema pero con confianza baja. No entra en los totales firmes hasta que alguien lo mire.",
    CONFLICTO:           "Las lecturas del sistema no coincidieron. No se elige ninguna: lo decide una persona.",
    VERIFICADO:          "Una persona lo miró contra el documento y lo dio por bueno.",
    CORREGIDO:           "Una persona lo corrigió mirando el documento.",
    ILEGIBLE_CONFIRMADO: "Una persona confirmó que en el documento no se puede leer.",
    AUSENTE_CONFIRMADO:  "Una persona confirmó que en el documento no está.",
    NO_REVISADO:         "El sistema no pudo leerlo y todavía no lo miró nadie.",
}


def es_firme(estado: str | None) -> bool:
    return estado in FIRMES


def espera_revision(estado: str | None) -> bool:
    return estado in PENDIENTES_DE_REVISION


def lo_decidio_una_persona(estado: str | None) -> bool:
    return estado in HUMANOS


def _lista(estados) -> str:
    return ",".join(f"'{e}'" for e in sorted(estados))


# Fragmentos de SQL, para que las consultas no repitan la lista de estados a mano y no
# se desincronicen. Una consulta que se olvide un estado es la forma más fácil de que
# un valor dudoso vuelva a colarse en un total.
SQL_FIRMES = _lista(FIRMES)
SQL_PROVISIONALES = _lista(PROVISIONALES)
SQL_PENDIENTES = _lista(PENDIENTES_DE_REVISION)
SQL_HUMANOS = _lista(HUMANOS)


def clasificar(valor_literal, nulo_motivo, confianza, umbral: float,
               estado_previo: str | None = None) -> str:
    """
    El estado que le corresponde a un campo recién extraído.

    Si una persona ya lo decidió, esa decisión manda: un reproceso no la pisa. Es la
    misma regla que ya sostiene `revision_humana`, dicha una vez y en un solo lugar.
    """
    if lo_decidio_una_persona(estado_previo):
        return estado_previo
    if nulo_motivo == "conflicto":
        return CONFLICTO
    if valor_literal is None:
        return NO_REVISADO
    if confianza is None or confianza < umbral:
        return PENDIENTE_BAJA
    return AUTOMATICO_ALTA
