# Imagen del sistema de análisis documental — UFIL Paraná.
#
# Se construye UNA vez en una máquina con internet, se exporta con `docker save` y
# viaja en un disco externo. En la fiscalía no se descarga nada.
FROM python:3.12-slim-bookworm

# Tesseract con el paquete de castellano. Es la ruta de OCR en CPU.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/*

# Usuario sin privilegios. Importa de verdad: los originales se guardan en modo 0444,
# y root ignora ese permiso. Corriendo como `ufil`, un intento de sobrescribir un
# original falla de entrada en vez de depender de que después lo detecte `verificar`.
RUN useradd --create-home --uid 10001 ufil

WORKDIR /app
COPY requisitos.txt .
RUN pip install --no-cache-dir -r requisitos.txt

COPY ufil/ ./ufil/
COPY assets/ ./assets/
COPY scripts/ ./scripts/
COPY pruebas/ ./pruebas/
COPY herramientas/ ./herramientas/

# El corpus se monta en solo lectura (restricción 2); los derivados van a /app/datos.
RUN mkdir -p /app/datos && chown -R ufil:ufil /app
USER ufil

# `/corpus` se monta de afuera en solo lectura. `/app/datos` NO se declara acá, y es
# a propósito: `VOLUME` hace que el motor de contenedores cree un **volumen anónimo**
# en ese camino, que aparece como punto de montaje —igual que un disco de verdad— y se
# destruye junto con el contenedor. O sea, en cada despliegue.
#
# Eso costó un legajo con dieciocho documentos y setenta y siete campos revisados a
# mano: se creaba, andaba todo bien, y al siguiente despliegue no estaba. Y como el
# volumen anónimo se ve como un montaje propio, cualquier comprobación que mire
# `/proc/self/mounts` contesta que los datos están a salvo.
#
# Dónde vive `/app/datos` lo declara quien corre la imagen, explícitamente:
# docker-compose lo mapea a `./datos` del host, y en Render se monta un disco en
# Settings → Disks. Si nadie lo declara, es almacenamiento efímero — y ahora el
# sistema lo dice, porque cuenta los arranques que sobrevivió en vez de deducirlo
# (ver ufil/permanencia.py).
VOLUME ["/corpus"]

# OJO CON `UFIL_ACCESO`. Esta imagen NO la trae, y es a propósito.
#
# Adentro de un contenedor el proceso está obligado a escuchar en 0.0.0.0 —si escuchara
# en 127.0.0.1 no lo alcanzaría ni el propio Docker—, así que la regla normal («escucha
# hacia afuera, entonces pide clave») no puede decidir sola. Quién llega de verdad lo
# decide la PUBLICACIÓN DEL PUERTO, que es cosa de quien corre la imagen y no de la
# imagen.
#
# `UFIL_ACCESO=abierto` significa «quién puede llegar a este puerto ya está restringido
# afuera de este proceso». Eso es cierto en docker-compose.yml, que publica en
# `127.0.0.1:8713:8713` —sólo esa máquina— y por eso la variable está ahí, tres líneas
# abajo de la publicación que la justifica.
#
# NO es cierto en un servicio de nube: ahí el puerto sale a internet. Con la variable
# horneada acá, cualquier despliegue de esta imagen en Render, Fly, una VM o un
# `docker run -p 0.0.0.0:8713:8713` dejaba el legajo abierto para cualquiera que supiera
# la dirección, sin ninguna puerta. Por omisión la imagen pide clave, que es lo que
# corresponde cuando no se sabe quién puede llegar.
ENV UFIL_DATOS=/app/datos PYTHONUNBUFFERED=1
EXPOSE 8713

# El puerto sale de PORT si está —Render, Fly y compañía lo inyectan y esperan que el
# proceso escuche ahí—, y si no del 8713 de siempre. Con el puerto clavado, el servicio
# arranca bien y el balanceador no lo encuentra nunca.
ENV UFIL_PUERTO=8713

# Chequeo de arranque: si las invariantes no se cumplen, se ve en el log.
HEALTHCHECK --interval=60s --timeout=10s --start-period=15s \
  CMD python3 -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT',os.environ.get('UFIL_PUERTO','8713'))+'/api/panel')"

CMD ["sh", "-c", "exec python3 -m ufil.cli servir --host 0.0.0.0 --puerto ${PORT:-$UFIL_PUERTO}"]
