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

VOLUME ["/corpus", "/app/datos"]
ENV UFIL_DATOS=/app/datos PYTHONUNBUFFERED=1
EXPOSE 8713

# Chequeo de arranque: si las invariantes no se cumplen, se ve en el log.
HEALTHCHECK --interval=60s --timeout=10s --start-period=15s \
  CMD python3 -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8713/api/panel')"

CMD ["python3", "-m", "ufil.cli", "servir", "--host", "0.0.0.0", "--puerto", "8713"]
