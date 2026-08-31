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

import ipaddress
import os
import secrets
import socket
import time
from html import escape as esc

# Sin caracteres que se confundan al copiarlos de una pantalla a un teléfono: nada de
# O contra 0, ni I contra 1 contra l.
ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
LARGO = 6
# Largo mínimo cuando la clave la pone una variable de entorno. Es más alto que el
# generado porque una clave puesta a mano tiende a ser corta y memorable, y esto se
# publica en internet.
LARGO_MINIMO_PUESTA = 12

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


def hace_falta_clave(host: str) -> bool:
    """
    ¿Este arranque tiene que pedir clave?

    La regla por omisión es la dirección de escucha: si el proceso escucha en algo que
    no es loopback, cualquiera de la red llega, y entonces hay clave. Decidirlo así
    —y no con una opción aparte— evita el caso de abrirlo a la red y quedarse sin clave
    por olvido.

    Hay UN caso donde esa regla se equivoca, y es adentro de un contenedor. Ahí el
    proceso está obligado a escuchar en 0.0.0.0 —si escuchara en 127.0.0.1 no lo
    alcanzaría ni el propio Docker—, pero quién llega de verdad no lo decide el
    proceso: lo decide la publicación del puerto, que en docker-compose.yml es
    `127.0.0.1:8713:8713`, o sea sólo esa máquina. Pedir clave ahí sería pedírsela a
    alguien que ya está sentado en la computadora, y mandarlo a buscarla a
    `docker compose logs`.

    Para ese caso, y sólo para ese, está `UFIL_ACCESO=abierto`. Significa: «quién puede
    llegar a este puerto ya está restringido afuera de este proceso». Ponerla en una
    instalación sin contenedor deja el sistema abierto de par en par.
    """
    modo = os.environ.get("UFIL_ACCESO", "auto").strip().lower()
    if modo == "abierto":
        return False
    if modo == "clave":
        return True
    return not es_local(host)


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


def clave_del_arranque() -> str:
    """
    La clave de esta corrida.

    Por omisión se genera al azar y se muestra en el arranque: es lo que corresponde en
    la fiscalía, donde alguien prende el sistema, lee la clave en pantalla y se la dicta
    a quien va a entrar desde el celular. Cambiarla en cada arranque es una ventaja ahí:
    la de ayer no sirve hoy.

    `UFIL_CLAVE` existe para el otro caso: un servicio que se reinicia solo —una nube,
    un `systemd` con restart— donde nadie está mirando la consola. Ahí una clave nueva
    en cada arranque es una clave que nadie llega a leer, y el sistema queda inaccesible
    hasta que alguien vaya a buscarla al log.

    Se exige un mínimo de largo: una clave de cuatro letras en algo publicado a internet
    se adivina sola, y fallar al arrancar es mejor que quedar abierto.
    """
    puesta = os.environ.get("UFIL_CLAVE", "").strip()
    if not puesta:
        return "".join(secrets.choice(ALFABETO) for _ in range(LARGO))
    if len(puesta) < LARGO_MINIMO_PUESTA:
        raise SystemExit(
            f"UFIL_CLAVE tiene {len(puesta)} caracteres y el mínimo es "
            f"{LARGO_MINIMO_PUESTA}. Una clave corta en un servicio que sale a internet "
            f"se adivina sola; preferimos no arrancar antes que quedar abiertos.")
    return puesta.upper()


class Porteria:
    """Guarda la clave del arranque y las sesiones que ya la escribieron."""

    def __init__(self, exigir: bool):
        self.exigir = exigir
        self.clave = clave_del_arranque() if exigir else None
        self.sesiones: set[str] = set()
        self.fallos: dict[str, int] = {}

    def deja_pasar(self, cookie: str | None) -> bool:
        if not self.exigir:
            return True
        if not cookie:
            return False
        # Comparación en tiempo constante contra cada sesión viva: son dos o tres.
        # Se compara en bytes: `compare_digest` sobre texto revienta con cualquier
        # carácter que no sea ASCII, y una cookie la puede escribir cualquiera.
        c = cookie.encode("utf-8", "replace")
        return any(secrets.compare_digest(c, s.encode("utf-8")) for s in self.sesiones)

    def abrir(self, intento: str, quien: str) -> str | None:
        """Devuelve el vale de sesión si la clave está bien, o None."""
        fallos = self.fallos.get(quien, 0)
        if fallos >= INTENTOS_LIBRES:
            time.sleep(min(ESPERA_BASE * (fallos - INTENTOS_LIBRES + 1), 20))
        # En bytes, por lo mismo: si alguien escribe una eñe o un acento en el teclado
        # del teléfono, comparar como texto tira excepción y el pedido termina en un
        # error 500 en vez de en «esa clave no es».
        escrito = intento.strip().upper().encode("utf-8", "replace")
        if self.clave and secrets.compare_digest(escrito, self.clave.encode("ascii")):
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

    Por eso los colores van escritos adentro y no como variables compartidas: no hay
    hoja de estilo que traer. Son los mismos de ufil/web/estilo.css y hay una prueba
    que verifica que no se separen.
    """
    from . import identidad as ident
    d = ident.actual()
    aviso = ('<p class="mal"><b>Esa clave no es.</b> Fijate en la pantalla de la '
             'computadora donde levantaste el sistema.</p>') if error else ""
    firma = ident.firma(d)
    return f"""<!doctype html>
<html lang="es-AR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Acceso · {esc(d['unidad'])}</title>
<meta name="theme-color" content="#23594C">
<style>
  /* Las mismas tipografías del sistema, servidas del disco. Si por lo que sea no
     cargan, las de reserva mantienen la pantalla legible. */
  @font-face{{font-family:'Archivo'; src:url('/fuentes/Archivo-Variable.ttf')
    format('truetype-variations'); font-weight:400 700; font-display:swap}}
  @font-face{{font-family:'IBM Plex Mono'; src:url('/fuentes/IBMPlexMono-Regular.ttf')
    format('truetype'); font-weight:400; font-display:swap}}
  :root{{
    color-scheme:light dark;
    --papel:#FCFBF8; --papel-2:#F2F0E9; --tinta:#0F172A; --tinta-2:#5D6B66;
    --verde:#23594C; --verde-2:#2F7463; --oro:#D7B46A; --rojo:#B71C1C;
    --borde:#70827C; --suave:#F6E9E8;
  }}
  @media (prefers-color-scheme:dark){{:root{{
    --papel:#0B1213; --papel-2:#111C1B; --tinta:#F2F5F2; --tinta-2:#AEBBB7;
    --verde:#72B5A2; --verde-2:#72B5A2; --oro:#E5C57C; --rojo:#F08B8B;
    --borde:#5A7A74; --suave:#2A1A1C;
  }}}}
  *{{box-sizing:border-box}}
  body{{margin:0; min-height:100vh; min-height:100dvh; display:flex; align-items:center;
    justify-content:center; background:var(--papel); color:var(--tinta);
    font-family:'Archivo',ui-sans-serif,system-ui,sans-serif; padding:24px;
    line-height:1.5}}
  .caja{{width:100%; max-width:392px}}
  /* La marca, con la jerarquía completa: organismo, unidad, área, herramienta. */
  .marca{{display:flex; gap:12px; align-items:center; margin-bottom:6px}}
  .mono-marca{{flex:none; width:46px; height:46px; border-radius:9px;
    background:var(--verde); display:grid; place-items:center; color:#F4F8F6}}
  .unidad{{font-size:17px; font-weight:700; letter-spacing:-.01em}}
  .area{{font-size:11px; color:var(--tinta-2)}}
  .organismo{{font-size:11.5px; color:var(--tinta-2); margin:0 0 4px;
    padding-top:10px; border-top:2px solid var(--oro); display:inline-block}}
  h1{{font-size:14px; font-weight:600; margin:18px 0 20px; color:var(--tinta-2)}}
  label{{display:block; font-size:10px; letter-spacing:.12em; text-transform:uppercase;
    color:var(--tinta-2); margin-bottom:7px; font-weight:600}}
  input{{width:100%; font-family:'IBM Plex Mono',ui-monospace,monospace;
    font-size:24px; letter-spacing:.28em; text-align:center; padding:14px 10px;
    border:1px solid var(--borde); border-radius:5px; background:var(--papel-2);
    color:inherit; text-transform:uppercase; min-height:56px}}
  input:focus{{outline:none; border-color:var(--verde-2);
    box-shadow:0 0 0 3px rgba(47,116,99,.22)}}
  button{{width:100%; margin-top:12px; padding:15px; font-size:14px; font-weight:600;
    cursor:pointer; border:1px solid var(--verde); border-radius:5px;
    background:var(--verde); color:var(--papel); min-height:52px}}
  button:hover{{background:var(--verde-2); border-color:var(--verde-2)}}
  .mal{{border-left:3px solid var(--rojo); border-radius:0 5px 5px 0; padding:9px 13px;
    font-size:12.5px; background:var(--suave); margin:0 0 16px; color:var(--tinta)}}
  .mal b{{color:var(--rojo)}}
  .pie{{font-size:11px; color:var(--tinta-2); margin-top:24px; line-height:1.6}}
  .fiscales{{font-size:11px; color:var(--tinta-2); margin-top:8px}}
</style></head><body>
<form class="caja" method="post" action="/acceso">
  <div class="marca">
    <span class="mono-marca" aria-hidden="true">
      <svg viewBox="0 0 32 32" width="26" height="26" fill="none"
           stroke="currentColor" stroke-width="1.7">
        <rect x="5" y="4" width="22" height="24" rx="2"/>
        <path d="M10 4v24"/><path d="M14 11h9" stroke="#D7B46A" stroke-width="2.4"/>
        <path d="M14 16.5h9M14 22h6" stroke-width="1.4"/>
      </svg>
    </span>
    <span>
      <div class="unidad">{esc(d['unidad'])}</div>
      <div class="area">{esc(d['area'])}</div>
    </span>
  </div>
  <p class="organismo">{esc(ident.linea_organismo(d))}</p>
  <h1>{esc(d['sistema'])}</h1>
  {aviso}
  <label for="c">Clave de acceso</label>
  <input id="c" name="clave" autocomplete="off" autocapitalize="characters"
         autocorrect="off" spellcheck="false" maxlength="{LARGO}" autofocus>
  <button type="submit">Entrar</button>
  <p class="pie">La clave se genera cada vez que se levanta el sistema y se muestra en
    la terminal de esa computadora. Si no la tenés, pedísela a quien lo levantó.</p>
  {f'<p class="fiscales">{esc(firma)}</p>' if firma else ''}
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


def como_se_entra(host: str, con_clave: bool) -> dict:
    """
    Un chequeo más para la pantalla de estado: quién puede entrar hoy.

    Son tres situaciones distintas y hay que distinguirlas, porque la del medio es la
    que puede estar mal sin que nadie se entere.
    """
    if con_clave:
        return {"nombre": "Quién puede entrar", "estado": "aviso",
                "detalle": "el sistema está abierto a los demás equipos de la red y pide "
                           "clave de acceso. El tráfico va sin cifrar, así que esto sirve "
                           "en la red de la fiscalía y no en un wifi abierto",
                "arreglo": "para dejarlo sólo en esta computadora, levantarlo sin --red"}
    if es_local(host):
        return {"nombre": "Quién puede entrar", "estado": "ok",
                "detalle": f"sólo quien esté sentado en esta computadora "
                           f"(escucha en {host})", "arreglo": None}
    # Escucha en toda la red y NO pide clave: es el caso del contenedor, donde el
    # puerto está restringido afuera. Si esa restricción no existe, esto está abierto
    # de par en par y nadie lo va a notar. Hay que decirlo.
    return {"nombre": "Quién puede entrar", "estado": "aviso",
            "detalle": f"escucha en {host} SIN pedir clave (UFIL_ACCESO=abierto). Es "
                       f"correcto si el puerto está restringido afuera de este proceso "
                       f"—un contenedor publicado en 127.0.0.1—; si no lo está, "
                       f"cualquiera de la red entra sin nada",
            "arreglo": "comprobar la publicación del puerto en docker-compose.yml, o "
                       "sacar UFIL_ACCESO=abierto"}
