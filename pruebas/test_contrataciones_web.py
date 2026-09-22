import json
import subprocess
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
      '/catalogo/contrataciones': require('./pruebas/fixtures/contrataciones/catalogo.json'),
      '/contrataciones?desde=0&limite=100': require('./pruebas/fixtures/contrataciones/contrataciones.json'),
      '/contratacion/1': require('./pruebas/fixtures/contrataciones/contratacion_1.json'),
      '/precios?desde=0&limite=100': require('./pruebas/fixtures/contrataciones/precios.json'),
      '/renglon/1/comparacion?niveles=A,B,C,D,E': require('./pruebas/fixtures/contrataciones/renglon_1.json'),
      '/hallazgos?desde=0&limite=100': require('./pruebas/fixtures/contrataciones/hallazgos.json')
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
    """
    
    idx_abrir = js.find('let catalogoContrataciones = null;')
    trozo_nuevo = js[idx_abrir:]

    full_js = "\n".join([mock_dom, trozo_utils, trozo_nuevo, script])
    
    p = subprocess.run(['node', '-e', full_js], capture_output=True, text=True, encoding='utf-8')
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
        self.assertIn("Falta Factura", html)
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
        self.assertIn("Ver fuente", html)
        
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
          const target = { classList: { contains: c => c === 'btn-guardar-hallazgo' }, dataset: { id: '1' }, disabled: false };
          for (let cb of eventListeners['dblclick']) {
              await cb({ target });
          }
          console.log(JSON.stringify(peticiones_post));
        })();
        """)
        posts = json.loads(out.strip())
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]['ruta'], '/hallazgo/1/revision')
        self.assertEqual(posts[0]['body']['estado'], 'pendiente')

if __name__ == '__main__':
    unittest.main()
