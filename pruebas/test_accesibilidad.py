"""
CONTRASTE, medido. WCAG 2.1 nivel AA.

Esto lo va a usar gente que trabaja ocho horas frente a la pantalla, en oficinas con
luz de tubo y monitores viejos, y algunas de esas personas no distinguen el rojo del
verde. «Se ve bien» no es una medición: el contraste se calcula.

AA pide:
  · 4,5:1 para texto normal;
  · 3:1 para texto grande (24px, o 18,66px en negrita);
  · 3:1 para el borde de un control —un campo de formulario cuyo límite no se ve es un
    campo que alguien no encuentra— (criterio 1.4.11, «contraste de lo que no es texto»).
    Los filetes decorativos quedan afuera del criterio a propósito: son adorno, no
    información, y subirles el contraste ensucia la página sin que nadie gane nada.

Se miden los pares que EXISTEN en la interfaz, en los dos temas.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

CSS = (RAIZ / "ufil/web/estilo.css").read_text(encoding="utf-8")


def _rgb(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def luminancia(color: str) -> float:
    def canal(v: int) -> float:
        x = v / 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(v) for v in _rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def relacion(a: str, b: str) -> float:
    la, lb = luminancia(a), luminancia(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _bloque(desde: str) -> str:
    """
    El bloque que arranca en `desde`, hasta su llave de cierre.

    Leer hasta el final del archivo se traga el `@media print`, que redefine `--tinta`
    a negro puro y da contrastes de fantasía. Me pasó midiendo esto: el tema oscuro
    daba 1,16:1 en un par que en realidad da 12,76:1.
    """
    i = CSS.index(desde) + len(desde)
    return CSS[i:CSS.index("}", i)]


def paleta(desde: str) -> dict[str, str]:
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6})", _bloque(desde)))


CLARO = paleta(":root{")
OSCURO = paleta(':root[data-tema="oscuro"]{')

# (texto, fondo, mínimo, dónde se ve)
PARES = [
    ("tinta",   "papel",       4.5, "texto normal"),
    ("tinta",   "papel-2",     4.5, "texto sobre bloque gris"),
    ("tinta-2", "papel",       4.5, "prosa secundaria"),
    ("tinta-2", "papel-2",     4.5, "prosa secundaria sobre gris"),
    ("tinta-3", "papel",       3.0, "rótulos y marginalia"),
    ("sello",   "papel",       4.5, "enlaces y sellos"),
    ("sello",   "papel-2",     4.5, "enlaces sobre gris"),
    ("verde",   "papel",       4.5, "sello «al día»"),
    ("ambar",   "papel",       4.5, "sello de atención"),
    ("lapiz",   "papel",       4.5, "sello de alerta"),
    ("lapiz",   "lapiz-suave", 4.5, "aviso de datos de demostración"),
    ("tinta",   "lapiz-suave", 4.5, "texto del aviso de demostración"),
    ("papel",   "lapiz",       4.5, "número sobre el chip rojo de la barra"),
    ("tinta",   "interp",      4.5, "carril de interpretación"),
    ("tinta-2", "interp",      4.5, "prosa del carril de interpretación"),
    ("sello",   "sello-suave", 4.5, "aviso de foja enderezada"),
    # 1.4.11: el límite de un control tiene que verse, y una barra que informa algo
    # también. La cronología dice qué contratos se pisan: es información, no adorno.
    ("borde-control", "papel",   3.0, "borde de campos, selectores y botones"),
    ("borde-control", "papel-2", 3.0, "borde de controles sobre gris"),
    ("marca",         "papel",   3.0, "barra de contrato en la cronología"),
    ("marca-solape",  "papel",   3.0, "barra de superposición en la cronología"),

    # La barra lateral es verde macizo: no hereda del papel y hay que medirla aparte.
    ("barra-txt",    "barra",   4.5, "ítems de la barra lateral"),
    ("barra-txt-2",  "barra",   4.5, "rótulos de grupo en la barra lateral"),
    ("barra-txt",    "barra-2", 4.5, "el ítem abierto de la barra lateral"),
    ("barra-txt-2",  "barra-2", 4.5, "prosa del ítem abierto"),
    ("barra-txt",    "barra-3", 4.5, "el ítem bajo el puntero"),
    ("oro",          "barra",   3.0, "la marca del ítem activo, sobre el azul"),
    ("barra-filete", "barra",   1.2, "separadores de la barra: adorno, no información"),

    # El dorado sobre el papel da 1,91:1. No puede llevar información y por eso no
    # aparece como par de texto en esta tabla: se usa como filete de adorno al lado
    # de algo que ya está dicho con palabras. La regla se verifica más abajo, en
    # ElDoradoNoLlevaInformacion.
    ("tribunal-txt", "papel",   4.5, "botón principal en texto, y sellos de firme"),
    ("tribunal-txt", "papel-2", 4.5, "botón principal sobre gris"),
    ("papel",      "tribunal-txt", 4.5, "texto del botón principal"),
    ("rio",   "papel",   3.0, "trazos de avance y borde del carril de interpretación"),
    ("rio",   "papel-2", 3.0, "trazos de avance sobre gris"),
    ("interp-filete", "interp", 3.0, "el borde que marca el carril de interpretación"),
    ("tribunal-txt",     "interp", 4.5, "el rótulo de clase dentro del carril"),
    ("ambar",      "ambar-suave", 4.5, "aviso de atención"),
    ("tinta",      "ambar-suave", 4.5, "texto del aviso de atención"),
]


class ElContrasteAlcanzaAA(unittest.TestCase):

    def _revisar(self, tema, nombre):
        flojos = []
        for texto, fondo, minimo, donde in PARES:
            self.assertIn(texto, tema, f"falta --{texto} en el tema {nombre}")
            self.assertIn(fondo, tema, f"falta --{fondo} en el tema {nombre}")
            r = relacion(tema[texto], tema[fondo])
            if r < minimo:
                flojos.append(f"{nombre}: --{texto} sobre --{fondo} da {r:.2f}:1 y "
                              f"pide {minimo}:1 ({donde})")
        self.assertEqual(flojos, [], "\n" + "\n".join(flojos))

    def test_tema_claro(self):
        self._revisar(CLARO, "claro")

    def test_tema_oscuro(self):
        self._revisar(OSCURO, "oscuro")

    def test_los_dos_temas_definen_lo_mismo(self):
        """
        Un token que existe en un tema y no en el otro se resuelve al valor del claro
        y queda ilegible sobre fondo oscuro. Es el defecto que no se ve hasta que
        alguien prende el modo oscuro.
        """
        self.assertEqual(sorted(CLARO), sorted(OSCURO),
                         "los dos temas tienen que definir exactamente los mismos tokens")


def _sin_comentarios(css: str) -> str:
    """El CSS sin comentarios. Un `{` adentro de un comentario le corre el selector a
    cualquier lectura del archivo por expresiones regulares."""
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _resolver(valor: str, tema: dict) -> str | None:
    """Un color de CSS a `#rrggbb`, si se puede. `None` para lo que no se puede medir
    en frío: `currentColor`, `transparent`, `inherit`, `rgba()` con transparencia."""
    v = valor.strip().replace("!important", "").strip()
    m = re.fullmatch(r"var\(--([\w-]+)\)", v)
    if m:
        return tema.get(m.group(1))
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", v):
        return v
    if re.fullmatch(r"#[0-9A-Fa-f]{3}", v):
        return "#" + "".join(c * 2 for c in v[1:])
    return None


class NingunColorEscritoAManoSobreUnFondoDelTema(unittest.TestCase):
    """
    La tabla de PARES mira TOKENS. Un color escrito a mano se le escapa entero, y ahí
    es donde se esconden los peores.

    Pasó de verdad: el atajo «Saltar al contenido» tenía `color:#FFF` sobre
    `background:var(--tribunal)`. En el tema claro `--tribunal` es azul oscuro y el
    blanco daba 12,38:1; en el oscuro el mismo token es azul claro y el mismo blanco
    daba **2,46:1**, la mitad de lo que pide AA. Un token cambia con el tema; un
    `#FFF` escrito a mano, no. Y ese atajo lo usa quien navega con el teclado, que es
    justamente quien menos puede permitirse no leerlo.

    Esta prueba recorre TODA regla que declare color y fondo juntos, resuelva de
    tokens o de literales, y los mide en los dos temas. Es el guardia de la clase
    entera, no del caso que ya apareció.
    """

    LIMPIO = _sin_comentarios(CSS)

    def test_cada_regla_que_declara_color_y_fondo_alcanza_AA(self):
        flojos = []
        for regla in re.finditer(r"([^{}]+)\{([^{}]*)\}", self.LIMPIO):
            selector, cuerpo = regla.group(1).strip(), regla.group(2)
            c = re.search(r"(?<![-\w])color:\s*([^;]+)", cuerpo)
            f = re.search(r"(?<![-\w])background(?:-color)?:\s*([^;]+)", cuerpo)
            if not (c and f):
                continue
            for nombre, tema in (("claro", CLARO), ("oscuro", OSCURO)):
                texto = _resolver(c.group(1), tema)
                fondo = _resolver(f.group(1).split()[0], tema)
                if not (texto and fondo):
                    continue
                r = relacion(texto, fondo)
                if r < 4.5:
                    flojos.append(f"{nombre}: «{selector}» da {r:.2f}:1 "
                                  f"({c.group(1).strip()} sobre {f.group(1).strip()})")
        self.assertEqual(flojos, [], "\n" + "\n".join(flojos))

    def test_la_prueba_esta_mirando_algo(self):
        """
        Una prueba que recorre reglas con una expresión regular deja de encontrarlas
        en silencio si el archivo cambia de forma, y entonces pasa siempre. Que falle
        cuando se queda sin terreno.
        """
        pares = [r for r in re.finditer(r"([^{}]+)\{([^{}]*)\}", self.LIMPIO)
                 if re.search(r"(?<![-\w])color:", r.group(2))
                 and re.search(r"(?<![-\w])background(?:-color)?:", r.group(2))]
        self.assertGreater(len(pares), 15,
                           "la prueba dejó de encontrar reglas: se le movió el terreno")


class ElOscuroEsUnaPaletaYNoDosSueltas(unittest.TestCase):
    """
    El tema oscuro se declara dos veces: una para quien lo tiene puesto en el sistema
    (`prefers-color-scheme`) y otra para quien lo eligió con el botón. Son dos listas
    idénticas de tokens, y por eso mismo se separan solas: se toca una, se olvida la
    otra, y el que eligió el oscuro a mano ve una pantalla distinta que el que lo tiene
    por preferencia del sistema. Que la diferencia la encuentre una prueba y no la
    persona.
    """

    def test_las_dos_declaraciones_del_oscuro_son_iguales(self):
        del_sistema = paleta('@media (prefers-color-scheme:dark){:root:not([data-tema="claro"]){')
        elegido = paleta(':root[data-tema="oscuro"]{')
        self.assertEqual(del_sistema, elegido,
                         "las dos declaraciones del tema oscuro se separaron")
        self.assertTrue(del_sistema, "no se encontró la declaración del oscuro")


class ElDoradoNoLlevaInformacion(unittest.TestCase):
    """
    El dorado da 1,91:1 sobre el papel: es de los colores más lindos de la paleta y
    de los menos legibles. Sirve como filete al lado de algo que ya está dicho con
    palabras, y no sirve para decir nada por su cuenta. La tentación de escribir un
    número en dorado sobre el papel aparece sola, así que queda escrita la regla:
    `--oro` como `color:` sólo puede aparecer dentro de la barra lateral, que es
    azul macizo y ahí da 6,26:1.
    """

    def test_el_oro_como_texto_vive_solo_en_la_barra(self):
        fuera = []
        for regla in re.finditer(r"([^{}]+)\{([^{}]*)\}", CSS):
            selector, cuerpo = regla.group(1).strip(), regla.group(2)
            if re.search(r"(?<!-)\bcolor:\s*var\(--oro\)", cuerpo):
                if "lateral" not in selector and "barra" not in selector:
                    fuera.append(selector)
        self.assertEqual(fuera, [],
                         "el dorado escribe texto fuera de la barra lateral: "
                         + "; ".join(fuera))


class LoQueNoSeDiceSoloConColor(unittest.TestCase):
    """
    Un estado que se distingue SÓLO por el color no existe para quien no distingue ese
    color, ni en una impresión en blanco y negro — y esto se imprime. Cada estado lleva
    además una palabra.
    """

    def test_los_sellos_llevan_texto_ademas_del_color(self):
        js = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")
        # ESTADO mapea cada estado a [etiqueta, tono]: la etiqueta es la palabra.
        estados = re.search(r"const ESTADO = \{(.*?)\n\};", js, re.S)
        self.assertIsNotNone(estados, "no está la tabla de estados")
        from ufil import confianza as cf
        for e in cf.TODOS:
            m = re.search(rf"{e}:\s*\[\s*'([^']+)'", estados.group(1))
            self.assertIsNotNone(m, f"«{e}» no tiene etiqueta en la interfaz")
            self.assertGreater(len(m.group(1)), 2,
                               f"«{e}» se distingue sólo por el color")

    def test_la_tabla_de_salud_no_usa_un_icono_de_color(self):
        """La primera columna de «Estado del sistema» es un sello con palabra."""
        self.assertIn("un sello, no un ícono de color", CSS,
                      "se perdió la razón por la que el estado del sistema usa sellos "
                      "con texto y no puntos de color")

    def test_los_controles_tienen_su_propio_token_de_borde(self):
        """
        Un control se distingue de un filete decorativo. Si los campos volvieran a usar
        `--filete`, su borde daría 1,57:1 y quedaría por debajo del mínimo sin que nada
        falle a la vista.

        La primera versión de esta prueba nombraba tres selectores a mano. Sirvió
        hasta que uno se renombró en un rediseño: la prueba no falló por el borde,
        falló porque no encontró el texto — y peor, dejó de mirar los controles que se
        agregaron después. Ahora busca TODA regla que le ponga borde a un `input`, un
        `select` o un `textarea`, así los que vengan quedan mirados solos.
        """
        flojos = []
        for regla in re.finditer(r"([^{}]+)\{([^{}]*)\}", CSS):
            selector, cuerpo = regla.group(1).strip(), regla.group(2)
            if not re.search(r"\b(input|select|textarea)\b", selector):
                continue
            if not re.search(r"(?<!-)\bborder(-color)?:", cuerpo):
                continue
            if "currentColor" in cuerpo or "transparent" in cuerpo:
                continue
            # Lo que importa no es qué token se usó sino cuánto contrasta. El borde
            # de foco, por ejemplo, usa el verde operativo y está perfecto: da 5,34:1.
            # Verificar el NOMBRE del token en vez del contraste rechazaría eso y
            # aceptaría cualquier token nuevo que resultara ser flojo.
            usados = re.findall(r"border(?:-color)?:[^;]*var\(--([\w-]+)\)", cuerpo)
            for token in usados:
                for nombre, tema in (("claro", CLARO), ("oscuro", OSCURO)):
                    if token not in tema:
                        flojos.append(f"{selector}: --{token} no existe en el {nombre}")
                        continue
                    for fondo in ("papel", "papel-2"):
                        r = relacion(tema[token], tema[fondo])
                        if r < 3.0:
                            flojos.append(f"{selector} ({nombre}): --{token} sobre "
                                          f"--{fondo} da {r:.2f}:1 y pide 3:1")
        self.assertEqual(flojos, [],
                         "bordes de control por debajo del mínimo:\n"
                         + "\n".join(flojos))
        self.assertGreater(
            len([1 for r in re.finditer(r"([^{}]+)\{([^{}]*)\}", CSS)
                 if re.search(r"\b(input|select|textarea)\b", r.group(1))
                 and "var(--borde-control)" in r.group(2)]), 2,
            "la prueba dejó de encontrar controles: se le movió el terreno abajo")


class SeVeEnUnTelefono(unittest.TestCase):
    """44 px es la medida abajo de la cual se falla el toque."""

    def test_los_controles_tienen_tamano_de_dedo(self):
        movil = CSS[CSS.index("@media (max-width:720px){"):]
        self.assertRegex(movil, r"\.boton,\s*\.tecla,\s*\.chip\{min-height:44px",
                         "los botones dejaron de tener 44 px en un teléfono")
        self.assertRegex(movil, r"input,\s*select,\s*textarea\{min-height:44px",
                         "los campos dejaron de tener 44 px en un teléfono")

    def test_el_tipo_de_los_campos_evita_el_zoom_de_ios(self):
        """Con menos de 16px, iOS hace zoom al tocar un campo y descuadra la pantalla."""
        self.assertIn("font-size:16px", CSS)


class LaPuertaDeLaNube(unittest.TestCase):
    """
    Una imagen que se publica a internet no puede venir con la puerta abierta.

    `UFIL_ACCESO=abierto` significa «quién llega a este puerto ya está restringido
    afuera de este proceso». Es cierto en docker-compose.yml, que publica en
    127.0.0.1. En un servicio de nube es falso, y estaba horneada en el Dockerfile:
    cualquier despliegue de esa imagen dejaba el legajo abierto para quien supiera la
    dirección.
    """

    def test_la_imagen_no_trae_la_puerta_abierta(self):
        docker = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
        activa = [l for l in docker.splitlines()
                  if "UFIL_ACCESO" in l and not l.lstrip().startswith("#")]
        self.assertEqual(activa, [],
                         "el Dockerfile fija UFIL_ACCESO: la imagen viaja con la puerta "
                         "abierta a donde sea que la desplieguen")

    def test_compose_la_abre_donde_corresponde_y_lo_dice(self):
        compose = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("UFIL_ACCESO: abierto", compose)
        self.assertIn("127.0.0.1:8713:8713", compose,
                      "compose abre la puerta pero ya no publica sólo en esta máquina")

    def test_el_despliegue_de_nube_pide_clave(self):
        render = (RAIZ / "render.yaml").read_text(encoding="utf-8")
        self.assertIn("value: clave", render,
                      "el despliegue público no está pidiendo clave")
        self.assertNotIn("value: abierto", render)

    def test_el_despliegue_de_nube_tiene_disco(self):
        """
        Sin disco persistente, un `git push` borra las revisiones hechas a mano — lo
        único del sistema que no se puede volver a generar a partir de los originales.
        """
        render = (RAIZ / "render.yaml").read_text(encoding="utf-8")
        self.assertIn("mountPath: /app/datos", render)

    def test_el_puerto_no_esta_clavado(self):
        """Render inyecta PORT. Con el puerto fijo el balanceador no lo encuentra."""
        docker = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("${PORT:-", docker)

    def test_una_clave_corta_no_arranca(self):
        import os
        from ufil import acceso
        previa = os.environ.get("UFIL_CLAVE")
        os.environ["UFIL_CLAVE"] = "1234"
        try:
            with self.assertRaises(SystemExit):
                acceso.clave_del_arranque()
        finally:
            if previa is None:
                os.environ.pop("UFIL_CLAVE", None)
            else:
                os.environ["UFIL_CLAVE"] = previa


if __name__ == "__main__":
    unittest.main(verbosity=2)
