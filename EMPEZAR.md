# Cómo hacerlo andar

Tres pasos. La primera vez tarda unos minutos; después es doble clic.

---

## Windows

**1. Instalar Python** — si ya lo tenés, salteá esto.

Bajalo de **https://www.python.org/downloads/** y en la primera pantalla del
instalador **tildá la casilla «Add Python to PATH»**. Es la de abajo de todo y es
fácil pasarla por alto; sin eso no funciona.

**2. Instalar Tesseract**, que es el programa que lee los escaneos.

Bajalo de **https://github.com/UB-Mannheim/tesseract/wiki** (el archivo
`tesseract-ocr-w64-setup-....exe`). Durante la instalación aparece una pantalla de
idiomas, *Additional language data*: **tildá «Spanish»** y **«Orientation and script
detection»**. Sin el castellano no lee nada.

**3. Instalar el sistema.**

Clic derecho sobre `scripts\instalar.ps1` → **Ejecutar con PowerShell**.

Chequea todo y avisa si falta algo, con el link para bajarlo.

**Listo. De ahí en adelante: doble clic en `scripts\arrancar.bat`.** Se abre solo en
el navegador.

---

## Mac o Linux

```bash
./scripts/instalar.sh      # una sola vez
./scripts/arrancar.sh      # todos los días
```

Si falta Python o Tesseract, el instalador dice exactamente qué comando correr.

---

## Usarlo

Se abre en **http://127.0.0.1:8713**.

1. **Cargar escaneos** → arrastrás los PDF → **Procesar**.
2. Tarda alrededor de dos segundos y medio por foja. Un expediente de 36 fojas es un
   minuto y medio. Podés cerrar la pestaña: el trabajo sigue.
3. **Panel** para ver qué encontró. **Cola de revisión** para resolver lo dudoso, con
   la foja al lado.

---

## Desde el celular, o desde otra computadora de la oficina

En la máquina donde está instalado:

```bash
./scripts/arrancar.sh --red          # Mac o Linux
scripts\arrancar.bat --red           # Windows
```

Muestra en pantalla una dirección y una clave. Desde cualquier celular o PC **de la
misma red** se entra escribiendo esa dirección en el navegador y después la clave.

La clave cambia cada vez que se levanta el sistema. **Los documentos no salen de la
máquina donde está instalado**: los demás equipos sólo ven la pantalla.

---

## Si algo no anda

Corré el diagnóstico y mandá lo que dice:

```bash
python -m ufil.cli diagnostico       # Mac o Linux
.venv\Scripts\python -m ufil.cli diagnostico    # Windows
```

Lista todo lo que el sistema necesita, con el estado de cada cosa y, si falta algo,
qué instalar. Lo mismo está adentro de la app, en **Estado del sistema**.

---

## Lo que conviene saber antes de mirarlo

**Lo que el sistema NO hace, a propósito:** no completa un dato que no pudo leer. Si
no lo puede sostener, lo deja vacío con el motivo y lo manda a la cola de revisión con
la imagen al lado. Va a haber campos vacíos, y eso es la función andando, no una falla.

**El importe manuscrito de las facturas de talonario no se lee.** Está medido: el OCR
devuelve un número equivocado y las tres rutas de lectura coinciden en el error, así que
no habría forma de detectarlo. El sistema se niega a leerlo y muestra el recorte para
que una persona lo cargue. Está explicado en `docs/09-lo-escrito-a-mano.md`.

**La exactitud sobre los contratos todavía no está medida.** Lee nombres, DNI, fechas y
montos, pero nadie cotejó eso contra el papel. Para poder dar un porcentaje hacen falta
unos contratos transcriptos a mano.
