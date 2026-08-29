#!/usr/bin/env bash
# Descarga las fuentes de la interfaz. Se corre UNA sola vez, en la etapa de
# instalación, en una máquina CON conexión. Después las fuentes quedan versionadas
# en assets/fuentes/ y la aplicación nunca más toca la red (restricción 1).
#
# Las tres familias son de licencia libre (SIL Open Font License 1.1).
set -euo pipefail

DESTINO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/assets/fuentes"
BASE="https://raw.githubusercontent.com/google/fonts/main"

mkdir -p "$DESTINO"

# Archivo (Omnibus-Type, AR) — la aplicación hablando.
# Source Serif 4 (Adobe)      — texto de documento e interpretación.
# IBM Plex Mono (IBM)         — dato leído, con anclaje.
ARCHIVOS=(
  "ofl/archivo/Archivo[wdth,wght].ttf"
  "ofl/archivo/Archivo-Italic[wdth,wght].ttf"
  "ofl/sourceserif4/SourceSerif4[opsz,wght].ttf"
  "ofl/sourceserif4/SourceSerif4-Italic[opsz,wght].ttf"
  "ofl/ibmplexmono/IBMPlexMono-Regular.ttf"
  "ofl/ibmplexmono/IBMPlexMono-Medium.ttf"
  "ofl/ibmplexmono/IBMPlexMono-SemiBold.ttf"
  "ofl/archivo/OFL.txt"
  "ofl/sourceserif4/OFL.txt"
  "ofl/ibmplexmono/OFL.txt"
)

fallo=0
for ruta in "${ARCHIVOS[@]}"; do
  nombre="$(basename "$ruta")"
  # Las licencias comparten nombre de archivo entre familias: se les antepone la familia.
  if [ "$nombre" = "OFL.txt" ]; then
    nombre="OFL-$(basename "$(dirname "$ruta")").txt"
  fi
  # Codificación de corchetes para la URL; en disco se guarda con el nombre original.
  url_ruta="${ruta//\[/%5B}"; url_ruta="${url_ruta//\]/%5D}"

  printf '  %-46s ' "$nombre"
  if curl -fsSL --retry 3 --retry-delay 2 -o "$DESTINO/$nombre" "$BASE/$url_ruta"; then
    printf 'ok  (%s)\n' "$(du -h "$DESTINO/$nombre" | cut -f1)"
  else
    printf 'FALLÓ\n'
    rm -f "$DESTINO/$nombre"
    fallo=1
  fi
done

if [ "$fallo" -ne 0 ]; then
  echo
  echo "Alguna descarga falló. La interfaz igual abre: la hoja de estilos declara una"
  echo "pila de reserva del sistema. Se ve peor, no se rompe."
  exit 1
fi

echo
echo "Listo. $(ls -1 "$DESTINO" | wc -l) archivos en assets/fuentes/"
echo "Versionalos en el repositorio: a partir de acá la aplicación no toca más la red."
