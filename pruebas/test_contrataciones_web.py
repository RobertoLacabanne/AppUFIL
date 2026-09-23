import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
import re

RAIZ = Path(__file__).resolve().parents[1]

def render(script):
    js = (RAIZ/'ufil/web/app.js').read_text(encoding='utf-8')
    
    trozo_utils = js[js.index('const esc ='):js.index('async function api(')]
    
    mock_dom = """
    let _hash = '#/contrataciones';
    const location = {
      get hash() { return _hash; },
      set hash(v) { _hash = v; },
      get href() { return 'http://localhost/' + _hash; },
      search: '',
      reloaded: false,
      reload: function() { this.reloaded = true; }
    };
    const window = { 
      location: location,
      document: {}
    };
    
    const URL = class { 
      constructor(u) { this.searchParams = new URLSearchParams(u.split('?')[1]||''); }
    };
    const URLSearchParams = class {
      constructor(q) { this.q = q; }
      get(k) { 
         const m = new RegExp('(?:^|&)'+k+'=([^&]*)').exec(this.q);
         return m ? decodeURIComponent(m[1]) : null;
      }
    };
    
    const console = { log: function(s) { process.stdout.write(s + '\\n'); } };
    
    const api_respuestas = {
      '/api/catalogo/contrataciones': require('./pruebas/fixtures/contrataciones/catalogo.json'),
      '/api/contrataciones?desde=0&limite=100': require('./pruebas/fixtures/contrataciones/contrataciones.json'),
      '/api/contratacion/1': require('./pruebas/fixtures/contrataciones/contratacion_1.json'),
      '/api/precios?desde=0&limite=100': require('./pruebas/fixtures/contrataciones/precios.json'),
      '/api/renglon/1/comparacion?niveles=A,B,C,D,E': require('./pruebas/fixtures/contrataciones/renglon_1.json'),
      '/api/hallazgos?desde=0&limite=100': require('./pruebas/fixtures/contrataciones/hallazgos.json')
    };
    let peticiones_post = [];
    async function api(ruta, opts) {
      if (opts && opts.method === 'POST') {
        peticiones_post.push({ruta, body: opts.body});
        return {ok: true};
      }
      return api_respuestas[ruta];
    }
    
    let redibujos = 0;
    async function redibujarTrasAccion(msg, fn) {
      redibujos++;
      await fn();
    }
    
    let eventListeners = {};
    const document = {
      addEventListener: function(evt, cb) {
         if (!eventListeners[evt]) eventListeners[evt] = [];
         eventListeners[evt].push(cb);
      },
      getElementById: function(id) {
         if (id === 'rev-estado-1') return {value: 'pendiente'};
         if (id === 'rev-nota-1') return {value: 'nota test'};
         return {
            hidden: true,
            style: {},
            classList: { add: function(){} },
            focus: function(){}
         };
      },
      activeElement: null,
      body: { classList: { add: function(){}, remove: function(){} } }
    };
    function $(s) { return document.getElementById(s.slice(1)); }
    
    const vista = { innerHTML: '' };
    
    function bloque(t, m, c) { return c; }
    function vistaVacia(a,b,c,d,e) { vista.innerHTML = d + ' ' + e; return 'vacia'; }
    function tabla(cols, filas) { 
       return filas.map(f => cols.map(c => c.r ? c.r(f) : f[c.k]).join(' | ')).join('\\n');
    }
    const fmtNum = new Intl.NumberFormat('es-AR', {minimumFractionDigits: 2});
    const fmtFechaHora = d => d;
    const fmtFecha = d => d;
    """
    
    idx_abrir = js.find('let catalogoContrataciones = null;')
    trozo_nuevo = js[idx_abrir:]

    full_js = "\n".join([mock_dom, trozo_utils, trozo_nuevo, script])
    
    # Por archivo y no con `node -e`: app.js ya pasa el largo máximo de una línea de
    # comandos de Windows (32.767 caracteres) y el proceso ni arrancaba.
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8',
                                     dir=RAIZ, prefix='.render-') as f:
        f.write(full_js)
    try:
        p = subprocess.run(['node', f.name], capture_output=True, text=True, encoding='utf-8')
    finally:
        os.unlink(f.name)
    if p.returncode != 0:
        raise RuntimeError("Error en Node:\n" + p.stderr)
    return p.stdout

class ContratacionesRender(unittest.TestCase):
    def test_vocabulario_prohibido(self):
        js = (RAIZ/'ufil/web/app.js').read_text(encoding='utf-8')
        terminos = ['fraude', 'delito', 'direccionamiento', 'irregularidad', 'irregular', 'ilícito', 'culpable', 'sospechoso']
        for t in terminos:
            self.assertFalse(re.search(r'\b' + t + r'\b', js, re.IGNORECASE), f"Término prohibido encontrado: {t}")
        for m in re.finditer(r'.{0,15}sobreprecio.{0,15}', js, re.IGNORECASE):
            self.assertTrue('posible' in m.group(0).lower(), "Sobreprecio usado sin posible: " + m.group(0))

    def test_pantalla_contrataciones(self):
        html = render("""
        (async () => {
          await vContrataciones();
          console.log(vista.innerHTML);
        })();
        """)
        self.assertIn("Licitación 1/2026", html)
        # El riel dice qué etapa no consta, y que no constar no es no haber existido.
        self.assertIn("Factura: no consta en lo cargado", html)
        self.assertIn("180.000,00", html)
        
    def test_pantalla_ficha(self):
        html = render("""
        (async () => {
          location.hash = '#/contratacion?id=1';
          await vContratacion();
          console.log(vista.innerHTML);
        })();
        """)
        self.assertIn("Licitación 1/2026", html)
        self.assertIn("Falta Factura", html)
        self.assertIn("no cotizó", html)
        self.assertIn("data-fuente", html)
        
    def test_pantalla_precios(self):
        html = render("""
        (async () => {
          await vPrecios();
          console.log(vista.innerHTML);
        })();
        """)
        self.assertIn("Resma A4", html)
        self.assertIn("1.000,00", html)
        self.assertIn("class=\"enlace-fuente\"", html)  # la foja, a un clic
        
    def test_pantalla_renglon(self):
        html = render("""
        (async () => {
          location.hash = '#/renglon?id=1';
          await vRenglon();
          console.log(vista.innerHTML);
        })();
        """)
        self.assertIn("Nivel A", html)
        self.assertIn("n = 1", html)
        self.assertIn("Distinto producto", html)
        
    def test_pantalla_hallazgos_y_revision(self):
        out = render("""
        (async () => {
          location.hash = '#/hallazgos';
          await vHallazgosContrataciones();
          // Un solo clic tiene que guardar; dos clics seguidos, mandar un solo pedido.
          const boton = { dataset: { guardarHallazgo: '1' }, disabled: false };
          const target = { classList: { contains: () => false },
                          closest: s => s === '[data-guardar-hallazgo]' ? boton : null };
          // Los dos clics llegan mientras el primer pedido sigue en vuelo.
          const oyentes = eventListeners['click'] || [];
          await Promise.all([...oyentes, ...oyentes].map(cb => cb({ target })));
          console.log(JSON.stringify(peticiones_post));
        })();
        """)
        posts = json.loads(out.strip())
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]['ruta'], '/api/hallazgo/1/revision')
        self.assertEqual(json.loads(posts[0]['body'])['estado'], 'pendiente',
                         "el cuerpo viaja como JSON, no como un objeto")

class PantallaSinBackend(unittest.TestCase):
    """Una instalación con la interfaz nueva y sin la ruta nueva no muestra un error."""

    def test_ruta_que_todavia_no_existe_se_dice(self):
        out = render("""
        (async () => {
          api = async (ruta) => {
            if (ruta.startsWith('/api/catalogo/')) return require('./pruebas/fixtures/contrataciones/catalogo.json');
            const e = new Error('ruta desconocida'); e.estado = 404; e.noEncontrado = false; throw e;
          };
          location.hash = '#/contrataciones';
          await vContrataciones();
          console.log(vista.innerHTML);
        })();
        """)
        self.assertIn("Todavía no disponible", out)

    def test_una_contratacion_que_no_existe_sigue_siendo_un_error(self):
        out = render("""
        (async () => {
          api = async (ruta) => {
            if (ruta.startsWith('/api/catalogo/')) return require('./pruebas/fixtures/contrataciones/catalogo.json');
            const e = new Error('no existe esa contratación'); e.estado = 404; e.noEncontrado = true; throw e;
          };
          location.hash = '#/contratacion?id=99';
          try { await vContratacion(); console.log('SIN ERROR'); } catch (e) { console.log('ERROR ' + e.message); }
        })();
        """)
        self.assertIn("ERROR no existe esa contratación", out)


if __name__ == '__main__':
    unittest.main()
