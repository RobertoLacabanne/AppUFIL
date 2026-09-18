"""
La huella de una foja: reconocer el mismo papel aunque el archivo sea otro.

El sistema ya no cargaba dos veces el MISMO ARCHIVO: se guarda bajo su SHA-256 y un
byte igual al anterior se anota como copia y se sigue. Eso alcanzaba mientras el
material llegara una sola vez y de una sola mano.

No alcanza. Medido sobre el expediente 201.602: abrir el PDF y volver a exportarlo
—que es lo que hace cualquier programa al guardarlo, y lo que hace un portal al
rearmar la descarga— produce **el mismo documento con otro SHA-256**. Mismas 88
páginas, mismos 22.776.043 bytes, otra huella. Cargado de nuevo, el sistema dijo
«nuevos 1» y el legajo quedó con 2 archivos y 176 fojas: el expediente entero
duplicado, sin un solo aviso.

Y en un expediente eso no es una molestia: es un error de fondo. Las mismas fojas dos
veces son los mismos importes contados dos veces, la misma decisión pedida dos veces
en la cola, y —lo peor— dos «documentos» que se pisan en el tiempo porque son el mismo
papel. El sistema encontraría una superposición que no existe y la pondría en un
informe.

Lo que se compara acá es LA FOJA, no el archivo: el dibujo de la página, no los bytes
del PDF que la envuelve. Dos archivos distintos que traen la misma foja tienen la
misma huella de foja.

Cómo, y por qué así
-------------------
La página se dibuja chiquita —24 puntos por pulgada, en gris— y se le saca el SHA-256 a
esos píxeles. Es EXACTO, no parecido: o es el mismo dibujo o no lo es. Eso es
deliberado y es la parte importante.

Una huella «perceptual» —de las que toleran diferencias— reconocería también un
reescaneo del mismo papel, que sería lindo. Pero toleraría de más: dos formularios en
blanco del mismo modelo, dos dorsos en blanco, dos carátulas del mismo expediente son
casi idénticos a los ojos de un algoritmo así. Declarar «es el mismo papel» sobre dos
fojas distintas, en un legajo penal, es peor que no decir nada: haría desaparecer
prueba. Entre pasar por alto un reescaneo y borrar una foja legítima, el sistema
prefiere lo primero, y lo dice.

A 24 dpi una A4 son unos 200×280 píxeles: suficiente para que dos fojas distintas casi
nunca coincidan, y barato. Medido sobre las 88 páginas del expediente: 0,53 s el
archivo entero, contra 119 s que cuesta leerlo. No se nota.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import fitz

# Chico, pero no tanto como para que dos fojas distintas se confundan. A 24 dpi una
# hoja A4 entra en unos 200×280 píxeles en gris.
DPI_HUELLA = 24


def de_pixmap(pix) -> str:
    """La huella de un dibujo ya renderizado."""
    h = hashlib.sha256()
    # El tamaño entra en la huella: dos páginas con los mismos bytes de píxel pero
    # distinto alto no son la misma foja.
    h.update(f"{pix.width}x{pix.height}:".encode())
    h.update(pix.samples)
    return h.hexdigest()


# Una foja con menos tinta que esto no prueba nada. Ver `de_pagina`.
#
# El número sale de medir el expediente 201.602 a esta misma resolución: los 44 dorsos
# en blanco dieron entre 0,00076 y 0,0046 —lo que traen es suciedad de escáner— y los
# 44 frentes, entre 0,047 y 0,71. El corte en 0,01 está el doble por encima del dorso
# más sucio y casi cinco veces por debajo del frente más flojo.
TINTA_MINIMA = 0.01

# Traducir y contar es trabajo del intérprete de C. Recorrer 56.000 bytes por página en
# Python, ochenta y ocho veces por archivo, no.
_OSCUROS = bytes(1 if v < 200 else 0 for v in range(256))


def tinta(pix) -> float:
    """Qué proporción del dibujo es oscura. Entre 0 y 1."""
    datos = pix.samples
    if not datos:
        return 0.0
    return datos.translate(_OSCUROS).count(1) / len(datos)


def de_pagina(pagina) -> str:
    """
    La huella de una página abierta con PyMuPDF, o `""` si la foja está en blanco.

    Un dorso en blanco NO tiene huella, y eso es a propósito. Dos hojas en blanco se
    parecen entre sí más que ninguna otra cosa —en un PDF generado son idénticas
    píxel por píxel—, así que contarlas como coincidencia diría «este expediente ya
    estaba» por cuarenta y cuatro dorsos vacíos. Una foja en blanco no es prueba de
    nada: ni de que el papel esté repetido ni de que no.

    (En este expediente los dorsos NO coinciden entre sí, porque cada uno trae su
    propia suciedad de escáner. Pero apoyarse en eso sería apoyarse en la mugre.)
    """
    pix = pagina.get_pixmap(dpi=DPI_HUELLA, colorspace=fitz.csGRAY)
    if tinta(pix) < TINTA_MINIMA:
        return ""
    return de_pixmap(pix)


def del_archivo(ruta: Path) -> list[str]:
    """Las huellas de todas las fojas de un PDF, en orden."""
    with fitz.open(ruta) as doc:
        return [de_pagina(p) for p in doc]


def cotejar(cx, huellas: list[str], sha_propio: str | None = None) -> dict:
    """
    Cuáles de estas fojas YA ESTÁN en el legajo, y dónde.

    Devuelve:
        total       cuántas fojas trae el archivo, todas
        con_huella  cuántas de ésas se pueden comparar (las que no están en blanco)
        repetidas   cuántas de las comparables ya estaban
        nuevas      cuántas de las comparables NO estaban
        donde       [(foja nueva, archivo donde ya estaba, foja de allá), ...]
        archivos    qué archivos del legajo aportan fojas repetidas, y cuántas
        mismo_que   el archivo del que éste es una copia entera, o None

    No decide nada por su cuenta. Un solapamiento puede ser un error —el mismo
    expediente cargado dos veces— o puede ser lo correcto: dos partes de un expediente
    comparten la foja del empalme, y eso es así en el papel. Quien carga sabe cuál de
    las dos cosas es; el sistema tiene que avisarle, no elegir por él.
    """
    total = len(huellas)
    con_huella = sum(1 for h in huellas if h)
    vacio = {"total": total, "con_huella": con_huella, "repetidas": 0,
             "nuevas": con_huella, "donde": [], "archivos": [], "mismo_que": None}
    if not con_huella:
        return vacio

    donde: list[tuple[int, str, int]] = []
    archivos: dict[str, dict] = {}
    for i, h in enumerate(huellas, start=1):
        if not h:
            continue
        r = cx.execute(
            """SELECT p.nro, a.nombre, a.sha256, a.paginas
                 FROM pagina p JOIN archivo a ON a.sha256 = p.sha256
                WHERE p.huella = ? AND (? IS NULL OR p.sha256 <> ?)
                ORDER BY a.ingerido_en LIMIT 1""",
            (h, sha_propio, sha_propio)).fetchone()
        if not r:
            continue
        donde.append((i, r["nombre"], r["nro"]))
        d = archivos.setdefault(r["sha256"], {"archivo": r["nombre"], "fojas": 0,
                                              "paginas": r["paginas"]})
        d["fojas"] += 1

    repetidas = len(donde)
    # ── ¿Es una copia ENTERA de un archivo que ya está? ───────────────────────
    # Tres condiciones, y hacen falta las tres. El archivo tiene que tener la misma
    # cantidad de fojas que aquel, TODAS sus fojas comparables tienen que estar en
    # aquel, y no puede traer ni una foja comparable que aquel no tenga.
    #
    # La tercera es la que evita el accidente grave. Las fojas en blanco no se pueden
    # comparar —no tienen huella— así que si alcanzara con «todo lo comparable ya
    # estaba», un archivo de ocho fojas donde cuatro son del empalme y cuatro son
    # nuevas pero casi vacías se declararía copia entera y se tiraría. Eso es hacer
    # desaparecer prueba, que es lo peor que puede hacer este sistema. Probado: pasaba.
    mismo_que = None
    for sha, d in archivos.items():
        if d["fojas"] == con_huella and d["paginas"] == total:
            mismo_que = d["archivo"]
            break

    return {"total": total, "con_huella": con_huella, "repetidas": repetidas,
            "nuevas": con_huella - repetidas, "donde": donde,
            "archivos": sorted(archivos.values(), key=lambda x: -x["fojas"]),
            "mismo_que": mismo_que}


def veredicto(cotejo: dict) -> str:
    """
    `nuevo`, `parcial` o `repetido`. Tres palabras, para que la pantalla no tenga que
    repetir la cuenta en cada lugar donde la muestra.

    `repetido` es el único que hace que un archivo NO se guarde, así que es el único
    que exige estar seguro: copia entera de un archivo que ya está. Todo lo demás se
    guarda y se avisa, porque entre cargar algo dos veces —que se ve, se cuenta y se
    puede borrar— y perder una foja, lo segundo no tiene vuelta.
    """
    if cotejo.get("mismo_que"):
        return "repetido"
    return "parcial" if cotejo["repetidas"] else "nuevo"
