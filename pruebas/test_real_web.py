import subprocess
import unittest
import tempfile
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

def render(script):
    js = (RAIZ/'ufil/web/app.js').read_text(encoding='utf-8')
    
    mock_dom = """
    const document = {
        createElement: (t) => ({ querySelector: () => ({}), onclick: null }),
        getElementById: () => ({}),
        body: { classList: { add: () => {} } },
        querySelectorAll: () => [],
        querySelector: () => ({ checked: false, onchange: null })
    };
    const _elementos = {};
    function $(s) { return _elementos[s] || { classList: {toggle:()=>{}, remove:()=>{}, add:()=>{}}, style: {}, dataset: {}, setAttribute: ()=>{} }; }
    let _vistaHtml = '';
    const vista = { 
       set innerHTML(v) { _vistaHtml = v; }, 
       get innerHTML() { return _vistaHtml; }, 
       querySelectorAll: () => [],
       querySelector: () => ({ checked: false, onchange: null })
    };
    function bloque(t, m, c) { return c; }
    function tabla() { return "TABLA"; }
    let IDENTIDAD = { organismo: 'TEST' };
    function cargarContinuidad() {}
    function cargarRelacionesDocumento() {}
    function preguntarQuienUnaVez() {}
    function vacio(a, b, c) { return `VACIO:${a}:${b}:${c?c.texto:''}`; }
    let TRABAJO = null;
    function sinLegajo() { return false; }
    let _fojaAbierta = null;
    function abrirFojaSuelta(sha, nro) { _fojaAbierta = {sha, nro}; }
    
    // Mock tablaBuscable
    let _tablasLlamadas = [];
    function tablaBuscable(destino, cols, filas, opts) {
        _tablasLlamadas.push({filas: filas.length, opts: opts});
        if (opts.alClic && filas.length > 0) {
            opts.alClic(filas[0]);
        }
    }

    let apiFojasMock = { archivos: [] };
    async function api(route, opts) {
        if (route === '/api/fojas') return apiFojasMock;
        return {};
    }
    """
    
    trozo_utils = js[js.index('const esc ='):js.index('async function api(')]
    trozo_fmt = js[js.index('const fmtNum ='):js.index('const NOMBRE_CAMPO =')]
    trozo_tipo = js[js.index('/* Los tipos de documento'):js.index('/* Por qué está esperando')]
    trozo_estado = js[js.index('/* Estado vacío:'):js.index('function vacio(')]
    trozo_panel = js[js.index('async function vPanel()'):js.index('async function vContratos()')]
    trozo_fojas = js[js.index('async function vFojas()'):js.index('async function vNumeros()')]
    trozo_doc = js[js.index('async function vDocumento(id)'):js.index('async function vCola(campoId)')]
    
    full_script = mock_dom + "\n" + trozo_fmt + "\n" + trozo_tipo + "\n" + trozo_utils + "\n" + trozo_estado + "\n" + trozo_panel + "\n" + trozo_fojas + "\n" + trozo_doc + "\n" + script
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.js', encoding='utf-8', delete=False) as tf:
        tf.write(full_script)
        temp_name = tf.name
    try:
        r = subprocess.run(['node', temp_name], capture_output=True, text=True, encoding='utf-8', cwd=RAIZ)
    finally:
        os.remove(temp_name)
    if r.returncode: 
        raise AssertionError(r.stdout + '\\n' + r.stderr)
    return r.stdout

class LegajoRealRender(unittest.TestCase):
    def test_fojas_paginadas_con_tablabuscable(self):
        render("""
        (async () => {
            const fojas = Array.from({length: 1628}, (_, i) => ({nro: i+1, clase: 'caratula', etiqueta: 'Carátula', apartada: false}));
            apiFojasMock = { 
                archivos: [{
                    sha256: 'abc',
                    archivo: 'sintetico.pdf',
                    de_trabajo: 1628,
                    apartadas: 0,
                    total: 1628,
                    fojas: fojas
                }]
            };
            
            _elementos['#f-trabajo-abc'] = {};
            await vFojas();
            
            if (_tablasLlamadas.length !== 1) throw new Error("No se llamó a tablaBuscable");
            if (_tablasLlamadas[0].filas !== 1628) throw new Error("No pasaron las 1628 filas");
            if (_fojaAbierta.sha !== 'abc' || _fojaAbierta.nro !== 1) throw new Error("alClic no abre la foja correctamente");
        })();
        """)

    def test_vista_vacia_procesando(self):
        render("""
        (async () => {
            TRABAJO = {estado: 'corriendo'};
            vistaVacia('f. 0000', 'R', 'T', 'Cabeza Original', 'Texto Original');
            if (!_vistaHtml.includes('VACIO:Procesando documentos:El sistema está extrayendo datos en este momento. Los resultados van a aparecer acá cuando termine.:')) {
                throw new Error("No muestra mensaje de procesando");
            }
            if (_vistaHtml.includes('Cargar escaneos')) {
                throw new Error("Ofrece cargar escaneos mientras procesa");
            }
        })();
        """)

    def test_numeros_panel_no_engañosos(self):
        render("""
        (async () => {
            const oldApi = api;
            api = async () => ({
                legajo: 1, documentos: 1,
                contratos: 2, comprobantes: 0,
                lote: 'test',
                personas_ambas_camaras: 0,
                superposiciones: 0, fechas_imposibles: 0,
                campos_criticos_total: 15,
                campos_criticos_firmes: 3,
                cobertura_pct: 20,
                a_revisar: 116,
                excluidos: 0,
                destacados: [],
                cobertura: []
            });
            await vPanel();
            api = oldApi;
            
            if (!_vistaHtml.includes('De los <strong>15</strong>\\n        campos críticos\\n        de los contratos')) {
                throw new Error("No distingue campos de contratos");
            }
            if (!_vistaHtml.includes('En todo el legajo, <strong>116</strong>\\n        campos esperan revisión')) {
                throw new Error("No aclara que los 116 son de todo el legajo");
            }
        })();
        """)

    def test_documento_huella_digital(self):
        render("""
        (async () => {
            const oldApi = api;
            api = async () => ({
                documento: {
                    documento_id: 1,
                    tipo: 'contrato_obra',
                    sha256: 'a1b2c3d4e5f6',
                },
                campos: [],
                paginas: [],
                hermanos: [],
                conflictos: {},
                interpretaciones: []
            });
            _elementos['#folio'] = {};
            await vDocumento(1);
            api = oldApi;
            
            if (!_vistaHtml.includes('huella digital a1b2c3d4e5f6')) {
                throw new Error("Sigue diciendo sha256 en vez de huella digital");
            }
        })();
        """)

if __name__ == '__main__':
    unittest.main()
