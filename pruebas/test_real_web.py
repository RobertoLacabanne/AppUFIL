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
    const location = {hash: '#/panel'};
    function sinLegajo() { return false; }
    let _fojaAbierta = null;
    function abrirFojaSuelta(sha, nro) { _fojaAbierta = {sha, nro}; }
    
    // Mock tablaServidor
    let _tablasLlamadas = [];
    function tablaServidor(destino, ruta, clave, cols, opts) {
        _tablasLlamadas.push({ruta, clave, opts});
        if (opts.alClic) {
            // Mock click event for test
            opts.alClic({sha256: 'abc', nro: 1, foja: 1});
        }
    }

    let apiFojasMock = { archivos: [] };
    let apiTrabajo = {total: 0}, apiApartadas = {total: 0};
    async function api(route, opts) {
        if (route === '/api/fojas') return apiFojasMock;
        if (route === '/api/fojas?limite=1&apartadas=no') return apiTrabajo;
        if (route === '/api/fojas?limite=1&apartadas=si') return apiApartadas;
        return {};
    }
    """
    
    trozo_utils = js[js.index('const esc ='):js.index('async function api(')]
    trozo_fmt = js[js.index('const fmtNum ='):js.index('const NOMBRE_CAMPO =')]
    trozo_tipo = js[js.index('/* Los tipos de documento'):js.index('/* Por qué está esperando')]
    trozo_estado = js[js.index('/* Una vista entera en estado vacío'):js.index('/* Estado vacío:')]
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
        """
        1.628 fojas del legajo real: la pantalla no las trae todas, pide la página al
        servidor, separa las de trabajo de las apartadas y dice cuántas hay de cada una.
        """
        render("""
        (async () => {
            apiTrabajo = {total: 990}; apiApartadas = {total: 638};
            location.hash = '#/fojas';
            await vFojas();
            if (_tablasLlamadas.length !== 1) throw new Error("No se llamó a tablaServidor");
            if (_tablasLlamadas[0].ruta !== '/api/fojas?apartadas=no')
                throw new Error("Tiene que abrir en las fojas de trabajo: " + _tablasLlamadas[0].ruta);
            if (!_vistaHtml.includes('990') || !_vistaHtml.includes('638'))
                throw new Error("No dice cuántas de trabajo y cuántas apartadas");
            if (!_fojaAbierta || _fojaAbierta.sha !== 'abc' || _fojaAbierta.nro !== 1)
                throw new Error("El clic no abre la foja");
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
            
            // Los 116 son lecturas con duda de todo el legajo, y se dice qué pasa con
            // ellas: no entran en ningún total hasta que alguien las confirme.
            if (!_vistaHtml.includes('datos leídos con duda')) {
                throw new Error("No dice qué son los 116");
            }
            if (!_vistaHtml.includes('No entran en ningún total hasta que alguien los confirme')) {
                throw new Error("No aclara que lo dudoso no se suma");
            }
            // El resumen es de contrataciones: nada del dominio de un corpus de prueba.
            if (/cámaras|superposiciones más largas/.test(_vistaHtml)) {
                throw new Error("El resumen volvió a hablar del dominio de un corpus de prueba");
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
