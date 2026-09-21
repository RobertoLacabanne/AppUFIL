import json
import subprocess
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

def render(script):
    js = (RAIZ/'ufil/web/app.js').read_text(encoding='utf-8')
    
    trozo_utils = js[js.index('const esc ='):js.index('async function api(')]
    trozo_papelera = js[js.index('async function vPapelera()'):js.index('let visorZoom = 1;')]
    trozo_zoom = js[js.index('let visorZoom = 1;'):js.index("if ($('#visor-zoom-in'))")]
    
    mock_dom = """
    let _hash = '#/papelera';
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
        constructor(url) { this.searchParams = new Map(); }
    };
    
    const document = {
        createElement: (t) => ({ querySelector: () => ({}), onclick: null }),
        body: { classList: { add: () => {} } },
        querySelector: (s) => null,
    };
    const _elementos = {};
    function $(s) { return _elementos[s] || null; }
    let _vistaHtml = '';
    const vista = { 
       set innerHTML(v) { _vistaHtml = v; }, 
       get innerHTML() { return _vistaHtml; }, 
       querySelectorAll: (s) => _vistaHtml.includes('b-quitar-arch') && s === '.b-quitar-arch' ? [{dataset:{sha:'abc'}, addEventListener: (e, f) => _elementos['b-quitar-arch']=f}] :
                              _vistaHtml.includes('b-restaurar') && s === '.b-restaurar' ? [{dataset:{sha:'abc'}, addEventListener: (e, f) => _elementos['b-restaurar']=f}] :
                              _vistaHtml.includes('b-destruir') && s === '.b-destruir' ? [{dataset:{sha:'abc'}, addEventListener: (e, f) => _elementos['b-destruir']=f}] : []
    };
    function fmtFechaHora(s) { return s; }
    
    const fmtNum = {format: (n) => String(n)};
    const plural = (n,s,p) => n===1?s:p;
    function sello(t, l) { return `[SELLO ${l}]`; }
    function bloque(t, m, c) { return c; }
    function vistaSinLegajo(m) { _vistaHtml = m; return 'sin_legajo'; }
    function vistaVacia(a,b,c,d,e) { _vistaHtml = d + ' ' + e; return 'vacia'; }
    function tabla(cols, filas) { 
       return filas.map(f => cols.map(c => c.r ? c.r(f) : f[c.k]).join(' | ')).join('\\n');
    }
    
    let lastApiRoute = null;
    let apiCuentasMock = { legajo: 1, documentos: 1 };
    let apiPapeleraMock = { archivos: [{sha256:'abc', nombre:'test.pdf', confirmacion_destruir:'DESTRUIR abc'}], total: 1 };
    let _cambiarHashEnQuitar = false;
    async function api(route, opts) {
        lastApiRoute = route;
        if (route === '/api/cuentas') return apiCuentasMock;
        if (route.startsWith('/api/papelera/archivos')) return apiPapeleraMock;
        if (route === '/api/archivo/quitar') {
            if (_cambiarHashEnQuitar) location.hash = '#/otra-pantalla';
            return {};
        }
        if (route === '/api/archivo/restaurar') return {};
        if (route === '/api/archivo/destruir') return {};
        return {};
    }
    
    let lastDialogoHtml = null;
    let _activeDialogo = null;
    let dialogCloseCalled = false;
    let _rutearLlamado = false;
    async function rutear() { _rutearLlamado = true; }
    async function vIngesta() { _rutearLlamado = true; }
    
    function dialogo(html) {
        lastDialogoHtml = html;
        const form = { querySelector: (s) => ({ onclick: null, disabled: false }), close: () => { dialogCloseCalled = true; }, innerHTML: '' };
        const bQuitar = { onclick: null, disabled: false };
        const bDestruir = { onclick: null, disabled: false };
        const inputDestruir = { value: 'DESTRUIR', oninput: null };
        _activeDialogo = {
            querySelector: (s) => {
                if (s === '#f-quitar-arch') return form;
                if (s === '#b-quitar') return bQuitar;
                if (s === '#conf-destruir') return inputDestruir;
                if (s === '#b-destruir') return bDestruir;
                return form;
            },
            close: () => { dialogCloseCalled = true; },
            innerHTML: html,
            get _bQuitar() { return bQuitar; },
            get _bDestruir() { return bDestruir; },
            get _inputDestruir() { return inputDestruir; }
        };
        return _activeDialogo;
    }
    """
    
    full_script = mock_dom + "\n" + trozo_utils + "\n" + trozo_papelera + "\n" + trozo_zoom + "\n" + script
    r = subprocess.run(['node','-e', full_script], capture_output=True, text=True, encoding='utf-8', cwd=RAIZ)
    if r.returncode: 
        raise AssertionError(r.stdout + '\n' + r.stderr)
    return r.stdout

class PapeleraRender(unittest.TestCase):
    def test_pedir_quitar(self):
        render("""
        (async () => {
            quitarProcesando = false;
            await pedirQuitarArchivo('abc', 'test.pdf', 'QUITAR abc', false, 0);
            assert.ok(lastDialogoHtml.includes('Quitar archivo'));
            assert.ok(lastDialogoHtml.includes('test.pdf'));
        })();
        """)

    def test_procesando_bloquea_quitar(self):
        render("""
        (async () => {
            lastDialogoHtml = null;
            quitarProcesando = false;
            await pedirQuitarArchivo('sha', 'test', 'QUITAR sha', true, 0);
            assert.ok(lastDialogoHtml.includes('Archivo en procesamiento'));
        })();
        """)

    def test_revisiones_humanas_se_informan(self):
        render("""
        (async () => {
            lastDialogoHtml = null;
            quitarProcesando = false;
            await pedirQuitarArchivo('sha', 'test', 'QUITAR sha', false, 42);
            assert.ok(lastDialogoHtml.includes('42 revisiones'));
            assert.ok(lastDialogoHtml.includes('Se conservarán en la papelera') || lastDialogoHtml.includes('Se conservar\\\\u00e1n') || lastDialogoHtml.includes('Se conservar\\u00e1n'));
            assert.ok(!lastDialogoHtml.includes('\\\\u'), "Contiene escapes dobles");
        })();
        """)

    def test_g1_g2_xss_y_apostrofos(self):
        render("""
        (async () => {
            apiPapeleraMock = { archivos: [{sha256:'abc', nombre:"x',globalThis.__x=1,'z.pdf", confirmacion_destruir:''}], total: 1 };
            await vPapelera();
            assert.ok(_vistaHtml.includes('data-sha="abc"'));
            assert.ok(!_vistaHtml.includes('onclick='));
            
            const escaped = esc("x',globalThis.__x=1,'z.pdf <&> \\"");
            assert.ok(escaped.includes('&#39;'));
            assert.ok(escaped.includes('&lt;'));
            assert.ok(escaped.includes('&gt;'));
        })();
        """)

    def test_g10_sin_escapes_unicode(self):
        render("""
        (async () => {
            lastDialogoHtml = null;
            await pedirQuitarArchivo('sha', 'test', 'QUITAR', false, 0);
            assert.ok(!lastDialogoHtml.includes('\\\\u'), "Contiene escapes");
            assert.ok(lastDialogoHtml.includes('Atención') || lastDialogoHtml.includes('Atenci\\u00f3n'));
        })();
        """)
        
    def test_g11_numero_revisiones_json(self):
        render("""
        (async () => {
            apiPapeleraMock = { archivos: [
                {sha256:'1', nombre:'A', tiene_revisiones_humanas: true, decisiones_humanas: 2},
                {sha256:'2', nombre:'B', tiene_revisiones_humanas: true, revisiones: 3},
                {sha256:'3', nombre:'C', tiene_revisiones_humanas: true}
            ], total: 3 };
            await vPapelera();
            assert.ok(_vistaHtml.includes('2 revisiones'));
            assert.ok(_vistaHtml.includes('3 revisiones'));
            assert.ok(_vistaHtml.includes('decisiones humanas'));
        })();
        """)

    def test_g4_doble_clic_un_pedido(self):
        render("""
        (async () => {
            let calls = 0;
            const oldApi = api;
            api = async (route, opts) => {
                if (route === '/api/archivo/quitar') calls++;
                return {};
            };
            quitarProcesando = false;
            await pedirQuitarArchivo('sha', 'test', 'QUITAR', false, 0);
            const p1 = _activeDialogo._bQuitar.onclick();
            const p2 = _activeDialogo._bQuitar.onclick();
            if (p1) await p1;
            if (p2) await p2;
            assert.strictEqual(calls, 1, "Debería mandar un solo pedido");
            api = oldApi;
        })();
        """)

    def test_g5_si_falla_el_refresco_se_dice_sin_decir_que_fallo_la_accion(self):
        # Codex lo vio en el navegador: la restauración salía bien, fallaba el pedido
        # de la lista y el error se escribía en el diálogo ya cerrado. Nadie lo veía.
        render("""
        (async () => {
            location.hash = '#/papelera';
            procesandoAccion = false;
            const oldApi = api;
            api = async (route) => {
                if (route === '/api/archivo/restaurar') return {ok: true};
                throw new Error('GET posterior falló');
            };
            await pedirRestaurarArchivo('abc');
            api = oldApi;
            assert.ok(lastDialogoHtml.includes('El archivo se restauró'), lastDialogoHtml);
            assert.ok(lastDialogoHtml.includes('GET posterior falló'), lastDialogoHtml);
            assert.ok(!lastDialogoHtml.includes('No se pudo completar la acción'),
                      'la restauración salió bien: no se puede decir que falló');
        })();
        """)

    def test_g6_no_perder_lugar(self):
        render("""
        (async () => {
            quitarProcesando = false;
            location.hash = '#/original';
            await pedirQuitarArchivo('sha', 'test', 'QUITAR', false, 0);
            _cambiarHashEnQuitar = true;
            _rutearLlamado = false;
            location.reloaded = false;
            await _activeDialogo._bQuitar.onclick();
            assert.ok(!_rutearLlamado, "NO debería llamar a rutear()");
            assert.ok(!location.reloaded, "NO debería llamar a reload");
        })();
        """)
        
    def test_g7_no_saber_no_es_vacia(self):
        render("""
        (async () => {
            apiPapeleraMock = {}; // Missing archivos
            await vPapelera();
            assert.ok(_vistaHtml.includes('No se pudo cargar') || _vistaHtml.includes('incompleta'));
        })();
        """)
        
    def test_g8_paginacion(self):
        render("""
        (async () => {
            apiPapeleraMock = { archivos: [{sha256:'x', nombre:'X'}], total: 150 };
            location.hash = '#/papelera?desde=100';
            await vPapelera();
            assert.ok(lastApiRoute.includes('desde=100'), "La query dice: " + lastApiRoute);
            assert.ok(_vistaHtml.includes('Mostrando 101–150 de 150') || _vistaHtml.includes('Mostrando 101-150 de 150'));
            
            apiPapeleraMock = { archivos: [{sha256:'x', nombre:'X', paginas: 10, lote: 'L1'}], total: 1 };
            await vPapelera();
            assert.ok(_vistaHtml.includes('10 |'));
            assert.ok(_vistaHtml.includes('L1'));
        })();
        """)
        
    def test_g3_zoom(self):
        render("""
        (async () => {
            _elementos['#visor-img'] = { naturalWidth: 1000, naturalHeight: 1414, style: {} };
            _elementos['#visor-marco'] = { style: {} };
            
            let lienzoStyle = {};
            document.querySelector = (s) => s === '.visor-lienzo' ? { style: lienzoStyle } : null;
            
            visorZoom = 2;
            aplicarZoomVisor();
            
            assert.strictEqual(lienzoStyle.width, '2000px');
            assert.strictEqual(_elementos['#visor-img'].style.width, '100%');
            assert.ok(!_elementos['#visor-img'].style.transform);
            
            visorZoom = 1;
            aplicarZoomVisor();
            assert.strictEqual(lienzoStyle.width, '');
        })();
        """)

    def test_g6_restaurar_redibuja_con_query(self):
        render("""
        (async () => {
            procesandoAccion = false;
            location.hash = '#/papelera?desde=100';
            _cambiarHashEnQuitar = false;
            let papeleraLlamada = false;
            const originalVPapelera = vPapelera;
            vPapelera = async () => { papeleraLlamada = true; };
            await pedirRestaurarArchivo('sha');
            assert.ok(papeleraLlamada, "Debería redibujar incluso si hay query params");
            vPapelera = originalVPapelera;
        })();
        """)

    def test_g8_pagina_vacia_no_es_papelera_vacia(self):
        render("""
        (async () => {
            apiPapeleraMock = { archivos: [], total: 10 };
            location.hash = '#/papelera?desde=100';
            await vPapelera();
            assert.ok(_vistaHtml.includes('No hay archivos en esta'));
            assert.ok(_vistaHtml.includes('primera'));
            
            // Should still say empty if really empty
            apiPapeleraMock = { archivos: [], total: 0 };
            location.hash = '#/papelera?desde=0';
            await vPapelera();
            assert.ok(_vistaHtml.includes('La papelera'));
        })();
        """)
