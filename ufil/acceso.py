"""
Acceso desde otro equipo de la misma red (típicamente, un celular).

Por qué existe. En 127.0.0.1 la app la ve sólo quien está sentado en esa máquina, y
alcanza con eso mientras se trabaja en el escritorio. Pero un fiscal que quiere mirar
una superposición parado en un pasillo necesita entrar desde el teléfono, y para eso el
servidor tiene que escuchar en la red de la fiscalía.

Eso cambia quién puede entrar: pasa de «el que está sentado acá» a «cualquiera que esté
en el mismo wifi». Un legajo penal no puede quedar así, entonces el modo red pide una
clave: seis caracteres que se generan en cada arranque y se imprimen una sola vez en la
terminal de quien levantó el servidor.

Lo que esto SÍ resuelve: que un compañero curioso, alguien de otra oficina o un equipo
conectado al mismo wifi no abra el legajo escribiendo una dirección IP.

Lo que esto NO resuelve, y conviene decirlo claro: el tráfico va en HTTP plano. Quien
pueda mirar los paquetes de esa red —un administrador de la red, un equipo intervenido—
puede leer lo que se transmite, la clave incluida. Para eso haría falta HTTPS con un
certificado, y un certificado propio en una máquina sin internet trae su propio lío de
instalación en cada teléfono. La decisión tomada es: modo red para una red de fiscalía
bajo control, y 127.0.0.1 —el modo por omisión— para todo lo demás.
"""
from __future__ import annotations

import html
import ipaddress
import secrets
import socket
import time

# Sin caracteres que se confundan al copiarlos de una pantalla a un teléfono: nada de
# O contra 0, ni I contra 1 contra l.
ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
LARGO = 6

# Tras varios intentos fallidos desde la misma dirección, cada intento nuevo espera.
# No es una cárcel: es hacer que probar un millón de combinaciones deje de ser gratis.
INTENTOS_LIBRES = 5
ESPERA_BASE = 1.5


def es_local(host: str) -> bool:
    """¿La dirección de escucha deja entrar sólo a esta misma máquina?"""
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def direccion_en_la_red() -> str | None:
    """La IP de esta máquina en su red, para poder dictarla. Sin salir a internet."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No se conecta a nada: sólo le pregunta al sistema qué placa usaría. No hay
        # tráfico, así que sirve igual en una máquina sin salida a internet.
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


class Porteria:
    """Guarda la clave del arranque y las sesiones que ya la escribieron."""

    def __init__(self, exigir: bool):
        self.exigir = exigir
        self.clave = "".join(secrets.choice(ALFABETO) for _ in range(LARGO)) if exigir else None
        self.sesiones: set[str] = set()
        self.fallos: dict[str, int] = {}

    def deja_pasar(self, cookie: str | None) -> bool:
        if not self.exigir:
            return True
        if not cookie:
            return False
        # Comparación en tiempo constante contra cada sesión viva: son dos o tres.
        return any(secrets.compare_digest(cookie, s) for s in self.sesiones)

    def abrir(self, intento: str, quien: str) -> str | None:
        """Devuelve el vale de sesión si la clave está bien, o None."""
        fallos = self.fallos.get(quien, 0)
        if fallos >= INTENTOS_LIBRES:
            time.sleep(min(ESPERA_BASE * (fallos - INTENTOS_LIBRES + 1), 20))
        if self.clave and secrets.compare_digest(intento.strip().upper(), self.clave):
            self.fallos.pop(quien, None)
            vale = secrets.token_urlsafe(32)
            self.sesiones.add(vale)
            return vale
        self.fallos[quien] = fallos + 1
        return None


def pagina_de_acceso(error: bool = False) -> bytes:
    """
    Una sola pantalla, sin JavaScript y sin depender de nada del resto de la app: si
    alguien llega acá es porque todavía no tiene permiso para pedir el CSS siquiera.
    """
    aviso = ('<p class="mal">Esa clave no es. Fijate en la pantalla de la computadora '
             'donde levantaste el sistema.</p>') if error else ""
    return f"""<!doctype html>
<html lang="es-AR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Acceso · UFIL</title>
<style>
  /* Las mismas tipografías del sistema, servidas del disco. Si por lo que sea no
     cargan, las de reserva mantienen la pantalla legible. */
  @font-face{{font-family:'Archivo'; src:url('/fuentes/Archivo-Variable.ttf')
    format('truetype-variations'); font-weight:400 700; font-display:swap}}
  @font-face{{font-family:'IBM Plex Mono'; src:url('/fuentes/IBMPlexMono-Regular.ttf')
    format('truetype'); font-weight:400; font-display:swap}}
  :root{{color-scheme:light dark}}
  body{{margin:0; min-height:100vh; display:flex; align-items:center;
    justify-content:center; background:#FCFBF9; color:#1B1D21;
    font-family:'Archivo',ui-sans-serif,system-ui,sans-serif; padding:24px}}
  @media (prefers-color-scheme:dark){{body{{background:#16171A; color:#E6E3DC}}}}
  .caja{{width:100%; max-width:380px}}
  h1{{font-size:19px; margin:0 0 4px; letter-spacing:-.01em}}
  .sub{{font-size:12px; opacity:.7; margin:0 0 22px; line-height:1.5}}
  label{{display:block; font-size:10px; letter-spacing:.12em; text-transform:uppercase;
    opacity:.6; margin-bottom:7px}}
  input{{width:100%; box-sizing:border-box;
    font-family:'IBM Plex Mono',ui-monospace,monospace;
    font-size:24px; letter-spacing:.28em; text-align:center; padding:14px 10px;
    border:1px solid currentColor; background:transparent; color:inherit;
    text-transform:uppercase; min-height:56px}}
  button{{width:100%; margin-top:12px; padding:15px; font-size:14px; cursor:pointer;
    border:1px solid currentColor; background:transparent; color:inherit;
    min-height:52px}}
  .mal{{border-left:3px solid #96301F; padding:8px 12px; font-size:12.5px;
    background:rgba(150,48,31,.08); margin:0 0 16px}}
  .pie{{font-size:11px; opacity:.6; margin-top:26px; line-height:1.6}}
</style></head><body>
<form class="caja" method="post" action="/acceso">
  <h1>Análisis documental</h1>
  <p class="sub">Unidad Fiscal de Investigación y Litigación de Paraná · MPF Entre Ríos</p>
  {aviso}
  <label for="c">Clave de acceso</label>
  <input id="c" name="clave" autocomplete="off" autocapitalize="characters"
         autocorrect="off" spellcheck="false" maxlength="{LARGO}" autofocus>
  <button type="submit">Entrar</button>
  <p class="pie">La clave se genera cada vez que se levanta el sistema y se muestra en
    la terminal de esa computadora. Si no la tenés, pedísela a quien lo levantó.</p>
</form></body></html>""".encode("utf-8")


ANCHO = 58


def texto_de_arranque(puerto: int, clave: str) -> str:
    """El cartel que se ve al levantar el sistema en modo red."""
    ip = direccion_en_la_red() or "<la-ip-de-esta-maquina>"
    def r(texto=""):
        return "  │ " + texto.ljust(ANCHO - 2) + "│"
    return "\n".join([
        "",
        "  ┌─ MODO RED " + "─" * (ANCHO - 12) + "┐",
        r("El sistema quedó visible para los demás equipos de"),
        r("esta red. Para entrar desde un celular, en el navegador:"),
        r(),
        r("    http://" + f"{ip}:{puerto}"),
        r(),
        r("    clave de acceso:   " + clave),
        r(),
        r("La clave cambia cada vez que se levanta el sistema."),
        r("El tráfico va sin cifrar: usalo en la red de la"),
        r("fiscalía, nunca en un wifi abierto."),
        "  └" + "─" * (ANCHO - 1) + "┘",
    ])
