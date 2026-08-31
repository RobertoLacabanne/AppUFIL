@echo off
REM Levanta el sistema. Es lo unico que hace falta hacer todos los dias:
REM doble clic en este archivo.
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo.
  echo   Todavia no esta instalado.
  echo   Corre primero: clic derecho en scripts\instalar.ps1 -^> Ejecutar con PowerShell
  echo.
  pause
  exit /b 1
)
REM El instalador de Tesseract no lo agrega al PATH; se busca donde lo deja.
if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set "PATH=%ProgramFiles%\Tesseract-OCR;%PATH%"
if exist "%ProgramFiles(x86)%\Tesseract-OCR\tesseract.exe" set "PATH=%ProgramFiles(x86)%\Tesseract-OCR;%PATH%"
echo.
echo   Abriendo http://127.0.0.1:8713 en el navegador...
echo   (para cerrar el sistema, cerra esta ventana negra)
echo.
start "" http://127.0.0.1:8713
".venv\Scripts\python.exe" -m ufil.cli servir %*
pause
