# Instalación en un solo comando, para Windows.
#
# Se corre así: clic derecho sobre este archivo -> "Ejecutar con PowerShell".
# O desde una ventana de PowerShell abierta en la carpeta del proyecto:
#     powershell -ExecutionPolicy Bypass -File scripts\instalar.ps1
#
# Chequea todo, instala lo que falta y deja la app andando. Lo que no puede resolver
# solo, lo dice con el link para bajarlo, en vez de seguir a medias.

$ErrorActionPreference = "Stop"
function Verde($t) { Write-Host "  $t" -ForegroundColor Green }
function Rojo($t)  { Write-Host "  $t" -ForegroundColor Red }
function Gris($t)  { Write-Host "  $t" -ForegroundColor DarkGray }

Set-Location (Join-Path $PSScriptRoot "..")

Write-Host ""
Write-Host "  Sistema de análisis documental - UFIL Paraná"
Write-Host "  Instalación"
Write-Host "  ------------------------------------------------------------"
Write-Host ""

# ── 1. Python ────────────────────────────────────────────────────────────────
$py = $null
foreach ($c in @("python", "python3", "py")) {
  try {
    $v = & $c -c "import sys;print(sys.version_info[0]*100+sys.version_info[1])" 2>$null
    if ($LASTEXITCODE -eq 0 -and [int]$v -ge 311) { $py = $c; break }
  } catch { }
}
if (-not $py) {
  Rojo "Falta Python 3.11 o posterior."
  Write-Host ""
  Write-Host "  Bajalo de:  https://www.python.org/downloads/"
  Write-Host "  IMPORTANTE: al instalarlo, tildá la casilla" -NoNewline
  Write-Host " 'Add Python to PATH' " -ForegroundColor Yellow -NoNewline
  Write-Host "en la primera pantalla."
  Write-Host "  Después cerrá esta ventana, abrí una nueva y volvé a correr esto."
  Write-Host ""
  Read-Host "  Enter para cerrar"
  exit 1
}
Verde ("OK  " + (& $py --version))

# ── 2. Tesseract, con castellano ─────────────────────────────────────────────
$tess = Get-Command tesseract -ErrorAction SilentlyContinue
if (-not $tess) {
  # El instalador de Windows no lo agrega al PATH: se busca donde lo deja.
  foreach ($p in @("$env:ProgramFiles\Tesseract-OCR\tesseract.exe",
                   "${env:ProgramFiles(x86)}\Tesseract-OCR\tesseract.exe",
                   "$env:LOCALAPPDATA\Programs\Tesseract-OCR\tesseract.exe")) {
    if (Test-Path $p) {
      $env:PATH = (Split-Path $p) + ";" + $env:PATH
      $tess = Get-Command tesseract -ErrorAction SilentlyContinue
      Gris "Tesseract encontrado en $(Split-Path $p) (se agregó al PATH de esta sesión)"
      break
    }
  }
}
if (-not $tess) {
  Rojo "Falta Tesseract, que es el programa que lee los escaneos."
  Write-Host ""
  Write-Host "  Bajá el instalador de:"
  Write-Host "     https://github.com/UB-Mannheim/tesseract/wiki" -ForegroundColor Cyan
  Write-Host ""
  Write-Host "  Al instalarlo, en la pantalla de idiomas ('Additional language data')"
  Write-Host "  buscá y tildá:" -NoNewline
  Write-Host " Spanish " -ForegroundColor Yellow -NoNewline
  Write-Host "y" -NoNewline
  Write-Host " Orientation and script detection " -ForegroundColor Yellow -NoNewline
  Write-Host "."
  Write-Host "  Sin el castellano no lee nada."
  Write-Host ""
  Read-Host "  Cuando termines, Enter para cerrar y volvé a correr esto"
  exit 1
}
Verde ("OK  " + ((& tesseract --version 2>&1) | Select-Object -First 1))

$langs = (& tesseract --list-langs 2>&1) -join "`n"
if ($langs -notmatch "(?m)^spa$") {
  Rojo "Tesseract está instalado, pero le falta el castellano."
  Write-Host ""
  Write-Host "  Volvé a correr el instalador de Tesseract y tildá 'Spanish'"
  Write-Host "  en la pantalla de idiomas adicionales."
  Write-Host ""
  Read-Host "  Enter para cerrar"
  exit 1
}
Verde "OK  idioma castellano instalado"

# ── 3. Entorno propio ────────────────────────────────────────────────────────
if (-not (Test-Path ".venv")) {
  Gris "Creando el entorno..."
  & $py -m venv .venv
}
$pip = ".\.venv\Scripts\pip.exe"
$pyv = ".\.venv\Scripts\python.exe"
Gris "Instalando las librerías (tarda un minuto la primera vez)..."
& $pip install --quiet --upgrade pip 2>$null | Out-Null
& $pip install --quiet -r requisitos.txt
if ($LASTEXITCODE -ne 0) {
  Rojo "Falló la instalación de las librerías."
  Read-Host "  Enter para cerrar"
  exit 1
}
Verde "OK  librerías instaladas"

# ── 4. Chequeo final, con el diagnóstico del propio sistema ─────────────────
Write-Host ""
& $pyv -m ufil.cli diagnostico
if ($LASTEXITCODE -ne 0) {
  Write-Host ""
  Rojo "Falta algo. Está listado arriba, con qué instalar en cada caso."
  Read-Host "  Enter para cerrar"
  exit 1
}

Write-Host ""
Write-Host "  ------------------------------------------------------------"
Verde "Listo. De acá en adelante, para levantarlo:"
Write-Host ""
Write-Host "      doble clic en  scripts\arrancar.bat" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Y se abre solo en el navegador."
Write-Host ""
Read-Host "  Enter para cerrar"
