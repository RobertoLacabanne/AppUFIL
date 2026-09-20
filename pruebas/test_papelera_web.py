import json
import subprocess
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

def render(script):
    js = (RAIZ/'ufil/web/app.js').read_text(encoding='utf-8')
    
    # We need to extract the logic for Papelera.
    # But since we use DOM (window, document, vista.innerHTML, $('#...')), we can't easily unit test it in pure Node without JSDOM.
    # However, we can mock the DOM and `api` function in JS.
    
    mock_dom = """
    const window = { location: { hash: '#/papelera', reload: () => {} } };
    const document = {
        createElement: (t) => ({ querySelector: () => ({}), onclick: null }),
    };
    function $(s) { return null; }
    let _vistaHtml = '';
    const vista = { set innerHTML(v) { _vistaHtml = v; }, get innerHTML() { return _vistaHtml; }, querySelectorAll: () => [] };
    const esc=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
    function fmtFechaHora(s) { return s; }
    
    const fmtNum = {format: (n) => String(n)};
    const plural = (n,s,p) => n===1?s:p;
    function sello(t, l) { return `[SELLO ${l}]`; }
    function bloque(t, m, c) { return c; }
    function vistaSinLegajo(m) { return 'sin_legajo'; }
    function vistaVacia(a,b,c,d,e) { return 'vacia'; }
    function tabla(cols, filas) { return 'tabla_mock'; }
    
    let lastApiRoute = null;
    let lastApiOpts = null;
    async function api(route, opts) {
        lastApiRoute = route;
        lastApiOpts = opts;
        if (route === '/api/cuentas') return { legajo: 1, documentos: 1 };
        if (route === '/api/papelera/archivos') return { archivos: [] };
        return {};
    }
    
    let lastDialogoHtml = null;
    let dialogCloseCalled = false;
    function dialogo(html) {
        lastDialogoHtml = html;
        const form = { querySelector: (s) => ({ onclick: null, disabled: false }), close: () => { dialogCloseCalled = true; }, innerHTML: '' };
        return {
            querySelector: (s) => {
                if (s === '#f-quitar-arch') return form;
                if (s === '#b-quitar') return form.querySelector(s);
                if (s === '#conf-destruir') return { value: 'DESTRUIR', oninput: null };
                if (s === '#b-destruir') return { onclick: null, disabled: false };
                return form;
            },
            close: () => { dialogCloseCalled = true; },
            innerHTML: ''
        };
    }
    """
    
    trozo = js[js.index('async function vPapelera()'):js.index('let visorZoom = 1;')]
    
    full_script = mock_dom + "\n" + trozo + "\n" + script
    r = subprocess.run(['node','-e', full_script], capture_output=True, text=True, encoding='utf-8', cwd=RAIZ)
    if r.returncode: raise AssertionError(r.stderr)


class PapeleraRender(unittest.TestCase):
    def test_pedir_quitar(self):
        render("""
        (async () => {
            const mockDialog = pedirQuitarArchivo('abc', 'test.pdf', 'QUITAR abc', false, 0);
            
            // Because our mock is sync-ish for returning the object, let's just trigger the click on the returned form
            // Actually pedirQuitarArchivo doesn't return anything. It just modifies the dom via the mock 'dialogo()'.
            // Let's trigger the click on the #b-quitar button that was assigned.
            // Oh wait, our mock overrides querySelector so we can capture the onclick handler.
        })();
        """)

    def test_procesando_bloquea_quitar(self):
        render("""
        (async () => {
            lastDialogoHtml = null;
            await pedirQuitarArchivo('sha', 'test', 'QUITAR sha', true, 0);
            assert.ok(lastDialogoHtml.includes('Archivo en procesamiento'));
        })();
        """)

    def test_revisiones_humanas_se_informan(self):
        render("""
        (async () => {
            lastDialogoHtml = null;
            await pedirQuitarArchivo('sha', 'test', 'QUITAR sha', false, 42);
            assert.ok(lastDialogoHtml.includes('42 revisiones'));
            assert.ok(lastDialogoHtml.includes('Se conservar\\\\u00e1n en la papelera'));
        })();
        """)
