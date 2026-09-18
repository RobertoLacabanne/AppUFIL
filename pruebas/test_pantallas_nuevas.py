"""
Las pantallas de foliatura, tablas y cronología: que digan lo que los datos dicen.

Se ejecuta el render de verdad con Node y datos variables, para que la prueba no pueda
pasar porque el JavaScript tenga los números escritos a mano.

Lo que se sostiene acá es sobre todo el vocabulario, que en estas tres pantallas no es
decoración:

  * la foliatura del papel y la página del PDF son dos cosas y se nombran distinto;
  * una foja sin foliatura anotada está «sin detectar», nunca «sin foliar»;
  * una continuidad que nadie confirmó se muestra como propuesta;
  * el desorden cronológico de un expediente armado por incorporación no es un error.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

ESC = ("const esc=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;')"
       ".replaceAll('>','&gt;').replaceAll('\"','&quot;');\n")


def _trozo(desde: str, hasta: str) -> str:
    js = (RAIZ / "ufil/web/app.js").read_text(encoding="utf-8")
    return js[js.index(desde):js.index(hasta)]


def _correr(script: str):
    return subprocess.run(["node", "-e", script], cwd=RAIZ, capture_output=True,
                          text=True, encoding="utf-8")


@unittest.skipUnless(shutil.which("node"), "El render JavaScript requiere Node")
class LasTresPantallas(unittest.TestCase):

    def test_la_foliatura_no_se_confunde_con_la_pagina_del_pdf(self):
        render = _trozo("function marcaDeOrigen(", "async function vFoliatura(")
        self.assertTrue(render.isascii(), "las tildes nuevas van como escapes \\uXXXX")
        script = ESC + render + r"""
const assert=require('node:assert/strict');
for (const n of [3,17,42]) {
  const d={fojas:[
    {pagina_pdf:n, foliaturas:[{serie:'principal',literal:String(n+100),estado:'leida',
      origen:'ocr',confianza:0.81,quien:null}]},
    {pagina_pdf:n+1, foliaturas:[]},
    {pagina_pdf:n+2, foliaturas:[{serie:'expediente_origen',literal:'X'+n,estado:'corregida',
      origen:'humano',confianza:1.0,quien:'Persona '+n}]}],
    saltos:[{clase:'salto',pagina_pdf:n+1,literal:String(n+100),detalle:'faltan '+n+' fojas'}]};
  const h=htmlFoliatura(d);
  // Las dos numeraciones, nombradas distinto.
  assert.ok(h.includes('Página del PDF'), 'nombra la pagina del PDF');
  assert.ok(h.includes('Foliatura del papel'), 'nombra la foliatura');
  // Los datos salen del JSON, no del codigo.
  assert.ok(h.includes(String(n+100)), 'muestra la foliatura ' + (n+100));
  assert.ok(h.includes('Persona '+n), 'dice quien la escribio');
  assert.ok(h.includes('faltan '+n+' fojas'), 'muestra el salto');
  assert.ok(h.includes('expediente_origen'), 'muestra la serie cuando no es la principal');
  // La distincion que importa.
  assert.ok(h.includes('sin detectar'), 'una foja sin foliatura dice «sin detectar»');
  assert.ok(!h.includes('sin foliar'), 'y NUNCA «sin foliar»: eso lo afirma una persona');
  assert.ok(h.includes('confianza 0.81'), 'lo propuesto por el sistema muestra confianza');
}
"""
        r = _correr(script)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_una_continuidad_sin_confirmar_se_muestra_como_propuesta(self):
        render = _trozo("function htmlTabla(", "async function vTablas(")
        self.assertTrue(render.isascii(), "las tildes nuevas van como escapes \\uXXXX")
        script = ESC + render + r"""
const assert=require('node:assert/strict');
for (const n of [2,11,29]) {
  const celdas=[{fila:0,columna:0,texto:'Cabeza '+n,es_encabezado:true},
                {fila:0,columna:1,texto:'Importe',es_encabezado:true},
                {fila:1,columna:0,texto:'Dato '+n,es_encabezado:false},
                {fila:1,columna:1,texto:String(n*7),es_encabezado:false}];
  const propuesta=htmlTabla({id:n,pagina_nro:n,filas:2,columnas:2,confianza:0.61,
                             continua_de:n-1,union_quien:null,celdas});
  assert.ok(propuesta.includes('propone'), 'sin confirmar, es una propuesta');
  assert.ok(propuesta.includes('nadie lo confirm'), 'y dice que nadie la confirmo');
  assert.ok(!propuesta.includes('Persona '+n), 'sin confirmar no hay nadie a quien nombrar');
  const firme=htmlTabla({id:n,pagina_nro:n,filas:2,columnas:2,confianza:0.61,
                         continua_de:n-1,union_quien:'Persona '+n,celdas});
  assert.ok(firme.includes('Persona '+n), 'confirmada, dice quien fue');
  // La tabla se muestra como tabla, con encabezado distinto de los datos.
  assert.ok(firme.includes('<th>Cabeza '+n+'</th>'), 'el encabezado va como th');
  assert.ok(firme.includes('<td>'+(n*7)+'</td>'), 'el dato va como td');
  assert.ok(firme.includes('confianza 0.61'));
  const sola=htmlTabla({id:n,pagina_nro:n,filas:1,columnas:2,confianza:0.5,
                        continua_de:null,union_quien:null,celdas:[]});
  assert.ok(!sola.includes('propone'), 'una tabla sola no propone ninguna union');
  assert.ok(!sola.includes('confirm'), 'ni habla de confirmar nada');
}
"""
        r = _correr(script)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_la_cronologia_usa_las_clases_que_le_da_el_backend(self):
        render = _trozo("function htmlCronologia(", "async function vCronologia(")
        self.assertTrue(render.isascii(), "las tildes nuevas van como escapes \\uXXXX")
        script = ESC + render + r"""
const assert=require('node:assert/strict');
for (const n of [5,23,61]) {
  // Clases inventadas: si la pantalla las muestra, es que salen del JSON.
  const clases=[{clave:'c'+n,que_es:'Clase inventada '+n},
                {clave:'d'+n,que_es:'Otra clase '+n}];
  const d={clases, linea:[
      {fecha:'2019-0'+(n%9+1)+'-01',clase:'c'+n,que_es:'Clase inventada '+n,
       literal:'literal '+n,documento_id:n,tipo:'t',archivo:'<arch>'+n,pagina_nro:n,
       origen:'campo:x'+n,confianza:0.9,nota:null,quien:null},
      {fecha:'2020-01-01',clase:'d'+n,que_es:'Otra clase '+n,literal:null,
       documento_id:n+1,tipo:'t',archivo:'A'+n,pagina_nro:n+1,origen:'humano',
       confianza:1,nota:null,quien:'Persona '+n}],
    desordenes:[{clase:'fuera_de_orden',documento_id:n,archivo:'A'+n,tipo:null,
                 detalle:'normal en un expediente armado por incorporacion'}]};
  const h=htmlCronologia(d,'');
  assert.ok(h.includes('Clase inventada '+n), 'las clases salen del JSON');
  assert.ok(h.includes('Otra clase '+n));
  assert.ok(h.includes('literal '+n), 'muestra lo que dice el papel');
  assert.ok(h.includes('Persona '+n), 'dice quien cargo la fecha a mano');
  assert.ok(h.includes('&lt;arch&gt;'+n), 'escapa el nombre del archivo');
  assert.ok(!h.includes('<arch>'+n));
  assert.ok(h.includes('incorporacion'), 'el desorden se explica, no se denuncia');
  assert.ok(h.includes('no por el orden en que'), 'dice que no es el orden de las fojas');
  // Vacia: lo dice y no deja controles sueltos prometiendo datos.
  const vacia=htmlCronologia({clases,linea:[],desordenes:[]},'');
  assert.ok(vacia.includes('Todav'), 'sin datos, lo dice');
  assert.ok(vacia.includes('estado firme'), 'y explica por que una fecha dudosa no entra');
}
"""
        r = _correr(script)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
